import time
import json

from tradingagents.agents.utils.agent_utils import (
    get_execution_constraints_prompt,
    get_internal_language_instruction,
    get_internal_language,
    get_market_descriptor,
    get_market_policy_report_label,
)


def create_aggressive_debator(llm):
    """
    创建并返回激进派辩手。
    
    参数：
        llm: 当前组件使用的语言模型客户端或可运行对象。
    
    返回：
        Callable | object: 当前组件生成的可调用对象或实例。
    """
    def aggressive_node(state) -> dict:
        """
        执行激进派辩论流程。
        
        参数：
            state: 当前工作流对应的图状态。
        
        返回：
            dict: 需要回写到图状态中的状态补丁。
        """
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        aggressive_history = risk_debate_state.get("aggressive_history", "")

        current_conservative_response = risk_debate_state.get("current_conservative_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        trader_decision = state["trader_investment_plan"]
        output_language = get_internal_language()
        speaker_label = "激进派分析师" if output_language.lower() == "chinese" else "Aggressive Analyst"
        ticker = state["company_of_interest"]
        market_descriptor = get_market_descriptor(ticker)
        execution_constraints = get_execution_constraints_prompt(ticker)
        market_policy_report_label = get_market_policy_report_label(ticker)

        prompt = f"""As the Aggressive Risk Analyst for {market_descriptor}s, your role is to actively champion high-reward opportunities, especially when policy catalysts, sector rotation, and资金情绪 may drive strong upside. When evaluating the trader's decision or plan, focus on the potential upside and why a faster-moving {market_descriptor} theme may justify accepting higher volatility. Respond directly to each point made by the conservative and neutral analysts, countering with data-driven rebuttals and persuasive reasoning. Here is the trader's decision:

{trader_decision}

Your task is to create a compelling case for the trader's decision by questioning and critiquing the conservative and neutral stances to demonstrate why your high-reward perspective offers the best path forward. Incorporate insights from the following sources into your arguments:

Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
{market_policy_report_label}: {news_report}
Company Fundamentals Report: {fundamentals_report}
Here is the current conversation history: {history} Here are the last arguments from the conservative analyst: {current_conservative_response} Here are the last arguments from the neutral analyst: {current_neutral_response}. If there are no responses from the other viewpoints yet, present your own argument based on the available data.

Engage actively by addressing specific concerns raised, refuting weaknesses in the opposing logic, and asserting why an aggressive {market_descriptor} approach may outperform when市场情绪 and政策催化 are aligned. Explicitly weigh execution constraints such as {execution_constraints}. Output conversationally without special formatting.{get_internal_language_instruction()}"""

        response = llm.invoke(prompt)

        argument = f"{speaker_label}: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": aggressive_history + "\n" + argument,
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Aggressive",
            "current_aggressive_response": argument,
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return aggressive_node
