#!/usr/bin/env python3
"""
tracker.py — Kalman filters for the radar console.

STAGE 1 (one TX horn, one RX horn) measures exactly two things about a
target: its RANGE and its RADIAL VELOCITY. There is no bearing, so there is
no x/y plane position to track and nothing here produces one.

    RangeVelocityKF      the stage-1 filter. State [r, v] (or [r, v, a]),
                         measurement z = [r, v] straight off the range-Doppler
                         map: range from the range bin (sub-bin interpolated)
                         and velocity from the Doppler bin. Both are real
                         measurements, which is why the filter converges fast
                         and why it can coast honestly through a dropout.

    TrackKF              the older 3D position/velocity filter. Stage 1 does
                         NOT use it (it has no position to feed it); it is kept
                         because stage2/radar_twin.py drives it from the
                         scanning twin, where azimuth exists.

Self-test:
    python3 tracker.py       # closing-target run: raw measurements vs filter
"""

import math

import numpy as np


# ======================================================================
# STAGE 1 — range / radial-velocity track
# ======================================================================

class RangeVelocityKF:
    """Kalman filter on (range, radial velocity) from one range-Doppler map.

    State
        model="cv":  x = [r, v]          driven by white-noise acceleration
        model="ca":  x = [r, v, a]       driven by white-noise jerk

    Measurement
        z = [r, v] with R = diag(sigma_r^2, sigma_v^2). Velocity is measured
        directly by the Doppler FFT, not differenced from range, so the
        velocity estimate does not have to be paid for in lag.

    Sign convention follows the wire contract: v < 0 is closing.
    """

    def __init__(self, sigma_a=2.0, p0_r=3.0, p0_v=3.0, model="cv",
                 gate_sigma=5.0, coast_s=2.0):
        if model not in ("cv", "ca"):
            raise ValueError("model must be 'cv' or 'ca'")
        self.model = model
        self.n = 2 if model == "cv" else 3
        self.sigma_a = float(sigma_a)
        self.gate_sigma = float(gate_sigma)
        self.coast_s = float(coast_s)
        self._p0 = (float(p0_r), float(p0_v))
        self.x = None
        self.P = None
        self.initialised = False
        self.last_t = None          # time of the last accepted measurement
        self.last_any_t = None      # time we were last stepped at all
        self.updates = 0
        self.rejects = 0
        self.misses = 0             # consecutive blocks with no accepted fix

    # ------------------------------------------------------------------
    def _F(self, dt):
        F = np.eye(self.n)
        F[0, 1] = dt
        if self.model == "ca":
            F[0, 2] = 0.5 * dt * dt
            F[1, 2] = dt
        return F

    def _Q(self, dt):
        q = self.sigma_a ** 2
        if self.model == "cv":
            return q * np.array([[dt ** 3 / 3.0, dt ** 2 / 2.0],
                                 [dt ** 2 / 2.0, dt]])
        return q * np.array([[dt ** 5 / 20.0, dt ** 4 / 8.0, dt ** 3 / 6.0],
                             [dt ** 4 / 8.0, dt ** 3 / 3.0, dt ** 2 / 2.0],
                             [dt ** 3 / 6.0, dt ** 2 / 2.0, dt]])

    def _H(self):
        H = np.zeros((2, self.n))
        H[0, 0] = 1.0
        H[1, 1] = 1.0
        return H

    # ------------------------------------------------------------------
    def reset(self):
        self.x = None
        self.P = None
        self.initialised = False
        self.last_t = None
        self.misses = 0

    def init(self, r, v=0.0, sigma_r=None, sigma_v=None):
        self.x = np.zeros(self.n)
        self.x[0] = float(r)
        self.x[1] = float(v)
        p0r, p0v = self._p0
        if sigma_r is not None:
            p0r = max(float(sigma_r), 1e-3)
        if sigma_v is not None:
            p0v = max(float(sigma_v), 1e-3)
        d = [p0r ** 2, p0v ** 2]
        if self.model == "ca":
            d.append((2.0 * self.sigma_a) ** 2)
        self.P = np.diag(d).astype(float)
        self.initialised = True
        self.misses = 0

    def predict(self, dt):
        if not self.initialised or dt <= 0:
            return
        F = self._F(dt)
        self.x = F @ self.x
        self.P = F @ self.P @ F.T + self._Q(dt)

    # ------------------------------------------------------------------
    def update(self, r, v, sigma_r, sigma_v):
        """Fold in one detection. Returns (accepted, normalised innovation)."""
        if not self.initialised:
            self.init(r, v, sigma_r, sigma_v)
            return True, 0.0
        z = np.array([float(r), float(v)])
        R = np.diag([max(float(sigma_r), 1e-4) ** 2,
                     max(float(sigma_v), 1e-4) ** 2])
        H = self._H()
        y = z - H @ self.x
        S = H @ self.P @ H.T + R
        try:
            Si = np.linalg.inv(S)
        except np.linalg.LinAlgError:
            return False, float("inf")
        # chi-square gate on the 2-D innovation: a detection that disagrees
        # with the track by more than gate_sigma is a different scatterer
        # (or clutter), not a measurement of this one.
        d2 = float(y @ Si @ y)
        if d2 > self.gate_sigma ** 2:
            self.rejects += 1
            self.misses += 1
            return False, math.sqrt(max(d2, 0.0))
        K = self.P @ H.T @ Si
        self.x = self.x + K @ y
        I_KH = np.eye(self.n) - K @ H
        self.P = I_KH @ self.P @ I_KH.T + K @ R @ K.T   # Joseph form
        self.updates += 1
        self.misses = 0
        return True, math.sqrt(max(d2, 0.0))

    def step(self, t, r=None, v=None, sigma_r=0.15, sigma_v=0.10):
        """Predict to time t, then fold in (r, v) if a detection exists.

        Call it on EVERY block, with r=None when nothing was detected, so the
        track coasts with a growing covariance instead of freezing. Returns
        (accepted, normalised innovation).
        """
        t = float(t)
        if self.initialised and self.last_any_t is not None:
            dt = t - self.last_any_t
            if dt > 0:
                self.predict(min(dt, 10.0))
        self.last_any_t = t
        if r is None:
            if self.initialised:
                self.misses += 1
                if self.last_t is not None and (t - self.last_t) > self.coast_s:
                    self.reset()
            return False, float("inf")
        fresh = not self.initialised
        ok, d = self.update(r, v if v is not None else 0.0, sigma_r, sigma_v)
        if ok:
            self.last_t = t
        elif not fresh and self.last_t is not None and (t - self.last_t) > self.coast_s:
            # the track has been disagreeing with every detection for longer
            # than the coast window: believe the radar, not the filter.
            self.reset()
            self.init(r, v if v is not None else 0.0, sigma_r, sigma_v)
            self.last_t = t
            ok = True
        return ok, d

    # ------------------------------------------------------------------
    @property
    def range(self):
        return float(self.x[0]) if self.initialised else None

    @property
    def vel(self):
        return float(self.x[1]) if self.initialised else None

    @property
    def accel(self):
        if self.initialised and self.model == "ca":
            return float(self.x[2])
        return 0.0

    @property
    def sigma_r(self):
        return float(math.sqrt(max(self.P[0, 0], 0.0))) if self.initialised else None

    @property
    def sigma_v(self):
        return float(math.sqrt(max(self.P[1, 1], 0.0))) if self.initialised else None

    @property
    def cov_rv(self):
        """The 2x2 (range, velocity) covariance — the ONLY covariance stage 1
        has. There is no azimuth term because there is no azimuth."""
        if not self.initialised:
            return None
        return [[float(self.P[0, 0]), float(self.P[0, 1])],
                [float(self.P[1, 0]), float(self.P[1, 1])]]

    def predict_ahead(self, horizon):
        """(range, velocity, sigma_range) projected `horizon` seconds out."""
        if not self.initialised:
            return None, None, None
        F = self._F(horizon)
        xp = F @ self.x
        Pp = F @ self.P @ F.T + self._Q(horizon)
        return float(xp[0]), float(xp[1]), float(math.sqrt(max(Pp[0, 0], 0.0)))

    def time_to_closest(self):
        """Seconds until range stops shrinking, or None if opening/stationary."""
        if not self.initialised:
            return None
        v = self.x[1]
        if v >= -1e-3:
            return None
        a = self.accel
        if abs(a) < 1e-6:
            return float(-self.x[0] / v) if self.x[0] > 0 else 0.0
        t = -v / a
        return float(t) if t > 0 else None


def range_sigma_from_snr(snr_db, sigma_ref=0.15, snr_ref=12.0,
                         lo=1.0, hi=6.0):
    """Inflate the range/velocity sigma for a weak detection.

    Peak-position error scales roughly as 1/sqrt(SNR) for an interpolated FFT
    peak, so a 6 dB drop in SNR doubles the spread. sigma_ref is the quoted
    accuracy at snr_ref dB; the multiplier is clamped to [lo, hi] so one
    marginal block cannot make the filter ignore the radar entirely.
    """
    try:
        snr = float(snr_db)
    except (TypeError, ValueError):
        return sigma_ref * hi
    k = 10.0 ** ((snr_ref - snr) / 20.0)
    return float(sigma_ref) * float(min(max(k, lo), hi))


def prediction_is_justified(sigma_pos, latency, typical_speed, margin=1.0):
    """Should the console extrapolate the track at all?

    Extrapolation trades lag for extrapolation error, and it only pays when
    the target moves further during the sensor latency than the measurement
    noise:  speed * latency > margin * sigma. Stage 1's range measurement is
    sigma_r ~ 0.15 m at a block rate of several Hz, so for a drone closing at
    1 m/s this passes comfortably — unlike the abandoned RSSI sensor, where it
    did not.
    """
    return (typical_speed * latency) > (margin * sigma_pos)


# ======================================================================
# STAGE 2 — 3D position track (kept for stage2/radar_twin.py)
# ======================================================================

class TrackKF:
    """Constant-velocity / constant-acceleration Kalman filter on 3D fixes.

    NOT used by stage 1, which has no bearing and therefore no position.
    stage2/radar_twin.py drives this from the scanning twin's (range, azimuth)
    fixes; keep the interface stable for it.

    State  x = [p(3), v(3)]        (model="cv")
           x = [p(3), v(3), a(3)]  (model="ca")
    """

    def __init__(self, sigma_a=3.0, p0_pos=5.0, p0_vel=3.0, model="ca"):
        self.model = model
        self.n = 6 if model == "cv" else 9
        self.sigma_a = float(sigma_a)
        self.x = None
        self.P = None
        self._p0 = (p0_pos, p0_vel)
        self.initialised = False
        self.last_t = None

    def _F(self, dt):
        F = np.eye(self.n)
        for i in range(3):
            F[i, i + 3] = dt
            if self.model == "ca":
                F[i, i + 6] = 0.5 * dt * dt
                F[i + 3, i + 6] = dt
        return F

    def _Q(self, dt):
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
        z = np.asarray(z, float)
        R = np.asarray(R, float)
        if not self.initialised:
            self.init(z)
            self.P[:3, :3] = R
            return
        H = np.zeros((3, self.n)); H[0, 0] = H[1, 1] = H[2, 2] = 1.0
        y = z - H @ self.x
        S = H @ self.P @ H.T + R
        try:
            K = self.P @ H.T @ np.linalg.inv(S)
        except np.linalg.LinAlgError:
            return
        self.x = self.x + K @ y
        I_KH = np.eye(self.n) - K @ H
        self.P = I_KH @ self.P @ I_KH.T + K @ R @ K.T

    def update_velocity(self, zv, Rv):
        """Fold in a DIRECT velocity measurement (Doppler)."""
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
        if self.last_t is not None:
            self.predict(max(0.0, t - self.last_t))
        self.last_t = t
        self.update(z, R)

    @property
    def pos(self):
        return self.x[:3].copy() if self.initialised else None

    @property
    def vel(self):
        return self.x[3:6].copy() if self.initialised else None

    @property
    def accel(self):
        return self.x[6:9].copy() if (self.initialised and self.model == "ca") else np.zeros(3)

    @property
    def speed(self):
        return float(np.linalg.norm(self.x[3:6])) if self.initialised else 0.0

    def predict_ahead(self, horizon):
        if not self.initialised:
            return None, None
        F = self._F(horizon)
        xp = F @ self.x
        Pp = F @ self.P @ F.T + self._Q(horizon)
        return xp[:3], Pp[:3, :3]

    @staticmethod
    def ellipse(cov2, nsigma=1.0):
        cov2 = np.asarray(cov2, float)[:2, :2]
        vals, vecs = np.linalg.eigh(cov2)
        vals = np.maximum(vals, 1e-9)
        order = vals.argsort()[::-1]
        vals, vecs = vals[order], vecs[:, order]
        a, b = nsigma * np.sqrt(vals)
        ang = math.atan2(vecs[1, 0], vecs[0, 0])
        return float(a), float(b), float(ang)


# ----------------------------------------------------------------------
def _self_test():
    """Stage-1 run: a drone closing from 10 m, then braking to a hover.

    Scores the raw per-block measurement against the filter on the quantity
    the console displays, and checks that the gate rejects a clutter blip
    without dragging the track onto it.
    """
    rng = np.random.default_rng(7)
    dt, T = 0.12, 12.0
    sig_r, sig_v = 0.15, 0.10

    def truth(t):
        # closing at 1 m/s for 8 s, then brakes over 1 s and hovers
        if t < 8.0:
            return 10.0 - 1.0 * t, -1.0
        if t < 9.0:
            a = 1.0
            tt = t - 8.0
            return 2.0 - 1.0 * tt + 0.5 * a * tt ** 2, -1.0 + a * tt
        return 1.5, 0.0

    print("  RangeVelocityKF self-test — drone closing from 10 m, then hovering")
    print(f"  block rate {1/dt:.1f} Hz, sigma_r {sig_r} m, sigma_v {sig_v} m/s\n")
    for model in ("cv", "ca"):
        kf = RangeVelocityKF(sigma_a=2.0, model=model)
        rng = np.random.default_rng(7)
        er_raw, er_kf, ev_raw, ev_kf = [], [], [], []
        clutter_pull = 0.0
        for k in range(int(T / dt)):
            t = k * dt
            r_t, v_t = truth(t)
            r_m = r_t + rng.normal(0, sig_r)
            v_m = v_t + rng.normal(0, sig_v)
            kf.step(t, r_m, v_m, sig_r, sig_v)
            er_raw.append(r_m - r_t); er_kf.append(kf.range - r_t)
            ev_raw.append(v_m - v_t); ev_kf.append(kf.vel - v_t)
            if abs(t - 5.0) < dt / 2:            # one clutter blip at 9 m
                before = kf.range
                kf.step(t + dt / 3, 9.0, 3.0, sig_r, sig_v)
                clutter_pull = abs(kf.range - before)
        rms = lambda e: float(np.sqrt(np.mean(np.square(e))))
        print(f"  model={model}  range RMS raw {rms(er_raw):.3f} m -> kf {rms(er_kf):.3f} m"
              f"   vel RMS raw {rms(ev_raw):.3f} -> kf {rms(ev_kf):.3f} m/s")
        print(f"             gate rejected {kf.rejects} blip(s); it moved the "
              f"track {clutter_pull*100:.1f} cm")
    print("\n  sigma inflation vs SNR:")
    for snr in (30, 20, 12, 6, 0):
        print(f"    {snr:>3} dB -> sigma_r {range_sigma_from_snr(snr):.3f} m")
    print("\n  Extrapolation gate (speed*latency > sigma_r):",
          "JUSTIFIED" if prediction_is_justified(0.15, 0.5, 1.0) else "no")


if __name__ == "__main__":
    _self_test()
