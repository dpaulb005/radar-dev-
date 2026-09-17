# radar-dev — a horn-fed 2.4 GHz FMCW radar that tracks a small drone

A frequency-modulated continuous-wave radar in the MIT "coffee-can" tradition,
fed by pyramidal horns cut from copper sheet, that finds a 25 g quadcopter at
3–10 m indoors by its reflection alone. The drone carries no beacon and no
transponder: it is a target.

One transmit horn, one receive horn. It measures **range and radial velocity**.

```
 ESP32 steps an ADF4351 PLL 2400 → 2483.5 MHz in 64 steps / 6.4 ms
   → 3 dB pad → PA → splitter ─┬─► TX horn ─── echo off the drone ──► RX horn
                               └─► mixer LO ◄──────── LNA ◄── band-pass ◄──┘
 mixer IF = beat tone, pitch ∝ range (870 Hz at 10 m)
   → video amp (TL072, 61 dB) → USB audio interface
   → laptop: range FFT · Doppler FFT · CFAR → Kalman tracker → console
```

| | |
|---|---|
| sweep | 2400–2483.5 MHz (83.5 MHz), 6.4 ms up-chirp, 7.4 ms PRI |
| range cell | 1.80 m, 0.04 m mean accuracy on the stepped waveform |
| velocity | 0.13 m/s resolution, unambiguous to ±4.15 m/s |
| antenna | optimum pyramidal horn, 264 × 193 mm aperture, 13.4 dBi, ~34° × 36° beam |
| drone echo at 10 m | −77 dBm (0.01 m² RCS), 72 dB above the leakage-limited floor after 64 chirps |

## What is here

This branch holds the design deliverables only. Everything used to produce them
(firmware, signal processing, the model generators, the full design notes) is
on the [`dev`](https://github.com/dpaulb005/radar-dev-/tree/dev) branch.

| | what | status |
|---|---|---|
| [`BOM_Radar_Build.xlsx`](BOM_Radar_Build.xlsx) | bill of materials: every part, its price and where to buy it | priced Sept 2026 |
| [`antenna/`](antenna/) | the horn: design dimensions and the HFSS simulation results | **simulation in progress**, results and the LaTeX report land in `antenna/results/` |
| [`3d/`](3d/) | 3D models of the radar bench and the drone: open `radar-bench.html` or `drone.html` in a browser, plus rendered views | done |
| [`breadboard/`](breadboard/) | the baseband board: schematics, hole-by-hole wiring, 17 build steps, the pick list, and the Multisim files for each block | **bench test pending**, Multisim circuits to be added |

## Where it stands

- **Designed and documented:** the RF chain, the horn, the video amplifier,
  the frame, the drone's 915 MHz control link.
- **Simulated:** every baseband block in SPICE, with the numbers each should
  produce recorded in `breadboard/multisim/README.md`.
- **In progress:** the HFSS model of the horn (probe match, gain, patterns) and
  the breadboard blocks re-run in Multisim.
- **Not built:** anything RF. Nothing here has been on a bench yet.

Azimuth from a second receiver is designed and tested in software but not built;
the BOM lists what it would add so nothing gets bought twice.
