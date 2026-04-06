from tradingagents.agents.utils.agent_utils import (
    get_internal_language_instruction,
    get_internal_language,
    get_market_descriptor,
    get_market_policy_report_label,
)


def create_bear_researcher(llm, memory):
    """
    创建并返回看空研究员。

    参数：
        llm: 当前组件使用的语言模型客户端或可运行对象。
        memory: 用于读取或存储历史反思的记忆后端。

    返回：
        Callable | object: 当前组件生成的可调用对象或实例。
    """
    def bear_node(state) -> dict:
        """
        执行看空研究流程。

        参数：
            state: 当前工作流对应的图状态。

        返回：
            dict: 需要回写到图状态中的状态补丁。
        """
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for rec in past_memories:
            past_memory_str += rec["recommendation"] + "\n\n"

        output_language = get_internal_language()
        speaker_label = "空头研究员" if output_language.lower() == "chinese" else "Bear Analyst"
        ticker = state["company_of_interest"]
        market_descriptor = get_market_descriptor(ticker)
        market_policy_report_label = get_market_policy_report_label(ticker)

        prompt = f"""You are a Bear Analyst making the case against investing in the stock. Your goal is to present a well-reasoned argument emphasizing risks, challenges, and negative indicators. Leverage the provided research and data to highlight potential downsides and counter bullish arguments effectively.

Key points to focus on:

- Risks and Challenges: Highlight factors like market saturation, financial instability, or macroeconomic threats that could hinder the stock's performance.
- Competitive Weaknesses: Emphasize vulnerabilities such as weaker market positioning, declining innovation, or threats from competitors.
- Negative Indicators: Use evidence from financial data, market trends, or recent adverse news to support your position.
- Bull Counterpoints: Critically analyze the bull argument with specific data and sound reasoning, exposing weaknesses or over-optimistic assumptions.
- Engagement: Present your argument in a conversational style, directly engaging with the bull analyst's points and debating effectively rather than simply listing facts.
- Tone: Avoid violent, self-harm, or disaster metaphors. Use neutral market wording such as downside risk, drawdown, concentrated selling, weak liquidity, or valuation pressure.

Resources available:

Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
{market_policy_report_label}: {news_report}
Company fundamentals report: {fundamentals_report}
Conversation history of the debate: {history}
Last bull argument: {current_response}
Reflections from similar situations and lessons learned: {past_memory_str}
Use this information to deliver a compelling bear argument for the {market_descriptor} market, including policy disappointment,估值过高,业绩不及预期,流动性退潮, or题材退潮风险. Refute the bull's claims and learn from prior lessons.
{get_internal_language_instruction()}"""

        response = llm.invoke(prompt)

        argument = f"{speaker_label}: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "latest_speaker": "Bear Researcher",
            "current_response": argument,
            "judge_decision": investment_debate_state.get("judge_decision", ""),
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bear_node
