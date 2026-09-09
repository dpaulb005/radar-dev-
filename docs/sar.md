# SAR — flying the radar

Everything else in this repo keeps the radar still and watches something move.
This inverts that: **the radar moves, the scene holds still, and the flight path
becomes the antenna.**

That is why it belongs here rather than after azimuth. A synthetic aperture
needs **one transmitter and one receiver** — exactly the stage-1 hardware — and
the cross-range resolution it produces has nothing to do with the 34° horn beam.
Twenty positions along a 2 m path is a twenty-element array you did not have to
build.

```
        drone flies ->   x x x x x x x x x x x x x x x x x x x x
                          \  \  \  |  |  |  /  /  /
                           \  \  \ |  |  | /  /  /       every position
                            \  \  \|  |  |/  /  /        sees the same target
                             \  \ \|  | |/  /  /         at a different range
                              \ \ \|  ||/ /  /
                                  target
                                                  I(x,y) = Σ sₙ(Rₙ)·e^(−j4πfcRₙ/c)
```

Built and tested: [`ground_station/sar.py`](../ground_station/sar.py),
25 assertions in `--selftest`.

---

## What it resolves

The scene is static, so **there is no drone WiFi to coexist with** — nothing is
flying in it that needs channel 1. The sweep can use the whole ISM band:

| | tracking sweep | imaging sweep |
|---|---|---|
| bandwidth | 40 MHz | **100 MHz** (2400–2500) |
| range cell `c/2B` | 3.75 m | **1.50 m** |

Cross-range comes from the path length, and there is a floor the horn sets that
no amount of flying can beat:

```
python3 ground_station/sar.py --aperture 2
```

| range | cross-range, 2 m path | limited by | path for the beam limit |
|---|---|---|---|
| 3 m | **0.10 m** | beam | 1.8 m |
| 5 m | 0.15 m | path | 3.0 m |
| 10 m | 0.31 m | path | 5.9 m |

**The image is deeply anisotropic — 1.50 m along range, 0.10–0.31 m across it.**
Ten to fifteen times sharper sideways than in depth. That is not a defect to fix,
it is what a 100 MHz sweep and a 2 m aperture are; it is worth knowing before you
look at an image and wonder why everything is smeared into radial streaks.

Steps must be under **105 mm** (λ/4 across the beam) or every target gets a ghost
at ±36°.

---

## The hard part is not what I expected

Not resolution. Not payload. **Knowing where the radar was.**

A position error `e` puts `4πe/λ` of phase into that pulse, and the standard
rule of thumb is to keep it under λ/8. Measured against this imaging chain, that
rule is wrong in two ways — both of which matter for a flight plan.

**Which axis you are wrong about matters more than by how much.**

| error, rms | along-track | line-of-sight |
|---|---|---|
| 5 mm | −0.0 dB | −1.0 dB |
| 10 mm | −0.0 dB | −3.2 dB |
| 15 mm (λ/8) | −0.0 dB | **−4.7 dB** |
| 20 mm | −0.1 dB | −5.5 dB |
| 50 mm | **−0.1 dB** | −6.7 dB |

Along-track slip is nearly free, because range changes as `dR/dx = −x/R`, which
is **zero at broadside** — sliding along the path barely changes what you
measure. Line-of-sight error goes into the range one-for-one and straight into
the phase.

So the working figure is about **λ/25 line-of-sight — 5 mm at 2.4 GHz** — and
about 50 mm along-track. λ/8 is not good enough.

### Which inverts the usual advice about bands

| | λ | line-of-sight tolerance |
|---|---|---|
| **2.4 GHz** | 122 mm | **5 mm** |
| 24 GHz | 12.4 mm | 0.5 mm |
| 60 GHz | 4.9 mm | 0.2 mm |

Kevin's argument for K- and V-band was smaller, lighter antennas — which is a
real advantage on a drone, and [`higher-bands.md`](higher-bands.md) still stands
on that. But for a *flying* aperture the low band is by far the easier one:
2.4 GHz asks for 5 mm of navigation where 24 GHz asks for 0.5 mm. RTK GPS lands
at 10–20 mm, which is workable at 2.4 GHz and hopeless at 24.

**This is the first argument in the repo that favours staying at 2.4 GHz.**

---

## Why backprojection, not the algorithm MIT hands out

MIT's SAR lab uses the range-migration algorithm. RMA is faster and it assumes
a straight track sampled at exactly even spacing.

**A drone does not fly a straight line.** Backprojection takes the positions as
*data* — whatever the navigation solution says, in three dimensions, curved and
unevenly spaced — and is exact by construction, with no Stolt interpolation to
get wrong. Measured: a path bowed by 150 mm images perfectly when its shape is
known, and **loses the target by 2 dB and smears it when a processor assumes it
was straight.** For an airborne aperture that is not a preference between two
methods; it is the only one of the two that works.

It costs under a second for these image sizes.

---

## Prove it on a rail first

The processing does not care how the radar moved. Push it along a plank by hand,
stopping at marks measured with a tape, and every number above applies — at
5 mm of tape accuracy, which is the tolerance the flight needs anyway.

A SAR image is the most demanding test of phase coherence there is: it fails
visibly and completely if anything in the chain is wrong. **Get an image off a
rail before anything leaves the ground** — a corner reflector at 6 m should
collapse to a point 0.10 m across.

```bash
python3 ground_station/sar.py --plan --aperture 2   # what a path buys
python3 ground_station/sar.py --selftest            # 25 assertions
```

---

## What is still open

- **The platform.** The 25 g ESP-FLY is the *target* elsewhere in this repo and
  cannot be the vehicle here — two horns, the RF chain, the ESP32, a digitiser
  and power is on the order of 1.5–2.5 kg, which wants a 7-inch class quad or
  larger. Not costed yet.
- **The digitiser.** A UMC404HD is a mains-powered desktop interface. Something
  has to record two channels at 48 kHz in the air, and that part is unchosen.
- **Navigation to 5 mm.** RTK GPS gets to 10–20 mm, which the table above says
  costs 3–5 dB. Closing the rest means autofocus on the data itself
  (phase-gradient autofocus is the standard answer) — unwritten.
- **Motion during a dwell.** Every number here assumes the radar is stationary
  while its 64 chirps are captured. A moving platform smears each dwell, and
  how fast you may fly follows from that. Not yet measured.
