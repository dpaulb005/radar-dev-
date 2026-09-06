# Building the MIT radar with a custom antenna — full plan

> **Build it from the step-by-step guides:** [`radar-hardware.md`](radar-hardware.md)
> and [`radar-software.md`](radar-software.md). The parts list in §4 below
> predates the September 2026 sourcing check — the ZX95 VCO is non-catalog
> and two Mini-Circuits parts are out of stock; the current, priced list is
> [`../hardware/BOM.md`](../hardware/BOM.md).


**Read this first, then `Phase 0`. Nothing here needs you to buy anything until
you have run the simulator and are happy with the numbers.**

This is a real radar: it **transmits** a swept signal and measures the **echo**
off a target. That is the thing you originally asked for back at the start of
this project and that I told you was not achievable passively — and I was right
about the *passive* version, but an **active FMCW radar makes it achievable**,
which is exactly what the MIT design is. It measures true range and velocity
from reflections, off targets that carry no transmitter at all.

Everything below is either quoted from a primary source or computed by the two
tools added to this repo:

```bash
python ground_station/fmcw_sim.py --budget       # radar performance + link budget
python ground_station/fmcw_sim.py --leakage      # the failure mode that bites everyone
python ground_station/fmcw_sim.py --microdoppler # how to see a HOVERING drone
python antenna/vivaldi.py --array 4 --svg a.svg  # the custom antenna
```

---

## 0. STOP — the one thing that will break this project

**Your radar and your drone both want 2.4 GHz, and the radar will jam the
drone.**

The MIT radar transmits **+13 dBm continuously**, swept across 2.36–2.50 GHz.
Your ESP-BLAST is flown over ESP-NOW on **WiFi channel 7 (2.442 GHz)** — right
in the middle of that sweep.

Run the numbers: +13 dBm into a 9 dBi antenna is +22 dBm EIRP. At 10 m the free
space loss is ~60 dB, so the drone's receiver sees the radar at **≈ −38 dBm**,
while the wanted control signal from your commander arrives at maybe −50 to
−60 dBm. **The interferer is 12–22 dB stronger than the signal you are trying to
fly on.** The radar dwells in the drone's 20 MHz channel ~14 % of each sweep, so
you would get heavy, bursty packet loss on the control link precisely when the
drone is close — which is exactly when you care.

> **Now unambiguous.** This project no longer does any passive RF tracking, so
> nothing needs the drone to keep a 2.4 GHz link alive. The conflict noted in
> `espfly.md` is gone: **move the drone to 915 MHz ELRS, no downside.**

### The fix: move the drone's control link off 2.4 GHz

ESP-FC already supports **CRSF/ELRS** (verified in its README feature list,
alongside PPM/SBUS/IBUS). So:

> **Replace the 2.4 GHz ESP-NOW link with a 900 MHz ExpressLRS link.**
> A 915 MHz ELRS RX (~$20) plus a 915 MHz ELRS TX module gives you a clean,
> long-range control link **1.5 GHz away from the radar band**, and it is
> *better* than ESP-NOW for range and link robustness anyway.

This has a second benefit: it removes the exclusive-binding awkwardness from
`docs/interception.md` §3 (ELRS has proper binding and a real failsafe), and it
frees the whole 2.4 GHz band for the radar.

**Do this before you build the radar, not after.** It changes the drone build.

---

## 1. Second constraint: stay inside the ISM band

The stock MIT design sweeps **2.36–2.50 GHz**. The bottom of that sweep is *not*
license-free in the US: **2360–2395 MHz is allocated to Aeronautical Mobile
Telemetry and medical body-area networks**, not to unlicensed devices. MIT ran
the course in an institutional context; you should not radiate there.

**Restrict the sweep to the 2.4 GHz ISM band: 2400–2483.5 MHz = 83.5 MHz.**

What that costs you (computed):

| | full MIT sweep (140 MHz) | **ISM-legal (83.5 MHz)** |
|---|---|---|
| range resolution `c/2B` | 1.07 m | **1.80 m** |
| legal unlicensed? | ✗ (dips into AMT band) | **✓** |

1.80 m resolution is fine for detecting a drone in a 5–10 m box — you are not
trying to resolve two drones 1 m apart. Take the legality.

---

## 1b. It measures range and velocity — NOT position

One TX horn + one RX horn has **no angle information**. To get position you
must scan the antennas (a ~$15 servo) or add a second receive channel.
This is a first-order architectural requirement, not a refinement — the full
analysis, the measured beam-stepping tradeoff and the end-to-end result
(**0.12 m RMS tracking error**) are in **[`scanning.md`](scanning.md)**.

## 2. What you actually get (computed, not guessed)

`fmcw_sim.py --f0 2.4 --sweep-bw 83.5 --chirp-ms 2`:

```
range resolution    : 1.80 m        <- bandwidth-limited, c/2B
max unambiguous rng : 79 m          <- sound-card Nyquist
velocity window     : +/-15.3 m/s
velocity resolution : 0.48 m/s
beat freq @ 10 m    : 2785 Hz       <- lands nicely in audio
```

Detection margin on **your** drone:

| target | RCS | echo @ 10 m | **SNR @ 10 m** |
|---|---|---|---|
| **small quad (ESP-BLAST class)** | 0.01 m² | −83 dBm | **58 dB** |
| larger quad (Phantom class) | 0.10 m² | −73 dBm | 68 dB |
| human | 1.0 m² | −63 dBm | 78 dB |
| car | 10 m² | −53 dBm | 88 dB |

**58 dB of margin on a small drone at 10 m.** Sensitivity is not your problem —
this radar sees your drone easily at the ranges you care about. Your problems
are the three below.

---

## 3. The three things that will actually bite you

### 3a. TX→RX leakage will drown the target (and background subtraction fixes it)

At short range the transmitter leaks directly into the receiver, ~35 dB down,
which is *enormously* stronger than any echo. Simulated, with a drone at 8 m
closing at 2 m/s:

```
raw (leakage present)        -> detected R = 2.1 m, v = 0.0 m/s   WRONG (leakage wins)
WITH background subtraction  -> detected R = 8.6 m, v = +1.9 m/s  correct
```

**Background subtraction** — subtract the average of the last N chirps before
the Doppler FFT — removes anything that doesn't move. That is one line of DSP
and it is the single most important line in the whole system.

### 3b. A HOVERING drone disappears — use the rotor lines

Background subtraction deletes everything at zero Doppler. A hovering drone is
at zero Doppler. It vanishes along with the clutter.

The way out is **rotor micro-Doppler** (`--microdoppler`). Your rotors do not
hover even when the airframe does:

```
prop 2.5", 20000 RPM, 3 blades
blade tip speed  : 66 m/s
tip Doppler      : +/-1.08 kHz      <- lands in the audio band
blade flash rate : 1000 Hz
body Doppler if hovering: 0 Hz      <- removed by clutter cancellation
```

**Look for a symmetric pair of sidebands ~1.1 kHz either side of DC that switch
on and off with the throttle.** That signature is also how you tell a drone from
a bird, a person, or a swaying tree — it is the classic drone-detection
discriminator, and it survives clutter cancellation.

### 3c. The default 20 ms chirp aliases a moving drone

At the MIT default 20 ms sweep the unambiguous velocity window is only
**±1.5 m/s**. The simulator demonstrates the failure: a target truly moving at
+2.0 m/s reads back as **−1.0 m/s**. Shorten the chirp:

| chirp | velocity window | max range |
|---|---|---|
| 20 ms (MIT default) | ±1.5 m/s | 472 m |
| 5 ms | ±6.2 m/s | 118 m |
| **2 ms (recommended)** | **±15.4 m/s** | **47–79 m** |
| 1 ms | ±30.8 m/s | 24 m |

**Use ~2 ms.** You trade unusable range for usable velocity.

---

## 4. Parts list

### 4a. RF chain — the six coax parts (unchanged from MIT)

| Callout | Qty | Part | Description | Supplier | Unit | Total |
|---|---|---|---|---|---|---|
| OSC1 | 1 | **ZX95-2536C+** | VCO, 2315–2536 MHz, +6 dBm | Mini-Circuits | $98.95 | $98.95 |
| ATT1 | 1 | **VAT-3+** | 3 dB SMA attenuator | Mini-Circuits | $13.95 | $13.95 |
| PA1/LNA1 | 2 | **ZX60-272LN-S+** | Amp, 14 dB gain, NF 1.2 dB | Mini-Circuits | $69.95 | $139.90 |
| SPLTR1 | 1 | **ZX10-2-42+** | Splitter, 1900–4200 MHz | Mini-Circuits | $34.95 | $34.95 |
| MXR1 | 1 | **ZX05-43MH-S+** | Mixer, +13 dBm LO | Mini-Circuits | $46.45 | $46.45 |
| — | 4 | **SM-SM50+** | SMA M-M barrels | Mini-Circuits | $5.95 | $23.80 |
| — | 3 | **086-12SM+** | 6″ SMA M-M cables | Mini-Circuits | $12.95 | $38.85 |

**RF subtotal ≈ $397.** All still stocked (DigiKey/Mini-Circuits).

### 4b. Baseband, modulator, power

| Part | Description | Supplier | Cost |
|---|---|---|---|
| **LT1214CN** | Low-noise quad op-amp (video amp) | DigiKey | $12.37 |
| ~~XR-2206~~ → **ESP32** | sweep generator — see modernisation below | you have one | $0 |
| EXP-300E | solderless breadboard | Mouser | $7.45 |
| 172-2236 | 3.5 mm plug → stripped wires | Mouser | $3.63 |
| 2× SMA bulkhead, brackets, 6-32 hardware | mounting | McMaster/Mouser | ~$25 |
| 8× AA battery holder + batteries | power (keep it off mains — less noise) | — | ~$10 |
| **Servo + bracket (e.g. MG996R) for the scan** | **turns range-only into position — see `scanning.md`** | — | **~$15** |
| Assorted 1 % resistors / 1000 pF caps | baseband filter | DigiKey | ~$6 |

**Total ≈ $460** with the ESP32 modernisation, ≈ $470 with the original XR-2206.

### 4c. Recommended modernisation: replace the XR-2206 with an ESP32

The XR-2206 function generator is long obsolete and increasingly counterfeit on
the open market. You already have ESP32s. Drive the VCO tuning voltage from an
**ESP32 DAC** (or a cheap MCP4921 SPI DAC for cleaner 12-bit steps) instead:

- **software-defined waveforms** — sawtooth, triangle, arbitrary, and you can
  change bandwidth/chirp time in code instead of swapping resistors;
- **synchronisation** — the same MCU can trigger the ADC/audio capture, which
  removes the sweep-to-capture alignment problem that plagues the sound-card
  build;
- it's the same modernisation the University of Alabama in Huntsville thesis
  *"Future-proofing the MIT coffee can radar"* (2022) made, along with moving
  to surface-mount parts and — note — **Vivaldi antennas**.

Buffer the DAC output with an op-amp and scale it to the VCO's 0–5 V tuning
range. Check the VCO tuning curve is monotonic and linearise it in software
(it is quite nonlinear; linearising is worth ~a bin of range resolution).

---

## 5. The custom antenna

### Why Vivaldi (and not a patch, and not the cans)

An FMCW radar has to stay matched across its **whole sweep**. Over 2.40–2.4835
GHz that's 3.4 %, and you want margin either side. An FR4 patch manages ~1–3 % —
marginal. A **Vivaldi (exponentially tapered slot) runs over octaves.** It is
also flat, repeatable, and manufacturable as an ordinary 2-layer PCB from the
same fab you already use for the flight controller.

`python antenna/vivaldi.py`:

```
band            : 2.30 - 2.60 GHz  (12.2 % fractional)
substrate       : FR4, er=4.4, h=1.6 mm, 1 oz Cu
mouth aperture W: 75.6 mm    (rule: >= lambda/2 = 65.2 mm)
flare length  L : 136.9 mm   (rule: >= lambda   = 130.3 mm)
throat slot     : 0.50 mm
opening rate R  : 0.0367 /mm
50 ohm feed     : 3.06 mm microstrip
board           : 162 x 84 mm
est. gain       : ~6.4 dBi  (single element)
```

**Be honest about the trade:** a *single* Vivaldi is ~6.4 dBi — slightly **worse**
than a coffee can (~9 dBi). The Vivaldi wins when you **array** it:

| configuration | gain | board | notes |
|---|---|---|---|
| coffee can | ~9 dBi | free | works, bulky, can't array |
| single Vivaldi | ~6.4 dBi | 162×84 mm | flat, repeatable, easy |
| **4-element Vivaldi array** | **~12.4 dBi** | 192×277 mm | +6 dB, ~51° az beam, needs a feed network |

`python antenna/vivaldi.py --array 4 --svg viv4.svg` writes the outline; import
into KiCad (File → Import → Graphics, 1:1), copper on `F.Cu`, outline on
`Edge.Cuts`.

### The array unlocks the thing you were worried about last night

Two RX Vivaldis spaced λ/2 give you **azimuth angle from the phase difference**
between channels. Range (from the beat) + angle (from the phase) = a genuine 2D
position fix **from a single radar site** — no multilateration, no coplanar-node
mirror ambiguity. That is a fundamentally better answer to your 3D question than
anything the RSSI system can do. It needs a second receive channel (a second
mixer + amp, ~$116), so treat it as Phase 5, not Phase 1.

---

## 6. How to simulate before you spend $460

**Two different simulations, don't confuse them:**

### 6a. System/signal simulation — `ground_station/fmcw_sim.py` (built, works now)

Models the whole chain: chirp → target echo → mixer beat → range FFT → Doppler
FFT → range-Doppler map, including thermal noise, TX leakage and ADC dynamic
range. Use it to choose bandwidth, chirp time and antenna gain **before**
ordering, and to develop your DSP against known ground truth.

```bash
python ground_station/fmcw_sim.py --budget                 # can it see my drone?
python ground_station/fmcw_sim.py --chirp-ms 2 --leakage   # prove background subtraction
python ground_station/fmcw_sim.py --chirp-ms 2 --rdmap rd.png
python ground_station/fmcw_sim.py --microdoppler --rpm 20000
```

### 6b. Electromagnetic simulation — openEMS (for the antenna only)

The antenna is the one part you cannot compute with algebra; it needs a
full-wave solver. **openEMS** is the free FDTD solver (the same one I suggested
back in the radar-simulation-software roadmap — this is where it earns its
keep).

```bash
pip install openEMS   # plus CSXCAD; see docs.openems.de
python antenna/vivaldi.py --openems > viv_sim.py   # scaffold + pass criteria
```

Work through the official **Simple Patch Antenna** tutorial first (an hour), then
adapt it — the mechanics (mesh, port, NF2FF far-field transform) are identical.

**Pass criterion: |S11| < −10 dB across 2.40–2.4835 GHz.** If the sim doesn't
hit that, change `--f-low` / throat width / opening rate and re-run. Iterating in
the solver is free; iterating in FR4 is $30 and two weeks each time.

---

## 7. Build plan

Each phase ends in a checkpoint. **Do not skip checkpoints** — an FMCW radar
that doesn't work is very hard to debug from the far end.

### Phase 0 — Simulate and decide (this week, $0)
Run `fmcw_sim.py --budget` and `--leakage`. Convince yourself the SNR margin and
the resolution are what you want. Decide sweep bandwidth (83.5 MHz) and chirp
time (2 ms).
**Checkpoint 0:** you can explain why 1.80 m resolution and ±15 m/s are the right
trades for your box.

### Phase 1 — Move the drone off 2.4 GHz (before anything else)
Fit a 915 MHz ELRS receiver to the ESP-BLAST, set ESP-FC's receiver to CRSF, bind
to a 915 MHz TX module, verify failsafe.
**Checkpoint 1:** the drone flies normally with the 2.4 GHz radio physically
removed. *You cannot safely test the radar near the drone until this is true.*

### Phase 2 — Antenna in simulation
Run `vivaldi.py`, port into openEMS, iterate to |S11| < −10 dB across the band.
**Checkpoint 2:** a simulated S11 plot meeting the criterion, and a far-field
pattern showing endfire gain ≈ 6–7 dBi.

### Phase 3 — Build the radar with coffee cans first
Order the RF BOM. Build on the breadboard exactly per the MIT design, but drive
the VCO from your ESP32 DAC. **Use coffee cans for the first light** — they are
free, known-good, and remove the antenna as a variable while you debug the RF
chain.
**Checkpoint 3:** point it at a car driving past and see a clean range line in
the MIT `Experiment 2` MATLAB/Python processing. This is the classic first
success and it validates the entire chain.

### Phase 4 — Swap in the custom Vivaldis
Order the PCBs (JLCPCB, 1.6 mm FR4, 1 oz). Measure S11 with a NanoVNA
(~$50 — buy one, you will use it forever) and compare against the openEMS
prediction.
**Checkpoint 4:** measured S11 within a few dB of simulation, and the radar
still sees the car. Then try the drone.

### Phase 5 — Drone detection and tracking
Hover the drone at 5–10 m. Find the body return (moving) and the **rotor
micro-Doppler lines** (hovering). Implement background subtraction and a simple
CFAR detector.
**Checkpoint 5:** you can plot drone range vs time as it flies, and identify it
as a drone from the rotor lines.

### Phase 6 — Angle, and integration with the interception project (optional)
Add a second RX channel and a two-element RX array for azimuth. Feed range +
angle into the existing tracker in place of (or alongside) the RSSI fixes.

---

## 8. Legal and safety

- **Stay in 2400–2483.5 MHz.** Do not radiate in 2360–2400 (AMT/MBAN).
  20 mW EIRP-class in ISM is the benign case, but keep the sweep inside the band.
- Do not point it at people at close range for extended periods. 20 mW is very
  low power (a WiFi router is 100 mW) but there is no reason to dwell on anyone.
- The 915 MHz ELRS link must respect your region's ISM rules (US 902–928 MHz).
- Everything in `docs/interception.md` §8 still applies to the flying side —
  VLOS, a human on the kill switch, tracking only, never weaponised.

---

## 9. How this fits the existing project

This does **not** throw away what we built. The two systems answer different
questions and complement each other:

| | passive RSSI system (built) | **FMCW radar (this plan)** |
|---|---|---|
| target must cooperate? | **yes** — must transmit | **no** — detects reflections |
| what it measures | position (multilateration) | **true range + velocity** |
| horizontal accuracy | ~2 m | ~1.8 m (resolution-limited) |
| altitude | ✗ (needs baro) | ✗ single site; ✓ with an array |
| identifies a drone? | by MAC | **by rotor micro-Doppler** |
| cost | ~$56 | ~$460 |

For the two-drone interception goal, the natural end state is: **track your own
interceptor cooperatively** (it carries your ESP32 and tells you where it is)
and **track the target by radar** (it doesn't have to cooperate at all). That is
a much stronger system than either half, and it's the architecture a real
counter-UAS installation uses.

---

## 10. First three things to do when you wake up

1. `python ground_station/fmcw_sim.py --budget` — see the 58 dB margin yourself.
2. Order a **915 MHz ELRS RX + TX module** (~$50). This is on the critical path
   and everything else waits on it.
3. Read the MIT course's **Radar System Design** PDF (block diagram, schematics,
   BOM, fabrication) — it is the canonical build reference:
   `ocw.mit.edu` → RES.LL-003 → Projects → *Radar System Design*.

Send me the transcript from the other session when you're up and I'll fold in
whatever it decided that this plan doesn't already cover.
