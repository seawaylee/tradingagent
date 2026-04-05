from typing import Any

from tradingagents.agent_core import AgentExecutionContext, AgentRegistry, AgentRunRequest, AgentRunResult, BaseAgent
from tradingagents.backtesting import BacktestEngine, BacktestReport
from tradingagents.data_tools import (
    CachedDataToolExecutor,
    DataCollectionJob,
    DataCollectionService,
    DataToolDefinition,
    configure_default_data_executor,
    create_default_data_tool_registry,
)
from tradingagents.data_tools.storage import LocalArtifactStore
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.market_tools import LocalMarketDataToolbox
from tradingagents.dataflows.config import set_config


class TradingPlatform:
    """组合数据工具、市场工具、Agent 与回测层的新平台入口。"""

    def __init__(self, config: dict[str, Any] | None = None):
        """
        初始化平台并装配默认组件。

        参数：
            config: 可选运行时配置。

        返回：
            None: 无返回值。
        """
        self.config = DEFAULT_CONFIG.copy()
        if config:
            self.config.update(config)
        set_config(self.config)
        self._ensure_directories()

        self.data_tool_registry = create_default_data_tool_registry()
        self.artifact_store = LocalArtifactStore(
            cache_dir=self.config["data_tools_cache_dir"],
            snapshot_dir=self.config["data_tools_snapshot_dir"],
        )
        self.data_tool_executor = CachedDataToolExecutor(
            registry=self.data_tool_registry,
            artifact_store=self.artifact_store,
        )
        configure_default_data_executor(self.data_tool_executor)
        self.data_collection_service = DataCollectionService(self.data_tool_executor)

        self.market_tools = LocalMarketDataToolbox(self.config["market_data_dir"])
        self.agent_registry = AgentRegistry()
        self.backtest_engine = BacktestEngine(self.market_tools)

    def register_data_tool(self, definition: DataToolDefinition) -> None:
        """
        注册自定义数据工具。

        参数：
            definition: 数据工具定义。

        返回：
            None: 无返回值。
        """
        self.data_tool_registry.register(definition)

    def collect_data(self, jobs: list[DataCollectionJob]):
        """
        独立运行数据采集任务。

        参数：
            jobs: 数据采集任务列表。

        返回：
            list[ToolExecutionResult]: 数据采集结果列表。
        """
        return self.data_collection_service.collect_many(jobs)

    def register_agent(self, agent: BaseAgent) -> None:
        """
        注册一个可独立运行的 Agent。

        参数：
            agent: Agent 实例。

        返回：
            None: 无返回值。
        """
        self.agent_registry.register(agent)

    def register_trading_agents_agent(self, **kwargs: Any) -> BaseAgent:
        """
        注册当前仓库内置的 TradingAgents 实现。

        参数：
            kwargs: 传给 TradingAgents 适配器的参数。

        返回：
            BaseAgent: 注册后的 Agent 实例。
        """
        from tradingagents.implementations.trading_agents import TradingAgentsAgent

        agent = TradingAgentsAgent(config=self.config.copy(), **kwargs)
        self.register_agent(agent)
        return agent

    def run_agent(self, agent_name: str, request: AgentRunRequest) -> AgentRunResult:
        """
        独立运行指定 Agent。

        参数：
            agent_name: Agent 名称。
            request: Agent 运行请求。

        返回：
            AgentRunResult: Agent 运行结果。
        """
        agent = self.agent_registry.get(agent_name)
        return agent.run(request, self.build_execution_context())

    def backtest_agent(
        self,
        agent_name: str,
        requests: list[AgentRunRequest],
        bar_rule: str = "1min",
    ) -> BacktestReport:
        """
        运行指定 Agent 并对其结果执行回测。

        参数：
            agent_name: Agent 名称。
            requests: Agent 运行请求列表。
            bar_rule: K 线重采样规则。

        返回：
            BacktestReport: 汇总回测结果。
        """
        agent = self.agent_registry.get(agent_name)
        return self.backtest_engine.backtest_agent(
            agent=agent,
            requests=requests,
            context=self.build_execution_context(),
            bar_rule=bar_rule,
        )

    def build_execution_context(self) -> AgentExecutionContext:
        """
        构建 Agent 运行上下文。

        参数：
            无。

        返回：
            AgentExecutionContext: 运行上下文对象。
        """
        return AgentExecutionContext(
            config=self.config.copy(),
            data_tools=self.data_tool_executor,
            market_tools=self.market_tools,
        )

    def _ensure_directories(self) -> None:
        """
        创建平台运行所需目录。

        参数：
            无。

        返回：
            None: 无返回值。
        """
        for key in [
            "local_data_dir",
            "data_tools_cache_dir",
            "data_tools_snapshot_dir",
            "market_data_dir",
            "agent_output_dir",
            "backtest_output_dir",
            "report_output_dir",
            "data_cache_dir",
        ]:
            from pathlib import Path

            Path(self.config[key]).mkdir(parents=True, exist_ok=True)


def create_default_platform(config: dict[str, Any] | None = None) -> TradingPlatform:
    """
    创建一个带默认组件的新平台实例。

    参数：
        config: 可选运行时配置。

    返回：
        TradingPlatform: 平台实例。
    """
    return TradingPlatform(config=config)
