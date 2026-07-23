# Experimental directions — through-wall sensing & radar simulation

Two ideas on the table:

1. A through-the-wall sensing (TTWS) system, à la the military "see people
   through walls" radars, with an eye toward a consumer product.
2. Intuitive radar / antenna **simulation software**.

This doc is an honest feasibility pass and a phased plan for each. Short
version of the recommendation up front:

- **Simulation software is the one to build first.** It's legal, unencumbered,
  genuinely useful, sellable, and it compounds with everything else here
  (you design the TTWS array *in your own tool*). Start here.
- **Through-wall is real and buildable — but not the product you first
  described.** Two facts reshape it: (a) millimeter wave does *not* go through
  walls; the physics wants the opposite end of the spectrum, and (b) in the
  US, through-wall *imaging* is legally restricted to law enforcement / fire /
  rescue. The viable consumer product in this space is **sense-through-wall
  presence & vital-signs** (breathing, occupancy, fall detection), which is a
  different regulatory animal and a real market. Build that, not a covert
  "see the person" imager.

---

## Part A — Through-wall sensing: what's actually true

### A.1 Two physics corrections that change the design

**mmWave doesn't penetrate walls.** This is the big one. Higher frequency =
shorter wavelength = *finer resolution but worse penetration*. Millimeter
wave (24–81 GHz) is strongly absorbed by drywall, brick, and especially
concrete; it's the wrong tool for going *through* a wall. Through-wall
systems deliberately trade resolution for penetration and work at **low
frequencies — UHF up through L/S-band (roughly 0.5–4 GHz), as ultra-wideband
(UWB) pulses.** Military ground-penetrating and through-wall radars sit down
there for exactly this reason. So the instinct "TTWS with millimeter wave
going through walls" is self-contradictory; the honest design uses UWB in
the low-GHz range. (mmWave is fantastic for *in-room* presence and micro-
motion sensing where there's no wall in the path — different product.)

**Resolution is set by bandwidth, penetration by center frequency, and you
can't max both.** Range resolution ΔR = c/(2·B). To resolve two people 30 cm
apart you need ~500 MHz of bandwidth. To punch through a 20 cm concrete wall
you want a low center frequency. UWB (wide B at a low center) is the
compromise the whole field converged on.

Sources: [penetration vs resolution](https://linpowave.com/blog/through-wall-detection-mmwave-radar),
[UWB through-wall radar](https://link.springer.com/content/pdf/10.1007/978-0-387-74159-8_23.pdf).

### A.2 The regulatory wall (this is the real gate, not the tech)

In the US, the FCC regulates UWB under 47 CFR Part 15 Subpart F, and it draws
a hard line around **"imaging systems"**:

- **Through-wall *imaging* systems** (§ 15.511) may only be operated by "law
  enforcement, emergency rescue or firefighting organizations that are under
  the authority of a local or state government," whose operators are eligible
  for licensing under Part 90, and use requires **coordination with the FCC**
  before operation.
  ([47 CFR 15.511](https://www.ecfr.gov/current/title-47/chapter-I/subchapter-A/part-15/subpart-F))
- **GPR / wall-imaging systems** (§ 15.509) are likewise limited to "law
  enforcement, fire fighting, emergency rescue, scientific research,
  commercial mining, or construction."
  ([47 CFR 15.509](https://www.ecfr.gov/current/title-47/chapter-I/subchapter-A/part-15/subpart-F/section-15.509))

Translation: **a general-consumer "see people through the wall" imager is not
a legal US product**, regardless of how cheaply you can build it. This isn't
a moral footnote — it's the business reality that kills that specific product.
There's also a constitutional overlay (*Kyllo v. United States*, 2001: using
sense-enhancing tech to see inside a home is a Fourth Amendment "search"),
and the well-documented controversy over police "Range-R" devices used
without warrants. And higher-capability radar can attract export-control
(EAR/ITAR) attention.

**None of this blocks the legal path** — it just tells you which product to
build. Presence/vital-sign sensors that don't form an *image* of the interior
are regulated far more permissively (ordinary UWB sensing, Part 15), which is
exactly why commercial UWB presence sensors already ship.

### A.3 The capability tiers (so "consumer product" means something concrete)

| Tier | What it does | Freq / hardware | Cost | Legal as consumer product? |
|------|-------------|-----------------|------|----------------------------|
| **0. In-room presence** | detects people & micro-motion in the same room | 60 GHz mmWave (TI IWR6843, Infineon BGT60) | $10–30 chip | ✅ yes — already common in smart-home |
| **1. Sense-*through*-wall presence/vitals** | "someone is in the next room, breathing rate, fell down" — no image | UWB 1–10 GHz single-channel (Novelda X4/X7, TI IWR + processing) | $50–300 | ✅ yes (not "imaging") — **this is the consumer product** |
| **2. Through-wall *localization*** | 1–2 blobs behind a wall, position only | UWB with a small Rx array | $500–2k, DIY-hard | ⚠️ edges toward "imaging" — regulatory gray zone |
| **3. Through-wall *imaging*** | skeletal poses / room map through concrete (the Camero Xaver / military tier) | UWB antenna array + SAR + big compute | $10k–50k+ | ❌ US: law-enforcement/fire/rescue only |

Your exciting mental image is Tier 3 (Camero-Tech Xaver, the MIT CSAIL
"RF-Pose" through-wall pose estimation research). It's real, but it's the
$10k+ export-sensitive, LE-only tier. **Tier 1 is where an actual product
lives**, and it's a good one: elder-care fall & breathing monitoring
(privacy-friendly precisely *because* it's not a camera), occupancy for HVAC/
security, sleep/vitals. That reframes "military → police → criminals" into
"eldercare → building automation → search-and-rescue," which is both the
legal market and the fundable one.

### A.4 A phased plan for the TTWS thread

- **T0 — Literature & parts (1–2 wk).** Read the UWB TTWS survey papers;
  order one UWB sensing module. Best hobbyist starting points: a **Novelda
  X4M200/X4M300** (respiration/presence dev kit, sensing built in) or a **TI
  IWR6843 / AWR1642** mmWave EVM for the in-room tier. Both have SDKs.
- **T1 — Reproduce Tier 0/1 (4–8 wk).** Get presence + breathing-rate
  detection working in one room, then aim the UWB unit through a single
  interior drywall wall and characterize what survives. Deliverable: a
  measured penetration/SNR table for your walls — this is the honest
  feasibility datum everything else hangs on.
- **T2 — Signal processing (8–12 wk).** Clutter removal (the wall reflection
  dwarfs the person — same direct-path problem as the drone radar, ~40 dB),
  background subtraction, micro-Doppler for breathing, MTI for motion. This is
  the real IP and it's all software.
- **T3 — Decide the product.** If Tier 1 vitals/fall detection is solid,
  that's the consumer path (with a clear privacy story and, if it's a medical
  claim, an FDA conversation). Localization (Tier 2) is a research demo, not a
  first product. Keep Tier 3 firmly in the "not a US consumer product" column.

**Guardrail:** design this as safety/care/rescue sensing, not covert
surveillance. That choice isn't just ethics — it's the difference between a
product you can legally sell and ship and one you can't.

---

## Part B — Radar / antenna simulation software (build this first)

This is the strong idea: legal, no export/FCC baggage, useful to *you*
immediately, and a real market gap between "toy" and "$40k HFSS license."

### B.1 What already exists (stand on these, don't reinvent)

| Layer | Mature tools to build on |
|-------|--------------------------|
| EM field solver (antennas) | **openEMS** (open-source FDTD), **NEC2/necpp** (wire antennas), **Meep** (FDTD) |
| RF circuit / network | **scikit-rf** (S-parameters, matching, Smith charts) |
| Phased array / radar system | **MATLAB Phased Array Toolbox** (the paid reference), **PyEHT / pytorch-based** DSP |
| Radar signal chain | build in NumPy/SciPy — you already have the solver muscle in this repo |

The gap isn't the math — openEMS already does rigorous FDTD. The gap is
**intuitiveness**: those tools have brutal learning curves. A tool that lets
you *draw* an antenna or lay out an array and *see* the pattern update, with
sane defaults, is genuinely wanted (education, ham radio, RF prosumers,
students).

### B.2 Scope it as three separable products, not one boil-the-ocean app

1. **Radar system simulator (start here — weeks, not months).** No Maxwell's
   equations. Model the *signal chain*: waveform (pulse/FMCW/chirp) →
   propagation (range, Doppler, path loss, RCS) → antenna pattern (as a gain
   function) → receiver → range-Doppler map / detection. This is analytic and
   fast, it directly reuses this repo's Python + web-GUI stack, and it's the
   part that teaches radar intuition. **This is the natural next build in
   `radar-dev`.**
2. **Antenna pattern designer (months).** Wrap NEC2/openEMS behind a friendly
   UI: place elements, sweep geometry, live-render the far-field pattern and
   array factor. Hard part is UX + meshing, not physics (solver exists).
3. **Full-wave EM playground (long-term).** Real FDTD via openEMS/Meep for
   near-field, S-params, coupling. This is where it gets "a lot of physics and
   math," so it's last.

### B.3 Concrete first milestone (fits this repo)

A **web-based radar system simulator** reusing the `server.py` + canvas GUI
pattern you already have:

- Inputs: waveform type & bandwidth, PRF, carrier, Tx power, antenna gain/
  beamwidth, and a scene of targets (range, velocity, RCS).
- Compute (pure NumPy): radar range equation for SNR, range resolution
  c/2B, Doppler shifts, and a synthesized **range-Doppler map**.
- Output: live range-Doppler heatmap (the `dataviz` sequential ramp),
  detections vs. the noise floor, and the classic tradeoff sliders
  (bandwidth↔resolution, PRF↔unambiguous range/velocity) so the *intuition*
  is visible. An **array-factor** view for N-element spacing/steering is a
  natural second tab.
- This is buildable on the stack already in `ground_station/` and turns the
  abstract equations in `docs/feasibility.md` into something you can play
  with — genuinely the fastest path to "that's pretty cool."

### B.4 Antenna-design phase (after the system sim lands)

- Wrap **openEMS** (Python interface) for full-wave, or **necpp** for quick
  wire-antenna work.
- UI: draw/parameterize geometry → run solver in a worker → render far-field
  gain (3D lobe + 2D cuts) and VSWR/S11 via scikit-rf.
- Validate against known closed-form cases (half-wave dipole pattern,
  2-element array factor) before trusting arbitrary geometry — same
  "checkpoint" discipline as the drone setup plan.

---

## Recommended sequencing

1. **Now:** build the **radar system simulator** (Part B.3). Fast, legal,
   compounding, reuses your stack, and makes the physics tangible.
2. **Parallel, low-cost:** order one UWB sensing dev kit and run the **T1
   through-wall characterization** (Part A.4) — one measured SNR table tells
   you whether the sensing product is worth pursuing, for ~$100–300.
3. **Then:** grow the simulator toward antenna/array design (Part B.4), and
   if the UWB numbers are good, develop the **Tier-1 presence/vitals** sensor
   as the consumer product — with the care/rescue framing that keeps it legal
   and fundable.
4. **Not on the roadmap as a consumer product:** through-wall *imaging*
   (Tier 3). Fascinating, but LE/fire/rescue-only in the US. Revisit only if
   you're building explicitly for that regulated market.

The through-wall imager is the cool poster; the simulator and the Tier-1
sensor are the things you can actually build, ship, and sell.
