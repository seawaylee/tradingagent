import logging
import re

from tradingagents.agents.utils.agent_utils import get_final_output_language


REPORT_FINALIZATION_SPECS = [
    ("market_report", "final_market_report", "market analysis report"),
    ("sentiment_report", "final_sentiment_report", "sentiment analysis report"),
    ("news_report", "final_news_report", "news analysis report"),
    ("fundamentals_report", "final_fundamentals_report", "fundamentals analysis report"),
    ("investment_plan", "final_investment_plan_report", "research manager investment plan"),
    ("trader_investment_plan", "final_trader_investment_plan_report", "trader execution plan"),
]

_ENGLISH_WORD_RE = re.compile(r"\b[A-Za-z][A-Za-z/+_-]{2,}\b")
_ENGLISH_LEAK_PATTERNS = [
    r"(?im)^(excellent!|now let me|let me compile|here is|based on a comprehensive)",
    r"(?m)^# .*\b(report|analysis|plan|decision)\b",
    r"(?m)^## [IVX]+\.",
]
logger = logging.getLogger(__name__)


def _needs_language_cleanup(text: str, final_language: str) -> bool:
    """
    判断报告是否明显泄漏了与最终语言不一致的英文内容。

    参数：
        text: 原始报告文本。
        final_language: 目标最终输出语言。

    返回：
        bool: 若需要进行语言清洗，则返回 True。
    """
    if not text or not text.strip():
        return False

    if (final_language or "").strip().lower() == "english":
        return False

    if any(re.search(pattern, text) for pattern in _ENGLISH_LEAK_PATTERNS):
        return True

    return len(_ENGLISH_WORD_RE.findall(text)) >= 20


def _rewrite_report_in_final_language(llm, report_text: str, report_label: str) -> str:
    """
    将泄漏英文的最终报告重写为目标最终语言。

    参数：
        llm: 当前组件使用的语言模型客户端或可运行对象。
        report_text: 原始报告内容。
        report_label: 报告标签，用于提示词描述。

    返回：
        str: 清洗后的最终报告。
    """
    final_language = get_final_output_language()
    if not _needs_language_cleanup(report_text, final_language):
        return report_text

    prompt = f"""Rewrite the following {report_label} for end users in {final_language}.

Requirements:
- Preserve every fact, number, date, stock ticker, and Markdown table.
- Translate all narrative text, headings, list labels, and summaries into {final_language}.
- Remove English workflow narration or meta commentary.
- Preserve explicit machine-readable tokens only when clearly required, including stock tickers and one of Buy / Overweight / Hold / Underweight / Sell if it already appears.
- Return only the cleaned Markdown report body.

Report:
{report_text}"""

    try:
        response = llm.invoke(prompt)
    except Exception as exc:
        logger.exception("Final report cleanup failed for %s", report_label)
        raise RuntimeError(
            f"Final report cleanup failed for {report_label}: {exc}"
        ) from exc

    cleaned = getattr(response, "content", "")
    if cleaned and cleaned.strip():
        return cleaned.strip()

    raise RuntimeError(f"Final report cleanup returned empty content for {report_label}")


def create_report_finalizer(llm):
    """
    创建并返回最终报告整理节点。

    参数：
        llm: 当前组件使用的语言模型客户端或可运行对象。

    返回：
        Callable | object: 当前组件生成的可调用对象或实例。
    """

    def report_finalizer_node(state) -> dict:
        """
        将中间态内容整理为最终对外报告。

        参数：
            state: 当前工作流对应的图状态。

        返回：
            dict: 需要回写到图状态中的状态补丁。
        """
        final_reports = {}

        for source_key, target_key, report_label in REPORT_FINALIZATION_SPECS:
            final_reports[target_key] = _rewrite_report_in_final_language(
                llm,
                state.get(source_key, ""),
                report_label,
            )

        final_reports["final_trade_decision_report"] = _rewrite_report_in_final_language(
            llm,
            state.get("final_trade_decision", ""),
            "portfolio manager final decision report",
        )
        return final_reports

    return report_finalizer_node
