# Antenna design and EM simulation

Two candidate custom antennas for the 2.4 GHz FMCW build, and the simulation
methodology that keeps you honest.

```bash
python antenna/horn.py                 # optimum pyramidal horn (recommended)
python antenna/vivaldi.py --array 4    # tapered-slot alternative
```

## Choose the antenna before you model — the workflows diverge

**Horn** is easier to mesh and easier to fabricate accurately, and the
waveguide feed is inherently wideband, which keeps the door open to widening
the VCO sweep later. **Vivaldi** is harder to feed correctly in simulation but
buys more bandwidth. For this build the horn is the recommendation.

## The horn design, and the constraint that trips people up

`antenna/horn.py` implements Balanis' optimum pyramidal horn for a WR-340 feed
at 2.45 GHz:

```
feed guide a x b       : 86.4 x 43.2 mm   TE10 cutoff 1.735 GHz
                                          single-mode to 3.47 GHz (covers 2.31-2.54)
guide wavelength       : 173.3 mm
coax probe             : ~29 mm long, 43 mm (lambda_g/4) from the shorted back wall
aperture a1 (H-plane)  : 263.8 mm
aperture b1 (E-plane)  : 193.1 mm
axial flare length     : pe 91.5 mm | ph 91.5 mm
realizability pe == ph : 0.00 % apart -> geometry closes
predicted gain         : 13.4 dBi
aperture bound 4piA/l^2: 16.3 dBi
aperture efficiency    : 51 %          <- textbook optimum
beamwidths             : ~34 deg E, ~36 deg H
```

**A pyramidal horn is only physically constructible if the E- and H-plane
flares reach the aperture at the same axial length (pe == ph).** The tool
enforces it. Adjust `a1` or `b1` by hand and you must re-solve the other, or
the geometry will not close in CAD — a confusing failure mode if you do not
know to look for it.

The near-symmetric E/H beamwidths are worth having: asymmetric patterns make
clutter behaviour direction-dependent and complicate any later angle work.

That is a 264 × 193 mm aperture, **twice** (TX and RX). If unwieldy,
`--gain 11` shrinks it substantially — note the trade in your log rather than
silently picking small.

## Sanity-check every result against closed form

> **G ≤ 4πA/λ².** An EM solver will happily hand you a gain that violates
> physics if the model is set up wrong, and the aperture bound is the only
> cheap defence.

Write the check into the log explicitly:

> *"Simulated 13.1 dBi, aperture bound 16.3 dBi, 47 % efficiency, plausible."*

That one sentence tells a reviewer more about you than the plot does. (Worked
example of why: a 100 × 85 mm aperture gives 4πA/λ² = 7.1, i.e. **8.5 dBi is
the ceiling at 100 % efficiency** — realistically 5–6 dBi. Any page quoting
14.4 dB from that aperture is describing a different build, or is wrong. A 35°
beamwidth independently implies an aperture nearer 180 mm.)

## HFSS setup

- **Parametrize every dimension as a design variable from the first sketch.**
  Retrofitting variables into a geometry drawn with hard numbers is miserable,
  and you cannot sweep without them.
- λ = 122 mm at 2.45 GHz. **Radiation boundary at λ/2 ≈ 61 mm**, not λ/4 —
  tight boxes wreck back-lobe and cross-pol fidelity and you will chase a
  discrepancy that is purely numerical. PML is better still.
- **Wave port on the actual SMA launch geometry**, de-embedded to the antenna
  reference plane. An idealised port floating in space is the most common
  reason a simulated S11 does not match a VNA.
- *Vivaldi microstrip feed gotcha:* the wave port must be ~8× substrate height
  tall and ~8–10× trace width wide. Too small clips the field, too large
  excites box modes. Both look like a mysteriously bad match.
- **Sheet metal as 2D sheets with a finite-conductivity boundary**, not 3D
  solids. Same physics, far fewer tets.
- **Use the symmetry planes** — the horn has two (Perfect E on one, Perfect H
  on the other). Quarter model, ~4× faster, identical answer.
- Mesh seeding: length-based seeds on the **aperture rim** and the **probe** —
  the two places the field varies fastest and adaptive refinement is slow to
  find on its own.
- FR4 as εr = 4.3, tanδ = 0.02, and **note in the log that FR4 varies 4.2–4.6
  batch to batch** — a predicted source of sim-vs-measured delta. Predicting it
  in advance is worth more than explaining it afterward.
- Adaptive at 2.45 GHz for the horn; **multi-frequency adaptive at 2.0 / 2.45 /
  3.0 GHz for the Vivaldi** — single-point adaptation on a wideband structure
  gives a mesh that is only right mid-band, and the taper edges are exactly
  where you need resolution.
- ΔS = 0.02, minimum two converged passes. Interpolating sweep 2.0–3.0 GHz.
- **Report realized gain, not peak directivity** — mismatch is part of the answer.

### Do the feed in two stages

1. **Horn alone**, waveguide port at the throat. Isolates the flare from the
   feed: realized gain, patterns, phase centre, with nothing confounding.
2. **Coax-to-waveguide transition alone**, shorted section only, wave port on
   the coax. Tune probe length and backshort distance for S11 < −15 dB across
   2.3–2.6 GHz. Two variables, clean parametric sweep.

Then combine and verify. Debugging a bad match in a combined model is miserable
because you cannot tell whether the flare or the launch is at fault.

## The five studies

1. **Convergence.** ΔS vs adaptive pass, and gain vs pass. Prove mesh
   independence before believing any number. One figure that demonstrates you
   know simulation output is not truth.
2. **Parametric sweep** on the two or three dominant dimensions. Prefer
   explicit sweeps over Optimetrics — you want to show you understand *why* the
   geometry moved; a black-box optimizer result is much weaker in a write-up.
3. **Realized gain, pattern cuts, and phase centre.** φ = 0° and 90°, θ from
   −180° to 180° at 1°. **Plot phase-centre position vs frequency across the
   band** — for FMCW this is the study that matters most and the one nobody
   else will have run. A phase centre that walks with frequency smears the beat
   tone and degrades range accuracy; Vivaldis are notorious for it because the
   radiating region moves along the taper.
4. **Two-element coupling.** Both antennas in one model at real spacing;
   extract S21 vs separation. **That coupling term sets your close-in noise
   floor through VCO phase noise** — it is the real limiter, and simulating it
   before cutting metal is the judgement call worth showing. Use FE-BI or the
   hybrid solver for the air between them; filling it with FEM gets expensive
   fast. Re-run with absorber or a metal fence and quantify the improvement.
5. **Optional, if going after angle:** the two-element Rx pair. Simulate
   **embedded** element patterns, not isolated ones — mutual coupling distorts
   each element's pattern, and that distortion is what corrupts the steering
   vector and breaks AoA estimators.

## Validation and documentation

S11 and S21 on a VNA (a LiteVNA is adequate at 2.4 GHz). Pattern cuts need a
range, but a rough outdoor two-mast measurement with a reference antenna gets
within a couple of dB — and writing up *why* it is only within a couple of dB
is itself worth documenting.

Per design iteration, committed as you go with real dates:

- design intent and the **hand calculation** that motivated the geometry
- HFSS parameter table **plus the `.aedt` file**, not just screenshots
- fabrication photos, including what went wrong
- **raw** measured data
- **sim vs measured overlay plot** — the money figure
- a paragraph on the discrepancy and your theory for it

Keep a dated lab notebook alongside. Commit history plus notebook is the
credibility artifact. For the write-up itself: **3–5 pages plus a repo link.**
