# Block-by-block test cards for Multisim (with ngspice reference results)

Every block of the breadboard schematic (`../kicad/radar_breadboard.kicad_sch`)
as a standalone circuit you can build in Multisim, with the exact parts,
values, sources, instrument settings and the readings you should get.
The expected numbers come from running the same circuits in **ngspice 42**
(`*.cir` files here; `ngspice -b video_amp.cir` reproduces them). The op-amp
in the netlists is a generic TL072-class macro (`tl072_macro.lib`: 3 MHz GBW,
100 dB, rails −1.5 V); in Multisim use the library **TL072CP** — expect the
same numbers within ~0.5 dB.

What you cannot model in Multisim: the 2.4 GHz chain (ADF4351, SPF5189Z,
splitter, mixer, horns). No SPICE models exist for those modules and the
frequencies are out of reach. Block 6 is the way round that: the *physics*
of the radar (chirp × delayed chirp → beat tone) scaled to frequencies SPICE
can run, so the mixer/beat idea is testable even though the hardware isn't.

Multisim part families used: `Basic → RESISTOR, CAPACITOR, CAP_ELECTROLIT`;
`Diodes → SCHOTTKY_DIODE → 1N5822`; `Analog → OPAMP → TL072CP`;
`Sources → POWER_SOURCES → DC_POWER / GROUND`; `Sources → SIGNAL_VOLTAGE_SOURCES
→ AC_VOLTAGE, PULSE_VOLTAGE`; `Sources → CONTROL_FUNCTION_BLOCKS → MULTIPLIER,
VOLTAGE_CONTROLLED_SINE_WAVE`; `Basic → TRANSMISSION_LINE (lossless)`.
Instruments: Oscilloscope (XSC), Bode Plotter (XBP), Spectrum Analyzer (XSA),
Function Generator (XFG). Analyses: DC Operating Point, AC Sweep, Transient,
Fourier.

---

## Block 1 — Video amplifier (`video_amp.cir`, `video_amp_radar.cir`)

The two-stage TL072 gain block between the mixer's IF port and the sound card.

**Parts**

| ref | value | Multisim | note |
|---|---|---|---|
| RS | 50 Ω | RESISTOR | *models the mixer's IF source impedance* — in series with the source |
| R1 | 49.9 Ω | RESISTOR | IF termination, to ground |
| C20 | 1 nF | CAPACITOR | RF stop, to ground |
| C1, C2 | 100 nF | CAPACITOR | coupling / high-pass |
| R2, R6 | 10 kΩ | RESISTOR | to VREF (159 Hz corners with C1/C2) |
| U1A, U1B, U2B | TL072CP | OPAMP | V+ = VANA, V− = ground |
| R3 | 100 kΩ | RESISTOR | U1A feedback |
| R4 | **1 kΩ** (gain 101) or **4.7 kΩ** (gain 22, first power-up) | RESISTOR | U1A − input to VREF |
| R7 | 10 kΩ (gain 11) or **0 Ω link** (unity, JP2 closed) | RESISTOR | U1B feedback |
| R8 | 1 kΩ | RESISTOR | U1B − input to VREF |
| R12 | 1 kΩ | RESISTOR | low-pass |
| C9 | 10 nF | CAPACITOR | low-pass, to VREF |
| R13 | 100 Ω | RESISTOR | output isolation |
| C10 | 10 µF | CAP_ELECTROLIT | + toward R13 |
| R14 | 100 kΩ | RESISTOR | output bleed to ground |
| RLOAD | 10 kΩ | RESISTOR | *models the sound-card line input* |
| VANA | 11.4 V | DC_POWER | op-amp rail |
| VREF | 5.7 V | DC_POWER | half rail (or wire in Block 2) |

**Input** — AC_VOLTAGE (or XFG) in series with RS = 50 Ω. Amplitude is the
source's open-circuit value; the 50 Ω / 49.9 Ω divider halves it at the IF
node, so *all gains below are quoted from the source*, 6 dB below the
"from the IF node" gain.

**Test 1a — frequency response** (AC Sweep 1 Hz → 100 kHz, or Bode Plotter
in→out, source AC magnitude 1 V):

| setting | 12.5 Hz | 159 Hz | 417 Hz | 1 kHz | 15.9 kHz | 22 kHz | peak |
|---|---|---|---|---|---|---|---|
| full: R4 = 1k, R7 = 10k | **10.6 dB** | 48.7 | 53.6 | 54.5 | 50.7 | 48.0 | 54.6 dB @ ~1.8 kHz |
| first power-up: R4 = 4.7k, R7 = 0 | — | 14.8 | — | **20.6 dB** (×10.7) | 17.8 | — | ~20.7 dB |

Read: leakage at 12.5 Hz is **44 dB below** the 417 Hz drone tone in the full
configuration — that is the whole job of the two high-passes. The low-pass
gives only ~6.5 dB at 22 kHz; the sound card's own filter does the rest.

**Test 1b — transient, first power-up config** (R4 = 4.7k, R7 = 0). XFG sine
1 kHz, **10 mV peak** (7.07 mV RMS), scope on the output: **107 mV peak**
(76 mV RMS), clean sine, no clipping. Also probe AOUT (U1A output): about
50 mV peak around VREF.

**Test 1c — transient, full gain** (R4 = 1k, R7 = 10k). Do **not** use
10 mV: the output clips at ±4.1 V (VANA − 1.5 V) — you'll see 8.2 V pk-pk
flat-topped. Use **0.5 mV peak** → 0.27 V peak out. This is why the jumpers
exist.

**Test 1d — the actual radar signal** (`video_amp_radar.cir`, full gain).
Two AC sources in series behind RS: **8 mV peak at 12.5 Hz** (TX→RX
leakage) + **40 µV peak at 417 Hz** (the drone at 10 m). Transient 2 s,
Fourier/XSA on the output:

| | input | output |
|---|---|---|
| 12.5 Hz leakage | 8 mV | **27 mV** |
| 417 Hz drone | 40 µV | **19 mV** |
| leakage-over-drone | 46 dB | **2.9 dB** |

Output swing ~0.1 V pk-pk — nothing clips, and the drone tone is no longer
buried. That is the pass criterion for the whole block.

---

## Block 2 — Buffered half-rail reference (`vref_bias.cir`)

| ref | value | Multisim |
|---|---|---|
| R9, R10 | 10 kΩ | RESISTOR (VANA → VDIV → GND) |
| C5 | 10 µF | CAP_ELECTROLIT, VDIV to GND |
| U2A | TL072CP | follower: + to VDIV, − to output |
| R11 | 47 Ω | RESISTOR, U2A out → VREF |
| C6 | 47 µF | CAP_ELECTROLIT, VREF to GND |
| RL | 2.2 kΩ | RESISTOR, VREF to GND (*models the six 10k/1k returns hanging on VREF*) |
| VANA | 11.4 V DC **+ 100 mV peak, 150 kHz** | DC_POWER in series with AC_VOLTAGE (buck ripple) |

- DC Operating Point: VDIV = **5.70 V**, VREF = **5.70 V** (macro model shows
  5.58 V because of its 100 Ω output; TL072CP will read ~5.70).
- AC Sweep VANA → VREF: **−41 dB at 100 Hz, −79 dB at 1 kHz, < −150 dB at
  150 kHz**. Transient: VREF ripple **unmeasurable** (< 1 µV) with 100 mV of
  150 kHz on the rail. If you see ripple, C5 or C6 is missing.

---

## Block 3 — 12 V input, protection, VANA filter (`power_in.cir`, `power_reverse.cir`)

| ref | value | Multisim |
|---|---|---|
| D1 | 1N5822 | SCHOTTKY_DIODE, anode to VIN, cathode = VPROT |
| C11 | 100 µF | CAP_ELECTROLIT, VPROT to GND |
| RBUCK | 60 Ω | RESISTOR (*models the LM2596 drawing 0.2 A*) |
| R15 | 10 Ω | RESISTOR, VPROT → VANA |
| C13 | 100 µF | CAP_ELECTROLIT, VANA to GND |
| ROPA | 1.1 kΩ | RESISTOR (*models two TL072 + dividers, ~10 mA*) |
| VIN | 12 V DC **+ 100 mV peak, 150 kHz** | DC_POWER + AC_VOLTAGE |

- DC: VPROT = **11.7 V**, VANA = **11.6 V** (0.3 V diode, 0.1 V across R15).
- Transient: VANA ripple **4 mV pk-pk** from 200 mV pk-pk on VIN
  (**−83 dB** at 150 kHz on the AC sweep; −2 dB at 120 Hz — the RC is for
  switching hash, not mains hum).
- **Reverse test:** VIN = −12 V DC → VPROT = **−0.1 mV**, input current
  **2 µA**. Nothing downstream sees it.

---

## Block 4 — Sync divider into the sound card (`sync_div.cir`)

| ref | value | Multisim |
|---|---|---|
| VGPIO | PULSE 0 → 3.3 V, rise/fall 10 ns, **width 6.4 ms, period 7.4 ms** | PULSE_VOLTAGE |
| RG | 30 Ω | RESISTOR (*GPIO output impedance*) |
| R23 | 10 kΩ | RESISTOR |
| R24 | 1 kΩ | RESISTOR, to GND |
| CCPL | 10 µF | CAPACITOR (*sound-card input coupling*) |
| RSC | 10 kΩ | RESISTOR (*sound-card input*) |

Scope, two channels, 60 ms:
- At the divider (AUDIO_R): **283 mV high, 0 V low**, clean square wave.
- After the coupling capacitor (what the software actually receives):
  **+201 mV to −100 mV**, the 6.4 ms plateau droops toward zero and the
  1 ms retrace is a negative pulse. The waveform has no DC level to
  threshold on; `radar_acquire.py` detects the **edges**, which survive.
  Try CCPL = 1 µF to see a worse card.

---

## Block 5 — Mixer IF input: termination + RF stop (`if_input.cir`)

| ref | value |
|---|---|
| VIF + RS 50 Ω | AC_VOLTAGE 1 V (*the mixer's IF port Thevenin*) |
| R1 | 49.9 Ω to GND |
| C20 | 1 nF to GND |
| C1 100 nF → R2 10 kΩ to GND | the first high-pass, for reference |

AC Sweep 10 Hz → 10 GHz, probe the IF node and the op-amp input:

| | 417 Hz | 1 MHz | 100 MHz | **2.44 GHz** |
|---|---|---|---|---|
| IF node vs source | −6.0 dB (the 50/49.9 divider) | −6.2 | −30 | **−58 dB** |

52 dB of rejection of the LO that leaks out of the mixer's IF port, from one
1 nF capacitor, with 0.05 dB loss at the beat frequency. Without C20 the
2.44 GHz line is flat at −6 dB and a TL072 will rectify it.

---

## Block 6 — The radar, scaled for SPICE (`fmcw_beat.cir`)

Chirp × delayed chirp = beat tone at `f_b = B·τ/T`. The carrier frequency
cancels, so the physics can be run at frequencies SPICE (and Multisim) can
handle:

| | real radar | this model |
|---|---|---|
| sweep | 2440 → 2480 MHz, B = 40 MHz | 1 → 5 MHz, **B = 4 MHz** |
| chirp time T | 6.4 ms | 6.4 ms |
| target delay τ (10 m) | 66.7 ns | **667 ns** (×10, because B is ÷10) |
| leakage delay (0.3 m) | 2 ns | 20 ns |
| beat f_b = B·τ/T | **417 Hz** | **417 Hz** |
| leakage beat | 12.5 Hz | 12.5 Hz |

**Build in Multisim**
- Chirp: `VOLTAGE_CONTROLLED_SINE_WAVE`, frequency range 1 MHz at 0 V → 5 MHz
  at 1 V, driven by a `PWL` ramp 0 → 1 V over 6.4 ms (repeat 3 times).
- Echo: `TRANSMISSION_LINE` lossless, Z0 = 50 Ω, **TD = 667 ns**, terminated
  50 Ω, then a gain block ×0.01 (−40 dB).
- Leakage: second line, TD = 20 ns, gain ×1 (switchable to 0).
- Mixer: `MULTIPLIER` (tx × (echo + leakage)).
- After it: R12 1 kΩ / C9 10 nF low-pass, then C1 100 nF/R2 10 kΩ and
  C2 100 nF/R6 10 kΩ high-passes (the video amp's filters).
- Transient: max step 10 ns, 19.2 ms. Spectrum Analyzer / Fourier on ONE
  chirp (e.g. 6.72–12.8 ms), Hanning.

**Expected**
- Leakage gain = 0: **peak at 417 Hz, 4.5 mV** (0.5 × 0.01 × 0.93 × 1 V).
  Move TD to 333 ns → 208 Hz; to 1 µs → 625 Hz. Range is pitch.
- Leakage gain = 1: the 417 Hz bin is still **4.4 mV**, but the single-chirp
  spectrum below ~250 Hz is dominated by the 12.5 Hz leakage's window
  skirt (one chirp is only 0.08 cycles of it). This is exactly why the real
  processing subtracts the chirp-to-chirp mean before the range FFT: the
  leakage is identical every chirp and vanishes; the drone's echo changes
  phase every chirp and survives.

---

## Not in Multisim — and what to do instead

| block | why not | what the test is |
|---|---|---|
| ADF4351 sweep | no model; 2.4 GHz | `radar_ctl` status shows `lock:1`; a spectrum analyser or an RTL-SDR with a 30 dB pad sees the CW tone at `CW 2440` |
| PA / LNA (SPF5189Z), splitter, mixer at RF | no models | the level budget in `docs/radar-hardware.md` §0, measured with a power meter or an SDR + pad at each SMA |
| horns | electromagnetic, not circuit | `docs/radar-hardware.md` § 2c: S11 ≤ −10 dB, TX–RX isolation ≤ −35 dB, gain by the two-antenna method — and why you do not need a VNA to build this |
| ESP32 / A4988 / stepper | digital + motor | bench: `AZ 30`, protractor |

The rule of thumb: everything left of the mixer's IF port in the schematic
is a circuit and Multisim can test it; everything right of it is RF and
gets tested with instruments on the bench.
