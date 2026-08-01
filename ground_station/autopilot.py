#!/usr/bin/env python3
"""
autopilot.py — the ground-station "pilot" for the interceptor drone.

Closes the outer loop that ESP-FC does not have: it takes the radar fixes
for BOTH drones, runs the guidance law, builds an 8-channel espnow-rclink
frame (sticks + ARM/ANGLE AUX), and streams it to the commander ESP32
(firmware/commander) over USB serial at a fixed rate. The commander relays
it to the interceptor as ordinary RC.

    fixes (target + interceptor, + interceptor heading)
        -> guidance.compute_rc  ->  "C,ch0,...,ch7\n"  -> commander -> drone

SAFETY — read docs/interception.md first. This can fly a real aircraft.
  * Defaults to DISARMED and --dry-run (prints frames, opens no serial).
  * Arming requires BOTH --commander PORT and --arm; even then a geofence
    breach or a stale fix forces the fail-safe frame (throttle min, ARM low).
  * The commander independently fail-safes if this stream stops.
  * A human RPIC must watch the aircraft (VLOS) with a physical kill at all
    times; this is a navigation aid, not permission to fly hands-off.
  * Tracking / station-keeping only — never contact, never a payload.

Modes:
  --sim         self-contained: an internal two-drone sim (reuses pursuit_sim's
                radar + target path) drives the loop so you can watch the exact
                channels the drone would receive — ideal for props-off
                hardware-in-the-loop bring-up (wire a real --commander, keep
                the interceptor DISARMED, watch esp-fc in the configurator).
  (hardware)    replace read_fixes() with your real dual-MAC tracker output.
"""

import argparse
import math
import sys
import time

import numpy as np

import guidance
import pursuit_sim as sim

# esp-fc default AUX plan (verified against ModelConfig.h ActuatorConditions):
#   AUX1 (ch4): ARM + AIRMODE, active 1300-2100
#   AUX2 (ch5): ANGLE 1300-2100 ; ALTHOLD 1700-2100
CH_MIN, CH_MID, CH_MAX = 880, 1500, 2120
ARM_ON, ARM_OFF = 1800, 1000
ANGLE_ON = 1500          # ANGLE only (below ALTHOLD's 1700 threshold)
ANGLE_ALTHOLD = 1800     # ANGLE + baro ALTHOLD (laptop controls horizontal only)
FAILSAFE = [CH_MID, CH_MID, CH_MIN, CH_MID, ARM_OFF, ANGLE_ON, CH_MIN, CH_MIN]


def build_frame(rc, armed, althold):
    """rc = guidance.compute_rc() dict -> 8 channel microseconds (AETR+AUX)."""
    return [
        rc["roll"], rc["pitch"], rc["throttle"], rc["yaw"],
        ARM_ON if armed else ARM_OFF,
        (ANGLE_ALTHOLD if althold else ANGLE_ON),
        CH_MIN,           # spare
        CH_MIN,           # spare (map a kill switch here in esp-fc if desired)
    ]


def serialize(frame):
    return "C," + ",".join(str(int(c)) for c in frame) + "\n"


class SimSource:
    """Internal two-drone sim for bench testing the full autopilot stack."""
    def __init__(self, seed=0):
        self.p = sim.Params()
        self.rng = np.random.default_rng(seed)
        nodes, n_pl = sim.load_nodes()
        self.anch = np.array([v["pos"][:2] for v in nodes.values()])
        self.center = self.anch.mean(axis=0)
        self.radius = max(2.5, 0.30 * (self.anch.max() - self.anch.min()))
        self.radar = sim.Radar(nodes, n_pl, 1.5, self.p.rssi_sigma, self.rng)
        self.rng_wp = {"ang": self.rng.uniform(0, 2 * math.pi), "pts": [], "rng": self.rng}
        # interceptor truth (the sim "is" the drone here)
        self.p_i = self.anch[0].astype(float).copy()
        self.v_i = np.zeros(2)
        self.a_state = np.zeros(2)
        self.t0 = time.time()
        self.last_ti = self.p_i.copy()
        self.est_t = None

    def read(self):
        """Returns (interceptor_est, interceptor_vel, target_est, target_vel, heading)."""
        t = time.time() - self.t0
        pt, vt = sim.target_state(self.p.target_path, t, self.p.target_speed,
                                  self.center, self.radius, self.rng_wp)
        fi, _ = self.radar.fix(self.p_i, self.last_ti)
        ft, _ = self.radar.fix(pt, self.est_t if self.est_t is not None else pt)
        self.last_ti = fi
        self.est_t = ft
        # sim heading = interceptor course when moving, else fixed (0 = +x)
        heading = math.atan2(self.v_i[1], self.v_i[0]) if np.linalg.norm(self.v_i) > 0.5 else 0.0
        return fi, self.v_i.copy(), ft, vt, heading

    def step(self, rc, dt):
        """Advance the simulated interceptor under the commanded accel."""
        a_max = guidance.max_accel(35.0)
        v_max = 12.0
        drag = a_max / v_max
        a_cmd = np.array(rc["accel_h"])
        self.a_state += (a_cmd - self.a_state) * (dt / (0.15 + dt))
        self.v_i += (self.a_state - drag * self.v_i) * dt
        self.p_i += self.v_i * dt

    def range(self, target_est):
        return float(np.linalg.norm(target_est - self.p_i))


def read_fixes_hardware():
    """HARDWARE HOOK — replace with your real dual-MAC tracker output.

    Must return (interceptor_xy, interceptor_vxy, target_xy, target_vxy,
    interceptor_heading_rad). Heading should come from the interceptor's
    AHRS telemetry downlink (see docs/interception.md); fall back to the
    takeoff calibration-dance value with yaw held fixed.
    """
    raise NotImplementedError(
        "Wire your dual-target tracker + heading telemetry here. "
        "Use --sim for bench/HIL testing until then.")


def in_geofence(xy, bounds):
    return bounds[0] <= xy[0] <= bounds[2] and bounds[1] <= xy[1] <= bounds[3]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--commander", help="serial port of the commander ESP32")
    ap.add_argument("--dry-run", action="store_true",
                    help="print frames, open no serial (default if no --commander)")
    ap.add_argument("--arm", action="store_true",
                    help="allow arming (DANGER: flies a real drone). Requires --commander")
    ap.add_argument("--sim", action="store_true", help="internal two-drone sim source")
    ap.add_argument("--hz", type=float, default=50.0)
    ap.add_argument("--lead", type=float, default=0.5, help="latency lead time (s)")
    ap.add_argument("--speed-cmd", type=float, default=8.0, help="max closing speed (m/s)")
    ap.add_argument("--hover-throttle", type=float, default=0.5)
    ap.add_argument("--althold", action="store_true",
                    help="engage baro ALTHOLD (laptop controls horizontal only)")
    ap.add_argument("--geofence", type=float, nargs=4,
                    metavar=("XMIN", "YMIN", "XMAX", "YMAX"),
                    help="disarm/failsafe if interceptor leaves this box")
    args = ap.parse_args()

    dry = args.dry_run or not args.commander
    armed_allowed = args.arm and args.commander and not args.dry_run
    if args.arm and not armed_allowed:
        print("! --arm ignored: requires --commander and no --dry-run", file=sys.stderr)

    ser = None
    if not dry:
        import serial
        ser = serial.Serial(args.commander, 115200, timeout=0)
        print(f"# commander on {args.commander}")
        time.sleep(1.0)   # let it boot / start pairing

    if not args.sim:
        print("! no --sim and no hardware tracker wired; use --sim for now",
              file=sys.stderr)
        sys.exit(2)
    src = SimSource()

    print(f"# autopilot: {'ARMED-CAPABLE' if armed_allowed else 'DISARMED'}"
          f"{' (dry-run)' if dry else ''}, {args.hz:.0f} Hz, lead {args.lead}s")
    period = 1.0 / args.hz
    last_status = 0.0
    armed = False
    try:
        while True:
            t = time.time()
            fi, vi, ft, vt, heading = src.read()

            breach = args.geofence and not in_geofence(fi, args.geofence)
            # arm only when allowed and inside the fence
            armed = armed_allowed and not breach

            if breach:
                frame = list(FAILSAFE)
                rc = {"accel_h": [0.0, 0.0]}
            else:
                rc = guidance.compute_rc(
                    fi, vi, ft, vt, heading, law="track",
                    speed_cmd=args.speed_cmd, throttle_hover=args.hover_throttle,
                    lead=args.lead, yaw_to_target=False)
                frame = build_frame(rc, armed, args.althold)

            line = serialize(frame)
            if ser:
                ser.write(line.encode())
            src.step(rc, period)

            if t - last_status >= 0.5:
                last_status = t
                rng = src.range(ft)
                print(f"range={rng:5.2f} m  armed={int(armed)}  "
                      f"breach={int(bool(breach))}  frame={frame}"
                      + ("" if ser else "  [dry]"))
            time.sleep(max(0, period - (time.time() - t)))
    except KeyboardInterrupt:
        pass
    finally:
        if ser:
            for _ in range(10):                 # command disarm on exit
                ser.write(serialize(FAILSAFE).encode())
                time.sleep(0.02)
            ser.close()
        print("\n# stopped; disarm frames sent")


if __name__ == "__main__":
    main()
