#!/usr/bin/env python3
"""
geometry.py — dilution-of-precision (DOP) analysis for node layouts.

Answers "can this radar sense 3D?" quantitatively, and tells you where to
put the nodes.

Range-based multilateration turns *range* errors into *position* errors by a
factor set purely by geometry — the dilution of precision. For nodes at p_i
and a drone at p, the unit line-of-sight vectors u_i = (p - p_i)/|p - p_i|
form the geometry matrix G (row i = u_i^T). With per-node range sigma s_i the
position covariance is

    C = (G^T W G)^-1 ,   W = diag(1/s_i^2)

Because W already carries the per-node range sigmas, C is in m^2 — so this
tool reports **1-sigma position error in METRES**, not a unitless DOP:

    sigma_h = sqrt(C_xx + C_yy)      sigma_v = sqrt(C_zz)

The unitless geometric DOP (what you'd get with a common range sigma) is
reported alongside, as is the vertical penalty sigma_v / sigma_h.

The key result this tool demonstrates: with all nodes at the SAME height
(coplanar), the vertical component is near-unobservable for a drone flying
near that height — every line of sight is nearly horizontal, so d(range)/dz
tends to 0 and VDOP explodes. Coplanar anchors also leave a genuine up/down
mirror ambiguity: a drone at +h and at -h produce identical ranges.

Usage:
    python geometry.py                      # analyze config.json + alternatives
    python geometry.py --layout tall        # analyze one layout
    python geometry.py --map                # HDOP/VDOP maps over the area
"""

import argparse
import itertools
import json
import math
import pathlib

import numpy as np

BASE = pathlib.Path(__file__).resolve().parent
RSSI_SIGMA_DB = 3.0


def rssi_range_sigma(d, n=2.1, sigma_db=RSSI_SIGMA_DB):
    """1-sigma range error at distance d for RSSI ranging (error grows with d)."""
    return d * (10.0 ** (sigma_db / (10.0 * n)) - 1.0)


def dop(nodes, p, sigma_fn=rssi_range_sigma, ranging="rssi"):
    """Return (sigma_h, sigma_v, sigma_3d) in METRES for anchors `nodes` (N,3)
    at point p (3,). Returns (nan, nan, nan) if the geometry is singular
    (i.e. that axis is unobservable).
    """
    nodes = np.asarray(nodes, float)
    p = np.asarray(p, float)
    d = np.linalg.norm(nodes - p, axis=1)
    if np.any(d < 1e-6):
        return (np.nan,) * 3
    U = (p - nodes) / d[:, None]              # unit LOS vectors, node -> drone
    if ranging == "rssi":
        s = np.array([sigma_fn(di) for di in d])
    else:                                      # constant-sigma (UWB/FTM style)
        s = np.full_like(d, 0.2)
    W = np.diag(1.0 / s ** 2)
    try:
        C = np.linalg.inv(U.T @ W @ U)
    except np.linalg.LinAlgError:
        return (np.nan,) * 3
    if np.any(np.diag(C) < 0):
        return (np.nan,) * 3
    sigma_h = math.sqrt(C[0, 0] + C[1, 1])
    sigma_v = math.sqrt(C[2, 2])
    sigma_3d = math.sqrt(C[0, 0] + C[1, 1] + C[2, 2])
    return sigma_h, sigma_v, sigma_3d


def geometric_dop(nodes, p):
    """Unitless HDOP/VDOP (common range sigma), the classic GPS-style figure."""
    nodes = np.asarray(nodes, float)
    p = np.asarray(p, float)
    d = np.linalg.norm(nodes - p, axis=1)
    U = (p - nodes) / d[:, None]
    try:
        C = np.linalg.inv(U.T @ U)
    except np.linalg.LinAlgError:
        return np.nan, np.nan
    if np.any(np.diag(C) < 0):
        return np.nan, np.nan
    return math.sqrt(C[0, 0] + C[1, 1]), math.sqrt(C[2, 2])


def cond_number(nodes, p):
    """Condition number of the geometry matrix — how close to degenerate."""
    nodes = np.asarray(nodes, float)
    d = np.linalg.norm(nodes - p, axis=1)
    U = (p - nodes) / d[:, None]
    return np.linalg.cond(U)


def coplanar_span(nodes):
    """Vertical spread of the anchors. ~0 means coplanar -> mirror ambiguity:
    a drone at height h above the node plane and its mirror at -h produce
    identical ranges, so the solver locks onto whichever side it starts on."""
    z = np.asarray(nodes, float)[:, 2]
    return float(z.max() - z.min())


# ----------------------------------------------------------------------
# candidate layouts
# ----------------------------------------------------------------------

def load_config_layout():
    try:
        cfg = json.loads((BASE / "config.json").read_text())
        return np.array([v["pos"] for v in cfg["nodes"].values()], float)
    except Exception:
        return np.array([[0, 0, 1], [8, 0, 1], [4, 7, 1]], float)


LAYOUTS = {
    "config": ("your config.json (as-is)", load_config_layout),
    "flat3": ("3 nodes, all at 1 m (coplanar)",
              lambda: np.array([[0, 0, 1], [8, 0, 1], [4, 7, 1]], float)),
    "flat4": ("4 nodes, all at 1 m (still coplanar)",
              lambda: np.array([[0, 0, 1], [8, 0, 1], [8, 7, 1], [0, 7, 1]], float)),
    "tall": ("4 nodes, staggered heights 0.3/1.5/3.0 m",
             lambda: np.array([[0, 0, 0.3], [8, 0, 3.0], [8, 7, 0.3], [0, 7, 3.0]], float)),
    "mast": ("3 ground nodes + 1 on a 5 m mast",
             lambda: np.array([[0, 0, 1], [8, 0, 1], [4, 7, 1], [4, 3.5, 5.0]], float)),
}


def summarize(nodes, label, alts=(1.5, 3.0, 6.0), ranging="rssi"):
    """Print expected 1-sigma errors at the array centroid vs drone altitude."""
    c = nodes[:, :2].mean(axis=0)
    zs = sorted(set(np.round(nodes[:, 2], 2).tolist()))
    span = coplanar_span(nodes)
    print(f"\n  {label}")
    print(f"    node heights: {zs} m   (n={len(nodes)})")
    if span < 0.5:
        print(f"    !! COPLANAR (vertical spread {span:.1f} m) — altitude is mirror-"
              f"ambiguous:\n       two solutions exist about the node plane and range "
              f"data cannot\n       distinguish them. Reported sigma_v understates this.")
    print(f"    {'drone alt':>10} | {'sigma_h':>8} | {'sigma_v':>9} | {'v/h':>5} | verdict")
    print(f"    {'-'*10}-+-{'-'*8}-+-{'-'*9}-+-{'-'*5}-+---------")
    for z in alts:
        h, v, _ = dop(nodes, [c[0], c[1], z], ranging=ranging)
        if math.isnan(v) or v > 999:
            print(f"    {z:>8.1f} m | {h:7.2f} m | {'  inf':>9} | {'--':>5} | "
                  f"SINGULAR — altitude unobservable")
            continue
        ratio = v / h
        if v > 8:     verdict = "unusable altitude"
        elif v > 4:   verdict = "poor altitude"
        elif v > 2:   verdict = "usable altitude"
        else:         verdict = "good altitude"
        print(f"    {z:>8.1f} m | {h:7.2f} m | {v:8.1f} m | {ratio:5.1f} | {verdict}")


def dop_map(nodes, z=1.5, extent=None, step=0.75, ranging="rssi"):
    """Grid of (HDOP, VDOP) over the area at altitude z."""
    if extent is None:
        pad = 3.0
        extent = (nodes[:, 0].min() - pad, nodes[:, 0].max() + pad,
                  nodes[:, 1].min() - pad, nodes[:, 1].max() + pad)
    xs = np.arange(extent[0], extent[1] + 1e-9, step)
    ys = np.arange(extent[2], extent[3] + 1e-9, step)
    H = np.zeros((len(ys), len(xs)))
    V = np.zeros((len(ys), len(xs)))
    for j, y in enumerate(ys):
        for i, x in enumerate(xs):
            h, v, _ = dop(nodes, [x, y, z], ranging=ranging)
            H[j, i], V[j, i] = h, v
    return xs, ys, H, V


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--layout", choices=list(LAYOUTS), help="analyze just one layout")
    ap.add_argument("--map", action="store_true", help="print an HDOP/VDOP map")
    ap.add_argument("--ranging", default="rssi", choices=["rssi", "uwb"],
                    help="error model: rssi (grows with range) or uwb (constant)")
    args = ap.parse_args()

    print("=" * 74)
    print("  GEOMETRY ANALYSIS — can this layout resolve 3D (altitude)?")
    print(f"  ranging model: {args.ranging}"
          f"{' (sigma grows with range, 3 dB RSSI)' if args.ranging=='rssi' else ' (constant 0.2 m)'}")
    print("  sigma_h / sigma_v = expected 1-sigma position error in METRES.")
    print("  v/h = the vertical penalty this geometry imposes.")
    print("=" * 74)

    names = [args.layout] if args.layout else list(LAYOUTS)
    for name in names:
        label, fn = LAYOUTS[name]
        nodes = fn()
        summarize(nodes, f"[{name}] {label}", ranging=args.ranging)

    if args.map:
        nodes = LAYOUTS[args.layout or "config"][1]()
        xs, ys, H, V = dop_map(nodes, ranging=args.ranging)
        print(f"\n  HDOP map at z=1.5 m (rows = y descending):")
        for j in range(len(ys) - 1, -1, -1):
            print("   " + " ".join(f"{H[j,i]:5.1f}" for i in range(len(xs))))
        print(f"\n  VDOP map at z=1.5 m:")
        for j in range(len(ys) - 1, -1, -1):
            print("   " + " ".join(
                ("  inf" if math.isnan(V[j, i]) or V[j, i] > 999 else f"{V[j,i]:5.0f}")
                for i in range(len(xs))))

    print("\n" + "=" * 68)


if __name__ == "__main__":
    main()
