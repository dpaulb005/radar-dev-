# KiCad schematic — breadboard + the system around it

`radar_breadboard.kicad_sch` — native KiCad schematic (opens in KiCad 7 or 8;
all symbols embedded, no libraries needed). One A3 sheet:

- **Left, BREADBOARD** — what is physically built on the breadboard: mixer-IF
  termination (49.9 Ω + 1 nF RF stop), two-stage TL072 video amplifier (two
  159 Hz high-passes, gain 101 × 11, 15.9 kHz low-pass, buffered output),
  buffered half-rail reference, 12 V protection and VANA filter, 5 V
  distribution with a ferrite + 10 µ + 100 n per RF module, ESP32 harness
  with 33 Ω series resistors to the ADF4351, A4988 logic pull-ups, sync
  divider.
- **Right, SYSTEM** — the modules the breadboard connects to: 12 V supply,
  LM2596, ESP32 devkit, ADF4351, 3 dB pad, PA, splitter, TX/RX horns,
  band-pass, LNA, mixer, A4988 + NEMA-17, UCA202 sound card. Every 2.4 GHz
  path is SMA coax between modules; nothing RF touches the breadboard.

Nets with the same label are one net across both halves.

| file | |
|---|---|
| `radar_breadboard.kicad_sch` / `.kicad_pro` | the schematic |
| `radar_breadboard.svg` / `.png` | rendered by `kicad-cli 7.0.11` |
| `gen_schematic.py` | regenerates everything; also runs a connectivity self-check (no dangling wires, no single-pin nets) and writes `nets.json` |

Not run: KiCad ERC (`kicad-cli` 7 has no `erc` subcommand; run it from the GUI).
