import datetime
from pathlib import Path
from typing import Any


def save_report_to_disk(final_state: dict[str, Any], ticker: str, save_path: Path) -> Path:
    """
    将完整分析报告按 CLI 相同的目录结构保存到磁盘。

    参数：
        final_state: Final graph state produced by the workflow.
        ticker: 待分析公司的 A 股股票代码。
        save_path: 输出文件的保存目录。

    返回：
        Path: 汇总报告文件路径。
    """
    save_path.mkdir(parents=True, exist_ok=True)
    sections = []

    analysts_dir = save_path / "1_analysts"
    analyst_parts = []
    if final_state.get("final_market_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "market_report.md").write_text(final_state["final_market_report"], encoding="utf-8")
        analyst_parts.append(("Market Analyst", final_state["final_market_report"]))
    if final_state.get("final_sentiment_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "sentiment_report.md").write_text(final_state["final_sentiment_report"], encoding="utf-8")
        analyst_parts.append(("Social Analyst", final_state["final_sentiment_report"]))
    if final_state.get("final_news_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "news_report.md").write_text(final_state["final_news_report"], encoding="utf-8")
        analyst_parts.append(("News Analyst", final_state["final_news_report"]))
    if final_state.get("final_fundamentals_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "fundamentals_report.md").write_text(final_state["final_fundamentals_report"], encoding="utf-8")
        analyst_parts.append(("Fundamentals Analyst", final_state["final_fundamentals_report"]))
    if analyst_parts:
        content = "\n\n".join(f"### {name}\n{text}" for name, text in analyst_parts)
        sections.append(f"## I. Analyst Team Reports\n\n{content}")

    if final_state.get("final_investment_plan_report"):
        research_dir = save_path / "2_research"
        research_dir.mkdir(exist_ok=True)
        (research_dir / "investment_plan.md").write_text(final_state["final_investment_plan_report"], encoding="utf-8")
        sections.append(f"## II. Research Team Decision\n\n{final_state['final_investment_plan_report']}")

    if final_state.get("final_trader_investment_plan_report"):
        trading_dir = save_path / "3_trading"
        trading_dir.mkdir(exist_ok=True)
        (trading_dir / "trader_investment_plan_report.md").write_text(final_state["final_trader_investment_plan_report"], encoding="utf-8")
        sections.append(f"## III. Trading Team Plan\n\n{final_state['final_trader_investment_plan_report']}")

    if final_state.get("final_trade_decision_report"):
        portfolio_dir = save_path / "4_portfolio"
        portfolio_dir.mkdir(exist_ok=True)
        (portfolio_dir / "final_trade_decision_report.md").write_text(final_state["final_trade_decision_report"], encoding="utf-8")
        sections.append(f"## IV. Portfolio Management Decision\n\n{final_state['final_trade_decision_report']}")

    header = f"# Trading Analysis Report: {ticker}\n\nGenerated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    report_file = save_path / "complete_report.md"
    report_file.write_text(header + "\n\n".join(sections), encoding="utf-8")
    return report_file


def build_default_report_path(base_dir: str | Path, ticker: str) -> Path:
    """
    生成与 CLI 一致的默认报告目录。

    参数：
        base_dir: 报告根目录。
        ticker: 股票代码。

    返回：
        Path: 本次运行的报告目录。
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(base_dir) / f"{ticker}_{timestamp}"


def persist_report(
    final_state: dict[str, Any],
    ticker: str,
    base_dir: str | Path,
    save_path: str | Path | None = None,
) -> Path:
    """
    持久化报告；若未显式指定目录，则自动生成 CLI 风格目录名。

    参数：
        final_state: Final graph state produced by the workflow.
        ticker: 股票代码。
        base_dir: 报告根目录。
        save_path: 可选的精确目标目录。

    返回：
        Path: 汇总报告文件路径。
    """
    target_dir = Path(save_path) if save_path else build_default_report_path(base_dir, ticker)
    return save_report_to_disk(final_state, ticker, target_dir)
