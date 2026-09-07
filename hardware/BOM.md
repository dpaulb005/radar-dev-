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

## A. RF chain — ~$196

| # | item | qty | ~$ | source | notes |
|---|---|---|---|---|---|
| 1 | **ZX05-43MH-S+** double-balanced mixer, 824–4200 MHz, LO +13 dBm | 1 | 73 | Mini-Circuits (direct; 9 in stock when checked) | **no substitute — order first** |
| 2 | **ADF4351 PLL board**, 35 MHz–4.4 GHz, SMA out, 25 MHz TCXO | 1 | 27 | Amazon | replaces the VCO; stepped over SPI by `radar_ctl` |
| 3 | **SPF5189Z LNA module**, 50–4000 MHz, NF 0.6 dB, 4-pack | 1 | 24 | Amazon | 2 used (PA + LNA), 2 spares; ~12 dB gain at 2.4 GHz, P1dB ~+18 dBm. **The chip is EOL** (Qorvo PCN 21-0060, last buy Sept 2021; replacement QPL9547) — the modules are built from remaining stock, which is why you buy the 4-pack now. Its 0.6 dB NF is the bare-die figure at 900 MHz; expect ~1 dB at 2.4 GHz on a module |
| 4 | 2-way SMA power splitter, 800–2500 MHz | 1 | 13 | Amazon / eBay | replaces ZX10-2-42-S+ |
| 5 | SMA 3 dB attenuator, DC–6 GHz | 1 | 9 | Amazon | replaces VAT-3+ |
| 6 | SMA M-M RG316 jumpers, 20 cm, 3-pack | 2 | 18 | Amazon | 6 runs in the chain |
| 7 | SMA adapter assortment (M-M barrels, F-F) | 1 | 12 | Amazon | |
| 7b | **2.4 GHz band-pass filter**, 2400–2500 MHz, SMA inline | 1 | 20 | Amazon / eBay | between RX horn and LNA — keeps out-of-band signals off the wideband SPF5189Z (it cannot reject WiFi ch 1; the drone's AP power is turned down for that) |

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

## C. Baseband, control, power — ~$83

| # | item | qty | ~$ | notes |
|---|---|---|---|---|
| 13 | **Behringer UCA202** USB audio interface | 1 | 30 | the ADC: L = beat, R = sync; 44.1/48 kHz 16-bit |
| 14 | ESP32 devkit (WROOM-32) | 1 | 10 | runs `firmware/radar_ctl` |
| 15 | TL072 ×2, breadboard, resistors/capacitors kit | 1 | 25 | video amp (`radar-hardware.md` §5) |
| 16 | 12 V 3 A supply + LM2596 buck ×2 | 1 | 18 | 12 V for the op-amp/stepper, 5 V for RF modules + ESP32 |

## D. Mechanical — stage 2 — ~$50

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

## F. Stage 3 extras (elevation) — ~$225, later

| # | item | qty | ~$ | notes |
|---|---|---|---|---|
| 22 | second ZX05-43MH-S+ mixer | 1 | 73 | second receive channel |
| 23 | second 2-way splitter (LO to both mixers) | 1 | 13 | |
| 24 | third horn — materials already in B | — | 0 | stacked 193 mm below RX |
| 25 | **4-input USB audio interface** (Behringer UMC404HD) | 1 | 100 | beat 1, beat 2, sync on one sample clock — two UCA202s cannot do phase |
| 26 | second TL072 channel (parts in C) | — | 0 | |

## Totals

| | |
|---|---|
| Stage 1 (A + B + C) | **~$374** |
| + Stage 2 (D) | ~$424 |
| + Drone fallback to 915 MHz (E-fallback) | ~$554 |
| + Stage 3 (F) | ~$780 |

Not needed: SDRs, external LNAs beyond the two, RF switches, any 2.4 GHz
sniffer boards, a UWB kit.

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
