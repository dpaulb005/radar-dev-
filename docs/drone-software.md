# ESP-FLY drone software — step by step (fly by phone, radar on the same band)

**Decision: the drone is flown from the phone.** The ESP-FLY is built and
flashed exactly as its official guide describes (ESP-Drone firmware, ESP-IDF,
the ESP-Drone app over the drone's own WiFi access point). The kit's radio
option is not used. The only deviations from the guide are two `menuconfig`
values, and there is one test the guide does not have.

The catch, stated once: the XIAO ESP32-S3's radio is **2.4 GHz only** — no
5 GHz WiFi, and Bluetooth is 2.4 GHz too. So the phone link lives inside the
band the radar sweeps. The way out is that a WiFi AP sits on **one fixed
20 MHz channel**, so the radar simply sweeps the *rest* of the band with a
guard gap. That is a better situation than an ELRS-2.4 link, which hops over
the whole band and cannot be avoided.

---

## 0. The numbers (why this works, and what it costs)

Radar at the drone, 5 m, beam on it: +10 dBm into 13.4 dBi = +23 dBm EIRP,
free-space loss 54 dB → **−31 dBm**. Phone's WiFi at the drone, 3 m: about
**−35 dBm**. In the same channel the radar wins by 4 dB and the link dies.

Out of channel, the drone's WiFi receiver rejects the radar like any
neighbouring-channel signal (802.11n minimums: 16 dB one channel away,
32 dB two or more away). With the AP on **channel 1** (2401–2423 MHz) and
the sweep starting at **2440 MHz** (28 MHz above the channel centre):

| | |
|---|---|
| radar seen by the drone's receiver | −31 − ~24 dB ≈ **−55 dBm** |
| phone signal | −35 dBm |
| signal-to-interference | **~20 dB** (802.11 at 1–6 Mb/s needs ~5–10) |
| radar sweep | **2440–2480 MHz = 40 MHz** |
| range cell | **3.75 m** (was 1.875 m) |
| drone echo SNR at 10 m | **71 dB — unchanged** (`fmcw_sim.py --f0 2.44 --sweep-bw 40 --gain 13.4 --budget`) |
| self-test at 40 MHz | range error 0.1–0.4 m, azimuth 0.4–2° — same as full band |
| scan revisit | 9 beams × 64 chirps × 7.4 ms = **4.3 s** (not the 1.5 s an earlier draft claimed); `--n-chirps 32` gives 2.1 s at −3 dB, and lock-and-dither is the real fix |

The coarser range cell does not hurt tracking: range *accuracy* comes from
sub-cell interpolation (SNR-limited, 71 dB), azimuth from beam centroiding,
and static clutter is removed by background subtraction regardless of cell
width. What you lose is the ability to separate two objects less than ~3.5 m
apart in range — you have one drone.

**The other direction is the one to design for — not free.** The horn is
wideband and the SPF5189Z behind it is a 50–4000 MHz amplifier with no
selectivity, so *everything* in the room lands on it. The mixer does move
channel-1 energy to 17–80 MHz, above the 15 kHz video filter — but only
while the chain is linear. The worst in-beam source is the **drone's own
AP at +20 dBm**, which is in the beam by definition:

| into the radar receiver | at the LNA | at the mixer RF | margin to compression* |
|---|---|---|---|
| drone AP +20 dBm, 5 m, in beam | −21 dBm | −9 dBm | **~8 dB** with WiFi's +10 dB peaks |
| drone AP turned down to +10 dBm | −31 dBm | −19 dBm | ~18 dB |
| phone +15 dBm, in the beam at 3 m | −21 dBm | −9 dBm | ~8 dB |
| phone behind the horns (F/B ≈ 25 dB) | −43 dBm | −31 dBm | ~30 dB |
| TX→RX leakage, 35 dB isolation | −25 dBm | −13 dBm | ~12 dB |

\*SPF5189Z input P1dB ≈ +6 dBm; ZX05-43MH-S+ RF-port compression ≈ +9 dBm.

So the plan needs three things Kevin pointed at:

1. **Turn the drone's AP power down to 10 dBm** — `menuconfig` →
   Component config → PHY → Max WiFi TX power (its minimum), in the same
   build as the channel change (§1). Indoors at 10 m that is plenty for the
   phone link and buys 10 dB at the radar.
2. **A 2.4 GHz band-pass filter between the RX horn and the LNA** (2400–2500
   MHz SMA inline, ~$20, `hardware/BOM.md` row 7b). It cannot separate
   channel 1 from the sweep — no cheap filter has a 17 MHz transition — but
   it takes every out-of-ISM signal (cellular, 5 GHz images, broadcast) off
   the wideband amplifier, which is Kevin's main point.
3. **The operator with the phone stands behind the horns.** The horn's
   front-to-back ratio is worth ~25 dB; a phone held in the beam is as bad
   as the drone's AP.

And a fourth, on the sweep: if the bring-up test below shows the noise
floor rising when the AP is on, widen the guard (`SET f0_mhz 2450`,
`SET bw_mhz 33.5`, range cell 4.5 m) before anything else.

Radar defaults stay the full band; the coexistence sweep is two serial
commands on `radar_ctl` (§3).

---

## 1. Build the drone and flash ESP-Drone — the official way, with two settings changed

Follow the kit's own guide **exactly** — the ESP-FLY tutorial video and the
Elektor build article linked from the official repository
(`Seeed-Projects/Co-Create_ESP-FLY`). Nothing in that procedure changes
except two `menuconfig` values set **before** the flash step. In the guide's
order:

1. Install **ESP-IDF 5.0.7** (the guide's version; PowerShell + ESP32-S3
   support in the installer).
2. Download the guide's pre-configured firmware, extract it, and `cd` into
   its `esp-drone` folder in the ESP-IDF PowerShell.
3. **Deviation 1 — the channel.** Run

   ```
   idf.py menuconfig
   ```

   → **ESPDrone Config → Wi-Fi/ESP-Now Channel** → set **1**
   (`CONFIG_WIFI_CHANNEL`; the default is 6, which sits inside the radar's
   sweep). Leave **Wi-Fi Base SSID** (`ESP-DRONE`) and **Wi-Fi Password**
   (`12345678`) as they are, so the app steps in the guide still apply.
4. **Deviation 2 — the AP power.** Same `menuconfig` →
   **Component config → PHY → Max WiFi TX power (dBm)** → set **10**
   (`CONFIG_ESP_PHY_MAX_WIFI_TX_POWER`; default 20, and 10 is the lowest the
   option allows). 10 dBm is plenty for a phone 3 m away and takes 10 dB off
   what the radar's receiver has to swallow (§0). Save and exit.
5. Flash and watch the log, exactly as the guide does:

   ```
   idf.py -p COMX flash monitor
   ```

   with your COM port. **"Ready to Fly"** in the log is the guide's success
   line and yours too.

Do **not** use the repository's prebuilt
`ESP32Drone_Firmware_FlashdownloadTool_0x00.bin`: it is built for channel 6.

**Checkpoint 1:** a WiFi-analyser app on the phone shows `ESP-DRONE-xxxx`
on **channel 1**. If it shows 6, the sdkconfig didn't take — re-run
menuconfig and re-flash.

Channel 11 (2451–2473) with the sweep **below** it (`SET f0_mhz 2400`,
`SET bw_mhz 40`) is the mirror-image alternative; channel 1 is preferred.
Channels 12–13 are not usable in the US.

## 2. Phone — as the guide says

1. Power the drone on a **flat, still surface** — the guide's own step; the
   IMU calibrates at power-up.
2. Join the phone to `ESP-DRONE-xxxx`, password `12345678`.
3. Open the **ESP-Drone** app (App Store; Android APK per the guide), tap
   **connect** — the drone's **green LED** lights. Left stick throttle/yaw,
   right stick pitch/roll.
4. Fly once **with the radar off**. Nothing about the flight has changed —
   this is the stock phone-flying path.

**Checkpoint 2:** stable hover from the phone, radar powered off.

## 3. Radar side: the coexistence sweep

In the `radar_ctl` serial monitor (or `SET` lines in your start-up notes):

```
SET f0_mhz 2440
SET bw_mhz 40
?          -> "f0_mhz":2440.0,"bw_mhz":40.0,"rf":1
```

`radar_acquire.py --ctl …` reads the sweep edges from that status, so nothing
else needs changing. Without `--ctl` (stage 1), pass `--f0-mhz 2440
--bw-mhz 40` so the range scale matches. The ESP32 refuses any setting that
would leave 2400–2483.5 MHz.

## 4. The link test — this is the checkpoint that matters

Drone on the bench **1 m in front of the horns, in the beam**, powered,
phone connected, props **off**. Run a ping tool on the phone against the
drone's IP (any "PingTools"-type app, 100 pings at 100 ms):

1. Radar `SWEEP 0` → note loss (should be 0 %) and round-trip (~5–20 ms).
2. Radar `SWEEP 1` on the coexistence sweep → **loss must stay ≈ 0 %** and
   round-trip unchanged.
3. For calibration of your own margin, `SET f0_mhz 2400 SET bw_mhz 83.5`
   (the sweep now crosses channel 1) → you should *see* packet loss appear.
   Go back to 2440/40.

4. **The reverse test — does the drone's WiFi hurt the radar?** With the
   drone on the bench in the beam and `radar_acquire.py` printing, toggle
   the drone's power (AP off / on) and have the phone stream (a video call
   on the drone's AP is a worst case). The radar's reported noise floor and
   the CFAR threshold must not move, and no detection may appear that
   tracks the WiFi activity. If they do: AP power down first, then the
   band-pass filter, then widen the guard.

**Checkpoint 4:** step 2 shows no loss with the beam on the drone at 1 m,
and step 4 shows the radar's noise floor indifferent to WiFi traffic. If
it does show loss, move the sweep up (`SET f0_mhz 2450`, `SET bw_mhz 33.5`,
range cell 4.5 m) and repeat; if it still does, the fallback is the 915 MHz
link in §6.

## 5. First flight with the radar scanning

Hover in the sector from the phone while `radar_acquire.py --ctl … --server
…` runs. The console tracks the drone; the phone link feels exactly as it did
in checkpoint 2.

**Checkpoint 5:** a 2-minute hover with a continuous radar track and no
control glitches. Record it (console Record button).

---

## 6. Fallback: move the link to 915 MHz ELRS

Only if checkpoint 4 fails. It costs ~$130 (RadioMaster Pocket + Bandit Nano
915 module + a 0.7 g Nano 915 receiver — your T8L has no module bay and
cannot do 900 MHz) and switches the drone to esp-fc with a CRSF receiver.
The full procedure is kept in [`archive/drone-915.md`](archive/drone-915.md); the esp-fc CLI
settings are in `firmware/archive/espfly-915/espfly-915.cli`. It also gives you back the
full 80 MHz sweep.

## 7. What is deliberately *not* on the drone

- No custom firmware of any kind: stock ESP-Drone from the kit's guide,
  two menuconfig values changed. The radar sees the airframe.
- No radio. The phone is the transmitter; the WiFi AP is the receiver.
