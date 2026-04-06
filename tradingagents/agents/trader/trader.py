import functools
import time
import json

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_execution_constraints_prompt,
    get_market_descriptor,
    get_user_facing_report_instruction,
)


def create_trader(llm, memory):
    """
    创建并返回交易员。
    
    参数：
        llm: 当前组件使用的语言模型客户端或可运行对象。
        memory: 用于读取或存储历史反思的记忆后端。
    
    返回：
        Callable | object: 当前组件生成的可调用对象或实例。
    """
    def trader_node(state, name):
        """
        执行交易员流程。
        
        参数：
            state: 当前工作流对应的图状态。
            name: 当前节点的展示名或发送者名称。
        
        返回：
            dict: 需要回写到图状态中的状态补丁。
        """
        company_name = state["company_of_interest"]
        instrument_context = build_instrument_context(company_name)
        market_descriptor = get_market_descriptor(company_name)
        execution_constraints = get_execution_constraints_prompt(company_name)
        investment_plan = state["investment_plan"]
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        if past_memories:
            for i, rec in enumerate(past_memories, 1):
                past_memory_str += rec["recommendation"] + "\n\n"
        else:
            past_memory_str = "No past memories found."

        context = {
            "role": "user",
            "content": f"Based on a comprehensive {market_descriptor} analysis for {company_name}, here is an investment plan. {instrument_context} This plan incorporates technical structure, policy and market news, fundamentals, and sentiment. Use this plan as the foundation for your next {market_descriptor} trading decision.\n\nProposed Investment Plan: {investment_plan}\n\nLeverage these insights to make an informed and strategic decision.",
        }

        messages = [
            {
                "role": "system",
                "content": f"""You are a {market_descriptor} trader. Based on the analysis, provide a specific recommendation to buy, sell, or hold. Your reasoning must reflect execution constraints including {execution_constraints}, and whether the setup may continue or fade. Apply lessons from past decisions to strengthen your analysis. Here are reflections from similar situations you traded in and the lessons learned: {past_memory_str}{get_user_facing_report_instruction()} Keep all explanatory content in the selected final output language, but preserve the final machine-readable line exactly as 'FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**'.""",
            },
            context,
        ]

        result = llm.invoke(messages)

        return {
            "messages": [result],
            "trader_investment_plan": result.content,
            "sender": name,
        }

    return functools.partial(trader_node, name="Trader")
