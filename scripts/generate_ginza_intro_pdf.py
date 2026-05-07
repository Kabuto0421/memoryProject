"""Generate a PDF introduction document for GiNZA."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, StyleSheet1, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.pdfmetrics import registerFont
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer


BASE_DIR = Path(__file__).resolve().parents[1]
SOURCE_PATH = BASE_DIR / "docs" / "ginza" / "ginza_intro.md"
OUTPUT_PATH = BASE_DIR / "docs" / "ginza" / "Ginza入門書.pdf"


def build_styles() -> StyleSheet1:
    """Create reportlab styles with a Japanese font."""
    registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "BodyJP",
        parent=styles["BodyText"],
        fontName="HeiseiKakuGo-W5",
        fontSize=10.5,
        leading=16,
        alignment=TA_LEFT,
        spaceAfter=4,
    )
    styles.add(body)
    styles.add(
        ParagraphStyle(
            "TitleJP",
            parent=styles["Title"],
            fontName="HeiseiKakuGo-W5",
            fontSize=22,
            leading=28,
            textColor=colors.HexColor("#1f2937"),
            spaceAfter=14,
        )
    )
    styles.add(
        ParagraphStyle(
            "Heading1JP",
            parent=styles["Heading1"],
            fontName="HeiseiKakuGo-W5",
            fontSize=16,
            leading=22,
            textColor=colors.HexColor("#111827"),
            spaceBefore=10,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            "Heading2JP",
            parent=styles["Heading2"],
            fontName="HeiseiKakuGo-W5",
            fontSize=13,
            leading=18,
            textColor=colors.HexColor("#111827"),
            spaceBefore=8,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            "CodeJP",
            parent=body,
            fontName="HeiseiKakuGo-W5",
            fontSize=9.5,
            leading=14,
            leftIndent=8,
            backColor=colors.HexColor("#f3f4f6"),
            borderPadding=6,
            spaceBefore=3,
            spaceAfter=6,
        )
    )
    return styles


def parse_markdown(text: str, styles: StyleSheet1) -> list:
    """Parse a limited markdown subset into reportlab flowables."""
    lines = text.splitlines()
    story: list = []
    bullet_buffer: list[str] = []
    code_buffer: list[str] = []
    in_code = False

    def flush_bullets() -> None:
        nonlocal bullet_buffer
        if not bullet_buffer:
            return
        items = [
            ListItem(Paragraph(escape_inline(item), styles["BodyJP"]))
            for item in bullet_buffer
        ]
        story.append(ListFlowable(items, bulletType="bullet", leftIndent=14))
        story.append(Spacer(1, 3))
        bullet_buffer = []

    def flush_code() -> None:
        nonlocal code_buffer
        if not code_buffer:
            return
        code_text = "<br/>".join(escape_code(line) for line in code_buffer)
        story.append(Paragraph(code_text, styles["CodeJP"]))
        code_buffer = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            flush_bullets()
            if in_code:
                flush_code()
                in_code = False
            else:
                in_code = True
            continue

        if in_code:
            code_buffer.append(line.rstrip())
            continue

        if not stripped:
            flush_bullets()
            story.append(Spacer(1, 6))
            continue

        if stripped.startswith("# "):
            flush_bullets()
            story.append(Paragraph(escape_inline(stripped[2:]), styles["TitleJP"]))
            continue
        if stripped.startswith("## "):
            flush_bullets()
            story.append(Paragraph(escape_inline(stripped[3:]), styles["Heading1JP"]))
            continue
        if stripped.startswith("### "):
            flush_bullets()
            story.append(Paragraph(escape_inline(stripped[4:]), styles["Heading2JP"]))
            continue
        if stripped.startswith("- "):
            bullet_buffer.append(stripped[2:])
            continue

        flush_bullets()
        story.append(Paragraph(escape_inline(stripped), styles["BodyJP"]))

    flush_bullets()
    flush_code()
    return story


def escape_inline(text: str) -> str:
    """Escape reportlab markup and preserve simple inline code."""
    escaped = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    parts = escaped.split("`")
    if len(parts) == 1:
        return escaped
    rebuilt: list[str] = []
    for index, part in enumerate(parts):
        if index % 2 == 1:
            rebuilt.append(f"<font backColor='#f3f4f6'>{part}</font>")
        else:
            rebuilt.append(part)
    return "".join(rebuilt)


def escape_code(text: str) -> str:
    """Escape code block text for reportlab paragraphs."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace(" ", "&nbsp;")
    )


def main() -> None:
    """Generate the PDF from the markdown source."""
    styles = build_styles()
    markdown = SOURCE_PATH.read_text(encoding="utf-8")
    story = parse_markdown(markdown, styles)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUTPUT_PATH),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="Ginza入門書",
        author="Codex",
    )
    doc.build(story)


if __name__ == "__main__":
    main()
