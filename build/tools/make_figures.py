#!/usr/bin/env python3
"""make_figures.py — the data-driven parts of the two build documents.

Writes LaTeX fragments into ../generated/, which fabrication.tex and
assembly.tex \\input. Nothing in them is typed by hand:

  * every horn size, fold angle and the cutting layout come from
    antenna/tools/make_build_guide.py, which solves them from horn.py and
    refuses to run if the panels would not close or the pieces would not
    fit the sheet;
  * the frame and bench geometry are the 3-D model's own numbers
    (3d/radar-bench.html), copied into FRAME below and checked;
  * the parts list is checked against BOM_Radar_Build.xlsx, so the
    "on your list" column says what is and is not in the order;
  * the breadboard steps are converted from breadboard/assembly/ASSEMBLY.md.

    python3 tools/make_figures.py      # from build/, then: latexmk -lualatex
"""
import math
import pathlib
import re
import shutil
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
BUILD = HERE.parent
ROOT = BUILD.parent
GEN = BUILD / "generated"
sys.path.insert(0, str(ROOT / "antenna" / "tools"))
import make_build_guide as bg  # noqa: E402  (solves and checks the horn)

G = bg.G


def f(v, nd=1):
    """A number for a label: trailing zeros and a bare point dropped."""
    s = f"{v:.{nd}f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


def c(x, y):
    return f"({x:.2f},{y:.2f})"


def write(name, text):
    (GEN / name).write_text(text)


# ───────────────────────────────────────────────────────────── the frame ──
# The bench and frame as the 3-D model builds them (3d/radar-bench.html).
# Board coordinates: x across (right +), z front-to-back (front, the horn
# side, is -z), y up from the plywood's top face. Millimetres.
FRAME = dict(
    board_w=457.0, board_d=381.0, board_t=18.0,       # 18 x 15 in, 3/4 in plywood
    up_x=213.0, up_sq=18.0, frame_z=-45.0,            # uprights, and the frame plane
    rx_y=300.0, tx_y=590.0, baseline=193.1,           # horn centres above the board
    beam_t=12.0, beam_d=32.0,                         # cross-beam section
    brace_foot_x=128.0, brace_top_below_beam=20.0,
    throat_z=-135.0, screen_w=293.1, screen_h=130.0, screen_dz=50.0,
    saddle_base_t=4.0, saddle_cheek_t=4.0, saddle_depth=34.0, saddle_over=32.0,
    saddle_bolt_h=25.0, saddle_bolt_dz=10.0,
)
F = FRAME
F["pipe_half_tall"] = G["a"] / 2            # the horn is rolled: a (86.4) runs up
F["pipe_half_wide"] = G["b"] / 2
F["beam_rx"] = F["rx_y"] - F["pipe_half_tall"] - F["saddle_base_t"] - F["beam_t"] / 2
F["beam_tx"] = F["tx_y"] - F["pipe_half_tall"] - F["saddle_base_t"] - F["beam_t"] / 2
F["beam_rx_top"] = F["beam_rx"] + F["beam_t"] / 2
F["beam_tx_top"] = F["beam_tx"] + F["beam_t"] / 2
# Real joints: the TX beam sits ON the upright tops (one screw down into each),
# the RX beam fits BETWEEN the uprights (one screw in through each upright).
# Beam tops land exactly where the model has them.
F["up_h"] = F["beam_tx_top"] - F["beam_t"]
F["beam_len"] = 2 * F["up_x"] + F["up_sq"]
F["beam_rx_len"] = 2 * F["up_x"] - F["up_sq"]
F["saddle_w"] = 2 * F["pipe_half_wide"] + 13.0
F["saddle_gap"] = 2 * (F["pipe_half_wide"] + 4.5 - F["saddle_cheek_t"] / 2)
F["brace_top"] = F["beam_rx"] - F["brace_top_below_beam"]
F["brace_len"] = math.hypot(F["up_x"] - F["brace_foot_x"], F["brace_top"])
F["brace_angle"] = math.degrees(math.atan2(F["brace_top"], F["up_x"] - F["brace_foot_x"]))
F["pipe_back_z"] = F["throat_z"] + G["Lg"]
F["mouth_z"] = F["throat_z"] - G["L"]
F["saddle_behind_throat"] = F["frame_z"] - F["throat_z"]
F["front_edge_z"] = -F["board_d"] / 2
F["overhang"] = F["front_edge_z"] - F["mouth_z"]
F["feed_z"] = F["throat_z"] + (G["Lg"] - G["probe_z"])

# the model's own checks, restated: mouths clear each other and the uprights
gap_rows = (F["tx_y"] - G["a1"] / 2) - (F["rx_y"] + G["a1"] / 2)
assert gap_rows > 10, "TX and RX mouths overlap"
assert F["baseline"] / 2 + G["b1"] / 2 < F["up_x"] - F["up_sq"] / 2, "RX mouth hits an upright"
assert abs(F["beam_rx_top"] - (F["rx_y"] - G["a"] / 2 - F["saddle_base_t"])) < 1e-6
assert F["saddle_gap"] > G["b"] + 2.5, "saddle too tight for the copper pipe"
F["row_gap"] = gap_rows

# bench layout, board coordinates (x, z, width along x, depth along z, label)
BENCH = [
    ("ADF4351 PLL", -180.0, -150.0, 55, 36, "rf"),
    ("3 dB pad", -101.5, -150.0, 26, 11, "rf"),
    ("PA", -30.5, -150.0, 40, 28, "rf"),
    ("splitter", 43.5, -150.0, 32, 24, "rf"),
    ("band-pass", 180.0, -82.0, 42, 13, "rf"),
    ("LNA", 101.0, -82.0, 40, 28, "rf"),
    ("mixer", 32.0, -82.0, 22, 20, "rf"),
    ("breadboard", 55.0, 75.0, 165, 55, "bb"),
    ("ESP32", 99.0, 152.0, 50, 27, "dig"),
    ("LM2596", 49.0, 152.0, 43, 21, "pwr"),
    ("GND terminal block", -90.0, 152.0, 50, 12, "pwr"),
]


# ───────────────────────────────────────────────────────────── numbers ──
def numbers():
    rows = {
        "aperW": G["a1"], "aperH": G["b1"], "pipeW": G["a"], "pipeH": G["b"],
        "flareL": G["L"], "pipeL": G["Lg"], "probeZ": G["probe_z"], "probeLen": G["probe_len"],
        "rodCut": G["rod_cut"], "seam": G["seam"], "hTop": G["h_top"], "hSide": G["h_side"],
        "wideW": G["wide_w"], "backW": G["back_w"], "backH": G["back_h"], "tabW": G["tab"],
        "gain": G["gain"], "hpE": G["hp_e"], "hpH": G["hp_h"],
        "boardW": F["board_w"], "boardD": F["board_d"], "upH": F["up_h"], "upX": F["up_x"],
        "upCC": 2 * F["up_x"], "beamLen": F["beam_len"], "beamRXlen": F["beam_rx_len"], "beamRXtop": F["beam_rx_top"],
        "beamTXtop": F["beam_tx_top"], "rxY": F["rx_y"], "txY": F["tx_y"], "hornBase": F["baseline"],
        "rowGap": F["row_gap"], "braceLen": F["brace_len"], "saddleW": F["saddle_w"],
        "saddleGap": F["saddle_gap"], "saddleD": F["saddle_depth"], "saddleH": F["saddle_over"],
        "saddleBehind": F["saddle_behind_throat"], "overhang": F["overhang"],
        "screenW": F["screen_w"], "screenH": F["screen_h"], "braceFootX": F["brace_foot_x"],
        "txTop": F["tx_y"] + G["a1"] / 2,
        "frontToFrame": F["frame_z"] - F["front_edge_z"], "beamRXbottom": F["beam_rx_top"] - F["beam_t"],
        "braceTop": F["brace_top"],
    }
    ints = {"leanTop": G["lean_top"], "leanSide": G["lean_side"], "cornerBend": G["corner_bend"],
            "braceAngle": F["brace_angle"], "sheetPct": bg.USED_MM2 / (bg.SHEET_W * bg.SHEET_H) * 100,
            "sheetIn": bg.USED_MM2 / 645.16}
    out = ["% generated by tools/make_figures.py — do not edit"]
    for k, v in rows.items():
        out.append(f"\\newcommand{{\\{k}}}{{{f(v)}}}")
    for k, v in ints.items():
        out.append(f"\\newcommand{{\\{k}}}{{{v:.0f}}}")
    write("numbers.tex", "\n".join(out) + "\n")


# ─────────────────────────────────────────────────────── drawing helpers ──
def poly(pts, style):
    return f"\\path[{style}] " + " -- ".join(c(*p) for p in pts) + " -- cycle;"


def line(p, q, style):
    return f"\\path[{style}] {c(*p)} -- {c(*q)};"


def dim(p, q, off, label, ext=True):
    """An aligned dimension, offset `off` (drawing units) to the left of p->q."""
    ex, ey = q[0] - p[0], q[1] - p[1]
    n = math.hypot(ex, ey)
    nx, ny = -ey / n, ex / n
    p2 = (p[0] + nx * off, p[1] + ny * off)
    q2 = (q[0] + nx * off, q[1] + ny * off)
    s = []
    if ext and abs(off) > 0.5:
        sg = 1 if off > 0 else -1
        s.append(line((p[0] + nx * 1.2 * sg, p[1] + ny * 1.2 * sg),
                      (p2[0] + nx * 2.0 * sg, p2[1] + ny * 2.0 * sg), "ext"))
        s.append(line((q[0] + nx * 1.2 * sg, q[1] + ny * 1.2 * sg),
                      (q2[0] + nx * 2.0 * sg, q2[1] + ny * 2.0 * sg), "ext"))
    s.append(f"\\draw[dim] {c(*p2)} -- {c(*q2)} node[dimlabel]{{{label}}};")
    return "\n".join(s)


def text(p, s, opts="font=\\scriptsize"):
    return f"\\node[{opts}] at {c(*p)} {{{s}}};"


def piece_paths(piece, show_bends=True):
    out = [poly(t, "tab") for t in piece["tabs"]]
    out.append(poly(piece["body"], "wall"))
    if show_bends:
        out += [line(p, q, "fold") for p, q in piece["bends"]]
    if "hole" in piece:
        hx, hy = piece["hole"]
        out.append(f"\\draw[cuedge,fill=white,line width=0.5pt] {c(hx, hy)} circle[radius=2.25];")
        out.append(line((hx - 5, hy), (hx + 5, hy), "draw=ink,line width=0.3pt"))
        out.append(line((hx, hy - 5), (hx, hy + 5), "draw=ink,line width=0.3pt"))
    return out


def pic(body, scale_mm, extra=""):
    return (f"\\begin{{tikzpicture}}[x={scale_mm}mm,y={scale_mm}mm{extra}]\n"
            + "\n".join(body) + "\n\\end{tikzpicture}\n")


# ─────────────────────────────────────────────────── horn: flat patterns ──
def horn_flats():
    a1, a, h = G["a1"], G["a"], G["h_top"]
    b1, b, hb = G["b1"], G["b"], G["h_side"]
    s = 0.5
    A = bg.piece_A()
    body = piece_paths(A)
    body += [line((a1 / 2, -3), (a1 / 2, h + 3), "centre"),
             dim((0, 0), (a1, 0), -9 / s * s * 2, f"{f(a1)} long edge = the mouth"),
             dim(((a1 - a) / 2, h), ((a1 + a) / 2, h), 9 * 2 * s, f"{f(a)} short edge = the pipe end"),
             dim((a1 / 2 + 22, 0), (a1 / 2 + 22, h), 0.01, f(h)),
             line((a1 / 2, h), (a1 / 2 + 25, h), "ext"), line((a1 / 2, 0), (a1 / 2 + 25, 0), "ext"),
             dim((a1, 0), ((a1 + a) / 2, h), -9, f"{f(G['seam'])} check"),
             text((a1 * 0.25, h * 0.38), "A", "partlabel")]
    write("flat_A.tex", pic(body, s))

    B = bg.piece_B()
    body = piece_paths(B)
    body += [line((b1 / 2, -3), (b1 / 2, hb + 3), "centre"),
             dim((0, 0), (b1, 0), -9, f"{f(b1)} long edge = the mouth"),
             dim(((b1 - b) / 2, hb), ((b1 + b) / 2, hb), 9, f(b)),
             dim((b1 / 2 + 18, 0), (b1 / 2 + 18, hb), 0.01, f(hb)),
             line((b1 / 2, hb), (b1 / 2 + 21, hb), "ext"), line((b1 / 2, 0), (b1 / 2 + 21, 0), "ext"),
             dim((0, 0), ((b1 - b) / 2, hb), 16, f"{f(G['seam'])} check"),
             text((b1 * 0.72, hb * 0.3), "B", "partlabel")]
    write("flat_B.tex", pic(body, s))

    out = []
    items = [(bg.piece_C(hole=True), "C", "top wide wall", "cut 1, feed hole", 0, 92),
             (bg.piece_C(), "C", "bottom wide wall", "cut 1", 1, 92),
             (bg.piece_D(), "D", "narrow wall", "cut 2", 2, 92),
             (bg.piece_E(), "E", "back wall", "cut 1", 0, 0)]
    xs = [0.0, 128.0, 256.0]
    for piece, letter, name, qty, col, y in items:
        x0, y0, x1, y1 = bg.outline(piece).bounds
        x = xs[col] + 6
        moved = bg._transform(piece, 0, x - x0, y - y0 + 6)
        out += piece_paths(moved)
        bp = moved["body"]
        bx0, by0 = bp[0]
        bw = bp[1][0] - bp[0][0]
        bh = bp[2][1] - bp[1][1]
        out.append(text((bx0 + bw / 2, by0 + bh * 0.62), letter, "partlabel"))
        out.append(dim((bx0, by0), (bx0 + bw, by0), -10, f(bw)))
        out.append(dim((bx0, by0), (bx0, by0 + bh), 14, f(bh)))
        if "hole" in moved:
            hx, hy = moved["hole"]
            out.append(dim((hx + 10, by0), (hx + 10, hy), 0.01, f(G["probe_z"])))
            out.append(line((hx + 3, hy), (hx + 13, hy), "ext"))
            out.append(text((hx, hy + 8), "feed hole", "font=\\tiny"))
        top = y + (y1 - y0) + 6
        if letter == "E":
            out.append(text((x + (x1 - x0) + 8, by0 + bh / 2 + 4), f"\\textbf{{{name}}}", "font=\\scriptsize,anchor=west"))
            out.append(text((x + (x1 - x0) + 8, by0 + bh / 2 - 4), qty + ", tabs on all four sides", "font=\\tiny,text=muted,anchor=west"))
        else:
            out.append(text((x + (x1 - x0) / 2, top + 13), f"\\textbf{{{name}}}", "font=\\scriptsize"))
            out.append(text((x + (x1 - x0) / 2, top + 6), qty, "font=\\tiny,text=muted"))
    write("flat_pipe.tex", pic(out, 0.5))


# ─────────────────────────────────────────────────── horn: sheet layout ──
def sheet_layout():
    s = 0.27
    W, H = bg.SHEET_W, bg.SHEET_H
    out = [f"\\path[draw=ink,line width=0.6pt,fill=boxbg] (0,0) rectangle {c(W, H)};"]
    for letter, piece in bg.LAYOUT:
        out += piece_paths(piece)
        p = bg.SPoly(piece["body"]).representative_point()
        out.append(text((p.x, p.y), letter, "font=\\bfseries\\small,text=accent"))
    out.append(dim((0, 0), (W, 0), -14, "610 mm (24 in)"))
    out.append(dim((W, 0), (W, H), -14, "305 mm (12 in)"))
    write("sheet_layout.tex", pic(out, s))


# ──────────────────────────────────────────────── horn: 1:1 templates ──
def templates():
    """Half templates for the symmetric flare panels, full ones for the pipe."""
    a1, a, h = G["a1"], G["a"], G["h_top"]
    halfA = [(0, 0), (a1 / 2, 0), (a / 2, h), (0, h)]
    out = [poly(halfA, "wall,fill=cuout!35"),
           line((0, -6), (0, h + 6), "centre,line width=0.6pt"),
           text((-2, h / 2), "CENTRE LINE: flip the template here", "rotate=90,font=\\footnotesize\\bfseries,anchor=south"),
           dim((0, 0), (a1 / 2, 0), -8, f"{f(a1 / 2)} (half of {f(a1)})"),
           dim((0, h), (a / 2, h), 8, f"{f(a / 2)} (half of {f(a)})"),
           dim((a1 / 2 + 10, 0), (a1 / 2 + 10, h), -0.01, f(h)),
           line((a / 2, h), (a1 / 2 + 13, h), "ext"), line((a1 / 2, 0), (a1 / 2 + 13, 0), "ext"),
           dim((a1 / 2, 0), (a / 2, h), -7, f"slant edge {f(G['seam'])}"),
           text((a1 / 4 - 4, h * 0.42), "A", "font=\\Huge\\bfseries,text=accent"),
           text((a1 / 4 - 4, h * 0.42 - 13), "top / bottom flare panel", "font=\\small"),
           text((a1 / 4 - 4, h * 0.42 - 20), "long edge = mouth, short edge = pipe", "font=\\scriptsize,text=muted")]
    write("tmpl_A.tex", pic(out, 1.0))

    b1, b, hb = G["b1"], G["b"], G["h_side"]
    B = bg.piece_B()
    # right half of B: the body from the centre line, and the right-hand slant tab
    halfB = [(b1 / 2, 0), (b1, 0), ((b1 + b) / 2, hb), (b1 / 2, hb)]
    tabR = B["tabs"][0]
    shift = -b1 / 2
    hb_poly = [(x + shift, y) for x, y in halfB]
    tab_poly = [(x + shift, y) for x, y in tabR]
    out = [poly(tab_poly, "tab"), poly(hb_poly, "wall,fill=cuout!35"),
           line(hb_poly[1], hb_poly[2], "fold"),
           line((0, -6), (0, hb + 6), "centre,line width=0.6pt"),
           text((-2, hb / 2), "CENTRE LINE: flip the template here", "rotate=90,font=\\footnotesize\\bfseries,anchor=south"),
           dim((0, 0), (b1 / 2, 0), -8, f"{f(b1 / 2)} (half of {f(b1)})"),
           dim((0, hb), (b / 2, hb), 8, f"{f(b / 2)} (half of {f(b)})"),
           dim((b1 / 2 + 16, 0), (b1 / 2 + 16, hb), -0.01, f(hb)),
           line((b / 2, hb), (b1 / 2 + 19, hb), "ext"), line((b1 / 2 + 7, 0), (b1 / 2 + 19, 0), "ext"),
           text((b1 / 4 - 6, hb * 0.40), "B", "font=\\Huge\\bfseries,text=accent"),
           text((b1 / 4 - 6, hb * 0.40 - 13), "side flare panel", "font=\\small"),
           text((b1 / 4 - 6, hb * 0.40 - 20), f"6 mm tab, fold {G['corner_bend']:.0f}° away from you", "font=\\scriptsize,text=muted")]
    write("tmpl_B.tex", pic(out, 1.0))

    # C and D side by side, E underneath: 157 mm wide, fits a portrait page at 1:1
    out = []
    x = 0.0
    Y = 82.0
    for piece, letter, name in ((bg.piece_C(hole=True), "C", "wide wall: cut 2, feed hole in one only"),
                                (bg.piece_D(), "D", "narrow wall: cut 2")):
        x0, y0, x1, y1 = bg.outline(piece).bounds
        moved = bg._transform(piece, 0, x - x0, Y - y0)
        out += piece_paths(moved)
        bp = moved["body"]
        bw, bh = bp[1][0] - bp[0][0], bp[2][1] - bp[1][1]
        out.append(text((bp[0][0] + bw / 2, bp[0][1] + bh * 0.62), letter, "font=\\Huge\\bfseries,text=accent"))
        out.append(text((x + (x1 - x0) / 2, Y + (y1 - y0) + 6), name, "font=\\scriptsize\\bfseries"))
        out.append(text((bp[0][0] + bw / 2, bp[0][1] + 4), "back edge", "font=\\tiny,text=muted"))
        out.append(text((bp[0][0] + bw / 2, bp[2][1] + 3), "front tab", "font=\\tiny,text=muted"))
        out.append(dim((bp[0][0], bp[0][1]), (bp[1][0], bp[1][1]), -5, f(bw)))
        if "hole" in moved:
            hx, hy = moved["hole"]
            out.append(dim((hx + 8, bp[0][1]), (hx + 8, hy), 0.01, f(G["probe_z"])))
            out.append(line((hx + 3, hy), (hx + 11, hy), "ext"))
            out.append(text((hx, hy + 7), "drill 4.5 (feed)", "font=\\tiny"))
        x += (x1 - x0) + 14
    E = bg.piece_E()
    x0, y0, x1, y1 = bg.outline(E).bounds
    movedE = bg._transform(E, 0, -x0, 8 - y0)
    out += piece_paths(movedE)
    bp = movedE["body"]
    out.append(text(((bp[0][0] + bp[1][0]) / 2, (bp[0][1] + bp[2][1]) / 2), "E", "font=\\Huge\\bfseries,text=accent"))
    out.append(text(((bp[0][0] + bp[1][0]) / 2, 8 + (y1 - y0) + 5), "back wall: cut 1, tabs on all four sides", "font=\\scriptsize\\bfseries"))
    # the print check, beside E
    qx, qy = 118.0, 8.0
    out.append(f"\\draw[line width=0.5pt] {c(qx, qy)} rectangle {c(qx + 50, qy + 50)};")
    out.append(text((qx + 25, qy + 25), "\\textbf{50 mm}\\\\[2pt]measure this square\\\\before cutting", "font=\\footnotesize,align=center"))
    out.append(dim((qx, qy), (qx + 50, qy), -4, "50.0", ext=False))
    write("tmpl_pipe.tex", pic(out, 1.0))


# ─────────────────────────────────────────────────────────── the frame ──
def frame_front():
    """Looking at the mouths from the front. y up from the plywood top."""
    s = 0.21
    o = []
    W = F["board_w"]
    o.append(f"\\path[woodpart] {c(-W / 2, -F['board_t'])} rectangle {c(W / 2, 0)};")
    for sx in (-1, 1):
        x = sx * F["up_x"]
        o.append(f"\\path[woodpart] {c(x - F['up_sq'] / 2, 0)} rectangle {c(x + F['up_sq'] / 2, F['up_h'])};")
        o.append(f"\\path[draw=woodedge,line width=2.2pt,line cap=round] {c(x - sx * F['up_sq'] / 2, F['brace_top'])} -- {c(sx * F['brace_foot_x'], 0)};")
    for yc, L in ((F["beam_rx"], F["beam_rx_len"]), (F["beam_tx"], F["beam_len"])):
        o.append(f"\\path[woodpart] {c(-L / 2, yc - F['beam_t'] / 2)} rectangle {c(L / 2, yc + F['beam_t'] / 2)};")
    # mouths: RX A, empty bay, TX (rolled: b1 across, a1 up)
    bw, bh = G["b1"], G["a1"]
    for (xc, yc, name, live) in ((-F["baseline"] / 2, F["rx_y"], "RX", True),
                                 (F["baseline"] / 2, F["rx_y"], "empty bay", False),
                                 (0.0, F["tx_y"], "TX", True)):
        if live:
            o.append(f"\\path[draw=cuedge,line width=0.7pt,fill=cuin!55] {c(xc - bw / 2, yc - bh / 2)} rectangle {c(xc + bw / 2, yc + bh / 2)};")
            o.append(f"\\path[draw=cuedge,line width=0.5pt,fill=cuin!95!black] {c(xc - G['b'] / 2, yc - G['a'] / 2)} rectangle {c(xc + G['b'] / 2, yc + G['a'] / 2)};")
            for sx, sy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
                o.append(line((xc + sx * G["b"] / 2, yc + sy * G["a"] / 2), (xc + sx * bw / 2, yc + sy * bh / 2), "draw=cuedge,line width=0.4pt"))
            o.append(text((xc, yc + bh / 2 - 14), name, "font=\\bfseries\\small,text=white"))
        else:
            o.append(f"\\path[hidden] {c(xc - bw / 2, yc - bh / 2)} rectangle {c(xc + bw / 2, yc + bh / 2)};")
            o.append(text((xc, yc), "empty bay", "font=\\scriptsize,text=muted,align=center"))
            o.append(text((xc, yc - 14), "(2nd receiver later)", "font=\\tiny,text=muted"))
        o.append(f"\\fill[accent] {c(xc, yc)} circle[radius=4];")
    # dimensions
    o.append(dim((-F["baseline"] / 2, F["rx_y"] - G["a1"] / 2 - 18), (F["baseline"] / 2, F["rx_y"] - G["a1"] / 2 - 18), 0.01, f"{f(F['baseline'])} c-c"))
    o.append(line((-F["baseline"] / 2, F["rx_y"]), (-F["baseline"] / 2, F["rx_y"] - G["a1"] / 2 - 22), "ext,dash pattern=on 1pt off 1pt"))
    o.append(line((F["baseline"] / 2, F["rx_y"]), (F["baseline"] / 2, F["rx_y"] - G["a1"] / 2 - 22), "ext,dash pattern=on 1pt off 1pt"))
    xr = W / 2 + 20
    o.append(dim((xr, 0), (xr, F["rx_y"]), -0.01, f"{f(F['rx_y'])}"))
    o.append(dim((xr + 26, 0), (xr + 26, F["tx_y"]), -0.01, f"{f(F['tx_y'])}"))
    o.append(line((F["baseline"] / 2 + 8, F["rx_y"]), (xr + 4, F["rx_y"]), "ext"))
    o.append(line((8, F["tx_y"]), (xr + 30, F["tx_y"]), "ext"))
    xl = -W / 2 - 22
    o.append(dim((xl, 0), (xl, F["beam_rx_top"]), 0.01, f"{f(F['beam_rx_top'])}"))
    o.append(dim((xl - 26, 0), (xl - 26, F["beam_tx_top"]), 0.01, f"{f(F['beam_tx_top'])}"))
    o.append(line((-F["up_x"] - F["up_sq"] / 2, F["beam_rx_top"]), (xl - 4, F["beam_rx_top"]), "ext"))
    o.append(line((-F["beam_len"] / 2, F["beam_tx_top"]), (xl - 30, F["beam_tx_top"]), "ext"))
    o.append(dim((-F["up_x"], -F["board_t"] - 22), (F["up_x"], -F["board_t"] - 22), 0.01, f"{f(2 * F['up_x'])} upright c-c"))
    o.append(dim((-W / 2, -F["board_t"] - 48), (W / 2, -F["board_t"] - 48), 0.01, f"{f(W)} plywood (18 in)"))
    o.append(text((xr + 13, F["rx_y"] + 18), "RX centre", "font=\\tiny,text=muted,rotate=90"))
    o.append(text((xr + 39, F["tx_y"] + 18), "TX centre", "font=\\tiny,text=muted,rotate=90"))
    o.append(text((xl, F["beam_rx_top"] + 18), "RX beam top", "font=\\tiny,text=muted,rotate=90"))
    o.append(text((xl - 26, F["beam_tx_top"] + 20), "TX beam top", "font=\\tiny,text=muted,rotate=90"))
    write("frame_front.tex", pic(o, s))


def horn_side(o, yc, z_throat, fill="cuin!55"):
    """A rolled horn seen from the side: pipe a tall, flare to a1, mouth toward -z."""
    hp, hm = G["a"] / 2, G["a1"] / 2
    zt, zb, zm = z_throat, z_throat + G["Lg"], z_throat - G["L"]
    o.append(poly([(zm, yc - hm), (zt, yc - hp), (zb, yc - hp), (zb, yc + hp), (zt, yc + hp), (zm, yc + hm)],
                  f"draw=cuedge,line width=0.7pt,fill={fill}"))
    o.append(line((zt, yc - hp), (zt, yc + hp), "draw=cuedge,line width=0.4pt"))
    zf = zt + (G["Lg"] - G["probe_z"])
    o.append(f"\\path[draw=black!70,fill=alu,line width=0.4pt] {c(zf - 6.35, yc - 6.35)} rectangle {c(zf + 6.35, yc + 6.35)};")
    o.append(f"\\fill[black!70] {c(zf, yc)} circle[radius=2.4];")


def frame_side():
    """From the left side: the horns hang forward of the frame, mouths toward -z."""
    s = 0.23
    o = []
    D = F["board_d"]
    o.append(f"\\path[woodpart] {c(-D / 2, -F['board_t'])} rectangle {c(D / 2, 0)};")
    z = F["frame_z"]
    o.append(f"\\path[woodpart] {c(z - F['up_sq'] / 2, 0)} rectangle {c(z + F['up_sq'] / 2, F['up_h'])};")
    for yc in (F["beam_rx"], F["beam_tx"]):
        o.append(f"\\path[woodpart] {c(z - F['beam_d'] / 2, yc - F['beam_t'] / 2)} rectangle {c(z + F['beam_d'] / 2, yc + F['beam_t'] / 2)};")
    for yc in (F["rx_y"], F["tx_y"]):
        base = yc - G["a"] / 2
        o.append(f"\\path[alupart] {c(z - F['saddle_depth'] / 2, base - F['saddle_base_t'])} rectangle {c(z + F['saddle_depth'] / 2, base - F['saddle_base_t'] + F['saddle_over'])};")
        horn_side(o, yc, F["throat_z"])
    # foil screen behind the horns
    zs = z + F["screen_dz"]
    o.append(f"\\path[draw=black!60,fill=alu!60,line width=0.5pt] {c(zs, F['rx_y'] - F['screen_h'] / 2)} rectangle {c(zs + 3, F['rx_y'] + F['screen_h'] / 2)};")
    o.append(text((zs + 14, F["rx_y"] + F["screen_h"] / 2 + 10), "foil screen", "font=\\tiny,text=muted"))
    # labels and dims
    o.append(text((-D / 2 + 30, -F["board_t"] - 10), "front", "font=\\scriptsize\\bfseries"))
    o.append(text((D / 2 - 30, -F["board_t"] - 10), "back", "font=\\scriptsize\\bfseries"))
    yd = F["tx_y"] + G["a1"] / 2 + 24
    o.append(dim((F["mouth_z"], yd), (F["throat_z"], yd), 0.01, f(G["L"])))
    o.append(dim((F["throat_z"], yd), (F["pipe_back_z"], yd), 0.01, f(G["Lg"])))
    for zz in (F["mouth_z"], F["throat_z"], F["pipe_back_z"]):
        o.append(line((zz, F["tx_y"] + 40), (zz, yd + 4), "ext,dash pattern=on 1pt off 1pt"))
    yb = -F["board_t"] - 34
    o.append(dim((F["front_edge_z"], yb), (z, yb), 0.01, f"{f(z - F['front_edge_z'])} to frame"))
    o.append(dim((F["mouth_z"], yb - 26), (F["front_edge_z"], yb - 26), 0.01, f"{f(F['overhang'])}"))
    o.append(line((F["mouth_z"], F["rx_y"] - G["a1"] / 2), (F["mouth_z"], yb - 30), "ext,dash pattern=on 1pt off 1pt"))
    o.append(line((F["front_edge_z"], -F["board_t"]), (F["front_edge_z"], yb - 30), "ext"))
    o.append(line((z, 0), (z, yb - 4), "ext"))
    o.append(dim((z + 30, F["beam_rx_top"]), (z + 30, F["rx_y"]), -0.01, f(G["a"] / 2 + F["saddle_base_t"])))
    o.append(text((F["throat_z"] - 6, F["tx_y"] + G["a1"] / 2 + 6), "throat", "font=\\tiny,text=muted"))
    write("frame_side.tex", pic(o, s))


def board_plan():
    """Top view of the plywood: front (horn side) at the bottom of the page."""
    s = 1 / 3
    o = []
    W, D = F["board_w"], F["board_d"]
    o.append(f"\\path[woodpart,fill=wood!55] {c(-W / 2, -D / 2)} rectangle {c(W / 2, D / 2)};")
    # horn footprints, dashed (they are up in the air)
    for xc, live in ((-F["baseline"] / 2, True), (0.0, True), (F["baseline"] / 2, False)):
        hw, mw = G["b"] / 2, G["b1"] / 2
        pts = [(xc - mw, F["mouth_z"]), (xc - hw, F["throat_z"]), (xc - hw, F["pipe_back_z"]),
               (xc + hw, F["pipe_back_z"]), (xc + hw, F["throat_z"]), (xc + mw, F["mouth_z"])]
        style = "hidden" if live else "hidden,draw=muted!50"
        o.append(f"\\path[{style}] " + " -- ".join(c(*p) for p in pts) + " -- cycle;")
    o.append(text((-F["baseline"] / 2, F["mouth_z"] + 8), "RX horn above", "font=\\tiny,text=muted"))
    o.append(text((0, F["mouth_z"] - 8), "TX horn above", "font=\\tiny,text=muted"))
    # uprights and brace feet
    for sx in (-1, 1):
        x = sx * F["up_x"]
        o.append(f"\\path[woodpart] {c(x - 9, F['frame_z'] - 9)} rectangle {c(x + 9, F['frame_z'] + 9)};")
        o.append(f"\\path[woodpart,fill=wood!80] {c(sx * F['brace_foot_x'] - 6, F['frame_z'] - 6)} rectangle {c(sx * F['brace_foot_x'] + 6, F['frame_z'] + 6)};")
    o.append(f"\\path[draw=woodedge,line width=0.4pt,dash pattern=on 4pt off 2pt] {c(-F['beam_len'] / 2, F['frame_z'])} -- {c(F['beam_len'] / 2, F['frame_z'])};")
    o.append(text((-196, F["frame_z"] - 9), "frame plane (beams above)", "font=\\tiny,text=woodedge,anchor=west"))
    fills = {"rf": "rfmod", "bb": "white", "dig": "pcb", "pwr": "red!12"}
    for name, x, z, w, d, kind in BENCH:
        o.append(f"\\path[module,fill={fills[kind]}] {c(x - w / 2, z - d / 2)} rectangle {c(x + w / 2, z + d / 2)};")
        lab = name if w > 30 else ""
        if lab:
            o.append(text((x, z), lab, "font=\\tiny"))
    for name, x, z, w, d, kind in BENCH:
        if w <= 30:
            o.append(text((x, z - d / 2 - 6), name, "font=\\tiny"))
    # coax runs on the board
    pos = {n: (x, z) for n, x, z, *_ in BENCH}
    runs = [("ADF4351 PLL", "3 dB pad", "R1"), ("3 dB pad", "PA", "R2"), ("PA", "splitter", "R3"),
            ("splitter", "mixer", "R5"), ("band-pass", "LNA", "R7"), ("LNA", "mixer", "R8")]
    box = {n: (x, z, w, d) for n, x, z, w, d, _ in BENCH}

    def edge(nm, toward):
        x, z, w, d = box[nm]
        dx, dz = toward[0] - x, toward[1] - z
        t = min((w / 2) / abs(dx) if dx else 1e9, (d / 2) / abs(dz) if dz else 1e9)
        return (x + dx * t, z + dz * t)
    for a_, b_, lab in runs:
        p1 = edge(a_, pos[b_])
        p2 = edge(b_, pos[a_])
        o.append(f"\\path[draw=black!80,line width=0.9pt,-{{Stealth[length=1.6mm]}}] {c(*p1)} -- {c(*p2)};")
        o.append(text(((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2 + 6), lab, "font=\\tiny\\bfseries,fill=wood!55,inner sep=0.5pt"))
    mx, mz = pos["mixer"]
    o.append(f"\\path[draw=sig,line width=0.9pt,-{{Stealth[length=1.6mm]}}] {c(mx, mz + 10)} -- {c(mx, 47)};")
    o.append(text((mx + 14, 20), "R9 IF", "font=\\tiny\\bfseries,text=sig"))
    # the two horn cables meet the board at the frame centre (the model's collar)
    sx_, sz_ = pos["splitter"]
    o.append(f"\\path[draw=black!80,line width=0.9pt,dash pattern=on 3pt off 1.5pt,-{{Stealth[length=1.6mm]}}] {c(sx_ - 16, sz_ + 4)} -- {c(-12, -112)} -- {c(-12, -20)};")
    o.append(text((-14, -100), "R4 up to TX", "font=\\tiny\\bfseries,anchor=east"))
    bx_, bz_ = pos["band-pass"]
    o.append(f"\\path[draw=black!80,line width=0.9pt,dash pattern=on 3pt off 1.5pt,{{Stealth[length=1.6mm]}}-] {c(bx_, bz_ + 6.5)} -- {c(bx_, -40)} -- {c(8, -40)} -- {c(8, -20)};")
    o.append(text((130, -40), "R6 down from RX", "font=\\tiny\\bfseries,fill=wood!55,inner sep=0.8pt"))
    o.append(f"\\fill[ink] {c(-2, -20)} circle[radius=2.2];")
    o.append(text((-2, -12), "cables up the frame", "font=\\tiny,text=muted,anchor=south"))
    # outline dims
    o.append(dim((-W / 2, D / 2 + 12), (W / 2, D / 2 + 12), 0.01, f"{f(W)} (18 in)"))
    o.append(dim((W / 2 + 14, -D / 2), (W / 2 + 14, D / 2), -0.01, f"{f(D)} (15 in)"))
    o.append(dim((-W / 2 - 14, -D / 2), (-W / 2 - 14, F["frame_z"]), 0.01, f(F["frame_z"] + D / 2)))
    o.append(line((-W / 2, F["frame_z"]), (-W / 2 - 18, F["frame_z"]), "ext"))
    o.append(text((0, -D / 2 - 30), "\\textbf{FRONT}: the horns point this way, into the room", "font=\\scriptsize"))
    o.append(text((0, D / 2 + 24), "\\textbf{BACK}: you sit here", "font=\\scriptsize"))
    # drawn with z up the page, then flipped so the horns are at the top and
    # the operator's side (the back) at the bottom: a true view from above
    write("board_plan.tex", pic(o, s, ",yscale=-1"))


def frame_parts():
    """Cut drawings: upright, beam with saddle positions, brace, saddle."""
    o = []
    # upright, drawn lying down at 1:5
    s = 0.2
    L = F["up_h"]
    o.append(f"\\path[woodpart] (0,0) rectangle {c(L, F['up_sq'])};")
    yc = F["beam_rx"]
    o.append(f"\\path[draw=accent,line width=0.5pt,fill=accent!15] {c(yc - F['beam_t'] / 2, 0)} rectangle {c(yc + F['beam_t'] / 2, F['up_sq'])};")
    o.append(f"\\fill[ink] {c(yc, F['up_sq'] / 2)} circle[radius=1.6];")
    o.append(f"\\fill[ink] {c(L, F['up_sq'] / 2)} circle[radius=1.6];")
    o.append(text((L, F["up_sq"] / 2), "pilot hole in the end", "font=\\tiny,anchor=west,xshift=1.5mm"))
    o.append(f"\\path[draw=accent,line width=0.5pt] {c(F['brace_top'], F['up_sq'] / 2)} circle[radius=3];")
    o.append(dim((0, -12), (L, -12), 0.01, f"{f(L)} upright, 18 mm (3/4 in) square, cut 2"))
    o.append(dim((0, 30), (F["beam_rx"], 30), 0.01, f"{f(F['beam_rx'])} to RX beam centre"))
    o.append(dim((0, 52), (F["beam_rx_top"], 52), 0.01, f"{f(F['beam_rx_top'])} to RX beam top"))
    o.append(dim((0, 74), (F["brace_top"], 74), 0.01, f"{f(F['brace_top'])} brace"))
    o.append(text((0, 9), "foot", "font=\\tiny,anchor=east,xshift=-1mm"))
    write("part_upright.tex", pic(o, s))

    o = []
    s = 0.25
    BL = F["beam_rx_len"]
    o.append(f"\\path[woodpart] {c(-BL / 2, 0)} rectangle {c(BL / 2, F['beam_d'])};")
    for x in (-F["baseline"] / 2, F["baseline"] / 2):
        o.append(f"\\path[alupart,fill=alu!60] {c(x - F['saddle_w'] / 2, (F['beam_d'] - F['saddle_depth']) / 2)} rectangle {c(x + F['saddle_w'] / 2, (F['beam_d'] + F['saddle_depth']) / 2)};")
        for dx in (-18, 18):
            o.append(f"\\fill[accent] {c(x + dx, F['beam_d'] / 2)} circle[radius=2];")
    o.append(dim((-BL / 2, -10), (BL / 2, -10), 0.01, f"{f(BL)} RX beam, 12 × 32 mm, fits between the uprights"))
    o.append(dim((-F["baseline"] / 2, F["beam_d"] + 12), (F["baseline"] / 2, F["beam_d"] + 12), 0.01, f"{f(F['baseline'])} saddle centres"))
    o.append(line((-F["baseline"] / 2, F["beam_d"] / 2), (-F["baseline"] / 2, F["beam_d"] + 16), "ext"))
    o.append(line((F["baseline"] / 2, F["beam_d"] / 2), (F["baseline"] / 2, F["beam_d"] + 16), "ext"))
    o.append(text((0, F["beam_d"] / 2), "seen from above", "font=\\tiny,text=muted"))
    write("part_beam_rx.tex", pic(o, s))

    o = []
    BL = F["beam_len"]
    o.append(f"\\path[woodpart] {c(-BL / 2, 0)} rectangle {c(BL / 2, F['beam_d'])};")
    for x in (-F["up_x"], F["up_x"]):
        for dz in (8, F["beam_d"] - 8):
            o.append(f"\\fill[ink] {c(x, dz)} circle[radius=2.2];")
    o.append(f"\\path[alupart,fill=alu!60] {c(-F['saddle_w'] / 2, (F['beam_d'] - F['saddle_depth']) / 2)} rectangle {c(F['saddle_w'] / 2, (F['beam_d'] + F['saddle_depth']) / 2)};")
    for dx in (-18, 18):
        o.append(f"\\fill[accent] {c(dx, F['beam_d'] / 2)} circle[radius=2];")
    o.append(dim((-BL / 2, -10), (BL / 2, -10), 0.01, f"{f(BL)} TX beam, 12 × 32 mm, sits on the upright tops"))
    o.append(dim((-F["up_x"], -26), (F["up_x"], -26), 0.01, f"{f(2 * F['up_x'])} screws down into the uprights"))
    o.append(line((-F["up_x"], F["beam_d"] / 2), (-F["up_x"], -30), "ext"))
    o.append(line((F["up_x"], F["beam_d"] / 2), (F["up_x"], -30), "ext"))
    write("part_beam_tx.tex", pic(o, s))

    # saddle: front view at 1:1, and the side view
    o = []
    sw, sg, t, ov = F["saddle_w"], F["saddle_gap"], F["saddle_cheek_t"], F["saddle_over"]
    bt = F["saddle_base_t"]
    U = [(-sw / 2, 0), (sw / 2, 0), (sw / 2, ov), (sg / 2, ov), (sg / 2, bt), (-sg / 2, bt), (-sg / 2, ov), (-sw / 2, ov)]
    o.append(poly(U, "alupart"))
    o.append(f"\\path[draw=cuedge,line width=0.6pt,fill=cuout!50,dash pattern=on 2pt off 1pt] {c(-G['b'] / 2 - 0.6, bt)} rectangle {c(G['b'] / 2 + 0.6, ov + 14)};")
    o.append(text((0, ov + 4), "horn pipe", "font=\\tiny"))
    for sx in (-1, 1):
        o.append(f"\\path[draw=ink,line width=0.4pt] {c(sx * sg / 2, F['saddle_bolt_h'])} -- {c(sx * (sw / 2 + 6), F['saddle_bolt_h'])};")
    o.append(dim((-sw / 2, -6), (sw / 2, -6), 0.01, f(sw)))
    o.append(dim((-sg / 2, ov + 20), (sg / 2, ov + 20), 0.01, f"{f(sg)} gap"))
    o.append(dim((sw / 2 + 8, 0), (sw / 2 + 8, ov), -0.01, f(ov)))
    o.append(dim((-sw / 2 - 8, 0), (-sw / 2 - 8, F["saddle_bolt_h"]), 0.01, f(F["saddle_bolt_h"])))
    o.append(text((sw / 2 + 2, F["saddle_bolt_h"] + 4), "M4 clamp screw", "font=\\tiny,anchor=west"))
    write("part_saddle.tex", pic(o, 1.0))


# ──────────────────────────────────────────────────────── the parts list ──
def read_order():
    try:
        from openpyxl import load_workbook
    except ImportError:
        return []
    p = ROOT / "BOM_Radar_Build.xlsx"
    if not p.exists():
        return []
    ws = load_workbook(p, data_only=True).active
    out = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        name, price = row[0], row[1]
        if name and isinstance(name, str) and not re.match(r"^[A-Z]\.\s", name.strip()):
            out.append((name.strip(), price))
    return out


# (section, item, qty, what it is / spec, order keyword or None, note on your order)
PARTS = [
    ("RF chain", "Mixer, double-balanced, SMA", "1",
     "ZX05-43MH-S+, or the generic 1.5–4.5 GHz module. IF must reach DC; LO +13 dBm", "mixer", ""),
    ("RF chain", "ADF4351 PLL board, SPI, SMA out", "1", "the sweep source, 25 MHz TCXO", "adf4351", ""),
    ("RF chain", "SPF5189Z amplifier module", "2", "one is the PA, one the LNA. A 4-pack leaves spares", "spf5189",
     "check you have 2"),
    ("RF chain", "2-way SMA power splitter", "1", "covers 2.4 GHz (e.g. 380–2500 MHz)", "splitter", ""),
    ("RF chain", "SMA attenuator, 3 dB", "1", "DC–6 GHz, between the PLL and the PA", "attenuator", ""),
    ("RF chain", "Band-pass filter, 2.4 GHz, SMA", "1", "2400–2500 MHz, plain SMA (not RP-SMA)", "bpf", ""),
    ("RF chain", "SMA M–M jumper, RG316, 20 cm", "6", "runs R1–R3, R5, R7, R8 on the board", "rg316",
     "check you have 6 short"),
    ("RF chain", "SMA M–M jumper, RG316, about 1 m", "1", "R4: splitter up to the TX horn", None, ""),
    ("RF chain", "SMA M–M jumper, RG316, about 60 cm", "1", "R6: RX horn down to the band-pass", None, ""),
    ("RF chain", "SMA adapter kit (M–M, F–F barrels)", "1", "for whatever genders your modules have", "adapter", ""),
    ("RF chain", "IF pigtail: SMA male to bare leads", "1", "mixer IF to breadboard J1. Or cut a spare jumper in half",
     None, ""),
    ("Horns", "Copper sheet, 24 ga (0.021 in), 12 × 24 in", "3", "one sheet per horn, page \\pageref{sec:sheet}",
     "copper", "check it is 3 sheets"),
    ("Horns", "SMA female 4-hole flange, solder cup", "3", "the horn feeds (plus spares)", "flange", ""),
    ("Horns", "Brass rod, 1/16 in", "100 mm", "three probes, cut 32 mm, trimmed to 28 mm", "brass", ""),
    ("Horns", "Plumbing solder and paste flux", "1", "not rosin-core electronics solder", "solder", ""),
    ("Horns", "Screws and nuts, M2.5 or 2-56, 8 mm", "12", "four per SMA flange. M3 will not fit the flange", None, ""),
    ("Baseband", "ESP32 devkit, 30-pin (WROOM-32)", "1", "runs radar\\_ctl: steps the PLL, drives SYNC", None, ""),
    ("Baseband", "TL072CP op-amp, DIP-8", "2", "the video amplifier and the half-rail reference", None, ""),
    ("Baseband", "830-point breadboard", "1", "", None, ""),
    ("Baseband", "Resistors, capacitors, 1N5822, 3 ferrite beads", "kit", "full pick list on page \\pageref{sec:picklist}",
     "resistor", ""),
    ("Baseband", "0.1 in male header strip, 40-pin", "2", "snapped into the 13 connectors J1–J12, JP3", None, ""),
    ("Baseband", "Solid 22 AWG jumper wire, 9 colours", "48 links", "the colour code on page \\pageref{sec:colours}", None, ""),
    ("Baseband", "USB audio interface, 4-input", "1", "Behringer UMC404HD: beat on INPUT 1, sync on INPUT 2",
     "umc404", ""),
    ("Baseband", "Shielded 1/4 in TS cable, 2 m", "2", "breadboard J2 and J12 to the UMC404HD", None, ""),
    ("Baseband", "USB cables", "2", "ESP32 (micro-USB) and UMC404HD (USB-B) to the laptop", None, ""),
    ("Power", "12 V 3 A supply, barrel plug", "1", "with a barrel jack to screw terminals", None, ""),
    ("Power", "LM2596 buck converter module", "1", "set to 5.00 V before it touches anything", "lm2596", ""),
    ("Power", "Screw terminal block, 6-way", "1", "the star ground", None, ""),
    ("Power", "Hook-up wire, 22 AWG red and black", "2 m each", "5 V leads to the three RF modules", None, ""),
    ("Frame", "Plywood, 18 × 15 in, 3/4 in", "1", "the bench, page \\pageref{sec:plan}", "plywood", ""),
    ("Frame", "18 mm (3/4 in) square wood", f"{2 * F['up_h'] / 1000 + 0.1:.1f} m",
     f"two uprights, {f(F['up_h'])} mm", None, ""),
    ("Frame", "12 × 32 mm (1/2 × 1 1/4 in) wood strip", f"{2 * F['beam_len'] / 1000 + 0.1:.1f} m",
     f"cross beams: one {f(F['beam_len'])} mm, one {f(F['beam_rx_len'])} mm", None, ""),
    ("Frame", "10 mm (3/8 in) dowel", "0.5 m", f"two braces, about {f(F['brace_len'], 0)} mm", None, ""),
    ("Frame", "Horn saddle clamps", "3", "3-D printed (PETG) or bent 3 mm aluminium, page \\pageref{sec:saddle}", None, ""),
    ("Frame", "L-brackets 40 mm, wood screws, M4 screws", "set", "uprights to plywood, beams to uprights, saddles", None, ""),
    ("Frame", "Card and kitchen foil", "1", f"the {f(F['screen_w'])} × {f(F['screen_h'])} mm screen behind the horns", None, ""),
    ("Frame", "Double-sided foam tape or small brackets", "1", "holds the RF modules down", None, ""),
    ("Drone link", "RadioMaster Pocket, EdgeTX", "1", "the drone's 915 MHz radio", "pocket", ""),
    ("Drone link", "RadioMaster Bandit Nano 915 MHz", "1", "in the Pocket's bay", "bandit", ""),
    ("Drone link", "ELRS 915 MHz nano receiver", "1", "BetaFPV ELRS Nano 915 or HappyModel ES900RX", "betafpv", ""),
]


def parts_table():
    order = read_order()

    def on_list(kw):
        if not kw:
            return None
        for name, price in order:
            if kw in name.lower():
                return (name, price)
        return None
    rows = []
    sec = None
    n_missing = 0
    for section, item, qty, spec, kw, note in PARTS:
        if section != sec:
            rows.append(f"\\multicolumn{{4}}{{l}}{{\\rule{{0pt}}{{12pt}}\\textbf{{\\color{{accent}}{section}}}}}\\\\")
            sec = section
        hit = on_list(kw)
        if hit:
            status = "\\textcolor{okgreen}{on your list}"
            if hit[1] in (None, "", "?"):
                status = "\\textcolor{warnamber}{listed, no price}"
        else:
            status = "\\textcolor{warnamber}{\\textbf{not on your list}}"
            n_missing += 1
        if note:
            status += f"\\newline\\textcolor{{warnamber}}{{{note}}}"
        rows.append(f"{item} & {qty} & {spec} & {status}\\\\")
    write("parts_rows.tex", "\n".join(rows) + "\n")
    order_lines = []
    for name, price in order:
        p = "—" if price in (None, "", "?") else (f"\\${price:.2f}" if isinstance(price, (int, float)) else str(price))
        order_lines.append(f"{esc(name)} & {p}\\\\")
    write("order_rows.tex", "\n".join(order_lines) + "\n")
    write("parts_missing.tex", f"\\newcommand{{\\partsMissing}}{{{n_missing}}}\n")


# ──────────────────────────────────────────── breadboard pick list (copy) ──
def pick_list():
    src = (ROOT / "breadboard" / "parts" / "PARTS.md").read_text()
    out = []
    for block in re.split(r"\n## ", src)[1:]:
        title, *rest = block.split("\n", 1)
        if title.startswith(("Jumper", "What not", "Also")):
            continue
        rows = [l for l in rest[0].splitlines() if l.startswith("|") and not l.startswith("|---")]
        if len(rows) < 2:
            continue
        if title.startswith("Headers"):
            continue
        out.append(f"\\multicolumn{{5}}{{l}}{{\\rule{{0pt}}{{11pt}}\\textbf{{\\color{{accent}}{md_inline(title)}}}}}\\\\")
        for r in rows[1:]:
            cells = [md_inline(x.strip()) for x in r.strip("|").split("|")]
            out.append(" & ".join(cells[:5]) + "\\\\")
    write("picklist_rows.tex", "\n".join(out) + "\n")


# ─────────────────────────────────────────────── markdown -> LaTeX bits ──
def esc(s):
    rep = {"\\": "\\textbackslash{}", "&": "\\&", "%": "\\%", "$": "\\$", "#": "\\#", "_": "\\_",
           "{": "\\{", "}": "\\}", "~": "\\textasciitilde{}", "^": "\\textasciicircum{}"}
    return "".join(rep.get(ch, ch) for ch in s)


def md_inline(s):
    s = esc(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", s)
    s = re.sub(r"`(.+?)`", r"\\code{\1}", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    return s


def md_table(lines, widths):
    rows = [l for l in lines if l.startswith("|") and not re.match(r"^\|[-| ]+\|$", l)]
    head = [md_inline(x.strip()) for x in rows[0].strip("|").split("|")]
    body = [[md_inline(x.strip()) for x in r.strip("|").split("|")] for r in rows[1:]]
    spec = "".join(f"P{{{w}\\linewidth}}" for w in widths)
    out = [f"\\begin{{tabular}}{{{spec}}}", "\\toprule",
           " & ".join(f"\\textbf{{{h}}}" for h in head) + "\\\\", "\\midrule"]
    out += [" & ".join(r) + "\\\\" for r in body]
    out += ["\\bottomrule", "\\end{tabular}"]
    return "\n".join(out)


def breadboard_steps():
    src = (ROOT / "breadboard" / "assembly" / "ASSEMBLY.md").read_text()
    src = src.replace("the sound card's right channel", "the sound card's sync input (INPUT 2)")
    src = src.replace("Then work the test cards in hardware/spice/.",
                      "Then work the test blocks in breadboard/multisim/.")
    parts = re.split(r"\n## Step (\d+) — (.+)\n", src)
    out = []
    for i in range(1, len(parts) - 1, 3):
        n, title, body = parts[i], parts[i + 1], parts[i + 2]
        body = body.split("\n---")[0]
        paras, tables, check = [], [], ""
        cur = []
        for l in body.splitlines():
            if l.startswith("!["):
                continue
            if l.startswith("|"):
                cur.append(l)
                continue
            if cur:
                tables.append(cur)
                cur = []
            if l.startswith("> **Check before moving on.**"):
                check = l.replace("> **Check before moving on.**", "").strip()
            elif l.strip():
                paras.append(l.strip())
        if cur:
            tables.append(cur)
        out.append(f"\\bbstep{{{n}}}{{{md_inline(title)}}}")
        out.append(f"\\begin{{center}}\\includegraphics[width=\\linewidth]{{step-{int(n):02d}.png}}\\end{{center}}")
        out.append("\\vspace{-4pt}" + md_inline(" ".join(paras)) + "\\par")
        for t in tables:
            head = t[0].lower()
            if "wire" in head:
                out.append("{\\footnotesize " + md_table(t, [0.06, 0.12, 0.30, 0.42]) + "}\\par")
            else:
                out.append("{\\footnotesize " + md_table(t, [0.12, 0.22, 0.56]) + "}\\par")
        if check:
            out.append(f"\\checkline{{{md_inline(check)}}}")
    write("bb_steps.tex", "\n".join(out) + "\n")


# ──────────────────────────────────────────────── vector figures (SVG) ──
def svg_figures():
    src = ROOT / "breadboard" / "layout" / "breadboard.svg"
    dst = GEN / "breadboard.pdf"
    if shutil.which("rsvg-convert") and src.exists():
        subprocess.run(["rsvg-convert", "-f", "pdf", "-o", str(dst), str(src)], check=True)
    else:
        shutil.copy(ROOT / "breadboard" / "layout" / "breadboard.png", GEN / "breadboard.png")


# ─────────────────────────────────────────── horn: a 3-D view with names ──
def _proj(d=(0.85, 0.5, -0.16)):
    """Orthographic camera looking along -d; returns p -> (screen x, screen y, depth)."""
    n = math.sqrt(sum(v * v for v in d))
    d = [v / n for v in d]
    f = [-v for v in d]
    up = (0.0, 1.0, 0.0)
    r = [f[1] * up[2] - f[2] * up[1], f[2] * up[0] - f[0] * up[2], f[0] * up[1] - f[1] * up[0]]
    rn = math.sqrt(sum(v * v for v in r))
    r = [v / rn for v in r]
    u = [r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0]]

    def P(p):
        return (sum(p[i] * r[i] for i in range(3)), sum(p[i] * u[i] for i in range(3)),
                sum(p[i] * f[i] for i in range(3)))
    return P, d


def horn_iso():
    """The assembled horn from behind and above, every piece named. Back at z=0."""
    a, b, a1, b1, Lg, L = G["a"], G["b"], G["a1"], G["b1"], G["Lg"], G["L"]
    P, d = _proj()
    zt, zm = Lg, Lg + L
    pipe = lambda sx, sy, z: (sx * a / 2, sy * b / 2, z)
    mouth = lambda sx, sy: (sx * a1 / 2, sy * b1 / 2, zm)
    faces = [  # (name, corners, fill)
        ("E", [pipe(-1, -1, 0), pipe(1, -1, 0), pipe(1, 1, 0), pipe(-1, 1, 0)], "cuin"),
        ("Ct", [pipe(-1, 1, 0), pipe(1, 1, 0), pipe(1, 1, zt), pipe(-1, 1, zt)], "cuout"),
        ("Cb", [pipe(-1, -1, 0), pipe(1, -1, 0), pipe(1, -1, zt), pipe(-1, -1, zt)], "cuout"),
        ("Dr", [pipe(1, -1, 0), pipe(1, 1, 0), pipe(1, 1, zt), pipe(1, -1, zt)], "cuin!80"),
        ("Dl", [pipe(-1, -1, 0), pipe(-1, 1, 0), pipe(-1, 1, zt), pipe(-1, -1, zt)], "cuin!80"),
        ("At", [pipe(-1, 1, zt), pipe(1, 1, zt), mouth(1, 1), mouth(-1, 1)], "cuout!90"),
        ("Ab", [pipe(-1, -1, zt), pipe(1, -1, zt), mouth(1, -1), mouth(-1, -1)], "cuout!90"),
        ("Br", [pipe(1, -1, zt), pipe(1, 1, zt), mouth(1, 1), mouth(1, -1)], "cuin!70"),
        ("Bl", [pipe(-1, -1, zt), pipe(-1, 1, zt), mouth(-1, 1), mouth(-1, -1)], "cuin!70"),
    ]
    centre = (0.0, 0.0, Lg)

    def outward(pts):
        (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = pts[0], pts[1], pts[2]
        ux, uy, uz = x1 - x0, y1 - y0, z1 - z0
        vx, vy, vz = x2 - x0, y2 - y0, z2 - z0
        n = [uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx]
        cx = [sum(p[i] for p in pts) / len(pts) for i in range(3)]
        ref = [cx[i] - centre[i] for i in range(3)]
        if sum(n[i] * ref[i] for i in range(3)) < 0:
            n = [-v for v in n]
        return n, cx
    vis = []
    for name, pts, fill in faces:
        n, cx = outward(pts)
        if name == "E":
            n = [0, 0, -1]
        if sum(n[i] * d[i] for i in range(3)) <= 0:
            if name in ("E", "Ct", "Cb", "Dl", "Dr"):
                continue                   # pipe insides: hidden behind the throat
            fill = "cuin!80!black"         # the inside of the flare, if it shows
        vis.append((P(cx)[2], name, pts, fill))
    vis.sort(key=lambda t: -t[0])          # far first
    o = []
    for _, name, pts, fill in vis:
        o.append("\\path[draw=cuedge,line width=0.6pt,line join=round,fill=%s] " % fill
                 + " -- ".join(c(*P(p)[:2]) for p in pts) + " -- cycle;")
    # the collar seam where flare meets pipe
    ring = [pipe(-1, 1, zt), pipe(1, 1, zt), pipe(1, -1, zt)]
    o.append("\\path[draw=cuedge,line width=1.1pt] " + " -- ".join(c(*P(p)[:2]) for p in ring) + ";")
    # the feed on the top wide wall
    fz = Lg - G["probe_z"]
    fx, fy = P((0, b / 2, fz))[:2]
    sq = [(-6.35, b / 2, fz - 6.35), (6.35, b / 2, fz - 6.35), (6.35, b / 2, fz + 6.35), (-6.35, b / 2, fz + 6.35)]
    o.append("\\path[alupart] " + " -- ".join(c(*P(p)[:2]) for p in sq) + " -- cycle;")
    top = P((0, b / 2 + 14, fz))[:2]
    o.append(f"\\path[draw=black!70,line width=2.4pt] {c(fx, fy)} -- {c(*top)};")
    # names
    def call(p3, dx, dy, txt, anchor):
        x, y = P(p3)[:2]
        o.append(f"\\draw[callout] {c(x, y)} -- {c(x + dx, y + dy)} node[anchor={anchor},font=\\scriptsize,align=left,fill=white,fill opacity=0.85,text opacity=1,inner sep=1.5pt] {{{txt}}};")
    call((0, (b + b1) / 4 + 6, zt + L * 0.55), -30, 30, "\\textbf{A} flare panel, top", "south east")
    call((a1 / 2, 0, zm), -12, 0, f"the mouth,\\\\{f(a1)} × {f(b1)}", "east")
    call(((a + a1) / 4, -b1 / 5, zt + L / 2), 30, -45, "\\textbf{B} flare panel, side", "north west")
    call((0, b / 2, zt), -6, 72, "the collar: C and D front tabs,\\\\the flare is soldered onto them", "south")
    call((0, b / 2 + 12, fz), 50, 52, "\\textbf{F} SMA flange,\\\\probe inside", "south west")
    call((-a / 4, b / 2, Lg * 0.18), 62, 22, "\\textbf{C} wide wall, top\\\\(the one with the feed hole)", "west")
    call((0, -b / 4, 0), 40, -16, "\\textbf{E} back wall", "west")
    call((a / 2, -b / 4, Lg * 0.5), 22, -48, "\\textbf{D} narrow wall", "north")
    write("horn_iso.tex", pic(o, 0.36))


def horn_exploded():
    """The same horn pulled apart along each piece's outward direction, in build order."""
    a, b, a1, b1, Lg, L = G["a"], G["b"], G["a1"], G["b1"], G["Lg"], G["L"]
    P, d = _proj()
    zt, zm = Lg, Lg + L
    pipe = lambda sx, sy, z: (sx * a / 2, sy * b / 2, z)
    mouth = lambda sx, sy: (sx * a1 / 2, sy * b1 / 2, zm)
    # (letter, corners, shift vector, fill)
    E_, F_ = 60.0, 70.0
    pieces = [
        ("E", [pipe(-1, -1, 0), pipe(1, -1, 0), pipe(1, 1, 0), pipe(-1, 1, 0)], (0, 0, -E_), "cuin"),
        ("C", [pipe(-1, 1, 0), pipe(1, 1, 0), pipe(1, 1, zt), pipe(-1, 1, zt)], (0, 26, 0), "cuout"),
        ("C", [pipe(-1, -1, 0), pipe(1, -1, 0), pipe(1, -1, zt), pipe(-1, -1, zt)], (0, -26, 0), "cuout"),
        ("D", [pipe(1, -1, 0), pipe(1, 1, 0), pipe(1, 1, zt), pipe(1, -1, zt)], (30, 0, 0), "cuin!80"),
        ("D", [pipe(-1, -1, 0), pipe(-1, 1, 0), pipe(-1, 1, zt), pipe(-1, -1, zt)], (-30, 0, 0), "cuin!80"),
        ("A", [pipe(-1, 1, zt), pipe(1, 1, zt), mouth(1, 1), mouth(-1, 1)], (0, 45, F_), "cuout!90"),
        ("A", [pipe(-1, -1, zt), pipe(1, -1, zt), mouth(1, -1), mouth(-1, -1)], (0, -45, F_), "cuout!90"),
        ("B", [pipe(1, -1, zt), pipe(1, 1, zt), mouth(1, 1), mouth(1, -1)], (45, 0, F_), "cuin!70"),
        ("B", [pipe(-1, -1, zt), pipe(-1, 1, zt), mouth(-1, 1), mouth(-1, -1)], (-45, 0, F_), "cuin!70"),
    ]
    items = []
    for letter, pts, sh, fill in pieces:
        moved = [(x + sh[0], y + sh[1], z + sh[2]) for x, y, z in pts]
        cx = [sum(p[i] for p in moved) / 4 for i in range(3)]
        shown = sum(sh[i] * d[i] for i in range(3)) > 0      # faces this way: labelled
        if letter == "E":
            shown = True
        items.append((P(cx)[2], letter, moved, fill if shown else "cuin!55!black", cx, shown))
    items.sort(key=lambda t: -t[0])
    o = []
    for _, letter, pts, fill, cx, shown in items:
        o.append("\\path[draw=cuedge,line width=0.6pt,line join=round,fill=%s] " % fill
                 + " -- ".join(c(*P(p)[:2]) for p in pts) + " -- cycle;")
        if shown:
            o.append(text(P(cx)[:2], letter, "font=\\bfseries\\large,text=accent,fill=white,fill opacity=0.8,text opacity=1,inner sep=1pt"))
    # assembly arrows: where each piece goes
    def arrow(p, q):
        o.append(f"\\draw[muted,line width=0.5pt,-{{Stealth[length=2mm]}},dash pattern=on 2pt off 1.2pt] {c(*P(p)[:2])} -- {c(*P(q)[:2])};")
    arrow((0, 0, -E_ + 8), (0, 0, -4))
    arrow(((a + a1) / 4 + 45, 0, zt + L / 2 + F_ - 10), ((a + a1) / 4 + 6, 0, zt + L / 2 + 4))
    fz = Lg - G["probe_z"]
    yF = b / 2 + 26 + 30
    sq = [(-6.35, yF, fz - 6.35), (6.35, yF, fz - 6.35), (6.35, yF, fz + 6.35), (-6.35, yF, fz + 6.35)]
    o.append("\\path[alupart] " + " -- ".join(c(*P(p)[:2]) for p in sq) + " -- cycle;")
    o.append(f"\\path[draw=black!70,line width=2.4pt] {c(*P((0, yF, fz))[:2])} -- {c(*P((0, yF + 14, fz))[:2])};")
    arrow((0, yF - 3, fz), (0, b / 2 + 26 + 2, fz))
    o.append(text(P((0, yF + 24, fz))[:2], "F", "font=\\bfseries\\large,text=accent"))
    write("horn_exploded.tex", pic(o, 0.36))


def gauges():
    """Card gauges for the collar, full size: the flare panels' lean from the pipe axis."""
    o = []
    x = 0.0
    for ang, who, panel in ((G["lean_top"], "C front tabs", "A"), (G["lean_side"], "D front tabs", "B")):
        r = 70.0
        t = math.radians(ang)
        o.append(f"\\path[draw=ink,line width=0.6pt,fill=boxbg] {c(x, 0)} -- {c(x + r, 0)} arc[start angle=0,end angle={ang:.2f},radius={r}] -- cycle;")
        o.append(f"\\draw[ink,line width=0.3pt] {c(x + 18, 0)} arc[start angle=0,end angle={ang:.2f},radius=18];")
        o.append(text((x + 26 * math.cos(t / 2), 26 * math.sin(t / 2)), f"\\textbf{{{ang:.0f}°}}", "font=\\small"))
        o.append(text((x + r / 2, -4), "lay this edge along the pipe wall", "font=\\tiny,anchor=north"))
        o.append(text((x + r * 0.5 * math.cos(t) - 4, r * 0.5 * math.sin(t) + 4),
                      f"{who} (panel {panel})", f"font=\\tiny,rotate={ang:.2f},anchor=south"))
        x += 95
    write("gauges.tex", pic(o, 1.0))


def bench_image():
    """The model's bench render, cropped to the 3-D view (no UI chrome)."""
    from PIL import Image
    im = Image.open(ROOT / "3d" / "renders" / "radar-bench" / "bench.png")
    w, h = im.size
    im.crop((0, int(h * 0.105), int(w * 0.785), int(h * 0.885))).save(GEN / "bench_view.png")
    im = Image.open(ROOT / "3d" / "renders" / "radar-bench" / "desk.png")
    w, h = im.size
    im.crop((0, int(h * 0.105), int(w * 0.785), int(h * 0.885))).save(GEN / "desk_view.png")


def main():
    GEN.mkdir(exist_ok=True)
    numbers()
    horn_flats()
    horn_iso()
    horn_exploded()
    gauges()
    bench_image()
    sheet_layout()
    templates()
    frame_front()
    frame_side()
    board_plan()
    frame_parts()
    parts_table()
    pick_list()
    breadboard_steps()
    svg_figures()
    print(f"wrote {len(list(GEN.iterdir()))} files to {GEN}")
    print(f"frame: upright {F['up_h']:.1f}, beams at {F['beam_rx_top']:.1f} / {F['beam_tx_top']:.1f}, "
          f"brace {F['brace_len']:.1f} at {F['brace_angle']:.0f} deg, row gap {F['row_gap']:.1f}, "
          f"saddle gap {F['saddle_gap']:.1f}, overhang {F['overhang']:.1f}")


if __name__ == "__main__":
    main()
