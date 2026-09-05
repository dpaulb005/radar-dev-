# Getting position out of the can radar

**The gap that is easy to miss when planning this build: one TX horn plus one
RX horn measures range and radial velocity, and nothing else.** There is no
angle in that measurement. A drone 8 m dead ahead and a drone 8 m at 30° off
axis produce the *identical* beat tone. Range alone cannot tell you where
something is.

This page is the answer, with numbers from
`ground_station/scan_design.py` and `ground_station/radar_twin.py`.

## The three options

| | what it gives | cost | verdict |
|---|---|---|---|
| **1. Range + Doppler only** | closing rate, rotor Doppler ID, "how far" | $0 | fine as the **first milestone**, not the end |
| **2. Mechanically scan the horns** | full 2-D position, a true PPI | **~$15 servo** | **recommended** |
| 3. Two RX channels, angle from phase | fast angle, no moving parts | ~$116 + 2nd ADC | ambiguous with horns — see below |

### Why interferometry does not work with horns

Angle from phase needs `|sin θ| ≤ λ/2d`. Two horns physically cannot sit closer
than one aperture apart, and your aperture is 264 mm = **2.15 λ**:

| baseline | λ | unambiguous | verdict |
|---|---|---|---|
| 61 mm | 0.50 | ±90° | clean |
| 150 mm | 1.22 | ±24° | clean |
| **264 mm (horn)** | **2.15** | **±13.4°** | **ambiguous inside its own 36° beam** |

You would get several candidate angles for one target. If you ever want
electronic angle, use the **horn for TX** and a pair of **small** elements at
λ/2 = 61 mm for RX.

## The scanning design

Bolt the horn pair to a servo and step it across a sector. Each dwell is one
coherent processing interval (64 chirps × 2 ms = 128 ms) plus servo settling.

**How finely to step** — measured, not assumed:

| oversample | step | beams | sweep | azimuth RMS error | cross-range @ 8 m |
|---|---|---|---|---|---|
| 2× | 18° | 6 | 0.95 s | 5.1° | 0.72 m |
| **3×** | **12°** | **9** | **1.42 s** | **2.5°** | **0.35 m** |
| 4× | 9° | 11 | 1.74 s | 3.6° | 0.51 m |
| 6× | 6° | 16 | 2.53 s | 2.1° | 0.29 m |

**Use 3× oversampling (12° step).** Going to 6× buys only 6 cm of cross-range
for nearly double the revisit time.

Note the measured 2.5° is worse than the ~1.8° the SNR-limited formula
predicts. That is honest: real centroiding is limited by **amplitude-estimate
noise and beam-pattern knowledge**, not by thermal SNR. Do not plan around the
theoretical number.

### Once you have a track, stop scanning the whole sector

| mode | revisit |
|---|---|
| full 90° search sweep | 1.42 s (0.7 Hz) |
| **locked 2-position dither** | **0.32 s (3.2 Hz)** — 4× faster |

Sequential lobing (dither ±half a beamwidth around the target and compare
amplitudes either side) is both faster and *more* accurate than reading a peak
position, because a difference of two large numbers is far more sensitive to
angle than the peak of a broad lobe.

## End-to-end result

`ground_station/radar_twin.py` chains the whole thing — beam positions →
`fmcw_sim` chirp/echo/range-Doppler per beam → CA-CFAR detection →
amplitude-weighted azimuth centroid → `tracker.TrackKF`:

```
python radar_twin.py --track 20

  t     true r/az     meas r/az      track x,y      err
 15.6   7.4/+11.0     7.4/+11.0   (  7.26,  1.41)   0.01
 17.1   7.0/ +6.4     6.9/ +6.4   (  6.88,  0.77)   0.04
 18.5   6.6/ +1.4     6.6/ +1.4   (  6.61,  0.16)   0.04

  RMS track error: 0.12 m over 15 scans
```

**12 cm RMS tracking error**, versus ~2 m from the passive RSSI system.

## Three DSP traps this twin already hit (so you don't have to)

1. **CFAR self-masking.** A strong target's spectral leakage contaminates the
   training cells, so the threshold rises and the *strongest* target is
   rejected while noise elsewhere passes. The guard band must be wider than
   the target's windowed mainlobe — `guard=4` cells here, not 1.
2. **Never average in dB.** CA-CFAR must average **linear power**. Taking a
   mean (or median) of dB values is biased toward the low outliers and turns
   ordinary spectral leakage into a 40 dB "detection".
3. **Interpolate the range peak.** Reading the raw FFT bin centre costs a fixed
   bias of up to half a range cell (~0.9 m here). A parabolic fit through the
   peak and its two neighbours turns 1.8 m *resolution* into ~**10 cm
   accuracy** — that single change is what takes the range error from +1.00 m
   to +0.09 m.

## Build order

1. **Antennas bolted down, range + Doppler only.** Prove the RF chain on a
   walking person and a passing car (`mit-radar.md` Phase 3).
2. **Add the servo → scanning PPI.** 12° steps over your sector. This is the
   cheapest path to real position, and it makes the console's PPI scope
   literally correct rather than decorative.
3. **Lock and dither** once tracking, for 4× revisit and better angle.
4. **Only then** consider a second RX channel — and with small elements, not
   the horns.

## Elevation

A single scan axis gives azimuth only. For 3-D, either add a second servo
(pan-tilt, ~$25 more) or accept 2-D and constrain altitude separately. With a
34° elevation beamwidth the horn already covers a useful vertical slice at
short range, so azimuth-only is a reasonable first system for an indoor box.
