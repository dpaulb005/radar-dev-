# antenna — the horn, and its HFSS simulation

Optimum pyramidal horn at 2.45 GHz on a WR-340 waveguide section with a coax
probe feed. Three are cut from copper sheet in one session: TX, RX, and a
spare for the azimuth upgrade.

## Design dimensions

Solved by `antenna/horn.py` on the `dev` branch; this is what the HFSS model
must reproduce before its output means anything.

| | |
|---|---|
| design frequency | 2.45 GHz (λ₀ = 122.4 mm) |
| feed guide a × b | 86.4 × 43.2 mm (WR-340) |
| TE10 cutoff | 1.735 GHz, single-mode to 3.47 GHz |
| guide wavelength λg | 173.3 mm |
| coax probe | ~29 mm long, 43 mm from the shorted back wall |
| aperture a1 (H-plane) | 263.8 mm |
| aperture b1 (E-plane) | 193.1 mm |
| axial flare length | 91.5 mm (pe = ph, geometry closes) |
| predicted gain | 13.4 dBi |
| aperture bound 4πA/λ² | 16.3 dBi |
| aperture efficiency | 51 % (textbook optimum) |
| beamwidths | ~34° E-plane, ~36° H-plane |

Accept the simulation if: gain 12.5–14 dBi at 2.45 GHz, S11 below −10 dB across
2400–2483.5 MHz after the probe sweep, beamwidths within a few degrees of the
above, and gain below the aperture bound. A converged solution of a wrong model
is still converged.

## Building it

[`horn-build-guide.pdf`](horn-build-guide.pdf) is the bench guide for cutting
the three horns from 24 gauge copper sheet: every piece drawn flat to scale, a
one-sheet cutting layout per horn, the fold angles, nine build steps with a
check each, and a record page to fill in for all three.

It is generated. [`tools/horn.py`](tools/horn.py) solves the horn, and
[`tools/make_build_guide.py`](tools/make_build_guide.py) derives every panel,
fold and layout from it, then refuses to write if the four flare panels would
not meet at the corners or one horn's pieces would not fit one 12 × 24 in sheet.

```
cd tools
python3 make_build_guide.py      # needs reportlab and shapely
```

One horn takes about 178 square inches of copper with its tabs, so three horns
need three 12 × 24 in sheets.

## Results

The HFSS output goes in [`results/`](results/), and the write-up is a LaTeX
report built from it once the measurements are in: S11 across the band, the
E- and H-plane cuts, the probe sweep, and the final table against the accept-if
line above. Until then the design numbers above are the only antenna data here.

The study notes the procedure was written from (an antenna-basics primer and
the twelve-step HFSS walkthrough for this horn) are in the history, at
[`antenna/hfss/` as of 3f95c6d](https://github.com/dpaulb005/radar-dev-/tree/3f95c6d/antenna/hfss).

## What the solver is for

The gain and beamwidths have a closed form and the table above already has
them. What HFSS is genuinely for is the **probe match**, which does not: sweep
probe depth and backshort distance, and arrive at the bench already close.
