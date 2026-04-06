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
from .eastmoney_mx import (
    get_company_announcements as get_mx_company_announcements,
    get_fundamentals as get_mx_fundamentals,
    get_market_news as get_mx_market_news,
    get_news as get_mx_news,
)
from .config import get_config

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
        "akshare": get_akshare_stock_data,
    },
    "get_indicators": {
        "akshare": get_akshare_indicators,
    },
    "get_fundamentals": {
        "akshare": get_akshare_fundamentals,
        "mx": get_mx_fundamentals,
    },
    "get_balance_sheet": {
        "akshare": get_akshare_balance_sheet,
    },
    "get_cashflow": {
        "akshare": get_akshare_cashflow,
    },
    "get_income_statement": {
        "akshare": get_akshare_income_statement,
    },
    "get_news": {
        "akshare": get_akshare_news,
        "mx": get_mx_news,
    },
    "get_market_news": {
        "akshare": get_akshare_market_news,
        "mx": get_mx_market_news,
    },
    "get_company_announcements": {
        "akshare": get_akshare_company_announcements,
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
    primary_vendors = [v.strip() for v in vendor_config.split(',')]

    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    all_available_vendors = list(VENDOR_METHODS[method].keys())
    fallback_vendors = primary_vendors.copy()
    for vendor in all_available_vendors:
        if vendor not in fallback_vendors:
            fallback_vendors.append(vendor)

    for vendor in fallback_vendors:
        if vendor not in VENDOR_METHODS[method]:
            continue

        vendor_impl = VENDOR_METHODS[method][vendor]
        impl_func = vendor_impl[0] if isinstance(vendor_impl, list) else vendor_impl

        try:
            return impl_func(*args, **kwargs)
        except Exception:
            continue

    raise RuntimeError(f"No available vendor for '{method}'")
