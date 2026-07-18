#!/usr/bin/env python3
"""
calibrate.py — measure each node's RSSI reference (rssi0 at 1 m).

Procedure, one node at a time (or all at once if you can place the drone
1 m from each in turn):

  1. Power the drone beacon and hold it a known distance from the node,
     same height as the node antenna, clear line of sight.
  2. Run:  python calibrate.py --hub /dev/ttyUSB0 --dist 1.0 --seconds 20
  3. Copy the reported rssi0 values into config.json.

If --dist is not 1.0 the tool back-computes rssi0 using the path-loss
exponent from config.json.
"""

import argparse
import json
import math
import statistics
import sys
import time

import serial


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hub", required=True, help="serial port of the hub node")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--dist", type=float, default=1.0,
                    help="actual drone-to-node distance in meters during capture")
    ap.add_argument("--seconds", type=float, default=20.0)
    ap.add_argument("--config", default="config.json")
    args = ap.parse_args()

    with open(args.config) as f:
        n_pl = json.load(f)["path_loss_n"]

    samples = {}  # node_id -> [rssi, ...]
    t_end = time.time() + args.seconds
    print(f"# capturing for {args.seconds:.0f}s at d={args.dist} m ...", file=sys.stderr)

    with serial.Serial(args.hub, args.baud, timeout=1) as ser:
        while time.time() < t_end:
            line = ser.readline().decode(errors="replace").strip()
            if not line.startswith("{"):
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "node" in msg and "rssi" in msg:
                samples.setdefault(int(msg["node"]), []).append(float(msg["rssi"]))

    if not samples:
        print("no reports received — check hub port, channel, and DRONE_MAC", file=sys.stderr)
        sys.exit(1)

    print(f"\n{'node':>4} {'reports':>8} {'median RSSI':>12} {'rssi0 @1m':>10}")
    for nid in sorted(samples):
        med = statistics.median(samples[nid])
        # rssi0 = rssi(d) + 10 n log10(d / 1m)
        rssi0 = med + 10.0 * n_pl * math.log10(args.dist)
        print(f"{nid:>4} {len(samples[nid]):>8} {med:>12.1f} {rssi0:>10.1f}")
    print("\npaste the rssi0 column into config.json under each node")


if __name__ == "__main__":
    main()
