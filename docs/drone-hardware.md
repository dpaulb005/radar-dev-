# ESP-FLY drone hardware — step by step (fly by phone)

**Build the kit exactly as its official guide says** — the ESP-FLY tutorial
video and Elektor article linked from `Seeed-Projects/Co-Create_ESP-FLY`:
XIAO ESP32-S3, the flight-controller board, MPU-6050, four 615 coreless
motors, 30 mm props, 1S battery. The radar needs nothing added to it. The
one deviation is what you **leave off**.

What *does* matter for the radar is where the drone's WiFi sits and what
the radar can see:

## 1. Do not fit the radio-controller receiver

The kit's optional radio-controller path (an ESP-NOW transmitter, or the
ELRS receiver — RP1 V2 — used with the ESP-FC firmware) is **2.4 GHz** and,
when bound to a live transmitter, hops across the whole band at 25–100 mW —
straight through the radar's sweep, in both directions. The phone-flying
build does not use it. If you already fitted an RP1 V2 for the T8L,
**unsolder it** (−0.9 g); if not, skip that step of the radio tutorial
entirely. Never have the T8L switched on during a radar session.

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
window; the interferometer reads bearing across it without moving. Fly
inside the sector at 3–10 m from the horns, at horn height ±1.5 m — the
first flights should stay where a single beam sees the drone at all times.

**Checkpoint 4:** floor marks at 3, 5 and 8 m along the boresight, and the
sector edges taped on the floor.

## 5. If the phone link test fails

The fallback hardware (a 915 MHz ELRS link, ~$130) is documented in
[`archive/drone-915.md`](archive/drone-915.md). Do the link test in
[`drone-software.md`](drone-software.md) §4 first; it takes ten minutes and
is the thing that tells you whether you need to spend anything at all.
