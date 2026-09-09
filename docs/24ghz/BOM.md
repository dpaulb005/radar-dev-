# Bill of materials — 24 GHz board

Researched September 2026. Every line is marked **confirmed** (I opened the
distributor's page and read the number) or **estimate** (I did not, and why).
Nothing is rounded up into a comfortable total.

The headline is short: **the 24 GHz build is one board.** Everything after the
mixer already exists and is already paid for, so the question is not what a
24 GHz radar costs, it is what this board costs — and most of that is fab and
assembly, not parts.

---

## What you already own — $0

Carried over from the 2.4 GHz build without modification.

| item | why it survives |
|---|---|
| UMC404HD 4-input interface | still 4 inputs, and it does 192 kHz, which at 24 GHz matters |
| ESP32 dev board | still the sequencer; different registers |
| 13 V supply, fuse, reverse protection, enclosure | band-independent |
| laptop, and every line of `ground_station/` | band-independent |
| SMA jumpers, adapters, pads | only for bench work now; nothing at 24 GHz uses coax |

Gone, and not replaced: both horns, the mixer, the band-pass, the LNA, the PA,
the splitter, the ADF4351 board, the TL072 video amplifier. About **$296** of
the current build is absorbed into a $36 pair of chips.

---

## A. Silicon — $35.74 confirmed

| # | item | qty | $ ea | $ | status | source |
|---|---|---|---|---|---|---|
| 1 | **BGT24LTR22E6327XTSA1** — 24 GHz MMIC, 2 TX / 2 RX, eWLB-52 | 1 | 15.26 | 15.26 | **confirmed**, 1580 in stock | [DigiKey](https://www.digikey.com/en/products/detail/infineon-technologies/BGT24LTR22E6327XTSA1/15776575) |
| 2 | **ADF4159CCPZ** — 13 GHz fractional-N ramp PLL, 24-LFCSP | 1 | 20.48 | 20.48 | **confirmed** | [DigiKey](https://www.digikey.com/en/products/detail/analog-devices-inc/ADF4159CCPZ-RL7/4916421) |

Buy two of each. The MMIC is the part you cannot rework off a board, and 13
weeks of manufacturer lead time is a long time to wait for a second one.
Adding a spare of each: **+$35.74**.

## B. Passives, regulation and clock — ~$45 estimate

| # | item | qty | $ | status |
|---|---|---|---|---|
| 3 | 1.5 V low-noise LDO, high PSRR (VCO supply noise lands in the beat spectrum) | 2 | ~6 | estimate |
| 4 | 3.3 V LDO for the PLL side | 1 | ~2 | estimate |
| 5 | 25 MHz TCXO for the ADF4159 reference | 1 | ~5 | estimate |
| 6 | 0402 C/R kit — decoupling, loop filter, IF DC blocks and dividers | 1 | ~25 | estimate |
| 7 | 10 µF bulk, ferrites, test points | — | ~7 | estimate |

Marked estimate because these are catalogue commodities whose exact part
numbers follow from the schematic, which does not exist yet. The total is not
sensitive to getting them wrong by a few dollars.

## C. The boards — $135 to $365, and this is the uncertain part

| # | item | qty | $ | status |
|---|---|---|---|---|
| 8 | **FR-4 dimension-sweep panel**, 100 × 100 mm, 2-layer, 0.2 mm | 5 | 5–15 | estimate, but FR-4 prototype pricing is well known |
| 9 | **RO4350B board**, ~70 × 50 mm, 2-layer, 0.254 mm core, ENIG, controlled impedance | 5 | **120–350** | **estimate — instant quote required** |
| 10 | stencil for the MMIC and 0402s | 1 | ~25 | estimate |

**Why row 9 is a range and not a number.** RO4350B laminate is $46–78 per
square foot. A 70 × 50 mm board is 0.038 ft², so the *material* in it is about
**$2.30**. Everything else in the price is fab setup: Rogers-specific lamination
and drilling, controlled-impedance coupons, ENIG, and the fact that a small
Rogers order is a special run rather than a slot on a shared FR-4 panel. Both
JLCPCB and PCBWay advertise RO4350B and neither publishes a figure outside
their instant-quote tool, which needs the Gerbers.

So this line cannot be pinned down until the board is drawn — and when it is,
it should be quoted at both houses before ordering. The range above brackets
what the material cost and the "4–6× FR-4" multiple imply.

## D. Assembly — $0 to $250

The BGT24LTR22 is a **52-ball eWLB on a 3.63 mm body**. That is not a soldering
iron job and not a hot-plate job.

| route | $ | what it means |
|---|---|---|
| turnkey assembly, consigned parts | 100–250 | send the board house the Gerbers and the chips. **estimate — quote required** |
| reflow it yourself | ~0 | stencil, paste, a controlled profile and X-ray you do not have to inspect the result. Possible; not advisable for the first one |

## E. Optional — measurement and de-risking

| # | item | $ | status | note |
|---|---|---|---|---|
| 11 | **EVAL-BGT24LTR22** evaluation board | **not obtainable** | Infineon, Mouser and DigiKey all refused the price to an automated fetch — request a quote | Exposes the RF and IF ports, so the SPI, the PLL loop and the firmware can be brought up against a known-good board before your own layout exists. It is the single best way to separate *"my antenna is wrong"* from *"my software is wrong"* |
| 12 | 2.92 mm edge-launch connector, 40 GHz (Amphenol CDI TMB-E9FS-1S1) | 38.50 ea | **confirmed** | [DigiKey](https://amphenolcdi.com/tmb-e9fs-1s1). Only if you build a separate antenna test coupon. Southwest Microwave's equivalents are $110–156 |
| 13 | 24 GHz VNA | — | borrow | No hobby instrument reaches 24 GHz; a NanoVNA-H4 stops at 1.5 GHz. See [`../goal.md`](../goal.md) and § measurement in [`README.md`](README.md) |

---

## Totals

| build | $ |
|---|---|
| **The learning board.** FR-4 sweep panel only, measured against a reflector | **5–15** |
| **Minimum real board.** One MMIC, one PLL, passives, Rogers fab at the low quote, self-assembled | **~205** |
| **Sensible.** Spares of both chips, both board types, stencil, turnkey assembly at the low quote | **~340** |
| **If every quote comes back high** | **~720** |

For comparison, from [`../higher-bands.md`](../higher-bands.md): an RFbeam
K-LC6 is $55, a TI IWR6843ISK is $283, and the IWR6843 with a DCA1000EVM
capture card so you can keep writing your own DSP is $1,271. All three ship
with the antenna already designed, which is why none of them is on this page.

**The sensible build costs about what the 2.4 GHz radar cost** — $346 for
budget build A in [`../../hardware/BOM.md`](../../hardware/BOM.md) — and it
reuses that build's entire back end. It is not a cheaper radar. It is the same
money spent on a board you designed instead of on coax modules somebody else
designed.

---

## What would change these numbers

- **A quote.** Rows 9 and the assembly line are 60–80 % of the total and both
  are estimates. Draw the board, quote it at JLCPCB and PCBWay, and this page
  becomes real.
- **Panelising.** Five boards is the fab minimum but the design only needs one
  to work. Putting the FR-4 sweep panel and the Rogers board on one order, or
  fitting several revisions of the antenna on one Rogers panel, spreads the
  setup cost that dominates row 9.
- **The eval board.** If it is under about $250 it is worth buying first purely
  to de-risk the firmware, and that cost comes back the first time it tells you
  the software is fine and the antenna is not.
