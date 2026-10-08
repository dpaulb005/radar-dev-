#!/usr/bin/env python3
"""make_waterjet.py — cut files for the copper horns on an OMAX abrasive waterjet.

OMAX machines run a tool path (.OMX) that OMAX's own LAYOUT program makes from
a drawing, with the machine's material library, nozzle and abrasive settings.
That last step belongs on the shop's computer. This script makes what goes
into it: clean DXF drawings of the true part shapes, nested on one sheet.

  waterjet/horn_sheet_mm.dxf     one horn's nine pieces on a 12 x 24 in sheet,
                                 millimetres. Cut it three times, one sheet each.
  waterjet/horn_sheet_inch.dxf   the same drawing scaled to inches, for a LAYOUT
                                 set up in inches. Use one or the other.
  waterjet/horn_sheet_ref.dxf    the same with the sheet edge, fold lines and
                                 piece letters on their own layers. Reference
                                 only: never cut from it.
  waterjet/test_coupon_mm.dxf    a 50 mm square with the 4.5 mm feed hole and a
                                 6 mm strip. Cut it first and measure it.
  waterjet/preview.png           what the cut file contains.

Every outline is a single closed polyline on layer CUT, drawn at the TRUE part
size: LAYOUT adds the kerf offset itself, so nothing here is offset. The piece
shapes come from antenna/tools/make_build_guide.py, the same solver the PDFs
use, so the cut parts match the printed templates exactly.

    python3 tools/make_waterjet.py          # from build/
"""
import math
import pathlib
import sys

import logging

import ezdxf
from shapely.geometry import Polygon, box

HERE = pathlib.Path(__file__).resolve().parent
BUILD = HERE.parent
ROOT = BUILD.parent
OUT = BUILD / "waterjet"
sys.path.insert(0, str(ROOT / "antenna" / "tools"))
import make_build_guide as bg  # noqa: E402

logging.getLogger("ezdxf").setLevel(logging.ERROR)   # R12 has no units field; that is expected

SHEET_W, SHEET_H = bg.SHEET_W, bg.SHEET_H     # 609.6 x 304.8, 24 x 12 in
# Spacing. A typical OMAX kerf is 0.75-1.0 mm. 5 mm between parts leaves a 4 mm web
# of copper between neighbouring cuts, stiff enough not to flutter in the jet, and
# 6 mm off the sheet edge. One horn still fits one 12 x 24 in sheet; any wider
# and the second row of pieces runs off the end (nest() checks).
MARGIN = 6.0
GAP = 5.0
HOLE_D = 4.5      # the feed hole, clears the SMA connector's insulator
MM_PER_IN = 25.4


# ───────────────────────────────────────────────────────── nesting ──
def nest():
    """The build guide's arrangement (two trapezoid pairs, the pipe walls beside
    them) re-run with waterjet spacing. Returns [(letter, piece)] and checks it."""
    A, B = bg.piece_A(), bg.piece_B()
    out = bg.outline
    y1 = MARGIN
    a1 = bg._place_at(A, 0, MARGIN, y1)
    a2 = bg._slide_right(A, 180, y1, a1, GAP)
    c1 = bg._place_at(bg.piece_C(hole=True), 90, out(a2).bounds[2] + GAP, y1)
    y2 = max(out(a1).bounds[3], out(c1).bounds[3]) + GAP
    b1 = bg._place_at(B, 0, MARGIN, y2)
    b2 = bg._slide_right(B, 180, y2, b1, GAP)
    c2 = bg._place_at(bg.piece_C(), 0, out(b2).bounds[2] + GAP, y2)
    d1 = bg._place_at(bg.piece_D(), 0, out(c2).bounds[2] + GAP, y2)
    d2 = bg._place_at(bg.piece_D(), 0, out(d1).bounds[2] + GAP, y2)
    e1 = bg._place_at(bg.piece_E(), 90, out(d2).bounds[2] + GAP, y2)
    placed = [("A", a1), ("A", a2), ("C", c1), ("B", b1), ("B", b2),
              ("C", c2), ("D", d1), ("D", d2), ("E", e1)]

    usable = box(MARGIN, MARGIN, SHEET_W - MARGIN, SHEET_H - MARGIN)
    shapes = [out(p) for _, p in placed]
    for i, s in enumerate(shapes):
        assert usable.contains(s), f"piece {placed[i][0]} is inside the {MARGIN} mm edge margin"
        for j in range(i):
            d = s.distance(shapes[j])
            assert d >= GAP - 0.01, f"{placed[j][0]} and {placed[i][0]} only {d:.2f} mm apart"
    return placed


def contour(piece):
    """The piece's outside edge as one closed ring, tabs included, no duplicate points."""
    shp = bg.outline(piece)
    assert shp.geom_type == "Polygon" and not shp.interiors, "a piece outline is not one simple shape"
    shp = shp.simplify(0.001, preserve_topology=True)   # drop collinear points left by the union
    pts = list(shp.exterior.coords)[:-1]
    assert Polygon(pts).is_valid
    return pts


# ─────────────────────────────────────────────────────────── DXF out ──
def new_doc():
    # R12: the oldest, plainest DXF. Every version of OMAX LAYOUT reads it, and
    # it stores outlines as polylines and holes as true circles.
    doc = ezdxf.new("R12", units=0)       # R12 has no units field: the importer asks
    for name, colour in (("CUT", 7), ("SHEET", 8), ("FOLD", 5), ("LABEL", 3)):
        doc.layers.add(name, color=colour)
    return doc


def add_parts(msp, placed, k=1.0):
    n_contours = n_holes = 0
    for letter, piece in placed:
        msp.add_polyline2d([(x * k, y * k) for x, y in contour(piece)], close=True,
                           dxfattribs={"layer": "CUT"})
        n_contours += 1
        if "hole" in piece:
            hx, hy = piece["hole"]
            msp.add_circle((hx * k, hy * k), HOLE_D / 2 * k, dxfattribs={"layer": "CUT"})
            n_holes += 1
    return n_contours, n_holes


def add_reference(msp, placed):
    msp.add_polyline2d([(0, 0), (SHEET_W, 0), (SHEET_W, SHEET_H), (0, SHEET_H)], close=True,
                       dxfattribs={"layer": "SHEET"})
    for letter, piece in placed:
        for p, q in piece["bends"]:
            msp.add_line(p, q, dxfattribs={"layer": "FOLD"})
        c = Polygon(piece["body"]).representative_point()
        msp.add_text(letter, dxfattribs={"layer": "LABEL", "height": 12}).set_placement(
            (c.x, c.y), align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER)
    msp.add_text("REFERENCE ONLY - DO NOT CUT. Sheet 609.6 x 304.8 mm (24 x 12 in), "
                 "24 ga copper. Blue = fold lines.", dxfattribs={"layer": "LABEL", "height": 5}
                 ).set_placement((MARGIN, SHEET_H - 9))


def coupon():
    """50 mm square with the feed hole in the middle, and a 6 mm x 40 mm strip
    (the size of a tab) beside it: checks size, hole and a narrow feature."""
    sq = [(0, 0), (50, 0), (50, 50), (0, 50)]
    strip = [(60, 5), (66, 5), (66, 45), (60, 45)]
    return sq, strip, (25.0, 25.0)


def write_all():
    OUT.mkdir(exist_ok=True)
    placed = nest()

    for name, k in (("horn_sheet_mm.dxf", 1.0), ("horn_sheet_inch.dxf", 1 / MM_PER_IN)):
        doc = new_doc()
        n_c, n_h = add_parts(doc.modelspace(), placed, k)
        doc.saveas(OUT / name)
    assert (n_c, n_h) == (9, 1), (n_c, n_h)

    doc = new_doc()
    add_parts(doc.modelspace(), placed)
    add_reference(doc.modelspace(), placed)
    doc.saveas(OUT / "horn_sheet_ref.dxf")

    doc = new_doc()
    msp = doc.modelspace()
    sq, strip, h = coupon()
    msp.add_polyline2d(sq, close=True, dxfattribs={"layer": "CUT"})
    msp.add_polyline2d(strip, close=True, dxfattribs={"layer": "CUT"})
    msp.add_circle(h, HOLE_D / 2, dxfattribs={"layer": "CUT"})
    doc.saveas(OUT / "test_coupon_mm.dxf")
    return placed


# ───────────────────────────────────────────────── read-back checks ──
def verify(placed):
    """Re-open the cut file and check it is what the build guide says it is."""
    doc = ezdxf.readfile(OUT / "horn_sheet_mm.dxf")
    msp = doc.modelspace()
    polys = [e for e in msp if e.dxftype() == "POLYLINE"]
    circles = [e for e in msp if e.dxftype() == "CIRCLE"]
    assert {e.dxf.layer for e in msp} == {"CUT"}, "cut file holds something other than CUT"
    assert len(polys) == 9 and len(circles) == 1
    for e in polys:
        assert e.is_closed, "an outline is not closed"
    shapes = [Polygon([(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]) for e in polys]
    for s in shapes:
        assert s.is_valid and s.area > 0
    areas = sorted(round(s.area) for s in shapes)
    want = sorted(round(bg.outline(p).area) for _, p in placed)
    assert areas == want, (areas, want)
    # the hole sits inside the top wide wall, the right distance from its back edge
    c = circles[0]
    assert abs(c.dxf.radius - HOLE_D / 2) < 1e-6
    hole_in = [s for s in shapes if s.contains(Polygon.from_bounds(*(
        c.dxf.center[0] - 2.25, c.dxf.center[1] - 2.25, c.dxf.center[0] + 2.25, c.dxf.center[1] + 2.25)))]
    assert len(hole_in) == 1, "feed hole is not inside exactly one piece"
    # the slanted edges of A and B both come out to the seam length
    for letter, piece in placed:
        if letter in "AB":
            (x0, y0), (x1, y1) = piece["body"][1], piece["body"][2]
            assert abs(math.hypot(x1 - x0, y1 - y0) - bg.G["seam"]) < 0.05
    inch = ezdxf.readfile(OUT / "horn_sheet_inch.dxf")
    ip = [e for e in inch.modelspace() if e.dxftype() == "POLYLINE"]
    ia = sorted(round(Polygon([(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]).area * MM_PER_IN ** 2) for e in ip)
    assert ia == areas, "inch file is not the same drawing"
    return shapes, circles[0]


def preview(placed, shapes, hole):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(12, 6.6), dpi=130)
    ax.add_patch(plt.Rectangle((0, 0), SHEET_W, SHEET_H, fc="#F3D2BC", ec="#6B3A1F", lw=1))
    ax.add_patch(plt.Rectangle((MARGIN, MARGIN), SHEET_W - 2 * MARGIN, SHEET_H - 2 * MARGIN,
                               fc="none", ec="#8A3B1E", lw=0.6, ls=(0, (4, 3))))
    for (letter, piece), s in zip(placed, shapes):
        x, y = s.exterior.xy
        ax.fill(x, y, fc="#E2A27A", ec="#14181D", lw=1.1)
        for p, q in piece["bends"]:
            ax.plot([p[0], q[0]], [p[1], q[1]], color="#1F5F8B", lw=0.7, ls=(0, (3, 2)))
        c = Polygon(piece["body"]).representative_point()
        ax.text(c.x, c.y, letter, ha="center", va="center", fontsize=15, weight="bold", color="#8A3B1E")
    ax.add_patch(plt.Circle((hole.dxf.center.x, hole.dxf.center.y), HOLE_D / 2, fc="white", ec="#14181D", lw=1))
    ax.set_xlim(-10, SHEET_W + 10)
    ax.set_ylim(-14, SHEET_H + 10)
    ax.set_aspect("equal")
    ax.set_xticks(range(0, 601, 100))
    ax.set_yticks(range(0, 301, 100))
    ax.tick_params(labelsize=8)
    ax.set_title(f"horn_sheet_mm.dxf: 9 outlines + 1 hole on layer CUT, true size. "
                 f"{GAP:.0f} mm between parts, {MARGIN:.0f} mm edge margin (dashed). "
                 "Blue fold lines are NOT in the cut file.", fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "preview.png")


def main():
    placed = write_all()
    shapes, hole = verify(placed)
    preview(placed, shapes, hole)
    total = sum(s.length for s in shapes) + math.pi * HOLE_D
    print(f"wrote {OUT}: 9 outlines + 1 hole, {total / 1000:.2f} m of cut per sheet, "
          f"pieces fill {sum(s.area for s in shapes) / (SHEET_W * SHEET_H) * 100:.0f}% of the sheet")


if __name__ == "__main__":
    main()
