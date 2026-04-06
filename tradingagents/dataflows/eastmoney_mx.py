from __future__ import annotations

import os
from datetime import timedelta

import pandas as pd
import requests

from .a_share_common import normalize_ashare_symbol, to_plain_symbol


MX_QUERY_URL = "https://mkapi2.dfcfs.com/finskillshub/api/claw/query"
MX_SEARCH_URL = "https://mkapi2.dfcfs.com/finskillshub/api/claw/news-search"
MX_TIMEOUT = 30
MX_INFO_TYPE_LABELS = {
    "REPORT": "研报",
    "NEWS": "新闻",
    "ANNOUNCEMENT": "公告",
}


def _get_mx_api_key() -> str:
    """
    获取妙想 API Key。

    返回：
        str: 可用的 API Key。
    """
    for env_name in ("MX_APIKEY", "EASTMONEY_APIKEY"):
        value = os.getenv(env_name, "").strip()
        if value:
            return value
    raise RuntimeError("Missing MX_APIKEY or EASTMONEY_APIKEY for Eastmoney MX vendor.")


def _post_mx(url: str, payload: dict) -> dict:
    """
    调用妙想 HTTP 接口并返回 JSON。

    参数：
        url: 接口地址。
        payload: 请求载荷。

    返回：
        dict: 解析后的 JSON 响应。
    """
    response = requests.post(
        url,
        headers={
            "Content-Type": "application/json",
            "apikey": _get_mx_api_key(),
        },
        json=payload,
        timeout=MX_TIMEOUT,
    )
    response.raise_for_status()
    result = response.json()
    status = result.get("status")
    if status not in (0, None):
        raise RuntimeError(result.get("message") or f"MX API returned status={status}")
    return result


def _format_table(df: pd.DataFrame, title: str, rows: int = 10) -> str:
    """
    将 DataFrame 渲染为 Markdown 风格文本。

    参数：
        df: 数据表。
        title: 标题。
        rows: 最多保留的行数。

    返回：
        str: 格式化后的文本。
    """
    if df.empty:
        return f"{title}\n\n暂无数据。"
    return f"{title}\n\n{df.head(rows).to_csv(index=False)}"


def _safe_truncate(text: str, limit: int = 180) -> str:
    """
    安全截断文本。

    参数：
        text: 原始文本。
        limit: 最大长度。

    返回：
        str: 截断后的文本。
    """
    clean = " ".join(str(text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3] + "..."


def _extract_query_tables(result: dict) -> list[dict]:
    """
    从查数响应中抽取 dataTableDTOList。

    参数：
        result: 接口返回结果。

    返回：
        list[dict]: 表格定义列表。
    """
    data = result.get("data") or {}
    inner = data.get("data") or {}
    search_result = inner.get("searchDataResultDTO") or data.get("searchDataResultDTO") or {}
    tables = search_result.get("dataTableDTOList") or data.get("dataTableDTOList") or []
    return [item for item in tables if isinstance(item, dict)]


def _normalize_name_map(name_map: object) -> dict[str, str]:
    """
    标准化 nameMap 结构。

    参数：
        name_map: 原始 nameMap。

    返回：
        dict[str, str]: 规范化后的字段映射。
    """
    if isinstance(name_map, dict):
        return {str(key): str(value) for key, value in name_map.items() if value not in (None, "")}
    if isinstance(name_map, list):
        return {str(index): str(value) for index, value in enumerate(name_map) if value not in (None, "")}
    return {}


def _ordered_indicator_keys(table: dict, indicator_order: list | None) -> list[str]:
    """
    生成指标字段顺序。

    参数：
        table: 表格对象。
        indicator_order: 接口返回的字段顺序。

    返回：
        list[str]: 已排序的字段列表。
    """
    data_keys = [str(key) for key in table.keys() if str(key) != "headName"]
    preferred = []
    seen = set()
    for key in indicator_order or []:
        key_str = str(key)
        if key_str in data_keys and key_str not in seen:
            preferred.append(key_str)
            seen.add(key_str)
    for key in data_keys:
        if key not in seen:
            preferred.append(key)
            seen.add(key)
    return preferred


def _resolve_indicator_label(key: str, name_map: dict[str, str]) -> str:
    """
    解析指标展示名。

    参数：
        key: 原始字段键。
        name_map: 字段名映射。

    返回：
        str: 展示名。
    """
    return name_map.get(key) or key


def _dto_to_frame(dto: dict) -> pd.DataFrame:
    """
    将妙想表格定义转换为 DataFrame。

    参数：
        dto: 单个 dataTableDTO。

    返回：
        pd.DataFrame: 转换后的表格。
    """
    table = dto.get("table") or {}
    if not isinstance(table, dict) or not table:
        return pd.DataFrame()

    name_map = _normalize_name_map(dto.get("nameMap"))
    indicator_keys = _ordered_indicator_keys(table, dto.get("indicatorOrder") or [])
    head_values = table.get("headName") or []
    if not isinstance(head_values, list):
        head_values = []

    if head_values:
        rows = []
        for row_index, head_value in enumerate(head_values):
            row = {"日期": head_value}
            for key in indicator_keys:
                raw_values = table.get(key, [])
                if not isinstance(raw_values, list):
                    raw_values = [raw_values]
                row[_resolve_indicator_label(key, name_map)] = raw_values[row_index] if row_index < len(raw_values) else ""
            rows.append(row)
        return pd.DataFrame(rows)

    rows = []
    for key in indicator_keys:
        raw_values = table.get(key, [])
        if isinstance(raw_values, list):
            value = raw_values[0] if raw_values else ""
        else:
            value = raw_values
        rows.append(
            {
                "指标": _resolve_indicator_label(key, name_map),
                "数值": value,
            }
        )
    return pd.DataFrame(rows)


def _extract_search_items(result: dict) -> list[dict]:
    """
    从资讯检索结果中抽取资讯列表。

    参数：
        result: 接口返回结果。

    返回：
        list[dict]: 资讯对象列表。
    """
    data = result.get("data") or {}
    inner = data.get("data") or {}
    llm_response = inner.get("llmSearchResponse") or inner.get("searchResponse") or {}
    items = llm_response.get("data") or []
    return [item for item in items if isinstance(item, dict)]


def _filter_items_by_date(items: list[dict], start_date: str, end_date: str) -> list[dict]:
    """
    按日期范围过滤资讯。

    参数：
        items: 原始资讯列表。
        start_date: 起始日期。
        end_date: 结束日期。

    返回：
        list[dict]: 过滤后的资讯列表。
    """
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date) + timedelta(days=1) - timedelta(seconds=1)
    filtered = []
    for item in items:
        published = pd.to_datetime(item.get("date"), errors="coerce")
        if pd.isna(published):
            continue
        if start <= published <= end:
            enriched = dict(item)
            enriched["_published"] = published
            filtered.append(enriched)
    return sorted(filtered, key=lambda value: value["_published"], reverse=True)


def _filter_items_by_symbol(items: list[dict], plain_symbol: str) -> list[dict]:
    """
    按关联证券代码过滤资讯。

    参数：
        items: 原始资讯列表。
        plain_symbol: 六位股票代码。

    返回：
        list[dict]: 过滤后的资讯列表。
    """
    matched = []
    for item in items:
        secu_list = item.get("secuList") or []
        if not isinstance(secu_list, list):
            secu_list = []
        codes = {str(entry.get("secuCode", "")).strip() for entry in secu_list if isinstance(entry, dict)}
        if plain_symbol in codes:
            matched.append(item)
    return matched or items


def _prefer_information_type(items: list[dict], info_type: str) -> list[dict]:
    """
    优先保留指定资讯类型；若没有匹配项，则返回原列表。

    参数：
        items: 原始资讯列表。
        info_type: 目标资讯类型。

    返回：
        list[dict]: 过滤后的结果列表。
    """
    matched = [
        item
        for item in items
        if str(item.get("informationType") or "").strip().upper() == info_type.upper()
    ]
    return matched or items


def _format_search_rows(items: list[dict], title: str, rows: int = 10) -> str:
    """
    将资讯列表格式化为文本表。

    参数：
        items: 资讯对象列表。
        title: 标题。
        rows: 最大行数。

    返回：
        str: 格式化结果。
    """
    if not items:
        return f"{title}\n\n暂无数据。"

    formatted_rows = []
    for item in items[:rows]:
        secu_names = []
        for secu in item.get("secuList") or []:
            if not isinstance(secu, dict):
                continue
            name = str(secu.get("secuName") or "").strip()
            code = str(secu.get("secuCode") or "").strip()
            if name or code:
                secu_names.append(f"{name}({code})" if name and code else name or code)
        formatted_rows.append(
            {
                "发布时间": item["_published"].strftime("%Y-%m-%d %H:%M:%S") if "_published" in item else str(item.get("date", "")),
                "类型": MX_INFO_TYPE_LABELS.get(str(item.get("informationType") or "").upper(), str(item.get("informationType") or "")),
                "标题": item.get("title", ""),
                "内容": _safe_truncate(item.get("content") or item.get("trunk") or ""),
                "机构": item.get("insName", ""),
                "关联证券": "；".join(secu_names),
            }
        )
    return _format_table(pd.DataFrame(formatted_rows), title, rows=rows)


def get_fundamentals(ticker: str, curr_date: str | None = None) -> str:
    """
    使用妙想查数接口获取综合基本面摘要。

    参数：
        ticker: 股票代码。
        curr_date: 当前分析日期。

    返回：
        str: 格式化后的基本面摘要。
    """
    normalized_symbol = normalize_ashare_symbol(ticker)
    plain_symbol = to_plain_symbol(ticker)
    query = f"{plain_symbol} 公司概况 主营业务 财务指标 归母净利润 扣非净利润 经营现金流 资产负债率 ROE"
    if curr_date:
        query += f" 截至{curr_date}"

    result = _post_mx(MX_QUERY_URL, {"toolQuery": query})
    tables = _extract_query_tables(result)
    if not tables:
        raise RuntimeError(f"MX fundamentals returned no structured tables for {normalized_symbol}.")

    sections = [f"# A-share company profile for {normalized_symbol}"]
    for dto in tables:
        title = str(dto.get("title") or dto.get("entityName") or "妙想基本面数据").strip()
        frame = _dto_to_frame(dto)
        sections.append(_format_table(frame, f"## {title}", rows=12))
    return "\n\n".join(sections)


def get_news(ticker: str, start_date: str, end_date: str) -> str:
    """
    使用妙想资讯检索接口获取个股新闻。

    参数：
        ticker: 股票代码。
        start_date: 起始日期。
        end_date: 结束日期。

    返回：
        str: 格式化后的个股新闻。
    """
    normalized_symbol = normalize_ashare_symbol(ticker)
    plain_symbol = to_plain_symbol(ticker)
    query = f"{plain_symbol} 个股新闻 公司资讯 研报 {start_date} 至 {end_date}"
    items = _extract_search_items(_post_mx(MX_SEARCH_URL, {"query": query}))
    dated = _filter_items_by_date(items, start_date, end_date)
    filtered = _filter_items_by_symbol(dated, plain_symbol)
    if not filtered:
        return f"{normalized_symbol} 在 {start_date} 到 {end_date} 之间没有匹配的新闻。"
    return _format_search_rows(filtered, f"# A-share company news for {normalized_symbol}", rows=20)


def get_market_news(curr_date: str, look_back_days: int = 7, limit: int = 10) -> str:
    """
    使用妙想资讯检索接口获取 A 股市场新闻。

    参数：
        curr_date: 当前日期。
        look_back_days: 回看天数。
        limit: 最大返回条数。

    返回：
        str: 格式化后的市场新闻。
    """
    start_date = (pd.Timestamp(curr_date) - timedelta(days=look_back_days)).strftime("%Y-%m-%d")
    query = f"A股 市场 政策 宏观 新闻 {start_date} 至 {curr_date}"
    items = _extract_search_items(_post_mx(MX_SEARCH_URL, {"query": query}))
    filtered = _filter_items_by_date(items, start_date, curr_date)
    if not filtered:
        return f"{curr_date} 前 {look_back_days} 天没有可用的市场快讯。"
    return _format_search_rows(filtered, "# A-share market and policy news", rows=limit)


def get_company_announcements(
    ticker: str,
    start_date: str,
    end_date: str,
    category: str = "全部",
) -> str:
    """
    使用妙想资讯检索接口获取个股公告。

    参数：
        ticker: 股票代码。
        start_date: 起始日期。
        end_date: 结束日期。
        category: 公告分类。

    返回：
        str: 格式化后的公告列表。
    """
    normalized_symbol = normalize_ashare_symbol(ticker)
    plain_symbol = to_plain_symbol(ticker)
    category_fragment = "" if not category or category == "全部" else f"{category} "
    query = f"{plain_symbol} {category_fragment}公告 {start_date} 至 {end_date}"
    items = _extract_search_items(_post_mx(MX_SEARCH_URL, {"query": query}))
    dated = _filter_items_by_date(items, start_date, end_date)
    filtered = _filter_items_by_symbol(dated, plain_symbol)
    filtered = _prefer_information_type(filtered, "ANNOUNCEMENT")
    if not filtered:
        return f"{normalized_symbol} 在 {start_date} 到 {end_date} 之间没有匹配的公告。"
    return _format_search_rows(filtered, f"# A-share company announcements for {normalized_symbol}", rows=20)
