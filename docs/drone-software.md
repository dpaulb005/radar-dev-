# ESP-FLY drone software — step by step (915 MHz link, radar gets the whole band)

**Decision: the drone flies on 915 MHz ELRS, not on its own 2.4 GHz WiFi.**
The airframe is built exactly as the kit's guide describes, but the flight
firmware is **esp-fc** rather than ESP-Drone, and the control link is a 0.7 g
ELRS receiver on UART2 instead of a phone on an access point.

The reason is bandwidth. The XIAO ESP32-S3's radio is **2.4 GHz only** — no
5 GHz, and Bluetooth is 2.4 GHz too — so any WiFi link lives inside the band
the radar sweeps, and the radar has to sweep around it. Moving the link to
915 MHz is 1.5 GHz of separation, and it hands the radar back the full band.

The airframe half of this is [`drone-hardware.md`](drone-hardware.md); the two
link configurations are [`drone-link.md`](drone-link.md) (ELRS and EdgeTX) and
[`drone-link-espfc.md`](drone-link-espfc.md) (esp-fc on the XIAO).

---

## 0. The numbers

| | phone on WiFi ch 1 | **915 MHz ELRS** |
|---|---|---|
| radar sweep | 2440–2480 MHz = **40 MHz** | 2400–2483.5 MHz = **83.5 MHz** |
| range cell `c/2B` | 3.75 m | **1.80 m** |
| beat slope | 41.70 Hz/m | 87.04 Hz/m |
| target FFT bin at 3 m | 0.80 — inside the DC lobe | **1.67** |
| in a 4.17 m room, error at 2 m | +0.54 m | **+0.02 m** |
| in a 4.17 m room, at 1.0 m | no fix | +0.17 m |
| interference between radar and link | ~20 dB of margin, tested per session | **none — 1.5 GHz apart** |
| cost | $0 | ~$130 and a firmware change |

The coexistence build was not *broken* — outdoors at 5–10 m a 3.75 m cell is a
small fraction of the scene and 40 MHz is fine. It falls apart in a room 4 m
deep, which is 1.1 range cells. See [`testing.md`](testing.md) § a small room
changes the answer.

**What the drone must not do is transmit in band.** esp-fc does not need WiFi
for control, but if it is left enabled for the configurator it is an in-beam
2.4 GHz emitter at close range. Turn it off before every radar session
(checkpoint 2 in [`drone-hardware.md`](drone-hardware.md) is the test).

The 915 MHz transmitter is not a problem in the other direction: at 25 mW and
1.5 GHz below the band, the 2400–2500 MHz band-pass in front of the LNA rejects
it, and anything that leaks past mixes to ~1.5 GHz — three orders of magnitude
above the 15.9 kHz video filter.

---

## 1. Flash esp-fc on the XIAO

Follow [`drone-link-espfc.md`](drone-link-espfc.md) § 3–4. In outline:

1. Build the airframe per the kit's guide, but flash **esp-fc**, not ESP-Drone.
2. **Ports** tab (Betaflight Configurator 10.10 — newer ones refuse esp-fc's
   MSP): tick **Serial Rx** on UART2, the GPIO 9 / GPIO 8 pair the receiver is
   soldered to.
3. **Receiver** tab: mode **Serial (via UART)**, provider **CRSF**.
4. Paste `firmware/espfly-915/espfly-915.cli` in the CLI tab. It pins the pins,
   the serial feature and a 0.4 s failsafe, and ends with `save`.
5. **Modes** tab: ARM on CH5, ANGLE on CH6.

**Checkpoint 1:** the Receiver tab's bars follow every stick, 1000–2000 with
1500 centred, and both switches toggle. Props off.

## 2. Bind the link

[`drone-link.md`](drone-link.md) § 1–2. Both ends flashed to the **same ELRS
version**, the **same binding phrase**, and regulatory domain **FCC915**.
EdgeTX: internal RF **off**, external RF **CRSF**, 100 Hz Full, 25 mW.

**Checkpoint 2:** receiver LED solid, Lua shows connected with LQ 100 and RSSI
−40…−60 dBm at bench distance.

## 3. Set the radar's sweep — now the full band

The firmware already defaults to it, so this is a check rather than a change:

```
?          -> "f0_mhz":2400.0,"bw_mhz":83.5,"rf":1
```

If it reports anything narrower, put it back:

```
SET f0_mhz 2400
SET bw_mhz 83.5
```

`radar_acquire.py --ctl …` reads the sweep edges from that status, so nothing
else needs changing. Without `--ctl`, pass `--f0-mhz 2400 --bw-mhz 83.5` so the
range scale matches. The ESP32 refuses any setting that would leave
2400–2483.5 MHz.

## 4. The link test — much shorter than it used to be

The whole coexistence procedure this section used to carry is gone: there is no
shared band left to test. Two things still need checking, and both are quick.

1. **The drone is silent in band.** Drone powered, props off, on the bench in
   the beam at 1 m. A WiFi-analyser app must show **nothing** from it. If
   `ESP-DRONE-xxxx` or any esp-fc AP appears, WiFi is still on — fix that
   first, because at 1 m in the beam it will swamp the receiver.
2. **The radar does not disturb the link.** With the drone in the beam at 1 m,
   `SWEEP 0` then `SWEEP 1`, and watch the ELRS telemetry on the radio: **LQ
   must stay 100 and RSSI must not move.** It should not — 1.5 GHz of
   separation — and if it does, something is radiating a harmonic and the
   band-pass is the first place to look.

**Checkpoint 4:** no 2.4 GHz emission from the drone, and LQ 100 with the sweep
running and the beam on it.

## 5. First flight with the radar sweeping

Hover in the sector with the radio while `radar_acquire.py --ctl … --server …`
runs. In a small room, remember the drone must keep moving **toward or away**
at **≥0.10 m/s** — a pure hover is subtracted along with the walls
([`testing.md`](testing.md)).

**Checkpoint 5:** a 2-minute hover with a continuous radar track and LQ 100.
Record it (console Record button).

---

## 6. The phone build, if you want it back

Flying from the phone over the drone's own AP is still a valid build and costs
nothing: flash ESP-Drone per the kit's guide with two `menuconfig` changes —
**ESPDrone Config → Wi-Fi/ESP-Now Channel → 1** (the default 6 sits inside the
sweep) and **Component config → PHY → Max WiFi TX power → 10** dBm. Then sweep
`SET f0_mhz 2440 / SET bw_mhz 40` above it, and run the coexistence link test
that used to live in § 4 — it is preserved in `docs/archive/` along with the
in-band interference budget for the drone's AP, the phone, and where the
operator should stand.

Take it if you are flying outdoors or in a large space. Do not take it in a
bedroom: 40 MHz gives a 3.75 m range cell, and a 4 m room is one cell deep.

## 7. What is deliberately *not* on the drone

- **No custom flight code.** esp-fc, unmodified, configured by a CLI script.
  CRSF is CRSF whether it arrives at 2.4 GHz or 915 MHz.
- **No 2.4 GHz transmitter of any kind** during a radar session.
- **No cooperation with the radar.** The drone carries nothing that helps it be
  found — the radar sees the airframe and nothing else, which is the whole
  point ([`goal.md`](goal.md) test 3).
