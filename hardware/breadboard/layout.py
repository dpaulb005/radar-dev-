#!/usr/bin/env python3
"""
layout.py — the breadboard, hole by hole, verified against the schematic.

Model: a standard 830-point breadboard.
  columns 1..63; top bank rows a-e (one strip per column), bottom bank rows
  f-j (one strip per column); four rails: TR+ (top red), TR- (top blue),
  BR+ (bottom red), BR- (bottom blue). Rail holes are addressed by the column
  they sit beside ("TR+@12"). Rails are assumed split in the middle (columns
  31|32) — bridging jumpers are included; harmless if yours is continuous.

Every component lead and every jumper end is a named hole. The script
  1. checks no hole is used twice and no part spans an impossible distance,
  2. derives the connectivity (strips + rails + jumpers + part bodies) and
     compares it with the schematic netlist (hardware/kicad/*_nets.json),
  3. writes layout.json (for the 3-D model), breadboard.svg (top view),
     WIRING.md (the build list).

Usage: python layout.py
"""
import json, math, pathlib, re, sys
from collections import defaultdict

OUT = pathlib.Path(__file__).resolve().parent
NETS = OUT.parent / "kicad" / "radar_breadboard_nets.json"

RAILS = {"TR+": "V5", "TR-": "GND", "BR+": "VANA", "BR-": "GND"}
ROWS_TOP, ROWS_BOT = "abcde", "fghij"

# ----------------------------------------------------------------------
# placement — (ref, kind, value, [(pin, hole), ...], note)
#   hole: "<row><col>" e.g. "c12", or a rail hole "TR-@12"
# ----------------------------------------------------------------------
P = []
def part(ref, kind, value, pins, note=""):
    P.append(dict(ref=ref, kind=kind, value=value, pins=pins, note=note))
DIP8_NAMES = {"1": "OUT A", "2": "IN- A", "3": "IN+ A", "4": "V-", "5": "IN+ B", "6": "IN- B", "7": "OUT B", "8": "V+"}
def dip(ref, value, col):
    """TL072 straddling the channel, notch / pin-1 dot toward the HIGH column (right).
    Top view with the notch on the right: e-row reads 4 3 2 1 left->right, f-row reads 5 6 7 8.
    (A DIP's pin 1 is counter-clockwise from the notch when seen from above.)"""
    pins = [(str(4 - i), f"e{col + i}") for i in range(4)] + [(str(5 + i), f"f{col + i}") for i in range(4)]
    part(ref, "dip8", value, pins, f"notch and pin-1 dot toward column {col + 3} (right); pin 1 at e{col + 3}, pin 8 at f{col + 3}")
def hdr(ref, value, first_col, row, names):   # single-row header, pins left->right
    part(ref, f"hdr{len(names)}", value, [(str(i + 1), f"{row}{first_col + i}") for i in range(len(names))],
         " / ".join(f"{i+1}={n}" for i, n in enumerate(names)))

# --- signal chain, top bank -------------------------------------------------
hdr("J1", "MIXER IF", 2, "a", ["IF", "GND"])                       # a2 = IF, a3 = GND stub
part("R1", "res", "49.9", [("1", "b2"), ("2", "TR-@2")], "IF termination straight to the top GND rail")
part("C20", "cer", "1n", [("1", "c2"), ("2", "TR-@3")], "RF stop, beside R1")
part("C1", "film", "100n", [("1", "d2"), ("2", "d4")], "5 mm film cap = 2 columns")
part("R2", "res", "10k", [("1", "c4"), ("2", "c1")], "AP -> VREF node (col 1)")
dip("U1", "TL072CP", 5)                                             # top: 4=e5 V-, 3=e6 IN+A, 2=e7 IN-A, 1=e8 OUT A
                                                                    # bottom: 5=f5 IN+B, 6=f6 IN-B, 7=f7 OUT B, 8=f8 V+
part("R3", "res", "100k", [("1", "b14"), ("2", "b10")], "feedback A: pin 1 at AM (col 14), pin 2 at AOUT (col 10)")
part("C2", "film", "100n", [("1", "c10"), ("2", "c12")], "AOUT -> BP")
part("R4", "res", "1k", [("1", "c14"), ("2", "c17")], "AM -> VREF (col 17). 4.7k here for gain 22 on first power-up")
part("R6", "res", "10k", [("1", "b12"), ("2", "b16")], "BP -> VREF (col 16)")
part("R7", "res", "10k", [("1", "b23"), ("2", "b19")], "feedback B: pin 1 at BM (col 23), pin 2 at BOUT (col 19). Wire link here = gain 1")
part("R8", "res", "1k", [("1", "c23"), ("2", "c26")], "BM -> VREF (col 26)")
part("R12", "res", "1k", [("1", "c19"), ("2", "c22")], "BOUT -> LP (col 22)")
part("C9", "cer", "10n", [("1", "d22"), ("2", "d24")], "LP -> VREF (col 24)")
dip("U2", "TL072CP", 30)                                            # top: 4=e30 V-, 3=e31 IN+A, 2=e32 IN-A, 1=e33 OUT A
                                                                    # bottom: 5=f30 IN+B, 6=f31 IN-B, 7=f32 OUT B, 8=f33 V+
part("R13", "res", "100", [("1", "i32"), ("2", "i35")], "OBUF (U2 pin 7, col 32 bottom) -> OISO (col 35)")
part("C10", "elec", "10u", [("1", "h35"), ("2", "h36")], "+ toward R13 (col 35), - toward J2 (col 36)")
part("R14", "res", "100k", [("1", "g36"), ("2", "BR-@36")], "output bleed to the bottom GND rail")
hdr("J2", "AUDIO L", 36, "f", ["AUDIO_L", "GND"])                  # f36 = AUDIO_L, f37 = GND stub
# --- bias ---------------------------------------------------------------------
part("R9", "res", "10k", [("1", "a36"), ("2", "a31")], "VANA stub (col 36 top, jumpered to BR+) -> VDIV (col 31 = U2 pin 3)")
part("R10", "res", "10k", [("1", "b31"), ("2", "TR-@33")], "VDIV (col 31) -> GND rail")
part("C5", "elec", "10u", [("1", "c31"), ("2", "TR-@35")], "+ at VDIV (col 31), - bent up to the GND rail")
part("R11", "res", "47", [("1", "c33"), ("2", "c29")], "VBUF (U2 pin 1, col 33) -> col 29, then a wire on to the VREF node (col 26)")
part("C6", "elec", "47u", [("1", "d26"), ("2", "TR-@26")], "+ at VREF")
# --- power, bottom bank -------------------------------------------------------
hdr("J3", "12V IN", 10, "j", ["VIN12", "GND"])                     # j10 = VIN12, j11 = GND stub
part("D1", "diode", "1N5822", [("A", "i10"), ("K", "i13")], "band (cathode) toward col 13 = VPROT")
part("C11", "elec", "100u", [("1", "h13"), ("2", "BR-@13")], "+ at VPROT")
hdr("J4", "TO BUCK IN", 13, "j", ["VPROT", "GND"])                 # j13 = VPROT, j14 = GND stub
part("R15", "res", "10", [("1", "g13"), ("2", "g16")], "VPROT -> VANA node (col 16 bottom)")
part("C13", "elec", "100u", [("1", "h16"), ("2", "BR-@16")], "+ at VANA")
hdr("J5", "FROM BUCK 5V", 18, "j", ["V5", "GND"])                  # j18 = V5, j19 = GND stub
part("C12", "elec", "100u", [("1", "h18"), ("2", "BR-@18")], "+ at V5")
part("C3", "cer", "100n", [("1", "g8"), ("2", "BR-@8")], "U1 V+ (pin 8, col 8 bottom) to GND, right at the pin")
part("C7", "cer", "100n", [("1", "g33"), ("2", "BR-@33")], "U2 V+ (pin 8, col 33 bottom) to GND")
# --- 5 V distribution, top bank right --------------------------------------
for i, (col, jref, jval, fb, ca, cb) in enumerate([(38, "J6", "ADF4351 5V", "FB1", "C14", "C15"),
                                                    (41, "J7", "PA 5V", "FB2", "C16", "C17"),
                                                    (44, "J8", "LNA 5V", "FB3", "C18", "C19")]):
    part(fb, "bead", "FB", [("1", f"TR+@{col}"), ("2", f"a{col}")], "from the top 5 V rail down into the column")
    part(ca, "elec", "10u", [("1", f"b{col}"), ("2", f"TR-@{col+1}")], "+ at the module rail")
    part(cb, "cer", "100n", [("1", f"c{col}"), ("2", f"TR-@{col+2}")], "")
    hdr(jref, jval, col, "d", ["5V", "GND"])                        # d{col} = V5_x, d{col+1} = GND stub
# --- digital, bottom bank right ----------------------------------------------
hdr("J9", "ESP32", 44, "j", ["GND", "SCK", "MOSI", "LE", "LD", "SYNC", "STEP", "DIR", "EN", "3V3"])   # j44..j53
part("R16", "res", "33", [("1", "f45"), ("2", "e46")], "SCK (bottom col 45) straight across the channel to top col 46")
part("R17", "res", "33", [("1", "f46"), ("2", "e47")], "MOSI (bottom col 46) across to top col 47")
part("R18", "res", "33", [("1", "f47"), ("2", "e48")], "LE (bottom col 47) across to top col 48")
hdr("J10", "ADF LOGIC", 52, "a", ["GND", "SCK_O", "MOSI_O", "LE_O", "LD", "CE"])                       # a52..a57 (top bank)
part("R19", "res", "10k", [("1", "b57"), ("2", "TR-@57")], "CE pull-down")
hdr("JP3", "CE EN", 57, "d", ["CE", "3V3"])                         # d57 = CE, d58 = 3V3 stub
hdr("J11", "A4988 LOGIC", 58, "j", ["GND", "3V3", "STEP", "DIR", "EN"])                                  # j58..j62
part("R20", "res", "10k", [("1", "i59"), ("2", "i62")], "EN pull-up: pin 1 at 3V3 (col 59), pin 2 at EN (col 62)")
part("R21", "res", "10k", [("1", "h60"), ("2", "BR-@60")], "STEP pull-down")
part("R22", "res", "10k", [("1", "h61"), ("2", "BR-@61")], "DIR pull-down")
part("R23", "res", "10k", [("1", "b60"), ("2", "b63")], "SYNC (jumpered up to col 60 top) -> AUDIO_R (col 63)")
part("R24", "res", "1k", [("1", "c63"), ("2", "TR-@63")], "0.3 V divider bottom leg")
part("J12", "hdr2", "AUDIO R", [("1", "d63"), ("2", "d62")], "1=AUDIO_R (col 63), 2=GND stub (col 62)")

# ----------------------------------------------------------------------
# jumper wires — (from, to, colour, what it does)
# ----------------------------------------------------------------------
W = []
def wire(a, b, colour, why): W.append(dict(a=a, b=b, colour=colour, why=why))
BK, RD, BL, YL, GN, OR, WH, GY, VI = "black", "red", "blue", "yellow", "green", "orange", "white", "grey", "violet"
# ground stubs of the headers to the rails
wire("e3", "TR-@4", BK, "J1 GND")
wire("j37", "BR-@37", BK, "J2 GND")
wire("f11", "BR-@11", BK, "J3 GND")
wire("f14", "BR-@14", BK, "J4 GND")
wire("f19", "BR-@19", BK, "J5 GND")
wire("e39", "TR-@41", BK, "J6 GND"); wire("e42", "TR-@44", BK, "J7 GND"); wire("e45", "TR-@47", BK, "J8 GND")
wire("f44", "BR-@44", BK, "J9 pin 1 GND"); wire("e52", "TR-@52", BK, "J10 pin 1 GND"); wire("f58", "BR-@58", BK, "J11 pin 1 GND")
wire("e62", "TR-@62", BK, "J12 GND")
# op-amp supplies
wire("a5", "TR-@5", BK, "U1 pin 4 (V-, top col 5) to the GND rail")
wire("a30", "TR-@30", BK, "U2 pin 4 (V-, top col 30) to the GND rail")
wire("h8", "BR+@8", RD, "U1 pin 8 (V+, bottom col 8) to the VANA rail")
wire("h33", "BR+@33", RD, "U2 pin 8 (V+, bottom col 33) to the VANA rail")
wire("f16", "BR+@16", RD, "VANA node (R15/C13) feeds the bottom red rail")
wire("e36", "BR+@36", RD, "R9's VANA end (top col 36) down to the VANA rail")
wire("g18", "TR+@18", OR, "V5 (J5/C12, bottom col 18) up to the top red rail")
wire("TR-@1", "BR-@1", BK, "tie the two GND rails together")
# rail bridges (boards whose rails split at the middle)
wire("TR+@31", "TR+@32", OR, "rail bridge (omit if your rails are continuous)")
wire("TR-@31", "TR-@32", BK, "rail bridge")
wire("BR+@31", "BR+@32", RD, "rail bridge")
wire("BR-@31", "BR-@32", BK, "rail bridge")
# signal chain
wire("a4", "a6", GN, "AP (C1/R2 node) into U1 pin 3 (IN+ A, col 6)")
wire("a8", "a10", GN, "U1 pin 1 (OUT A, col 8) to the AOUT node (col 10)")
wire("a14", "a7", GN, "AM node (R3/R4) back to U1 pin 2 (IN- A, col 7)")
wire("d12", "g5", GN, "BP (C2/R6 node) across the channel into U1 pin 5 (IN+ B, bottom col 5)")
wire("g7", "a19", GN, "U1 pin 7 (OUT B, bottom col 7) up to the BOUT node (col 19)")
wire("a23", "i6", GN, "BM node (R7/R8) across to U1 pin 6 (IN- B, bottom col 6)")
wire("e22", "h30", GN, "LP (R12/C9 node) across to U2 pin 5 (IN+ B, bottom col 30)")
wire("j32", "j31", GN, "U2 pin 7 (col 32) to pin 6 (col 31): unity-gain buffer")
wire("a33", "a32", GN, "U2 pin 1 (col 33) to pin 2 (col 32): VREF buffer, unity gain")
# VREF distribution (source node = col 26: R8, R11, C6)
wire("b29", "b26", VI, "R11's far end (col 29) to the VREF node (col 26)")
wire("a26", "a24", VI, "VREF -> C9's VREF end")
wire("b24", "c16", VI, "VREF -> R6's VREF end (col 16)")
wire("d16", "d17", VI, "VREF (col 16) -> R4's VREF end (col 17)")
wire("a1", "a16", VI, "VREF -> R2's VREF end (col 1): long run along row a")
# digital
wire("a46", "b53", BL, "R16 out (top col 46) -> J10 pin 2 SCK_O (col 53)")
wire("a47", "b54", BL, "R17 out (top col 47) -> J10 pin 3 MOSI_O (col 54)")
wire("a48", "b55", BL, "R18 out (top col 48) -> J10 pin 4 LE_O (col 55)")
wire("f48", "b56", BL, "J9 pin 5 LD (bottom col 48) -> J10 pin 5 LD (top col 56)")
wire("f53", "e58", YL, "J9 pin 10 3V3 (bottom col 53) -> JP3 pin 2 (top col 58)")
wire("g53", "g59", YL, "3V3 -> J11 pin 2 / R20 (bottom col 59)")
wire("g50", "g60", WH, "J9 pin 7 STEP (col 50) -> J11 pin 3 (col 60)")
wire("g51", "g61", WH, "J9 pin 8 DIR (col 51) -> J11 pin 4 (col 61)")
wire("g52", "g62", WH, "J9 pin 9 EN (col 52) -> J11 pin 5 (col 62)")
wire("h49", "a60", GY, "J9 pin 6 SYNC (bottom col 49) up to R23 (top col 60)")

# ----------------------------------------------------------------------
# model + checks
# ----------------------------------------------------------------------
def parse(h):
    m = re.fullmatch(r"([a-j])(\d+)", h)
    if m: return ("strip", ("T" if m.group(1) in ROWS_TOP else "B") + m.group(2), m.group(1), int(m.group(2)))
    m = re.fullmatch(r"(TR\+|TR-|BR\+|BR-)@(\d+)", h)
    if m: return ("rail", m.group(1), None, int(m.group(2)))
    raise ValueError(h)

def check():
    errors = []
    used = {}
    for p in P:
        for pin, h in p["pins"]:
            k = parse(h)
            if h in used: errors.append(f"hole {h} used by {used[h]} and {p['ref']}.{pin}")
            used[h] = f"{p['ref']}.{pin}"
            if k[0] == "strip" and int(k[3]) > 63: errors.append(f"{p['ref']} off the board at {h}")
    for w in W:
        for h in (w["a"], w["b"]):
            if h in used: errors.append(f"hole {h} used by {used[h]} and a wire ({w['why']})")
            used[h] = f"wire:{w['why']}"
    # part spans (columns) — axial parts need 2..5 columns, 5 mm film exactly 2, 2.5 mm electrolytic 1
    for p in P:
        if p["kind"] in ("res", "diode", "bead", "film", "cer", "elec") and len(p["pins"]) == 2:
            (_, ha), (_, hb) = p["pins"]
            (xa, ya), (xb, yb) = hole_xy(ha), hole_xy(hb)
            reach = math.hypot(xa - xb, ya - yb) / 2.54          # lead-to-lead distance in hole pitches
            lim = {"res": (2, 6), "diode": (2, 6), "bead": (0, 4), "film": (1.5, 2.5), "cer": (0, 6), "elec": (0, 6)}[p["kind"]]
            if not (lim[0] <= reach <= lim[1]): errors.append(f"{p['ref']} reach {reach:.1f} pitches ({ha}-{hb}) outside {lim}")
    return errors, used

def connectivity():
    parent = {}
    def find(a):
        while parent.setdefault(a, a) != a: parent[a] = parent[parent[a]]; a = parent[a]
        return a
    def union(a, b): parent[find(a)] = find(b)
    def node(h):
        k = parse(h)
        if k[0] == "strip": return ("strip", k[1])
        r, col = k[1], k[3]
        return ("rail", r, "L" if col <= 31 else "R")     # split rails
    for w in W: union(node(w["a"]), node(w["b"]))
    pin_node = {}
    for p in P:
        for pin, h in p["pins"]:
            pin_node[(p["ref"], pin)] = find(node(h))
    return find, pin_node

def expected_nets():
    nets = json.loads(NETS.read_text())
    bb_refs = {p["ref"] for p in P}
    exp = {}
    for name, pins in nets.items():
        keep = []
        for pn in pins:
            ref, pin = pn.split(".", 1)
            if ref in bb_refs:
                if ref.startswith("J") and pin.isdigit(): keep.append((ref, pin))
                elif ref == "D1": keep.append((ref, {"1": "K", "2": "A"}[pin]))
                else: keep.append((ref, pin))
        if keep: exp[name] = keep
    return exp

def verify():
    errors, used = check()
    find, pin_node = connectivity()
    exp = expected_nets()
    # 1. every schematic net must be one group on the board
    group_of_net = {}
    for name, pins in exp.items():
        groups = {pin_node[p] for p in pins if p in pin_node}
        missing = [p for p in pins if p not in pin_node]
        if missing: errors.append(f"net {name}: pins not placed {missing}")
        if len(groups) > 1: errors.append(f"net {name} is SPLIT into {len(groups)} groups: " + str({p: pin_node[p] for p in pins if p in pin_node}))
        if groups: group_of_net[name] = groups.pop()
    # 2. no two nets may share a group
    seen = {}
    for name, g in group_of_net.items():
        if g in seen: errors.append(f"nets {seen[g]} and {name} are SHORTED on the board (group {g})")
        seen[g] = name
    # 3. rails carry what they claim
    for rail, net in RAILS.items():
        for half in ("L", "R"):
            g = find(("rail", rail, half))
            if g in seen and seen[g] != net: errors.append(f"rail {rail}{half} is on net {seen[g]}, expected {net}")
    return errors, exp, pin_node, find

# ----------------------------------------------------------------------
# outputs
# ----------------------------------------------------------------------
def hole_xy(h):   # mm, board coordinates; column pitch 2.54; top-left origin
    k = parse(h)
    x = 7.0 + (k[3] - 1) * 2.54
    if k[0] == "strip":
        r = k[2]; i = "abcdefghij".index(r)
        y = 9.0 + i * 2.54 + (3.0 if i >= 5 else 0)      # channel gap between e and f
    else:
        y = {"TR+": 2.0, "TR-": 4.54, "BR+": 38.6, "BR-": 41.1}[k[1]]
    return x, y

COLOURS = {"black": "#111", "red": "#d33", "blue": "#2f77b0", "yellow": "#e0b020", "green": "#2a9d5c", "orange": "#e07a20", "white": "#eee", "grey": "#8a8f96", "violet": "#7a4fbf"}
def svg():
    S = 5.0; W_, H_ = 170, 47
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W_*S} {H_*S}" width="{W_*S}" height="{H_*S}" font-family="IBM Plex Mono, DejaVu Sans Mono, monospace">',
         f'<rect width="{W_*S}" height="{H_*S}" fill="#f4f1e8" rx="8"/>']
    # rails stripes
    for r, y, c in (("TR+", 2.0, "#d33"), ("TR-", 4.54, "#2f77b0"), ("BR+", 38.6, "#d33"), ("BR-", 41.1, "#2f77b0")):
        o.append(f'<line x1="{5*S}" y1="{(y-1.4 if "+" in r else y+1.4)*S}" x2="{165*S}" y2="{(y-1.4 if "+" in r else y+1.4)*S}" stroke="{c}" stroke-width="2"/>')
        o.append(f'<text x="{1.2*S}" y="{(y+0.6)*S}" font-size="9" fill="{c}">{RAILS[r]}</text>')
    # holes
    for col in range(1, 64):
        for row in "abcdefghij":
            x, y = hole_xy(f"{row}{col}"); o.append(f'<rect x="{(x-0.5)*S}" y="{(y-0.5)*S}" width="{S}" height="{S}" fill="#555"/>')
        for r in RAILS:
            x, y = hole_xy(f"{r}@{col}"); o.append(f'<rect x="{(x-0.5)*S}" y="{(y-0.5)*S}" width="{S}" height="{S}" fill="#777"/>')
        if col % 5 == 0 or col == 1:
            x, _ = hole_xy(f"a{col}"); o.append(f'<text x="{x*S}" y="{7.2*S}" font-size="8" text-anchor="middle" fill="#666">{col}</text>')
    for row in "abcdefghij":
        _, y = hole_xy(f"{row}1"); o.append(f'<text x="{4.8*S}" y="{(y+0.6)*S}" font-size="8" text-anchor="end" fill="#666">{row}</text>')
    # rail split marker
    xs, _ = hole_xy("a31"); xe, _ = hole_xy("a32")
    o.append(f'<line x1="{(xs+xe)/2*S}" y1="{0.5*S}" x2="{(xs+xe)/2*S}" y2="{6*S}" stroke="#bbb" stroke-dasharray="3 3"/>')
    o.append(f'<line x1="{(xs+xe)/2*S}" y1="{37*S}" x2="{(xs+xe)/2*S}" y2="{43*S}" stroke="#bbb" stroke-dasharray="3 3"/>')
    # wires (under parts)
    for w in W:
        (x1, y1), (x2, y2) = hole_xy(w["a"]), hole_xy(w["b"]); c = COLOURS[w["colour"]]
        sag = -max(1.5, abs(x2 - x1) * 0.12) if (y1 + y2) / 2 < 22 else max(1.5, abs(x2 - x1) * 0.12)
        o.append(f'<path d="M{x1*S},{y1*S} Q{(x1+x2)/2*S},{((y1+y2)/2+sag)*S} {x2*S},{y2*S}" fill="none" stroke="{c}" stroke-width="3" stroke-linecap="round" opacity=".9"/>')
        o.append(f'<circle cx="{x1*S}" cy="{y1*S}" r="2.2" fill="{c}"/><circle cx="{x2*S}" cy="{y2*S}" r="2.2" fill="{c}"/>')
    # parts
    for p in P:
        pts = [hole_xy(h) for _, h in p["pins"]]
        if p["kind"] == "dip8":
            # true to life: 9.9 x 6.4 mm body on 7.62 mm row spacing, notch at the pin-1/pin-8 end (right), dot beside pin 1
            xs_ = [q[0] for q in pts]; xc = (min(xs_) + max(xs_)) / 2; x0, x1 = xc - 4.95, xc + 4.95
            yc = (pts[0][1] + pts[4][1]) / 2; y0, y1 = yc - 3.2, yc + 3.2
            for (pin, h), (x, y) in zip(p["pins"], pts):     # legs from the body edge into the holes
                o.append(f'<line x1="{x*S}" y1="{(y0 if h[0]=="e" else y1)*S}" x2="{x*S}" y2="{y*S}" stroke="#9a9a9a" stroke-width="3"/>')
            o.append(f'<rect x="{x0*S}" y="{y0*S}" width="{(x1-x0)*S}" height="{(y1-y0)*S}" fill="#1b1f24" rx="1.5"/>')
            o.append(f'<path d="M{x1*S},{(yc-1.1)*S} A{1.1*S},{1.1*S} 0 0 0 {x1*S},{(yc+1.1)*S} Z" fill="#efe9d6"/>')   # notch, right end
            o.append(f'<circle cx="{(x1-1.3)*S}" cy="{(y0+1.2)*S}" r="2.2" fill="#ddd"/>')                             # pin-1 dot (row e end)
            o.append(f'<text x="{(x0+x1)/2*S}" y="{(yc+0.45)*S}" font-size="6" fill="#fff" stroke="#1b1f24" stroke-width="2" paint-order="stroke" text-anchor="middle" font-weight="bold">{p["ref"]} {p["value"]}</text>')
            for (pin, h), (x, y) in zip(p["pins"], pts):
                top = h[0] == "e"
                o.append(f'<text x="{x*S}" y="{(y + (-1.35 if top else 1.95))*S}" font-size="5.5" fill="#333" text-anchor="middle">{pin}</text>')
                o.append(f'<text transform="translate({x*S},{(y0+0.35 if top else y1-0.35)*S}) rotate(-90)" font-size="4.2" fill="#cfcfcf" text-anchor="{"end" if top else "start"}" dominant-baseline="middle">{DIP8_NAMES[pin]}</text>')
        elif p["kind"].startswith("hdr"):
            x0, x1 = pts[0][0] - 1.27, pts[-1][0] + 1.27; y = pts[0][1]
            o.append(f'<rect x="{x0*S}" y="{(y-1.27)*S}" width="{(x1-x0)*S}" height="{2.54*S}" fill="#222" rx="2"/>')
            for (pin, h), (x, yy) in zip(p["pins"], pts): o.append(f'<rect x="{(x-0.45)*S}" y="{(yy-0.45)*S}" width="{0.9*S}" height="{0.9*S}" fill="#d4b25a"/>')
            lab = p["ref"] + (" " + p["value"] if len(p["pins"]) >= 5 else "")
            o.append(f'<text x="{(x0+x1)/2*S}" y="{(y + (3.4 if y > 22 else -2.2))*S}" font-size="7.5" fill="#222" text-anchor="middle" font-weight="bold">{lab}</text>')
        else:
            (x1, y1), (x2, y2) = pts; col = {"res": "#d9c39a", "film": "#d8b53a", "cer": "#d08a3a", "elec": "#2a3140", "diode": "#222", "bead": "#666"}[p["kind"]]
            o.append(f'<line x1="{x1*S}" y1="{y1*S}" x2="{x2*S}" y2="{y2*S}" stroke="#999" stroke-width="1.5"/>')
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2; ang = 0 if abs(x2 - x1) >= abs(y2 - y1) else 90
            bw, bh = (5.5, 2.2) if p["kind"] in ("res", "diode") else (3.4, 2.4)
            o.append(f'<g transform="translate({mx*S},{my*S}) rotate({ang})"><rect x="{-bw/2*S}" y="{-bh/2*S}" width="{bw*S}" height="{bh*S}" fill="{col}" rx="{2 if p["kind"]!="film" else 0}" stroke="#333" stroke-width=".6"/></g>')
            if p["kind"] == "elec":
                o.append(f'<text x="{(x1)*S}" y="{(y1-1.2)*S}" font-size="7" fill="#c33" text-anchor="middle">+</text>')
            if p["kind"] == "diode":
                o.append(f'<g transform="translate({mx*S},{my*S}) rotate({ang})"><rect x="{1.4*S}" y="{-bh/2*S}" width="{0.5*S}" height="{bh*S}" fill="#ddd"/></g>')
            if ang == 0:
                o.append(f'<text x="{mx*S}" y="{(my-1.9)*S}" font-size="7" fill="#111" text-anchor="middle" font-weight="bold">{p["ref"]}</text>')
                o.append(f'<text x="{mx*S}" y="{(my-0.7)*S}" font-size="6.5" fill="#333" text-anchor="middle">{p["value"]}</text>')
            else:
                fill = "#fff" if p["kind"] in ("elec", "diode") else "#111"
                o.append(f'<text transform="translate({mx*S},{my*S}) rotate(-90)" font-size="6.5" fill="{fill}" text-anchor="middle" dominant-baseline="middle" font-weight="bold">{p["ref"]} {p["value"]}</text>')
    o.append('</svg>')
    (OUT / "breadboard.svg").write_text("\n".join(o))

def wiring_md(exp, pin_node, find):
    L = ["# Breadboard wiring — every hole, every wire\n",
         "Generated by `layout.py` and **verified against the schematic netlist**: every net is one",
         "connected group on the board, no two nets touch, and the rails carry what they claim.",
         "Board: 830-point. Columns 1–63 left→right; rows a–e top bank, f–j bottom bank; each column",
         "of five holes is one strip. Rails: `TR+` top red = **V5**, `TR-` top blue = **GND**, `BR+`",
         "bottom red = **VANA**, `BR-` bottom blue = **GND**. `TR-@12` = the top-blue-rail hole beside column 12.",
         "Rails are assumed split at columns 31|32; four bridge wires are included (harmless if continuous).\n",
         "## Build order\n",
         "1. Rails and rail bridges, the GND-to-GND tie, then the op-amp supply wires.",
         "2. U1, U2 (notch = pin 1 toward the low column number).",
         "3. Signal chain left → right (J1 … J2), then the bias parts around U2.",
         "4. Power on the bottom bank (J3 … C12), then the three 5 V feeds top-right.",
         "5. Digital: J9, R16–R18, J10, JP3/R19, J11, R20–R22, R23/R24, J12.",
         "6. Jumper wires last, colour by colour, ticking each row below.\n",
         "## Components\n", "| ref | part | lead → hole | note |", "|---|---|---|---|"]
    for p in P:
        pins = ", ".join(f"{pin}→**{h}**" for pin, h in p["pins"])
        L.append(f"| {p['ref']} | {p['value']} ({p['kind']}) | {pins} | {p['note']} |")
    L += ["\n## Jumper wires\n", "| # | from | to | colour | purpose |", "|---|---|---|---|---|"]
    for i, w in enumerate(W, 1):
        L.append(f"| {i} | **{w['a']}** | **{w['b']}** | {w['colour']} | {w['why']} |")
    L += ["\n## Nets as built (what each strip carries)\n", "| net | pins on the board |", "|---|---|"]
    for name, pins in sorted(exp.items(), key=lambda kv: (kv[0].startswith('N$'), kv[0])):
        L.append(f"| {name} | " + ", ".join(f"{r}.{p}" for r, p in pins) + " |")
    L.append("\n`python layout.py` re-runs the check; edit the placement at the top of the file and it will refuse to write if a net splits or shorts.")
    (OUT / "WIRING.md").write_text("\n".join(L) + "\n")

if __name__ == "__main__":
    errors, exp, pin_node, find = verify()
    for e in errors: print("ERROR:", e)
    print(f"{len(P)} parts, {len(W)} wires, {len(exp)} schematic nets checked")
    if errors:
        sys.exit(1)
    print("VERIFIED: every net is one group, no shorts, rails correct")
    root_net = {pin_node[p]: name for name, pins in exp.items() for p in pins}
    groups = {}                                   # every strip / rail half -> the net it carries
    for col in range(1, 64):
        for bank in "TB":
            n = root_net.get(find(("strip", f"{bank}{col}")))
            if n: groups[f"{bank}{col}"] = n
    for rail in RAILS:
        for half in "LR":
            n = root_net.get(find(("rail", rail, half)))
            if n: groups[rail + half] = n
    (OUT / "layout.json").write_text(json.dumps(dict(parts=P, wires=W, rails=RAILS, nets=exp, group_net=groups), indent=1))
    svg(); wiring_md(exp, pin_node, find)
    print("wrote layout.json, breadboard.svg, WIRING.md")
