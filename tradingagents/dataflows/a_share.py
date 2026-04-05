from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta
from http.client import RemoteDisconnected
import math
import sys
import time
import textwrap

import akshare as ak
import pandas as pd
import requests
from akshare.utils import tqdm as ak_tqdm

from .a_share_common import (
    format_date_for_api,
    get_date_range,
    get_previous_trade_date,
    normalize_ashare_symbol,
    parse_date_column,
    to_exchange_prefixed_symbol,
    to_plain_symbol,
)
from .stockstats_utils import load_ohlcv


INDICATOR_DESCRIPTIONS = {
    "close_50_sma": "50日简单移动平均线，用于识别中期趋势和动态支撑阻力。",
    "close_200_sma": "200日简单移动平均线，用于识别长期趋势和牛熊切换。",
    "close_10_ema": "10日指数移动平均线，用于捕捉更快的短期趋势变化。",
    "macd": "MACD 指标，用于识别趋势变化与动量。",
    "macds": "MACD 信号线，用于配合 MACD 判断金叉死叉。",
    "macdh": "MACD 柱状图，用于衡量动量强弱变化。",
    "rsi": "RSI 指标，用于识别超买超卖与背离。",
    "boll": "布林带中轨，衡量价格相对中枢。",
    "boll_ub": "布林带上轨，衡量价格上沿压力。",
    "boll_lb": "布林带下轨，衡量价格下沿支撑。",
    "atr": "ATR 波动率指标，用于仓位和止损参考。",
    "vwma": "成交量加权均线，用于结合量价确认趋势。",
    "mfi": "资金流量指标，用于衡量量价驱动的超买超卖。",
}

IMPORTANT_FINANCIAL_METRICS = [
    "归母净利润",
    "扣非净利润",
    "营业总收入",
    "基本每股收益",
    "每股净资产",
    "每股经营性现金流",
    "销售毛利率",
    "净资产收益率",
    "资产负债率",
]

BALANCE_SHEET_COLUMNS = [
    "REPORT_DATE_NAME",
    "TOTAL_ASSETS",
    "TOTAL_LIABILITIES",
    "TOTAL_PARENT_EQUITY",
    "MONETARYFUNDS",
    "INVENTORY",
    "ACCOUNTS_RECE",
    "GOODWILL",
]

CASHFLOW_COLUMNS = [
    "REPORT_DATE_NAME",
    "NETCASH_OPERATE",
    "NETCASH_INVEST",
    "NETCASH_FINANCE",
    "CCE_ADD",
    "PAY_STAFF_CASH",
    "PAY_ALL_TAX",
]

INCOME_COLUMNS = [
    "REPORT_DATE_NAME",
    "TOTAL_OPERATE_INCOME",
    "OPERATE_PROFIT",
    "TOTAL_PROFIT",
    "NETPROFIT",
    "PARENT_NETPROFIT",
    "DEDUCT_PARENT_NETPROFIT",
    "BASIC_EPS",
]


@contextmanager
def _temporary_string_storage(storage: str):
    """
    临时切换 pandas 字符串存储模式，并在退出后恢复原配置。

    参数：
        storage: 临时使用的字符串存储模式。

    返回：
        None: 无返回值。
    """
    original = pd.get_option("mode.string_storage")
    pd.set_option("mode.string_storage", storage)
    try:
        yield
    finally:
        pd.set_option("mode.string_storage", original)


@contextmanager
def _suppress_akshare_progress():
    """
    临时关闭 AkShare 内部 tqdm 进度条输出。

    返回：
        None: 无返回值。
    """
    replacements = {}
    silent_get_tqdm = lambda enable=True: (lambda iterable, *args, **kwargs: iterable)

    replacements[(ak_tqdm, "get_tqdm")] = ak_tqdm.get_tqdm
    ak_tqdm.get_tqdm = silent_get_tqdm

    for module in list(sys.modules.values()):
        module_name = getattr(module, "__name__", "")
        if not module_name.startswith("akshare."):
            continue
        if hasattr(module, "get_tqdm"):
            replacements[(module, "get_tqdm")] = getattr(module, "get_tqdm")
            setattr(module, "get_tqdm", silent_get_tqdm)
    try:
        yield
    finally:
        for (module, attr), original in replacements.items():
            setattr(module, attr, original)


def _format_table(df: pd.DataFrame, title: str, rows: int = 10) -> str:
    """
    格式化表格输出。
    
    参数：
        df: 需要格式化、筛选或转换的数据表。
        title: 表格标题。
        rows: 格式化输出中保留的最大行数。
    
    返回：
        str: 格式化后的字符串结果。
    """
    if df.empty:
        return f"{title}\n\n暂无数据。"
    return f"{title}\n\n{df.head(rows).to_csv(index=False)}"


def _round_numeric_frame(df: pd.DataFrame) -> pd.DataFrame:
    """
    对数值型数据表执行四舍五入。
    
    参数：
        df: 需要格式化、筛选或转换的数据表。
    
    返回：
        pd.DataFrame: 处理后的数据表。
    """
    rounded = df.copy()
    for column in rounded.columns:
        if pd.api.types.is_numeric_dtype(rounded[column]):
            rounded[column] = rounded[column].round(4)
    return rounded


def _select_statement_columns(df: pd.DataFrame, preferred_columns: list[str]) -> pd.DataFrame:
    """
    选择财务报表字段。
    
    参数：
        df: 需要格式化、筛选或转换的数据表。
        preferred_columns: 输出中优先保留的字段顺序列表。
    
    返回：
        pd.DataFrame: 处理后的数据表。
    """
    available = [column for column in preferred_columns if column in df.columns]
    if not available:
        return df.head(8)
    return df.loc[:, available].head(8)


def _filter_report_rows(df: pd.DataFrame, curr_date: str | None) -> pd.DataFrame:
    """
    筛选报告行。
    
    参数：
        df: 需要格式化、筛选或转换的数据表。
        curr_date: 当前分析或交易日期，格式为 YYYY-MM-DD。
    
    返回：
        pd.DataFrame: 处理后的数据表。
    """
    if df.empty or not curr_date:
        return df
    for column in ("REPORT_DATE", "NOTICE_DATE", "报告日期", "公告日期"):
        if column in df.columns:
            filtered = df.copy()
            filtered[column] = parse_date_column(filtered[column])
            cutoff = pd.Timestamp(curr_date)
            filtered = filtered[filtered[column] <= cutoff]
            filtered = filtered.sort_values(column, ascending=False)
            return filtered
    return df


def _latest_abstract_snapshot(abstract_df: pd.DataFrame, curr_date: str | None) -> pd.DataFrame:
    """
    返回最新财务摘要快照。
    
    参数：
        abstract_df: AkShare 返回的财务摘要数据表。
        curr_date: 当前分析或交易日期，格式为 YYYY-MM-DD。
    
    返回：
        pd.DataFrame: 处理后的数据表。
    """
    report_columns = [column for column in abstract_df.columns if str(column).isdigit()]
    if not report_columns:
        return pd.DataFrame()

    parsed_dates = {
        column: pd.to_datetime(str(column), format="%Y%m%d", errors="coerce")
        for column in report_columns
    }

    if curr_date:
        cutoff = pd.Timestamp(curr_date)
        eligible = [column for column, value in parsed_dates.items() if value <= cutoff]
    else:
        eligible = report_columns

    if not eligible:
        eligible = report_columns

    latest_column = max(eligible, key=lambda column: parsed_dates[column])
    filtered = abstract_df[abstract_df["指标"].isin(IMPORTANT_FINANCIAL_METRICS)][["指标", latest_column]].copy()
    filtered.columns = ["指标", latest_column]
    return filtered


def _safe_truncate(text: str, limit: int = 160) -> str:
    """
    安全截断文本。
    
    参数：
        text: 需要截断或处理的输入文本。
        limit: 结果中允许保留的最大长度。
    
    返回：
        str: 安全处理后的字符串结果。
    """
    clean = " ".join(str(text).split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3] + "..."


def _is_retryable_akshare_error(exc: Exception) -> bool:
    """
    判断异常是否属于可重试的 AkShare 网络错误。

    参数：
        exc: 待判断的异常对象。

    返回：
        bool: 条件满足时返回 True，否则返回 False。
    """
    if isinstance(exc, (requests.exceptions.RequestException, RemoteDisconnected, TimeoutError)):
        return True

    message = str(exc)
    retryable_markers = (
        "Remote end closed connection without response",
        "Connection aborted",
        "Read timed out",
        "ConnectTimeout",
        "Max retries exceeded",
        "temporarily unavailable",
    )
    return any(marker in message for marker in retryable_markers)


def _call_akshare_api(func, *args, retries: int = 3, retry_delay: float = 1.0, **kwargs):
    """
    调用 AkShare 接口，并对网络抖动执行有限次重试。

    参数：
        func: 需要执行的 AkShare 函数。
        args: 传给 AkShare 函数的位置参数。
        retries: 最大重试次数。
        retry_delay: 首次重试前的等待秒数，后续按次数递增。
        kwargs: 传给 AkShare 函数的关键字参数。

    返回：
        Any: AkShare 原始返回结果。
    """
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt >= retries or not _is_retryable_akshare_error(exc):
                raise
            time.sleep(retry_delay * attempt)
    raise last_exc


def _format_data_error(title: str, exc: Exception) -> str:
    """
    将外部数据源异常转换为可读文本，避免工具节点直接崩溃。

    参数：
        title: 当前数据块标题。
        exc: 原始异常对象。

    返回：
        str: 适合直接返回给上层代理的错误说明。
    """
    return (
        f"{title}\n\n"
        f"数据源访问失败：{type(exc).__name__}: {_safe_truncate(str(exc), 220)}"
    )


def _load_stock_hist_with_fallback(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    获取历史行情，并在东方财富源失败时回退到腾讯源。

    参数：
        symbol: 待分析标的的 A 股股票代码。
        start_date: 起始日期（含当日），格式为 YYYY-MM-DD。
        end_date: 结束日期（含当日），格式为 YYYY-MM-DD。

    返回：
        pd.DataFrame: 历史行情数据表。
    """
    plain_symbol = to_plain_symbol(symbol)
    try:
        return _call_akshare_api(
            ak.stock_zh_a_hist,
            symbol=plain_symbol,
            period="daily",
            start_date=format_date_for_api(start_date),
            end_date=format_date_for_api(end_date),
            adjust="qfq",
        )
    except Exception:  # noqa: BLE001
        with _suppress_akshare_progress():
            return _call_akshare_api(
                ak.stock_zh_a_hist_tx,
                symbol=to_exchange_prefixed_symbol(symbol).lower(),
                start_date=format_date_for_api(start_date),
                end_date=format_date_for_api(end_date),
                adjust="qfq",
            )


def _load_company_profile(plain_symbol: str) -> pd.DataFrame:
    """
    获取公司概况，并优先使用更稳定的巨潮资讯接口。

    参数：
        plain_symbol: 不带交易所前缀的纯数字股票代码。

    返回：
        pd.DataFrame: 公司概况数据表。
    """
    try:
        return _call_akshare_api(ak.stock_profile_cninfo, symbol=plain_symbol)
    except Exception:  # noqa: BLE001
        return _call_akshare_api(ak.stock_individual_info_em, symbol=plain_symbol)


def get_stock_data(symbol: str, start_date: str, end_date: str) -> str:
    """
    返回股票行情数据。
    
    参数：
        symbol: 待分析标的的 A 股股票代码。
        start_date: 起始日期（含当日），格式为 YYYY-MM-DD。
        end_date: 结束日期（含当日），格式为 YYYY-MM-DD。
    
    返回：
        str: 当前查询结果。
    """
    normalized_symbol = normalize_ashare_symbol(symbol)
    try:
        df = _load_stock_hist_with_fallback(symbol, start_date, end_date)
    except Exception as exc:  # noqa: BLE001
        return _format_data_error(
            f"# A-share price data for {normalized_symbol} from {start_date} to {end_date}",
            exc,
        )

    if df.empty:
        return f"未找到 {normalized_symbol} 在 {start_date} 到 {end_date} 之间的 A 股行情数据。"

    renamed = df.rename(
        columns={
            "日期": "Date",
            "date": "Date",
            "开盘": "Open",
            "open": "Open",
            "收盘": "Close",
            "close": "Close",
            "最高": "High",
            "high": "High",
            "最低": "Low",
            "low": "Low",
            "成交量": "Volume",
            "成交额": "Amount",
            "amount": "Amount",
            "振幅": "AmplitudePct",
            "涨跌幅": "PctChange",
            "涨跌额": "PriceChange",
            "换手率": "TurnoverPct",
        }
    )
    renamed["Date"] = pd.to_datetime(renamed["Date"]).dt.strftime("%Y-%m-%d")
    if "PctChange" not in renamed.columns and "Close" in renamed.columns:
        renamed["PctChange"] = renamed["Close"].pct_change().mul(100).round(4)
    selected_columns = [
        column
        for column in ["Date", "Open", "High", "Low", "Close", "Volume", "Amount", "PctChange", "TurnoverPct"]
        if column in renamed.columns
    ]
    output = _round_numeric_frame(renamed.loc[:, selected_columns])
    header = f"# A-share price data for {normalized_symbol} from {start_date} to {end_date}\n"
    header += f"# Records: {len(output)}\n\n"
    return header + output.to_csv(index=False)


def _get_indicator_data(symbol: str, indicator: str, curr_date: str) -> dict[str, str]:
    """
    返回指标原始数据。
    
    参数：
        symbol: 待分析标的的 A 股股票代码。
        indicator: 需要计算或查询的技术指标名称。
        curr_date: 当前分析或交易日期，格式为 YYYY-MM-DD。
    
    返回：
        dict[str, str]: 指标名称与结果文本的映射。
    """
    from stockstats import wrap

    aligned_trade_date = get_previous_trade_date(curr_date)
    data = load_ohlcv(symbol, aligned_trade_date)
    df = wrap(data.copy())
    df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
    df[indicator]

    result = {}
    for _, row in df.iterrows():
        value = row[indicator]
        if pd.isna(value):
            result[row["Date"]] = "N/A"
        else:
            result[row["Date"]] = str(value)
    return result


def get_indicators(symbol: str, indicator: str, curr_date: str, look_back_days: int) -> str:
    """
    返回指标结果。
    
    参数：
        symbol: 待分析标的的 A 股股票代码。
        indicator: 需要计算或查询的技术指标名称。
        curr_date: 当前分析或交易日期，格式为 YYYY-MM-DD。
        look_back_days: Number of calendar days to look back from the current date.
    
    返回：
        str: 当前查询结果。
    """
    if indicator not in INDICATOR_DESCRIPTIONS:
        supported = ", ".join(sorted(INDICATOR_DESCRIPTIONS))
        raise ValueError(f"Indicator {indicator} is not supported for A-share analysis. Choose from: {supported}")

    normalized_symbol = normalize_ashare_symbol(symbol)
    aligned_trade_date = get_previous_trade_date(curr_date)
    try:
        indicator_values = _get_indicator_data(symbol, indicator, aligned_trade_date)
    except Exception as exc:  # noqa: BLE001
        return _format_data_error(
            f"## {normalized_symbol} {indicator} values through {aligned_trade_date}",
            exc,
        )
    end = pd.Timestamp(aligned_trade_date)
    start = end - pd.Timedelta(days=look_back_days)

    lines = []
    for date_value in pd.date_range(start=start, end=end, freq="D"):
        date_str = date_value.strftime("%Y-%m-%d")
        lines.append(f"{date_str}: {indicator_values.get(date_str, 'N/A: 非交易日或无数据')}")

    return (
        f"## {normalized_symbol} {indicator} values through {aligned_trade_date}\n\n"
        + "\n".join(lines)
        + "\n\n"
        + INDICATOR_DESCRIPTIONS[indicator]
    )


def get_fundamentals(ticker: str, curr_date: str | None = None) -> str:
    """
    返回基本面数据。
    
    参数：
        ticker: 待分析公司的 A 股股票代码。
        curr_date: 当前分析或交易日期，格式为 YYYY-MM-DD。
    
    返回：
        str: 当前查询结果。
    """
    normalized_symbol = normalize_ashare_symbol(ticker)
    plain_symbol = to_plain_symbol(ticker)
    exchange_symbol = to_exchange_prefixed_symbol(ticker)
    errors = []

    try:
        info_df = _load_company_profile(plain_symbol)
    except Exception as exc:  # noqa: BLE001
        info_df = pd.DataFrame()
        errors.append(f"公司概况接口失败：{type(exc).__name__}: {_safe_truncate(str(exc), 120)}")

    try:
        intro_df = _call_akshare_api(ak.stock_zyjs_ths, symbol=plain_symbol)
    except Exception as exc:  # noqa: BLE001
        intro_df = pd.DataFrame()
        errors.append(f"主营业务简介接口失败：{type(exc).__name__}: {_safe_truncate(str(exc), 120)}")

    try:
        business_df = _call_akshare_api(ak.stock_zygc_em, symbol=exchange_symbol)
    except Exception as exc:  # noqa: BLE001
        business_df = pd.DataFrame()
        errors.append(f"主营构成接口失败：{type(exc).__name__}: {_safe_truncate(str(exc), 120)}")

    try:
        abstract_df = _call_akshare_api(ak.stock_financial_abstract, symbol=plain_symbol)
    except Exception as exc:  # noqa: BLE001
        abstract_df = pd.DataFrame()
        errors.append(f"财务摘要接口失败：{type(exc).__name__}: {_safe_truncate(str(exc), 120)}")

    info_snapshot = info_df.head(20).copy()
    intro_snapshot = intro_df.head(1).copy()
    business_snapshot = business_df.head(6).copy()
    abstract_snapshot = _latest_abstract_snapshot(abstract_df, curr_date) if not abstract_df.empty else pd.DataFrame()

    sections = [
        _format_table(info_snapshot, f"# A-share company profile for {normalized_symbol}", rows=20),
        _format_table(intro_snapshot, "## 主营业务简介", rows=3),
        _format_table(business_snapshot, "## 最新主营构成", rows=6),
        _format_table(abstract_snapshot, "## 最新关键财务摘要", rows=12),
    ]
    if errors:
        sections.append("## 数据获取说明\n\n" + "\n".join(f"- {item}" for item in errors))
    return "\n\n".join(sections)


def get_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    """
    返回资产负债表数据。
    
    参数：
        ticker: 待分析公司的 A 股股票代码。
        freq: Requested reporting frequency, such as quarterly or annual.
        curr_date: 当前分析或交易日期，格式为 YYYY-MM-DD。
    
    返回：
        str: 当前查询结果。
    """
    exchange_symbol = to_exchange_prefixed_symbol(ticker)
    try:
        if freq == "annual":
            df = _call_akshare_api(ak.stock_balance_sheet_by_yearly_em, symbol=exchange_symbol)
        else:
            df = _call_akshare_api(ak.stock_balance_sheet_by_report_em, symbol=exchange_symbol)
    except Exception as exc:  # noqa: BLE001
        return _format_data_error(
            f"# A-share balance sheet for {normalize_ashare_symbol(ticker)} ({freq})",
            exc,
        )

    filtered = _filter_report_rows(df, curr_date)
    selected = _round_numeric_frame(_select_statement_columns(filtered, BALANCE_SHEET_COLUMNS))
    return _format_table(selected, f"# A-share balance sheet for {normalize_ashare_symbol(ticker)} ({freq})", rows=8)


def get_cashflow(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    """
    返回现金流量表数据。
    
    参数：
        ticker: 待分析公司的 A 股股票代码。
        freq: Requested reporting frequency, such as quarterly or annual.
        curr_date: 当前分析或交易日期，格式为 YYYY-MM-DD。
    
    返回：
        str: 当前查询结果。
    """
    exchange_symbol = to_exchange_prefixed_symbol(ticker)
    try:
        if freq == "annual":
            df = _call_akshare_api(ak.stock_cash_flow_sheet_by_quarterly_em, symbol=exchange_symbol)
        else:
            df = _call_akshare_api(ak.stock_cash_flow_sheet_by_report_em, symbol=exchange_symbol)
    except Exception as exc:  # noqa: BLE001
        return _format_data_error(
            f"# A-share cash flow for {normalize_ashare_symbol(ticker)} ({freq})",
            exc,
        )

    filtered = _filter_report_rows(df, curr_date)
    selected = _round_numeric_frame(_select_statement_columns(filtered, CASHFLOW_COLUMNS))
    return _format_table(selected, f"# A-share cash flow for {normalize_ashare_symbol(ticker)} ({freq})", rows=8)


def get_income_statement(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    """
    返回利润表数据。
    
    参数：
        ticker: 待分析公司的 A 股股票代码。
        freq: Requested reporting frequency, such as quarterly or annual.
        curr_date: 当前分析或交易日期，格式为 YYYY-MM-DD。
    
    返回：
        str: 当前查询结果。
    """
    exchange_symbol = to_exchange_prefixed_symbol(ticker)
    try:
        if freq == "annual":
            df = _call_akshare_api(ak.stock_profit_sheet_by_quarterly_em, symbol=exchange_symbol)
        else:
            df = _call_akshare_api(ak.stock_profit_sheet_by_report_em, symbol=exchange_symbol)
    except Exception as exc:  # noqa: BLE001
        return _format_data_error(
            f"# A-share income statement for {normalize_ashare_symbol(ticker)} ({freq})",
            exc,
        )

    filtered = _filter_report_rows(df, curr_date)
    selected = _round_numeric_frame(_select_statement_columns(filtered, INCOME_COLUMNS))
    return _format_table(selected, f"# A-share income statement for {normalize_ashare_symbol(ticker)} ({freq})", rows=8)


def get_news(ticker: str, start_date: str, end_date: str) -> str:
    """
    返回个股新闻数据。
    
    参数：
        ticker: 待分析公司的 A 股股票代码。
        start_date: 起始日期（含当日），格式为 YYYY-MM-DD。
        end_date: 结束日期（含当日），格式为 YYYY-MM-DD。
    
    返回：
        str: 当前查询结果。
    """
    normalized_symbol = normalize_ashare_symbol(ticker)
    plain_symbol = to_plain_symbol(ticker)
    try:
        with _temporary_string_storage("python"):
            df = _call_akshare_api(ak.stock_news_em, symbol=plain_symbol)
    except Exception as exc:  # noqa: BLE001
        return _format_data_error(f"# A-share company news for {normalized_symbol}", exc)
    if df.empty:
        return f"未找到 {normalized_symbol} 的相关新闻。"

    filtered = df.copy()
    filtered["发布时间"] = parse_date_column(filtered["发布时间"])
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date) + timedelta(days=1) - timedelta(seconds=1)
    filtered = filtered[(filtered["发布时间"] >= start) & (filtered["发布时间"] <= end)]
    filtered = filtered.sort_values("发布时间", ascending=False)

    if filtered.empty:
        return f"{normalized_symbol} 在 {start_date} 到 {end_date} 之间没有匹配的新闻。"

    formatted = filtered.loc[:, ["发布时间", "文章来源", "新闻标题", "新闻内容", "新闻链接"]].head(20).copy()
    formatted["发布时间"] = formatted["发布时间"].dt.strftime("%Y-%m-%d %H:%M:%S")
    formatted["新闻内容"] = formatted["新闻内容"].map(_safe_truncate)
    return _format_table(formatted, f"# A-share company news for {normalized_symbol}", rows=20)


def get_market_news(curr_date: str, look_back_days: int = 7, limit: int = 10) -> str:
    """
    返回市场新闻数据。
    
    参数：
        curr_date: 当前分析或交易日期，格式为 YYYY-MM-DD。
        look_back_days: Number of calendar days to look back from the current date.
        limit: 结果中允许保留的最大长度。
    
    返回：
        str: 当前查询结果。
    """
    try:
        df = _call_akshare_api(ak.stock_info_global_em)
    except Exception as exc:  # noqa: BLE001
        return _format_data_error("# A-share market and policy news", exc)
    if df.empty:
        return "未获取到 A 股市场与宏观快讯。"

    filtered = df.copy()
    filtered["发布时间"] = parse_date_column(filtered["发布时间"])
    end = pd.Timestamp(curr_date) + timedelta(days=1) - timedelta(seconds=1)
    start = end - timedelta(days=look_back_days)
    filtered = filtered[(filtered["发布时间"] >= start) & (filtered["发布时间"] <= end)]
    filtered = filtered.sort_values("发布时间", ascending=False)

    if filtered.empty:
        return f"{curr_date} 前 {look_back_days} 天没有可用的市场快讯。"

    formatted = filtered.loc[:, ["发布时间", "标题", "摘要", "链接"]].head(limit).copy()
    formatted["发布时间"] = formatted["发布时间"].dt.strftime("%Y-%m-%d %H:%M:%S")
    formatted["摘要"] = formatted["摘要"].map(lambda value: _safe_truncate(value, 180))
    return _format_table(formatted, "# A-share market and policy news", rows=limit)


def get_company_announcements(
    ticker: str,
    start_date: str,
    end_date: str,
    category: str = "全部",
) -> str:
    """
    返回公司公告数据。
    
    参数：
        ticker: 待分析公司的 A 股股票代码。
        start_date: 起始日期（含当日），格式为 YYYY-MM-DD。
        end_date: 结束日期（含当日），格式为 YYYY-MM-DD。
        category: Category name or announcement category for the request.
    
    返回：
        str: 当前查询结果。
    """
    normalized_symbol = normalize_ashare_symbol(ticker)
    plain_symbol = to_plain_symbol(ticker)

    # 优先使用巨潮资讯按股票+时间区间查询的接口，避免逐日扫描公告池导致主流程过慢。
    cninfo_category = ""
    normalized_category = str(category or "").strip()
    if normalized_category in {"", "全部"}:
        cninfo_category = ""
    else:
        cninfo_category_map = {
            "风险提示": "风险提示",
            "持股变动": "股权变动",
            "股权激励": "股权激励",
            "公司治理": "公司治理",
            "日常经营": "日常经营",
            "董事会": "董事会",
            "监事会": "监事会",
            "股东大会": "股东大会",
            "补充更正": "补充更正",
            "澄清致歉": "澄清致歉",
            "特别处理和退市": "特别处理和退市",
        }
        cninfo_category = cninfo_category_map.get(normalized_category, "")

    if normalized_category in {"", "全部"} or cninfo_category:
        try:
            with _suppress_akshare_progress():
                direct = _call_akshare_api(
                    ak.stock_zh_a_disclosure_report_cninfo,
                    symbol=plain_symbol,
                    market="沪深京",
                    category=cninfo_category,
                    start_date=format_date_for_api(start_date),
                    end_date=format_date_for_api(end_date),
                    retries=2,
                    retry_delay=0.5,
                )
            if not direct.empty:
                combined = direct.rename(
                    columns={
                        "公告时间": "公告日期",
                        "公告链接": "网址",
                    }
                ).copy()
                combined["公告日期"] = parse_date_column(combined["公告日期"])
                combined["公告类型"] = normalized_category or "公告"
                combined = combined.sort_values("公告日期", ascending=False).drop_duplicates(
                    subset=["公告标题", "公告日期"]
                )
                formatted = combined.loc[:, ["公告日期", "公告类型", "公告标题", "网址"]].head(20).copy()
                formatted["公告日期"] = formatted["公告日期"].dt.strftime("%Y-%m-%d")
                return _format_table(
                    formatted,
                    f"# A-share company announcements for {normalized_symbol}",
                    rows=20,
                )
        except Exception:
            # 保留原有逐日扫描逻辑作为兼容兜底。
            pass

    frames = []
    errors = []

    for date_value in get_date_range(start_date, end_date):
        try:
            with _suppress_akshare_progress():
                daily = _call_akshare_api(
                    ak.stock_notice_report,
                    symbol=category,
                    date=format_date_for_api(date_value),
                    retries=2,
                    retry_delay=0.5,
                )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{date_value}: {type(exc).__name__}: {_safe_truncate(str(exc), 100)}")
            continue
        if daily.empty:
            continue
        matched = daily[daily["代码"].astype(str).str.upper() == plain_symbol]
        if not matched.empty:
            frames.append(matched)

    if not frames:
        if errors:
            return (
                f"{normalized_symbol} 在 {start_date} 到 {end_date} 之间未能稳定获取公告数据。\n\n"
                + "\n".join(errors[:5])
            )
        return f"{normalized_symbol} 在 {start_date} 到 {end_date} 之间没有匹配的公告。"

    combined = pd.concat(frames, ignore_index=True)
    combined["公告日期"] = parse_date_column(combined["公告日期"])
    combined = combined.sort_values("公告日期", ascending=False).drop_duplicates(subset=["公告标题", "公告日期"])
    formatted = combined.loc[:, ["公告日期", "公告类型", "公告标题", "网址"]].head(20).copy()
    formatted["公告日期"] = formatted["公告日期"].dt.strftime("%Y-%m-%d")
    output = _format_table(formatted, f"# A-share company announcements for {normalized_symbol}", rows=20)
    if errors:
        output += "\n\n## 数据获取说明\n\n" + "\n".join(f"- {item}" for item in errors[:5])
    return output
