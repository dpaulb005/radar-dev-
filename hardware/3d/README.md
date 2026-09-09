# hardware/3d — the bench model

`radar-bench.html` is a self-contained Three.js page (open it in a browser;
it loads three.js r128 from cdnjs). It shows every row of `hardware/BOM.md`
as an object on a plywood bench, the 830-point breadboard wired hole by hole,
the three build stages, and the drone 3 m out in the room.

- Buttons: stage 1 / 2 / 3, Bench / Breadboard / Room views, labels, coax, wiring.
- The BOM panel on the right: click a row → the camera flies to the part and
  it pulses; hover any object for its name; click an object → its BOM row.
- Rows marked *consumable* / *tool* (solder, flux, snips) are listed but not
  modelled. The copper sheet **is** the horns; the SMA flange (B9) and the
  brass probe (B10) are separately clickable on every horn.

## The RF chain

Laid out in two rows, as in `radar-hardware.md` §3 — transmit (ADF4351 → pad →
PA → splitter) across the back, receive (band-pass → LNA → mixer) in front of
it — with every SMA on one centre-line, so each coax jumper leaves both
connectors along its own axis. Each horn is carried by a mast that grips the
**waveguide** in a saddle clamp, well behind the flare; the mast top sits
flush with the guide's underside. In stages 2–3 the horn feeds hand over to
the turntable through a service loop at the rotation axis, so the cabling
stays attached as the yoke sweeps.

## The breadboard is the real one

Every part sits in the holes `hardware/breadboard/WIRING.md` gives it, and all
48 jumper wires are drawn between their stated holes in their stated colours —
so hovering `R16 33` or a jumper names the actual holes it occupies. Rails are
`TR+` V5 / `TR-` GND / `BR+` VANA / `BR-` GND, as in that file.

The modules carry their real pinouts from `hardware/breadboard/MODULES.md`, and
the harness is drawn pin to pin, not approximated: ESP32 `D18`→J9.2 SCK,
`D23`→J9.3 MOSI, `D5`→J9.4 LE, `D19`→J9.5 LD, `D25`→J9.6 SYNC, `D26/D27/D14`→
STEP/DIR/EN, A4988 `STEP/DIR/ENABLE/VDD/GND`→J11, its `1A/1B/2A/2B` out to the
NEMA-17 coils and `VMOT` straight off the terminal block, ADF4351
`CLK/DATA/LE/LD/CE`→J10 and `VCC/GND`→J6, and J2/J12 out to the UCA202's two
RCA inputs. Hover any pin for its net.

## Stages

| stage | what the model shows |
|---|---|
| 1 | fixed horn pair, 290 mm centres, on two masts |
| 2 | the pair on the turntable — the stepper, the lazy susan, the yoke |
| 3 | **azimuth interferometer**: all three horns rolled 90° so the 193.1 mm side is horizontal, two receivers touching at a 193 mm baseline, and the second receive chain (band-pass 2 → LNA 2 → mixer 2) feeding the UMC404HD |

Stage 3 follows [`../../docs/azimuth.md`](../../docs/azimuth.md): side by side
*unrolled* the phase centres would be 263.8 mm apart, past the 209 mm ambiguity
limit, so the roll is what makes the baseline legal.

Screenshots: `radar-bench-bench.png`, `radar-bench-breadboard.png`,
`radar-bench-stage3.png`, `radar-bench-room.png`.

The electrical reference is `hardware/kicad/radar_breadboard.kicad_sch`; the
printable build sheet, with the same holes, is `hardware/breadboard/`.

## Verifying it

The model hard-codes the breadboard placement, the module pinouts and the BOM
totals, all of which live in markdown files that change on their own. Rather
than trust that, re-derive it:

```bash
cd hardware/3d
python verify_model.py            # data checks, about a second
python verify_model.py --render   # also loads the page in headless Chrome
                                  # and fails on any JavaScript error
```

198 checks: every part and all 48 jumpers against `WIRING.md` (same refs, same
holes, same pin order, same wire colours), every connector pin's net against
its "Nets as built" table, the ESP32 / A4988 / ADF4351 pinouts against
`MODULES.md`, every `pinAt()` in the harness against the pins that actually
exist, and the panel's stage totals against `BOM.md`. It exits non-zero and
names the offending hole, pin or figure. Run it after editing the model **or**
after editing any of those three documents — a change to either side fails it.
