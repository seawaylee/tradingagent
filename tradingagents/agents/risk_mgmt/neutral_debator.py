import time
import json

from tradingagents.agents.utils.agent_utils import (
    get_execution_constraints_prompt,
    get_internal_language_instruction,
    get_internal_language,
    get_market_descriptor,
    get_market_policy_report_label,
)


def create_neutral_debator(llm):
    """
    创建并返回中性派辩手。
    
    参数：
        llm: 当前组件使用的语言模型客户端或可运行对象。
    
    返回：
        Callable | object: 当前组件生成的可调用对象或实例。
    """
    def neutral_node(state) -> dict:
        """
        执行中性派辩论流程。
        
        参数：
            state: 当前工作流对应的图状态。
        
        返回：
            dict: 需要回写到图状态中的状态补丁。
        """
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        neutral_history = risk_debate_state.get("neutral_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_conservative_response = risk_debate_state.get("current_conservative_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        trader_decision = state["trader_investment_plan"]
        output_language = get_internal_language()
        speaker_label = "中性派分析师" if output_language.lower() == "chinese" else "Neutral Analyst"
        ticker = state["company_of_interest"]
        market_descriptor = get_market_descriptor(ticker)
        execution_constraints = get_execution_constraints_prompt(ticker)
        market_policy_report_label = get_market_policy_report_label(ticker)

        prompt = f"""As the Neutral Risk Analyst for {market_descriptor}s, your role is to provide a balanced perspective, weighing both the potential benefits and risks of the trader's decision or plan. Judge whether the setup supports participation, reduced sizing, or simple observation under {market_descriptor} market conditions. Here is the trader's decision:

{trader_decision}

Your task is to challenge both the Aggressive and Conservative Analysts, pointing out where each perspective may be overly optimistic or overly cautious. Use insights from the following data sources to support a moderate, sustainable strategy to adjust the trader's decision:

Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
{market_policy_report_label}: {news_report}
Company Fundamentals Report: {fundamentals_report}
Here is the current conversation history: {history} Here is the last response from the aggressive analyst: {current_aggressive_response} Here is the last response from the conservative analyst: {current_conservative_response}. If there are no responses from the other viewpoints yet, present your own argument based on the available data.

Engage actively by analyzing both sides critically, addressing weaknesses in the aggressive and conservative arguments to advocate for a more balanced approach. Explicitly discuss sizing, trigger prices, and whether the trade still makes sense once liquidity and execution constraints such as {execution_constraints} are considered. Output conversationally without special formatting.{get_internal_language_instruction()}"""

        response = llm.invoke(prompt)

        argument = f"{speaker_label}: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": neutral_history + "\n" + argument,
            "latest_speaker": "Neutral",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": argument,
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return neutral_node
