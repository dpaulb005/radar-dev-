#!/usr/bin/env python3
"""
guidance.py — interception guidance laws + attitude/RC mapping.

Given the interceptor and target states (position, velocity) from the ground
tracker, compute a world-frame acceleration command, then convert it to
quad attitude setpoints and finally to espnow-rclink RC channel microseconds
for the "commander" firmware to relay to the interceptor.

Three guidance laws:
  * track         — cascaded position + velocity controller with target-
                    velocity feed-forward. Recommended default: it settles
                    ONTO a maneuvering target instead of trailing it. This is
                    the standard external-tracker ("mocap drone lab") law.
  * pure_pursuit  — naive: steers velocity toward the target's current
                    position. Simple, but always lags a moving target
                    (a pursuit curve) — kept mainly for comparison.
  * pro_nav       — True Proportional Navigation; nulls the line-of-sight
                    rotation rate to lead a fast crossing target. Needs a
                    (noisier) target velocity estimate.

All positions/velocities are in a local ENU-ish world frame (meters, m/s).
Interception here is treated in the horizontal plane at a roughly common
altitude — see docs/interception.md for why (3 coplanar ground nodes give
poor vertical resolution).
"""

import math
import numpy as np

G = 9.81


def _unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else np.zeros_like(v)


def predict(p_t, v_t, lead):
    """Latency-compensate: propagate the target forward through the total
    loop delay (sensor + age-of-fix + tilt-to-accel lag, ~0.4-0.7 s) so the
    interceptor aims where the target *will* be, not where it was."""
    if v_t is None or lead <= 0:
        return np.asarray(p_t, float)
    return np.asarray(p_t, float) + np.asarray(v_t, float) * lead


# ----------------------------------------------------------------------
# guidance laws → desired world-frame acceleration (horizontal, 2-vector)
# ----------------------------------------------------------------------

def track(p_i, v_i, p_t, v_t=None, kp=1.6, kv=2.6, v_max=12.0, a_max=None, lead=0.0):
    """Cascaded position+velocity tracking with target-velocity feed-forward.

        v_des = v_t + kp * (p_t - p_i)         (clamped to v_max)
        a     = kv * (v_des - v_i)             (saturated to a_max)

    The feed-forward term `v_t` is what lets the interceptor *match* a moving
    target and drive the position error to zero, rather than trailing it the
    way naive pursuit does. `v_t` may be a noisy estimate — even a rough one
    helps. This is the law used for external-tracker (motion-capture) drone
    control.
    """
    p_i = np.asarray(p_i, float); v_i = np.asarray(v_i, float)
    ff = np.zeros(2) if v_t is None else np.asarray(v_t, float)
    v_des = ff + kp * (predict(p_t, v_t, lead) - p_i)
    s = np.linalg.norm(v_des)
    if s > v_max:
        v_des = v_des / s * v_max
    return _saturate(kv * (v_des - v_i), a_max)


def pure_pursuit(p_i, v_i, p_t, speed_cmd, k=3.0, a_max=None):
    """Proportional velocity guidance.

    Drives the interceptor velocity toward `speed_cmd` along the
    line-of-sight to the target's current position.

        v_des = speed_cmd * unit(p_t - p_i)
        a     = k * (v_des - v_i)              (saturated to a_max)
    """
    los = np.asarray(p_t) - np.asarray(p_i)
    v_des = _unit(los) * speed_cmd
    a = k * (v_des - np.asarray(v_i))
    return _saturate(a, a_max)


def pro_nav(p_i, v_i, p_t, v_t, N=4.0, speed_cmd=None, k_close=1.5, a_max=None):
    """True Proportional Navigation (vector form).

    LOS rotation-rate vector (Zarchan, *Tactical and Strategic Missile
    Guidance*):

        R      = p_t - p_i            (relative position)
        V_r    = v_t - v_i            (relative velocity)
        Omega  = (R x V_r) / (R . R)  (LOS angular velocity, rad/s)
        a_pn   = N * (V_r x Omega)    (perpendicular to V_r; nulls LOS rate)

    Pure PN assumes closing speed already exists; a quad starts from rest, so
    we add a closing term along the LOS to build/hold `speed_cmd` of closing
    velocity. In 2-D the cross products reduce to scalars, which we re-embed.
    """
    R = np.asarray(p_t) - np.asarray(p_i)
    V_r = np.asarray(v_t) - np.asarray(v_i)
    r2 = float(R @ R)
    if r2 < 1e-9:
        return np.zeros(2)

    # 2-D cross products are scalars (z-components):
    omega_z = (R[0] * V_r[1] - R[1] * V_r[0]) / r2          # Omega (scalar)
    # a_pn = N * (V_r x Omega): (Vx,Vy) x (0,0,omega_z) = (Vy*omega_z, -Vx*omega_z)
    a_pn = N * np.array([V_r[1] * omega_z, -V_r[0] * omega_z])

    a_close = np.zeros(2)
    if speed_cmd is not None:
        los_hat = _unit(R)
        closing = -float(V_r @ los_hat)          # +ve when closing
        a_close = k_close * (speed_cmd - closing) * los_hat

    return _saturate(a_pn + a_close, a_max)


def _saturate(a, a_max):
    if a_max is None:
        return a
    n = np.linalg.norm(a)
    return a if n <= a_max else a / n * a_max


def max_accel(max_lean_deg):
    """Horizontal acceleration available at a given max lean angle."""
    return G * math.tan(math.radians(max_lean_deg))


# ----------------------------------------------------------------------
# world-frame acceleration → quad attitude setpoints
# ----------------------------------------------------------------------

def accel_to_attitude(a_h, yaw, max_lean_deg=35.0):
    """Convert horizontal world accel (2-vector) + vehicle yaw to lean angles.

        theta = atan2(|a_h|, g)                         (tilt magnitude)
        the tilt is directed along bearing atan2(ay, ax) in the world; rotate
        into the body frame by -yaw to split into pitch (forward) and roll
        (right).

    `yaw` is the vehicle heading (rad, 0 = +x/world-east, CCW +). Returns
    (roll_rad, pitch_rad) clamped to +/- max_lean.
    """
    ax, ay = float(a_h[0]), float(a_h[1])
    tilt = math.atan2(math.hypot(ax, ay), G)
    tilt = min(tilt, math.radians(max_lean_deg))
    bearing = math.atan2(ay, ax)          # world-frame direction of accel
    rel = bearing - yaw                    # body-frame direction
    pitch = tilt * math.cos(rel)           # forward tilt component
    roll = tilt * math.sin(rel)            # right tilt component
    return roll, pitch


# ----------------------------------------------------------------------
# attitude + throttle/yaw → RC channel microseconds
# ----------------------------------------------------------------------

# espnow-rclink full-resolution channel span (channels 0-3): 880..2120 us,
# center 1500. Order below matches a typical esp-fc AETR map; VERIFY against
# your `get pin`/rc config and reorder CHANNEL_ORDER if needed.
RC_MIN, RC_MID, RC_MAX = 880, 1500, 2120
RC_HALF = (RC_MAX - RC_MIN) / 2.0
CHANNEL_ORDER = ("roll", "pitch", "throttle", "yaw")   # AETR


def _stick(frac):
    """frac in [-1, 1] -> microseconds."""
    return int(round(RC_MID + max(-1.0, min(1.0, frac)) * RC_HALF))


def _throttle_us(frac01):
    return int(round(RC_MIN + max(0.0, min(1.0, frac01)) * (RC_MAX - RC_MIN)))


def attitude_to_rc(roll, pitch, throttle01, yaw_rate=0.0,
                   max_lean_deg=35.0, max_yaw_rate=math.radians(180)):
    """Map lean angles (rad), throttle [0,1], yaw-rate (rad/s) to RC dict.

    Returns {"roll":us,"pitch":us,"throttle":us,"yaw":us} and an ordered
    list `channels` following CHANNEL_ORDER for the commander firmware.
    """
    lean = math.radians(max_lean_deg)
    d = {
        "roll": _stick(roll / lean),
        "pitch": _stick(pitch / lean),
        "throttle": _throttle_us(throttle01),
        "yaw": _stick(yaw_rate / max_yaw_rate),
    }
    d["channels"] = [d[name] for name in CHANNEL_ORDER]
    return d


def compute_rc(p_i, v_i, p_t, v_t, yaw, *, law="track",
               speed_cmd=10.0, max_lean_deg=35.0, throttle_hover=0.5,
               yaw_to_target=True, N=4.0, lead=0.0):
    """End-to-end: states -> RC channels for the interceptor.

    Throttle is held near hover here (open-loop); real altitude hold needs
    baro feedback — see docs/interception.md. `yaw_to_target` optionally
    commands a yaw rate to point the nose at the target (helps if control is
    body-frame rather than world-frame).
    """
    a_max = max_accel(max_lean_deg)
    p_t_lead = predict(p_t, v_t, lead)
    if law == "pro_nav":
        a_h = pro_nav(p_i, v_i, p_t_lead, v_t, N=N, speed_cmd=speed_cmd, a_max=a_max)
    elif law == "pure_pursuit":
        a_h = pure_pursuit(p_i, v_i, p_t_lead, speed_cmd, a_max=a_max)
    else:  # track (default)
        a_h = track(p_i, v_i, p_t, v_t, v_max=speed_cmd, a_max=a_max, lead=lead)

    # NOTE: accel_to_attitude splits the world-frame accel into roll/pitch
    # using `yaw`. The SIGN of the roll term depends on your roll convention
    # (positive-roll-right vs -left) — a wrong sign flies the drone AWAY from
    # the target. Resolve it empirically on the bench (calibration dance)
    # before any free flight. See docs/interception.md sec. Heading.
    roll, pitch = accel_to_attitude(a_h, yaw, max_lean_deg)

    yaw_rate = 0.0
    if yaw_to_target:
        los = np.asarray(p_t) - np.asarray(p_i)
        want = math.atan2(los[1], los[0])
        err = math.atan2(math.sin(want - yaw), math.cos(want - yaw))
        yaw_rate = max(-1.0, min(1.0, 1.5 * err)) * math.radians(120)

    rc = attitude_to_rc(roll, pitch, throttle_hover, yaw_rate, max_lean_deg)
    rc["accel_h"] = [float(a_h[0]), float(a_h[1])]
    return rc


if __name__ == "__main__":
    # quick sanity check
    p_i = np.array([0.0, 0.0]); v_i = np.array([0.0, 0.0])
    p_t = np.array([5.0, 5.0]); v_t = np.array([1.0, 0.0])
    for law in ("track", "pure_pursuit", "pro_nav"):
        rc = compute_rc(p_i, v_i, p_t, v_t, yaw=0.0, law=law, speed_cmd=10)
        print(f"{law:12s} accel_h={np.round(rc['accel_h'],2)}  "
              f"channels(AETR)={rc['channels']}")
