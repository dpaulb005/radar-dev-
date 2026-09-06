# radar-dev — active FMCW radar for drone tracking

**Current scope: an MIT-style 2.4 GHz coffee-can FMCW radar with a custom horn
antenna, tracking a drone by its reflections.** No passive/beacon tracking —
the radar sees the airframe itself, so the drone needs no cooperation, no
beacon firmware and no MAC filtering.

## Step-by-step guides (start here)

| | hardware | software |
|---|---|---|
| **radar** | [`docs/radar-hardware.md`](docs/radar-hardware.md) — horns, RF chain in MIT order, video amp, sync, turntable, stacked RX | [`docs/radar-software.md`](docs/radar-software.md) — `radar_ctl` firmware, `radar_acquire.py`, self-test, console |
| **ESP-FLY** | [`docs/drone-hardware.md`](docs/drone-hardware.md) — flown by phone: nothing changes on the airframe; what to take off | [`docs/drone-software.md`](docs/drone-software.md) — ESP-Drone AP on channel 1, radar sweeps 2440–2483.5 MHz above it, the ping test that proves coexistence |

Fallback if the phone link and the radar won't coexist: a 915 MHz ELRS link
([`docs/drone-915.md`](docs/drone-915.md), [`docs/drone-915-esp-fc.md`](docs/drone-915-esp-fc.md)).

Parts, priced and in stock as of Sept 2026: [`hardware/BOM.md`](hardware/BOM.md).
Background: [`docs/mit-radar.md`](docs/mit-radar.md) (the plan and its
constraints), [`docs/scanning.md`](docs/scanning.md) (why you need to scan to
get position), [`docs/antenna.md`](docs/antenna.md) (the horn).

```bash
cd ground_station && pip install -r requirements.txt
python radar_acquire.py --selftest        # the live DSP, on a synthetic drone — no hardware
python radar_acquire.py --device 3 --ctl /dev/ttyUSB0 --server http://localhost:8080
python server.py                          # console at http://localhost:8080
```

| tool | what it does |
|---|---|
| `firmware/radar_ctl/` | **radar ESP32**: steps the ADF4351 sweep, SYNC to the sound card, turntable, serial protocol |
| `ground_station/radar_acquire.py` | **live radar**: sound card → chirps → range-Doppler → CFAR → azimuth centroid → console (`--selftest`, `--replay`) |
| `firmware/espfly/` | the ESP-FLY's esp-fc configuration for a 915 MHz CRSF receiver (no custom drone code) |
| `ground_station/fmcw_sim.py` | chirp → echo → range-Doppler map, link budget |
| `ground_station/scan_design.py` | range-only vs scanning vs interferometry, sized |
| `ground_station/radar_twin.py` | full twin: scan → CFAR → centroid → track |
| `antenna/horn.py` | optimum pyramidal horn, with the pe==ph and aperture-bound checks |
| `ground_station/tracker.py` | Kalman tracking filter (**on** for radar, see `tracking.md`) |

---

<details>
<summary><b>Archived: the passive RF localization system</b> (superseded, kept for reference)</summary>

The original approach located a *cooperative* drone by multilaterating RSSI of
its own WiFi frames across ground sniffer nodes. It works (~2 m), but it needs
the drone to transmit, and it cannot measure altitude from coplanar nodes. The
active radar supersedes it on every axis. Docs below are retained because the
console, geometry tools, tracking filter and guidance code are all still used.

## radar-dev — passive RF localization for an ESP32 drone

Locates an ESP32-equipped drone within a ~5–10 m flight area using its own
2.4 GHz transmissions, for well under $150 — and, as the end goal, uses that
radar to fly one drone to another (**two-drone interception**, see
[`docs/interception.md`](docs/interception.md)).

**Important scope note:** the original idea — a true passive radar detecting
*reflections* of the controller's signal off the drone — is not physically
achievable at 5–10 m on a hobby budget (the echo is ~45 dB below the direct
signal, and 20 MHz of bandwidth gives 7.5 m range resolution: one range cell
covers the whole area). The full analysis is in
[`docs/feasibility.md`](docs/feasibility.md). What *does* work, and what this
repo implements, is **passive emitter localization**: receive-only sniffer
nodes measure the drone's own WiFi frames and multilaterate its position.
Same goal, achievable physics.

**Building the ESP-FLY?** (XIAO ESP32-S3 airframe) — read
[`docs/espfly.md`](docs/espfly.md). Short version: esp-fc's `ESP-FC` softAP
beacons at ~10 Hz all flight, so you get a beacon **free with no firmware
patch**; you **must fly the ESP-NOW link** (an external ELRS receiver leaves
WiFi down and LoRa is undecodable by an ESP32 sniffer); the channel is **1, not
7**; the S3 **supports FTM**, which is the accuracy upgrade that matters; and
with no barometer, altitude needs **one node on the ceiling**.

**Building the ESP-BLAST?** (Max Imagination's ESP32-WROOM-32 rocket drone
running ESP-FC with an ESP-NOW radio link) — read
[`docs/espblast.md`](docs/espblast.md) first. Short version: the stock drone
only transmits a 1 Hz keepalive in flight, so you either bump
`LINK_ALIVE_INTERVAL_MS` from 1000 to 40 in your esp-fc build (one line,
you compile it yourself anyway) or piggyback a $3 beacon board; the WROOM-32
chip has no FTM support, so RSSI mode is the mode; and the RC link defaults
to WiFi channel 7, which is now the default across this repo's firmware.

## Architecture

```
                        [ drone: ESP32 running drone_beacon ]
                          ~~~ 2.4 GHz ESP-NOW beacons ~~~
                         /            |             \
                  [rx_node 1]    [rx_node 2]    [rx_node 3]     (promiscuous
                   RSSI: -51      RSSI: -58      RSSI: -47       receive-only)
                         \            |             /
                          ESP-NOW reports, same channel
                                      |
                                 [hub_node] --USB serial--> laptop
                                                            ground_station/locate.py
                                                            → {"x":3.2,"y":4.9,...}
```

- **`firmware/drone_beacon/`** — standalone beacon: broadcasts ESP-NOW
  frames at 25 Hz; on S2/S3/C3/C6 chips also enables an 802.11mc FTM
  responder. Use it on a piggyback board if your drone runs flight firmware
  you'd rather not touch (for ESP-FC there's a simpler one-line patch — see
  `docs/espblast.md`).
- **`firmware/rx_node/`** — 3–4 ground sniffer nodes. Promiscuous mode,
  filter on the drone's MAC, median RSSI every 250 ms → ESP-NOW to the hub.
  These never transmit toward the drone.
- **`firmware/hub_node/`** — relays node reports to the laptop as JSON lines
  over USB serial.
- **`firmware/rx_node_ftm/`** — optional upgrade: time-of-flight ranging
  (~0.5–2 m accuracy, no RSSI calibration). Needs ESP32-S2/S3/C3/C6 on both
  ends — **not applicable to the ESP-BLAST's WROOM-32**.
- **`firmware/mac_scanner/`** — helper: sweeps channels 1–13 and prints
  every transmitter MAC with frame rate and RSSI, so you can identify your
  drone's MAC and channel before configuring the sniffers.
- **`ground_station/server.py`** — the radar console: a local web GUI
  (Python asyncio + WebSocket + canvas) with a PPI-style scope (range
  rings, phosphor trail, velocity vector, uncertainty halo), per-node
  health cards with RSSI sparklines, serial port picker, sim mode, session
  recording, drag-to-place node layout, and a built-in calibration wizard.
  `python server.py` → <http://localhost:8080>.
- **`ground_station/locate.py`** — headless CLI: converts RSSI → distance
  (log-distance path-loss model), solves position by weighted nonlinear
  least squares, smooths with an EMA, prints JSON fixes. `server.py`
  imports its solver, so both share one implementation.

Hardware shopping list with prices: [`hardware/BOM.md`](hardware/BOM.md)
(~$56 core system).

### Interception (the end goal)

Because both drones are ESP32 emitters, the same ground radar can track **both**
and fly one to the other. ESP-FC has no autonomous navigation, so **the laptop
is the autopilot**: it multilaterates both drones, runs a guidance law, and
streams RC channels to the interceptor via a tethered "commander" ESP32 (which
*is* the drone's radio over espnow-rclink). Full architecture, verified against
the esp-fc / espnow-rclink source, plus the honest performance envelope and the
safety/legal bright lines, is in [`docs/interception.md`](docs/interception.md).

- **`ground_station/guidance.py`** — guidance laws (position+velocity tracking
  with target-velocity feed-forward and latency compensation; pure pursuit;
  proportional navigation) and the world-accel → attitude → RC-channel mapping.
- **`ground_station/digital_twin.py`** — full **3D digital twin** of the whole
  system (both quads, radar + barometer sensor suite, latency, guidance), for
  testing the end goal before risking hardware. See
  [`docs/3d-sensing.md`](docs/3d-sensing.md).
- **`ground_station/geometry.py`** — node-layout geometry analysis (where to
  put nodes; why coplanar nodes can't measure altitude).
- **`ground_station/pursuit_sim.py`** — closed-loop interception simulation
  reusing the real solver and RSSI noise model (Monte-Carlo, envelope sweep,
  plots). Empirically: reliably arrives within ~2 m of a slow/hovering target;
  the ESP-BLAST at top speed is uncatchable with RSSI.
- **`ground_station/autopilot.py`** — the host pilot (fixes → guidance → RC
  frame → commander), defaulting to DISARMED + dry-run, with geofence/fail-safe.
- **`firmware/commander/commander.ino`** — the espnow-rclink transmitter bridge.
- GUI **Pursuit demo** — live two-drone visualization in the radar console.

What it can do: **fly to and loiter within a couple of metres of a hovering or
slowly-drifting (≤~3 m/s) target, scored by range.** What it can't: catch a
fast drone, or make physical contact (that needs UWB or onboard terminal
guidance). This is a *tracking* system — never weaponized, see the doc.


### Active FMCW radar (MIT coffee-can architecture) — the reflection radar

The passive system above needs the target to transmit. An **active FMCW radar**
does not: it transmits a swept carrier and measures the echo, giving true range
and velocity off a non-cooperative target. Full build plan, parts list, custom
Vivaldi antenna and simulation workflow:
**[`docs/mit-radar.md`](docs/mit-radar.md)**.

- **`ground_station/fmcw_sim.py`** — FMCW system simulator + link budget
  (chirp → echo → beat → range-Doppler map, with TX leakage and ADC dynamic
  range). Answers "can it see my drone?" before you spend $460.
- **`antenna/vivaldi.py`** — designs the custom tapered-slot antenna that
  replaces the coffee cans; exports an SVG outline for KiCad and an openEMS
  verification scaffold.

⚠️ **Before building it:** a 2.4 GHz radar will jam a 2.4 GHz ESP-NOW control
link. Move the drone to a 915 MHz ELRS link first — see §0 of the plan.

### Tracking, mmWave and antennas

- **[`docs/tracking.md`](docs/tracking.md)** — the Tier-1 Kalman filter, and the
  measurement showing it is a *downgrade* on today's RSSI sensor and a win once
  FTM lands. `ground_station/tracker.py` ships it, gated on
  `speed x latency > sigma`; the console shows which estimator is live.
- **[`docs/mmwave.md`](docs/mmwave.md)** — buying a TI IWR6843 instead of
  building a passive front end: 3.7 cm range cells, ~11 cm cross-range at 10 m,
  sees the airframe with no beacon at all. Most of this repo survives the swap.
- **[`docs/antenna.md`](docs/antenna.md)** — optimum pyramidal horn
  (`antenna/horn.py`), the pe==ph realizability constraint, the `G <= 4piA/l^2`
  sanity check, and the five-study HFSS methodology.

**Master build guide (whole system: both drones + radar + interception, with a
priced parts list and ordered steps): [`docs/BUILD.md`](docs/BUILD.md).**
Radar-only setup detail is in [`docs/SETUP.md`](docs/SETUP.md).

Try the GUI right now with zero hardware:

```bash
cd ground_station && pip install -r requirements.txt
python server.py --sim        # then open http://localhost:8080
```

## Quickstart

1. **Make the drone transmit trackably** (≥10 Hz): ESP-BLAST/ESP-FC → the
   one-line alive-interval patch in `docs/espblast.md`; any other ESP32
   drone → flash or piggyback `firmware/drone_beacon/drone_beacon.ino`.
   Find the drone's MAC and channel with `firmware/mac_scanner/` (the
   beacon also prints its MAC at boot).
2. **Flash 3 sniffer nodes**: in `firmware/rx_node/rx_node.ino`, set
   `DRONE_MAC` to that MAC and give each board a unique `NODE_ID` (1, 2, 3).
   You'll need `HUB_MAC` from step 3 — flash the hub first if easier.
3. **Flash the hub**: `firmware/hub_node/hub_node.ino`; note the MAC it
   prints and put it into the sniffers' `HUB_MAC`. Keep every firmware on
   the same `WIFI_CHANNEL` (default 7, the espnow-rclink default).
4. **Place the nodes** in a triangle around the flight area (baseline ≥ 6 m,
   antennas vertical, ~1 m high). Tape-measure their positions and enter them
   in `ground_station/config.json`.
5. **Calibrate** (once per node placement):
   ```bash
   cd ground_station && pip install -r requirements.txt
   python calibrate.py --hub /dev/ttyUSB0 --dist 1.0 --seconds 20
   ```
   Hold the powered drone 1 m from each node during capture; copy the
   reported `rssi0` values into `config.json`.
6. **Fly and locate**:
   ```bash
   python locate.py --hub /dev/ttyUSB0 --plot
   ```

No hardware yet? Test the whole solver pipeline with synthetic data:

```bash
python locate.py --sim --plot
```

## What accuracy to expect

| Mode | Accuracy @ 5–10 m | Notes |
|------|-------------------|-------|
| RSSI (default) | 1–3 m | Sensitive to multipath and antenna orientation; median filter + EMA already applied. Best outdoors with line of sight. |
| FTM upgrade | ~0.5–2 m | Needs S2/S3/C3/C6 chips both ends (not the ESP-BLAST's WROOM-32); run `rx_node_ftm` nodes on their own USB ports and add them with `--port`. |
| UWB (DW3000) | 0.1–0.3 m | Future path, see BOM. |

Tips that matter more than code: identical antenna orientation on all nodes,
nodes ≥ 1 m off the ground, drone inside the node triangle, and a clean
calibration. If fixes wander, raise `path_loss_n` toward 2.5 (cluttered
environments) and re-calibrate.

## Legal / safety

Receive-only monitoring of your **own** transmitter, plus standard 802.11
exchanges with your **own** devices. The sniffer filters on your drone's MAC
and discards everything else. No jamming, no deauth, nothing directed at
third parties.

</details>
