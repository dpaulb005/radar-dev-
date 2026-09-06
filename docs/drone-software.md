# ESP-FLY drone software — step by step (fly by phone, radar on the same band)

**Decision: the drone is flown from the phone.** That means the ESP-FLY runs
the **ESP-Drone** firmware and is controlled over its own WiFi access point.
There is no radio, no ELRS, no esp-fc receiver setup. The drone-side "software"
is one firmware option and one test.

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
| radar sweep | **2440–2483.5 MHz = 43.5 MHz** |
| range cell | **3.45 m** (was 1.80 m) |
| drone echo SNR at 10 m | **71 dB — unchanged** (`fmcw_sim.py --f0 2.44 --sweep-bw 43.5 --gain 13.4 --budget`) |
| self-test at 43.5 MHz | range error 0.1–0.4 m, azimuth 0.4–2° — same as full band |

The coarser range cell does not hurt tracking: range *accuracy* comes from
sub-cell interpolation (SNR-limited, 71 dB), azimuth from beam centroiding,
and static clutter is removed by background subtraction regardless of cell
width. What you lose is the ability to separate two objects less than ~3.5 m
apart in range — you have one drone.

The other direction is free: the phone and the AP are strong *into the
radar's* receiver (−35 dBm), but the mixer moves them to 17–70 MHz, far above
the 15 kHz video low-pass, and −35 dBm is 40 dB below the LNA's compression.

Radar defaults stay the full band; the coexistence sweep is two serial
commands on `radar_ctl` (§3).

---

## 1. ESP-Drone firmware on channel 1

ESP-Drone defaults to **channel 6** (`CONFIG_WIFI_CHANNEL=6`), which sits in
the middle of the band and leaves no room for a useful sweep on either side.
Rebuild it on channel 1:

1. Clone Seeed's ESP-FLY firmware (the `Firmware/` tree of
   `Seeed-Projects/Co-Create_ESP-FLY`, an esp-drone fork for the XIAO S3)
   with ESP-IDF installed.
2. `idf.py menuconfig` → **ESPDrone Config → Wi-Fi/ESP-Now Channel** = **1**
   (or add `CONFIG_WIFI_CHANNEL=1` to `sdkconfig.defaults`). While there:
   `WIFI_BASE_SSID` / `WIFI_PASSWORD` are the AP name and password; leave
   `WIFI_MAX_STA_CONN` at 3.
3. `idf.py -p <port> flash`.

**Checkpoint 1:** a WiFi-analyser app on the phone shows the `ESP-DRONE-xxxx`
AP on **channel 1**. If it is on 6, the sdkconfig didn't take.

Channel 11 (2451–2473) with the sweep **below** it (`SET f0_mhz 2400`,
`SET bw_mhz 40`) is the mirror-image alternative; channel 1 is preferred
because it leaves 3.5 MHz more sweep. Channels 12–13 are not usable in the US.

## 2. App

Connect the phone to the drone's AP (password from §1), open the ESP-Drone
app, connect (default host 192.168.43.42, UDP 2390 — check the app's
connection settings if it doesn't find the drone). Fly it once **with the
radar off** to confirm nothing about the flight changed — it hasn't, this is
the stock ESP-FLY phone-flying path.

**Checkpoint 2:** stable hover from the phone, radar powered off.

## 3. Radar side: the coexistence sweep

In the `radar_ctl` serial monitor (or `SET` lines in your start-up notes):

```
SET f0_mhz 2440
SET bw_mhz 43.5
?          -> "f0_mhz":2440.0,"bw_mhz":43.5
```

`radar_acquire.py --ctl …` reads the sweep edges from that status, so nothing
else needs changing. Without `--ctl` (stage 1), pass `--f0-mhz 2440
--bw-mhz 43.5` so the range scale matches. The ESP32 refuses any setting that
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
   Go back to 2440/43.5.

**Checkpoint 4:** step 2 shows no loss with the beam on the drone at 1 m. If
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
The full procedure is kept in [`drone-915.md`](drone-915.md); the esp-fc CLI
settings are in `firmware/espfly/espfly-915.cli`. It also gives you back the
full 83.5 MHz sweep.

## 7. What is deliberately *not* on the drone

- No beacon firmware, no MAC filtering, no esp-fc patches — those were the
  passive system. The radar sees the airframe.
- No radio. The phone is the transmitter; the WiFi AP is the receiver.
