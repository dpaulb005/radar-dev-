# ESP-FLY drone hardware — step by step (915 MHz ELRS link)

**Build the kit exactly as its official guide says** — the ESP-FLY tutorial
video and Elektor article linked from `Seeed-Projects/Co-Create_ESP-FLY`:
XIAO ESP32-S3, the flight-controller board, MPU-6050, four 615 coreless
motors, 30 mm props, 1S battery.

Then make **one change that is not in the kit's guide**: the drone flies on a
**915 MHz** control link, not on its own 2.4 GHz WiFi. Nothing else on the
airframe changes.

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

A real room measured 2.87 × 4.17 m is **1.1 range cells deep at 40 MHz**: range
cannot separate the drone from the wall behind it, only Doppler can, and that is
the difference between a coarse detector and a real ranging instrument. In a
garage or a garden at 5–10 m the 40 MHz sweep is perfectly usable, so **if you
have the space, you do not need any of this**.

The second reason is interference, and it is not subtle. The radar puts ≈ +10 dBm
into a 13 dBi horn and sweeps 2400–2483.5 MHz continuously. At 10 m the drone's
receiver sees that at about −34 dBm; its own control signal arrives at
−50…−60 dBm. A 2.4 GHz link — ELRS 2.4, ESP-NOW, WiFi, anything — is being jammed
by 20 dB every time the beam points at the drone, which is exactly when you need
it. ELRS's LoRa is tough, but you would be betting the aircraft on an untested
margin.

Neither end of the kit's own radio path can move. The **RadioMaster RP1 V2**
receiver is ExpressLRS **2.4 GHz** only, and the **RadioMaster T8L** radio has a
built-in 2.4 GHz module (SX1281), 2.400–2.480 GHz, and **no external module
bay** — there is no 900 MHz variant of it. So both ends get replaced. Keep the
T8L; it is still the right tool for any flight with the radar off.

The cost is **≈ $130** and a firmware change: you stop flying from a phone and
start flying with sticks.

## 1. What to buy (≈ $130)

| item | ~$ | why this one |
|---|---|---|
| **RadioMaster Pocket** (ELRS or CC2500 internal — irrelevant, you use the bay) | 65 | cheapest EdgeTX radio with a **Nano module bay** |
| **RadioMaster Bandit Nano**, 915 MHz ELRS module | 40 | fits the Pocket's Nano bay; 10 mW–1 W; FCC915 |
| BetaFPV ELRS Nano 915 (0.7 g) or HappyModel ES900RX (0.6 g) | 17 | lightest 900 MHz receivers; same CRSF wiring as the RP1 V2 |
| 915 MHz receiver antenna (usually included: ~80 mm wire or "T") | 0–5 | |

**Not the Bandit BR1.** It is 915 MHz and it works, but it weighs **2.9 g**
against a 25 g airframe — four times a nano receiver, for range performance you
do not need across a bedroom.

Alternatives: any EdgeTX radio with a JR bay (Boxer, TX12) + Bandit Micro;
HappyModel ES900TX (Nano) instead of the Bandit Nano. Both ends must be the
**same ELRS major version** and the **same regulatory domain (FCC915)**; a
version mismatch is the most common ELRS failure and it simply will not bind.
Links and checked prices: [`../hardware/ORDER.md`](../hardware/ORDER.md) § E.

Weight: the RP1 V2 is ~0.9 g with its 31 mm antenna; the Nano 915 is ~0.7 g
plus a ~1 g antenna → about **+1 g on a 25 g aircraft**. Fine.

Slide the Bandit Nano into the Pocket's bay, screw it down and fit its antenna
(the module ships with one).

## 2. Fit the 915 MHz receiver, not the 2.4 GHz one

The kit's optional radio path (an ESP-NOW transmitter, or the ELRS **RP1 V2**)
is 2.4 GHz and hops across the whole band at 25–100 mW, straight through the
radar's sweep in both directions. **Do not fit it.** If you already did,
unsolder it (−0.9 g).

Fit instead a **915 MHz ELRS nano receiver** — BetaFPV ELRS Nano 915 (0.7 g) or
HappyModel ES900RX (0.6 g). It has exactly the same four pads as the RP1 V2 and
speaks the same **CRSF**, so it lands on the same four XIAO pads:

| receiver pad | XIAO ESP32-S3 |
|---|---|
| **3V3** | receiver power — not 5 V, see step 3 |
| GND | GND |
| **TX** (receiver → FC) | **GPIO 9** = UART2 RX |
| **RX** (FC → receiver, telemetry) | **GPIO 8** = UART2 TX |

1. Photograph the current wiring before touching anything.
2. Desolder the RP1 V2. Note which XIAO pin its **TX** wire went to — that
   is the pin esp-fc has as the serial-RX input (in the published esp-fc /
   XIAO guide it is **GPIO 9 = serial 2 RX**, with **GPIO 8 = serial 2 TX**;
   yours may differ — the wire tells you, and `get pin` in the esp-fc CLI
   confirms it).
3. Solder the 915 receiver to the **same four pads**: power to **3V3** (the
   drone has no 5 V rail in flight — the XIAO's 5 V pin is USB VBUS — and the
   published guide runs the receiver from 3V3), GND, its TX to the XIAO pin
   the old TX used (GPIO 9), its RX to the old RX pin (GPIO 8).
4. Shrink-wrap the receiver, tape it to the top plate away from the motors.

**Checkpoint 2:** power the drone on USB; the receiver's LED blinks slowly (not
bound yet) — it is alive on the same rail the RP1 V2 was. Once the link is bound
([`drone-software.md`](drone-software.md) § 1) that same LED goes **solid**
within a few seconds of the radio coming on.

## 3. The XIAO pin map esp-fc uses

From the published esp-fc / XIAO ESP-FLY guide, and what
[`../hardware/3d/drone.html`](../hardware/3d/drone.html) draws. Every XIAO pin
has a job:

| XIAO | GPIO | function |
|---|---|---|
| D0 | 1 | motor 4 — front-left |
| D1 | 2 | battery voltage (ADC) |
| D2 | 3 | motor 3 — rear-left |
| D3 | 4 | motor 1 — rear-right |
| D4 | 5 | I2C SDA → MPU-6050 |
| D5 | 6 | I2C SCL → MPU-6050 |
| D6 | 43 | status LED |
| D7 | 44 | spare (UART0 RX) |
| D8 | 7 | motor 2 — front-right |
| **D9** | **8** | **UART2 TX → receiver RX** (telemetry) |
| **D10** | **9** | **UART2 RX ← receiver TX** (CRSF) |
| 3V3 | — | **receiver power.** The drone has no 5 V rail in flight — the XIAO's 5 V pin is USB VBUS — so the published guide powers the receiver from 3V3, and so does this build |
| 5V | — | USB only |

Motor order is Betaflight's (1 rear-right, 2 front-right, 3 rear-left,
4 front-left), props-in: rear-right and front-left CW, the other two CCW.

## 4. Route the 915 MHz antenna

A 915 MHz quarter-wave is a **~80 mm wire** (or a "T"), not the RP1 V2's 31 mm.
On a 67 mm frame:

- run it straight out along one arm and past the motor, or straight back
  as a tail, with ~10 mm of the base kept clear of any metal or the battery;
- never parallel to and touching a motor wire, never under a prop;
- fix it with a short piece of heat-shrink to a zip-tie stub so it cannot
  reach a prop in a crash.

A drooping tail antenna is the usual answer on micro quads and works.

**Checkpoint 4:** props on, spin up on the bench held down — the antenna does
not touch a prop at full throttle.

## 5. Turn the drone's WiFi off

The XIAO ESP32-S3, the flight-controller board, MPU-6050, motors and battery are
untouched by the link swap, and so is esp-fc itself. With a serial receiver
esp-fc never brings WiFi up at all in flight, so **the drone emits nothing in
2.4 GHz** — that was the whole point. The XIAO's on-board antenna still serves
that WiFi, which esp-fc does not use for control: leave it alone, there is
nothing to change, but make sure nothing is transmitting on it during a radar
session.

**Checkpoint 5:** with the drone powered, a WiFi-analyser app on the phone shows
**nothing** from the drone. If it still advertises `ESP-DRONE-xxxx`, esp-fc is
not running or WiFi is still enabled — fix that before flying near the radar.

## 6. Make the drone a good radar target (optional, free)

A 25 g quad's radar cross-section is small (**~0.01 m² is assumed in every link
budget in this repo and has been measured by nobody** — it could be several times
lower). At 10 m the thermal margin is large enough that it does not need help.
If you want more echo, a 30 mm square of copper tape laid flat on the top plate
roughly doubles it. Free, and worth doing for the first flights.

## 7. Where to hover

The horns' beams are 34° × 36°. At 5 m that is a ~3 m wide, ~3 m tall window.
Fly inside the sector at 3–10 m from the horns, at horn height ±1.5 m.

**In a room smaller than the beam this matters differently.** At 1.5 m the beam
is only 0.92 m across; at 4.17 m it is 2.55 m — 32 % to 89 % of a 2.87 m wide
room. The horn does no localising at that scale, and the drone must keep moving
**toward or away** from the radar at **≥0.10 m/s** or it is subtracted along with
the walls. A pure hover is invisible: measured at 2.5 m with 50 dB of clutter
cancellation, 0.00 m/s gives 0 fixes out of 5, 0.05 m/s gives 3, and 0.10 m/s and
above gives 5.

**Checkpoint 7:** floor marks at 3, 5 and 8 m along the boresight (or at 1.5, 2.5
and 3.5 m in a small room), and the sector edges taped on the floor.

## 8. The 2.4 GHz phone build, if you want it back

Flying from the phone over the drone's own AP on channel 1 is still a valid
build — it needs no extra hardware and no firmware change, and it was this
project's plan until the small-room measurements. The cost is that the radar
must sweep 2440–2480 MHz above the WiFi, giving up half its bandwidth and the
range resolution with it.

Take it if you are flying outdoors or in a large space, where a 3.75 m range
cell is a small fraction of the scene. Do not take it in a bedroom.
