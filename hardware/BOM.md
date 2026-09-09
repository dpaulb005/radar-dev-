# Bill of Materials — horn-fed FMCW radar (drone: stock ESP-FLY, flown by phone)

Researched September 2026 (Mini-Circuits store checked directly; Amazon /
FPV retailers for the rest). Prices are US street, rounded. Order in the
table order — the mixer is the critical path.

> **What changed from the MIT list, and why.** Three of MIT's six coax parts
> are no longer buyable at retail: the **ZX95-2536C+ VCO is a non-catalog
> part**, and the ZX60-272LN-S+ amplifier ($119, ×2) and ZX10-2-42-S+
> splitter ($61) showed **stock 0**. Amazon carries no coaxial VCO and no
> 2.4 GHz mixer at all. The list below keeps the one part with no substitute
> (the mixer) and replaces the rest with parts that are in stock, for ~$200
> of RF instead of ~$577.

## A. RF chain — ~$205 (first receiver)

| # | item | qty | ~$ | source | notes |
|---|---|---|---|---|---|
| 1 | **ZX05-43MH-S+** double-balanced mixer, 824–4200 MHz, LO +13 dBm | 1 | 73 | Mini-Circuits (direct; 9 in stock when checked) | **no substitute — order first** |
| 2 | **ADF4351 PLL board**, 35 MHz–4.4 GHz, SMA out, 25 MHz TCXO | 1 | 27 | Amazon | replaces the VCO; stepped over SPI by `radar_ctl` |
| 3 | **SPF5189Z LNA module**, 50–4000 MHz, NF 0.6 dB, 4-pack | 1 | 24 | Amazon | 2 used (PA + LNA), 2 spares; ~12 dB gain at 2.4 GHz, P1dB ~+18 dBm. **The chip is EOL** (Qorvo PCN 21-0060, last buy Sept 2021; replacement QPL9547) — the modules are built from remaining stock, which is why you buy the 4-pack now. Its 0.6 dB NF is the bare-die figure at 900 MHz; expect ~1 dB at 2.4 GHz on a module |
| 4 | 2-way SMA power splitter, 800–2500 MHz | 1 | 13 | Amazon / eBay | replaces ZX10-2-42-S+ |
| 5 | SMA 3 dB attenuator, DC–6 GHz | 1 | 9 | Amazon | replaces VAT-3+ |
| 6 | SMA M-M RG316 jumpers, 20 cm, 3-pack | 2 | 18 | Amazon | 6 runs in the chain |
| 7 | SMA adapter assortment (M-M barrels, F-F) | 1 | 12 | Amazon | |
| 7b | **2.4 GHz band-pass filter**, 2400–2500 MHz, SMA inline | 1 | 29 | GPIO Labs (2450 MHz ISM BPF, $29.10, >40 dB at 2.2/2.8 GHz, 2.7 dB loss) or Data Alliance (BandPass2450, $13.70, no rejection spec published). The same FBP-2400-style module is listed on Amazon (ASIN B0C3BL74VN, B0C8269CGF) and AliExpress (~$25); Amazon prices were not verifiable from here. Mini-Circuits VBF-2435+ is $57.50 at DigiKey; ZFBP-2400-S+ (50 dB rejection, 2.2 dB loss) is the lab-grade option | between RX horn and LNA — keeps out-of-band signals off the wideband SPF5189Z (it cannot reject WiFi ch 1; the drone's AP power is turned down for that) |

## B. Horns — ~$95 (materials for three)

| # | item | qty | ~$ | notes |
|---|---|---|---|---|
| 8 | **Copper sheet 24 ga (0.021"), 12" × 24"** | 2 | 45 | ~130 in² per horn; copper so the seams solder. Not aluminium |
| 9 | **SMA female 4-hole flange, solder cup**, 10-pack | 1 | 12 | the feed probe launch |
| 10 | Brass rod 1/16" | 1 | 5 | probe: 28 mm into the guide |
| 11 | 60/40 solder + paste flux | 1 | 15 | plumbing solder; long seams |
| 12 | Aviation snips / sheet nibbler | 1 | 18 | |

Dimensions: aperture 263.8 × 193.1 mm, WR-340 throat 86.4 × 43.2 mm, flare
91.5 mm, probe 43.7 mm from the back wall. Cut list in
[`../docs/radar-hardware.md`](../docs/radar-hardware.md) §2.

## C. Baseband, control, power — ~$83 (~$53 if you skip the UCA202, see Totals)

| # | item | qty | ~$ | notes |
|---|---|---|---|---|
| 13 | **Behringer UCA202** USB audio interface | 1 | 30 | the ADC: L = beat, R = sync; 44.1/48 kHz 16-bit |
| 14 | ESP32 devkit (WROOM-32) | 1 | 10 | runs `firmware/radar_ctl` |
| 15 | TL072 ×2, breadboard, resistors/capacitors kit | 1 | 25 | video amp (`radar-hardware.md` §5) |
| 16 | 12 V 3 A supply + LM2596 buck ×2 | 1 | 18 | 12 V for the op-amp/stepper, 5 V for RF modules + ESP32 |

## D. Mechanical — turntable — ~$53

| # | item | qty | ~$ | notes |
|---|---|---|---|---|
| 17 | Plywood ~18" × 15", L-brackets, M3 hardware, standoffs | 1 | 28 | |
| 18 | **NEMA-17 stepper + A4988** (+ lazy-susan bearing) | 1 | 25 | not a hobby servo: three copper horns sag one, and the 2.5° azimuth budget cannot absorb that |

## E. Drone — nothing (flown from the phone)

The drone is the stock ESP-FLY kit built per its official guide, ESP-Drone
firmware with the AP on WiFi channel 1 at 10 dBm; the radar sweeps
2440–2480 MHz above it. Do not buy or fit the kit's radio-controller option.
**$0.** The table below is the
fallback if the coexistence test in `docs/drone-software.md` §4 fails.

### E-fallback. 915 MHz control link — ~$130

| # | item | qty | ~$ | notes |
|---|---|---|---|---|
| 19 | **RadioMaster Pocket** (EdgeTX, Nano module bay) | 1 | 65 | the T8L has no module bay and is 2.4 GHz only |
| 20 | **RadioMaster Bandit Nano** 915 MHz ELRS TX module | 1 | 40 | FCC915 |
| 21 | **BetaFPV ELRS Nano RX 915 MHz** (0.7 g) or HappyModel ES900RX (0.6 g) | 1 | 17 | same four CRSF pads as the RP1 V2 |

## F. Stage 3 — azimuth interferometer — ~$251

Bearing from the phase difference between two receivers, in one 0.47 s dwell,
which is the only way to get it on a *moving* drone. See
[`../docs/azimuth.md`](../docs/azimuth.md).

| # | item | qty | ~$ | notes |
|---|---|---|---|---|
| 22 | second ZX05-43MH-S+ mixer | 1 | 73 | second receive channel. Critical path — order first |
| 23 | second 2-way splitter (LO to both mixers) | 1 | 13 | |
| 24 | second 2400–2500 band-pass filter | 1 | 29 | in front of the second LNA; same part as row 7b |
| 25 | third horn — materials already in B | — | 0 | **beside** the first RX at 193 mm centres, all three horns rotated 90° |
| 26 | **4-input USB audio interface** (Behringer UMC404HD) | 1 | 100 | beat A, beat B, sync on one sample clock. Two UCA202s cannot do phase — independent clocks |
| 27 | third + fourth TL072, second passives set, second breadboard | 1 | 18 | row 15's two TL072 are fully used by U1A/U1B/U2B/U2A; a second video amp needs three more channels |
| 28 | second LNA (SPF5189Z 4-pack, row 3) | — | 0 | |
| 29 | 2 more SMA jumper 3-packs | 2 | 18 | the second receive chain adds four coax runs. Buy them together: the two RX chains must be phase-matched, and identical cables from one batch is the cheap way to do it |

## G. Test gear the plan assumes — ~$105

`docs/testing.md` requires these at checkpoints 2 and 3. Neither is a radar
part, and you may already have or be able to borrow them.

| # | item | qty | ~$ | notes |
|---|---|---|---|---|
| 30 | **NanoVNA-H4** | 1 | 65 | required: tuning the horn probe depth to a match is checkpoint 2, and there is no other way to see it |
| 31 | RTL-SDR v4 + 30 dB SMA pad | 1 | 40 | optional: checks the PA output at checkpoint 3. A power meter substitutes |

## Totals

Prices below use the **$29** band-pass (GPIO Labs, the only cheap one that
publishes rejection figures). The `~$` column in every table is the line total.

### If you are building the azimuth radar, which is the point of the project

Buy the **UMC404HD from the start and skip the UCA202** — the 4-input interface
does everything the 2-input one does, and a phase measurement needs both beat
channels on one sample clock. That is the only change from buying in stages.

| | | running |
|---|---|---|
| A. RF chain, first receiver | 205 | 205 |
| B. Horns, materials for all three | 95 | 300 |
| C. Baseband, control, power (**less the UCA202**) | 53 | 353 |
| D. Turntable | 53 | 406 |
| F. Second receiver and interferometer | 251 | **657** |
| G. Test gear (NanoVNA required, SDR optional) | 105 | 762 |
| shipping (Mini-Circuits direct) + 6 % tax | ~55 | **~815** |

**Parts only: ~$657. Everything, delivered: ~$815.**

Already owned, not counted: the laptop, the phone, and the ESP-FLY drone.

### If you build it in stages instead

| | | running |
|---|---|---|
| Stage 1 — range and velocity (A + B + C with the UCA202) | 383 | 383 |
| + Stage 2 — turntable (D) | 53 | 436 |
| + Stage 3 — azimuth (F) | 251 | 687 |
| + test gear (G) | 105 | 792 |

Staging costs **$30 more** (the UCA202 becomes a spare) and defers $251.

### The cheaper azimuth path

One RF switch in front of a single receive chain instead of a whole second
chain. Section F's $251 becomes about $40, and the UCA202 is enough because
there is still only one beat channel. See `../docs/azimuth.md` for the
trade: the two antennas are then sampled 7.4 ms apart, so the target's motion
phase has to be corrected from the measured velocity.

| | |
|---|---|
| A + B + C (with UCA202) + D + SPDT SMA switch + jumpers | **~$475** |
| + test gear and tax | ~$620 |

### Ways to spend less

| | saves |
|---|---|
| 3D print the horns and line them with copper tape instead of cutting sheet | ~$40 |
| Borrow a NanoVNA from the department | $65 |
| Skip the RTL-SDR, use a borrowed power meter | $40 |
| Data Alliance band-pass at $13.70 instead of GPIO Labs at $29, ×2 | $31 |

Not needed: external LNAs beyond the two, any 2.4 GHz sniffer boards,
a UWB kit. An RF switch is the cheaper single-chain alternative to section F;
`docs/azimuth.md` explains why it is not the first choice.

---

<details>
<summary>Archived — passive RSSI/FTM localisation BOM (superseded)</summary>


Target: locate your own ESP32-equipped drone within a 5–10 m area, budget < $150.
Prices are typical US street prices (AliExpress / Amazon, mid-2026).

> **ESP-BLAST builders:** see `docs/archive/espblast.md`. Your drone-side cost is $0
> (one-line esp-fc patch) or ~$3 (row 6, piggyback beacon board). Upgrade A
> (FTM) does **not** apply — the ESP-BLAST's WROOM-32 lacks FTM support.

## Core system — RSSI multilateration (~$55)

| # | Item | Qty | Unit | Total | Notes |
|---|------|-----|------|-------|-------|
| 1 | ESP32-S3 (or ESP32-C3) dev board | 4 | $6 | $24 | 3 sniffer nodes + 1 hub. S3/C3/C6 also support FTM for the upgrade path. Boards with an IPEX connector + external antenna give steadier RSSI than PCB-antenna boards. |
| 2 | 2.4 GHz dipole antenna, IPEX/u.FL | 3 | $2 | $6 | Only if you chose IPEX boards. Keep all node antennas vertical (same polarization). |
| 3 | USB-C cables | 4 | $2 | $8 | One per board for flashing; hub stays connected to the laptop. |
| 4 | USB power banks (any small 5 V) | 3 | $5 | $15 | Powers the sniffer nodes in the field. Reuse phone banks if you have them. |
| 5 | Tripods / stakes / zip ties | 3 | ~$1 | $3 | Get node antennas ~1 m off the ground and note each node's (x, y, z). |

| 6 | ESP32-C3 Super Mini (optional piggyback beacon) | 0–1 | $3 | $0–3 | Only if you can't/won't patch the drone's own firmware. ~2.5 g, powered from the drone's 5 V rail. |

**Subtotal: ~$56–59.** The drone-side ESP32 you already have — it either gets
the one-line firmware patch or carries the piggyback beacon.

## Accuracy upgrade A — WiFi FTM time-of-flight (+$0–18)

| # | Item | Qty | Unit | Total | Notes |
|---|------|-----|------|-------|-------|
| 7 | ESP32-S3/C3/C6 boards | 0–3 | $6 | $0–18 | If you already bought S3/C3 boards in row 1, this upgrade is **free** — it's just different firmware (`rx_node_ftm`). Original-ESP32 (non-S/C) chips do **not** support FTM — this rules out the ESP-BLAST's WROOM-32 as the responder. |

FTM gives ~0.5–2 m ranging without any RSSI calibration. Recommended: buy
S3 or C6 boards up front so both modes work.

## Accuracy upgrade B — UWB, sub-30 cm (+$100, still ≤ $150 total if it replaces A)

| # | Item | Qty | Unit | Total | Notes |
|---|------|-----|------|-------|-------|
| 8 | DW3000/DWM3000 UWB module (e.g. Makerfabs ESP32 UWB DW3000) | 4 | $25–30 | $100–120 | 3 anchors + 1 tag on the drone. Centimeter-class two-way ranging. This is the "do it properly" path if RSSI accuracy disappoints. Weight check first: a UWB tag module is ~5–10 g — significant on a mini quad like the ESP-BLAST. |

## Alternative for a bone-stock drone — 5.8 GHz VTX tracking (~$45)

| # | Item | Qty | Unit | Total | Notes |
|---|------|-----|------|-------|-------|
| 9 | RX5808 5.8 GHz receiver module | 3 | $10 | $30 | Analog RSSI output read by an ESP32 ADC; tracks the FPV video carrier with zero drone modifications. Coarser than 2.4 GHz sniffing; see the note in `docs/archive/espblast.md` and the RotorHazard project for the reference design. |

## Explicitly NOT needed

- **SDRs** (RTL-SDR, KrakenSDR, HackRF) — required only for true
  reflection-based passive radar, which doesn't work at this range/budget
  (see `docs/archive/feasibility.md`).
- Directional antennas, LNAs, RF switches.

## Placement guidance

- Spread the 3 sniffer nodes in a triangle **around** the flight area
  (baseline ≥ 6 m). Geometry inside the triangle is much better than outside.
- Add a 4th sniffer node (one more $6 board) for 3D fixes and robustness —
  the solver in `ground_station/` uses as many nodes as report in.
- Measure node positions with a tape measure to ~10 cm; position error of the
  anchors goes straight into the solution.

</details>
