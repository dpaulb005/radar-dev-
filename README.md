# radar-dev — a horn-fed FMCW radar that tracks a small drone

A 2.4 GHz FMCW radar in the MIT "coffee-can" tradition, fed by pyramidal horns
you cut and solder yourself, that finds a 25 g quadcopter at 3–10 m indoors by
its **reflection**. The drone carries nothing and cooperates with nothing: no
beacon, no transponder, no telemetry. It is a target.

One transmit horn, one receive horn. It measures **range and radial velocity**,
and it is finished at that: there is nothing half-built in here waiting on a
later part.

> **Build a radar where I design the antenna, and get azimuth on a small drone.**

That sentence is the specification the project was started against, and every
decision in this repo is still judged by three tests taken from it:

| test | means | where it stands |
|---|---|---|
| **Is the antenna mine?** | I cut, tune and characterise it. Not a patch array someone else laid out, and certainly not one baked into a chip package. | yes — three horns, cut from copper sheet, tuned against the radar's own SNR |
| **Is the target a small drone?** | 25 g quadcopter, 3–10 m, indoors, carrying nothing. | yes — a stock ESP-FLY, seen by its airframe alone |
| **Does it give azimuth on a drone that is *flying*?** | Not a hovering one. Bearing has to survive the target moving. | designed, written, passing its tests, and **not built** — [`stage2/`](stage2/) |

Those tests are why bearing, when it comes, comes from two receivers rather than
a mechanical scan, why elevation was dropped, why the drone's control link moved
to 915 MHz, and why the cheaper 24 GHz modules were rejected despite being
better radars.

## How it works

```
 handset ──915 MHz ELRS──► drone                        (control plane, off the radar's band)

 ESP32 steps an ADF4351 PLL 2400→2483.5 MHz in 64 steps / 6.4 ms
   → 3 dB pad → PA → splitter ─┬─► TX horn ─── echo off the drone ──► RX horn
                               └─► mixer LO ◄──────── LNA ◄── band-pass ◄──┘
 mixer IF = beat tone, pitch ∝ range (870 Hz at 10 m)
   → video amp (TL072, 61 dB, 159 Hz HP ×2, 15.9 kHz LP) → USB interface
   → laptop: range FFT · Doppler FFT · CFAR → detections
   → Kalman tracker → web console                       (sensing plane)
```

| | |
|---|---|
| sweep | 2400–2483.5 MHz (83.5 MHz), 6.4 ms up-chirp, 7.4 ms PRI — the whole ISM band, because the drone's link is on 915 MHz |
| range cell / accuracy | **1.80 m** / 0.04 m mean, 0.10 m worst, measured 3–20 m on the real stepped waveform |
| velocity | 0.13 m/s resolution, unambiguous to ±4.15 m/s, reachable to ±26 m/s |
| bearing | **none.** One receive horn measures no angle; the 13.4 dBi horn's 34° × 36° beam is the only direction there is |
| drone echo at 10 m | −77 dBm at the optimistic 0.01 m² RCS (−83 dBm at the 0.0026 m² design case), 72 dB above the leakage-limited floor after 64 chirps — in free space |
| what actually decides it | clutter cancellation. You need ~55 dB at 10 m, and nothing in this repo can predict yours |

**What it does not do.** Bearing, so a detection is a range and a radial
velocity down the boresight rather than a position on the floor. Elevation is not
coming back either, even with the upgrade fitted: one baseline measures one
angle, and that angle is azimuth. A target with exactly zero radial velocity: background
subtraction removes it with the room, and worse, nothing abstains — 0.05 m/s of
drift is enough, but a drone parked on a shelf is invisible. Multipath in a small
room is not modelled at all.

**The upgrade path.** Azimuth from the phase difference between two receivers is
written, tested and quarantined in [`stage2/`](stage2/). It is not built and it
is not part of this radar; [`stage2/README.md`](stage2/README.md) says what it
is, what it costs and how to bring it back. The build below makes seven cheap
decisions that keep it a bolt-on rather than a rebuild — cut three horns in one
session, put up a three-horn frame, roll every horn 90° so the bays sit 193 mm
apart, buy the amplifiers, op-amps and cables in multiples, and know what the
interface choice would cost — and all but one of them is free. Each is flagged
where the decision is made; `docs/radar-hardware.md` § 7 collects them.

## Build it

**Start with [`BUILD.md`](BUILD.md).** It is the whole project in the order you
should actually build it — which is not the order the documents below teach it.
It puts the long lead times and the expensive mistakes first: what to run today
for nothing, what to order before anything else, what to make while the RF parts
are in transit, and the one ten-minute measurement that decides whether this
works in your room at all.

The five documents it sends you to, each ending its steps with a checkpoint you
can verify before moving on:

1. **[`hardware/BOM.md`](hardware/BOM.md)** — every part and why it was chosen,
   priced and stock-checked. **[`hardware/ORDER.md`](hardware/ORDER.md)** is the
   same list with links, in buying order. Order the mixer first; it is the
   critical path.
2. **[`docs/radar-hardware.md`](docs/radar-hardware.md)** — the horns (cut list,
   all three in one session), the three-horn frame, the RF chain in MIT order,
   the breadboard video amp, sync, power, and the seven decisions that keep the
   azimuth upgrade a bolt-on.
3. **[`docs/radar-software.md`](docs/radar-software.md)** — what the signal
   actually is at every point, flashing `firmware/radar_ctl`, running
   `ground_station/radar_acquire.py`, the console, and the three measurements
   that decide whether it works in your room.
4. **[`docs/drone-hardware.md`](docs/drone-hardware.md)** — build the ESP-FLY
   kit to its own guide, then the one change that is not in that guide: the
   915 MHz receiver, its four pads and its antenna.
5. **[`docs/drone-software.md`](docs/drone-software.md)** — esp-fc on the XIAO,
   the ELRS bind, and the checks that prove the link and the sweep ignore each
   other.

Alongside them:

- **[`hardware/breadboard/`](hardware/breadboard/)** — the video amp hole by
  hole. `WIRING.md` lists every lead and jumper by hole, generated by
  `layout.py`, which proves the placement against the KiCad netlist before it
  writes anything. `breadboard.html` is the interactive version.
- **[`hardware/3d/`](hardware/3d/)** — `radar-bench.html` is the whole radar on
  its plywood bench, every BOM row an object and every wire routed pin to pin;
  `drone.html` is the target, every part, pad and lead labelled with what it
  weighs. Both are checked against the documents they draw.
- **[`hardware/kicad/`](hardware/kicad/)** — `radar_flow.kicad_sch` is the one
  to start with: every part wired to every part it touches, in signal order,
  with the level on each connection. Also the breadboard at component level and
  a simulation sheet with every value on the page.
- **[`hardware/spice/`](hardware/spice/)** — one test card per block: values,
  stimulus, expected reading. Simulate before you solder.

## Run it

```bash
cd ground_station && pip install -r requirements.txt
python radar_acquire.py --selftest                      # the live DSP on a synthetic drone
python radar_acquire.py --device 3 --ctl /dev/ttyUSB0   # the radar: one JSON line per block
python radar_acquire.py --device 3 --ctl /dev/ttyUSB0 \
       --server http://localhost:8080 --map            # ... and into the console
python server.py                                       # console at http://localhost:8080
python server.py --demo                                # the console with no hardware at all
```

Everything that can be checked without hardware, is:

```bash
cd ground_station && python test_radar.py              # the radar's own suite, 22 cases
cd ../stage2 && python test_stage2.py                  # the quarantined azimuth suite, 27 cases
cd ../hardware/breadboard && python layout.py          # placement vs the netlist
cd ../3d && python verify_model.py --render            # bench model vs WIRING/MODULES/BOM
            python verify_drone.py --render            # drone model vs the drone docs
cd ../../docs && python verify_build_order.py          # BUILD.md's checkpoints and sections resolve
```

The two model verifiers re-derive the drawings from the documents, so they fail
if either side moves without the other — geometry included: no lead may pass
through a part it is not connected to, no bend may exceed 95°, and every wire
end must land on a pad that exists.

## Code

| | |
|---|---|
| `firmware/radar_ctl/` | radar ESP32: ADF4351 sweep, sync line, serial protocol, optional turntable, and the `SWMODE` RF-switch mode only stage 2 uses; boots RF-off |
| `firmware/espfly-915/` | the drone's flight-controller config for the 915 MHz link |
| `ground_station/radar_acquire.py` | sound card, WAV or synth → chirps → range-Doppler → CFAR → JSON lines, and the POST to the console; `--selftest`, `--replay`, `--map` |
| `ground_station/fmcw_sim.py` | `RadarSpec`, the as-built radar, `range_doppler`, the link budget |
| `ground_station/dsp.py` | `cfar_detect` and the horn's beam gain — the detection half of the DSP |
| `ground_station/synth.py` | `SynthSource` and `segment_chirps`: the signal the self-test and the suite run on, and how a stream is cut into chirps |
| `ground_station/tracker.py` | the Kalman filter, on range and radial velocity |
| `ground_station/server.py` + `web/` | the console: range–Doppler heatmap, range-vs-time waterfall, detection table, track, `/api/radar`; `--demo` needs no hardware |
| `ground_station/test_radar.py` | the regression suite, 22 cases — geometry, DSP, ranging; no hardware, no network |
| `antenna/horn.py` | the horn design — optimum pyramidal on a WR-340 feed |
| `antenna/vivaldi.py` | the wideband PCB alternative to the horns — a design study, not the antenna built |
| `hardware/3d/` | both models, their screenshot renderer and their two verifiers |
| `stage2/` | the quarantined azimuth build, below |

**Written, passing, and not built: [`stage2/`](stage2/).** Azimuth from the phase
between two receivers, and everything that only makes sense once there is a
bearing: `interferometer.py`, the azimuth CLI taken out of `radar_acquire.py`
(`acquire_az.py`), the beam-scan alternative (`scanning.py`, `scan_design.py`),
the scan-based digital twin (`radar_twin.py`), the synthetic-aperture study
(`sar.py`), the 24 GHz study (`patch24.py`) and their own suite,
`test_stage2.py`. It imports from `ground_station/`; nothing in
`ground_station/` imports it, and no step of the build above needs it.
[`stage2/README.md`](stage2/README.md) is the way in.
