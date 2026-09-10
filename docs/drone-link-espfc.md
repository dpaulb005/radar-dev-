# The control link — esp-fc configuration for 915 MHz

> **This is the current plan.** The software half of
> [`drone-link.md`](drone-link.md): what runs on the drone once its control
> link leaves the 2.4 GHz band the radar needs.

What runs on the drone is **esp-fc, unmodified**. There is no custom flight
code in this repo and there should not be: the drone is a passive target
for the radar, and CRSF is CRSF whether it arrives at 2.4 GHz or 915 MHz.
"Drone software" is therefore three configurations, in this order:

1. ExpressLRS on the **TX module and receiver** (band, bind, rate)
2. EdgeTX on the **Pocket** (model, module, switches)
3. esp-fc on the **XIAO** (serial port, CRSF, arm/mode switches, failsafe)

The esp-fc part is captured as a CLI script: `firmware/espfly-915/espfly-915.cli`.

Props OFF for everything until §6.

---

## 1. ExpressLRS — both ends on FCC915, one binding phrase

Use the **ExpressLRS Configurator** (desktop app). For each device, target
→ flash:

| device | target | options |
|---|---|---|
| Bandit Nano | RadioMaster → Bandit Nano 900 TX | regulatory domain **FCC915**, binding phrase e.g. `espfly-radar`, same version as the RX |
| BetaFPV Nano 915 RX | BetaFPV → Nano 900 RX (or HappyModel → ES900RX) | **FCC915**, **same** binding phrase, same version |

Flash the module over its USB port; flash the receiver by USB/UART adapter
or over its own WiFi (power it, join `ExpressLRS RX`, open 10.0.0.1).

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

## 2b. The ESP-FLY pin map esp-fc uses

From the published esp-fc / XIAO ESP-FLY guide, and what `hardware/3d/drone.html`
draws. Every XIAO pin has a job:

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

## 3. esp-fc — Configurator part

Connect the drone by USB, open **Betaflight Configurator 10.10** (esp-fc
speaks its MSP; newer configurators refuse it).

1. **Ports** tab: on the UART your receiver is wired to (the published
   XIAO guide uses **UART 2**, GPIO 9 RX / GPIO 8 TX), tick **Serial Rx**.
   Save. If you are not sure which UART, `get pin` in the CLI tab lists
   `pin_serial_2_rx` etc. against the GPIO you found in
   [`drone-link.md`](drone-link.md) §3.
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
Ports tab's Serial Rx tick) and the receiver *provider* (CRSF). After step
3, `get serial_2` and `get rx` in the CLI show what the configurator wrote —
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

## 6. First flights — radar OFF, then radar ON

1. **T8L + RP1 V2 baseline** is not needed any more; from here fly on the
   Pocket. Props on, room clear, ANGLE mode, arm, hover at 1 m for 30 s,
   land. Same as before the swap — the flight controller is unchanged.
2. **Radar sweeping, drone on the bench 1 m in front of the horns**, powered
   and bound, props off: open the ELRS Lua → the receiver's **LQ must stay
   100** and RSSI unchanged while `SWEEP 1` runs. That single number is the
   proof that the band separation works. (With the old RP1 V2 in this test,
   LQ would be dropping.)
3. Hover in the sector with the radar scanning. The console shows the fix;
   Lua shows LQ still 100.

**Checkpoint 6:** a 2-minute hover in the scanned sector with LQ 100
throughout and a continuous radar track in the console.

## 7. What is deliberately *not* on the drone

- No beacon firmware, no MAC filtering, no WiFi AP — those were the passive
  system. The radar sees the airframe; the drone cooperates by being made
  of copper, carbon and motors.
- No custom code in esp-fc. If you later want the drone to *use* the radar's
  track (the two-drone end goal), that is the laptop-side commander path in
  [`interception.md`](archive/interception.md), and with ELRS it becomes trivially
  cleaner: the laptop drives the Pocket's trainer port or a second ELRS
  module instead of an ESP-NOW commander. Different project, later.
