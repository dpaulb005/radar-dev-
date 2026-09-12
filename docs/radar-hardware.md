# Radar hardware — step by step

The MIT RES.LL-003 coffee-can FMCW radar, built with the parts you can
actually buy in 2026 and fed by your own pyramidal horns. Every step ends
with a checkpoint. Do not skip checkpoints.

This page is the whole radar: **one transmit horn, one receive horn, range and
radial velocity.** There is no bearing in it, and nothing below is waiting on a
later part to become useful. A few decisions are made so that the azimuth
upgrade in [`../stage2/`](../stage2/) stays a bolt-on — they are marked where
they are made, all but one of them is free, and you can ignore them entirely if
you never intend to build it.

Companion pages: [`radar-software.md`](radar-software.md) (what runs on it and
what it measures), [`../hardware/BOM.md`](../hardware/BOM.md) (priced parts),
[`../hardware/ORDER.md`](../hardware/ORDER.md) (links and prices, in buying
order), and [`../hardware/3d/radar-bench.html`](../hardware/3d/) — the whole
bench as a 3-D model, every BOM row an object and every wire routed pin to pin.

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
            └──► STEP/DIR ──► A4988 ──► turntable│                     (USB interface → laptop)
                                 (optional)      │
                                                 │
 RX HORN ──►[BPF 2400–2500]──►[LNA SPF5189Z +12 dB]──► RF ─┘
```

Signal order is the MIT order: **VCO → attenuator → PA → splitter → {TX, LO}**
on the transmit side and **RX → LNA → mixer RF** on the receive side; the
mixer's IF is the *beat* signal, an audio tone whose pitch is range. Only the
sweep generator differs from MIT: their XR-2206 ramp + ZX95 VCO is a
discontinued part, so the ESP32 steps an ADF4351 PLL instead (details and
the one trade-off in [`radar-software.md`](radar-software.md) §1).

**Band:** the sweep is the whole ISM band, **2400–2483.5 MHz**, and the
firmware refuses anything outside it. Not MIT's 2.36–2.50 GHz: 2360–2395 MHz is
licensed aeronautical telemetry. 83.5 MHz of sweep is a **1.80 m** range cell,
and nothing downstream can improve on that number.

The whole band is available only because the drone's control link was moved off
it, to 915 MHz. Sweeping *around* a WiFi channel instead caps the radar at about
43 MHz whichever channel you pick, and indoors that is the difference between
holding 0.1 m of range accuracy everywhere in a small room and being 0.2–0.5 m
out and blind inside 1.5 m. [`drone-hardware.md`](drone-hardware.md) has the
link and what it costs.

**What it measures, and what it does not:**

| | |
|---|---|
| range | 1.80 m cell, 0.04 m mean accuracy, from the beat tone |
| radial velocity | 0.13 m/s, unambiguous to ±4.15 m/s, from chirp-to-chirp phase |
| bearing | **none.** One receiver measures no angle. The 34° beam is all the direction there is |
| optional | turntable under the frame — points the 34° beam at a wider sector, and is how you measure the beam pattern |

A detection is therefore a range, a radial velocity and an SNR: a track down the
boresight, not a position on the floor. Everything that would turn it into a
bearing — a second receive horn and the phase comparison between the two — is
written and quarantined in [`../stage2/`](../stage2/), and none of it is built
here.

**Build it so the door stays open.** A handful of the steps below cost nothing
now and save a rebuild if you ever do go after azimuth: horn orientation, the
frame holding three horns, which parts to buy in multiples, and where the spare
op-amp and amplifier go. Each is flagged *keeps the door open* at the point of
the decision, and § 7 collects all seven in one table.

---

## 1. Order the parts

Full priced table: [`../hardware/BOM.md`](../hardware/BOM.md). The critical-path
item is the **ZX05-43MH-S+ mixer** — Mini-Circuits had 9 in stock when
checked; nothing on Amazon replaces it. Order it first.

**Checkpoint 1:** mixer, ADF4351 board, SPF5189Z ×2 (buy the 4-pack), splitter,
attenuator, band-pass filter, SMA jumpers ×6, SMA flange connectors ×10, copper
sheet ×2, a **2-input USB audio interface**, ESP32 devkit, TL072 ×2 + passives,
12 V supply + LM2596 ×2 are all on the bench.

The interface is the one item whose answer depends on how far you intend to go.
This radar records two channels — beat and sync — so any line-level two-input
interface does it, including one you already own. *Keeps the door open:* the
azimuth upgrade is the one thing that would replace it rather than add to it,
because comparing the phase of two receivers needs **four channels on one sample
clock** and two separate two-input boxes have independent clocks. Buy the
four-input one up front only if you have already decided to build
[`../stage2/`](../stage2/); otherwise run on what you own and decide later.

---

## 2. Build the horns — make all three at once

Make **three**, in one session, from one marked-out sheet. This radar uses two
of them — one transmit, one receive — and the third costs nothing: materials for
three are already in the bill, and a spare horn is worth having the first time
you dent one.

*Keeps the door open:* the third horn is the azimuth upgrade's second receiver,
and two receivers get compared against each other by phase, so they want to be
as close to identical as you can make them. That is far easier while the jig is
set up and your hand is in than it is in a year. Cut all three now even if you
never fit the third.

Numbers from `antenna/horn.py` at its default — an *optimum* pyramidal horn on a
WR-340 guide at **2.45 GHz**. (2.45 is the ISM nominal; the sweep centre is
2.4418 GHz. Re-solving at the sweep centre moves the aperture by ~1 mm and the
probe by 0.4 mm, which is below what you can cut and well below the 0.5 mm steps
§ 2c tunes the probe in. The numbers below are the ones the cut list, the 3-D
model and `DEFAULT_BASELINE_M` all use, so use these.)

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

**Checkpoint 2:** three identical horns, all seams continuous, probe at
43.7 / 28 mm, and continuity panel to panel below 0.5 Ω — an ohm-meter does
that one.

### 2c. You do not need a VNA to build this

A VNA reaching 2.5 GHz is the most expensive item anywhere near this project: a
LiteVNA-64 is ~$165, a NanoVNA V2 Plus4 ~$150, and the common $65 NanoVNA-H4
stops at 1.5 GHz and **cannot see this antenna at all**. None of it is worth
buying for one measurement.

You do not need it because the link has ~54 dB of margin at 10 m — the echo
above the leakage-limited detection floor, less the 13 dB a confident detection
needs, at the pessimistic 0.0026 m² RCS. (Do not confuse it with the ~55 dB of
*clutter cancellation* the room has to give you, in
[`radar-software.md`](radar-software.md) § 8. Similar number, unrelated
quantity, and the clutter one is the one that actually decides the build.) A
horn with a poor 3:1 match loses 1.25 dB, and there are two of them, so a badly
tuned pair costs 2.5 dB out of 54. The dimensions come from closed-form optimum-horn theory
and are reliable if you cut to them; a VNA only confirms it.

**Tune with the radar itself instead.** Once the chain is alive (checkpoint 7),
park the PLL with `CW 2460`, put a corner reflector at a fixed range on
boresight, and adjust the probe depth in 0.5 mm steps for maximum detection SNR.
That optimises the exact quantity you care about, which is more than S11 tells
you anyway. *Keeps the door open:* tune the spare horn the same way and stop when
it reads within 1 dB of the one you fitted — a matched pair is what the azimuth
upgrade needs, and tuning it now is free.

**If you want the real measurement, borrow the instrument** — a university RF
teaching lab or a local amateur radio club; LiteVNAs are common and members lend
them. Twenty minutes covers every row:

| test | PASS |
|---|---|
| return loss | S11 ≤ −10 dB over 2400–2484 MHz (tune the 28 mm probe in 0.5 mm steps for the minimum) |
| TX–RX isolation, TX 290 mm above the RX row | S21 ≤ −35 dB |
| **RX vs the spare horn** | S11 curves within 2 dB of each other across the band — not needed here, but two receivers feeding a phase comparison want to be twins, so check it while the instrument is on the bench |
| gain, two-antenna method at 3 m | 13.4 ± 1.5 dBi |
| beamwidths (rotate the horn by hand against a protractor) | 34 ± 4° E, 36 ± 4° H; first sidelobe ≤ −12 dB |

---

## 3. The board and the RF chain

An 18" × 15" plywood board, parts laid out **in signal order** so every coax
run is short and nothing crosses (the 3-D model is the layout):

```
   [VCO/ADF4351] → [att] → [PA] → [splitter] ─┬─► (TX horn, on the mast)
                                              └─► [mixer LO]
   (RX horn) ──► [band-pass] ──► [LNA] ────────► [mixer RF]
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
   mixer. It no longer has to reject the drone's own WiFi — the control link
   moved to 915 MHz and the sweep took the whole band. Its 3 dB edges are 2380/2500 MHz, so the 2400–2483.5 sweep fits
   with ~20 MHz to spare at each end, and the 2.7 dB it costs sits in front of
   the LNA so it lands straight on the noise figure. **Torque SMA
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
 mixer IF ──┤100n├──┬── R1 10k ──┐        The two 100n/10k high-passes (159 Hz)
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

**Hole-by-hole layout:** [`hardware/breadboard/WIRING.md`](../hardware/breadboard/WIRING.md)
lists every lead and every jumper (`R3 pin 1 → b14`, wire 27 `a4 → a7`), generated by
`layout.py`, which proves the placement against the KiCad netlist before it writes anything.
`breadboard.html` in the same folder is the interactive version: hover a part, wire, net or
hole and the board shows what shares that connection.

Total gain ≈ 61 dB, and about 55 dB of that reaches the output node once the
49.9 Ω termination has halved the incoming signal. A 10 m drone echo (≈ −78 dBm
at the IF) comes out at ~21 mV and the leakage at ~116 mV, against a 316 mV line
nominal: nothing clips. The leakage figure scales directly with how poor your
TX→RX isolation turns out to be, so measure it rather than assuming it — 35 dB is
what every number here assumes.

Two things the breadboard drawing above leaves out, which an external review of
the carrier-PCB version caught and you should add too:
**49.9 Ω from the IF to ground** right at the input (the mixer's IF port wants
a 50 Ω load; without it the conversion loss and flatness wander), and a
**1 nF ceramic from the IF to ground** beside it. The mixer leaks LO at
2.4 GHz out of its IF port; a TL072 will happily rectify that into a DC
offset and a raised noise floor. The 1 nF with 49.9 Ω is a 3 MHz corner,
invisible to the audio band.

**Simulate it before you build it.** `hardware/spice/README.md` has one test
card per block — part values, stimulus, expected reading — and
`hardware/spice/multisim/` has the same blocks for Multisim (`import/*.cir` open
straight through **File ▸ Open ▸ SPICE netlist**; the ngspice decks in
`hardware/spice/` itself carry `.control` blocks and do not import). The
schematic with every value on it is `hardware/kicad/radar_multisim.kicad_sch`.
The readings that matter:

**One caveat on the stimulus frequencies below.** They are scaled to the
*superseded* 40 MHz sweep: 12.5 Hz was its leakage beat and 417 Hz its 10 m
echo. On the 83.5 MHz sweep the same two land at **26 Hz** and **870 Hz**, where
the two 159 Hz high-passes reject the leakage by 31 dB rather than 43 dB — so
the 46 dB input ratio comes out at about **15 dB**, not 3 dB. Nothing clips
either way (the echo is ~21 mV and the leakage ~116 mV against a 316 mV line
nominal), and every corner frequency below is unchanged, but re-run the two
video-amp rows at 26 Hz and 870 Hz if you want the bench check to match the
sweep you are actually going to transmit.

| block | stimulus | PASS |
|---|---|---|
| video amp, first power-up gain (R4 4.7k, R7 link) | 10 mVpk 1 kHz through 50 Ω | 107 mVpk out; −6 dB at 159 Hz, −3 dB at 15.9 kHz |
| video amp, full gain | 8 mV @ 12.5 Hz + 40 µV @ 417 Hz | 27 mV leakage, 19 mV echo — the 46 dB input ratio becomes 3 dB |
| half-rail reference | 100 mVpk 150 kHz on VANA | VREF 5.70 V, ripple < 1 µV |
| 12 V input | 200 mVpp 150 kHz; then −12 V | VANA 11.6 V, 4 mVpp; reversed: VPROT −0.1 mV |
| sync divider | 3.3 V pulse 6.4 / 7.4 ms | 283 mV at the divider; +201 / −100 mV after the card's coupling |
| IF input | AC sweep to 10 GHz | −58 dB at 2.44 GHz, −6 dB at 417 Hz |
| the radar, scaled | VCO 1→5 MHz over 6.4 ms, 667 ns delay | peak at 417 Hz at the beat output |

**Checkpoint 5:** with the sound card's input monitor open and the mixer IF
*disconnected*, touching the input node with a finger gives a hum — the amp
is alive. Output DC sits near 0 V (after the 10 µF). A 1 kHz tone in gives the
same 107 mV out that the simulation predicted.

---

## 6. Sync and the sound card

- ESP32 **GPIO25** → 10 kΩ → sound card **RIGHT** tip; 1 kΩ from tip to
  ground. That is 0.3 V of square wave: high during the up-chirp, low during
  retrace. `radar_acquire.py` measures the chirp time and the PRI from it —
  the software never assumes either.
- Video amp output → sound card **LEFT**.
- On a **UMC404HD** — if you happen to own one, or bought it for the upgrade
  already — those two are the front-panel combo jacks **INPUT 1** (beat) and
  **INPUT 3** (sync), on ¼" TS plugs, which leaves INPUT 2 free for a second
  beat channel later.
- On a **two-input interface** they are simply left and right. On a small USB
  mixer such as the Xenyx 302USB that is the stereo RCA line channel — beat into
  its left, sync into its right, the mic channel all the way down, and its
  Line/USB switch on **LINE IN**, or you record the computer's own playback
  instead of the radar. What reaches the computer is the main mix, so the main
  level control is part of your calibration.
- Either way, set the gain once so the leakage tone sits well below clip and
  never touch it again. The video amp is designed around this: about 61 dB of
  gain puts the leakage at ~116 mV and a 10 m drone echo at ~21 mV against a
  316 mV line nominal, so nothing clips and nothing needs riding. (It is also a
  habit worth keeping: with two beat channels, a gain change on one of them is a
  phase error.)
- In the OS disable every "enhancement", AGC and noise suppression. 44.1 or
  48 kHz, 16-bit. Both work; tell the software which (`--fs`).

**Checkpoint 6:** in any audio recorder, the right channel shows a clean
square wave at ~135 Hz (6.4 ms up + 1 ms retrace) once `radar_ctl` is
running (next page).

---

## 7. Mount the horns — build the three-horn frame

Two horns are live: TX and RX. Build the frame for **three** anyway and leave
the third bay empty — it is the one piece of mechanics that cannot be added
later without taking the mast apart, and an empty bay costs nothing.

```
            ┌───────────┐
            │    TX     │      TX centred above, 290 mm below its
            └───────────┘      centre to the RX row: same isolation
                  │            as the old side-by-side 290 mm, and
               290 mm          symmetric across the row
                  │
      ┌───────────┬───────────┐
      │    RX     │  (empty)  │   touching, centres 193 mm apart
      └───────────┴───────────┘   ← the bay the second receiver takes
        built       left for the upgrade
```

- **Rotate all three horns 90° from the obvious orientation**: the 193.1 mm
  (b1) side goes **horizontal**, the 263.8 mm side vertical. Polarisation
  becomes horizontal, which is fine as long as all three match. Here it costs
  nothing either way; what it buys is below.
- *Keeps the door open:* that rotation is not cosmetic, and it is the reason the
  two bays are 193 mm apart rather than 264 mm. A phase difference between two
  receivers has to stay inside ±π across the beam, which caps the spacing:

  ```
  d  ≤  λ / (2 · sin θ_max)  =  0.1228 / (2 × sin 17°)  =  210 mm
  ```

  Two horns side by side in the un-rotated orientation put their phase centres
  **263.8 mm** apart, past that limit, and the bearing wraps at ±13.4° — inside
  the 17° half-beam, where it does real damage. Rotated, they touch at
  **193 mm**, unambiguous to **±18.5°**, which covers the half-beam with room
  to spare. The horizontal beamwidth goes from 36° to 34°, which is nothing, and
  the polarisation rotates, which is fine as long as the transmit horn rotates
  with them.
- *Keeps the door open:* **the two RX mouths must end up flush in one plane**, to
  a millimetre, so build the empty bay's saddle to the same depth as the live
  one. A 1 mm depth difference in *air* is 3° of phase; 1 mm of extra *coax* on
  one channel is 4.2°, because a wave is ~30 % slower in PTFE. Neither matters
  with one receiver; both are bearing bias with two, and a bay built to a
  different depth than its neighbour is a bias no calibration removes.
- *Keeps the door open:* **measure the finished bay spacing and write it on the
  frame.** 193.1 mm is the horn's E-plane aperture, i.e. two ideal mouths
  touching. Real walls and the 6 mm solder tabs push the built centres 1–2 mm
  further apart, and that spacing is a *scale factor* on every bearing the
  upgrade would report — a boresight calibration cannot absorb it, because on
  boresight `sin θ = 0`. 2 mm of error is ~1 % of bearing, about 0.2° at the edge
  of the beam. Measure mouth centre to mouth centre now, while a tape fits
  between them.
- TX centred above the row, mouth in the same plane, 290 mm centre to centre.
  Centred matters: it keeps the leakage path equal into both bays.
- Centre of the RX row ~300 mm above the board.
- Coax from the horn to the board: whatever you use for the live receiver, cut
  its twin from the same reel at the same time and coil it with the frame. *Keeps
  the door open* for the price of 20 cm of RG316.
- A sheet of aluminium foil on cardboard behind the horns (not across the
  mouths) buys a few dB of isolation for free.
- **You stand behind the horns**, phone in pocket. A phone in the beam at 3 m
  is as strong at the receiver as the drone's own WiFi; behind the horns it is
  ~25 dB weaker.

### The seven decisions that keep the door open

None of these is part of measuring range and velocity. All of them are free or
nearly free *now* and expensive *later*, which is the only reason a document
about range and velocity mentions them at all. If you are certain you will never want bearing, skip the
table and build the radar.

| decide now | why it matters later | costs now |
|---|---|---|
| Frame holds three horns; leave the second RX bay empty | otherwise the whole mast is rebuilt | $0 |
| Build all three horns in one session | the two receive horns would have to match | $0, materials are for three |
| Rotate all horns 90°, b1 horizontal | a rotated pair is unambiguous at 193 mm, an un-rotated pair at 264 mm is not | $0 |
| Decide whether you want bearing **before** buying the interface | comparing phase needs both beat channels on one sample clock, i.e. a 4-input interface. If bearing is the goal, buy it once now; if this radar is the goal, run it on any 2-in interface and write that off later | $0 or +$139 |
| Buy the SPF5189Z **4-pack** | 2 used here, 1 would become the second LNA, 1 the LO amplifier | $0, already the 4-pack |
| Buy SMA jumpers as one batch | two receive chains want phase-matched cables, and one batch is the cheap way | $0 |
| Put two TL072s on the board and wire only one video amp | a second video channel then drops into empty rows | +$4 |

Everything else the upgrade needs is new parts bought when you get there —
[`../hardware/BOM.md`](../hardware/BOM.md) § F prices them, and
[`../stage2/`](../stage2/) is the design.

**Checkpoint 7 — the leakage tone.** Power everything, `SWEEP 1`, open the
sound card monitor. You must see a **low tone with a strong ~26 Hz component**
on the left channel: that is TX leaking straight into RX through the mixer, and
it proves the PLL, PA, splitter, LO drive, LNA, mixer and video amp are all
alive in one go. No tone → work backwards: LO drive at the mixer, PA output,
ADF4351 lock LED.

Then the MIT test: `python radar_acquire.py --device N` and **walk toward the
horns from 5 m**. Range decreases, velocity is negative and about your walking
speed. That is a working radar, and it is the whole of this build — the bring-up,
the three measurements that decide whether it works in your room and the console
are in [`radar-software.md`](radar-software.md).

---

## 8. Azimuth — not in this build, and where it went

Bearing from the phase difference between two receivers is **designed, written
and passing its tests**, and it is **not built here**. All of it — what it
measures and what it costs, the second receive chain, the LO budget once one
splitter has to feed two mixers, the RF-switch alternative, the beam-scan option
the turntable used to serve, and the calibration it needs — lives in
[`../stage2/`](../stage2/). Nothing on this page depends on any of it, and
nothing on this page has to be undone to get there.

What § 1–7 already did for it, so it stays a bolt-on rather than a rebuild:

| done | where |
|---|---|
| the frame holds the second horn, at 193 mm, because all three are rolled 90° | § 7 |
| the third horn is cut, tuned and matched to the one you fitted | § 2, § 2c |
| the spare LNA and two spare op-amp channels are already on the bench | § 1, § 5 |
| the SMA jumpers came from one batch, so two receive chains would match | § 7 |
| the interface decision was made knowingly, not by accident | § 1 |

The parts to buy when you get there are priced in
[`../hardware/BOM.md`](../hardware/BOM.md) § F. The checkpoints on this page stop
at **7**, which is the finished radar; bringing up a second receiver has its own
bench procedure — the calibration constant above all — and that lives with the
code in [`../stage2/README.md`](../stage2/README.md).

---

## 9. Optional — a turntable, for pointing and for measuring the horn

The radar sees whatever is inside the 34° beam and reports its range and radial
velocity; it does not care where the frame is pointed. The turntable does two
jobs, and neither of them is measuring a bearing:

- **pointing.** It aims the whole three-horn frame at a wider sector than one
  beam covers, between dwells.
- **measuring the horn.** It is how you get a real beam pattern: park the PLL on
  `CW`, put a corner reflector on boresight, and step the frame past it while
  watching the detection SNR. That is the only antenna measurement on this bench
  that does not need a borrowed VNA (§ 2c).

- NEMA-17 + A4988, 1/16 microstep (MS1–3 high), VREF set for ~0.8 A.
- Lazy-susan bearing (150 mm), stepper 1:1 via a printed hub. `STEPS_PER_DEG`
  in `radar_ctl.ino` is 8.889 for 1:1 (200 × 16 / 360).
- Coax to three horns needs slack for ±45°. Loose loops, not a tight twist.
- It moves **between** dwells, never during one. Point, dwell, read, repeat: a
  frame that is moving while the block is being recorded smears every range cell.

Most indoor flying fits in one 34° beam at 3–10 m, so this is the part to skip
first if the budget is tight. $53, and nothing else depends on it.

---

## 9b. Where this goes next — 24 GHz

Everything downstream of the mixer's IF is band-independent: the video
amplifier, the reference, the power, the sound card, the whole DSP and its tests.
A 24 GHz front end would take the range cell from **1.80 m to 0.60 m**, which is
the figure that matters here. (It would also widen the unambiguous cone of the
quarantined azimuth design from ±18.5° to about ±90°, because the baseline that
matters scales with the wavelength — that study is in
[`../stage2/`](../stage2/).)

The catch is the antenna, and it is the reason this build is at 2.4 GHz: every
cheap 24 GHz module arrives with its array already laid out on the package, so
buying one hands the most interesting part of the project to someone else. The
version worth building is a board carrying a BGT24LTR22, an ADF4159 ramp PLL and
three patch columns you lay out yourself. Do it after this one works, not
instead of it.

---

## 10. Safety and legality (short)

- +10 dBm into a 13 dBi horn is 0.2 W EIRP — under the Part 15 limits for the
  band, but keep the mouths pointed away from people at < 1 m out of habit.
- The sweep stays inside **2400–2483.5 MHz**; the firmware refuses anything
  else. Do not "extend it for resolution" — below 2400 is licensed aeronautical
  telemetry.
- The drone flies on a **915 MHz** ELRS link, 1.5 GHz away from the sweep, which
  is why the radar gets the whole band. Do the link check in
  [`drone-software.md`](drone-software.md) before the drone is ever in the air
  with the radar sweeping: with `SWEEP 1` running, link quality must stay at 100
  and RSSI must not move.
- Do not fit the kit's own 2.4 GHz radio option. It hops across the sweep.
