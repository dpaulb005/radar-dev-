#!/usr/bin/env python3
"""make_basics.py — "Antenna engineering, the working basics" as a note-taking PDF.

Written for someone who is about to simulate and then cut a 2.45 GHz pyramidal
horn, so it stops where that stops: aperture antennas, waveguide feeds, and the
handful of numbers that decide whether a horn works. It is not a substitute for
Balanis; it is the part of Balanis you need before HFSS will tell you anything
you can trust.

    python3 make_basics.py          # writes antenna-basics.pdf
"""
import pathlib

from reportlab.platypus import PageBreak, Spacer

from notesheet import (NoteDoc, P, bullets, callout, note_lines, table,
                       title_block, S)

OUT = pathlib.Path(__file__).resolve().parent / "antenna-basics.pdf"


def story():
    s = []
    s += title_block(
        "Antenna engineering — the working basics",
        "Companion notes for the 2.45 GHz pyramidal horn in this repo · print and write on",
        "An antenna is an impedance transformer between a transmission line and free space, "
        "and every quantity below is a way of asking how well it does that, or where the "
        "energy goes once it has. This covers what you need to read an HFSS result and know "
        "whether to believe it. Symbols follow Balanis.",
        [["λ", "free-space wavelength, c/f. At 2.45 GHz, <b>122.4 mm</b>"],
         ["a, b", "waveguide broad and narrow inside dimensions"],
         ["a<sub>1</sub>, b<sub>1</sub>", "horn aperture, H-plane and E-plane"],
         ["ρ<sub>1</sub>, ρ<sub>2</sub>", "E- and H-plane flare radii (apex distances)"],
         ["Γ", "reflection coefficient at the feed; S<sub>11</sub> is the same thing in dB"]])

    # ---------------------------------------------------------------- 1
    s.append(P("1 · What the antenna is doing", "h2"))
    s.append(P(
        "A transmission line carries a guided wave: the fields are bound to the conductors "
        "and nothing radiates. Free space carries an unguided wave with a characteristic "
        "impedance of <b>η<sub>0</sub> = 376.7 Ω</b>. An antenna is the structure that gets "
        "you from one to the other without reflecting most of the power back where it came "
        "from. A horn does it gradually — that is the whole idea of the flare."))
    s.append(P(
        "<b>Reciprocity.</b> The pattern, gain and impedance of a passive antenna are "
        "identical transmitting and receiving. This is why the radar can use two identical "
        "horns and why you may simulate only the transmit case. It stops being true the "
        "moment anything non-reciprocal is in the path — a circulator, a ferrite, an "
        "amplifier."))

    s.append(P("Field regions", "h3"))
    s.append(P(
        "The pattern is only a pattern once you are far enough away. Three regions, with D "
        "the largest aperture dimension:"))
    s.append(table(
        [["region", "extent", "what happens there"],
         ["Reactive near field", "r &lt; 0.62·√(D³/λ)", "Stored energy, not radiation. Fields are largely out of phase with each other."],
         ["Radiating near field (Fresnel)", "0.62·√(D³/λ) &lt; r &lt; 2D²/λ", "It radiates, but the pattern still changes shape with distance."],
         ["Far field (Fraunhofer)", "r &gt; 2D²/λ", "Pattern shape is fixed; only amplitude falls, as 1/r. <b>This is where gain is defined.</b>"]],
        [28, 30, 42], mono_cols=(1,)))
    s.append(callout(
        "Why this bites you on the bench",
        "For this horn D is the 327 mm aperture diagonal, so the far field starts at "
        "<b>2D²/λ = 1.75 m</b>. A gain measurement at 1 m is measuring the wrong thing. The "
        "two-antenna method in the build notes uses 3 m for exactly this reason. HFSS reports "
        "far-field quantities by extrapolation, so it does not care — but your tape measure does."))

    # ---------------------------------------------------------------- 2
    s.append(P("2 · The quantities, and what each one hides", "h2"))

    s.append(P("Radiation pattern", "h3"))
    s.append(P(
        "Power density as a function of direction, normalised and plotted in dB. The features "
        "worth naming: the <b>main lobe</b>, the <b>half-power beamwidth</b> (HPBW, the angle "
        "between the −3 dB points), the <b>first null beamwidth</b>, the <b>sidelobes</b> and "
        "the <b>back lobe</b>. A uniformly illuminated rectangular aperture has a sin(x)/x "
        "pattern and a first sidelobe at <b>−13.2 dB</b>; anything that tapers the "
        "illumination toward the edges pushes sidelobes down and widens the main lobe. You "
        "cannot have both."))

    s.append(P("Directivity, gain, and efficiency — three different things", "h3"))
    s.append(table(
        [["term", "definition", "what it excludes"],
         ["Directivity D", "How much of the radiated power goes in the best direction, vs an isotropic radiator.", "All losses. A perfectly lossy antenna can have high directivity."],
         ["Gain G", "G = e<sub>cd</sub> · D, where e<sub>cd</sub> is conduction and dielectric efficiency.", "Mismatch. Power reflected at the port is not counted."],
         ["Realized gain", "G<sub>re</sub> = (1 − |Γ|²) · G", "Nothing. <b>This is the number that matters,</b> and what HFSS plots by default."]],
        [22, 48, 30]))
    s.append(P(
        "For a well-made horn the difference between D and G is a few tenths of a dB — copper "
        "loss at 2.4 GHz is small. The difference between G and realized gain is entirely "
        "about your feed match, which is the part you actually have to tune.", "small"))
    s.append(P(
        "<b>dBi vs dBd.</b> dBi is referenced to an isotropic radiator, dBd to a half-wave "
        "dipole. dBd + 2.15 = dBi. Datasheets that quote a suspiciously good number are often "
        "quietly using dBd, or quoting directivity, or both.", "small"))

    s.append(P("EIRP", "h3"))
    s.append(P(
        "EIRP = transmit power + antenna gain, and it is what regulators limit. This radar "
        "puts about +10 dBm into a 13.4 dBi horn, so <b>EIRP ≈ +23.4 dBm = 0.2 W</b> — inside "
        "Part 15 for the 2.4 GHz ISM band. Note that gain cuts both ways: a higher-gain horn "
        "is not free, it spends your legal budget."))

    s.append(P("Aperture, and the bound you cannot beat", "h3"))
    s.append(P("For an aperture antenna of physical area A:"))
    s.append(P("G = (4π/λ²) · A · e<sub>ap</sub>        with  e<sub>ap</sub> ≤ 1", "eq"))
    s.append(P(
        "The <b>aperture efficiency</b> e<sub>ap</sub> collects everything that stops the "
        "aperture radiating as if it were uniformly illuminated and perfectly in phase: taper, "
        "phase error across the mouth, spillover, blockage. An optimum pyramidal horn runs at "
        "about <b>0.51</b>, and that is not a defect — it is the price of the phase curvature "
        "that comes with a short flare (§ 4)."))
    s.append(callout(
        "The cheapest sanity check in antenna work",
        "4πA/λ² is the gain of a perfectly illuminated aperture of that size. <b>No passive "
        "antenna of that aperture can exceed it.</b> A solver that hands you a gain above the "
        "bound is telling you the model is wrong — usually a port that is injecting more power "
        "than you think, or a radiation boundary so close it is acting as a reflector. For "
        "this horn the bound is <b>16.3 dBi</b> and the design sits at 13.4 dBi. Compute it "
        "before you trust any simulated gain, every time."))

    s.append(P("Impedance, match and bandwidth", "h3"))
    s.append(P(
        "At the feed the antenna looks like an impedance Z<sub>in</sub>. Referenced to the "
        "line impedance Z<sub>0</sub> (50 Ω here) it becomes the reflection coefficient:"))
    s.append(P("Γ = (Z<sub>in</sub> − Z<sub>0</sub>) / (Z<sub>in</sub> + Z<sub>0</sub>)\n"
               "S<sub>11</sub> (dB) = 20·log<sub>10</sub>|Γ|        VSWR = (1+|Γ|)/(1−|Γ|)", "eq"))
    s.append(table(
        [["S<sub>11</sub>", "VSWR", "|Γ|", "power reflected", "mismatch loss"],
         ["−6 dB", "3.0", "0.50", "25 %", "1.25 dB"],
         ["−10 dB", "1.92", "0.32", "10 %", "0.46 dB"],
         ["−14 dB", "1.50", "0.20", "4 %", "0.18 dB"],
         ["−20 dB", "1.22", "0.10", "1 %", "0.04 dB"]],
        [18, 16, 16, 24, 26], mono_cols=(0, 1, 2)))
    s.append(P(
        "<b>−10 dB is the usual pass mark</b>, and the table shows why it is a reasonable "
        "place to stop: the last 4 % of power costs a lot of tuning. <b>Bandwidth</b> is "
        "simply the frequency range over which you still meet it. This radar sweeps "
        "2400–2483.5 MHz, which is 3.4 % fractional bandwidth — trivially easy for a "
        "waveguide horn, whose limit is the single-mode band of the guide, not the aperture.", "small"))

    s.append(P("Polarisation", "h3"))
    s.append(P(
        "The orientation of the E-field. A rectangular waveguide in TE<sub>10</sub> gives "
        "linear polarisation, parallel to the <b>narrow</b> wall (b). Two linearly polarised "
        "antennas misaligned by angle ψ suffer a <b>polarisation loss factor of cos²ψ</b>: at "
        "45° that is 3 dB, at 90° it is in principle infinite and in practice 20–30 dB of "
        "cross-polarisation. This is why the build insists all three horns are rotated "
        "together — the radar only cares that transmit and receive agree."))

    s.append(P("Phase centre", "h3"))
    s.append(P(
        "The point the radiated field appears to come from. For a horn it sits inside the "
        "flare, not at the mouth, and it moves with frequency and differs between E- and "
        "H-planes. It does not matter for a one-antenna gain figure. It matters a great deal "
        "if you ever put two horns side by side and measure the phase difference between them "
        "to get a bearing, because that is the baseline you are dividing by."))

    s.append(PageBreak())

    # ---------------------------------------------------------------- 3
    s.append(P("3 · Waveguide, because the horn is fed by one", "h2"))
    s.append(P(
        "A hollow metal pipe carries a wave only above a <b>cutoff frequency</b>. Below it the "
        "field decays exponentially — the guide is a high-pass filter, and that is a property "
        "of the geometry, not the material. Modes are named TE<sub>mn</sub> and TM<sub>mn</sub> "
        "for the number of half-wave variations across each dimension."))
    s.append(P("f<sub>c</sub>(TE<sub>mn</sub>) = (c/2)·√((m/a)² + (n/b)²)", "eq"))
    s.append(P(
        "<b>TE<sub>10</sub> is the dominant mode</b> — the lowest cutoff, one half-wave across "
        "the broad wall a and nothing across b. You want it alone: as soon as a second mode "
        "propagates, the aperture field is a sum of two patterns and the result is neither "
        "predictable nor stable. The single-mode window runs from f<sub>c</sub>(TE<sub>10</sub>) "
        "= c/2a to f<sub>c</sub>(TE<sub>20</sub>) = c/a — exactly one octave."))
    s.append(table(
        [["for WR-340 (86.4 × 43.2 mm)", "value"],
         ["TE<sub>10</sub> cutoff, c/2a", "<b>1.735 GHz</b>"],
         ["TE<sub>20</sub> cutoff, c/a", "3.470 GHz"],
         ["single-mode band", "1.735 – 3.470 GHz — 2.45 GHz sits comfortably inside"],
         ["guide wavelength λ<sub>g</sub> at 2.45 GHz", "<b>173.3 mm</b> (λ<sub>0</sub> is 122.4 mm)"]],
        [48, 52]))
    s.append(P("λ<sub>g</sub> = λ / √(1 − (λ/2a)²)        always longer than λ", "eq"))
    s.append(P(
        "<b>The guide wavelength is longer than free space</b>, and it is λ<sub>g</sub> — not "
        "λ — that sets every length inside the guide. Using λ/4 where λ<sub>g</sub>/4 belongs "
        "is one of the most common ways a first waveguide design comes out mistuned: here it "
        "is the difference between 30.6 mm and 43.3 mm.", "small"))

    s.append(P("Getting energy in: the coax probe", "h3"))
    s.append(P(
        "A quarter-wave monopole pushed through the broad wall, parallel to the E-field, with "
        "a <b>short circuit λ<sub>g</sub>/4 behind it</b>. The short reflects a wave that "
        "arrives back at the probe having travelled λ<sub>g</sub>/2, in phase with the forward "
        "wave, so the two add going out of the guide and cancel going backward. Two knobs:"))
    s.append(bullets([
        "<b>Probe depth</b> sets the coupling, and therefore the real part of the impedance. "
        "Too short under-couples; too deep starts to look capacitive.",
        "<b>Backshort distance</b> trims the reactance. λ<sub>g</sub>/4 is the design value; "
        "a couple of millimetres either way is the fine adjustment.",
    ]))
    s.append(P(
        "For this horn: backshort at <b>43.3 mm</b>, probe about <b>29 mm</b> into a 43.2 mm "
        "guide. The probe must clear the far wall — check it, because a probe that touches is "
        "a short circuit and reads as a beautiful, entirely fictional S<sub>11</sub>.", "small"))

    # ---------------------------------------------------------------- 4
    s.append(P("4 · Aperture antennas and horn design", "h2"))
    s.append(P(
        "Open the end of a waveguide and it radiates, badly: the sudden step from "
        "η<sub>guide</sub> to 377 Ω reflects a lot, and the aperture is small so the beam is "
        "broad. Flaring fixes both — a gradual taper matches better, and a larger mouth is a "
        "larger aperture. But flaring introduces the problem that horn theory exists to "
        "manage."))

    s.append(P("Aperture phase error — the central idea", "h3"))
    s.append(P(
        "In a flared horn the wave spreads cylindrically/spherically from a virtual apex. The "
        "path from that apex to the edge of the mouth is longer than the path to the centre, "
        "so the field at the mouth is <b>not in phase across the aperture</b> — it lags at the "
        "edges. The error is quadratic, and it is expressed dimensionlessly as:"))
    s.append(P("s = b<sub>1</sub>² / (8·λ·ρ<sub>1</sub>)        (E-plane)\n"
               "t = a<sub>1</sub>² / (8·λ·ρ<sub>2</sub>)        (H-plane)", "eq"))
    s.append(P(
        "Make the horn longer for a given mouth and ρ grows, the phase error falls, and the "
        "aperture efficiency rises toward 1 — but the horn gets absurd. Make it shorter and "
        "the efficiency collapses. The <b>optimum horn</b> is the shortest one for a given "
        "gain, and it sits at:"))
    s.append(table(
        [["", "optimum value", "this horn"],
         ["E-plane, s", "1/4 = 0.250", "<b>0.250</b>"],
         ["H-plane, t", "3/8 = 0.375", "<b>0.375</b>"],
         ["aperture efficiency", "≈ 0.51", "0.51"]],
        [34, 33, 33], mono_cols=(1, 2)))
    s.append(P(
        "Those two fractions are the whole of optimum-horn design. Everything else — "
        "b<sub>1</sub> = √(2λρ<sub>1</sub>), a<sub>1</sub> = √(3λρ<sub>2</sub>), the 51 % "
        "efficiency — follows from them.", "small"))

    s.append(P("Three horns, one idea", "h3"))
    s.append(table(
        [["type", "flared in", "use"],
         ["H-plane sectoral", "a only", "fan beam, narrow in H"],
         ["E-plane sectoral", "b only", "fan beam, narrow in E"],
         ["Pyramidal", "both", "pencil beam — <b>this build</b>"]],
        [26, 22, 52]))
    s.append(callout(
        "The constraint that catches everyone",
        "A pyramidal horn only closes as a solid if the E-plane and H-plane flares reach the "
        "aperture at the <b>same axial length</b>: p<sub>e</sub> = p<sub>h</sub>. Change "
        "a<sub>1</sub> or b<sub>1</sub> on its own and the geometry no longer meets — in CAD "
        "you get a shape that will not loft, and in HFSS you get a solid with a sliver in it "
        "that meshes badly and solves slowly. <tt>horn.py</tt> solves both together and prints "
        "the mismatch as a percentage for exactly this reason."))

    s.append(P("Beamwidth and gain, closed form", "h3"))
    s.append(P("HPBW<sub>E</sub> ≈ 54·λ/b<sub>1</sub>        HPBW<sub>H</sub> ≈ 78·λ/a<sub>1</sub>", "eq"))
    s.append(P(
        "The E-plane is narrower for the same aperture dimension because its illumination is "
        "uniform, while the H-plane inherits a cosine taper from the TE<sub>10</sub> "
        "distribution. The taper is also why the H-plane sidelobes are lower. For this horn: "
        "<b>34° E, 36° H, 13.4 dBi</b>.", "small"))
    s.append(P(
        "Note what a 34° beam means for a radar: at 5 m the beam is about 3 m across. The horn "
        "does almost no localising indoors. Any real bearing has to come from somewhere else — "
        "a scan, or the phase between two receivers.", "small"))

    s.append(PageBreak())

    # ---------------------------------------------------------------- 5
    s.append(P("5 · Where the antenna meets the radar", "h2"))
    s.append(P(
        "Gain enters the radar equation <b>twice</b>, once on transmit and once on receive, so "
        "a decibel of antenna is worth two decibels of link:"))
    s.append(P("P<sub>r</sub> = P<sub>t</sub>·G<sub>t</sub>·G<sub>r</sub>·λ²·σ / ((4π)³·R⁴)", "eq"))
    s.append(bullets([
        "<b>R⁴, not R².</b> Doubling the range costs 12 dB, because the wave spreads on the "
        "way out and again on the way back.",
        "<b>λ² in the numerator</b> looks like lower frequency is better, but G for a fixed "
        "<i>physical aperture</i> goes as 1/λ², so two fixed apertures beat it back the other way.",
        "<b>σ, the radar cross-section</b>, is the wildest term: it is not the target's physical "
        "area, it varies enormously with aspect and frequency, and for a small drone it is a "
        "guess until measured.",
    ]))
    s.append(P(
        "Two antenna properties decide the rest of the radar's behaviour: <b>gain</b> sets how "
        "far, and <b>beamwidth</b> sets how well you can tell two targets apart in angle — and "
        "also, unhelpfully, how much of the room you are illuminating and therefore how much "
        "clutter comes back with the target."))

    s.append(P("Isolation, which is its own problem", "h3"))
    s.append(P(
        "A bistatic radar with separate TX and RX horns has the transmitter running "
        "continuously a few hundred millimetres from the receiver. The direct leakage is "
        "vastly stronger than any echo, and how much of it there is — S<sub>21</sub> between "
        "the two horns — is an antenna question you can simulate. Here the target is "
        "<b>S<sub>21</sub> ≤ −35 dB</b> at 290 mm separation."))

    # ---------------------------------------------------------------- 6
    s.append(P("6 · Measuring it, and simulating it", "h2"))
    s.append(P("On the bench", "h3"))
    s.append(table(
        [["measurement", "how", "watch out for"],
         ["S<sub>11</sub>", "One-port VNA sweep, calibrated at the connector.", "Calibrate at the far end of the cable, not the VNA face."],
         ["Gain", "Two identical antennas, known separation R, Friis: G = (S<sub>21</sub> + 20log<sub>10</sub>(4πR/λ))/2.", "R must exceed 2D²/λ. Ground reflections; get both antennas well off the floor."],
         ["Pattern", "Rotate one antenna against a protractor, record S<sub>21</sub>.", "The far-field condition again, plus everything in the room reflecting."],
         ["Isolation", "S<sub>21</sub> between the two mounted horns.", "Measure it in the final mount — the mount is part of the answer."]],
        [18, 46, 36]))
    s.append(P(
        "None of this needs an anechoic chamber to be useful. It needs you to know which "
        "number is being corrupted by the room, which is mostly the sidelobes and the deep "
        "nulls, not the main lobe or the match.", "small"))

    s.append(P("What a solver actually does", "h3"))
    s.append(table(
        [["method", "solves", "good at", "used by"],
         ["FEM", "Volume meshed into tetrahedra, frequency by frequency.", "Enclosed, inhomogeneous structures — waveguides, horns, connectors.", "<b>HFSS</b>"],
         ["MoM", "Currents on surfaces, integral equation.", "Open, mostly-metal radiators — wires, patches, large reflectors.", "FEKO, NEC"],
         ["FDTD", "Time-stepping the grid, one run gives all frequencies.", "Wideband and transient problems.", "CST, Meep"]],
        [12, 34, 34, 20]))
    s.append(P(
        "FEM is the right tool for this horn because the interesting physics is inside a "
        "closed metal volume with a coax feed on it. The cost is that it solves one frequency "
        "at a time and interpolates between them."))
    s.append(callout(
        "Convergence is not accuracy",
        "HFSS refines the mesh until the scattering parameters stop moving by more than "
        "<b>ΔS</b> between passes, then declares convergence. That means <i>the solver has "
        "stopped changing its mind about the model you gave it</i>. It says nothing about "
        "whether the model is the antenna you are going to build. A converged solution of a "
        "wrong geometry, a port that is too small, or an air box that is too close is "
        "converged and wrong. <b>Always check the answer against closed form</b> — that is "
        "what the numbers on the first page of the HFSS guide are for."))

    s.append(P("Ways to get a confidently wrong answer", "h3"))
    s.append(bullets([
        "<b>Air box too close.</b> A radiation boundary nearer than about λ/4 reflects, and "
        "the pattern and S<sub>11</sub> both change. λ/4 at 2.45 GHz is 30.6 mm.",
        "<b>Port too small or too large.</b> A coax wave port must enclose the dielectric and "
        "essentially nothing else. Too big and it starts supporting waveguide modes of its own.",
        "<b>Meshing the metal instead of the air.</b> What radiates is the field in the air "
        "volume. Model the air and give its walls a boundary; do not model 0.5 mm copper sheet "
        "and ask the solver to mesh it.",
        "<b>Gain above 4πA/λ².</b> Physically impossible, so the model is wrong. Check first.",
        "<b>A pattern with no back lobe at all.</b> Real horns leak backwards. A perfectly "
        "clean back hemisphere usually means the radiation boundary is wrapping the structure "
        "rather than enclosing it.",
    ]))

    s.append(P("7 · Symbols, quick reference", "h2"))
    s.append(table(
        [["symbol", "is", "for this horn"],
         ["λ", "free-space wavelength", "122.4 mm at 2.45 GHz"],
         ["λ<sub>g</sub>", "guide wavelength, TE<sub>10</sub>", "173.3 mm"],
         ["a, b", "guide inside dimensions", "86.4 × 43.2 mm (WR-340)"],
         ["a<sub>1</sub>, b<sub>1</sub>", "aperture, H-plane and E-plane", "263.8 × 193.1 mm"],
         ["ρ<sub>1</sub>, ρ<sub>2</sub>", "E- and H-plane flare radii", "152.4 / 189.6 mm"],
         ["p<sub>e</sub>, p<sub>h</sub>", "axial flare lengths (must be equal)", "91.5 / 91.5 mm"],
         ["s, t", "aperture phase errors", "0.250 / 0.375"],
         ["e<sub>ap</sub>", "aperture efficiency", "0.51"],
         ["G", "gain", "13.4 dBi (bound 16.3)"],
         ["η<sub>0</sub>", "free-space impedance", "376.7 Ω"],
         ["Γ, S<sub>11</sub>", "reflection at the feed", "target ≤ −10 dB, 2.40–2.484 GHz"]],
        [18, 44, 38], mono_cols=(2,)))

    s.append(P("Work it out yourself", "h3"))
    s.append(P(
        "The fastest way to make any of this stick is to rederive the horn from λ alone. Try "
        "it: from f = 2.45 GHz get λ; from WR-340's a get f<sub>c</sub> and λ<sub>g</sub>; "
        "from ρ<sub>1</sub> = 152.4 mm get b<sub>1</sub> = √(2λρ<sub>1</sub>) and check it "
        "against 193.1 mm; then get the gain from 0.51·4πa<sub>1</sub>b<sub>1</sub>/λ² and "
        "the beamwidths from 54λ/b<sub>1</sub> and 78λ/a<sub>1</sub>."))
    s.append(note_lines(9))
    return s


def main():
    doc = NoteDoc(OUT, "Antenna engineering — the working basics",
                  "notes for the 2.45 GHz pyramidal horn",
                  "radar-dev · antenna/horn.py")
    doc.build(story())
    print(f"wrote {OUT.name}")


if __name__ == "__main__":
    main()
