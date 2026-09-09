#!/usr/bin/env python3
"""interferometer.py — can two receive antennas give azimuth from ONE dwell?

The scan-based centroid needs seconds and so only works on a hovering target
(see signal-chain.md § stage 10). A two-element interferometer measures bearing
inside a single 0.47 s dwell, from the phase difference between two receivers.

    Δφ = 2π · d · sin(θ) / λ        θ = asin( Δφ · λ / (2π d) )

This measures how well that works using the project's own signal generator.
The second channel is produced by moving the synthetic target half the extra
path length, because SynthSource's target term carries phase 4π·r/λ, so a range
offset of d·sin(θ)/2 puts exactly 2π·d·sin(θ)/λ of extra phase on that channel
and nothing else changes (the beat frequency shifts by ~1 Hz, a 0.01 bin).

Writes interferometer.json for make_figures.py.

Usage:  python3 interferometer.py
"""
import json
import math
import pathlib
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "ground_station"))

from radar_acquire import SynthSource, segment_chirps        # noqa: E402
from radar_twin import beam_gain                             # noqa: E402

FS, T_UP, RETRACE, N_CHIRPS = 48_000.0, 6.4e-3, 1.0e-3, 64
F0, BW = 2.440e9, 40e6
C = 2.99792458e8
LAM = C / (F0 + BW / 2)                  # 0.1219 m, free space
VF_RG316 = 0.695                         # PTFE coax: a wave is slower inside the cable
LAM_COAX = LAM * VF_RG316                # 0.0847 m — this is what a length mismatch sees
TARGET_R, TARGET_V, TARGET_RCS = 10.0, -1.8, 0.0026
BASELINE = 0.1931                        # horn E-plane width: two horns touching


def two_channel(true_az, d, seed, rcs=TARGET_RCS, n_chirps=N_CHIRPS,
                vel=TARGET_V):
    """Return the complex range-Doppler map for each of two receivers."""
    dr = d * math.sin(math.radians(true_az)) / 2.0     # half the extra path
    maps = []
    for ch, extra in enumerate((0.0, dr)):
        src = SynthSource(FS, T_UP, n_chirps,
                          targets=[(TARGET_R + extra, true_az, vel, rcs)],
                          retrace_s=RETRACE, beam_az=0.0, f0=F0, bw=BW,
                          seed=seed * 100 + ch * 7 + 1)
        beats, sync = src.read()      # one RX per SynthSource here, two sources
        beat = beats[0]
        cube, timing = segment_chirps(beat, sync, FS, n_chirps)
        if cube is None:
            return None, None
        c = cube - cube.mean(axis=0, keepdims=True)     # drop static leakage
        rng = np.fft.fft(c * np.hanning(c.shape[1]), axis=1)[:, :c.shape[1] // 2]
        rd = np.fft.fftshift(np.fft.fft(rng * np.hanning(c.shape[0])[:, None], axis=0), axes=0)
        maps.append(rd)
    return maps[0], maps[1]


def bearing(rd1, rd2, d, cal=0.0):
    """Phase-difference bearing at the strongest non-zero-Doppler cell."""
    mag = np.abs(rd1)
    nv = mag.shape[0]
    zero = nv // 2
    mag[zero - 1:zero + 2, :] = 0.0                     # skip leakage / clutter
    mag[:, :1] = 0.0
    vi, ri = np.unravel_index(np.argmax(mag), mag.shape)
    dphi = np.angle(rd2[vi, ri] * np.conj(rd1[vi, ri])) - cal
    dphi = (dphi + math.pi) % (2 * math.pi) - math.pi
    s = dphi * LAM / (2 * math.pi * d)
    if abs(s) > 1:
        return float("nan")
    return math.degrees(math.asin(s))


def run():
    truths = list(range(-16, 17, 2))
    out = {"lam": LAM, "lam_coax": LAM_COAX, "baseline": BASELINE,
           "unambiguous_deg": math.degrees(math.asin(min(1.0, LAM / (2 * BASELINE))))}

    # --- accuracy across the beam, three noise seeds --------------------
    rows = []
    for az in truths:
        est = []
        for seed in (1, 2, 3):
            r1, r2 = two_channel(az, BASELINE, seed)
            if r1 is None:
                continue
            est.append(bearing(r1, r2, BASELINE))
        rows.append(dict(truth=az, mean=float(np.nanmean(est)),
                         err=float(np.nanmean(est) - az),
                         spread=float(np.nanstd(est))))
    out["accuracy"] = rows
    e = np.array([r["err"] for r in rows])
    print(f"baseline {BASELINE*1000:.0f} mm, unambiguous +/-{out['unambiguous_deg']:.1f} deg")
    print(f"bearing error over +/-16 deg: rms {np.sqrt(np.nanmean(e**2)):.2f}, "
          f"worst {np.nanmax(np.abs(e)):.2f} deg")

    # --- how it degrades as the echo gets weaker ------------------------
    snr_rows = []
    for scale_db in (0, -10, -20, -25, -30, -35):
        rcs = TARGET_RCS * 10 ** (scale_db / 10)
        errs = []
        for az in (-12, -6, 0, 6, 12):
            for seed in (1, 2, 3):
                r1, r2 = two_channel(az, BASELINE, seed, rcs=rcs)
                if r1 is None:
                    continue
                b = bearing(r1, r2, BASELINE)
                if not math.isnan(b):
                    errs.append(b - az)
        if errs:
            snr_rows.append(dict(rcs_db=scale_db,
                                 rms=float(np.sqrt(np.mean(np.array(errs) ** 2)))))
            print(f"  echo {scale_db:>4} dB : bearing rms {snr_rows[-1]['rms']:.2f} deg")
    out["vs_snr"] = snr_rows

    # --- what an uncalibrated cable-length mismatch costs ----------------
    cal_rows = []
    for mm in (0, 2, 5, 10, 20):
        phase = 2 * math.pi * (mm / 1000.0) / LAM_COAX     # coax, not free space
        errs = []
        for az in (-12, 0, 12):
            r1, r2 = two_channel(az, BASELINE, 1)
            b = bearing(r1, r2, BASELINE, cal=-phase)   # unremoved offset
            if not math.isnan(b):
                errs.append(b - az)
        cal_rows.append(dict(mm=mm, phase_deg=math.degrees(phase),
                             rms=float(np.sqrt(np.mean(np.array(errs) ** 2)))))
        print(f"  cable mismatch {mm:>2} mm = {math.degrees(phase):>5.1f} deg phase "
              f"-> bearing rms {cal_rows[-1]['rms']:.2f} deg")
    out["vs_cal"] = cal_rows

    (HERE / "interferometer.json").write_text(json.dumps(out, indent=1) + "\n")
    print("\nwrote interferometer.json")


if __name__ == "__main__":
    run()
