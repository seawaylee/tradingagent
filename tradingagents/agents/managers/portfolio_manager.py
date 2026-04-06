from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_execution_constraints_prompt,
    get_final_output_language,
    get_market_descriptor,
    get_user_facing_report_instruction,
)


def create_portfolio_manager(llm, memory):
    """
    创建并返回投资组合经理。
    
    参数：
        llm: 当前组件使用的语言模型客户端或可运行对象。
        memory: 用于读取或存储历史反思的记忆后端。
    
    返回：
        Callable | object: 当前组件生成的可调用对象或实例。
    """
    def portfolio_manager_node(state) -> dict:

        """
        执行投资组合管理流程。
        
        参数：
            state: 当前工作流对应的图状态。
        
        返回：
            dict: 需要回写到图状态中的状态补丁。
        """
        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(ticker)
        market_descriptor = get_market_descriptor(ticker)
        execution_constraints = get_execution_constraints_prompt(ticker)
        output_language = get_final_output_language()
        use_chinese_labels = output_language.lower() == "chinese"
        rating_heading = "评级" if use_chinese_labels else "Rating"
        summary_heading = "执行摘要" if use_chinese_labels else "Executive Summary"
        thesis_heading = "投资逻辑" if use_chinese_labels else "Investment Thesis"

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        market_research_report = state["market_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        sentiment_report = state["sentiment_report"]
        trader_plan = state["investment_plan"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        prompt = f"""As the {market_descriptor} Portfolio Manager, synthesize the risk analysts' debate and deliver the final trading decision.

{instrument_context}

---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction to enter or add to position
- **Overweight**: Favorable outlook, gradually increase exposure
- **Hold**: Maintain current position, no action needed
- **Underweight**: Reduce exposure, take partial profits
- **Sell**: Exit position or avoid entry

**Context:**
- Trader's proposed plan: **{trader_plan}**
- Lessons from past decisions: **{past_memory_str}**

**Required Output Structure:**
1. **{rating_heading}**: State one of Buy / Overweight / Hold / Underweight / Sell.
2. **{summary_heading}**: A concise action plan covering entry strategy, position sizing, key risk levels, expected holding period, and market-specific execution constraints.
3. **{thesis_heading}**: Detailed reasoning anchored in the analysts' debate, policy context, and past reflections.

---

**Risk Analysts Debate History:**
{history}

---

Be decisive and ground every conclusion in specific evidence from the analysts. Explicitly discuss {execution_constraints}, and whether execution risk changes the final action.{get_user_facing_report_instruction()} Keep the rating keyword itself in English as one of Buy / Overweight / Hold / Underweight / Sell for downstream parsing, but translate all headings and explanatory text into the selected final output language."""

        response = llm.invoke(prompt)

        new_risk_debate_state = {
            "judge_decision": response.content,
            "history": risk_debate_state["history"],
            "aggressive_history": risk_debate_state["aggressive_history"],
            "conservative_history": risk_debate_state["conservative_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "latest_speaker": "Judge",
            "current_aggressive_response": risk_debate_state["current_aggressive_response"],
            "current_conservative_response": risk_debate_state["current_conservative_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "count": risk_debate_state["count"],
        }

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": response.content,
        }

    return portfolio_manager_node
