# mmWave front end (TI IWR6843) — buying the radar instead of building it

The honest summary of the trade: **a bigger drone does not rescue the passive
reflection idea; buying an active mmWave sensor does, and it makes the whole
beacon problem disappear.**

## Why size is not the binding constraint

RCS scales with the airframe, so a bigger drone does echo louder — about 18 dB
from the ESP-FLY to a metre-span hex. Not enough, and not the real problem:

| drone | RCS | echo below the direct path at 5 m |
|---|---|---|
| ESP-FLY, 67 mm | 0.005 m² | 48 dB |
| 5-inch freestyle | 0.02 m² | 42 dB |
| 450-class / 7-inch | 0.08 m² | 36 dB |
| large hex, 1 m | 0.30 m² | 30 dB |

Two things kill it regardless of size. The **direct signal still swamps the
echo by 30 dB even on the biggest airframe.** And **range resolution comes from
bandwidth alone**: a 20 MHz WiFi illuminator is a 7.5 m range cell no matter
what is flying in it — your ELRS link, under 1 MHz, is a 150 m cell. A bigger
target changes neither number, and gets flown further away, where the echo
ratio falls as the fourth power of range.

## What an active mmWave sensor changes

All three objections dissolve at once. **You control the transmitter**, so
there is no uncooperative direct path to cancel. A 60 GHz chip sweeps **4 GHz**
of bandwidth — a **3.7 cm** range cell instead of 7.5 m. And it costs a few
hundred dollars, not the $500+ a coherent passive front end needs.

Detection range from the radar equation at 13 dB minimum SNR:

| sensor | ESP-FLY | 5-inch | 450-class | large hex |
|---|---|---|---|---|
| **TI IWR6843, 60 GHz** | **13 m** | 19 m | 27 m | 37 m |
| TI AWR1843, 77 GHz | 13 m | 19 m | 27 m | 37 m |
| Infineon BGT60 | 7 m | 10 m | 13 m | 19 m |

Your current 25 g drone is trackable to ~13 m, which covers an indoor room.

**On angles, keep resolution and accuracy separate.** Angular *resolution* is
coarse (~14° azimuth) and only matters if you need to separate two drones
flying close together. For locating **one** drone, *accuracy* is what counts:
~**0.6°** at 20 dB SNR, which is **11 cm of cross-range error at 10 m**.
Combined with centimetre range accuracy that is roughly **10× better than the
RSSI system**.

There is also a clean signature to lock onto: spinning props put the blade tips
at ~110 m/s, which at 60 GHz is a **44 kHz Doppler shift**. Nothing else in a
room does that, so static clutter from walls and furniture drops out easily.

And the part that should appeal most: **it sees the airframe itself.** No
beacon, no MAC filter, no esp-fc patch, no choosing between ELRS and ESP-NOW to
keep WiFi alive. The whole ESP-NOW-vs-ELRS constraint in
[`espfly.md`](espfly.md) §2 stops applying.

## What to buy

**IWR6843AOPEVM.** The antenna is on the package, so there is nothing to build,
it runs off USB, and it streams a 3D point cloud over serial from the stock
demo. Critically it has a **wide field of view in both azimuth and elevation** —
the cheaper ISK variant is only ~30° in elevation and would give you poor
altitude, which is precisely the axis you are already short of.

Typical price for these evaluation modules is **$200–350**; I could not confirm
today's figure (DigiKey blocked the fetch), so check before ordering.
**Skip the $30 presence-detection modules** — they do not expose enough raw
data to track anything.

## What survives the swap

Most of the repo. The web console, the scope, node health cards, session
recording, the geometry tools and the tracking filter all work on **any** source
of 3D fixes. What changes is only the front end:

| layer | today | with mmWave |
|---|---|---|
| sensing | 4 sniffer nodes | the module itself, on USB |
| fixes | multilateration solver | serial reader parsing the point cloud + clustering to pick the drone out of the returns |
| hub | ESP32 hub board | the radar |
| filter | gated off (see `tracking.md`) | **the filter comes into its own** — Doppler gives velocity directly, 8× better |

**Keep the RF system rather than deleting it.** Two independent sensors that
fail in different ways is a genuinely better tracker, and the existing code
already fuses multiple range sources.

## On eventually building your own

Be clear which part you mean. Designing a 60 GHz front end from scratch means
Rogers substrate, sub-millimetre antenna tolerances and RF layout that is hard
to get right without lab equipment. The realistic build is **your own carrier
board and antenna array around a bare module, plus your own signal processing
replacing the TI demo** — which is where the interesting work is anyway.

If you want the from-first-principles experience, that is exactly what
[`mit-radar.md`](mit-radar.md) is for. It is excellent for learning, but its
narrow sweep gives ~1–1.8 m of range resolution, so **it will not beat the
module you bought.** Build it to understand radar; buy the module to track the
drone.
