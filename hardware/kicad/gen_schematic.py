#!/usr/bin/env python3
"""gen_schematic.py — the full sheet: breadboard (left) + system it connects to (right).
See kicad_lib.py for the library/writer. Usage: python gen_schematic.py"""
from kicad_lib import *
import kicad_lib

# ======================================================================
# LEFT HALF — THE BREADBOARD
# ======================================================================
note("BREADBOARD  —  what you actually build (video amp, bias, power, harness)", 15, 22, 2.5, True)
note("Mixer IF in on a shielded pigtail. 49.9 R + 1 nF FIRST, right at the input.", 15, 27, 1.5)

# --- row A: signal chain -------------------------------------------------
J1 = place(hdr(2, "right"), 20, 60, "MIXER IF", ref="J1"); note("mixer IF pigtail", 14, 67, 1.1)          # pins (25.08,60) (25.08,57.46)
# hdr pins go downward from y: pin1 at y, pin2 at y+2.54 (lib y negative -> sheet +)
w(J1["pins"]["1"], (28, 60), (35, 60)); J(35, 60); lbl("IF", 28, 60)
gnd(25.08, 57.46 + 2.54 * 2)  # placeholder removed below
symbols.pop()                                                   # (keep helper simple)
w(J1["pins"]["2"], (28, 62.54)); gnd(28, 62.54)
R1 = R("R1", "49.9", 35, 70); w((35, 60), R1["pins"]["1"]); gnd(35, 73.81)
Crf = C("C20", "1n", 42, 70); w((35, 60), (42, 60), Crf["pins"]["1"]); J(42, 60); gnd(42, 73.81)
C1 = C("C1", "100n", 52, 60, 90); w((42, 60), C1["pins"]["1"])
w(C1["pins"]["2"], (62, 60)); J(62, 60)
R2 = R("R2", "10k", 62, 70); w((62, 60), R2["pins"]["1"]); lbl("VREF", 62, 73.81, 0, "left")
U1A = place("Amplifier_Operational:TL072", 78, 62.54, "TL072", unit=1, ref="U1")
w((62, 60), U1A["pins"]["3"])
w(U1A["pins"]["1"], (88, 62.54)); J(88, 62.54)
R3 = R("R3", "100k", 78, 50, 90); w((88, 62.54), (88, 50), R3["pins"]["2"])
w(R3["pins"]["1"], (66, 50), (66, 65.08), U1A["pins"]["2"]); J(66, 65.08)
R4 = R("R4", "1k", 66, 72); w((66, 65.08), R4["pins"]["1"]); lbl("VREF", 66, 75.81)
note("U1A gain 1+R3/R4 = 101  (4.7k here -> 22 for first power-up)", 62, 44, 1.2)
C2 = C("C2", "100n", 95, 62.54, 90); w((88, 62.54), C2["pins"]["1"])
w(C2["pins"]["2"], (104, 62.54)); J(104, 62.54)
R6 = R("R6", "10k", 104, 70); w((104, 62.54), R6["pins"]["1"]); lbl("VREF", 104, 73.81)
U1B = place("Amplifier_Operational:TL072", 118, 65.08, "TL072", unit=2, ref="U1")
w((104, 62.54), U1B["pins"]["5"])
w(U1B["pins"]["7"], (128, 65.08)); J(128, 65.08)
R7 = R("R7", "10k", 118, 52, 90); w((128, 65.08), (128, 52), R7["pins"]["2"])
w(R7["pins"]["1"], (108, 52), (108, 67.62), U1B["pins"]["6"]); J(108, 67.62)
R8 = R("R8", "1k", 108, 74); w((108, 67.62), R8["pins"]["1"]); lbl("VREF", 108, 77.81)
note("U1B gain 1+R7/R8 = 11", 108, 46, 1.2)
R12 = R("R12", "1k", 135, 65.08, 90); w((128, 65.08), R12["pins"]["1"])
w(R12["pins"]["2"], (142, 65.08)); J(142, 65.08)
C9 = C("C9", "10n", 142, 72); w((142, 65.08), C9["pins"]["1"]); lbl("VREF", 142, 75.81)
note("R12/C9 = 15.9 kHz LP", 136, 80, 1.2)
U2B = place("Amplifier_Operational:TL072", 156, 67.62, "TL072", unit=2, ref="U2")
w((142, 65.08), U2B["pins"]["5"])
w(U2B["pins"]["7"], (166, 67.62)); J(166, 67.62)
w((166, 67.62), (166, 74), (146, 74), (146, 70.16), U2B["pins"]["6"])
R13 = R("R13", "100", 172, 67.62, 90); w((166, 67.62), R13["pins"]["1"])
C10 = C("C10", "10u", 182, 67.62, 90, pol=True); w(R13["pins"]["2"], C10["pins"]["1"])
w(C10["pins"]["2"], (190, 67.62)); J(190, 67.62)
R14 = R("R14", "100k", 190, 75); w((190, 67.62), R14["pins"]["1"]); gnd(190, 78.81)
J2 = place(hdr(2, "left"), 198, 67.62, "AUDIO L", ref="J2")
w((190, 67.62), J2["pins"]["1"]); lbl("AUDIO_L", 190, 67.62)
w(J2["pins"]["2"], (192.92, 72)); gnd(192.92, 72)
note("-> UCA202 LEFT (shielded lead)", 186, 78, 1.2)

# --- row B: reference, VANA, op-amp power ------------------------------------
note("Half-rail reference VREF = VANA/2, buffered", 15, 92, 1.4, True)
rail("VANA", 30, 98)
R9 = R("R9", "10k", 30, 104); w((30, 98), R9["pins"]["1"])
w(R9["pins"]["2"], (30, 112)); J(30, 112)
R10 = R("R10", "10k", 30, 118); w((30, 112), R10["pins"]["1"]); gnd(30, 121.81)
C5 = C("C5", "10u", 38, 118, pol=True); w((30, 112), (38, 112), C5["pins"]["1"]); J(38, 112); gnd(38, 121.81)
U2A = place("Amplifier_Operational:TL072", 52, 114.54, "TL072", unit=1, ref="U2")
w((38, 112), U2A["pins"]["3"])
w(U2A["pins"]["1"], (62, 114.54)); J(62, 114.54)
w((62, 114.54), (62, 121), (42, 121), (42, 117.08), U2A["pins"]["2"])
R11 = R("R11", "47", 68, 114.54, 90); w((62, 114.54), R11["pins"]["1"])
w(R11["pins"]["2"], (76, 114.54), (80, 114.54)); J(76, 114.54); lbl("VREF", 80, 114.54)
C6 = C("C6", "47u", 76, 122, pol=True); w((76, 114.54), C6["pins"]["1"]); gnd(76, 125.81)

note("12 V in -> D1 -> VPROT -> R15/C13 -> VANA (op-amp rail, ~11 V)", 92, 92, 1.4, True)
J3 = place(hdr(2, "left"), 128, 100, "12V IN", ref="J3")
D1 = place("Device:D_Schottky", 112, 100, "1N5822", ref="D1", vpos=(108, 104.5), rpos=(110.5, 97.5))
w(J3["pins"]["1"], D1["pins"]["A"]); lbl("VIN12", 119, 100)
note("12 V IN (J3)  /  TO BUCK IN (J4)", 118, 94, 1.1)
w(J3["pins"]["2"], (122.92, 104)); gnd(122.92, 104)
w(D1["pins"]["K"], (100, 100)); J(100, 100); lbl("VPROT", 100, 100)
C11 = C("C11", "100u", 100, 108, pol=True); w((100, 100), C11["pins"]["1"]); gnd(100, 111.81)
R15 = R("R15", "10", 92, 108); w((100, 100), (92, 100), R15["pins"]["1"])
w(R15["pins"]["2"], (92, 115)); rail("VANA", 92, 115)   # rail symbol pin at its origin
C13 = C("C13", "100u", 84, 122, pol=True); w((92, 115), (84, 115), C13["pins"]["1"]); J(92, 115); gnd(84, 125.81)
J4 = place(hdr(2, "left"), 128, 110, "TO BUCK IN", ref="J4")
w(J4["pins"]["1"], (118, 110)); lbl("VPROT", 118, 110, 0, "right")
w(J4["pins"]["2"], (122.92, 114)); gnd(122.92, 114)
# op-amp supply pins + decoupling
for ref, x in (("U1", 150), ("U2", 176)):
    Up = place("Amplifier_Operational:TL072", x, 104, "TL072", unit=3, ref=ref, hide_value=True)
    rail("VANA", x, 96.38); gnd(x, 111.62)
Cd = C("C3", "100n", 162, 104); rail("VANA", 162, 100.19); gnd(162, 107.81)
Cd = C("C7", "100n", 188, 104); rail("VANA", 188, 100.19); gnd(188, 107.81)
note("100 nF at each TL072 V+ pin", 148, 118, 1.2)

# --- row C: 5 V distribution ------------------------------------------------
note("5 V from the LM2596, ferrite + 10u + 100n per RF module", 15, 134, 1.4, True)
J5 = place(hdr(2, "right"), 20, 145, "FROM BUCK 5V", ref="J5"); note("from LM2596 OUT", 14, 152.5, 1.1)
w(J5["pins"]["1"], (32, 145)); J(32, 145); rail("V5", 32, 141)
w((32, 145), (32, 141))
w(J5["pins"]["2"], (28, 148)); gnd(28, 148)
C12 = C("C12", "100u", 32, 152, pol=True); w((32, 145), C12["pins"]["1"]); gnd(32, 155.81)
for i, (net, y, cref, jref, jval) in enumerate([("V5_ADF", 140, ("C14", "C15"), "J6", "ADF4351 5V"),
                                                 ("V5_PA", 156, ("C16", "C17"), "J7", "PA 5V"),
                                                 ("V5_LNA", 172, ("C18", "C19"), "J8", "LNA 5V")]):
    FB = place("Device:FerriteBead", 46, y, "FB", 90, ref=f"FB{i+1}")
    w((36, 145), (36, y), FB["pins"]["1"])
    if i == 0:
        w((32, 145), (36, 145)); J(36, 145)
    if i == 1:
        J(36, 156)
    w(FB["pins"]["2"], (54, y), (62, y), (70.92, y)); J(54, y); J(62, y)
    Ca = C(cref[0], "10u", 54, y + 7, pol=True); w((54, y), Ca["pins"]["1"]); gnd(54, y + 10.81)
    Cb = C(cref[1], "100n", 62, y + 7); w((62, y), Cb["pins"]["1"]); gnd(62, y + 10.81)
    Jx = place(hdr(2, "left"), 76, y, jval, ref=jref)
    lbl(net, 62, y); note(jval, 80, y + 1, 1.1)
    w(Jx["pins"]["2"], (70.92, y + 5)); gnd(70.92, y + 5)
# fix the FB wire for the last one: the vertical trunk from (36,145) down to 172 goes through 156
wires[:] = [x for x in wires if x != ((36, 145), (36, 156))]   # dedupe overlapping trunk pieces
wires[:] = [x for x in wires if x != ((36, 145), (36, 140))]
w((36, 140), (36, 172))

# --- row D: ESP32 harness, ADF logic, A4988 logic, sync divider --------------
note("ESP32 harness (J9) -> ADF4351 logic (J10, 33 R series) and A4988 logic (J11)", 96, 134, 1.4, True)
J9 = place(hdr(10, "right"), 96, 142, "ESP32", ref="J9")
for i, n in enumerate(["GND", "SCK", "MOSI", "LE", "LD", "SYNC", "STEP", "DIR", "EN", "+3V3"]):
    p = J9["pins"][str(i + 1)]
    if n == "GND":
        w(p, (p[0] + 3, p[1])); gnd(p[0] + 3, p[1])
    elif n == "+3V3":
        w(p, (p[0] + 3, p[1])); rail("+3V3", p[0] + 3, p[1])
    else:
        w(p, (p[0] + 4, p[1])); lbl(n, p[0] + 4, p[1])
note("J9: GPIO18 23 5 19 25 26 27 14, 3V3 from the devkit", 96, 170, 1.1)
J10 = place(hdr(6, "left"), 166, 142, "ADF LOGIC", ref="J10"); note("to ADF4351 logic pins", 170, 150, 1.1)
w(J10["pins"]["1"], (156, 142)); gnd(156, 142)
for i, (n, ref) in enumerate([("SCK", "R16"), ("MOSI", "R17"), ("LE", "R18")]):
    y = 142 + 2.54 * (i + 1)
    Rs = R(ref, "33", 134, y, 90, ); Rs["hide_value"] = True; Rs["rpos"] = (131, y - 1.2)
    w((124, y), Rs["pins"]["1"]); lbl(n, 124, y, 0, "right")
    w(Rs["pins"]["2"], (146, y), J10["pins"][str(i + 2)]); lbl(n + "_O", 146, y)
w(J10["pins"]["5"], (152, 152.16)); lbl("LD", 152, 152.16, 0, "right")
w(J10["pins"]["6"], (146, 154.7)); J(146, 154.7)
R19 = R("R19", "10k", 146, 162); w((146, 154.7), R19["pins"]["1"]); gnd(146, 165.81)
JP3 = place(hdr(2, "right"), 128, 154.7, "JP3 CE EN", ref="JP3"); note("JP3: CE enable", 120, 162, 1.1)
w(JP3["pins"]["1"], (140, 154.7), (146, 154.7)); lbl("CE", 140, 154.7)
w(JP3["pins"]["2"], (136, 157.24)); rail("+3V3", 136, 157.24)
J11 = place(hdr(5, "left"), 166, 176, "A4988 LOGIC", ref="J11"); note("to A4988 logic pins", 170, 190, 1.1)
w(J11["pins"]["1"], (156, 176)); gnd(156, 176)
w(J11["pins"]["2"], (154, 178.54)); rail("+3V3", 154, 178.54)
for i, n in enumerate(["STEP", "DIR", "EN"]):
    p = J11["pins"][str(i + 3)]
    w(p, (p[0] - 5, p[1])); lbl(n, p[0] - 5, p[1], 0, "right")
R20 = R("R20", "10k", 184, 150); rail("+3V3", 184, 146.19)
w(R20["pins"]["2"], (184, 156)); lbl("EN", 184, 156)
R21 = R("R21", "10k", 192, 150); lbl("STEP", 192, 145); w(R21["pins"]["1"], (192, 145)); gnd(192, 153.81)
R22 = R("R22", "10k", 200, 150); lbl("DIR", 200, 145); w(R22["pins"]["1"], (200, 145)); gnd(200, 153.81)
note("EN pull-up = motor off until firmware", 178, 162, 1.1)
# sync divider
R23 = R("R23", "10k", 182, 200, 90); lbl("SYNC", 176, 200, 0, "right"); w((176, 200), R23["pins"]["1"])
w(R23["pins"]["2"], (190, 200)); J(190, 200)
R24 = R("R24", "1k", 190, 206); w((190, 200), R24["pins"]["1"]); gnd(190, 209.81)
J12 = place(hdr(2, "left"), 200, 200, "AUDIO R", ref="J12")
w((190, 200), J12["pins"]["1"]); lbl("AUDIO_R", 190, 200)
w(J12["pins"]["2"], (194.92, 205)); gnd(194.92, 205)
note("0.3 V sync -> UCA202 RIGHT (J12)", 172, 214, 1.2)

# ======================================================================
# RIGHT HALF — THE SYSTEM AROUND IT
# ======================================================================
note("SYSTEM  —  what the breadboard connects to (all 2.4 GHz on SMA coax, never on the breadboard)", 222, 22, 2.5, True)

PSU = place(block("PSU_12V_3A", [], ["+12V", "GND"]), 240, 40, "12 V 3 A supply", ref="PS1")
w(PSU["pins"]["+12V"], (262, 41.27)); lbl("VIN12", 262, 41.27)
w(PSU["pins"]["GND"], (258, 43.81)); gnd(258, 43.81)
note("fuse 1 A in the +12 V lead", 222, 52, 1.1)

BUCK = place(block("LM2596_buck", ["IN+", "IN-"], ["OUT+", "OUT-"]), 240, 66, "LM2596 -> 5.00 V", ref="PS2")
w(BUCK["pins"]["IN+"], (218, 67.27)); lbl("VPROT", 218, 67.27, 0, "right")
w(BUCK["pins"]["IN-"], (222, 69.81)); gnd(222, 69.81)
w(BUCK["pins"]["OUT+"], (262, 67.27)); lbl("V5", 262, 67.27)
w(BUCK["pins"]["OUT-"], (258, 69.81)); gnd(258, 69.81)
note("set 5.00 V BEFORE connecting J5", 222, 76, 1.1)

ESP = place(block("ESP32_devkit", ["USB"], ["GPIO18 SCK", "GPIO23 MOSI", "GPIO5 LE", "GPIO19 LD",
                                            "GPIO25 SYNC", "GPIO26 STEP", "GPIO27 DIR", "GPIO14 EN",
                                            "3V3", "GND"], 30.48), 240, 110, "ESP32 devkit (radar_ctl)", ref="A1")
for pn, net in [("GPIO18 SCK", "SCK"), ("GPIO23 MOSI", "MOSI"), ("GPIO5 LE", "LE"), ("GPIO19 LD", "LD"),
                ("GPIO25 SYNC", "SYNC"), ("GPIO26 STEP", "STEP"), ("GPIO27 DIR", "DIR"), ("GPIO14 EN", "EN")]:
    p = ESP["pins"][pn]; w(p, (p[0] + 4, p[1])); lbl(net, p[0] + 4, p[1])
p = ESP["pins"]["3V3"]; w(p, (p[0] + 3, p[1])); rail("+3V3", p[0] + 3, p[1])
p = ESP["pins"]["GND"]; w(p, (p[0] + 3, p[1])); gnd(p[0] + 3, p[1])
p = ESP["pins"]["USB"]; w(p, (p[0] - 4, p[1])); lbl("USB laptop", p[0] - 4, p[1], 0, "right")

# --- TX chain (y = 50) ---
ADF = place(block("ADF4351_module", ["5V", "GND", "CLK", "DATA", "LE", "CE", "LD"], ["RF OUT"], 25.4), 296, 52, "ADF4351 board", ref="M1")
for pn, net in [("CLK", "SCK_O"), ("DATA", "MOSI_O"), ("LE", "LE_O"), ("CE", "CE"), ("LD", "LD")]:
    p = ADF["pins"][pn]; w(p, (p[0] - 4, p[1])); lbl(net, p[0] - 4, p[1], 0, "right")
p = ADF["pins"]["5V"]; w(p, (p[0] - 4, p[1])); lbl("V5_ADF", p[0] - 4, p[1], 0, "right")
p = ADF["pins"]["GND"]; w(p, (p[0] - 3, p[1])); gnd(p[0] - 3, p[1])
yrf = ADF["pins"]["RF OUT"][1]
ATT = place(block("ATT_3dB", ["IN"], ["OUT"], 12.7), ADF["pins"]["RF OUT"][0] + 8.89, yrf, "3 dB pad", ref="M2")
w(ADF["pins"]["RF OUT"], ATT["pins"]["IN"]); note("+5 dBm", ADF["pins"]["RF OUT"][0] - 1, yrf - 4, 1.0)
PA = place(block("PA_SPF5189Z", ["IN", "5V", "GND"], ["OUT"], 17.78), ATT["pins"]["OUT"][0] + 11.43, yrf + 2.54, "PA module", ref="M3")
w(ATT["pins"]["OUT"], PA["pins"]["IN"]); note("+2", ATT["pins"]["OUT"][0] - 1, yrf - 4, 1.0)
p = PA["pins"]["5V"]; w(p, (p[0] - 5, p[1])); lbl("V5_PA", p[0] - 5, p[1], 0, "right")
p = PA["pins"]["GND"]; w(p, (p[0] - 3, p[1])); gnd(p[0] - 3, p[1])
SPL = place(block("Splitter_2way", ["S"], ["OUT1", "OUT2"], 15.24), PA["pins"]["OUT"][0] + 10.16, PA["pins"]["OUT"][1] + 1.27, "2-way splitter", ref="M4")
w(PA["pins"]["OUT"], SPL["pins"]["S"]); note("+14 dBm", PA["pins"]["OUT"][0] - 2, yrf - 4, 1.0)
TXH = place(block("Horn_TX", ["RF"], [], 12.7), SPL["pins"]["OUT1"][0] + 8.89, SPL["pins"]["OUT1"][1], "TX horn 13.4 dBi", ref="AE1")
w(SPL["pins"]["OUT1"], TXH["pins"]["RF"]); note("+10.5 dBm -> +23 dBm EIRP", SPL["pins"]["OUT1"][0] - 6, yrf + 14, 1.0)

# --- RX chain (y = 95) ---
RXH = place(block("Horn_RX", [], ["RF"], 12.7), 296, 100, "RX horn 13.4 dBi", ref="AE2")
BPF = place(block("BPF_2400_2500", ["IN"], ["OUT"], 15.24), RXH["pins"]["RF"][0] + 10.16, 100, "band-pass 2400-2500", ref="M5")
w(RXH["pins"]["RF"], BPF["pins"]["IN"])
LNA = place(block("LNA_SPF5189Z", ["IN", "5V", "GND"], ["OUT"], 17.78), BPF["pins"]["OUT"][0] + 11.43, 100 + 2.54, "LNA module", ref="M6")
w(BPF["pins"]["OUT"], LNA["pins"]["IN"])
p = LNA["pins"]["5V"]; w(p, (p[0] - 5, p[1])); lbl("V5_LNA", p[0] - 5, p[1], 0, "right")
p = LNA["pins"]["GND"]; w(p, (p[0] - 3, p[1])); gnd(p[0] - 3, p[1])
MIX = place(block("Mixer_ZX05-43MH", ["LO", "RF"], ["IF"], 20.32), LNA["pins"]["OUT"][0] + 20, 100 + 1.27, "mixer ZX05-43MH-S+", ref="M7")
xm = LNA["pins"]["OUT"][0] + 5
w(LNA["pins"]["OUT"], (xm, LNA["pins"]["OUT"][1]), (xm, MIX["pins"]["RF"][1]), MIX["pins"]["RF"])
# LO from splitter OUT2 down to the mixer
o2 = SPL["pins"]["OUT2"]; lo = MIX["pins"]["LO"]
w(o2, (o2[0] + 3, o2[1]), (o2[0] + 3, 84), (lo[0] - 3, 84), (lo[0] - 3, lo[1]), lo)
note("LO +10.5 dBm", lo[0] - 14, 83, 1.0)
p = MIX["pins"]["IF"]; w(p, (p[0] + 4, p[1])); lbl("IF", p[0] + 4, p[1])
note("IF -> shielded pigtail -> J1 on the breadboard", MIX["x"] - 14, MIX["y"] + 12, 1.0)
note("echo -74 dBm @ 10 m", 288, 110, 1.0)

# --- stepper (y = 150) ---
A49 = place(block("A4988", ["VMOT", "GND", "VDD", "STEP", "DIR", "EN", "RESET", "SLEEP", "MS1", "MS2", "MS3"],
                  ["1A", "1B", "2A", "2B"], 22.86), 300, 156, "A4988 driver", ref="M8")
p = A49["pins"]["VMOT"]; w(p, (p[0] - 6, p[1])); lbl("VIN12", p[0] - 6, p[1], 0, "right")
Cv = C("C21", "100u", 282, p[1] + 7, pol=True); w((282, p[1]), Cv["pins"]["1"]); J(282, p[1]); gnd(282, p[1] + 10.81)
p = A49["pins"]["GND"]; w(p, (p[0] - 3, p[1])); gnd(p[0] - 3, p[1])
xb = A49["pins"]["VDD"][0] - 5
for pn in ["VDD", "RESET", "SLEEP", "MS1", "MS2", "MS3"]:
    p = A49["pins"][pn]; w(p, (xb, p[1]))
    if pn != "VDD": J(xb, p[1])
w((xb, A49["pins"]["VDD"][1]), (xb, A49["pins"]["MS3"][1])); w((xb, A49["pins"]["VDD"][1]), (xb, A49["pins"]["VDD"][1] - 4))
rail("+3V3", xb, A49["pins"]["VDD"][1] - 4)
for pn in ["STEP", "DIR", "EN"]:
    p = A49["pins"][pn]; w(p, (p[0] - 9, p[1])); lbl(pn, p[0] - 9, p[1], 0, "right")
MOT = place(block("NEMA17", ["1A", "1B", "2A", "2B"], [], 15.24), 336, A49["pins"]["1A"][1] + 3.81, "NEMA-17 stepper", ref="M9")
for pn in ["1A", "1B", "2A", "2B"]:
    w(A49["pins"][pn], MOT["pins"][pn])
note("VMOT from the fused 12 V, NOT through D1. MS1-3 high = 1/16 step. VREF for ~0.8 A.", 280, 186, 1.0)

# --- sound card (y = 200) ---
UCA = place(block("UCA202_sound_card", ["L in", "R in", "GND"], ["USB"], 22.86), 300, 205, "Behringer UCA202", ref="A2")
p = UCA["pins"]["L in"]; w(p, (p[0] - 4, p[1])); lbl("AUDIO_L", p[0] - 4, p[1], 0, "right")
p = UCA["pins"]["R in"]; w(p, (p[0] - 4, p[1])); lbl("AUDIO_R", p[0] - 4, p[1], 0, "right")
p = UCA["pins"]["GND"]; w(p, (p[0] - 3, p[1])); gnd(p[0] - 3, p[1])
p = UCA["pins"]["USB"]; w(p, (p[0] + 4, p[1])); lbl("USB laptop", p[0] + 4, p[1])
note("L = beat 0-2.6 kHz, R = sync. 44.1 kHz 16-bit. radar_acquire.py", 280, 218, 1.1)

note("Nets with the same label are connected across both halves (KiCad local labels).", 222, 240, 1.3)
note("Sweep 2440-2480 MHz (drone WiFi on ch 1), 64 steps x 100 us, PRI 7.4 ms. Boots RF OFF.", 222, 244, 1.3)


if __name__ == "__main__":
    write_kicad(); write_svg(); run_checks()
