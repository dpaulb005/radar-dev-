# Full setup plan — ESP-BLAST drone + passive RF radar

> **Passive system — archived.** The current radar bring-up is
> [`radar-software.md`](../radar-software.md).


The complete path from parts on the bench to a live radar display, in five
phases. Each phase ends with a checkpoint you can verify before moving on —
do not skip checkpoints; every debugging hour in this hobby is spent on a
skipped checkpoint.

Time budget: roughly one evening per phase. Cost: ~$56 in radar hardware
(see `hardware/BOM.md`) on top of the drone build itself.

---

## Phase 0 — Bench prerequisites

- [ ] Drone built per the ESP-BLAST Instructable through Step 10 (ESP-FC
      flashes and Betaflight configurator connects)
- [ ] ESP-NOW transmitter working (drone arms and responds to sticks)
- [ ] Radar parts on hand: 4× ESP32 dev boards, cables, 3 power banks
- [ ] Laptop with Python 3.10+ and Arduino IDE (with the `esp32` board
      package installed)
- [ ] This repo cloned; `pip install -r ground_station/requirements.txt`

---

## Phase 1 — Make the drone trackable (30 min)

A stock ESP-BLAST transmits a keepalive only once per second, which is too
slow to track. Full background and both options: `docs/espblast.md`.

1. In your esp-fc working copy, build once so PlatformIO fetches deps:
   `pio run -e esp32`
2. Edit `.pio/libdeps/esp32/EspNowRcLink/include/EspNowRcLink/Protocol.h`:
   change `LINK_ALIVE_INTERVAL_MS = 1000` → `40`.
3. Reflash: `pio run -e esp32 -t upload` (same bootloader-jumper procedure
   as the Instructable's Step 10).
4. Confirm the drone still binds to the transmitter and arms normally.

**Checkpoint 1:** flash `firmware/mac_scanner/` onto any spare ESP32, open
the serial monitor (115200). With drone + transmitter powered you should see
one MAC on the RC-link channel (default **7**) at ~25 Hz. Write down that
MAC and channel — you need both in Phase 2. Power-cycle the drone and watch
the MAC vanish/return to confirm it's really the drone.

---

## Phase 2 — Build the sensor network (1–2 h)

All three sketches are in `firmware/`; flash order matters only in that the
hub prints the MAC the sniffers need.

1. **Hub** (`hub_node/hub_node.ino`): set `WIFI_CHANNEL` to the channel from
   Checkpoint 1, flash, note the MAC it prints at boot. Stays on your
   laptop's USB.
2. **Sniffers** (`rx_node/rx_node.ino`) × 3: set `NODE_ID` (1, 2, 3 —
   unique), `DRONE_MAC` (Checkpoint 1), `HUB_MAC` (step 1), `WIFI_CHANNEL`.
   Flash each; label the boards physically with their number.
3. Power the sniffers from the power banks.

**Checkpoint 2:** with drone + transmitter on, open a serial monitor on the
hub. You should see one JSON line per node roughly every 250 ms, e.g.
`{"node":2,"rssi":-51,"n":6,"t":184039}`. If a node is silent: wrong
channel, wrong `DRONE_MAC`, or wrong `HUB_MAC` — in that order of
likelihood. Close the serial monitor when done (the GUI needs the port).

---

## Phase 3 — Field layout & calibration (45 min, at the flying site)

1. Place the 3 sniffer nodes in a triangle **around** the intended flight
   box, baselines ≥ 6 m, antennas vertical, ~1 m off the ground (tripods,
   stakes, or fence posts).
2. Pick an origin (e.g. node 1's stake), measure every node's (x, y, z)
   with a tape measure to ~10 cm.
3. Start the GUI: `cd ground_station && python server.py` → open
   <http://localhost:8080>.
4. Enter the node positions: press **EDIT LAYOUT** on the scope and drag
   each node marker to its measured spot (or edit `config.json` directly —
   the GUI persists to the same file).
5. Connect the hub in the **Link** panel (pick the port, press Connect).
   All three node cards should go **LIVE**.
6. Calibrate each node from the **Calibration** panel: select the node,
   hold the powered drone 1.0 m from it at antenna height (prop it on a
   box — don't hold it; your body absorbs 2.4 GHz), press **Start**, wait
   out the progress bar, press **Apply**. Repeat per node.

**Checkpoint 3:** place the drone at a known spot inside the triangle
(e.g. dead center). The blip on the scope should sit within ~1–2 m of
truth and the RESID tile should read < ~2 m. Walk the drone slowly around
the box and watch the blip follow.

---

## Phase 4 — Flight test (first calm day)

1. Start a recording (**Record** button) — every raw report and fix goes to
   `ground_station/recordings/rec-*.jsonl` for later analysis.
2. Hover in the middle of the box at ~1.5 m. Expect a steady blip, 1–2 m
   wander, solver at ~4 Hz (limited by the nodes' 250 ms report window).
3. Fly slow laps. Watch the **RESID** tile: residual spikes mean the RSSI
   model is being violated (multipath, antenna shadowing) — normal during
   banking, should recover in hover.
4. Fast passes: expect the blip to lag and smear (EMA smoothing + antenna
   pattern shifts). This is a physics limit of RSSI at 4 Hz, not a bug.

**Checkpoint 4:** a recorded session where hover fixes stay within ~2 m of
where you actually hovered. That's the system working as designed.

---

## Phase 5 — Tuning & upgrades (optional)

| Symptom | Fix |
|---|---|
| Fixes biased toward one node | Re-run that node's calibration; check its antenna is vertical |
| Blip wanders in clean line-of-sight | Raise path-loss n toward 2.4–2.5 (Model panel), recalibrate |
| Node card SLOW/LOST intermittently | Power bank auto-sleeping (add a load resistor or use a different bank); or RF shadowing — raise the node |
| Solver rate < 3 Hz | A node isn't reporting — check Checkpoint 2 for it |
| Want sub-meter accuracy | UWB path in `hardware/BOM.md` (weight caveat applies) |
| Want a 4th node / 3D fixes | Add a board as `NODE_ID 4`, add it in config, done — the solver uses all reporting nodes |

---

## Operating reference (GUI)

`python server.py` then <http://localhost:8080>. Also reachable from a
phone on the same network via `python server.py --host 0.0.0.0` (own
devices on your own network only).

- **Scope**: wheel = zoom, drag = pan, double-click = auto-fit. Range rings
  center on the node centroid; dashed circles are each node's live measured
  distance; the halo around the blip is the solver residual; the line from
  the blip is the velocity vector (1 s lookahead).
- **EDIT LAYOUT**: drag node triangles to update positions (persisted).
- **Sim mode**: full synthetic flight for testing every part of the GUI
  with zero hardware — the dashed ring is the simulated ground truth.
- **Record**: JSONL session logs in `ground_station/recordings/`.
- Headless / scripted use: `locate.py` and `calibrate.py` still work as
  CLI tools against the same `config.json`.
