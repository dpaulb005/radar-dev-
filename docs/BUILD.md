# Master build guide — full two-drone interception system

Everything needed to go from parts to a working system where one ESP-BLAST
drone is flown by the ground radar to another. This is the index that ties the
detailed docs together:

- Drone integration specifics → [`espblast.md`](espblast.md)
- Radar bring-up detail → [`SETUP.md`](SETUP.md)
- Interception architecture & guidance → [`interception.md`](interception.md)
- Why RSSI (not reflection radar / mmWave) → [`feasibility.md`](feasibility.md)
- Priced radar parts table → [`../hardware/BOM.md`](../hardware/BOM.md)

---

## 1. Complete hardware list

Prices are typical US street prices (mid-2026). "You have it" = part of your
existing drone build or bench.

### 1a. The two aircraft — 2 × ESP-BLAST, **built without FPV**

You need **two** drones: a *target* and an *interceptor* (identical builds).
Follow the ESP-BLAST Instructable, but omit the FPV chain. Per drone:

| Item | Notes |
|------|-------|
| Custom flight-controller PCB | JLCPCB, ~$7 for 5 boards; carries the ESP32 |
| ESP32-WROOM-32 module | the flight controller MCU (do the u.FL antenna mod for range) |
| MPU9250 9-axis IMU | gyro+accel+**magnetometer** — the mag is needed later for heading downlink |
| BMP280 barometer | enables ESP-FC's baro altitude-hold |
| 4 × JMT HLK-DL03 8A ESC | brushless motor drivers |
| 4 × 1104 brushless motors + 2.5″ props | |
| 3S LiPo + XT30, 3.3 V regulator, caps | power |
| Buzzer, 30 AWG silicone wire, PETG frame | |
| GPS module | **optional** — not used for interception (the radar provides position); keep only if you want it as a sensor |
| ~~FPV camera, MinimOSD, tilt servo, 5.8 GHz VTX~~ | **OMIT — no FPV.** Saves cost, weight, and complexity |

**~$115–125 per drone without FPV → ~$230–250 for both.**

### 1b. Radio control for the drones

| Item | Qty | Unit | Notes |
|------|-----|------|-------|
| Handheld ESP-NOW transmitter (ESP32) | 1 | ~$15 | Flies the **target** manually (the ESP-BLAST "Radio Controller"). Also your manual-flight tool during bring-up. |
| **Commander ESP32 dev board** | 1 | $6 | Flies the **interceptor** — it's the ground station's radio (`firmware/commander`). |

The interceptor is flown *only* by the commander (binding is exclusive — see
§3 of `interception.md`). You do not need a second handheld.

### 1c. Ground radar sensor network (~$56)

| Item | Qty | Unit | Notes |
|------|-----|------|-------|
| ESP32-S3 / C3 dev board (IPEX antenna) | 4 | $6 | 3 sniffer nodes + 1 hub |
| 2.4 GHz dipole antenna, u.FL | 3 | $2 | vertical, same polarization on all nodes |
| USB power bank (small 5 V) | 3 | $5 | powers the field nodes |
| USB-C cables | 5 | $2 | flashing + hub + commander |
| Tripods / stakes / zip ties | 3 | ~$1 | node antennas ~1 m up, positions measured |

Add a **4th sniffer** ($6) for better geometry / robustness — the solver uses
however many report in.

### 1d. Ground station + test safety gear

| Item | Notes |
|------|-------|
| Laptop | runs `ground_station/` (Python 3.10+, Arduino IDE / PlatformIO) — you have it |
| **Net / cage / tethers** | non-negotiable for two-aircraft convergence tests |
| Prop guards ×2 sets, eye protection | |
| LiPo charging bag, tape measure (to ~10 cm) | |

### System total

| Subsystem | Cost |
|-----------|------|
| 2 × ESP-BLAST (no FPV) | ~$230–250 |
| Handheld TX + commander | ~$21 |
| Ground radar network | ~$56 |
| Test safety gear | ~$30–60 |
| **Total** | **~$340–390** |

The drones dominate the cost; the entire radar + interception add-on is
under ~$80. Not needed: SDRs, directional antennas, LNAs (see `feasibility.md`).

---

## 2. Build steps, in order (each ends with a checkpoint)

### Stage A — Build & fly both drones (no FPV)
Build both ESP-BLAST airframes per the Instructable through the flight-controller
steps, omitting the FPV camera/OSD/VTX/servo. Flash ESP-FC to each; in the
configurator set conservative angle/rate/throttle limits and **RC-loss →
disarm**. Bind each to the handheld and fly manually (props on, open area).
**Checkpoint A:** both drones arm, self-level in ANGLE mode, and fly under
manual control; RC-loss disarms them.

### Stage B — Make both drones trackable
Both the target *and* the interceptor must emit frames fast enough to track.
Apply the one-line ESP-FC patch (`LINK_ALIVE_INTERVAL_MS` 1000 → 40) to both, as
in [`espblast.md`](espblast.md). Record each drone's MAC and the link channel
(default 7) with `firmware/mac_scanner`.
**Checkpoint B:** `mac_scanner` shows both drones at ~25 Hz on the same channel;
you have both MACs written down.

### Stage C — Build & calibrate the ground radar
Flash `firmware/hub_node` (note its MAC) and 3–4 `firmware/rx_node` sniffers
(set each `NODE_ID`, the drone MAC, `HUB_MAC`, channel). Place the nodes in a
≥6 m triangle around the flight box, antennas vertical ~1 m up; measure each
position. Run `ground_station/server.py`, enter node positions (drag in EDIT
LAYOUT), connect the hub, calibrate each node with the wizard. Detail in
[`SETUP.md`](SETUP.md).
**Checkpoint C:** with one drone powered, its blip tracks within ~1–2 m of truth
inside the triangle; solver ~4 Hz.

### Stage D — Track both drones at once
Extend the tracker to separate the two drones by source MAC and solve each
independently (today the pipeline follows one target). This is the main
software task remaining before flight.
**Checkpoint D:** the console shows two blips, target and interceptor, both
updating live.

### Stage E — Commander bring-up (props OFF)
Flash `firmware/commander` to the commander ESP32. Power it **before** the
interceptor so it wins pairing. With props off, run
`python autopilot.py --commander <port> --sim` (or stream test frames) and watch
the interceptor's channels move in the ESP-FC configurator. **Resolve the
roll/pitch sign convention here** (a wrong sign flies it away — see the note in
`guidance.py`).
**Checkpoint E:** laptop-sent channels move the interceptor's sticks/motors
(props off) in the configurator; ARM/ANGLE AUX behave; stopping the stream
fail-safes to disarm.

### Stage F — Heading downlink
Add an ESP-NOW (or MSP/WiFi) downlink of the interceptor's AHRS yaw to the
laptop; calibrate the magnetometer on-frame (motor-current interference) and
implement the takeoff calibration dance. See §4 of `interception.md`.
**Checkpoint F:** the laptop shows the interceptor's heading, stable and correct
as you rotate it by hand.

### Stage G — Guidance (already done, validate on your data)
`guidance.py` + `pursuit_sim.py` are built and validated. Replay your Stage-C/D
logs through the sim to confirm the tuning and the feedback-sign against your
real noise/latency before flying.
**Checkpoint G:** sim intercepts on your recorded data with sane gains.

### Stage H — Netted flight tests, slow first
In a net/cage, tethered/prop-guarded, human on the kill (VLOS):
1. Interceptor flies to a **stationary** beacon position and loiters (expect
   ~1–2 m). Verify RC-loss, geofence, and kill fail-safes fire.
2. Target hovers, then drifts at ≤1–3 m/s; interceptor station-keeps within a
   couple metres.
**Checkpoint H:** the interceptor reliably flies to and loiters near a slow/
hovering target, scored by measured range. **This is the realistic end-state.**

Do **not** attempt to intercept the ESP-BLAST at speed — it's ~6–9× faster than
this sensor can track (see the envelope in `interception.md`). Pushing further
means UWB ranging or fusing the target's own IMU telemetry.

---

## 3. Safety & legal (summary — full version in `interception.md` §8)

Fly under Part 107 discipline when unsure; **maintain visual line of sight**
(you have no FPV); a human RPIC watches with a **kill that always beats the
autonomy loop**; never over people; register at ≥250 g and comply with Remote
ID. **The hard line: this is tracking / station-keeping only — never a payload,
never intentional contact.** Weaponizing a UAS is separately illegal.
