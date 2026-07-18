#!/usr/bin/env python3
"""
locate.py — real-time drone position solver.

Consumes JSON lines from the hub node (RSSI reports relayed from the
sniffer nodes) and optionally from FTM nodes (direct distance reports),
converts RSSI to distance with a log-distance path-loss model, and
multilaterates the drone position with nonlinear least squares.

Usage:
    python locate.py --hub /dev/ttyUSB0
    python locate.py --hub /dev/ttyUSB0 --port /dev/ttyUSB1 --port /dev/ttyUSB2
    python locate.py --sim                # no hardware: synthetic circular flight
    python locate.py --hub COM5 --plot    # live matplotlib view

Input line formats (one JSON object per line):
    {"node":1,"rssi":-54,"n":12,"t":123}     RSSI report (via hub)
    {"node":2,"dist":4.37,"rtt_ns":29,"t":123}  FTM distance report

Output: one JSON fix per solve interval on stdout:
    {"t":1721312000.1,"x":3.21,"y":4.87,"z":1.5,"nodes_used":3,"resid_m":0.4}
"""

import argparse
import json
import math
import queue
import sys
import threading
import time

import numpy as np
from scipy.optimize import least_squares

SOLVE_INTERVAL_S = 0.25   # how often to attempt a fix
MEAS_MAX_AGE_S   = 1.0    # discard node measurements older than this
EMA_ALPHA        = 0.35   # position smoothing (1.0 = no smoothing)
RSSI_SIGMA_DB    = 3.0    # assumed RSSI noise, drives per-node weights
FTM_SIGMA_M      = 1.0    # assumed FTM ranging noise


def rssi_to_distance(rssi, rssi0, n):
    """Log-distance path loss: d = d0 * 10^((rssi0 - rssi) / (10 n)), d0 = 1 m."""
    return 10.0 ** ((rssi0 - rssi) / (10.0 * n))


def rssi_distance_sigma(dist, n):
    """1-sigma distance error implied by RSSI_SIGMA_DB of RSSI noise."""
    return dist * (10.0 ** (RSSI_SIGMA_DB / (10.0 * n)) - 1.0)


def solve_position(meas, x0, drone_z, solve_3d):
    """
    meas: list of (anchor_pos ndarray(3), dist, sigma).
    Returns (position ndarray(3), rms residual in meters).
    """
    anchors = np.array([m[0] for m in meas])
    dists = np.array([m[1] for m in meas])
    sigmas = np.array([max(m[2], 1e-3) for m in meas])

    if solve_3d:
        def residuals(p):
            return (np.linalg.norm(anchors - p, axis=1) - dists) / sigmas
        guess = x0
    else:
        def residuals(pxy):
            p = np.array([pxy[0], pxy[1], drone_z])
            return (np.linalg.norm(anchors - p, axis=1) - dists) / sigmas
        guess = x0[:2]

    res = least_squares(residuals, guess, method="lm", max_nfev=200)
    p = res.x if solve_3d else np.array([res.x[0], res.x[1], drone_z])
    unweighted = np.linalg.norm(anchors - p, axis=1) - dists
    return p, float(np.sqrt(np.mean(unweighted ** 2)))


def serial_reader(port, baud, out_q, stop):
    import serial  # pyserial
    while not stop.is_set():
        try:
            with serial.Serial(port, baud, timeout=1) as ser:
                print(f"# opened {port}", file=sys.stderr)
                while not stop.is_set():
                    line = ser.readline().decode(errors="replace").strip()
                    if not line.startswith("{"):
                        continue
                    try:
                        out_q.put(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            print(f"# {port}: {e}; retrying in 2 s", file=sys.stderr)
            time.sleep(2)


def sim_reader(cfg, out_q, stop):
    """Synthetic drone flying a circle — lets you test the solver end to end."""
    n = cfg["path_loss_n"]
    t0 = time.time()
    while not stop.is_set():
        t = time.time() - t0
        true_pos = np.array([4 + 3 * math.cos(0.3 * t),
                             3.5 + 3 * math.sin(0.3 * t),
                             cfg["drone_z"]])
        for node_id, nc in cfg["nodes"].items():
            d = np.linalg.norm(true_pos - np.array(nc["pos"]))
            rssi = nc["rssi0"] - 10 * n * math.log10(max(d, 0.1))
            rssi += np.random.normal(0, RSSI_SIGMA_DB)
            out_q.put({"node": int(node_id), "rssi": round(rssi),
                       "n": 10, "t": int(t * 1000)})
        out_q.put({"_true": true_pos.tolist()})
        time.sleep(SOLVE_INTERVAL_S)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hub", help="serial port of the hub node")
    ap.add_argument("--port", action="append", default=[],
                    help="extra serial port (FTM node); repeatable")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--plot", action="store_true", help="live matplotlib view")
    ap.add_argument("--sim", action="store_true", help="synthetic data, no hardware")
    ap.add_argument("--solve-3d", action="store_true",
                    help="solve z too (needs >=4 nodes at different heights)")
    args = ap.parse_args()

    with open(args.config) as f:
        cfg = json.load(f)
    n_pl = cfg["path_loss_n"]
    drone_z = cfg.get("drone_z", 1.5)
    node_cfg = {int(k): v for k, v in cfg["nodes"].items()}

    if not args.sim and not args.hub and not args.port:
        ap.error("give --hub and/or --port, or --sim")

    q, stop = queue.Queue(), threading.Event()
    threads = []
    if args.sim:
        threads.append(threading.Thread(target=sim_reader, args=(cfg, q, stop), daemon=True))
    for port in ([args.hub] if args.hub else []) + args.port:
        threads.append(threading.Thread(target=serial_reader,
                                        args=(port, args.baud, q, stop), daemon=True))
    for t in threads:
        t.start()

    plot = None
    if args.plot:
        import matplotlib.pyplot as plt
        plt.ion()
        fig, ax = plt.subplots()
        ax.set_aspect("equal")
        ax.set_xlabel("x [m]"); ax.set_ylabel("y [m]"); ax.set_title("drone fix")
        anch = np.array([v["pos"] for v in node_cfg.values()])
        ax.plot(anch[:, 0], anch[:, 1], "k^", label="nodes")
        dot, = ax.plot([], [], "ro", label="drone")
        trail, = ax.plot([], [], "r-", alpha=0.3)
        pad = 2
        ax.set_xlim(anch[:, 0].min() - pad, anch[:, 0].max() + pad)
        ax.set_ylim(anch[:, 1].min() - pad, anch[:, 1].max() + pad)
        ax.legend()
        plot = (plt, fig, dot, trail, [])

    latest = {}          # node_id -> (dist, sigma, wall_time)
    est = np.array([np.mean([v["pos"][0] for v in node_cfg.values()]),
                    np.mean([v["pos"][1] for v in node_cfg.values()]),
                    drone_z])
    last_solve = 0.0

    try:
        while True:
            try:
                msg = q.get(timeout=SOLVE_INTERVAL_S)
            except queue.Empty:
                msg = None

            now = time.time()
            if msg and "node" in msg:
                nid = int(msg["node"])
                if nid in node_cfg:
                    if "dist" in msg:                       # FTM report
                        latest[nid] = (float(msg["dist"]), FTM_SIGMA_M, now)
                    elif "rssi" in msg:                     # RSSI report
                        d = rssi_to_distance(float(msg["rssi"]),
                                             node_cfg[nid]["rssi0"], n_pl)
                        latest[nid] = (d, rssi_distance_sigma(d, n_pl), now)

            if now - last_solve < SOLVE_INTERVAL_S:
                continue
            last_solve = now

            meas = [(np.array(node_cfg[nid]["pos"]), d, s)
                    for nid, (d, s, ts) in latest.items()
                    if now - ts <= MEAS_MAX_AGE_S]
            min_nodes = 4 if args.solve_3d else 3
            if len(meas) < min_nodes:
                continue

            pos, resid = solve_position(meas, est, drone_z, args.solve_3d)
            est = EMA_ALPHA * pos + (1 - EMA_ALPHA) * est
            print(json.dumps({"t": round(now, 2),
                              "x": round(float(est[0]), 2),
                              "y": round(float(est[1]), 2),
                              "z": round(float(est[2]), 2),
                              "nodes_used": len(meas),
                              "resid_m": round(resid, 2)}), flush=True)

            if plot:
                plt_, fig, dot, trail, hist = plot
                hist.append(est[:2].copy())
                hist[:] = hist[-100:]
                h = np.array(hist)
                dot.set_data([est[0]], [est[1]])
                trail.set_data(h[:, 0], h[:, 1])
                fig.canvas.draw_idle()
                plt_.pause(0.001)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()


if __name__ == "__main__":
    main()
