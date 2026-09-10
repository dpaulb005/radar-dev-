# What this project is for

> **Build a radar where I design the antenna, and get azimuth on a small drone.**

Everything else is negotiable. That sentence is not, and this document exists
because several decisions only became obvious once it was written down — and
one recommendation in this repo had to be withdrawn because it quietly
contradicted it.

Three tests. A change is good if it passes all three.

| test | means |
|---|---|
| **Is the antenna mine?** | I cut, tune and characterise it. Not a patch array someone else laid out, and certainly not one baked into a chip package. |
| **Does it give azimuth on a drone that is flying?** | Not a hovering one. Bearing has to survive the target moving. |
| **Is the target a small drone?** | 25 g quadcopter, 3–10 m, indoors, carrying nothing and cooperating with nothing. |

---

## The decisions so far, judged against it

### Azimuth by scanning — dropped

The turntable stepped through nine beam positions and took an
amplitude-weighted centroid across them. Measured, that gives 1.5° rms in
4.3 seconds — but only on a target that is nearly stationary, because the
centroid assumes every beam saw the drone at one bearing. At 10 m with a 2.5°
budget, a 4.3 s scan needs the drone slower than **0.10 m/s**.

Fails test 2. Dropped. The evidence is in
[`signal-chain.md`](signal-chain.md) § stage 10, including the measurement
that spending the same scan time on a longer dwell beats more beams tenfold,
and that neither survives a flying target.

### Azimuth by interferometry — adopted

Two receive horns 193 mm apart, bearing from the phase between them, inside one
0.47 s dwell with nothing moving. **0.18° rms, 0.29° worst**, 8 times inside
the budget and nine times faster than the scan.

Passes all three tests, and it is the reason the project has a stage 2 at all.
Built, tested, and running: [`azimuth.md`](azimuth.md),
`ground_station/interferometer.py`, 34 cases in `ground_station/test_radar.py`.

### Elevation and 3-D — dropped

One baseline measures one angle. Putting it horizontal spends it on azimuth,
which is what test 2 asks for. Range, azimuth and radial velocity is a 2-D track
on the floor, which is what the console already draws.

### The turntable — demoted to optional

It was mandatory when bearing came from scanning. It now points the frame at a
sector wider than the 34° beam and takes no part in any measurement. Most
indoor flying at 3–10 m fits in one beam, so it is the first thing to cut.

### Sharing the band with the drone's own WiFi — kept, then reversed

The drone flew from a phone over its own access point on channel 1, so the
radar swept 2440–2480 MHz above it. That halved the bandwidth, doubled the
range cell to 3.75 m and pushed the target from 5.3 FFT bins from DC to 2.7 —
and *that* is what made the old scanning azimuth noisy in the first place.

It was kept for a long time, because the interferometer does not care: it reads
phase, not amplitude across beams, and 0.18° has margin to burn.

**Then a real room was measured, and it does not survive that.** A 2.87 × 4.17 m
bedroom is **1.1 range cells deep** at 40 MHz, so range cannot separate the
drone from the wall behind it at all. Measured, in that room: at 2 m the 40 MHz
sweep is 0.54 m out, and inside 1.5 m it finds nothing. At 83.5 MHz the same
target reads to 0.02 m and works from 1.0 m.

So the link moved to **915 MHz ELRS** and the radar took the whole band —
2400–2483.5 MHz, a **1.80 m** cell. It costs about $130 and a firmware change
(esp-fc instead of ESP-Drone; sticks instead of a phone), documented in
[`drone-link.md`](drone-link.md).

**Judged against the three tests, this changes nothing** — the antenna is still
mine, the azimuth method is unchanged, the target is still a stock 25 g drone
carrying nothing. It is a pure win bought with money, which is why it took a
measurement rather than an argument to justify it. In a garage or a garden the
old 40 MHz sweep is still perfectly good, and the phone build is kept in
[`drone-software.md`](drone-software.md) § 6 for exactly that.

### The horn — the whole point

263.8 × 193.1 mm aperture, WR-340 throat, 91.5 mm flare, probe 43.7 mm from the
back wall. Cut, soldered, tuned and characterised by you, three of them,
rotated 90° so the receive pair sits at an unambiguous 193 mm baseline. This is
test 1, and no other part of the project touches it.

---

## The higher-band question, re-judged

Kevin suggested considering K-band (24 GHz) or V-band (60 GHz): *"electrically
smaller antennas with more narrow beams, less interference potential."*
[`higher-bands.md`](higher-bands.md) costs the options: $60 for a 24 GHz
transceiver module, $283 for a 60 GHz TI board, $1,271 if you want raw data
from the latter.

**I recommended the $60 module. Against this goal that recommendation is
wrong, and I have withdrawn it.**

Every one of those parts ships with its antenna already designed. The RFbeam
module has an integrated patch array with no external port. The TI IWR6843's
antenna is etched on its evaluation board, and the antenna-on-package variant
has it inside the chip. Buying any of them means the most interesting part of
this project — the part that is test 1 — is done by someone else and soldered
shut. The radar would work better and would no longer be the thing you set out
to build.

### Which half of Kevin's argument actually applies

His framing was *"antenna designs more conducive to drone platforms, especially
size and weight."* That is a radar **carried on** a drone. Yours **watches** one
from a bench, where size and weight cost nothing. So:

| Kevin's point | applies here? |
|---|---|
| smaller, lighter antennas | **no** — it sits on plywood |
| narrower beams | yes |
| better range resolution | yes, and it is the weakest number you have |
| less interference | **no longer** — moving the drone's link to 915 MHz already returned the bandwidth the coexistence took, for $130 instead of a new band |

Three of four are real wins. That is worth taking seriously — just not by
buying a sealed module.

### The version that would pass all three tests

Go to 24 GHz and **design the antenna yourself anyway**. At 24 GHz a 13.4 dBi
horn is 27 × 20 mm, too small to fold from sheet copper, but that opens
techniques the 2.4 GHz build cannot use:

- a **patch array etched on ordinary FR-4**, which at 24 GHz is a $5 PCB and
  a genuinely deeper antenna design exercise than a horn — feed networks,
  element spacing, substrate loss,
- a **machined or 3-D-printed horn** at 27 × 20 mm, metallised the same way,
- **λ/2 = 6.2 mm element spacing**, so a fully unambiguous interferometer over
  the whole beam instead of the ±18.4° you have.

That research is now done and it is written up in
[`24ghz/`](24ghz/README.md) — a costed rough draft of the whole thing.

**The premise above is wrong in one important way, and the correction is what
unblocks it.** I wrote that this needs a front end with an *external antenna
port*. It does not. A 24 GHz radar MMIC brings its RF out on **single-ended
50 Ω pins** meant to be soldered to a microstrip trace, and at a 12.4 mm
wavelength that trace runs a few millimetres to an antenna etched on the same
board. There is no port, no connector and no cable — the antenna is part of
the layout you draw. Test 1 passes, and it passes more completely than it does
at 2.4 GHz, where the horn is yours but the rest of the chain is bought modules.

The draft picks Infineon's **BGT24LTR22** ($15.26, two *simultaneous*
quadrature receivers, differential analog IF on pins) with an **ADF4159** ramp
PLL ($20.48), and three printed four-patch columns. The receive columns sit
λ/2 = 6.213 mm apart, which makes the interferometer **unambiguous to ±90°**
instead of ±18.4°, over the entire 81° pattern the antenna can see.

**Order of operations, which is also Kevin's own advice:** finish this radar
first. Everything downstream of the mixer's IF is band-independent — the video
amplifier, the reference, the power, the sound card, the whole DSP, the
interferometer and its tests all survive a change of band. You only get to
write that once, and it is written.

---

## What is still open

- ~~A 24 GHz front end with an external antenna port.~~ **Answered** in
  [`24ghz/`](24ghz/README.md), including the fact that the question itself was
  wrong: these chips have no antenna port because the antenna is on your board.
  What is open there instead is a **PCB and assembly quote**, which is 60–80 %
  of that build's cost and cannot be pinned down until the board is drawn.
- **Switched-mode azimuth on real hardware.** Implemented and tested in
  simulation, never run against a real RF switch.
- **The servo scan on the full band.** Every scan-geometry number in
  [`signal-chain.md`](signal-chain.md) was measured at 40 MHz. At 83.5 MHz the
  scan collapses, because the TX leakage outranks a beam-attenuated target in
  off-boresight beams. Fixing it means gating the leakage inside `centroid()`.
  The interferometer does not have this problem.
- **The calibration constant's drift** with temperature, over a session. Known
  to matter at 0.43° of bearing per mm of cable; never measured.

---

## Using this document

When a change is proposed, run it past the three tests at the top. If it fails
test 1 it is not this project, however much better it performs — that is what
happened to the $60 module. If it fails test 2 it is the old scanning azimuth
wearing a new hat. If it fails test 3 it belongs to a different target.
