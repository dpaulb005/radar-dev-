#!/usr/bin/env python3
"""
scan_design.py — getting POSITION out of a coffee-can radar.

The thing that is easy to miss when planning this build: one TX horn plus one
RX horn measures **range and radial velocity, and nothing else**. There is no
angle in that measurement. A target at 8 m dead ahead and a target at 8 m
thirty degrees off-axis produce the identical beat tone. For "where is the
drone" you need angle from somewhere.

This tool compares the three ways to get it and sizes each one.

WHICH ONE THIS PROJECT BUILT, and why the other two are here for reference:
the answer is the two-receiver interferometer. Mechanical scanning was the
plan and was dropped after measurement -- it cannot give the bearing of a
drone that is flying, because the scan takes seconds and the bearing moves
while it runs (docs/signal-chain.md, "stage 10"). The interferometer reads
bearing inside one 0.47 s dwell at 0.09 deg rms, against 1.5 deg and 4.3 s
for the scan. See docs/azimuth.md and ground_station/interferometer.py.
The sizing below is still correct for what each approach costs.

    python scan_design.py                 # compare the options
    python scan_design.py --interf        # interferometer ambiguity detail
    python scan_design.py --sector 90     # size a mechanical scan
"""

import argparse
import math

C = 299_792_458.0


class RadarFront:
    """The can radar as designed in docs/mit-radar.md + antenna/horn.py."""

    def __init__(self, f_ghz=2.442, bw_mhz=83.5, t_chirp_ms=2.0, n_chirps=64,
                 bw_az_deg=36.0, bw_el_deg=34.0, snr_db=58.0,
                 aperture_mm=264.0):
        self.f = f_ghz * 1e9
        self.bw = bw_mhz * 1e6
        self.t_chirp = t_chirp_ms * 1e-3
        self.n_chirps = n_chirps
        self.bw_az = bw_az_deg
        self.bw_el = bw_el_deg
        self.snr_db = snr_db
        self.aperture = aperture_mm / 1000.0

    @property
    def lam(self):
        return C / self.f

    @property
    def range_res(self):
        return C / (2 * self.bw)

    @property
    def cpi(self):
        """Coherent processing interval — the dwell needed for one measurement."""
        return self.n_chirps * self.t_chirp

    # ---- accuracy (theoretical vs what you will actually get) ----
    def range_accuracy(self, snr_db=None, linearity_frac=0.05):
        """Range accuracy. Theory is SNR-limited; reality is limited by how
        linear your VCO sweep is, which is why we floor it."""
        snr = 10 ** ((self.snr_db if snr_db is None else snr_db) / 10)
        theory = self.range_res / math.sqrt(2 * snr)
        floor = linearity_frac * self.range_res      # VCO sweep nonlinearity
        return max(theory, floor), theory, floor

    def angle_accuracy(self, snr_db=None, pattern_frac=0.05):
        """Angular accuracy from centroiding the beam. Same story: theory is
        SNR-limited, practice is limited by how well you know the pattern and
        how repeatable the servo is."""
        snr = 10 ** ((self.snr_db if snr_db is None else snr_db) / 10)
        theory = self.bw_az / (1.6 * math.sqrt(2 * snr))
        floor = pattern_frac * self.bw_az
        return max(theory, floor), theory, floor

    def cross_range_err(self, r, snr_db=None):
        acc, _, _ = self.angle_accuracy(snr_db)
        return r * math.radians(acc)

    # ---- option 2: mechanical scan ----
    def scan(self, sector_deg=90.0, oversample=3.0, settle_ms=30.0):
        step = self.bw_az / oversample
        n_beams = max(1, int(round(sector_deg / step)) + 1)
        dwell = self.cpi + settle_ms * 1e-3
        sweep = n_beams * dwell
        return dict(step=step, n_beams=n_beams, dwell=dwell,
                    sweep=sweep, rate=1.0 / sweep)

    # ---- option 3: phase interferometry ----
    def interferometer(self, baseline_m=None):
        """Two RX channels, angle from phase difference.

            dphi = 2*pi*d*sin(theta)/lambda

        Unambiguous only while |dphi| <= pi, i.e. |sin(theta)| <= lambda/(2d).
        With big horns the baseline is forced to be large (they physically
        cannot sit closer than one aperture apart), and the unambiguous field
        of view shrinks below the beamwidth -> ambiguous inside your own beam.
        """
        d = self.aperture if baseline_m is None else baseline_m
        ratio = self.lam / (2 * d)
        unamb = math.degrees(math.asin(min(1.0, ratio))) if ratio <= 1 else 90.0
        return dict(baseline=d, baseline_lam=d / self.lam, unamb_half_fov=unamb,
                    ambiguous_in_beam=unamb < self.bw_az / 2)


def compare(rf: RadarFront, sector=90.0, ranges=(5.0, 10.0, 20.0)):
    ra, ra_t, ra_f = rf.range_accuracy()
    aa, aa_t, aa_f = rf.angle_accuracy()
    print("=" * 72)
    print("  GETTING POSITION FROM THE CAN RADAR")
    print("=" * 72)
    print(f"  carrier {rf.f/1e9:.3f} GHz, sweep {rf.bw/1e6:.1f} MHz, "
          f"chirp {rf.t_chirp*1e3:.0f} ms x {rf.n_chirps}")
    print(f"  horn beamwidth {rf.bw_az:.0f} deg az / {rf.bw_el:.0f} deg el, "
          f"aperture {rf.aperture*1000:.0f} mm")
    print(f"  CPI (dwell for one measurement): {rf.cpi*1e3:.0f} ms")
    print("-" * 72)
    print("  WHAT ONE TX + ONE RX HORN ACTUALLY MEASURES")
    print(f"    range          : resolution {rf.range_res:.2f} m, "
          f"accuracy {ra*100:.0f} cm")
    print(f"                     (theory {ra_t*1000:.1f} mm, but VCO sweep "
          f"nonlinearity floors it at {ra_f*100:.0f} cm)")
    print(f"    radial velocity: direct from Doppler, "
          f"{rf.lam/(2*rf.n_chirps*rf.t_chirp):.2f} m/s resolution")
    print(f"    angle          : NONE. This is the whole problem.")
    print()
    print("  A target 8 m dead ahead and one 8 m at 30 deg off-axis give the")
    print("  SAME beat tone. Range alone cannot guide an interceptor.")
    print("=" * 72)

    # --- option 1 ---
    print("\n  OPTION 1 — accept range + velocity only")
    print("    Useful for: closing-rate alarm, altitude-hold assist, a 1-D")
    print("    'how far is it' readout, and Doppler ID of the rotors.")
    print("    Not enough for: position, guidance, interception.")
    print("    Cost: $0.   Verdict: fine as the FIRST milestone, not the end.")

    # --- option 2 ---
    sc = rf.scan(sector)
    print(f"\n  OPTION 2 — mechanically scan the horn pair  [RECOMMENDED]")
    print(f"    servo/stepper sweeps the antennas in azimuth")
    print(f"    beam step {sc['step']:.0f} deg (1/3 beamwidth -- measured sweet spot), "
          f"{sc['n_beams']} positions over a {sector:.0f} deg sector")
    print(f"    dwell {sc['dwell']*1e3:.0f} ms/beam -> sweep {sc['sweep']:.2f} s "
          f"= {sc['rate']:.2f} Hz revisit")
    print(f"    angular accuracy by centroiding: {aa:.1f} deg "
          f"(theory {aa_t:.2f}, floored at {aa_f:.1f})")
    print(f"    cross-range error:")
    for r in ranges:
        print(f"       at {r:>4.0f} m : {rf.cross_range_err(r):.2f} m "
              f"(range err {ra*100:.0f} cm)")
    print(f"    Cost: ~$15 servo + bracket.  Gives a true PPI, which is exactly")
    print(f"    what the console's scope already draws.")

    # --- option 3 ---
    it = rf.interferometer()
    print(f"\n  OPTION 3 — two RX channels, angle from phase")
    print(f"    baseline forced by horn size: {it['baseline']*1000:.0f} mm "
          f"= {it['baseline_lam']:.2f} lambda")
    print(f"    unambiguous only within +/-{it['unamb_half_fov']:.1f} deg, "
          f"but the beam is +/-{rf.bw_az/2:.0f} deg")
    if it["ambiguous_in_beam"]:
        print(f"    >> AMBIGUOUS INSIDE ITS OWN BEAM. Two horns physically cannot")
        print(f"       sit closer than one aperture apart, so you get grating")
        print(f"       lobes: several candidate angles for one target.")
        print(f"    Fix: horn for TX (gain), and a pair of SMALL elements spaced")
        print(f"       lambda/2 = {rf.lam/2*1000:.0f} mm for RX angle.")
        small = rf.interferometer(rf.lam / 2)
        print(f"       -> unambiguous +/-{small['unamb_half_fov']:.0f} deg. Clean.")
    print(f"    Cost: ~$116 (second mixer + LNA) + a 2nd ADC channel.")
    print(f"    Faster than scanning, but more RF to get right.")

    print("\n" + "=" * 72)
    print("  RECOMMENDATION")
    print("=" * 72)
    print("  What this project actually built, after measuring all three:")
    print("   1. Range + Doppler only, three horns bolted into their final")
    print("      frame with one receive chain populated. Prove the RF chain")
    print("      against a walking person.")
    print("   2. The SECOND RECEIVER. Bearing from the phase between the two,")
    print("      inside one 0.47 s dwell: 0.09 deg rms. This is stage 2.")
    print("   3. A turntable only if you want a sector wider than the 34 deg")
    print("      beam. It points; it takes no part in the measurement.")
    print("")
    print("  Scanning was the plan and was DROPPED. It is not the cheap path to")
    print("  position, it is a path to the position of a target that is not")
    print("  moving: the scan takes seconds and the bearing moves while it runs,")
    print("  so at 10 m a 4.3 s scan needs the drone under 0.10 m/s. Spending")
    print("  the same seconds on a longer dwell beats more beams tenfold, and")
    print("  neither survives a flying target. See docs/signal-chain.md and")
    print("  docs/azimuth.md; the interferometer is ground_station/interferometer.py.")
    print("")
    print("  One correction to the sizing above: with all three horns ROTATED")
    print("  90 deg the two receivers touch at a 193 mm baseline, which is")
    print("  unambiguous to +/-18.4 deg and covers the 17 deg half-beam. The")
    print("  grating-lobe warning applies to the UN-rotated 263.8 mm spacing.")


def track_while_scan(rf: RadarFront, sector=90.0):
    """Acquire by scanning, then dither the beam on the target."""
    sc = rf.scan(sector)
    dither = 2 * (rf.cpi + 0.03)
    print("\n  TRACK-WHILE-SCAN vs LOCKED DITHER")
    print(f"    full {sector:.0f} deg search sweep : {sc['sweep']:.2f} s "
          f"({sc['rate']:.2f} Hz)")
    print(f"    locked 2-position dither    : {dither:.2f} s "
          f"({1/dither:.1f} Hz)  <- {sc['sweep']/dither:.1f}x faster")
    print(f"    Sequential lobing also sharpens angle well past the beamwidth,")
    print(f"    because you compare amplitudes either side of the target rather")
    print(f"    than reading the peak position.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sector", type=float, default=90.0)
    ap.add_argument("--snr", type=float, default=58.0)
    ap.add_argument("--beamwidth", type=float, default=36.0)
    ap.add_argument("--interf", action="store_true")
    args = ap.parse_args()
    rf = RadarFront(snr_db=args.snr, bw_az_deg=args.beamwidth)
    compare(rf, args.sector)
    track_while_scan(rf, args.sector)
    if args.interf:
        print("\n  INTERFEROMETER BASELINE SWEEP")
        print(f"  {'baseline':>10} {'lambda':>7} | {'unambiguous':>12} | verdict")
        for d_mm in (61, 100, 150, 200, 264, 400):
            r = rf.interferometer(d_mm / 1000)
            v = "ambiguous in beam" if r["ambiguous_in_beam"] else "clean"
            print(f"  {d_mm:>8} mm {r['baseline_lam']:>6.2f} | "
                  f"+/-{r['unamb_half_fov']:>8.1f} deg | {v}")


if __name__ == "__main__":
    main()
