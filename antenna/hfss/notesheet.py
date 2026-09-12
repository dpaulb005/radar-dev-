#!/usr/bin/env python3
"""notesheet.py — the shared page furniture for the two study PDFs.

Both documents are meant to be PRINTED and written on, so the layout is a
Cornell-style split: body text in a column on the left, and a ruled margin down
the right that is never written into by the generator. Every page therefore has
somewhere to put a note, including the ones that are mostly tables.

DejaVu is registered rather than using the built-in Helvetica, because the
built-ins are WinAnsi-encoded and have no Greek: lambda, rho, theta and phi
would come out as black boxes, which in an antenna document is most of the
symbols that matter.
"""
import pathlib

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle)

FONTS = pathlib.Path("/usr/share/fonts/truetype/dejavu")
for name, fn in [("DJ", "DejaVuSans.ttf"), ("DJ-B", "DejaVuSans-Bold.ttf"),
                 ("DJM", "DejaVuSansMono.ttf"), ("DJM-B", "DejaVuSansMono-Bold.ttf")]:
    pdfmetrics.registerFont(TTFont(name, str(FONTS / fn)))
pdfmetrics.registerFontFamily("DJ", normal="DJ", bold="DJ-B", italic="DJ", boldItalic="DJ-B")

PAGE_W, PAGE_H = LETTER
M_L, M_R, M_T, M_B = 46, 42, 58, 46
NOTES_W = 150                      # the ruled column on the right
GUTTER = 16
BODY_W = PAGE_W - M_L - M_R - NOTES_W - GUTTER

INK = colors.HexColor("#14181d")
MUT = colors.HexColor("#5f6670")
RULE = colors.HexColor("#c9cdd3")
FAINT = colors.HexColor("#e3e6ea")
ACC = colors.HexColor("#8a3b1e")
BOX = colors.HexColor("#f2efe7")

S = {
    "h1": ParagraphStyle("h1", fontName="DJ-B", fontSize=17, leading=21, textColor=INK,
                         spaceBefore=2, spaceAfter=9),
    "h2": ParagraphStyle("h2", fontName="DJ-B", fontSize=12.5, leading=16, textColor=ACC,
                         spaceBefore=14, spaceAfter=5),
    "h3": ParagraphStyle("h3", fontName="DJ-B", fontSize=10.5, leading=14, textColor=INK,
                         spaceBefore=10, spaceAfter=3),
    "p": ParagraphStyle("p", fontName="DJ", fontSize=9.3, leading=13.4, textColor=INK,
                        alignment=TA_LEFT, spaceAfter=6),
    "small": ParagraphStyle("small", fontName="DJ", fontSize=8.2, leading=11.6, textColor=MUT,
                            spaceAfter=5),
    "eq": ParagraphStyle("eq", fontName="DJM", fontSize=9.6, leading=14, textColor=INK,
                         leftIndent=10, spaceBefore=4, spaceAfter=7),
    "cell": ParagraphStyle("cell", fontName="DJ", fontSize=8.2, leading=11, textColor=INK),
    "cellb": ParagraphStyle("cellb", fontName="DJ-B", fontSize=8.2, leading=11, textColor=INK),
    "cellm": ParagraphStyle("cellm", fontName="DJM", fontSize=8.0, leading=11, textColor=INK),
    "step": ParagraphStyle("step", fontName="DJ-B", fontSize=10, leading=13.5,
                           textColor=colors.white, spaceAfter=0),
}


def P(t, s="p"):
    return Paragraph(t, S[s])


def bullets(items, style="p"):
    """A bulleted list that keeps the body column's measure."""
    rows = [[Paragraph("•", S[style]), Paragraph(t, S[style])] for t in items]
    t = Table(rows, colWidths=[11, BODY_W - 11])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("TOPPADDING", (0, 0), (-1, -1), 0),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    return t


def table(rows, widths, head=True, mono_cols=()):
    """A table sized to the body column. rows[0] is the header when head."""
    data = []
    for r, row in enumerate(rows):
        out = []
        for c, cell in enumerate(row):
            st = "cellb" if (head and r == 0) else ("cellm" if c in mono_cols else "cell")
            out.append(Paragraph(str(cell), S[st]))
        data.append(out)
    total = sum(widths)
    t = Table(data, colWidths=[w / total * BODY_W for w in widths], repeatRows=1 if head else 0)
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("TOPPADDING", (0, 0), (-1, -1), 3.5),
             ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
             ("LEFTPADDING", (0, 0), (-1, -1), 5),
             ("RIGHTPADDING", (0, 0), (-1, -1), 5),
             ("LINEBELOW", (0, 0), (-1, -2), 0.4, FAINT),
             ("BOX", (0, 0), (-1, -1), 0.5, RULE)]
    if head:
        style += [("BACKGROUND", (0, 0), (-1, 0), BOX),
                  ("LINEBELOW", (0, 0), (-1, 0), 0.7, RULE)]
    t.setStyle(TableStyle(style))
    return t


def callout(title, body):
    """A boxed aside — the things that cost people an evening."""
    inner = [[Paragraph(title, S["cellb"])], [Paragraph(body, S["cell"])]]
    t = Table(inner, colWidths=[BODY_W])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BOX),
                           ("LINEBEFORE", (0, 0), (0, -1), 2.4, ACC),
                           ("TOPPADDING", (0, 0), (-1, -1), 5),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                           ("LEFTPADDING", (0, 0), (-1, -1), 9),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 9)]))
    return KeepTogether([Spacer(1, 3), t, Spacer(1, 7)])


def step(n, title):
    """A numbered step banner for the HFSS procedure."""
    t = Table([[Paragraph(f"{n}", S["step"]), Paragraph(title, S["h3"])]],
              colWidths=[22, BODY_W - 22])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), ACC),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("ALIGN", (0, 0), (0, 0), "CENTER"),
                           ("TOPPADDING", (0, 0), (-1, -1), 3),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                           ("LEFTPADDING", (1, 0), (1, 0), 8)]))
    return KeepTogether([Spacer(1, 9), t, Spacer(1, 4)])


def note_lines(n):
    """n ruled lines in the BODY column, for working something out in place."""
    rows = [[""] for _ in range(n)]
    t = Table(rows, colWidths=[BODY_W], rowHeights=[17] * n)
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, FAINT)]))
    return KeepTogether([Spacer(1, 4), t, Spacer(1, 6)])


class NoteDoc(BaseDocTemplate):
    """Letter page, body column left, permanently ruled note column right."""

    def __init__(self, path, title, subtitle, footer):
        super().__init__(str(path), pagesize=LETTER, title=title, author="radar-dev",
                         subject=subtitle, leftMargin=M_L, rightMargin=M_R,
                         topMargin=M_T, bottomMargin=M_B)
        self.doc_title, self.subtitle, self.footer = title, subtitle, footer
        frame = Frame(M_L, M_B, BODY_W, PAGE_H - M_T - M_B, id="body",
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates([PageTemplate(id="notes", frames=[frame],
                                            onPage=self._furniture)])

    def _furniture(self, c, doc):
        c.saveState()
        top = PAGE_H - M_T
        # running head
        c.setFont("DJ-B", 8); c.setFillColor(MUT)
        c.drawString(M_L, top + 16, self.doc_title.upper())
        c.setFont("DJ", 8)
        c.drawRightString(PAGE_W - M_R, top + 16, self.footer)
        c.setStrokeColor(RULE); c.setLineWidth(0.6)
        c.line(M_L, top + 10, PAGE_W - M_R, top + 10)
        # notes column
        nx = M_L + BODY_W + GUTTER
        c.setFont("DJ-B", 7.5); c.setFillColor(MUT)
        c.drawString(nx, top - 1, "NOTES")
        c.setStrokeColor(FAINT); c.setLineWidth(0.45)
        y = top - 14
        while y > M_B + 4:
            c.line(nx, y, nx + NOTES_W, y)
            y -= 17
        c.setStrokeColor(RULE); c.setLineWidth(0.5)
        c.line(nx - GUTTER / 2, M_B, nx - GUTTER / 2, top + 4)
        # footer
        c.setFont("DJ", 8); c.setFillColor(MUT)
        c.drawRightString(PAGE_W - M_R, M_B - 18, f"{doc.page}")
        c.restoreState()


def title_block(title, subtitle, lead, meta_rows):
    """The opening block: title, one-line thesis, and a small facts table."""
    out = [Paragraph(title, S["h1"]), Paragraph(subtitle, S["small"]), Spacer(1, 6),
           Paragraph(lead, S["p"]), Spacer(1, 4),
           table(meta_rows, [30, 70], head=False), Spacer(1, 8)]
    return out
