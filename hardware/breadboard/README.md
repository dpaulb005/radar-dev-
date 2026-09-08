# Breadboard — hole-level layout

Where every lead and every jumper goes on the 830-point breadboard that carries the
video amplifier, bias, power entry and the digital harness (`docs/radar-hardware.md`,
sheet `hardware/kicad/radar_breadboard.kicad_sch`).

| file | what |
|---|---|
| `layout.py` | the placement (one line per part, one per wire) plus a checker: no hole used twice, every part within reach, and a union-find pass that proves every schematic net is one connected group with no shorts against `../kicad/radar_breadboard_nets.json`. Refuses to write outputs if anything fails. |
| `WIRING.md` | generated build sheet: component table (lead → hole), numbered jumper list, nets as built |
| `breadboard.svg` / `.png` | generated top view |
| `layout.json` | machine-readable placement, wires and strip → net map |
| `gen_page.py` → `breadboard.html` | interactive page: hover/click any part, wire, net or hole to see what it touches; build checklist |

```
python3 layout.py      # VERIFIED: every net is one group, no shorts, rails correct
python3 gen_page.py    # rebuild breadboard.html
```

Conventions: columns 1–63 left → right, rows a–e (top bank) and f–j (bottom bank); the five holes
of one column in one bank are one strip. `TR-@12` means the top blue rail, hole nearest column 12
(use the closest free rail hole). Rails: top red **V5**, top blue **GND**, bottom red **VANA**,
bottom blue **GND**; four bridge wires at 31|32 cover boards with split rails. U1/U2 pin 1 sits
at the low column number (e5, e30).
