# hardware/3d — the two models

Two self-contained Three.js pages (open either in a browser; each loads
three.js r128 from cdnjs). Between them they draw every row of
`hardware/BOM.md` as a real object.

| page | what it is |
|---|---|
| [`radar-bench.html`](radar-bench.html) | the radar: the three-horn frame, the RF chain, the 830-point breadboard wired hole by hole, the USB interface and laptop, both build stages, the optional turntable, and the room with the drone 3 m out |
| [`drone.html`](drone.html) | the target: a Seeed ESP-FLY with the 915 MHz receiver fitted — every part, every pad, every wire, and what each one weighs |

Both share the same conventions: click a panel row and the camera flies to the
part and it pulses; hover any object for its name; hover a pin or pad for its
net; click an object and its panel row scrolls into view. Rows marked
*consumable* or *tool* are listed but not modelled.

## radar-bench.html

**The RF chain** is laid out in two rows, as in `radar-hardware.md` §3 —
transmit (ADF4351 → pad → PA → splitter) across the back, receive (band-pass →
LNA → mixer) in front of it — with every SMA on one centre-line, so each coax
jumper leaves both connectors along its own axis. Each horn is gripped by a
saddle clamp on the **waveguide**, well behind the flare, standing on the
frame's cross beam. Every horn feed hands over near the rotation axis, so the
cabling survives the optional turntable turning.

**Wiring you can follow.** Cable routing is done the way harness routing is
normally done: each lead is a polyline of straight runs with a filleted arc at
every bend. A spline through the same waypoints overshoots at each direction
change — exactly what throws a cable past its corner and through whatever is
behind it — so one is not used. Each lead then:

1. leaves its connector along that connector's own axis, so it looks plugged in;
2. turns sideways first if the pin points up or down, so it never doubles back;
3. drops to a cable run a few millimetres above the plywood and follows a lane
   between the modules — never over or through one;
4. climbs at the near edge of the breadboard and comes in over the top, because
   dropping to run height at a header would put the wire inside the board;
5. turns 90° at most, and never sharper.

Where two leads must cross, the crossing is *earned*: lanes are ordered so that
the only crossings left are the ones the two pin orders force. Five remain, all
inside a single connector's own fan. The ten ESP32 jumpers are drawn as what
they are — Dupont jumpers arched over the gap — because the devkit's pin order
is the reverse of J9's and no lane assignment can undo that.

Everything a lead plugs into is modelled: header sockets under the ESP32 and
A4988 (which is what lifts their pins clear of the plywood), a 4-pin JST on the
stepper, a DC barrel jack and plug plus a mains inlet on the supply, the RCA
line inputs on the stage-1 mixer, the UMC404HD's four front combo jacks with
¼" TS plugs seated in them, and three USB-A sockets on the laptop. The ESP32 and
the interface are both corded to the laptop — without those the bench has no
power and no serial.

**The interface changes with the stage, and so do its leads.** Stage 1 records
two channels, beat and sync, so the model fits the two-input mixer already on
the shelf, a Xenyx 302USB, with RCA phono leads into its stereo line channel.
Stage 2 needs four channels on one sample clock, so the mixer comes off the desk
and a UMC404HD takes its place on ¼" TS plugs. Because each stage has its own
interface and its own audio leads, the geometry self-test walks **both** stages
rather than the one on screen — which is how it caught the second splitter
sitting in the middle of the ADF4351's logic loom, a fault that had been in the
layout since stage 2 was drawn.

**The breadboard is the real one.** Every part sits in the holes
`hardware/breadboard/WIRING.md` gives it, and all 48 jumpers are drawn between
their stated holes in their stated colours, so hovering `R16 33` or a jumper
names the actual holes it occupies. Rails are `TR+` V5 / `TR-` GND / `BR+`
VANA / `BR-` GND, as in that file. The modules carry their real pinouts from
`hardware/breadboard/MODULES.md`, and the harness is drawn pin to pin:
ESP32 `D18`→J9.2 SCK, `D23`→J9.3 MOSI, `D5`→J9.4 LE, `D19`→J9.5 LD,
`D25`→J9.6 SYNC, `D26/D27/D14`→STEP/DIR/EN, A4988 `STEP/DIR/ENABLE/VDD/GND`→J11
with `1A/1B/2A/2B` out to the NEMA-17 and `VMOT` off the terminal block,
ADF4351 `CLK/DATA/LE/LD/CE`→J10 and `VCC/GND`→J6, and J2/J12 out to INPUT 1 and
INPUT 3 of the UMC404HD.

**Stages.** One **three-horn frame** (`radar-hardware.md` §7), not three rigs.
All three horns are rolled 90° so the 193.1 mm side is horizontal; TX sits
centred 290 mm above the receive row, which keeps the leakage path equal into
both receivers. There is no base plate under the frame and no pedestal: each
mast and each diagonal brace stands on its own foot, bolted through the plywood,
which puts the horn row the 300 mm above the board the hardware doc asks for and
leaves the whole RF chain in plain sight. The base plate exists only with the
turntable fitted, because then the frame has to bolt to something that turns.

| button | what the model shows |
|---|---|
| 1 · TX + RX A | two horns fitted, the RX B position built and left empty — range and radial velocity |
| 2 · + RX B → azimuth | RX B and its chain added (band-pass 2 → LNA 2 → mixer 2), and the UMC404HD replacing the 2-in mixer — azimuth from phase in one dwell |
| Turntable | optional at either stage: motor on the board shaft **up**, four standoffs carrying the bearing's fixed race at shaft height, a printed hub clamping the D-shaft to the frame — direct 1:1, which is what `STEPS_PER_DEG 8.889` assumes |

The roll is what makes the baseline legal, per
[`../../docs/radar-hardware.md`](../../docs/radar-hardware.md) § 7: side by side *unrolled* the
phase centres would be 263.8 mm apart, past the 209 mm ambiguity limit, and the
bearing would wrap at ±13.4° — inside the 17° half-beam. Rolled, the horns
touch at 193 mm and stay unambiguous to ±18.4°. Both receive runs leave their
feeds the same way and take the same path to the board, because 1 mm of extra
coax on one channel is 4.3° of phase and about 0.3° of bearing error.

## drone.html

The target, drawn from Seeed's photographs of the kit rather than from the
summary in the spec sheet — because "46 × 46 × 29 mm, closed body" describes a
box, and the ESP-FLY is not one. It is an **X**: a 24 mm centre plate, four
two-prong arms out to four cylindrical **motor pods** at 37 mm pitch, a bumper
ring joining the pods, four **landing legs** bent from 25 mm of solid-core
jumper wire, and a small printed **canopy** with the engraved ESP FLY cover over
the electronics. The 46 mm the kit quotes is pod edge to pod edge. The 1S pack
hangs underneath in a zip-tie strap.

The stack is what makes the kit's two heights come out right: the pack's back
at 10.5 mm, the plate at 12, the can's top at **29 mm**, the blade plane at
**31**. Inside the canopy, the flight-controller board stands on 2.5 mm
standoffs and the XIAO plugs onto headers above it, USB-C looking out of the
window in the nose.

The one part that is not in the kit is the **915 MHz receiver**: 0.7 g, taped
flat to the canopy's left flank — there is no room on a 22 mm cover and none
inside — with its four wires running aft and in through the canopy's loom slot
to the FC's receiver pads, and 80 mm of antenna streaming straight back down the
centreline, the one line behind the drone that no propeller disc can reach.
Which pad is which, and why the receiver runs on 3V3 and not 5 V, is in
[`../../docs/drone-hardware.md`](../../docs/drone-hardware.md) §§ 2–3.

Buttons: Overview / Top / Underside / Receiver, Exploded, Frame (hides the
X-frame, canopy and cover so the wiring shows), Props, Labels, Spin.

## Screenshots

`render.py` regenerates all of them; each is a URL the page understands, so the
picture and the model can never drift apart.

```bash
cd hardware/3d
python render.py                  # both models
python render.py drone            # one of them
```

| file | URL |
|---|---|
| `radar-bench-bench.png` | `?view=bench&stage=1` |
| `radar-bench-breadboard.png` | `?view=bb&stage=1` |
| `radar-bench-stage2.png` | `?view=bench&stage=2` |
| `radar-bench-room.png` | `?view=room&stage=2` |
| `radar-bench-plan.png` | `?view=top&stage=1&labels=0` |
| `radar-bench-desk.png` | `?view=desk&stage=1&labels=0` |
| `drone-overview.png` | `?view=over` |
| `drone-top.png` | `?view=top` |
| `drone-exploded.png` | `?view=over&explode=1` |
| `drone-receiver.png` | `?view=rx` |
| `drone-underside.png` | `?view=under` |

The bench page also takes `&turntable=1`, `&labels=0`, `&coax=0`, `&wires=0`;
the drone page takes `&explode=1`, `&labels=0`, `&frame=0`, `&props=0`.

## Verifying them

Both models hard-code numbers that live in markdown files which change on their
own. Rather than trust that, re-derive it:

```bash
cd hardware/3d
python verify_model.py            # the bench: data checks, about a second
python verify_model.py --render   # also loads the page in headless Chrome
python verify_drone.py            # the drone, against docs/ and BOM.md
python verify_drone.py --render
```

`verify_model.py` — 242 checks: every part and all 48 jumpers against
`WIRING.md` (same refs, same holes, same pin order, same wire colours), every
connector pin's net against its "Nets as built" table, the ESP32 / A4988 /
ADF4351 pinouts against `MODULES.md`, every wire against the pins that actually
exist, the horn frame's geometry against `radar-hardware.md`, and the panel's
rows and stage totals against `BOM.md`.

`verify_drone.py` — 101 checks: every XIAO pad's GPIO and job against
`drone-hardware.md` § 3, the receiver's TX→GPIO9 / RX→GPIO8 / 3V3 against
§ 2 of the same file, the Betaflight motor order and the props-in pattern, the
airframe's parts and its 24 / 37 / 46 / 29 / 31 mm against
`drone-hardware.md`, the drone rows of `BOM.md` §E, that `radar-bench.html`'s
drone says the same thing, and that the mass roll-up lands on Seeed's 18 g and
25 g.

`--render` additionally loads the page and runs its own geometry self-test over
the real scene graph:

- **the bench**: no lead may pass through a part it is not connected to, and no
  bend may exceed 95°. It samples every cable curve against every module's
  bounding box, because sixty cables cannot be eyeballed;
- **the drone**: props cannot overlap, the analytic envelope must be the kit's
  67 × 67 × 31 mm, the antenna must stay outside every prop disc and be 80 mm
  long, every wire end must land within 1.2 mm of a real pad, no lead may pass
  through a motor can or the pack or the module shield, the receiver must be
  wired to GPIO9/GPIO8, and the masses must add up.

Each prints `GEOM OK`, or names the wire, the part it hits and the coordinate.
Both exit non-zero and name the offending hole, pin, figure or wire. Run them
after editing a model **or** after editing any document they read — a change to
either side fails them.

`_headless.py` holds the shared Chromium plumbing, including the one sandbox
workaround: where outbound HTTPS goes through a proxy Chromium does not trust,
three.js is fetched once and substituted as a `file://` URL into a temporary
copy of the page. The committed pages stay CDN-based for a normal browser.

The electrical reference is `hardware/kicad/radar_breadboard.kicad_sch`; the
printable build sheet, with the same holes, is `hardware/breadboard/`.
