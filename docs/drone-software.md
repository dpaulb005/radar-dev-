# ESP-FLY drone software — step by step (915 MHz link, radar gets the whole band)

**Decision: the drone flies on 915 MHz ELRS, not on its own 2.4 GHz WiFi.**
The airframe is built exactly as the kit's guide describes, but the flight
firmware is **esp-fc** rather than ESP-Drone, and the control link is a 0.7 g
ELRS receiver on UART2 instead of a phone on an access point.

The reason is bandwidth. The XIAO ESP32-S3's radio is **2.4 GHz only** — no
5 GHz, and Bluetooth is 2.4 GHz too — so any WiFi link lives inside the band
the radar sweeps, and the radar has to sweep around it. Moving the link to
915 MHz is 1.5 GHz of separation, and it hands the radar back the full band.

What runs on the drone is **esp-fc, unmodified**. There is no custom flight code
in this repo and there should not be: the drone is a passive target for the
radar, and CRSF is CRSF whether it arrives at 2.4 GHz or 915 MHz. "Drone
software" is therefore three configurations, in this order:

1. ExpressLRS on the **TX module and receiver** (band, bind, rate)
2. EdgeTX on the **Pocket** (model, module, switches)
3. esp-fc on the **XIAO** (serial port, CRSF, arm/mode switches, failsafe)

The esp-fc part is captured as a CLI script: `firmware/espfly-915/espfly-915.cli`.
The airframe half of this, including which pad the receiver's every wire goes
to, is [`drone-hardware.md`](drone-hardware.md).

Props OFF for everything until § 8.

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
deep, which is 1.1 range cells: nothing in range separates the drone from the
wall behind it.

**What the drone must not do is transmit in band.** esp-fc does not need WiFi
for control, but if it is left enabled for the configurator it is an in-beam
2.4 GHz emitter at close range. Turn it off before every radar session
(checkpoint 5 in [`drone-hardware.md`](drone-hardware.md) is the test).

The 915 MHz transmitter is not a problem in the other direction: at 25 mW and
1.5 GHz below the band, the 2400–2500 MHz band-pass in front of the LNA rejects
it, and anything that leaks past mixes to ~1.5 GHz — three orders of magnitude
above the 15.9 kHz video filter.

---

## 1. ExpressLRS — both ends on FCC915, one binding phrase

Use the **ExpressLRS Configurator** (desktop app). For each device, target
→ flash:

| device | target | options |
|---|---|---|
| Bandit Nano | RadioMaster → Bandit Nano 900 TX | regulatory domain **FCC915**, binding phrase e.g. `espfly-radar`, same version as the RX |
| BetaFPV Nano 915 RX | BetaFPV → Nano 900 RX (or HappyModel → ES900RX) | **FCC915**, **same** binding phrase, same version |

Flash the module over its USB port; flash the receiver by USB/UART adapter
or over its own WiFi (power it, join `ExpressLRS RX`, open 10.0.0.1). Both ends
must be on the **same ELRS major version** as well as the same domain — a
version mismatch is the most common ELRS failure and it simply will not bind.

**Checkpoint 1:** with both flashed and the receiver powered on the drone,
the receiver LED goes **solid** within a few seconds of the Pocket being on:
bound, on 915.

## 2. EdgeTX on the Pocket

Model setup → Internal RF: **OFF**. External RF: **CRSF**. Then the ELRS Lua
script (Tools → ExpressLRS):

| setting | value | why |
|---|---|---|
| Packet rate | **100 Hz Full** (or 200 Hz) | 10 full-res channels; 900 MHz tops out at 200 |
| Telemetry ratio | 1:64 | you only need LQ/RSSI back |
| Switch mode | Wide | |
| TX power | **25 mW** | indoors, 10 m; raise later if LQ ever drops |
| Dynamic power | off while testing | you want a constant number to compare against the radar |

Mixer (default is fine): CH1–4 = **A E T R** on the sticks (esp-fc's map is
set to match below), CH5 = a two-position switch for **ARM**, CH6 = a
switch for **ANGLE** mode.

**Checkpoint 2:** Lua shows the module *connected*, LQ 100, and the
receiver's RSSI around −40…−60 dBm at bench distance.

## 3. esp-fc — flashing, and the Configurator part

Flash **esp-fc**, not ESP-Drone, on the XIAO, per esp-fc's own build
instructions — nothing in this repo patches it. Then connect the drone by USB
and open **Betaflight Configurator 10.10** (esp-fc speaks its MSP; newer
configurators refuse it).

1. **Ports** tab: on the UART your receiver is wired to (the published
   XIAO guide uses **UART 2**, GPIO 9 RX / GPIO 8 TX), tick **Serial Rx**.
   Save. If you are not sure which UART, `get pin` in the CLI tab lists
   `pin_serial_2_rx` etc. against the GPIO you found when you soldered the
   receiver ([`drone-hardware.md`](drone-hardware.md) § 2).
2. **Receiver** tab: Receiver Mode **Serial (via UART)**, Serial Receiver
   Provider **CRSF**. Channel map **TAER1234** if the bars move on the wrong
   sticks; otherwise the default. Save.
3. Move the sticks: the four bars follow, 1000 → 2000 with 1500 centred.
   Adjust EdgeTX endpoints, not esp-fc, if they don't reach.
4. **Modes** tab: ARM on the CH5 switch range, ANGLE on CH6. Save.

**Checkpoint 3:** Receiver tab bars follow every stick and both switches.
If they twitch or drop: wrong UART, or TX/RX wires swapped.

## 4. esp-fc — CLI script

`firmware/espfly-915/espfly-915.cli` pins the receiver wiring, the serial
function and the failsafe in a form you can paste back after any reset.
Open the **CLI** tab and paste it line by line (or all at once if your
configurator passes multi-line). It ends with `save`.

What it sets, and why (the exact syntax is esp-fc's, from its `docs/cli.md`):

```
set pin_serial_2_rx 9          # the XIAO GPIO the receiver's TX is soldered to
set pin_serial_2_tx 8          # and its RX (needed for CRSF telemetry back)
set feature_rx_serial 1        # receiver is serial, not the built-in ESP-NOW "SPI Rx"
set failsafe_delay 4           # 0.4 s of no packets -> failsafe (the only stage-2 action is DROP)
set failsafe_kill_switch 0
save
```

Two things the CLI file does **not** set, because their ids are best read
back from the configurator rather than guessed: the serial-2 *function* (the
Ports tab's Serial Rx tick) and the receiver *provider* (CRSF). After § 3,
`get serial_2` and `get rx` in the CLI show what the configurator wrote —
paste those two lines into your copy of the file so it is complete for your
build.

**Checkpoint 4:** `reboot`, reconnect, Receiver tab still live; `get pin`
shows serial 2 on the pins you soldered.

## 5. Failsafe test (props OFF)

1. Arm on the bench (motors spin, props off). Switch the Pocket **off**.
2. Within ~0.5 s the motors must **stop** and the drone disarm. esp-fc's
   only stage-2 failsafe is DROP — that is the correct behaviour for a
   25 g indoor quad; there is no GPS return.
3. Power the Pocket back on: the link recovers, the drone stays disarmed
   until you cycle the ARM switch.

**Checkpoint 5:** motors stop on TX-off every time, three times in a row.

## 6. Set the radar's sweep — now the full band

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

## 7. The link test — much shorter than it used to be

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
   band-pass is the first place to look. (With the old 2.4 GHz RP1 V2 in this
   same test, LQ would be dropping.)

**Checkpoint 7:** no 2.4 GHz emission from the drone, and LQ 100 with the sweep
running and the beam on it.

## 8. First flights — radar OFF, then radar ON

1. **Radar off.** Props on, room clear, ANGLE mode, arm, hover at 1 m for 30 s,
   land. This is the same aircraft it was before the link swap — the flight
   controller is unchanged, only the receiver and the sticks are new.
2. **Radar sweeping.** Hover in the sector with the radio while
   `radar_acquire.py --ctl … --server …` runs. The console shows the fix; the
   ELRS Lua shows LQ still 100. In a small room, remember the drone must keep
   moving **toward or away** at **≥0.10 m/s** — a pure hover is subtracted
   along with the walls.

**Checkpoint 8:** a 2-minute hover in the scanned sector with LQ 100 throughout
and a continuous radar track in the console. Record it (console Record button).

---

## 9. The phone build, if you want it back

Flying from the phone over the drone's own AP is still a valid build and costs
nothing: flash ESP-Drone per the kit's guide with two `menuconfig` changes —
**ESPDrone Config → Wi-Fi/ESP-Now Channel → 1** (the default 6 sits inside the
sweep) and **Component config → PHY → Max WiFi TX power → 10** dBm. Then sweep
`SET f0_mhz 2440 / SET bw_mhz 40` above it. The two systems now share the band,
so the link test in § 7 comes back in its long form: fly the drone in the beam
at 1 m with `SWEEP 1` running and confirm the phone holds control and the
console still tracks. The margin is about 20 dB and it has to be re-measured in
every room.

Take it if you are flying outdoors or in a large space. Do not take it in a
bedroom: 40 MHz gives a 3.75 m range cell, and a 4 m room is one cell deep.

## 10. What is deliberately *not* on the drone

- **No custom flight code.** esp-fc, unmodified, configured by a CLI script.
  CRSF is CRSF whether it arrives at 2.4 GHz or 915 MHz.
- **No 2.4 GHz transmitter of any kind** during a radar session. No beacon
  firmware, no MAC filtering, no WiFi AP — those belonged to the passive
  tracking system, which needed something to hear. This one does not.
- **No cooperation with the radar.** The drone carries nothing that helps it be
  found: a 25 g quadcopter, 3–10 m, indoors, made of copper, carbon and motors.
  The radar sees the airframe and nothing else, which is the whole point.
- **No radar-driven flight.** If you later want the drone to *use* the radar's
  track, that is a laptop-side commander driving the Pocket's trainer port or a
  second ELRS module — a different project, later.
