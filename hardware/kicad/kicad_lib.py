#!/usr/bin/env python3
"""
kicad_lib.py — shared symbol library, placement model, KiCad 7 writer, SVG preview
and connectivity self-check for the radar schematics (gen_schematic.py, gen_multisim.py).

Original header:
gen_schematic.py — generate the radar's KiCad schematic (native .kicad_sch)
plus an SVG preview and a connectivity self-check, from one placement model.

Sheet layout (A3):
  LEFT   "BREADBOARD" — everything that is actually built on the breadboard:
         mixer-IF termination + RF stop, two-stage TL072 video amplifier with
         the two 159 Hz high-passes and the 15.9 kHz low-pass, buffered
         half-rail reference, 12 V protection / VANA filter, 5 V distribution
         with ferrites, ESP32 <-> ADF4351 / A4988 harness resistors, sync divider.
  RIGHT  "SYSTEM" — the modules the breadboard connects to: 12 V supply,
         LM2596, ESP32 devkit, ADF4351, 3 dB pad, PA, splitter, TX/RX horns,
         band-pass, LNA, mixer, A4988 + NEMA-17, UCA202 sound card.
         Same net names on both halves = same net (KiCad local labels).

All symbols are embedded (no external libraries needed). Open
radar_breadboard.kicad_sch in KiCad 7 or 8.

Usage:  python gen_schematic.py   -> radar_breadboard.kicad_sch, .kicad_pro, .svg
"""
import math, uuid, json, pathlib

OUT = pathlib.Path(__file__).resolve().parent
PROJECT = "radar_breadboard"
ROOT_UUID = "0f5c1a3e-9c2b-4d7a-8a11-radar0000001"
TITLE = "Horn-fed FMCW radar — breadboard and system"
COMMENTS = ("Left: the breadboard. Right: the modules it connects to.",
            "All 2.4 GHz paths are SMA coax between modules; nothing RF touches the breadboard.")
frames = []

def frame(x1, y1, x2, y2):
    frames.append((x1, y1, x2, y2))

def reset(project, root_uuid, title, comments):
    global PROJECT, ROOT_UUID, TITLE, COMMENTS
    PROJECT, ROOT_UUID, TITLE, COMMENTS = project, root_uuid, title, comments
    symbols.clear(); wires.clear(); junctions.clear(); labels.clear(); texts.clear(); frames.clear(); refcount.clear()


def U():
    return str(uuid.uuid4())

def f(v):
    v = round(v, 2)
    return f"{v:.2f}".rstrip("0").rstrip(".") if v != int(v) else str(int(v))

# ----------------------------------------------------------------------
# symbol library (KiCad library coordinates: mm, Y UP)
# pin: (number, name, (x, y), orientation_deg_into_body, length, electrical)
# ----------------------------------------------------------------------
LIB = {}

def defsym(name, pins, graphics, power=False, units=1, ref_prefix="U", hide_pin_names=False):
    LIB[name] = dict(pins=pins, graphics=graphics, power=power, units=units,
                     ref=ref_prefix, hide_pin_names=hide_pin_names)

# passives
defsym("Device:R",
       [("1", "~", (0, 3.81), 270, 1.27, "passive", 1), ("2", "~", (0, -3.81), 90, 1.27, "passive", 1)],
       [("rect", (-1.016, -2.54), (1.016, 2.54))], ref_prefix="R", hide_pin_names=True)
defsym("Device:C",
       [("1", "~", (0, 3.81), 270, 2.794, "passive", 1), ("2", "~", (0, -3.81), 90, 2.794, "passive", 1)],
       [("line", (-2.032, 0.762), (2.032, 0.762)), ("line", (-2.032, -0.762), (2.032, -0.762))],
       ref_prefix="C", hide_pin_names=True)
defsym("Device:C_Polarized",
       [("1", "~", (0, 3.81), 270, 2.794, "passive", 1), ("2", "~", (0, -3.81), 90, 2.794, "passive", 1)],
       [("line", (-2.032, 0.762), (2.032, 0.762)), ("line", (-2.032, -0.762), (2.032, -0.762)),
        ("line", (-1.4, 1.9), (-0.6, 1.9)), ("line", (-1.0, 1.5), (-1.0, 2.3))],
       ref_prefix="C", hide_pin_names=True)
defsym("Device:D_Schottky",
       [("1", "K", (-3.81, 0), 0, 2.54, "passive", 1), ("2", "A", (3.81, 0), 180, 2.54, "passive", 1)],
       [("poly", [(1.27, 1.27), (-1.27, 0), (1.27, -1.27), (1.27, 1.27)]),
        ("line", (-1.27, 1.27), (-1.27, -1.27)), ("line", (-1.27, 1.27), (-1.9, 1.27)), ("line", (-1.27, -1.27), (-0.64, -1.27))],
       ref_prefix="D", hide_pin_names=True)
defsym("Device:FerriteBead",
       [("1", "~", (0, 3.81), 270, 1.27, "passive", 1), ("2", "~", (0, -3.81), 90, 1.27, "passive", 1)],
       [("rect", (-1.016, -2.54), (1.016, 2.54)), ("line", (-1.016, -2.54), (1.016, 2.54))],
       ref_prefix="FB", hide_pin_names=True)
# dual op-amp: unit 1 = A, unit 2 = B, unit 3 = power
defsym("Amplifier_Operational:TL072",
       [("3", "+", (-7.62, 2.54), 0, 2.54, "input", 1), ("2", "-", (-7.62, -2.54), 0, 2.54, "input", 1),
        ("1", "~", (7.62, 0), 180, 2.54, "output", 1),
        ("5", "+", (-7.62, 2.54), 0, 2.54, "input", 2), ("6", "-", (-7.62, -2.54), 0, 2.54, "input", 2),
        ("7", "~", (7.62, 0), 180, 2.54, "output", 2),
        ("8", "V+", (0, 7.62), 270, 2.54, "power_in", 3), ("4", "V-", (0, -7.62), 90, 2.54, "power_in", 3)],
       [("poly", [(-5.08, 5.08), (5.08, 0), (-5.08, -5.08), (-5.08, 5.08)]),
        ("line", (-4.4, 2.54), (-3.2, 2.54)), ("line", (-3.8, 3.14), (-3.8, 1.94)), ("line", (-4.4, -2.54), (-3.2, -2.54))],
       units=3, ref_prefix="U")

def hdr(n, side="right"):
    """single-row 2.54 mm header; pins exit to the given side"""
    name = f"Connector:HDR{n}_{side[0].upper()}"
    if name in LIB:
        return name
    pins = []
    for i in range(n):
        y = -i * 2.54
        if side == "right":
            pins.append((str(i + 1), "~", (5.08, y), 180, 2.54, "passive", 1))
        else:
            pins.append((str(i + 1), "~", (-5.08, y), 0, 2.54, "passive", 1))
    g = [("rect", (-2.54, 1.27), (2.54, -(n - 1) * 2.54 - 1.27))]
    for i in range(n):
        y = -i * 2.54
        g.append(("rect", (-0.635, y + 0.635), (0.635, y - 0.635)))
    defsym(name, pins, g, ref_prefix="J", hide_pin_names=True)
    return name

def block(name, left, right, width=22.86):
    """a module drawn as a box with named pins on its left/right edges"""
    lib = f"Radar:{name}"
    if lib in LIB:
        return lib
    n = max(len(left), len(right))
    h = n * 2.54 + 2.54
    pins, num = [], 1
    for i, pn in enumerate(left):
        pins.append((str(num), pn, (-width / 2 - 2.54, h / 2 - 2.54 - i * 2.54), 0, 2.54, "passive", 1)); num += 1
    for i, pn in enumerate(right):
        pins.append((str(num), pn, (width / 2 + 2.54, h / 2 - 2.54 - i * 2.54), 180, 2.54, "passive", 1)); num += 1
    defsym(lib, pins, [("rect", (-width / 2, h / 2), (width / 2, -h / 2))], ref_prefix="M")
    return lib

def power(name):
    lib = f"power:{name}"
    if lib in LIB:
        return lib
    if name == "GND":
        g = [("line", (0, 0), (0, -1.27)), ("line", (-1.27, -1.27), (1.27, -1.27)),
             ("line", (-0.76, -1.9), (0.76, -1.9)), ("line", (-0.25, -2.5), (0.25, -2.5))]
        pins = [("1", name, (0, 0), 270, 0, "power_in", 1)]
    else:
        g = [("line", (0, 0), (0, 2.54)), ("poly", [(-0.762, 1.27), (0, 2.54), (0.762, 1.27)])]
        pins = [("1", name, (0, 0), 90, 0, "power_in", 1)]
    defsym(lib, pins, g, power=True, ref_prefix="#PWR", hide_pin_names=True)
    return lib

# ----------------------------------------------------------------------
# placement model
# ----------------------------------------------------------------------
symbols, wires, junctions, labels, texts = [], [], [], [], []
refcount = {}

def xform(px, py, x, y, rot):
    a = math.radians(rot)
    return (round(x + px * math.cos(a) - py * math.sin(a), 2),
            round(y - (px * math.sin(a) + py * math.cos(a)), 2))

def place(lib, x, y, value="", rot=0, unit=1, ref=None, hide_value=False, vpos=None, rpos=None):
    L = LIB[lib]
    if ref is None:
        if L["power"]:
            refcount["#PWR"] = refcount.get("#PWR", 0) + 1
            ref = f"#PWR{refcount['#PWR']:03d}"
        else:
            ref = L["ref"]
    pins = {}
    for (num, name, (px, py), o, ln, et, un) in L["pins"]:
        if un == unit:
            pins[num] = xform(px, py, x, y, rot)
            pins[name] = pins[num]
    s = dict(lib=lib, x=x, y=y, rot=rot, unit=unit, ref=ref, value=value, pins=pins,
             hide_value=hide_value, vpos=vpos, rpos=rpos)
    symbols.append(s)
    return s

def w(*pts):
    for a, b in zip(pts, pts[1:]):
        wires.append((tuple(round(v, 2) for v in a), tuple(round(v, 2) for v in b)))

def J(x, y):
    junctions.append((round(x, 2), round(y, 2)))

def lbl(name, x, y, rot=0, just="left"):
    labels.append((name, round(x, 2), round(y, 2), rot, just))

def note(text, x, y, size=1.5, bold=False):
    texts.append((text, x, y, size, bold))

def gnd(x, y):
    return place(power("GND"), x, y, "GND")

def rail(name, x, y):
    return place(power(name), x, y, name)

def R(ref, val, x, y, rot=0):
    s = place("Device:R", x, y, val, rot, ref=ref); return s

def C(ref, val, x, y, rot=0, pol=False):
    return place("Device:C_Polarized" if pol else "Device:C", x, y, val, rot, ref=ref)

# ======================================================================
# connectivity self-check (union-find over wires, pins, labels, power)
# ======================================================================
def netlist():
    parent = {}
    def find(a):
        while parent.setdefault(a, a) != a:
            parent[a] = parent[parent[a]]; a = parent[a]
        return a
    def union(a, b):
        parent[find(a)] = find(b)
    pts = {}
    def key(p):
        return (round(p[0], 2), round(p[1], 2))
    for a, b in wires:
        union(("pt", key(a)), ("pt", key(b)))
    # a wire endpoint lying on another wire's interior joins it only via a junction
    for jx, jy in junctions:
        for a, b in wires:
            if on_segment((jx, jy), a, b):
                union(("pt", (jx, jy)), ("pt", key(a)))
    pinnodes = []
    for s in symbols:
        L = LIB[s["lib"]]
        for (num, name, _, _, _, _, un) in L["pins"]:
            if un != s["unit"]:
                continue
            p = key(s["pins"][num])
            node = ("pin", s["ref"], num if not L["power"] else name)
            pinnodes.append((node, p))
            union(node, ("pt", p))
            if L["power"]:
                union(node, ("net", s["value"]))
    for (name, x, y, _, _) in labels:
        union(("net", name), ("pt", (round(x, 2), round(y, 2))))
    nets = {}
    for node, p in pinnodes:
        nets.setdefault(find(node), []).append(node)
    names = {}
    for (name, x, y, _, _) in labels:
        names[find(("net", name))] = name
    for s in symbols:
        if LIB[s["lib"]]["power"]:
            names[find(("net", s["value"]))] = s["value"]
    out = {}
    for root, nodes in nets.items():
        nm = names.get(root, "N$" + str(len(out)))
        out[nm] = sorted(f"{r}.{n}" for (_, r, n) in nodes)
    return out

def on_segment(p, a, b):
    (x, y), (x1, y1), (x2, y2) = p, a, b
    if abs((x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)) > 0.05:
        return False
    return min(x1, x2) - 0.05 <= x <= max(x1, x2) + 0.05 and min(y1, y2) - 0.05 <= y <= max(y1, y2) + 0.05

# ======================================================================
# KiCad writer
# ======================================================================
def lib_symbol_sexpr(name):
    L = LIB[name]
    out = [f'  (symbol "{name}"' + (" (power)" if L["power"] else "") +
           (" (pin_names hide)" if L["hide_pin_names"] else " (pin_names (offset 0.762))") +
           ' (in_bom yes) (on_board yes)']
    out.append(f'    (property "Reference" "{L["ref"]}" (at 0 0 0) (effects (font (size 1.27 1.27))))')
    out.append(f'    (property "Value" "{name.split(":")[1]}" (at 0 0 0) (effects (font (size 1.27 1.27))))')
    out.append('    (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))')
    out.append('    (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))')
    # graphics: unit 0 (shared)
    out.append(f'    (symbol "{name.split(":")[1]}_0_1"')
    for g in L["graphics"]:
        if g[0] == "rect":
            (x1, y1), (x2, y2) = g[1], g[2]
            out.append(f'      (rectangle (start {f(x1)} {f(y1)}) (end {f(x2)} {f(y2)}) (stroke (width 0.254) (type default)) (fill (type none)))')
        elif g[0] == "line":
            (x1, y1), (x2, y2) = g[1], g[2]
            out.append(f'      (polyline (pts (xy {f(x1)} {f(y1)}) (xy {f(x2)} {f(y2)})) (stroke (width 0.254) (type default)) (fill (type none)))')
        elif g[0] == "poly":
            pts = " ".join(f"(xy {f(x)} {f(y)})" for x, y in g[1])
            out.append(f'      (polyline (pts {pts}) (stroke (width 0.254) (type default)) (fill (type none)))')
    out.append('    )')
    for un in range(1, L["units"] + 1):
        out.append(f'    (symbol "{name.split(":")[1]}_{un}_1"')
        for (num, pname, (px, py), o, ln, et, u) in L["pins"]:
            if u != un:
                continue
            out.append(f'      (pin {et} line (at {f(px)} {f(py)} {o}) (length {f(ln)})'
                       f' (name "{pname}" (effects (font (size 1.27 1.27))))'
                       f' (number "{num}" (effects (font (size 1.27 1.27)))))')
        out.append('    )')
    out.append('  )')
    return "\n".join(out)

def write_kicad():
    global PROJECT, ROOT_UUID
    used = sorted({s["lib"] for s in symbols})
    L = ['(kicad_sch (version 20230121) (generator eeschema)', f'  (uuid "{ROOT_UUID}")', '  (paper "A3")',
         f'  (title_block (title "{TITLE}") (date "2026-09-07") (rev "1")'
         f'    (company "radar-dev") (comment 1 "{COMMENTS[0]}")'
         f'    (comment 2 "{COMMENTS[1]}"))',
         '  (lib_symbols']
    for n in used:
        L.append(lib_symbol_sexpr(n))
    L.append('  )')
    for (x1, y1, x2, y2) in frames:
        L.append(f'  (polyline (pts (xy {f(x1)} {f(y1)}) (xy {f(x2)} {f(y1)}) (xy {f(x2)} {f(y2)}) (xy {f(x1)} {f(y2)}) (xy {f(x1)} {f(y1)})) (stroke (width 0.3) (type dash)) (uuid "{U()}"))')
    for (jx, jy) in junctions:
        L.append(f'  (junction (at {f(jx)} {f(jy)}) (diameter 0) (color 0 0 0 0) (uuid "{U()}"))')
    for a, b in wires:
        L.append(f'  (wire (pts (xy {f(a[0])} {f(a[1])}) (xy {f(b[0])} {f(b[1])})) (stroke (width 0) (type default)) (uuid "{U()}"))')
    for (name, x, y, rot, just) in labels:
        jst = "left bottom" if just == "left" else "right bottom"
        L.append(f'  (label "{name}" (at {f(x)} {f(y)} {rot}) (fields_autoplaced) (effects (font (size 1.27 1.27)) (justify {jst})) (uuid "{U()}"))')
    for (t, x, y, size, bold) in texts:
        b = " bold" if bold else ""
        L.append(f'  (text "{t}" (at {f(x)} {f(y)} 0) (effects (font (size {f(size)} {f(size)}){b}) (justify left bottom)) (uuid "{U()}"))')
    for s in symbols:
        Ls = LIB[s["lib"]]
        vx, vy = (s["x"] + 2.5, s["y"] + 1.5) if s["rot"] == 0 else (s["x"] - 3.5, s["y"] + 5.0)
        rx, ry = (s["x"] + 2.5, s["y"] - 1.5) if s["rot"] == 0 else (s["x"] - 3.5, s["y"] - 3.5)
        if s["lib"].startswith("Radar:"):
            n = max(1, len([p for p in Ls["pins"] if p[6] == s["unit"]]))
            rx, ry = s["x"] - 6, s["y"] - (n * 1.27 + 3.5)
            vx, vy = s["x"] - 6, s["y"] + (n * 1.27 + 4.5)
        elif s["lib"].startswith("Connector:"):
            rx, ry = s["x"] - 3.5, s["y"] - 3.6
            vx, vy = s["x"] - 3.5, s["y"] + 1.27 * len(Ls["pins"]) + 3.0
        if s["rpos"]: rx, ry = s["rpos"]
        if s["vpos"]: vx, vy = s["vpos"]
        hv = " hide" if (s["hide_value"] or s["lib"].startswith("Connector:")) else ""
        L.append(f'  (symbol (lib_id "{s["lib"]}") (at {f(s["x"])} {f(s["y"])} {s["rot"]}) (unit {s["unit"]})'
                 f' (in_bom {"no" if Ls["power"] else "yes"}) (on_board yes) (dnp no) (uuid "{U()}")')
        L.append(f'    (property "Reference" "{s["ref"]}" (at {f(rx)} {f(ry)} 0) (effects (font (size 1.27 1.27)) (justify left){" hide" if Ls["power"] else ""}))')
        L.append(f'    (property "Value" "{s["value"]}" (at {f(vx)} {f(vy)} 0) (effects (font (size 1.27 1.27)) (justify left){hv}))')
        L.append(f'    (property "Footprint" "" (at {f(s["x"])} {f(s["y"])} 0) (effects (font (size 1.27 1.27)) hide))')
        L.append(f'    (property "Datasheet" "" (at {f(s["x"])} {f(s["y"])} 0) (effects (font (size 1.27 1.27)) hide))')
        for (num, pname, _, _, _, _, un) in Ls["pins"]:
            if un == s["unit"]:
                L.append(f'    (pin "{num}" (uuid "{U()}"))')
        L.append(f'    (instances (project "{PROJECT}" (path "/{ROOT_UUID}" (reference "{s["ref"]}") (unit {s["unit"]}))))')
        L.append('  )')
    L.append('  (sheet_instances (path "/" (page "1")))')
    L.append(')')
    (OUT / f"{PROJECT}.kicad_sch").write_text("\n".join(L) + "\n")
    (OUT / f"{PROJECT}.kicad_pro").write_text(json.dumps({
        "meta": {"filename": f"{PROJECT}.kicad_pro", "version": 1},
        "sheets": [[ROOT_UUID, ""]], "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []}}, indent=2))

# ======================================================================
# SVG preview (same placement math)
# ======================================================================
def write_svg():
    S = 3.2   # px per mm
    W, H = 420 * S, 297 * S
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="DejaVu Sans Mono, monospace">',
         f'<rect width="{W}" height="{H}" fill="#f7f4ea"/>',
         f'<line x1="{212*S}" y1="{12*S}" x2="{212*S}" y2="{285*S}" stroke="#bbb" stroke-dasharray="6 6"/>']
    def P(x, y):
        return f"{x*S:.1f},{y*S:.1f}"
    for (x1, y1, x2, y2) in frames:
        o.append(f'<rect x="{x1*S:.1f}" y="{y1*S:.1f}" width="{(x2-x1)*S:.1f}" height="{(y2-y1)*S:.1f}" fill="none" stroke="#999" stroke-dasharray="8 6" stroke-width="1.5"/>')
    for a, b in wires:
        o.append(f'<line x1="{a[0]*S:.1f}" y1="{a[1]*S:.1f}" x2="{b[0]*S:.1f}" y2="{b[1]*S:.1f}" stroke="#0b5e2b" stroke-width="1.8"/>')
    for jx, jy in junctions:
        o.append(f'<circle cx="{jx*S:.1f}" cy="{jy*S:.1f}" r="3" fill="#0b5e2b"/>')
    for s in symbols:
        Ls = LIB[s["lib"]]; x, y, rot = s["x"], s["y"], s["rot"]
        col = "#8a2d2d" if not Ls["power"] else "#2d3f8a"
        for g in Ls["graphics"]:
            if g[0] == "rect":
                pts = [xform(*g[1], x, y, rot), xform(g[2][0], g[1][1], x, y, rot), xform(*g[2], x, y, rot), xform(g[1][0], g[2][1], x, y, rot)]
                o.append(f'<polygon points="{" ".join(P(*p) for p in pts)}" fill="none" stroke="{col}" stroke-width="1.6"/>')
            elif g[0] == "line":
                a = xform(*g[1], x, y, rot); b = xform(*g[2], x, y, rot)
                o.append(f'<line x1="{a[0]*S:.1f}" y1="{a[1]*S:.1f}" x2="{b[0]*S:.1f}" y2="{b[1]*S:.1f}" stroke="{col}" stroke-width="1.6"/>')
            elif g[0] == "poly":
                pts = [xform(px, py, x, y, rot) for px, py in g[1]]
                o.append(f'<polyline points="{" ".join(P(*p) for p in pts)}" fill="none" stroke="{col}" stroke-width="1.6"/>')
        for (num, pname, (px, py), orient, ln, et, un) in Ls["pins"]:
            if un != s["unit"]:
                continue
            a = xform(px, py, x, y, rot)
            ex, ey = px + ln * math.cos(math.radians(orient)), py + ln * math.sin(math.radians(orient))
            b = xform(ex, ey, x, y, rot)
            o.append(f'<line x1="{a[0]*S:.1f}" y1="{a[1]*S:.1f}" x2="{b[0]*S:.1f}" y2="{b[1]*S:.1f}" stroke="{col}" stroke-width="1.6"/>')
            o.append(f'<circle cx="{a[0]*S:.1f}" cy="{a[1]*S:.1f}" r="2" fill="none" stroke="{col}" stroke-width="0.8"/>')
            if not Ls["hide_pin_names"] and pname not in ("~",):
                # pin name inside the body
                tx = b[0] + (1.0 if orient == 0 else -1.0) * (0 if rot else 1) * 0.8
                anchor = "start" if orient == 0 else "end"
                if Ls["power"]:
                    continue
                o.append(f'<text x="{(b[0] + (0.9 if orient == 0 else -0.9))*S:.1f}" y="{(b[1]+0.5)*S:.1f}" font-size="9" text-anchor="{anchor}" fill="#333">{pname}</text>')
        if Ls["power"]:
            o.append(f'<text x="{x*S:.1f}" y="{(y + (4.2 if s["value"] == "GND" else -3.2))*S:.1f}" font-size="9" text-anchor="middle" fill="#2d3f8a">{s["value"]}</text>')
        else:
            if s["lib"].startswith("Radar:") or s["lib"].startswith("Connector:"):
                n = len([p for p in Ls["pins"] if p[6] == s["unit"]])
                o.append(f'<text x="{(x-6)*S:.1f}" y="{(y - (8 if s["lib"].startswith("Radar:") else 3.2))*S:.1f}" font-size="10" font-weight="bold" fill="#8a2d2d">{s["ref"]}</text>')
                o.append(f'<text x="{(x-6)*S:.1f}" y="{(y + n*1.27 + 4.2)*S:.1f}" font-size="9" fill="#333">{s["value"]}</text>')
            else:
                dx, dy = (2.3, -1.2) if rot == 0 else (-3.5, -4.6)
                o.append(f'<text x="{(x+dx)*S:.1f}" y="{(y+dy)*S:.1f}" font-size="9" font-weight="bold" fill="#8a2d2d">{s["ref"]}</text>')
                dx, dy = (2.3, 2.2) if rot == 0 else (-3.5, 6.0)
                o.append(f'<text x="{(x+dx)*S:.1f}" y="{(y+dy)*S:.1f}" font-size="9" fill="#333">{s["value"]}</text>')
    for (name, x, y, rot, just) in labels:
        anchor = "start" if just == "left" else "end"
        o.append(f'<text x="{x*S:.1f}" y="{(y-0.6)*S:.1f}" font-size="9.5" fill="#1a3d8f" text-anchor="{anchor}" font-weight="bold">{name}</text>')
    for (t, x, y, size, bold) in texts:
        fw = ' font-weight="bold"' if bold else ''
        o.append(f'<text x="{x*S:.1f}" y="{y*S:.1f}" font-size="{size*5.2:.1f}" fill="#222"{fw}>{t}</text>')
    o.append('</svg>')
    (OUT / f"{PROJECT}.svg").write_text("\n".join(o))


def run_checks():
    nets = netlist()
    (OUT / f"{PROJECT}_nets.json").write_text(json.dumps(nets, indent=1, sort_keys=True))
    ends = {}
    for a, b in wires:
        for p in (a, b):
            ends[p] = ends.get(p, 0) + 1
    pinpts = {tuple(round(v, 2) for v in p) for s in symbols for p in s["pins"].values()}
    lblpts = {(x, y) for (_, x, y, _, _) in labels}
    dangling = [p for p, n in ends.items() if n == 1 and p not in pinpts and p not in lblpts
                and not any(on_segment(p, a, b) and p not in (a, b) for a, b in wires)]
    single = {k: v for k, v in nets.items() if len(v) == 1 and not k.startswith("N$")}
    print(f"symbols {len(symbols)}  wires {len(wires)}  labels {len(labels)}  nets {len(nets)}")
    print("dangling wire ends:", dangling)
    print("nets with a single pin:", single)
    return nets
