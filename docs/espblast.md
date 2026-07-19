# Integrating with the ESP-BLAST (Max Imagination's ESP32 rocket drone)

This guide adapts the localization system to the specific hardware and
firmware of the ESP-BLAST build:

- **MCU: ESP32-WROOM-32** (original ESP32) on a custom 4-layer FC PCB,
  u.FL external antenna mod
- **Flight firmware: ESP-FC** (`rtlopez/esp-fc`), compiled and flashed by you
  with PlatformIO (`pio run -e esp32 -t upload`)
- **RC link: ESP-NOW** via the `EspNowRcLink` library (`rtlopez/espnow-rclink`),
  ESP32-based handheld transmitter
- Analog 5.8 GHz FPV VTX + MinimOSD, GPS, BMP280 barometer, MPU9250 IMU

## What this means for the tracker

### 1. FTM is off the table

The ESP32-WROOM-32 has no 802.11mc FTM hardware. Ignore
`firmware/rx_node_ftm/` and the FTM responder half of `drone_beacon` for this
drone — it applies only if you ever rebuild around an S2/S3/C3/C6. **RSSI
multilateration is the mode to use.**

### 2. The RC link lives on WiFi channel 7 by default

`EspNowRcLink` defines `WIFI_CHANNEL_DEFAULT = 7`. All the firmware in this
repo now defaults to channel 7 to match. If your link uses a different
channel, find it with `firmware/mac_scanner/` and set `WIFI_CHANNEL`
consistently everywhere.

### 3. A stock ESP-BLAST barely transmits — one small patch fixes that

The espnow-rclink protocol is transmitter-driven. The drone (receiver side)
only sends:

| Message | When | Rate |
|---|---|---|
| `PAIR_REQ` (broadcast) | powered on, not yet paired | 5 Hz |
| `FC_ALIVE` (unicast to TX) | while paired/flying | **1 Hz** (`LINK_ALIVE_INTERVAL_MS = 1000`) |

1 sample/second/node is far too slow to track a moving drone (the solver
wants ≥ 10 Hz of frames). Two ways to fix it — pick one:

#### Option A (recommended, free): raise the alive rate in your esp-fc build

You already compile esp-fc yourself, so change one constant in its
espnow-rclink dependency and reflash:

1. Build once (`pio run -e esp32`) so PlatformIO fetches dependencies.
2. Open `.pio/libdeps/esp32/EspNowRcLink/include/EspNowRcLink/Protocol.h`
   (path may vary slightly by version; search the file for
   `LINK_ALIVE_INTERVAL_MS`).
3. Change:
   ```c
   // before
   LINK_ALIVE_INTERVAL_MS = 1000
   // after — 25 alive frames per second
   LINK_ALIVE_INTERVAL_MS = 40
   ```
4. `pio run -e esp32 -t upload` and reflash the drone.

The alive frame is a few bytes; at 25 Hz this is negligible airtime and the
transmitter simply treats each one as a link-is-up refresh. Note that
PlatformIO may re-download the library if you clean or bump versions —
re-apply the edit if `pio run -t clean` ever wipes `.pio/libdeps`.

Bench-verify before flying: with drone and transmitter both on, run the hub
and confirm each rx_node reports ~every 250 ms with `n` around 6 (25 Hz ×
0.25 s).

#### Option B (no firmware changes): piggyback beacon board

Solder a bare ESP32-C3 Super Mini (~$3, ~2.5 g) to the drone's 5 V buck
output (5V/GND pads) and flash it with `firmware/drone_beacon/`. It
broadcasts 25 Hz beacons independently of the flight electronics.

- Set the beacon's `WIFI_CHANNEL` to the same channel as the RC link (7) so
  one set of sniffer nodes hears everything; its tiny 25 Hz frames won't
  meaningfully contend with the control link.
- Weight note: on a ~40 g-frame mini quad, 2.5 g is real but flyable. Skip
  the pin headers, solder wires directly, and zip-tie it in the battery bay.
- The `DRONE_MAC` you give the sniffers is then the *C3's* MAC (printed at
  boot), not the flight controller's.

### 4. Finding the drone's MAC and channel

For Option A you track the flight controller's own STA MAC. Easiest way to
get it (works for any option): flash a spare board with
`firmware/mac_scanner/`, power the drone (and transmitter, if paired), and
watch the table it prints — the drone shows up as a MAC with a steady frame
rate that follows the alive/beacon rate you configured. The scanner also
tells you which channel the traffic is on. Put that MAC into `DRONE_MAC` in
`firmware/rx_node/rx_node.ino`.

### 5. Calibration with this airframe

The ESP-BLAST's u.FL whip antenna is roughly a vertical dipole when the
drone is belly-down. Calibrate (`ground_station/calibrate.py`) with the
drone powered, propped in its normal hover orientation at 1 m from each
node, ideally on a cardboard box rather than in your hand (bodies absorb
2.4 GHz and skew rssi0 by several dB). Expect extra RSSI wobble when the
drone pitches over into fast forward flight — the antenna pattern changes.
The solver's median + EMA filtering absorbs some of this; don't expect
better than ~2-3 m during aggressive passes. For calm hover in the 5-10 m
box, 1-2 m is realistic.

### 6. Also worth knowing: the 5.8 GHz VTX option

The ESP-BLAST's analog FPV camera transmits continuously on 5.8 GHz — a
perfect always-on tracking signal that needs zero drone modifications.
Cheap RX5808 receiver modules (~$10) expose an analog RSSI pin an ESP32 can
read; this is exactly how RotorHazard race timers detect drone proximity
per gate. Trilateration accuracy is coarser than 2.4 GHz ESP-NOW sniffing
(analog RSSI, strong antenna-pattern dependence), so this repo doesn't
implement it — but if you later want tracking with a bone-stock drone,
3 × (RX5808 + ESP32) ≈ $45 is the path, and the RotorHazard project is the
reference design to borrow from.

## Quick checklist for the ESP-BLAST

- [ ] Patch `LINK_ALIVE_INTERVAL_MS` → 40 in your esp-fc tree, reflash (Option A)
- [ ] `mac_scanner`: confirm channel (default 7) and record the drone's MAC
- [ ] Put MAC + channel into `rx_node.ino`, flash 3 sniffer nodes + hub
- [ ] Nodes in a ≥6 m triangle around the flight box, antennas vertical, ~1 m high
- [ ] `calibrate.py` at 1 m per node → `config.json`
- [ ] `locate.py --hub <port> --plot`, hover test before fast passes
