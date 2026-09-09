# The antenna

This is the part of the 24 GHz build that is the point of the project. It is
also the part where the design work is *larger* than the horn's, not smaller.

The 2.4 GHz horn has four numbers — aperture, throat, flare, probe depth — and
you get them right with a ruler and a file. This has the substrate, the element
dimensions, the feed topology, the impedance transformation, the element
spacing, the column count, the interferometer baseline and the etch tolerance,
and once the board is ordered none of them can be filed.

Every number below comes from [`antenna/patch24.py`](../../antenna/patch24.py),
which implements the cavity and two-slot models from Balanis ch. 14 and carries
42 assertions. Run `python3 antenna/patch24.py` to reproduce it and
`--selftest` to check it.

---

## Why patches, and why columns

At 24 GHz a 13.4 dBi pyramidal horn is 27 × 20 mm. You cannot fold that from
sheet copper, and you certainly cannot tune a probe inside it. So the antenna
becomes printed — and printing opens a geometry the horn cannot have.

A single patch radiates about 6.5 dBi into a pattern roughly 81° wide in the
plane of its width and rather broader along its length. Stack four of them
along the length and the array factor narrows *that* plane and leaves the other
alone:

```
        ELEVATION                          AZIMUTH
        narrowed by the array              left as the single patch

          ____                                 \      |      /
         |    |  patch 1                         \    |    /
          ____                                    \   |   /
         |    |  patch 2      23.2°                \  |  /      80.7°
          ____                                      \ | /
         |    |  patch 3                             \|/
          ____                                     --------
         |    |  patch 4
```

That is exactly the right way round for this radar:

- **elevation 23.2°** covers ±2.0 m of height at 10 m. A drone flying at 3–10 m
  indoors stays in it, and narrowing elevation is free gain.
- **azimuth 80.7°** is the sector you want to search, and you search it by
  *measuring* the bearing, not by pointing.

The horn cannot do this. Its E- and H-plane beamwidths are both set by one
aperture, so narrowing one narrows the other and every degree of azimuth beam
you give up is a degree you then have to scan across.

---

## The element

`RO4350B, εr 3.66, h 0.254 mm, tan δ 0.0037`

```
      free-space lambda          12.427 mm
      guide wavelength            6.804 mm
      patch W x L                 4.070 x 3.163 mm
      effective er                3.336
      edge resistance               419 ohm
      inset for 50 ohm            0.949 mm
      50 ohm trace width          0.556 mm
      feed loss                  0.0308 dB/mm (dielectric 0.0143, conductor 0.0165)
```

```
                 W = 4.070 mm
        <------------------------>
        +------------------------+     ^
        |                        |     |
        |      ____________      |     |
        |     |            |     |     |  L = 3.163 mm
        |     |  inset     |     |     |
        +-----+  0.949 mm  +-----+     v
              |            |
              |  0.556 mm wide, 50 Ω
              |
```

The radiating edge of a patch this size looks like **419 Ω**, so it cannot be
fed at the edge. Cutting the feed 0.949 mm into the patch drops the resistance
as cos⁴ along the length and lands it on 50 Ω. That is one number that has to
be right in the Gerbers, because it cannot be adjusted afterwards.

**Substrate choice is not a preference, it is a loss budget.** The same feed
line on FR-4:

| | RO4350B | FR-4 |
|---|---|---|
| feed attenuation | **0.031 dB/mm** | 0.130 dB/mm |
| of which dielectric | 0.014 | **0.106** |
| loss over a 24 mm column feed | **0.75 dB** | 2.95 dB |
| realized column gain | **11.8 dBi** | 9.6 dBi |

FR-4 costs 2.2 dB per antenna, so 4.4 dB two-way, and 85 % of that is the
dielectric — it is the material, not the copper, and no layout fixes it. It is
still the right material for the *first* board, for a reason that has nothing
to do with loss. See § the panel.

---

## The column

Series-fed comb line: one microstrip line with four patches tapped off it,
spaced **one guide wavelength (6.804 mm)** so every element is driven in phase.

```
      realized gain              11.8 dBi (after 0.75 dB of feed)
      elevation beamwidth        23.2 deg
      azimuth beamwidth          80.7 deg   (single patch; the column does not narrow it)
      series-feed squint         0.54 deg at the band edge
```

Series feed is the compact choice and its usual objection is **beam squint** —
the element phasing is set by the guide wavelength, which moves with frequency,
so the beam tilts across the sweep. Here the sweep is 250 MHz on 24.125 GHz,
about 1 %, and the squint works out at **0.54° at the band edge**. Against a
23° elevation beam that is nothing, and it is in elevation anyway, where this
radar makes no measurement.

A corporate (branching) feed would remove the squint entirely at the cost of
more copper, more loss and a harder layout between elements only 6.8 mm apart.
Not worth it at 1 % bandwidth.

---

## The interferometer, which is the reason for all of it

```
      interferometer: RX centres 6.213 mm apart (2.14 mm copper gap)
        unambiguous            +/-90.0 deg  -> covers the whole 81 deg azimuth pattern: YES
        phase -> bearing       0.318 deg per deg
        etch tolerance         52.9 deg/mm of trace -> 50 um mismatch = 0.84 deg of bearing
      board, antennas only     51.6 x 31.6 mm (TX kept 3 lambda from the RX pair)
```

The two receive columns sit **λ/2 apart**, and at λ/2 the phase difference
reaches ±π exactly at ±90°. There is no ambiguity anywhere the antenna can see.
Compare:

| | 2.4 GHz, built | 24 GHz |
|---|---|---|
| baseline | 193.1 mm | **6.213 mm** |
| baseline in wavelengths | 1.58 λ | **0.50 λ** |
| unambiguous cone | ±18.4° | **±90°** |
| azimuth beamwidth | 34° | 81° |
| cone covers the beam? | just barely | **completely** |
| bearing per degree of phase | 0.100° | 0.318° |
| what sets the phase error | 4.25°/mm of **coax**, budget gone at 6 mm | 52.9°/mm of **etch**, fixed at fab |

Two things in that table pull in opposite directions and both matter.

**The good one.** At 2.4 GHz the two receive channels are two lengths of RG316,
and a 1 mm difference is 0.43° of bearing — the whole 2.5° budget is spent by
6 mm, and it drifts with temperature, and it changes every time something is
unplugged ([`../azimuth.md`](../azimuth.md)). Here there are **no cables**.
Both paths are etched in one process step on one substrate; a 50 µm etch
mismatch is 0.84° of bearing, it does not drift with what you plug in, and the
boresight calibration you already wrote removes the fixed part once.

**The bad one.** A shorter baseline is a *less* sensitive interferometer:
0.318° of bearing per degree of phase against 0.100°. Three times more of any
phase error you fail to remove ends up in the bearing. Thermal noise is not the
problem — the floor is 0.23° rms at 10 m, eleven times inside the budget — but
it does mean the calibration has to be done, not skipped.

The transmit column is kept **3 λ = 37.3 mm** from the receive pair. The MMIC's
own TX→RX isolation is above 40 dB and FMCW leakage lands in the DC range bin
anyway, so this is margin rather than a requirement.

---

## The one thing the datasheet cannot promise

```
RO4350B:
  patch bandwidth          1.97 % = 475 MHz (the ISM band is 250 MHz wide)
  substrate tolerance      er 3.66 +/- 0.05
    er  3.61 -> resonates at 24.281 GHz (+156 MHz)
    er  3.71 -> resonates at 23.972 GHz (-153 MHz)
  worst shift 156 MHz + half the band 125 MHz = 281 MHz needed, 238 MHz available
  -> MISSES part of the band (-44 MHz of margin)

FR-4:
  patch bandwidth          1.40 % = 339 MHz
  substrate tolerance      er 4.3 +/- 0.2
    er  4.10 -> resonates at 24.675 GHz (+550 MHz)
    er  4.50 -> resonates at 23.611 GHz (-514 MHz)
  worst shift 550 MHz + half the band 125 MHz = 675 MHz needed, 169 MHz available
  -> MISSES part of the band (-506 MHz of margin)
```

A patch is a resonator about 2 % wide. The ISM band is 1 % wide. That should be
comfortable, and it is not, because the resonance moves with the substrate's
permittivity and the permittivity is a tolerance, not a number.

- **RO4350B misses by 44 MHz** in the worst corner. That is recoverable: it is
  a corner, not a typical, and a measured length correction removes it.
- **FR-4 misses by 506 MHz.** Not recoverable. On FR-4 you cannot know where
  the patch will resonate to better than ±0.6 GHz before you measure one.

This is not an argument against FR-4. It is the argument for measuring first.

---

## The panel

```
  prototype panel: 7 patches, L stepped by 40 um
   variant    L (mm)    resonates near
         A     2.824         25.150 GHz
         B     2.864         24.799 GHz
         C     2.904         24.457 GHz
         D     2.944         24.125 GHz
         E     2.984         23.802 GHz
         F     3.024         23.487 GHz
         G     3.064         23.180 GHz
```

One cheap FR-4 board carrying seven patches whose lengths differ by 40 µm.
Between them they resonate from 23.18 to 25.15 GHz, so whatever the panel's
actual εr turns out to be, **one of them lands in the band** and tells you the
correction to apply.

Measure them, keep the length that resonates at 24.125, scale it to the Rogers
stack-up, and order the real board. That is one $5 iteration instead of one
$300 one, and it converts the −506 MHz of FR-4 uncertainty into a measured
constant.

Measuring seven patches at 24 GHz is not free either — see
[`README.md`](README.md) § what is still open. If no VNA can be borrowed, the
fallback is the same one the horn's probe depth used: put the panel in front of
a known reflector at a known range and compare detection SNR between variants.
It is cruder, it is a relative measurement, and for picking the best of seven
that is all it has to be.

---

## What is not designed yet

- **The ground plane and the stack-up.** Two layers, 0.254 mm core, copper
  pour under everything. Whether the return path under the RX feeds needs
  stitching vias at 24 GHz, and at what pitch, is a layout question this
  document does not answer.
- **Mutual coupling** between the two receive columns at a 2.14 mm gap. It is
  the assumption most likely to be wrong and the cheapest to check in a
  simulator before ordering anything.
- **The MMIC launch.** Getting from an eWLB ball to a 0.556 mm microstrip
  without a discontinuity is its own small design problem, and Infineon's
  application notes are the reference for it.
- **A simulation.** openEMS or Sonnet, before the Gerbers go out. The
  2.4 GHz Vivaldi tool ([`antenna/vivaldi.py`](../../antenna/vivaldi.py))
  already emits an openEMS script; this one does not, and should.
