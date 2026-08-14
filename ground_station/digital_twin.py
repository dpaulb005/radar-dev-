#!/usr/bin/env python3
"""
digital_twin.py — full 3D digital twin of the two-drone interception system.

Where pursuit_sim.py models the horizontal problem, this models the whole
vehicle-and-sensor stack in 3D so you can test the real end goal — "detect
the target, fly the interceptor to it" — before risking hardware.

What it models
--------------
* **Both aircraft in 3D**: point-mass quads with lean-limited horizontal
  acceleration, first-order attitude lag, drag-limited top speed, and a
  vertical channel that mirrors ESP-FC's ALTHOLD (throttle stick commands a
  climb RATE, clamped to -2..+4 m/s, closed onboard).
* **The sensor suite as it really is**:
    - radar (x, y) from RSSI multilateration through the *real* solver, at
      the real rate, with the real noise model;
    - altitude from the on-board BMP280 **barometer**, not the radar —
      because coplanar ground nodes cannot observe altitude (run
      `geometry.py`; it is mirror-ambiguous). This is the key architectural
      finding the twin exists to test.
* **Latency** end-to-end (sensor + solve + uplink), the binding constraint.
* **Guidance**: horizontal via the validated `guidance.track` law, vertical
  via a climb-rate command — i.e. exactly what autopilot.py will send.

Usage
-----
    python digital_twin.py                      # one run, 3D report
    python digital_twin.py --trials 40          # Monte-Carlo
    python digital_twin.py --alt-source radar   # prove why baro is needed
    python digital_twin.py --plot twin.png      # 3D trajectory plot
    python digital_twin.py --compare-alt        # baro vs radar altitude
"""

import argparse
import math
import pathlib

import numpy as np

import guidance
import locate
import geometry
import pursuit_sim as sim

BASE = pathlib.Path(__file__).resolve().parent
G = 9.81


# ----------------------------------------------------------------------
class TwinParams:
    def __init__(self, **kw):
        self.dt = 0.01
        self.sim_time = 40.0
        self.radar_hz = 8.0
        self.baro_hz = 20.0          # BMP280 is happy well above this
        self.baro_sigma = 0.4        # m, 1-sigma (relative alt is the good part)
        self.latency = 0.15
        self.rssi_sigma = 3.0
        self.capture_radius = 2.5    # "arrival" — within sensor accuracy
        self.contact_radius = 1.0
        self.max_lean_deg = 35.0
        self.v_max = 12.0
        self.tau = 0.15
        self.climb_max = 4.0         # ESP-FC ALTHOLD stick range
        self.sink_max = -2.0
        self.tau_climb = 0.35        # vertical loop is slower than attitude
        self.target_speed = 3.0
        self.target_path = "orbit"
        self.target_alt = 2.5
        self.alt_source = "baro"     # baro | radar | truth
        self.alt_hold = True
        self.__dict__.update(kw)


# ----------------------------------------------------------------------
class Sensors:
    """Radar (x,y) + barometer (z), each with its own rate and noise."""

    def __init__(self, p: TwinParams, nodes, n_pl, rng):
        self.p = p
        self.rng = rng
        self.anch = {k: np.array(v["pos"], float) for k, v in nodes.items()}
        self.rssi0 = {k: v["rssi0"] for k, v in nodes.items()}
        self.n_pl = n_pl
        self.node_arr = np.array([v["pos"] for v in nodes.values()], float)

    def radar_fix(self, true_p, guess, solve_3d=False):
        """Multilaterate through the REAL solver. Returns (xyz, resid)."""
        meas = []
        for k, a in self.anch.items():
            d = float(np.linalg.norm(true_p - a))
            rssi = self.rssi0[k] - 10 * self.n_pl * math.log10(max(d, 0.1))
            rssi += self.rng.normal(0, self.p.rssi_sigma)
            dm = locate.rssi_to_distance(rssi, self.rssi0[k], self.n_pl)
            meas.append((a, dm, locate.rssi_distance_sigma(dm, self.n_pl)))
        pos, resid = locate.solve_position(meas, guess, true_p[2], solve_3d=solve_3d)
        return pos, resid

    def baro(self, true_z):
        return true_z + self.rng.normal(0, self.p.baro_sigma)


# ----------------------------------------------------------------------
class Quad3D:
    """Point-mass quad: lean-limited horizontally, climb-rate limited vertically."""

    def __init__(self, p0, params: TwinParams):
        self.p = np.array(p0, float)
        self.v = np.zeros(3)
        self.a_h = np.zeros(2)       # lagged horizontal accel
        self.vz_cmd = 0.0
        self.par = params
        self.a_max = guidance.max_accel(params.max_lean_deg)
        self.drag = self.a_max / params.v_max

    def step(self, a_cmd_h, vz_cmd, dt):
        pr = self.par
        # horizontal: attitude lag then drag
        a_cmd_h = np.asarray(a_cmd_h, float)
        n = np.linalg.norm(a_cmd_h)
        if n > self.a_max:
            a_cmd_h = a_cmd_h / n * self.a_max
        self.a_h += (a_cmd_h - self.a_h) * (dt / (pr.tau + dt))
        self.v[:2] += (self.a_h - self.drag * self.v[:2]) * dt
        # vertical: ALTHOLD closes a climb-RATE loop onboard
        vz_cmd = float(np.clip(vz_cmd, pr.sink_max, pr.climb_max))
        self.vz_cmd += (vz_cmd - self.vz_cmd) * (dt / (pr.tau_climb + dt))
        self.v[2] = self.vz_cmd
        self.p += self.v * dt
        if self.p[2] < 0.2:                       # ground
            self.p[2] = 0.2
            self.v[2] = max(0.0, self.v[2])


# ----------------------------------------------------------------------
def target_3d(path, t, speed, center, radius, alt, rng_wp):
    """Target state in 3D: horizontal path from pursuit_sim + a bobbing altitude."""
    p2, v2 = sim.target_state(path, t, speed, center, radius, rng_wp)
    z = alt + 0.8 * math.sin(0.35 * t)            # gentle altitude changes
    vz = 0.8 * 0.35 * math.cos(0.35 * t)
    return np.array([p2[0], p2[1], z]), np.array([v2[0], v2[1], vz])


def run(p: TwinParams, seed=0, record=False):
    rng = np.random.default_rng(seed)
    nodes, n_pl = sim.load_nodes()
    anch = np.array([v["pos"][:2] for v in nodes.values()])
    center = anch.mean(axis=0)
    radius = max(2.5, 0.30 * (anch.max() - anch.min()))
    sensors = Sensors(p, nodes, n_pl, rng)
    rng_wp = {"ang": rng.uniform(0, 2 * math.pi), "pts": [], "rng": rng}

    interceptor = Quad3D([anch[0][0], anch[0][1], 1.0], p)

    buf_i, buf_t = [], []          # latency buffers: (t_available, xyz)
    est_i = interceptor.p.copy()
    est_t = None
    est_t_prev = None
    vt_est = np.zeros(3)
    guess_i = interceptor.p.copy()
    guess_t = None
    next_radar = 0.0
    next_baro = 0.0
    baro_i = interceptor.p[2]
    baro_t = p.target_alt
    radar_dt = 1.0 / p.radar_hz

    min_sep = 1e9
    min_sep_h = 1e9
    t_arrive = t_contact = None
    log = [] if record else None
    alt_err = []

    steps = int(p.sim_time / p.dt)
    for s in range(steps):
        t = s * p.dt
        pt, vt = target_3d(p.target_path, t, p.target_speed, center, radius,
                           p.target_alt, rng_wp)

        # ---- barometers (fast, both aircraft downlink their own altitude) ----
        if t >= next_baro:
            next_baro += 1.0 / p.baro_hz
            baro_i = sensors.baro(interceptor.p[2])
            baro_t = sensors.baro(pt[2])

        # ---- radar fixes ----
        if t >= next_radar:
            next_radar += radar_dt
            solve3 = (p.alt_source == "radar")
            fi, _ = sensors.radar_fix(interceptor.p, guess_i, solve_3d=solve3)
            ft, _ = sensors.radar_fix(pt, guess_t if guess_t is not None else pt,
                                      solve_3d=solve3)
            guess_i, guess_t = fi, ft
            # fuse altitude according to the configured source
            if p.alt_source == "baro":
                fi = np.array([fi[0], fi[1], baro_i])
                ft = np.array([ft[0], ft[1], baro_t])
            elif p.alt_source == "truth":
                fi = np.array([fi[0], fi[1], interceptor.p[2]])
                ft = np.array([ft[0], ft[1], pt[2]])
            buf_i.append((t + p.latency, fi))
            buf_t.append((t + p.latency, ft))
            alt_err.append(ft[2] - pt[2])

        while buf_i and buf_i[0][0] <= t:
            _, est_i = buf_i.pop(0)
        while buf_t and buf_t[0][0] <= t:
            _, new_t = buf_t.pop(0)
            if est_t is not None:
                vt_est = 0.4 * ((new_t - est_t) / radar_dt) + 0.6 * vt_est
            est_t_prev, est_t = est_t, new_t

        # ---- guidance ----
        if est_t is not None:
            a_h = guidance.track(est_i[:2], interceptor.v[:2], est_t[:2],
                                 vt_est[:2], v_max=p.v_max,
                                 a_max=interceptor.a_max, lead=p.latency + 0.3)
            # vertical: P on altitude error + target climb feed-forward
            dz = est_t[2] - est_i[2]
            vz_cmd = float(np.clip(1.2 * dz + vt_est[2], p.sink_max, p.climb_max))
        else:
            a_h, vz_cmd = np.zeros(2), 0.0

        interceptor.step(a_h, vz_cmd, p.dt)

        sep = float(np.linalg.norm(pt - interceptor.p))
        sep_h = float(np.linalg.norm(pt[:2] - interceptor.p[:2]))
        min_sep = min(min_sep, sep)
        min_sep_h = min(min_sep_h, sep_h)
        if record and s % 5 == 0:
            log.append((t, interceptor.p.copy(), pt.copy()))
        if t_arrive is None and sep <= p.capture_radius:
            t_arrive = t
        if sep <= p.contact_radius:
            t_contact = t
            break

    return {"arrive": t_arrive is not None, "t_arrive": t_arrive,
            "contact": t_contact is not None, "t_contact": t_contact,
            "min_sep": min_sep, "min_sep_h": min_sep_h,
            "alt_rms": float(np.sqrt(np.mean(np.square(alt_err)))) if alt_err else float("nan"),
            "log": log, "nodes": anch}


# ----------------------------------------------------------------------
def report(p, trials, label=""):
    arr = con = 0
    seps, alts, times = [], [], []
    for i in range(trials):
        r = run(p, seed=500 + i)
        arr += r["arrive"]; con += r["contact"]
        seps.append(r["min_sep"]); alts.append(r["alt_rms"])
        if r["arrive"]:
            times.append(r["t_arrive"])
    print(f"  {label or p.alt_source:<8} alt-source={p.alt_source:<6} "
          f"target={p.target_speed} m/s @ {p.target_alt} m")
    print(f"     arrival(<{p.capture_radius}m)={arr/trials*100:3.0f}%   "
          f"contact(<{p.contact_radius}m)={con/trials*100:3.0f}%   "
          f"median 3D miss={np.median(seps):.2f} m   "
          f"alt RMS err={np.nanmedian(alts):.2f} m"
          + (f"   t_arrive={np.median(times):.1f}s" if times else ""))
    return arr / trials, float(np.median(seps))


def plot3d(p, path, seed=3):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d import Axes3D  # noqa

    r = run(p, seed=seed, record=True)
    log = r["log"]
    ti = np.array([x[1] for x in log]); tt = np.array([x[2] for x in log])
    plt.style.use("dark_background")
    fig = plt.figure(figsize=(9, 7.5))
    fig.patch.set_facecolor("#0d0d0d")
    ax = fig.add_subplot(111, projection="3d")
    ax.set_facecolor("#0d0d0d")
    nodes, _ = sim.load_nodes()
    na = np.array([v["pos"] for v in nodes.values()], float)
    ax.scatter(na[:, 0], na[:, 1], na[:, 2], c="#d95926", marker="^", s=70, label="radar nodes")
    ax.plot(tt[:, 0], tt[:, 1], tt[:, 2], color="#c98500", lw=2, label="target")
    ax.plot(ti[:, 0], ti[:, 1], ti[:, 2], color="#3987e5", lw=2, label="interceptor")
    ax.scatter(*ti[0], color="#3987e5", s=45)
    ax.scatter(*tt[0], color="#c98500", s=45)
    if r["arrive"]:
        ax.scatter(*ti[-1], color="#0ca30c", marker="*", s=280, label="arrival")
        title = f"ARRIVAL in {r['t_arrive']:.1f}s — 3D miss {r['min_sep']:.2f} m"
    else:
        ax.scatter(*ti[-1], color="#d03b3b", marker="x", s=110)
        title = f"no arrival — closest {r['min_sep']:.2f} m"
    ax.set_xlabel("x [m]"); ax.set_ylabel("y [m]"); ax.set_zlabel("altitude [m]")
    ax.set_zlim(0, max(6, p.target_alt + 3))
    ax.set_title(f"{title}\nalt source: {p.alt_source}", color="#c3c2b7", fontsize=10)
    ax.legend(fontsize=8, loc="upper left")
    fig.tight_layout(); fig.savefig(path, dpi=110)
    print(f"  wrote {path}  ({title})")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--trials", type=int, default=0)
    ap.add_argument("--plot", metavar="PNG")
    ap.add_argument("--alt-source", default="baro", choices=["baro", "radar", "truth"])
    ap.add_argument("--compare-alt", action="store_true",
                    help="baro vs radar vs perfect altitude, head to head")
    ap.add_argument("--target-speed", type=float, default=3.0)
    ap.add_argument("--target-alt", type=float, default=2.5)
    ap.add_argument("--target-path", default="orbit",
                    choices=["orbit", "drift", "waypoints", "evade"])
    ap.add_argument("--radar-hz", type=float, default=8.0)
    ap.add_argument("--latency", type=float, default=0.15)
    args = ap.parse_args()

    p = TwinParams(alt_source=args.alt_source, target_speed=args.target_speed,
                   target_alt=args.target_alt, target_path=args.target_path,
                   radar_hz=args.radar_hz, latency=args.latency)

    if args.compare_alt:
        n = args.trials or 25
        print("\n  ALTITUDE SOURCE COMPARISON — the 3D question, measured")
        print(f"  ({n} trials each, target {p.target_speed} m/s at {p.target_alt} m)\n")
        for src in ("truth", "baro", "radar"):
            report(TwinParams(**{**p.__dict__, "alt_source": src}), n)
        print("\n  'radar' solves altitude from the coplanar node array — see"
              "\n  geometry.py for why that is mirror-ambiguous.\n")
    elif args.plot:
        plot3d(p, args.plot)
    elif args.trials:
        print()
        report(p, args.trials)
        print()
    else:
        r = run(p, seed=3)
        print(f"\n  3D digital twin — alt source: {p.alt_source}")
        if r["arrive"]:
            print(f"  ARRIVAL in {r['t_arrive']:.1f} s")
        else:
            print(f"  no arrival in {p.sim_time:.0f} s")
        print(f"  closest 3D approach : {r['min_sep']:.2f} m")
        print(f"  closest horizontal  : {r['min_sep_h']:.2f} m")
        print(f"  target alt RMS error: {r['alt_rms']:.2f} m\n")


if __name__ == "__main__":
    main()
