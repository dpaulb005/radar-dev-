#!/usr/bin/env python3
"""
vivaldi.py — design the custom antenna that replaces the coffee cans.

A Vivaldi (exponentially tapered slot) antenna is the right custom antenna for
this radar, for one concrete reason: **bandwidth**. An FMCW radar sweeps its
carrier, and the antenna must stay matched across the whole sweep. A patch is
typically 1-3 % bandwidth on FR4 — marginal against a 3.4 % sweep — while a
Vivaldi runs over octaves. It is also flat, cheap, and manufacturable as an
ordinary 2-layer PCB (JLCPCB), which is exactly the process you already use
for the drone's flight controller.

This tool computes the geometry, writes an SVG outline you can import into
KiCad/Inkscape as a board edge + copper pour, and prints an openEMS snippet so
you can verify the design in simulation *before* paying for boards.

Geometry
--------
The flare is an exponential taper between the throat (slot width w_t) and the
mouth (aperture W), over length L:

    y(x) = C1 * e^(R*x) + C2       fitted through (0, w_t/2) and (L, W/2)

Design rules of thumb (lowest usable frequency f_low):
    W (mouth)  >= lambda_low / 2      aperture sets the low-frequency cutoff
    L (length) >= lambda_low          longer = more gain, more directive
    R (rate)   ~ 0.03-0.10 /mm        higher = faster flare, wider beam

Usage
-----
    python vivaldi.py                       # design for 2.4 GHz, print table
    python vivaldi.py --svg viv.svg         # export outline for KiCad
    python vivaldi.py --f-low 2.3 --array 4 # 4-element array variant
    python vivaldi.py --openems             # print a simulation script
"""

import argparse
import math

C = 299_792_458.0


def microstrip_width_50(er=4.4, h_mm=1.6, z0=50.0):
    """Hammerstad synthesis for a z0-ohm microstrip width (mm)."""
    A = z0 / 60 * math.sqrt((er + 1) / 2) + (er - 1) / (er + 1) * (0.23 + 0.11 / er)
    wh = 8 * math.exp(A) / (math.exp(2 * A) - 2)
    if wh > 2:  # wide-strip branch
        B = 377 * math.pi / (2 * z0 * math.sqrt(er))
        wh = 2 / math.pi * (B - 1 - math.log(2 * B - 1)
                            + (er - 1) / (2 * er) * (math.log(B - 1) + 0.39 - 0.61 / er))
    return wh * h_mm


class Vivaldi:
    def __init__(self, f_low_ghz=2.30, f_high_ghz=2.60, er=4.4, h_mm=1.6,
                 w_throat=0.5, rate=None, length_mult=1.05, mouth_mult=0.58):
        self.f_low = f_low_ghz * 1e9
        self.f_high = f_high_ghz * 1e9
        self.er = er
        self.h = h_mm
        self.w_throat = w_throat
        self.lam_low = C / self.f_low * 1000.0            # mm
        self.W = mouth_mult * self.lam_low                # aperture (>= lam/2)
        self.L = length_mult * self.lam_low               # flare length
        self.rate = rate if rate else self._auto_rate()
        self.feed_w = microstrip_width_50(er, h_mm)

    def _auto_rate(self):
        """Pick an opening rate that reaches the mouth smoothly over L."""
        return math.log((self.W / 2) / (self.w_throat / 2)) / self.L

    # --- taper ---
    def taper(self, n=200):
        """Return [(x, y)] of the upper flare edge, x in [0, L] (mm)."""
        y0, y1 = self.w_throat / 2, self.W / 2
        R, L = self.rate, self.L
        denom = math.exp(R * L) - 1.0
        return [(x, y0 + (y1 - y0) * (math.exp(R * x) - 1.0) / denom)
                for x in (i * L / (n - 1) for i in range(n))]

    @property
    def total_len(self):
        return self.L + 25.0        # flare + feed/transition region

    @property
    def board(self):
        return (self.total_len, self.W + 8.0)

    def gain_estimate_dbi(self):
        """Crude aperture estimate; verify in openEMS."""
        lam = C / ((self.f_low + self.f_high) / 2) * 1000.0
        return 10 * math.log10(max(1.0, 4 * math.pi * (self.W * self.L * 0.5) / lam ** 2))

    def report(self, array=1):
        bw = (self.f_high - self.f_low) / ((self.f_high + self.f_low) / 2) * 100
        bx, by = self.board
        print("=" * 66)
        print("  VIVALDI ANTENNA — custom replacement for the coffee cans")
        print("=" * 66)
        print(f"  band                 : {self.f_low/1e9:.2f} - {self.f_high/1e9:.2f} GHz"
              f"   ({bw:.1f} % fractional)")
        print(f"  substrate            : FR4, er={self.er}, h={self.h} mm, 1 oz Cu")
        print(f"  lambda @ f_low       : {self.lam_low:.1f} mm")
        print("-" * 66)
        print(f"  mouth aperture  W    : {self.W:.1f} mm   (rule: >= lambda/2 = "
              f"{self.lam_low/2:.1f} mm)")
        print(f"  flare length    L    : {self.L:.1f} mm   (rule: >= lambda = "
              f"{self.lam_low:.1f} mm)")
        print(f"  throat slot     w_t  : {self.w_throat:.2f} mm")
        print(f"  opening rate    R    : {self.rate:.4f} /mm")
        print(f"  50 ohm feed width    : {self.feed_w:.2f} mm  (microstrip on {self.h} mm FR4)")
        print(f"  board size           : {bx:.0f} x {by:.0f} mm")
        print(f"  est. gain (single)   : ~{self.gain_estimate_dbi():.1f} dBi  "
              f"(verify in openEMS)")
        if array > 1:
            pitch = C / ((self.f_low + self.f_high) / 2) * 1000 * 0.5
            print("-" * 66)
            print(f"  ARRAY x{array}            : element pitch {pitch:.1f} mm (lambda/2)")
            print(f"  array width          : {(array-1)*pitch + by:.0f} mm")
            print(f"  est. array gain      : ~{self.gain_estimate_dbi() + 10*math.log10(array):.1f} dBi"
                  f"  (+{10*math.log10(array):.1f} dB)")
            print(f"  azimuth beamwidth    : ~{101.5/(array*0.5):.0f} deg")
            print("  NOTE: an array needs a corporate feed network (Wilkinson or")
            print("        quarter-wave splitters) — build and verify ONE element first.")
        print("=" * 66)
        print("\n  Why Vivaldi and not a patch: an FMCW radar must stay matched across")
        print(f"  the whole {bw:.1f} % sweep. FR4 patches manage ~1-3 %. Vivaldi does octaves.")
        print("  Why not keep the coffee cans: they work, but they are ~9 dBi with a")
        print("  wide beam, they are bulky, and you cannot array them. A PCB Vivaldi")
        print("  is flat, repeatable, and orderable from the same fab as your FC.\n")

    # --- export ---
    def svg(self, path, array=1):
        """Write the flare outline as SVG (mm units) for KiCad/Inkscape import."""
        bx, by = self.board
        pitch = C / ((self.f_low + self.f_high) / 2) * 1000 * 0.5
        total_w = (array - 1) * pitch + by
        up = self.taper()
        feed_x = -20.0
        parts = []
        for k in range(array):
            yoff = total_w / 2 + (k - (array - 1) / 2) * pitch
            top = " ".join(f"{x+25:.2f},{yoff - y:.2f}" for x, y in up)
            bot = " ".join(f"{x+25:.2f},{yoff + y:.2f}" for x, y in reversed(up))
            # closed slot region: upper edge -> across mouth -> lower edge
            parts.append(
                f'<polygon points="{top} {self.L+25:.2f},{yoff-by/2:.2f} '
                f'{feed_x+25:.2f},{yoff-by/2:.2f} {feed_x+25:.2f},{yoff+by/2:.2f} '
                f'{self.L+25:.2f},{yoff+by/2:.2f} {bot}" '
                f'fill="#b87333" stroke="#333" stroke-width="0.2"/>')
            parts.append(
                f'<rect x="{feed_x+25-6:.2f}" y="{yoff-self.feed_w/2:.2f}" '
                f'width="6" height="{self.feed_w:.2f}" fill="#e0a030"/>')
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{bx+30:.0f}mm" '
               f'height="{total_w+10:.0f}mm" viewBox="0 -5 {bx+30:.2f} {total_w+10:.2f}">'
               f'<rect x="0" y="-5" width="{bx+30:.2f}" height="{total_w+10:.2f}" fill="#0d5c2f"/>'
               + "".join(parts) +
               f'<text x="4" y="{total_w+3:.2f}" font-size="4" fill="#fff">'
               f'Vivaldi {self.f_low/1e9:.2f}-{self.f_high/1e9:.2f} GHz  '
               f'W={self.W:.0f} L={self.L:.0f} FR4 {self.h}mm  x{array}</text></svg>')
        open(path, "w").write(svg)
        print(f"  wrote {path}  ({bx+30:.0f} x {total_w+10:.0f} mm)")
        print("  Import into KiCad: File > Import > Graphics, set scale 1:1, place the")
        print("  copper polygon on F.Cu and the board outline on Edge.Cuts.")

    def openems(self):
        print(f"""
# --- openEMS verification script (save as viv_sim.py, run with python) -------
# Install: https://docs.openems.de   (needs openEMS + CSXCAD python bindings)
from openEMS import openEMS
from CSXCAD import ContinuousStructure
import numpy as np

f0, fc = {(self.f_low+self.f_high)/2:.3e}, {(self.f_high-self.f_low):.3e}
FDTD = openEMS(NrTS=60000, EndCriteria=1e-4)
FDTD.SetGaussExcite(f0, fc)
FDTD.SetBoundaryCond(['MUR']*6)
CSX = ContinuousStructure(); FDTD.SetCSX(CSX)

sub = CSX.AddMaterial('FR4', epsilon={self.er}, kappa=0.001)   # lossy FR4
cu  = CSX.AddMetal('copper')

# board {self.board[0]:.0f} x {self.board[1]:.0f} x {self.h} mm
sub.AddBox([0,-{self.board[1]/2:.1f},0], [{self.board[0]:.1f},{self.board[1]/2:.1f},{self.h}])

# flare polygon (exponential taper) — mirror for the second half
taper = np.array({[(round(x,2), round(y,2)) for x, y in self.taper(40)]})
# ... build the slot as a polygon on the top layer, add the microstrip feed
#     of width {self.feed_w:.2f} mm and a lumped port at the board edge.

mesh = CSX.GetGrid(); mesh.SetDeltaUnit(1e-3)
res = 299792458/(self.f_high)/1e-3/20     # ~lambda/20 cells
# mesh.AddLine('x', ...) etc.

FDTD.Run('/tmp/viv', cleanup=True)
# Post-process: port.CalcPort(...) -> S11;  nf2ff -> gain pattern
# PASS CRITERIA: |S11| < -10 dB across {self.f_low/1e9:.2f}-{self.f_high/1e9:.2f} GHz
# ---------------------------------------------------------------------------
""")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--f-low", type=float, default=2.30, help="lowest freq (GHz)")
    ap.add_argument("--f-high", type=float, default=2.60, help="highest freq (GHz)")
    ap.add_argument("--thickness", type=float, default=1.6, help="FR4 thickness mm")
    ap.add_argument("--array", type=int, default=1, help="number of elements")
    ap.add_argument("--svg", metavar="FILE")
    ap.add_argument("--openems", action="store_true")
    args = ap.parse_args()

    v = Vivaldi(args.f_low, args.f_high, h_mm=args.thickness)
    v.report(array=args.array)
    if args.svg:
        v.svg(args.svg, array=args.array)
    if args.openems:
        v.openems()


if __name__ == "__main__":
    main()
