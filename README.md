# radar-dev — passive RF localization for an ESP32 drone

Locates an ESP32-equipped drone within a ~5–10 m flight area using its own
2.4 GHz transmissions, for well under $150.

**Important scope note:** the original idea — a true passive radar detecting
*reflections* of the controller's signal off the drone — is not physically
achievable at 5–10 m on a hobby budget (the echo is ~45 dB below the direct
signal, and 20 MHz of bandwidth gives 7.5 m range resolution: one range cell
covers the whole area). The full analysis is in
[`docs/feasibility.md`](docs/feasibility.md). What *does* work, and what this
repo implements, is **passive emitter localization**: receive-only sniffer
nodes measure the drone's own WiFi frames and multilaterate its position.
Same goal, achievable physics.

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
- **`ground_station/locate.py`** — converts RSSI → distance (log-distance
  path-loss model), solves position by weighted nonlinear least squares,
  smooths with an EMA, prints JSON fixes and optionally live-plots.

Hardware shopping list with prices: [`hardware/BOM.md`](hardware/BOM.md)
(~$56 core system).

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
