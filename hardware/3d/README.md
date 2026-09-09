# hardware/3d — the bench model

`radar-bench.html` is a self-contained Three.js page (open it in a browser;
it loads three.js r128 from cdnjs). It shows every row of `hardware/BOM.md`
as an object on a plywood bench, the 830-point breadboard wired hole by hole,
the two build stages and the optional turntable, and the drone 3 m out in the room.

- Buttons: stage 1 / 2, the optional turntable, Bench / Breadboard / Room views, labels, coax, wiring.
- The BOM panel on the right: click a row → the camera flies to the part and
  it pulses; hover any object for its name; click an object → its BOM row.
- Rows marked *consumable* / *tool* (solder, flux, snips) are listed but not
  modelled. The copper sheet **is** the horns; the SMA flange (B9) and the
  brass probe (B10) are separately clickable on every horn.
## The RF chain

Laid out in two rows, as in `radar-hardware.md` §3 — transmit (ADF4351 → pad →
PA → splitter) across the back, receive (band-pass → LNA → mixer) in front of
it — with every SMA on one centre-line, so each coax jumper leaves both
connectors along its own axis. Each horn is gripped by a saddle clamp on the
**waveguide**, well behind the flare, standing on the frame's cross beam, with
the beam's top face flush to the guide's underside. Every horn feed hands over
near the rotation axis, so the cabling stays attached if the optional turntable
turns the frame.

## Wiring you can follow

Every pin a wire lands on is a real object with a name, a landing point and a
direction, so a lead leaves its connector along that connector's own axis and
arrives at the far one the same way — it looks plugged in rather than passing
nearby. From there it drops to a cable run a few millimetres above the plywood
and stays there, routing through the corridors between modules instead of
flying over them. Parallel leads are fanned apart so a loom reads as ten wires,
not one rope. Coax is SMA with visible nuts and boots; the breadboard harness is
hook-up wire in the colours `WIRING.md` calls out.

The things a wire has to plug into are modelled too: header sockets under the
ESP32 and A4988 (which is what lifts their pins clear of the board), a 4-pin
JST on the stepper, a DC barrel jack and plug on the supply, RCA jacks on the
UCA202, combo jacks on the UMC404HD, and a USB-A socket on the laptop.

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

The model is one **three-horn frame** (`radar-hardware.md` §7), not three
different rigs. All three horns are rolled 90° so the 193.1 mm side is
horizontal; TX sits centred 290 mm above the receive row, which keeps the
leakage path equal into both receivers.

| button | what the model shows |
|---|---|
| 1 · TX + RX A | the frame with two horns fitted and the RX B position built and left empty — range and radial velocity |
| 2 · + RX B → azimuth | RX B and its receive chain added (band-pass 2 → LNA 2 → mixer 2 into the UMC404HD) — azimuth from phase in one dwell |
| Turntable | optional at either stage. The motor stands on the board shaft **up**, four standoffs carry the bearing fixed race at shaft height, and a printed hub clamps the D-shaft to the frame base plate — direct 1:1, which is what `STEPS_PER_DEG 8.889` assumes. With it off, the frame sits on a fixed pedestal |

The roll is what makes the baseline legal, per
[`../../docs/azimuth.md`](../../docs/azimuth.md): side by side *unrolled* the
phase centres would be 263.8 mm apart, past the 209 mm ambiguity limit, and the
bearing would wrap at ±13.4° — inside the 17° half-beam. Rolled, the horns
touch at 193 mm and stay unambiguous to ±18.4°.

Both receive runs leave their feeds the same way and take the same path to the
board, because 1 mm of extra coax on one channel is 4.3° of phase and about
0.3° of bearing error.

Screenshots: `radar-bench-bench.png`, `radar-bench-breadboard.png`,
`radar-bench-stage2.png`, `radar-bench-room.png`.

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
