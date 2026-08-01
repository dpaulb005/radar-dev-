#!/usr/bin/env python3
"""
pursuit_sim.py — end-to-end interception feasibility simulation.

Closes the full loop in software so you can see, before touching hardware,
what the passive-radar interceptor can and cannot catch:

    target flies a path
        -> ground nodes "hear" both drones (RSSI + noise)
            -> locate.solve_position multilaterates BOTH  (the real solver)
                -> guidance law computes a command from the NOISY, DELAYED fix
                    -> interceptor point-mass dynamics respond (lean-limited,
                       first-order attitude lag, drag-limited top speed)

It reuses the actual `locate` solver and RSSI noise model and the actual
`guidance` laws, so the numbers reflect the real pipeline, not a toy.

Usage:
    python pursuit_sim.py                       # one run, prints result
    python pursuit_sim.py --plot run.png        # save a trajectory plot
    python pursuit_sim.py --trials 100          # Monte-Carlo intercept rate
    python pursuit_sim.py --trials 100 --target-speed 8 --law pro_nav
    python pursuit_sim.py --sweep               # envelope table over speeds

Everything is horizontal-plane (x, y) at a common altitude; see
docs/interception.md.
"""

import argparse
import json
import math
import pathlib

import numpy as np

import locate
import guidance

BASE = pathlib.Path(__file__).resolve().parent
G = 9.81


# ----------------------------------------------------------------------
# configuration container
# ----------------------------------------------------------------------

class Params:
    def __init__(self, **kw):
        self.dt = 0.01                 # physics step (s)
        self.sim_time = 30.0           # max sim seconds
        self.radar_hz = 8.0            # position-fix rate
        self.latency = 0.15            # end-to-end delay (s)
        self.rssi_sigma = 3.0          # dB
        self.capture_radius = 2.5      # m; "arrival" = within radar accuracy.
        self.contact_radius = 1.0      # m; "contact" needs terminal guidance.
        self.max_lean_deg = 35.0       # interceptor agility
        self.v_max = 12.0              # interceptor top speed (m/s)
        self.tau = 0.15                # attitude first-order lag (s)
        self.target_speed = 3.0        # m/s
        self.target_path = "orbit"     # orbit|drift|waypoints|evade
        self.law = "track"             # track|pure_pursuit|pro_nav
        self.speed_cmd = None          # default -> v_max
        self.__dict__.update(kw)
        if self.speed_cmd is None:
            self.speed_cmd = self.v_max


def load_nodes():
    try:
        cfg = json.loads((BASE / "config.json").read_text())
        nodes = {k: v for k, v in cfg["nodes"].items()}
        return nodes, cfg.get("path_loss_n", 2.1)
    except Exception:
        nodes = {"1": {"pos": [0, 0, 1], "rssi0": -38.0},
                 "2": {"pos": [8, 0, 1], "rssi0": -38.0},
                 "3": {"pos": [4, 7, 1], "rssi0": -38.0}}
        return nodes, 2.1


# ----------------------------------------------------------------------
# the simulated ground radar (RSSI -> real solver -> noisy fix)
# ----------------------------------------------------------------------

class Radar:
    def __init__(self, nodes, n_pl, z, sigma, rng):
        self.anch = {k: np.array(v["pos"], float) for k, v in nodes.items()}
        self.rssi0 = {k: v["rssi0"] for k, v in nodes.items()}
        self.n_pl = n_pl
        self.z = z
        self.sigma = sigma
        self.rng = rng

    def fix(self, xy, guess_xy):
        """Return a noisy multilaterated (x, y) for a true horizontal pos."""
        true3 = np.array([xy[0], xy[1], self.z])
        meas = []
        for k, a in self.anch.items():
            d = float(np.linalg.norm(true3 - a))
            rssi = self.rssi0[k] - 10 * self.n_pl * math.log10(max(d, 0.1))
            rssi += self.rng.normal(0, self.sigma)
            dm = locate.rssi_to_distance(rssi, self.rssi0[k], self.n_pl)
            meas.append((a, dm, locate.rssi_distance_sigma(dm, self.n_pl)))
        guess = np.array([guess_xy[0], guess_xy[1], self.z])
        pos, resid = locate.solve_position(meas, guess, self.z, solve_3d=False)
        return pos[:2], resid


# ----------------------------------------------------------------------
# target trajectory
# ----------------------------------------------------------------------

def target_state(path, t, speed, center, radius, rng_wp):
    """Return (pos_xy, vel_xy) of the target at time t."""
    cx, cy = center
    if path == "orbit":
        w = speed / max(radius, 0.5)
        p = np.array([cx + radius * math.cos(w * t),
                      cy + radius * math.sin(w * t)])
        v = np.array([-radius * w * math.sin(w * t),
                      radius * w * math.cos(w * t)])
        return p, v
    if path == "drift":
        ang = rng_wp["ang"]
        p = np.array([cx, cy]) + speed * t * np.array([math.cos(ang), math.sin(ang)])
        v = speed * np.array([math.cos(ang), math.sin(ang)])
        return p, v
    if path == "evade":
        # slow orbit that speeds up radially outward — a fleeing drone
        w = speed / max(radius, 0.5)
        r = radius + 0.15 * speed * t
        p = np.array([cx + r * math.cos(w * t), cy + r * math.sin(w * t)])
        v = np.array([-r * w * math.sin(w * t) + 0.15 * speed * math.cos(w * t),
                      r * w * math.cos(w * t) + 0.15 * speed * math.sin(w * t)])
        return p, v
    # waypoints: piecewise-linear through random points, re-seeded lazily
    seg = 4.0
    i = int(t // seg)
    while len(rng_wp["pts"]) < i + 2:
        rng_wp["pts"].append(np.array([cx, cy]) + rng_wp["rng"].uniform(-radius, radius, 2))
    a, b = rng_wp["pts"][i], rng_wp["pts"][i + 1]
    frac = (t % seg) / seg
    p = a + (b - a) * frac
    v = (b - a) / seg
    n = np.linalg.norm(v)
    if n > speed:
        v = v / n * speed
    return p, v


# ----------------------------------------------------------------------
# one closed-loop run
# ----------------------------------------------------------------------

def run(p: Params, seed=0, record=False):
    rng = np.random.default_rng(seed)
    nodes, n_pl = load_nodes()
    anch = np.array([v["pos"][:2] for v in nodes.values()])
    center = anch.mean(axis=0)
    radius = max(2.5, 0.30 * (anch.max() - anch.min()))
    z = 1.5

    radar = Radar(nodes, n_pl, z, p.rssi_sigma, rng)
    rng_wp = {"ang": rng.uniform(0, 2 * math.pi),
              "pts": [], "rng": rng}

    # interceptor starts at the first node, at rest
    p_i = anch[0].astype(float).copy()
    v_i = np.zeros(2)
    a_state = np.zeros(2)            # lagged actual accel

    a_max = guidance.max_accel(p.max_lean_deg)
    drag = a_max / p.v_max          # linear drag -> terminal speed ~ v_max
    alpha_tau = p.dt / (p.tau + p.dt)

    # delayed-fix buffers: list of (t_available, xy)
    buf_i, buf_t = [], []
    last_fix_i = p_i.copy()
    last_fix_t = None
    est_i = p_i.copy()
    est_t = None
    est_t_prev = None
    vt_est = np.zeros(2)
    radar_dt = 1.0 / p.radar_hz
    next_radar = 0.0

    a_cmd = np.zeros(2)
    min_sep = 1e9
    t_arrive = None       # first time within capture_radius (radar-limited)
    t_contact = None      # first time within contact_radius (needs terminal)
    log = [] if record else None

    steps = int(p.sim_time / p.dt)
    for s in range(steps):
        t = s * p.dt
        pt, vt = target_state(p.target_path, t, p.target_speed,
                              center, radius, rng_wp)

        # --- radar produces fixes at radar_hz, delivered after latency ---
        if t >= next_radar:
            next_radar += radar_dt
            fx_i, _ = radar.fix(p_i, last_fix_i)
            fx_t, _ = radar.fix(pt, est_t if est_t is not None else pt)
            buf_i.append((t + p.latency, fx_i))
            buf_t.append((t + p.latency, fx_t))
            last_fix_i = fx_i

        # --- consume any fix whose delay has elapsed ---
        while buf_i and buf_i[0][0] <= t:
            _, est_i = buf_i.pop(0)
        while buf_t and buf_t[0][0] <= t:
            ta, new_t = buf_t.pop(0)
            if est_t is not None and est_t_prev is not None:
                dtf = radar_dt
                vt_est = 0.4 * ((new_t - est_t) / dtf) + 0.6 * vt_est
            est_t_prev = est_t
            est_t = new_t

        # --- guidance on the noisy, delayed estimates ---
        if est_t is not None:
            if p.law == "pro_nav":
                a_cmd = guidance.pro_nav(est_i, v_i, est_t, vt_est,
                                         N=4.0, speed_cmd=p.speed_cmd, a_max=a_max)
            elif p.law == "pure_pursuit":
                a_cmd = guidance.pure_pursuit(est_i, v_i, est_t,
                                              p.speed_cmd, a_max=a_max)
            else:  # track
                a_cmd = guidance.track(est_i, v_i, est_t, vt_est,
                                       v_max=p.speed_cmd, a_max=a_max)

        # --- interceptor dynamics: attitude lag + drag ---
        a_state += (a_cmd - a_state) * alpha_tau
        a_net = a_state - drag * v_i
        v_i = v_i + a_net * p.dt
        p_i = p_i + v_i * p.dt

        sep = float(np.linalg.norm(pt - p_i))
        min_sep = min(min_sep, sep)
        if record and s % 5 == 0:
            log.append((t, p_i.copy(), pt.copy(), est_i.copy(),
                        est_t.copy() if est_t is not None else None))
        if t_arrive is None and sep <= p.capture_radius:   # within sensor accuracy
            t_arrive = t
        if sep <= p.contact_radius:      # physical contact (needs terminal guidance)
            t_contact = t
            break

    return {"arrive": t_arrive is not None, "t_arrive": t_arrive,
            "contact": t_contact is not None, "t_contact": t_contact,
            "intercept": t_arrive is not None, "t_capture": t_arrive,
            "min_sep": min_sep, "log": log,
            "meta": {"center": center, "radius": radius, "nodes": anch}}


# ----------------------------------------------------------------------
# reporting
# ----------------------------------------------------------------------

def monte_carlo(p: Params, trials):
    arr, con, times, misses = 0, 0, [], []
    for i in range(trials):
        r = run(p, seed=1000 + i)
        misses.append(r["min_sep"])
        arr += r["arrive"]
        con += r["contact"]
        if r["arrive"]:
            times.append(r["t_arrive"])
    misses = np.array(misses)
    print(f"\n  law={p.law}  target={p.target_path}@{p.target_speed} m/s  "
          f"radar={p.radar_hz:.0f} Hz  noise={p.rssi_sigma} dB  "
          f"latency={p.latency*1000:.0f} ms")
    print(f"  trials={trials}  arrival (<{p.capture_radius:.1f} m)={arr/trials*100:.0f}%  "
          f"contact (<{p.contact_radius:.1f} m)={con/trials*100:.0f}%")
    print(f"  median closest approach={np.median(misses):.2f} m  "
          f"p90={np.percentile(misses,90):.2f} m")
    if times:
        print(f"  median time-to-arrival={np.median(times):.1f} s (n={len(times)})")
    return arr / trials, float(np.median(misses))


def sweep(p: Params, trials):
    print(f"\nInterception envelope — arrival rate within {p.capture_radius:.1f} m "
          f"(median closest approach), interceptor v_max={p.v_max:.0f} m/s")
    print(f"  radar={p.radar_hz:.0f} Hz, noise={p.rssi_sigma} dB, "
          f"latency={p.latency*1000:.0f} ms, {trials} trials/cell")
    print(f"\n{'target m/s':>10} | {'track':>16} | {'pro_nav':>16}")
    print("-" * 50)
    for spd in (1, 2, 3, 5, 8, 12, 18):
        row = f"{spd:>10} |"
        for law in ("track", "pro_nav"):
            pr = Params(**{**p.__dict__, "target_speed": spd, "law": law})
            arr, miss = 0, []
            for i in range(trials):
                r = run(pr, seed=2000 + i)
                miss.append(r["min_sep"])
                arr += r["arrive"]
            row += f" {arr/trials*100:>3.0f}%  {np.median(miss):>5.2f} m |"
        print(row)
    print("\nA target near or above the interceptor's top speed cannot be "
          "caught in a tail chase; note how the miss floor tracks the sensor "
          "accuracy, not the guidance.")


def plot_run(p: Params, path, seed=7):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    r = run(p, seed=seed, record=True)
    log = r["log"]
    ti = np.array([x[1] for x in log])
    tt = np.array([x[2] for x in log])
    ei = np.array([x[3] for x in log])
    nodes = r["meta"]["nodes"]

    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.set_facecolor("#0d0d0d"); fig.patch.set_facecolor("#0d0d0d")
    ax.plot(nodes[:, 0], nodes[:, 1], "^", color="#d95926", ms=11,
            label="radar nodes")
    ax.plot(tt[:, 0], tt[:, 1], "-", color="#c98500", lw=2, label="target (true)")
    ax.plot(ti[:, 0], ti[:, 1], "-", color="#3987e5", lw=2, label="interceptor (true)")
    ax.plot(ei[:, 0], ei[:, 1], ".", color="#3987e5", ms=2, alpha=0.35,
            label="interceptor (radar est.)")
    ax.plot(*ti[0], "o", color="#3987e5", ms=9)
    ax.plot(*tt[0], "o", color="#c98500", ms=9)
    if r["arrive"]:
        ax.plot(*ti[-1], "*", color="#0ca30c", ms=22, label="ARRIVAL")
        title = f"ARRIVAL in {r['t_arrive']:.1f}s (closest {r['min_sep']:.2f} m)"
    else:
        ax.plot(*ti[-1], "x", color="#d03b3b", ms=14)
        title = f"no arrival (closest {r['min_sep']:.2f} m)"
    ax.set_title(f"{title}  ·  {p.law}, target {p.target_path}@{p.target_speed} m/s, "
                 f"{p.radar_hz:.0f} Hz / {p.rssi_sigma} dB", color="#c3c2b7", fontsize=10)
    ax.set_xlabel("x [m]"); ax.set_ylabel("y [m]")
    ax.set_aspect("equal"); ax.grid(alpha=0.15)
    ax.legend(loc="upper right", fontsize=8, framealpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    print(f"  wrote {path}  ({title})")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--trials", type=int, default=0, help="Monte-Carlo run count")
    ap.add_argument("--plot", metavar="PNG", help="save a single-run trajectory plot")
    ap.add_argument("--sweep", action="store_true", help="envelope table over speeds")
    ap.add_argument("--law", default="track",
                    choices=["track", "pure_pursuit", "pro_nav"])
    ap.add_argument("--target-speed", type=float, default=3.0)
    ap.add_argument("--target-path", default="orbit",
                    choices=["orbit", "drift", "waypoints", "evade"])
    ap.add_argument("--radar-hz", type=float, default=8.0)
    ap.add_argument("--latency", type=float, default=0.15)
    ap.add_argument("--rssi-sigma", type=float, default=3.0)
    ap.add_argument("--v-max", type=float, default=12.0)
    args = ap.parse_args()

    p = Params(law=args.law, target_speed=args.target_speed,
               target_path=args.target_path, radar_hz=args.radar_hz,
               latency=args.latency, rssi_sigma=args.rssi_sigma, v_max=args.v_max)

    if args.sweep:
        sweep(p, args.trials or 60)
    elif args.trials:
        monte_carlo(p, args.trials)
    elif args.plot:
        plot_run(p, args.plot)
    else:
        r = run(p, seed=7)
        if r["arrive"]:
            print(f"ARRIVED within {p.capture_radius:.1f} m in {r['t_arrive']:.1f} s "
                  f"(closest approach {r['min_sep']:.2f} m)")
        else:
            print(f"no arrival in {p.sim_time:.0f} s (closest {r['min_sep']:.2f} m)")


if __name__ == "__main__":
    main()
