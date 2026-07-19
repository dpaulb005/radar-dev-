# Bill of Materials

Target: locate your own ESP32-equipped drone within a 5–10 m area, budget < $150.
Prices are typical US street prices (AliExpress / Amazon, mid-2026).

> **ESP-BLAST builders:** see `docs/espblast.md`. Your drone-side cost is $0
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
| 9 | RX5808 5.8 GHz receiver module | 3 | $10 | $30 | Analog RSSI output read by an ESP32 ADC; tracks the FPV video carrier with zero drone modifications. Coarser than 2.4 GHz sniffing; see the note in `docs/espblast.md` and the RotorHazard project for the reference design. |

## Explicitly NOT needed

- **SDRs** (RTL-SDR, KrakenSDR, HackRF) — required only for true
  reflection-based passive radar, which doesn't work at this range/budget
  (see `docs/feasibility.md`).
- Directional antennas, LNAs, RF switches.

## Placement guidance

- Spread the 3 sniffer nodes in a triangle **around** the flight area
  (baseline ≥ 6 m). Geometry inside the triangle is much better than outside.
- Add a 4th sniffer node (one more $6 board) for 3D fixes and robustness —
  the solver in `ground_station/` uses as many nodes as report in.
- Measure node positions with a tape measure to ~10 cm; position error of the
  anchors goes straight into the solution.
