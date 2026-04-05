import datetime
import html
import re
from pathlib import Path
from typing import Any


def _collect_report_sections(final_state: dict[str, Any], save_path: Path) -> list[str]:
    """
    收集各阶段报告内容，并落盘分段 Markdown 文件。

    参数：
        final_state: Final graph state produced by the workflow.
        save_path: 输出文件的保存目录。

    返回：
        list[str]: 按顺序拼接后的报告章节列表。
    """
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

    return sections


def _build_complete_report_text(ticker: str, sections: list[str]) -> str:
    """
    生成完整报告 Markdown 文本。

    参数：
        ticker: 待分析公司的 A 股股票代码。
        sections: 报告章节列表。

    返回：
        str: 完整 Markdown 报告内容。
    """
    header = f"# Trading Analysis Report: {ticker}\n\nGenerated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + "\n\n".join(sections)


def build_pdf_report_path(markdown_report_file: str | Path) -> Path:
    """
    由 Markdown 报告路径推导 PDF 路径。

    参数：
        markdown_report_file: Markdown 报告路径。

    返回：
        Path: PDF 报告路径。
    """
    return Path(markdown_report_file).with_suffix(".pdf")


def _apply_inline_markup(text: str) -> str:
    """
    将 Markdown 行内标记转换为适合 ReportLab 的简化富文本。

    参数：
        text: 原始文本行。

    返回：
        str: 转换后的富文本内容。
    """
    pattern = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`)")
    chunks = []
    last = 0
    for match in pattern.finditer(text):
        chunks.append(html.escape(text[last:match.start()]))
        token = match.group(0)
        if token.startswith("**"):
            chunks.append(f'<font color="#0B5CAB">{html.escape(token[2:-2])}</font>')
        else:
            chunks.append(f'<font color="#5B4B8A">{html.escape(token[1:-1])}</font>')
        last = match.end()
    chunks.append(html.escape(text[last:]))
    return "".join(chunks)


def _render_pdf_report(report_text: str, output_path: Path) -> None:
    """
    将 Markdown 风格的完整报告渲染为 PDF。

    参数：
        report_text: 完整 Markdown 报告。
        output_path: PDF 输出路径。

    返回：
        None: 无返回值。
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("PDF export requires reportlab. Install it with `pip install reportlab`.") from exc

    font_name = "STSong-Light"
    try:
        pdfmetrics.getFont(font_name)
    except KeyError:
        pdfmetrics.registerFont(UnicodeCIDFont(font_name))

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=20,
        leading=28,
        textColor=colors.HexColor("#102A43"),
        spaceAfter=14,
        wordWrap="CJK",
    )
    heading_style = ParagraphStyle(
        "ReportHeading",
        parent=styles["Heading1"],
        fontName=font_name,
        fontSize=14,
        leading=20,
        textColor=colors.HexColor("#0B5CAB"),
        spaceBefore=8,
        spaceAfter=8,
        wordWrap="CJK",
    )
    subheading_style = ParagraphStyle(
        "ReportSubHeading",
        parent=styles["Heading2"],
        fontName=font_name,
        fontSize=11.5,
        leading=17,
        textColor=colors.HexColor("#334E68"),
        spaceBefore=4,
        spaceAfter=6,
        wordWrap="CJK",
    )
    body_style = ParagraphStyle(
        "ReportBody",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=10.5,
        leading=16,
        textColor=colors.HexColor("#1F2933"),
        wordWrap="CJK",
    )
    bullet_style = ParagraphStyle(
        "ReportBullet",
        parent=body_style,
        leftIndent=14,
        firstLineIndent=0,
    )

    story = []
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        if not paragraph_lines:
            return
        text = " ".join(line.strip() for line in paragraph_lines)
        story.append(Paragraph(_apply_inline_markup(text), body_style))
        story.append(Spacer(1, 6))
        paragraph_lines.clear()

    for raw_line in report_text.splitlines():
        stripped = raw_line.strip()

        if not stripped:
            flush_paragraph()
            continue

        if stripped.startswith("```"):
            continue

        if stripped.startswith("# "):
            flush_paragraph()
            story.append(Paragraph(_apply_inline_markup(stripped[2:].strip()), title_style))
            story.append(Spacer(1, 6))
            continue

        if stripped.startswith("## "):
            flush_paragraph()
            story.append(Paragraph(_apply_inline_markup(stripped[3:].strip()), heading_style))
            continue

        if stripped.startswith("### "):
            flush_paragraph()
            story.append(Paragraph(_apply_inline_markup(stripped[4:].strip()), subheading_style))
            continue

        if re.match(r"^\d+\.\s+", stripped):
            flush_paragraph()
            story.append(Paragraph(_apply_inline_markup(stripped), body_style))
            story.append(Spacer(1, 4))
            continue

        if stripped.startswith("- "):
            flush_paragraph()
            story.append(Paragraph(_apply_inline_markup(stripped[2:].strip()), bullet_style, bulletText="-"))
            story.append(Spacer(1, 4))
            continue

        paragraph_lines.append(stripped)

    flush_paragraph()

    def draw_page_number(canvas, doc) -> None:
        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(colors.HexColor("#7B8794"))
        canvas.drawRightString(doc.pagesize[0] - 40, 24, f"Page {canvas.getPageNumber()}")

    document = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=40,
        rightMargin=40,
        topMargin=48,
        bottomMargin=40,
        title="Trading Analysis Report",
    )
    document.build(story, onFirstPage=draw_page_number, onLaterPages=draw_page_number)


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
    sections = _collect_report_sections(final_state, save_path)
    report_text = _build_complete_report_text(ticker, sections)
    report_file = save_path / "complete_report.md"
    report_file.write_text(report_text, encoding="utf-8")
    _render_pdf_report(report_text, build_pdf_report_path(report_file))
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
