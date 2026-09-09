# Getting azimuth

Scanning the horns cannot give the bearing of a drone that is flying. The
centroid assumes every beam saw the target at one bearing, so the whole scan has
to finish before the bearing moves, and at 10 m with a 2.5° budget that caps a
4.3 s scan at a target speed of 0.10 m/s. Details and the measurement are in
[`signal-chain.md`](signal-chain.md) § stage 10.

The fix is to stop measuring bearing across time and measure it across
**space**: two receiving antennas, and the phase difference between them.

```
        RX A          RX B                 Δφ = 2π · d · sin(θ) / λ
          |<--- d --->|
           \    |    /                      θ = asin( Δφ · λ / 2π d )
            \   |   /
             \  |  /  θ                     one dwell, 0.47 s
              \ | /                         no moving parts
               \|/
             target
```

Both receivers see the same echo at the same instant, so the target is not
allowed to move during the measurement. The whole thing takes one dwell.

---

## It works, and by a wide margin

![interferometer performance](figures/08-interferometer.png)

Measured by [`figures/interferometer.py`](figures/interferometer.py), which
drives the project's own signal generator and processing, three noise seeds per
point:

| | scanning, 9 beams × 64 | two receivers, one dwell |
|---|---|---|
| time per fix | 4.3 s | **0.47 s** |
| bearing error, rms | 1.5° | **0.09°** |
| bearing error, worst | 2.7° | **0.14°** |
| works on a moving target | no | yes |

That is 18× inside the 2.5° budget, and 9× faster. Thermal noise is nowhere
near the limit: the bearing stays under 0.1° until the echo weakens by 25 dB,
equivalent to pushing the drone out past 40 m, and the cliff after that is the
CFAR losing the target altogether, not the phase measurement degrading.

**Calibration is the actual requirement.** 1 mm of extra coax on one channel is
3° of phase at 2.46 GHz and 0.3° of bearing error. Beyond about 8 mm of
uncorrected mismatch you are outside the budget. Either match the two cables
physically, or measure the fixed offset once against a reflector on boresight
and subtract it. A trihedral corner reflector is a good target for this and
prints in an afternoon.

---

## The geometry, and the one non-obvious constraint

Ambiguity sets the maximum baseline. The phase difference has to stay inside
±π across the beam, so:

```
d  ≤  λ / (2 · sin θ_max)  =  0.1219 / (2 × sin 17°)  =  209 mm
```

The horns are 263.8 mm wide across the aperture and 193.1 mm tall. Two of them
side by side in their normal orientation put the phase centres **263.8 mm**
apart, past the limit, and the bearing wraps beyond ±13.4° — inside the beam,
where it does real damage.

**So rotate all three horns 90°.** With the 193.1 mm dimension horizontal, two
receive horns can touch and still sit at a 193 mm baseline, which is
unambiguous to **±18.4°** and covers the 17° half-beam with room to spare. The
azimuth beamwidth changes from 36° to 34°, which is nothing, and the
polarisation rotates, which is fine as long as the transmit horn is rotated
with them.

The turntable stays, but its job changes. It no longer scans during a
measurement. It points the pair, and only moves when the target drifts towards
the edge of the 34° beam.

---

## What to buy

The parts are the ones already scoped for stage 3. They were specified to stack
a second receive horn *below* for elevation; for azimuth the same parts go
*beside* instead.

| item | ~$ | note |
|---|---|---|
| second ZX05-43MH-S+ mixer | 73 | the critical-path part, order first |
| second 2-way splitter | 13 | LO to both mixers |
| second 2400–2500 band-pass | 29 | in front of the second LNA |
| 4-input USB interface (UMC404HD) | 100 | beat A, beat B and sync on **one sample clock** |
| third horn | 0 | copper for three is already in BOM section B |
| second LNA | 0 | the SPF5189Z 4-pack covers it |
| second TL072 video channel | 0 | parts already in section C |
| **total** | **~215** | |

The 4-input interface is not optional and not substitutable. Two UCA202s have
independent sample clocks, and a phase measurement between two independently
clocked converters means nothing.

---

## What to write

About fifteen lines, and the plan is already in
[`radar-software.md`](radar-software.md) § 9 — written for elevation, but the
maths is identical.

1. Read 3 channels instead of 2.
2. Run `segment_chirps` on both beat channels against the **one** sync channel,
   so both cubes are cut on the same edges.
3. Take the range–Doppler of each, keeping it **complex**. `range_doppler`
   currently returns dB; it needs to return or expose the complex map.
4. At each CFAR detection, at that exact range–Doppler cell:
   `Δφ = angle(rd_B · conj(rd_A)) − cal`, then
   `θ = asin(Δφ · λ / 2π d)`.
5. Delete the beam-scan centroid from the azimuth path. It is no longer how
   bearing is measured.

Calibration is one constant. Put a corner reflector on boresight, read Δφ, store
it as `cal`, and subtract it from then on. Re-check it after anything is
unplugged, and after a large temperature change.

---

## The cheaper version, and why it is not the first choice

One RF switch in front of a single receive chain, alternating antennas chirp by
chirp, costs about $30 instead of $215 and removes channel mismatch entirely,
because both measurements go through the same mixer and the same amplifier.

The catch is that the two measurements are then 7.4 ms apart, and in that time a
drone at 1.8 m/s advances its round-trip phase by 79°, against a signal that is
157° at the edge of the beam. That motion term has to be subtracted using the
measured velocity, which couples velocity error into bearing error: one velocity
bin of 0.13 m/s costs about 0.6° of bearing. It also halves the Doppler samples
per antenna.

It would probably work. It is more software risk for less money, and the
simultaneous version has the parts already costed, so start there.

---

## What this gives up

Elevation. One baseline measures one angle, and putting it horizontal spends it
on azimuth. Range, azimuth and radial velocity is a 2-D track on the floor
plane, which is what the console and the tracker already draw.
