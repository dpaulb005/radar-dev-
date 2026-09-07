# firmware/espfly — what runs on the ESP-FLY

**Current plan: nothing from here.** The drone is flown from the phone on
the stock ESP-Drone firmware (AP on channel 1) — see `docs/drone-software.md` (this directory is archived; the live plan is the phone).

This directory is the **fallback**: esp-fc configuration for a 915 MHz
ELRS/CRSF receiver, if the phone link and the radar turn out not to coexist:

- `espfly-915.cli` — the esp-fc CLI settings (receiver pins, serial RX,
  failsafe). Paste into the Configurator's CLI tab.

Step-by-step: [`../../docs/drone-hardware.md`](../../docs/drone-hardware.md)
(receiver swap, antenna, radio) and
[`../../docs/drone-software.md`](../../docs/drone-software.md) (ELRS flash,
EdgeTX model, esp-fc Ports/Receiver/Modes, failsafe test, first flights).

Building esp-fc yourself (only if you are not using the ESP-FLY's supplied
binary): PlatformIO, env `esp32s3` (`pio run -e esp32s3 -t upload`). The
receiver-related changes are all runtime settings; no source edits.

Not here any more, on purpose: `drone_beacon`, MAC filtering, the AP/FTM
patches — those belonged to the passive RF tracker.
