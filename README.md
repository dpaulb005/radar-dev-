# radar-dev — a horn-fed FMCW radar that tracks a small drone

An MIT "coffee-can" style 2.4 GHz FMCW radar, rebuilt with hand-made
pyramidal horns, that finds a 25 g quadcopter (Seeed ESP-FLY) at 3–10 m
indoors by its **reflection** — the drone carries nothing and cooperates with
nothing. The drone is flown from a phone over its own WiFi; the radar shares
the band by sweeping above the WiFi channel.

## How it works

```
 phone ──WiFi ch 1──► drone                       (control plane)

 ESP32 steps an ADF4351 PLL 2440→2480 MHz in 64 steps / 6.4 ms
   → 3 dB pad → PA → splitter ─┬─► TX horn ─── echo off the drone ──► RX horn
                               └─► mixer LO ◄──────── LNA ◄── band-pass ◄──┘
 mixer IF = beat tone, pitch ∝ range (417 Hz at 10 m)
   → video amp (TL072, 60 dB, 159 Hz HP ×2, 15.9 kHz LP) → USB sound card
   → laptop: range FFT · Doppler FFT · CFAR · phase difference between two receivers → azimuth
   → Kalman tracker → web console                 (sensing plane)
```

| | |
|---|---|
| sweep | 2440–2480 MHz (40 MHz), 6.4 ms up-chirp, 7.4 ms PRI |
| range cell / accuracy | 3.75 m / ~0.2 m after peak interpolation |
| azimuth | phase between two RX horns 193 mm apart → 0.09° rms, in one 0.47 s dwell |
| drone echo at 10 m | −74 dBm, 71 dB SNR after 64 chirps |
| phone link margin | ~20 dB at the drone's receiver; AP at 10 dBm, band-pass and operator placement protect the radar |
| stages | 1 range + velocity · 2 second RX horn → azimuth · turntable optional, coverage only |

## Implement

Read in this order. Each step ends with a checkpoint you can verify before
moving on.

1. **[`hardware/BOM.md`](hardware/BOM.md)** — every part, priced and stock-checked (Sept 2026). Order the mixer first.
2. **[`docs/radar-hardware.md`](docs/radar-hardware.md)** — horns (cut list, all three at once), the three-horn frame, RF chain in MIT order, the breadboard video amp, sync, power, and the seven decisions that make stage 1 upgrade to azimuth without a rebuild.
3. **[`docs/radar-software.md`](docs/radar-software.md)** — flash `firmware/radar_ctl`, run `ground_station/radar_acquire.py`, feed the console.
4. **[`docs/drone-hardware.md`](docs/drone-hardware.md)** — build the kit exactly per its guide; the one thing to leave off.
5. **[`docs/drone-software.md`](docs/drone-software.md)** — the kit's official build and flash, with two menuconfig changes (channel 1, 10 dBm); the coexistence sweep and ping test.

Breadboard build sheet: [`hardware/breadboard/`](hardware/breadboard/) — every lead and jumper by hole (`WIRING.md`), verified against the netlist, with an interactive `breadboard.html`.

Schematics: [`hardware/kicad/`](hardware/kicad/) — `radar_flow.kicad_sch` (**start here**: every part wired to every part it touches, in signal order, with the level on each connection), `radar_breadboard.kicad_sch` (the breadboard at component level) and `radar_multisim.kicad_sch` (every value on the page, one frame per test). All render in KiCad 7/8; PNGs alongside.

## Test

**[`docs/higher-bands.md`](docs/higher-bands.md)** — what moving to 24 or 60 GHz would cost and buy: $60 for a band swap that reuses the whole baseband, $283 for a tracker that ends the project. Kevin's suggestion, costed.

**[`docs/azimuth.md`](docs/azimuth.md)** — how bearing is actually measured: two receivers, one dwell, 0.09° rms. Scanning cannot do it on a moving target.

**[`docs/signal-chain.md`](docs/signal-chain.md)** — what the signal actually is at every point, from the frequency staircase leaving the antenna to the 100-byte fix, with every figure generated from the running code. Read this to understand *how it works*.

**[`docs/testing.md`](docs/testing.md)** — every test in run order: the DSP with no hardware, each breadboard block in ngspice or Multisim (`hardware/spice/`, `hardware/spice/multisim/`), the horns on a NanoVNA, the RF chain by its leakage tone, the walking-person test, the phone-link ping test with the sweep on, and tracking against floor marks.

```bash
cd ground_station && pip install -r requirements.txt
python radar_acquire.py --selftest            # the live DSP on a synthetic drone: PASS
python radar_acquire.py --device 3 --ctl /dev/ttyUSB0 --server http://localhost:8080
python server.py                              # console at http://localhost:8080
```

## Code

| | |
|---|---|
| `firmware/radar_ctl/` | radar ESP32: ADF4351 sweep, sync line, serial protocol, the stage-2 RF switch (`SWMODE`), optional turntable; boots RF-off |
| `ground_station/radar_acquire.py` | sound card → chirps → range-Doppler → CFAR → azimuth → console; `--selftest`, `--replay` |
| `ground_station/interferometer.py` | azimuth from the phase between two receivers, in one dwell: geometry, calibration, switched-mode parity and the refusals |
| `ground_station/test_radar.py` | the regression suite, 34 cases, no hardware or network needed |
| `ground_station/server.py` + `web/` | the console (PPI scope, tracker, `/api/radar`) |
| `ground_station/fmcw_sim.py`, `radar_twin.py`, `scan_design.py`, `tracker.py` | simulator, digital twin, scan sizing, Kalman filter |
| `antenna/horn.py` | the horn design (optimum pyramidal, WR-340 feed) |
| `hardware/kicad/`, `hardware/spice/` | schematics (generated), simulation netlists and test cards |

## Archive

Design history, the passive-RF system this replaced, analyses behind the
numbers (scanning, antenna, tracking, interference), the 915 MHz fallback and
external design reviews: [`docs/archive/`](docs/archive/).
