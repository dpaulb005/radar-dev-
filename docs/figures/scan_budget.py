#!/usr/bin/env python3
"""scan_budget.py — where should the scan-time budget go?

A mechanical scan costs  n_beams x n_chirps x PRI  seconds. That budget can buy
finer servo steps (more beams) or longer dwells (more chirps per beam). This
measures which one actually buys azimuth accuracy, by running the real pipeline:
SynthSource -> segment_chirps -> process -> ScanningRadar.centroid, exactly as
radar_acquire.py does it, over three noise seeds so one lucky run is not evidence.

Writes scan_budget.json, which make_figures.py turns into figure 7.

Usage:  python3 scan_budget.py          (slow: a few minutes)
"""
import json
import pathlib
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "ground_station"))

from radar_acquire import SynthSource, segment_chirps, process   # noqa: E402
from radar_twin import ScanningRadar                             # noqa: E402

FS, T_UP, RETRACE, PRI = 48_000.0, 6.4e-3, 1.0e-3, 7.4e-3
TARGET_R, TARGET_V, TARGET_RCS = 10.0, -1.8, 0.0026
AZIMUTHS = [-24, -12, -6, 0, 6, 12, 24]
SEEDS = (1, 2, 3)
SECTOR = 90.0


def centroid(radar, per_beam):
    """ScanningRadar.centroid's azimuth, inlined so the experiment is self-contained."""
    cand = []
    for az, dets in per_beam:
        for (r, v, s, lvl) in sorted(dets, key=lambda d: -d[3])[:1]:
            cand.append((az, r, v, s, lvl))
    if not cand:
        return None
    anchor = max(cand, key=lambda c: c[4])
    items = [c for c in cand if abs(c[1] - anchor[1]) <= 1.5 * radar.spec.range_res]
    w = np.array([10 ** (c[4] / 10) for c in items])
    w = w / w.sum()
    return float(np.sum(np.array([c[0] for c in items]) * w))


def scan(step, n_chirps, f0, bw, seed):
    n_beams = int(round(SECTOR / step)) + 1
    beams = np.linspace(-SECTOR / 2, SECTOR / 2, n_beams)
    radar = ScanningRadar(sector=SECTOR)
    errs = []
    for true_az in AZIMUTHS:
        per = []
        for i, b in enumerate(beams):
            src = SynthSource(FS, T_UP, n_chirps,
                              targets=[(TARGET_R, true_az, TARGET_V, TARGET_RCS)],
                              retrace_s=RETRACE, beam_az=b, f0=f0, bw=bw,
                              seed=seed * 1000 + i * 17 + int(true_az))
            beat, sync = src.read()
            cube, timing = segment_chirps(beat, sync, FS, n_chirps)
            if cube is None:
                continue
            dets, spec = process(cube, FS, timing, n_chirps, f0=f0, bw=bw)
            radar.spec = spec
            if dets:
                per.append((b, dets))
        az = centroid(radar, per)
        errs.append(np.nan if az is None else az - true_az)
    return np.array(errs, float), n_beams


CONFIGS = [
    # label,             step, chirps, f0,      bw,    family
    ("9 beams · 64",      12,   64,  2.440e9,  40e6, "base"),
    ("16 beams · 64",      6,   64,  2.440e9,  40e6, "beams"),
    ("23 beams · 64",      4,   64,  2.440e9,  40e6, "beams"),
    ("12 beams · 96",      8,   96,  2.440e9,  40e6, "mixed"),
    ("9 beams · 160",     12,  160,  2.440e9,  40e6, "dwell"),
    ("9 beams · 256",     12,  256,  2.440e9,  40e6, "dwell"),
    ("9 beams · 64, 80 MHz", 12, 64, 2.400e9,  80e6, "wideband"),
]


def main():
    out = []
    for label, step, nc, f0, bw, fam in CONFIGS:
        errs = []
        for seed in SEEDS:
            e, n_beams = scan(step, nc, f0, bw, seed)
            errs.append(e)
        e = np.concatenate(errs)
        row = dict(label=label, step=step, chirps=nc, beams=n_beams, family=fam,
                   bw_mhz=bw / 1e6, scan_s=round(n_beams * nc * PRI, 2),
                   rms=round(float(np.sqrt(np.nanmean(e ** 2))), 2),
                   worst=round(float(np.nanmax(np.abs(e))), 2))
        out.append(row)
        print(f"{label:>22}  {row['scan_s']:>6.1f} s   rms {row['rms']:>4.1f}°   "
              f"worst {row['worst']:>4.1f}°", flush=True)
    (HERE / "scan_budget.json").write_text(json.dumps(out, indent=1) + "\n")
    print("\nwrote scan_budget.json")


if __name__ == "__main__":
    main()
