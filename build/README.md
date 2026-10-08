# Build documents

Two printable PDFs that take the radar from a pile of parts to a working bench:

| file | what it is |
|---|---|
| [`fabrication.pdf`](fabrication.pdf) | **Part 1, parts and fabrication.** The parts list checked against `BOM_Radar_Build.xlsx`, tools, the copper horn pieces flat and laid out on the sheet, full-size cutting templates (print at 100 %), the frame drawings and cut list, the saddle clamp, the cable runs, schematics of everything on the breadboard, the pick list and the connector table. |
| [`assembly.pdf`](assembly.pdf) | **Part 2, assembly and bring-up.** The build in stages, each ending in a gate you measure: horns, frame, the seventeen breadboard steps, power, firmware, mounting and cabling, then first light, the walk test, clutter cancellation and the drone link. |

Nothing in the drawings is typed by hand. `tools/make_figures.py` takes the horn
from `antenna/tools/make_build_guide.py` (which solves it from `horn.py`), the
frame and bench layout from the 3-D model's numbers, the parts status from the
spreadsheet, and the breadboard steps from `breadboard/assembly/ASSEMBLY.md`,
and writes LaTeX fragments into `generated/`.

Rebuild (needs Python with shapely, reportlab, openpyxl and Pillow; LuaLaTeX with
TikZ and circuitikz; `rsvg-convert`):

    cd build
    python3 tools/make_figures.py
    latexmk -lualatex fabrication.tex assembly.tex
