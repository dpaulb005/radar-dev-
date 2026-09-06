# firmware/espfly — what runs on the ESP-FLY

**esp-fc, unmodified.** The drone is a non-cooperative radar target; it needs
no code from this repo. What it needs is *configuration* so that it flies on
915 MHz ELRS (out of the radar's 2.4 GHz sweep) — captured here:

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
