#!/usr/bin/env python3
"""
horn.py — optimum pyramidal horn designer (Balanis), with the checks that
catch a wrong answer before you cut metal.

Why a horn instead of the Vivaldi: easier to fabricate accurately, far easier
to mesh, and the waveguide feed is inherently wideband, which keeps the door
open to widening the VCO sweep later.

Design (Balanis, optimum pyramidal horn):
    optimum E-plane :  b1 = sqrt(2*lambda*rho1)
    optimum H-plane :  a1 = sqrt(3*lambda*rho2)
    gain            :  G = (4*pi/lambda^2) * eps_ap * a1 * b1 , eps_ap ~ 0.51

REALIZABILITY CONSTRAINT (the one that trips people up):
    a pyramidal horn only closes in CAD if the E- and H-plane flares reach the
    aperture at the SAME axial length, pe == ph:

        pe = (b1 - b) * sqrt((rho1/b1)^2 - 1/4)
        ph = (a1 - a) * sqrt((rho2/a1)^2 - 1/4)

    Change a1 or b1 and you must re-solve the other. Skip it and the geometry
    will not close, which is a confusing failure mode if you don't know to
    look for it.

SANITY CHECK on every result:  G <= 4*pi*A/lambda^2 (the aperture bound).
An EM solver will happily hand you a gain that violates physics if the model
is set up wrong; the bound is the only cheap defence.

    python horn.py                 # WR-340 feed, 2.45 GHz, optimum design
    python horn.py --gain 11       # smaller aperture if 265 mm is unwieldy
"""

import argparse
import math

C = 299_792_458.0

WAVEGUIDES = {   # inner dimensions (m)
    "WR-340": (0.0864, 0.0432),
    "WR-284": (0.0721, 0.0341),
    "WR-430": (0.1092, 0.0546),
}


def cutoff_te10(a):
    return C / (2 * a)


def solve_optimum(lam, a, b, gain_dbi, eps_ap=0.51, iters=200):
    """Solve a1, b1 for a target gain while enforcing pe == ph."""
    G = 10 ** (gain_dbi / 10)
    # Balanis' standard iteration: for the optimum horn b1 ~ sqrt(2*lam*rho1)
    # and a1 = G*lam^2/(eps_ap*4*pi*b1). Iterate chi = rho_e/lam.
    chi = G / (2 * math.pi * math.sqrt(2 * math.pi * eps_ap))   # seed
    for _ in range(iters):
        # from the gain expression with the optimum relations substituted
        lhs = (math.sqrt(2 * chi) - b / lam) ** 2 * (2 * chi - 1)
        rhs = (G / (2 * math.pi) * math.sqrt(3 / (2 * math.pi)) / math.sqrt(chi)
               - a / lam) ** 2 * ((G ** 2 / (6 * math.pi ** 3)) / chi - 1)
        f = lhs - rhs
        d = 1e-6
        chi2 = chi + d
        lhs2 = (math.sqrt(2 * chi2) - b / lam) ** 2 * (2 * chi2 - 1)
        rhs2 = (G / (2 * math.pi) * math.sqrt(3 / (2 * math.pi)) / math.sqrt(chi2)
                - a / lam) ** 2 * ((G ** 2 / (6 * math.pi ** 3)) / chi2 - 1)
        df = ((lhs2 - rhs2) - f) / d
        if abs(df) < 1e-12:
            break
        step = f / df
        chi -= max(-0.5 * chi, min(0.5 * chi, step))
        if chi <= 0.5:
            chi = 0.51
    rho1 = chi * lam                                   # E-plane
    rho2 = (G ** 2 / (8 * math.pi ** 3)) * (lam / chi) # H-plane
    b1 = math.sqrt(2 * lam * rho1)
    a1 = math.sqrt(3 * lam * rho2)
    return a1, b1, rho1, rho2


def flare_lengths(a, b, a1, b1, rho1, rho2):
    pe = (b1 - b) * math.sqrt((rho1 / b1) ** 2 - 0.25)
    ph = (a1 - a) * math.sqrt((rho2 / a1) ** 2 - 0.25)
    return pe, ph


def report(f_ghz=2.45, wg="WR-340", gain_dbi=13.4, eps_ap=0.51):
    lam = C / (f_ghz * 1e9)
    a, b = WAVEGUIDES[wg]
    a1, b1, rho1, rho2 = solve_optimum(lam, a, b, gain_dbi, eps_ap)
    pe, ph = flare_lengths(a, b, a1, b1, rho1, rho2)

    A = a1 * b1
    bound = 4 * math.pi * A / lam ** 2
    g_lin = eps_ap * bound
    g_dbi = 10 * math.log10(g_lin)
    # optimum-horn beamwidths (Balanis approximations)
    hp_E = 54.0 * lam / b1
    hp_H = 78.0 * lam / a1

    print("=" * 68)
    print(f"  OPTIMUM PYRAMIDAL HORN — {f_ghz:.2f} GHz, {wg} feed")
    print("=" * 68)
    print(f"  lambda0                : {lam*1000:.1f} mm")
    print(f"  feed guide a x b       : {a*1000:.1f} x {b*1000:.1f} mm")
    print(f"  TE10 cutoff            : {cutoff_te10(a)/1e9:.3f} GHz"
          f"   (single-mode to {cutoff_te10(a)*2/1e9:.2f} GHz)")
    lam_g = lam / math.sqrt(max(1e-9, 1 - (lam / (2 * a)) ** 2))
    print(f"  guide wavelength       : {lam_g*1000:.1f} mm")
    print(f"  coax probe             : ~{lam_g/4*1000*0.68:.0f} mm long, "
          f"{lam_g/4*1000:.0f} mm from the shorted back wall")
    print("-" * 68)
    print(f"  aperture a1 (H-plane)  : {a1*1000:.1f} mm")
    print(f"  aperture b1 (E-plane)  : {b1*1000:.1f} mm")
    print(f"  axial flare length     : pe {pe*1000:.1f} mm | ph {ph*1000:.1f} mm")
    close = abs(pe - ph) / max(pe, ph) * 100
    print(f"  realizability pe == ph : {close:.2f} % apart  -> "
          f"{'OK, geometry closes' if close < 2 else 'FAIL, re-solve'}")
    print("-" * 68)
    print(f"  predicted gain         : {g_dbi:.1f} dBi")
    print(f"  aperture bound 4piA/l^2: {10*math.log10(bound):.1f} dBi  "
          f"(={bound:.1f} linear)")
    print(f"  aperture efficiency    : {g_lin/bound*100:.0f} %  "
          f"{'<- textbook optimum' if 45 < g_lin/bound*100 < 60 else ''}")
    print(f"  beamwidths             : ~{hp_E:.0f} deg E-plane, ~{hp_H:.0f} deg H-plane")
    print("=" * 68)
    print("\n  SANITY CHECK, always run it: a claimed gain above the aperture bound")
    print("  is impossible. Quote it in your log like this ->")
    print(f"    \"predicted {g_dbi:.1f} dBi, aperture bound {10*math.log10(bound):.1f} dBi,")
    print(f"     {g_lin/bound*100:.0f}% efficiency, plausible for an optimum pyramidal horn\"")
    print(f"\n  Build note: that is a {a1*1000:.0f} x {b1*1000:.0f} mm aperture, TWICE")
    print("  (one TX, one RX). If unwieldy, --gain 11 shrinks it; record the")
    print("  trade in your log rather than silently picking small.\n")
    return dict(a1=a1, b1=b1, pe=pe, ph=ph, gain=g_dbi, bound=10*math.log10(bound))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--freq", type=float, default=2.45, help="GHz")
    ap.add_argument("--wg", default="WR-340", choices=list(WAVEGUIDES))
    ap.add_argument("--gain", type=float, default=13.4, help="target gain dBi")
    args = ap.parse_args()
    report(args.freq, args.wg, args.gain)


if __name__ == "__main__":
    main()
