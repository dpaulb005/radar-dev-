#!/usr/bin/env python3
"""
acquire_az.py — STAGE 2. Live acquisition WITH AZIMUTH.

This is the azimuth half of ground_station/radar_acquire.py, lifted out when
stage 1 was cut back to range and radial velocity. Stage 1 has one receiver and
no bearing anywhere in it; everything that needs the second receiver is here:

    --interferometer        AZIMUTH from the phase between two receivers, in
                            one dwell. This is how bearing is meant to be
                            measured. Needs 3 audio channels: beat A, beat B,
                            sync, on ONE sample clock (a UMC404HD; two UCA202s
                            cannot do phase).
    --switched              the same thing on one chain and an RF switch:
                            antennas alternate chirp by chirp, and the one-PRI
                            motion phase is corrected from the measured
                            velocity. Velocity (and therefore bearing) folds at
                            half the simultaneous limit.
    --calibrate             measure the fixed chain phase offset from a
                            boresight reflector and store it.

Everything else -- the sound-card and WAV sources, radar_ctl, segmentation, the
range-Doppler transform and the CFAR detector -- is stage 1's, imported from
../ground_station. Nothing in ../ground_station imports this file.

Test it with no hardware at all:
    python3 acquire_az.py --selftest --st-az -8 --st-vel -1.8
    python3 acquire_az.py --selftest --switched --st-az 12 --st-vel 0.9
"""

import argparse
import json
import math
import os
import pathlib
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "ground_station"))

import fmcw_sim                                                   # noqa: E402
from dsp import cfar_detect                                       # noqa: E402
from radar_acquire import AudioSource, Ctl, WavSource, post_fix    # noqa: E402
from synth import BW_HZ, F0_HZ, SynthSource, segment_chirps        # noqa: E402

import interferometer as interf                                   # noqa: E402


def _maps(beats, sync, fs, n, timing_hint, f0, bw, thresh):
    """Cut every beat channel on the SAME sync edges and transform each one.

    Returns (cubes, timing, rds, ranges, vels, dets) where rds are COMPLEX
    range-Doppler maps -- the interferometer needs the phase, not the dB.
    Cutting both channels on one sync is what keeps their cells aligned.
    """
    cubes, timing = [], None
    for bt in beats:
        cube, tm = segment_chirps(bt, sync, fs, n)
        if cube is None:
            return None, None, None, None, None, None
        cubes.append(cube)
        timing = timing or tm
    t_up, pri = timing
    spec = fmcw_sim.RadarSpec(f0=f0, bw=bw, t_chirp=t_up, fs=fs, n_chirps=cubes[0].shape[0])
    rds, ranges, vels = [], None, None
    for cube in cubes:
        rd, ranges, vels = fmcw_sim.range_doppler(cube.astype(complex), spec,
                                                  bg_subtract=True, complex_out=True)
        rds.append(rd)
    vels = vels * (t_up / pri)                 # the Doppler axis is set by the PRI
    dets = cfar_detect(20 * np.log10(np.abs(rds[0]) + 1e-15), ranges, vels,
                       min_range=1.5, max_range=30.0, thresh_db=thresh)
    return cubes, timing, rds, ranges, vels, dets


def run(args):
    n = args.n_chirps
    ctl = Ctl(args.ctl) if args.ctl else None
    f0, bw = args.f0_mhz * 1e6, args.bw_mhz * 1e6
    if ctl:
        t_nom = ctl.status["t_chirp_ms"] / 1000.0 + ctl.status["retrace_us"] / 1e6
        f0, bw = ctl.status["f0_mhz"] * 1e6, ctl.status["bw_mhz"] * 1e6   # the truth
    else:
        t_nom = args.t_chirp_ms / 1000.0 + 1e-3
    print(f"# sweep {f0/1e6:.1f}-{(f0+bw)/1e6:.1f} MHz, range cell {3e8/(2*bw):.2f} m",
          file=sys.stderr)
    block_s = (n + 3) * t_nom               # a few spare chirps for sync slop

    if args.cal_file and pathlib.Path(args.cal_file).exists() and not args.calibrate:
        I = interf.Interferometer.load(args.cal_file, f0_hz=f0, bw_hz=bw,
                                       baseline_m=args.baseline)
        print(f"# calibration loaded: {math.degrees(I.cal):+.2f} deg from "
              f"{args.cal_file}", file=sys.stderr)
    else:
        I = interf.Interferometer(baseline_m=args.baseline, f0_hz=f0, bw_hz=bw)
        if not args.calibrate:
            print("# WARNING: no calibration. Bearings carry the fixed chain "
                  "offset until you run --calibrate against a boresight "
                  "reflector.", file=sys.stderr)
    if args.switched:
        print(f"# SWITCHED: velocity folds at +/-"
              f"{interf.switched_v_max(t_nom, I.lam):.2f} m/s (half the "
              f"simultaneous figure, because every other chirp is thrown "
              f"away). Past that the BEARING is wrong, not just the "
              f"velocity, so it is reported as no_az=velocity-fold.",
              file=sys.stderr)
    print(f"# interferometer: baseline {I.d*1000:.1f} mm, unambiguous "
          f"+/-{I.unambiguous_deg:.1f} deg, {I.bearing_error_per_mm_coax():.2f} "
          f"deg of bearing per mm of cable mismatch"
          + ("  [SWITCHED: motion-corrected]" if args.switched else ""),
          file=sys.stderr)

    n_beats = 1 if args.switched else 2

    if args.selftest:
        targets = [(args.st_range, args.st_az, args.st_vel, 0.01)]
        src = SynthSource(args.fs, args.t_chirp_ms / 1000.0, n, targets, f0=f0, bw=bw,
                          n_rx=n_beats, baseline_m=args.baseline,
                          cal_rad=math.radians(args.st_cal_deg), switched=args.switched)
        fs = args.fs
    elif args.replay:
        src = WavSource(args.replay, block_s)
        fs = src.fs
    else:
        src = AudioSource(args.device, args.fs, block_s, record=args.record,
                          n_beats=n_beats)
        fs = args.fs

    if ctl:
        ctl.sweep(True)                      # the ESP32 boots with RF off

    try:
        while True:
            beats, sync = src.read()
            if beats is None:
                break
            if args.switched:
                cube, timing, edges = segment_chirps(beats[0], sync, fs, n,
                                                     return_edges=True)
                if cube is None:
                    print("# no sync", file=sys.stderr); time.sleep(0.2); continue
                parity = interf.tdm_parity(edges)
                if parity is None:
                    print("# switched mode: no frame marker in the sync. The "
                          "antennas cannot be told apart and every bearing "
                          "would be sign-flipped. Flash radar_ctl with SWMODE 1.",
                          file=sys.stderr)
                    if args.selftest and args.once:
                        return []
                    time.sleep(0.2); continue
                ca, cb = interf.tdm_split(cube, parity)
                t_up, pri = timing
                spec = fmcw_sim.RadarSpec(f0=f0, bw=bw, t_chirp=t_up, fs=fs,
                                          n_chirps=ca.shape[0])
                rds = []
                for c in (ca, cb):
                    rd, ranges, vels = fmcw_sim.range_doppler(
                        c.astype(complex), spec, bg_subtract=True, complex_out=True)
                    rds.append(rd)
                vels = vels * (t_up / (2 * pri))    # every other chirp -> 2x PRI
                vmax = interf.switched_v_max(pri, I.lam)
                dets = cfar_detect(20 * np.log10(np.abs(rds[0]) + 1e-15), ranges,
                                   vels, min_range=1.5, max_range=30.0,
                                   thresh_db=args.thresh)
            else:
                _, timing, rds, ranges, vels, dets = _maps(
                    beats, sync, fs, n, None, f0, bw, args.thresh)
                if rds is None:
                    print("# no sync", file=sys.stderr); time.sleep(0.2); continue
                t_up, pri = timing

            if not dets:
                print(json.dumps({"t": round(time.time(), 2), "fix": None}), flush=True)
                if args.selftest and args.once:
                    return []
                continue

            if args.calibrate:
                best = max(dets, key=lambda d: d[3])
                vi, ri = interf.cell_of(ranges, vels, best[0], best[1])
                cal = I.calibrate(rds[0], rds[1], vi, ri,
                                  true_az_deg=args.cal_az,
                                  v_mps=(best[1] if args.switched else None),
                                  pri_s=(pri if args.switched else None))
                print(f"# CALIBRATED on the target at {best[0]:.2f} m, assumed "
                      f"{args.cal_az:+.1f} deg: offset {math.degrees(cal):+.2f} deg "
                      f"({math.degrees(cal)/I.bearing_error_per_mm_coax()*I.deg_bearing_per_deg_phase:.1f}"
                      f" mm equivalent)", file=sys.stderr)
                if args.cal_file:
                    I.save(args.cal_file)
                    print(f"# written to {args.cal_file}", file=sys.stderr)
                args.calibrate = False
                if args.once:
                    return [dict(range=best[0], vel=best[1], snr=best[2],
                                 az=args.cal_az, cal_deg=math.degrees(cal),
                                 x=best[0], y=0.0, beams=1)]

            recs = interf.add_bearings(dets, rds[0], rds[1], ranges, vels, I,
                                      v_mps_for_tdm=args.switched, pri_s=pri)
            # The fix is the STRONGEST return, full stop. If that one has
            # no trustworthy bearing then there is no fix: promoting a
            # weaker sidelobe that happens to have a bearing would be
            # inventing an answer.
            best = max(recs, key=lambda r: r["level"]) if recs else None
            refused = best["az_reason"] if (best and best["az"] is None) else None
            if refused:
                best = None
            out = {"t": round(time.time(), 2),
                   "t_chirp_ms": round(t_up * 1e3, 3), "pri_ms": round(pri * 1e3, 3),
                   "mode": "switched" if args.switched else "interferometer",
                   **({"v_unambiguous": round(vmax, 2)} if args.switched else {}),
                   "dets": [{"range": round(r["range"], 2), "vel": round(r["vel"], 2),
                             "az": (None if r["az"] is None else round(r["az"], 2)),
                             "snr": round(r["snr"], 1), "q": round(r["quality"], 2),
                             **({"no_az": r["az_reason"]} if r["az"] is None else {})}
                            for r in recs[:5]],
                   **({"no_fix": refused} if refused else {}),
                   "fix": (None if best is None else
                           {"range": round(best["range"], 2), "az": round(best["az"], 2),
                            "vel": round(best["vel"], 2), "snr": round(best["snr"], 1),
                            "x": round(best["x"], 2), "y": round(best["y"], 2),
                            "beams": 1})}
            print(json.dumps(out), flush=True)
            if best and args.server:
                post_fix(args.server, {"x": best["x"], "y": best["y"],
                                       "range": best["range"], "az": best["az"],
                                       "vel": best["vel"], "snr": best["snr"],
                                       "beams": 1, "t": time.time()})
            if args.selftest and args.once:
                if out["fix"]:
                    return [out["fix"]]
                return [{"refused": refused}] if refused else []
    finally:
        src.close()
        if ctl:
            try:
                ctl.sweep(False)             # leave the radar silent
            except Exception:
                pass


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--device", help="sound device index or name (see python -m sounddevice)")
    ap.add_argument("--fs", type=float, default=44100.0)
    ap.add_argument("--n-chirps", type=int, default=64)
    ap.add_argument("--t-chirp-ms", type=float, default=6.4,
                    help="nominal up-chirp (only for block sizing; measured live from sync)")
    ap.add_argument("--thresh", type=float, default=15.0, help="CFAR threshold dB")
    ap.add_argument("--f0-mhz", type=float, default=F0_HZ / 1e6,
                    help="sweep start; overridden by radar_ctl status when --ctl is given")
    ap.add_argument("--bw-mhz", type=float, default=BW_HZ / 1e6,
                    help="sweep width; 40 with --f0-mhz 2440 for WiFi-channel-1 coexistence")
    ap.add_argument("--ctl", help="radar_ctl serial port (sweep on/off)")
    # ---- azimuth ----
    g = ap.add_argument_group("azimuth (stage 2)")
    g.add_argument("--interferometer", action="store_true",
                   help="AZIMUTH from two receivers (the default here). Needs 3 "
                        "audio channels: beat A, beat B, sync, on ONE sample clock")
    g.add_argument("--switched", action="store_true",
                   help="azimuth on one chain with an RF switch alternating "
                        "antennas chirp by chirp; motion-corrected")
    g.add_argument("--baseline", type=float, default=interf.DEFAULT_BASELINE_M,
                   help="receive antenna spacing in metres (default 0.1931, "
                        "two rotated horns touching)")
    g.add_argument("--calibrate", action="store_true",
                   help="measure the fixed chain phase offset from the strongest "
                        "target, assumed to be at --cal-az, then continue")
    g.add_argument("--cal-az", type=float, default=0.0,
                   help="true bearing of the calibration reflector (default boresight)")
    g.add_argument("--cal-file", default="interferometer_cal.json",
                   help="where the calibration constant is stored and reloaded")
    g.add_argument("--st-cal-deg", type=float, default=0.0,
                   help="selftest only: inject this much chain phase offset, to "
                        "prove --calibrate removes it")
    ap.add_argument("--server", help="console URL, e.g. http://localhost:8080")
    ap.add_argument("--record", metavar="WAV", help="save raw stereo audio")
    ap.add_argument("--replay", metavar="WAV")
    ap.add_argument("--selftest", action="store_true", help="synthetic target, no hardware")
    ap.add_argument("--st-range", type=float, default=8.0)
    ap.add_argument("--st-az", type=float, default=15.0)
    ap.add_argument("--st-vel", type=float, default=1.0)
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        args.once = True
        if args.st_vel == 0.0:
            print("# note: a target with exactly zero Doppler is removed with the "
                  "clutter (bg_subtract) -- a real hover still shows rotor "
                  "micro-Doppler and body jitter; use --st-vel != 0", file=sys.stderr)
        fixes = run(args)
        if fixes and "refused" in fixes[0]:
            why = fixes[0]["refused"]
            vmax = interf.switched_v_max(args.t_chirp_ms / 1000.0 + 1e-3,
                                         interf.wavelength(args.f0_mhz * 1e6,
                                                           args.bw_mhz * 1e6))
            expected = args.switched and why == "velocity-fold" and abs(args.st_vel) > 0.8 * vmax
            print(f"SELFTEST {'PASS (correct refusal: ' + why + ')' if expected else 'FAIL (refused: ' + why + ')'}"
                  f": switched mode folds above +/-{vmax:.2f} m/s and the target "
                  f"is at {args.st_vel:+.2f}")
            sys.exit(0 if expected else 1)
        if not fixes:
            print("SELFTEST FAIL: no fix"); sys.exit(1)
        f = fixes[0]
        # the dwell is n_chirps x PRI long and the target keeps moving through
        # it, so the honest truth is the MID-DWELL range, not the t=0 range
        t_dwell = args.n_chirps * (args.t_chirp_ms / 1000.0 + 1e-3)
        r_true = args.st_range + args.st_vel * t_dwell / 2
        er = abs(f["range"] - r_true); ea = abs(f["az"] - args.st_az)
        # a phase interferometer is held to the real budget, not the
        # 4 deg the beam-scan centroid needed
        ok = er < 0.5 and ea < 2.5
        tag = "PASS" if ok else "FAIL"
        print(f"SELFTEST {tag} [{'switched' if args.switched else 'interferometer'}]: "
              f"range {f['range']:.2f} m (mid-dwell truth {r_true:.2f}), "
              f"az {f['az']:.2f} deg (true {args.st_az}, error {ea:.2f}), "
              f"vel {f['vel']:.2f} m/s (true {args.st_vel})")
        sys.exit(0 if ok else 1)
    run(args)


if __name__ == "__main__":
    main()
