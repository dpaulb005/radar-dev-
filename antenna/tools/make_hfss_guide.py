#!/usr/bin/env python3
"""make_hfss_guide.py — "Designing the horn in Ansys HFSS", as a printable PDF.

A beginner's route through antenna design in HFSS, built around this project's
horn and nothing else. Every dimension comes from horn.py, and the model it
describes is the horn the build guide makes: connector on the top wide wall,
probe hanging 28 mm into the pipe, 43.7 mm in front of the back wall.

The "what a good result looks like" figures are not simulation output. The
radiation patterns are computed here by integrating the horn's aperture field
(the textbook method, independent of HFSS), and the S11 curves are labelled as
an illustration of shape. Nothing in the guide is presented as a result that
was not actually computed.

    python3 make_hfss_guide.py        # writes ../hfss-design-guide.pdf

Needs numpy, reportlab and shapely. Shares its drawing code with
make_build_guide.py so the two documents look like one set.
"""
import math

import numpy as np
from reportlab.graphics.shapes import Circle, Drawing, Line, PolyLine, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether, PageBreak, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle)

import make_build_guide as bg
from make_build_guide import (ACC, BEND, BODY_W, BOX, BRASS, CU_EDGE, CU_IN, CU_OUT, DIM, FAINT,
                              INK, M, MUT, PAGE_H, PAGE_W, RULE, STEEL, S, Cam, G, P, Sheet,
                              bullets, callout, callouts, mm_str, mouth_rim, numbered,
                              render_horn, table, text_block)

OUT = bg.HERE.parent / "hfss-design-guide.pdf"
C0 = 299_792_458.0
AIR = colors.HexColor("#2b6cb0")


def neg(v, nd=0):
    """A number with a real minus sign."""
    return f"{v:.{nd}f}".replace("-", "−")


def keep(*items):
    """Keep items on one page. Nested KeepTogethers are unwrapped: reportlab
    pushes a nested one to the next page even when it would fit."""
    flat = []
    for it in items:
        for sub in (it if isinstance(it, list) else [it]):
            flat.extend(sub._content if isinstance(sub, KeepTogether) else [sub])
    return KeepTogether(flat)


def step(n, title):
    t = Table([[Paragraph(str(n), S["stepn"]), Paragraph(title, S["steph"])]],
              colWidths=[30, BODY_W - 30])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), ACC),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                           ("LEFTPADDING", (0, 0), (0, 0), 2), ("RIGHTPADDING", (0, 0), (0, 0), 2),
                           ("LEFTPADDING", (1, 0), (1, 0), 8),
                           ("LINEBELOW", (1, 0), (1, 0), 0.7, RULE)]))
    return t
PORT = colors.HexColor("#c0392b")

# ─────────────────────────────────────────────────────── the extra numbers ──


def extras():
    H = bg.load_horn()
    f = 2.45e9
    lam = C0 / f
    a, b = H.WAVEGUIDES["WR-340"]
    a1, b1, rho1, rho2 = H.solve_optimum(lam, a, b, 13.4, 0.51)
    x = dict(lam=lam * 1e3, fc=C0 / (2 * a) / 1e9, fc2=C0 / a / 1e9,
             lam_g=lam / math.sqrt(1 - (lam / (2 * a)) ** 2) * 1e3,
             bound=10 * math.log10(4 * math.pi * a1 * b1 / lam ** 2),
             rho1=rho1 * 1e3, rho2=rho2 * 1e3)
    x["quarter"] = x["lam"] / 4
    x["quarter_low"] = C0 / 2.2e9 / 4 * 1e3
    x["clear"] = 40.0
    # coax stub: the SMA's own pin, and the PTFE diameter that makes it 50 ohm
    x["d_pin"] = 1.27
    x["d_rod"] = 25.4 / 16
    x["d_diel"] = x["d_pin"] * 10 ** (50 * math.sqrt(2.1) / 138)
    x["stub"] = 10.0
    # probe clearance at the longest probe the sweep tries
    x["plen_max"] = 34.0
    x["tip_gap"] = G["b"] - x["plen_max"]
    assert x["tip_gap"] > 5, "the longest probe in the sweep would touch the far wall"
    assert x["clear"] > x["quarter_low"], "air box closer than a quarter wave at 2.2 GHz"

    # the patterns aperture theory predicts: cosine across a1, uniform across b1,
    # each with the flare's quadratic phase error, times the (1 + cos) element factor
    k = 2 * np.pi / lam
    xs = np.linspace(-a1 / 2, a1 / 2, 2001)
    ys = np.linspace(-b1 / 2, b1 / 2, 2001)
    Ex = np.cos(np.pi * xs / a1) * np.exp(-1j * k * xs ** 2 / (2 * rho2))
    Ey = np.exp(-1j * k * ys ** 2 / (2 * rho1))
    th = np.radians(np.linspace(-90, 90, 1801))

    def pattern(u, E):
        F = np.array([np.trapezoid(E * np.exp(1j * k * u * np.sin(t)), u) for t in th])
        F = np.abs(F) * (1 + np.cos(th)) / 2
        return 20 * np.log10(F / F.max())

    x["theta"] = np.degrees(th)
    x["pat_e"] = pattern(ys, Ey)
    x["pat_h"] = pattern(xs, Ex)

    def hpbw(p):
        i = np.where(p >= -3.0)[0]
        return x["theta"][i[-1]] - x["theta"][i[0]]
    x["hp_e"], x["hp_h"] = hpbw(x["pat_e"]), hpbw(x["pat_h"])
    sel = (x["theta"] >= 38) & (x["theta"] <= 55)
    x["shoulder"] = float(x["pat_e"][sel].mean())
    # aperture efficiency and directivity by integrating the same field
    X, Y = np.meshgrid(xs, ys)
    Eap = np.cos(np.pi * X / a1) * np.exp(-1j * k * (X ** 2 / (2 * rho2) + Y ** 2 / (2 * rho1)))
    num = abs(np.trapezoid(np.trapezoid(Eap, xs, axis=1), ys)) ** 2
    den = a1 * b1 * np.trapezoid(np.trapezoid(abs(Eap) ** 2, xs, axis=1), ys)
    x["eff"] = num / den
    x["dir"] = 10 * math.log10(4 * math.pi * a1 * b1 / lam ** 2 * x["eff"])
    assert abs(x["dir"] - G["gain"]) < 0.3, "aperture integration disagrees with horn.py"
    return x


X = extras()

# ──────────────────────────────────────────────────────────────── figures ──


def air_box():
    A2, B2, L, Lg = G["a1"] / 2, G["b1"] / 2, G["L"], G["Lg"]
    c = X["clear"]
    return (-A2 - c, A2 + c), (-B2 - c, B2 + c), (-Lg - c, L + c)


def draw_box_wire(d, cam, color=AIR, width=0.7, dash=(3, 2)):
    (x0, x1), (y0, y1), (z0, z1) = air_box()
    corners = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    for i, p in enumerate(corners):
        for q in corners[i + 1:]:
            if sum(1 for u, v in zip(p, q) if u != v) == 1:
                d.add(Line(*cam.proj(p), *cam.proj(q), strokeColor=color, strokeWidth=width,
                           strokeDashArray=list(dash)))


def fig_model_3d(H=300, scale=0.62, with_labels=True):
    W = BODY_W
    d = Drawing(W, H)
    cam = Cam(bg.AZ, bg.EL, scale, W / 2 + 6, H / 2 + 8)
    draw_box_wire(d, cam)
    render_horn(d, cam)
    mouth_rim(d, cam, width=1.3)
    b2, Lg, L = G["b"] / 2, G["Lg"], G["L"]
    zp = -Lg + G["probe_z"]
    px, py = cam.proj((0, b2 + 13, zp))
    d.add(Circle(px, py, 3.2, fillColor=PORT, strokeColor=colors.white, strokeWidth=0.6))
    # axes, drawn from the back bottom corner of the air box
    (x0, x1), (y0, y1), (z0, z1) = air_box()
    o = (x1, y0, z0)
    for vec, name in (((50, 0, 0), "x"), ((0, 50, 0), "y"), ((0, 0, 50), "z")):
        p = tuple(o[i] + vec[i] for i in range(3))
        (ax, ay), (bx, by) = cam.proj(o), cam.proj(p)
        d.add(Line(ax, ay, bx, by, strokeColor=INK, strokeWidth=0.9))
        d.add(String(bx + 3, by - 2, name, fontName="DJ-B", fontSize=8, fillColor=INK))
    if with_labels:
        B2 = G["b1"] / 2
        pr = cam.proj
        callouts(d, W, [
            (pr((-20, (b2 + B2) / 2, L * 0.5)), "L", H - 26, "copper walls",
             "drawn as thin sheets, set to Perfect E"),
            (pr((10, -(b2 + B2) / 2 - 6, L * 0.62)), "L", 80, "the mouth",
             "open to the air box. No boundary on it"),
            ((px, py), "R", H - 22, "the feed",
             "a short coax stub. The wave port\nsits on its end, under a metal cap"),
            (pr((x0, y1, z1)), "L", H - 80, "air box",
             f"{mm_str(X['clear'])} mm clear of the horn all round"),
            (pr((x1, (y0 + y1) / 2, (z0 + z1) / 2)), "R", 150, "radiation boundary",
             "on all six faces of the air box:\nwhere modelled space ends"),
            (pr((0, 0, 0)), "R", 70, "origin",
             "z = 0 at the throat, where the\nflare meets the pipe. +z out of the mouth"),
        ])
    return d


def fig_band():
    """Where the radar's band sits against what the pipe can carry."""
    W, H = BODY_W, 96
    d = Drawing(W, H)
    f0, f1 = 1.0, 4.0
    x0, x1 = 30, W - 30

    def X_(f):
        return x0 + (f - f0) / (f1 - f0) * (x1 - x0)
    y = 46
    d.add(Rect(x0, y - 6, X_(X["fc"]) - x0, 12, fillColor=colors.HexColor("#e9e4dc"), strokeColor=None))
    d.add(Rect(X_(X["fc"]), y - 6, X_(X["fc2"]) - X_(X["fc"]), 12, fillColor=colors.HexColor("#dcebd9"),
               strokeColor=None))
    d.add(Rect(X_(X["fc2"]), y - 6, x1 - X_(X["fc2"]), 12, fillColor=colors.HexColor("#f3dcd6"),
               strokeColor=None))
    d.add(Line(x0, y, x1, y, strokeColor=INK, strokeWidth=0.8))
    for f in (1, 1.5, 2, 2.5, 3, 3.5, 4):
        d.add(Line(X_(f), y - 8, X_(f), y - 6, strokeColor=INK, strokeWidth=0.6))
        d.add(String(X_(f), y - 18, f"{f:g} GHz", fontName="DJ", fontSize=7, fillColor=MUT,
                     textAnchor="middle"))
    d.add(Rect(X_(2.4), y - 9, X_(2.4835) - X_(2.4), 18, fillColor=ACC, strokeColor=None))
    d.add(Line(X_(2.2), y + 14, X_(2.7), y + 14, strokeColor=BEND, strokeWidth=0.8))
    for f in (2.2, 2.7):
        d.add(Line(X_(f), y + 11, X_(f), y + 17, strokeColor=BEND, strokeWidth=0.8))
    d.add(String(X_(2.45), y + 20, "simulate 2.2 to 2.7 GHz", fontName="DJ", fontSize=7.2,
                 fillColor=BEND, textAnchor="middle"))
    d.add(String(X_(2.44), y - 30, "radar 2.400–2.4835", fontName="DJ-B", fontSize=7.4, fillColor=ACC,
                 textAnchor="middle"))
    d.add(String((x0 + X_(X["fc"])) / 2, y + 20, "too low: the pipe", fontName="DJ", fontSize=7.2,
                 fillColor=MUT, textAnchor="middle"))
    d.add(String((x0 + X_(X["fc"])) / 2, y + 11, "carries nothing", fontName="DJ", fontSize=7.2,
                 fillColor=MUT, textAnchor="middle"))
    d.add(String((X_(X["fc2"]) + x1) / 2, y + 20, "too high: a second wave", fontName="DJ", fontSize=7.2,
                 fillColor=MUT, textAnchor="middle"))
    d.add(String((X_(X["fc2"]) + x1) / 2, y + 11, "pattern fits and it gets messy", fontName="DJ",
                 fontSize=7.2, fillColor=MUT, textAnchor="middle"))
    for f, t in ((X["fc"], f"{X['fc']:.3f}"), (X["fc2"], f"{X['fc2']:.2f}")):
        d.add(Line(X_(f), y - 10, X_(f), y + 8, strokeColor=INK, strokeWidth=0.9))
        d.add(String(X_(f), H - 8, t + " GHz", fontName="DJ-B", fontSize=7.4, fillColor=INK,
                     textAnchor="middle"))
    return d


def fig_s11_power():
    """S11 in plain terms: how much of the power comes back."""
    W, H = BODY_W, 104
    d = Drawing(W, H)
    x0, w, y = 14, 250, 60
    d.add(Rect(x0, y, w, 16, fillColor=ACC, strokeColor=None))
    d.add(String(x0 + w / 2, y + 4.5, "100% sent up the cable", fontName="DJ-B", fontSize=8,
                 fillColor=colors.white, textAnchor="middle"))
    d.add(Rect(x0, y - 30, w * 0.9, 16, fillColor=CU_OUT, strokeColor=None))
    d.add(String(x0 + w * 0.45, y - 25.5, "90% goes into the horn and out as the beam", fontName="DJ",
                 fontSize=7.6, fillColor=INK, textAnchor="middle"))
    d.add(Rect(x0 + w * 0.9, y - 30, w * 0.1, 16, fillColor=colors.HexColor("#7a8794"), strokeColor=None))
    d.add(String(x0 + w * 0.95, y - 46, "10% comes back", fontName="DJ", fontSize=7.4,
                 fillColor=MUT, textAnchor="middle"))
    d.add(String(x0, y + 24, "S11 = −10 dB means:", fontName="DJ-B", fontSize=8.4, fillColor=INK))
    rows = [("S11", "power reflected", "power into the horn"),
            ("−3 dB", "50 %", "50 %  (bad)"), ("−6 dB", "25 %", "75 %"),
            ("−10 dB", "10 %", "90 %  (the target)"), ("−15 dB", "3 %", "97 %"), ("−20 dB", "1 %", "99 %")]
    tx = 300
    for i, (a, b_, c_) in enumerate(rows):
        yy = H - 14 - i * 14
        f = "DJ-B" if i == 0 or "target" in c_ else "DJ"
        d.add(String(tx, yy, a, fontName=f, fontSize=8, fillColor=INK))
        d.add(String(tx + 52, yy, b_, fontName=f, fontSize=8, fillColor=INK))
        d.add(String(tx + 142, yy, c_, fontName=f, fontSize=8, fillColor=INK))
    return d


def fig_planes():
    """Looking into the mouth: the field direction and the two pattern cuts."""
    W, H = BODY_W, 165
    d = Drawing(W, H)
    sc = 0.5
    sh = Sheet(W, H, sc, 130, H / 2 + 2)
    sh.d = d
    A2, B2, a2, b2 = G["a1"] / 2, G["b1"] / 2, G["a"] / 2, G["b"] / 2
    sh.poly([(-A2, -B2), (A2, -B2), (A2, B2), (-A2, B2)], fill=CU_IN, stroke=CU_EDGE, width=0.9)
    for sx, sy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
        sh.line((sx * a2, sy * b2), (sx * A2, sy * B2), CU_EDGE, 0.5)
    sh.poly([(-a2, -b2), (a2, -b2), (a2, b2), (-a2, b2)], fill=colors.HexColor("#5a3420"),
            stroke=CU_EDGE, width=0.6)
    for xx in (-90, -45, 0, 45, 90):
        amp = math.cos(math.pi * xx / G["a1"])
        hh = 60 * amp
        sh.line((xx, -hh), (xx, hh), colors.white, 1.3)
        sh.arrow_head((xx, hh), (xx, hh - 5), size=4.5, color=colors.white)
    sh.line((-A2 - 22, 0), (A2 + 22, 0), BEND, 1.2, dash=[6, 3])
    sh.line((0, -B2 - 18), (0, B2 + 18), ACC, 1.2, dash=[6, 3])
    sh.text((A2 + 26, -3), "H-plane cut, φ = 0°", 7.6, BEND, "start", bold=True)
    sh.text((6, B2 + 12), "E-plane cut, φ = 90°", 7.6, ACC, "start", bold=True)
    sh.text((-A2, -B2 - 14), "x →", 7.4, MUT, "start")
    sh.text((-A2 - 8, -B2), "y ↑", 7.4, MUT, "end")
    text_block(d, 330, H - 20, [
        "**Looking into the mouth**", "",
        "White arrows: the electric field. It points",
        "across the narrow side (along y), strongest",
        "in the middle and fading to nothing at the",
        "side walls.", "",
        "The E-plane is the slice that contains",
        "those arrows. The H-plane is the slice at",
        "right angles to it."], size=8, lead=11.4)
    return d


def fig_var_section():
    """Side view cut down the middle, with the HFSS variable on every size."""
    W, H = BODY_W, 300
    d = Drawing(W, H)
    sc = 1.15
    Lg, L = G["Lg"], G["L"]
    hin, hout = G["b"] / 2, G["b1"] / 2
    ox, oy = 44 + Lg * sc, H / 2 - 2
    sh = Sheet(W, H, sc, ox, oy)
    sh.d = d
    sh.poly([(-Lg, -hin), (0, -hin), (L, -hout), (L, hout), (0, hin), (-Lg, hin)],
            fill=colors.HexColor("#eef3f8"), stroke=None)
    for s in (1, -1):
        sh.line((-Lg, s * hin), (0, s * hin), CU_EDGE, 2.4)
        sh.line((0, s * hin), (L, s * hout), CU_EDGE, 2.4)
    sh.line((-Lg, -hin), (-Lg, hin), CU_EDGE, 2.4)
    sh.line((-Lg - 6, 0), (L + 8, 0), MUT, 0.4, dash=[5, 2, 1, 2])
    zp = -Lg + G["probe_z"]
    # coax stub, cap and probe
    rd = X["d_diel"] / 2
    sh.poly([(zp - rd, hin), (zp + rd, hin), (zp + rd, hin + X["stub"]), (zp - rd, hin + X["stub"])],
            fill=colors.white, stroke=INK, width=0.5)
    sh.poly([(zp - rd, hin + X["stub"]), (zp + rd, hin + X["stub"]), (zp + rd, hin + X["stub"] + 1.2),
             (zp - rd, hin + X["stub"] + 1.2)], fill=STEEL, stroke=INK, width=0.4)
    sh.line((zp - rd, hin + X["stub"]), (zp + rd, hin + X["stub"]), PORT, 1.6)
    sh.line((zp, hin + X["stub"]), (zp, hin - G["probe_len"]), BRASS, 2.0)
    # variables
    yb = -hout - 14
    for zz, hh in ((-Lg, hin), (0, hin), (L, hout)):
        sh.line((zz, -hh - 2), (zz, yb - 3), DIM, 0.35)
    sh.dim((-Lg, yb), (0, yb), 0, f"Lg = {mm_str(Lg)}", ext=False)
    sh.dim((0, yb), (L, yb), 0, f"pe = {mm_str(L)}", ext=False)
    xl = -Lg - 12
    sh.line((-Lg - 2, hin), (xl - 3, hin), DIM, 0.35)
    sh.line((-Lg - 2, -hin), (xl - 3, -hin), DIM, 0.35)
    sh.dim((xl, -hin), (xl, hin), 0, f"b = {mm_str(G['b'])}", ext=False, text_off=3, size=6.8)
    sh.dim((L + 10, -hout), (L + 10, hout), 0, f"b1 = {mm_str(G['b1'])}", ext=False, text_off=-9)
    yd = hin + 26
    sh.line((-Lg, hin + 2), (-Lg, yd + 3), DIM, 0.35)
    sh.line((zp, hin + 13), (zp, yd + 3), DIM, 0.35)
    sh.dim((-Lg, yd), (zp, yd), 0, f"bshort = {mm_str(G['probe_z'])}", ext=False)
    sh.dim((zp + 10, hin), (zp + 10, hin - G["probe_len"]), 0.001, f"plen = {mm_str(G['probe_len'])}",
           ext=False, size=6.6, text_off=-14)
    sh.line((zp + 1.5, hin - G["probe_len"]), (zp + 13, hin - G["probe_len"]), DIM, 0.35)
    sh.text((0, -3.5 - 8), "z = 0", 7, ACC, "middle", bold=True)
    sh.line((0, -6), (0, 6), ACC, 1.0)
    text_block(d, ox + (L + 34) * sc, H - 22, [
        "**Side view, cut down the middle**",
        "(the y–z plane: the E-plane)", "",
        "The top view is the same shape with",
        f"a = {mm_str(G['a'])} at the pipe and",
        f"a1 = {mm_str(G['a1'])} at the mouth.", "",
        "Red line: the wave port, where the",
        "signal enters, under a metal cap.",
        "Brass: the probe, on the centre line."], size=8, lead=11.4)
    return d


def fig_feed_detail():
    W, H = BODY_W, 190
    d = Drawing(W, H)
    sc = 4.0
    sh = Sheet(W, H, sc, 150, 104)
    sh.d = d
    t = 1.0
    rd, rp, rr = X["d_diel"] / 2, X["d_pin"] / 2, X["d_rod"] / 2
    stub = X["stub"]
    sh.poly([(-24, 0), (-rd, 0), (-rd, t), (-24, t)], fill=CU_OUT, stroke=CU_EDGE, width=0.5)
    sh.poly([(rd, 0), (24, 0), (24, t), (rd, t)], fill=CU_OUT, stroke=CU_EDGE, width=0.5)
    sh.poly([(-rd, t), (rd, t), (rd, t + stub), (-rd, t + stub)], fill=colors.HexColor("#f4f4f0"),
            stroke=INK, width=0.5)
    sh.line((-rd, t), (-rd, t + stub), INK, 1.4)
    sh.line((rd, t), (rd, t + stub), INK, 1.4)
    sh.poly([(-rd, t + stub), (rd, t + stub), (rd, t + stub + 0.8), (-rd, t + stub + 0.8)],
            fill=STEEL, stroke=INK, width=0.4)
    sh.line((-rd, t + stub), (rd, t + stub), PORT, 2.2)
    sh.poly([(-rp, 0), (rp, 0), (rp, t + stub), (-rp, t + stub)], fill=BRASS, stroke=INK, width=0.4)
    sh.poly([(-rr, -14), (rr, -14), (rr, 0), (-rr, 0)], fill=BRASS, stroke=INK, width=0.4)
    sh.line((-2.6, -10.5), (2.6, -9.3), colors.white, 3.0)
    sh.line((-2.6, -10.5), (2.6, -9.3), INK, 0.4)
    sh.line((-2.6, -11.5), (2.6, -10.3), INK, 0.4)
    # integration line: pin surface to shield
    yl = t + stub - 0.9
    sh.line((rp, yl), (rd, yl), AIR, 1.0)
    sh.arrow_head((rd, yl), (rp, yl), size=4.5, color=AIR)
    sh.dim((-rd, t + stub + 3.2), (rd, t + stub + 3.2), 0, f"{X['d_diel']:.2f}", ext=False, size=6.6)
    sh.text((-23.5, t + 0.9), "top wide wall, with a", 6.6, INK, "start")
    sh.text((-23.5, -2.4), f"{X['d_diel']:.2f} mm hole in it", 6.6, INK, "start")
    pr = sh.P
    callouts(d, W, [
        (pr((0, t + stub + 0.4)), "R", 176, "metal cap (PEC), 1 mm thick",
         "HFSS needs metal behind a port\nthat sits inside the model"),
        (pr((rd * 0.6, t + stub)), "R", 134, "wave port: the end face of the stub",
         "the red line. Where the 50 Ω signal enters"),
        (pr(((rp + rd) / 2 + 0.3, yl)), "R", 98, "integration line",
         "pin surface straight out to the shield"),
        (pr((-rd + 0.2, t + stub * 0.45)), "L", 150, "Teflon, εr 2.1",
         f"{X['d_diel']:.2f} across, shield on its\noutside face (Perfect E)"),
        (pr((0, t + stub * 0.6)), "R", 58, f"pin, {mm_str(X['d_pin'], 2)} mm (PEC)",
         "the SMA's own centre pin"),
        (pr((0, -7)), "R", 22, f"probe, {X['d_rod']:.2f} mm (PEC)",
         f"the 1/16 in brass rod, plen = {mm_str(G['probe_len'])} into the pipe"),
    ])
    return d


def fig_airbox_clear():
    W, H = BODY_W, 210
    d = Drawing(W, H)
    sc = 0.6
    Lg, L, c = G["Lg"], G["L"], X["clear"]
    hin, hout = G["b"] / 2, G["b1"] / 2
    ox, oy = 20 + (Lg + c) * sc, H / 2 + 8
    sh = Sheet(W, H, sc, ox, oy)
    sh.d = d
    sh.poly([(-Lg, -hin), (0, -hin), (L, -hout), (L, hout), (0, hin), (-Lg, hin)],
            fill=colors.HexColor("#eef3f8"), stroke=CU_EDGE, width=1.6)
    (x0, x1), (y0, y1), (z0, z1) = air_box()
    sh.poly([(z0, y0), (z1, y0), (z1, y1), (z0, y1)], fill=None, stroke=AIR, width=1.0, dash=[4, 2])
    sh.dim((L, hout), (z1, hout), 0.001, mm_str(c), ext=False, size=6.6, text_off=3)
    sh.dim((0, hout), (0, y1), 0.001, mm_str(c), ext=False, size=6.6, text_off=3)
    sh.dim((-Lg, 0), (z0, 0), 0.001, mm_str(c), ext=False, size=6.6, text_off=3)
    sh.text((z0, y0 - 13), "air box: radiation boundary on every face", 7, AIR, "start", bold=True)
    text_block(d, 330, H - 18, [
        "**How big the air box is**", "",
        "A radiation boundary must sit at least a",
        "quarter wavelength from anything that",
        f"radiates: {X['quarter']:.1f} mm at 2.45 GHz, and",
        f"{X['quarter_low']:.1f} mm at 2.2 GHz, the bottom of",
        f"the sweep. {mm_str(c)} mm clears both.", "",
        "Closer, and the boundary reflects some of",
        "the wave back. The pattern and S11 both",
        "move, and nothing warns you."], size=8, lead=11.4)
    return d


def fig_flow():
    W, H = BODY_W, 150
    d = Drawing(W, H)
    boxes = [("1", "Draw the air", "inside the horn, from\nthe variables"),
             ("2", "Mark the metal", "every wall becomes a\nPerfect E sheet"),
             ("3", "Add the feed", "coax stub and a\nwave port"),
             ("4", "Add space", "air box with a radiation\nboundary round it"),
             ("5", "Solve", "mesh, solve, refine,\nrepeat until it settles"),
             ("6", "Read it", "S11, gain, beam width,\nand check against theory")]
    bw, bh = 150, 48
    for i, (n, t, sub) in enumerate(boxes):
        col, row = i % 3, i // 3
        x = 12 + col * (bw + 30)
        y = H - 16 - bh - row * (bh + 26)
        d.add(Rect(x, y, bw, bh, fillColor=BOX, strokeColor=RULE, strokeWidth=0.7))
        d.add(Rect(x, y, 20, bh, fillColor=ACC, strokeColor=None))
        d.add(String(x + 10, y + bh / 2 - 4, n, fontName="DJ-B", fontSize=11, fillColor=colors.white,
                     textAnchor="middle"))
        d.add(String(x + 28, y + bh - 15, t, fontName="DJ-B", fontSize=9, fillColor=INK))
        for j, s in enumerate(sub.split("\n")):
            d.add(String(x + 28, y + bh - 27 - j * 9.5, s, fontName="DJ", fontSize=7.4, fillColor=MUT))
        if col < 2:
            d.add(String(x + bw + 15, y + bh / 2 - 5, "→", fontName="DJ-B", fontSize=14, fillColor=MUT,
                         textAnchor="middle"))
    d.add(String(12 + 2 * (bw + 30) + bw / 2, H - 16 - bh - 17, "↓", fontName="DJ-B", fontSize=13,
                 fillColor=MUT, textAnchor="middle"))
    return d


def plot_axes(d, x0, y0, w, h, xr, yr, xticks, yticks, xlabel, ylabel):
    def P_(xv, yv):
        return (x0 + (xv - xr[0]) / (xr[1] - xr[0]) * w, y0 + (yv - yr[0]) / (yr[1] - yr[0]) * h)
    d.add(Rect(x0, y0, w, h, fillColor=colors.white, strokeColor=RULE, strokeWidth=0.6))
    for xv in xticks:
        px, _ = P_(xv, yr[0])
        d.add(Line(px, y0, px, y0 + h, strokeColor=FAINT, strokeWidth=0.4))
        d.add(String(px, y0 - 10, f"{xv:g}", fontName="DJ", fontSize=6.8, fillColor=MUT, textAnchor="middle"))
    for yv in yticks:
        _, py = P_(xr[0], yv)
        d.add(Line(x0, py, x0 + w, py, strokeColor=FAINT, strokeWidth=0.4))
        d.add(String(x0 - 4, py - 2.5, f"{yv:g}", fontName="DJ", fontSize=6.8, fillColor=MUT, textAnchor="end"))
    d.add(String(x0 + w / 2, y0 - 22, xlabel, fontName="DJ", fontSize=7.4, fillColor=INK, textAnchor="middle"))
    d.add(String(x0 - 26, y0 + h + 6, ylabel, fontName="DJ", fontSize=7.4, fillColor=INK))
    return P_


def fig_patterns():
    W, H = BODY_W, 250
    d = Drawing(W, H)
    x0, y0, w, h = 44, 40, 300, 186
    P_ = plot_axes(d, x0, y0, w, h, (-90, 90), (-30, 0), range(-90, 91, 30), range(-30, 1, 5),
                   "angle off the centre of the beam, θ (degrees)", "gain relative to the peak (dB)")
    for key, colr, dash in (("pat_h", BEND, [4, 2]), ("pat_e", ACC, None)):
        pts = []
        for t_, v in zip(X["theta"], X[key]):
            pts += list(P_(t_, max(v, -30)))
        d.add(PolyLine(pts, strokeColor=colr, strokeWidth=1.5, strokeDashArray=dash))
    _, y3 = P_(-90, -3)
    d.add(Line(x0, y3, x0 + w, y3, strokeColor=INK, strokeWidth=0.5, strokeDashArray=[1, 2]))
    d.add(String(x0 + w - 3, y3 + 3, "−3 dB", fontName="DJ", fontSize=6.8, fillColor=INK, textAnchor="end"))
    sx, sy = P_(46, X["shoulder"])
    d.add(String(sx + 4, sy + 6, "shoulder", fontName="DJ", fontSize=6.8, fillColor=ACC))
    text_block(d, 372, H - 20, [
        "**What theory predicts**",
        "computed from the horn's mouth,",
        "not simulated", "",
        "**E-plane, solid line**",
        f"  beam {X['hp_e']:.1f}° wide at −3 dB",
        f"  shoulder near {neg(X['shoulder'])} dB, 40° to 55°", "",
        "**H-plane, dashed line**",
        f"  beam {X['hp_h']:.1f}° wide at −3 dB",
        "  falls smoothly, no sidelobe", "",
        f"**Peak gain {X['dir']:.1f} dBi**",
        f"  aperture efficiency {X['eff'] * 100:.0f}%"], size=8, lead=11.4)
    return d


def fig_s11_shapes():
    """Illustration only: the shape of a tuned and a mistuned S11."""
    W, H = BODY_W, 225
    d = Drawing(W, H)
    x0, y0, w, h = 44, 40, 300, 162
    P_ = plot_axes(d, x0, y0, w, h, (2.2, 2.7), (-30, 0), [2.2, 2.3, 2.4, 2.5, 2.6, 2.7],
                   range(-30, 1, 5), "frequency (GHz)", "S11 (dB)")
    bx0, _ = P_(2.4, 0)
    bx1, _ = P_(2.4835, 0)
    d.add(Rect(bx0, y0, bx1 - bx0, h, fillColor=colors.HexColor("#f6e9e2"), strokeColor=None))
    _, y10 = P_(2.2, -10)
    d.add(Line(x0, y10, x0 + w, y10, strokeColor=INK, strokeWidth=0.6, strokeDashArray=[3, 2]))
    d.add(String(x0 + 4, y10 + 3, "−10 dB", fontName="DJ", fontSize=6.8, fillColor=INK))
    fs = np.linspace(2.2, 2.7, 201)

    def curve(f0, R, Q):
        z = R / 50 + 1j * Q * (fs / f0 - f0 / fs)
        g = np.abs((z - 1) / (z + 1))
        return 20 * np.log10(np.maximum(g, 10 ** (-30 / 20)))
    for f0, R, Q, colr, dash, lab in ((2.442, 1.12, 5, ACC, None, "tuned: dip in the band, below −10 dB across it"),
                                      (2.27, 1.6, 6, MUT, [4, 2], "mistuned: dip in the wrong place")):
        pts = []
        for f, v in zip(fs, curve(f0, R * 50, Q)):
            pts += list(P_(f, max(v, -30)))
        d.add(PolyLine(pts, strokeColor=colr, strokeWidth=1.5, strokeDashArray=dash))
    d.add(String((bx0 + bx1) / 2, y0 + h - 10, "band", fontName="DJ-B", fontSize=7, fillColor=ACC,
                 textAnchor="middle"))
    text_block(d, 372, H - 20, [
        "**An illustration, not a result**",
        "the shape to look for", "",
        "**Solid line: a tuned probe**",
        "The dip sits inside the radar's band",
        "and the whole band is below −10 dB.", "",
        "**Dashed line: a mistuned probe**",
        "There is a dip, but at the wrong frequency.",
        "Plotting only the band would show a",
        "flat, poor line and no clue which way",
        "to move. Plot 2.2 to 2.7 GHz."], size=8, lead=11.4)
    return d


def fig_sweep_grid():
    W, H = BODY_W, 200
    d = Drawing(W, H)
    plens = [24 + i for i in range(11)]
    bshorts = [G["probe_z"] - 6 + 2 * i for i in range(7)]
    x0, y0, w, h = 60, 36, 270, 130
    P_ = plot_axes(d, x0, y0, w, h, (23.5, 34.5), (bshorts[0] - 1, bshorts[-1] + 1), plens,
                   [round(v, 1) for v in bshorts], "plen, probe length (mm)", "bshort (mm)")
    for p in plens:
        for bs in bshorts:
            x, y = P_(p, bs)
            d.add(Circle(x, y, 2.1, fillColor=colors.white, strokeColor=AIR, strokeWidth=0.8))
    x, y = P_(G["probe_len"], G["probe_z"])
    d.add(Circle(x, y, 4.5, fillColor=ACC, strokeColor=None))
    d.add(Line(x, y + 4.5, x, y0 + h + 8, strokeColor=ACC, strokeWidth=0.6))
    d.add(String(x + 3, y0 + h + 6, "the build guide's starting point", fontName="DJ", fontSize=6.8,
                 fillColor=ACC))
    text_block(d, 372, H - 20, [
        "**The tuning sweep**", "",
        "plen: 24 to 34 mm, 1 mm steps (11)",
        f"bshort: {mm_str(bshorts[0])} to {mm_str(bshorts[-1])} mm, 2 mm steps (7)",
        f"= {len(plens) * len(bshorts)} solves, each with its own mesh.", "",
        "Every circle is one full simulation.",
        "Leave it running overnight.", "",
        "At plen = 34 the probe tip still clears",
        f"the far wall by {mm_str(X['tip_gap'])} mm."], size=8, lead=11.4)
    return d


def fig_isolation():
    W, H = BODY_W, 170
    d = Drawing(W, H)
    sc = 0.3
    A, B = G["a1"] * sc, G["b1"] * sc
    cx = 150
    y = 52
    for i, name in enumerate(("RX, port 1", "TX, port 2")):
        x = cx + (i - 0.5) * 290 * sc - A / 2
        d.add(Rect(x, y, A, B, fillColor=CU_IN, strokeColor=CU_EDGE, strokeWidth=0.9))
        d.add(String(x + A / 2, y + B / 2 - 3, name, fontName="DJ-B", fontSize=8, fillColor=colors.white,
                     textAnchor="middle"))
    sh = Sheet(W, H, 1.0, 0, 0)
    sh.d = d
    c1, c2 = cx - 145 * sc, cx + 145 * sc
    for xx in (c1, c2):
        sh.line((xx, y - 2), (xx, y - 14), DIM, 0.35)
    sh.dim((c1, y - 11), (c2, y - 11), 0, "290 mm along x, centre to centre", ext=False, size=7,
           text_off=-10)
    d.add(String(12, H - 14, "In the model: both horns in their usual orientation, mouths flush.",
                 fontName="DJ", fontSize=7.6, fillColor=MUT))
    text_block(d, 330, H - 34, [
        "**Why along x**", "",
        "On the frame every horn is turned a",
        "quarter turn, so their 263.8 side runs",
        "up and TX sits 290 mm above RX.",
        "Turned back to the model's orientation,",
        "that 'above' is the x direction.", "",
        "Report S21, from port 2 into port 1,",
        "across 2.400–2.4835 GHz."], size=8, lead=11.4)
    return d


# ────────────────────────────────────────────────────────────── document ──
def on_page(canv, doc):
    canv.saveState()
    canv.setStrokeColor(RULE)
    canv.setLineWidth(0.5)
    canv.line(M, PAGE_H - 30, PAGE_W - M, PAGE_H - 30)
    canv.setFont("DJ", 7.6)
    canv.setFillColor(MUT)
    canv.drawString(M, PAGE_H - 25, "Designing the horn in Ansys HFSS  ·  2.45 GHz pyramidal horn")
    canv.drawRightString(PAGE_W - M, PAGE_H - 25, "radar-dev")
    canv.line(M, 30, PAGE_W - M, 30)
    canv.drawString(M, 20, "Sizes in mm, computed by antenna/tools/horn.py. Menu names follow "
                           "Ansys Electronics Desktop 2023–2025.")
    canv.drawRightString(PAGE_W - M, 20, f"{doc.page}")
    canv.restoreState()


def build():
    doc = BaseDocTemplate(str(OUT), pagesize=LETTER, leftMargin=M, rightMargin=M, topMargin=40,
                          bottomMargin=40, title="Designing the horn in Ansys HFSS", author="radar-dev",
                          subject="Antenna design in HFSS, for the 2.45 GHz horn")
    frame = Frame(M, 40, BODY_W, PAGE_H - 80, id="f", leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="p", frames=[frame], onPage=on_page)])
    g, x = G, X
    st = []

    # ── cover
    st += [P("Designing the horn in Ansys HFSS", "title"),
           P("The basics of antenna design in HFSS, worked through on this project's horn: what the "
             "antenna has to do, how the solver works, how to build the model, and how to tell a "
             "good answer from a wrong one.", "sub"),
           fig_model_3d(H=350, scale=0.6),
           P("The model this guide builds: the horn as thin metal sheets, a coax feed on the top "
             "wall, and a box of air around it.", "cap"),
           table([["the numbers to beat", "from theory", "accept from HFSS"],
                  ["peak gain", f"{g['gain']:.1f} dBi", f"{g['gain'] - 1.5:.1f} to {g['gain'] + 1.5:.1f} dBi"],
                  ["upper limit for this mouth", f"{x['bound']:.1f} dBi", "never above it"],
                  ["beam width, E-plane", f"{x['hp_e']:.1f}°", f"{x['hp_e'] - 4:.0f}° to {x['hp_e'] + 4:.0f}°"],
                  ["beam width, H-plane", f"{x['hp_h']:.1f}°", f"{x['hp_h'] - 4:.0f}° to {x['hp_h'] + 4:.0f}°"],
                  ["S11 across 2.400–2.4835 GHz", "set by the probe", "−10 dB or lower, after tuning"]],
                 [2.4, 1.5, 2.2]),
           PageBreak()]

    # ── 1. basics
    st += [P("1  What the horn has to do", "h1"),
           P("An antenna design comes down to three numbers. For this horn they are:"),
           table([["", "what it means", "target"],
                  ["gain", "how strongly the horn focuses power straight ahead, compared with an "
                   "antenna that spreads it evenly in every direction. Measured in dBi",
                   f"{g['gain']:.1f} dBi, about {10 ** (g['gain'] / 10):.0f} times"],
                  ["beam width", "how wide the beam is, measured between the two angles where the "
                   "power has dropped to half (−3 dB)", f"about {x['hp_e']:.0f}° × {x['hp_h']:.0f}°"],
                  ["match, S11", "how much of the power sent up the cable bounces back off the horn "
                   "instead of going out as the beam", "−10 dB or lower across the band"]],
                 [1, 4, 1.8]),
           Spacer(1, 6),
           P("How a horn works", "h2"),
           P(f"The pipe at the back is a waveguide: a metal tube that carries a radio wave along it. "
             f"A tube this size only carries signals above {x['fc']:.3f} GHz, and above "
             f"{x['fc2']:.2f} GHz a second wave pattern starts to fit and the signal gets messy. "
             f"The radar's band sits comfortably between the two, so the pipe carries exactly one "
             f"clean wave. The flare then widens that wave gently into a large mouth, and a large "
             f"mouth makes a narrow, strong beam."),
           fig_band(),
           P("Gain has a ceiling", "h2"),
           P(f"For a mouth of {mm_str(g['a1'])} × {mm_str(g['b1'])} mm at 2.45 GHz, no antenna can "
             f"do better than {x['bound']:.1f} dBi. Real horns reach about half of that ceiling: "
             f"integrating the wave across this horn's mouth gives {x['eff'] * 100:.0f}%, which is "
             f"{x['dir']:.1f} dBi. This is the most useful check in the whole guide. <b>If HFSS "
             f"reports more than {x['bound']:.1f} dBi, the model is wrong</b>, however well it "
             f"converged."),
           P("S11, in plain terms", "h2"),
           fig_s11_power(),
           P("The flare sets the gain and the beam, and theory already gets those right. The match "
             "depends on the probe, and nothing but a simulation or a measurement tells you that. "
             "Getting the match right is the real reason to run HFSS.", "small"),
           PageBreak()]

    st += [P("The E-plane and the H-plane", "h2"),
           P("A radiation pattern is 3D, so it is usually shown as two slices through the beam. "
             "They are named after the electric field inside the horn."),
           fig_planes(),
           P(f"Mixing the two up is the most common mistake in reporting a horn. There is an easy "
             f"check: here <b>the E-plane beam is the narrower one</b> ({x['hp_e']:.1f}° against "
             f"{x['hp_h']:.1f}°).", "small"),
           P("2  How HFSS works", "h1"),
           P("HFSS solves for the electric and magnetic field everywhere inside a box you define. "
             "You never write equations. You describe the geometry and say what each surface is: "
             "metal, the place the signal enters, or the edge of the modelled world."),
           fig_flow(),
           bullets([
               "<b>Mesh.</b> HFSS fills the space with small tetrahedra and solves the field on each "
               "one. Smaller pieces give a better answer and a slower solve.",
               "<b>Adaptive passes.</b> After each solve it finds where the error is largest, "
               "splits the pieces there, and solves again.",
               "<b>Convergence.</b> It stops when the answer stops changing between passes. The "
               "setting that controls this is <b>Delta S</b>: how much S11 may still move before it "
               "counts as settled.",
               "<b>Frequency sweep.</b> The mesh is built at one frequency, 2.45 GHz, then reused "
               "to work out S11 across a range of frequencies.",
               "<b>Far field.</b> From the field on the box, HFSS works out the beam at any "
               "distance: gain, beam width and pattern."]),
           callout("Model the air, not the copper",
                   "The wave lives in the air inside the horn and touches only the inside surface "
                   "of the copper. So the model draws the air, and marks each wall as a perfectly "
                   "conducting sheet (Perfect E). That is electrically what a copper horn is at "
                   "2.45 GHz, and it solves many times faster than meshing 0.5 mm metal."),
           PageBreak()]

    # ── 3. the model
    st += [P("3  The model", "h1"),
           P("One horn, in its usual orientation: the wide side along x, the narrow side along y, "
             "the beam coming out along +z. The frame turns the horns a quarter turn, but that "
             "changes nothing about one horn on its own."),
           fig_var_section(),
           P("Variables", "h2"),
           P("Type every size as a named variable, never as a bare number. Two of them, "
             "<b>plen</b> and <b>bshort</b>, are the ones you will sweep to tune the match, and a "
             "model built from bare numbers cannot be swept at all."),
           table([["variable", "value", "what it is"],
                  ["freq", "2.45 GHz", "design frequency"],
                  ["a, b", f"{mm_str(g['a'])} mm, {mm_str(g['b'])} mm", "pipe, inside, wide and narrow"],
                  ["a1, b1", f"{mm_str(g['a1'])} mm, {mm_str(g['b1'])} mm", "mouth, inside"],
                  ["pe", f"{mm_str(g['L'])} mm", "flare depth, pipe to mouth"],
                  ["Lg", f"{mm_str(g['Lg'])} mm", "pipe length, back wall to the flare"],
                  ["bshort", f"{mm_str(g['probe_z'])} mm", "probe centre to the back wall. <b>Swept</b>"],
                  ["plen", f"{mm_str(g['probe_len'])} mm", "probe length into the pipe. <b>Swept</b>"],
                  ["drod", f"{x['d_rod']:.3f} mm", "probe diameter, 1/16 in brass rod"],
                  ["dpin", f"{mm_str(x['d_pin'], 2)} mm", "SMA centre pin, inside the coax stub"],
                  ["ddiel", f"{x['d_diel']:.2f} mm", "Teflon diameter that makes the stub 50 Ω"],
                  ["clear", f"{mm_str(x['clear'])} mm", "air-box clearance round the horn"]],
                 [1.3, 1.6, 4.1]),
           PageBreak()]

    # ── 4. building
    st += [P("4  Building the model", "h1"),
           keep(step(1, "Start the design"),
                numbered([
                    "<b>Project → Insert HFSS Design.</b>",
                    "<b>HFSS → Solution Type → Modal</b> (listed as Driven Modal in older "
                    "versions). Modal suits a single coax or waveguide feed.",
                    "<b>Modeler → Units → mm</b>, before drawing anything. Changing units later "
                    "quietly reinterprets every number already typed.",
                    "<b>Project → Project Variables</b>, or type a name into any size box and HFSS "
                    "offers to create it. Enter every variable in the table on the previous page."])),
           keep(step(2, "Draw the air inside the horn"),
                numbered([
                    "<b>Draw → Box</b> for the pipe: position (−a/2, −b/2, −Lg), size (a, b, Lg).",
                    "<b>Draw → Rectangle</b> at the throat: centred on the axis at z = 0, a × b. "
                    "Draw a second one at z = pe, a1 × b1.",
                    "Select both rectangles, then <b>Modeler → Surface → Connect</b>. HFSS joins "
                    "them into a solid: the flare.",
                    "Select the pipe and the flare, <b>Modeler → Boolean → Unite</b>, and rename the "
                    "result <b>horn_air</b>. Material: vacuum."]),
                P(f"Check the flare: its sides should lean out {g['lean_top']:.1f}° top and bottom "
                  f"and {g['lean_side']:.1f}° at the sides. If Connect twists the solid, the two "
                  "rectangles are not centred on the same axis.", "small")),
           keep(step(3, "Turn the walls into metal sheets"),
                numbered([
                    "Select horn_air and switch to face selection (press <b>F</b>). Pick every "
                    "outside face <b>except the mouth</b>: four flare faces, four pipe faces, and "
                    "the back.",
                    "<b>Modeler → Surface → Create Object From Face.</b> These new sheets are the walls.",
                    "<b>Delete horn_air.</b> It was only a template; the air box fills that space later.",
                    "Select the wall sheets, right-click, <b>Assign Boundary → Perfect E</b>. Name "
                    "it walls."]),
                P("Later, for the real copper loss, change walls to <b>Finite Conductivity</b>, "
                  "copper. Expect it to cost a few hundredths of a dB. Not worth it on the first run.",
                  "small")),
           keep(step(4, "The feed: a short coax on the top wall"),
                fig_feed_detail(),
                P("Cut through the top wall at the feed, drawn large. The stub stands for the SMA "
                  "connector the build fits there.", "cap")),
           numbered([
               f"<b>Teflon.</b> A cylinder along y, diameter ddiel, centred at x = 0, z = −Lg + "
               f"bshort, from the top wall (y = b/2) up {mm_str(x['stub'])} mm. Material: "
               f"Teflon (tm), εr 2.1.",
               "<b>Pin.</b> A cylinder, diameter dpin, on the same axis and the same length. "
               "Material: pec. Subtract the pin from the Teflon with <b>Clone tool objects</b> "
               "ticked, so the pin survives.",
               "<b>Probe.</b> A cylinder, diameter drod, from y = b/2 down to y = b/2 − plen. "
               "Material: pec.",
               "<b>Shield.</b> Assign Perfect E to the Teflon's curved outside face.",
               "<b>Hole.</b> Cut a hole of diameter ddiel in the top wall sheet where the stub "
               "meets it. A probe that touches the wall gives a perfect-looking, completely false "
               "S11.",
               "<b>Cap.</b> A pec disc, diameter ddiel, 1 mm thick, on top of the stub."]),
           keep(step(5, "The wave port"),
                numbered([
                    "Select the flat end face of the Teflon, just under the cap.",
                    "<b>Assign Excitation → Wave Port.</b> One mode. Draw the <b>integration line</b> "
                    "from the pin's surface straight out to the shield. Keep "
                    "<b>Renormalize to 50 Ω</b> on."]),
                callout("The port must cover the coax and nothing else",
                        "A port larger than the Teflon face stops behaving like a coax and the S11 "
                        "means nothing. After the first solve, check <b>Results → Solution Data → "
                        "Port Field Display</b>: mode 1 must look like spokes running from the pin "
                        "to the shield.")),
           keep(step(6, "The air box and the radiation boundary"),
                fig_airbox_clear()),
           numbered([
               "<b>Draw → Box</b> around everything, clear by the clear variable on every side. "
               "Material: vacuum.",
               "Subtract the Teflon, pin and probe from the air box, with Clone tool objects "
               "ticked, so no two solids overlap.",
               "Select the box's six outside faces, <b>Assign Boundary → Radiation</b>."]),
           PageBreak()]

    # ── 5. solving
    st += [P("5  Solving it", "h1"),
           keep(step(7, "Solution setup and frequency sweep"),
                P("<b>HFSS → Analysis Setup → Add Solution Setup</b>, then add a frequency sweep "
                  "to it."),
                table([["setting", "value", "why"],
                       ["Solution frequency", "2.45 GHz", "the mesh is built here"],
                       ["Maximum number of passes", "20", "a ceiling, not a target"],
                       ["Maximum Delta S", "0.02", "0.01 for the final run"],
                       ["Minimum converged passes", "2", "one lucky pass is not convergence"],
                       ["Sweep type", "Interpolating", "few solves for a smooth curve"],
                       ["Sweep range", "2.2 to 2.7 GHz, 501 points", "see a mistuned dip, not just the band"]],
                      [2.2, 2, 2.8])),
           keep(step(8, "Far-field setup"),
                numbered([
                    "<b>HFSS → Radiation → Insert Far Field Setup → Infinite Sphere.</b>",
                    "A 3D sphere: θ 0 to 180°, φ 0 to 360°, 2° steps. Name it ff_3d.",
                    "The H-plane cut: φ = 0°, θ −180 to 180°, 1° steps. Name it cut_H.",
                    "The E-plane cut: φ = 90°, same θ range. Name it cut_E."])),
           keep(step(9, "Run it, then check the solver before believing it"),
                P("<b>HFSS → Analyze All</b>. Then work down this list in order."),
                table([["", "check", "where", "pass"],
                       ["1", "convergence", "Results → Solution Data → Convergence",
                        "Delta S under target, and the last passes barely changing"],
                       ["2", "port mode", "Solution Data → Port Field Display", "spokes, pin to shield"],
                       ["3", "mesh size", "Solution Data → Profile",
                        "tens of thousands to a few hundred thousand pieces"],
                       ["4", "gain vs the ceiling", "Far field report, Realized Gain Total",
                        f"below {x['bound']:.1f} dBi. Above it, the model is wrong"],
                       ["5", "the numbers", "the table on page 1", "gain, both beam widths, S11"]],
                      [0.3, 1.5, 2.8, 2.8])),
           P("Reports: <b>Results → Create Modal Solution Data Report → Rectangular Plot</b> for "
             "S11 in dB, and <b>Results → Create Far Fields Report → Radiation Pattern</b> for "
             "Realized Gain Total on cut_E and cut_H. Use realized gain: it includes what the "
             "mismatch costs, which is the gain the radar actually gets.", "small"),
           PageBreak()]

    # ── 6. what good looks like
    st += [P("6  What a good result looks like", "h1"),
           P("HFSS should land close to these. The patterns below are computed by adding up the "
             "wave across the horn's mouth, the textbook method, independently of HFSS. They "
             "leave out what happens at the rim and behind the horn, so expect HFSS to differ "
             "beyond about 60° and to show a small back lobe."),
           fig_patterns(),
           P(f"The E-plane shoulder near {neg(x['shoulder'])} dB is real, not an error. It comes "
             "from the flare being short for its width, which is the trade that keeps this horn "
             "compact. HFSS may show it as a small bump or sidelobe at about the same level.",
             "small"),
           fig_s11_shapes(),
           PageBreak()]

    # ── 7. tuning
    st += [P("7  Tuning the match", "h1"),
           P("Do not touch the flare: theory already sets it right. The match depends only on the "
             "feed, and there are exactly two knobs."),
           bullets(["<b>plen</b>, how far the probe reaches into the pipe, sets how strongly it "
                    "couples to the wave. It mostly moves the bottom of the dip up and down.",
                    "<b>bshort</b>, how far the probe is from the back wall, sets the timing "
                    "between the wave going forward and the one bouncing off the back. It mostly "
                    "slides the dip left and right."]),
           keep(step(10, "Sweep both"),
                P("<b>Optimetrics → Add → Parametric</b>, and add both variables as linear sweeps."),
                fig_sweep_grid()),
           numbered([
               "Plot S11 for every combination on one graph.",
               "Keep the pair whose curve stays below −10 dB across the whole of 2.400–2.4835 GHz, "
               "with the dip near the middle.",
               "If several pass, take the one with the most margin at the worst frequency, not the "
               "deepest dip.",
               "Set those values as the defaults, re-solve at Delta S 0.01, and take the gain and "
               "patterns from that final run.",
               "Give the chosen plen and bshort to the build: drill the feed hole at bshort and "
               "trim the rod to plen."]),
           callout("A deep dip is not the goal",
                   "−35 dB at one frequency and −8 dB at the band edge is worse than −14 dB "
                   "everywhere. The radar sweeps the whole band, and the worst frequency is the "
                   "one that counts."),
           PageBreak()]

    # ── 8. isolation
    st += [P("8  The second model: transmit to receive", "h1"),
           P("One question a single horn cannot answer: how much of the transmitted signal leaks "
             "straight into the receive horn. That leak is far stronger than the drone's echo, "
             "and the build needs it at <b>−35 dB or lower</b>."),
           keep(step(11, "Two horns, two ports"), fig_isolation()),
           numbered([
               "Save the tuned design as a copy. Select every part of the horn, "
               "<b>Edit → Duplicate → Along Line</b>, 290 mm along x.",
               "Give the copy its own wave port. The original is port 1 (RX), the copy port 2 (TX).",
               "Grow the air box so it still clears both horns by clear on every side.",
               "Solve with the same setup and plot S21 in dB. Pass: −35 dB or lower across the band."]),
           P("The build's foil sheet behind the horns and the frame are not in this model. Both "
             "should only improve the number, so a pass here is a safe pass.", "small"),
           Spacer(1, 6),
           P("9  Saving the results", "h1"),
           P("Everything goes in <b>antenna/results/</b>. Right-click any report, "
             "<b>Export</b>, and save it as .csv beside a picture of it."),
           table([["file", "what"],
                  ["horn.aedtz", "the project, archived: File → Archive"],
                  ["s11.csv, s11.png", "S11 of the tuned horn, 2.2 to 2.7 GHz"],
                  ["gain-eplane.csv, gain-hplane.csv", "realized gain on cut_E and cut_H at 2.45 GHz"],
                  ["patterns.png", "both cuts on one plot"],
                  ["probe-sweep.csv", "the parametric sweep: S11 for every plen and bshort"],
                  ["isolation.csv", "S21 between the two horns"]],
                 [2.5, 4.5]),
           PageBreak()]

    # ── record
    rows = [["result", "target", "HFSS"],
            ["realized gain at 2.400 GHz", f"{g['gain']:.1f} ± 1.5 dBi", ""],
            ["realized gain at 2.442 GHz", f"{g['gain']:.1f} ± 1.5 dBi", ""],
            ["realized gain at 2.483 GHz", f"{g['gain']:.1f} ± 1.5 dBi", ""],
            ["beam width, E-plane", f"{x['hp_e']:.1f} ± 4°", ""],
            ["beam width, H-plane", f"{x['hp_h']:.1f} ± 4°", ""],
            ["E-plane shoulder or first sidelobe", f"about {neg(x['shoulder'])} dB", ""],
            ["worst S11 in 2.400–2.4835 GHz", "−10 dB or lower", ""],
            ["chosen plen", f"start {mm_str(g['probe_len'])} mm", ""],
            ["chosen bshort", f"start {mm_str(g['probe_z'])} mm", ""],
            ["TX to RX, worst S21 in band", "−35 dB or lower", ""],
            ["final passes, final Delta S", "converged, ≤ 0.01", ""]]
    rec = table(rows, [3, 2, 2])
    rec.setStyle(TableStyle([("TOPPADDING", (0, 1), (-1, -1), 4.5), ("BOTTOMPADDING", (0, 1), (-1, -1), 4.5),
                             ("LINEBEFORE", (2, 0), (2, -1), 0.4, RULE)]))
    st += [P("Results record", "h1"),
           P("Fill this in from the final, tuned run. It is the page the LaTeX report is built from."),
           rec,
           Spacer(1, 10),
           P("Common mistakes", "h2"),
           table([["symptom", "likely cause"],
                  [f"gain above {x['bound']:.1f} dBi", "a wall missing its Perfect E, or the air box "
                   "too small and reflecting"],
                  ["S11 near 0 dB everywhere", "the probe touches the wall, or the port covers more "
                   "than the Teflon face"],
                  ["a perfect-looking dip, far too deep", "the probe is shorted to the wall: check the hole"],
                  ["the H-plane beam comes out narrower", "the cuts are swapped, or the pipe was drawn "
                   "a quarter turn round"],
                  ["results change when the air box grows", "it was too close. Keep clear above "
                   f"{x['quarter_low']:.0f} mm"],
                  ["millions of mesh pieces", "a thin solid somewhere: walls must be sheets"]],
                 [2.4, 4.6]),
           Spacer(1, 10),
           P("Words used in this guide", "h2"),
           table([["word", "means"],
                  ["dB, dBi", "a ratio on a log scale. −10 dB is a tenth, −20 dB a hundredth. dBi is "
                   "gain compared with an antenna that radiates evenly in every direction"],
                  ["S11", "the fraction of power that bounces back from the antenna into the cable"],
                  ["S21", "the fraction that leaks from one antenna's port into another's"],
                  ["realized gain", "gain after taking off what the mismatch reflects"],
                  ["waveguide", "the metal pipe at the back of the horn"],
                  ["Perfect E", "a surface HFSS treats as perfect metal"],
                  ["wave port", "where the signal enters the model"],
                  ["radiation boundary", "a surface that lets waves leave the model without "
                   "reflecting"],
                  ["mesh, pass", "the small pieces space is cut into, and one round of solving them"],
                  ["Delta S", "how much S11 changed between the last two passes"],
                  ["far field", "the beam as seen from a long way off"]],
                 [1.5, 5.5])]
    doc.build(st)


if __name__ == "__main__":
    build()
    print(f"wrote {OUT}")
    print(f"theory: {X['dir']:.2f} dBi, efficiency {X['eff'] * 100:.1f}%, beams E {X['hp_e']:.1f} / "
          f"H {X['hp_h']:.1f} deg, E shoulder {X['shoulder']:.1f} dB")
    print(f"feed: Teflon {X['d_diel']:.2f} mm for 50 ohm on a {X['d_pin']} mm pin; "
          f"tip gap at plen 34 = {X['tip_gap']:.1f} mm")
