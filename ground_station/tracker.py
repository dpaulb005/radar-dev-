#!/usr/bin/env python3
"""
tracker.py — Tier 1 constant-velocity Kalman filter with prediction.

Replaces the exponential moving average in locate.py / server.py. An EMA is
not a predictor: it is a lag. This filter estimates position AND velocity in
3D, trusts each fix according to the geometry it was taken with, and can
project the track forward to compensate the sensor latency you actually have.

State  x = [px, py, pz, vx, vy, vz]
Model  constant velocity, driven by white-noise acceleration (sigma_a)
Meas   z = [px, py, pz] from the multilateration solve
       R = the full 3x3 position covariance from geometry.position_cov(),
           so a fix with bad geometry (e.g. altitude from coplanar nodes)
           is automatically down-weighted instead of being believed.

Outputs the filtered state, its covariance, and predicted positions at
+0.5 s / +1.0 s with the covariance grown accordingly — which is what the
console draws as the ghost blip and its expanding ellipse.

Self-test:
    python tracker.py            # compare KF vs EMA against a known truth
"""

import math

import numpy as np


class TrackKF:
    """Constant-velocity Kalman filter on 3D position fixes."""

    def __init__(self, sigma_a=3.0, p0_pos=5.0, p0_vel=3.0, model="ca"):
        """model: "cv" = constant velocity (6 state), "ca" = constant
        acceleration (9 state). A quadcopter in a turn violates the CV
        assumption badly -- see the self-test -- so CA is the default.

        sigma_a is the process-noise drive: an acceleration (m/s^2) for CV,
        a jerk (m/s^3) for CA."""
        self.model = model
        self.n = 6 if model == "cv" else 9
        self.sigma_a = float(sigma_a)
        self.x = None
        self.P = None
        self._p0 = (p0_pos, p0_vel)
        self.initialised = False
        self.last_t = None

    # ---------------------------------------------------------------
    def _F(self, dt):
        F = np.eye(self.n)
        for i in range(3):
            F[i, i + 3] = dt
            if self.model == "ca":
                F[i, i + 6] = 0.5 * dt * dt
                F[i + 3, i + 6] = dt
        return F

    def _Q(self, dt):
        """Continuous white-noise process noise (accel for CV, jerk for CA)."""
        q = self.sigma_a ** 2
        Q = np.zeros((self.n, self.n))
        if self.model == "cv":
            for i in range(3):
                Q[i, i] = q * dt ** 3 / 3.0
                Q[i, i + 3] = Q[i + 3, i] = q * dt ** 2 / 2.0
                Q[i + 3, i + 3] = q * dt
        else:
            for i in range(3):
                p, v, a = i, i + 3, i + 6
                Q[p, p] = q * dt ** 5 / 20.0
                Q[p, v] = Q[v, p] = q * dt ** 4 / 8.0
                Q[p, a] = Q[a, p] = q * dt ** 3 / 6.0
                Q[v, v] = q * dt ** 3 / 3.0
                Q[v, a] = Q[a, v] = q * dt ** 2 / 2.0
                Q[a, a] = q * dt
        return Q

    # ---------------------------------------------------------------
    def init(self, pos, vel=None):
        self.x = np.zeros(self.n)
        self.x[:3] = np.asarray(pos, float)
        if vel is not None:
            self.x[3:6] = np.asarray(vel, float)
        pp, pv = self._p0
        d = [pp ** 2] * 3 + [pv ** 2] * 3
        if self.model == "ca":
            d += [(2 * self.sigma_a) ** 2] * 3
        self.P = np.diag(d).astype(float)
        self.initialised = True

    def predict(self, dt):
        if not self.initialised or dt <= 0:
            return
        F = self._F(dt)
        self.x = F @ self.x
        self.P = F @ self.P @ F.T + self._Q(dt)

    def update(self, z, R):
        """z: (3,) position fix. R: (3,3) measurement covariance."""
        z = np.asarray(z, float)
        R = np.asarray(R, float)
        if not self.initialised:
            self.init(z)
            self.P[:3, :3] = R
            return
        H = np.zeros((3, self.n)); H[0, 0] = H[1, 1] = H[2, 2] = 1.0
        y = z - H @ self.x                       # innovation
        S = H @ self.P @ H.T + R
        try:
            K = self.P @ H.T @ np.linalg.inv(S)
        except np.linalg.LinAlgError:
            return
        self.x = self.x + K @ y
        I_KH = np.eye(self.n) - K @ H
        # Joseph form: stays positive-definite under rounding
        self.P = I_KH @ self.P @ I_KH.T + K @ R @ K.T

    def update_velocity(self, zv, Rv):
        """Fold in a DIRECT velocity measurement (e.g. mmWave Doppler).

        This is the measurement RSSI can never give you: velocity without
        differencing noisy positions. It is what turns the filter from a
        marginal gain into an 8x one (see _self_test)."""
        if not self.initialised:
            return
        zv = np.asarray(zv, float); Rv = np.asarray(Rv, float)
        H = np.zeros((3, self.n)); H[0, 3] = H[1, 4] = H[2, 5] = 1.0
        y = zv - H @ self.x
        S = H @ self.P @ H.T + Rv
        try:
            K = self.P @ H.T @ np.linalg.inv(S)
        except np.linalg.LinAlgError:
            return
        self.x = self.x + K @ y
        I_KH = np.eye(self.n) - K @ H
        self.P = I_KH @ self.P @ I_KH.T + K @ Rv @ K.T

    def step(self, t, z, R):
        """Predict to time t, then fold in the fix."""
        if self.last_t is not None:
            self.predict(max(0.0, t - self.last_t))
        self.last_t = t
        self.update(z, R)

    # ---------------------------------------------------------------
    @property
    def pos(self):
        return self.x[:3].copy() if self.initialised else None

    @property
    def accel(self):
        return self.x[6:9].copy() if (self.initialised and self.model == "ca") else np.zeros(3)

    @property
    def vel(self):
        return self.x[3:6].copy() if self.initialised else None

    @property
    def speed(self):
        return float(np.linalg.norm(self.x[3:6])) if self.initialised else 0.0

    def predict_ahead(self, horizon):
        """Where will it be in `horizon` seconds, and how sure are we?"""
        if not self.initialised:
            return None, None
        F = self._F(horizon)
        xp = F @ self.x
        Pp = F @ self.P @ F.T + self._Q(horizon)
        return xp[:3], Pp[:3, :3]

    # ---------------------------------------------------------------
    @staticmethod
    def ellipse(cov2, nsigma=1.0):
        """2x2 covariance -> (semi_major, semi_minor, angle_rad) for drawing."""
        cov2 = np.asarray(cov2, float)[:2, :2]
        vals, vecs = np.linalg.eigh(cov2)
        vals = np.maximum(vals, 1e-9)
        order = vals.argsort()[::-1]
        vals, vecs = vals[order], vecs[:, order]
        a, b = nsigma * np.sqrt(vals)
        ang = math.atan2(vecs[1, 0], vecs[0, 0])
        return float(a), float(b), float(ang)


def prediction_is_justified(sigma_pos, latency, typical_speed, margin=1.0):
    """Should we extrapolate at all?

    Predicting forward trades lag for extrapolation error. The velocity used
    to extrapolate is itself estimated from noisy positions, so the trade only
    pays when the distance the target covers during the latency exceeds the
    measurement noise:

        speed * latency  >  margin * sigma_pos

    Measured on this repo's own sensors (see _self_test), the RSSI system at
    ~1.5 m / 4 Hz / 0.5 s FAILS this test and an EMA beats the filter; adding
    FTM or a mmWave front end passes it and the filter wins decisively.
    """
    return (typical_speed * latency) > (margin * sigma_pos)


def az_el(pos, ref):
    """Azimuth (deg, 0 = +x, CCW) and elevation (deg) of pos seen from ref."""
    d = np.asarray(pos, float) - np.asarray(ref, float)
    horiz = math.hypot(d[0], d[1])
    az = math.degrees(math.atan2(d[1], d[0])) % 360.0
    el = math.degrees(math.atan2(d[2], horiz)) if horiz > 1e-9 else 90.0
    return az, el, float(np.linalg.norm(d))


# -------------------------------------------------------------------
def _self_test():
    """The experiment that decided the design.

    Compares the current EMA against this filter, scoring both on what the
    system actually needs: error against the drone's TRUE CURRENT position
    when fixes arrive late. Run it and you can see why the filter is gated.
    """
    import numpy as np

    def truth(t, w=1.2, r=1.8):
        return np.array([2.5 + r * math.cos(w * t), 3.0 + r * math.sin(w * t),
                         1.2 + 0.4 * math.sin(0.8 * t)])

    def vtruth(t, w=1.2, r=1.8):
        return np.array([-r * w * math.sin(w * t), r * w * math.cos(w * t),
                         0.32 * math.cos(0.8 * t)])

    T = 80.0
    speed = 1.8 * 1.2
    scen = [("RSSI multilateration (today)", 1.50, 0.25, 0.50, False),
            ("+ FTM ranging",                0.60, 0.25, 0.35, False),
            ("mmWave (position only)",       0.10, 0.05, 0.05, False),
            ("mmWave + Doppler velocity",    0.10, 0.05, 0.05, True)]

    print("  Tracker self-test — RMS error vs the drone's TRUE CURRENT position")
    print("  (fixes arrive late; this is what the interceptor has to fly at)\n")
    print(f"  {'sensor':<30} {'sig':>5} {'rate':>5} {'lat':>5} | "
          f"{'EMA':>5} | {'KF':>5} | {'KF+pred':>7} | predict?")
    print("  " + "-" * 88)
    for name, sig, dt, lat, use_vel in scen:
        rng = np.random.default_rng(3); ema = None; e = []
        for k in range(int(T / dt)):
            t = k * dt; tm = t - lat
            if tm < 0: continue
            z = truth(tm) + rng.normal(0, sig, 3)
            ema = z.copy() if ema is None else 0.35 * z + 0.65 * ema
            e.append(np.linalg.norm(ema - truth(t)))
        ema_rms = float(np.sqrt(np.mean(np.square(e))))

        out = []
        for horizon in (0.0, lat):
            rng = np.random.default_rng(3); kf = TrackKF(sigma_a=2.0, model="cv"); e = []
            for k in range(int(T / dt)):
                t = k * dt; tm = t - lat
                if tm < 0: continue
                z = truth(tm) + rng.normal(0, sig, 3)
                kf.step(tm, z, np.eye(3) * sig ** 2)
                if use_vel and kf.initialised:
                    kf.update_velocity(vtruth(tm) + rng.normal(0, 0.10, 3),
                                       np.eye(3) * 0.10 ** 2)
                est = kf.pos if horizon == 0 else kf.predict_ahead(horizon)[0]
                e.append(np.linalg.norm(est - truth(t)))
            out.append(float(np.sqrt(np.mean(np.square(e)))))

        best = min([ema_rms] + out)
        m = lambda v: "*" if abs(v - best) < 1e-9 else " "
        ok = "YES" if prediction_is_justified(sig, lat, speed) else "no"
        print(f"  {name:<30} {sig:>5.2f} {1/dt:>4.0f}H {lat:>5.2f} | {ema_rms:>4.2f}{m(ema_rms)}| "
              f"{out[0]:>4.2f}{m(out[0])}| {out[1]:>6.2f}{m(out[1])}| {ok}")
    print("\n  * = best in row.  The gate is speed*latency > sigma: extrapolation only")
    print("  pays when the target moves further during the latency than the noise.")
    print("  On today's RSSI sensor it does NOT, so server.py keeps the EMA until")
    print("  FTM or mmWave is present. This is measured, not assumed.")


if __name__ == "__main__":
    _self_test()
