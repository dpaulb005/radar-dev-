# antenna/hfss — study notes for simulating the horn

Two PDFs, both laid out for printing and writing on: body text on the left, a
ruled notes column down the right of every page.

| file | what it is |
|---|---|
| [`antenna-basics.pdf`](antenna-basics.pdf) | **Antenna engineering, the working basics.** Field regions, gain vs directivity vs realized gain, the aperture bound, S<sub>11</sub> and match, waveguide modes and λ<sub>g</sub>, aperture phase error and optimum-horn design, how gain enters the radar equation twice, and how to read a solver result without believing it too easily. 8 pages. |
| [`hfss-horn-model.pdf`](hfss-horn-model.pdf) | **Modelling this horn in HFSS.** A twelve-step procedure for the exact antenna in [`../horn.py`](../horn.py) — variables, geometry, the coax probe feed, boundaries, ports, solution setup, far-field cuts, and the parametric sweep that tunes the match. Ends with a table to fill in. 8 pages. |

```
python3 make_basics.py     # -> antenna-basics.pdf
python3 make_hfss.py       # -> hfss-horn-model.pdf
```

Needs `reportlab` and DejaVu (`/usr/share/fonts/truetype/dejavu`). The built-in
Helvetica has no Greek glyphs, so λ, ρ and φ would print as black boxes — which
in an antenna document is most of the symbols that matter.

**The HFSS guide imports `../horn.py`.** Every dimension in its variable table,
its cross-section drawing and its accept-if table is solved at generation time,
so the guide cannot drift from the antenna the repo specifies. Change the design
frequency or the target gain in `horn.py`, re-run `make_hfss.py`, and the
document follows.

## The one idea worth taking from both

Run `python3 ../horn.py` first. It gives you the gain, the beamwidths and the
aperture bound in a millisecond, and those are the numbers the simulation has to
reproduce before any of its output means anything — a converged HFSS solution of
a wrong model is still converged.

What the solver is genuinely for is the **probe match**, which has no useful
closed form: sweep probe depth and backshort distance, and arrive at the bench
already close. [`../../docs/radar-hardware.md`](../../docs/radar-hardware.md)
§ 2c is the fallback if you never simulate at all — tune the probe against the
radar's own detection SNR, which optimises the quantity you actually care about.
