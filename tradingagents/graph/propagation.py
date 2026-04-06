# tradingagents/graph/propagation.py

from typing import Dict, Any, List, Optional
from tradingagents.agents.utils.agent_states import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
)


class Propagator:
    """Handles state initialization and propagation through the graph."""

    def __init__(self, max_recur_limit=100):
        """
        使用配置参数初始化对象。
        
        参数：
            max_recur_limit: 最大递归限制。
        
        返回：
            None: 无返回值。
        """
        self.max_recur_limit = max_recur_limit

    def create_initial_state(
        self, company_name: str, trade_date: str
    ) -> Dict[str, Any]:
        """
        创建代理图的初始状态。
        
        参数：
            company_name: 传入图工作流的股票代码或公司标识。
            trade_date: YYYY-MM-DD 格式的交易日期。
        
        返回：
            Dict[str, Any]: 当前组件生成的可调用对象或实例。
        """
        return {
            "messages": [("human", company_name)],
            "company_of_interest": company_name,
            "trade_date": str(trade_date),
            "investment_debate_state": InvestDebateState(
                {
                    "bull_history": "",
                    "bear_history": "",
                    "history": "",
                    "latest_speaker": "",
                    "current_response": "",
                    "judge_decision": "",
                    "count": 0,
                }
            ),
            "risk_debate_state": RiskDebateState(
                {
                    "aggressive_history": "",
                    "conservative_history": "",
                    "neutral_history": "",
                    "history": "",
                    "latest_speaker": "",
                    "current_aggressive_response": "",
                    "current_conservative_response": "",
                    "current_neutral_response": "",
                    "judge_decision": "",
                    "count": 0,
                }
            ),
            "market_report": "",
            "fundamentals_report": "",
            "sentiment_report": "",
            "news_report": "",
            "final_market_report": "",
            "final_fundamentals_report": "",
            "final_sentiment_report": "",
            "final_news_report": "",
            "investment_plan": "",
            "final_investment_plan_report": "",
            "trader_investment_plan": "",
            "final_trader_investment_plan_report": "",
            "final_trade_decision": "",
            "final_trade_decision_report": "",
        }

    def get_graph_args(
        self,
        callbacks: Optional[List] = None,
        thread_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        获取图调用所需参数。
        
        参数：
            callbacks: 执行期间使用的可选回调处理器。
        
        返回：
            Dict[str, Any]: 当前查询结果。
        """
        config = {"recursion_limit": self.max_recur_limit}
        if callbacks:
            config["callbacks"] = callbacks
        if thread_id:
            config["configurable"] = {"thread_id": thread_id}
        return {
            "stream_mode": "values",
            "config": config,
        }
