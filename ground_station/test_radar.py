#!/usr/bin/env python3
"""test_radar.py — the regression suite. No hardware, no pytest, no network.

    python3 test_radar.py            run everything
    python3 test_radar.py -v         print every case
    python3 test_radar.py azimuth    run only groups whose name matches

Exit status is 0 only if every case passes, so this is CI-ready as it stands.

What it covers, and why each one is here:

  geometry      the numbers the hardware was built around: the baseline that
                makes the pair unambiguous, the one that does not, and what a
                millimetre of coax costs. If someone "tidies" a constant these
                fail before the radar does.
  dsp           range and velocity still come out right, including the two
                timings being different numbers (T_up sets range, PRI sets
                velocity) which is the bug that is easiest to reintroduce.
  azimuth       the interferometer end to end through radar_acquire, across
                the beam and across velocity, in both wirings.
  calibration   an injected chain offset is measured, stored, reloaded and
                removed.
  refusal       the cases where the right answer is "no bearing": ambiguous
                phase, a one-sided cell, and switched mode near its velocity
                fold. A radar that guesses is worse than one that abstains.
  limits        the documented limits are real: the switched fold is half the
                simultaneous one, and the un-rotated horn spacing genuinely
                wraps inside the beam.
  ranging       stage 1's actual job: does a target at a known range come back
                at that range, across the whole 3-20 m envelope, on the
                waveform the hardware really transmits (a 64-step staircase
                with PLL settling, not an ideal ramp). Includes the bin-0
                notch that used to cost a metre at 3 m, so it cannot come
                back, and the TX->RX isolation the whole thing rests on.
"""

import math
import pathlib
import subprocess
import sys
import tempfile

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import fmcw_sim                                                  # noqa: E402
import interferometer as I                                       # noqa: E402
import radar_acquire as R                                        # noqa: E402

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
    """Run radar_acquire's self-test and return (ok, last_line)."""
    p = subprocess.run([sys.executable, "radar_acquire.py", "--selftest",
                        "--f0-mhz", "2440", "--bw-mhz", "40", *map(str, extra)],
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
    check(g, "wavelength at mid-sweep", abs(J.lam - 0.12187) < 1e-4,
          f"{J.lam*1000:.2f} mm")
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


def test_dsp():
    g = "dsp"
    db, rg, vl = fmcw_sim.range_doppler(
        np.random.default_rng(0).normal(size=(8, 300)) + 0j,
        fmcw_sim.RadarSpec(f0=F0, bw=BW, t_chirp=T_UP, fs=FS, n_chirps=8))
    cx, rg2, vl2 = fmcw_sim.range_doppler(
        np.random.default_rng(0).normal(size=(8, 300)) + 0j,
        fmcw_sim.RadarSpec(f0=F0, bw=BW, t_chirp=T_UP, fs=FS, n_chirps=8),
        complex_out=True)
    check(g, "complex_out matches the dB map",
          np.allclose(db, 20 * np.log10(np.abs(cx) + 1e-15))
          and np.allclose(rg, rg2) and np.allclose(vl, vl2))

    src = R.SynthSource(FS, T_UP, N, [(10.0, 0.0, -1.8, 0.0026)],
                        retrace_s=RETRACE, f0=F0, bw=BW, seed=3)
    beats, sync = src.read()
    cube, timing, edges = R.segment_chirps(beats[0], sync, FS, N, return_edges=True)
    check(g, "segmentation finds the chirps", cube is not None and cube.shape[0] == N,
          f"{None if cube is None else cube.shape}")
    t_up, pri = timing
    check(g, "T_up is measured, not assumed", abs(t_up - T_UP) < 1e-4,
          f"{t_up*1e3:.3f} ms")
    check(g, "PRI is a DIFFERENT number from T_up",
          abs(pri - (T_UP + RETRACE)) < 1e-4 and pri > t_up + 5e-4,
          f"PRI {pri*1e3:.3f} ms vs T_up {t_up*1e3:.3f} ms")
    check(g, "edges come back when asked", edges is not None and len(edges) == N + 1)

    ok, line = cli("--st-range-only", "--st-range", "8", "--st-vel", "-1.2")
    check(g, "stage 1 range and velocity", ok, line)


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
        check(g, f"{tag}: 36 bearings across the beam", bad == 0,
              f"{36 - bad}/36 pass, worst error {max(errs) if errs else float('nan'):.2f} deg")
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
    src = R.SynthSource(FS, T_UP, N, [(10.0, -8.0, -1.8, 0.0026)],
                        retrace_s=RETRACE, f0=F0, bw=BW, n_rx=2, seed=4)
    beats, sync = src.read()
    _, timing, rds, rg, vl, dets = R._maps(beats, sync, FS, N, None, F0, BW, 15.0)
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
    src = R.SynthSource(FS, T_UP, N, [(10.0, -8.0, -1.8, 0.0026)],
                        retrace_s=RETRACE, f0=F0, bw=BW, switched=True, seed=5)
    beats, sync = src.read()
    _, _, edges = R.segment_chirps(beats[0], sync, FS, N, return_edges=True)
    gaps = np.diff(np.asarray(edges, float))
    check(g, "the block marker is an unmistakable 2x gap",
          gaps.max() / np.median(gaps) > 1.8,
          f"{gaps.max()/np.median(gaps):.2f}x")
    check(g, "parity is recovered from it", I.tdm_parity(edges) is not None)

    src2 = R.SynthSource(FS, T_UP, N, [(10.0, -8.0, -1.8, 0.0026)],
                         retrace_s=RETRACE, f0=F0, bw=BW, switched=True,
                         marker=False, seed=5)
    b2, s2 = src2.read()
    _, _, e2 = R.segment_chirps(b2[0], s2, FS, N, return_edges=True)
    check(g, "without the marker parity is refused, not guessed",
          I.tdm_parity(e2) is None,
          "a guess here negates every bearing")

    cube = np.arange(8 * 3, dtype=float).reshape(8, 3)
    ca0, cb0 = I.tdm_split(cube, 0)
    ca1, cb1 = I.tdm_split(cube, 1)
    check(g, "tdm_split honours parity",
          np.array_equal(ca0, cube[0::2]) and np.array_equal(ca1, cube[1::2]))

    check(g, "the interferometer module's own unit tests", I._selftest(verbose=False))


# ======================================================================
ROOM = [(4.0, 0.0, 0.0, 1.0), (8.0, 10.0, 0.0, 1.0), (11.5, -12.0, 0.0, 2.0)]


def _in_room(cancel_db, seeds=(0, 1, 2, 3, 4), drone_r=10.0, drone_v=-1.8):
    """Is the drone the STRONGEST return, with a room in the way?

    Every other number in this suite is thermal-noise-limited. Indoors it will
    not be: a 1 m^2 wall is 26 dB above a 0.0026 m^2 drone and shares its 3.75 m
    range cell. What saves the drone is that the room does not move -- so what
    matters is how well the room CANCELS, not how strong the echo is."""
    hits = 0
    for seed in seeds:
        src = R.SynthSource(FS, T_UP, N, [(drone_r, 0.0, drone_v, 0.0026)] + ROOM,
                            retrace_s=RETRACE, f0=F0, bw=BW, seed=seed,
                            n_steps=64, clutter_cancel_db=cancel_db)
        beats, sync = src.read()
        cube, timing = R.segment_chirps(beats[0], sync, FS, N)
        if cube is None:
            continue
        dets, spec = R.process(cube, FS, timing, N, f0=F0, bw=BW,
                               min_range=1.5, max_range=30.0)
        if not dets:
            continue
        mid = drone_r + drone_v * (timing[1] * N / 2)
        if abs(sorted(dets, key=lambda d: -d[3])[0][0] - mid) < 1.0:
            hits += 1
    return hits, len(seeds)


def _range_err(truth, dc_per_chirp=False, iso=35.0, n_steps=64, seeds=(0, 1, 2, 3)):
    """Mean signed range error for a target at `truth`, straight through the
    real pipeline: SynthSource -> segment_chirps -> process, fix chosen by
    absolute level exactly as radar_acquire.run() chooses it."""
    errs = []
    for seed in seeds:
        src = R.SynthSource(FS, T_UP, N, [(truth, 0.0, -1.8, 0.0026)],
                            retrace_s=RETRACE, f0=F0, bw=BW, seed=seed,
                            isolation_db=iso, n_steps=n_steps,
                            band_select_us=20.0, lock_tau_us=10.0)
        beats, sync = src.read()
        cube, timing = R.segment_chirps(beats[0], sync, FS, N,
                                        dc_per_chirp=dc_per_chirp)
        if cube is None:
            continue
        dets, spec = R.process(cube, FS, timing, N, f0=F0, bw=BW,
                               min_range=1.0, max_range=60.0)
        if not dets:
            continue
        mid = truth + (-1.8) * (timing[1] * N / 2)     # the target moves in the dwell
        errs.append(sorted(dets, key=lambda d: -d[3])[0][0] - mid)
    return float(np.mean(errs)) if errs else float("nan")


def test_ranging():
    g = "ranging"
    ENV = (3.0, 5.0, 8.0, 10.0, 15.0, 20.0)

    # -- the waveform the hardware actually transmits. radar_ctl steps an
    #    ADF4351 64 times and each write retriggers a VCO band select, so the
    #    beat is a staircase with a settling transient on every step, not a
    #    tone. It has to make no difference at these ranges, because the phase
    #    error it causes is 2*pi*df*tau -- 15 deg at 10 m -- and that is the
    #    whole reason a stepped sweep is allowed to stand in for a ramp.
    worst = max(abs(_range_err(r, n_steps=64) - _range_err(r, n_steps=None))
                for r in ENV)
    check(g, "stepped sweep matches an ideal ramp", worst < 0.05,
          f"worst divergence {worst:.3f} m over 3-20 m")

    # -- the actual requirement
    errs = {r: _range_err(r) for r in ENV}
    worst_r, worst_e = max(errs.items(), key=lambda kv: abs(kv[1]))
    check(g, "range is accurate across the 3-20 m envelope",
          all(abs(e) < 0.25 for e in errs.values()),
          f"worst {worst_e:+.2f} m at {worst_r:.0f} m")
    check(g, "and best where the drone flies (3-10 m)",
          max(abs(errs[r]) for r in (3.0, 5.0, 8.0, 10.0)) < 0.2,
          f"{', '.join(f'{r:.0f}m {errs[r]:+.2f}' for r in (3.0, 5.0, 8.0, 10.0))}")

    # -- the regression this group exists for. Subtracting the per-chirp mean
    #    removes a window-shaped lobe two bins wide centred on DC, which eats
    #    part of any target within 7.5 m at 40 MHz. If someone puts it back,
    #    3 m goes a metre long and nothing else complains.
    near_off, near_on = _range_err(3.0), _range_err(3.0, dc_per_chirp=True)
    check(g, "the bin-0 notch stays OFF", abs(near_off) < 0.2 < abs(near_on),
          f"3 m reads {near_off:+.2f} m without it, {near_on:+.2f} m with it")
    check(g, "the notch is worse across the whole envelope",
          (np.mean([abs(_range_err(r, dc_per_chirp=True)) for r in ENV])
           > 3 * np.mean([abs(e) for e in errs.values()])),
          "mean |error| at least 3x worse with it on")

    # -- what the whole thing rests on. 35 dB is the design figure
    #    (docs/radar-hardware.md, separate horns 305 mm apart); below about
    #    29 dB the leakage skirt outranks the target and the radar reports the
    #    leak's range, or nothing at all. That is 6 dB of margin on the 83.5 MHz
    #    sweep -- it was 3 dB at 40 MHz, and the wider sweep is what bought it.
    check(g, "works at the designed 35 dB isolation",
          max(abs(_range_err(r, iso=35.0)) for r in (3.0, 10.0)) < 0.25)
    check(g, "still works at 30 dB", abs(_range_err(10.0, iso=30.0)) < 0.5,
          "the 83.5 MHz sweep buys 3 dB of isolation margin over 40 MHz")
    # below the cliff it either finds nothing or finds the leak. Both are
    # "blind"; the first is the better failure, because it abstains.
    # -- the room. This is the number to measure on day one, and the one most
    #    likely to decide whether the build works: with 1 m^2 walls the drone
    #    needs about 40 dB of clutter cancellation to stay the strongest
    #    return. Measured on the 83.5 MHz sweep: 5/5 at 55 dB of cancellation,
    #    3/5 at 50, nothing by 40. Thermal SNR is 71 dB and says nothing about
    #    any of it. Note the wider sweep needs slightly MORE cancellation, not
    #    less: narrower cells concentrate a wall's energy into a sharper, taller
    #    peak, so its residue competes better with the drone.
    good, n = _in_room(55.0)
    check(g, "drone survives a room when clutter cancels well", good == n,
          f"{good}/{n} at 55 dB cancellation")
    bad, n = _in_room(25.0)
    check(g, "and is lost when it does not", bad < n,
          f"{bad}/{n} at 25 dB — the walls win")
    check(g, "so clutter cancellation, not SNR, is the indoor limit",
          good - bad >= 3, f"{good}/{n} at 50 dB vs {bad}/{n} at 25 dB")

    blind = _range_err(10.0, iso=28.0)
    check(g, "goes blind below ~29 dB, as documented",
          math.isnan(blind) or abs(blind) > 2.0,
          "no fix at all at 28 dB" if math.isnan(blind)
          else f"10 m reads {blind:+.2f} m off — the leak, not the target")


GROUPS = [("geometry", test_geometry), ("dsp", test_dsp), ("azimuth", test_azimuth),
          ("calibration", test_calibration), ("refusal", test_refusal),
          ("limits", test_limits),
          ("ranging", test_ranging)]

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
