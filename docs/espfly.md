# ESP-FLY integration (XIAO ESP32-S3 + esp-fc + espnow-rclink)

The mirror of [`espblast.md`](espblast.md) for the ESP-FLY airframe. Same
firmware stack, so that doc applies almost verbatim — **with four differences
that come from the chip and the airframe**, and two corrections to what this
repo previously assumed.

## What changed vs the ESP-BLAST

| | ESP-BLAST (WROOM-32) | **ESP-FLY (XIAO ESP32-S3)** |
|---|---|---|
| FTM ranging | ✗ no hardware | **✓ supported — use it** |
| Barometer | BMP280 | **none — altitude needs a ceiling node** |
| Piggyback beacon board | possible | **no, 25 g airframe** |
| Beacon without patching | needs the alive-interval patch | **free: the AP beacons at ~10 Hz** |

## 1. You get a 10 Hz beacon for free — no firmware patch needed

When esp-fc is built for the S3 with the **built-in ESP-NOW receiver** (the
"SPI Rx" option), it starts an **open access point named `ESP-FC` at boot and
leaves it up during flight** (`Wireless.cpp:9-25`). That AP radiates standard
802.11 beacons at roughly **10 Hz**, which the sniffer nodes can track with no
patch at all. The arming lockout applies only to the separate rescue-config
WiFi mode, not to this AP.

The espnow-rclink link itself is *not* a good beacon: v0.1.1 sends pair
requests at 20 Hz **before** pairing and then only a **1 Hz keepalive** in
flight (`Protocol.h`). So the AP beacons are what you actually track.

Want more than 10 Hz? The one-line alive-interval patch from `espblast.md`
still works and stacks on top (→ 25 Hz). It is now **optional**, not required.

## 2. You must fly on ESP-NOW — ELRS is untrackable

With an **external ELRS receiver, esp-fc never brings WiFi up at all**, and the
ELRS link itself is LoRa, which an ESP32 sniffer cannot decode. There is
nothing for the ground network to hear.

> **If you want the passive radar to work, fly the ESP-NOW link.**
> This directly reverses the recommendation in `mit-radar.md` §0, which said to
> move to 915 MHz ELRS to keep the *active* radar from jamming the control
> link. Both statements are true — they just belong to different systems:
> - **passive RF tracking → must use ESP-NOW** (you need something to hear)
> - **active 2.4 GHz FMCW radar → must leave 2.4 GHz** (or it jams you)
>
> You cannot run the 2.4 GHz coffee-can radar and the ESP-NOW tracker at the
> same time on the same drone. Pick one per flight, or move the active radar
> to 60 GHz (see [`mmwave.md`](mmwave.md)), which removes the conflict entirely
> because it neither needs nor disturbs the 2.4 GHz band.

## 3. Channel is 1, not 7

The rclink receiver adopts whatever channel the softAP is on, and esp-fc's
Arduino `softAP()` call uses the **default, channel 1** — not the channel 7
this repo previously assumed. `firmware/rx_node/rx_node.ino` now defaults to 1.

**Always confirm with `firmware/mac_scanner` before flashing the sniffers.**

## 4. FTM is real on this drone — and it is the accuracy step that matters

The S3 has the FTM hardware and esp-fc already runs a softAP, so enabling the
responder is **one extra argument on that `softAP()` call** in `Wireless.cpp`.
`firmware/rx_node_ftm/` then ranges against the `ESP-FC` network directly,
giving **time-of-flight distance with no RSSI calibration at all**.

This is not a nice-to-have. Measured in `ground_station/tracker.py`, moving
from RSSI (~1.5 m) to FTM (~0.6 m) is the step that makes the tracking filter
worth switching on — see [`tracking.md`](tracking.md).

## 5. No barometer → put a node on the ceiling

The ESP-FLY has no baro, so the trick used in `3d-sensing.md` (take altitude
from the drone) is unavailable. Altitude has to come from the geometry, and
**coplanar nodes cannot measure it**. The fix is one node out of the plane:

```
3 floor nodes at 0.3 m + 1 CEILING node at 2.6 m, 5 x 6 m room:
   drone at 0.8 m -> sigma_h 1.94 m, sigma_v 0.70 m
   drone at 1.2 m -> sigma_h 2.01 m, sigma_v 0.54 m   <- checkpoint: < 1 m PASS
   drone at 2.0 m -> sigma_h 2.30 m, sigma_v 0.23 m
```

That layout is now the default in `ground_station/config.json`, with
`solve_3d: true`. Verify your own room with:

```bash
python ground_station/geometry.py          # sigma_h / sigma_v for your layout
```

## Parts (indoor 5 × 6 m room, ~$85)

Drone side: nothing new — XIAO ESP32-S3, kit antenna, RP1 V2, T8L, and a
patched esp-fc build.

| Item | Qty | ~$ | Why |
|---|---|---|---|
| ESP32-S3 dev board w/ u.FL (XIAO S3 fine) | 5 | 30 | 4 sniffers + 1 hub; S3 gives RSSI **and** FTM |
| 2.4 GHz u.FL dipole | 4 | 8 | steadier than PCB antennas; mount all vertical |
| USB-C cables + 5 V wall adapters | 5 | 15 | indoors, mains beats power banks |
| Ceiling mount (adhesive hook/strip) | 1 | 3 | **this is what makes altitude solvable** |
| Small tripods/stands | 3 | 10 | floor nodes at ~0.3 m in three corners |
| Laser distance meter | 1 | 20 | anchor error goes straight into the fix |

## Build order (each step has a checkpoint — don't skip them)

1. **Patch and build esp-fc.** In `Wireless.cpp`: start the AP unconditionally
   rather than only for the ESP-NOW receiver; pass the **FTM responder flag**
   to `softAP()`; drop WiFi TX power to ~8 dBm (nodes are within 10 m).
   Optionally add a 25 Hz ESP-NOW broadcast beacon in the main loop, copied
   from `firmware/drone_beacon`. Build/flash with PlatformIO, `esp32s3` target.
   **Checkpoint:** `mac_scanner` shows one MAC at the expected rate, and T8L
   link quality is unchanged with the AP up.
2. **Flash the ground network.** Hub first, note its MAC. Then four `rx_node`
   boards with unique IDs, the drone's **AP MAC** (from esp-fc's CLI `wifi`
   command), the hub MAC, and the scanned channel (probably 1).
   **Checkpoint:** the hub prints a JSON line from every node every ~250 ms.
3. **Add FTM ranging.** Flash `rx_node_ftm` with SSID `ESP-FC`, open network.
   Worth doing: forward FTM distances to the hub over ESP-NOW like the RSSI
   nodes, so a ceiling node doesn't need its own USB run.
   **Checkpoint:** printed distance matches a tape measure within 1 m at 3 m.
4. **Lay out and calibrate.** Three floor corners at 0.3 m, one on the ceiling
   above the flight area centre. Measure every position **including z** into
   `config.json`. Calibrate each node's 1 m reference RSSI with the drone on
   USB power sitting on a box — *not in your hand*.
   **Checkpoint:** `geometry.py` reports vertical sigma < 1 m at room centre.
5. **Run the console.** `python ground_station/server.py`, open
   <http://localhost:8080>. Hover in the middle of the room first.
