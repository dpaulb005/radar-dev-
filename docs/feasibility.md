# Feasibility: passive radar vs. passive RF localization at 5–10 m

## The question

> Can I build a passive radar that uses reflections of my RC controller's
> signal off the drone to locate it within 5–10 m, for under $150?

Short answer: **reflection-based passive radar at this range and budget is not
feasible**, but **locating the drone from its own transmissions is easy and
cheap** — and since the drone carries an ESP32 that is already transmitting,
that is the right architecture. This repo implements it.

## Why reflection-based passive radar fails at 5–10 m / $150

Passive (bistatic) radar uses a non-cooperative illuminator (here, your RC
controller) and detects the target's echo. Three problems kill it at this
scale:

### 1. Range resolution

Range resolution of any radar is set by signal bandwidth:

```
ΔR = c / (2·B)
```

| Illuminator                | Bandwidth | Range resolution |
|----------------------------|-----------|------------------|
| WiFi (802.11n, 20 MHz)     | 20 MHz    | **7.5 m**        |
| Bluetooth / BLE            | 1–2 MHz   | 75–150 m         |
| ExpressLRS / typical RC UHF| ≤ 1 MHz   | ≥ 150 m          |
| DVB-T (classic passive radar illuminator) | ~8 MHz | ~19 m |

Even with the widest hobby illuminator (20 MHz WiFi), one range cell is 7.5 m —
as large as your whole operating area. You cannot resolve *where* in 5–10 m the
echo came from; the direct path and the echo land in the same correlation bin.

### 2. Direct-path-to-echo power ratio

The echo is tiny. For a small quadcopter, radar cross-section at 2.4 GHz is
roughly σ ≈ 0.01–0.1 m². With transmitter–receiver baseline d, and
transmitter→drone and drone→receiver distances R₁ and R₂:

```
P_echo / P_direct = σ·d² / (4π·R₁²·R₂²)
```

With d = R₁ = R₂ = 5 m and σ = 0.01 m²: ratio ≈ 3×10⁻⁵ → **the echo is ~45 dB
below the direct signal**, arriving a few nanoseconds later. Real passive
radars suppress the direct path with adaptive cancellation across coherent
dual-channel receivers and then integrate for seconds to pull targets out in
the range–Doppler map. Targets are typically kilometers away, where direct-path
and echo geometry actually differ.

### 3. Hardware cost

A minimum credible passive radar front end is two *phase-coherent* receive
channels (reference antenna + surveillance antenna) sharing one clock, at
2.4 GHz, with ≥20 MHz of instantaneous bandwidth. The cheapest practical
options (KrakenSDR ~$500, dual-channel PlutoSDR-class hardware ~$200+, or
clock-modified RTL-SDRs *plus* a 2.4 GHz downconverter) all blow the budget —
and still hit problems 1 and 2.

Doppler helps (a drone at 5 m/s gives f_d = 2v/λ ≈ 80 Hz at 2.4 GHz, which is
separable from the static direct path), so passive radar *detection* of drones
is a real technique — but at hundreds of meters with $500+ hardware, not at
5–10 m for $150.

## The reframe that works: the drone is a cooperative emitter

You don't need reflections. The drone's ESP32 already radiates 2.4 GHz WiFi
frames tens of times per second. Locating an *emitter* is orders of magnitude
easier than detecting its echo:

| Approach | Physics | Accuracy @ 5–10 m | Cost | In this repo |
|----------|---------|-------------------|------|--------------|
| **RSSI multilateration** (receive-only) | log-distance path loss at 3–4 sniffer nodes | 1–3 m | ~$30 | ✅ primary system |
| **WiFi FTM (802.11mc)** round-trip time | time-of-flight ranging, ESP32-S3/C3/C6 | ~0.5–2 m | ~$40 | ✅ optional upgrade |
| UWB (DW3000) two-way ranging | ns-level time-of-flight | 0.1–0.3 m | ~$100–120 | 📋 documented upgrade path |

The RSSI system is genuinely *passive* on the ground side: the sniffer nodes
never transmit toward the drone — they sit in promiscuous (monitor) mode and
measure the received signal strength of frames the drone was sending anyway,
then multilaterate. FTM is two-way (nodes ping the drone), trading passivity
for real time-of-flight distance.

## Error budget for the RSSI system

The log-distance path-loss model:

```
RSSI(d) = RSSI₀ − 10·n·log10(d / d₀)
```

At 2.4 GHz outdoors, n ≈ 2.0–2.5. RSSI on ESP32 has ±2–4 dB of noise and
multipath fading; at n = 2, a 2 dB error is a ~26 % distance error → ~1.5–2.5 m
position error at 5–10 m with 4 nodes and median filtering. Good enough to
know where the drone is in a backyard; not good enough to land on a target.
FTM or UWB are the paths to sub-meter.

## Legality note

Everything here is receive-only monitoring of *your own* transmitter plus
standard 802.11 protocol exchanges with *your own* devices. No jamming, no
deauth, no interception of third-party traffic — the sniffer filters on your
drone's MAC address only.
