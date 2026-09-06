# Review — "Radar carrier V1" design package (external, September 2026)

Package reviewed: `radar-pcb-v1/` (README, `radar_carrier.kicad_pcb`,
`radar_carrier.net`, four net-labelled schematic SVGs, BOM, `build_design.py`,
`verification.json`, `design_review.html`). Produced by another model from
`docs/LLM-DESIGN-PROMPT.md` §2 and the pipeline page.

## Verdict

**Keep it, with four changes before fabrication.** It is not the integrated
RF board §2 asked for and it says so honestly: it is a through-hole
*carrier* — video amplifier, bias, power distribution to the RF modules, and
harness headers for the ESP32, ADF4351 and A4988 — with every 2.4 GHz path
left on SMA cables. For a first board that is the right scope: it replaces
the breadboard, not the coax modules. The netlist reads correctly against
the intended circuit, the gain/filter values match `radar-hardware.md` §5,
and the package's self-imposed caveats (no native KiCad DRC run, no ground
plane, no bench validation) are accurate.

## What it got right that this repo had wrong

The package's "Known system issues" section found four real errors in our
numbers. All are now corrected in the repo:

| claim in the package | check | was | now |
|---|---|---|---|
| beat at 10 m for 43.5 MHz / 6.4 ms is 453 Hz, not 401 | 2·B·R/(c·T) = 453 Hz — the 401 figure came from an earlier 38.5 MHz sweep | 401 Hz | 417 Hz for the 40 MHz sweep now used |
| 9 dwells × 64 chirps × 7.4 ms ≥ 4.26 s, not 1.5 s | arithmetic | "≈ 1.5 s per scan" | 4.3 s; `--n-chirps 32` → 2.1 s; lock-and-dither is the fix |
| the endpoint-inclusive 64-step model has a different slope (~461 Hz) | firmware used Δf = B/(N−1) over N step times → slope B·N/((N−1)·T), a 1.6 % range-scale error | Δf = B/(N−1) | Δf = B/N: slope exactly B/T_up |
| a carrier parked at 2483.5 MHz has no upper-edge allowance | correct; a CW tone's phase noise and spurs sit above the edge | sweep to 2483.5 | sweep top ≤ 2480, enforced in firmware (`ISM_MARGIN_HZ`) |

Two further points it raised are also adopted:

- **Firmware booted straight into a full-band sweep.** It now boots with the
  PLL locked, parked, and the RF output *disabled* (`"sweep":0,"rf":0`);
  `radar_acquire.py` sends `SWEEP 1` on start and `SWEEP 0` on exit; `RFOFF`
  exists.
- **The sound card's input is AC-coupled**, so the sync square wave (86 %
  duty) arrives as a drooping plateau plus a large negative retrace pulse.
  The old level-threshold segmentation would have reported "no sync" on real
  hardware. Segmentation now detects edges in the derivative, and the
  self-test's synthetic source models a 10 Hz coupling high-pass on both
  channels.
- **SPF5189Z is EOL** (Qorvo PCN 21-0060, LTB Sept 2021, replacement
  QPL9547). The Amazon modules are built from remaining stock; the BOM now
  says so and why the 4-pack is bought up front.

## Circuit check (against `radar_carrier.net`)

- IF → R1 49.9 Ω to GND (50 Ω termination for the mixer IF port) → C1 100 n →
  U1A (+), R2 10 k to VREF: 159 Hz high-pass. ✓
- U1A non-inverting, R3 100 k / (R4 1 k + R5 4.02 k): gain 21 with JP1 open,
  101 closed. ✓ The 21 default for first power-up is sensible.
- C2 100 n / R6 10 k second 159 Hz high-pass into U1B; R7 10 k / R8 1 k: gain
  11, JP2 shorts to unity. ✓
- R12 1 k / C9 10 n → 15.9 kHz low-pass referenced to VREF, U2B follower,
  R13 100 Ω, C10 10 µ, R14 100 k bleed → J2. ✓
- VREF = VANA/2 through R9/R10, buffered by U2A, R11 47 Ω isolation into
  C6 47 µ with feedback taken before R11. ✓ (stable driving the capacitor)
- Power: D1 1N5822 series on 12 V in, C11 100 µ, R15 10 Ω / C13 100 µ RC
  into VANA (159 Hz corner, ~0.1 V drop). ✓ Three ferrite-filtered 5 V
  outputs with 10 µ + 100 n each. ✓
- Digital: 33 Ω series on SCK/MOSI/LE, LD pass-through, CE jumper with 10 k
  pull-down, A4988 EN pulled up (motor disabled until firmware acts),
  STEP/DIR pull-downs, SYNC divider 10 k / 1 k → 0.3 V. ✓
- `verification.json`: 73 parts, 164 pads, 37 nets, 0 unrouted, 0 shorts,
  min clearance 0.21 mm. Consistent with the routed preview.

## Change before fabrication

1. **RF stop at the IF input.** Add 1 nF (C0G) from IF to GND beside R1.
   The mixer leaks LO at 2.44 GHz out of its IF port; a TL072 will rectify
   it. 49.9 Ω × 1 nF is a 3 MHz corner — nothing in the audio band notices.
2. **Ground pour.** The board has no ground plane, only routed GND traces,
   on a 60 dB audio gain stage next to a stepper driver harness. Add a GND
   fill on both layers in KiCad (zones, stitched) before ordering. This is
   the package's own top caveat; it costs nothing.
3. **Bandwidth at maximum gain.** TL072 GBW is 3 MHz. Stage A at 101 V/V has
   ~30 kHz bandwidth — fine — but the 1111 V/V jumper setting (101 × 11)
   runs stage A near its limit *and* is 20 dB more gain than the leakage
   budget allows (200 mV × 10 = 2 V → clips). Either delete that setting
   from the table or add a note that it is for no-leakage bench tests only.
4. **Run native KiCad DRC/ERC.** The package parsed the S-expressions but
   never opened them in KiCad. Do that; check the DIP-8 and radial-capacitor
   footprints against the parts actually bought (it flags this itself).

## Nice to have

- A second IF channel (duplicate U1/U2 chain) on the same board would make
  it the stage-3 carrier too. Cheap to add now, awkward later.
- Move the A4988 logic header (J11) and its pull-ups to the far corner from
  J1/U1; on the current layout they share the bottom edge.
- The README's mixer LO note is right: +10.5 dBm into a level-13 mixer is
  ~2.5 dB low. Either drop the 3 dB pad (→ +13.5 dBm both arms) or accept
  ~1 dB extra conversion loss. Decide on the bench with a power meter; the
  carrier is unaffected either way.

## What the package is not

Not the §2 integrated RF PCB (Wilkinson, matched SPF5189Z dies, SMT mixer,
4-layer). That remains a v2 after the coax build is proven — and given the
SPF5189Z EOL, a v2 should be designed around the QPL9547 or another
in-production amplifier rather than a discontinued die.
