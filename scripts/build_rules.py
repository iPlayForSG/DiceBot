"""Build the six standalone Chinese tabletop rulebooks.

The source editions are documented in README.md. This builder writes only
Chinese content and does not append the English publisher PDFs.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from rulebook_content import BOOKS


OUTPUT = Path(__file__).resolve().parents[1] / "web/public/rules"
OUTPUT.mkdir(parents=True, exist_ok=True)
pdfmetrics.registerFont(TTFont("Chinese", "C:/Windows/Fonts/simhei.ttf"))

TITLE = ParagraphStyle("title", fontName="Chinese", fontSize=24, leading=32,
                       textColor=colors.HexColor("#173b45"), spaceAfter=11)
SUBTITLE = ParagraphStyle("subtitle", fontName="Chinese", fontSize=11, leading=18,
                          textColor=colors.HexColor("#567075"), spaceAfter=17)
SECTION = ParagraphStyle("section", fontName="Chinese", fontSize=14, leading=21,
                         textColor=colors.HexColor("#1f5c67"), spaceBefore=13,
                         spaceAfter=7, keepWithNext=True)
BODY = ParagraphStyle("body", fontName="Chinese", fontSize=10.1, leading=16,
                      textColor=colors.HexColor("#26383d"), spaceAfter=7)
CELL = ParagraphStyle("cell", fontName="Chinese", fontSize=9.1, leading=14,
                      textColor=colors.HexColor("#26383d"))
HEADER = ParagraphStyle("header", parent=CELL, textColor=colors.white)
NOTE = ParagraphStyle("note", fontName="Chinese", fontSize=8.7, leading=14,
                      textColor=colors.HexColor("#61777a"), spaceBefore=10)


def paragraph(value: str, style: ParagraphStyle = BODY) -> Paragraph:
    return Paragraph(escape(value), style)


def footer(canvas, document, title: str) -> None:
    canvas.saveState()
    width, _ = A4
    canvas.setStrokeColor(colors.HexColor("#d7e3e1"))
    canvas.line(45, 39, width - 45, 39)
    canvas.setFont("Chinese", 8)
    canvas.setFillColor(colors.HexColor("#60797b"))
    canvas.drawString(47, 25, f"桌游夜航 · {title} · 中文规则")
    canvas.drawRightString(width - 47, 25, f"第 {document.page} 页")
    canvas.restoreState()


def build(slug: str, book: dict) -> None:
    path = OUTPUT / f"{slug}.pdf"
    flow = [paragraph(book["title"], TITLE), paragraph(book["subtitle"], SUBTITLE)]
    for heading, blocks in book["sections"]:
        flow.append(paragraph(heading, SECTION))
        for block in blocks:
            if isinstance(block, tuple):
                headers, rows, widths = block
                data = [[paragraph(cell, HEADER) for cell in headers]]
                data.extend([paragraph(cell, CELL) for cell in row] for row in rows)
                grid = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
                grid.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f5c67")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                     [colors.HexColor("#f0f6f5"), colors.white]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LINEBELOW", (0, -1), (-1, -1), 0.5,
                     colors.HexColor("#d4e4e1")),
                ]))
                flow.extend([grid, Spacer(1, 9)])
            else:
                flow.append(paragraph(block))
    flow.append(paragraph(book["note"], NOTE))
    document = SimpleDocTemplate(str(path), pagesize=A4,
                                 leftMargin=47, rightMargin=47,
                                 topMargin=48, bottomMargin=51,
                                 title=f"{book['title']} · 中文规则", author="桌游夜航")
    document.build(flow,
                   onFirstPage=lambda c, d: footer(c, d, book["title"]),
                   onLaterPages=lambda c, d: footer(c, d, book["title"]))
    print(slug, path.stat().st_size)


if __name__ == "__main__":
    for slug, book in BOOKS.items():
        build(slug, book)
