from langchain_core.messages import AIMessage
import time
import json

from tradingagents.agents.utils.agent_utils import (
    get_execution_constraints_prompt,
    get_internal_language_instruction,
    get_internal_language,
    get_market_descriptor,
    get_market_policy_report_label,
)


def create_conservative_debator(llm):
    """
    创建并返回保守派辩手。
    
    参数：
        llm: 当前组件使用的语言模型客户端或可运行对象。
    
    返回：
        Callable | object: 当前组件生成的可调用对象或实例。
    """
    def conservative_node(state) -> dict:
        """
        执行保守派辩论流程。
        
        参数：
            state: 当前工作流对应的图状态。
        
        返回：
            dict: 需要回写到图状态中的状态补丁。
        """
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        conservative_history = risk_debate_state.get("conservative_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        trader_decision = state["trader_investment_plan"]
        output_language = get_internal_language()
        speaker_label = "保守派分析师" if output_language.lower() == "chinese" else "Conservative Analyst"
        ticker = state["company_of_interest"]
        market_descriptor = get_market_descriptor(ticker)
        execution_constraints = get_execution_constraints_prompt(ticker)
        market_policy_report_label = get_market_policy_report_label(ticker)

        prompt = f"""As the Conservative Risk Analyst for {market_descriptor}s, your primary objective is to protect assets, minimize volatility, and avoid being trapped by high-turnover themes, weak liquidity, and execution risk. When evaluating the trader's decision or plan, critically examine high-risk elements, pointing out where the decision may expose the portfolio to undue risk and where more cautious alternatives could secure better risk-adjusted returns. Here is the trader's decision:

{trader_decision}

Your task is to actively counter the arguments of the Aggressive and Neutral Analysts, highlighting where their views may overlook potential threats or fail to prioritize sustainability. Respond directly to their points, drawing from the following data sources to build a convincing case for a low-risk approach adjustment to the trader's decision:

Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
{market_policy_report_label}: {news_report}
Company Fundamentals Report: {fundamentals_report}
Here is the current conversation history: {history} Here is the last response from the aggressive analyst: {current_aggressive_response} Here is the last response from the neutral analyst: {current_neutral_response}. If there are no responses from the other viewpoints yet, present your own argument based on the available data.

Engage by questioning their optimism and emphasizing the potential downsides they may have overlooked, including监管风险、情绪退潮、缩量下跌, and execution friction under constraints such as {execution_constraints}. Output conversationally without special formatting.{get_internal_language_instruction()}"""

        response = llm.invoke(prompt)

        argument = f"{speaker_label}: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": conservative_history + "\n" + argument,
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Conservative",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": argument,
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return conservative_node
