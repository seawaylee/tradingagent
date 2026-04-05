import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tradingagents.agent_core.types import AgentExecutionContext, AgentRunRequest, DecisionAction
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.implementations.trading_agents import TradingAgentsAgent


class _StubGraph:
    def propagate(self, symbol: str, trade_date: str):
        final_state = {
            "final_market_report": f"{symbol} market",
            "final_sentiment_report": f"{symbol} sentiment",
            "final_news_report": f"{symbol} news",
            "final_fundamentals_report": f"{symbol} fundamentals",
            "final_investment_plan_report": f"{symbol} research",
            "final_trader_investment_plan_report": f"{symbol} trader",
            "final_trade_decision": f"{symbol} decision",
            "final_trade_decision_report": f"{symbol} portfolio",
        }
        return final_state, "SELL"


class ReportPersistenceTest(unittest.TestCase):
    def test_trading_agents_agent_persists_cli_style_report_for_code_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DEFAULT_CONFIG.copy()
            config.update(
                {
                    "report_output_dir": str(Path(temp_dir) / "reports"),
                }
            )
            agent = TradingAgentsAgent(config=config)
            context = AgentExecutionContext(
                config=config,
                data_tools=None,
                market_tools=None,
            )

            with patch.object(TradingAgentsAgent, "_get_graph", return_value=_StubGraph()):
                result = agent.run(
                    AgentRunRequest(symbol="600570", trade_date="2026-04-03"),
                    context,
                )

            self.assertEqual(result.decision.action, DecisionAction.SELL)
            self.assertIn("report_dir", result.outputs)
            self.assertIn("report_file", result.outputs)

            report_dir = Path(result.outputs["report_dir"])
            report_file = Path(result.outputs["report_file"])

            self.assertTrue(report_dir.exists())
            self.assertTrue(report_file.exists())
            self.assertTrue((report_dir / "1_analysts" / "market_report.md").exists())
            self.assertTrue((report_dir / "1_analysts" / "sentiment_report.md").exists())
            self.assertTrue((report_dir / "1_analysts" / "news_report.md").exists())
            self.assertTrue((report_dir / "1_analysts" / "fundamentals_report.md").exists())
            self.assertTrue((report_dir / "2_research" / "investment_plan.md").exists())
            self.assertTrue((report_dir / "3_trading" / "trader_investment_plan_report.md").exists())
            self.assertTrue((report_dir / "4_portfolio" / "final_trade_decision_report.md").exists())
            self.assertIn("600570", report_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
