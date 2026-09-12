# Bill of Materials — horn-fed FMCW radar (drone: stock ESP-FLY on a 915 MHz link)

> **To actually order, use [`ORDER.md`](ORDER.md)** — the same list with links
> and prices re-checked 10 September 2026. Three have moved: the ZX05 mixer is
> $79 and scarce, the UMC404HD is $139 not $100, and the GPIO Labs filter comes
> in SMA *and* RP-SMA (you need SMA — its 3 dB edges are 2380/2500 MHz, which
> the full-band sweep fits inside). This page is the reasoning; that one is the
> shopping.
>
> **The interface is the one row that depends on how far you are going.** This
> radar records two channels — beat and sync — and any line-level 2-in interface
> does it, including one you already own. The azimuth upgrade in
> [`../stage2/`](../stage2/) would need four on one sample clock, and that is the
> UMC404HD at $139. Row 13 is what you buy now; row 26 is what the upgrade
> replaces it with.

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

## A. RF chain — ~$205 (the one receive chain this radar has)

| # | item | qty | ~$ | source | notes |
|---|---|---|---|---|---|
| 1 | **ZX05-43MH-S+** double-balanced mixer, 824–4200 MHz, LO +13 dBm | 1 | 73 | Mini-Circuits (direct; 9 in stock when checked) | **no substitute — order first** |
| 2 | **ADF4351 PLL board**, 35 MHz–4.4 GHz, SMA out, 25 MHz TCXO | 1 | 27 | Amazon | replaces the VCO; stepped over SPI by `radar_ctl` |
| 3 | **SPF5189Z LNA module**, 50–4000 MHz, NF 0.6 dB, 4-pack | 1 | 24 | Amazon | 2 used (PA + LNA), 2 spares; ~12 dB gain at 2.4 GHz, P1dB ~+18 dBm. **The chip is EOL** (Qorvo PCN 21-0060, last buy Sept 2021; replacement QPL9547) — the modules are built from remaining stock, which is why you buy the 4-pack now. Its 0.6 dB NF is the bare-die figure at 900 MHz; expect ~1 dB at 2.4 GHz on a module |
| 4 | 2-way SMA power splitter, 800–2500 MHz | 1 | 13 | Amazon / eBay | replaces ZX10-2-42-S+ |
| 5 | SMA 3 dB attenuator, DC–6 GHz | 1 | 9 | Amazon | replaces VAT-3+ |
| 6 | SMA M-M RG316 jumpers, 20 cm, 3-pack | 2 | 18 | Amazon | 6 runs in the chain |
| 7 | SMA adapter assortment (M-M barrels, F-F) | 1 | 12 | Amazon | |
| 7b | **2.4 GHz band-pass filter**, 2400–2500 MHz, SMA inline | 1 | 29 | GPIO Labs (2450 MHz ISM BPF, $29.10, >40 dB at 2.2/2.8 GHz, 2.7 dB loss) or Data Alliance (BandPass2450, $13.70, no rejection spec published). The same FBP-2400-style module is listed on Amazon (ASIN B0C3BL74VN, B0C8269CGF) and AliExpress (~$25); Amazon prices were not verifiable from here. Mini-Circuits VBF-2435+ is $57.50 at DigiKey; ZFBP-2400-S+ (50 dB rejection, 2.2 dB loss) is the lab-grade option | between RX horn and LNA — keeps out-of-band signals off the wideband SPF5189Z, which amplifies 50–4000 MHz, so without it every signal in the building reaches the mixer. It no longer has to reject the drone's own WiFi: the control link moved to 915 MHz and the sweep took the whole band |

## B. Horns — ~$95 (materials for three)

| # | item | qty | ~$ | notes |
|---|---|---|---|---|
| 8 | **Copper sheet 24 ga (0.021"), 12" × 24"** | 2 | 45 | ~130 in² per horn, enough for three — two are fitted, the third is a spare that the azimuth upgrade would use. Copper so the seams solder. Not aluminium |
| 9 | **SMA female 4-hole flange, solder cup**, 10-pack | 1 | 12 | the feed probe launch |
| 10 | Brass rod 1/16" | 1 | 5 | probe: 28 mm into the guide |
| 11 | 60/40 solder + paste flux | 1 | 15 | plumbing solder; long seams |
| 12 | Aviation snips / sheet nibbler | 1 | 18 | |

Dimensions: aperture 263.8 × 193.1 mm, WR-340 throat 86.4 × 43.2 mm, flare
91.5 mm, probe 43.7 mm from the back wall. Cut list in
[`../docs/radar-hardware.md`](../docs/radar-hardware.md) §2.

## C. Baseband, control, power — ~$43

| # | item | qty | ~$ | notes |
|---|---|---|---|---|
| 13 | USB audio interface, 2 inputs — **owned: Behringer Xenyx 302USB** | 1 | 0 | the ADC. This radar records two channels, beat and sync, so any line-level 2-in interface does it. On the 302USB that is the stereo RCA line channel, beat left and sync right, mic channel down and the Line/USB switch on LINE IN. Row 26 is the only part of the baseband section the azimuth upgrade would replace rather than add to |
| 14 | ESP32 devkit (WROOM-32) | 1 | 10 | runs `firmware/radar_ctl` |
| 15 | TL072 ×2, breadboard, resistors/capacitors kit | 1 | 25 | video amp (`radar-hardware.md` §5) |
| 16a | 12 V 3 A supply — **owned** | 1 | 0 | 12 V for the op-amp and the stepper |
| 16b | LM2596 buck ×2 | 1 | 8 | 5.00 V for the RF modules and the ESP32; set it before anything is connected |

## D. Mechanical — the three-horn frame, and an optional turntable — ~$53

| # | item | qty | ~$ | notes |
|---|---|---|---|---|
| 17 | Plywood ~18" × 15", L-brackets, M3 hardware, standoffs | 1 | 28 | |
| 18 | NEMA-17 stepper + A4988 (+ lazy-susan bearing) | 0–1 | 25 | **optional.** Two jobs, neither of them a measurement of direction: it points the 34° beam at a wider sector, and it is how you sweep a reflector past boresight to measure the horn's real beam pattern. Skip it first if the budget is tight |

## E. Drone and its control link — ~$122

The drone is a **stock Seeed ESP-FLY**, built to its own guide, flown on a
**915 MHz ELRS link** so the radar can sweep the whole 2400–2483.5 MHz band
instead of squeezing into 40 MHz above the drone's WiFi. Do not buy or fit the
kit's 2.4 GHz radio option (ESP-NOW transmitter or RP1 V2) — it hops across the
radar's sweep. Why this is worth $122 is measured in
[`../docs/radar-software.md`](../docs/radar-software.md) § 8: in a 4 m room the
40 MHz coexistence sweep is 0.2–0.5 m out and blind inside 1.5 m, while the full
band holds 0.1 m everywhere.

### The 915 MHz ELRS link

| # | item | qty | ~$ | notes |
|---|---|---|---|---|
| 19 | **RadioMaster Pocket** (any internal RF — you use the bay) | 1 | 65 | cheapest EdgeTX radio with a **Nano module bay**. The T8L cannot do this: internal 2.4 GHz only, no bay, no 900 MHz variant |
| 20 | **RadioMaster Bandit Nano**, 915 MHz ELRS module | 1 | 40 | fits the Pocket's Nano bay; 10 mW–1 W; FCC915 |
| 21 | **BetaFPV ELRS Nano 915 RX** (0.7 g) *or* HappyModel ES900RX (0.6 g) | 1 | 17 | lightest 900 MHz receivers; CRSF to the XIAO's UART2 (GPIO 9 RX / GPIO 8 TX) |
| 21b | 915 MHz receiver antenna | 0–1 | 0–5 | usually included: ~80 mm wire or a "T" |

Both ends must be the **same ExpressLRS major version** and the **same
regulatory domain (FCC915)**. Alternatives: any EdgeTX radio with a JR bay
(Boxer, TX12) plus a Bandit Micro; HappyModel ES900TX instead of the Bandit
Procedure in [`../docs/drone-hardware.md`](../docs/drone-hardware.md), firmware
and binding in [`../docs/drone-software.md`](../docs/drone-software.md).

**If you are flying outdoors or in a space where 5–10 m is available, you can
skip this section entirely** and fly from the phone on WiFi channel 1 with a
2440–2480 MHz sweep. It costs nothing and a 3.75 m range cell is a small
fraction of a large scene. It is only a bedroom that makes this $122 worth
spending.

## F. The azimuth upgrade — not part of this build — ~$299

**Buy none of this to build the radar.** Bearing from the phase difference
between two receivers is designed, written and quarantined in
[`../stage2/`](../stage2/); this section exists so you know what it would cost
and what you must *not* buy twice. Rows 25 and 28 are already in the box, because
sections B and A bought them in multiples on purpose.

| # | item | qty | ~$ | notes |
|---|---|---|---|---|
| 22 | second ZX05-43MH-S+ mixer | 1 | 73 | second receive channel. Critical path — order first |
| 23 | second 2-way splitter (LO to both mixers) | 1 | 13 | |
| 23b | **6 dB SMA pad** | 1 | 9 | **only with the ZX05 mixer.** Splitting the LO again leaves +7 dBm per mixer, 6 dB under the ZX05's +13 dBm rating, so the spare SPF5189Z from row 3 goes in as an LO amplifier — and it needs this pad in front of it or it is driven past its +18 dBm P1dB. The $25 generic modules are level-7 parts that take +7 dBm directly: skip this row. [`../stage2/README.md`](../stage2/README.md) has the LO budget |
| 24 | second 2400–2500 band-pass filter | 1 | 29 | in front of the second LNA; same part as row 7b |
| 25 | third horn — materials already in B, cut in the same session | — | 0 | drops into the empty bay **beside** the fitted RX at 193 mm centres, all three horns rotated 90° |
| 26 | **Behringer UMC404HD** 4-input USB interface | 1 | 139 | the one part the upgrade forces you to replace rather than add to. It needs beat A, beat B and sync on **one sample clock**: two 2-in interfaces have independent clocks and a phase measurement between independently clocked converters means nothing. Nothing else in the baseband section changes |
| 27 | third + fourth TL072, second passives set, second breadboard | 1 | 18 | row 15's two TL072 are fully used by U1A/U1B/U2B/U2A; a second video amp needs three more channels |
| 28 | second LNA (SPF5189Z 4-pack, row 3) | — | 0 | |
| 29 | 2 more SMA jumper 3-packs | 2 | 18 | the second receive chain adds four coax runs. Buy them together: the two RX chains must be phase-matched, and identical cables from one batch is the cheap way to do it |

## G. Test gear — buy none of it

| # | item | qty | ~$ | notes |
|---|---|---|---|---|
| 30 | VNA reaching 2.5 GHz | 0 | 0 | **not required.** The link has 54 dB of margin, so a badly tuned horn costs 2.5 dB of it. Tune the probe against the radar's own detection SNR instead — `docs/radar-hardware.md` § 2c. Borrow one if you want the real numbers |
| 31 | RTL-SDR v4 + 30 dB SMA pad | 0 | 0 | optional. The leakage tone at checkpoint 7 already proves the whole chain is alive |

**Do not buy a NanoVNA-H4.** It stops at 1.5 GHz and cannot see a 2.44 GHz horn
at all. A VNA that does reach this band is a LiteVNA-64 at ~$165 or a NanoVNA V2
Plus4 at ~$150 — more than any single radar part here, for a measurement the
build does not depend on.

## Totals

Prices below use the **$29** band-pass (GPIO Labs, the only cheap one that
publishes rejection figures). The `~$` column in every table is the line total.

### What to order now

This is the list: the whole radar — range and radial velocity — with nothing in
it that the azimuth upgrade would make you buy twice. It puts up the three-horn
frame and fills two of its bays.

**Order 1 — the radar, $317**

This list builds the horns the way [`../docs/radar-hardware.md`](../docs/radar-hardware.md)
§ 2 documents them: cut from 0.021" copper sheet, seams soldered, continuity
checked panel to panel. 3D-printing the shells and lining them with copper tape
saves about $40 (see *Ways to spend less*), but there is no cut list, no probe
mounting detail and no seam-continuity checkpoint written for that version — so
it is a substitution you are making yourself, not a documented build.

| item | $ |
|---|---|
| mixer, 1.5–4.5 GHz SMA module | 25 |
| ADF4351 PLL board | 27 |
| SPF5189Z LNA **4-pack** (2 used now, 2 held for the upgrade) | 24 |
| 2-way splitter | 13 |
| 3 dB SMA attenuator | 9 |
| SMA jumpers, 3 packs, **one order** so the cables match | 27 |
| SMA adapter assortment | 12 |
| band-pass filter | 14 |
| three horns: copper sheet ×2, SMA flange 10-pack, brass rod, solder, snips | 95 |
| frame: plywood, L-brackets, M3 hardware, standoffs | 28 |
| ESP32 devkit | 10 |
| **two** TL072, breadboard, passives kit | 25 |
| LM2596 ×2 (12 V supply already owned) | 8 |
| USB audio interface — **already owned**, any 2-in carries beat and sync | 0 |
| | **317** |

**Order 1b — the drone's control link, $122.** Only if you are flying in a
small room; see § E. RadioMaster Pocket 65, Bandit Nano 915 40, BetaFPV ELRS
Nano 915 RX 17. Skip it outdoors and fly from the phone on a 40 MHz sweep.

**Order 2 — the azimuth upgrade, only if you go there, $70**

| item | $ |
|---|---|
| second mixer | 25 |
| second 2-way splitter, for LO to both mixers | 13 |
| second band-pass filter | 14 |
| two more TL072, second passives set, second breadboard | 18 |
| | **70** |

Order 1 alone is the radar. **$387 of parts** buys both (order 1 at $317 plus
order 2 at $70), **about $416 delivered** — plus **$122** for the 915 MHz link if
you are flying indoors, so **~$538** for the full indoor build with the upgrade.
Add the $139 four-input interface when you commit to the upgrade and it is
**~$677**. Print the horns instead of cutting them and take $40 off. Live prices
and links are in [`ORDER.md`](ORDER.md).

Nothing in order 1 becomes redundant if you never place order 2, and nothing in
it is wasted if you do: the LNA 4-pack, the horn count, the frame and the second
TL072 are all sized for the larger radar. The one item people get wrong here is
the sound card: a UCA202 bought now is $30 thrown away, because two of them
cannot measure phase.

---

### Under $500, if you already know you want azimuth eventually

Neither of these is needed for the radar this repo builds — order 1 above is. They
are for the case where you have already decided to end up at the quarantined
azimuth design, and want the cheapest route to it. They differ in how the two
receive antennas are read.

**Build A — switched single chain, ~$346 delivered.** Cheapest that works.

| item | $ |
|---|---|
| mixer, cheap 1.5–4.5 GHz SMA module (see note) | 25 |
| ADF4351 PLL board | 27 |
| SPF5189Z LNA 4-pack | 24 |
| 2-way splitter, 3 dB pad, SMA jumpers ×3 packs, adapters | 61 |
| band-pass filter (Data Alliance) | 14 |
| SPDT 2.4 GHz RF switch, driven from a spare ESP32 pin | 25 |
| three printed horns: filament, copper tape, SMA flanges, brass rod, solder | 62 |
| ESP32, TL072 ×2 + breadboard + passives, 12 V supply + bucks | 53 |
| UCA202 (2 channels is enough: one beat, one sync) | 30 |
| **parts** | **321** |
| shipping + 6 % tax | 25 |
| **total** | **~346** |

**Build B — simultaneous two channels, ~$468 delivered.** Same as A plus a
second mixer, splitter, band-pass, video-amp channel and the 4-input
interface, less the switch and the UCA202. Costs $122 more and removes the
motion-phase correction, which is the only real software risk in A.

Both assume: horns printed rather than cut from copper sheet, **no turntable**,
and **no VNA** — the probe gets tuned against the radar's own SNR instead.

**Why no turntable.** It was mandatory back when azimuth came from scanning a
beam. It measures nothing now: it points the beam at a wider sector, and it
sweeps a reflector past boresight when you want the horn's real pattern. Add it
later for $53 if you want either.

**About the cheap mixer.** Several 1.5–4.5 GHz double-balanced SMA modules sell
for ~$25 with 8.5 dB conversion loss against the ZX05-43MH's 7 dB, which costs
1.5 dB out of a 54 dB margin and does not matter. What the listings do *not*
state is the LO drive level they need. This chain delivers +10 dBm, which suits
a level-7 diode mixer; confirm that before ordering, and keep the $73
Mini-Circuits part as the fallback if the leakage tone at checkpoint 3 comes out
weak. That one substitution is $96 of the saving.

---

### The full-price build, for reference

If none of the above compromises are acceptable.

If you know from the start that you are going to azimuth, buy the **UMC404HD
once** and skip the two-input interface entirely — it does everything the
two-input one does, and it is the only part of the baseband section the upgrade
touches. That is the single change from buying in stages.

| | | running |
|---|---|---|
| A. RF chain, first receiver | 205 | 205 |
| B. Horns, materials for all three | 95 | 300 |
| C. Baseband, control, power | 43 | 343 |
| D. Turntable | 53 | 396 |
| F. Second receiver and the azimuth upgrade (UMC404HD included) | 299 | **695** |
| G. Test gear (buy none) | 0 | 695 |
| shipping (Mini-Circuits direct) + 6 % tax | ~56 | **~751** |

**Parts only: ~$695. Delivered: ~$751.**

Already owned and priced at zero above: the laptop, the 12 V supply, and a
two-input USB interface (a Behringer Xenyx 302USB). Also the ESP-FLY drone.

### If you build it in stages instead

| | | running |
|---|---|---|
| The radar — range and radial velocity (A + B + C) | 343 | 343 |
| + the azimuth upgrade (F, including the 4-input interface it forces) | 299 | 642 |
| + optional turntable (D) | 53 | 695 |


The first row is this build. Staged this way nothing is rebuilt: the radar puts
up the three-horn frame and the upgrade is purely additive. One thing *is*
written off — the two-input interface, once four channels on one clock are
needed. That is the right trade when the two-input one is already on the shelf;
it is not a reason to spend $139 up front on a capability you have not decided to
build.

### The cheaper azimuth path

One RF switch in front of a single receive chain instead of a whole second
chain. Section F's $160 of receive hardware (the $299 above, less the $139
interface) becomes about $40, and a two-input interface is enough because there
is still only one beat channel. See [`../stage2/README.md`](../stage2/README.md)
for the trade: the two antennas are then sampled 7.4 ms apart, so the target's
motion phase has to be corrected from the measured velocity, and the unambiguous
velocity halves.

| | |
|---|---|
| A + B + C (with UCA202) + D + SPDT SMA switch + jumpers | **~$475** |
| + tax and shipping | ~$620 |

### Ways to spend less

| | saves |
|---|---|
| 3D print the horns and line them with copper tape instead of cutting sheet | ~$40 |
| Skip the VNA entirely and tune against detection SNR | $165 |
| Skip the RTL-SDR, use a borrowed power meter | $40 |
| Data Alliance band-pass at $13.70 instead of GPIO Labs at $29, ×2 | $31 |

Not needed: external LNAs beyond the two, any 2.4 GHz sniffer boards,
a UWB kit. An RF switch is the cheaper single-chain alternative to section F;
`stage2/README.md` explains why it is not the first choice.
