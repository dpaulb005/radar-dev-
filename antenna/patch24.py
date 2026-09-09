#!/usr/bin/env python3
"""patch24.py — the 24 GHz antenna and the board it lives on.

At 2.4 GHz the antenna is a horn you fold from copper sheet (`horn.py`).
At 24 GHz a 13.4 dBi horn is 27 x 20 mm, too small to fold and too small to
tune with a file — so the antenna becomes a printed patch array. That is not a
smaller design exercise, it is a bigger one: you choose the substrate, the
element, the feed, the spacing, the impedance match and the interferometer
baseline, and a board house prints exactly what you drew.

Everything here comes from the standard cavity/two-slot model
(Balanis, *Antenna Theory*, ch. 14) and from the project's own radar equation
in `ground_station/fmcw_sim.py`. Nothing is quoted from a datasheet plot.

    W    = (c/2f) sqrt(2/(er+1))                      patch width
    eeff = (er+1)/2 + (er-1)/2 (1+12h/W)^-1/2         effective permittivity
    dL   = 0.412 h (eeff+0.3)(W/h+0.264)
                 / ((eeff-0.258)(W/h+0.8))            fringing extension
    L    = c/(2 f sqrt(eeff)) - 2 dL                  resonant length

The architecture it designs, and why:

    one board, three printed columns, no connectors and no cable.
      TX      : 4 patches, series-fed
      RX1 RX2 : 4 patches each, series-fed, centres lambda/2 apart

    Stacking vertically narrows ELEVATION (which costs nothing indoors) and
    leaves AZIMUTH as the single-patch pattern (~80 deg, which is what you
    want to search). The lambda/2 horizontal spacing then makes the
    interferometer unambiguous across that entire pattern, instead of the
    +/-18.4 deg the 193 mm horn baseline gives at 2.4 GHz.

Usage:
    python3 patch24.py               the design
    python3 patch24.py --sweep       the FR-4 prototype panel's dimension sweep
    python3 patch24.py --selftest    assertions; exit status is the verdict
"""

import argparse
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "ground_station"))

C = 2.99792458e8
MU0 = 4e-7 * math.pi
SIGMA_CU = 5.8e7           # copper conductivity, S/m
ROUGHNESS = 1.3            # Hammerstad roughness multiplier on conductor loss

F0 = 24.125e9              # centre of the 24.00-24.25 GHz ISM band
BAND = (24.00e9, 24.25e9)
N_ELEM = 4                 # patches per column
TX_OFFSET_LAM = 3.0        # TX column kept this far from the RX pair
T_UP = 1.4e-3              # up-chirp
T_RETRACE = 0.15e-3        # ADF4159 retrace
FS = 192_000.0             # UMC404HD, and at 24 GHz it has to be 192 k

# Substrates worth considering. er and tand are the 10 GHz datasheet figures.
SUBSTRATES = {
    "RO4350B": dict(er=3.66, tand=0.0037, h=0.254e-3, er_tol=0.05,
                    note="the real one: er held to +/-0.05, so the patch lands where you drew it"),
    "FR-4":    dict(er=4.30, tand=0.0250, h=0.200e-3, er_tol=0.20,
                    note="the cheap panel: er is only +/-0.2, which at 24 GHz is +/-0.6 GHz of resonance"),
}


# ----------------------------------------------------------------------
# the element
# ----------------------------------------------------------------------
def patch(f, er, h):
    """Width, length and effective permittivity of a rectangular patch."""
    lam0 = C / f
    W = (C / (2 * f)) * math.sqrt(2.0 / (er + 1.0))
    eeff = (er + 1) / 2 + (er - 1) / 2 * (1 + 12 * h / W) ** -0.5
    dL = 0.412 * h * ((eeff + 0.3) * (W / h + 0.264)) / ((eeff - 0.258) * (W / h + 0.8))
    L = C / (2 * f * math.sqrt(eeff)) - 2 * dL
    return dict(W=W, L=L, Le=L + 2 * dL, eeff=eeff, dL=dL,
                lam0=lam0, lam_g=lam0 / math.sqrt(eeff))


def edge_resistance(f, W, lam0):
    """Input resistance at the radiating edge, from the two-slot model. This is
    what the feed has to transform down to 50 ohm."""
    G1 = (1 / 90) * (W / lam0) ** 2 if W < lam0 else (1 / 120) * (W / lam0)
    return 1.0 / (2 * G1)          # mutual coupling ignored; ~10 % optimistic


def inset(Rin, L, R_target=50.0):
    """How far to cut the feed into the patch to see R_target. The resistance
    falls as cos^4 along the length."""
    if Rin <= R_target:
        return 0.0
    return (L / math.pi) * math.acos((R_target / Rin) ** 0.25)


def microstrip_w(er, h, z0=50.0):
    """Trace width for a target impedance (Wheeler/Hammerstad, W/h > 1 branch)."""
    B = 377 * math.pi / (2 * z0 * math.sqrt(er))
    wh = (2 / math.pi) * (B - 1 - math.log(2 * B - 1)
                          + (er - 1) / (2 * er) * (math.log(B - 1) + 0.39 - 0.61 / er))
    return wh * h


def microstrip_loss_db_per_mm(f, er, tand, h, w, eeff):
    """Conductor + dielectric attenuation of a microstrip line. At 24 GHz this
    is the number that decides whether FR-4 is allowed anywhere near the feed."""
    lam0 = C / f
    a_d = 27.3 * (er * (eeff - 1)) / (math.sqrt(eeff) * (er - 1)) * tand / lam0
    Rs = math.sqrt(math.pi * f * MU0 / SIGMA_CU)
    a_c = ROUGHNESS * 8.686 * Rs / (50.0 * w)
    return (a_d + a_c) / 1000.0, a_d / 1000.0, a_c / 1000.0


def fractional_bw(er, h, W, L, lam0):
    """-10 dB fractional bandwidth of a thin rectangular patch (Balanis 14-81).
    This decides whether a substrate tolerance matters: a resonance that shifts
    less than half the bandwidth still covers the band."""
    return 3.77 * (er - 1) / (er ** 2) * (W / L) * (h / lam0)


# ----------------------------------------------------------------------
# the patterns
# ----------------------------------------------------------------------
def _hplane(theta, W, lam0):
    """Two-slot H-plane pattern (the plane containing the patch width). This is
    the AZIMUTH cut, and the array does nothing to it."""
    k0 = 2 * math.pi / lam0
    x = k0 * W / 2 * math.sin(theta)
    sinc = 1.0 if abs(x) < 1e-12 else math.sin(x) / x
    return abs(math.cos(theta) * sinc)


def beamwidth_numeric(pattern, *args, hi=math.pi / 2 - 1e-6):
    """-3 dB full beamwidth of a pattern function, found by bisection rather
    than by a remembered closed form."""
    target = 1 / math.sqrt(2.0)
    lo = 0.0
    if pattern(hi, *args) > target:
        return 2 * math.degrees(hi)
    for _ in range(200):
        mid = (lo + hi) / 2
        if pattern(mid, *args) > target:
            lo = mid
        else:
            hi = mid
    return 2 * math.degrees((lo + hi) / 2)


def af_beamwidth_deg(n, d, lam0):
    """-3 dB beamwidth of a uniform broadside array factor."""
    return math.degrees(0.886 * lam0 / (n * d))


def unambiguous_deg(lam0, d):
    """Bearing at which the interferometer's phase difference reaches +/-pi."""
    s = lam0 / (2 * d)
    return 90.0 if s >= 1 else math.degrees(math.asin(s))


def squint_deg(df, f, eeff):
    """Beam squint of a series (comb-line) feed at an offset from centre. The
    element phasing is set by the guide wavelength, which moves with frequency."""
    s = (df / f) * math.sqrt(eeff)
    return 0.0 if abs(s) >= 1 else math.degrees(math.asin(s))


# ----------------------------------------------------------------------
# the board
# ----------------------------------------------------------------------
def column(n, p, s, single_dbi=6.5):
    """A series-fed comb-line column: element spacing is one guide wavelength,
    so every patch is fed in phase off a single line."""
    d = p["lam_g"]
    w50 = microstrip_w(s["er"], s["h"], 50.0)
    a_tot, a_d, a_c = microstrip_loss_db_per_mm(F0, s["er"], s["tand"],
                                                s["h"], w50, p["eeff"])
    feed_len = (n - 1) * d + 4e-3            # the line, plus a run to the MMIC
    return dict(n=n, d=d, span=(n - 1) * d, height=(n - 1) * d + p["L"],
                w50=w50, feed_len=feed_len,
                loss_db=a_tot * feed_len * 1e3,
                a_tot=a_tot, a_d=a_d, a_c=a_c,
                gain_dbi=single_dbi + 10 * math.log10(n) - a_tot * feed_len * 1e3,
                elev_bw=af_beamwidth_deg(n, d, p["lam0"]))


def board(name, s, n_elem=N_ELEM, verbose=True):
    p = patch(F0, s["er"], s["h"])
    Rin = edge_resistance(F0, p["W"], p["lam0"])
    y0 = inset(Rin, p["L"])
    col = column(n_elem, p, s)
    az_bw = beamwidth_numeric(_hplane, p["W"], p["lam0"])

    baseline = p["lam0"] / 2                       # RX1 -> RX2 centres
    gap = baseline - p["W"]
    unamb = unambiguous_deg(p["lam0"], baseline)
    sq = squint_deg((BAND[1] - BAND[0]) / 2, F0, p["eeff"])

    # deg of bearing per deg of phase error, at boresight
    bearing_per_phase = 1.0 / (2 * math.pi * baseline / p["lam0"])
    phase_per_mm = 360.0 / (p["lam_g"] * 1e3)      # microstrip, not free space

    # RX1 | RX2 ... TX, with the transmitter kept TX_OFFSET_LAM away
    board_w = baseline + 2 * p["W"] + TX_OFFSET_LAM * p["lam0"]
    board_h = col["height"] + 8e-3

    if verbose:
        print(f"\n{name}   er {s['er']}, h {s['h']*1e3:.3f} mm, tand {s['tand']}")
        print(f"  {s['note']}")
        print(f"    free-space lambda        {p['lam0']*1e3:8.3f} mm")
        print(f"    guide wavelength         {p['lam_g']*1e3:8.3f} mm")
        print(f"    patch W x L              {p['W']*1e3:8.3f} x {p['L']*1e3:.3f} mm")
        print(f"    effective er             {p['eeff']:8.3f}")
        print(f"    edge resistance          {Rin:8.0f} ohm")
        print(f"    inset for 50 ohm         {y0*1e3:8.3f} mm")
        print(f"    50 ohm trace width       {col['w50']*1e3:8.3f} mm")
        print(f"    feed loss                {col['a_tot']:8.4f} dB/mm "
              f"(dielectric {col['a_d']:.4f}, conductor {col['a_c']:.4f})")
        print(f"    column: {n_elem} patches at {col['d']*1e3:.3f} mm (one lambda_g)")
        print(f"      realized gain          {col['gain_dbi']:8.1f} dBi "
              f"(after {col['loss_db']:.2f} dB of feed)")
        print(f"      elevation beamwidth    {col['elev_bw']:8.1f} deg")
        print(f"      azimuth beamwidth      {az_bw:8.1f} deg   (single patch; "
              f"the column does not narrow it)")
        print(f"      series-feed squint     {sq:8.2f} deg at the band edge")
        print(f"    interferometer: RX centres {baseline*1e3:.3f} mm apart "
              f"({gap*1e3:.2f} mm copper gap)")
        print(f"      unambiguous            +/-{unamb:.1f} deg  -> covers the "
              f"whole {az_bw:.0f} deg azimuth pattern: "
              f"{'YES' if 2*unamb >= az_bw else 'NO'}")
        print(f"      phase -> bearing       {bearing_per_phase:.3f} deg per deg")
        print(f"      etch tolerance         {phase_per_mm:.1f} deg/mm of trace "
              f"-> 50 um mismatch = {phase_per_mm*0.05*bearing_per_phase:.2f} deg of bearing")
        print(f"    board, antennas only     {board_w*1e3:.1f} x {board_h*1e3:.1f} mm "
              f"(TX kept {TX_OFFSET_LAM:.0f} lambda from the RX pair)")
    return dict(p=p, Rin=Rin, y0=y0, col=col, az_bw=az_bw, baseline=baseline,
                unamb=unamb, squint=sq, bearing_per_phase=bearing_per_phase,
                phase_per_mm=phase_per_mm, board_w=board_w, board_h=board_h)


def band_check(name, s, verbose=True):
    """A patch is narrowband. The question is not whether the resonance moves
    with the substrate tolerance -- it always does -- but whether it moves
    further than the patch's own bandwidth can absorb."""
    p0 = patch(F0, s["er"], s["h"])
    bw = fractional_bw(s["er"], s["h"], p0["W"], p0["L"], p0["lam0"])
    half_bw = F0 * bw / 2
    need = (BAND[1] - BAND[0]) / 2
    worst = 0.0
    shifts = []
    for er in (s["er"] - s["er_tol"], s["er"] + s["er_tol"]):
        f = F0 * math.sqrt(p0["eeff"]) / math.sqrt(patch(F0, er, s["h"])["eeff"])
        worst = max(worst, abs(f - F0))
        shifts.append((er, f))
    margin = half_bw - (need + worst)
    if verbose:
        print(f"\n{name}:")
        print(f"  patch bandwidth          {bw*100:.2f} % = {F0*bw/1e6:.0f} MHz "
              f"(the ISM band is {(BAND[1]-BAND[0])/1e6:.0f} MHz wide)")
        print(f"  substrate tolerance      er {s['er']} +/- {s['er_tol']}")
        for er, f in shifts:
            print(f"    er {er:5.2f} -> resonates at {f/1e9:6.3f} GHz "
                  f"({(f-F0)/1e6:+.0f} MHz)")
        print(f"  worst shift {worst/1e6:.0f} MHz + half the band {need/1e6:.0f} MHz "
              f"= {(worst+need)/1e6:.0f} MHz needed, {half_bw/1e6:.0f} MHz available")
        print(f"  -> {'COVERS the band' if margin > 0 else 'MISSES part of the band'} "
              f"({margin/1e6:+.0f} MHz of margin)")
        if margin <= 0:
            print("     which is exactly why the first board is a dimension sweep\n"
                  "     you measure, not a design you trust.")
    return dict(bw=bw, half_bw=half_bw, worst=worst, margin=margin)


# ----------------------------------------------------------------------
# what it buys, in the project's own radar equation
# ----------------------------------------------------------------------
def link(b, t_up=T_UP, retrace=T_RETRACE, fs=FS, n_chirps=64,
         rcs=0.01, r=10.0, verbose=True):
    """The 24 GHz operating point, scored by ground_station/fmcw_sim.py -- the
    same RadarSpec, the same radar equation and the same leakage-limited MDS
    that produce the 2.4 GHz build's published 71 dB.

    Velocity is computed from the PRI, not the up-chirp: the retrace is dead
    time but the Doppler axis still samples on it. That is the same distinction
    signal-chain.md draws for the 6.4 ms / 7.4 ms pair.
    """
    from fmcw_sim import RadarSpec

    g = b["col"]["gain_dbi"]
    new_ = RadarSpec(f0=BAND[0], bw=BAND[1] - BAND[0], t_chirp=t_up, fs=fs,
                     pt_dbm=5.0,          # BGT24LTR22 TX, datasheet typical
                     gt_dbi=g, gr_dbi=g,
                     nf_db=8.0,           # BGT24LTR22 NF_SSB
                     losses_db=2.0,       # mismatch; the feed loss is in the gain
                     n_chirps=n_chirps, isolation_db=30.0)
    # the build as it stands, exactly as docs/drone-software.md invokes it
    old = RadarSpec(f0=2.440e9, bw=40e6, gt_dbi=13.4, gr_dbi=13.4)
    old.t_chirp, old.fs = 6.4e-3, 48_000.0
    pri_new, pri_old = t_up + retrace, 7.4e-3

    def vmax(s, pri):
        return s.lam / (4 * pri)

    def vres(s, pri):
        return s.lam / (2 * s.n_chirps * pri)

    r_max48 = C * t_up * (48_000.0 / 2) / (2 * new_.bw)
    snr = new_.rx_dbm(r, rcs) - new_.practical_mds_dbm()
    snr_old = old.rx_dbm(r, rcs) - old.practical_mds_dbm()
    lin = 10 ** (snr / 10)
    sigma_phase_deg = math.degrees(1.0 / math.sqrt(lin))
    sigma_bearing_deg = sigma_phase_deg * b["bearing_per_phase"]

    if verbose:
        print("\n  operating point, scored by ground_station/fmcw_sim.py")
        print(f"    {'':<26}{'24 GHz':>13}{'2.4 GHz now':>14}")
        rows = [
            ("swept bandwidth", f"{new_.bw/1e6:.0f} MHz", f"{old.bw/1e6:.0f} MHz"),
            ("range cell", f"{new_.range_res:.2f} m", f"{old.range_res:.2f} m"),
            ("up-chirp / PRI", f"{t_up*1e3:.2f}/{pri_new*1e3:.2f} ms",
                               f"{old.t_chirp*1e3:.1f}/{pri_old*1e3:.1f} ms"),
            ("sample rate", f"{new_.fs/1e3:.0f} kHz", f"{old.fs/1e3:.0f} kHz"),
            ("beat at 10 m", f"{new_.beat_hz(10):.0f} Hz", f"{old.beat_hz(10):.0f} Hz"),
            ("beat at 20 m", f"{new_.beat_hz(20):.0f} Hz", f"{old.beat_hz(20):.0f} Hz"),
            ("Nyquist range", f"{new_.r_max:.0f} m", f"{old.r_max:.0f} m"),
            ("...on a 48 kHz card", f"{r_max48:.1f} m", f"{old.r_max:.0f} m"),
            ("unambiguous velocity", f"+/-{vmax(new_, pri_new):.2f} m/s",
                                     f"+/-{vmax(old, pri_old):.2f} m/s"),
            ("velocity cell", f"{vres(new_, pri_new):.3f} m/s",
                              f"{vres(old, pri_old):.3f} m/s"),
            ("dwell, 64 chirps", f"{pri_new*n_chirps*1e3:.0f} ms",
                                 f"{pri_old*64*1e3:.0f} ms"),
            ("antenna gain", f"{g:.1f} dBi", f"{old.gt_dbi:.1f} dBi"),
            ("echo at 10 m", f"{new_.rx_dbm(r, rcs):.0f} dBm",
                             f"{old.rx_dbm(r, rcs):.0f} dBm"),
            ("SNR at 10 m", f"{snr:.0f} dB", f"{snr_old:.0f} dB"),
            ("interferometer cone", f"+/-{b['unamb']:.0f} deg", "+/-18.4 deg"),
        ]
        for k, a, c in rows:
            print(f"    {k:<26}{a:>13}{c:>14}")
        print(f"\n    thermal floor on bearing {sigma_bearing_deg:.2f} deg rms "
              f"(phase {sigma_phase_deg:.2f} deg)")
        print(f"    the budget is 2.5 deg, so thermal noise is "
              f"{2.5/sigma_bearing_deg:.0f}x inside it and calibration dominates.")
        print(f"\n    A 48 kHz card still reaches {r_max48:.1f} m, which covers the "
              f"3-10 m cage,")
        print(f"    but only {48_000.0*t_up:.0f} samples per chirp. At 192 kHz it is "
              f"{fs*t_up:.0f} samples")
        print(f"    and {new_.r_max:.0f} m. The UMC404HD already does 192 kHz; the "
              f"UCA202 does not.")
    return dict(spec=new_, old=old, pri=pri_new, snr=snr, snr_old=snr_old,
                v_max=vmax(new_, pri_new), v_res=vres(new_, pri_new),
                sigma_bearing_deg=sigma_bearing_deg,
                sigma_phase_deg=sigma_phase_deg)


def sweep_panel(s, n=7, step_um=40, verbose=True):
    """The prototype panel: one board carrying several patch lengths, so you
    measure which one resonates instead of trusting the substrate."""
    p = patch(F0, s["er"], s["h"])
    rows = []
    for i in range(n):
        L = p["L"] + (i - n // 2) * step_um * 1e-6
        rows.append((chr(65 + i), L, F0 * p["L"] / L))
    if verbose:
        print(f"\n  prototype panel: {n} patches, L stepped by {step_um} um")
        print(f"  {'variant':>8}{'L (mm)':>10}{'resonates near':>18}")
        for tag, L, f in rows:
            print(f"{tag:>8}{L*1e3:>10.3f}{f/1e9:>15.3f} GHz")
        print("  Measure all of them, keep the one that lands at 24.125, and use\n"
              "  its length on the Rogers board. One $5 iteration, not one $300 one.")
    return rows


# ----------------------------------------------------------------------
def selftest():
    ok = 0

    def check(cond, msg):
        nonlocal ok
        assert cond, msg
        ok += 1

    ro = SUBSTRATES["RO4350B"]
    p = patch(F0, ro["er"], ro["h"])

    # -- element geometry lands where the textbook says it should
    check(3.5e-3 < p["W"] < 4.5e-3, f"patch W out of range: {p['W']}")
    check(2.8e-3 < p["L"] < 3.5e-3, f"patch L out of range: {p['L']}")
    check(p["L"] < p["W"], "a rectangular patch is wider than it is long")
    check(1 < p["eeff"] < ro["er"], "eeff must sit between air and the substrate")
    check(abs(p["lam0"] - C / F0) < 1e-9, "lambda0 must be c/f")
    check(abs(p["lam_g"] - p["lam0"] / math.sqrt(p["eeff"])) < 1e-12,
          "lambda_g must be lambda0/sqrt(eeff)")

    # -- resonance really is at F0: rebuild f from the length
    f_back = C / (2 * math.sqrt(p["eeff"]) * (p["L"] + 2 * p["dL"]))
    check(abs(f_back - F0) / F0 < 1e-9, f"length does not resonate at F0: {f_back}")

    # -- the feed
    Rin = edge_resistance(F0, p["W"], p["lam0"])
    check(150 < Rin < 600, f"edge resistance implausible: {Rin}")
    y0 = inset(Rin, p["L"])
    check(0 < y0 < p["L"] / 2, f"inset must cut in, not through: {y0}")
    w50 = microstrip_w(ro["er"], ro["h"], 50.0)
    check(0.4e-3 < w50 < 0.7e-3, f"50 ohm width implausible: {w50}")
    check(microstrip_w(ro["er"], ro["h"], 70.7) < w50,
          "a 70.7 ohm line is narrower than a 50 ohm one")
    check(inset(40.0, p["L"]) == 0.0, "no inset needed when the edge is below 50 ohm")

    # -- loss: FR-4 must come out far worse than Rogers, and dielectric-dominated
    a_ro, ad_ro, _ = microstrip_loss_db_per_mm(F0, ro["er"], ro["tand"], ro["h"],
                                               w50, p["eeff"])
    fr = SUBSTRATES["FR-4"]
    pf = patch(F0, fr["er"], fr["h"])
    a_fr, ad_fr, _ = microstrip_loss_db_per_mm(F0, fr["er"], fr["tand"], fr["h"],
                                               microstrip_w(fr["er"], fr["h"]), pf["eeff"])
    check(a_fr > 2 * a_ro, f"FR-4 must be much lossier: {a_fr} vs {a_ro}")
    check(ad_fr / a_fr > 0.5, "FR-4 loss at 24 GHz is dielectric-dominated")

    # -- patterns
    az = beamwidth_numeric(_hplane, p["W"], p["lam0"])
    check(60 < az < 100, f"single-patch azimuth beamwidth implausible: {az}")
    check(_hplane(0.0, p["W"], p["lam0"]) == 1.0, "pattern must peak at broadside")
    check(_hplane(math.radians(80), p["W"], p["lam0"])
          < _hplane(math.radians(20), p["W"], p["lam0"]), "pattern must fall off")
    check(af_beamwidth_deg(8, p["lam_g"], p["lam0"])
          < af_beamwidth_deg(4, p["lam_g"], p["lam0"]),
          "more elements must give a narrower beam")

    # -- the interferometer is the whole point: lambda/2 must be unambiguous
    #    across the entire azimuth pattern, unlike the 193 mm horn baseline
    b = board("RO4350B", ro, verbose=False)
    check(abs(b["unamb"] - 90.0) < 1e-9,
          f"lambda/2 spacing must be unambiguous to +/-90 deg, got {b['unamb']}")
    check(2 * b["unamb"] >= b["az_bw"], "unambiguous cone must cover the pattern")
    check(unambiguous_deg(p["lam0"], 0.1931) < 5.0,
          "the 2.4 GHz baseline would be hopelessly ambiguous at 24 GHz")
    check(b["baseline"] > p["W"], "the two RX columns must not overlap")
    check(b["col"]["gain_dbi"] < 6.5 + 10 * math.log10(N_ELEM),
          "realized gain must be below ideal by the feed loss")
    check(b["squint"] < 2.0, f"series feed squint must be negligible: {b['squint']}")

    # -- bandwidth vs substrate tolerance is the reason for the cheap panel first
    bro = band_check("RO4350B", ro, verbose=False)
    bfr = band_check("FR-4", fr, verbose=False)
    check(bro["margin"] > bfr["margin"], "Rogers must beat FR-4 on margin")
    check(bfr["margin"] < 0, "FR-4 cannot be trusted to land in band")
    check(bro["bw"] > 0.01, "patch bandwidth should be a percent or so")

    # -- the operating point has to fit the sound card that already exists
    lk = link(b, verbose=False)
    s = lk["spec"]
    check(s.beat_hz(20.0) < s.fs / 2, "20 m must sit below Nyquist")
    check(s.beat_hz(10.0) < 48_000.0 / 2,
          "10 m must still work on the 48 kHz card that already exists")
    check(lk["v_max"] > 2.0, f"must cover a 2 m/s drone: {lk['v_max']}")
    check(lk["v_res"] < 0.129, "velocity cell must beat the 2.4 GHz build's 0.13 m/s")
    check(s.range_res < 0.7, f"range cell must beat 3.75 m by 6x: {s.range_res}")
    check(lk["snr"] > 20.0, f"must detect a 0.01 m^2 drone at 10 m: {lk['snr']}")
    check(lk["sigma_bearing_deg"] < 2.5, "thermal bearing floor must be in budget")
    check(lk["snr"] < lk["snr_old"], "24 GHz must cost echo, not gain it")

    # -- the 2.4 GHz comparison column must reproduce the published build,
    #    or the comparison is worthless
    old = lk["old"]
    check(abs(old.range_res - 3.75) < 0.01, f"published range cell is 3.75 m: {old.range_res}")
    check(abs(old.beat_hz(1.0) - 41.70) < 0.05, f"published 41.70 Hz/m: {old.beat_hz(1.0)}")
    check(abs(old.lam / (4 * 7.4e-3) - 4.12) < 0.02, "published +/-4.12 m/s")
    check(abs(old.rx_dbm(10.0, 0.01) - (-74.0)) < 1.0,
          f"published echo is -74 dBm: {old.rx_dbm(10.0, 0.01)}")
    check(abs(lk["snr_old"] - 71.0) < 1.5, f"published SNR is 71 dB: {lk['snr_old']}")

    # -- the sweep panel is monotone and brackets the band
    rows = sweep_panel(fr, verbose=False)
    fs_ = [f for _, _, f in rows]
    check(all(a > b_ for a, b_ in zip(fs_, fs_[1:])), "longer patch = lower f")
    check(fs_[0] > BAND[1] > BAND[0] > fs_[-1], "the sweep must bracket the band")

    print(f"selftest: {ok} checks passed")
    return 0


# ----------------------------------------------------------------------
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--elements", type=int, default=N_ELEM)
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(selftest())

    print("=" * 74)
    print(f"  24 GHz patch columns — {F0/1e9:.3f} GHz, ISM band "
          f"{BAND[0]/1e9:.2f}-{BAND[1]/1e9:.2f} GHz")
    print("=" * 74)
    boards = {}
    for name, s in SUBSTRATES.items():
        boards[name] = board(name, s, n_elem=args.elements)
    for name, s in SUBSTRATES.items():
        band_check(name, s)
    link(boards["RO4350B"])
    if args.sweep:
        sweep_panel(SUBSTRATES["FR-4"])
    print("\n  Compare: the 2.4 GHz horn is 263.8 x 193.1 mm, folded from sheet")
    print("  copper, and its 193 mm interferometer baseline is unambiguous only")
    print("  to +/-18.4 deg. This is a few square centimetres, a board house")
    print("  prints it, and it is unambiguous everywhere it can see.")
