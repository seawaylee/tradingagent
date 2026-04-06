import logging

from .a_share import (
    get_balance_sheet as get_akshare_balance_sheet,
    get_cashflow as get_akshare_cashflow,
    get_company_announcements as get_akshare_company_announcements,
    get_fundamentals as get_akshare_fundamentals,
    get_income_statement as get_akshare_income_statement,
    get_indicators as get_akshare_indicators,
    get_market_news as get_akshare_market_news,
    get_news as get_akshare_news,
    get_stock_data as get_akshare_stock_data,
)
from .hk_share import get_stock_data as get_hk_stock_data
from .hk_share import (
    get_balance_sheet as get_hk_balance_sheet,
    get_cashflow as get_hk_cashflow,
    get_company_announcements as get_hk_company_announcements,
    get_fundamentals as get_hk_fundamentals,
    get_income_statement as get_hk_income_statement,
    get_indicators as get_hk_indicators,
    get_news as get_hk_news,
)
from .eastmoney_mx import (
    get_company_announcements as get_mx_company_announcements,
    get_fundamentals as get_mx_fundamentals,
    get_market_news as get_mx_market_news,
    get_news as get_mx_news,
)
from .config import get_config
from .market_symbols import is_hk_symbol


logger = logging.getLogger(__name__)
HK_INCOMPATIBLE_VENDORS = {
    "get_news": {"mx"},
    "get_fundamentals": {"mx"},
    "get_company_announcements": {"mx"},
}


def _route_market_impl(primary_impl_name: str, hk_impl_name: str | None = None):
    """
    根据代码市场选择实现。

    参数：
        primary_impl_name: 默认实现名称。
        hk_impl_name: 港股实现名称。

    返回：
        Callable: 已封装的路由函数。
    """
    def _wrapped(*args, **kwargs):
        symbol = args[0] if args else kwargs.get("symbol") or kwargs.get("ticker")
        if hk_impl_name and symbol and is_hk_symbol(str(symbol)):
            return globals()[hk_impl_name](*args, **kwargs)
        return globals()[primary_impl_name](*args, **kwargs)

    return _wrapped

TOOLS_CATEGORIES = {
    "core_stock_apis": {
        "description": "A-share OHLCV stock price data",
        "tools": ["get_stock_data"],
    },
    "technical_indicators": {
        "description": "A-share technical analysis indicators",
        "tools": ["get_indicators"],
    },
    "fundamental_data": {
        "description": "A-share company fundamentals and statements",
        "tools": ["get_fundamentals", "get_balance_sheet", "get_cashflow", "get_income_statement"],
    },
    "news_data": {
        "description": "A-share company news, market news, and announcements",
        "tools": ["get_news", "get_market_news", "get_company_announcements"],
    },
}

VENDOR_LIST = ["akshare", "mx"]

VENDOR_METHODS = {
    "get_stock_data": {
        "akshare": _route_market_impl("get_akshare_stock_data", "get_hk_stock_data"),
    },
    "get_indicators": {
        "akshare": _route_market_impl("get_akshare_indicators", "get_hk_indicators"),
    },
    "get_fundamentals": {
        "akshare": _route_market_impl("get_akshare_fundamentals", "get_hk_fundamentals"),
        "mx": get_mx_fundamentals,
    },
    "get_balance_sheet": {
        "akshare": _route_market_impl("get_akshare_balance_sheet", "get_hk_balance_sheet"),
    },
    "get_cashflow": {
        "akshare": _route_market_impl("get_akshare_cashflow", "get_hk_cashflow"),
    },
    "get_income_statement": {
        "akshare": _route_market_impl("get_akshare_income_statement", "get_hk_income_statement"),
    },
    "get_news": {
        "akshare": _route_market_impl("get_akshare_news", "get_hk_news"),
        "mx": get_mx_news,
    },
    "get_market_news": {
        "akshare": get_akshare_market_news,
        "mx": get_mx_market_news,
    },
    "get_company_announcements": {
        "akshare": _route_market_impl("get_akshare_company_announcements", "get_hk_company_announcements"),
        "mx": get_mx_company_announcements,
    },
}

def get_category_for_method(method: str) -> str:
    """
    获取指定方法所属的数据类别。
    
    参数：
        method: 用于供应商路由的抽象方法名。
    
    返回：
        str: 当前查询结果。
    """
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"Method '{method}' not found in any category")

def get_vendor(category: str, method: str = None) -> str:
    """
    获取某个数据类别或工具方法对应的供应商配置。
    
    参数：
        category: 当前请求对应的类别名或公告类别。
        method: 用于供应商路由的抽象方法名。
    
    返回：
        str: 当前查询结果。
    """
    config = get_config()

    # 如果提供了 method，则优先检查工具级配置
    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]

    # 回退到类别级配置
    return config.get("data_vendors", {}).get(category, "akshare")


def _select_market_compatible_vendors(method: str, vendors: list[str], symbol: str | None) -> list[str]:
    """
    根据标的市场过滤与当前方法兼容的 vendor。

    参数：
        method: 抽象工具方法名。
        vendors: 已配置 vendor 列表。
        symbol: 股票代码。

    返回：
        list[str]: 兼容当前市场的 vendor 列表。
    """
    if symbol and is_hk_symbol(str(symbol)):
        incompatible = HK_INCOMPATIBLE_VENDORS.get(method, set())
        return [vendor for vendor in vendors if vendor not in incompatible]
    return vendors

def route_to_vendor(method: str, *args, **kwargs):
    """
    将方法调用路由到配置好的 A 股数据实现。
    
    参数：
        method: 用于供应商路由的抽象方法名。
        args: 透传给底层可调用对象的位置参数。
        kwargs: 透传给底层可调用对象的关键字参数。
    
    返回：
        Any: 路由后的后端实现返回结果。
    """
    category = get_category_for_method(method)
    vendor_config = get_vendor(category, method)
    configured_vendors = [v.strip() for v in vendor_config.split(",") if v.strip()]
    if not configured_vendors:
        configured_vendors = ["akshare"]
    symbol = args[0] if args else kwargs.get("symbol") or kwargs.get("ticker")
    compatible_vendors = _select_market_compatible_vendors(method, configured_vendors, symbol)
    config = get_config()
    allow_vendor_fallback = bool(config.get("allow_vendor_fallback", False))

    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    if not compatible_vendors:
        raise RuntimeError(
            f"No market-compatible vendor configured for '{method}' and symbol '{symbol}'. configured={configured_vendors}"
        )

    candidate_vendors = compatible_vendors if allow_vendor_fallback else compatible_vendors[:1]
    errors = []

    for idx, vendor in enumerate(candidate_vendors):
        if vendor not in VENDOR_METHODS[method]:
            continue

        vendor_impl = VENDOR_METHODS[method][vendor]
        impl_func = vendor_impl[0] if isinstance(vendor_impl, list) else vendor_impl

        try:
            return impl_func(*args, **kwargs)
        except Exception as exc:
            detail = f"vendor={vendor} error={type(exc).__name__}: {exc}"
            errors.append(detail)
            logger.exception(
                "Vendor call failed: method=%s vendor=%s args=%s kwargs=%s",
                method,
                vendor,
                args,
                kwargs,
            )
            if not allow_vendor_fallback:
                raise RuntimeError(
                    f"Vendor call failed for '{method}' with {detail}; fallback disabled"
                ) from exc
            if idx == len(candidate_vendors) - 1:
                break

    attempted = ", ".join(candidate_vendors) if candidate_vendors else "(none)"
    if errors:
        raise RuntimeError(
            f"All configured vendors failed for '{method}'. attempted=[{attempted}] details={' | '.join(errors)}"
        )
    raise RuntimeError(
        f"No configured vendor implementation available for '{method}'. attempted=[{attempted}]"
    )
