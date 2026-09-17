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

## Results

The HFSS output goes in [`results/`](results/), and the write-up is a LaTeX
report built from it once the measurements are in: S11 across the band, the
E- and H-plane cuts, the probe sweep, and the final table against the accept-if
line above. Until then the design numbers above are the only antenna data here.

The study notes the procedure was written from (an antenna-basics primer and
the twelve-step HFSS walkthrough for this horn) are on the `dev` branch under
[`antenna/hfss/`](https://github.com/dpaulb005/radar-dev-/tree/dev/antenna/hfss).

## What the solver is for

The gain and beamwidths have a closed form and the table above already has
them. What HFSS is genuinely for is the **probe match**, which does not: sweep
probe depth and backshort distance, and arrive at the bench already close.
