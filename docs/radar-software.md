# Radar software — step by step

What runs on the radar, how it gets into the hardware, and how to bring it
up in the same order as [`radar-hardware.md`](radar-hardware.md).

Two programs:

| where | file | job |
|---|---|---|
| radar ESP32 | `firmware/radar_ctl/radar_ctl.ino` | step the ADF4351 sweep, drive SYNC, point the turntable, serial protocol |
| laptop | `ground_station/radar_acquire.py` | sound card → chirps → range-Doppler → CFAR → azimuth centroid → fix → console |

`radar_acquire.py` is the hardware twin of `radar_twin.py`: it reuses
`fmcw_sim.range_doppler`, `radar_twin.cfar_detect` and
`radar_twin.ScanningRadar.centroid` unchanged, so the DSP you validated in
simulation (0.09 m RMS track error) is the DSP that runs live. Fixes go into
the existing console (`server.py`) through `POST /api/radar`.

---

## 1. The one design change from MIT, and what it costs

MIT sweeps an analog VCO with a triangle wave. The ZX95-2536C+ is a
non-catalog part now, so the ESP32 **steps an ADF4351 PLL** instead:

- `N_STEPS` (64) frequencies across the sweep (default 2400–2480 MHz), `STEP_US` (100 µs)
  each → **6.4 ms up-chirp**, then 1 ms retrace parked at 2400 MHz.
- Every step is locked to the board's 25 MHz TCXO, so **sweep linearity is
  not a tuning problem** — MIT's biggest practical headache is gone.
- The cost: PLL relock per step limits how fast the chirp can be. 6.4 ms
  instead of MIT's ~20 ms is still *faster* than MIT, but the Doppler window
  is `λ / (4 · PRI)` = **±4.2 m/s** at a 7.4 ms PRI. A drone crossing faster
  than that aliases in velocity (range is unaffected). If that bites,
  `SET step_us 60` and check the lock LED still flashes clean.

Consequences the software handles for you:

- The beat frequency is `f_b = 2·B·R / (c·T_up)`: **417 Hz at 10 m**, 125 Hz
  at 3 m with the 40 MHz sweep. Range 0–30 m spans 0–1.25 kHz. Audio — the
  sound card's 48 kHz is 40× more than the 15.9 kHz anti-alias filter lets
  through, which itself reaches 380 m (`docs/testing.md`, sound-card budget).
- `T_up` and the PRI are **measured from the SYNC channel every block**, not
  assumed, so `SET steps` / `SET step_us` on the ESP32 need no matching
  change on the laptop.
- Stepped sweeps have a range ambiguity at `c / (2·Δf)` = 114 m with 64
  steps. Irrelevant indoors.

**Known issue, azimuth at 40 MHz.** The coexistence sweep halves the
bandwidth, moving the target from 5.3 FFT bins from DC to 2.7, deeper into the
leakage mainlobe. Every beam's amplitude estimate gets noisier, and the
centroid is a weighted average of exactly those amplitudes, so azimuth error
rises to 6.3° against a 2.5° budget and `--selftest` fails on it. It is
variance, not bias: tightening the centroid's grouping window from 1.5 range
cells to 0.3 changes the answer not at all. Range and velocity are unaffected.

The fix is integration, not finer beam steps. Measured over three noise seeds
([`../docs/figures/scan_budget.py`](figures/scan_budget.py)), for the same
~10 s of scan time: 23 beams x 64 chirps gives 2.0° worst, while 9 beams x 160
chirps gives **0.2°**. 160 chirps at 40 MHz lands exactly where 64 chirps at
80 MHz already was. `--chirps 160` is the one-line change.

That only helps a hovering target. The centroid assumes every beam saw the
drone at one bearing, so `t_scan < theta * R / v_tangential`; at 10 m and 2.5°
the 4.3 s scan needs the drone under 0.10 m/s. Bearing on a *moving* drone has
to come from one dwell, which is stage 3's second RX horn. See
[`signal-chain.md`](signal-chain.md) § stage 10.

---

## 2. Install (laptop)

```bash
cd ground_station
pip install -r requirements.txt        # adds sounddevice
# PortAudio for sounddevice:
#   Debian/Ubuntu:  sudo apt install libportaudio2
#   macOS:          brew install portaudio
#   Windows:        the wheel already includes it
python -m sounddevice                  # lists audio devices; note the UCA202's index
```

**Checkpoint 2 — no hardware needed:**

```bash
python radar_acquire.py --selftest
# SELFTEST PASS: range 8.26 m (mid-dwell truth 8.24), az 13.9 deg (true 15.0), vel 1.03 m/s ...
python radar_acquire.py --selftest --st-range 5 --st-az -30 --st-vel -2
python radar_acquire.py --selftest --st-range-only --st-range 6 --st-vel 1.5
```

The self-test synthesises exactly what the sound card will see — a real
(single-ended) beat signal per up-chirp, the retrace gap, the sync square
wave, TX leakage at 35 dB isolation, thermal noise, the horn's beam pattern
— and pushes it through the *same* code path as live audio. If this fails
after you edit the DSP, the hardware is not the problem.

Things the self-test taught during development, already fixed in the code,
that you will otherwise rediscover on hardware:

1. **The PRI is not the chirp time.** Doppler comes from chirp-to-chirp phase,
   so the velocity axis must use `T_up + retrace`, not `T_up`. 15 % velocity
   error otherwise.
2. **CFAR must peak-pick.** A strong target's windowed mainlobe is 3–5 bins
   wide; every one of those bins beats the (distant) training cells, so the
   *shoulder* bins were coming out as separate targets 1–2 range cells short.
3. **Centroid on the strongest absolute return per beam**, not on the
   highest CFAR ratio. A moving target smears across Doppler bins; picking
   the bin with the quietest neighbours instead of the loudest bin threw the
   azimuth 25° off.
4. A target with **exactly zero Doppler is invisible** — background
   subtraction removes it with the clutter. A real hovering drone has rotor
   micro-Doppler (±1 kHz, `fmcw_sim.py --microdoppler`) and body jitter and
   *is* seen; a perfectly still synthetic target is not. Don't test with
   `--st-vel 0`.
5. **Near the sector edge the centroid is pulled inward** by a few degrees,
   because there are no beams beyond the edge to balance it. Make the scan
   sector one beam step wider than the flight box on each side.

---

## 3. Flash `radar_ctl` (radar ESP32)

Arduino IDE, esp32 core 2.x or 3.x, board **"ESP32 Dev Module"**, 115200.
Open `firmware/radar_ctl/radar_ctl.ino`, check the two things that depend on
your parts:

| line | check |
|---|---|
| `F_REF_HZ 25000000` | the ADF4351 board's crystal — 25 MHz on nearly all of them, 10 MHz on a few. It is printed on the can. |
| `AZ_MODE_STEPPER 1` / `STEPS_PER_DEG` | stepper vs servo, and your gearing |

Wiring is in the sketch header. Flash, open the serial monitor at 115200:

```
{"fw":"radar_ctl","f0_mhz":2400.0,"bw_mhz":83.5,"steps":64,"step_us":100,"t_chirp_ms":6.400,"retrace_us":1000,"sweep":1,"az":0.00,"lock":1}
```

`"lock":1` is the ADF4351's lock-detect pin. If it is 0: wrong `F_REF_HZ`,
or LE/CLK/DATA swapped, or the board's CE pin not tied high.

**If the drone is flown by phone** (its WiFi AP on channel 1), set the
coexistence sweep now and keep it — `SET f0_mhz 2440` then `SET bw_mhz 40`
(range cell 3.75 m, drone SNR unchanged; the reasoning and the link test are
in [`drone-software.md`](drone-software.md)). `radar_acquire.py --ctl` picks
the edges up from `?`; in stage 1 without `--ctl` pass `--f0-mhz 2440
--bw-mhz 40`.

Commands you will use by hand:

```
?              status
SWEEP 0        stop (parks on 2400 MHz, SYNC low)
CW 2440        park anywhere 2200–4400 MHz — for antenna / spectrum tests
SWEEP 1        chirp
AZ 30 / HOME   turntable
SET step_us 80 / SET steps 32 / SET retrace_us 1000
SET f0_mhz 2440 / SET bw_mhz 40   sweep edges (refused if outside 2400-2483.5)
```

The ESP32 **boots silent**: PLL locked and parked, RF output *off*, sweep
stopped (`"sweep":0,"rf":0`). Nothing radiates until you send `SWEEP 1` or
`CW`, and `radar_acquire.py` sends `SWEEP 1` when it starts and `SWEEP 0`
when it exits. `RFOFF` kills the output from any state.

**Checkpoint 3:** `?` shows `lock:1`; with `SWEEP 1` the right audio channel
shows the ~135 Hz square wave (hardware checkpoint 6).

---

## 4. Stage 1 — range and velocity (no turntable)

```bash
python radar_acquire.py --device 3 --ctl /dev/ttyUSB0 --range-only --record first-walk.wav
```

`--ctl` is still needed in stage 1 — the script turns the sweep on and off
through it; `--range-only` keeps the turntable out of it.

`--device` is the UCA202's index from `python -m sounddevice`. Output is one
JSON line per block of 64 chirps (~0.5 s):

```
{"t": 1788671945.4, "t_chirp_ms": 6.395, "pri_ms": 7.392, "dets": [{"range": 4.62, "vel": -1.31, "snr": 38.4}]}
```

- `t_chirp_ms` should sit within 1 % of the ESP32's `t_chirp_ms`. If it
  jumps around, the sync divider is marginal — check the 0.3 V level.
- The sound card's input is AC-coupled, so the recorded sync is not a clean
  square wave: a drooping positive plateau and a large negative retrace
  pulse. The software detects the *edges* (jumps in the derivative), which
  survive coupling; it does not threshold the level.
- `# no sync` means the right channel is flat: `SWEEP 1`, cable, channel
  swapped.
- **Walk toward the horns from 5 m.** `range` counts down, `vel` is negative
  and roughly your speed. Walk away: positive. Stand still: you vanish (zero
  Doppler is clutter) — wave an arm and you're back.

Tuning: `--thresh` (CFAR, dB over local background; 15 default, raise to 18
if the room produces false hits, lower to 12 for a small drone at 10 m).
`--n-chirps 128` doubles integration (+3 dB, half the update rate).

**Checkpoint 4:** a recorded `first-walk.wav` where `range` tracks a tape
measure within ~0.3 m at 3, 5 and 8 m (stand at each, sway gently). Replay it
any time with `--replay first-walk.wav`.

---

## 5. Stage 2 — scanning, and into the console

```bash
python radar_acquire.py --device 3 --ctl /dev/ttyUSB0 --sector 100 --step 12 \
                        --server http://localhost:8080
```

Per scan the script sends `AZ` for each beam, waits for `OK AZ` (motion done
plus settle), captures 64 chirps, runs CFAR, and after the last beam
centroids across beams (`archive/scanning.md` — 12° steps, 3× oversampling, measured
2.5° azimuth RMS). One line per scan:

```
{"t": ..., "beams": 9, "fix": {"range": 7.9, "az": 11.3, "vel": 0.6, "snr": 48.2, "x": 7.75, "y": 1.55, "beams": 6}}
```

A 100° sector at 12° is 9 beams × 64 chirps × 7.4 ms ≈ **4.3 s per revisit**
plus turntable moves — slow. `--n-chirps 32` halves it for 3 dB of SNR you
can spare; the real answer is the lock-and-dither mode in §6, which revisits
in ~0.3 s once a track exists. `--sector` should be the flight box plus one
step each side (§2 item 5).

**Console:** run `python server.py` in another terminal, open
<http://localhost:8080>. With `--server` set, every fix is POSTed to
`/api/radar` and the console shows it: the FIX pill reads **RADAR n BEAMS**,
the Estimator reads **radar · …**, the scope blip and the uncertainty ellipse
come from the radar's polar covariance (tight in range, 2.5° wide in
cross-range). Three keys in `config.json` describe the geometry:

```json
"radar_origin": [0.0, 0.0, 1.0],   // horn position in the room frame, boresight = +x at az 0
"radar_sigma_r": 0.15,             // m, from the parabolic range interpolation
"radar_sigma_az_deg": 2.5          // measured centroid accuracy
```

**Checkpoint 5:** stand at three tape-measured spots across the sector; the
console's X/Y tiles agree within ~0.4 m cross-range at 8 m. Record the
session (Record button) — the JSONL has every radar fix.

---

## 6. Once tracking: lock and dither (next software step)

`archive/scanning.md` measured that a locked 2-position dither (±half a beamwidth
around the target, compare amplitudes) revisits **4× faster** than the full
sweep and is *more* accurate than reading a peak. `radar_acquire.py` does
the full sweep only; the dither is the natural next addition — the ESP32
side needs nothing new (`AZ` is enough).

---

## 7. How the numbers are made (so you can argue with them)

| quantity | from | code |
|---|---|---|
| range | beat frequency, range FFT per chirp, parabolic peak interpolation | `fmcw_sim.range_doppler`, `cfar_detect` |
| velocity | phase across 64 chirps at the target's range bin (Doppler FFT), axis scaled by the measured PRI | `range_doppler`, `process()` |
| detection | CA-CFAR in linear power, guard 4 / train 6, one-sided at the near edge, peak-picked | `cfar_detect` |
| azimuth | amplitude-weighted centroid of the strongest return across beams, anchored on the strongest beam, ±1.5 range cells | `ScanningRadar.centroid` |
| chirp time / PRI | rising and falling edges on the SYNC channel, per block | `segment_chirps` |
| covariance into the tracker | σ_r = 0.15 m, σ_x = r · 2.5°, rotated by azimuth | `server.py: ingest_radar` |

---

## 8. Troubleshooting

| symptom | look at |
|---|---|
| `# no sync` | `SWEEP 1`; R channel wiring; divider level; wrong `--device` |
| detections at 0.3–1.5 m always | leakage; `min_range` is 1.5 m by design — improve isolation (foil between horns), check the two 160 Hz high-passes |
| everything at one range, any speed | video amp clipping: leakage too strong, lower gain of stage A to 51 |
| range right, velocity wrong by ~15 % | PRI vs chirp time — should be impossible now; check `t_chirp_ms` vs `?` |
| no target beyond 4 m | LO drive low (measure), LNA unpowered, RX horn probe length, polarisation mismatch |
| azimuth stuck on beam centres | centroid has one beam only — lower `--thresh`, or the step is too coarse |
| azimuth biased toward 0 near the edges | expected; widen `--sector` |
| fix jumps between two targets | you (the operator) are a target too — stand behind the horns |

---

## 9. Stage 3 — azimuth from two receivers (not written yet)

The plan below was written for elevation, with the second horn stacked below.
For **azimuth**, which is what the project needs, put the second horn *beside*
the first instead and rotate all three horns 90°. The maths is identical; only
the baseline's orientation changes. Measured performance and the full build
note: [`azimuth.md`](azimuth.md).

With two receive channels at 193 mm spacing, the angle off boresight is
`θ = asin( Δφ · λ / (2π · d) )` from the phase difference between the two
range FFTs at the detected bin; ±18.5° unambiguous, which covers the 17°
half-beam. To add it: capture 3 channels (beat 1, beat 2, sync) from a
4-input interface, run `segment_chirps` on both beats against the one sync,
take `range_doppler` of each, and at each CFAR detection read
`angle(rd1[bin]) − angle(rd2[bin])`. Keep the range-Doppler map **complex** for this; `range_doppler` currently
returns dB. Calibrate the fixed cable-length phase offset once against a
reflector on boresight: 1 mm of coax is 3 deg of phase and 0.3 deg of bearing. Everything else (centroid,
console, tracker) already accepts a `z`.
