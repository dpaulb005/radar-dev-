#!/usr/bin/env python3
"""
gen_multisim.py — the Multisim replication sheet.

Only the circuits you simulate, one framed block per test card in
hardware/spice/README.md, spread out so that EVERY component value, every
source setting and every probe point (TP_*) is readable. The sources are
drawn in (VDC / VSIN / VPULSE) with their settings, the loads that stand in
for the rest of the system are drawn as resistors, and each frame carries
the reading you should get (from ngspice).

Blocks: 1 video amplifier · 2 half-rail reference · 3 12 V input ·
        4 sync divider · 5 the radar as a behavioural model (scaled FMCW).

Usage:  python gen_multisim.py  -> radar_multisim.kicad_sch (+ .kicad_pro, .svg, nets)
"""
from kicad_lib import *
import kicad_lib, math

reset("radar_multisim", "3b7e0c52-6a1d-4f0e-9c3b-radar0000002",
      "Horn-fed FMCW radar — Multisim test blocks",
      ("Every value and source setting on the sheet. One frame = one test card in hardware/spice/README.md.",
       "TL072CP x3, single 11.4 V rail (VANA), VREF = 5.7 V. Probe the TP_* labels."))

# --- simulation sources ---------------------------------------------------
oct_ = [(2.54 * math.cos(math.radians(a)), 2.54 * math.sin(math.radians(a))) for a in range(0, 361, 45)]
defsym("Simulation:VDC", [("1", "+", (0, 5.08), 270, 2.54, "passive", 1), ("2", "-", (0, -5.08), 90, 2.54, "passive", 1)],
       [("poly", oct_), ("line", (-1.0, 0.9), (1.0, 0.9)), ("line", (0, 0.4), (0, 1.4)), ("line", (-1.0, -0.9), (1.0, -0.9))],
       ref_prefix="V", hide_pin_names=True)
sine = [(-1.6 + 3.2 * i / 12, 0.9 * math.sin(math.pi * 2 * i / 12)) for i in range(13)]
defsym("Simulation:VSIN", [("1", "+", (0, 5.08), 270, 2.54, "passive", 1), ("2", "-", (0, -5.08), 90, 2.54, "passive", 1)],
       [("poly", oct_), ("poly", sine)], ref_prefix="V", hide_pin_names=True)
defsym("Simulation:VPULSE", [("1", "+", (0, 5.08), 270, 2.54, "passive", 1), ("2", "-", (0, -5.08), 90, 2.54, "passive", 1)],
       [("poly", oct_), ("poly", [(-1.6, -0.8), (-1.6, 0.8), (0, 0.8), (0, -0.8), (1.6, -0.8), (1.6, 0.8)])],
       ref_prefix="V", hide_pin_names=True)

def vsrc(kind, ref, x, y, value):
    return place(f"Simulation:{kind}", x, y, value, ref=ref, vpos=(x + 3.5, y + 1.5), rpos=(x + 3.5, y - 1.5))

def opamp(ref, unit, x, y):
    return place("Amplifier_Operational:TL072", x, y, "TL072CP", unit=unit, ref=ref,
                 vpos=(x - 4, y + 7.5), rpos=(x - 2, y - 7))

def Rh(ref, val, x, y):   # horizontal resistor, value above, ref below
    return place("Device:R", x, y, val, 90, ref=ref, vpos=(x - 3.5, y - 2.2), rpos=(x - 3.0, y + 4.6))

def Rv(ref, val, x, y):   # vertical resistor, ref/value to the right
    return place("Device:R", x, y, val, 0, ref=ref, vpos=(x + 2.3, y + 1.8), rpos=(x + 2.3, y - 1.0))

def Ch(ref, val, x, y, pol=False):
    return place("Device:C_Polarized" if pol else "Device:C", x, y, val, 90, ref=ref,
                 vpos=(x - 3.5, y - 3.0), rpos=(x - 3.0, y + 5.4))

def Cv(ref, val, x, y, pol=False):
    return place("Device:C_Polarized" if pol else "Device:C", x, y, val, 0, ref=ref,
                 vpos=(x + 2.6, y + 1.8), rpos=(x + 2.6, y - 1.0))

def tp(name, x, y):
    lbl(name, x, y)

# ======================================================================
# FRAME 1 — video amplifier (test card 1)
# ======================================================================
frame(12, 28, 408, 100)
note("1 · VIDEO AMPLIFIER  —  mixer IF in, sound-card line out.  Probe TP_IF TP_AP TP_AOUT TP_BOUT TP_LP TP_AUDIO", 14, 26, 2.0, True)

VIF = vsrc("VSIN", "V_IF", 22, 62, "AC 10 mVpk 1 kHz")
note("V_IF: Multisim AC_VOLTAGE. 10 mVpk for the low-gain build,", 14, 76, 1.1)
note("0.5 mVpk for full gain (it clips at 10 mV). Bode: AC sweep 1 Hz-100 kHz", 14, 79.5, 1.1)
w(VIF["pins"]["+"], (22, 50), (28.19, 50))
w(VIF["pins"]["-"], (22, 70)); gnd(22, 70)
RS = Rh("R_S", "50", 32, 50); note("mixer IF source impedance", 26, 45, 1.0)
w(RS["pins"]["2"], (44, 50)); J(44, 50); tp("TP_IF", 44, 50)
R1 = Rv("R1", "49.9", 44, 58); w((44, 50), R1["pins"]["1"]); gnd(44, 61.81)
C20 = Cv("C20", "1n", 52, 58); w((44, 50), (52, 50), C20["pins"]["1"]); J(52, 50); gnd(52, 61.81)
C1 = Ch("C1", "100n", 62, 50); w((52, 50), C1["pins"]["1"])
w(C1["pins"]["2"], (72, 50)); J(72, 50); tp("TP_AP", 72, 50)
R2 = Rv("R2", "10k", 72, 58); w((72, 50), R2["pins"]["1"]); w(R2["pins"]["2"], (72, 64)); lbl("VREF", 72, 64)
U1A = opamp("U1", 1, 88, 52.54)
w((72, 50), U1A["pins"]["3"])
w(U1A["pins"]["1"], (100, 52.54)); J(100, 52.54); tp("TP_AOUT", 100, 52.54)
R3 = Rh("R3", "100k", 88, 40); w((100, 52.54), (100, 40), R3["pins"]["2"])
w(R3["pins"]["1"], (76, 40), (76, 55.08), U1A["pins"]["2"]); J(76, 55.08)
R4 = Rv("R4", "1k", 76, 62); w((76, 55.08), R4["pins"]["1"]); w(R4["pins"]["2"], (76, 68)); lbl("VREF", 76, 68)
note("gain A = 1 + R3/R4 = 101   (R4 = 4.7k -> 22, first power-up)", 62, 92, 1.1)

C2 = Ch("C2", "100n", 108, 52.54); w((100, 52.54), C2["pins"]["1"])
w(C2["pins"]["2"], (118, 52.54)); J(118, 52.54)
R6 = Rv("R6", "10k", 118, 60); w((118, 52.54), R6["pins"]["1"]); w(R6["pins"]["2"], (118, 66)); lbl("VREF", 118, 66)
U1B = opamp("U1", 2, 134, 55.08)
w((118, 52.54), U1B["pins"]["5"])
w(U1B["pins"]["7"], (146, 55.08)); J(146, 55.08); tp("TP_BOUT", 146, 55.08)
R7 = Rh("R7", "10k", 134, 42); w((146, 55.08), (146, 42), R7["pins"]["2"])
w(R7["pins"]["1"], (122, 42), (122, 57.62), U1B["pins"]["6"]); J(122, 57.62)
R8 = Rv("R8", "1k", 122, 64); w((122, 57.62), R8["pins"]["1"]); w(R8["pins"]["2"], (122, 70)); lbl("VREF", 122, 70)
note("gain B = 1 + R7/R8 = 11   (R7 = wire link -> 1)", 118, 95.5, 1.1)

R12 = Rh("R12", "1k", 154, 55.08); w((146, 55.08), R12["pins"]["1"])
w(R12["pins"]["2"], (164, 55.08)); J(164, 55.08); tp("TP_LP", 164, 55.08)
C9 = Cv("C9", "10n", 164, 62); w((164, 55.08), C9["pins"]["1"]); w(C9["pins"]["2"], (164, 68)); lbl("VREF", 164, 68)
note("R12/C9: 15.9 kHz low-pass", 150, 92, 1.1)
U2B = opamp("U2", 2, 180, 57.62)
w((164, 55.08), U2B["pins"]["5"])
w(U2B["pins"]["7"], (192, 57.62)); J(192, 57.62)
w((192, 57.62), (192, 66), (170, 66), (170, 60.16), U2B["pins"]["6"])
R13 = Rh("R13", "100", 200, 57.62); w((192, 57.62), R13["pins"]["1"])
C10 = Ch("C10", "10u", 212, 57.62, pol=True); w(R13["pins"]["2"], C10["pins"]["1"])
w(C10["pins"]["2"], (222, 57.62)); J(222, 57.62); tp("TP_AUDIO", 222, 57.62)
R14 = Rv("R14", "100k", 222, 65); w((222, 57.62), R14["pins"]["1"]); gnd(222, 68.81)
RL = Rv("R_LOAD", "10k", 234, 65); w((222, 57.62), (234, 57.62), RL["pins"]["1"]); J(234, 57.62); gnd(234, 68.81)
note("R_LOAD = sound-card line input", 226, 76, 1.0)

# supplies for this frame
VA = vsrc("VDC", "V_ANA", 262, 60, "DC 11.4 V"); w(VA["pins"]["+"], (262, 50)); rail("VANA", 262, 50); w(VA["pins"]["-"], (262, 68)); gnd(262, 68)
VR = vsrc("VDC", "V_REF", 282, 60, "DC 5.7 V"); w(VR["pins"]["+"], (282, 50)); lbl("VREF", 282, 50); w(VR["pins"]["-"], (282, 68)); gnd(282, 68)
note("(or drive VREF from frame 2)", 276, 76, 1.0)
for ref, x in (("U1", 304), ("U2", 322)):
    place("Amplifier_Operational:TL072", x, 58, "TL072CP", unit=3, ref=ref, hide_value=True, rpos=(x + 3, y0 := 55))
    rail("VANA", x, 50.38); gnd(x, 65.62)
C3 = Cv("C3", "100n", 340, 58); rail("VANA", 340, 54.19); gnd(340, 61.81)
C7 = Cv("C7", "100n", 352, 58); rail("VANA", 352, 54.19); gnd(352, 61.81)
note("EXPECTED  low gain (R4 4.7k, R7 link): 10 mVpk in -> 107 mVpk at TP_AUDIO", 262, 84, 1.1, True)
note("full gain: 54.6 dB from V_IF at 1 kHz, -6 dB at 159 Hz, -3 dB at 15.9 kHz; clips at +/-4.1 V", 262, 88, 1.1)
note("radar input 8 mV @ 12.5 Hz + 40 uV @ 417 Hz -> TP_AUDIO 27 mV leak, 19 mV echo", 262, 92, 1.1)
note("U1A/U1B/U2B = TL072CP  (Multisim: Analog > OPAMP > TL072CP)", 262, 96, 1.1)

# ======================================================================
# FRAME 2 — half-rail reference (test card 2)
# ======================================================================
frame(12, 106, 132, 165)
note("2 · HALF-RAIL REFERENCE  —  VREF = VANA/2 buffered", 14, 104, 2.0, True)
VA2 = vsrc("VDC", "V_ANA", 22, 134, "DC 11.4 V"); note("ripple test: + 100 mVpk 150 kHz", 14, 144, 1.0)
w(VA2["pins"]["+"], (22, 122), (40, 122)); w(VA2["pins"]["-"], (22, 142)); gnd(22, 142)
rail("VANA", 30, 122); w((22, 122), (30, 122)); J(30, 122)
R9 = Rv("R9", "10k", 40, 128); w((40, 122), R9["pins"]["1"])
w(R9["pins"]["2"], (40, 134)); J(40, 134); tp("TP_VDIV", 40, 134)
R10 = Rv("R10", "10k", 40, 140); w((40, 134), R10["pins"]["1"]); gnd(40, 143.81)
C5 = Cv("C5", "10u", 50, 140, pol=True); w((40, 134), (50, 134), C5["pins"]["1"]); J(50, 134); gnd(50, 143.81)
U2A = opamp("U2", 1, 68, 136.54)
w((50, 134), U2A["pins"]["3"])
w(U2A["pins"]["1"], (80, 136.54)); J(80, 136.54)
w((80, 136.54), (80, 146), (58, 146), (58, 139.08), U2A["pins"]["2"])
R11 = Rh("R11", "47", 88, 136.54); w((80, 136.54), R11["pins"]["1"])
w(R11["pins"]["2"], (98, 136.54)); J(98, 136.54); tp("TP_VREF", 98, 136.54)
C6 = Cv("C6", "47u", 98, 144, pol=True); w((98, 136.54), C6["pins"]["1"]); gnd(98, 147.81)
RL2 = Rv("R_LOAD", "2.2k", 110, 144); w((98, 136.54), (110, 136.54), RL2["pins"]["1"]); J(110, 136.54); gnd(110, 147.81)
note("R_LOAD = the six VREF returns", 100, 152, 1.0)
place("Amplifier_Operational:TL072", 122, 128, "TL072CP", unit=3, ref="U2", hide_value=True); rail("VANA", 122, 120.38); gnd(122, 135.62)
note("EXPECTED  TP_VDIV 5.70 V, TP_VREF 5.70 V, ripple at TP_VREF < 1 uV", 14, 161, 1.1, True)

# ======================================================================
# FRAME 3 — 12 V input (test card 3)
# ======================================================================
frame(140, 106, 270, 165)
note("3 · 12 V INPUT  —  D1 -> VPROT -> R15/C13 -> VANA", 142, 104, 2.0, True)
VIN = vsrc("VDC", "V_IN", 150, 134, "DC 12 V"); note("ripple test: + 100 mVpk 150 kHz; reverse test: -12 V", 142, 152, 1.0)
w(VIN["pins"]["+"], (150, 122), (158.19, 122)); w(VIN["pins"]["-"], (150, 142)); gnd(150, 142)
D1 = place("Device:D_Schottky", 162, 122, "1N5822", rot=180, ref="D1", vpos=(158, 118.5), rpos=(158, 127.5))
w(D1["pins"]["K"], (174, 122)); J(174, 122); tp("TP_VPROT", 174, 122)
C11 = Cv("C11", "100u", 174, 130, pol=True); w((174, 122), C11["pins"]["1"]); gnd(174, 133.81)
RB = Rv("R_BUCK", "60", 186, 130); w((174, 122), (186, 122), RB["pins"]["1"]); J(186, 122); gnd(186, 133.81)
note("60 R = the LM2596 drawing 0.2 A", 178, 140, 1.0)
R15 = Rh("R15", "10", 196, 122); w((186, 122), R15["pins"]["1"])
w(R15["pins"]["2"], (206, 122)); J(206, 122); tp("TP_VANA", 206, 122)
C13 = Cv("C13", "100u", 206, 130, pol=True); w((206, 122), C13["pins"]["1"]); gnd(206, 133.81)
RO = Rv("R_OPAMPS", "1.1k", 218, 130); w((206, 122), (218, 122), RO["pins"]["1"]); J(218, 122); gnd(218, 133.81)
note("1.1k = two TL072 + dividers", 210, 140, 1.0)
note("EXPECTED  TP_VPROT 11.7 V, TP_VANA 11.6 V, ripple 4 mVpp;", 142, 158, 1.1, True)
note("with V_IN = -12 V: TP_VPROT -0.1 mV, 2 uA", 142, 162, 1.1)

# ======================================================================
# FRAME 4 — sync divider (test card 4)
# ======================================================================
frame(278, 106, 408, 165)
note("4 · SYNC DIVIDER  —  ESP32 GPIO -> 0.3 V -> sound-card R", 280, 104, 2.0, True)
VG = vsrc("VPULSE", "V_GPIO", 288, 134, "PULSE 0/3.3 V"); note("6.4 ms high, 7.4 ms period, 10 ns edges", 280, 146, 1.0)
w(VG["pins"]["+"], (288, 122), (296.19, 122)); w(VG["pins"]["-"], (288, 142)); gnd(288, 142)
RG = Rh("R_GPIO", "30", 300, 122); note("GPIO output R", 294, 117, 1.0)
R23 = Rh("R23", "10k", 312, 122); w(RG["pins"]["2"], R23["pins"]["1"])
w(R23["pins"]["2"], (322, 122)); J(322, 122); tp("TP_SYNC", 322, 122)
R24 = Rv("R24", "1k", 322, 130); w((322, 122), R24["pins"]["1"]); gnd(322, 133.81)
CC = Ch("C_CPL", "10u", 334, 122, pol=True); w((322, 122), CC["pins"]["1"])
w(CC["pins"]["2"], (346, 122)); J(346, 122); tp("TP_SC", 346, 122)
RSC = Rv("R_SC", "10k", 346, 130); w((346, 122), RSC["pins"]["1"]); gnd(346, 133.81)
note("C_CPL / R_SC = the sound card's AC-coupled input", 330, 140, 1.0)
note("EXPECTED  TP_SYNC 283 mV high / 0 V low;", 280, 158, 1.1, True)
note("TP_SC +201 mV drooping / -100 mV retrace pulse -> software detects EDGES", 280, 162, 1.1)

# ======================================================================
# FRAME 5 — the radar as a behavioural model (test card 6)
# ======================================================================
frame(12, 172, 408, 262)
note("5 · THE RADAR ITSELF, SCALED  —  chirp x delayed chirp = beat. Carrier cancels, so B/10 and delay x10 give the real 417 Hz", 14, 170, 2.0, True)
PWL = place(block("PWL_ramp", [], ["OUT"], 20.32), 30, 196, "0 V -> 1 V in 6.4 ms, repeat", ref="X1")
VCO = place(block("VCO_sine", ["IN"], ["OUT"], 20.32), 66, 196, "1 -> 5 MHz for 0 -> 1 V, 1 Vpk", ref="X2")
w(PWL["pins"]["OUT"], VCO["pins"]["IN"])
w(VCO["pins"]["OUT"], (92, 196)); J(92, 196); lbl("TX", 92, 196)
DL1 = place(block("DELAY_LINE", ["IN"], ["OUT"], 20.32), 116, 188, "lossless, Z0 50, TD 667 ns", ref="T1")
DL2 = place(block("DELAY_LINE", ["IN"], ["OUT"], 20.32), 116, 206, "lossless, Z0 50, TD 20 ns", ref="T2")
w((92, 196), (98, 196), (98, 188), DL1["pins"]["IN"]); w((98, 196), (98, 206), DL2["pins"]["IN"]); J(98, 196)
RT1 = Rv("R_T1", "50", 134, 194); w(DL1["pins"]["OUT"], (134, 188), RT1["pins"]["1"]); J(134, 188); gnd(134, 197.81)
RT2 = Rv("R_T2", "50", 134, 212); w(DL2["pins"]["OUT"], (134, 206), RT2["pins"]["1"]); J(134, 206); gnd(134, 215.81)
G1 = place(block("GAIN", ["IN"], ["OUT"], 15.24), 152, 188, "x 0.01  (echo, -40 dB)", ref="A1")
G2 = place(block("GAIN", ["IN"], ["OUT"], 15.24), 152, 206, "x 1 leakage on / x 0 off", ref="A2")
w((134, 188), G1["pins"]["IN"]); w((134, 206), G2["pins"]["IN"])
SUM = place(block("SUMMER", ["A", "B"], ["OUT"], 15.24), 178, 197.27, "A + B", ref="A3")
w(G1["pins"]["OUT"], (170, 188), (170, SUM["pins"]["A"][1]), SUM["pins"]["A"])
w(G2["pins"]["OUT"], (170, 206), (170, SUM["pins"]["B"][1]), SUM["pins"]["B"])
MUL = place(block("MULTIPLIER", ["X", "Y"], ["OUT"], 15.24), 206, 197.27, "X * Y  = the mixer", ref="A4")
w(SUM["pins"]["OUT"], (196, SUM["pins"]["OUT"][1]), (196, MUL["pins"]["Y"][1]), MUL["pins"]["Y"])
w((92, 196), (92, 226), (196, 226), (196, MUL["pins"]["X"][1]), MUL["pins"]["X"]); J(92, 196)
w(MUL["pins"]["OUT"], (224, MUL["pins"]["OUT"][1])); J(224, MUL["pins"]["OUT"][1]); lbl("IF_MODEL", 224, MUL["pins"]["OUT"][1])
yb = MUL["pins"]["OUT"][1]
R12m = Rh("R12", "1k", 232, yb); w((224, yb), R12m["pins"]["1"])
w(R12m["pins"]["2"], (242, yb)); J(242, yb)
C9m = Cv("C9", "10n", 242, yb + 8); w((242, yb), C9m["pins"]["1"]); gnd(242, yb + 11.81)
C1m = Ch("C1", "100n", 252, yb); w((242, yb), C1m["pins"]["1"])
w(C1m["pins"]["2"], (262, yb)); J(262, yb)
R2m = Rv("R2", "10k", 262, yb + 8); w((262, yb), R2m["pins"]["1"]); gnd(262, yb + 11.81)
C2m = Ch("C2", "100n", 272, yb); w((262, yb), C2m["pins"]["1"])
w(C2m["pins"]["2"], (282, yb)); J(282, yb); tp("TP_BEAT", 282, yb)
R6m = Rv("R6", "10k", 282, yb + 8); w((282, yb), R6m["pins"]["1"]); gnd(282, yb + 11.81)
note("R12/C9 = the amp's 15.9 kHz LP;  C1/R2, C2/R6 = its two 159 Hz HPs (they kill the leakage tone)", 226, 222, 1.0)
note("Multisim parts: PIECEWISE_LINEAR_VOLTAGE -> VOLTAGE_CONTROLLED_SINE_WAVE; LOSSLESS_LINE_TYPE1; VOLTAGE_GAIN_BLOCK; VOLTAGE_SUMMER; MULTIPLIER", 14, 236, 1.1)
note("Transient: TMAX 10 ns, stop 19.2 ms (3 chirps). Fourier at TP_BEAT over ONE chirp (6.4 ms), Hanning window.", 14, 240, 1.1)
note("EXPECTED  leakage gain x0: peak at 417 Hz, 4.5 mV.   TD1 = 333 ns -> 208 Hz.   TD1 = 1.33 us -> 833 Hz (20 m).", 14, 246, 1.1, True)
note("Leakage gain x1: the 417 Hz line is unchanged but the spectrum floor rises 20 dB near DC - what chirp-to-chirp subtraction removes in software.", 14, 250, 1.1)
note("Real radar: B = 40 MHz, TD = 66.7 ns (10 m), T = 6.4 ms  ->  f_beat = B x TD / T = 417 Hz.  Here: B = 4 MHz, TD = 667 ns. Same answer.", 14, 254, 1.1)
note("The blocks right of the mixer's IF port cannot be simulated in Multisim (no 2.4 GHz models): ADF4351, SPF5189Z, splitter, mixer, horns are measured, not modelled.", 14, 258, 1.1)

# legend
note("PARTS  resistors 1 % 1/4 W · 100n / 10n film or C0G · 10u 47u 100u electrolytic 25 V (+ marked) · 1N5822 · TL072CP x3 · single 12 V rail", 14, 270, 1.2)
note("Netlists that produced the EXPECTED lines: hardware/spice/*.cir (ngspice 42).  Same values as the breadboard sheet radar_breadboard.kicad_sch.", 14, 274, 1.2)

if __name__ == "__main__":
    write_kicad(); write_svg(); run_checks()
