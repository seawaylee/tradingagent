from __future__ import annotations

import os
import re
from datetime import timedelta

import akshare as ak
import pandas as pd
from stockstats import wrap

from .a_share import (
    INDICATOR_DESCRIPTIONS,
    _call_akshare_api,
    _format_data_error,
    _format_table,
    _round_numeric_frame,
    _safe_truncate,
)
from .a_share_common import format_date_for_api, parse_date_column
from .config import get_config
from .market_symbols import normalize_hk_symbol


HK_BALANCE_SHEET_ITEMS = [
    "总资产",
    "总负债",
    "股东权益合计",
    "现金及现金等价物",
    "存货",
    "应收账款",
    "商誉",
]

HK_CASHFLOW_ITEMS = [
    "经营业务现金净额",
    "投资业务现金净额",
    "融资业务现金净额",
    "融资前现金净额",
    "现金净额",
]

HK_INCOME_ITEMS = [
    "营业额",
    "营运收入",
    "毛利",
    "营业利润",
    "除税前利润",
    "本年度溢利",
    "股东应占溢利",
]

HK_CORE_INDICATOR_COLUMNS = [
    "基本每股收益(元)",
    "每股净资产(元)",
    "每股经营现金流(元)",
    "营业总收入",
    "营业总收入滚动环比增长(%)",
    "净利润",
    "净利润滚动环比增长(%)",
    "股东权益回报率(%)",
    "市盈率",
    "市净率",
    "总资产回报率(%)",
]

HK_ANNOUNCEMENT_KEYWORDS = (
    "公告",
    "通函",
    "业绩",
    "年报",
    "中报",
    "季报",
    "财报",
    "回购",
    "派息",
    "分红",
    "董事会",
    "股东大会",
    "配售",
    "增发",
    "委任",
    "更换核数师",
)


def _clean_hk_ohlcv(data: pd.DataFrame) -> pd.DataFrame:
    """
    将港股 OHLCV 数据规范化为统一格式。

    参数：
        data: 输入数据表。

    返回：
        pd.DataFrame: 处理后的行情数据。
    """
    renamed = data.rename(
        columns={
            "日期": "Date",
            "date": "Date",
            "开盘": "Open",
            "open": "Open",
            "最高": "High",
            "high": "High",
            "最低": "Low",
            "low": "Low",
            "收盘": "Close",
            "close": "Close",
            "成交量": "Volume",
            "volume": "Volume",
            "成交额": "Amount",
            "amount": "Amount",
            "换手率": "TurnoverPct",
            "涨跌幅": "PctChange",
        }
    ).copy()
    renamed["Date"] = pd.to_datetime(renamed["Date"], errors="coerce")
    renamed = renamed.dropna(subset=["Date", "Close"])

    for column in ["Open", "High", "Low", "Close", "Volume"]:
        if column in renamed.columns:
            renamed[column] = pd.to_numeric(renamed[column], errors="coerce")

    renamed = renamed.dropna(subset=["Close"])
    return renamed


def _load_hk_hist(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    获取港股历史行情。

    参数：
        symbol: 待分析标的的港股代码。
        start_date: 起始日期（含当日），格式为 YYYY-MM-DD。
        end_date: 结束日期（含当日），格式为 YYYY-MM-DD。

    返回：
        pd.DataFrame: 原始行情数据表。
    """
    normalized_symbol = normalize_hk_symbol(symbol)
    plain_symbol = normalized_symbol.split(".", 1)[0]
    try:
        return _call_akshare_api(
            ak.stock_hk_hist,
            symbol=plain_symbol,
            period="daily",
            start_date=format_date_for_api(start_date),
            end_date=format_date_for_api(end_date),
            adjust="qfq",
        )
    except Exception:  # noqa: BLE001
        fallback = _call_akshare_api(
            ak.stock_hk_daily,
            symbol=plain_symbol,
            adjust="qfq",
        )
        fallback = fallback.copy()
        fallback["date"] = pd.to_datetime(fallback["date"], errors="coerce")
        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date)
        return fallback[(fallback["date"] >= start) & (fallback["date"] <= end)]


def _load_hk_ohlcv(symbol: str, curr_date: str) -> pd.DataFrame:
    """
    加载港股技术指标所需 OHLCV 数据，并在本地缓存。

    参数：
        symbol: 待分析标的的港股代码。
        curr_date: 当前分析日期，格式为 YYYY-MM-DD。

    返回：
        pd.DataFrame: 清洗后的 OHLCV 数据。
    """
    config = get_config()
    normalized_symbol = normalize_hk_symbol(symbol)
    end = pd.Timestamp(curr_date).normalize()
    start = end - pd.DateOffset(years=5)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    os.makedirs(config["data_cache_dir"], exist_ok=True)
    cache_file = os.path.join(
        config["data_cache_dir"],
        f"{normalized_symbol.replace('.', '_')}-hk-akshare-qfq-{start_str}-{end_str}.csv",
    )

    if os.path.exists(cache_file):
        data = pd.read_csv(cache_file, on_bad_lines="skip")
    else:
        data = _load_hk_hist(symbol, start_str, end_str)
        data.to_csv(cache_file, index=False, encoding="utf-8-sig")

    cleaned = _clean_hk_ohlcv(data)
    return cleaned[cleaned["Date"] <= end]


def _get_indicator_data(symbol: str, indicator: str, curr_date: str) -> tuple[str, dict[str, str]]:
    """
    计算港股技术指标序列。

    参数：
        symbol: 待分析标的的港股代码。
        indicator: 技术指标名称。
        curr_date: 当前分析日期，格式为 YYYY-MM-DD。

    返回：
        tuple[str, dict[str, str]]: 对齐后的最近交易日与指标文本映射。
    """
    data = _load_hk_ohlcv(symbol, curr_date)
    if data.empty:
        raise ValueError(f"No Hong Kong stock price data available on or before {curr_date}.")

    aligned_trade_date = data["Date"].max().strftime("%Y-%m-%d")
    df = wrap(data.copy())
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df[indicator]

    result = {}
    for _, row in df.iterrows():
        value = row[indicator]
        result[row["Date"]] = "N/A" if pd.isna(value) else str(value)
    return aligned_trade_date, result


def _load_hk_statement(symbol: str, statement_name: str, freq: str) -> pd.DataFrame:
    """
    获取港股财务报表明细。

    参数：
        symbol: 待分析标的的港股代码。
        statement_name: 报表名称。
        freq: annual 或 quarterly。

    返回：
        pd.DataFrame: 报表明细。
    """
    normalized_symbol = normalize_hk_symbol(symbol)
    plain_symbol = normalized_symbol.split(".", 1)[0]
    indicator = "年度" if freq == "annual" else "报告期"
    return _call_akshare_api(
        ak.stock_financial_hk_report_em,
        stock=plain_symbol,
        symbol=statement_name,
        indicator=indicator,
    )


def _latest_statement_snapshot(
    df: pd.DataFrame,
    curr_date: str | None,
    preferred_items: list[str],
) -> pd.DataFrame:
    """
    提取港股报表最近一期关键科目快照。

    参数：
        df: 报表明细。
        curr_date: 当前分析日期，格式为 YYYY-MM-DD。
        preferred_items: 需要保留的关键科目。

    返回：
        pd.DataFrame: 单行或双列表格快照。
    """
    if df.empty:
        return df

    filtered = df.copy()
    filtered["REPORT_DATE"] = parse_date_column(filtered["REPORT_DATE"])
    if curr_date:
        cutoff = pd.Timestamp(curr_date)
        filtered = filtered[filtered["REPORT_DATE"] <= cutoff]
    if filtered.empty:
        filtered = df.copy()
        filtered["REPORT_DATE"] = parse_date_column(filtered["REPORT_DATE"])

    latest_date = filtered["REPORT_DATE"].max()
    latest = filtered[filtered["REPORT_DATE"] == latest_date].copy()
    selected = latest[latest["STD_ITEM_NAME"].isin(preferred_items)].copy()

    if selected.empty:
        selected = latest.loc[:, ["STD_ITEM_NAME", "AMOUNT"]].head(8).copy()
        selected.insert(0, "REPORT_DATE", latest_date.strftime("%Y-%m-%d"))
        return _round_numeric_frame(selected)

    row = {"REPORT_DATE": latest_date.strftime("%Y-%m-%d")}
    for item in preferred_items:
        item_rows = selected[selected["STD_ITEM_NAME"] == item]
        if not item_rows.empty:
            row[item] = item_rows["AMOUNT"].iloc[0]
    return _round_numeric_frame(pd.DataFrame([row]))


def get_stock_data(symbol: str, start_date: str, end_date: str) -> str:
    """
    返回港股行情数据。

    参数：
        symbol: 待分析标的的港股代码。
        start_date: 起始日期（含当日），格式为 YYYY-MM-DD。
        end_date: 结束日期（含当日），格式为 YYYY-MM-DD。

    返回：
        str: 当前查询结果。
    """
    normalized_symbol = normalize_hk_symbol(symbol)

    try:
        df = _load_hk_hist(symbol, start_date, end_date)
    except Exception as exc:  # noqa: BLE001
        return _format_data_error(
            f"# Hong Kong stock price data for {normalized_symbol} from {start_date} to {end_date}",
            exc,
        )

    if df.empty:
        return f"未找到 {normalized_symbol} 在 {start_date} 到 {end_date} 之间的港股行情数据。"

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
            "volume": "Volume",
            "成交额": "Amount",
            "amount": "Amount",
            "振幅": "AmplitudePct",
            "涨跌幅": "PctChange",
            "涨跌额": "PriceChange",
            "换手率": "TurnoverPct",
        }
    ).copy()
    renamed["Date"] = pd.to_datetime(renamed["Date"], errors="coerce").dt.strftime("%Y-%m-%d")
    if "PctChange" not in renamed.columns and "Close" in renamed.columns:
        renamed["PctChange"] = renamed["Close"].pct_change().mul(100).round(4)

    selected_columns = [
        column
        for column in ["Date", "Open", "High", "Low", "Close", "Volume", "Amount", "PctChange", "TurnoverPct"]
        if column in renamed.columns
    ]
    output = _round_numeric_frame(renamed.loc[:, selected_columns])
    header = f"# Hong Kong stock price data for {normalized_symbol} from {start_date} to {end_date}\n"
    header += f"# Records: {len(output)}\n\n"
    return header + output.to_csv(index=False)


def get_indicators(symbol: str, indicator: str, curr_date: str, look_back_days: int) -> str:
    """
    返回港股技术指标数据。

    参数：
        symbol: 待分析标的的港股代码。
        indicator: 技术指标名称。
        curr_date: 当前分析日期，格式为 YYYY-MM-DD。
        look_back_days: 回看自然日天数。

    返回：
        str: 当前查询结果。
    """
    if indicator not in INDICATOR_DESCRIPTIONS:
        supported = ", ".join(sorted(INDICATOR_DESCRIPTIONS))
        raise ValueError(
            f"Indicator {indicator} is not supported for Hong Kong stock analysis. Choose from: {supported}"
        )

    normalized_symbol = normalize_hk_symbol(symbol)
    try:
        aligned_trade_date, indicator_values = _get_indicator_data(symbol, indicator, curr_date)
    except Exception as exc:  # noqa: BLE001
        return _format_data_error(
            f"## {normalized_symbol} {indicator} values through {curr_date}",
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
    返回港股基本面摘要。

    参数：
        ticker: 待分析标的的港股代码。
        curr_date: 当前分析日期，格式为 YYYY-MM-DD。

    返回：
        str: 当前查询结果。
    """
    normalized_symbol = normalize_hk_symbol(ticker)
    plain_symbol = normalized_symbol.split(".", 1)[0]
    errors = []

    try:
        profile_df = _call_akshare_api(ak.stock_hk_company_profile_em, symbol=plain_symbol)
    except Exception as exc:  # noqa: BLE001
        profile_df = pd.DataFrame()
        errors.append(f"公司资料接口失败：{type(exc).__name__}: {_safe_truncate(str(exc), 120)}")

    try:
        security_df = _call_akshare_api(ak.stock_hk_security_profile_em, symbol=plain_symbol)
    except Exception as exc:  # noqa: BLE001
        security_df = pd.DataFrame()
        errors.append(f"证券资料接口失败：{type(exc).__name__}: {_safe_truncate(str(exc), 120)}")

    try:
        indicator_df = _call_akshare_api(ak.stock_hk_financial_indicator_em, symbol=plain_symbol)
    except Exception as exc:  # noqa: BLE001
        indicator_df = pd.DataFrame()
        errors.append(f"核心指标接口失败：{type(exc).__name__}: {_safe_truncate(str(exc), 120)}")

    indicator_columns = [column for column in HK_CORE_INDICATOR_COLUMNS if column in indicator_df.columns]
    indicator_snapshot = indicator_df.loc[:, indicator_columns].head(1).copy() if indicator_columns else pd.DataFrame()
    indicator_snapshot = _round_numeric_frame(indicator_snapshot)

    sections = [
        _format_table(profile_df.head(1), f"# Hong Kong stock company profile for {normalized_symbol}", rows=5),
        _format_table(security_df.head(1), "## 证券资料", rows=5),
        _format_table(indicator_snapshot, "## 核心财务指标", rows=10),
    ]
    if errors:
        sections.append("## 数据获取说明\n\n" + "\n".join(f"- {item}" for item in errors))
    return "\n\n".join(sections)


def get_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    """
    返回港股资产负债表关键科目。

    参数：
        ticker: 待分析标的的港股代码。
        freq: annual 或 quarterly。
        curr_date: 当前分析日期，格式为 YYYY-MM-DD。

    返回：
        str: 当前查询结果。
    """
    normalized_symbol = normalize_hk_symbol(ticker)
    try:
        df = _load_hk_statement(ticker, "资产负债表", freq)
    except Exception as exc:  # noqa: BLE001
        return _format_data_error(
            f"# Hong Kong stock balance sheet for {normalized_symbol} ({freq})",
            exc,
        )

    snapshot = _latest_statement_snapshot(df, curr_date, HK_BALANCE_SHEET_ITEMS)
    return _format_table(snapshot, f"# Hong Kong stock balance sheet for {normalized_symbol} ({freq})", rows=8)


def get_cashflow(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    """
    返回港股现金流量表关键科目。

    参数：
        ticker: 待分析标的的港股代码。
        freq: annual 或 quarterly。
        curr_date: 当前分析日期，格式为 YYYY-MM-DD。

    返回：
        str: 当前查询结果。
    """
    normalized_symbol = normalize_hk_symbol(ticker)
    try:
        df = _load_hk_statement(ticker, "现金流量表", freq)
    except Exception as exc:  # noqa: BLE001
        return _format_data_error(
            f"# Hong Kong stock cash flow for {normalized_symbol} ({freq})",
            exc,
        )

    snapshot = _latest_statement_snapshot(df, curr_date, HK_CASHFLOW_ITEMS)
    return _format_table(snapshot, f"# Hong Kong stock cash flow for {normalized_symbol} ({freq})", rows=8)


def get_income_statement(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    """
    返回港股利润表关键科目。

    参数：
        ticker: 待分析标的的港股代码。
        freq: annual 或 quarterly。
        curr_date: 当前分析日期，格式为 YYYY-MM-DD。

    返回：
        str: 当前查询结果。
    """
    normalized_symbol = normalize_hk_symbol(ticker)
    try:
        df = _load_hk_statement(ticker, "利润表", freq)
    except Exception as exc:  # noqa: BLE001
        return _format_data_error(
            f"# Hong Kong stock income statement for {normalized_symbol} ({freq})",
            exc,
        )

    snapshot = _latest_statement_snapshot(df, curr_date, HK_INCOME_ITEMS)
    return _format_table(snapshot, f"# Hong Kong stock income statement for {normalized_symbol} ({freq})", rows=8)


def get_news(ticker: str, start_date: str, end_date: str) -> str:
    """
    返回港股个股新闻。

    参数：
        ticker: 待分析标的的港股代码。
        start_date: 起始日期（含当日），格式为 YYYY-MM-DD。
        end_date: 结束日期（含当日），格式为 YYYY-MM-DD。

    返回：
        str: 当前查询结果。
    """
    normalized_symbol = normalize_hk_symbol(ticker)
    plain_symbol = normalized_symbol.split(".", 1)[0]
    try:
        df = _call_akshare_api(ak.stock_news_em, symbol=plain_symbol)
    except Exception as exc:  # noqa: BLE001
        return _format_data_error(f"# Hong Kong stock company news for {normalized_symbol}", exc)
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
    return _format_table(formatted, f"# Hong Kong stock company news for {normalized_symbol}", rows=20)


def get_company_announcements(
    ticker: str,
    start_date: str,
    end_date: str,
    category: str = "全部",
) -> str:
    """
    返回港股公告代理结果。

    参数：
        ticker: 待分析标的的港股代码。
        start_date: 起始日期（含当日），格式为 YYYY-MM-DD。
        end_date: 结束日期（含当日），格式为 YYYY-MM-DD。
        category: 公告类别，占位保留。

    返回：
        str: 当前查询结果。
    """
    normalized_symbol = normalize_hk_symbol(ticker)
    plain_symbol = normalized_symbol.split(".", 1)[0]
    try:
        df = _call_akshare_api(ak.stock_news_em, symbol=plain_symbol)
    except Exception as exc:  # noqa: BLE001
        return _format_data_error(f"# Hong Kong stock company announcements for {normalized_symbol}", exc)
    if df.empty:
        return f"未找到 {normalized_symbol} 的公告代理数据。"

    filtered = df.copy()
    filtered["发布时间"] = parse_date_column(filtered["发布时间"])
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date) + timedelta(days=1) - timedelta(seconds=1)
    filtered = filtered[(filtered["发布时间"] >= start) & (filtered["发布时间"] <= end)]

    pattern = "|".join(re.escape(keyword) for keyword in HK_ANNOUNCEMENT_KEYWORDS)
    title_series = filtered["新闻标题"].fillna("").astype(str)
    content_series = filtered["新闻内容"].fillna("").astype(str)
    filtered = filtered[
        title_series.str.contains(pattern, case=False, regex=True)
        | content_series.str.contains(pattern, case=False, regex=True)
    ]
    filtered = filtered.sort_values("发布时间", ascending=False)

    if filtered.empty:
        return f"{normalized_symbol} 在 {start_date} 到 {end_date} 之间没有匹配的公告代理数据。"

    formatted = filtered.loc[:, ["发布时间", "新闻标题", "文章来源", "新闻链接"]].head(20).copy()
    formatted.columns = ["公告日期", "公告标题", "来源", "网址"]
    formatted["公告日期"] = formatted["公告日期"].dt.strftime("%Y-%m-%d %H:%M:%S")
    output = _format_table(formatted, f"# Hong Kong stock company announcements for {normalized_symbol}", rows=20)
    output += "\n\n## 数据说明\n\n- 当前港股公告使用东方财富新闻流中的披露类内容作为代理结果。"
    return output
