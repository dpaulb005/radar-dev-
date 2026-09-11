#!/usr/bin/env python3
"""sar.py — synthetic aperture imaging from the stage-1 radar.

One transmit horn, one receive horn, and no moving antennas *during* a
measurement. The aperture is synthesised by **moving the whole radar** and
taking one dwell at each point along the way: N positions is an N-element array
you did not have to build, and the cross-range resolution it buys has nothing
to do with the 34 deg horn beam.

Two ways to move it, and the processing is identical:

    the drone    fly the radar along a path and image the scene. The flight
                 path IS the aperture. This is the target application.
    a rail       push it along a plank by hand. Slower, but it is how you
                 prove the chain works before anything leaves the ground.

The only thing that changes between them is how well you know where the radar
was, and that is the whole difficulty of the airborne version -- see
nav_tolerance() below. It is NOT resolution, and it is NOT payload.

This is the one capability that needs no second receiver, which is why it comes
before azimuth rather than after it.

    range resolution      c / 2B                  -- the sweep, and nothing else
    cross-range           lambda * R / (2 L)      -- the rail length
    can't be beaten       lambda / (4 sin(th/2))  -- the horn beam, th = 34 deg

The scene is static, so **there is no drone WiFi to coexist with** and the
sweep can use the whole ISM band: 2400-2500 MHz, B = 100 MHz, a 1.50 m range
cell instead of the 3.75 m the 40 MHz tracking sweep is stuck with.

Why backprojection and not the range-migration algorithm MIT hands out: RMA is
faster and assumes a straight track sampled at exactly even spacing. **A drone
does not fly a straight line.** Backprojection takes the positions as data --
feed it whatever the navigation solution says, in three dimensions, crooked and
unevenly spaced -- and is exact by construction, with no Stolt interpolation to
get wrong. For an airborne aperture that is not a preference, it is the only one
of the two that works. At these image sizes it costs under a second.

    I(x,y) = SUM_n  s_n(R_n) * exp(-j 4 pi fc R_n / c),  R_n = |(x,y) - rail_n|

Usage:
    python3 sar.py --selftest       assertions; exit status is the verdict
    python3 sar.py --demo           image a synthetic scene, write a PNG
    python3 sar.py --plan           what a given rail buys, before you build it
"""

import argparse
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

C = 2.99792458e8

# the imaging sweep: the whole ISM band, because a static scene has no drone
# flying in it and nothing to share the band with
F0_SAR, BW_SAR = 2.400e9, 100e6
BEAM_AZ_DEG = 34.0            # the rolled horn's azimuth beamwidth


# ----------------------------------------------------------------------
# what a rail buys, before you build one
# ----------------------------------------------------------------------
def range_res(bw=BW_SAR):
    return C / (2.0 * bw)


def cross_range_res(r, rail_len, fc=F0_SAR + BW_SAR / 2, beam_deg=BEAM_AZ_DEG):
    """Cross-range resolution at range r, and which limit is binding.

    The rail can only integrate over the angle the target is actually
    illuminated across, so the horn beam sets a floor no length of rail can
    beat. Returns the achieved resolution and the two limits behind it."""
    lam = C / fc
    aperture = lam * r / (2.0 * rail_len)                 # rail-limited
    floor = lam / (4.0 * math.sin(math.radians(beam_deg) / 2.0))   # beam-limited
    return dict(res=max(aperture, floor), aperture_limited=aperture,
                beam_limited=floor,
                binding="rail" if aperture > floor else "beam",
                rail_for_beam_limit=r * math.radians(beam_deg))


def nav_tolerance(fc=F0_SAR + BW_SAR / 2):
    """How well the platform's position must be known, and along which axis.

    Both numbers below are measured by --selftest against the imaging chain,
    not quoted from a rule of thumb -- and the rule of thumb is wrong here.

    ALONG-TRACK error barely matters. Range to a target changes as
    dR/dx = -x/R, which is ZERO at broadside, so an along-track slip mostly
    slides the aperture rather than corrupting it: 50 mm rms costs 0.1 dB.

    LINE-OF-SIGHT error is the one that bites, because it goes into the range
    one-for-one and so into the phase as 4*pi*e/lambda. Measured:

        2 mm rms  -0.2 dB      15 mm (lambda/8)  -4.7 dB
        5 mm rms  -1.0 dB      20 mm             -5.5 dB
       10 mm rms  -3.2 dB      30 mm             -6.7 dB

    So the working figure is about **lambda/25 line of sight**, not lambda/8.
    At 2.4 GHz that is 5 mm; at 24 GHz it would be 0.5 mm. The low band is by
    far the easier one to fly, which is the opposite of the usual advice."""
    lam = C / fc
    return dict(lam=lam, los_1db=lam / 25.0, los_lambda_8=lam / 8.0,
                along_track_1db=lam / 2.5)


def max_spacing(fc=F0_SAR + BW_SAR / 2, half_angle_deg=BEAM_AZ_DEG / 2):
    """Largest rail step that does not alias. The two-way phase advances
    4*pi/lambda per metre of range change, so the aperture is sampled at twice
    the rate a one-way array would be, and the Nyquist step is lambda/4 across
    the full scene angle."""
    return C / fc / (4.0 * math.sin(math.radians(half_angle_deg)))


def grating_lobe_deg(spacing, fc=F0_SAR + BW_SAR / 2):
    """Where the first ambiguity lands for a given step. Inside the beam it
    puts a ghost of every target into the image."""
    s = (C / fc) / (2.0 * spacing)
    return 90.0 if s >= 1.0 else math.degrees(math.asin(s))


def plan(rail_len=2.0, spacing=None, r=(3.0, 5.0, 10.0), bw=BW_SAR, verbose=True):
    fc = F0_SAR + bw / 2
    step = spacing if spacing else max_spacing(fc)
    n = int(math.floor(rail_len / step)) + 1
    out = dict(rail_len=rail_len, step=step, n_positions=n,
               range_res=range_res(bw), max_step=max_spacing(fc),
               grating_deg=grating_lobe_deg(step, fc))
    if verbose:
        print(f"\n  rail {rail_len:.2f} m, sweep {bw/1e6:.0f} MHz at "
              f"{fc/1e9:.3f} GHz (lambda {C/fc*1e3:.1f} mm)")
        print(f"    range resolution        {out['range_res']:.2f} m   (c/2B)")
        print(f"    largest step allowed    {out['max_step']*1e3:.0f} mm  "
              f"(lambda/4 across the {BEAM_AZ_DEG:.0f} deg beam)")
        print(f"    using                   {step*1e3:.0f} mm -> "
              f"{n} positions, first ambiguity at +/-{out['grating_deg']:.0f} deg")
        print(f"    {'range':>8}{'cross-range':>14}{'limited by':>13}"
              f"{'rail for beam limit':>22}")
        for rr in r:
            c = cross_range_res(rr, rail_len, fc)
            print(f"    {rr:>7.1f}m{c['res']:>13.2f}m{c['binding']:>13}"
                  f"{c['rail_for_beam_limit']:>20.1f} m")
        print(f"    a dwell per position, {n} of them, is one image")
    return out


# ----------------------------------------------------------------------
# range compression
# ----------------------------------------------------------------------
def range_profiles(cubes, t_up, fs, f0=F0_SAR, bw=BW_SAR, pad=8,
                   remove_static=True):
    """Range-compress one dwell per rail position into complex profiles.

    cubes is a list, one (n_chirps, n_samples) beat cube per position.

    The scene does not move, so every chirp in a dwell is the same measurement:
    averaging them coherently is the matched filter for a static target and
    buys sqrt(n_chirps) of SNR. There is no Doppler processing here and no
    per-chirp mean removal -- that notch is what used to cost a metre at 3 m
    (docs/radar-software.md § 1, stage 7).

    The mixer is single-ended, so the beat is real and its spectrum carries a
    mirror image at -f. hilbert() builds the analytic signal before the range
    FFT, which is what makes the phase meaningful.

    remove_static subtracts the profile averaged over POSITIONS. Anything that
    does not change as the radar moves is not in the scene -- the TX->RX
    leakage above all, which is ~52 dB above the echo and sits at a fixed
    range. A real target's range changes along the rail, so it survives. This
    is a high-pass along the aperture, not along range, so unlike the bin-0
    notch it does not eat the target it is protecting."""
    from scipy.signal import hilbert
    n_fft = None
    prof = []
    for cube in cubes:
        chirp = np.asarray(cube, float).mean(axis=0)       # coherent, static scene
        an = hilbert(chirp)
        n_fft = int(len(an) * pad)
        win = np.hanning(len(an))
        prof.append(np.fft.fft(an * win, n=n_fft)[:n_fft // 2])
    prof = np.array(prof)
    if remove_static and len(prof) > 2:
        prof = prof - prof.mean(axis=0, keepdims=True)
    freqs = np.arange(prof.shape[1]) * fs / n_fft
    ranges = freqs * C * t_up / (2.0 * bw)
    return prof, ranges


# ----------------------------------------------------------------------
# the image
# ----------------------------------------------------------------------
def backproject(profiles, ranges, positions, grid_x, grid_y,
                fc=F0_SAR + BW_SAR / 2, rail_y=0.0):
    """Coherent backprojection onto a grid.

    For every pixel and every rail position, look up the complex range profile
    at the exact round-trip range to that pixel and undo the carrier phase. In
    focus the terms add; out of focus they cancel.

    Exact for any rail geometry, including one that is not straight: positions
    may be (x,) or (x, y) pairs, so a measured, crooked rail images correctly
    where the range-migration algorithm would smear."""
    pos = np.asarray(positions, float)
    if pos.ndim == 1:
        pos = np.stack([pos, np.full_like(pos, rail_y)], axis=1)
    X, Y = np.meshgrid(np.asarray(grid_x, float), np.asarray(grid_y, float))
    img = np.zeros(X.shape, complex)
    dr = ranges[1] - ranges[0]
    k = 4.0 * math.pi * fc / C
    for n in range(pos.shape[0]):
        R = np.hypot(X - pos[n, 0], Y - pos[n, 1])
        idx = R / dr
        i0 = np.floor(idx).astype(int)
        frac = idx - i0
        ok = (i0 >= 0) & (i0 < len(ranges) - 1)
        s = np.zeros(X.shape, complex)
        i0c = np.clip(i0, 0, len(ranges) - 2)
        p = profiles[n]
        s = (p[i0c] * (1 - frac) + p[i0c + 1] * frac) * ok
        img += s * np.exp(-1j * k * R)
    return img


def db_image(img, floor_db=-35.0):
    """Magnitude in dB, normalised to the brightest pixel and floored."""
    m = np.abs(img)
    m /= (m.max() + 1e-30)
    d = 20 * np.log10(m + 1e-30)
    return np.maximum(d, floor_db)


# ----------------------------------------------------------------------
# a synthetic scene, through the project's own signal generator
# ----------------------------------------------------------------------
def simulate(scene, positions, n_chirps=16, fs=48_000.0, t_up=6.4e-3,
             retrace=1.0e-3, f0=F0_SAR, bw=BW_SAR, seed=0, isolation_db=35.0,
             n_steps=64):
    """One dwell per rail position, from SynthSource -- the same generator the
    tracking side is tested with, including the stepped ADF4351 waveform.

    scene is [(x, y, rcs)] in metres. positions may be x only, or (x, y) pairs
    for a path that is not a straight line -- which is every real flight path.
    The radar looks along +y."""
    from radar_acquire import SynthSource, segment_chirps
    pos = np.asarray(positions, float)
    if pos.ndim == 1:
        pos = np.stack([pos, np.zeros_like(pos)], axis=1)
    cubes = []
    for i, (xn, yn) in enumerate(pos):
        targets = []
        for (tx, ty, rcs) in scene:
            r = math.hypot(tx - xn, ty - yn)
            az = math.degrees(math.atan2(tx - xn, ty - yn))
            targets.append((r, az, 0.0, rcs))
        src = SynthSource(fs, t_up, n_chirps, targets=targets, retrace_s=retrace,
                          beam_az=0.0, f0=f0, bw=bw, seed=seed * 977 + i,
                          isolation_db=isolation_db, n_steps=n_steps)
        beats, sync = src.read()
        cube, timing = segment_chirps(beats[0], sync, fs, n_chirps)
        if cube is None:
            return None, None
        cubes.append(cube)
    return cubes, timing


def image_scene(scene, rail_len=2.0, step=None, y_range=(2.0, 14.0),
                x_range=(-4.0, 4.0), px=0.05, n_chirps=16, seed=0, **kw):
    """Scene -> image, the whole way through. Returns (img, extent, positions)."""
    step = step or max_spacing()
    positions = np.arange(-rail_len / 2, rail_len / 2 + 1e-9, step)
    cubes, timing = simulate(scene, positions, n_chirps=n_chirps, seed=seed, **kw)
    if cubes is None:
        return None, None, None
    prof, ranges = range_profiles(cubes, timing[0], 48_000.0)
    gx = np.arange(x_range[0], x_range[1] + 1e-9, px)
    gy = np.arange(y_range[0], y_range[1] + 1e-9, px)
    img = backproject(prof, ranges, positions, gx, gy)
    return img, (gx[0], gx[-1], gy[0], gy[-1]), positions


def peak_of(img, extent, px=0.05):
    """Brightest pixel, in scene coordinates."""
    gy, gx = np.unravel_index(np.argmax(np.abs(img)), img.shape)
    x = extent[0] + gx * px
    y = extent[2] + gy * px
    return x, y


def _width_at(img, extent, px, axis, level_db=-3.0):
    """-3 dB width of the peak along an axis, in metres."""
    d = db_image(img, floor_db=-60.0)
    iy, ix = np.unravel_index(np.argmax(np.abs(img)), img.shape)
    line = d[iy, :] if axis == "x" else d[:, ix]
    i0 = ix if axis == "x" else iy
    lo = i0
    while lo > 0 and line[lo] > level_db:
        lo -= 1
    hi = i0
    while hi < len(line) - 1 and line[hi] > level_db:
        hi += 1
    return (hi - lo) * px


# ----------------------------------------------------------------------
def selftest():
    ok = [0]

    def check(cond, msg):
        assert cond, msg
        ok[0] += 1

    # -- the design numbers
    check(abs(range_res(100e6) - 1.4990) < 1e-3, "100 MHz must give a 1.50 m cell")
    check(range_res(40e6) > range_res(100e6), "less bandwidth is a coarser cell")
    c10 = cross_range_res(10.0, 2.0)
    c10_long = cross_range_res(10.0, 4.0)
    check(c10_long["res"] < c10["res"], "a longer aperture is finer cross-range")
    check(abs(c10["res"] - c10["aperture_limited"]) < 1e-9 and c10["binding"] == "rail",
          "2 m of aperture at 10 m is aperture-limited")
    check(cross_range_res(3.0, 2.0)["binding"] == "beam",
          "close in, the horn beam is the floor no aperture can beat")
    check(cross_range_res(10.0, 100.0)["res"] == cross_range_res(10.0, 50.0)["res"],
          "past the beam limit more aperture buys nothing")
    check(max_spacing() < 0.11, "step must be under lambda/4 across the beam")
    check(grating_lobe_deg(max_spacing()) > BEAM_AZ_DEG / 2,
          "at the legal step the first ambiguity is outside the beam")
    check(grating_lobe_deg(0.4) < BEAM_AZ_DEG / 2,
          "and at 4x that step it is inside it, which puts ghosts in the image")

    # -- one simulation, reused
    pos = np.arange(-1.0, 1.0 + 1e-9, max_spacing())
    cubes, timing = simulate([(0.0, 6.0, 0.05)], pos, n_chirps=8, seed=1)
    check(cubes is not None and len(cubes) == len(pos), "every position captured")
    prof, ranges = range_profiles(cubes, timing[0], 48_000.0)
    check(prof.shape[0] == len(pos) and np.iscomplexobj(prof),
          "one complex range profile per position")
    gx = np.arange(-2.0, 2.0 + 1e-9, 0.04)
    gy = np.arange(4.0, 8.0 + 1e-9, 0.04)
    ext = (gx[0], gx[-1], gy[0], gy[-1])

    def img_of(p):
        return backproject(prof, ranges, p, gx, gy)

    img = img_of(pos)
    x, y = peak_of(img, ext, 0.04)
    check(abs(x - 0.0) < 0.1, f"point target focuses in cross-range: x={x:.2f}")
    check(abs(y - 6.0) < range_res() / 2, f"and in range: y={y:.2f}")
    wx = _width_at(img, ext, 0.04, "x")
    check(wx < 3 * cross_range_res(6.0, 2.0)["res"],
          f"cross-range width {wx:.2f} m tracks the prediction")
    check(_width_at(img, ext, 0.04, "y") > wx * 3,
          "range is much coarser than cross-range -- the image is anisotropic")

    ref = np.abs(img).max()

    def loss_db(p):
        return 20 * math.log10(np.abs(img_of(p)).max() / ref)

    # -- the finding this file exists to pin down: WHICH axis matters
    rng = np.random.default_rng(0)
    along = pos + rng.normal(0, 0.050, size=pos.shape)          # 50 mm along-track
    check(loss_db(along) > -0.5,
          f"50 mm along-track is nearly free: {loss_db(along):.1f} dB")
    los = np.stack([pos, rng.normal(0, 0.005, size=pos.shape)], axis=1)
    check(loss_db(los) > -2.0, f"5 mm line-of-sight costs about 1 dB: {loss_db(los):.1f}")
    los20 = np.stack([pos, rng.normal(0, 0.020, size=pos.shape)], axis=1)
    check(loss_db(los20) < -3.0,
          f"20 mm line-of-sight is already {loss_db(los20):.1f} dB -- lambda/8 is NOT enough")
    check(loss_db(los20) < loss_db(along) - 3.0,
          "line of sight is the sensitive axis, by a wide margin")

    # -- the reason for backprojection and not RMA: a path that is not a line.
    #    FLY the bow, then image it two ways -- with the true path, and with the
    #    straight line a range-migration processor would assume.
    bend = np.stack([pos, 0.15 * pos ** 2], axis=1)             # 150 mm of bow
    cb, tb = simulate([(0.0, 6.0, 0.05)], bend, n_chirps=8, seed=1)
    pb, rb = range_profiles(cb, tb[0], 48_000.0)
    good = np.abs(backproject(pb, rb, bend, gx, gy))            # true path
    bad = np.abs(backproject(pb, rb, pos, gx, gy))              # assumed straight
    xg, yg = peak_of(backproject(pb, rb, bend, gx, gy), ext, 0.04)
    check(abs(xg) < 0.1 and abs(yg - 6.0) < range_res() / 2,
          f"a bowed path focuses when its shape is known: ({xg:.2f},{yg:.2f})")
    check(20 * math.log10(bad.max() / good.max()) < -2.0,
          "and assuming it was straight loses the target: "
          f"{20*math.log10(bad.max()/good.max()):.1f} dB")

    # -- static removal must not move the target, unlike the bin-0 notch it
    #    superficially resembles (docs/radar-software.md § 1, stage 7)
    #    A short aperture barely migrates the target in RANGE (83 mm here,
    #    against a 1.5 m cell), so it is fair to ask whether the mean profile
    #    takes some of the target with it. It does not, because the target's
    #    PHASE turns 8.5 rad across the aperture while the leakage's does not
    #    turn at all -- that is the whole difference the subtraction keys on.
    p_keep, _ = range_profiles(cubes, timing[0], 48_000.0, remove_static=False)
    x2, y2 = peak_of(backproject(p_keep, ranges, pos, gx, gy), ext, 0.04)
    check(abs(x2) < 0.1 and abs(y2 - 6.0) < range_res() / 2,
          f"the target is found with or without static removal: ({x2:.2f},{y2:.2f})")
    check(abs(y2 - y) < 0.15 * range_res(),
          f"and the two agree to well inside a range cell: {y:.2f} vs {y2:.2f}")

    # -- two targets resolve when they should and merge when they should not
    fine = cross_range_res(6.0, 2.0)["res"]
    for sep, want in ((4 * fine, 2), (0.3 * fine, 1)):
        cs, tm = simulate([(-sep / 2, 6.0, 0.05), (sep / 2, 6.0, 0.05)], pos,
                          n_chirps=8, seed=2)
        pr, rr = range_profiles(cs, tm[0], 48_000.0)
        line = np.abs(backproject(pr, rr, pos, gx, np.array([6.0])))[0]
        line = line / line.max()
        peaks = sum(1 for i in range(1, len(line) - 1)
                    if line[i] > line[i - 1] and line[i] > line[i + 1] and line[i] > 0.5)
        check(peaks == want,
              f"separation {sep:.2f} m -> {peaks} peak(s), wanted {want}")

    print(f"selftest: {ok[0]} checks passed")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--aperture", type=float, default=2.0)
    args = ap.parse_args()
    if args.selftest:
        sys.exit(selftest())
    plan(args.aperture)
    n = nav_tolerance()
    print(f"\n  navigation: line of sight must be known to ~{n['los_1db']*1e3:.0f} mm "
          f"(lambda/25) for 1 dB")
    print(f"              along-track is 10x looser, ~{n['along_track_1db']*1e3:.0f} mm")
