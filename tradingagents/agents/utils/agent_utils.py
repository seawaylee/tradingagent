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
from tradingagents.dataflows.market_symbols import get_market_label, is_hk_symbol, normalize_market_symbol


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
    描述精确的标的，确保代理始终保留带交易所后缀的代码。
    
    参数：
        ticker: 待分析公司的股票代码。
    
    返回：
        str: 函数执行结果。
    """
    normalized_ticker = normalize_market_symbol(ticker)
    if is_hk_symbol(normalized_ticker):
        return (
            f"The instrument to analyze is `{normalized_ticker}`. "
            "Use this exact Hong Kong stock ticker in every tool call, report, and recommendation, "
            "preserving the market suffix `.HK`."
        )

    market_label = get_market_label(normalized_ticker)
    return (
        f"The instrument to analyze is `{normalized_ticker}`. "
        f"Use this exact {market_label} ticker in every tool call, report, and recommendation, "
        "preserving the market suffix `.SH`, `.SZ`, or `.BJ`."
    )


def get_market_descriptor(ticker: str) -> str:
    """
    返回市场描述词。

    参数：
        ticker: 待分析公司的股票代码。

    返回：
        str: 市场描述词。
    """
    normalized_ticker = normalize_market_symbol(ticker)
    return "Hong Kong stock" if is_hk_symbol(normalized_ticker) else "A-share"


def get_market_indefinite_descriptor(ticker: str) -> str:
    """
    返回带不定冠词的市场描述词。

    参数：
        ticker: 待分析公司的股票代码。

    返回：
        str: 带冠词的市场描述词。
    """
    descriptor = get_market_descriptor(ticker)
    article = "an" if descriptor.startswith("A-") else "a"
    return f"{article} {descriptor}"


def get_market_scope(ticker: str) -> str:
    """
    返回市场范围描述。

    参数：
        ticker: 待分析公司的股票代码。

    返回：
        str: 市场范围描述。
    """
    normalized_ticker = normalize_market_symbol(ticker)
    return "Hong Kong stock market" if is_hk_symbol(normalized_ticker) else "A-share market"


def get_execution_constraints_prompt(ticker: str) -> str:
    """
    返回市场执行约束提示语。

    参数：
        ticker: 待分析公司的股票代码。

    返回：
        str: 执行约束描述。
    """
    if is_hk_symbol(normalize_market_symbol(ticker)):
        return (
            "lot size, intraday liquidity, gap risk from overnight U.S./China tech sentiment, "
            "southbound flows, and the absence of A-share-style daily price limits or T+1 resale constraints "
            "for most Hong Kong main-board stocks"
        )
    return "T+1,涨跌停,成交额和换手率质量,以及情绪冲高回落风险"


def get_market_news_focus_prompt(ticker: str) -> str:
    """
    返回市场新闻关注点提示语。

    参数：
        ticker: 待分析公司的股票代码。

    返回：
        str: 新闻关注点描述。
    """
    if is_hk_symbol(normalize_market_symbol(ticker)):
        return (
            "Focus on HKEX-style disclosures, company news, China policy spillover, USD/HKD rates, "
            "southbound flows, sector rotation, and any event that can affect next-day or short-swing "
            "trading in the Hong Kong stock market."
        )
    return (
        "Focus on policy catalysts,监管变化,业绩披露窗口, liquidity conditions, and any event that can affect "
        "next-day or short-swing trading in the A-share market."
    )


def get_fundamental_focus_prompt(ticker: str) -> str:
    """
    返回市场特定的基本面关注点。

    参数：
        ticker: 待分析公司的股票代码。

    返回：
        str: 基本面关注点描述。
    """
    if is_hk_symbol(normalize_market_symbol(ticker)):
        return (
            "Pay special attention to Hong Kong stock specific signals such as revenue quality, margin structure, "
            "cash conversion, leverage, ROE, buybacks, shareholder return, and valuation versus Hong Kong peers."
        )
    return (
        "Pay special attention to A-share specific fundamental signals such as 归母净利润, 扣非净利润, 经营现金流, "
        "存货, 应收, 商誉, and the stability of the core business."
    )


def get_market_policy_report_label(ticker: str) -> str:
    """
    返回市场政策报告标签。

    参数：
        ticker: 待分析公司的股票代码。

    返回：
        str: 报告标签。
    """
    return "Latest Hong Kong market and policy report" if is_hk_symbol(normalize_market_symbol(ticker)) else "Latest A-share market and policy news"


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
