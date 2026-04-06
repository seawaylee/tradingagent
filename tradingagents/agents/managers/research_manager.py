import re

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_execution_constraints_prompt,
    get_market_descriptor,
    get_user_facing_report_instruction,
)


_POLICY_SENSITIVE_REPLACEMENTS = [
    ("自杀式", "高风险"),
    ("自残式", "高风险"),
    ("血洗", "大幅回撤"),
    ("屠杀", "大幅抛压"),
    ("绞杀", "快速压缩"),
    ("杀跌", "恐慌性下跌"),
    ("砸盘", "大额卖出"),
    ("踩踏", "集中抛售"),
    ("暴雷", "突发利空"),
    ("爆仓", "强平风险"),
    ("腰斩", "大幅下跌"),
    ("死亡交叉", "下行交叉"),
    ("死叉", "下行交叉"),
    ("自救", "修复"),
]


def _sanitize_financial_prompt_text(text: str) -> str:
    """
    将容易触发策略过滤的金融隐喻替换为中性表达。

    参数：
        text: 待清洗的提示词上下文。

    返回：
        str: 清洗后的文本。
    """
    cleaned = text or ""
    for source, target in _POLICY_SENSITIVE_REPLACEMENTS:
        cleaned = cleaned.replace(source, target)

    cleaned = re.sub(r"\bpast mistakes\b", "past lessons", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bmistakes\b", "lessons", cleaned, flags=re.IGNORECASE)
    return cleaned


def _build_memory_text(past_memories) -> str:
    """
    将历史记忆整理为单段文本，并提前做降敏清洗。

    参数：
        past_memories: 记忆检索结果列表。

    返回：
        str: 拼接后的历史记忆文本。
    """
    memory_parts = []
    for rec in past_memories:
        recommendation = rec.get("recommendation", "") if isinstance(rec, dict) else ""
        if recommendation:
            memory_parts.append(_sanitize_financial_prompt_text(recommendation))
    return "\n\n".join(memory_parts)


def create_research_manager(llm, memory):
    """
    创建并返回研究经理。

    参数：
        llm: 当前组件使用的语言模型客户端或可运行对象。
        memory: 用于读取或存储历史反思的记忆后端。

    返回：
        Callable | object: 当前组件生成的可调用对象或实例。
    """
    def research_manager_node(state) -> dict:
        """
        执行研究经理流程。

        参数：
            state: 当前工作流对应的图状态。

        返回：
            dict: 需要回写到图状态中的状态补丁。
        """
        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(ticker)
        market_descriptor = get_market_descriptor(ticker)
        execution_constraints = get_execution_constraints_prompt(ticker)
        history = _sanitize_financial_prompt_text(
            state["investment_debate_state"].get("history", "")
        )
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        investment_debate_state = state["investment_debate_state"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)
        past_memory_str = _build_memory_text(past_memories)

        prompt = f"""As the {market_descriptor} research manager and debate facilitator, critically evaluate this round of debate and make a definitive decision: align with the bear analyst, align with the bull analyst, or choose Hold only if the setup truly lacks edge.

Summarize the key points from both sides concisely, focusing on the most compelling evidence or reasoning. Your recommendation—Buy, Sell, or Hold—must be clear and actionable. Avoid defaulting to Hold simply because both sides have valid points; commit to a stance grounded in the debate's strongest arguments and execution constraints such as {execution_constraints}.

Additionally, develop a detailed investment plan for the trader. This should include:

Your Recommendation: A decisive stance supported by the most convincing arguments.
Rationale: An explanation of why these arguments lead to your conclusion.
Strategic Actions: Concrete steps for implementing the recommendation, explicitly noting whether the trade is suitable for next-day execution, a short swing, or observation only.
Take into account your past lessons from similar situations. Use these insights to refine your decision-making and ensure continuous improvement. Avoid violent, self-harm, or disaster metaphors; prefer neutral market language such as sharp decline, downside risk, forced selling, or rapid drawdown. Present your analysis conversationally, as if speaking naturally, without special formatting.

Here are your past reflections and lessons:
\"{past_memory_str}\"

{instrument_context}

Here is the debate:
Debate History:
{history}{get_user_facing_report_instruction()}"""
        response = llm.invoke(prompt)

        new_investment_debate_state = {
            "judge_decision": response.content,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "latest_speaker": "Research Manager",
            "current_response": response.content,
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": response.content,
        }

    return research_manager_node
