# Where to buy it

The shopping list, with links. **Prices checked 10 September 2026** and marked
**confirmed** where I opened the seller's page, **est.** where I did not.
[`BOM.md`](BOM.md) explains *why* each part is the one chosen; this page is
just where to click.

> **Three things changed since the BOM was priced.** Read these before ordering.
>
> 1. **ZX05-43MH-S+ mixer is now $79.31 and hard to get** — DigiKey stock-notify
>    only, Mouser backorder. It is the critical path. Order it first, or take
>    the $25 generic module the budget build already specifies.
> 2. **UMC404HD is $139, not the $100 in the BOM** — but it is no longer a
>    stage-1 purchase. Stage 1 records two channels and runs on the two-input
>    interface already owned; the $139 lands only if you go to stage 2.
> 3. **The GPIO Labs filter comes in SMA *and* RP-SMA.** You need **plain SMA**.
>    RP-SMA reverses the pin gender and will not mate with the rest of the chain.
>    Its 3 dB edges are **2380 / 2500 MHz**, so the full-band 2400–2483.5 sweep
>    fits with about 20 MHz to spare at each end — checked, because the sweep
>    now runs to the band edge where it used to stop at 2480.

---

## A. RF chain

| # | item | $ | where |
|---|---|---|---|
| 1 | **ZX05-43MH-S+** mixer, 824–4200 MHz | **79.31** confirmed | [DigiKey](https://www.digikey.com/en/products/detail/mini-circuits/ZX05-43MH-S/21727733) · [Mouser](https://www.mouser.com/ProductDetail/Mini-Circuits/ZX05-43MH-S+?qs=Imq1NPwxi75nb0uK%2FtVCPQ%3D%3D) (backorder) · [Mini-Circuits direct](https://www.minicircuits.com/pdfs/ZX05-43MH-S+.pdf) |
| 1-alt | generic 1.5–4.5 GHz SMA mixer module | ~25 est. | what the under-$500 build uses instead |
| 2 | **ADF4351 PLL board**, 35 MHz–4.4 GHz, SMA out | ~27 est. | [Amazon B0BCWVHFT1](https://us.amazon.com/Frequency-Synthesizer-Development-Generator-35M-4-4GHz/dp/B0BCWVHFT1) · [B078NRD8V6](https://www.amazon.com/35M-4-4GHz-Frequency-Synthesizer-Development-Generator/dp/B078NRD8V6) — get the plain **SPI** board, not a USB-controlled signal generator |
| 3 | **SPF5189Z LNA**, 4-pack | ~24 est. | [Amazon B08244LD9S](https://www.amazon.com/SPF5189Z-SPF-5189Z-5189Z-50MHz-4000MHz-Amplifier/dp/B08244LD9S) (4pcs) · singles: [B0H4CH543K](https://www.amazon.com/SPF5189Z-50-4000MHz-Ultra-Wideband-Wireless-Communication/dp/B0H4CH543K) |
| 4 | 2-way SMA splitter, 380–2500 MHz | ~13 est. | [eBay 156232418130](https://www.ebay.com/itm/156232418130) · lab-grade: [Pasternack PE2074](https://www.pasternack.com/2-way-sma-reactive-power-divider-0.8-ghz-2.5-ghz-30-watts-pe2074-p.aspx) |
| 5 | SMA 3 dB attenuator, DC–6/8 GHz | ~9 est. | [Amazon B0B93NB895](https://www.amazon.com/clp/B0B93NB895) (2 pcs) |
| 6 | SMA M-M RG316 jumpers, 20 cm | ~18 est. | any Amazon 3-pack — **buy all of them in one order** so the two receive cables are from the same reel (1 mm of mismatch is 0.43° of bearing) |
| 7 | SMA adapter assortment | ~12 est. | any Amazon kit; skip until you need it |
| 7b | **2.4 GHz band-pass** — buy **two**, one per receive chain | **29.10** confirmed | [GPIO Labs, SMA-F both ends](https://gpio.com/products/2450-mhz-ism-bandpass-filter-for-wifi-zigbee-and-bluetooth) — **3 dB edges 2380 / 2500 MHz**, 2.7 dB loss, >40 dB at 2.2 and 2.8 GHz. Your 2400–2483.5 sweep sits inside it with ~20 MHz of margin at each end. ⚠️ [the RP-SMA version](https://gpio.com/products/2450-mhz-or-2-4-ghz-ism-bandpass-filter-for-wifi-zigbee-and-bluetooth-with-rp-sma-connectors) will **not** mate with your chain |

## B. Horns

| # | item | $ | where |
|---|---|---|---|
| 8 | Copper sheet **24 ga, 12″ × 24″**, ×2 | ~45 est. | [Amazon B00AKMNO74](https://www.amazon.com/Copper-Sheet-Metal-12-24/dp/B00AKMNO74) · [B092MXPMYK](https://www.amazon.com/Copper-Sheet-Metal-Material-Size/dp/B092MXPMYK) — **copper, not brass or aluminium**; the seams have to solder |
| 9 | SMA female 4-hole flange, solder cup, 10-pack | ~12 est. | [Amazon B074BQV9PK](https://www.amazon.com/Female-4-Hole-Connector-Straight-Shipping/dp/B074BQV9PK) · [B09MVXKZGR](https://www.amazon.com/Female-Chassis-Connector-Straight-Shipping/dp/B09MVXKZGR) — must be **solder cup**, not PCB pin |
| 10 | Brass rod 1/16″ | ~5 est. | any hobby shop / Amazon |
| 11 | 60/40 solder + paste flux | ~15 est. | plumbing solder, not electronics rosin-core — the seams are long |
| 12 | Aviation snips or sheet nibbler | ~18 est. | any hardware store |

## C. Baseband, control, power

| # | item | $ | where |
|---|---|---|---|
| 13 | USB audio interface, 2 inputs — **owned, do not buy** | **0** | a Behringer Xenyx 302USB is on the shelf. Stage 1 wants two channels, beat and sync, and its stereo RCA line channel carries them: beat left, sync right, mic channel down, Line/USB switch on LINE IN. Buy the **UMC404HD** ([Sweetwater](https://www.sweetwater.com/store/detail/UMC404HD--behringer-u-phoria-umc404hd-usb-audio-interface) · [Amazon B00QHURLHM](https://www.amazon.com/BEHRINGER-Audio-Interface-4-Channel-UMC404HD/dp/B00QHURLHM), $139) only when you commit to stage 2, which needs four channels on one sample clock |
| 14 | ESP32 devkit (WROOM-32) | ~10 est. | any Amazon/AliExpress devkit |
| 15 | TL072 ×2, breadboard, R/C kit | ~25 est. | any electronics supplier |
| 16a | 12 V 3 A supply — **owned, do not buy** | **0** | already on the shelf |
| 16b | LM2596 buck ×2 | ~8 est. | any Amazon |

## D. Mechanical

| # | item | $ | where |
|---|---|---|---|
| 17 | Plywood, L-brackets, M3 hardware, standoffs | ~28 est. | hardware store |
| 18 | NEMA-17 + A4988 + lazy-susan bearing | ~25 est. | **optional** — points the beam at a wider sector, takes no part in measuring azimuth. Cut this first |

## E. The 915 MHz control link

| # | item | $ | where |
|---|---|---|---|
| 19 | **RadioMaster Pocket** (EdgeTX, Nano bay) | ~65 est. | [RadioMaster](https://radiomasterrc.com/products/pocket-radio-controller-m2) · [GetFPV](https://www.getfpv.com/radiomaster-pocket-radio-cc2500-elrs-2-4ghz.html) — the **CC2500** version is arguably better here: no internal 2.4 GHz ELRS to leave on by mistake |
| 20 | **Bandit Nano** 915 MHz ELRS module | ~40 est. | [RadioMaster](https://radiomasterrc.com/products/bandit-nano-expresslrs-rf-module) · [GetFPV](https://www.getfpv.com/radiomaster-bandit-nano-915mhz-expresslrs-rf-module.html) |
| 21 | **BetaFPV ELRS Nano 915 RX** (0.7 g) | ~17 est. | [BetaFPV](https://betafpv.com/products/elrs-nano-receiver) · [GetFPV](https://www.getfpv.com/betafpv-expresslrs-nano-915mhz-receiver.html) · alt [HappyModel ES900RX](https://www.getfpv.com/happymodel-expresslrs-es900rx-receiver-module.html) (0.6 g) |

⚠️ **Not the Bandit BR1.** It is 915 MHz and it works, but it weighs **2.9 g**
against a 25 g airframe — four times the nano receivers, for range performance
you do not need across a bedroom.

⚠️ Flash **both ends** to the same ExpressLRS major version and the same
regulatory domain (**FCC915**), with one binding phrase. Version mismatch is the
most common ELRS failure and it simply will not bind.

### Band-pass alternatives, if you want more margin

| part | passband (3 dB) | loss | rejection | $ | note |
|---|---|---|---|---|---|
| **GPIO Labs 2450 ISM** | 2380–2500 | 2.7 dB | >40 dB | **29.10** | the one to buy. SMA-F both ends |
| [Mini-Circuits ZFBP-2400-S+](https://www.minicircuits.com/WebStore/dashboard.html?model=ZFBP-2400-S%2B) | 2300–2500 | 2.2 dB | 50 dB | 49.95 | more margin and 0.5 dB less loss, in a shielded case. Worth it only if you find the cheap one is tilting the sweep |
| ~~Mini-Circuits VBF-2435+~~ | 2340–2530 | — | — | 57.50 | **not a drop-in.** It is a surface-mount LTCC chip, not a connectorised part — you would have to build a carrier board with SMA launches |

The filter sits **in front of the LNA**, so its insertion loss adds directly to
the system noise figure: 2.7 dB on top of the 4 dB the link budget assumes. That
is irrelevant against 71 dB of margin, and it is the price of not putting every
signal in the room into a 50–4000 MHz amplifier.

**You can measure your own filter without a VNA.** Park the ADF4351 at a series
of CW frequencies (`CW 2380`, `CW 2400`, … `CW 2500`) and watch the TX→RX
leakage level in `radar_acquire.py`. The leakage is flat with frequency, so what
you are plotting is the filter's response. If the bottom of the sweep is more
than a couple of dB down, raise `SET f0_mhz` until it is not.

## F. Stage 2 — azimuth (order later)

Second mixer, second splitter, second band-pass, second LNA (already in the
4-pack), second TL072 channel. Same links as rows 1, 4, 7b, 3, 15.

## G. Test gear

**Buy none of it.** A NanoVNA-H4 stops at 1.5 GHz and cannot see a 2.44 GHz
antenna. The horn is tuned against detection SNR instead — see
[`../docs/radar-software.md`](../docs/radar-software.md) § 8.

---

## Revised totals

| | originally priced | with prices checked Sept 2026, less what is owned |
|---|---|---|
| stage 1 order | 394 | **284** (interface and 12 V supply owned) |
| stage 2 order | 70 | 213 (74 + the UMC404HD stage 2 forces) |
| 915 MHz link | — | 122 |
| parts | 464 | **497** |
| **delivered, indoor build, stage 1 only** | — | **~430** |

Dropping the SMA adapter assortment and the turntable takes it to **~$630**.
Using the $25 generic mixer instead of the ZX05 is already assumed in these
numbers; the ZX05 build is about $54 more per receive channel.

## Order in this sequence

1. **The mixer** — longest lead, tightest stock, and nothing else works without it.
2. **Everything else RF** (rows 2–7b) in one order, so the cables match.
3. **Copper and the interface** — these are what you build while the RF ships.
4. **The 915 link** — only if you are flying indoors. Outdoors, skip § E and fly
   from the phone on a 40 MHz sweep.
5. **Stage 2** — after stage 1 sees a corner reflector at a tape-measured range.
