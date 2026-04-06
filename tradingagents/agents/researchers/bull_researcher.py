from tradingagents.agents.utils.agent_utils import (
    get_internal_language_instruction,
    get_internal_language,
    get_market_descriptor,
    get_market_policy_report_label,
)


def create_bull_researcher(llm, memory):
    """
    创建并返回看多研究员。

    参数：
        llm: 当前组件使用的语言模型客户端或可运行对象。
        memory: 用于读取或存储历史反思的记忆后端。

    返回：
        Callable | object: 当前组件生成的可调用对象或实例。
    """
    def bull_node(state) -> dict:
        """
        执行看多研究流程。

        参数：
            state: 当前工作流对应的图状态。

        返回：
            dict: 需要回写到图状态中的状态补丁。
        """
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

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
        speaker_label = "多头研究员" if output_language.lower() == "chinese" else "Bull Analyst"
        ticker = state["company_of_interest"]
        market_descriptor = get_market_descriptor(ticker)
        market_policy_report_label = get_market_policy_report_label(ticker)

        prompt = f"""You are a Bull Analyst advocating for investing in the stock. Your task is to build a strong, evidence-based case emphasizing growth potential, competitive advantages, and positive market indicators. Leverage the provided research and data to address concerns and counter bearish arguments effectively.

Key points to focus on:
- Growth Potential: Highlight the company's market opportunities, revenue projections, and scalability.
- Competitive Advantages: Emphasize factors like unique products, strong branding, or dominant market positioning.
- Positive Indicators: Use financial health, industry trends, and recent positive news as evidence.
- Bear Counterpoints: Critically analyze the bear argument with specific data and sound reasoning, addressing concerns thoroughly and showing why the bull perspective holds stronger merit.
- Engagement: Present your argument in a conversational style, engaging directly with the bear analyst's points and debating effectively rather than just listing data.
- Tone: Avoid violent, self-harm, or disaster metaphors. Use neutral market wording such as upside, drawdown, downside risk, selling pressure, or valuation compression.

Resources available:
Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
{market_policy_report_label}: {news_report}
Company fundamentals report: {fundamentals_report}
Conversation history of the debate: {history}
Last bear argument: {current_response}
Reflections from similar situations and lessons learned: {past_memory_str}
Use this information to deliver a compelling bull argument for the {market_descriptor} market. Discuss why policy support,行业景气, valuation repair,资金风格, or催化事件 may justify upside. Refute the bear's concerns and learn from prior lessons.
{get_internal_language_instruction()}"""

        response = llm.invoke(prompt)

        argument = f"{speaker_label}: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "latest_speaker": "Bull Researcher",
            "current_response": argument,
            "judge_decision": investment_debate_state.get("judge_decision", ""),
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node
