import tempfile
import unittest
from pathlib import Path

import pandas as pd

from tradingagents.agent_core import BaseAgent
from tradingagents.agent_core.types import (
    AgentDecision,
    AgentExecutionContext,
    AgentRunRequest,
    AgentRunResult,
    DecisionAction,
)
from tradingagents.backtesting import BacktestEngine
from tradingagents.data_tools import (
    CachedDataToolExecutor,
    DataCollectionJob,
    DataCollectionService,
    DataToolDefinition,
    DataToolRegistry,
    LocalArtifactStore,
)
from tradingagents.market_tools import LocalMarketDataToolbox
from tradingagents.platform import TradingPlatform


class _CountingTool:
    def __init__(self):
        self.calls = 0

    def __call__(self, symbol: str) -> str:
        self.calls += 1
        return f"{symbol}-call-{self.calls}"


class _MockAgent(BaseAgent):
    def __init__(self, name: str = "mock_agent"):
        super().__init__(name)

    def run(self, request: AgentRunRequest, context: AgentExecutionContext) -> AgentRunResult:
        decision = AgentDecision(
            agent_name=self.name,
            symbol=request.symbol,
            trade_date=request.trade_date,
            action=DecisionAction.HOLD,
            rationale="测试 Agent 独立运行。",
        )
        return AgentRunResult(agent_name=self.name, decision=decision, outputs={"ok": True})


class PlatformArchitectureTest(unittest.TestCase):
    def test_data_tool_executor_uses_cache_and_snapshots(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            counter = _CountingTool()
            registry = DataToolRegistry()
            registry.register(
                DataToolDefinition(
                    name="counting_tool",
                    handler=counter,
                    description="计数测试工具",
                )
            )
            store = LocalArtifactStore(
                cache_dir=str(Path(temp_dir) / "cache"),
                snapshot_dir=str(Path(temp_dir) / "snapshots"),
            )
            executor = CachedDataToolExecutor(registry, store)
            collector = DataCollectionService(executor)

            first = executor.execute("counting_tool", symbol="000001.SZ")
            second = executor.execute("counting_tool", symbol="000001.SZ")
            collected = collector.collect(
                DataCollectionJob(
                    tool_name="counting_tool",
                    params={"symbol": "000001.SZ"},
                    snapshot_group="daily",
                    snapshot_date="2026-04-02",
                )
            )

            self.assertFalse(first.from_cache)
            self.assertTrue(second.from_cache)
            self.assertEqual(counter.calls, 1)
            self.assertEqual(first.value, second.value)
            self.assertIsNotNone(collected.snapshot_path)
            self.assertTrue(Path(collected.snapshot_path).exists())

    def test_market_tools_and_backtest_engine_work_with_local_ticks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            toolbox = LocalMarketDataToolbox(temp_dir)
            ticks = pd.DataFrame(
                {
                    "timestamp": [
                        "2026-04-02 09:30:00",
                        "2026-04-02 09:30:30",
                        "2026-04-02 09:31:00",
                        "2026-04-02 09:31:30",
                    ],
                    "price": [10.0, 10.2, 10.5, 10.7],
                    "volume": [100, 200, 150, 300],
                }
            )
            toolbox.save_ticks("600519.SH", "2026-04-02", ticks)

            bars = toolbox.build_bars("600519.SH", "2026-04-02", rule="1min")
            engine = BacktestEngine(toolbox)
            decision = AgentDecision(
                agent_name="demo",
                symbol="600519.SH",
                trade_date="2026-04-02",
                action=DecisionAction.BUY,
                holding_period_bars=1,
            )
            result = engine.backtest_decision(decision, bar_rule="1min")

            self.assertEqual(len(bars), 2)
            self.assertTrue(result.executed)
            self.assertGreater(result.return_pct, 0)
            self.assertAlmostEqual(result.entry_price, 10.0)
            self.assertAlmostEqual(result.exit_price, 10.7)

    def test_platform_registers_and_runs_independent_agents(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = {
                "local_data_dir": temp_dir,
                "data_tools_cache_dir": str(Path(temp_dir) / "data_tools" / "cache"),
                "data_tools_snapshot_dir": str(Path(temp_dir) / "data_tools" / "snapshots"),
                "market_data_dir": str(Path(temp_dir) / "market_tools"),
                "agent_output_dir": str(Path(temp_dir) / "agents"),
                "backtest_output_dir": str(Path(temp_dir) / "backtests"),
                "report_output_dir": str(Path(temp_dir) / "reports"),
                "data_cache_dir": str(Path(temp_dir) / "legacy_cache"),
            }
            platform = TradingPlatform(config=config)
            platform.register_agent(_MockAgent())

            result = platform.run_agent(
                "mock_agent",
                AgentRunRequest(symbol="000001.SZ", trade_date="2026-04-02"),
            )

            self.assertEqual(result.agent_name, "mock_agent")
            self.assertEqual(result.decision.action, DecisionAction.HOLD)
            self.assertTrue(result.outputs["ok"])


if __name__ == "__main__":
    unittest.main()
