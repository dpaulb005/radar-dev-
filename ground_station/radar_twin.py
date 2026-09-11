#!/usr/bin/env python3
"""
radar_twin.py — digital twin of the can radar.

    scan_design (beam positions)
        -> fmcw_sim (chirp -> echo -> range-Doppler map, per beam)
            -> CFAR detector (range, velocity, SNR out of the map)
                -> beam centroiding (azimuth from amplitude across beams)
                    -> (x, y) detections
                        -> tracker.TrackKF (position + velocity + prediction)

NOTE ON THE AZIMUTH STEP. `ScanningRadar.centroid` below takes azimuth from
the amplitude across beam positions. That is NOT how the built radar measures
bearing any more, and it cannot be: a scan takes seconds, and the centroid
assumes every beam saw the target at one bearing, so at 10 m with a 2.5 deg
budget a 4.3 s scan needs the drone slower than 0.10 m/s. Measured in
docs/radar-software.md § 1.

Bearing now comes from the phase between TWO receivers inside a single 0.47 s
dwell: see interferometer.py, and radar_acquire.py --interferometer. The code
here is kept because it still models a hovering target correctly, and because
the beam-gain and CFAR pieces are shared.

That is the whole signal chain of an active radar, in software, so you can
write and debug the detection and tracking code before the RF parts arrive —
and so the console has something realistic to display.

    python radar_twin.py                 # one scan, show detections
    python radar_twin.py --track 30      # 30 s of scanning + tracking
    python radar_twin.py --plot ppi.png  # PPI plot of a scan
"""

import argparse
import math

import numpy as np

import fmcw_sim
from fmcw_sim import RadarSpec
from scan_design import RadarFront
from tracker import TrackKF


# ----------------------------------------------------------------------
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
    # strongest return per range cell
    out, seen = [], set()
    for r, v, s, lvl in sorted(dets, key=lambda d: -d[2]):
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
