#!/usr/bin/env python3
"""test_radar.py — the STAGE-1 regression suite. No hardware, no pytest, no network.

    python3 test_radar.py            run everything
    python3 test_radar.py -v         print every case
    python3 test_radar.py ranging    run only groups whose name matches

Exit status is 0 only if every case passes, so this is CI-ready as it stands.

Stage 1 is one TX horn and one RX horn: range and radial velocity, no azimuth.
The azimuth suite went with the code, to stage2/test_stage2.py, which must also
pass (cd stage2 && python3 test_stage2.py) -- between the two of them every case
this file used to hold is still run.

What it covers, and why each one is here:

  geometry      the wavelength the phase sees, which every range and velocity
                number scales off. If someone "tidies" a constant these fail
                before the radar does. (The baseline and coax-mismatch cases
                are stage 2's: stage2/test_stage2.py.)
  dsp           range and velocity still come out right, including the two
                timings being different numbers (T_up sets range, PRI sets
                velocity) which is the bug that is easiest to reintroduce.
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

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import fmcw_sim                                                  # noqa: E402
import radar_acquire as R                                        # noqa: E402
import synth as S                                                # noqa: E402

FS, T_UP, RETRACE, N = 48_000.0, 6.4e-3, 1.0e-3, 64
F0, BW = 2.400e9, 83.5e6
PASS, FAIL = [], []
VERBOSE = "-v" in sys.argv


_RANGE_RE = __import__("re").compile(r"range\s+([0-9.]+)\s*m")


def _reported_range(line):
    """The range the CLI's self-test verdict printed, in metres."""
    m = _RANGE_RE.search(line)
    return float(m.group(1)) if m else float("nan")


def check(group, name, cond, detail=""):
    (PASS if cond else FAIL).append(f"{group}: {name}")
    if VERBOSE or not cond:
        print(f"  {'pass' if cond else 'FAIL'}  {group:<12} {name}"
              f"{'   ' + detail if detail else ''}")


def cli(*extra):
    """Run radar_acquire's self-test and return (ok, last_line)."""
    p = subprocess.run([sys.executable, "radar_acquire.py", "--selftest",
                        "--f0-mhz", "2400", "--bw-mhz", "83.5", *map(str, extra)],
                       cwd=HERE, capture_output=True, text=True)
    line = (p.stdout.strip().splitlines() or [""])[-1]
    return p.returncode == 0, line


# ======================================================================
def test_geometry():
    g = "geometry"
    # The wavelength at the CENTRE of the sweep is the one the phase sees, and
    # the one every velocity scales off (v_max = lam/4/PRI). 2440 + 40/2 MHz.
    spec = fmcw_sim.RadarSpec(f0=2.440e9, bw=40e6)
    check(g, "wavelength at mid-sweep", abs(spec.lam - 0.12187) < 1e-4,
          f"{spec.lam*1000:.2f} mm")
    check(g, "the horn baseline constant has ONE definition",
          abs(fmcw_sim.DEFAULT_BASELINE_M - 0.1931) < 1e-9
          and S.SynthSource(FS, T_UP, 4, [], f0=F0, bw=BW).baseline_m
          == fmcw_sim.DEFAULT_BASELINE_M,
          "fmcw_sim.DEFAULT_BASELINE_M, imported by synth and by stage 2")


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

    src = S.SynthSource(FS, T_UP, N, [(10.0, 0.0, -1.8, 0.0026)],
                        retrace_s=RETRACE, f0=F0, bw=BW, seed=3)
    beats, sync = src.read()
    cube, timing, edges = S.segment_chirps(beats[0], sync, FS, N, return_edges=True)
    check(g, "segmentation finds the chirps", cube is not None and cube.shape[0] == N,
          f"{None if cube is None else cube.shape}")
    t_up, pri = timing
    check(g, "T_up is measured, not assumed", abs(t_up - T_UP) < 1e-4,
          f"{t_up*1e3:.3f} ms")
    check(g, "PRI is a DIFFERENT number from T_up",
          abs(pri - (T_UP + RETRACE)) < 1e-4 and pri > t_up + 5e-4,
          f"PRI {pri*1e3:.3f} ms vs T_up {t_up*1e3:.3f} ms")
    check(g, "edges come back when asked", edges is not None and len(edges) == N + 1)

    ok, line = cli("--st-range", "8", "--st-vel", "-1.2")
    check(g, "stage 1 range and velocity", ok, line)


# ======================================================================
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
        src = S.SynthSource(FS, T_UP, N, [(drone_r, 0.0, drone_v, 0.0026)] + ROOM,
                            retrace_s=RETRACE, f0=F0, bw=BW, seed=seed,
                            n_steps=64, clutter_cancel_db=cancel_db)
        beats, sync = src.read()
        cube, timing = S.segment_chirps(beats[0], sync, FS, N)
        if cube is None:
            continue
        dets, spec, *_ = R.process(cube, FS, timing, N, f0=F0, bw=BW,
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
        src = S.SynthSource(FS, T_UP, N, [(truth, 0.0, -1.8, 0.0026)],
                            retrace_s=RETRACE, f0=F0, bw=BW, seed=seed,
                            isolation_db=iso, n_steps=n_steps,
                            band_select_us=20.0, lock_tau_us=10.0)
        beats, sync = src.read()
        cube, timing = S.segment_chirps(beats[0], sync, FS, N,
                                        dc_per_chirp=dc_per_chirp)
        if cube is None:
            continue
        dets, spec, *_ = R.process(cube, FS, timing, N, f0=F0, bw=BW,
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
    #    3/5 at 50, nothing by 40. Free-space SNR says nothing about any of it:
    #    72 dB above the leakage-limited floor, 89 dB above thermal, and neither
    #    predicts a room. Note the wider sweep needs slightly MORE cancellation, not
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

    # 4. dets[0] must be the strongest ABSOLUTE return, not the best CFAR ratio.
    #    cfar_detect used to sort by the ratio, and a leakage residue sitting
    #    just above min_range in a quiet neighbourhood outranked the real target,
    #    whose own Doppler smear lifts its local background. The CLI reported
    #    ~0.7 m short at 3 m and 5 m while the absolute-level checks above all
    #    passed, because they never looked at the ordering. dets[0] is what the
    #    console draws as the fix and what the tracker is fed, so the ordering is
    #    part of the measurement. Drive it end to end through the real CLI.
    for truth in (3.0, 5.0, 8.0):
        ok, line = cli("--st-range", str(truth), "--st-vel", "-1.8")
        got = _reported_range(line)
        check(g, f"dets[0] is the target, not a nearer residue, at {truth:.0f} m",
              ok and not math.isnan(got) and abs(got - (truth - 0.43)) < 0.4,
              f"reported {got:.2f} m" if not math.isnan(got) else line)

GROUPS = [("geometry", test_geometry), ("dsp", test_dsp),
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
