# The 24 GHz build

> **Rough draft.** Nothing here has been fabricated. Every number is either
> computed by [`antenna/patch24.py`](../../antenna/patch24.py) and
> [`ground_station/fmcw_sim.py`](../../ground_station/fmcw_sim.py), or a price
> checked at a distributor in September 2026 and marked as such in
> [`BOM.md`](BOM.md). The open questions are listed at the bottom and they are
> real.

Read [`../goal.md`](../goal.md) first. This project exists to **build a radar
where I design the antenna and get azimuth on a small drone**, and that
sentence has already killed one recommendation in this repo. It is what makes
this document possible, because a fact I had wrong is what was blocking it.

---

## The thing I had wrong

[`../higher-bands.md`](../higher-bands.md) rejected every 24 GHz option on one
argument: *the antenna is already designed and soldered shut*. That is true of
the **modules** — RFbeam's K-LC6, TI's IWR6843ISK, Seeed's MR60 — and it is
why buying one fails test 1.

It is not true of the **chips**. A 24 GHz radar MMIC brings its RF ports out as
**single-ended 50 Ω pins** that are meant to be soldered to a microstrip trace,
and at 12.4 mm wavelength that trace runs a few millimetres to an antenna
etched on the same board. There is no connector, no cable, and no antenna in
the box. Infineon's BGT24LTR22 datasheet lists "single-ended RF terminals" as a
feature and Infineon's own eval board uses its TX port to "transmit the 24 GHz
microwave signal to an **external** antenna".

So the antenna is not something you buy at 24 GHz. It is a copper pattern on a
board you draw, exactly like the horn is a copper shape you fold — and it is
the *majority* of the layout work rather than a footnote. Test 1 passes.

| test | 24 GHz build |
|---|---|
| **Is the antenna mine?** | yes — three printed columns I lay out, tune and measure |
| **Azimuth on a drone that is flying?** | yes — two simultaneous receivers, one 99 ms dwell, no moving parts |
| **Is the target a small drone?** | yes — 38 dB of margin on 0.01 m² at 10 m |

---

## What it is

One board. A transceiver chip, a ramp PLL, and three antennas printed beside
them in the same copper.

```
        <------------------------ ~70 mm ------------------------>

        +-------------------------------------------------------+   ^
        |   ____                                  ____  ____     |   |
        |  |    |  TX                            |    ||    |    |   |
        |  |____|                                |____||____|    |   |
        |   ____   4 patches                      ____  ____     |   |
        |  |    |  6.804 mm apart                |    ||    |    |  ~50
        |  |____|  (one guide wavelength)        |____||____|    |   mm
        |   ____                                  ____  ____     |   |
        |  |    |                                |    ||    |    |   |
        |  |____|                                |____||____|    |   |
        |   ____                                  ____  ____     |   |
        |  |    |                                |    ||    |    |   |
        |  |____|                                |____||____|    |   |
        |    ||                                    ||    ||      |   |
        |    ||         <--- 37.3 mm --->          RX1  RX2      |   |
        |    ||                                     |<-->|       |   |
        |  +-+--------------------------------------+-+--+       |   |
        |  |          BGT24LTR22   (VQFN-free eWLB) |  6.213 mm  |   |
        |  +----------------------------------------+  = λ/2     |   |
        |     ADF4159 ramp PLL · 1.5 V LDO · 25 MHz TCXO         |   |
        |     4 differential IF pairs ---> ribbon ---> interface |   v
        +-------------------------------------------------------+
```

Three columns of four patches. Stacking them **vertically** narrows elevation
to 23°, which costs nothing indoors, and leaves **azimuth as the single-patch
pattern, 81° wide** — which is the sector you actually want to search. The two
receive columns then sit **λ/2 = 6.213 mm apart**, and that is the whole point:

> at 2.4 GHz the horns are 193 mm apart and the interferometer wraps outside
> **±18.4°**. At 24 GHz the same measurement is unambiguous to **±90°** — over
> the entire pattern the antenna can see. The ambiguity problem does not get
> smaller, it disappears.

---

## What it buys, in the project's own radar equation

Produced by `python3 antenna/patch24.py`, scored by the same `RadarSpec` that
scores the current build (the 2.4 GHz column reproduces the published −74 dBm
and 71 dB from [`../../README.md`](../../README.md)):

```
                                   24 GHz   2.4 GHz now
  swept bandwidth                 250 MHz        40 MHz
  range cell                       0.60 m        3.75 m
  up-chirp / PRI             1.40/1.55 ms    6.4/7.4 ms
  sample rate                     192 kHz        48 kHz
  beat at 10 m                   11913 Hz        417 Hz
  Nyquist range                      81 m         576 m
  ...on a 48 kHz card              20.1 m         576 m
  unambiguous velocity        +/-2.00 m/s   +/-4.12 m/s
  velocity cell                 0.063 m/s     0.129 m/s
  dwell, 64 chirps                  99 ms        474 ms
  antenna gain                   11.8 dBi      13.4 dBi
  echo at 10 m                   -105 dBm       -74 dBm
  SNR at 10 m                       38 dB         72 dB
  interferometer cone           +/-90 deg   +/-18.4 deg
```

**Read the trade honestly.** You spend 34 dB of echo — λ² costs 20 dB, the
printed columns are 1.6 dB down on the horns each way, the MMIC's 8 dB noise
figure costs 4 dB, and its +5 dBm transmitter is 8 dB below the amplified
2.4 GHz chain. What is left is 38 dB at 10 m against a 0.01 m² drone, which is
still more margin than the radar needs.

What you get for it:

- **a 0.60 m range cell instead of 3.75 m.** The single worst number in the
  current design. Today a drone and the wall behind it land in the same cell.
- **azimuth unambiguous over the whole pattern**, not a ±18.4° cone.
- **no WiFi in the band.** No band-pass filter, no turning the drone's access
  point down to 10 dBm, no giving up half the sweep — and it was giving up half
  the sweep that pushed the target to 2.7 FFT bins from DC and made the old
  scanning azimuth noisy in the first place ([`../signal-chain.md`](../signal-chain.md) § stage 10).
- **a 99 ms fix instead of 474 ms**, and a finer velocity cell with it.
- **no coax on the receive channels at all.** At 2.4 GHz the bearing budget is
  spent by 6 mm of cable-length mismatch ([`../azimuth.md`](../azimuth.md)).
  Here both receive paths are etched on one substrate in one process step; a
  50 µm etch mismatch is 0.84° of bearing, it is fixed, and the boresight
  calibration you already wrote removes it once.

---

## The chip, and why this one

Full reasoning in [`frontend.md`](frontend.md). The short version:

| part | TX/RX | why not |
|---|---|---|
| **BGT24LTR22** | 2 / 2 | **chosen.** Two *simultaneous* quadrature receivers, differential analog IF on pins, /16 divider sized to drive an external PLL, external VTUNE, $15.26, 1580 in stock |
| BGT24MTR12 | 1 / 2 | obsolete at DigiKey. It was the classic choice |
| BGT24LTR11 | 1 / 1 | one receiver, so no azimuth. $6.41 |
| BGT24ATR22 | 2 / 2 | its IF pins are marked *"DFT not recommend to be used by customers"* — data only leaves through the internal ADC over 400 kbit/s I²C. That deletes the video amp, the sound card and the DSP |
| ADF5901 + ADF5904 + ADF4159 | 2 / 4 | works, and gives four receivers, but $149 of silicon against $36 and two more BGAs to place |

The BGT24LTR22's two receivers are **simultaneous**, not time-multiplexed. That
matters: `--switched` mode in `radar_acquire.py` exists because a single-chain
build has to alternate antennas, and alternating halves the unambiguous
velocity and needs a firmware frame marker to recover block parity. None of
that applies here. The simultaneous path — the one that measures 0.09° rms in
simulation — is the one the hardware natively is.

---

## What survives the band change

Everything downstream of the mixer, which is most of what has been built:

| | |
|---|---|
| `ground_station/interferometer.py` | one constant: `DEFAULT_BASELINE_M = 0.006213`. The wrap logic, the calibration file, the abstain-rather-than-guess rule are all unchanged |
| `ground_station/radar_acquire.py` | unchanged; new `--f0-mhz 24000 --bw-mhz 250` |
| `ground_station/fmcw_sim.py`, `test_radar.py` | unchanged — the 34 cases are band-independent and already score this design |
| the tracker and the web console | unchanged |
| UMC404HD interface, ESP32, 13 V supply | unchanged |
| `firmware/radar_ctl` | rewritten for ADF4159 registers instead of ADF4351. Same stepped-PLL architecture, same SPI, same sync output |
| the TL072 video amplifier | **probably deleted.** The BGT24LTR22 has an integrated baseband: high-pass (20–100 kHz), 30 dB VGA in 5 dB steps, and a 600 kHz anti-alias filter. That is the video amp, on the die |
| the horns, the band-pass, the LNA, the mixer, the splitter, the pad | gone. All of it is inside the MMIC |

The thing that does **not** survive is the channel count. Two receivers × I and
Q is four analog signals, and the sync channel makes five, against the
UMC404HD's four inputs. [`frontend.md`](frontend.md) § IF path costs the three
ways out; the cheap one is to take I only from each receiver and keep the sync,
which is exactly the real-valued beat the current DSP already expects.

---

## The order of work

1. **Finish the 2.4 GHz radar.** Unchanged advice, and Kevin's. Everything
   above assumes the DSP is written and tested, and it is.
2. **A $5 FR-4 dimension-sweep panel.** Seven patches, lengths stepped 40 µm,
   resonating from 23.18 to 25.15 GHz. Measure which one lands at 24.125 and
   use its length on the Rogers board. See [`antenna.md`](antenna.md) § the
   panel — and note the substrate check says **neither** substrate is
   guaranteed to land in band on tolerance alone, which is the entire argument
   for measuring before committing.
3. **The Rogers board.** [`BOM.md`](BOM.md), $270–$600 depending on quotes.
4. **Port the firmware**, run `test_radar.py`, run the interferometer.

---

## What is still open

These are the things that would change the plan if they came back wrong.

- **The PCB quote.** Rogers material is $46–78/ft², so a 70 × 50 mm board is
  about **$2.30 of laminate** — the cost is entirely fab setup, and neither
  JLCPCB nor PCBWay publishes it outside an instant quote. [`BOM.md`](BOM.md)
  ranges it $120–350 and that range is the single biggest uncertainty here.
- **Assembly.** The BGT24LTR22 is a 52-ball eWLB on a 3.63 mm body. That is not
  a hand-soldering job and not a hot-plate job. It is stencil, paste and a
  reflow profile, or turnkey assembly with a consigned part.
- **Measurement.** A $65 NanoVNA stops at 1.5 GHz; there is no hobby instrument
  that sees 24 GHz. The antenna gets characterised the way the horn's probe
  depth was — against detection SNR on a known reflector at a known range —
  unless a 24 GHz VNA can be borrowed.
- **RCS at 24 GHz.** Every link budget in this repo assumes 0.01 m² for the
  25 g quad, measured by nobody. At 12.4 mm wavelength the airframe is
  electrically large where at 122 mm it was not, so the number is probably
  better than assumed, but it is an assumption.
- **Mutual coupling** between the two receive columns at a 2.14 mm copper gap.
  The design assumes it is small enough to ignore; it is the first thing a
  simulation should check.
