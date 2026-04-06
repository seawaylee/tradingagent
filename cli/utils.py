import questionary
from typing import List, Optional, Tuple, Dict

from rich.console import Console

from cli.models import AnalystType
from tradingagents.dataflows.market_symbols import normalize_market_symbol
from tradingagents.llm_clients.model_catalog import get_model_options

console = Console()

TICKER_INPUT_EXAMPLES = "Examples: 600519, 000001, 300750, 688041"

ANALYST_ORDER = [
    ("Market Analyst", AnalystType.MARKET),
    ("Social Media Analyst", AnalystType.SOCIAL),
    ("News Analyst", AnalystType.NEWS),
    ("Fundamentals Analyst", AnalystType.FUNDAMENTALS),
]


def get_ticker() -> str:
    """
    提示用户输入股票代码。
    
    返回：
        str: 当前查询结果。
    """
    ticker = questionary.text(
        f"Enter the exact ticker symbol to analyze ({TICKER_INPUT_EXAMPLES}):",
        validate=lambda x: len(x.strip()) > 0 or "Please enter a valid ticker symbol.",
        style=questionary.Style(
            [
                ("text", "fg:green"),
                ("highlighted", "noinherit"),
            ]
        ),
    ).ask()

    if not ticker:
        console.print("\n[red]No ticker symbol provided. Exiting...[/red]")
        exit(1)

    return normalize_ticker_symbol(ticker)


def normalize_ticker_symbol(ticker: str) -> str:
    """
    将股票代码输入规范化为标准市场代码。
    
    参数：
        ticker: 待分析公司的股票代码。
    
    返回：
        str: 规范化后的代码结果。
    """
    return normalize_market_symbol(ticker)


def get_analysis_date() -> str:
    """
    提示用户输入 YYYY-MM-DD 格式的日期。
    
    返回：
        str: 当前查询结果。
    """
    import re
    from datetime import datetime

    def validate_date(date_str: str) -> bool:
        """
        校验日期是否合法。
        
        参数：
            date_str: YYYY-MM-DD 格式的日期字符串。
        
        返回：
            bool: 条件满足时返回 True，否则返回 False。
        """
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            return False
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    date = questionary.text(
        "Enter the analysis date (YYYY-MM-DD):",
        validate=lambda x: validate_date(x.strip())
        or "Please enter a valid date in YYYY-MM-DD format.",
        style=questionary.Style(
            [
                ("text", "fg:green"),
                ("highlighted", "noinherit"),
            ]
        ),
    ).ask()

    if not date:
        console.print("\n[red]No date provided. Exiting...[/red]")
        exit(1)

    return date.strip()


def select_analysts() -> List[AnalystType]:
    """
    通过交互式多选框选择分析师。
    
    返回：
        List[AnalystType]: 当前交互选择结果。
    """
    choices = questionary.checkbox(
        "Select Your [Analysts Team]:",
        choices=[
            questionary.Choice(display, value=value) for display, value in ANALYST_ORDER
        ],
        instruction="\n- Press Space to select/unselect analysts\n- Press 'a' to select/unselect all\n- Press Enter when done",
        validate=lambda x: len(x) > 0 or "You must select at least one analyst.",
        style=questionary.Style(
            [
                ("checkbox-selected", "fg:green"),
                ("selected", "fg:green noinherit"),
                ("highlighted", "noinherit"),
                ("pointer", "noinherit"),
            ]
        ),
    ).ask()

    if not choices:
        console.print("\n[red]No analysts selected. Exiting...[/red]")
        exit(1)

    return choices


def select_research_depth() -> int:
    """
    通过交互式选择器选择研究深度。
    
    返回：
        int: 当前交互选择结果。
    """

    # 定义研究深度及其对应数值
    DEPTH_OPTIONS = [
        ("Shallow - Quick research, few debate and strategy discussion rounds", 1),
        ("Medium - Middle ground, moderate debate rounds and strategy discussion", 3),
        ("Deep - Comprehensive research, in depth debate and strategy discussion", 5),
    ]

    choice = questionary.select(
        "Select Your [Research Depth]:",
        choices=[
            questionary.Choice(display, value=value) for display, value in DEPTH_OPTIONS
        ],
        instruction="\n- Use arrow keys to navigate\n- Press Enter to select",
        style=questionary.Style(
            [
                ("selected", "fg:yellow noinherit"),
                ("highlighted", "fg:yellow noinherit"),
                ("pointer", "fg:yellow noinherit"),
            ]
        ),
    ).ask()

    if choice is None:
        console.print("\n[red]No research depth selected. Exiting...[/red]")
        exit(1)

    return choice


def select_shallow_thinking_agent(provider) -> str:
    """
    通过交互式选择器选择快速思考模型。
    
    参数：
        provider: 模型提供方名称。
    
    返回：
        str: 当前交互选择结果。
    """

    choice = questionary.select(
        "Select Your [Quick-Thinking LLM Engine]:",
        choices=[
            questionary.Choice(display, value=value)
            for display, value in get_model_options(provider, "quick")
        ],
        instruction="\n- Use arrow keys to navigate\n- Press Enter to select",
        style=questionary.Style(
            [
                ("selected", "fg:magenta noinherit"),
                ("highlighted", "fg:magenta noinherit"),
                ("pointer", "fg:magenta noinherit"),
            ]
        ),
    ).ask()

    if choice is None:
        console.print(
            "\n[red]No shallow thinking llm engine selected. Exiting...[/red]"
        )
        exit(1)

    return choice


def select_deep_thinking_agent(provider) -> str:
    """
    通过交互式选择器选择深度思考模型。
    
    参数：
        provider: 模型提供方名称。
    
    返回：
        str: 当前交互选择结果。
    """

    choice = questionary.select(
        "Select Your [Deep-Thinking LLM Engine]:",
        choices=[
            questionary.Choice(display, value=value)
            for display, value in get_model_options(provider, "deep")
        ],
        instruction="\n- Use arrow keys to navigate\n- Press Enter to select",
        style=questionary.Style(
            [
                ("selected", "fg:magenta noinherit"),
                ("highlighted", "fg:magenta noinherit"),
                ("pointer", "fg:magenta noinherit"),
            ]
        ),
    ).ask()

    if choice is None:
        console.print("\n[red]No deep thinking llm engine selected. Exiting...[/red]")
        exit(1)

    return choice

def select_llm_provider() -> tuple[str, str]:
    """
    通过交互式选择器选择 LLM 提供方及默认接口地址。

    返回：
        tuple[str, str]: 当前交互选择结果。
    """
    # 定义不同模型提供方及其对应的接口地址
    BASE_URLS = [
        ("OpenAI", "https://api.openai.com/v1"),
        ("Google", "https://generativelanguage.googleapis.com/v1"),
        ("Anthropic", "https://api.anthropic.com/"),
        ("Azure", ""),
        ("xAI", "https://api.x.ai/v1"),
        ("Openrouter", "https://openrouter.ai/api/v1"),
        ("Ollama", "http://localhost:11434/v1"),
        ("Qwen", "https://coding.dashscope.aliyuncs.com/v1"),
        ("Zhipu", "https://open.bigmodel.cn/api/coding/paas/v4"),
    ]
    
    choice = questionary.select(
        "Select your LLM Provider:",
        choices=[
            questionary.Choice(display, value=(display, value))
            for display, value in BASE_URLS
        ],
        instruction="\n- Use arrow keys to navigate\n- Press Enter to select",
        style=questionary.Style(
            [
                ("selected", "fg:magenta noinherit"),
                ("highlighted", "fg:magenta noinherit"),
                ("pointer", "fg:magenta noinherit"),
            ]
        ),
    ).ask()
    
    if choice is None:
        console.print("\n[red]no OpenAI backend selected. Exiting...[/red]")
        exit(1)
    
    display_name, url = choice
    print(f"You selected: {display_name}\tURL: {url}")

    return display_name, url


def ask_azure_endpoint(default: str = "") -> str:
    """
    输入 Azure OpenAI endpoint。

    参数：
        default: 交互输入框中显示的默认值。

    返回：
        str: 当前交互选择结果。
    """
    endpoint = questionary.text(
        "Enter Azure OpenAI endpoint:",
        default=default,
        validate=lambda x: len(x.strip()) > 0 or "Azure endpoint cannot be empty.",
        style=questionary.Style([
            ("text", "fg:green"),
            ("highlighted", "noinherit"),
        ]),
    ).ask()

    if not endpoint:
        console.print("\n[red]No Azure endpoint provided. Exiting...[/red]")
        exit(1)

    return endpoint.strip()


def ask_azure_api_version(default: str = "2024-12-01-preview") -> str:
    """
    输入 Azure OpenAI API 版本。

    参数：
        default: 交互输入框中显示的默认值。

    返回：
        str: 当前交互选择结果。
    """
    api_version = questionary.text(
        "Enter Azure OpenAI API version:",
        default=default,
        validate=lambda x: len(x.strip()) > 0 or "Azure API version cannot be empty.",
        style=questionary.Style([
            ("text", "fg:green"),
            ("highlighted", "noinherit"),
        ]),
    ).ask()

    if not api_version:
        console.print("\n[red]No Azure API version provided. Exiting...[/red]")
        exit(1)

    return api_version.strip()


def ask_azure_deployment(label: str, default: str = "") -> str:
    """
    输入 Azure OpenAI deployment 名称。

    参数：
        label: 当前 deployment 的用途标签。
        default: 交互输入框中显示的默认值。

    返回：
        str: 当前交互选择结果。
    """
    deployment = questionary.text(
        f"Enter Azure deployment name for {label}:",
        default=default,
        validate=lambda x: len(x.strip()) > 0 or "Azure deployment cannot be empty.",
        style=questionary.Style([
            ("text", "fg:green"),
            ("highlighted", "noinherit"),
        ]),
    ).ask()

    if not deployment:
        console.print("\n[red]No Azure deployment provided. Exiting...[/red]")
        exit(1)

    return deployment.strip()


def ask_openai_reasoning_effort() -> str:
    """
    选择 OpenAI 的推理强度。
    
    返回：
        str: 当前交互选择结果。
    """
    choices = [
        questionary.Choice("Medium (Default)", "medium"),
        questionary.Choice("High (More thorough)", "high"),
        questionary.Choice("Low (Faster)", "low"),
    ]
    return questionary.select(
        "Select Reasoning Effort:",
        choices=choices,
        style=questionary.Style([
            ("selected", "fg:cyan noinherit"),
            ("highlighted", "fg:cyan noinherit"),
            ("pointer", "fg:cyan noinherit"),
        ]),
    ).ask()


def ask_anthropic_effort() -> str | None:
    """
    选择 Anthropic 的推理强度。
    
    返回：
        str | None: 当前交互选择结果。
    """
    return questionary.select(
        "Select Effort Level:",
        choices=[
            questionary.Choice("High (recommended)", "high"),
            questionary.Choice("Medium (balanced)", "medium"),
            questionary.Choice("Low (faster, cheaper)", "low"),
        ],
        style=questionary.Style([
            ("selected", "fg:cyan noinherit"),
            ("highlighted", "fg:cyan noinherit"),
            ("pointer", "fg:cyan noinherit"),
        ]),
    ).ask()


def ask_gemini_thinking_config() -> str | None:
    """
    选择 Gemini 的思考模式配置。
    
    返回：
        str | None: 当前交互选择结果。
    """
    return questionary.select(
        "Select Thinking Mode:",
        choices=[
            questionary.Choice("Enable Thinking (recommended)", "high"),
            questionary.Choice("Minimal/Disable Thinking", "minimal"),
        ],
        style=questionary.Style([
            ("selected", "fg:green noinherit"),
            ("highlighted", "fg:green noinherit"),
            ("pointer", "fg:green noinherit"),
        ]),
    ).ask()


def ask_language_selection(title: str, default_language: str = "English") -> str:
    """
    选择指定用途的语言。
    
    参数：
        title: 当前语言选择器的标题文本。
        default_language: 默认语言名称。
    
    返回：
        str: 当前交互选择结果。
    """
    language_choices = [
        "English",
        "Chinese",
        "Japanese",
        "Korean",
        "Hindi",
        "Spanish",
        "Portuguese",
        "French",
        "German",
        "Arabic",
        "Russian",
    ]

    ordered_choices = [default_language] + [lang for lang in language_choices if lang != default_language]
    display_names = {
        "English": "English",
        "Chinese": "Chinese (中文)",
        "Japanese": "Japanese (日本語)",
        "Korean": "Korean (한국어)",
        "Hindi": "Hindi (हिन्दी)",
        "Spanish": "Spanish (Español)",
        "Portuguese": "Portuguese (Português)",
        "French": "French (Français)",
        "German": "German (Deutsch)",
        "Arabic": "Arabic (العربية)",
        "Russian": "Russian (Русский)",
    }

    choice = questionary.select(
        title,
        choices=[
            questionary.Choice(
                f"{display_names[language]}{' (default)' if language == default_language else ''}",
                language,
            )
            for language in ordered_choices
        ]
        + [questionary.Choice("Custom language", "custom")],
        style=questionary.Style([
            ("selected", "fg:yellow noinherit"),
            ("highlighted", "fg:yellow noinherit"),
            ("pointer", "fg:yellow noinherit"),
        ]),
    ).ask()

    if choice == "custom":
        return questionary.text(
            "Enter language name (e.g. Turkish, Vietnamese, Thai, Indonesian):",
            validate=lambda x: len(x.strip()) > 0 or "Please enter a language name.",
        ).ask().strip()

    return choice


def ask_internal_language() -> str:
    """
    选择内部分析与辩论语言。
    
    返回：
        str: 当前交互选择结果。
    """
    return ask_language_selection("Select Internal Language:", default_language="English")



def ask_output_language() -> str:
    """
    选择最终报告输出语言。
    
    返回：
        str: 当前交互选择结果。
    """
    return ask_language_selection("Select Final Output Language:", default_language="Chinese")
