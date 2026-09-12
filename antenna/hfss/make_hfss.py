#!/usr/bin/env python3
"""make_hfss.py — "Modelling this horn in HFSS", as a note-taking PDF.

Every dimension in the document is imported from ../horn.py and computed here,
so the guide cannot drift from the antenna the repo actually specifies. Change
the design frequency or the target gain in horn.py, re-run this, and the HFSS
variable table changes with it.

    python3 make_hfss.py           # writes hfss-horn-model.pdf
"""
import importlib.util
import math
import pathlib

from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.platypus import PageBreak, Spacer

from notesheet import (ACC, BODY_W, INK, MUT, NoteDoc, P, S, bullets, callout,
                       note_lines, step, table, title_block)

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "hfss-horn-model.pdf"
C = 299792458.0


def geometry():
    """Every number the model needs, from horn.py's own solver."""
    spec = importlib.util.spec_from_file_location("H", HERE.parent / "horn.py")
    H = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(H)
    except SystemExit:
        pass
    f = 2.45e9
    lam = C / f
    a, b = H.WAVEGUIDES["WR-340"]
    a1, b1, rho1, rho2 = H.solve_optimum(lam, a, b, 13.4, 0.51)
    pe, ph = H.flare_lengths(a, b, a1, b1, rho1, rho2)
    lam_g = lam / math.sqrt(1 - (lam / (2 * a)) ** 2)
    g = dict(f=f, lam=lam * 1e3, lam_g=lam_g * 1e3, a=a * 1e3, b=b * 1e3,
             a1=a1 * 1e3, b1=b1 * 1e3, rho1=rho1 * 1e3, rho2=rho2 * 1e3,
             pe=pe * 1e3, ph=ph * 1e3, fc=C / (2 * a) / 1e9, fc2=C / a / 1e9,
             L_guide=115.0, back=lam_g / 4 * 1e3, probe=29.0,
             d_pin=1.5875, gain=10 * math.log10(0.51 * 4 * math.pi * a1 * b1 / lam ** 2),
             bound=10 * math.log10(4 * math.pi * a1 * b1 / lam ** 2),
             hp_e=54 * lam / b1, hp_h=78 * lam / a1)
    # 50 ohm coax stub sized around the real 1/16" probe rod, PTFE
    g["d_diel"] = g["d_pin"] * 10 ** (50 * math.sqrt(2.1) / 138)
    g["clear"] = 40.0                      # air-box clearance, must exceed lambda/4
    g["quarter"] = g["lam"] / 4
    g["ff"] = 2 * (math.hypot(a1, b1)) ** 2 / lam
    g["box_x"] = g["a1"] / 2 + g["clear"]
    g["box_y"] = g["b1"] / 2 + g["clear"]
    g["box_zmin"] = -(g["L_guide"] + g["clear"])
    g["box_zmax"] = g["pe"] + g["clear"]
    g["z_probe"] = -(g["L_guide"] - g["back"])
    return g


G = geometry()


def section_drawing():
    """E-plane cross-section, to scale, with the model's coordinate origin on it."""
    d = Drawing(BODY_W, 172)
    sc = 0.46                                    # mm -> pt
    ox, oy = 150, 88                             # origin (throat centre) on the page
    zb, zt, zap = -G["L_guide"], 0.0, G["pe"]
    hb, hap = G["b"] / 2, G["b1"] / 2

    def X(z): return ox + z * sc
    def Y(v): return oy + v * sc

    wall = colors.HexColor("#8a3b1e")
    # guide walls (E-plane: the b dimension)
    for s_ in (+1, -1):
        d.add(Line(X(zb), Y(s_ * hb), X(zt), Y(s_ * hb), strokeColor=wall, strokeWidth=2.4))
        d.add(Line(X(zt), Y(s_ * hb), X(zap), Y(s_ * hap), strokeColor=wall, strokeWidth=2.4))
    d.add(Line(X(zb), Y(-hb), X(zb), Y(hb), strokeColor=wall, strokeWidth=2.4))   # back short
    # interior air
    d.add(Polygon([X(zb), Y(-hb), X(zt), Y(-hb), X(zap), Y(-hap), X(zap), Y(hap),
                   X(zt), Y(hb), X(zb), Y(hb)],
                  fillColor=colors.HexColor("#eef2f6"), strokeColor=None))
    for s_ in (+1, -1):
        d.add(Line(X(zb), Y(s_ * hb), X(zt), Y(s_ * hb), strokeColor=wall, strokeWidth=2.4))
        d.add(Line(X(zt), Y(s_ * hb), X(zap), Y(s_ * hap), strokeColor=wall, strokeWidth=2.4))
    d.add(Line(X(zb), Y(-hb), X(zb), Y(hb), strokeColor=wall, strokeWidth=2.4))
    # axis
    d.add(Line(X(zb) - 14, Y(0), X(zap) + 22, Y(0), strokeColor=colors.HexColor("#9aa0a8"),
               strokeWidth=0.5, strokeDashArray=[3, 3]))
    # probe
    zp = G["z_probe"]
    d.add(Line(X(zp), Y(-hb), X(zp), Y(-hb + G["probe"]), strokeColor=INK, strokeWidth=3))
    d.add(Line(X(zp), Y(-hb), X(zp), Y(-hb - 13), strokeColor=INK, strokeWidth=3))
    d.add(Rect(X(zp) - 4.5, Y(-hb) - 15, 9, 9, fillColor=colors.HexColor("#d4b25a"),
               strokeColor=INK, strokeWidth=0.5))
    # origin marker
    d.add(Line(X(0), Y(0) - 7, X(0), Y(0) + 7, strokeColor=ACC, strokeWidth=1.2))
    d.add(String(X(0) + 3, Y(0) + 9, "z = 0  (throat)", fontName="DJ", fontSize=6.2, fillColor=ACC))
    d.add(String(X(zap) + 5, Y(0) - 2, "+z", fontName="DJ", fontSize=6.5, fillColor=MUT))

    def dim(z0, z1, y, txt):
        d.add(Line(X(z0), Y(y), X(z1), Y(y), strokeColor=MUT, strokeWidth=0.5))
        for z in (z0, z1):
            d.add(Line(X(z), Y(y) - 3, X(z), Y(y) + 3, strokeColor=MUT, strokeWidth=0.5))
        d.add(String((X(z0) + X(z1)) / 2, Y(y) + 4, txt, fontName="DJ", fontSize=6.2,
                     fillColor=MUT, textAnchor="middle"))

    dim(zb, zt, hap + 26, f'L_guide = {G["L_guide"]:.0f}')
    dim(zt, zap, hap + 26, f'p_e = {G["pe"]:.1f}')
    dim(zb, zp, -hap - 20, f'backshort = {G["back"]:.1f}')
    # aperture height
    d.add(Line(X(zap) + 14, Y(-hap), X(zap) + 14, Y(hap), strokeColor=MUT, strokeWidth=0.5))
    d.add(String(X(zap) + 17, Y(0) - 10, f'b1', fontName="DJ", fontSize=6.2, fillColor=MUT))
    d.add(String(X(zap) + 17, Y(0) - 18, f'{G["b1"]:.1f}', fontName="DJ", fontSize=6.2, fillColor=MUT))
    d.add(String(X(zb) - 12, Y(0) - 3, "short", fontName="DJ", fontSize=6.2, fillColor=MUT,
                 textAnchor="end"))
    d.add(String(X(zp), Y(-hb) - 24, f'probe {G["probe"]:.0f} mm', fontName="DJ", fontSize=6.2,
                 fillColor=INK, textAnchor="middle"))
    d.add(String(2, 158, "E-plane section (the y–z plane, phi = 90°). Drawn to scale; "
                         "all dimensions mm.", fontName="DJ", fontSize=7, fillColor=MUT))
    return d


def story():
    g = G
    s = []
    s += title_block(
        "Modelling this horn in HFSS",
        "Optimum pyramidal horn, WR-340 feed, 2.45 GHz · every dimension generated from antenna/horn.py",
        "A procedure, not a tutorial on the software. It builds the exact antenna this repo "
        "specifies, in the order that gets you a trustworthy S<sub>11</sub> and pattern with "
        "the fewest re-solves, and it ends by checking the solver against closed-form theory — "
        "because a converged answer and a correct answer are different things.",
        [["solver", "Ansys HFSS (Electronics Desktop). Menu paths are 2023 R2; older versions differ slightly"],
         ["design", f'optimum pyramidal horn, {g["gain"]:.1f} dBi, WR-340 feed'],
         ["feed", "coax probe, λ<sub>g</sub>/4 backshort, SMA"],
         ["source", "antenna/horn.py — re-run make_hfss.py if that changes"]])

    # ------------------------------------------------------------------
    s.append(P("0 · The numbers to beat", "h2"))
    s.append(P(
        "Write these down before you open HFSS. They come from closed-form optimum-horn "
        "theory, they are independent of the solver, and at the end you will compare the "
        "simulation against them. If the two disagree by more than the tolerance in the right "
        "column, <b>the model is wrong, not the theory</b> — this geometry is well inside the "
        "range where the analytic result is reliable."))
    s.append(table(
        [["quantity", "closed form", "accept if HFSS gives"],
         ["Realized gain", f'<b>{g["gain"]:.1f} dBi</b>', f'{g["gain"]-1.5:.1f} – {g["gain"]+1.5:.1f} dBi'],
         ["Aperture bound, 4πA/λ²", f'{g["bound"]:.1f} dBi', "<b>never exceeded</b> — if it is, stop and find the error"],
         ["HPBW, E-plane (φ = 90°)", f'{g["hp_e"]:.1f}°', f'{g["hp_e"]-4:.0f}° – {g["hp_e"]+4:.0f}°'],
         ["HPBW, H-plane (φ = 0°)", f'{g["hp_h"]:.1f}°', f'{g["hp_h"]-4:.0f}° – {g["hp_h"]+4:.0f}°'],
         ["First sidelobe", "−13 dB (E), lower in H", "≤ −12 dB"],
         ["S<sub>11</sub>, 2.400–2.484 GHz", "set by the probe, not the flare", "≤ −10 dB after tuning"],
         ["TE<sub>10</sub> cutoff", f'{g["fc"]:.3f} GHz', "port mode 1 must be propagating"],
         ["Next mode, TE<sub>20</sub>", f'{g["fc2"]:.3f} GHz', "must stay cut off — check port modes"]],
        [30, 30, 40], mono_cols=(1,)))

    s.append(P("Coordinates used throughout", "h3"))
    s.append(bullets([
        "<b>+z</b> is boresight, out of the mouth. <b>z = 0 at the throat</b>, where the flare "
        "starts — so the back short is at negative z and the aperture at positive z.",
        f'<b>x</b> along the broad wall a ({g["a"]:.1f} mm) → this is the <b>H-plane</b>, φ = 0°.',
        f'<b>y</b> along the narrow wall b ({g["b"]:.1f} mm) → E-field direction, the '
        f'<b>E-plane</b>, φ = 90°.',
        "The build rotates all three horns 90° on the frame so b<sub>1</sub> ends up "
        "horizontal. That is a mounting choice and changes nothing in this model — simulate "
        "it in the natural orientation and rotate the result in your head.",
    ]))
    s.append(section_drawing())

    s.append(PageBreak())

    # ------------------------------------------------------------------
    s.append(P("Part I — building the model", "h2"))

    s.append(step(1, "New design, and get the units right first"))
    s.append(bullets([
        "<b>Project → Insert HFSS Design.</b>",
        "<b>HFSS → Solution Type → Driven Modal.</b> Modal is the right choice for a single "
        "coax or waveguide feed; Driven Terminal is for multi-conductor lines where you want "
        "voltages per conductor.",
        "<b>Modeler → Units → mm.</b> Do this <i>before</i> drawing anything. Changing units "
        "later rescales nothing and silently reinterprets every number you have typed.",
    ]))

    s.append(step(2, "Enter the geometry as variables, not as numbers"))
    s.append(P(
        "Type a name such as <tt>a1</tt> into any dimension box and HFSS offers to create it. "
        "Do this for all of them now: probe length and backshort are the two you will sweep, "
        "and a model built from literals cannot be swept at all."))
    s.append(table(
        [["variable", "value", "what it is"],
         ["<tt>freq</tt>", "2.45 GHz", "design frequency"],
         ["<tt>a</tt>", f'{g["a"]:.2f} mm', "guide broad wall, WR-340"],
         ["<tt>b</tt>", f'{g["b"]:.2f} mm', "guide narrow wall"],
         ["<tt>a1</tt>", f'{g["a1"]:.2f} mm', "aperture, H-plane"],
         ["<tt>b1</tt>", f'{g["b1"]:.2f} mm', "aperture, E-plane"],
         ["<tt>pe</tt>", f'{g["pe"]:.2f} mm', "axial flare length (p<sub>e</sub> = p<sub>h</sub>)"],
         ["<tt>Lg</tt>", f'{g["L_guide"]:.0f} mm', "guide section length behind the throat"],
         ["<tt>bshort</tt>", f'{g["back"]:.2f} mm', "probe to back wall = λ<sub>g</sub>/4 — <b>sweep this</b>"],
         ["<tt>plen</tt>", f'{g["probe"]:.0f} mm', "probe into the guide — <b>sweep this</b>"],
         ["<tt>dpin</tt>", f'{g["d_pin"]:.4f} mm', "probe rod, 1/16 inch brass"],
         ["<tt>ddiel</tt>", f'{g["d_diel"]:.3f} mm', "PTFE outside diameter, see step 5"],
         ["<tt>clear</tt>", f'{g["clear"]:.0f} mm', f'air-box clearance (λ/4 = {g["quarter"]:.1f} mm minimum)']],
        [22, 24, 54], mono_cols=(1,)))

    s.append(step(3, "The guide, the flare, and why you draw the air"))
    s.append(callout(
        "Model the air, not the copper",
        "What radiates is the field in the volume <i>inside</i> the horn. Drawing 0.5 mm copper "
        "sheet and asking HFSS to mesh it wastes an enormous number of tetrahedra resolving "
        "metal that carries no field to speak of. Draw the interior air, then put a perfectly "
        "conducting <b>sheet</b> where each wall goes. Electrically that is exactly what a "
        "soldered copper horn is at 2.45 GHz, and it solves in a fraction of the time."))
    s.append(bullets([
        "<b>Draw → Box</b> for the guide: position <tt>(-a/2, -b/2, -Lg)</tt>, size "
        "<tt>(a, b, Lg)</tt>. Name it <tt>guide_air</tt>.",
        "<b>Draw → Rectangle</b> at the throat, z = 0, spanning <tt>a × b</tt> centred on the "
        "axis. Draw a second rectangle at z = <tt>pe</tt> spanning <tt>a1 × b1</tt>.",
        "Select both rectangles, then <b>Modeler → Surface → Connect</b>. That lofts a solid "
        "between the two profiles — this is the flare. Name it <tt>flare_air</tt>.",
        "Select both solids → <b>Modeler → Boolean → Unite</b>. Unite keeps the name of the "
        "first object selected, so <b>rename the result <tt>horn_air</tt></b> — the rest of "
        "this procedure calls it that. Assign material <b>vacuum</b>.",
    ]))
    s.append(P(
        f'Sanity check the loft before going on: the flare half-angles should come out '
        f'{math.degrees(math.atan((g["b1"]/2-g["b"]/2)/g["pe"])):.1f}° in the E-plane and '
        f'{math.degrees(math.atan((g["a1"]/2-g["a"]/2)/g["pe"])):.1f}° in the H-plane. If '
        'Connect refuses, or produces a twisted solid, the two rectangles are not coaxial or '
        'not parallel.', "small"))

    s.append(step(4, "Turn the walls into perfect-E sheets"))
    s.append(bullets([
        "Select <tt>horn_air</tt>, switch to <b>face selection</b>, and pick every outside face "
        "<b>except the aperture</b> at z = <tt>pe</tt>. That is: four flare panels, four guide "
        "walls, and the back short.",
        "<b>Modeler → Surface → Create Object From Face.</b> You now have sheet objects lying "
        "exactly on those walls.",
        "<b>Delete <tt>horn_air</tt>.</b> It was scaffolding. The air box in step 7 will fill "
        "that volume, and the sheets stay behind as the metal.",
        "Select all the new sheets → <b>right-click → Assign Boundary → Perfect E</b>. Name it "
        "<tt>walls</tt>.",
    ]))
    s.append(P(
        "<b>Second pass, later:</b> to see conductor loss, assign <b>Finite Conductivity</b> "
        "with copper (5.8×10<sup>7</sup> S/m) instead of Perfect E. Expect it to cost a few "
        "hundredths of a dB at this frequency — worth knowing, not worth waiting for on the "
        "first solve.", "small"))

    s.append(step(5, "The coax feed — the part that decides your S11"))
    s.append(P(
        f'The real probe is a 1/16 inch brass rod, {g["d_pin"]:.3f} mm across. If you model the '
        f'rod at that diameter you must size the PTFE around it to keep the stub at 50 Ω, or '
        f'you have built an impedance step into your own model and will spend an evening '
        f'tuning it out:'))
    s.append(P("Z<sub>0</sub> = (138/√ε<sub>r</sub>)·log<sub>10</sub>(D/d) = 50 Ω  with  "
               f'ε<sub>r</sub> = 2.1  →  D/d = 3.350  →  <b>D = {g["d_diel"]:.3f} mm</b>', "eq"))
    s.append(bullets([
        f'<b>Pin.</b> Cylinder, radius <tt>dpin/2</tt>, axis along <b>+y</b>, from '
        f'<tt>y = -b/2 - 10</tt> (a 10 mm stub outside the wall, where the port goes) up to '
        f'<tt>y = -b/2 + plen</tt>. Centre it at <tt>x = 0</tt>, <tt>z = -Lg + bshort</tt>. '
        f'Material: <b>pec</b>. Name <tt>pin</tt>.',
        f'<b>Dielectric.</b> Cylinder, radius <tt>ddiel/2</tt>, same axis, from '
        f'<tt>y = -b/2 - 10</tt> to <tt>y = -b/2</tt> (it stops at the wall). Material '
        f'<b>Teflon (ε<sub>r</sub> 2.1)</b>. Name <tt>coax</tt>.',
        "<b>Boolean → Subtract</b>: <tt>coax</tt> minus <tt>pin</tt>, <b>with “clone tool "
        "objects” ticked</b> so the pin survives.",
        "Assign <b>Perfect E</b> to the outer curved face of <tt>coax</tt> — that is the shield.",
        "The wall sheet the probe passes through needs a clearance hole: subtract <tt>coax</tt> "
        "from that sheet, or draw the sheet with the hole already in it. A probe shorted to the "
        "wall gives a beautiful and completely fictional S<sub>11</sub>.",
    ]))
    s.append(P(
        f'Geometry check: the probe tip sits at y = {-g["b"]/2 + g["probe"]:.1f} mm and the far '
        f'wall is at y = {g["b"]/2:.1f} mm, so there is '
        f'{g["b"]/2 - (-g["b"]/2 + g["probe"]):.1f} mm of clearance. It must stay positive at '
        f'every value of <tt>plen</tt> you sweep.', "small"))

    s.append(step(6, "Wave port on the end of the stub"))
    s.append(bullets([
        "Select the <b>flat annular end face</b> of <tt>coax</tt> at <tt>y = -b/2 - 10</tt>.",
        "<b>Assign Excitation → Wave Port.</b> Modes: <b>1</b>. Add an <b>integration line</b> "
        "from the pin surface radially out to the shield — this fixes the sign and the "
        "impedance reference.",
        "Leave <b>Renormalize to 50 Ω</b> on.",
    ]))
    s.append(callout(
        "The port must enclose the coax and nothing else",
        "A wave port on a coax should be exactly the dielectric annulus. If you accidentally "
        "draw it larger — onto the air box, say — it stops being a TEM coax port and starts "
        "supporting hollow-waveguide modes, and your S<sub>11</sub> becomes meaningless. After "
        "the first solve, open <b>HFSS → Results → Solution Data → Port Field Display</b> and "
        "look at mode 1: it must be the radial TEM pattern of a coax."))

    s.append(step(7, "Air box and radiation boundary"))
    s.append(P(
        f'<b>Draw → Box</b> enclosing everything, material <b>vacuum</b>. With '
        f'<tt>clear = {g["clear"]:.0f} mm</tt> that is roughly:'))
    s.append(table(
        [["axis", "from", "to", "why"],
         ["x", f'{-g["box_x"]:.0f} mm', f'{g["box_x"]:.0f} mm', "aperture half-width + clearance"],
         ["y", f'{-g["box_y"]:.0f} mm', f'{g["box_y"]:.0f} mm', "includes room for the coax stub below"],
         ["z", f'{g["box_zmin"]:.0f} mm', f'{g["box_zmax"]:.0f} mm', "behind the short, and in front of the mouth"]],
        [12, 22, 22, 44], mono_cols=(1, 2)))
    s.append(bullets([
        "<b>Subtract</b> <tt>coax</tt> and <tt>pin</tt> from the air box, cloning the tools, so "
        "no two solids overlap.",
        "Select all six outer faces → <b>Assign Boundary → Radiation</b>.",
    ]))
    s.append(P(
        f'<b>λ/4 at 2.45 GHz is {g["quarter"]:.1f} mm</b>, and that is the minimum standoff for '
        f'a radiation boundary — closer and it reflects, which moves both the pattern and '
        f'S<sub>11</sub>. {g["clear"]:.0f} mm gives some margin. If the model is too big to '
        f'solve, the right fix is a <b>PML</b> (which works down to about λ/8), not a smaller '
        f'radiation box.', "small"))

    s.append(PageBreak())

    # ------------------------------------------------------------------
    s.append(P("Part II — solving and checking", "h2"))

    s.append(step(8, "Solution setup and sweep"))
    s.append(table(
        [["setting", "value", "why"],
         ["Solution Frequency", "2.45 GHz", "the adaptive mesh is built at this one frequency"],
         ["Maximum Number of Passes", "20", "a ceiling, not a target — it should converge before this"],
         ["Maximum Delta S", "0.02", "0.02 is the usual working value; tighten to 0.01 for the final run"],
         ["Sweep type", "Interpolating", "far fewer solves than Discrete for a smooth S-curve"],
         ["Sweep range", "2.20 – 2.70 GHz", "wide enough to see the resonance move while tuning"],
         ["Points", "501", "interpolating decides its own solve points; this is the output grid"]],
        [28, 22, 50], mono_cols=(1,)))
    s.append(P(
        "Sweeping well below the band matters while you tune: a probe that is mistuned shows "
        "up as a dip at 2.2 or 2.7 GHz, and if you only plot 2.4–2.484 you see a flat, "
        "featureless −3 dB and no clue which way to move.", "small"))

    s.append(step(9, "Far-field setup"))
    s.append(bullets([
        "<b>Radiation → Insert Far Field Setup → Infinite Sphere.</b>",
        "<b>3D:</b> θ 0→180 step 2°, φ 0→360 step 2°. Name it <tt>ff_3d</tt>.",
        "<b>H-plane cut:</b> φ = 0 fixed, θ −180→180 step 1°. Name it <tt>cut_H</tt>.",
        "<b>E-plane cut:</b> φ = 90 fixed, θ −180→180 step 1°. Name it <tt>cut_E</tt>.",
    ]))
    s.append(P(
        "Getting the two planes the wrong way round is the most common reporting error in horn "
        "work, and it is easy to catch: <b>the E-plane is the narrower beam</b> here "
        f'({g["hp_e"]:.1f}° against {g["hp_h"]:.1f}°), because the H-plane carries the cosine '
        "taper of the TE<sub>10</sub> mode. If your φ = 0 cut is the narrow one, your guide is "
        "rotated 90° from the convention on the previous page.", "small"))

    s.append(step(10, "Analyse, then check the solver before you believe it"))
    s.append(P("<b>HFSS → Analyze All.</b> Then, in this order:"))
    s.append(table(
        [["#", "check", "where", "what you want"],
         ["1", "Convergence", "Results → Solution Data → Convergence", "ΔS below target, and the last two or three passes <b>changing very little</b> — one pass sneaking under the threshold is luck, not convergence"],
         ["2", "Port mode", "Solution Data → Port Field Display", "Mode 1 is coax TEM. If it looks like a waveguide mode, the port is wrong"],
         ["3", "Mesh count", "Solution Data → Profile", "Tens to a couple of hundred thousand tetrahedra. Millions means something is over-refined — usually a thin solid"],
         ["4", "Gain vs the bound", "Far field → Gain Total, dB", f'Must be under <b>{g["bound"]:.1f} dBi</b>. Above it, the model is wrong'],
         ["5", "Then the numbers", "the table on page 1", "Gain, both beamwidths, sidelobes, S<sub>11</sub>"]],
        [6, 24, 32, 38]))

    s.append(step(11, "Tune the two knobs"))
    s.append(P(
        "The flare sets the pattern and the gain, and it is already optimal — do not touch it. "
        "The <b>match</b> is set entirely by the feed, and there are exactly two variables:"))
    s.append(bullets([
        "<b><tt>plen</tt></b> (probe depth) — sets coupling, and mostly moves the real part of "
        "Z<sub>in</sub>.",
        "<b><tt>bshort</tt></b> (probe to back wall) — mostly trims the reactance.",
    ]))
    s.append(P(
        f'<b>Optimetrics → Add → Parametric.</b> Sweep <tt>plen</tt> from 24 to 34 mm in 1 mm '
        f'steps and <tt>bshort</tt> from {g["back"]-6:.0f} to {g["back"]+6:.0f} mm in 2 mm '
        f'steps, and plot a family of S<sub>11</sub> curves. You are looking for the pair that '
        f'puts the dip in the middle of 2400–2483.5 MHz and keeps it below −10 dB across the '
        f'whole span. Two variables and about sixty solves is an overnight job, and it is the '
        f'only part of this that genuinely needs the solver.'))
    s.append(callout(
        "What the simulation is really buying you",
        "The gain and the pattern you could have had from horn.py in a millisecond, and the "
        "agreement between them is a check on the <i>model</i>, not a discovery. The probe "
        "match is the part with no useful closed form — and it is also the one thing the build "
        "notes say you can tune on the bench against detection SNR without a VNA. Simulating "
        "it first means you arrive at the bench already close."))

    s.append(step(12, "The second model: TX-to-RX isolation"))
    s.append(P(
        "A separate project, and the one antenna question this radar has that a single horn "
        "cannot answer. The build mounts TX 290 mm above the RX row and needs "
        "<b>S<sub>21</sub> ≤ −35 dB</b>; the leakage that gets through is ~46 dB stronger than "
        "the drone echo and sets the whole dynamic-range problem downstream."))
    s.append(bullets([
        "Duplicate the horn (<b>Edit → Duplicate → Along Line</b>), offset <b>290 mm along "
        "y</b> — the E-plane direction, which is how the frame stacks them.",
        "Two wave ports, one per horn. Grow the air box so it still clears λ/4 from "
        "<b>both</b> apertures.",
        "Plot <b>S<sub>21</sub></b> across the band. Expect a large model and a long solve — "
        "this is the one worth running overnight.",
        "Worth a second run with a conducting sheet between the two horns, which is what the "
        "foil-on-cardboard trick in the build notes is doing.",
    ]))

    s.append(P("Record what you get", "h2"))
    s.append(P(
        "Fill this in from the solved model and keep it with the build log — it is what you "
        "will compare the VNA against if you ever borrow one, and what tells you whether a "
        "disappointing bench result is the horn or the rest of the chain."))
    s.append(table(
        [["quantity", "closed form", "HFSS", "measured"],
         ["Realized gain, dBi", f'{g["gain"]:.1f}', "", ""],
         ["HPBW E-plane, °", f'{g["hp_e"]:.1f}', "", ""],
         ["HPBW H-plane, °", f'{g["hp_h"]:.1f}', "", ""],
         ["First sidelobe, dB", "−13", "", ""],
         ["S<sub>11</sub> at 2.400 GHz", "—", "", ""],
         ["S<sub>11</sub> at 2.442 GHz", "—", "", ""],
         ["S<sub>11</sub> at 2.484 GHz", "—", "", ""],
         ["Best plen / bshort, mm", f'{g["probe"]:.0f} / {g["back"]:.1f}', "", ""],
         ["TX–RX S<sub>21</sub> at 290 mm, dB", "target ≤ −35", "", ""]],
        [34, 20, 23, 23], mono_cols=(1,)))
    s.append(note_lines(6))
    return s


def main():
    doc = NoteDoc(OUT, "Modelling this horn in HFSS",
                  "optimum pyramidal horn, WR-340, 2.45 GHz",
                  "radar-dev · antenna/hfss")
    doc.build(story())
    print(f"wrote {OUT.name}")


if __name__ == "__main__":
    main()
