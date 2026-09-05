# Tracking filter — what the measurement actually says

The plan was: replace the EMA with a constant-velocity Kalman filter and
predict ~0.5 s ahead to compensate sensor latency. **I built it and measured
it, and on today's sensor that makes things worse.** The filter is in the repo
and is the right thing to build — it is just *gated off* until the sensor is
good enough to earn it.

Reproduce everything here with:

```bash
python ground_station/tracker.py
```

## The experiment

Score each estimator on what the system actually needs: **error against the
drone's TRUE CURRENT position**, when fixes arrive late. Agile target
(1.2 rad/s orbit, ~2.5 m/s², 2.2 m/s).

| sensor | σ | rate | latency | EMA | Kalman | Kalman + predict |
|---|---|---|---|---|---|---|
| **RSSI multilateration (today)** | 1.50 m | 4 Hz | 0.50 s | **2.16 m** | 2.37 m | 2.92 m |
| + FTM ranging | 0.60 m | 4 Hz | 0.35 s | 1.56 m | **1.24 m** | 1.40 m |
| mmWave (position only) | 0.10 m | 20 Hz | 0.05 s | 0.32 m | 0.16 m | **0.15 m** |
| mmWave + Doppler velocity | 0.10 m | 20 Hz | 0.05 s | 0.32 m | 0.12 m | **0.04 m** |

## Why — one line

> **Prediction only pays when the target moves further during the latency than
> the measurement noise:  `speed × latency > σ`.**

- RSSI today: moves **1.08 m** during the latency, noise is **1.50 m** → the
  velocity you extrapolate with is itself derived from differencing noisy
  positions, so you inject more error than you remove. Prediction *cannot* pay.
- FTM: moves 0.76 m vs 0.60 m of noise → it starts paying, and the filter wins
  by ~20 %.
- mmWave with Doppler: velocity is **measured directly**, not differenced —
  which is why it goes from a marginal gain to an **8× one**.

A constant-**acceleration** model was also tried; it is worse than constant
velocity here (the orbit's acceleration is itself rotating), so CV stays the
default.

## What shipped

`ground_station/tracker.py`:
- 3D Kalman filter, CV (6-state) or CA (9-state), Joseph-form update.
- **R comes from `geometry.position_cov()`**, so a fix taken with poor geometry
  — e.g. altitude from near-coplanar nodes — is automatically distrusted
  instead of believed.
- `update_velocity()` for a direct Doppler measurement (the mmWave path).
- `predict_ahead(t)` → predicted position **and** grown covariance.
- `prediction_is_justified(σ, latency, speed)` — the gate above.

`server.py` runs the filter **always** (it supplies the covariance ellipse and
the az/el readout) but only lets it **drive** the displayed fix when the gate
passes. The console shows which is live: *"Estimator: EMA (filter gated off)"*
or *"Kalman + predict"*. Today, on RSSI, it correctly reads gated-off.

The console draws the 1-σ covariance ellipse on the current fix, and — with
**PREDICT** enabled — an orange ghost blip at +0.5 s with its own larger
ellipse, so the growth of uncertainty with horizon is visible rather than
implied.

## Update: on the can radar, the filter turns ON

The project moved to an active FMCW radar, which changes the verdict
completely — because the radar **measures velocity directly from Doppler**
instead of differencing noisy positions:

| sensor | σ | rate | latency | EMA | KF | KF + predict |
|---|---|---|---|---|---|---|
| RSSI (dropped) | 1.50 m | 4 Hz | 0.50 s | **2.09 m** | 2.32 | 2.83 |
| can radar, scanning | 0.32 m | 1.1 Hz | 0.60 s | 1.87 | 1.36 | **0.65 m** |
| can radar, locked dither | 0.32 m | 3.1 Hz | 0.20 s | 1.29 | 0.50 | **0.26 m** |

**5× better than the EMA**, and the gate enables it automatically. End to end
through the real detection chain, `radar_twin.py --track` measures **0.12 m RMS
tracking error**.

## What to do about it

1. **Add FTM** (`espfly.md` §4). It is one argument on a `softAP()` call and it
   flips the filter from a downgrade to a 20 % win.
2. Then raise the node count / rate if you want more.
3. The mmWave front end ([`mmwave.md`](mmwave.md)) is where this becomes
   transformative, because Doppler gives velocity without differencing.

**Tier 2 (EKF on raw ranges)** — feeding every RSSI/FTM range into the filter
as it arrives rather than solving a position per window — is the right next
step *after* FTM lands. It handles node dropout and mixes the two ranging types
by their real noise. Validate it in `digital_twin.py` before hardware; that
model already matches the measured ~2 m horizontal accuracy.
