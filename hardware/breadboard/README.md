# Breadboard — hole-level layout

Where every lead and every jumper goes on the 830-point breadboard that carries the
video amplifier, bias, power entry and the digital harness (`docs/radar-hardware.md`,
sheet `hardware/kicad/radar_breadboard.kicad_sch`).

| file | what |
|---|---|
| `layout.py` | the placement (one line per part, one per wire) plus a checker: no hole used twice, every part within reach, and a union-find pass that proves every schematic net is one connected group with no shorts against `../kicad/radar_breadboard_nets.json`. Refuses to write outputs if anything fails. |
| **`ASSEMBLY.md`** | **generated step-by-step build guide — 17 steps, a picture of the board at each one, and something to measure before you move on. Start here.** |
| `steps/` | one SVG + PNG per assembly step: grey is what you already built, colour is what that step adds |
| `WIRING.md` | generated build sheet: component table (lead → hole), numbered jumper list, nets as built |
| `breadboard.svg` / `.png` | generated top view |
| `layout.json` | machine-readable placement, wires and strip → net map |
| `gen_page.py` → `breadboard.html` | interactive page: hover/click any part, wire, net or hole to see what it touches; build checklist; **Chips & modules** tab with the real TL072, ESP32 (30- and 38-pin), A4988, ADF4351 and UCA202 pinouts and where each used pin lands on the board |
| `MODULES.md`, `modules.png` | the same pin maps as tables / picture |

```
python3 layout.py      # checks, then writes WIRING.md, ASSEMBLY.md, steps/, layout.json, breadboard.svg
python3 render_png.py  # rasterise breadboard.svg and steps/*.svg to PNG (uses the Chromium in /opt/pw-browsers)
python3 gen_page.py    # rebuild breadboard.html
```

`layout.py` refuses to write anything unless every schematic net is one connected
group on the board **and** every part and every wire belongs to exactly one
assembly step — so the guide cannot drift from the placement.

**Jumper colour code.** One hue per function: black GND, red VANA, orange V5,
yellow 3V3, green the audio signal path, violet VREF, blue SPI to the ADF4351,
brown the stepper's STEP/DIR/EN, pink SYNC. There is deliberately no white and
no grey wire anywhere — on a cream breadboard both disappear.

Conventions: columns 1–63 left → right, rows a–e (top bank) and f–j (bottom bank); the five holes
of one column in one bank are one strip. `TR-@12` means the top blue rail, hole nearest column 12
(use the closest free rail hole). Rails: top red **V5**, top blue **GND**, bottom red **VANA**,
bottom blue **GND**; four bridge wires at 31|32 cover boards with split rails. U1/U2 sit with the
notch and pin-1 dot toward the higher column (pin 1 at e8 / e33, pin 8 at f8 / f33): seen from
above the top row reads 4 3 2 1 left→right and the bottom row 5 6 7 8, as on a real DIP.
