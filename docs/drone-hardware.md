# ESP-FLY drone hardware — step by step (fly by phone)

**Nothing changes on the airframe.** The phone-flying ESP-FLY is the stock
build: XIAO ESP32-S3, the flight-controller board, MPU-6050, four coreless
motors, 1S battery, ESP-Drone firmware. The receiver you fitted for the T8L
(RP1 V2) is simply not used — leave it or remove it (−0.9 g), your call.

What *does* matter for the radar is where the drone's WiFi sits and what
the radar can see:

## 1. Take the RP1 V2 off, or power it down

An ELRS 2.4 receiver that is powered but unbound sends nothing, so it is
harmless to the radar. But if it is bound to a T8L that is switched on, the
link hops over the whole 2.4 GHz band at 25–100 mW — right through the
radar's sweep, in both directions. **Either unsolder the RP1 V2, or never
have the T8L on during radar sessions.** Unsoldering is the version that
cannot be forgotten.

**Checkpoint 1:** with the drone powered, a WiFi-analyser app on the phone
shows exactly one thing from the drone: its `ESP-DRONE-xxxx` AP.

## 2. Keep the antenna as it is

The XIAO's antenna is the AP's antenna. Do not add a 915 MHz wire; there is
nothing to attach it to in this configuration.

## 3. Make the drone a good radar target (optional, free)

A 25 g quad's radar cross-section is small (~0.01 m² was assumed in every
link budget in this repo; the margin at 10 m is 71 dB so it does not need
help). If you ever want more echo at longer range, a 30 mm square of
copper tape on the top plate, flat, roughly doubles it. Not needed indoors.

## 4. Where to hover

The horns' beams are 34° × 36°. At 5 m that is a ~3 m wide, ~3 m tall
window per beam position; the turntable sweeps it across the sector. Fly
inside the sector at 3–10 m from the horns, at horn height ±1.5 m — the
first flights should stay where a single beam sees the drone at all times.

**Checkpoint 4:** floor marks at 3, 5 and 8 m along the boresight, and the
sector edges taped on the floor.

## 5. If the phone link test fails

The fallback hardware (a 915 MHz ELRS link, ~$130) is documented in
[`archive/drone-915.md`](archive/drone-915.md). Do the link test in
[`drone-software.md`](drone-software.md) §4 first; it takes ten minutes and
is the thing that tells you whether you need to spend anything at all.
