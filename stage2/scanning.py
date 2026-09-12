#!/usr/bin/env python3
"""
scanning.py — STAGE 2. The mechanically scanned radar: step the beam across a
sector, detect in every dwell, and take azimuth from the amplitude across beam
positions.

    ScanningRadar.dwell_detect   one beam dwell: illuminate, RD map, CFAR
    ScanningRadar.one_scan       sweep the sector
    ScanningRadar.centroid       amplitude centroid across beams -> azimuth

NOTE ON THE AZIMUTH STEP. centroid() takes azimuth from the amplitude across
beam positions. That is NOT how this radar is meant to measure bearing, and it
cannot be: a scan takes seconds, and the centroid assumes every beam saw the
target at one bearing, so at 10 m with a 2.5 deg budget a 4.3 s scan needs the
drone slower than 0.10 m/s. Measured in docs/radar-software.md section 1.
Bearing comes from the phase between TWO receivers inside a single 0.47 s
dwell: interferometer.py. This code is kept because it still models a hovering
target correctly.

It is stage-2 code, but the detector it uses is stage 1's: cfar_detect and
beam_gain come from ../ground_station/dsp.py.
"""

import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "ground_station"))

import fmcw_sim                                                   # noqa: E402
from dsp import beam_gain, cfar_detect                            # noqa: E402
from fmcw_sim import RadarSpec                                    # noqa: E402

from scan_design import RadarFront                                # noqa: E402


# ----------------------------------------------------------------------
class ScanningRadar:
    def __init__(self, sector=90.0, spec=None, front=None, seed=0):
        self.spec = spec or RadarSpec(f0=2.4e9, bw=83.5e6, t_chirp=2e-3, n_chirps=64)
        self.front = front or RadarFront()
        self.sector = sector
        sc = self.front.scan(sector, oversample=3.0)
        self.step = sc["step"]
        self.n_beams = sc["n_beams"]
        self.dwell = sc["dwell"]
        self.sweep_time = sc["sweep"]
        self.beams = [(-sector / 2 + i * self.step) for i in range(self.n_beams)]
        self.rng = np.random.default_rng(seed)

    def dwell_detect(self, boresight_deg, targets):
        """One beam dwell: illuminate, build the RD map, run CFAR."""
        vis = []
        for (r, az, v, rcs) in targets:
            g = beam_gain(az - boresight_deg, self.front.bw_az)
            if g <= 1e-3:
                continue
            # two-way beam gain scales the apparent RCS
            vis.append((r, v, rcs * g * g))
        if not vis:
            vis = [(1e6, 0.0, 1e-9)]     # nothing in the beam
        cube = fmcw_sim.simulate(self.spec, vis, seed=int(self.rng.integers(1e6)),
                                 leakage=True)
        rd, ranges, vels = fmcw_sim.range_doppler(cube, self.spec, bg_subtract=True)
        return cfar_detect(rd, ranges, vels)

    def one_scan(self, targets):
        """Sweep the sector; return per-beam detections and centroided fixes."""
        per_beam = []
        for b in self.beams:
            per_beam.append((b, self.dwell_detect(b, targets)))
        return per_beam, self.centroid(per_beam)

    def centroid(self, per_beam, peaks_per_beam=1):
        """Amplitude-weighted centroid across beams -> azimuth far finer than
        the beamwidth.

        Single-target assumption: anchor on the strongest return anywhere in
        the sweep, then accept each beam's peak that lies within ~1.5 range
        cells of it. Grouping by naive range proximity instead lets adjacent
        range bins chain together, and quantisation then splits one target
        across two groups, which throws the azimuth onto a beam boresight.
        """
        cand = []
        for az, dets in per_beam:
            # cfar_detect ranks by CFAR ratio, which is the right order for
            # DETECTION but not for centroiding: a target smeared over a few
            # Doppler bins yields several detections per beam, and the beam
            # weight must come from the strongest absolute return, not from
            # whichever bin happened to have the quietest training cells.
            best = sorted(dets, key=lambda d: -d[3])[:peaks_per_beam]
            for (r, v, s, lvl) in best:
                cand.append((az, r, v, s, lvl))
        if not cand:
            return []
        res = self.spec.range_res
        anchor = max(cand, key=lambda c: c[4])
        items = [c for c in cand if abs(c[1] - anchor[1]) <= 1.5 * res]
        w = np.array([10 ** (c[4] / 10) for c in items])
        w = w / w.sum()
        az = float(np.sum(np.array([c[0] for c in items]) * w))
        r = float(np.sum(np.array([c[1] for c in items]) * w))
        v = float(np.sum(np.array([c[2] for c in items]) * w))
        snr = float(max(c[3] for c in items))
        return [dict(range=r, az=az, vel=v, snr=snr,
                     x=r * math.cos(math.radians(az)),
                     y=r * math.sin(math.radians(az)),
                     beams=len(items))]
