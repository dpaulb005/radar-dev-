# Radar software — what it measures, and how to bring it up

What runs on the radar, what the signal actually is at every point, how to get
it into the hardware, and how to prove each stage works — in the same order as
[`radar-hardware.md`](radar-hardware.md).

Two programs:

| where | file | job |
|---|---|---|
| radar ESP32 | `firmware/radar_ctl/radar_ctl.ino` | step the ADF4351 sweep, drive SYNC, serial protocol; also drives the optional turntable or the stage-2 RF switch |
| laptop | `ground_station/radar_acquire.py` | sound card → chirps → range-Doppler → CFAR → azimuth → fix → console |

`radar_acquire.py` is the hardware twin of `radar_twin.py`: it reuses
`fmcw_sim.range_doppler`, `radar_twin.cfar_detect` and
`interferometer.bearing` unchanged, so the DSP validated in simulation
(0.09 m RMS track error) is the DSP that runs live. Fixes go into the console
(`server.py`) through `POST /api/radar`.

---

## 1. What the signal actually is

This radar never measures time of flight. A drone 10 m away returns its echo
66.7 nanoseconds later, and nothing on this bench can time that. Instead the
transmitter is always changing frequency, so by the time the echo arrives the
transmitter has moved on, and the **difference between the two frequencies** is
what gets measured. That difference is an audio tone. The whole machine exists
to turn a distance into a pitch and then measure the pitch.

The ADF4351 is not swept smoothly. It is re-tuned 64 times, 1.305 MHz per step,
100 µs per step, which walks 2400 MHz up to 2483.5 MHz in 6.4 ms, then parks
back at 2400 for 1 ms and does it again. The echo is that identical staircase,
delayed. For 66.7 ns out of every 100 µs step the transmitter has stepped up and
the echo has not, so the two differ by one whole step. That is 0.067 % of the
time, and the average difference is:

```
f_beat = 2 · B · R / (c · T_up) = 87.04 Hz per metre of range
```

| range | beat tone |
|---|---|
| 3 m | 261 Hz |
| 10 m | 870 Hz |
| 30 m | 2.61 kHz |

Range **resolution** is set by the sweep width alone, `c / 2B` = **1.80 m**, and
nothing downstream can improve it.

### The chain, as data

| # | where | what the data is | size |
|---|---|---|---|
| 1 | ADF4351 output | 2400–2483.5 MHz, +5 dBm | — |
| 2 | TX horn | 0.2 W EIRP over a 34° beam | — |
| 3 | RX horn | the same staircase, 66.7 ns late, −80 dBm | — |
| 4 | mixer IF | one audio tone per target, 870 Hz at 10 m, 40 µV pk | — |
| 5 | video amp out | the same tone at 19 mV pk | — |
| 6 | sound card | 2 channels (3 in stage 2), 16-bit, 48 kHz | **92 KB** per block |
| 7 | after segmentation | 64 × 292 float array | **146 KB** |
| 8 | after two FFTs | 64 × 146 range–Doppler map, dB | **73 KB** |
| 9 | after CFAR | a list of (range, velocity, SNR) | ~300 B |
| 10 | after the bearing | one fix: range, azimuth, velocity | ~100 B |

A block is 64 chirps, 473 ms. The funnel from 92 KB of audio down to a
100-byte answer is the entire job of the software.

### Stage 6 — what the laptop really records

Two channels of ordinary 16-bit audio.

**Left** is the beat signal, and it looks nothing like a clean tone, because it
is not one: the transmit horn leaks straight into the receive horn 290 mm away,
and that path produces its own beat at roughly 26 Hz that arrives **46 dB
stronger** than the drone. What you see is almost entirely leakage.

**Right** is the sync square wave from GPIO25, high for the up-chirp and low for
the retrace. The sound card's input is AC coupled, so the square wave arrives as
a drooping plateau followed by a negative spike. Its **levels are meaningless**
and its **edges are exact**, which decides how the next stage works.

### Stage 7 — cutting the stream into chirps

The software differentiates the sync channel and finds the jumps, rather than
thresholding a level that AC coupling has already destroyed. Rising edges are
chirp starts, falling edges are chirp ends. Two timings come out, and they are
**not the same number**:

| measured | value | used for |
|---|---|---|
| `T_up`, the up-chirp | 6.396 ms | the beat → range scale |
| `PRI`, chirp to chirp | 7.396 ms | the velocity axis |

Both are measured on every block rather than assumed, so changing `step_us` on
the ESP32 needs no matching change on the laptop. The first 5 % of each chirp is
dropped while the PLL settles, leaving 292 samples: a 64 × 292 array, one row
per chirp.

> **What is deliberately *not* done here: removing the per-chirp mean.** It used
> to be, and it cost a metre at 3 m. Subtracting a constant from a chirp removes
> a window-shaped lobe centred on range bin 0 and about two bins wide, so it
> eats part of any target within two bins of DC — everything closer than
> **3.6 m**. Measured across 3–20 m it cost a mean 0.27 m and 1.05 m at 3 m;
> without it, 0.04 m and 0.04 m. The DC it was removing is already gone twice
> over: the sound card is AC-coupled, and the range-Doppler map subtracts the
> average chirp. The `ranging` group in `test_radar.py` holds it so it cannot
> come back quietly.

### Stage 8 — two FFTs, and why one is not enough

Fourier transform one row and the frequency axis becomes a range axis. The
target is **not** the peak: with 292 samples a bin is 164 Hz wide, so a drone at
10 m sits 5.3 bins from DC, and the leakage mainlobe is still bigger.
Subtracting the average of all 64 chirps removes the static part of the leakage
and it is still not enough on its own.

Now transform **down the columns**, across the 64 chirps. A target moving
towards the horns advances its phase a little on every chirp; the leakage and
the walls do not. That second transform sorts everything by velocity, and it is
what actually finds the drone: in the zero-Doppler row the leakage peaks near
4 m, and in the drone's own row it peaks at 10 m where it belongs. **Range alone
could not separate them; Doppler could.**

| axis | resolution | unambiguous span |
|---|---|---|
| range | 1.80 m | 381 m (filter limited) |
| velocity | 0.13 m/s | ±4.12 m/s |

Cell-averaging CFAR then compares each cell to its neighbours and keeps whatever
stands 15 dB above the local background. Zero Doppler is skipped entirely, since
that is where leakage and static clutter live.

Note how little of the range FFT is used. 48 kHz sampling reaches 576 m and the
15.9 kHz anti-alias filter cuts that to 381 m, so an indoor target lives in the
first 5 % of the bins. The sound card is not the limit anywhere in this design.

### The equations, in one place

| quantity | expression | this build |
|---|---|---|
| beat frequency | `2·B·R / (c·T_up)` | 87.04 Hz per metre |
| range resolution | `c / 2B` | 1.80 m |
| target's FFT bin | `2·B·R / c` | 5.6 bins at 10 m (5.3 after the settling trim) |
| velocity resolution | `λ / (2·N·PRI)` | 0.13 m/s |
| unambiguous velocity | `± λ / (4·PRI)` | ±4.12 m/s |
| max range from sampling | `c·T_up·f_s / (4·B)` | 576 m |
| max range from the filter | `c·T_up·f_LP / (2·B)` | 381 m |
| bearing from phase | `asin(Δφ·λ / 2π d)` | ±18.4° at d = 193 mm |
| scan time a moving target allows | `θ·R / v_tangential` | 0.44 s per m/s at 10 m |

---

## 2. The one design change from MIT, and what it costs

MIT sweeps an analog VCO with a triangle wave. The ZX95-2536C+ is a non-catalog
part now, so the ESP32 **steps an ADF4351 PLL** instead:

- `N_STEPS` (64) frequencies across the sweep, `STEP_US` (100 µs) each →
  **6.4 ms up-chirp**, then 1 ms retrace parked at 2400 MHz.
- Every step is locked to the board's 25 MHz TCXO, so **sweep linearity is not a
  tuning problem** — MIT's biggest practical headache is gone.
- The cost: PLL relock per step limits how fast the chirp can be. 6.4 ms instead
  of MIT's ~20 ms is still *faster* than MIT, but the Doppler window is
  `λ / (4·PRI)` = **±4.12 m/s** at a 7.4 ms PRI. A drone crossing faster than
  that aliases in velocity; range is unaffected.

**The staircase itself costs nothing, and that is measured rather than
assumed.** `SynthSource(n_steps=64, band_select_us=20, lock_tau_us=10)`
generates what the hardware really transmits — 64 plateaux, each with the
ADF4351's VCO band select and loop settling on its leading edge — and the range
answers track an ideal linear ramp to **2 mm** across 3–20 m. The reason is that
a step's worth of frequency error `Δf` only turns into a phase error of
`2π·Δf·τ`, and `τ` is 66.7 ns at 10 m: **15°**. It would matter at 120 m, where
it reaches 180°. This is why a stepped sweep is allowed to stand in for a ramp
at all, and `test_radar.py`'s `ranging` group holds it.

**Set R3 DB23.** The firmware does. It picks the ADF4351's fast band-select
mode, 20 µs instead of 80 µs. At 80 µs of a 100 µs step the PLL would spend most
of every step slewing.

**How much Doppler window you can buy, and what it costs.** `SET steps` and
`SET step_us` shorten the PRI and widen the unambiguous velocity, but a shorter
chirp means fewer steps in the range profile and less processing gain per bin.
Measured against a 0.01 m² drone at 10 m:

| steps × step_us | PRI | unambiguous | dwell | drone at 10 m |
|---|---|---|---|---|
| 64 × 100 µs *(default)* | 7400 µs | ±4.1 m/s | 474 ms | **46 dB** |
| 32 × 100 µs | 3700 µs | ±8.3 m/s | 474 ms | 40 dB |
| 16 × 100 µs | 1900 µs | ±16.1 m/s | 486 ms | 35 dB |
| **16 × 60 µs** | 1160 µs | **±26.4 m/s** | 297 ms | 23 dB |
| 8 × 100 µs | 1000 µs | ±30.6 m/s | 256 ms | **lost** |
| 8 × 40 µs | 420 µs | ±72.8 m/s | 108 ms | **lost** |

**16 steps is the floor.** At 8 the range profile has four usable bins, the
leakage fills them, and the target is gone — no threshold recovers it. So the
reachable window is **±26 m/s**, six times the default.

Rotor tips on a 30 mm prop at 70 000 rpm move at 110 m/s, so a *clean*
micro-Doppler spectrum is out of reach — it needs a window the configurations
that fast cannot hold a target in. ±26 m/s still shows the blade return as a
broad aliased Doppler spread, which is enough to tell a drone from a person,
whose limbs stay inside ±5 m/s. Untested on hardware, and `SynthSource` models a
point target with no rotors, so the *requirement* above is measured but the
*signature* is not.

---

## 3. Install, and the tests that need no hardware

```bash
cd ground_station
pip install -r requirements.txt        # adds sounddevice
# PortAudio for sounddevice:
#   Debian/Ubuntu:  sudo apt install libportaudio2
#   macOS:          brew install portaudio
#   Windows:        the wheel already includes it
python -m sounddevice                  # lists audio devices; note the interface's index
```

**Checkpoint 1 — ten minutes, no hardware at all:**

```bash
python radar_acquire.py --selftest
# SELFTEST PASS: range 8.26 m (mid-dwell truth 8.24), az 13.9 deg (true 15.0), vel 1.03 m/s ...
python radar_acquire.py --selftest --f0-mhz 2400 --bw-mhz 83.5 --st-range 5 --st-az -30 --st-vel -2
python radar_acquire.py --selftest --st-range-only --st-range 6 --st-vel 1.5
python radar_twin.py --track 20        # 0.09 m RMS
python test_radar.py                   # the whole suite, 45 cases
```

PASS: `SELFTEST PASS` on each and the twin's RMS track error ≤ 0.15 m. The
self-test synthesises exactly what the sound card records — single-ended beat,
AC-coupled sync with droop, TX leakage at 35 dB isolation, thermal noise, the
horn beam pattern — and runs it through the live code path. If it fails after
you touch the DSP, the hardware is not the problem.

Then check that the drawings still agree with the build sheet:

```bash
cd ../hardware/breadboard && python layout.py      # placement vs the schematic netlist
cd ../3d && python verify_model.py --render        # the bench model vs WIRING.md, MODULES.md, BOM.md
python verify_drone.py --render                    # the drone model vs the drone docs and BOM § E
```

PASS: `layout.py` rewrites without complaint and both verifiers print VERIFIED.
They re-derive the models from the documents, so they fail if either the model
*or* a document moves without the other. `--render` also loads each page in
headless Chrome and fails on a JavaScript error or a geometry fault.

Five things the self-test taught during development, already fixed in the code,
that you would otherwise rediscover on hardware:

1. **The PRI is not the chirp time.** Doppler comes from chirp-to-chirp phase,
   so the velocity axis must use `T_up + retrace`, not `T_up`. 15 % velocity
   error otherwise.
2. **CFAR must peak-pick.** A strong target's windowed mainlobe is 3–5 bins
   wide; every one of those bins beats the distant training cells, so the
   *shoulder* bins came out as separate targets 1–2 range cells short.
3. **Centroid on the strongest absolute return per beam**, not on the highest
   CFAR ratio. A moving target smears across Doppler bins, and picking the bin
   with the quietest neighbours instead of the loudest bin threw the azimuth 25°
   off.
4. **A target with exactly zero Doppler is invisible** — background subtraction
   removes it with the clutter. Don't test with `--st-vel 0`; see § 8.
5. **Near the sector edge the centroid is pulled inward**, because there are no
   beams beyond the edge to balance it. Make any scan sector one beam step wider
   than the flight box on each side.

---

## 4. Flash `radar_ctl` (radar ESP32)

Arduino IDE, esp32 core 2.x or 3.x, board **"ESP32 Dev Module"**, 115200.
Open `firmware/radar_ctl/radar_ctl.ino` and check the two things that depend on
your parts:

| line | check |
|---|---|
| `F_REF_HZ 25000000` | the ADF4351 board's crystal — 25 MHz on nearly all of them, 10 MHz on a few. It is printed on the can. |
| `AZ_MODE_STEPPER 1` / `STEPS_PER_DEG` | stepper vs servo, and your gearing |

Wiring is in the sketch header. Flash, open the serial monitor at 115200:

```
{"fw":"radar_ctl","f0_mhz":2400.0,"bw_mhz":83.5,"steps":64,"step_us":100,"t_chirp_ms":6.400,"retrace_us":1000,"sweep":1,"az":0.00,"lock":1}
```

`"lock":1` is the ADF4351's lock-detect pin. If it is 0: wrong `F_REF_HZ`, or
LE/CLK/DATA swapped, or the board's CE pin not tied high.

**The sweep is the whole band by default** — 2400–2483.5 MHz, a 1.80 m range
cell — because the drone's control link lives at 915 MHz.
`radar_acquire.py --ctl` picks the edges up from `?`; without `--ctl`, pass
`--f0-mhz 2400 --bw-mhz 83.5`.

Commands you will use by hand:

```
?              status
SWEEP 0        stop (parks on 2400 MHz, SYNC low)
CW 2460        park anywhere 2200–4400 MHz — for antenna and spectrum tests
SWEEP 1        chirp
AZ 30 / HOME   turntable
SET step_us 80 / SET steps 32 / SET retrace_us 1000
SET f0_mhz 2400 / SET bw_mhz 83.5      sweep edges (refused outside 2400–2483.5)
SWMODE 1       stage-2 RF switch, alternating antennas
RFOFF          kill the output from any state
```

The ESP32 **boots silent**: PLL locked and parked, RF output *off*, sweep
stopped. Nothing radiates until you send `SWEEP 1` or `CW`, and
`radar_acquire.py` sends `SWEEP 1` when it starts and `SWEEP 0` when it exits.

**Checkpoint 2 — the RF chain, from the serial line alone.**

1. `?` shows `lock:1`, `rf:0`. Nothing radiates yet.
2. `CW 2460` → +10.5 ± 2 dBm at the splitter's LO arm (power meter, or an
   RTL-SDR behind a 30 dB pad). PA out +14 ± 2 dBm.
3. `SWEEP 1` → **the leakage tone**: a low tone with a strong ~26 Hz component
   on the left audio channel, and the ~135 Hz sync square wave on the right. The
   leakage tone proves the PLL, PA, splitter, LO drive, LNA, mixer and video amp
   are all alive in one shot. No tone: work backwards, LO drive first.

---

## 5. Stage 1 — range and velocity

```bash
python radar_acquire.py --device 3 --ctl /dev/ttyUSB0 --range-only --record first-walk.wav
```

`--ctl` is still needed in stage 1 — the script turns the sweep on and off
through it; `--range-only` keeps the scan logic out of it. `--device` is the
interface's index from `python -m sounddevice`. Output is one JSON line per
block of 64 chirps (~0.5 s):

```
{"t": 1788671945.4, "t_chirp_ms": 6.395, "pri_ms": 7.392, "dets": [{"range": 4.62, "vel": -1.31, "snr": 38.4}]}
```

- `t_chirp_ms` should sit within 1 % of the ESP32's. If it jumps around, the
  sync divider is marginal — check the 0.3 V level.
- `# no sync` means the right channel is flat: `SWEEP 1`, cable, channel
  swapped, or the wrong `--device`.
- **Walk toward the horns from 5 m.** `range` counts down, `vel` is negative and
  roughly your speed. Walk away: positive. Stand still: you vanish, because zero
  Doppler is clutter — wave an arm and you are back.

Tuning: `--thresh` (CFAR, dB over local background; 15 default, raise to 18 if
the room produces false hits, lower to 12 for a small drone at 10 m).
`--n-chirps 128` doubles integration (+3 dB, half the update rate).

**Checkpoint 3:** at 3, 5 and 8 m against a tape measure (stand at each, sway
gently) the printed range is within 0.4 m, and `first-walk.wav` replays the same
answers with `--replay first-walk.wav`.

---

## 6. Stage 2 — azimuth from two receivers

**Written and tested.** `ground_station/interferometer.py` is the engine and
`radar_acquire.py --interferometer` runs it. The hardware, the parts and what it
buys are in [`radar-hardware.md`](radar-hardware.md) § 8.

```bash
# two receive chains, three audio channels (beat A, beat B, sync)
python radar_acquire.py --interferometer --ctl /dev/ttyUSB0 --f0-mhz 2400 --bw-mhz 83.5

# one chain and an RF switch instead (SWMODE 1 on the ESP32 first)
python radar_acquire.py --switched --ctl /dev/ttyUSB0 --f0-mhz 2400 --bw-mhz 83.5

# calibrate once, against a corner reflector on boresight
python radar_acquire.py --interferometer --calibrate --cal-az 0 --ctl /dev/ttyUSB0
# -> writes interferometer_cal.json, reloaded automatically from then on

# no hardware at all
python radar_acquire.py --selftest --interferometer --st-az -8 --st-vel -1.8
```

What it does, per block: cut **both** beat channels on the **one** sync so their
cells line up, take the complex range–Doppler of each, and at every CFAR
detection read `angle(rd_B · conj(rd_A)) − cal`, then
`az = asin(Δφ·λ / 2π d)`.

Three things it refuses to answer rather than guess, reported as `no_az`:

| reason | when |
|---|---|
| `ambiguous` | the phase fell outside the ±18.4° cone |
| `low-quality` | one channel is far weaker at that cell, so one of them is measuring noise |
| `velocity-fold` | switched mode only, target reported near its ±2.06 m/s fold |

And the fix is always the **strongest** return. If that one has no trustworthy
bearing the block reports `"fix": null` with `no_fix`, rather than promoting a
weaker sidelobe that happens to have a bearing.

### Calibration

One constant, in radians, in `interferometer_cal.json`. Point at a reflector
whose bearing you know, run `--calibrate`, and the fixed offset of chain B
relative to chain A is measured and stored. 1 mm of extra coax is **4.3°** of
phase and **0.43°** of bearing — the wave sees the 84.7 mm wavelength inside
PTFE, not the 121.9 mm one in air — so about 6 mm of unmatched cable spends the
whole 2.5° budget. Re-check `cal` after anything is unplugged; if it drifts more
than about 20° between sessions, look for a connector rather than believing the
bearing.

### Switched mode needs a frame marker, and this is not optional

A block of audio starts at an arbitrary point in the A/B alternation, so which
antenna a chirp came from is **not recoverable from the data**. Get it backwards
and every bearing comes out negated. `radar_ctl`'s `SWMODE 1` therefore skips
one chirp per block — SYNC stays low for a whole extra PRI — and restarts the
alternation on antenna A. `interferometer.tdm_parity()` finds that doubled gap.
Without it the software refuses to report bearings at all rather than risk the
sign.

### The one limit that is not fixable in software

Switched mode uses every other chirp, so its unambiguous velocity is **half**
the simultaneous figure: ±2.06 m/s at a 7.4 ms PRI, against ±4.12 m/s. Past that
the velocity folds, and because the motion correction is computed *from* the
velocity, a folded target reports a bearing that can be a whole beamwidth out.
The guard catches targets *reported* near the fold; it cannot catch one that
folded to a small apparent velocity, and no processing of two alternating
sub-cubes can. This is the strongest argument for building the simultaneous
version.

---

## 7. Scanning the turntable — coverage only

```bash
python radar_acquire.py --device 3 --ctl /dev/ttyUSB0 --sector 48 --step 24 \
                        --server http://localhost:8080
```

Per scan the script sends `AZ` for each beam, waits for `OK AZ` (motion done
plus settle), captures 64 chirps, runs CFAR, and centroids across beams after
the last one. **Three beams over 48° is the geometry to use**, not the nine over
90° this repo used to specify — [`radar-hardware.md`](radar-hardware.md) § 8 has
the measurements. One line per scan:

```
{"t": ..., "beams": 3, "fix": {"range": 7.9, "az": 11.3, "vel": 0.6, "snr": 48.2, "x": 7.75, "y": 1.55, "beams": 3}}
```

**Console:** run `python server.py` in another terminal and open
<http://localhost:8080>. With `--server` set, every fix is POSTed to
`/api/radar`: the FIX pill reads **RADAR n BEAMS**, and the scope blip and its
uncertainty ellipse come from the radar's polar covariance — tight in range,
wide in cross-range. Three keys in `config.json` describe the geometry:

```json
"radar_origin": [0.0, 0.0, 1.0],   // horn position in the room frame, boresight = +x at az 0
"radar_sigma_r": 0.15,             // m, from the parabolic range interpolation
"radar_sigma_az_deg": 2.5          // measured centroid accuracy
```

**Checkpoint 4:** stand at three tape-measured spots across the sector; the
console's X/Y tiles agree within ~0.4 m cross-range at 8 m.

---

## 8. What decides whether this works indoors

Three measurements, in the order they will bite you. None of them is a software
problem, and the first one is the single number most likely to decide whether
the build works at all.

### Measure your clutter cancellation, the day the chain first works

Every SNR figure in this repo — the 71 dB at 10 m above all — is
thermal-noise-limited and assumes an empty universe. Indoors that is not the
limit. A 1 m² patch of wall is **26 dB above** a 0.0026 m² drone and shares its
1.80 m range cell. The drone survives only because the wall does not move and
gets subtracted, so what matters is not how strong the echo is but **how well
the room cancels**.

Simulated in `test_radar.py` (`ranging` group), with a room at 4, 8 and 11.5 m:

| clutter cancellation | drone is the strongest return |
|---|---|
| **55 dB** | **5/5** |
| 50 dB | 3/5 |
| 45 dB | 2/5 |
| 40 dB and below | 0/5 — the walls win |

So you need roughly **55 dB** at 10 m. More bandwidth does not rescue this and
mildly hurts: narrower cells concentrate a wall's energy into a sharper, taller
peak whose residue competes better with the drone. It is a mechanical and
stability problem — a rigid mount, no fan, nobody walking about, and a chain
that does not drift over the 0.47 s dwell.

**How to measure it, before you ever fly the drone.** Point the radar at a
static scene, capture two blocks a few seconds apart, and difference them:

1. Record a block. Record another. Subtract the range profiles.
2. The ratio of the strongest clutter peak to the residue after subtraction
   **is** your cancellation, in dB.
3. Above 50, the link budget in this repo means something. At 30, no amount of
   DSP will find a 25 g drone at 10 m indoors, and the fix is mechanical —
   tripod, mass, no air currents — not software.

It costs nothing and it tells you whether to trust every other number here.

### A perfectly still target is invisible, and nothing abstains

`range_doppler(bg_subtract=True)` subtracts the mean across chirps, which is
what removes the TX leakage and the room. A target with no radial velocity is
removed with them. Measured:

| radial velocity | 1.4 s scan | one dwell, interferometer |
|---|---|---|
| **0.00 m/s** | **8.9° rms** | **8.5° rms** |
| 0.02 m/s | 7.9° | 8.5° |
| 0.05 m/s | 2.2° | **0.13°** |
| 0.10 m/s | 0.26° | 0.11° |

Worse than the error: at exactly zero Doppler `radar_acquire.py` locks onto a
leakage residue at 2.2 m and reports it as the fix with SNR 49.7 and quality
1.0. So *"hold it as still as you can"* is actively the wrong instruction. A
real hover is never that still — rotors and airframe jitter keep it out of the
DC bin — and **0.05 m/s is enough**. But a drone parked on a shelf is invisible,
and so is one crossing the beam purely sideways, and if you are bench-testing
against a corner reflector then **the reflector has to be moving**, on a slow
slide or swinging, or you are measuring the room.

### A small room changes the answer

Worked for a real one: **2.87 × 4.17 m** (9'5" × 13'8"), radar at one end
looking down the length, walls at 4.17 m behind and ~2.2–2.6 m either side.
Drone 0.0026 m², closing at 0.5 m/s.

**The room is 1.1 range cells deep at 40 MHz.** Range cannot separate the drone
from the wall behind it — only Doppler can. That single fact drives the rest:

| drone at | 40 MHz (2440–2480) | 83.5 MHz (full ISM) |
|---|---|---|
| 1.00 m | **no fix** | +0.17 m |
| 1.50 m | +0.74 m (3/5) | +0.09 m |
| 2.00 m | +0.54 m | +0.02 m |
| 2.50 m | +0.30 m | −0.05 m |
| 3.00 m | +0.19 m | −0.08 m |
| 4.00 m | −0.32 m | −0.03 m |

**Bandwidth matters far more indoors than the free-space figures suggest.** In
open air the two sweeps range a target at 10 m equally well. In a 4 m room the
40 MHz sweep is 0.2–0.5 m out and blind inside 1.5 m, while 83.5 MHz holds 0.1 m
everywhere. That is the whole argument for moving the drone's control link to
915 MHz, in one table.

Two surprises, both good. **Clutter cancellation stops mattering**: 30 dB is as
good as 60 dB here, where 10 m needed 55 dB, because the drone is close and the
echo goes as R⁻⁴. And **the near wall is not the problem** — the far wall in the
same range cell is, and only because it removes the range dimension, not because
it is loud.

Two that are not. **The beam fills the room**: at 34° it is 0.92 m across at
1.5 m and 2.55 m at 4.17 m, so the horn does no localising at all and whatever
azimuth you want has to come from the second receiver. And **multipath is not
modelled**: a 2.87 × 4.17 m box is a resonant cavity at 2.4 GHz, wall bounces
put ghost targets at longer apparent ranges, and nothing here predicts them.
Expect returns that are not the drone.

---

## 9. How the numbers are made

| quantity | from | code |
|---|---|---|
| range | beat frequency, range FFT per chirp, parabolic peak interpolation | `fmcw_sim.range_doppler`, `cfar_detect` |
| velocity | phase across 64 chirps at the target's range bin, axis scaled by the measured PRI | `range_doppler`, `process()` |
| detection | CA-CFAR in linear power, guard 4 / train 6, one-sided at the near edge, peak-picked | `cfar_detect` |
| azimuth, stage 2 | phase difference between the two beat channels at the CFAR cell, minus `cal` | `interferometer.bearing` |
| azimuth, scanning | amplitude-weighted centroid of the strongest return across beams, ±1.5 range cells | `ScanningRadar.centroid` |
| chirp time / PRI | rising and falling edges on the SYNC channel, per block | `segment_chirps` |
| covariance into the tracker | σ_r = 0.15 m, σ_x = r · 2.5°, rotated by azimuth | `server.py: ingest_radar` |

---

## 10. Troubleshooting

| symptom | look at |
|---|---|
| `# no sync` | `SWEEP 1`; R channel wiring; divider level; wrong `--device` |
| detections at 0.3–1.5 m always | leakage; `min_range` is 1.5 m by design — improve isolation (foil behind the horns), check the two 160 Hz high-passes |
| everything at one range, any speed | video amp clipping: leakage too strong, lower the gain of stage A to 51 |
| range right, velocity wrong by ~15 % | PRI vs chirp time — should be impossible now; check `t_chirp_ms` against `?` |
| no target beyond 4 m | LO drive low (measure), LNA unpowered, RX horn probe length, polarisation mismatch |
| target vanishes when it stops | working as designed — § 8 |
| nothing survives past 5 m in a real room | clutter cancellation — measure it, § 8 |
| bearing biased by a constant | `cal` — recalibrate, then look for the connector |
| bearing negated in switched mode | the frame marker; `SWMODE 1` and check `tdm_parity` |
| fix jumps between two targets | you are a target too — stand behind the horns |
