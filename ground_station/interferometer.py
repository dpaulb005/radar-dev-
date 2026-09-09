#!/usr/bin/env python3
"""interferometer.py — azimuth from two receive antennas, in one dwell.

Scanning the horns and comparing amplitudes across beam positions cannot give
the bearing of a drone that is flying: the scan takes seconds and the bearing
moves while it runs (measured in docs/signal-chain.md § stage 10). This module
measures bearing across *space* instead of across time.

    Δφ = 2π · d · sin(θ) / λ            θ = asin( Δφ · λ / (2π · d) )

Two receivers a baseline `d` apart see the same echo with a path difference of
d·sin(θ), so the phase between them is the bearing. It is read at the target's
own range–Doppler cell, inside one 0.47 s dwell, with nothing moving.

Two wiring options are supported, both giving the same call:

  SIMULTANEOUS  two receive chains, two beat channels on one sample clock.
                Nothing to correct. `Interferometer.bearing(rd_a, rd_b, ...)`.

  SWITCHED      one chain, an RF switch alternating antennas chirp by chirp.
                Antenna B is then sampled one PRI later than A, and the target
                has moved in that time, so the round-trip motion phase
                4π·v·PRI/λ is subtracted. `tdm_split()` then the same call with
                `v_mps` given.

Calibration is one constant. Two receive paths are never phase-identical: 1 mm
of extra coax is 4.3° at 2.46 GHz (the wave sees the 84.7 mm wavelength inside
PTFE, not the 121.9 mm one in air), which is 0.43° of bearing. Point the array
at a reflector on boresight, call `calibrate()`, and the offset is removed from
then on.

Self-test:  python3 interferometer.py --selftest
"""

from __future__ import annotations

import json
import math
import pathlib

import numpy as np

C = 2.99792458e8
VF_PTFE = 0.695          # RG316 / RG405: a wave is ~30 % slower inside the cable

# The horns' E-plane aperture, which is how close two of them can physically sit
# once all three are rotated 90° (docs/radar-hardware.md § 7).
DEFAULT_BASELINE_M = 0.1931


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def wavelength(f0_hz: float, bw_hz: float) -> float:
    """Wavelength at the centre of the sweep, which is what the phase sees."""
    return C / (f0_hz + bw_hz / 2.0)


def coax_mm_to_deg(mm: float, lam_free_m: float) -> float:
    """Phase error from a cable-length mismatch. Uses the wavelength *in* the
    coax, which is the mistake that is easy to make and costs a factor of 1.4."""
    return 360.0 * (mm / 1000.0) / (lam_free_m * VF_PTFE)


def max_unambiguous_baseline(lam_m: float, half_beam_deg: float) -> float:
    """Largest baseline whose phase still stays inside ±π across the beam."""
    return lam_m / (2.0 * math.sin(math.radians(half_beam_deg)))


def wrap_pi(x):
    return (x + math.pi) % (2.0 * math.pi) - math.pi


def tdm_split(cube: np.ndarray, parity: int = 0):
    """Switched mode: pull the two antennas' chirps apart.

    parity : the row index of the first antenna-A chirp, from tdm_parity().
             Get this wrong and every bearing comes out negated.

    Returns (cube_a, cube_b), each half as many chirps, both the same length.
    The effective PRI doubles, so the unambiguous velocity halves; bearing
    does not care, but the caller must rescale its Doppler axis.
    """
    p = int(parity) % 2
    a = cube[p::2]
    b = cube[1 - p::2]
    n = min(a.shape[0], b.shape[0])
    return a[:n].copy(), b[:n].copy()


def tdm_parity(edges, tol=0.35):
    """Which cube row came from antenna A, in switched mode.

    A block of audio starts at an arbitrary point in the A/B alternation, so
    row parity is NOT knowable from the data alone — read antenna B as A and
    every bearing comes out with the wrong sign. radar_ctl therefore marks the
    start of each block by holding SYNC low for one extra retrace before it
    returns the switch to antenna A. That doubled gap is unmistakable in the
    edge times, and the chirp after it is antenna A.

    edges : rising-edge sample indices from segment_chirps(..., return_edges=True)
    Returns 0 or 1 (the row index of the first antenna-A chirp), or None when
    no marker is present — in which case the caller must not guess.
    """
    if edges is None or len(edges) < 4:
        return None
    gaps = np.diff(np.asarray(edges, dtype=float))
    med = float(np.median(gaps))
    if med <= 0:
        return None
    long_at = np.flatnonzero(gaps > med * (1.0 + tol))
    if long_at.size == 0:
        return None
    # the chirp AFTER the long gap is antenna A
    return int((long_at[0] + 1) % 2)


def motion_phase(v_mps: float, pri_s: float, lam_m: float) -> float:
    """Round-trip phase a target accumulates in one PRI. In switched mode
    antenna B is sampled one PRI after A, so this rides on top of the bearing
    and has to come off. Sign follows the same convention as the range walk:
    a target whose range grows adds phase."""
    return 4.0 * math.pi * v_mps * pri_s / lam_m


# ----------------------------------------------------------------------
# the measurement
# ----------------------------------------------------------------------
class Interferometer:
    """Bearing from the phase between two receivers.

    baseline_m : centre-to-centre spacing of the two receive antennas
    f0_hz, bw_hz : the sweep, used only for the centre wavelength
    cal_rad : fixed phase offset of chain B relative to chain A (cables, LNAs,
              mixers). Set it with calibrate(), or load it from disk.
    """

    def __init__(self, baseline_m=DEFAULT_BASELINE_M, f0_hz=2.440e9, bw_hz=40e6,
                 cal_rad=0.0):
        if baseline_m <= 0:
            raise ValueError("baseline must be positive")
        self.d = float(baseline_m)
        self.lam = wavelength(f0_hz, bw_hz)
        self.cal = float(cal_rad)
        self.f0_hz, self.bw_hz = float(f0_hz), float(bw_hz)

    # -- geometry ------------------------------------------------------
    @property
    def unambiguous_deg(self) -> float:
        """Half-angle inside which the phase does not wrap."""
        s = self.lam / (2.0 * self.d)
        return 90.0 if s >= 1.0 else math.degrees(math.asin(s))

    @property
    def deg_bearing_per_deg_phase(self) -> float:
        """Bearing sensitivity at boresight, in degrees of angle per degree of
        phase. Multiply by coax_mm_to_deg() for degrees of bearing per mm of
        cable mismatch."""
        return self.lam / (2.0 * math.pi * self.d)

    def bearing_error_per_mm_coax(self) -> float:
        """How much bearing one millimetre of cable mismatch costs."""
        return coax_mm_to_deg(1.0, self.lam) * self.deg_bearing_per_deg_phase

    def bearing_from_phase(self, dphi_rad: float):
        """Angle for a (already calibrated and motion-corrected) phase.
        Returns None when the phase lands outside the unambiguous cone."""
        s = wrap_pi(dphi_rad) * self.lam / (2.0 * math.pi * self.d)
        if abs(s) > 1.0:
            return None
        return math.degrees(math.asin(s))

    def phase_for_bearing(self, az_deg: float) -> float:
        """The inverse, for tests and for building synthetic data."""
        return 2.0 * math.pi * self.d * math.sin(math.radians(az_deg)) / self.lam

    # -- the measurement ----------------------------------------------
    def phase_at(self, rd_a, rd_b, vi, ri, v_mps=None, pri_s=None) -> float:
        """Calibrated phase difference at one range–Doppler cell.

        rd_a, rd_b : COMPLEX range-Doppler maps, same shape, same cell grid.
        vi, ri     : the cell (Doppler index, range index).
        v_mps/pri_s: switched mode only — removes the one-PRI motion phase.
        """
        a = complex(rd_a[vi, ri])
        b = complex(rd_b[vi, ri])
        dphi = np.angle(b * np.conj(a)) - self.cal
        if v_mps is not None and pri_s is not None:
            dphi -= motion_phase(v_mps, pri_s, self.lam)
        return wrap_pi(dphi)

    def bearing(self, rd_a, rd_b, vi, ri, v_mps=None, pri_s=None):
        """Bearing in degrees at one range–Doppler cell, or None if ambiguous."""
        return self.bearing_from_phase(
            self.phase_at(rd_a, rd_b, vi, ri, v_mps=v_mps, pri_s=pri_s))

    def quality(self, rd_a, rd_b, vi, ri) -> float:
        """0..1 confidence in this cell's phase: how equal the two channels
        are in magnitude. A cell where one channel is much stronger is a cell
        where one of them is measuring noise."""
        ma, mb = abs(complex(rd_a[vi, ri])), abs(complex(rd_b[vi, ri]))
        if ma <= 0 or mb <= 0:
            return 0.0
        return float(min(ma, mb) / max(ma, mb))

    # -- calibration ---------------------------------------------------
    def calibrate(self, rd_a, rd_b, vi, ri, true_az_deg=0.0,
                  v_mps=None, pri_s=None) -> float:
        """Point at a reflector whose bearing you know (boresight is easiest)
        and call this. Stores and returns the fixed offset in radians."""
        a = complex(rd_a[vi, ri])
        b = complex(rd_b[vi, ri])
        measured = np.angle(b * np.conj(a))
        if v_mps is not None and pri_s is not None:
            measured -= motion_phase(v_mps, pri_s, self.lam)
        self.cal = float(wrap_pi(measured - self.phase_for_bearing(true_az_deg)))
        return self.cal

    def save(self, path):
        pathlib.Path(path).write_text(json.dumps({
            "cal_rad": self.cal, "cal_deg": math.degrees(self.cal),
            "baseline_m": self.d, "f0_hz": self.f0_hz, "bw_hz": self.bw_hz,
            "lam_m": self.lam, "unambiguous_deg": self.unambiguous_deg,
        }, indent=1) + "\n")
        return path

    @classmethod
    def load(cls, path, **override):
        d = json.loads(pathlib.Path(path).read_text())
        return cls(baseline_m=override.get("baseline_m", d["baseline_m"]),
                   f0_hz=override.get("f0_hz", d["f0_hz"]),
                   bw_hz=override.get("bw_hz", d["bw_hz"]),
                   cal_rad=d["cal_rad"])


# ----------------------------------------------------------------------
# putting a bearing on every detection
# ----------------------------------------------------------------------
def cell_of(ranges, vels, r_m, v_mps):
    """Nearest range–Doppler cell to a detection's (range, velocity)."""
    return int(np.argmin(np.abs(vels - v_mps))), int(np.argmin(np.abs(ranges - r_m)))


def switched_v_max(pri_s: float, lam_m: float) -> float:
    """Unambiguous velocity in switched mode.

    Taking every other chirp doubles the effective PRI, so this is HALF the
    simultaneous figure. It matters more than it looks: past this speed the
    reported velocity folds, and in switched mode the velocity is what the
    motion correction is built from, so a folded velocity does not just make
    the velocity wrong — it makes the BEARING wrong, by up to a whole beam.
    """
    return lam_m / (4.0 * 2.0 * pri_s)


def add_bearings(dets, rd_a, rd_b, ranges, vels, interf,
                 v_mps_for_tdm=None, pri_s=None, min_quality=0.25,
                 v_guard=0.80):
    """Attach an azimuth to each (range, vel, snr, level) detection.

    Returns a list of dicts. `az` is None, with `az_reason` saying why, when:

      ambiguous       the phase fell outside the unambiguous cone,
      low-quality     one channel is much weaker than the other at that cell,
                      so at least one of them is measuring noise,
      velocity-fold   switched mode only: the target is reported close enough
                      to the folding velocity that its measured speed cannot be
                      trusted, and therefore neither can the motion correction
                      built from it.

    A caution about that last one, because it is a real limit and not a
    conservative one. Switched mode throws away every other chirp, so its
    unambiguous velocity is HALF the simultaneous figure — 2.06 m/s at a
    7.4 ms PRI. Past it the velocity folds, and because the motion correction
    is computed FROM the velocity, a folded target does not merely report the
    wrong speed: it reports a bearing that can be a whole beamwidth out. The
    guard here catches targets REPORTED near the fold. It cannot catch one
    that has folded to a small apparent velocity, and no processing of these
    two sub-cubes can: alternating the antenna every chirp puts a second
    Doppler line exactly half a span away whatever the true velocity is, so
    the folded and unfolded cases are indistinguishable in the data. This is
    the strongest argument for building the simultaneous version, which has
    the full +/-4.12 m/s and needs no correction at all.

    Reporting no bearing is always better than reporting a wrong one.
    """
    vmax = (switched_v_max(pri_s, interf.lam)
            if (v_mps_for_tdm and pri_s) else None)
    out = []
    for d in dets:
        r, v, snr = float(d[0]), float(d[1]), float(d[2])
        lvl = float(d[3]) if len(d) > 3 else snr
        vi, ri = cell_of(ranges, vels, r, v)
        q = interf.quality(rd_a, rd_b, vi, ri)
        az, why = None, None
        if q < min_quality:
            why = "low-quality"
        elif vmax is not None and abs(v) > v_guard * vmax:
            why = "velocity-fold"
        else:
            az = interf.bearing(rd_a, rd_b, vi, ri,
                                v_mps=(v if v_mps_for_tdm else None),
                                pri_s=(pri_s if v_mps_for_tdm else None))
            if az is None:
                why = "ambiguous"
        rec = dict(range=r, vel=v, snr=snr, level=lvl, az=az, quality=q,
                   az_reason=why)
        if az is not None:
            rec["x"] = r * math.cos(math.radians(az))
            rec["y"] = r * math.sin(math.radians(az))
        out.append(rec)
    return out


# ----------------------------------------------------------------------
# self-test — no hardware, no sound card
# ----------------------------------------------------------------------
def _selftest(verbose=True):
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        ok = ok and bool(cond)
        if verbose:
            print(f"  {'PASS' if cond else 'FAIL'}  {name}{'  ' + detail if detail else ''}")

    lam = wavelength(2.440e9, 40e6)
    check("wavelength at 2460 MHz", abs(lam - 0.12187) < 1e-4, f"{lam*1000:.2f} mm")

    I = Interferometer()
    check("unambiguous cone covers the 17 deg half-beam",
          I.unambiguous_deg > 17.0, f"+/-{I.unambiguous_deg:.2f} deg")
    check("un-rotated horns would NOT cover it",
          Interferometer(baseline_m=0.2638).unambiguous_deg < 17.0,
          f"+/-{Interferometer(baseline_m=0.2638).unambiguous_deg:.2f} deg at 263.8 mm")
    check("max baseline for a 17 deg half-beam",
          abs(max_unambiguous_baseline(lam, 17.0) - 0.2084) < 1e-3,
          f"{max_unambiguous_baseline(lam, 17.0)*1000:.1f} mm")
    check("1 mm of coax", abs(coax_mm_to_deg(1.0, lam) - 4.25) < 0.05,
          f"{coax_mm_to_deg(1.0, lam):.2f} deg")

    # round trip: bearing -> phase -> bearing
    worst = 0.0
    for az in np.arange(-18.0, 18.01, 0.5):
        got = I.bearing_from_phase(I.phase_for_bearing(az))
        worst = max(worst, abs(got - az))
    check("phase round-trip over +/-18 deg", worst < 1e-9, f"worst {worst:.2e} deg")

    # ambiguity is reported, not guessed
    beyond = I.phase_for_bearing(45.0)          # outside the cone: wraps
    check("phase outside the cone is flagged",
          I.bearing_from_phase(beyond) is None or abs(I.bearing_from_phase(beyond) - 45.0) > 1.0)

    # synthetic two-channel cells, with a known offset to calibrate away
    rng = np.random.default_rng(7)
    n_v, n_r = 64, 146
    vi, ri = 20, 11
    offset = math.radians(37.0)                 # a cable mismatch
    for truth in (-15.0, -7.5, 0.0, 7.5, 15.0):
        a = np.zeros((n_v, n_r), complex)
        b = np.zeros((n_v, n_r), complex)
        amp = 1.0
        a[vi, ri] = amp * np.exp(1j * 0.9)
        b[vi, ri] = amp * np.exp(1j * (0.9 + I.phase_for_bearing(truth) + offset))
        # calibrate once on a boresight target, then measure
        cal_a = np.zeros_like(a); cal_b = np.zeros_like(b)
        cal_a[vi, ri] = np.exp(1j * 0.3)
        cal_b[vi, ri] = np.exp(1j * (0.3 + offset))
        K = Interferometer()
        K.calibrate(cal_a, cal_b, vi, ri, true_az_deg=0.0)
        got = K.bearing(a, b, vi, ri)
        check(f"calibrated bearing at {truth:+.1f} deg",
              got is not None and abs(got - truth) < 1e-6,
              f"got {got:+.4f}" if got is not None else "ambiguous")

    # switched mode: the one-PRI motion phase must come off
    pri, v = 7.4e-3, -1.8
    truth = 9.0
    a = np.zeros((n_v, n_r), complex); b = np.zeros((n_v, n_r), complex)
    a[vi, ri] = 1.0
    b[vi, ri] = np.exp(1j * (I.phase_for_bearing(truth) + motion_phase(v, pri, I.lam)))
    naive = I.bearing(a, b, vi, ri)
    fixed = I.bearing(a, b, vi, ri, v_mps=v, pri_s=pri)
    check("switched mode without correction is wrong",
          naive is not None and abs(naive - truth) > 2.0, f"{naive:+.2f} deg")
    check("switched mode with correction is right",
          fixed is not None and abs(fixed - truth) < 1e-6, f"{fixed:+.2f} deg")

    # tdm_split really interleaves
    cube = np.arange(8 * 3, dtype=float).reshape(8, 3)
    ca, cb = tdm_split(cube)
    check("tdm_split takes even/odd chirps",
          np.array_equal(ca, cube[0::2]) and np.array_equal(cb, cube[1::2]))

    # quality gate rejects a cell where one channel is dead
    a2 = np.zeros((4, 4), complex); b2 = np.zeros((4, 4), complex)
    a2[1, 1] = 1.0; b2[1, 1] = 0.01
    check("quality flags a one-sided cell", I.quality(a2, b2, 1, 1) < 0.25,
          f"q={I.quality(a2, b2, 1, 1):.3f}")

    # add_bearings shape and gating
    dets = [(10.0, -1.8, 40.0, -3.0)]
    ranges = np.linspace(0, 40, n_r); vels = np.linspace(-4, 4, n_v)
    A = np.zeros((n_v, n_r), complex); B = np.zeros((n_v, n_r), complex)
    cv, cr = cell_of(ranges, vels, 10.0, -1.8)
    A[cv, cr] = 1.0
    B[cv, cr] = np.exp(1j * I.phase_for_bearing(-6.0))
    recs = add_bearings(dets, A, B, ranges, vels, I)
    check("add_bearings returns a bearing",
          recs[0]["az"] is not None and abs(recs[0]["az"] + 6.0) < 1e-6,
          f"az {recs[0]['az']:+.3f}" if recs[0]["az"] is not None else "")
    check("add_bearings gives cartesian too",
          abs(recs[0]["x"] - 10 * math.cos(math.radians(-6))) < 1e-9)

    # save / load round trip
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "cal.json"
        K.save(p)
        L = Interferometer.load(p)
        check("calibration survives save/load", abs(L.cal - K.cal) < 1e-12)

    if verbose:
        print(f"\n  baseline {I.d*1000:.1f} mm, lambda {I.lam*1000:.2f} mm, "
              f"unambiguous +/-{I.unambiguous_deg:.2f} deg")
        print(f"  1 mm of coax mismatch = {coax_mm_to_deg(1, I.lam):.2f} deg phase "
              f"= {I.bearing_error_per_mm_coax():.3f} deg bearing")
        print(f"  the 2.5 deg budget is spent at "
              f"{2.5 / I.bearing_error_per_mm_coax():.1f} mm of mismatch")
        print(f"\n  {'ALL PASS' if ok else 'FAILURES ABOVE'}")
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if _selftest() else 1)
