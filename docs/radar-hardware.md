# Radar hardware — step by step

The MIT RES.LL-003 coffee-can FMCW radar, built with the parts you can
actually buy in 2026 and fed by your own pyramidal horns. Every step ends
with a checkpoint. Do not skip checkpoints.

Companion pages: [`radar-software.md`](radar-software.md) (what runs on it),
[`../hardware/BOM.md`](../hardware/BOM.md) (priced parts), the 3-D model of
the finished assembly (published artifact "Horn-Fed Radar Assembly"),
[`archive/antenna.md`](archive/antenna.md) (why the horn is that shape).

---

## 0. What you are building

```
                 +3 dB att   PA (SPF5189Z)      2-way splitter
 ADF4351 ──►[-3 dB]──►[+12 dB @2.4G]──►[ ]──────────────────► TX HORN  ≈ +10 dBm
 (stepped   ▲                            │
  sweep)    │ SPI                        └──► LO ┐
            │                                    │  ZX05-43MH-S+ mixer
  ESP32 ────┤  SYNC ──► 10k/1k ──► sound card R  │
 radar_ctl  │                                    │ IF ──► video amp ──► sound card L
            └──► STEP/DIR ──► A4988 ──► turntable│                       (UCA202 → USB)
                                                 │
 RX HORN ──►[BPF 2400–2500]──►[LNA SPF5189Z +12 dB]──► RF ─┘
```

Signal order is the MIT order: **VCO → attenuator → PA → splitter → {TX, LO}**
on the transmit side and **RX → LNA → mixer RF** on the receive side; the
mixer's IF is the *beat* signal, an audio tone whose pitch is range. Only the
sweep generator differs from MIT: their XR-2206 ramp + ZX95 VCO is a
discontinued part, so the ESP32 steps an ADF4351 PLL instead (details and
the one trade-off in [`radar-software.md`](radar-software.md) §1).

**Band:** the sweep stays inside 2400–2480 MHz — the ISM band with a 3.5 MHz
emission margin at the top — *not* MIT's 2.36–2.50
GHz (2360–2395 MHz is licensed aeronautical telemetry — see
[`archive/mit-radar.md`](archive/mit-radar.md) §1). 83.5 MHz → 1.80 m range resolution.

**Three stages, same RF chain:**

| stage | adds | measures |
|---|---|---|
| 1 | horns bolted down | range + radial velocity |
| 2 | turntable (stepper) | + azimuth → 2-D position |
| 3 | 2nd RX horn stacked below, 2nd RX chain, 4-in audio interface | + elevation → 3-D |

---

## 1. Order the parts

Full priced table: [`../hardware/BOM.md`](../hardware/BOM.md). The critical-path
item is the **ZX05-43MH-S+ mixer** — Mini-Circuits had 9 in stock when
checked; nothing on Amazon replaces it. Order it first.

**Checkpoint 1:** mixer, ADF4351 board, SPF5189Z ×2 (buy the 4-pack), splitter,
attenuator, SMA jumpers ×6, SMA flange connectors ×10, copper sheet ×2, UCA202,
ESP32 devkit, TL072 + passives, 12 V supply + LM2596 ×2 are all on the bench.

---

## 2. Build the horns (one for stage 1–2 pair ×2, a third for stage 3)

Numbers from `antenna/horn.py` — an *optimum* pyramidal horn on a WR-340 guide
at 2.44 GHz:

| | mm |
|---|---|
| aperture a1 × b1 | **263.8 × 193.1** |
| throat (WR-340 inside) a × b | **86.4 × 43.2** |
| flare axial length | **91.5** |
| waveguide section length | **115** (anything ≥ 100 is fine) |
| probe: distance from the shorted back wall | **43.7** (λg/4) |
| probe length into the guide | **28** (≈ λ/4, must clear the 43.2 wall) |

Gain 13.4 dBi, beamwidth 34° E / 36° H. The horn is *squat* — the flare is
only 91.5 mm deep for a 264 mm mouth. That is what "optimum" means (shortest
flare for the gain); do not lengthen it to look like a textbook horn.

### 2a. Cut list per horn (0.021" copper)

The four flare panels are trapezoids. Their slant heights are longer than the
91.5 mm axial length because each panel leans outward:

| panel | qty | short edge | long edge | slant height |
|---|---|---|---|---|
| top / bottom (H-plane walls) | 2 | 86.4 | 263.8 | **118.3** |
| left / right (E-plane walls) | 2 | 43.2 | 193.1 | **127.4** |
| guide walls, broad | 2 | 86.4 × 115 | | |
| guide walls, narrow | 2 | 43.2 × 115 | | |
| back wall | 1 | 86.4 × 43.2 | | |

(Slant = √(91.5² + ((long − short)/2)²).) Add a 6 mm solder tab on one long
side of each guide wall and along the flare seams; the tabs overlap, the
seam gets soldered on the *outside* so the inside stays smooth.

### 2b. Assembly order

1. Fold and solder the **waveguide box** first (four walls + back wall).
   Plumbing solder, paste flux, a 60–100 W iron or a small torch; copper
   sinks heat, so a 25 W electronics iron will not do it.
2. Drill the **probe hole** in the centre of one *broad* (86.4 mm) wall,
   43.7 mm from the back wall. Bolt the SMA flange there with M3 hardware
   (4-hole flange, 12.7 mm square pattern). The probe is a 1/16" brass rod
   soldered into the flange's solder cup, trimmed so **28 mm** projects into
   the guide, standing perpendicular to the broad wall.
3. Tack the four **flare panels** to the front of the box, then to each
   other at the corners, check the mouth measures 263.8 × 193.1 at the rim,
   then run the seams.
4. Check every seam with a multimeter — continuity from any panel to any
   other, both ends. A gap in a seam is an RF leak, and leaks show up later
   as a mysterious noise floor.

**Checkpoint 2:** two identical horns, all seams continuous, probe at 43.7 / 28
mm. If you have a NanoVNA: return loss better than −10 dB across 2.40–2.48 GHz.
If you don't, that gets checked in step 7 with the leakage tone instead.

---

## 3. The board and the RF chain

An 18" × 15" plywood board, parts laid out **in signal order** so every coax
run is short and nothing crosses (the 3-D model is the layout):

```
   [VCO/ADF4351] → [att] → [PA] → [splitter] ─┬─► (TX horn, on the mast)
                                              └─► [mixer LO]
   (RX horn) ──────────────► [LNA] ────────────► [mixer RF]
                                                  [mixer IF] → breadboard
   ESP32 + A4988 + LM2596s + terminal block along the back edge
```

1. Screw each SMA module down with L-brackets or double-sided foam tape.
   Modules with mounting holes: use them.
2. Coax runs (RG316 SMA M-M): VCO→att, att→PA, PA→splitter, splitter→mixer LO,
   RX horn→**band-pass filter**→LNA, LNA→mixer RF, plus two longer runs up
   the mast to the horns. The band-pass (2400–2500 MHz inline SMA) sits at
   the LNA input: the horn is wideband and the SPF5189Z amplifies
   50–4000 MHz, so without it every signal in the building reaches the
   mixer. It does *not* reject the drone's channel-1 WiFi — that is handled
   by the drone's AP running at 10 dBm (`drone-software.md` §0). **Torque SMA
   by hand plus 1/8 turn with a wrench** — finger-tight SMA is a 1 dB loss
   you will chase for an evening.
3. Mark the modules' **DC feed** direction (SPF5189Z boards and the ADF4351
   board have their own 5 V pins — they are not bias-tee fed). Wire each
   to the 5 V rail with a 100 nF + 10 µF right at the board.

**Checkpoint 3:** chain wired VCO→…→TX and RX→…→IF, every SMA torqued, nothing
powered yet.

---

## 4. Power

| rail | source | feeds |
|---|---|---|
| 12 V | 12 V 3 A supply | TL072 video amp, A4988 VMOT |
| 5 V | LM2596 #1 from 12 V | ADF4351 board, SPF5189Z ×2, ESP32 VIN |
| 3.3 V | ESP32's own regulator | ADF4351 logic (already 3.3 V — no shifting) |

Set the LM2596 output to 5.0 V **before** connecting any module. Common
ground everywhere, star-wired at a terminal block. Keep the stepper's wires
away from the IF/breadboard side; a stepper is an EMI source right in the
audio band.

**Checkpoint 4:** 5.00 V on every module's supply pin, ESP32 enumerates on USB.

---

## 5. Video amplifier (breadboard)

MIT's is an LM324/LT1214 gain stage plus a 15 kHz active filter. This does
the same with one TL072 on the 12 V rail:

```
 mixer IF ──┤100n├──┬── R1 10k ──┐        The two 100n/10k high-passes (160 Hz)
                    │            │        are what stop the TX→RX leakage tone
                 R2 10k       ┌──┴──┐     (~26 Hz) from saturating the gain.
                    │         │ TL072│    Leakage is ~40 dB above the drone
                   VBIAS      │  A   │──► node A  (gain 1 + 100k/1k = 101)
                              └─────┘
 node A ──┤100n├──┬── 10k ── TL072 B (gain 1 + 10k/1k = 11) ── 1k ──┬──┤10µ├──► sound card L
                 VBIAS                                              10n
                                                                    │
                                                                   VBIAS
 VBIAS = 6 V: 10k/10k divider from 12 V, 10 µF to ground.
 1k + 10n after stage B = 15.9 kHz low-pass (anti-alias for 44.1 kHz).
```

Total gain ≈ 61 dB. A 10 m drone echo (≈ −78 dBm at the IF) comes out at
~20 mV; leakage comes out at ~200 mV; nothing clips a line input.

Two things the breadboard drawing above leaves out that the reviewed carrier
PCB (`docs/archive/reviews/radar-carrier-v1.md`) should add and you should too:
**49.9 Ω from the IF to ground** right at the input (the mixer's IF port wants
a 50 Ω load; without it the conversion loss and flatness wander), and a
**1 nF ceramic from the IF to ground** beside it. The mixer leaks LO at
2.4 GHz out of its IF port; a TL072 will happily rectify that into a DC
offset and a raised noise floor. The 1 nF with 49.9 Ω is a 3 MHz corner,
invisible to the audio band.

**Checkpoint 5:** with the sound card's input monitor open and the mixer IF
*disconnected*, touching the input node with a finger gives a hum — the amp
is alive. Output DC sits near 0 V (after the 10 µF).

---

## 6. Sync and the sound card

- ESP32 **GPIO25** → 10 kΩ → sound card **RIGHT** tip; 1 kΩ from tip to
  ground. That is 0.3 V of square wave: high during the up-chirp, low during
  retrace. `radar_acquire.py` measures the chirp time and the PRI from it —
  the software never assumes either.
- Video amp output → sound card **LEFT**.
- UCA202: input switch to line level; in the OS disable every "enhancement",
  AGC and noise suppression. 44.1 or 48 kHz, 16-bit. Both work; tell the
  software which (`--fs`).

**Checkpoint 6:** in any audio recorder, the right channel shows a clean
square wave at ~135 Hz (6.4 ms up + 1 ms retrace) once `radar_ctl` is
running (next page).

---

## 7. Mount the horns — stage 1

- Two posts, horns **290 mm centre-to-centre**, side by side, mouths flush
  in one plane, centre height ~300 mm above the board.
- **Same polarisation on both**: the 193 mm (b1) side vertical. Mixing them
  costs ~20 dB.
- TX on the splitter side, RX on the LNA side, short coax up the posts.
- A sheet of aluminium foil on cardboard between the two horns' *rear*
  halves (not in front of the mouths) buys a few dB of isolation for free.

- **You stand behind the horns**, phone in pocket. A phone in the beam at
  3 m is as strong at the receiver as the drone's own WiFi; behind the horns
  it is ~25 dB weaker.

**Checkpoint 7 — the leakage tone.** Power everything, `SWEEP 1`, open the
sound card monitor. You must see a **low tone with a strong ~135 Hz
component** on the left channel: that is TX leaking straight into RX through
the mixer, and it proves the VCO, PA, splitter, LO drive, LNA, mixer and
video amp are all alive in one go. No tone → work backwards: LO drive at the
mixer (+10 dBm ±2 with a power meter or an RTL-SDR with a 30 dB pad), PA
output, ADF4351 lock LED.

Then the MIT test: `python radar_acquire.py --device N` and **walk toward the
horns from 5 m**. Range decreases, velocity is negative and about your walking
speed. That is a working radar.

---

## 8. Stage 2 — turntable

- NEMA-17 + A4988, 1/16 microstep (MS1–3 high), VREF set for ~0.8 A.
- Turntable: a lazy-susan bearing (150 mm) with the stepper driving it 1:1
  via a printed hub, or the stepper shaft straight up through a plate if the
  horn pair is balanced over it. `STEPS_PER_DEG` in `radar_ctl.ino` is 8.889
  for 1:1 (200 × 16 / 360); change it if you gear it.
- Coax to the horns needs slack for ±45°. Two loose loops, not a tight twist.
- Zero the turntable with the horns pointed at the centre of the flight box.
  `HOME` in the serial monitor is that direction.

**Checkpoint 8:** `AZ 30` then `AZ -30` from the serial monitor: the horns move
±30° by protractor and come back to the same mark on `HOME`, within 1°. Then
`python radar_acquire.py --ctl /dev/ttyUSB0` and walk across the sector —
the fix's azimuth follows you.

---

## 9. Stage 3 — stacked receivers (elevation)

Add the third horn **193 mm directly below** the RX horn (mouths touching:
that is the E-plane aperture, the closest two horns can sit, 1.57 λ,
unambiguous to ±18.5°). It needs its own receive chain:

- second SPF5189Z (you have it in the 4-pack), **second ZX05-43MH-S+ mixer**,
  a second 2-way splitter to feed LO to both mixers, a second video-amp channel
  (the other half of the TL072 pair — use two TL072s),
- and a **4-input audio interface** (Behringer UMC404HD or similar): beat 1,
  beat 2, sync. Two UCA202s do not share a sample clock and cannot be used
  for phase.

The elevation is the phase difference between the two receive channels at
the target's range bin. That processing is *not* in `radar_acquire.py` yet —
see [`radar-software.md`](radar-software.md) §9 for what it needs. Build
stages 1 and 2 first; stage 3 is a second project on top of a working radar.

---

## 10. Safety and legality (short)

- +10 dBm into a 13 dBi horn is 0.2 W EIRP — under the Part 15 limits for the
  band, but keep the mouths pointed away from people at < 1 m out of habit.
- The sweep stays inside 2400–2480 MHz (firmware refuses anything else). Do not "extend it for resolution".
- The drone is flown by phone over its WiFi AP on **channel 1**, and the
  radar sweeps **2440–2480 MHz** above it — set that before the drone is
  ever in the air with the radar sweeping, and do the ping test in
  [`drone-software.md`](drone-software.md) §4 first.
