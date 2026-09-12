# Radar software — what it measures, and how to bring it up

What runs on the radar, what the signal actually is at every point, how to get
it into the hardware, and how to prove each step works — in the same order as
[`radar-hardware.md`](radar-hardware.md).

What this radar measures is **range and radial velocity**. There is no bearing in
it — that is the quarantined upgrade in [`../stage2/`](../stage2/) — so a block of
audio comes out as a list of detections, each a range, a velocity and an SNR.

Three programs:

| where | file | job |
|---|---|---|
| radar ESP32 | `firmware/radar_ctl/radar_ctl.ino` | step the ADF4351 sweep, drive SYNC, serial protocol; also drives the optional turntable |
| laptop | `ground_station/radar_acquire.py` | sound card → chirps → range-Doppler → CFAR → detections → console |
| laptop | `ground_station/server.py` + `web/` | the console: range-Doppler heatmap, waterfall, detection table, Kalman track |

`radar_acquire.py` runs the same DSP whether the samples come from the sound
card, a recorded WAV or the synthesiser: `synth.py` makes the signal,
`fmcw_sim.range_doppler` makes the map and `dsp.cfar_detect` picks the
detections out of it, so what the regression suite exercises is what runs live.
Detections go into the console (`server.py`) through `POST /api/radar`.

---

## 1. What the signal actually is

This radar never measures time of flight. A drone 10 m away returns its echo
66.7 nanoseconds later, and nothing on this bench can time that. Instead the
transmitter is always changing frequency, so by the time the echo arrives the
transmitter has moved on, and the **difference between the two frequencies** is
what gets measured. That difference is an audio tone. The whole machine exists
to turn a distance into a pitch and then measure the pitch.

The ADF4351 is not swept smoothly. It is re-tuned 64 times, 1.305 MHz per step,
100 µs per step, which walks 2400 MHz up the band in 6.4 ms, then parks back at
2400 for 1 ms and does it again. The last step sits one step below the nominal
top, at **2482.195 MHz**, so the slope is exactly `bw / T_up` with no N/(N−1)
fudge — and the highest frequency actually radiated is 1.3 MHz inside the band
edge, which is where the emission-mask margin comes from. The echo is that identical staircase,
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

> **Two drone RCS values are in use in this repo, and they differ by 5.9 dB.**
> The link-budget tables (`fmcw_sim.py --budget`, the README's headline echo)
> assume **0.01 m²**; the room and ranging simulations in `test_radar.py` and
> § 8 below assume **0.0026 m²**, the more pessimistic of the two. The chain
> table that follows is the 0.0026 m² case, which is why its −80 dBm at the RX
> horn is 5.9 dB below the README's −77 dBm for the same target at the same
> range. Neither has been measured on a real ESP-FLY — see
> [`drone-hardware.md`](drone-hardware.md) § 6. Treat 0.0026 m² as the design
> case and 0.01 m² as the optimistic one.

| # | where | what the data is | size |
|---|---|---|---|
| 1 | ADF4351 output | 2400–2483.5 MHz, +5 dBm | — |
| 2 | TX horn | 0.2 W EIRP over a 34° beam | — |
| 3 | RX horn | the same staircase, 66.7 ns late, −80 dBm | — |
| 4 | mixer IF | one audio tone per target, 870 Hz at 10 m, 40 µV pk | — |
| 5 | video amp out | the same tone at 21 mV pk | — |
| 6 | sound card | 2 channels, 16-bit, 48 kHz | **92 KB** per block |
| 7 | after segmentation | 64 × 292 float array | **146 KB** |
| 8 | after two FFTs | 64 × 146 range–Doppler map, dB | **73 KB** |
| 9 | after CFAR | a list of (range, velocity, SNR) | ~300 B |

A block is 64 chirps, 473 ms. The funnel from 92 KB of audio down to a
~300-byte answer is the entire job of the software.

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
| range | 1.80 m | 183 m (filter limited) |
| velocity | 0.13 m/s | ±4.15 m/s |

Cell-averaging CFAR then compares each cell to its neighbours and keeps whatever
stands 15 dB above the local background. Zero Doppler is skipped entirely, since
that is where leakage and static clutter live.

Note how little of the range FFT is used. 48 kHz sampling reaches 276 m and the
15.9 kHz video low-pass cuts that to 183 m, so a 10 m indoor target lives in the
first 5 % of the bins. The sound card is not the limit anywhere in this design.
(Both numbers scale as 1/B, so they were 576 m and 381 m on the old 40 MHz
sweep. The wider sweep halves the reach and still leaves an order of magnitude
more than an indoor room needs. The 15.9 kHz RC is one pole, so it limits the
*noise bandwidth*; the interface's own converter does the real anti-aliasing.)

### The equations, in one place

| quantity | expression | this build |
|---|---|---|
| beat frequency | `2·B·R / (c·T_up)` | 87.04 Hz per metre |
| range resolution | `c / 2B` | 1.80 m |
| target's FFT bin | `2·B·R / c` | 5.6 bins at 10 m (5.3 after the settling trim) |
| velocity resolution | `λ / (2·N·PRI)` | 0.13 m/s |
| unambiguous velocity | `± λ / (4·PRI)` | ±4.15 m/s |
| max range from sampling | `c·T_up·f_s / (4·B)` | 276 m |
| max range from the filter | `c·T_up·f_LP / (2·B)` | 183 m |

There is no angle equation in that table, and that is the point: one receiver
gives range and velocity. The phase-to-bearing relation and the cost of scanning
a beam instead are in [`../stage2/`](../stage2/).

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
  `λ / (4·PRI)` = **±4.15 m/s** at a 7.4 ms PRI. A drone crossing faster than
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
# SELFTEST PASS: range 8.26 m (mid-dwell truth 8.24), vel 1.04 m/s (true 1.0), SNR 55.5 dB
python radar_acquire.py --selftest --f0-mhz 2400 --bw-mhz 83.5 --st-range 5 --st-vel -2
python radar_acquire.py --selftest --st-range 6 --st-vel 1.5
python server.py --demo                # the console on synthetic blocks, no hardware
python test_radar.py                   # the whole suite, 22 cases
```

PASS: `SELFTEST PASS` on each, and the console draws a target that moves. The
self-test synthesises exactly what the sound card records — single-ended beat,
AC-coupled sync with droop, TX leakage at 35 dB isolation, thermal noise, the
horn beam pattern — and runs it through the live code path. If it fails after
you touch the DSP, the hardware is not the problem.

(The azimuth suite is quarantined with the rest of stage 2 and is not part of
this build's bring-up: `cd ../stage2 && python test_stage2.py`.)

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

Three things the self-test taught during development, already fixed in the code,
that you would otherwise rediscover on hardware:

1. **The PRI is not the chirp time.** Doppler comes from chirp-to-chirp phase,
   so the velocity axis must use `T_up + retrace`, not `T_up`. 15 % velocity
   error otherwise.
2. **CFAR must peak-pick.** A strong target's windowed mainlobe is 3–5 bins
   wide; every one of those bins beats the distant training cells, so the
   *shoulder* bins came out as separate targets 1–2 range cells short.
3. **A target with exactly zero Doppler is invisible** — background subtraction
   removes it with the clutter. Don't test with `--st-vel 0`; see § 8.

(Two more lessons, both about picking a bearing out of a beam scan, moved to
[`../stage2/`](../stage2/) with the code they apply to.)

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
CW 2460        park on one frequency — for antenna and spectrum tests
               (the synthesiser reaches 2200–4400 MHz; the firmware clamps
                CW to 2400–2483.5 and replies ERR outside it)
SWEEP 1        chirp
AZ 30 / HOME   turntable
SET step_us 80 / SET steps 32 / SET retrace_us 1000
SET f0_mhz 2400 / SET bw_mhz 83.5      sweep edges. Refused unless the top step
                                       (f0 + bw − bw/steps) stays inside 2483.5 MHz
                                       with 1 MHz to spare, so set bw before steps
RFOFF          kill the output from any state
```

The firmware also carries `SWMODE`, the RF-switch mode the quarantined azimuth
design uses to alternate between two antennas. Nothing here sends it, and with
one receive chain it does nothing useful.

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

## 5. Run it — range and velocity

```bash
python radar_acquire.py --device 3 --ctl /dev/ttyUSB0 --record first-walk.wav
```

`--ctl` is how the script turns the sweep on when it starts and off when it
exits, so it is worth having even though nothing else needs the serial line.
`--device` is the interface's index from `python -m sounddevice`. Output is one
JSON line per block of 64 chirps (~0.5 s):

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

## 6. Azimuth — quarantined, not deleted

Bearing from the phase difference between two receivers is **written, tested and
not part of this build**. The engine, the one calibration constant it needs, the
switched-mode alternative and the frame marker that keeps its sign honest, the
beam-scan option the turntable used to serve, and the numbers each of them is
worth are all in [`../stage2/`](../stage2/), with `test_stage2.py` beside them
and still passing. The flags that used to be on `radar_acquire.py` —
`--interferometer`, `--switched`, `--calibrate` — went with them, into
`stage2/acquire_az.py`. Start at [`../stage2/README.md`](../stage2/README.md).

Two things about that quarantine matter while you work on this page:

- **the dependency runs one way.** `stage2/` imports from `ground_station/` —
  `fmcw_sim`, `dsp`, `synth` — and nothing in `ground_station/` imports
  `stage2/`. So the stage-1 DSP can be changed without consulting it, but a
  change that moves `range_doppler`, `cfar_detect` or `segment_chirps` has a
  second suite to keep green.
- **`synth.py` keeps its unused arguments.** `SynthSource` still takes `n_rx`,
  `switched` and `cal_rad`; stage 1 always runs `n_rx=1` and never touches the
  other two. They are not dead weight, they are what stage 2 is tested through,
  and removing them would break the quarantined suite for no gain here.

The turntable's old job — step the beam across a sector, centroid the amplitudes,
call that a bearing — went to `stage2/` with the rest of it. What is left of the
turntable is pointing and measuring the horn
([`radar-hardware.md`](radar-hardware.md) § 9).

---

## 7. The console

```bash
python server.py                       # http://localhost:8080
python server.py --demo                # same console, synthetic blocks, no hardware
```

Then point the acquisition at it:

```bash
python radar_acquire.py --device 3 --ctl /dev/ttyUSB0 \
                        --server http://localhost:8080 --map
```

`--server` POSTs one payload per block to `/api/radar`; `--map` adds the
range–Doppler map to that payload, which is the only part big enough to be worth
a flag — without it the detections, the track and the waterfall all still arrive
and only the heatmap goes dark. Four panels, and none of them draws a direction:

| panel | what it shows |
|---|---|
| range–Doppler heatmap | the block's map as the DSP sees it, range across, velocity down — the leakage ridge at zero Doppler, the target off it |
| range-vs-time waterfall | one column per block, so a target walking in is a diagonal streak and a wall is a vertical line |
| detection table | what CFAR kept this block: range, velocity, SNR, strongest first |
| track | the Kalman filter's range and velocity, with the raw detections behind it |

**There is no plan view.** A plan position indicator draws a bearing, this radar
does not measure one, and a scope that invents an angle to put a blip on is worse
than no scope. The waterfall is the honest version of the same picture: it shows
everything the radar knows, against time.

The endpoints, if you want to drive it yourself:

```
GET  /              the console page
POST /api/radar     ingest one block
GET  /api/state     the latest block (minus the map), the track, the waterfall, stats
GET  /api/stream    Server-Sent Events, one event per ingested block
```

This radar's only geometry constant is the range uncertainty the tracker is
given, σ_r = 0.15 m, which comes from the parabolic interpolation of the range
peak; it and the velocity uncertainty beside it are `config.json` values, not
code changes. `server.py` prints a line for any azimuth or multilateration key
left over in that file and then ignores it.

**Checkpoint 4:** with `server.py` running and `--server` set, stand at the same
three tape-measured ranges as checkpoint 3. Each one appears in the detection
table, the track follows to the same 0.4 m, and the waterfall shows three
stripes where you stood and the diagonals between them.

---

## 8. What decides whether this works indoors

Three measurements, in the order they will bite you. None of them is a software
problem, and the first one is the single number most likely to decide whether
the build works at all.

### Measure your clutter cancellation, the day the chain first works

Every SNR figure in this repo — the 72 dB at 10 m above all — assumes an empty
universe. (It is also not the *thermal* figure: 72 dB is the echo above the
**leakage-limited** floor, the one `fmcw_sim.practical_mds_dbm()` computes,
because the TX leakage sits at the converter's input and everything more than
its dynamic range below that is unrecoverable. Against thermal noise alone the
same echo is 89 dB up. The leakage-limited number is the honest one, and it is
still not the limit indoors.) A 1 m² patch of wall is **26 dB above** a 0.0026 m² drone and shares its
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
removed with them. Measured in the range domain at 2.5 m with 50 dB of clutter
cancellation, 0.00 m/s gives 0 detections out of 5 attempts, 0.05 m/s gives 3,
and 0.10 m/s and above gives 5
([`drone-hardware.md`](drone-hardware.md) § 7).

Worse than the miss: at exactly zero Doppler `radar_acquire.py` locks onto a
leakage residue at 2.2 m and reports it as the strongest detection, with SNR
49.7. So *"hold it as still as you can"* is actively the wrong instruction. A
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
1.5 m and 2.55 m at 4.17 m, so the horn does no localising at all: everything in
the room that moves is in the beam, and range and Doppler are the only things
separating them. And **multipath is not
modelled**: a 2.87 × 4.17 m box is a resonant cavity at 2.4 GHz, wall bounces
put ghost targets at longer apparent ranges, and nothing here predicts them.
Expect returns that are not the drone.

---

## 9. How the numbers are made

| quantity | from | code |
|---|---|---|
| range | beat frequency, range FFT per chirp, parabolic peak interpolation | `fmcw_sim.range_doppler`, `cfar_detect` |
| velocity | phase across 64 chirps at the target's range bin, axis scaled by the measured PRI | `range_doppler`, `process()` |
| detection | CA-CFAR in linear power, guard 4 / train 6, one-sided at the near edge, peak-picked | `dsp.cfar_detect` |
| chirp time / PRI | rising and falling edges on the SYNC channel, per block | `synth.segment_chirps` |
| range uncertainty into the tracker | σ_r = 0.15 m, from the parabolic range interpolation | `server.py: ingest_radar` |

(Azimuth, by either method, is made in [`../stage2/`](../stage2/) and nowhere
here.)

---

## 10. Troubleshooting

| symptom | look at |
|---|---|
| `# no sync` | `SWEEP 1`; R channel wiring; divider level; wrong `--device` |
| detections at 0.3–1.5 m always | leakage; `min_range` is 1.5 m by design — improve isolation (foil behind the horns), check the two 159 Hz high-passes |
| everything at one range, any speed | video amp clipping: leakage too strong, lower the gain of stage A to 51 |
| range right, velocity wrong by ~15 % | PRI vs chirp time — should be impossible now; check `t_chirp_ms` against `?` |
| no target beyond 4 m | LO drive low (measure), LNA unpowered, RX horn probe length, polarisation mismatch |
| target vanishes when it stops | working as designed — § 8 |
| nothing survives past 5 m in a real room | clutter cancellation — measure it, § 8 |
| the strongest detection jumps between two ranges | you are a target too — stand behind the horns |
| console empty but `radar_acquire.py` is printing lines | `--server` not set, or set to a different port than `server.py` is on |
