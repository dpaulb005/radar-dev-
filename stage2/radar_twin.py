#!/usr/bin/env python3
"""
radar_twin.py — STAGE 2. Digital twin of the scanning can radar.

    scan_design (beam positions)
        -> fmcw_sim (chirp -> echo -> range-Doppler map, per beam)
            -> CFAR detector (range, velocity, SNR out of the map)
                -> beam centroiding (azimuth from amplitude across beams)
                    -> (x, y) detections
                        -> tracker.TrackKF (position + velocity + prediction)

That is the whole signal chain of an active radar, in software, so you can
write and debug the detection and tracking code before the RF parts arrive --
and so the console has something realistic to display.

The scan itself is ScanningRadar in scanning.py; read the note there about why
the beam centroid is not how this radar measures bearing (it needs the target
nearly stationary -- the phase interferometer does not). The stage-1 pieces
this demo stands on, fmcw_sim, dsp.cfar_detect and tracker.TrackKF, are
imported from ../ground_station.

    python radar_twin.py                 # one scan, show detections
    python radar_twin.py --track 30      # 30 s of scanning + tracking
    python radar_twin.py --plot ppi.png  # PPI plot of a scan
"""

import argparse
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "ground_station"))

from tracker import TrackKF                                       # noqa: E402

from scanning import ScanningRadar                                # noqa: E402


# ----------------------------------------------------------------------
def demo_scan(sector, drone_r, drone_az, drone_v):
    rad = ScanningRadar(sector=sector)
    targets = [(drone_r, drone_az, drone_v, 0.01)]      # the drone
    per_beam, fixes = rad.one_scan(targets)
    print("=" * 68)
    print("  SCANNING CAN RADAR — one sweep")
    print("=" * 68)
    print(f"  sector {sector:.0f} deg, {rad.n_beams} beams, step {rad.step:.0f} deg, "
          f"dwell {rad.dwell*1e3:.0f} ms")
    print(f"  sweep time {rad.sweep_time:.2f} s ({1/rad.sweep_time:.2f} Hz revisit)")
    print(f"  TRUTH: drone at {drone_r:.1f} m, {drone_az:+.1f} deg, "
          f"{drone_v:+.1f} m/s, RCS 0.01 m^2\n")
    print(f"  {'beam az':>8} | detections (range m, vel m/s, SNR dB)")
    print(f"  {'-'*8}-+-{'-'*45}")
    for az, dets in per_beam:
        if dets:
            s = ", ".join(f"({r:.1f}, {v:+.1f}, {sn:.0f})" for r, v, sn, _ in dets[:3])
        else:
            s = "-"
        print(f"  {az:>+7.0f} | {s}")
    print(f"\n  CENTROIDED FIXES:")
    for f in fixes[:3]:
        err_r = f["range"] - drone_r
        err_a = f["az"] - drone_az
        print(f"    range {f['range']:5.2f} m (err {err_r:+.2f})   "
              f"az {f['az']:+6.1f} deg (err {err_a:+.1f})   "
              f"vel {f['vel']:+.1f} m/s   {f['beams']} beams   SNR {f['snr']:.0f} dB")
        print(f"      -> cartesian x={f['x']:+.2f} y={f['y']:+.2f} m, "
              f"cross-range err {abs(math.radians(err_a))*f['range']:.2f} m")
    if not fixes:
        print("    (none)")
    return rad, fixes


def track_run(seconds, sector):
    rad = ScanningRadar(sector=sector)
    kf = TrackKF(sigma_a=2.0, model="cv")
    t = 0.0
    print("=" * 68)
    print(f"  SCANNING + TRACKING, {seconds:.0f} s")
    print("=" * 68)
    print(f"  {'t':>6} {'true r/az':>14} {'meas r/az':>14} {'track x,y':>16} {'err':>6}")
    errs = []
    while t < seconds:
        # drone orbits at 8 m, moving in azimuth
        r_t = 8.0 + 1.5 * math.sin(0.25 * t)
        az_t = 20.0 * math.sin(0.18 * t)
        vr = 1.5 * 0.25 * math.cos(0.25 * t)
        _, fixes = rad.one_scan([(r_t, az_t, vr, 0.01)])
        t += rad.sweep_time
        if not fixes:
            print(f"  {t:>6.1f} {r_t:>7.1f}/{az_t:>+5.1f}   (no detection)")
            continue
        f = fixes[0]
        z = np.array([f["x"], f["y"], 1.2])
        sig_r, sig_a = 0.09, math.radians(1.8)
        R = np.diag([max(sig_r, f["range"] * sig_a) ** 2,
                     max(sig_r, f["range"] * sig_a) ** 2, 1.0])
        kf.step(t, z, R)
        tx = r_t * math.cos(math.radians(az_t))
        ty = r_t * math.sin(math.radians(az_t))
        err = math.hypot(kf.pos[0] - tx, kf.pos[1] - ty)
        errs.append(err)
        print(f"  {t:>6.1f} {r_t:>7.1f}/{az_t:>+5.1f} {f['range']:>7.1f}/{f['az']:>+5.1f}"
              f"  ({kf.pos[0]:>6.2f},{kf.pos[1]:>6.2f}) {err:>6.2f}")
    if errs:
        print(f"\n  RMS track error: {np.sqrt(np.mean(np.square(errs))):.2f} m "
              f"over {len(errs)} scans")


def ppi_plot(path, sector, drone_r, drone_az, drone_v):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rad = ScanningRadar(sector=sector)
    per_beam, fixes = rad.one_scan([(drone_r, drone_az, drone_v, 0.01)])
    plt.style.use("dark_background")
    fig = plt.figure(figsize=(8, 7)); fig.patch.set_facecolor("#0d0d0d")
    ax = fig.add_subplot(111, projection="polar")
    ax.set_facecolor("#0d0d0d")
    ax.set_theta_zero_location("N"); ax.set_theta_direction(-1)
    ax.set_thetamin(-sector / 2 - 10); ax.set_thetamax(sector / 2 + 10)
    for az, dets in per_beam:
        ax.plot([math.radians(az)] * 2, [0, 60], color="#2c2c2a", lw=0.8)
        for (r, v, s, lvl) in dets:
            ax.plot(math.radians(az), r, "o", color="#3987e5",
                    ms=4 + min(8, s / 6), alpha=0.55)
    for f in fixes[:1]:
        ax.plot(math.radians(f["az"]), f["range"], "*", color="#0ca30c", ms=22,
                label=f"fix {f['range']:.1f} m {f['az']:+.1f}°")
    ax.plot(math.radians(drone_az), drone_r, "o", mfc="none", mec="#c98500",
            ms=16, mew=2, label="truth")
    ax.set_rmax(40); ax.set_title("Scanning can radar — PPI", color="#c3c2b7")
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout(); fig.savefig(path, dpi=110)
    print(f"  wrote {path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sector", type=float, default=90.0)
    ap.add_argument("--range", type=float, default=8.0)
    ap.add_argument("--az", type=float, default=12.0)
    ap.add_argument("--vel", type=float, default=1.5)
    ap.add_argument("--track", type=float, metavar="SECONDS")
    ap.add_argument("--plot", metavar="PNG")
    args = ap.parse_args()
    if args.track:
        track_run(args.track, args.sector)
    elif args.plot:
        ppi_plot(args.plot, args.sector, args.range, args.az, args.vel)
    else:
        demo_scan(args.sector, args.range, args.az, args.vel)


if __name__ == "__main__":
    main()
