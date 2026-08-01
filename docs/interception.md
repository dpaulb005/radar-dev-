# Two-drone interception — architecture & build plan

**Goal:** one ESP-BLAST drone (the *interceptor*) autonomously flies to a
second ESP-BLAST (the *target*), located by the passive-RF radar.

This document is the end-to-end design. The firmware/API claims were verified
against primary source (esp-fc `@master`, espnow-rclink `@main`); the
performance numbers were verified empirically in `ground_station/pursuit_sim.py`.

---

## 1. The core problem: a single point can't find a bearing

The ground radar in this repo locates a drone by **multilateration** — three
or more spatially-separated nodes each measure range (via RSSI), and the
intersection gives position. A single receiver on the interceptor could only
measure *range* to the target (one number → a circle of possible positions),
never *direction*. To get direction from one platform you'd need an antenna
array (angle-of-arrival) or a directional/rotating antenna — an RF-seeker
payload — bolted onto a sub-250 g rocket quad, running DSP next to a 4 kHz
flight loop. That's a different, much harder project.

**So the interceptor doesn't find the target itself. The ground radar tracks
*both* drones** (both are ESP32s emitting ESP-NOW frames), the laptop computes
the intercept, and it flies the interceptor by remote control — the same idea
as a motion-capture drone lab, with RF multilateration standing in for the
cameras.

```
[target drone] ──ESP-NOW──┐
                          ├──▶ [3–4 fixed sniffer nodes] ──USB──▶ [LAPTOP = autopilot]
[interceptor] ──ESP-NOW──┘        RSSI + source-MAC              │  • multilaterate BOTH drones (4–10 Hz)
      ▲                                                          │  • track + predict (latency-compensate)
      │                                                          │  • guidance → world accel → lean angles
      │                                                          │  • build 8-ch RC frame (sticks + ARM/ANGLE)
      └──────ESP-NOW RC──────[commander ESP32]◀────USB serial────┘
                             (espnow-rclink transmitter)
```

Why this wins: **zero added weight on the airframe** (the drone stays stock),
all intelligence lives on the laptop where it's easy to log and tune, and the
yaw-ambiguity problem is solvable centrally (§4).

---

## 2. The autonomy gap: ESP-FC has no "go to a point"

Verified from the esp-fc source, the flight controller is a **rate/attitude
controller only**:

- **ACRO** (rate, default) and **ANGLE** (self-leveling — stick commands a
  lean angle, `FC_PID_LEVEL` drives measured attitude to it). ANGLE is what we
  use, so the laptop can command *lean angles* directly.
- **ALTHOLD** exists but is an **experimental baro climb-rate hold** (throttle
  stick → −2…+4 m/s), not position hold. Useful: engage it and the laptop only
  has to control the horizontal plane.
- **No GPS position hold, no return-to-home, no waypoint navigation.** GPS is a
  read-only sensor feeding telemetry/OSD. The Betaflight-style POS/NAV PID
  tokens exist only for configurator compatibility and are unused.

**Conclusion: "fly to the target" must be closed by the laptop.** ESP-FC keeps
doing what it's good at — fast attitude stabilization — and the ground station
supplies the entire outer loop it lacks: localize → track/predict → guidance →
lean-angle + throttle + AUX → RC frame.

---

## 3. The commander: being the drone's radio

The **commander** (`firmware/commander/commander.ino`) is a tethered ESP32
running the espnow-rclink **transmitter**. The laptop streams it stick values
over USB serial (`C,ch0,…,ch7\n`); it emits `RC_DATA` frames the interceptor's
ESP-FC accepts as ordinary RC. Verified transmitter API: `tx.begin()`,
`tx.setChannel(c, µs)`, `tx.commit()`, `tx.update()`, ~50 Hz.

**Exclusive binding — the key operational rule.** The link has *no encryption
and no cryptographic binding* — just auto-pairing where the **first
transmitter to answer wins, locked until the drone is power-cycled**. So:

- Power the **commander on first** so it becomes the interceptor's sole
  controller. There is **no live hand-off** between a human transmitter and the
  laptop.
- Therefore **manual override must live inside the commander/laptop path** — a
  kill on the commander that forces disarm channels or stops streaming — not a
  second physical radio.

**Channel plan** (8 channels: 4 full-res AETR + 4 packed AUX), matching esp-fc
defaults:

| RC ch | AETR | esp-fc mode | Driven with |
|-------|------|-------------|-------------|
| ch0 | roll (A) | ROLL | φ lean → µs |
| ch1 | pitch (E) | PITCH | θ lean → µs |
| ch2 | throttle (T) | THRUST | hover / climb-rate stick |
| ch3 | yaw (R) | YAW | ~1500 (yaw held fixed) |
| ch4 | AUX1 | ARM + AIRMODE (1300–2100) | 1800 arm / 1000 safe |
| ch5 | AUX2 | ANGLE (1300–2100), ALTHOLD (1700–2100) | 1500 = ANGLE, 1800 = ANGLE+ALTHOLD |
| ch6 | AUX3 | spare | — |
| ch7 | AUX4 | spare (map a kill) | low = safe |

Confirm these ranges in the ESP-FC configurator/CLI to match.

---

## 4. Heading: the one sensor the radar can't provide

A position tracker gives (x, y, z) but **not yaw ψ**. A quad only accelerates
horizontally by tilting its thrust vector *in its own body frame*, so turning a
desired world-frame acceleration into roll/pitch needs ψ. Get ψ wrong by >90°
and the position feedback flips sign — the drone flies *away*. Three sources,
in order of preference:

1. **Downlink ESP-FC's AHRS heading** (recommended). The MPU9250 is a 9-axis
   IMU; esp-fc fuses it to an absolute heading far cleaner than anything from
   RSSI. espnow-rclink is currently uplink-only (telemetry is a TODO), but
   ESP-NOW is bidirectional — add a few-byte heading downlink to the commander,
   or use esp-fc's MSP/WiFi `MSP_ATTITUDE`. Fly with **yaw commanded fixed** so
   the world→body rotation is nearly constant. *Caveat:* the magnetometer on a
   brushless frame is corrupted by motor currents — calibrate it on-frame and
   route it away from power wiring.
2. **Takeoff "calibration dance"** (bootstrap / fallback). Command a known pure
   body-axis lean for ~1 s, watch which way the tracker says it moved, solve ψ.
   This is exactly ArduPilot's compass-less startup. Do it at every takeoff
   even with telemetry, to pin the absolute offset — and to **resolve the
   roll-sign convention** (a wrong sign flies it away; `guidance.py` flags this
   at `accel_to_attitude`).
3. **Velocity-inferred heading** (last resort only). A quad can strafe, so
   course ≠ heading; and differentiating a 1–3 m / 4–10 Hz position stream
   gives ~14 m/s of velocity noise. Coarse, straight-line-only.

---

## 5. Guidance (what the code implements)

`ground_station/guidance.py`, in the world horizontal plane:

- **`track` (default)** — cascaded position + velocity control with
  **target-velocity feed-forward** and **latency compensation**:
  ```
  p_t* = p_t + v_t · τ_Σ                      # predict through loop delay τ_Σ ≈ 0.5 s
  v_des = v_t + k_p · (p_t* − p_i)            # feed-forward + position P
  a_des = k_v · (v_des − v_i)                 # velocity P, saturated to lean limit
  ```
  The feed-forward is what makes it *settle onto* a moving target instead of
  trailing it — this is the standard external-tracker (mocap) law. Then
  `a_des` → lean angle `θ ≈ atan(|a|/g)`, split into roll/pitch by ψ, mapped to
  stick µs.
- **`pure_pursuit`** — aim at the target's current position. Simple, but lags a
  maneuvering target; kept for comparison.
- **`pro_nav`** — true proportional navigation (nulls line-of-sight rate,
  N≈3–5). A modest upgrade against a *smooth, constant-velocity* target;
  capped by target-velocity noise.

Both laws share a ceiling set by how well you know the target's velocity, which
from differenced RSSI is uncertain by several m/s. Fusing the target's own IMU
telemetry is what actually sharpens it.

---

## 6. What will and won't work — the honest envelope

The binding constraint is **total loop delay** τ_Σ ≈ 0.4–0.7 s (sensor +
age-of-fix + tilt-to-accel lag), not link bandwidth. The feasibility crossover
where latency-lead error equals the ~2 m position-noise floor is:

```
v_cross ≈ σ / τ_Σ ≈ 2 m / 0.55 s ≈ 3.6 m/s
```

| Target motion | Achievable miss | Verdict |
|---------------|-----------------|---------|
| Hover | ~1 m (fix averaging) | **Good** |
| Drift ≤ ~3 m/s | ~1.5–2.5 m | **Feasible — fly to & loiter** |
| 3–5 m/s | ~2.5–4 m | Marginal (the ceiling) |
| 10 m/s | ~6–8 m, shaky | Infeasible for capture |
| **28 m/s (ESP-BLAST top speed)** | tens of m, unstable | **Not feasible (~6–9× too fast)** |

This matches the simulation. `pursuit_sim.py` (which reuses the real solver and
RSSI noise model) measured, at realistic 3 dB / 8 Hz / 150 ms:

- Clean-sensor check: the `track` law drives the interceptor to **contact
  (<1 m)** — the guidance is correct.
- Slow (3 m/s) target: **98 % arrival within 2.5 m**, median closest approach
  **~1.1 m**, ~45 % reach <1 m. Sub-metre "contact" is intermittent because it
  sits *below the sensor's own accuracy* — closing the last metre needs terminal
  guidance (onboard homing / UWB / a camera), not the ground RSSI radar.
- Fleeing target: arrival collapses past ~5 m/s — partly the speed, partly the
  target leaving the node array's useful volume (multilateration is poor outside
  the ~10 m footprint).

**Two hard truths to design around:** the ESP-BLAST at speed is uncatchable
with this sensor, and everything only works *inside* the node-array volume. The
realistic mission is **"fly to and loiter within a couple of metres of a
hovering or slowly-drifting target, scored by measured range."**

**Biggest levers, ranked:** (1) UWB ranging instead of RSSI — σ→0.1–0.3 m,
kHz rates — the one change that could push the ceiling to ~10–30 m/s; (2) fuse
the *target's own* IMU/baro telemetry over spare ESP-NOW bandwidth (cheap, both
drones are yours); (3) predictive filtering + latency compensation (already in
`guidance.py`); (4) faster node report rate; (5) more/better-placed nodes.

---

## 7. The code in this repo

| File | Role |
|------|------|
| `ground_station/guidance.py` | guidance laws + world-accel → attitude → RC channel mapping |
| `ground_station/pursuit_sim.py` | end-to-end closed-loop sim (real solver + noise); Monte-Carlo, envelope sweep, plots |
| `ground_station/autopilot.py` | the host "pilot": fixes → guidance → 8-ch frame → commander serial, with arming/geofence/fail-safe. Defaults to DISARMED + dry-run |
| `firmware/commander/commander.ino` | tethered ESP32 espnow-rclink transmitter; relays serial frames, fail-safes on stream loss |
| GUI **Pursuit demo** (`server.py` + `web/`) | live two-drone visualization in the radar console (sim) |

Try it with no hardware:

```bash
cd ground_station
python pursuit_sim.py --trials 40 --target-speed 3     # intercept statistics
python pursuit_sim.py --sweep --target-path drift       # speed envelope
python pursuit_sim.py --plot run.png                     # trajectory plot
python autopilot.py --sim --dry-run                      # watch the RC frames it would send
python server.py --sim                                   # GUI → http://localhost:8080 → "Pursuit demo"
```

---

## 8. Safety & legal — read before flying

**This flies a real aircraft toward another aircraft. Treat it accordingly.**

**Legal (US):**
- Every flight is under the **recreational exception (49 USC 44809)** *or*
  **Part 107**. An R&D intercept project likely isn't "strictly recreational,"
  so **default to the stricter Part 107 standard** when unsure.
- **Visual line of sight is mandatory** (14 CFR 107.31 / 44809). You're building
  **without FPV**, so VLOS is your only situational awareness — never let either
  drone get far or fast enough to lose sight.
- **Autonomy is legal only because you can override it** (14 CFR 107.19(c)): a
  human remote pilot must be watching, finger on the kill. No hands-off / BVLOS
  without a waiver.
- **Never over uninvolved people** (107.39); check airspace each session
  (B4UFLY/LAANC); ≤400 ft AGL; away from airports.
- **Register** at ≥250 g (FAADroneZone) and comply with **Remote ID**. These
  quads sit near the threshold — **weigh each as-flown**.
- **THE HARD LINE — pursuit is fine, weaponization is not.** Tracking / "fly to
  the estimated position" / station-keeping is legitimate navigation. Adding
  **anything meant to strike, entangle, capture, or damage** the other aircraft
  makes it a **weaponized UAS — separately illegal (FAA Reauthorization Act 2018
  §363, up to $25,000/violation)**. Design "intercept" as
  **approach/proximity/station-keeping and score a tag by measured range, never
  contact, never a payload.**

**Test discipline:**
- **Contain first flights** in a net/cage or on a tether — two aircraft
  converging is exactly what netting is for.
- **Slow before fast:** props-off arming → low hover → slow translation → only
  much later any real closing speed. Cap angle/rate/throttle in esp-fc.
- **Prop guards + eye protection** on both aircraft for early work; spectators
  behind a barrier; **sacrificial airframes** for first near-miss tests.
- **Layered fail-safes, verify each fires:** RC-loss → **disarm** (not "hover
  away"; test by powering off the commander); an independent **kill in the
  commander/laptop path** that always beats the autonomy loop; **geofence** →
  disarm/descend on breach; low-battery fail-safe. `autopilot.py` defaults to
  DISARMED and fail-safes on geofence breach or stale fixes; `commander.ino`
  fail-safes if the serial stream stops. LiPo fire safety on hand.

---

## 9. Phased build plan

0. **Bench (props off).** Bring up esp-fc on both quads; confirm ARM/ANGLE/
   ALTHOLD on AUX in the configurator; set conservative limits, RC-loss = disarm.
   Bring up the commander; verify it wins pairing (power-on-first) and that
   `setChannel/commit/update` move the channels (watch in the configurator).
   **Nail down the roll/pitch sign** here.
1. **Localization ground truth.** Deploy the sniffer nodes; calibrate; confirm
   ~1–3 m / 4–10 Hz; **track both drones at once** (per-MAC).
2. **Heading downlink.** Add the AHRS-yaw telemetry downlink; calibrate the
   magnetometer on-frame; implement the takeoff calibration dance.
3. **Guidance in sim/replay.** (Done in this repo: `pursuit_sim.py`,
   `guidance.py`.) Validate the sign convention and latency compensation against
   real Phase-1 logs before flying.
4. **Netted low-speed flight.** Laptop flies the interceptor to a **stationary
   beacon** and loiters; measure real miss (~1–2 m expected); verify all
   fail-safes.
5. **Slow moving target.** Target hovers then drifts ≤3 m/s; interceptor
   station-keeps within a couple metres. **This is the realistic end-state.**
6. **(Optional) Push the envelope.** Add target-IMU telemetry fusion and/or UWB
   ranging *before* attempting any higher-speed pursuit. Do **not** attempt
   near-top-speed intercept — it's ~6–9× beyond this sensor.
