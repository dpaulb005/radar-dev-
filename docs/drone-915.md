# Fallback — ESP-FLY on a 915 MHz ELRS link

> **Not the current plan.** The drone is flown from the phone over its own
> WiFi AP on channel 1, with the radar sweeping 2440–2480 MHz above it
> ([`drone-915-esp-fc.md`](drone-915-esp-fc.md)). Use this page only if the link
> test in that guide's §4 fails. The esp-fc side of it is
> [`drone-915-esp-fc.md`](drone-915-esp-fc.md).

One drone. Goal: the ESP-FLY flies on a control link that is **not in the
2.4 GHz band the radar sweeps**. Nothing else on the airframe changes.

## 0. Why, in one paragraph

The radar puts ≈ +10 dBm into a 13 dBi horn and sweeps 2400–2483.5 MHz
continuously. At 10 m the drone's receiver sees that at about −34 dBm; its
own control signal arrives at −50…−60 dBm. A 2.4 GHz link — ELRS 2.4,
ESP-NOW, WiFi, anything — is being jammed by 20 dB every time the beam
points at the drone, which is exactly when you need it. ELRS's LoRa is
tough, but you would be betting the aircraft on an untested margin. The
900 MHz ELRS band is 1.5 GHz away: **zero** interaction, and better range
and wall penetration as a bonus.

## 1. What you have, and what it can't do

- **Receiver: RadioMaster RP1 V2** — an ExpressLRS **2.4 GHz** receiver.
- **Radio: RadioMaster T8L** — a screenless ELRS radio with a **built-in
  2.4 GHz** module (SX1281), 2.400–2.480 GHz, and **no external module bay**.
  There is no 900 MHz variant. It cannot be moved to 915 MHz.

So both ends of the link get replaced. Keep the T8L: it is still the right
tool for every flight where the radar is off (all of the bring-up in
[`drone-915-esp-fc.md`](drone-915-esp-fc.md)).

## 2. Parts (≈ $130)

| item | ~$ | why this one |
|---|---|---|
| **RadioMaster Pocket** (ELRS or CC2500 internal — irrelevant, you use the bay) | 65 | cheapest EdgeTX radio with a **Nano module bay** |
| **RadioMaster Bandit Nano**, 915 MHz ELRS module | 40 | fits the Pocket's Nano bay; 10 mW–1 W; FCC915 |
| **BetaFPV ELRS Nano receiver, 915 MHz** (0.7 g) or HappyModel ES900RX (0.6 g) | 17 | lightest 900 MHz receivers; same CRSF wiring as the RP1 V2 |
| 915 MHz receiver antenna (usually included: ~80 mm wire or "T") | 0–5 | |

Alternatives: any EdgeTX radio with a JR bay (Boxer, TX12) + Bandit Micro;
HappyModel ES900TX (Nano) instead of the Bandit Nano. Both ends must be the
**same ELRS major version** and the **same regulatory domain (FCC915)**.

Weight: the RP1 V2 is ~0.9 g with its 31 mm antenna; the Nano 915 is ~0.7 g
plus a ~1 g antenna → about **+1 g on a 25 g aircraft**. Fine.

## 3. Swap the receiver

The RP1 V2 is wired to the XIAO ESP32-S3 with four wires: 5 V (or the pad
you currently power it from), GND, RX-TX → XIAO RX, RX-RX → XIAO TX. The
915 MHz receiver has **exactly the same four pads** and speaks the **same
CRSF** protocol, so:

1. Photograph the current wiring before touching anything.
2. Desolder the RP1 V2. Note which XIAO pin its **TX** wire went to — that
   is the pin esp-fc has as the serial-RX input (in the published esp-fc /
   XIAO guide it is **GPIO 9 = serial 2 RX**, with **GPIO 8 = serial 2 TX**;
   yours may differ — the wire tells you, and `get pin` in the esp-fc CLI
   confirms it).
3. Solder the 915 receiver to the **same four pads**: power to the same rail
   the RP1 V2 used, GND, its TX to the XIAO pin the old TX used, its RX to
   the old RX pin.
4. Shrink-wrap the receiver, tape it to the top plate away from the motors.

**Checkpoint 3:** power the drone on USB; the receiver's LED blinks slowly
(no bind) — it is alive on the same rail the RP1 V2 was.

## 4. Route the 915 MHz antenna

A 915 MHz quarter-wave is **~80 mm**, not 31 mm. On a 67 mm frame:

- run it straight out along one arm and past the motor, or straight back
  as a tail, with ~10 mm of the base kept clear of any metal or the battery;
- never parallel to and touching a motor wire, never under a prop;
- fix it with a short piece of heat-shrink to a zip-tie stub so it cannot
  reach a prop in a crash.

A drooping tail antenna is the usual answer on micro quads and works.

**Checkpoint 4:** props on, spin up on the bench held down — the antenna
does not touch a prop at full throttle.

## 5. Nothing else changes

The XIAO ESP32-S3, the flight-controller board, MPU-6050, motors, battery
and esp-fc firmware are untouched. With a serial receiver, esp-fc does not
bring WiFi up at all in flight (`espfly.md` §2) — so **the drone emits
nothing in 2.4 GHz** and the radar band is clean. That was the whole point.

## 6. Radio side

Slide the Bandit Nano into the Pocket's bay, screw it, fit its antenna (the
module ships with one). Set the Pocket's **internal** RF module to OFF and
the **external** module to CRSF in the model setup — [`drone-915-esp-fc.md`](drone-915-esp-fc.md) §1.

**Checkpoint 6:** the Pocket boots, the module's OLED lights, ELRS Lua opens
and shows the module's version and FCC915.
