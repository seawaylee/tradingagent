from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_market_indefinite_descriptor,
    get_market_scope,
    get_news,
    get_user_facing_report_instruction,
)
from tradingagents.dataflows.config import get_config


def create_social_media_analyst(llm):
    """
    创建并返回社交媒体分析师。
    
    参数：
        llm: 当前组件使用的语言模型客户端或可运行对象。
    
    返回：
        Callable | object: 当前组件生成的可调用对象或实例。
    """
    def social_media_analyst_node(state):
        """
        执行社交媒体分析流程。
        
        参数：
            state: 当前工作流对应的图状态。
        
        返回：
            dict: 需要回写到图状态中的状态补丁。
        """
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(ticker)
        market_descriptor = get_market_indefinite_descriptor(ticker)
        market_scope = get_market_scope(ticker)

        tools = [
            get_news,
        ]

        system_message = (
            f"You are a {market_descriptor} sentiment analyst focused on retail mood, media framing, and company-specific public attention. Use get_news(ticker, start_date, end_date) to summarize signals that proxy for investor sentiment in the {market_scope}, such as media tone, repeated narratives, product buzz, capital-flow attention, and emotionally charged reactions around the stock. Do not assume direct access to overseas social platforms; infer sentiment from financial media and company-specific news flow. Highlight whether sentiment is improving, overheating, or deteriorating, and explain the likely short-term impact on {market_scope} trading."
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
            + get_user_facing_report_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "sentiment_report": report,
        }

    return social_media_analyst_node
