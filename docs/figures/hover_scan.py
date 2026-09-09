#!/usr/bin/env python3
"""hover_scan.py — if the drone holds still, does the servo scan give azimuth?

The scan-versus-interferometer measurement in scan_budget.py holds the target
at a fixed azimuth AND gives it 1.8 m/s of radial velocity, so it answers
"how accurate is the centroid?" and not "does this work on a drone that is
trying to hover?". Those turn out to be different questions, because a hovering
target has two separate problems and only one of them is about time:

  1. SMEAR. The centroid assumes every beam saw the target at one bearing. Any
     tangential drift during the scan spreads it across beams.
  2. DOPPLER. process() range-Doppler map is background-subtracted
     (fmcw_sim.range_doppler, bg_subtract=True: c -= c.mean(axis=0)), which is
     what removes the TX leakage and the room. A target with no radial velocity
     is removed with them. The interferometer has the same problem -- its
     bearing() zeroes the three middle Doppler bins for exactly this reason.

So this sweeps drift speed in the two extreme directions, which bracket
reality, and measures BOTH the bearing error and whether there was a fix at
all, for the scan and for the interferometer, on the same targets.

    pure radial     drift straight at the radar: full Doppler, no smear
    pure tangential drift across it: zero Doppler, maximum smear

Writes hover_scan.json.

Usage:
    python3 hover_scan.py              the whole thing (~15 minutes)
    python3 hover_scan.py --geometry   just the geometry sweep
    python3 hover_scan.py --selftest   assert the published conclusions
"""
import json
import math
import pathlib
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "ground_station"))

from radar_acquire import SynthSource, segment_chirps, process   # noqa: E402
from radar_twin import ScanningRadar                             # noqa: E402
from scan_budget import centroid                                 # noqa: E402

# this directory's interferometer.py is a different module from
# ground_station/interferometer.py, which is already on the path -- load it by
# path so the name collision cannot pick the wrong one
import importlib.util                                            # noqa: E402
_spec = importlib.util.spec_from_file_location(
    "figures_interferometer", HERE / "interferometer.py")
_fig_interf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fig_interf)
two_channel, bearing, BASELINE = (_fig_interf.two_channel, _fig_interf.bearing,
                                  _fig_interf.BASELINE)

FS, T_UP, RETRACE, PRI = 48_000.0, 6.4e-3, 1.0e-3, 7.4e-3
F0, BW = 2.440e9, 40e6
TARGET_R, TARGET_RCS = 10.0, 0.0026
AZIMUTHS = (-12, -6, 0, 6, 12)
SEEDS = (1, 2, 3)
SECTOR, STEP = 90.0, 12.0
BUDGET_DEG = 2.5

SPEEDS = (0.0, 0.02, 0.05, 0.10, 0.20, 0.35, 0.50, 1.00)

# A hovering drone is never perfectly still: the rotors and the airframe jitter,
# which is what keeps it out of the zero-Doppler bin. JITTER is a stand-in for
# that, and it is deliberately small -- radar_acquire.py --selftest already
# passes at 0.05 m/s, so 0.15 is a modest assumption, not a generous one.
JITTER = 0.15

CASES = (
    # label            how v is spent                   what it isolates
    ("closing",        lambda v: (v, 0.0)),           # detectability + range walk
    ("drifting",       lambda v: (0.0, v)),           # the real hover: both faults
    ("drifting+jitter", lambda v: (JITTER, v)),       # SMEAR alone
)


def one_scan(true_az, v_r, v_t, n_chirps, seed, n_beams=None, sector=None):
    """A full sector scan on a target moving at (v_r radial, v_t tangential).

    The target moves BETWEEN beams, which is the thing the centroid cannot see:
    beam i is recorded at t = i * n_chirps * PRI.
    """
    sector = SECTOR if sector is None else sector
    if n_beams is None:
        n_beams = int(round(sector / STEP)) + 1
    beams = np.linspace(-sector / 2, sector / 2, n_beams)
    radar = ScanningRadar(sector=sector)
    per = []
    for i, b in enumerate(beams):
        t = i * n_chirps * PRI
        r_i = TARGET_R + v_r * t
        az_i = true_az + math.degrees(v_t * t / TARGET_R)
        src = SynthSource(FS, T_UP, n_chirps,
                          targets=[(r_i, az_i, v_r, TARGET_RCS)],
                          retrace_s=RETRACE, beam_az=b, f0=F0, bw=BW,
                          seed=seed * 1000 + i * 17 + int(true_az))
        beats, sync = src.read()
        cube, timing = segment_chirps(beats[0], sync, FS, n_chirps)
        if cube is None:
            continue
        dets, spec = process(cube, FS, timing, n_chirps, f0=F0, bw=BW)
        radar.spec = spec
        if dets:
            per.append((b, dets))
    if not per:
        return None
    return centroid(radar, per)


def one_interferometer(true_az, v_r, v_t, seed):
    """One 0.47 s dwell, two receivers. Tangential drift over a single dwell is
    small by construction; the Doppler problem is not."""
    r1, r2 = two_channel(true_az, BASELINE, seed, vel=v_r)
    if r1 is None:
        return None
    b = bearing(r1, r2, BASELINE)
    return None if (b is None or math.isnan(b)) else b


def sweep(method, label):
    rows = []
    for cname, split in CASES:
        for v in SPEEDS:
            v_r, v_t = split(v)
            errs, misses = [], 0
            for az in AZIMUTHS:
                for seed in SEEDS:
                    est = method(az, v_r, v_t, seed)
                    if est is None or not np.isfinite(est):
                        misses += 1
                    else:
                        errs.append(est - az)
            n = len(AZIMUTHS) * len(SEEDS)
            e = np.array(errs, float)
            rows.append(dict(
                method=label, case=cname, v=v, v_r=round(v_r, 3), v_t=round(v_t, 3),
                fixes=len(errs), trials=n,
                rms=None if not len(e) else round(float(np.sqrt(np.mean(e ** 2))), 2),
                worst=None if not len(e) else round(float(np.max(np.abs(e))), 2),
                in_budget=None if not len(e) else bool(
                    np.max(np.abs(e)) <= BUDGET_DEG)))
            r = rows[-1]
            rms = "  --  " if r["rms"] is None else f"{r['rms']:>6.2f}"
            flag = "" if r["in_budget"] else "   <-- outside the 2.5 deg budget"
            print(f"  {label:<16} {cname:<16} v {v:>4.2f}   rms {rms} deg"
                  f"   worst {r['worst']:>6.2f}{flag}", flush=True)
    return rows


# sector, beams. Fewer beams means a shorter scan (less smear) but a coarser
# centroid; a narrower sector means finer steps for the same scan time but less
# coverage. Both knobs, measured against drift rather than argued about.
GEOMETRIES = (
    (90.0, 9),   # what the repo currently specifies
    (90.0, 5),
    (72.0, 7),
    (48.0, 5),
    (48.0, 3),
    (36.0, 4),
)
DRIFTS = (0.0, 0.05, 0.10, 0.20, 0.35, 0.50, 0.75, 1.00, 1.50)


def geometry_sweep():
    """A scan is slow because it visits many beams, and the target smears in
    proportion. Does a shorter scan buy drift tolerance faster than the coarser
    centroid loses it? Both effects are real and pull opposite ways."""
    rows = []
    print("\nscan geometry vs drift tolerance (64 chirps, hover jitter "
          f"{JITTER} m/s, beamwidth 36 deg)")
    for sector, n_beams in GEOMETRIES:
        step = sector / (n_beams - 1)
        for v_t in DRIFTS:
            errs = []
            for az in AZIMUTHS:
                for seed in SEEDS:
                    est = one_scan(az, JITTER, v_t, 64, seed,
                                   n_beams=n_beams, sector=sector)
                    if est is not None and np.isfinite(est):
                        errs.append(est - az)
            e = np.array(errs, float)
            row = dict(sector=sector, n_beams=n_beams, step=round(step, 1),
                       v_t=v_t, scan_s=round(n_beams * 64 * PRI, 2),
                       fixes=len(e), trials=len(AZIMUTHS) * len(SEEDS),
                       rms=None if not len(e) else round(float(np.sqrt(np.mean(e ** 2))), 2),
                       worst=None if not len(e) else round(float(np.max(np.abs(e))), 2))
            rows.append(row)
            rms = "  --  " if row["rms"] is None else f"{row['rms']:>6.2f}"
            ok = "" if (row["worst"] is not None and row["worst"] <= BUDGET_DEG) else "  X"
            print(f"  {int(sector):>3} deg / {n_beams} beams "
                  f"({row['scan_s']:>4.2f} s, {step:>4.1f} deg step)"
                  f"   drift {v_t:>4.2f}   rms {rms}   worst {row['worst']:>6.2f}{ok}",
                  flush=True)
    return rows


def _find(rows, **kw):
    for r in rows:
        if all(abs(r[k] - v) < 1e-9 if isinstance(v, float) else r[k] == v
               for k, v in kw.items()):
            return r
    raise KeyError(kw)


def selftest():
    """Assert the conclusions this experiment is cited for, against its own
    saved results. If the physics or the pipeline changes underneath them,
    this fails instead of the docs quietly going stale."""
    blob = json.loads((HERE / "hover_scan.json").read_text())
    drift, geom = blob["drift"], blob["geometry"]
    ok = 0

    def check(cond, msg):
        nonlocal ok
        assert cond, msg
        ok += 1

    # -- a target with exactly zero Doppler is removed with the clutter, and
    #    every method fails on it. This is the claim that "hold still" is the
    #    wrong instruction.
    for m in ("scan 4.3 s", "scan 10.7 s", "interferometer"):
        r = _find(drift, method=m, case="closing", v=0.0)
        check(r["rms"] > 5.0, f"{m} must fail at exactly zero Doppler: {r['rms']}")
    # -- and a little radial motion is all it takes to recover
    r = _find(drift, method="interferometer", case="closing", v=0.05)
    check(r["rms"] < 0.3, f"0.05 m/s must be enough to be seen: {r['rms']}")

    # -- smear: the 4.3 s scan holds the budget to ~0.15 m/s of drift
    check(_find(drift, method="scan 4.3 s", case="drifting+jitter",
                v=0.10)["worst"] <= BUDGET_DEG, "4.3 s scan must hold at 0.10 m/s")
    check(_find(drift, method="scan 4.3 s", case="drifting+jitter",
                v=0.20)["worst"] > BUDGET_DEG, "4.3 s scan must fail at 0.20 m/s")

    # -- the correction to signal-chain.md: a LONGER scan is worse, not better,
    #    once the target is allowed to move at all
    short = _find(drift, method="scan 4.3 s", case="drifting+jitter", v=0.0)
    long_ = _find(drift, method="scan 10.7 s", case="drifting+jitter", v=0.0)
    check(long_["rms"] > short["rms"] * 5,
          f"the 10.7 s scan must be much worse under drift: {long_['rms']} vs {short['rms']}")

    # -- the interferometer does not care about drift at all
    a = _find(drift, method="interferometer", case="drifting+jitter", v=0.0)
    b = _find(drift, method="interferometer", case="drifting+jitter", v=1.0)
    check(abs(a["rms"] - b["rms"]) < 0.05, "one dwell must be immune to drift")
    check(b["worst"] <= BUDGET_DEG, "interferometer must hold budget at 1 m/s")

    # -- geometry: 3 beams over 48 deg beats 9 over 90 under drift, and loses
    #    to it on a parked target. Both halves matter; the crossover is the point.
    g9 = {r["v_t"]: r for r in geom if r["n_beams"] == 9}
    g3 = {r["v_t"]: r for r in geom if r["n_beams"] == 3}
    check(g9[0.0]["rms"] < g3[0.0]["rms"], "9 beams must win on a parked target")
    check(g3[0.5]["worst"] <= BUDGET_DEG, f"48/3 must hold at 0.50 m/s: {g3[0.5]['worst']}")
    check(g3[0.75]["worst"] > BUDGET_DEG, "48/3 must fail by 0.75 m/s")
    check(g9[0.2]["worst"] > BUDGET_DEG, "90/9 must fail at 0.20 m/s")
    check(g3[0.5]["rms"] < g9[0.5]["rms"] / 3, "48/3 must beat 90/9 badly at 0.5")
    check(g3[0.0]["scan_s"] < g9[0.0]["scan_s"] / 2, "and be far quicker")

    # -- a sector barely wider than the targets squeezes the centroid: this is
    #    why "fewer beams" is not the whole story
    g36 = {r["v_t"]: r for r in geom if r["sector"] == 36.0}
    check(g36[0.0]["worst"] > BUDGET_DEG,
          "a 36 deg sector must fail even at rest, on targets out to +/-12 deg")

    print(f"selftest: {ok} checks passed")
    return 0


def main():
    # --geometry re-runs only the geometry sweep and merges it into the
    # existing JSON; the drift sweep above it is slow and does not change.
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if "--geometry" in sys.argv:
        path = HERE / "hover_scan.json"
        blob = json.loads(path.read_text()) if path.exists() else {}
        blob["geometry"] = geometry_sweep()
        path.write_text(json.dumps(blob, indent=1) + "\n")
        print("\nwrote hover_scan.json (geometry only)")
        return
    out = []
    print("scan, 9 beams x 64 chirps = 4.26 s")
    out += sweep(lambda az, vr, vt, seed: one_scan(az, vr, vt, 64, seed),
                 "scan 4.3 s")
    print("scan, 9 beams x 160 chirps = 10.66 s")
    out += sweep(lambda az, vr, vt, seed: one_scan(az, vr, vt, 160, seed),
                 "scan 10.7 s")
    print("interferometer, one 0.47 s dwell")
    out += sweep(one_interferometer, "interferometer")
    beams = geometry_sweep()
    (HERE / "hover_scan.json").write_text(
        json.dumps({"drift": out, "geometry": beams}, indent=1) + "\n")
    print("\nwrote hover_scan.json")


if __name__ == "__main__":
    main()
