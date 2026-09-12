#!/usr/bin/env python3
"""
dsp.py — the stage-1 detector: CFAR on a range-Doppler map, plus the horn's
main-lobe gain model.

Both functions used to live in radar_twin.py, which is now stage-2 scanning
code. They are here because stage 1 (one TX horn, one RX horn, range and
radial velocity) owns the detector: radar_acquire.py turns a beat cube into a
range-Doppler map with fmcw_sim.range_doppler and then calls cfar_detect on it.
The scan borrows them, not the other way round.

beam_gain is needed by synth.py to illuminate a target off boresight, which is
why it sits next to the detector rather than in the antenna code.
"""

import math

import numpy as np


def cfar_detect(rd_db, ranges, vels, guard=4, train=6, thresh_db=15.0,
                min_range=1.5, max_range=60.0):
    """Cell-averaging CFAR on the range-Doppler map.

    Returns [(range, velocity, snr_db)] for cells exceeding the local
    background. Two details that matter on a real (small) map:

      * the range axis here is only tens of bins wide, so a fixed two-sided
        training window would exclude the near ranges entirely -- exactly
        where a drone in a room is. Training cells are therefore taken from
        whichever side has them.
      * the GUARD band must be wider than the target's spectral footprint.
        With only ~90 samples per chirp the windowed mainlobe is several bins
        wide, and a guard of 1 lets the target's own leakage into the training
        cells -- classic CFAR self-masking, where the STRONGEST target is the
        one that gets rejected while noise elsewhere passes.

    Zero-Doppler is skipped: that is where TX leakage and static clutter live.
    """
    dets = []
    nv, nr = rd_db.shape
    zero_v = int(np.argmin(np.abs(vels)))
    for vi in range(nv):
        if abs(vi - zero_v) <= 1:
            continue
        row = rd_db[vi]
        for ri in range(nr):
            r = ranges[ri]
            if not (min_range <= r <= max_range):
                continue
            lo = row[max(0, ri - guard - train):max(0, ri - guard)]
            hi = row[min(nr, ri + guard + 1):min(nr, ri + guard + 1 + train)]
            tr = np.concatenate([lo, hi])
            if tr.size < 3:
                continue
            # CA-CFAR averages LINEAR POWER. Averaging (or taking a median of)
            # dB values is biased toward the low outliers and turns ordinary
            # spectral leakage into a 40 dB "detection".
            bg = 10.0 * math.log10(float(np.mean(10.0 ** (tr / 10.0))) + 1e-30)
            # Peak-pick: a strong target's windowed mainlobe is several bins
            # wide and every one of them beats the (distant) training cells,
            # so without this the SHOULDER bins come out as separate
            # "targets" 1-2 range cells short of the real one.
            is_peak = ((ri == 0 or row[ri] >= row[ri - 1]) and
                       (ri == nr - 1 or row[ri] >= row[ri + 1]))
            if is_peak and row[ri] - bg > thresh_db:
                # Sub-bin range: fit a parabola through the peak and its two
                # neighbours. Reading the raw bin centre costs a fixed bias of
                # up to half a range cell (~0.9 m here); interpolation is what
                # turns 1.8 m resolution into ~10 cm accuracy.
                r_hat = float(r)
                if 0 < ri < nr - 1:
                    y0, y1, y2 = row[ri - 1], row[ri], row[ri + 1]
                    den = (y0 - 2 * y1 + y2)
                    if abs(den) > 1e-9:
                        d = 0.5 * (y0 - y2) / den
                        if abs(d) <= 1.0:
                            r_hat = float(r + d * (ranges[1] - ranges[0]))
                dets.append((r_hat, float(vels[vi]), float(row[ri] - bg),
                             float(row[ri])))
    # Strongest return per range cell, ranked by ABSOLUTE LEVEL (d[3]), not by
    # the CFAR ratio (d[2]). This is the same lesson the scan centroid learned
    # the hard way: the cell with the quietest neighbours is not the target. A
    # moving target smears across Doppler bins, which lifts its own local
    # background and lowers its ratio, while a leakage residue just above
    # min_range sits in a quiet neighbourhood and wins on ratio alone. Ranking
    # by ratio put the reported range ~0.7 m short at 3 m and 5 m -- inside the
    # envelope this radar is specified for -- and dets[0] is what the console
    # shows as the fix and what the tracker is fed. The ratio is still what gets
    # REPORTED as snr_db; it is just not what orders the list.
    out, seen = [], set()
    for r, v, s, lvl in sorted(dets, key=lambda d: -d[3]):
        key = round(r, 1)
        if key in seen:
            continue
        seen.add(key)
        out.append((r, v, s, lvl))
    return out


def beam_gain(off_axis_deg, beamwidth_deg):
    """Gaussian approximation to the horn's main lobe (linear power)."""
    if abs(off_axis_deg) > 2.5 * beamwidth_deg:
        return 0.0
    return math.exp(-2.773 * (off_axis_deg / beamwidth_deg) ** 2)
