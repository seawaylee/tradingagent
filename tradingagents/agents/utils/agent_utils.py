from langchain_core.messages import HumanMessage, RemoveMessage

# 从独立工具模块导入各类工具
from tradingagents.agents.utils.core_stock_tools import (
    get_stock_data
)
from tradingagents.agents.utils.technical_indicators_tools import (
    get_indicators
)
from tradingagents.agents.utils.fundamental_data_tools import (
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement
)
from tradingagents.agents.utils.news_data_tools import (
    get_news,
    get_company_announcements,
    get_market_news,
)


def _build_language_instruction(language: str, usage_label: str) -> str:
    """
    为指定语言与用途生成提示语。

    参数：
        language: 目标语言名称。
        usage_label: 当前语言用途标签。

    返回：
        str: 当前语言约束提示语。
    """
    lang = (language or "").strip() or "English"
    if lang.lower() == "english":
        return ""
    return (
        f" Write all narrative text, section headings, bullet labels, table headers, and summaries in {lang}."
        f" Treat this as the selected {usage_label}."
        " Do not switch back to English for prose."
        " Do not add workflow narration or meta commentary such as collecting data, compiling the report, or preparing the final answer."
        " Translate default English headings unless an explicit machine-readable token is required."
        " Only preserve English when it is an explicit machine-readable token, stock ticker, indicator name, or required downstream rating keyword."
    )



def get_internal_language_instruction() -> str:
    """
    返回与当前内部语言匹配的提示语。

    返回：
        str: 当前内部语言约束提示语。
    """
    return _build_language_instruction(get_internal_language(), "internal language")



def get_final_language_instruction() -> str:
    """
    返回与当前最终语言匹配的提示语。

    返回：
        str: 当前最终语言约束提示语。
    """
    return _build_language_instruction(get_final_output_language(), "final output language")



def get_language_instruction() -> str:
    """
    兼容旧接口，返回当前最终语言匹配的提示语。

    返回：
        str: 当前最终语言约束提示语。
    """
    return get_final_language_instruction()


def get_user_facing_report_instruction() -> str:
    """
    返回面向最终报告的统一输出约束。

    返回：
        str: 报告语言与格式约束提示语。
    """
    return (
        f"{get_final_language_instruction()}"
        " Return only the finished report body in Markdown."
        " Do not include process narration, tool-call summaries, or transition sentences before the real content."
    )



def get_internal_language() -> str:
    """
    获取当前配置的内部语言。

    返回：
        str: 当前内部语言名称。
    """
    from tradingagents.dataflows.config import get_config

    config = get_config()
    return config.get("internal_language", "English").strip()



def get_final_output_language() -> str:
    """
    获取当前配置的最终输出语言。

    返回：
        str: 当前最终输出语言名称。
    """
    from tradingagents.dataflows.config import get_config

    config = get_config()
    return config.get("final_output_language", config.get("output_language", "Chinese")).strip()



def get_output_language() -> str:
    """
    兼容旧接口，返回当前最终输出语言。

    返回：
        str: 当前最终输出语言名称。
    """
    return get_final_output_language()



def build_instrument_context(ticker: str) -> str:
    """
    描述精确的 A 股标的，确保代理始终保留带交易所后缀的代码。
    
    参数：
        ticker: 待分析公司的 A 股股票代码。
    
    返回：
        str: 函数执行结果。
    """
    return (
        f"The instrument to analyze is `{ticker}`. "
        "Use this exact A-share ticker in every tool call, report, and recommendation, "
        "preserving the market suffix `.SH`, `.SZ`, or `.BJ`."
    )


def create_msg_delete():
    """
    创建并返回消息清理函数。
    
    返回：
        Callable | object: 当前组件生成的可调用对象或实例。
    """
    def delete_messages(state):
        """
        清空消息，并为 Anthropic 兼容性补充占位消息。
        
        参数：
            state: 当前工作流对应的图状态。
        
        返回：
            None: 无返回值。
        """
        messages = state["messages"]

        # 删除现有全部消息
        removal_operations = [RemoveMessage(id=m.id) for m in messages]

        # 添加最小占位消息
        placeholder = HumanMessage(content="Continue")

        return {"messages": removal_operations + [placeholder]}

    return delete_messages
