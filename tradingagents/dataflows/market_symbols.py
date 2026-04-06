from __future__ import annotations

import re

from .a_share_common import normalize_ashare_symbol


def normalize_hk_symbol(symbol: str) -> str:
    """
    将用户输入规范化为 ``01810.HK``。

    参数：
        symbol: 待分析标的的港股代码。

    返回：
        str: 规范化后的代码结果。
    """
    normalized = symbol.strip().upper().replace(" ", "")
    if not normalized:
        raise ValueError("Ticker symbol cannot be empty.")

    exchange_prefix_match = re.fullmatch(r"HK(\d{4,5})", normalized)
    if exchange_prefix_match:
        return f"{exchange_prefix_match.group(1).zfill(5)}.HK"

    exchange_suffix_match = re.fullmatch(r"(\d{4,5})\.HK", normalized)
    if exchange_suffix_match:
        return f"{exchange_suffix_match.group(1).zfill(5)}.HK"

    digits_match = re.fullmatch(r"\d{4,5}", normalized)
    if digits_match:
        return f"{digits_match.group(0).zfill(5)}.HK"

    raise ValueError(
        "Unsupported Hong Kong stock symbol format. Use a 4/5-digit code such as 1810 or 01810."
    )


def normalize_market_symbol(symbol: str) -> str:
    """
    规范化 A 股或港股代码。

    参数：
        symbol: 待分析标的代码。

    返回：
        str: 规范化后的带市场后缀代码。
    """
    errors = []
    for normalizer in (normalize_ashare_symbol, normalize_hk_symbol):
        try:
            return normalizer(symbol)
        except ValueError as exc:
            errors.append(str(exc))

    raise ValueError("Unsupported ticker symbol format. " + " ".join(errors))


def is_hk_symbol(symbol: str) -> bool:
    """
    判断代码是否为港股。

    参数：
        symbol: 待分析标的代码。

    返回：
        bool: 条件满足时返回 True，否则返回 False。
    """
    try:
        return normalize_hk_symbol(symbol).endswith(".HK")
    except ValueError:
        return False


def get_market_label(symbol: str) -> str:
    """
    返回代码对应的市场标签。

    参数：
        symbol: 待分析标的代码。

    返回：
        str: 市场标签。
    """
    if is_hk_symbol(symbol):
        return "Hong Kong stock"
    return "A-share"
