from typing import Any

from tradingagents.agent_core.base import BaseAgent
from tradingagents.agent_core.types import (
    AgentDecision,
    AgentExecutionContext,
    AgentRunRequest,
    AgentRunResult,
    DecisionAction,
)
from tradingagents.reporting import persist_report


class TradingAgentsAgent(BaseAgent):
    """将现有 TradingAgents 图封装为新架构下的一个 Agent 实现。"""

    def __init__(
        self,
        name: str = "tradingagents",
        selected_analysts: list[str] | None = None,
        debug: bool = False,
        config: dict[str, Any] | None = None,
    ):
        """
        初始化 TradingAgents 适配器。

        参数：
            name: Agent 注册名称。
            selected_analysts: 启用的分析师列表。
            debug: 是否启用旧图调试模式。
            config: 运行时配置。

        返回：
            None: 无返回值。
        """
        super().__init__(name=name)
        self.selected_analysts = selected_analysts or ["market", "social", "news", "fundamentals"]
        self.debug = debug
        self.config = config
        self._graph = None

    def run(self, request: AgentRunRequest, context: AgentExecutionContext) -> AgentRunResult:
        """
        运行 TradingAgents，并返回标准化决策。

        参数：
            request: Agent 输入请求。
            context: Agent 运行上下文。

        返回：
            AgentRunResult: 标准化后的 Agent 结果。
        """
        graph = self._get_graph(context)
        final_state, raw_signal = graph.propagate(request.symbol, request.trade_date)
        action = self._normalize_action(raw_signal)
        report_file = self._persist_report(final_state, request, context)
        report_metadata = {}
        if report_file is not None:
            report_metadata = {
                "report_file": str(report_file),
                "report_dir": str(report_file.parent),
            }

        decision = AgentDecision(
            agent_name=self.name,
            symbol=request.symbol,
            trade_date=request.trade_date,
            action=action,
            rationale=final_state.get("final_trade_decision_report", final_state.get("final_trade_decision", "")),
            confidence=request.context.get("confidence"),
            quantity=float(request.context.get("quantity", 1.0)),
            decision_time=request.context.get("decision_time"),
            holding_period_bars=int(request.context.get("holding_period_bars", 1)),
            metadata={
                "raw_signal": raw_signal,
                "selected_analysts": list(self.selected_analysts),
                **report_metadata,
            },
        )
        return AgentRunResult(
            agent_name=self.name,
            decision=decision,
            outputs={
                "raw_signal": raw_signal,
                "final_state": final_state,
                **report_metadata,
            },
        )

    def _get_graph(self, context: AgentExecutionContext):
        """
        延迟构建旧版 TradingAgents 图实例。

        参数：
            context: Agent 运行上下文。

        返回：
            Any: 旧版图对象实例。
        """
        if self._graph is None:
            from tradingagents.graph.trading_graph import TradingAgentsGraph

            runtime_config = context.config.copy()
            if self.config:
                runtime_config.update(self.config)
            self._graph = TradingAgentsGraph(
                selected_analysts=self.selected_analysts,
                debug=self.debug,
                config=runtime_config,
            )
        return self._graph

    def _normalize_action(self, raw_signal: str) -> DecisionAction:
        """
        将旧图输出的评级规范化为标准动作。

        参数：
            raw_signal: 旧图输出的原始信号文本。

        返回：
            DecisionAction: 标准化后的动作枚举。
        """
        signal = (raw_signal or "").strip().upper()
        if signal in {"BUY", "OVERWEIGHT"}:
            return DecisionAction.BUY
        if signal in {"SELL", "UNDERWEIGHT"}:
            return DecisionAction.SELL
        return DecisionAction.HOLD

    def _persist_report(
        self,
        final_state: dict[str, Any],
        request: AgentRunRequest,
        context: AgentExecutionContext,
    ):
        """
        将代码调用结果持久化为与 CLI 相同的报告目录结构。

        参数：
            final_state: 图执行后的最终状态。
            request: Agent 输入请求。
            context: Agent 运行上下文。

        返回：
            Path | None: 报告文件路径；若显式关闭持久化则返回 None。
        """
        if request.context.get("persist_report", True) is False:
            return None

        report_base_dir = request.context.get("report_base_dir") or context.config["report_output_dir"]
        report_save_path = request.context.get("report_save_path")
        return persist_report(
            final_state=final_state,
            ticker=request.symbol,
            base_dir=report_base_dir,
            save_path=report_save_path,
        )
