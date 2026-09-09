#!/usr/bin/env python3
"""gen_flow.py — radar_flow.kicad_sch: how the five test blocks connect to each other.

radar_multisim.kicad_sch draws blocks 1-5 as five isolated test frames, because
that is how you bench them: one at a time, with your own sources on the inputs.
This sheet puts them back together and answers what that sheet cannot: what feeds
block 1, where block 2's output goes, what block 3 powers, and where the two
audio channels end up.

Block numbers are the same on both sheets:
  1  VIDEO AMPLIFIER          4  SYNC DIVIDER
  2  HALF-RAIL REFERENCE      5  THE RADAR ITSELF (scaled behavioural model)
  3  12 V INPUT

Only three signals cross between blocks: VANA, VREF and the mixer's IF.
The two supply nets are drawn as labels, the way the breadboard sheet does it.

Usage: python gen_flow.py
"""
from kicad_lib import *
import kicad_lib

kicad_lib.reset(
    "radar_flow", "8f2c1d34-9a77-4c21-b6e5-2d84ff10a901",
    "How the five test blocks connect — the whole radar in one flow",
    ["Block numbers match radar_multisim.kicad_sch. Labels with the same name are the same net.",
     "Levels: 25 g quad at 10 m, RCS 0.0026 m2, sweep 2440-2480 MHz. Baseband figures measured in ngspice."])

# ----------------------------------------------------------------------
# one flowchart block: number above, title and explanation below
# ----------------------------------------------------------------------
def box(tag, title, x, y, left, right, w=30, sub=None):
    lib = block("FB_" + tag, left, right, w)
    h = (max(len(left), len(right)) * 2.54 + 2.54) / 2
    s = place(lib, x, y, title, ref="B" + tag, hide_value=True, rpos=(x, y - h - 2.4))
    note(title, x - w / 2, y + h + 3.4, 1.35, True)
    if sub:
        note(sub, x - w / 2, y + h + 7.0, 1.05)
    return s

def sig(text, x, y, size=1.1):
    note(text, x, y, size)

def stub(pin, name, dx):
    """a short wire off a pin, ending in a net label"""
    end = (pin[0] + dx, pin[1])
    w(pin, end)
    lbl(name, end[0], end[1], 0, "left" if dx > 0 else "right")

# ======================================================================
# RF FRONT END — bought modules.  Nothing here has a SPICE model.
# ======================================================================
frame(12, 18, 408, 80)
note("RF FRONT END  —  bought modules, SMA to SMA.  Nothing here has a SPICE model at 2.4 GHz, so every one is measured on the bench, never simulated.",
     15, 23, 1.85, True)

ADF = box("ADF", "ADF4351 PLL", 44, 40, ["+5V", "SPI"], ["RF"], 26,
          "64 steps of 625 kHz, 100 us each.\nThat is the 6.4 ms up-chirp.")
ATT = box("ATT", "3 dB pad", 96, 38.73, ["IN"], ["OUT"], 22, "flattens the PLL\ninto 50 ohm")
PA  = box("PA", "SPF5189Z PA", 145, 40, ["IN", "+5V"], ["OUT"], 26, "+12 dB")
SPL = box("SPL", "2-way splitter", 200, 40, ["IN"], ["TX", "LO"], 27, "half radiates,\nhalf becomes the LO")
TXH = box("TXH", "TX HORN", 253, 38.73, ["FEED"], ["BEAM"], 22, "13.4 dBi, 34 deg")
DRN = box("DRN", "ESP-FLY 25 g", 312, 38.73, ["ILLUM"], ["ECHO"], 28, "3-10 m out. Flown from the\nphone over its own AP, ch 1.")
RXH = box("RXH", "RX HORN", 372, 38.73, ["BEAM"], ["FEED"], 22, "identical horn")

w(ADF["pins"]["RF"], ATT["pins"]["IN"]);      sig("+5 dBm", 66, 36)
w(ATT["pins"]["OUT"], PA["pins"]["IN"]);      sig("+2 dBm", 114, 36)
w(PA["pins"]["OUT"], SPL["pins"]["IN"]);      sig("+14 dBm", 166, 36)
w(SPL["pins"]["TX"], TXH["pins"]["FEED"]);    sig("+10 dBm", 221, 36)
w(TXH["pins"]["BEAM"], DRN["pins"]["ILLUM"]); sig("0.2 W EIRP", 271, 36)
w(DRN["pins"]["ECHO"], RXH["pins"]["BEAM"]);  sig("echo comes back", 330, 36)

MIX = box("MIX", "ZX05-43MH mixer", 220, 64, ["IF"], ["RF", "LO"], 30,
          "RF x LO.  The carrier cancels and what is left is\na tone whose pitch is the range.")
LNA = box("LNA", "SPF5189Z LNA", 298, 62.73, ["OUT"], ["IN"], 27, "+12 dB, NF 0.6 dB.\nSets the noise floor.")
BPF = box("BPF", "2400-2500 BPF", 366, 62.73, ["OUT"], ["IN"], 27, "keeps everything that is not\nthe ISM band off the LNA")

w(RXH["pins"]["FEED"], (385.54, 38.73), (385.54, 62.73), BPF["pins"]["IN"])
sig("-80 dBm", 388, 52)
w(BPF["pins"]["OUT"], LNA["pins"]["IN"]);  sig("-83 dBm", 328, 60.5)
w(LNA["pins"]["OUT"], MIX["pins"]["RF"]);  sig("-71 dBm", 252, 60.5)
w(SPL["pins"]["LO"], (245, 41.27), (245, 65.27), MIX["pins"]["LO"])
sig("LO: the same chirp,\nnot delayed", 206, 55)

# ======================================================================
# BLOCK 5 — a behavioural stand-in for everything above.
# ======================================================================
frame(12, 84, 200, 120)
note("5   THE RADAR ITSELF  (scaled)", 15, 89, 2.1, True)
note("Everything in the band above, written as a circuit SPICE can actually run.  Build it first:\n"
     "it shows you a beat tone before you have bought a single RF part.", 15, 93.5, 1.15)

B5 = box("5", "chirp x delayed chirp", 88, 102, ["chirp in"], ["BEAT"], 40,
         "Delay line, multiplier, then the amplifier's own filters.  Bandwidth scaled down 10x and the\n"
         "delay up 10x, because the carrier cancels: 4 MHz over 667 ns gives the same 417 Hz as 40 MHz\n"
         "over 66.7 ns, and lets SPICE step at 10 ns instead of 20 ps.")

# ======================================================================
# BLOCK 1 — the video amplifier.  The other four blocks exist to serve it.
# ======================================================================
frame(12, 124, 408, 182)
note("1   VIDEO AMPLIFIER  —  40 uV of audio in, line level out.  Everything else on this sheet exists to feed it.",
     15, 129, 2.1, True)

TRM = box("1a", "49.9 R + 1 nF", 48, 146, ["IF"], ["OUT"], 27, "terminates the mixer and\nshorts its 2.4 GHz LO leak")
HP1 = box("1b", "C1 / R2", 104, 147.27, ["IN", "VREF"], ["OUT"], 24, "159 Hz high-pass")
U1A = box("1c", "U1A  x101", 156, 147.27, ["IN", "VREF"], ["OUT"], 24, "R3 100k / R4 1k")
HP2 = box("1d", "C2 / R6", 206, 147.27, ["IN", "VREF"], ["OUT"], 24, "159 Hz again")
U1B = box("1e", "U1B  x11", 256, 147.27, ["IN", "VREF"], ["OUT"], 24, "R7 10k / R8 1k")
LPF = box("1f", "R12 / C9", 306, 147.27, ["IN", "VREF"], ["OUT"], 24, "15.9 kHz low-pass")
U2B = box("1g", "U2B buffer", 358, 146, ["IN"], ["OUT"], 24, "unity gain, then\n100 R and 10 uF out")

w(MIX["pins"]["IF"], (196, 64), (196, 134), (34, 134), (34, 146), TRM["pins"]["IF"])
sig("IF  —  -78 dBm at 417 Hz, which is 40 uV pk.  This one wire carries the whole measurement.", 40, 132.5, 1.25)
w(B5["pins"]["BEAT"], (116, 102), (116, 140), (26, 140), (26, 146), (34, 146))
J(34, 146)
sig("Block 5 feeds the same wire the mixer does.  That is the point of it:\n"
    "you can bring up the whole amplifier, and see a 417 Hz tone come out of it,\n"
    "with the RF half of the sheet still in its packaging.", 212, 96, 1.2)

w(TRM["pins"]["OUT"], HP1["pins"]["IN"]);  sig("40 uV", 72, 143.5)
w(HP1["pins"]["OUT"], U1A["pins"]["IN"]);  sig("20 uV", 126, 143.5)
w(U1A["pins"]["OUT"], HP2["pins"]["IN"]);  sig("2.0 mV", 176, 143.5)
w(HP2["pins"]["OUT"], U1B["pins"]["IN"]);  sig("2.0 mV", 226, 143.5)
w(U1B["pins"]["OUT"], LPF["pins"]["IN"]);  sig("22 mV", 278, 143.5)
w(LPF["pins"]["OUT"], U2B["pins"]["IN"]);  sig("22 mV", 328, 143.5)

for p in (HP1, U1A, HP2, U1B, LPF):
    stub(p["pins"]["VREF"], "VREF", -7)

note("Gain is 60.2 dB measured from the amplifier's own input, but 53.6 dB from the mixer, because 50 ohm driving 49.9 ohm halves the signal before the first stage.\n"
     "The TX-to-RX leakage arrives alongside the echo at 8 mV and leaves at 27 mV.  That 46 dB head start is what the two high-passes exist to cut down, and it is\n"
     "why the gain is split in two: one stage of 1100 would saturate on the leakage long before the echo ever reached the output.",
     40, 171, 1.2)
note("VANA powers all three op-amps here.  VREF is their input reference: on a single supply every stage swings about 5.7 V, not about 0 V.", 40, 179.5, 1.2)

# ======================================================================
# BLOCKS 3 and 2 — the supply pair.  3 feeds 2, and both feed 1.
# ======================================================================
frame(12, 188, 150, 222)
note("3   12 V INPUT", 15, 193, 2.1, True)
B3 = box("3", "D1  ->  R15 / C13", 74, 204, ["12 V"], ["VANA"], 34,
         "1N5822 makes a reversed plug harmless: VPROT reads -0.11 mV,\nnot -12 V. R15/C13 then filters the buck's 150 kHz to 4 mVpp.")
stub(B3["pins"]["VANA"], "VANA", 12)
sig("11.58 V", 96, 201.5)

frame(12, 226, 150, 262)
note("2   HALF-RAIL REFERENCE", 15, 231, 2.1, True)
B2 = box("2", "R9 / R10  ->  U2A", 74, 238, ["VANA"], ["VREF"], 34,
         "VANA / 2, buffered, so the six returns inside block 1\ncannot pull the reference around.")
stub(B2["pins"]["VANA"], "VANA", -12)
stub(B2["pins"]["VREF"], "VREF", 12)
sig("5.7 V", 96, 235.5)
sig("VANA and VREF are net labels: every label with the same name is one wire.\n"
    "VANA reaches block 2's divider and block 1's three op-amp rails.\n"
    "VREF reaches six points inside block 1: R2, R4, R6, R8, C9 and the buffer.",
    15, 253, 1.15)

# ======================================================================
# BLOCK 4 — sync, plus where both audio channels end up.
# ======================================================================
frame(156, 188, 408, 250)
note("4   SYNC DIVIDER  —  and the two channels the laptop actually records", 159, 193, 2.1, True)

ESP = box("ESP", "ESP32 + radar_ctl", 200, 209.27, ["USB 5V"], ["SPI", "SYNC", "STEP/DIR"], 30,
          "Steps the PLL, holds SYNC high for the\nup-chirp, turns the table between chirps.\nBoots with the RF off.")
B4  = box("4", "10k / 1k", 268, 209.27, ["GPIO25"], ["AUDIO_R"], 24, "3.3 V logic down to 0.3 V\nso it cannot clip the input")
UCA = box("UCA", "UCA202", 336, 209.27, ["L in", "R in"], ["USB"], 26, "48 kHz, 16-bit, line level.\nEvery enhancement off.")
A49 = box("A49", "A4988 + NEMA-17", 268, 228, ["STEP/DIR"], [], 30, "1/16 step, 8.889 steps per degree")

w(ESP["pins"]["SYNC"], B4["pins"]["GPIO25"]);   sig("3.3 V square", 236, 206.2)
w(B4["pins"]["AUDIO_R"], UCA["pins"]["R in"]);  sig("0.3 V", 296, 207.5)
w(ESP["pins"]["STEP/DIR"], (232, 211.81), (232, 228), A49["pins"]["STEP/DIR"])
sig("step / dir", 236, 221)
w(ESP["pins"]["SPI"], (230, 206.73), (230, 186), (20, 186), (20, 41.27), ADF["pins"]["SPI"])
sig("SCK / MOSI / LE, each through 33 R, all the way back up to the PLL", 60, 185.4, 1.05)

w(U2B["pins"]["OUT"], (390, 146), (390, 199), (320.46, 199), UCA["pins"]["L in"])
sig("AUDIO_L  —  19 mV pk at 417 Hz", 328, 197, 1.2)
note("Left channel is the measurement.  Right channel is the clock: radar_acquire.py finds the chirp edges on it and derives T_up and the PRI\n"
     "from them on every block, so changing the sweep on the ESP32 needs no matching change on the laptop.", 159, 243, 1.15)

# ======================================================================
# The far end.
# ======================================================================
frame(156, 254, 408, 290)
note("SOFTWARE", 159, 259, 2.0, True)
LAP = box("LAP", "laptop", 380, 272, ["USB"], [], 22)
w(UCA["pins"]["USB"], (392, 209.27), (392, 272), LAP["pins"]["USB"])
sig("USB", 380, 262)
note("ground_station/radar_acquire.py, once per block of 64 chirps:\n\n"
     "read 48 kHz stereo  ->  find the sync edges (T_up, PRI)  ->  cut into 64 chirps\n"
     "  ->  FFT along one chirp   = RANGE       ->  FFT across the 64 = VELOCITY\n"
     "  ->  CA-CFAR, peak-picked  = DETECTIONS  ->  weight over azimuth = BEARING\n"
     "  ->  {range, velocity, snr} to server.py, drawn in the browser.",
     159, 264, 1.25)

# ======================================================================
# Reading order.
# ======================================================================
note("HOW TO READ THIS SHEET", 15, 268, 1.85, True)
note("Build and bench them in this order, because each needs the one before it:\n"
     "3  first.  Everything else runs on its output.\n"
     "2  next.  Block 1 will not bias without VREF.\n"
     "1  then, driven at its IF pin by a signal generator.\n"
     "4  whenever.  It touches nothing else on the sheet.\n"
     "5  any time, in SPICE alone, before the RF parts arrive.",
     15, 272, 1.2)

if __name__ == "__main__":
    write_kicad(); write_svg(); run_checks()
