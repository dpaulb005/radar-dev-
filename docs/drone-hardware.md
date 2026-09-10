# ESP-FLY drone hardware — step by step (915 MHz ELRS link)

**Build the kit exactly as its official guide says** — the ESP-FLY tutorial
video and Elektor article linked from `Seeed-Projects/Co-Create_ESP-FLY`:
XIAO ESP32-S3, the flight-controller board, MPU-6050, four 615 coreless
motors, 30 mm props, 1S battery.

Then make **one change that is not in the kit's guide**: the drone flies on a
**915 MHz** control link, not on its own 2.4 GHz WiFi.

## What the airframe actually is

Worth being precise about, because the radar cares about the shape and because
the 3-D model in [`../hardware/3d/drone.html`](../hardware/3d/drone.html) is
built to it. The ESP-FLY is an **X-frame**, not a box:

- one printed part — a 24 mm centre plate, four **two-prong arms** fanning out
  to four **cylindrical motor pods** at 37 mm pitch, and a **bumper ring**
  joining the pods. Pod edge to pod edge is the 46 mm the kit quotes;
- four **landing legs**, each 25 mm of solid-core jumper wire bent into a V and
  pushed into holes at a pod base;
- a small printed **canopy** on the centre plate, about 24 mm square and 12 mm
  tall, closed by the engraved **ESP FLY cover**. The USB-C looks out of a
  window in its nose; the FC board and the XIAO stack inside it on headers;
- the **1S pack hangs underneath** the centre plate in a zip-tie strap, long
  axis fore and aft, its leads coming up into the canopy's nose opening.

Nothing is glued but the motors (a spot of superglue in each pod). Heights:
**29 mm** to the top of a motor, **31 mm** to the blade plane, **67 mm** across
the props.

## 0. Why, and what it costs

The radar's sweep and the drone's control link cannot share 2.4 GHz. Every WiFi
channel sits inside 2400–2483.5 MHz, so sweeping *around* one caps the radar at
about **43 MHz** whichever channel you pick. Moving the link to 915 MHz — 1.5 GHz
away, zero interaction — gives the radar the **whole band, 83.5 MHz**, and that
is not a small gain indoors:

| | 40 MHz (sweeping around WiFi) | **83.5 MHz (link on 915)** |
|---|---|---|
| range cell `c/2B` | 3.75 m | **1.80 m** |
| beat slope | 41.70 Hz/m | 87.04 Hz/m |
| target FFT bin at 3 m | 0.80 — inside the DC lobe | **1.67** |
| range error in a 4 m room at 2 m | +0.54 m | **+0.02 m** |
| range error at 1.0 m | no fix at all | +0.17 m |

In a small room that is the difference between a coarse detector and a real
ranging instrument — see [`testing.md`](testing.md) § a small room changes the
answer. In a garage or a garden at 5–10 m the 40 MHz sweep is perfectly usable,
so **if you have the space, you do not need any of this**.

The cost is **≈ $130** and a firmware change: you stop flying from a phone and
start flying with sticks.

## 1. Fit the 915 MHz receiver, not the 2.4 GHz one

The kit's optional radio path (an ESP-NOW transmitter, or the ELRS **RP1 V2**)
is 2.4 GHz and hops across the whole band at 25–100 mW, straight through the
radar's sweep in both directions. **Do not fit it.** If you already did,
unsolder it (−0.9 g).

Fit instead a **915 MHz ELRS nano receiver** — BetaFPV ELRS Nano 915 (0.7 g) or
HappyModel ES900RX (0.6 g). Same four pads, same CRSF wiring as the RP1 V2:

| receiver pad | XIAO ESP32-S3 |
|---|---|
| **3V3** | the drone has no 5 V in flight (the XIAO's 5 V pin is USB VBUS); the published esp-fc guide powers the receiver from 3V3 |
| GND | GND |
| **TX** (receiver → FC) | **GPIO 9** = UART2 RX |
| **RX** (FC → receiver, telemetry) | **GPIO 8** = UART2 TX |

Full wiring and the parts list are in [`drone-link.md`](drone-link.md); the
firmware side is [`drone-link-espfc.md`](drone-link-espfc.md).

**Checkpoint 1:** with the drone powered and the transmitter on, the receiver's
LED goes **solid** within a few seconds — bound, on 915.

## 2. Turn the drone's WiFi off, and keep the antenna

The XIAO's on-board antenna still serves its WiFi, which esp-fc does not use for
control. Leave the antenna alone — there is nothing to change — but make sure
nothing is transmitting on it during a radar session. The 915 MHz receiver
brings its own ~80 mm wire or "T" antenna; route it away from the flight
controller and away from the motors.

**Checkpoint 2:** with the drone powered, a WiFi-analyser app on the phone shows
**nothing** from the drone. If it still advertises `ESP-DRONE-xxxx`, esp-fc is
not running or WiFi is still enabled — fix that before flying near the radar.

## 3. Make the drone a good radar target (optional, free)

A 25 g quad's radar cross-section is small (**~0.01 m² is assumed in every link
budget in this repo and has been measured by nobody** — it could be several times
lower). At 10 m the thermal margin is large enough that it does not need help.
If you want more echo, a 30 mm square of copper tape laid flat on the top plate
roughly doubles it. Free, and worth doing for the first flights.

## 4. Where to hover

The horns' beams are 34° × 36°. At 5 m that is a ~3 m wide, ~3 m tall window.
Fly inside the sector at 3–10 m from the horns, at horn height ±1.5 m.

**In a room smaller than the beam this matters differently.** At 1.5 m the beam
is only 0.92 m across; at 4.17 m it is 2.55 m — 32 % to 89 % of a 2.87 m wide
room. The horn does no localising at that scale, and the drone must keep moving
**toward or away** from the radar at **≥0.10 m/s** or it is subtracted along with
the walls. A pure hover is invisible. See [`testing.md`](testing.md).

**Checkpoint 4:** floor marks at 3, 5 and 8 m along the boresight (or at 1.5, 2.5
and 3.5 m in a small room), and the sector edges taped on the floor.

## 5. The 2.4 GHz phone build, if you want it back

Flying from the phone over the drone's own AP on channel 1 is still a valid
build — it needs no extra hardware and no firmware change, and it was this
project's plan until the small-room measurements. The cost is that the radar
must sweep 2440–2480 MHz above the WiFi, giving up half its bandwidth and the
range resolution with it.

Take it if you are flying outdoors or in a large space, where a 3.75 m range
cell is a small fraction of the scene. Do not take it in a bedroom.
