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
# Jumper colours are a CODE, one hue per function, so the finished board can be
# read at a glance and a mis-plugged wire stands out. Nothing electrical depends
# on them; if your jumper kit is short of a colour, substitute and note it.
# There is deliberately no WHITE and no GREY: on a cream breadboard both vanish,
# which is exactly what made the old STEP/DIR/EN and SYNC wires unreadable.
BK = "black"     # GND
RD = "red"       # VANA, the +12 V analogue rail
OR = "orange"    # V5
YL = "yellow"    # 3V3 logic supply
GN = "green"     # the audio signal path, mixer IF through to the sound card
VI = "violet"    # VREF, the half-rail bias
BL = "blue"      # SPI from the ESP32 to the ADF4351
BR = "brown"     # stepper control: STEP, DIR, EN
PK = "pink"      # SYNC, the chirp marker going back to the sound card
WIRE_FUNCTION = {BK: "GND", RD: "VANA (+12 V analogue)", OR: "V5", YL: "3V3 logic",
                 GN: "audio signal path", VI: "VREF half-rail bias",
                 BL: "SPI to the ADF4351", BR: "stepper STEP / DIR / EN",
                 PK: "SYNC to the sound card"}
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
wire("g50", "g60", BR, "J9 pin 7 STEP (col 50) -> J11 pin 3 (col 60)")
wire("g51", "g61", BR, "J9 pin 8 DIR (col 51) -> J11 pin 4 (col 61)")
wire("g52", "g62", BR, "J9 pin 9 EN (col 52) -> J11 pin 5 (col 62)")
wire("h49", "a60", PK, "J9 pin 6 SYNC (bottom col 49) up to R23 (top col 60)")

# ----------------------------------------------------------------------
# assembly steps — the build, one small verifiable move at a time
#
# Every part and every wire belongs to exactly one step; check_steps() proves it,
# so a part added to the placement above cannot be silently left out of the guide.
# Wires are keyed by their two holes, which the hole-reuse check already forces
# to be unique. Order is power first, then the op-amps, then signal left to
# right, then the digital side: each step is testable before the next one goes in.
# ----------------------------------------------------------------------
STEPS = []
def step(title, why, parts=(), wires=(), check=""):
    STEPS.append(dict(n=len(STEPS) + 1, title=title, why=why,
                      parts=list(parts), wires=[list(w) for w in wires], check=check))

step("Rails, bridged and tied",
     "Nothing works until the four rails carry what they claim. Many 830-point boards "
     "split every rail at the middle, so the right-hand half of each is dead until you "
     "bridge it — and a split you did not notice is the classic reason half a board is "
     "unpowered. The last wire ties the two GND rails into one ground.",
     wires=[("TR+@31", "TR+@32"), ("TR-@31", "TR-@32"), ("BR+@31", "BR+@32"),
            ("BR-@31", "BR-@32"), ("TR-@1", "BR-@1")],
     check="Continuity from each rail's far left hole to its far right hole. "
           "If your board's rails are continuous, these four bridges are harmless.")

step("12 V in, and the diode that saves the board",
     "J3 takes the 12 V supply. D1 is a series Schottky: get the supply backwards and "
     "it simply does not conduct, instead of taking the op-amps and the electrolytics "
     "with it. The band on the diode body is the cathode and it faces RIGHT, toward "
     "column 13. C11 is the bulk reservoir on the protected side.",
     parts=["J3", "D1", "C11", "J4"],
     wires=[("f11", "BR-@11"), ("f14", "BR-@14")],
     check="D1's band toward column 13. C11's + leg toward column 13, its - to the GND rail.")

step("The VANA rail — clean 12 V for the op-amps",
     "R15 and C13 are an RC filter, not a resistor someone forgot to remove: 10 ohms "
     "into 100 uF rolls off at about 160 Hz, which keeps supply noise out of an "
     "amplifier whose whole job is a signal down at 20 mV. The output of that filter "
     "is what feeds the bottom red rail.",
     parts=["R15", "C13"], wires=[("f16", "BR+@16")],
     check="Bottom red rail now sits at 12 V minus the diode drop, about 11.6 V.")

step("5 V in from the buck converter",
     "J5 brings 5 V back from the LM2596 after you have set it with nothing else "
     "connected. C12 decouples it and the orange wire carries it up to the top red "
     "rail, which is what the three RF modules will feed from.",
     parts=["J5", "C12"], wires=[("f19", "BR-@19"), ("g18", "TR+@18")],
     check="Set the buck to 5.00 V BEFORE this wire goes in. Top red rail = 5.00 V.")

step("Seat the two op-amps",
     "U1 is the two gain stages, U2 the reference buffer and the output. Both straddle "
     "the centre channel so the two sides of the package land on separate strips. The "
     "notch and the pin-1 dot face RIGHT, toward the higher column. C3 and C7 are the "
     "100 nF decouplers and they go right at pin 8 of each chip, not somewhere tidier.",
     parts=["U1", "U2", "C3", "C7"],
     wires=[("a5", "TR-@5"), ("a30", "TR-@30"), ("h8", "BR+@8"), ("h33", "BR+@33")],
     check="Pin 1 at e8 (U1) and e33 (U2). Power the board: both chips should sit at "
           "room temperature. A warm op-amp means V+ and V- are swapped.")

step("The half-rail reference",
     "This amplifier runs on a single supply, so 'zero' has to be manufactured: R9 and "
     "R10 divide VANA in half at column 31, C5 holds it still, and U2's second half "
     "buffers it so the divider is not loaded by everything downstream. R11 and C6 "
     "carry that buffered VREF to the node the whole signal chain hangs off.",
     parts=["R9", "R10", "C5", "R11", "C6"],
     wires=[("e36", "BR+@36"), ("j32", "j31"), ("a33", "a32"), ("b29", "b26")],
     check="VREF (column 26) should read half of VANA, about 5.8 V, and be steady.")

step("Spread VREF along the board",
     "Four violet wires, and they are the reason the amplifier has a zero to swing "
     "about. The long one runs the length of row a to reach the input stage at column "
     "1. Do them as a set so none is forgotten — a stage whose VREF is missing is not "
     "dead, it is railed, which is a more confusing symptom.",
     wires=[("a26", "a24"), ("b24", "c16"), ("d16", "d17"), ("a1", "a16")],
     check="Every violet wire end reads the same 5.8 V.")

step("The input: mixer IF, terminated",
     "R1 is the 49.9 ohm load the mixer's IF port wants; without it the conversion "
     "loss and the flatness wander. C20 shunts the LO that leaks out of that same port "
     "at 2.4 GHz, which a TL072 would otherwise rectify into a DC offset. C1 and R2 "
     "are the first high-pass, and they are what stop the TX leakage tone from "
     "saturating the gain.",
     parts=["J1", "R1", "C20", "C1", "R2"],
     wires=[("e3", "TR-@4"), ("a4", "a6")],
     check="R1 across the IF input reads 49.9 ohms to ground.")

step("Gain stage A, times 101",
     "R3 over R4 sets the gain. R4 is 1k for the full 40 dB, but fit 4.7k on first "
     "power-up for a gain of 22: if the TX leakage is stronger than you expected, a "
     "lower first gain is the difference between seeing it and clipping on it. C2 and "
     "R6 are the second high-pass into stage B.",
     parts=["R3", "C2", "R4", "R6"],
     wires=[("a8", "a10"), ("a14", "a7")],
     check="Inject 10 mV at 1 kHz: about 107 mV out of stage A with R4 at 4.7k.")

step("Gain stage B, times 11, and the anti-alias corner",
     "R7 over R8 gives the second 21 dB. R12 with C9 is the 15.9 kHz low-pass that "
     "limits the noise bandwidth reaching the sound card. The last wire takes that "
     "filtered node across the channel into U2's spare half.",
     parts=["R7", "R8", "R12", "C9"],
     wires=[("d12", "g5"), ("g7", "a19"), ("a23", "i6"), ("e22", "h30")],
     check="Total gain now about 61 dB. Sweep it: -3 dB at 15.9 kHz, -6 dB at 159 Hz.")

step("Output, isolated and bled to ground",
     "R13 and C10 hand the signal to the sound card through a series resistor, so a "
     "cable capacitance does not hang directly off an op-amp output. R14 bleeds the "
     "coupling cap so the jack is not left holding a charge, and J2 is the audio-left "
     "output to the interface.",
     parts=["R13", "C10", "R14", "J2"], wires=[("j37", "BR-@37")],
     check="Output DC near 0 V after C10. Finger on the input gives a hum: the amp is alive.")

step("Three 5 V feeds for the RF modules",
     "The ADF4351, the PA and the LNA each get a ferrite bead and their own 10 uF plus "
     "100 nF pair, so one module's switching noise does not arrive at the next one "
     "along the rail. Identical blocks at columns 38, 41 and 44 — build one, check it, "
     "then repeat it twice.",
     parts=["FB1", "C14", "C15", "J6", "FB2", "C16", "C17", "J7", "FB3", "C18", "C19", "J8"],
     wires=[("e39", "TR-@41"), ("e42", "TR-@44"), ("e45", "TR-@47")],
     check="5.00 V at all three of J6, J7, J8 with nothing plugged into them.")

step("The ESP32 header and its series resistors",
     "J9 is where the radar's ESP32 lands. R16 to R18 are 33 ohm series resistors on "
     "SCK, MOSI and LE: they damp the edges so a 2.54 mm breadboard run does not ring "
     "into the PLL's logic inputs. Each one hops the centre channel into the top bank.",
     parts=["J9", "R16", "R17", "R18"], wires=[("f44", "BR-@44")],
     check="Each resistor reads 33 ohms between its two strips, and nothing else.")

step("SPI across to the ADF4351",
     "Four blue wires carry the damped SPI and the lock-detect line up to J10. R19 "
     "pulls CE down so the synthesiser's output stays OFF until something deliberately "
     "enables it, and JP3 is the link that enables it. The yellow wire brings 3V3 over "
     "from the ESP32 — the ADF4351 board is 3.3 V logic and needs no level shifting.",
     parts=["J10", "R19", "JP3"],
     wires=[("e52", "TR-@52"), ("a46", "b53"), ("a47", "b54"), ("a48", "b55"),
            ("f48", "b56"), ("f53", "e58")],
     check="With JP3 off, CE reads 0 V. The radar must boot with RF off.")

step("The A4988 stepper header",
     "Only for the optional turntable; skip the whole step if you are not fitting one. "
     "R20 pulls EN up so the driver is disabled until the ESP32 says otherwise, and "
     "R21 and R22 pull STEP and DIR down so a floating input cannot make the motor "
     "twitch at power-up. The three brown wires are the control lines.",
     parts=["J11", "R20", "R21", "R22"],
     wires=[("f58", "BR-@58"), ("g53", "g59"), ("g50", "g60"), ("g51", "g61"), ("g52", "g62")],
     check="EN sits at 3V3, STEP and DIR at 0 V, with the ESP32 unplugged.")

step("The SYNC divider back to the sound card",
     "The last block, and the one that makes the whole radar measurable: R23 and R24 "
     "divide the ESP32's 3.3 V chirp marker down to about 0.3 V, which is a line-level "
     "signal the sound card's right channel can take. Without it the laptop cannot cut "
     "the beat signal into chirps and there is no range axis at all.",
     parts=["R23", "R24", "J12"], wires=[("e62", "TR-@62"), ("h49", "a60")],
     check="A 135 Hz square wave of about 0.3 V at J12 once radar_ctl is running.")

step("Before you power anything",
     "The board is finished. These are the measurements that catch a build error while "
     "it is still cheap, with the supply DISCONNECTED and nothing plugged into the "
     "headers.",
     check="Ohm-meter, all with power off: GND to VANA, GND to V5 and GND to 3V3 must "
           "each read open (over 1 kohm). Any of them near zero is a short — find it "
           "before you connect 12 V. Then work the test cards in hardware/spice/.")


def check_steps():
    """Every part and every wire in exactly one step, and every reference real."""
    errs = []
    refs = {p["ref"] for p in P}
    holes = {(w["a"], w["b"]) for w in W}
    seen_p, seen_w = {}, {}
    for st in STEPS:
        for r in st["parts"]:
            if r not in refs: errs.append(f"step {st['n']} lists unknown part {r}")
            elif r in seen_p: errs.append(f"{r} is in step {seen_p[r]} and step {st['n']}")
            else: seen_p[r] = st["n"]
        for a, b in st["wires"]:
            if (a, b) not in holes: errs.append(f"step {st['n']} lists unknown wire {a}-{b}")
            elif (a, b) in seen_w: errs.append(f"wire {a}-{b} is in step {seen_w[(a,b)]} and step {st['n']}")
            else: seen_w[(a, b)] = st["n"]
    for r in sorted(refs - set(seen_p)): errs.append(f"{r} is in no assembly step")
    for a, b in sorted(holes - set(seen_w)): errs.append(f"wire {a}-{b} is in no assembly step")
    return errs


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

# Rendered hues, chosen to stay apart from each other AND from the #f4f1e8 board.
COLOURS = {"black": "#14181d", "red": "#cc2b2b", "orange": "#e2701a", "yellow": "#c8951a",
           "green": "#1f9153", "violet": "#7a4fbf", "blue": "#2f77b0", "brown": "#8a5a2b",
           "pink": "#e0669a"}
LEAD = "#5f6670"          # component leads and DIP legs: dark enough to read on cream
GHOST = 0.38              # "already built": faded AND desaturated, like a Lego manual
HALO  = "#ffd24a"         # highlight behind whatever this step adds


def swatch(o, S, x, y, name):
    """One colour-key entry. Returns the x to start the next one at.

    The advance is measured from the label, not guessed: at font-size 8 on a
    5 px/mm grid a monospace character is about 0.98 mm wide. Guessing is what
    made the step legends print on top of each other."""
    label = f"{name} — {WIRE_FUNCTION[name]}"
    o.append(f'<rect x="{x*S}" y="{(y-1.7)*S}" width="{2.2*S}" height="{2.2*S}" rx="2" '
             f'fill="{COLOURS[name]}" stroke="#00000040" stroke-width=".8"/>')
    o.append(f'<text x="{(x+3.0)*S}" y="{y*S}" font-size="8" fill="#333">{esc(label)}</text>')
    return x + 3.0 + 0.98 * len(label) + 3.4


def legend(o, S, W_, H_, active):
    """Colour key along the bottom: one swatch per function, plus the step caption."""
    y = 49.5 if active is None else 48.5
    if active is not None:
        st = STEPS[active - 1]
        o.append(f'<text x="{7*S}" y="{y*S}" font-size="11" font-weight="bold" fill="#14181d">'
                 f'Step {st["n"]} of {len(STEPS)} — {esc(st["title"])}</text>')
        used = {w["colour"] for w in W if [w["a"], w["b"]] in st["wires"]}
        if used:
            x = 7.0
            for name in [c for c in WIRE_FUNCTION if c in used]:
                x = swatch(o, S, x, y + 3.1, name)
        return
    o.append(f'<text x="{7*S}" y="{y*S}" font-size="9" font-weight="bold" fill="#14181d">'
             f'JUMPER COLOUR CODE — one hue per function. No white, no grey: both vanish on a cream board.</text>')
    x, yy = 7.0, y + 3.7
    for i, name in enumerate(WIRE_FUNCTION):
        if i == 5: x, yy = 7.0, yy + 4.2
        x = swatch(o, S, x, yy, name)


def esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def svg(active=None, path=None):
    """Top view. active=None draws the finished board; active=N draws assembly
    step N: everything from earlier steps ghosted back, this step's parts and
    wires in full colour with a halo, and later steps not drawn at all."""
    step_of_part = {r: st["n"] for st in STEPS for r in st["parts"]}
    step_of_wire = {(a, b): st["n"] for st in STEPS for a, b in st["wires"]}
    def state(n):
        if active is None: return "on"
        if n is None or n > active: return "off"
        return "on" if n == active else "ghost"
    S = 5.0; W_, H_ = 170, 47 + (12 if active is None else 9)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W_*S} {H_*S}" width="{W_*S}" height="{H_*S}" font-family="IBM Plex Mono, DejaVu Sans Mono, monospace">',
         '<defs><filter id="built" color-interpolation-filters="sRGB">'
         '<feColorMatrix type="saturate" values="0.08"/></filter></defs>',
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
        st = state(step_of_wire.get((w["a"], w["b"])))
        if st == "off": continue
        (x1, y1), (x2, y2) = hole_xy(w["a"]), hole_xy(w["b"]); c = COLOURS[w["colour"]]
        sag = -max(1.5, abs(x2 - x1) * 0.12) if (y1 + y2) / 2 < 22 else max(1.5, abs(x2 - x1) * 0.12)
        # Parallel runs (STEP/DIR/EN, the SPI group) share a row and a span, so
        # one sag draws them all on top of each other and a bundle of three
        # looks like one wire. Fan them by a hole's worth, keyed off the start
        # column so the fan is stable between renders.
        sag += (parse(w["a"])[3] % 3 - 1) * (0.9 if sag > 0 else -0.9)
        d = f'M{x1*S},{y1*S} Q{(x1+x2)/2*S},{((y1+y2)/2+sag)*S} {x2*S},{y2*S}'
        o.append(f'<g opacity="{GHOST}" filter="url(#built)">' if st == "ghost" else '<g>')
        if st == "on" and active is not None:      # halo so the new wire reads instantly
            o.append(f'<path d="{d}" fill="none" stroke="{HALO}" stroke-width="8" stroke-linecap="round" opacity=".55"/>')
        # a thin dark casing keeps every hue apart from the cream board
        o.append(f'<path d="{d}" fill="none" stroke="#00000030" stroke-width="4.6" stroke-linecap="round"/>')
        o.append(f'<path d="{d}" fill="none" stroke="{c}" stroke-width="3" stroke-linecap="round"/>')
        o.append(f'<circle cx="{x1*S}" cy="{y1*S}" r="2.4" fill="{c}" stroke="#00000040" stroke-width=".8"/>'
                 f'<circle cx="{x2*S}" cy="{y2*S}" r="2.4" fill="{c}" stroke="#00000040" stroke-width=".8"/>')
        o.append('</g>')
    # parts
    for p in P:
        st = state(step_of_part.get(p["ref"]))
        if st == "off": continue
        pts = [hole_xy(h) for _, h in p["pins"]]
        if st == "on" and active is not None:      # halo behind the part being added
            hx = [q[0] for q in pts]; hy = [q[1] for q in pts]
            o.append(f'<rect x="{(min(hx)-2.6)*S}" y="{(min(hy)-2.6)*S}" '
                     f'width="{(max(hx)-min(hx)+5.2)*S}" height="{(max(hy)-min(hy)+5.2)*S}" '
                     f'fill="{HALO}" opacity=".5" rx="{2.4*S}"/>')
        o.append(f'<g opacity="{GHOST}" filter="url(#built)">' if st == "ghost" else '<g>')
        if p["kind"] == "dip8":
            # true to life: 9.9 x 6.4 mm body on 7.62 mm row spacing, notch at the pin-1/pin-8 end (right), dot beside pin 1
            xs_ = [q[0] for q in pts]; xc = (min(xs_) + max(xs_)) / 2; x0, x1 = xc - 4.95, xc + 4.95
            yc = (pts[0][1] + pts[4][1]) / 2; y0, y1 = yc - 3.2, yc + 3.2
            for (pin, h), (x, y) in zip(p["pins"], pts):     # legs from the body edge into the holes
                o.append(f'<line x1="{x*S}" y1="{(y0 if h[0]=="e" else y1)*S}" x2="{x*S}" y2="{y*S}" stroke="{LEAD}" stroke-width="3"/>')
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
            # A wide header has room for its own name; putting it inside the body
            # is the only way to stop J9/J10/J11 colliding with the resistors
            # packed around them. Narrow 2-pin headers keep the label outside.
            if len(p["pins"]) >= 4:
                o.append(f'<text x="{(x0+x1)/2*S}" y="{(y+0.5)*S}" font-size="6.6" fill="#f4f1e8" '
                         f'text-anchor="middle" font-weight="bold">{esc(p["ref"] + " " + p["value"])}</text>')
            else:
                o.append(f'<text x="{(x0+x1)/2*S}" y="{(y + (3.4 if y > 22 else -2.2))*S}" font-size="7.5" '
                         f'fill="#222" text-anchor="middle" font-weight="bold" stroke="#f4f1e8" '
                         f'stroke-width="2.6" paint-order="stroke">{esc(p["ref"])}</text>')
        else:
            (x1, y1), (x2, y2) = pts; col = {"res": "#d9c39a", "film": "#d8b53a", "cer": "#d08a3a", "elec": "#2a3140", "diode": "#222", "bead": "#666"}[p["kind"]]
            o.append(f'<line x1="{x1*S}" y1="{y1*S}" x2="{x2*S}" y2="{y2*S}" stroke="{LEAD}" stroke-width="1.5"/>')
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2; ang = 0 if abs(x2 - x1) >= abs(y2 - y1) else 90
            bw, bh = (5.5, 2.2) if p["kind"] in ("res", "diode") else (3.4, 2.4)
            o.append(f'<g transform="translate({mx*S},{my*S}) rotate({ang})"><rect x="{-bw/2*S}" y="{-bh/2*S}" width="{bw*S}" height="{bh*S}" fill="{col}" rx="{2 if p["kind"]!="film" else 0}" stroke="#333" stroke-width=".6"/></g>')
            if p["kind"] == "elec":
                o.append(f'<text x="{(x1)*S}" y="{(y1-1.2)*S}" font-size="7" fill="#c33" text-anchor="middle">+</text>')
            if p["kind"] == "diode":
                o.append(f'<g transform="translate({mx*S},{my*S}) rotate({ang})"><rect x="{1.4*S}" y="{-bh/2*S}" width="{0.5*S}" height="{bh*S}" fill="#ddd"/></g>')
            if ang == 0:
                o.append(f'<text x="{mx*S}" y="{(my-1.9)*S}" font-size="7" fill="#111" text-anchor="middle" font-weight="bold" stroke="#f4f1e8" stroke-width="2.6" paint-order="stroke">{p["ref"]}</text>')
                o.append(f'<text x="{mx*S}" y="{(my-0.7)*S}" font-size="6.5" fill="#333" text-anchor="middle" stroke="#f4f1e8" stroke-width="2.6" paint-order="stroke">{p["value"]}</text>')
            else:
                fill = "#fff" if p["kind"] in ("elec", "diode") else "#111"
                o.append(f'<text transform="translate({mx*S},{my*S}) rotate(-90)" font-size="6.5" fill="{fill}" text-anchor="middle" dominant-baseline="middle" font-weight="bold" stroke="{"#1b1f24" if fill == "#fff" else "#f4f1e8"}" stroke-width="2.2" paint-order="stroke">{p["ref"]} {p["value"]}</text>')
        o.append('</g>')
    legend(o, S, W_, H_, active)
    o.append('</svg>')
    (path or (OUT / "breadboard.svg")).write_text("\n".join(o))

def assembly_md():
    """ASSEMBLY.md — the build as numbered steps, one picture each.

    Each picture shows the board as it should look when that step is done: what
    you already built ghosted back, what this step adds in full colour. Nothing
    here is hand-written twice — the parts, the wires and the holes all come from
    the same placement the netlist check runs against."""
    by_ref = {q["ref"]: q for q in P}
    by_holes = {(w["a"], w["b"]): w for w in W}
    L = ["# Building the breadboard, step by step\n",
         "Seventeen steps. Each one adds a handful of parts, ends with something you can",
         "measure, and has a picture of the board as it should look when you are done.",
         "**Build in this order**: power first so every later stage has something to run",
         "on, then the op-amps, then the signal left to right, then the digital side.\n",
         "Generated by `layout.py` from the same placement the schematic check runs",
         "against, so these steps cannot drift from [`WIRING.md`](WIRING.md) or from the",
         "board. `python3 layout.py` rebuilds the lot.\n",
         "## Before you start\n",
         "| | |",
         "|---|---|",
         "| board | 830-point breadboard. Columns **1–63** left to right; rows **a–e** are the top bank, **f–j** the bottom. The five holes of one column in one bank are a single strip. |",
         "| hole names | `b14` = row b, column 14. `TR-@12` = the **top blue** rail, hole nearest column 12 — on a real board just use the closest free rail hole. |",
         "| rails | top red **V5**, top blue **GND**, bottom red **VANA** (+12 V analogue), bottom blue **GND**. |",
         "| tools | a fine pair of snips, tweezers, a multimeter. No soldering: everything here pushes in. |",
         "\n### The jumper colour code\n",
         "One hue per function, so a finished board can be read at a glance and a wire in",
         "the wrong place stands out. Nothing electrical depends on it — if your jumper",
         "kit is short of a colour, substitute one and note it on the sheet.\n",
         "| colour | carries |", "|---|---|"]
    for c, what in WIRE_FUNCTION.items():
        n = sum(1 for w in W if w["colour"] == c)
        L.append(f"| **{c}** | {what} — {n} wire{'s' if n != 1 else ''} |")
    L += ["", "There is deliberately **no white and no grey wire** anywhere in this build: on a",
          "cream breadboard both disappear, and the three stepper lines and the SYNC line",
          "used to be exactly that. They are brown and pink now.\n", "---\n"]
    for st in STEPS:
        L.append(f"## Step {st['n']} — {st['title']}\n")
        L.append(f"![step {st['n']}](steps/step-{st['n']:02d}.png)\n")
        L.append(st["why"] + "\n")
        if st["parts"]:
            L += ["| part | value | push it in at |", "|---|---|---|"]
            for r in st["parts"]:
                q = by_ref[r]
                where = ", ".join(f"{pin}→**{h}**" for pin, h in q["pins"])
                L.append(f"| {r} | {q['value']} | {where} |")
            L.append("")
        if st["wires"]:
            L += ["| wire | colour | from → to | what it does |", "|---|---|---|---|"]
            for i, (a, b) in enumerate(st["wires"], 1):
                w = by_holes[(a, b)]
                L.append(f"| {i} | {w['colour']} | **{a}** → **{b}** | {w['why']} |")
            L.append("")
        if st["check"]:
            L.append(f"> **Check before moving on.** {st['check']}\n")
        L.append("---\n")
    L += ["## When it is all in\n",
          "The finished board: [`breadboard.png`](breadboard.png), every hole and net in",
          "[`WIRING.md`](WIRING.md), and [`breadboard.html`](breadboard.html) if you want",
          "to hover a part and see what it touches.\n",
          "Simulate before you trust it — `../spice/README.md` has one test card per block,",
          "with the stimulus and the reading to expect.\n"]
    (OUT / "ASSEMBLY.md").write_text("\n".join(L) + "\n")


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
    (OUT / "layout.json").write_text(json.dumps(dict(parts=P, wires=W, rails=RAILS, nets=exp, group_net=groups, steps=STEPS, wire_function=WIRE_FUNCTION), indent=1))
    if errs := check_steps():
        for e in errs: print("STEP ERROR:", e)
        sys.exit(1)
    print(f"{len(STEPS)} assembly steps cover every part and every wire exactly once")
    svg(); wiring_md(exp, pin_node, find)
    sd = OUT / "steps"; sd.mkdir(exist_ok=True)
    for st in STEPS:
        svg(active=st["n"], path=sd / f"step-{st['n']:02d}.svg")
    assembly_md()
    print(f"wrote layout.json, breadboard.svg, WIRING.md, ASSEMBLY.md, steps/ ({len(STEPS)} svg)")
