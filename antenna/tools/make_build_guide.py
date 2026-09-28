#!/usr/bin/env python3
"""make_build_guide.py — the copper-sheet horn, as a printable build guide.

Every dimension is solved by horn.py beside this file, and every derived number
(panel heights, the corner-seam length, the bend angles, the sheet layout) is
computed here and checked before anything is drawn:

  * the two flare trapezoids must share one corner-seam length, or the four
    panels would not meet at the corners;
  * every piece of one horn must fit on one 12 x 24 in sheet with a cutting gap
    between neighbours and a margin at the edge.

If either check fails the script stops instead of writing a guide that cannot
be built.

    python3 make_build_guide.py        # writes ../horn-build-guide.pdf

Needs reportlab and shapely, and the DejaVu fonts (for the degree sign, the
multiplication sign and the arrows in the labels).
"""
import importlib.util
import math
import pathlib

from reportlab.graphics.shapes import (Circle, Drawing, Group, Line, Polygon, PolyLine,
                                       Rect, String)
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether,
                                PageBreak, PageTemplate, Paragraph, Spacer, Table,
                                TableStyle)
from shapely.geometry import Polygon as SPoly
from shapely.geometry import box as sbox

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent / "horn-build-guide.pdf"
C0 = 299_792_458.0

# ─────────────────────────────────────────────────────────────── geometry ──


def load_horn():
    spec = importlib.util.spec_from_file_location("horn", HERE / "horn.py")
    H = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(H)
    return H


def geometry():
    H = load_horn()
    lam = C0 / 2.45e9
    a, b = H.WAVEGUIDES["WR-340"]
    a1, b1, rho1, rho2 = H.solve_optimum(lam, a, b, 13.4, 0.51)
    pe, ph = H.flare_lengths(a, b, a1, b1, rho1, rho2)
    g = {k: v * 1e3 for k, v in dict(a=a, b=b, a1=a1, b1=b1, pe=pe, ph=ph).items()}
    g["L"] = (g["pe"] + g["ph"]) / 2
    g.update(Lg=115.0,          # pipe length, back wall to throat (anything >= 100 works)
             t=0.533,           # 24 gauge copper, 0.021 in
             tab=6.0,           # every solder tab
             probe_z=43.7,      # probe centre from the inside face of the back wall
             probe_len=28.0,    # probe length inside the pipe
             rod_cut=32.0,      # cut the rod long, trim to length
             gain=10 * math.log10(0.51 * 4 * math.pi * a1 * b1 / lam ** 2),
             hp_e=54 * lam / b1, hp_h=78 * lam / a1)
    L = g["L"]
    dx, dy = (g["a1"] - g["a"]) / 2, (g["b1"] - g["b"]) / 2
    g["h_top"] = math.hypot(L, dy)           # top/bottom panel height (leans by dy)
    g["h_side"] = math.hypot(L, dx)          # side panel height (leans by dx)
    g["seam"] = math.sqrt(L ** 2 + dx ** 2 + dy ** 2)
    g["lean_top"] = math.degrees(math.atan2(dy, L))
    g["lean_side"] = math.degrees(math.atan2(dx, L))
    n_top = (0.0, L, -dy)
    n_side = (L, 0.0, -dx)
    cosang = sum(p * q for p, q in zip(n_top, n_side)) / (math.hypot(*n_top) * math.hypot(*n_side))
    g["corner_bend"] = math.degrees(math.acos(cosang))
    # the two trapezoids must give the same corner seam, or the panels do not meet
    seam_top = math.hypot(dx, g["h_top"])
    seam_side = math.hypot(dy, g["h_side"])
    assert abs(seam_top - g["seam"]) < 0.05 and abs(seam_side - g["seam"]) < 0.05, \
        "flare panels do not close at the corners"
    assert abs(g["pe"] - g["ph"]) / g["pe"] < 0.02, "horn.py did not close the flare"
    t = g["t"]
    g["wide_w"] = g["a"] + 2 * t             # wide walls lap over the narrow walls
    g["back_w"] = g["a"] + 4 * t             # back wall covers the pipe and its side tabs
    g["back_h"] = g["b"] + 2 * t
    return g


G = geometry()

# ─────────────────────────────────────────────────────────── flat pieces ──
# Every piece is a list of (x, y) in mm, drawn as seen from its OUTSIDE face.


def trapezoid(short, long_, h):
    return [(0, 0), (long_, 0), ((long_ + short) / 2, h), ((long_ - short) / 2, h)]


def edge_tab(p0, p1, w, outward):
    """A w-wide tab on edge p0->p1, ends chamfered at 45 degrees."""
    ex, ey = p1[0] - p0[0], p1[1] - p0[1]
    n = math.hypot(ex, ey)
    dx, dy = ex / n, ey / n
    nx, ny = outward
    return [p0, p1,
            (p1[0] + w * nx - w * dx, p1[1] + w * ny - w * dy),
            (p0[0] + w * nx + w * dx, p0[1] + w * ny + w * dy)]


def unit_normal_out(p0, p1, centre):
    ex, ey = p1[0] - p0[0], p1[1] - p0[1]
    n = math.hypot(ex, ey)
    nx, ny = ey / n, -ex / n
    mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
    if (mx - centre[0]) * nx + (my - centre[1]) * ny < 0:
        nx, ny = -nx, -ny
    return nx, ny


def piece_A():
    return dict(body=trapezoid(G["a"], G["a1"], G["h_top"]), tabs=[], bends=[])


def piece_B():
    body = trapezoid(G["b"], G["b1"], G["h_side"])
    cx = G["b1"] / 2
    cy = G["h_side"] / 2
    tabs, bends = [], []
    for p0, p1 in ((body[1], body[2]), (body[3], body[0])):
        n = unit_normal_out(p0, p1, (cx, cy))
        tabs.append(edge_tab(p0, p1, G["tab"], n))
        bends.append((p0, p1))
    return dict(body=body, tabs=tabs, bends=bends)


def piece_C(hole=False):
    w, L, tb = G["wide_w"], G["Lg"], G["tab"]
    body = [(0, 0), (w, 0), (w, L), (0, L)]
    tabs = [[(-tb, 0), (0, 0), (0, L), (-tb, L)],
            [(w, 0), (w + tb, 0), (w + tb, L), (w, L)],
            [(0, L), (w, L), (w, L + tb), (0, L + tb)]]
    bends = [((0, 0), (0, L)), ((w, 0), (w, L)), ((0, L), (w, L))]
    d = dict(body=body, tabs=tabs, bends=bends)
    if hole:
        d["hole"] = (w / 2, G["probe_z"])
    return d


def piece_D():
    w, L, tb = G["b"], G["Lg"], G["tab"]
    return dict(body=[(0, 0), (w, 0), (w, L), (0, L)],
                tabs=[[(0, L), (w, L), (w, L + tb), (0, L + tb)]],
                bends=[((0, L), (w, L))])


def piece_E():
    w, h, tb = G["back_w"], G["back_h"], G["tab"]
    return dict(body=[(0, 0), (w, 0), (w, h), (0, h)],
                tabs=[[(0, -tb), (w, -tb), (w, 0), (0, 0)],
                      [(0, h), (w, h), (w, h + tb), (0, h + tb)],
                      [(-tb, 0), (0, 0), (0, h), (-tb, h)],
                      [(w, 0), (w + tb, 0), (w + tb, h), (w, h)]],
                bends=[((0, 0), (w, 0)), ((0, h), (w, h)), ((0, 0), (0, h)), ((w, 0), (w, h))])


def outline(piece):
    shp = SPoly(piece["body"])
    for tb in piece["tabs"]:
        shp = shp.union(SPoly(tb))
    return shp


# ────────────────────────────────────────────────────────── sheet layout ──
SHEET_W, SHEET_H = 609.6, 304.8          # 24 x 12 in
MARGIN, GAP = 4.0, 3.0


def _transform(piece, rot, dx, dy):
    """rot in {0, 90, 180, 270} about the origin, then translate."""
    def tr(p):
        x, y = p
        for _ in range(rot // 90):
            x, y = -y, x
        return (x + dx, y + dy)
    out = dict(body=[tr(p) for p in piece["body"]],
               tabs=[[tr(p) for p in t] for t in piece["tabs"]],
               bends=[(tr(p), tr(q)) for p, q in piece["bends"]])
    if "hole" in piece:
        out["hole"] = tr(piece["hole"])
    return out


def _place_at(piece, rot, x_min, y_min):
    raw = _transform(piece, rot, 0, 0)
    bx0, by0, _, _ = outline(raw).bounds
    return _transform(piece, rot, x_min - bx0, y_min - by0)


def _slide_right(piece, rot, y_min, after, gap):
    """Smallest x that keeps `piece` at least gap clear of `after`."""
    lo, hi = -300.0, 700.0
    ref = outline(after)
    for _ in range(60):
        mid = (lo + hi) / 2
        cand = outline(_place_at(piece, rot, mid, y_min))
        if cand.distance(ref) >= gap and not cand.intersects(ref):
            hi = mid
        else:
            lo = mid
    return _place_at(piece, rot, hi, y_min)


def layout_one_horn():
    """Nine pieces, one 12 x 24 in sheet. Returns [(letter, placed piece)]."""
    A, B = piece_A(), piece_B()
    placed = []
    y1 = MARGIN
    a1 = _place_at(A, 0, MARGIN, y1)
    a2 = _slide_right(A, 180, y1, a1, GAP)
    x_after = outline(a2).bounds[2] + GAP
    c1 = _place_at(piece_C(hole=True), 90, x_after, y1)
    placed += [("A", a1), ("A", a2), ("C", c1)]
    y2 = max(outline(a1).bounds[3], outline(c1).bounds[3]) + GAP
    b1 = _place_at(B, 0, MARGIN, y2)
    b2 = _slide_right(B, 180, y2, b1, GAP)
    x = outline(b2).bounds[2] + GAP
    c2 = _place_at(piece_C(), 0, x, y2)
    x = outline(c2).bounds[2] + GAP
    d1 = _place_at(piece_D(), 0, x, y2)
    x = outline(d1).bounds[2] + GAP
    d2 = _place_at(piece_D(), 0, x, y2)
    x = outline(d2).bounds[2] + GAP
    e1 = _place_at(piece_E(), 90, x, y2)
    placed += [("B", b1), ("B", b2), ("C", c2), ("D", d1), ("D", d2), ("E", e1)]

    sheet = sbox(MARGIN, MARGIN, SHEET_W - MARGIN, SHEET_H - MARGIN)
    shapes = [outline(p) for _, p in placed]
    for i, s in enumerate(shapes):
        assert sheet.contains(s), f"piece {placed[i][0]} runs off the sheet"
        for j in range(i):
            assert s.distance(shapes[j]) >= GAP - 0.01, \
                f"pieces {placed[j][0]} and {placed[i][0]} are closer than the cutting gap"
    used = sum(s.area for s in shapes)
    return placed, used


LAYOUT, USED_MM2 = layout_one_horn()

# ──────────────────────────────────────────────────────────────── styling ──
FONTS = pathlib.Path("/usr/share/fonts/truetype/dejavu")
for name, fn in [("DJ", "DejaVuSans.ttf"), ("DJ-B", "DejaVuSans-Bold.ttf"),
                 ("DJM", "DejaVuSansMono.ttf")]:
    pdfmetrics.registerFont(TTFont(name, str(FONTS / fn)))
pdfmetrics.registerFontFamily("DJ", normal="DJ", bold="DJ-B", italic="DJ", boldItalic="DJ-B")

PAGE_W, PAGE_H = LETTER
M = 40
BODY_W = PAGE_W - 2 * M

INK = colors.HexColor("#14181d")
MUT = colors.HexColor("#5f6670")
RULE = colors.HexColor("#c9cdd3")
FAINT = colors.HexColor("#e3e6ea")
ACC = colors.HexColor("#8a3b1e")
BOX = colors.HexColor("#f4efe6")
CU_OUT = colors.HexColor("#e2a27a")
CU_IN = colors.HexColor("#b86f45")
CU_EDGE = colors.HexColor("#6b3a1f")
TAB = colors.HexColor("#f3d2bc")
BEND = colors.HexColor("#1f5f8b")
DIM = colors.HexColor("#3b4450")
BRASS = colors.HexColor("#c9a43a")
STEEL = colors.HexColor("#9aa3ad")

S = {
    "title": ParagraphStyle("title", fontName="DJ-B", fontSize=24, leading=29, textColor=INK),
    "sub": ParagraphStyle("sub", fontName="DJ", fontSize=11.5, leading=16, textColor=MUT,
                          spaceAfter=10),
    "h1": ParagraphStyle("h1", fontName="DJ-B", fontSize=16, leading=20, textColor=INK,
                         spaceBefore=0, spaceAfter=8),
    "h2": ParagraphStyle("h2", fontName="DJ-B", fontSize=12, leading=15, textColor=ACC,
                         spaceBefore=10, spaceAfter=4),
    "p": ParagraphStyle("p", fontName="DJ", fontSize=9.4, leading=13.6, textColor=INK,
                        alignment=TA_LEFT, spaceAfter=6),
    "small": ParagraphStyle("small", fontName="DJ", fontSize=8.2, leading=11.4, textColor=MUT,
                            spaceAfter=4),
    "cap": ParagraphStyle("cap", fontName="DJ", fontSize=8.2, leading=11.2, textColor=MUT,
                          spaceBefore=2, spaceAfter=8),
    "cell": ParagraphStyle("cell", fontName="DJ", fontSize=8.4, leading=11.2, textColor=INK),
    "cellb": ParagraphStyle("cellb", fontName="DJ-B", fontSize=8.4, leading=11.2, textColor=INK),
    "stepn": ParagraphStyle("stepn", fontName="DJ-B", fontSize=11, leading=13,
                            textColor=colors.white, alignment=1),
    "steph": ParagraphStyle("steph", fontName="DJ-B", fontSize=11.5, leading=14, textColor=INK),
}


def P(t, s="p"):
    return Paragraph(t, S[s])


def bullets(items, style="p", width=BODY_W):
    rows = [[Paragraph("•", S[style]), Paragraph(t, S[style])] for t in items]
    t = Table(rows, colWidths=[11, width - 11])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("TOPPADDING", (0, 0), (-1, -1), 0),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    return t


def numbered(items):
    rows = [[Paragraph(f"{i}.", S["p"]), Paragraph(t, S["p"])] for i, t in enumerate(items, 1)]
    t = Table(rows, colWidths=[16, BODY_W - 16])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("TOPPADDING", (0, 0), (-1, -1), 0),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    return t


def table(rows, widths, head=True, width=BODY_W, blank_cols=()):
    data = []
    for r, row in enumerate(rows):
        data.append([Paragraph(str(c), S["cellb" if head and r == 0 else "cell"]) for c in row])
    total = sum(widths)
    t = Table(data, colWidths=[w / total * width for w in widths], repeatRows=1 if head else 0)
    st = [("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("TOPPADDING", (0, 0), (-1, -1), 3.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.2),
          ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
          ("LINEBELOW", (0, 0), (-1, -2), 0.4, FAINT), ("BOX", (0, 0), (-1, -1), 0.5, RULE)]
    if head:
        st += [("BACKGROUND", (0, 0), (-1, 0), BOX), ("LINEBELOW", (0, 0), (-1, 0), 0.7, RULE)]
    for c in blank_cols:
        st += [("LINEBEFORE", (c, 0), (c, -1), 0.4, RULE)]
    t.setStyle(TableStyle(st))
    return t


def callout(title, body):
    t = Table([[Paragraph(title, S["cellb"])], [Paragraph(body, S["cell"])]], colWidths=[BODY_W])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BOX),
                           ("LINEBEFORE", (0, 0), (0, -1), 2.4, ACC),
                           ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                           ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9)]))
    return KeepTogether([Spacer(1, 2), t, Spacer(1, 7)])


def step(n, title):
    t = Table([[Paragraph(str(n), S["stepn"]), Paragraph(title, S["steph"])]],
              colWidths=[24, BODY_W - 24])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), ACC),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                           ("LEFTPADDING", (1, 0), (1, 0), 8),
                           ("LINEBELOW", (1, 0), (1, 0), 0.7, RULE)]))
    return t


def fig(drawing, caption):
    return [drawing, P(caption, "cap")]


# ──────────────────────────────────────────────────────── drawing helpers ──
def mm_str(v, nd=1):
    s = f"{v:.{nd}f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


class Sheet:
    """A reportlab Drawing with a mm coordinate frame: page = origin + mm * scale."""

    def __init__(self, w, h, scale=1.0, ox=0.0, oy=0.0):
        self.d = Drawing(w, h)
        self.sc, self.ox, self.oy = scale, ox, oy

    def P(self, p):
        return (self.ox + p[0] * self.sc, self.oy + p[1] * self.sc)

    def poly(self, pts, fill=None, stroke=CU_EDGE, width=0.8, dash=None):
        flat = [c for p in pts for c in self.P(p)]
        self.d.add(Polygon(flat, fillColor=fill, strokeColor=stroke, strokeWidth=width,
                           strokeDashArray=dash, strokeLineJoin=1))

    def line(self, p, q, color=INK, width=0.6, dash=None):
        (x0, y0), (x1, y1) = self.P(p), self.P(q)
        self.d.add(Line(x0, y0, x1, y1, strokeColor=color, strokeWidth=width,
                        strokeDashArray=dash, strokeLineCap=1))

    def text(self, p, s, size=7.5, color=INK, anchor="middle", bold=False, angle=0.0,
             page=False):
        x, y = p if page else self.P(p)
        st = String(0, 0, s, fontName="DJ-B" if bold else "DJ", fontSize=size,
                    fillColor=color, textAnchor=anchor)
        g = Group(st)
        g.translate(x, y)
        if angle:
            g.rotate(angle)
        self.d.add(g)

    def circle(self, p, r_mm, fill=None, stroke=INK, width=0.6):
        x, y = self.P(p)
        self.d.add(Circle(x, y, r_mm * self.sc, fillColor=fill, strokeColor=stroke,
                          strokeWidth=width))

    def arrow_head(self, tip, frm, size=4.0, color=DIM):
        (tx, ty), (fx, fy) = self.P(tip), self.P(frm)
        ang = math.atan2(ty - fy, tx - fx)
        a1, a2 = ang + math.radians(155), ang - math.radians(155)
        self.d.add(Polygon([tx, ty, tx + size * math.cos(a1), ty + size * math.sin(a1),
                            tx + size * math.cos(a2), ty + size * math.sin(a2)],
                           fillColor=color, strokeColor=color, strokeWidth=0.3))

    def dim(self, p, q, off, label=None, size=7.2, ext=True, color=DIM, text_off=2.8):
        """Aligned dimension between p and q, offset `off` mm to the left of p->q."""
        ex, ey = q[0] - p[0], q[1] - p[1]
        n = math.hypot(ex, ey)
        ux, uy = ex / n, ey / n
        nx, ny = -uy, ux
        p2 = (p[0] + nx * off, p[1] + ny * off)
        q2 = (q[0] + nx * off, q[1] + ny * off)
        if ext:
            sgn = 1 if off >= 0 else -1
            gap = 1.2 / self.sc
            over = 2.0 / self.sc
            self.line((p[0] + nx * gap * sgn, p[1] + ny * gap * sgn),
                      (p2[0] + nx * over * sgn, p2[1] + ny * over * sgn), color, 0.35)
            self.line((q[0] + nx * gap * sgn, q[1] + ny * gap * sgn),
                      (q2[0] + nx * over * sgn, q2[1] + ny * over * sgn), color, 0.35)
        self.line(p2, q2, color, 0.45)
        self.arrow_head(p2, q2, color=color)
        self.arrow_head(q2, p2, color=color)
        label = label if label is not None else mm_str(n)
        ang = math.degrees(math.atan2(uy, ux))
        if ang > 90.01:
            ang -= 180
        if ang <= -90:
            ang += 180
        mx, my = self.P(((p2[0] + q2[0]) / 2, (p2[1] + q2[1]) / 2))
        sgn = 1 if off >= 0 else -1
        # put the text on the outside of the dimension line
        tn = (text_off if sgn > 0 else -text_off - size * 0.75)
        rad = math.radians(ang)
        tx, ty = mx - math.sin(rad) * tn, my + math.cos(rad) * tn
        g = Group(String(0, 0, label, fontName="DJ", fontSize=size, fillColor=color,
                         textAnchor="middle"))
        g.translate(tx, ty)
        g.rotate(ang)
        # white knock-out behind the text so it reads over hatching
        self.d.add(g)

def callouts(d, W, items, size=8.4):
    """items: ((ax, ay) page point, 'L' or 'R', y, title, sub). Text stays inside [0, W]."""
    for (ax, ay), side, y, title, sub in items:
        subs = sub.split("\n") if sub else []
        tw = max([stringWidth(title, "DJ-B", size)] + [stringWidth(s, "DJ", size - 0.8) for s in subs])
        if side == "L":
            tx, anchor, lx = 0, "start", tw + 4
        else:
            tx, anchor, lx = W, "end", W - tw - 4
        d.add(Line(lx, y + 3, ax, ay, strokeColor=MUT, strokeWidth=0.5))
        d.add(Circle(ax, ay, 1.4, fillColor=INK, strokeColor=colors.white, strokeWidth=0.4))
        d.add(String(tx, y, title, fontName="DJ-B", fontSize=size, fillColor=INK, textAnchor=anchor))
        for i, s in enumerate(subs):
            d.add(String(tx, y - 10 - i * 9.5, s, fontName="DJ", fontSize=size - 0.8,
                         fillColor=MUT, textAnchor=anchor))


def text_block(d, x, y_top, lines, size=8.2, lead=11.6):
    for i, s in enumerate(lines):
        bold = s.startswith("**")
        s = s.strip("*")
        d.add(String(x, y_top - i * lead, s, fontName="DJ-B" if bold else "DJ", fontSize=size,
                     fillColor=INK))


# ────────────────────────────────────────────────────────────── 3-D views ──
class Cam:
    """Orthographic camera: azimuth from the +z (mouth) axis toward +x, elevation up."""

    def __init__(self, az, el, scale, ox, oy):
        az, el = math.radians(az), math.radians(el)
        self.d = (math.sin(az) * math.cos(el), math.sin(el), math.cos(az) * math.cos(el))
        self.r = (math.cos(az), 0.0, -math.sin(az))
        self.u = (-math.sin(az) * math.sin(el), math.cos(el), -math.cos(az) * math.sin(el))
        self.sc, self.ox, self.oy = scale, ox, oy

    def proj(self, p):
        return (self.ox + self.sc * sum(a * b for a, b in zip(p, self.r)),
                self.oy + self.sc * sum(a * b for a, b in zip(p, self.u)))

    def depth(self, p):
        return sum(a * b for a, b in zip(p, self.d))


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _norm(a):
    n = math.sqrt(_dot(a, a))
    return tuple(x / n for x in a)


LIGHT = _norm((-0.35, 0.85, -0.4))


def shade(base, lit):
    k = 0.55 + 0.5 * lit
    return colors.Color(min(1, base.red * k), min(1, base.green * k), min(1, base.blue * k))


def horn_parts():
    """Each part as thin faces: dict key -> list of (points, outward normal, colours)."""
    a2, b2, A2, B2 = G["a"] / 2, G["b"] / 2, G["a1"] / 2, G["b1"] / 2
    L, Lg = G["L"], G["Lg"]
    cu = (CU_OUT, CU_IN)
    parts = {
        "C_top": [([(-a2, b2, -Lg), (a2, b2, -Lg), (a2, b2, 0), (-a2, b2, 0)], (0, 1, 0), cu)],
        "C_bot": [([(-a2, -b2, -Lg), (a2, -b2, -Lg), (a2, -b2, 0), (-a2, -b2, 0)], (0, -1, 0), cu)],
        "D_right": [([(a2, -b2, -Lg), (a2, b2, -Lg), (a2, b2, 0), (a2, -b2, 0)], (1, 0, 0), cu)],
        "D_left": [([(-a2, -b2, -Lg), (-a2, b2, -Lg), (-a2, b2, 0), (-a2, -b2, 0)], (-1, 0, 0), cu)],
        "E": [([(-a2, -b2, -Lg), (a2, -b2, -Lg), (a2, b2, -Lg), (-a2, b2, -Lg)], (0, 0, -1), cu)],
        "A_top": [([(-a2, b2, 0), (a2, b2, 0), (A2, B2, L), (-A2, B2, L)], (0, L, -(B2 - b2)), cu)],
        "A_bot": [([(-a2, -b2, 0), (a2, -b2, 0), (A2, -B2, L), (-A2, -B2, L)], (0, -L, -(B2 - b2)), cu)],
        "B_right": [([(a2, -b2, 0), (a2, b2, 0), (A2, B2, L), (A2, -B2, L)], (L, 0, -(A2 - a2)), cu)],
        "B_left": [([(-a2, -b2, 0), (-a2, b2, 0), (-A2, B2, L), (-A2, -B2, L)], (-L, 0, -(A2 - a2)), cu)],
    }
    # connector: flange plate and jack body, as boxes on the top wall
    z = -Lg + G["probe_z"]
    f = []

    def box(x0, x1, y0, y1, z0, z1, col):
        c = (col, col)
        f.extend([
            ([(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)], (0, 1, 0), c),
            ([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], (0, 0, 1), c),
            ([(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)], (0, 0, -1), c),
            ([(x1, y0, z0), (x1, y0, z1), (x1, y1, z1), (x1, y1, z0)], (1, 0, 0), c),
            ([(x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)], (-1, 0, 0), c)])
    box(-6.35, 6.35, b2, b2 + 1.6, z - 6.35, z + 6.35, STEEL)
    box(-3.2, 3.2, b2 + 1.6, b2 + 12, z - 3.2, z + 3.2, colors.HexColor("#d9b75e"))
    parts["F"] = f
    return parts


def render_horn(d, cam, offsets=None, parts=None):
    offsets = offsets or {}
    parts = parts or horn_parts()
    faces = []
    for key, flist in parts.items():
        off = offsets.get(key, (0, 0, 0))
        for pts, n, (c_out, c_in) in flist:
            pts = [tuple(p[i] + off[i] for i in range(3)) for p in pts]
            faces.append((pts, _norm(n), c_out, c_in, key))
    faces.sort(key=lambda f: sum(cam.depth(p) for p in f[0]) / len(f[0]) + (3 if f[4] == "F" else 0))
    for pts, n, c_out, c_in, key in faces:
        facing = _dot(n, cam.d) >= 0
        nn = n if facing else tuple(-x for x in n)
        fill = shade(c_out if facing else c_in, max(0.0, _dot(nn, LIGHT)))
        d.add(Polygon([c for p in pts for c in cam.proj(p)], fillColor=fill,
                      strokeColor=colors.HexColor("#4a4f55") if key == "F" else CU_EDGE,
                      strokeWidth=0.4 if key == "F" else 0.7, strokeLineJoin=1))


def mouth_rim(d, cam, off=(0, 0, 0), width=1.6):
    A2, B2, L = G["a1"] / 2, G["b1"] / 2, G["L"]
    rim = [(-A2, -B2, L), (A2, -B2, L), (A2, B2, L), (-A2, B2, L)]
    pts = [c for p in rim for c in cam.proj(tuple(p[i] + off[i] for i in range(3)))]
    d.add(Polygon(pts, fillColor=None, strokeColor=CU_EDGE, strokeWidth=width, strokeLineJoin=1))


# ─────────────────────────────────────────────────────────────── figures ──
AZ, EL = 50, 50


def fig_cover():
    W, H = BODY_W, 292
    d = Drawing(W, H)
    sc = 0.9
    cam = Cam(AZ, EL, sc, W / 2 + 4, H / 2 + 22)
    render_horn(d, cam)
    mouth_rim(d, cam)
    a2, b2, A2, B2, L, Lg = G["a"] / 2, G["b"] / 2, G["a1"] / 2, G["b1"] / 2, G["L"], G["Lg"]
    z = -Lg + G["probe_z"]
    pr = cam.proj
    callouts(d, W, [
        (pr((-20, (b2 + B2) / 2, L * 0.5)), "L", 268, "A  top and bottom flare panels",
         f"{mm_str(G['a1'])} wide at the mouth"),
        (pr((10, -(b2 + B2) / 2 - 6, L * 0.62)), "L", 58, "the mouth",
         f"{mm_str(G['a1'])} × {mm_str(G['b1'])} inside\nyou are looking into it"),
        (pr((0, b2 + 12, z)), "R", 272, "F  SMA connector",
         f"brass probe {mm_str(G['probe_len'])} mm inside"),
        (pr((-8, b2, -Lg * 0.9)), "R", 232, "C  wide pipe walls",
         "the top one carries the connector"),
        (pr((a2, 0, -Lg)), "R", 190, "E  back wall", "closes the far end of the pipe"),
        (pr((a2, -b2 * 0.4, -Lg * 0.62)), "R", 146, "D  narrow pipe walls", ""),
        (pr(((a2 + A2) / 2 + 4, -B2 * 0.15, L * 0.5)), "R", 62, "B  side flare panels",
         f"{mm_str(G['b1'])} tall at the mouth"),
    ])
    return d


def fig_mouth_view():
    """Looking straight into the mouth."""
    W, H = 200, 150
    d = Drawing(W, H)
    sc = 0.42
    sh = Sheet(W, H, sc, W / 2, H / 2 + 6)
    sh.d = d
    A2, B2, a2, b2 = G["a1"] / 2, G["b1"] / 2, G["a"] / 2, G["b"] / 2
    sh.poly([(-A2, -B2), (A2, -B2), (A2, B2), (-A2, B2)], fill=CU_IN, stroke=CU_EDGE, width=0.9)
    for sx, sy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
        sh.line((sx * a2, sy * b2), (sx * A2, sy * B2), CU_EDGE, 0.6)
    sh.poly([(-a2, -b2), (a2, -b2), (a2, b2), (-a2, b2)], fill=colors.HexColor("#5a3420"),
            stroke=CU_EDGE, width=0.7)
    sh.dim((-A2, -B2), (A2, -B2), -12, mm_str(G["a1"]), size=7)
    sh.dim((A2, -B2), (A2, B2), -12, mm_str(G["b1"]), size=7)
    sh.text((0, -3), f"{mm_str(G['a'])} × {mm_str(G['b'])}", 6.4, colors.white)
    d.add(String(W / 2, H - 10, "looking into the mouth", fontName="DJ-B", fontSize=8,
                 fillColor=INK, textAnchor="middle"))
    return d



def fig_exploded():
    """The build in three stages, each from the cover's viewpoint, parts lettered."""
    W, H = BODY_W, 236
    d = Drawing(W, H)
    parts = horn_parts()
    pipe = {k: parts[k] for k in ("C_top", "C_bot", "D_right", "D_left", "E")}
    with_f = dict(pipe, F=parts["F"])
    a2, b2, A2, B2, L, Lg = G["a"] / 2, G["b"] / 2, G["a1"] / 2, G["b1"] / 2, G["L"], G["Lg"]
    cw = W / 3

    def tag(cam, p, letter, big=True):
        x, y = cam.proj(p)
        d.add(Circle(x, y, 8 if big else 7, fillColor=colors.white, strokeColor=ACC, strokeWidth=1.1))
        d.add(String(x, y - 3.6, letter, fontName="DJ-B", fontSize=10 if big else 9, fillColor=ACC,
                     textAnchor="middle"))

    # stage 1: the pipe, walls parted a little, back wall pulled back
    off1 = {"C_top": (0, 16, 0), "D_right": (18, 0, 0), "E": (0, 0, -48)}
    c1 = Cam(AZ, EL, 0.74, cw * 0.5 + 4, 134)
    render_horn(d, c1, off1, pipe)
    tag(c1, (0, b2 + 16, -Lg * 0.45), "C")
    tag(c1, (a2 + 18, -4, -Lg * 0.5), "D")
    tag(c1, (0, 0, -Lg - 48), "E")
    # stage 2: pipe closed, connector on
    c2 = Cam(AZ, EL, 0.74, cw * 1.5 + 4, 134)
    render_horn(d, c2, {}, with_f)
    tag(c2, (0, b2 + 30, -Lg + G["probe_z"] - 34), "F")
    x0, y0 = c2.proj((0, b2 + 12, -Lg + G["probe_z"]))
    x1, y1 = c2.proj((0, b2 + 24, -Lg + G["probe_z"] - 28))
    d.add(Line(x0, y0, x1, y1, strokeColor=ACC, strokeWidth=0.7))
    # stage 3: the flare on
    c3 = Cam(AZ, EL, 0.43, cw * 2.5 + 18, 140)
    render_horn(d, c3, {}, parts)
    mouth_rim(d, c3, width=1.1)
    tag(c3, (-20, (b2 + B2) / 2, L * 0.55), "A")
    tag(c3, ((a2 + A2) / 2 + 3, -10, L * 0.5), "B")
    tag(c3, (10, -(b2 + B2) / 2 - 6, L * 0.62), "A", big=False)
    for i, (title, lines) in enumerate((
            ("1  the pipe", ["two wide walls C, two narrow", "walls D, and the back wall E"]),
            ("2  the connector", ["F bolts to the top wall, its", "rod reaching down inside"]),
            ("3  the flare", ["two A panels and two B panels", "on the front of the pipe"]))):
        cx = cw * i + cw / 2
        d.add(String(cx, 34, title, fontName="DJ-B", fontSize=9, fillColor=INK, textAnchor="middle"))
        for j, s in enumerate(lines):
            d.add(String(cx, 21 - j * 10, s, fontName="DJ", fontSize=7.6, fillColor=MUT,
                         textAnchor="middle"))
        if i:
            d.add(String(cw * i + 2, 118, "→", fontName="DJ-B", fontSize=16, fillColor=MUT,
                         textAnchor="middle"))
    return d


def _section(kind):
    """Side ('side') or top ('top') cut through the middle, to scale, with notes."""
    side = kind == "side"
    sc = 0.9
    Lg, L = G["Lg"], G["L"]
    hin = (G["b"] if side else G["a"]) / 2
    hout = (G["b1"] if side else G["a1"]) / 2
    H = 2 * hout * sc + (78 if side else 52)
    W = BODY_W
    d = Drawing(W, H)
    ox, oy = 78 + Lg * sc, 34 + hout * sc
    sh = Sheet(W, H, sc, ox, oy)
    sh.d = d
    pts = [(-Lg, -hin), (0, -hin), (L, -hout), (L, hout), (0, hin), (-Lg, hin)]
    sh.poly(pts, fill=colors.HexColor("#f6f1e8"), stroke=None)
    for s in (1, -1):
        sh.line((-Lg, s * hin), (0, s * hin), CU_EDGE, 2.4)
        sh.line((0, s * hin), (L, s * hout), CU_EDGE, 2.4)
    sh.line((-Lg, -hin), (-Lg, hin), CU_EDGE, 2.4)
    sh.line((-Lg - 6, 0), (L + 6, 0), MUT, 0.4, dash=[5, 2, 1, 2])
    zp = -Lg + G["probe_z"]
    if side:
        sh.poly([(zp - 6.35, hin), (zp + 6.35, hin), (zp + 6.35, hin + 1.8), (zp - 6.35, hin + 1.8)],
                fill=STEEL, stroke=INK, width=0.4)
        sh.poly([(zp - 3.2, hin + 1.8), (zp + 3.2, hin + 1.8), (zp + 3.2, hin + 12), (zp - 3.2, hin + 12)],
                fill=colors.HexColor("#d9b75e"), stroke=INK, width=0.4)
        sh.line((zp, hin), (zp, hin - G["probe_len"]), BRASS, 2.4)
        yd = hin + 24
        sh.line((-Lg, hin + 2), (-Lg, yd + 3), DIM, 0.35)
        sh.line((zp, hin + 13), (zp, yd + 3), DIM, 0.35)
        sh.dim((-Lg, yd), (zp, yd), 0, mm_str(G["probe_z"]), ext=False)
        sh.dim((zp + 7, hin), (zp + 7, hin - G["probe_len"]), 0.001, mm_str(G["probe_len"]),
               ext=False, size=6.8, text_off=-8.5)
        sh.line((zp + 1.5, hin - G["probe_len"]), (zp + 10, hin - G["probe_len"]), DIM, 0.35)
    else:
        sh.circle((zp, 0), 2.2, fill=BRASS, stroke=INK, width=0.5)
    yb = -hout - 13
    for zz, hh in ((-Lg, hin), (0, hin), (L, hout)):
        sh.line((zz, -hh - 2), (zz, yb - 3), DIM, 0.35)
    sh.dim((-Lg, yb), (0, yb), 0, f"{mm_str(Lg)}  pipe", ext=False)
    sh.dim((0, yb), (L, yb), 0, f"{mm_str(L)}  flare", ext=False)
    xl = -Lg - 12
    sh.line((-Lg - 2, hin), (xl - 3, hin), DIM, 0.35)
    sh.line((-Lg - 2, -hin), (xl - 3, -hin), DIM, 0.35)
    sh.dim((xl, -hin), (xl, hin), 0, mm_str(2 * hin), ext=False, text_off=3)
    sh.dim((L + 10, -hout), (L + 10, hout), 0, mm_str(2 * hout), ext=False, text_off=-9)
    # part letters
    lw = "C" if side else "D"
    lf = "A" if side else "B"
    sh.text((-Lg * 0.72, hin + 5), lw, 9.5, ACC, bold=True)
    sh.text((-Lg * 0.72, -hin - 11), lw, 9.5, ACC, bold=True)
    mid = ((L / 2), (hin + hout) / 2)
    sh.text((mid[0] - 12, mid[1] + 8), lf, 9.5, ACC, bold=True)
    sh.text((mid[0] - 12, -mid[1] - 16), lf, 9.5, ACC, bold=True)
    sh.text((-Lg + 7, -3.5), "E", 9.5, ACC, bold=True)
    if side:
        sh.text((zp + 9, hin + 6), "F", 9.5, ACC, "start", bold=True)
        notes = ["**SIDE VIEW, cut down the middle**", "",
                 "The connector (F) sits on top of", "the pipe. Its brass rod hangs",
                 f"{mm_str(G['probe_len'])} mm down into the pipe,",
                 f"{mm_str(G['probe_z'])} mm in front of the back wall (E).", "",
                 "The top and bottom panels (A)", f"lean out {G['lean_top']:.0f}° from the pipe."]
    else:
        notes = ["**TOP VIEW, cut across the middle**", "",
                 "The rod sits exactly halfway", "across the pipe, on the centre", "line (the brass dot).", "",
                 "The side panels (B) lean out", f"{G['lean_side']:.0f}° from the pipe."]
    text_block(d, ox + (L + 34) * sc, H - 18, notes)
    return d


def draw_piece(sh, piece, letter=None, fill=CU_OUT, show_bends=True, label_size=10):
    for tb in piece["tabs"]:
        sh.poly(tb, fill=TAB, stroke=CU_EDGE, width=0.6)
    sh.poly(piece["body"], fill=fill, stroke=CU_EDGE, width=0.8)
    if show_bends:
        for p, q in piece["bends"]:
            sh.line(p, q, BEND, 0.8, dash=[3, 2])
    if "hole" in piece:
        sh.circle(piece["hole"], 2.25, fill=colors.white, stroke=INK, width=0.6)
    if letter:
        c = SPoly(piece["body"]).representative_point()
        sh.text((c.x, c.y - 2.5), letter, label_size, ACC, bold=True)


def fig_flat_A():
    W, H = BODY_W, 150
    d = Drawing(W, H)
    sc = 0.86
    sh = Sheet(W, H, sc, 12, 26)
    sh.d = d
    a1, a, h = G["a1"], G["a"], G["h_top"]
    draw_piece(sh, piece_A())
    sh.dim((0, 0), (a1, 0), -9, f"{mm_str(a1)}   long edge, the mouth")
    sh.dim(((a1 - a) / 2, h), ((a1 + a) / 2, h), 8, f"{mm_str(a)}   short edge, the pipe end")
    sh.line((a1 / 2, 0), (a1 / 2, h), MUT, 0.4, dash=[5, 2, 1, 2])
    sh.dim((a1 / 2, 0), (a1 / 2, h), 0.001, mm_str(h), ext=False, text_off=3)
    sh.dim((a1, 0), ((a1 + a) / 2, h), -8, f"{mm_str(G['seam'])}  check")
    sh.text((a1 * 0.28, h * 0.35), "A", 16, ACC, bold=True)
    text_block(d, 318, H - 22, ["**A  top and bottom flare panels**",
                                "cut 2 per horn  ·  no tabs", "",
                                "The long edge is the mouth, the short",
                                "edge meets the pipe. The height is",
                                "measured up the centre line, square",
                                "to both edges."])
    return d


def fig_flat_B():
    W, H = BODY_W, 160
    d = Drawing(W, H)
    sc = 0.86
    sh = Sheet(W, H, sc, 30, 26)
    sh.d = d
    b1, b, h = G["b1"], G["b"], G["h_side"]
    draw_piece(sh, piece_B())
    sh.dim((0, 0), (b1, 0), -9, f"{mm_str(b1)}   long edge, the mouth")
    sh.dim(((b1 - b) / 2, h), ((b1 + b) / 2, h), 8, mm_str(b))
    sh.line((b1 / 2, 0), (b1 / 2, h), MUT, 0.4, dash=[5, 2, 1, 2])
    sh.dim((b1 / 2, 0), (b1 / 2, h), 0.001, mm_str(h), ext=False, text_off=3)
    sh.dim((0, 0), ((b1 - b) / 2, h), 15, f"{mm_str(G['seam'])}  check")
    sh.text((b1 * 0.68, h * 0.3), "B", 16, ACC, bold=True)
    text_block(d, 318, H - 22, ["**B  side flare panels**",
                                "cut 2 per horn", "",
                                "A 6 mm tab on both slanted edges,",
                                "its ends cut off at 45°.", "",
                                f"**Fold each tab {G['corner_bend']:.0f}° away from you,**",
                                "so it lies on the outside of an A panel."])
    return d


def fig_flat_pipe():
    W, H = BODY_W, 200
    d = Drawing(W, H)
    sc = 1.0
    x = 14
    items = [(piece_C(hole=True), "C", "top wide wall", "cut 1  ·  feed hole"),
             (piece_C(), "C", "bottom wide wall", "cut 1"),
             (piece_D(), "D", "narrow wall", "cut 2"),
             (piece_E(), "E", "back wall", "cut 1")]
    base_y = 30
    for piece, letter, name, qty in items:
        shp = outline(piece)
        x0, y0, x1, y1 = shp.bounds
        sh = Sheet(W, H, sc, x - x0 * sc, base_y - y0 * sc)
        sh.d = d
        draw_piece(sh, piece)
        body = piece["body"]
        bw = body[1][0] - body[0][0]
        bh = body[2][1] - body[1][1]
        sh.text((bw / 2, bh * 0.62), letter, 14, ACC, bold=True)
        sh.dim((0, 0), (bw, 0), -12 if letter != "E" else -11, mm_str(bw))
        if letter == "E":
            sh.dim((bw, 0), (bw, bh), -13, mm_str(bh))
        else:
            sh.dim((0, 0), (0, bh), 12, mm_str(bh), text_off=3)
        if "hole" in piece:
            hx, hy = piece["hole"]
            sh.line((hx, 0), (hx, hy - 2.5), DIM, 0.35, dash=[2, 1.5])
            sh.dim((hx + 8, 0), (hx + 8, hy), 0.001, mm_str(G["probe_z"]), ext=False, size=6.8,
                   text_off=-8.5)
            sh.line((hx + 2.5, hy), (hx + 11, hy), DIM, 0.35)
            sh.text((hx, hy + 5), "feed hole, centred", 6.4, INK)
        tx = x + (x1 - x0) * sc / 2
        top = base_y + (y1 - y0) * sc
        d.add(String(tx, top + 16, name, fontName="DJ-B", fontSize=8.2, fillColor=INK,
                     textAnchor="middle"))
        d.add(String(tx, top + 6, qty, fontName="DJ", fontSize=7.2, fillColor=MUT, textAnchor="middle"))
        x += (x1 - x0) * sc + 30
    return d


def fig_legend():
    d = Drawing(BODY_W, 22)
    x = 2
    d.add(Rect(x, 6, 18, 11, fillColor=CU_OUT, strokeColor=CU_EDGE, strokeWidth=0.7))
    d.add(String(x + 24, 8, "the wall itself", fontName="DJ", fontSize=8, fillColor=INK))
    x += 108
    d.add(Rect(x, 6, 18, 11, fillColor=TAB, strokeColor=CU_EDGE, strokeWidth=0.7))
    d.add(String(x + 24, 8, "solder tab, 6 mm", fontName="DJ", fontSize=8, fillColor=INK))
    x += 116
    d.add(Line(x, 11.5, x + 22, 11.5, strokeColor=BEND, strokeWidth=0.9, strokeDashArray=[3, 2]))
    d.add(String(x + 28, 8, "fold line", fontName="DJ", fontSize=8, fillColor=INK))
    x += 80
    d.add(Line(x, 11.5, x + 22, 11.5, strokeColor=CU_EDGE, strokeWidth=0.9))
    d.add(String(x + 28, 8, "cut line", fontName="DJ", fontSize=8, fillColor=INK))
    x += 74
    d.add(String(x, 8, "sizes in mm, drawn to scale", fontName="DJ", fontSize=8, fillColor=MUT))
    return d


def fig_sheet():
    W = BODY_W
    sc = (W - 24) / SHEET_W
    H = SHEET_H * sc + 24
    d = Drawing(W, H)
    sh = Sheet(W, H, sc, 4, 18)
    sh.d = d
    sh.poly([(0, 0), (SHEET_W, 0), (SHEET_W, SHEET_H), (0, SHEET_H)],
            fill=colors.HexColor("#faf6f0"), stroke=INK, width=0.9)
    for letter, piece in LAYOUT:
        draw_piece(sh, piece, letter, label_size=12)
    d.add(String(4 + SHEET_W * sc / 2, 5, "610 mm  (24 in)", fontName="DJ", fontSize=7.6,
                 fillColor=MUT, textAnchor="middle"))
    g = Group(String(0, 0, "305 mm  (12 in)", fontName="DJ", fontSize=7.6, fillColor=MUT,
                     textAnchor="middle"))
    g.translate(4 + SHEET_W * sc + 12, 18 + SHEET_H * sc / 2)
    g.rotate(90)
    d.add(g)
    return d


def fig_marking():
    W, H = BODY_W, 150
    d = Drawing(W, H)
    sc = 0.6
    sh = Sheet(W, H, sc, 24, 26)
    sh.d = d
    a1, a, h = G["a1"], G["a"], G["h_top"]
    sh.poly(trapezoid(a, a1, h), fill=None, stroke=CU_EDGE, width=0.9)
    sh.line((-8, 0), (a1 + 8, 0), MUT, 0.5)
    sh.line((-8, h), (a1 + 8, h), MUT, 0.5, dash=[3, 2])
    sh.line((a1 / 2, -6), (a1 / 2, h + 8), ACC, 0.7, dash=[5, 2, 1, 2])
    sh.dim((a1 / 2, 0), (a1, 0), -10, mm_str(a1 / 2))
    sh.dim((a1 / 2, h), ((a1 + a) / 2, h), 9, mm_str(a / 2))
    sh.dim((a1 / 2, 0), (a1 / 2, h), 12, mm_str(h))
    marks = [("1", (8, -9)), ("2", (a1 / 2 + 7, 8)), ("3", (a1 / 2 + 7, h - 8)),
             ("4", ((a1 + a) / 2 + 8, h - 8)), ("5", ((a1 + (a1 + a) / 2) / 2 + 12, h / 2))]
    for n, p in marks:
        x, y = sh.P(p)
        d.add(Circle(x, y, 6.5, fillColor=ACC, strokeColor=None))
        d.add(String(x, y - 3, n, fontName="DJ-B", fontSize=8, fillColor=colors.white,
                     textAnchor="middle"))
    text_block(d, 214, H - 20, [
        "1  Draw the long edge with a straight edge.",
        "2  Mark its middle and square a centre line up from it.",
        "3  Measure the height up the centre line and square",
        "    a second line across there.",
        "4  From the centre line, measure half of each edge out",
        "    both ways along its own line.",
        "5  Join the marks. Both slanted edges must come out",
        f"    {mm_str(G['seam'])} mm, on every A and every B."], size=8.2, lead=12)
    return d


def fig_folds():
    W, H = BODY_W, 132
    d = Drawing(W, H)
    items = [("pipe corners", 90, "C side tabs, folded\nover the D walls"),
             ("back wall", 90, "E, all four tabs,\nfolded over the pipe"),
             ("wide wall front", G["lean_top"], "C front tab: the collar\nthe A panels sit on"),
             ("narrow wall front", G["lean_side"], "D front tab: the collar\nthe B panels sit on"),
             ("flare corners", G["corner_bend"], "B slanted tabs, over\nthe outside of A")]
    cw = W / len(items)
    for i, (name, ang, note) in enumerate(items):
        cx = i * cw + cw / 2
        y0 = 62
        L1, L2 = 36, 26
        x0 = cx - L1 / 2 - 8
        d.add(Line(x0, y0, x0 + L1, y0, strokeColor=CU_EDGE, strokeWidth=3.2))
        r = math.radians(ang)
        d.add(Line(x0 + L1, y0, x0 + L1 + L2 * math.cos(r), y0 + L2 * math.sin(r),
                   strokeColor=colors.HexColor("#d39a73"), strokeWidth=3.2))
        d.add(Line(x0 + L1, y0, x0 + L1 + L2 + 4, y0, strokeColor=MUT, strokeWidth=0.4,
                   strokeDashArray=[2, 2]))
        pts = []
        for k in range(21):
            aa = r * k / 20
            pts += [x0 + L1 + 14 * math.cos(aa), y0 + 14 * math.sin(aa)]
        d.add(PolyLine(pts, strokeColor=BEND, strokeWidth=0.8))
        d.add(String(x0 + L1 + 19 * math.cos(r / 2) + 2, y0 + 19 * math.sin(r / 2) - 3,
                     f"{ang:.0f}°", fontName="DJ-B", fontSize=9.5, fillColor=BEND))
        d.add(String(cx, 112, name, fontName="DJ-B", fontSize=8.4, fillColor=INK, textAnchor="middle"))
        for j, s in enumerate(note.split("\n")):
            d.add(String(cx, 38 - j * 10, s, fontName="DJ", fontSize=7.4, fillColor=MUT,
                         textAnchor="middle"))
    d.add(String(2, 2, "Cut a cardboard angle gauge for each of the three odd angles and hold it "
                 "against every fold of that kind.", fontName="DJ", fontSize=7.6, fillColor=INK))
    return d


def fig_pipe_end():
    W, H = BODY_W, 170
    d = Drawing(W, H)
    sc = 1.5
    sh = Sheet(W, H, sc, 150, 86)
    sh.d = d
    a2, b2, t = G["a"] / 2, G["b"] / 2, G["t"] * 3.0
    tb = G["tab"]
    for s in (1, -1):
        xi, xo = s * a2, s * (a2 + t)
        sh.poly([(min(xi, xo), -b2), (max(xi, xo), -b2), (max(xi, xo), b2), (min(xi, xo), b2)],
                fill=CU_IN, stroke=CU_EDGE, width=0.5)
    for s in (1, -1):
        yi, yo = s * b2, s * (b2 + t)
        sh.poly([(-a2 - t, min(yi, yo)), (a2 + t, min(yi, yo)), (a2 + t, max(yi, yo)),
                 (-a2 - t, max(yi, yo))], fill=CU_OUT, stroke=CU_EDGE, width=0.5)
        for sx in (1, -1):
            xo = sx * (a2 + t)
            sh.poly([(xo, yi), (xo + sx * t, yi), (xo + sx * t, yi - s * tb), (xo, yi - s * tb)],
                    fill=TAB, stroke=CU_EDGE, width=0.5)
            sh.circle((xo + sx * t * 1.7, yi - s * tb * 0.5), 1.2, fill=colors.HexColor("#8c8f94"),
                      stroke=None)
    sh.line((-a2, -b2 - 2), (-a2, -b2 - 16), DIM, 0.35)
    sh.line((a2, -b2 - 2), (a2, -b2 - 16), DIM, 0.35)
    sh.dim((-a2, -b2 - 13), (a2, -b2 - 13), 0, f"{mm_str(G['a'])} inside", ext=False)
    sh.dim((a2 - 12, -b2), (a2 - 12, b2), 0, f"{mm_str(G['b'])} inside", ext=False, text_off=-9)
    sh.text((0, b2 + 9), f"C  wide wall, cut {mm_str(G['wide_w'])} wide", 7.6, INK, bold=True)
    sh.text((-a2 - 14, -2.5), "D", 10, ACC, "end", bold=True)
    sh.text((a2 + 12, -2.5), "D", 10, ACC, "start", bold=True)
    text_block(d, 322, H - 16, [
        "**Looking into the back of the pipe**", "",
        "The narrow walls (D) stand between",
        "the wide walls (C). The wide walls lap",
        "over their edges, which is why they are",
        f"cut {mm_str(G['wide_w'])} wide, not {mm_str(G['a'])}.", "",
        "Each C side tab folds down over the",
        "outside of a D wall. Solder there.",
        "Grey dots: solder. Thickness drawn 3×."], size=8, lead=11.4)
    return d


def fig_feed():
    W, H = BODY_W, 200
    d = Drawing(W, H)
    sc = 3.0
    sh = Sheet(W, H, sc, 150, 132)
    sh.d = d
    t = G["t"] * 2.0
    sh.poly([(-36, 0), (-2.25, 0), (-2.25, t), (-36, t)], fill=CU_OUT, stroke=CU_EDGE, width=0.5)
    sh.poly([(2.25, 0), (36, 0), (36, t), (2.25, t)], fill=CU_OUT, stroke=CU_EDGE, width=0.5)
    sh.text((-35.5, t + 1.6), "top wide wall (C)", 7, INK, "start", bold=True)
    sh.text((-35.5, -4.5), "inside the pipe", 7, MUT, "start")
    sh.poly([(-6.35, t), (6.35, t), (6.35, t + 1.6), (-6.35, t + 1.6)], fill=STEEL, stroke=INK, width=0.4)
    for sx in (-1, 1):
        sh.poly([(sx * 4.32 - 1.1, -2.5), (sx * 4.32 + 1.1, -2.5), (sx * 4.32 + 1.1, t + 3.2),
                 (sx * 4.32 - 1.1, t + 3.2)], fill=colors.HexColor("#8c8f94"), stroke=INK, width=0.3)
    sh.poly([(-3.2, t + 1.6), (3.2, t + 1.6), (3.2, t + 11), (-3.2, t + 11)],
            fill=colors.HexColor("#d9b75e"), stroke=INK, width=0.4)
    sh.poly([(-2.05, t), (2.05, t), (2.05, -2.0), (-2.05, -2.0)], fill=colors.white, stroke=INK, width=0.4)
    sh.poly([(-0.9, -2.0), (0.9, -2.0), (0.9, -5.2), (-0.9, -5.2)], fill=BRASS, stroke=INK, width=0.4)
    sh.poly([(-0.79, -5.2), (0.79, -5.2), (0.79, -30), (-0.79, -30)], fill=BRASS, stroke=INK, width=0.4)
    sh.line((-2.6, -21.2), (2.6, -19.6), colors.white, 3.4)
    sh.line((-2.6, -21.2), (2.6, -19.6), INK, 0.4)
    sh.line((-2.6, -22.4), (2.6, -20.8), INK, 0.4)
    sh.line((-7, 0), (-1.2, 0), DIM, 0.35)
    sh.line((-7, -30), (-1.2, -30), DIM, 0.35)
    sh.dim((-5, -30), (-5, 0), 0.001, f"{mm_str(G['probe_len'])} mm", ext=False, text_off=3, size=7)
    sh.text((-9, -34), "rod drawn shortened", 6.4, MUT, "middle")
    pr = sh.P
    callouts(d, W, [
        (pr((0, t + 9)), "R", 186, "SMA connector", "threaded end up, to the radar's coax"),
        (pr((6.0, t + 0.9)), "R", 148, "4-hole flange, flat on the copper",
         "scrape the copper bright under it"),
        (pr((4.32, -2.3)), "R", 112, "screw and nut, M2.5 or 2-56",
         "mark the holes from the flange itself"),
        (pr((2.05, -1.0)), "R", 80, "centre hole clears the white insulator",
         "usually 4 to 5 mm: measure yours"),
        (pr((0.9, -3.8)), "R", 52, "solder cup, facing into the pipe", ""),
        (pr((0.79, -14)), "R", 24, "1/16 in brass rod, soldered in the cup",
         "straight down, square to the wall"),
    ])
    return d


def fig_mount():
    W, H = BODY_W, 190
    d = Drawing(W, H)
    sc = 0.3
    b1, a1 = G["b1"] * sc, G["a1"] * sc
    cx, base = 140, 30
    for i, (name, live) in enumerate((("RX", True), ("empty bay", False))):
        x0 = cx - b1 + i * b1
        d.add(Rect(x0, base, b1, a1, fillColor=CU_OUT if live else colors.white, strokeColor=CU_EDGE,
                   strokeWidth=0.8, strokeDashArray=None if live else [3, 2]))
        d.add(String(x0 + b1 / 2, base + a1 / 2 - 3, name, fontName="DJ-B", fontSize=8.5,
                     fillColor=INK, textAnchor="middle"))
    ty = base + 290 * sc
    d.add(Rect(cx - b1 / 2, ty, b1, a1, fillColor=CU_OUT, strokeColor=CU_EDGE, strokeWidth=0.8))
    d.add(String(cx, ty + a1 / 2 - 3, "TX", fontName="DJ-B", fontSize=8.5, fillColor=INK,
                 textAnchor="middle"))
    sh = Sheet(W, H, 1.0, 0, 0)
    sh.d = d
    c1, c2 = cx - b1 / 2, cx + b1 / 2
    for xx in (c1, c2):
        sh.line((xx, base - 2), (xx, base - 13), DIM, 0.35)
    sh.dim((c1, base - 10), (c2, base - 10), 0, "193 centre to centre", ext=False, size=7,
           text_off=-10)
    yr, yt = base + a1 / 2, ty + a1 / 2
    xr = cx + b1 + 10
    sh.line((cx + b1 + 2, yr), (xr + 3, yr), DIM, 0.35)
    sh.line((cx + b1 / 2 + 2, yt), (xr + 3, yt), DIM, 0.35)
    sh.dim((xr, yr), (xr, yt), 0.001, "290", ext=False, size=7, text_off=-9)
    text_block(d, 312, H - 16, [
        "**Seen from the front, into the mouths**", "",
        "Turn every horn a quarter turn, so the",
        f"{mm_str(G['b1'])} side runs across and the {mm_str(G['a1'])}",
        "side runs up. The connector ends up on",
        "the side of the pipe.", "",
        "All three mouths flush in one plane.",
        "The RX horn and the empty bay touch,",
        "and TX is centred above the pair.", "",
        "Grip each horn by its pipe, never by", "the flare."], size=8, lead=11.6)
    return d


def fig_continuity():
    W, H = BODY_W, 196
    d = Drawing(W, H)
    cam = Cam(AZ, EL, 0.5, 128, 112)
    render_horn(d, cam)
    mouth_rim(d, cam, width=1.2)
    a2, b2, A2, B2, L, Lg = G["a"] / 2, G["b"] / 2, G["a1"] / 2, G["b1"] / 2, G["L"], G["Lg"]
    pts = [((-20, (b2 + B2) / 2, L * 0.5), "1"), (((a2 + A2) / 2 + 4, -10, L * 0.5), "2"),
           ((-26, b2, -Lg * 0.25), "3"), ((a2, -4, -Lg * 0.6), "4"),
           ((10, -(b2 + B2) / 2 - 6, L * 0.62), "5"), ((0, b2 + 12, -Lg + G["probe_z"]), "6")]
    for p, n in pts:
        x, y = cam.proj(p)
        d.add(Circle(x, y, 6, fillColor=colors.white, strokeColor=ACC, strokeWidth=1.2))
        d.add(String(x, y - 3, n, fontName="DJ-B", fontSize=7.4, fillColor=ACC, textAnchor="middle"))
    text_block(d, 262, H - 14, [
        "**Every piece to every other piece**",
        "Meter on its lowest resistance range. Touch the",
        "probes to bare copper on two different pieces.",
        "Test 1 to 2, 1 to 3, 1 to 4, 1 to 5, 2 to 3, and on:",
        "every pair, across every seam.", "",
        "**Pass: under 0.5 Ω, every pair.**", "",
        "Then the connector (6): its outer body to the",
        "copper under 0.5 Ω, its centre pin to the copper",
        "open. The pin touching the copper is a short."], size=8, lead=11.4)
    return d


# ────────────────────────────────────────────────────────────── document ──
def on_page(canv, doc):
    canv.saveState()
    canv.setStrokeColor(RULE)
    canv.setLineWidth(0.5)
    canv.line(M, PAGE_H - 30, PAGE_W - M, PAGE_H - 30)
    canv.setFont("DJ", 7.6)
    canv.setFillColor(MUT)
    canv.drawString(M, PAGE_H - 25, "Horn antenna build guide  ·  2.45 GHz, copper sheet")
    canv.drawRightString(PAGE_W - M, PAGE_H - 25, "radar-dev")
    canv.line(M, 30, PAGE_W - M, 30)
    canv.drawString(M, 20, "Sizes in mm, computed by antenna/tools/horn.py. "
                           "Pipe and mouth sizes are inside sizes.")
    canv.drawRightString(PAGE_W - M, 20, f"{doc.page}")
    canv.restoreState()


def keep(*items):
    flat = []
    for it in items:
        flat.extend(it if isinstance(it, list) else [it])
    return KeepTogether(flat)


def build():
    doc = BaseDocTemplate(str(OUT), pagesize=LETTER, leftMargin=M, rightMargin=M,
                          topMargin=40, bottomMargin=40, title="Horn antenna build guide",
                          author="radar-dev",
                          subject="Building the 2.45 GHz pyramidal horn from copper sheet")
    frame = Frame(M, 40, BODY_W, PAGE_H - 80, id="f", leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="p", frames=[frame], onPage=on_page)])
    g = G
    story = []

    # ── cover
    spec = table([["mouth, inside", f"{mm_str(g['a1'])} × {mm_str(g['b1'])} mm"],
                  ["flare depth", f"{mm_str(g['L'])} mm, mouth to pipe"],
                  ["pipe, inside", f"{mm_str(g['a'])} × {mm_str(g['b'])} mm, {mm_str(g['Lg'])} mm long"],
                  ["probe", f"{mm_str(g['probe_len'])} mm into the pipe, {mm_str(g['probe_z'])} mm "
                            "from the back wall, on the centre line"],
                  ["what it does", f"focuses the signal about {10 ** (g['gain'] / 10):.0f} times "
                                   f"({g['gain']:.1f} dBi) into a beam about {g['hp_e']:.0f}° × "
                                   f"{g['hp_h']:.0f}° wide"],
                  ["copper", "one 12 × 24 in sheet per horn"]],
                 [1, 2.6], head=False, width=BODY_W - 214)
    row = Table([[spec, fig_mouth_view()]], colWidths=[BODY_W - 206, 206])
    row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0)]))
    story += [P("Horn antenna build guide", "title"),
              P("Three identical horns, cut from 24 gauge copper sheet and soldered together. One "
                "transmits, one receives, and one is the spare for the azimuth upgrade.", "sub"),
              fig_cover(), Spacer(1, 6), row,
              Spacer(1, 8),
              P("How to use this guide", "h2"),
              bullets(["Pages 2 and 3 show how the nine pieces fit together, and what the inside "
                       "looks like.",
                       "Pages 4 to 6 are the shopping list, the cut list, every piece drawn flat, and "
                       "how to lay one horn out on one sheet.",
                       "Pages 7 to 9 are the build, nine steps, each with its check.",
                       "The last page is a record to fill in for all three horns."]),
              PageBreak()]

    # ── how it fits together
    story += [P("How it fits together", "h1"),
              P("The horn is a short rectangular pipe that opens out into a wide mouth, like a "
                "megaphone. The pipe is closed at the back. The radar's cable plugs into a connector "
                "on top of the pipe, and a short brass rod under that connector passes the signal into "
                "the pipe. The flare then shapes it into a beam. Nine flat pieces make one horn, "
                "lettered A to E all through this guide, and F is the bought connector."),
              *fig(fig_exploded(), "The order it goes together. The pipe is built first as a closed box, "
                                  "then the connector goes on, then the four flare panels."),
              P("Words used in this guide", "h2"),
              table([["word", "means"],
                     ["pipe", f"the closed rectangular box at the back, {mm_str(g['a'])} × {mm_str(g['b'])} "
                      "inside. Pieces C, D and E"],
                     ["flare", "the four sloping panels that open out from the pipe to the mouth. "
                      "Pieces A and B"],
                     ["mouth", "the big open end the beam comes out of"],
                     ["probe", "the short brass rod inside the pipe, soldered to the connector. It "
                      "passes the signal between the cable and the horn"],
                     ["tab", "a 6 mm strip along an edge, folded over so two pieces overlap and "
                      "can be soldered"],
                     ["collar", "the front tabs of the pipe, folded outward. The flare panels sit on "
                      "them"],
                     ["seam", "any joint between two pieces. Every seam must be soldered closed"],
                     ["inside size", "measured between the inside faces of the copper. Every pipe "
                      "and mouth size in this guide is an inside size"]],
                    [1.2, 5.8]),
              Spacer(1, 8),
              callout("Why the inside matters and the outside does not",
                      "The radio wave only ever touches the inside surface of the copper. Keep the "
                      "inside smooth, every seam closed and every size right. All soldering is done "
                      "from the outside, and it can look as rough as it likes."),
              PageBreak(),
              P("Inside the horn, to scale", "h1"),
              P("Both views cut the horn in half down the middle. Every inside size the build has "
                "to hit is on one of them."),
              *fig(_section("side"), "Side view. The connector's rod stands straight down from the top wall."),
              *fig(_section("top"), "Top view. The rod is halfway across, on the centre line."),
              PageBreak()]

    # ── materials, cut list
    story += [P("What you need", "h1"),
              table([["for three horns", "", "notes"],
                     ["copper sheet, 24 gauge (0.021 in), 12 × 24 in", "3 sheets",
                      "one sheet per horn (page 6). Copper, so the seams take solder"],
                     ["SMA female connector, 4-hole flange, solder cup", "3, plus spares",
                      "must be solder cup, not a PCB pin"],
                     ["brass rod, 1/16 in", "about 100 mm", f"three probes cut {mm_str(g['rod_cut'])} mm "
                      "long, trimmed later"],
                     ["plumbing solder and paste flux", "", "not electronics rosin-core. The seams are "
                      "long and copper soaks up heat"],
                     ["screws and nuts, M2.5 or 2-56", "12 sets", "four per connector. The flange holes "
                      "are too small for M3"]],
                    [3.2, 1.3, 3.5]),
              Spacer(1, 6),
              table([["tools", "used for"],
                     ["aviation snips or a sheet nibbler", "cutting the pieces"],
                     ["steel rule, square, fine marker or scriber", "marking out"],
                     ["60 to 100 W iron with a big tip, or a small torch", "soldering. A 25 W "
                      "electronics iron will not heat the sheet"],
                     ["two lengths of angle iron or hardwood, and clamps", "folding tabs on a straight line"],
                     ["drill, 2.7 mm and 4.5 mm bits, a centre punch, a file", "the connector holes, "
                      "and deburring"],
                     ["calipers and a multimeter", "checking sizes and seams"],
                     ["gloves and safety glasses", "cut copper edges are sharp. Ventilate while "
                      "soldering"]],
                    [3.4, 3.6]),
              Spacer(1, 6),
              P("Cut list, per horn", "h2"),
              table([["piece", "name", "qty", "size of the wall", "tabs", "folds"],
                     ["A", "flare panel, top and bottom", "2",
                      f"trapezoid, edges {mm_str(g['a'])} and {mm_str(g['a1'])}, {mm_str(g['h_top'])} high",
                      "none", "none"],
                     ["B", "flare panel, sides", "2",
                      f"trapezoid, edges {mm_str(g['b'])} and {mm_str(g['b1'])}, {mm_str(g['h_side'])} high",
                      "both slanted edges", f"{g['corner_bend']:.0f}°"],
                     ["C", "pipe wall, wide", "2", f"{mm_str(g['wide_w'])} × {mm_str(g['Lg'])}",
                      "both long edges, and the front edge", f"90° sides, {g['lean_top']:.0f}° front"],
                     ["D", "pipe wall, narrow", "2", f"{mm_str(g['b'])} × {mm_str(g['Lg'])}",
                      "front edge", f"{g['lean_side']:.0f}° front"],
                     ["E", "back wall", "1", f"{mm_str(g['back_w'])} × {mm_str(g['back_h'])}",
                      "all four edges, corners notched", "90°"],
                     ["F", "connector and probe", "1", "bought", "", ""]],
                    [0.62, 1.8, 0.45, 2.3, 1.8, 1.3]),
              Spacer(1, 3),
              P(f"Every tab is 6 mm wide. The sheet is 0.53 mm thick, which is why C and E are cut a "
                f"little over the pipe's {mm_str(g['a'])} mm: the wide walls lap over the edges of the "
                f"narrow ones, and the back wall fits over all four. The inside still comes out "
                f"{mm_str(g['a'])} × {mm_str(g['b'])}.", "small"),
              PageBreak()]

    # ── flat patterns
    story += [P("The pieces, flat", "h1"),
              P("Drawn to scale, each as seen from its outside face. Mark and cut exactly these "
                "outlines. Dashed blue lines are where tabs fold."),
              fig_legend(), Spacer(1, 4),
              fig_flat_A(),
              *fig(fig_flat_B(), f"The slanted edges of A and B must both come out {mm_str(g['seam'])} mm, "
                                "because that is where they meet at the corners. If they differ, the "
                                "panels will not close."),
              *fig(fig_flat_pipe(), f"The pipe pieces, back edge at the bottom. Only the top C gets the "
                                   f"feed hole: {mm_str(g['probe_z'])} mm up from the back edge, halfway "
                                   "across. The strips above C and D are the front tabs."),
              PageBreak()]

    # ── sheet layout
    story += [P("Laying out one sheet", "h1"),
              P("Everything for one horn fits on one 12 × 24 in sheet, with a 3 mm cutting gap "
                "between pieces and 4 mm clear of the sheet edge. Turn every second trapezoid round "
                "so the pair nest. Repeat on a second and third sheet for the other two horns."),
              *fig(fig_sheet(), f"One horn's nine pieces on one sheet, to scale. They use "
                               f"{USED_MM2 / (SHEET_W * SHEET_H) * 100:.0f}% of it. Use the spare strip "
                               "along the top to practise a fold and a soldered seam first."),
              callout("How much copper to buy",
                      f"One horn takes about {USED_MM2 / 645.16:.0f} square inches of copper, tabs "
                      "included. With room to cut between pieces, two 12 × 24 in sheets make two horns, "
                      "not three: what is left over is too narrow for a third set of flare panels. "
                      "Three horns need three sheets. A fourth is cheap insurance against a mis-cut."),
              P("Marking out a trapezoid accurately", "h2"),
              P("Do not mark the slanted edges by measuring along them. Mark two parallel lines and a "
                "centre line, then measure out from the centre. Shown for A; B is the same with its "
                "own numbers."),
              fig_marking(),
              PageBreak()]

    # ── build
    story += [P("Building it", "h1"),
              keep(step(1, "Mark, cut and deburr"),
                   numbered([
                       "Mark every piece with a fine marker or a scribed line. Write its letter on "
                       "what will be its outside face.",
                       "Cut with the snips, blade just outside the line. Cut the 45° ends of the B "
                       "tabs and the corner notches of E last.",
                       "File every edge smooth. Burrs stop panels sitting flush, and they cut.",
                       "Flatten any piece the snips curled: lay it flat and press it with a block of "
                       "wood. Check each piece against its size before going on."])),
              keep(step(2, "Drill the feed hole while the top wall is flat"),
                   numbered([
                       f"On the top C, mark a point {mm_str(g['probe_z'])} mm up from the back edge and "
                       f"{mm_str(g['wide_w'] / 2)} mm in from the side, which is halfway across. "
                       "Centre-punch it.",
                       "Drill a small pilot, then open it to clear the connector's white insulator, "
                       "usually 4 to 5 mm. Deburr both sides.",
                       "Hold the flange over the hole, centred and square to the edges, and mark its "
                       "four holes through it. Drill them 2.7 mm."])),
              keep(step(3, "Fold the tabs"),
                   P("Clamp the piece between two straight edges with the fold line exactly at their "
                     "edge, then press the tab over with a block of wood."),
                   fig_folds()),
              callout("Which way each tab folds",
                      "C side tabs, E tabs and B tabs fold away from the outside face, so they wrap "
                      "around the neighbouring wall. C and D front tabs fold toward the outside face, "
                      "flaring out like the rim of a funnel: that rim is the collar the flare sits on."),
              keep(step(4, "Build the pipe"), fig_pipe_end()),
              numbered([
                  f"Stand the two narrow walls (D) on edge, {mm_str(g['a'])} apart inside, and lay the "
                  "bottom C across them, side tabs folded down over their outsides. Clamp.",
                  "Turn the box over and fit the top C, feed hole up, the same way.",
                  f"Measure inside with calipers at both ends: {mm_str(g['a'])} × {mm_str(g['b'])}, "
                  "within half a millimetre, and the two diagonals equal. Adjust before soldering.",
                  "Tack each corner with a spot of solder, check again, then run solder along every "
                  "tab from the outside. Keep the inside clean."]),
              keep(step(5, "Close the back"),
                   numbered([
                       "Slide the back wall (E) over the back of the pipe, tabs forward over the "
                       "outside. The pipe walls butt against its inside face.",
                       "Solder all four tabs. The inside face of E is what the probe is measured "
                       "from, so it must sit flat and square across the whole end."])),
              keep(step(6, "Fit the connector and the probe"),
                   fig(fig_feed(), "Cut through the top wall at the feed hole.")),
              numbered([
                  f"Cut {mm_str(g['rod_cut'])} mm of brass rod and solder one end into the connector's "
                  "cup, straight in line with it. If the rod will not enter the cup, file its end "
                  "down until it does.",
                  "Scrape the copper bright around the hole. Push the rod in through the hole and "
                  "bolt the flange down tight: it must touch metal all round.",
                  f"Trim the rod so {mm_str(g['probe_len'])} mm stands inside, measured from the inside "
                  "face of the wall. It must hang straight down, square to the wall."]),
              callout("The probe is the one part worth tuning",
                      "Its length and its distance from the back wall decide how much of the signal "
                      "gets into the horn instead of bouncing back down the cable. The HFSS simulation "
                      "sweeps both. If it settles on different numbers, use its numbers. To trim the "
                      "rod later, unbolt the connector and lift it out with the rod attached."),
              keep(step(7, "Add the flare"),
                   numbered([
                       f"Set the collar against the cardboard gauges: the two C front tabs lean out "
                       f"{g['lean_top']:.0f}° and the two D front tabs {g['lean_side']:.0f}°.",
                       "Set the top and bottom panels (A) on the C collar tabs, short edge to the "
                       "pipe. Tack each at the middle of its short edge only.",
                       "Set the side panels (B) on the D collar tabs, their slanted tabs over the "
                       "outside of the A panels. Tack each at its short edge.",
                       "Pull the corners together and tack each corner seam at the mouth.",
                       f"Measure the mouth at the rim: {mm_str(g['a1'])} × {mm_str(g['b1'])} inside, and "
                       "the two diagonals equal. Squeeze or spread the corners until it is, then tack "
                       "the middle of each corner seam.",
                       "Run the four corner seams and the collar, all from the outside, working from "
                       "the pipe toward the mouth."])),
              keep(step(8, "Check it"), fig_continuity()),
              P("Then measure everything on the record page. Build all three horns before fitting any: "
                "the two receive horns should come out as close to twins as you can make them."),
              keep(step(9, "Mount it"), fig_mount()),
              PageBreak()]

    # ── record
    rows = [["check", "target", "horn 1", "horn 2", "horn 3"],
            ["mouth width, inside", f"{mm_str(g['a1'])} ± 2", "", "", ""],
            ["mouth height, inside", f"{mm_str(g['b1'])} ± 2", "", "", ""],
            ["mouth diagonals", "equal ± 2", "", "", ""],
            ["flare depth, mouth to pipe", f"{mm_str(g['L'])} ± 1", "", "", ""],
            ["pipe inside, width × height", f"{mm_str(g['a'])} × {mm_str(g['b'])} ± 0.5", "", "", ""],
            ["pipe length, back wall to flare", f"{mm_str(g['Lg'])} ± 2", "", "", ""],
            ["probe centre from back wall", f"{mm_str(g['probe_z'])} ± 0.5", "", "", ""],
            ["probe length inside", f"{mm_str(g['probe_len'])} ± 0.5", "", "", ""],
            ["probe square to the wall", "check with a square", "", "", ""],
            ["every seam, piece to piece", "under 0.5 Ω", "", "", ""],
            ["connector body to copper", "under 0.5 Ω", "", "", ""],
            ["connector centre pin to copper", "open", "", "", ""]]
    rec = table(rows, [2.4, 1.7, 1, 1, 1])
    rec.setStyle(TableStyle([("TOPPADDING", (0, 1), (-1, -1), 4.2), ("BOTTOMPADDING", (0, 1), (-1, -1), 4.2),
                             ("LINEBEFORE", (2, 0), (-1, -1), 0.4, RULE)]))
    trims = Table([[Paragraph(h, S["cellb"]) for h in ("horn", "length inside (mm)", "echo strength",
                                                       "notes")]] + [[""] * 4 for _ in range(4)],
                  colWidths=[BODY_W * f for f in (0.14, 0.24, 0.24, 0.38)],
                  rowHeights=[18] + [19] * 4)
    trims.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), BOX), ("BOX", (0, 0), (-1, -1), 0.5, RULE),
                               ("INNERGRID", (0, 0), (-1, -1), 0.4, FAINT),
                               ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story += [P("Build record", "h1"),
              P("Measure each horn and write the numbers in. This page is the evidence the horns were "
                "built to the design, and it is what the simulation results get compared with."),
              rec,
              Spacer(1, 10),
              P("Tuning, once the radar runs", "h2"),
              P("No test instrument is needed. With the radar running, set it to a single frequency, "
                "put a corner reflector at a fixed distance straight in front, and watch how strong its "
                "echo is. Trim the receive horn's probe half a millimetre at a time and keep the length "
                "that gives the strongest echo. Then trim the spare horn until it reads within 1 dB of "
                "the one you fitted, so the pair match."),
              trims,
              Spacer(1, 10),
              P("What goes wrong", "h2"),
              table([["symptom", "likely cause"],
                     ["the mouth will not close to size", "the slanted edges of A and B differ. Measure "
                      f"both against {mm_str(g['seam'])} mm and trim the long one"],
                     ["a seam reads over 0.5 Ω", "a dry joint, or flux trapped under a tab. Clean it and "
                      "re-flow the solder"],
                     ["connector body open to the copper", "oxide or flux under the flange. Scrape the "
                      "copper bright and bolt it down again"],
                     ["connector centre pin shorted to the copper", "the rod or cup touches the edge of "
                      "the hole. Centre the connector over the hole"],
                     ["a weak echo that trimming will not fix", "a gap somewhere in the metal. Repeat the "
                      "continuity check on every seam"]],
                    [2.3, 4.7])]
    doc.build(story)


if __name__ == "__main__":
    build()
    print(f"wrote {OUT}")
    print(f"flare: top/bottom panel {G['h_top']:.1f} high, side panel {G['h_side']:.1f} high, "
          f"corner seam {G['seam']:.1f}")
    print(f"folds: collar {G['lean_top']:.1f} / {G['lean_side']:.1f} deg, corners {G['corner_bend']:.1f} deg")
    print(f"one horn uses {USED_MM2:.0f} mm^2 = {USED_MM2 / 645.16:.0f} in^2, "
          f"{USED_MM2 / (SHEET_W * SHEET_H) * 100:.0f}% of a 12 x 24 in sheet")
