#!/usr/bin/env python3
"""test_stage2.py — the STAGE-2 regression suite. No hardware, no pytest, no network.

    python3 test_stage2.py            run everything
    python3 test_stage2.py -v         print every case
    python3 test_stage2.py azimuth    run only groups whose name matches

Exit status is 0 only if every case passes. These are the azimuth cases out of
ground_station/test_radar.py, moved here with the code they test. Stage 2 is not
built -- one TX horn and TWO RX horns -- so this suite is what says the code is
still correct the day it is. It drives acquire_az.py, and the stage-1 modules it
needs (fmcw_sim, dsp, synth, radar_acquire) come from ../ground_station.

What it covers, and why each one is here:

  geometry      the numbers the hardware was built around: the baseline that
                makes the pair unambiguous, the one that does not, and what a
                millimetre of coax costs. If someone "tidies" a constant these
                fail before the radar does.
  azimuth       the interferometer end to end through acquire_az, across the
                beam and across velocity, in both wirings.
  calibration   an injected chain offset is measured, stored, reloaded and
                removed.
  refusal       the cases where the right answer is "no bearing": ambiguous
                phase, a one-sided cell, and switched mode near its velocity
                fold. A radar that guesses is worse than one that abstains.
  limits        the documented limits are real: the switched fold is half the
                simultaneous one, and the un-rotated horn spacing genuinely
                wraps inside the beam.
"""

import math
import pathlib
import subprocess
import sys
import tempfile

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parent / "ground_station"))

import acquire_az as A                                            # noqa: E402
import interferometer as I                                        # noqa: E402
import synth as S                                                 # noqa: E402

FS, T_UP, RETRACE, N = 48_000.0, 6.4e-3, 1.0e-3, 64
F0, BW = 2.400e9, 83.5e6
PASS, FAIL = [], []
VERBOSE = "-v" in sys.argv


def check(group, name, cond, detail=""):
    (PASS if cond else FAIL).append(f"{group}: {name}")
    if VERBOSE or not cond:
        print(f"  {'pass' if cond else 'FAIL'}  {group:<12} {name}"
              f"{'   ' + detail if detail else ''}")


def cli(*extra):
    """Run acquire_az's self-test and return (ok, last_line)."""
    p = subprocess.run([sys.executable, "acquire_az.py", "--selftest",
                        "--f0-mhz", "2400", "--bw-mhz", "83.5", *map(str, extra)],
                       cwd=HERE, capture_output=True, text=True)
    line = (p.stdout.strip().splitlines() or [""])[-1]
    return p.returncode == 0, line


_ERR_RE = __import__("re").compile(r"error\s+([0-9.]+)")


def az_error(line):
    """The absolute azimuth error the self-test printed."""
    m = _ERR_RE.search(line)
    return float(m.group(1)) if m else float("nan")


# ======================================================================
def test_geometry():
    g = "geometry"
    J = I.Interferometer()
    check(g, "193 mm pair clears the 17 deg half-beam", J.unambiguous_deg > 17.0,
          f"+/-{J.unambiguous_deg:.2f} deg")
    check(g, "263.8 mm pair does NOT",
          I.Interferometer(baseline_m=0.2638).unambiguous_deg < 17.0,
          f"+/-{I.Interferometer(baseline_m=0.2638).unambiguous_deg:.2f} deg "
          "-- this is why all three horns are rotated 90 deg")
    check(g, "max baseline for the beam",
          abs(I.max_unambiguous_baseline(J.lam, 17.0) - 0.2084) < 1e-3,
          f"{I.max_unambiguous_baseline(J.lam, 17.0)*1000:.1f} mm")
    check(g, "1 mm of coax is 4.25 deg, not 2.95",
          abs(I.coax_mm_to_deg(1.0, J.lam) - 4.25) < 0.05,
          "uses the wavelength inside PTFE")
    check(g, "1 mm of coax costs 0.43 deg of bearing",
          abs(J.bearing_error_per_mm_coax() - 0.427) < 0.01)
    check(g, "the 2.5 deg budget survives ~6 mm of mismatch",
          5.0 < 2.5 / J.bearing_error_per_mm_coax() < 7.0)
    worst = max(abs(J.bearing_from_phase(J.phase_for_bearing(a)) - a)
                for a in np.arange(-18, 18.01, 0.25))
    check(g, "phase round-trip is exact over the whole cone", worst < 1e-9)


def test_azimuth():
    g = "azimuth"
    for mode in ("--interferometer", "--switched"):
        errs, bad = [], 0
        for az in (-16, -12, -8, -4, 0, 4, 8, 12, 16):
            for v in (-1.4, -0.7, 0.9, 1.4):
                ok, line = cli(mode, "--st-range", "10", "--st-az", str(az),
                               "--st-vel", str(v))
                if not ok:
                    bad += 1
                    if VERBOSE:
                        print("      ", line)
                else:
                    e = az_error(line)
                    if not math.isnan(e):
                        errs.append(e)
        tag = mode.lstrip("-")
        # Simultaneous must answer every time. Switched is allowed to ABSTAIN --
        # never to be wrong. On the 83.5 MHz sweep it declines two of the 36, both
        # at the beam edge (+/-16 deg) at the slowest velocity (-0.7 m/s): the
        # alternation puts a second Doppler line half a span away, CFAR ranks that
        # folded line strongest, and the velocity-fold guard refuses to read a
        # bearing off it. At 40 MHz CFAR also surfaced the true-velocity peak, so
        # a usable detection survived. This is switched mode's documented limit
        # (radar-software.md § 6) with the boundary moved, not a new failure -- and
        # it is one more reason the simultaneous build is the one to make.
        allowed = 0 if mode == "--interferometer" else 2
        check(g, f"{tag}: 36 bearings across the beam", bad <= allowed,
              f"{36 - bad}/36 answered"
              + (f", {bad} abstained (<= {allowed} allowed)" if bad else "")
              + f", worst error {max(errs) if errs else float('nan'):.2f} deg")
        check(g, f"{tag}: inside the 2.5 deg budget",
              bool(errs) and max(errs) < 2.5, f"worst {max(errs):.2f} deg" if errs else "")

    ok, line = cli("--interferometer", "--st-range", "10", "--st-az", "-8",
                   "--st-vel", "-1.8")
    check(g, "simultaneous is far better than the budget, not merely inside it",
          ok and az_error(line) < 0.2, line.split(":")[-1].strip())


def test_calibration():
    g = "calibration"
    with tempfile.TemporaryDirectory() as td:
        cal = str(pathlib.Path(td) / "cal.json")
        ok, line = cli("--interferometer", "--st-range", "10", "--st-az", "-8",
                       "--st-vel", "-1.8", "--st-cal-deg", "37",
                       "--cal-file", str(pathlib.Path(td) / "absent.json"))
        check(g, "an uncalibrated 37 deg chain offset is caught", not ok,
              f"error {az_error(line):.2f} deg, close to 37 x 0.1")

        ok, _ = cli("--interferometer", "--st-range", "10", "--st-az", "0",
                    "--st-vel", "-1.8", "--st-cal-deg", "37", "--calibrate",
                    "--cal-file", cal)
        check(g, "calibrating on a boresight reflector succeeds", ok)
        import json
        d = json.loads(pathlib.Path(cal).read_text())
        check(g, "the stored constant is the injected one",
              abs(d["cal_deg"] - 37.0) < 0.5, f"{d['cal_deg']:.2f} deg")

        ok, line = cli("--interferometer", "--st-range", "10", "--st-az", "-8",
                       "--st-vel", "-1.8", "--st-cal-deg", "37", "--cal-file", cal)
        check(g, "reloading it removes the offset", ok and az_error(line) < 0.2, line)

        J = I.Interferometer.load(cal)
        check(g, "load() round-trips", abs(math.degrees(J.cal) - 37.0) < 0.5)


def test_refusal():
    g = "refusal"
    J = I.Interferometer()
    beyond = J.phase_for_bearing(45.0)
    got = J.bearing_from_phase(beyond)
    check(g, "a wrapped phase is not reported as a bearing",
          got is None or abs(got - 45.0) > 1.0)

    a = np.zeros((4, 4), complex); b = np.zeros((4, 4), complex)
    a[1, 1] = 1.0; b[1, 1] = 0.01
    recs = I.add_bearings([(10.0, -1.0, 30.0, -3.0)],
                          a, b, np.linspace(0, 40, 4), np.linspace(-4, 4, 4), J)
    check(g, "a one-sided cell reports no bearing",
          recs[0]["az"] is None and recs[0]["az_reason"] == "low-quality")

    # switched mode near its fold must abstain rather than guess
    ok, line = cli("--switched", "--st-range", "10", "--st-az", "-8", "--st-vel", "-1.9")
    check(g, "switched abstains near the velocity fold",
          ok and "refusal" in line, line)

    # and the fix is never a weaker sidelobe standing in for the real target
    src = S.SynthSource(FS, T_UP, N, [(10.0, -8.0, -1.8, 0.0026)],
                        retrace_s=RETRACE, f0=F0, bw=BW, n_rx=2, seed=4)
    beats, sync = src.read()
    _, timing, rds, rg, vl, dets = A._maps(beats, sync, FS, N, None, F0, BW, 15.0)
    recs = I.add_bearings(dets, rds[0], rds[1], rg, vl, J)
    strongest = max(recs, key=lambda r: r["level"])
    check(g, "the strongest return is the real target, not a sidelobe",
          abs(strongest["range"] - 9.6) < 1.0, f"{strongest['range']:.2f} m")


def test_limits():
    g = "limits"
    J = I.Interferometer()
    pri = T_UP + RETRACE
    v_sim = J.lam / (4 * pri)
    v_sw = I.switched_v_max(pri, J.lam)
    check(g, "switched velocity limit is exactly half the simultaneous one",
          abs(v_sw - v_sim / 2) < 1e-9, f"+/-{v_sw:.2f} vs +/-{v_sim:.2f} m/s")

    # the frame marker is what makes switched mode possible at all
    src = S.SynthSource(FS, T_UP, N, [(10.0, -8.0, -1.8, 0.0026)],
                        retrace_s=RETRACE, f0=F0, bw=BW, switched=True, seed=5)
    beats, sync = src.read()
    _, _, edges = S.segment_chirps(beats[0], sync, FS, N, return_edges=True)
    gaps = np.diff(np.asarray(edges, float))
    check(g, "the block marker is an unmistakable 2x gap",
          gaps.max() / np.median(gaps) > 1.8,
          f"{gaps.max()/np.median(gaps):.2f}x")
    check(g, "parity is recovered from it", I.tdm_parity(edges) is not None)

    src2 = S.SynthSource(FS, T_UP, N, [(10.0, -8.0, -1.8, 0.0026)],
                         retrace_s=RETRACE, f0=F0, bw=BW, switched=True,
                         marker=False, seed=5)
    b2, s2 = src2.read()
    _, _, e2 = S.segment_chirps(b2[0], s2, FS, N, return_edges=True)
    check(g, "without the marker parity is refused, not guessed",
          I.tdm_parity(e2) is None,
          "a guess here negates every bearing")

    cube = np.arange(8 * 3, dtype=float).reshape(8, 3)
    ca0, cb0 = I.tdm_split(cube, 0)
    ca1, cb1 = I.tdm_split(cube, 1)
    check(g, "tdm_split honours parity",
          np.array_equal(ca0, cube[0::2]) and np.array_equal(ca1, cube[1::2]))

    check(g, "the interferometer module's own unit tests", I._selftest(verbose=False))


GROUPS = [("geometry", test_geometry), ("azimuth", test_azimuth),
          ("calibration", test_calibration), ("refusal", test_refusal),
          ("limits", test_limits)]

if __name__ == "__main__":
    want = [a for a in sys.argv[1:] if not a.startswith("-")]
    for name, fn in GROUPS:
        if want and not any(w in name for w in want):
            continue
        print(f"\n{name}")
        fn()
    n = len(PASS) + len(FAIL)
    print(f"\n{'=' * 60}\n{len(PASS)}/{n} passed")
    for f in FAIL:
        print("  FAILED:", f)
    sys.exit(1 if FAIL else 0)
