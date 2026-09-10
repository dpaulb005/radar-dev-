#!/usr/bin/env python3
"""make_figures.py — every figure in docs/signal-chain.md, drawn from the real code.

Nothing here is an illustration. The waveforms are produced by
ground_station/radar_acquire.py's SynthSource (the same physics the digital twin
and the self-test use), cut up by the same segment_chirps(), and processed by the
same fmcw_sim.range_doppler() and cfar_detect() that run on live audio.

Usage:  python3 make_figures.py
"""
import math
import pathlib
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "ground_station"))

import fmcw_sim                                    # noqa: E402
from radar_acquire import SynthSource, segment_chirps, process   # noqa: E402

# ----------------------------------------------------------------------
# the configuration this project actually runs
# ----------------------------------------------------------------------
FS = 48_000.0          # UCA202
F0 = 2.400e9           # the whole ISM band; the drone's link is on 915 MHz
BW = 83.5e6            # sweep width -> 1.80 m range cells
T_UP = 6.4e-3          # 64 PLL steps x 100 us
RETRACE = 1.0e-3
N_CHIRPS = 64
TARGET_R = 10.0        # the drone
TARGET_V = -1.8        # closing, m/s
TARGET_RCS = 0.0026    # m^2, a 25 g quad
C = 2.99792458e8

INK = "#1e1b16"
ACC = "#b8541c"
BLU = "#2c6fad"
GRN = "#2f8f5b"
GREY = "#8b8477"
PAPER = "#faf8f2"

plt.rcParams.update({
    "figure.facecolor": PAPER, "axes.facecolor": PAPER, "savefig.facecolor": PAPER,
    "font.family": "DejaVu Sans", "font.size": 9,
    "axes.edgecolor": GREY, "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": GREY, "ytick.color": GREY, "axes.titlesize": 10,
    "axes.titleweight": "bold", "axes.grid": True, "grid.color": "#e3ded1",
    "grid.linewidth": 0.7, "legend.frameon": False,
})


def save(fig, name):
    fig.tight_layout()
    fig.savefig(HERE / name, dpi=160)
    plt.close(fig)
    print("wrote", name)


# ======================================================================
# 1 — what leaves the antenna: a frequency staircase, and its echo
# ======================================================================
def fig_chirp():
    n_steps, step_us = 64, 100.0
    df = BW / n_steps
    tau = 2 * TARGET_R / C                      # 66.7 ns round trip at 10 m

    t_fine = np.linspace(0, (T_UP + RETRACE) * 2, 40000)
    def f_of_t(t):
        tm = np.mod(t, T_UP + RETRACE)
        k = np.floor(np.clip(tm, 0, T_UP - 1e-12) / (step_us * 1e-6))
        f = F0 + k * df
        return np.where(tm >= T_UP, F0, f)

    fig, ax = plt.subplots(2, 1, figsize=(9, 5.4), height_ratios=[2.1, 1])

    a = ax[0]
    a.plot(t_fine * 1e3, (f_of_t(t_fine) - F0) / 1e6, color=BLU, lw=1.6,
           label="transmitted, straight out of the PLL")
    a.plot(t_fine * 1e3, (f_of_t(t_fine - tau) - F0) / 1e6, color=ACC, lw=1.6,
           ls="--", label=f"echo, the same staircase {tau*1e9:.1f} ns later")
    a.set_xlim(0, (T_UP + RETRACE) * 2 * 1e3)
    a.set_ylim(-3, BW / 1e6 + 3)
    a.set_ylabel("MHz above 2440")
    a.set_title("1 · What the antenna radiates: a 64-step frequency staircase, twice")
    a.legend(loc="upper right", fontsize=8)
    a.annotate("up-chirp, 6.4 ms", (T_UP / 2 * 1e3, BW / 1e6 * 0.42), color=BLU,
               ha="center", fontsize=8)
    a.annotate("retrace,\nparked at 2440", ((T_UP + RETRACE / 2) * 1e3, BW / 1e6 * 0.55),
               color=GREY, ha="center", fontsize=8)

    # the zoom that shows the actual beat: 300 ns across one step edge
    b = ax[1]
    edge = 3200e-6                      # a step boundary, 32 steps in
    tz = np.linspace(edge - 100e-9, edge + 200e-9, 6000)
    b.step((tz - edge) * 1e9, (f_of_t(tz) - F0) / 1e6, color=BLU, lw=2.0, where="post",
           label="transmitted")
    b.step((tz - edge) * 1e9, (f_of_t(tz - tau) - F0) / 1e6, color=ACC, lw=2.0, ls="--",
           where="post", label="echo")
    b.axvspan(0, tau * 1e9, color=ACC, alpha=0.16)
    b.set_xlabel("nanoseconds either side of one step edge")
    b.set_ylabel("MHz above 2440")
    b.set_title("zoomed to 300 ns: the transmitter has already stepped up while the echo has not")
    b.legend(loc="upper left", fontsize=8)
    b.annotate("for 66.7 ns the two differ by one\nwhole step, 625 kHz. That is\n"
               "0.067 % of each 100 µs step, so\nthe average difference is 417 Hz.",
               (tau * 1e9 + 12, 19.6), color=ACC, fontsize=8.5)
    save(fig, "01-chirp.png")


# ======================================================================
# 2 — what the sound card actually records
# ======================================================================
def make_audio():
    src = SynthSource(FS, T_UP, N_CHIRPS,
                      targets=[(TARGET_R, 0.0, TARGET_V, TARGET_RCS)],
                      retrace_s=RETRACE, beam_az=0.0, f0=F0, bw=BW, seed=3)
    beats, sync = src.read()          # read() is multi-channel; stage 1 has one
    return beats[0], sync


def fig_soundcard(beat, sync):
    n = int((T_UP + RETRACE) * FS * 2.6)
    t = np.arange(n) / FS * 1e3
    fig, ax = plt.subplots(2, 1, figsize=(9, 4.6), sharex=True)

    ax[0].plot(t, beat[:n], color=GRN, lw=0.8)
    ax[0].set_ylabel("left: counts")
    ax[0].set_title("2 · The two channels the laptop records, 16-bit at 48 kHz")
    ax[0].annotate("the leakage tone dominates; the drone echo is 1/1000 of this",
                   (0.35, 0.86), xycoords="axes fraction", fontsize=8, color=GREY)

    ax[1].plot(t, sync[:n], color=BLU, lw=1.0)
    ax[1].set_ylabel("right: counts")
    ax[1].set_xlabel("milliseconds")
    ax[1].annotate("AC coupling turns the square wave into a drooping plateau\n"
                   "and a negative retrace spike — the edges survive, the levels do not",
                   (0.30, 0.12), xycoords="axes fraction", fontsize=8, color=GREY)
    save(fig, "02-soundcard.png")


# ======================================================================
# 3 — finding the chirps, and the cube they become
# ======================================================================
def fig_segment(beat, sync, cube, timing):
    d = np.diff(sync.astype(float))
    dmax, dmin = float(np.max(d)), float(np.min(d))
    up = np.flatnonzero(d > 0.5 * dmax) + 1
    dn = np.flatnonzero(d < 0.5 * dmin) + 1
    n = int((T_UP + RETRACE) * FS * 2.6)
    t = np.arange(len(d)) / FS * 1e3

    fig, ax = plt.subplots(1, 2, figsize=(9.6, 3.6), width_ratios=[1.25, 1])
    ax[0].plot(t[:n], d[:n], color=BLU, lw=0.9)
    for i in up[up < n]:
        ax[0].axvline(i / FS * 1e3, color=GRN, lw=1.4)
    for i in dn[dn < n]:
        ax[0].axvline(i / FS * 1e3, color=ACC, lw=1.4, ls="--")
    ax[0].set_xlabel("milliseconds")
    ax[0].set_ylabel("d(sync)/dt")
    ax[0].set_title("3 · Chirp edges, found on the derivative")
    ax[0].annotate("green = chirp start\norange = chirp end", (0.62, 0.72),
                   xycoords="axes fraction", fontsize=8, color=GREY)

    im = ax[1].imshow(cube, aspect="auto", cmap="RdBu_r", origin="lower",
                      extent=[0, cube.shape[1], 0, cube.shape[0]],
                      vmin=-np.percentile(np.abs(cube), 99),
                      vmax=np.percentile(np.abs(cube), 99))
    ax[1].set_xlabel("sample within the chirp")
    ax[1].set_ylabel("chirp number")
    ax[1].set_title(f"the cube: {cube.shape[0]} × {cube.shape[1]} floats")
    ax[1].grid(False)
    fig.colorbar(im, ax=ax[1], label="counts")
    save(fig, "03-segmentation.png")


# ======================================================================
# 4 — one chirp's spectrum: where the range actually appears
# ======================================================================
def fig_range_fft(cube):
    n_s = cube.shape[1]
    win = np.hanning(n_s)
    sp = np.abs(np.fft.rfft(cube[0] * win))
    spb = np.abs(np.fft.rfft((cube[0] - cube.mean(axis=0)) * win))
    f = np.fft.rfftfreq(n_s, 1 / FS)
    rng = f * C * T_UP / (2 * BW)
    slope = 2 * BW / (C * T_UP)          # Hz per metre

    fig, ax = plt.subplots(1, 2, figsize=(9.6, 3.6))
    db = lambda x: 20 * np.log10(np.maximum(x, 1e-9) / np.max(sp))
    ax[0].plot(f, db(sp), color=GREY, lw=1.2, label="raw chirp")
    ax[0].plot(f, db(spb), color=GRN, lw=1.4, label="after removing the chirp average")
    ax[0].axvline(slope * TARGET_R, color=ACC, lw=1.2, ls="--")
    ax[0].annotate(f"drone at {TARGET_R:.0f} m\n= {slope*TARGET_R:.0f} Hz",
                   (slope * TARGET_R + 90, -12), color=ACC, fontsize=8)
    ax[0].annotate("TX→RX leakage,\n0.3 m ≈ 12 Hz", (30, -3), color=GREY, fontsize=8)
    ax[0].set_xlim(0, 2000)
    ax[0].set_ylim(-70, 3)
    ax[0].set_xlabel("beat frequency, Hz")
    ax[0].set_ylabel("dB relative to peak")
    ax[0].set_title("4 · One chirp, spectrum. Pitch is range.")
    ax[0].legend(fontsize=8, loc="lower right")

    ax[1].plot(rng, db(spb), color=GRN, lw=1.4)
    ax[1].axvline(TARGET_R, color=ACC, lw=1.2, ls="--")
    ax[1].set_xlim(0, 48)
    ax[1].set_ylim(-70, 3)
    ax[1].set_xlabel("range, metres")
    ax[1].set_ylabel("dB")
    ax[1].set_title(f"the same axis in metres · {C/(2*BW):.2f} m per cell")
    ax[1].annotate(f"48 kHz sampling reaches {FS/2/slope:.0f} m; the 15.9 kHz filter\n"
                   f"cuts that to {15900/slope:.0f} m. Indoors you use the first 5 %\n"
                   f"of the FFT. With {n_s} samples a bin is {FS/n_s:.0f} Hz, so the drone\n"
                   f"sits only {slope*TARGET_R/(FS/n_s):.1f} bins from DC and the leakage\n"
                   "mainlobe still covers it. Figure 5 is where it separates.",
                   (0.24, 0.10), xycoords="axes fraction", fontsize=8, color=GREY)
    save(fig, "04-range-fft.png")


# ======================================================================
# 5 — range-Doppler, and the detection that comes out of it
# ======================================================================
def fig_range_doppler(cube, timing, dets):
    t_up, pri = timing
    spec = fmcw_sim.RadarSpec(f0=F0, bw=BW, t_chirp=t_up, fs=FS, n_chirps=cube.shape[0])
    rd, ranges, vels = fmcw_sim.range_doppler(cube.astype(complex), spec, bg_subtract=True)
    vels = vels * (t_up / pri)
    keep = (ranges >= 0) & (ranges <= 40)

    fig, ax = plt.subplots(1, 2, figsize=(9.8, 3.8), width_ratios=[1.3, 1])
    m = rd[:, keep]
    im = ax[0].pcolormesh(ranges[keep], vels, m - m.max(), cmap="magma",
                          vmin=-45, vmax=0, shading="auto")
    ax[0].set_xlabel("range, metres")
    ax[0].set_ylabel("radial velocity, m/s")
    ax[0].set_title("5 · Range–Doppler, after subtracting the chirp average")
    ax[0].set_xlim(0, 30)
    ax[0].grid(False)
    fig.colorbar(im, ax=ax[0], label="dB below peak")
    best = max(dets, key=lambda d: d[3])
    for d in dets:
        if d is not best:
            ax[0].plot(d[0], d[1], "o", ms=5, mfc="none", mec="#7fd8a8", mew=1.0, alpha=0.8)
    ax[0].plot(best[0], best[1], "o", ms=13, mfc="none", mec="#5cc38a", mew=2.2)
    ax[0].annotate(f"strongest: {best[0]:.2f} m, {best[1]:+.2f} m/s, SNR {best[2]:.0f} dB\n"
                   f"truth was {TARGET_R:.1f} m, {TARGET_V:+.1f} m/s",
                   (best[0] + 1.2, best[1] - 0.9), color="#5cc38a", fontsize=8.5)
    ax[0].annotate(f"{len(dets)} detections survive CFAR;\nonly the strongest is labelled",
                   (0.03, 0.06), xycoords="axes fraction", color="#7fd8a8", fontsize=8)

    zero_row = int(np.argmin(np.abs(vels)))
    tgt_row = int(np.argmin(np.abs(vels - best[1])))
    ref = m.max()
    ax[1].plot(ranges[keep], m[zero_row] - ref, color=GREY, lw=1.5,
               label=f"zero-Doppler row: leakage and clutter")
    ax[1].plot(ranges[keep], m[tgt_row] - ref, color=GRN, lw=1.7,
               label=f"the drone's row, {vels[tgt_row]:+.2f} m/s")
    ax[1].axvline(TARGET_R, color=ACC, ls="--", lw=1.1)
    ax[1].set_xlabel("range, metres")
    ax[1].set_ylabel("dB below peak")
    ax[1].set_title("what Doppler buys you")
    ax[1].set_xlim(0, 30)
    ax[1].set_ylim(-45, 3)
    ax[1].legend(fontsize=8, loc="upper right")
    ax[1].annotate("in range alone the drone is buried in the\n"
                   "leakage skirt; the Doppler FFT is what\n"
                   "separates them", (0.05, 0.06), xycoords="axes fraction",
                   fontsize=8, color=GREY)
    save(fig, "05-range-doppler.png")
    return rd, ranges, vels


# ======================================================================
# 6 — azimuth: the turntable makes the third number, and where it breaks
# ======================================================================
def fig_azimuth():
    """Run the REAL pipeline (radar_acquire.py --selftest) at a spread of true
    azimuths, on both the old 40 MHz coexistence sweep and the full band now used,
    and plot what it reports."""
    import json as _json
    import subprocess
    gs = HERE.parent.parent / "ground_station"
    truths = [-30, -24, -18, -12, -6, 0, 6, 12, 18, 24, 30]

    def sweep(f0_mhz, bw_mhz):
        out = []
        for az in truths:
            r = subprocess.run(
                [sys.executable, "radar_acquire.py", "--selftest",
                 "--f0-mhz", str(f0_mhz), "--bw-mhz", str(bw_mhz),
                 "--st-range", str(TARGET_R), "--st-az", str(az), "--st-vel", str(TARGET_V)],
                cwd=gs, capture_output=True, text=True)
            fix = None
            for line in r.stdout.splitlines():
                if line.startswith("{"):
                    try:
                        fix = _json.loads(line).get("fix")
                    except ValueError:
                        pass
            out.append(fix["az"] if fix else float("nan"))
        return np.array(out, dtype=float)

    a40 = sweep(2440, 40)
    a80 = sweep(2400, 80)
    t = np.array(truths, dtype=float)

    fig, ax = plt.subplots(1, 2, figsize=(9.6, 3.8))
    lim = [-36, 36]
    ax[0].plot(lim, lim, color=GREY, ls=":", lw=1.2, label="perfect")
    ax[0].plot(t, a80, "o-", color=GRN, lw=1.4, ms=5, label="full band (2400–2483.5), in use")
    ax[0].plot(t, a40, "s-", color=ACC, lw=1.4, ms=5, label="40 MHz (2440–2480), the old WiFi-coexistence sweep")
    ax[0].set_xlim(lim); ax[0].set_ylim(lim)
    ax[0].set_xlabel("true azimuth, degrees")
    ax[0].set_ylabel("reported azimuth, degrees")
    ax[0].set_title("6 · Azimuth, from the real pipeline")
    ax[0].legend(fontsize=8, loc="upper left")

    e40, e80 = a40 - t, a80 - t
    ax[1].axhspan(-2.5, 2.5, color=GRN, alpha=0.12)
    ax[1].plot(t, e80, "o-", color=GRN, lw=1.4, ms=5)
    ax[1].plot(t, e40, "s-", color=ACC, lw=1.4, ms=5)
    ax[1].axhline(0, color=GREY, lw=1.0)
    ax[1].set_xlabel("true azimuth, degrees")
    ax[1].set_ylabel("error, degrees")
    ax[1].set_title("error against the 2.5° budget (shaded)")
    ax[1].annotate(f"full band: {np.nanmax(np.abs(e80)):.1f}° worst", (0.04, 0.10),
                   xycoords="axes fraction", color=GRN, fontsize=8.5)
    ax[1].annotate(f"40 MHz: {np.nanmax(np.abs(e40)):.1f}° worst", (0.04, 0.88),
                   xycoords="axes fraction", color=ACC, fontsize=8.5)
    save(fig, "06-azimuth.png")
    return t, a40, a80


# ======================================================================
# 7 — where the scan-time budget should go, and the limit on all of it
# ======================================================================
def fig_scan_budget():
    """Reads scan_budget.json, written by scan_budget.py."""
    import json as _json
    f = HERE / "scan_budget.json"
    if not f.exists():
        print("skip 07: run scan_budget.py first")
        return
    rows = _json.loads(f.read_text())
    fig, ax = plt.subplots(1, 2, figsize=(9.8, 3.9))

    # -- left: what the budget buys ------------------------------------
    fam_style = {"beams": (ACC, "s-", "more beams (finer servo steps)"),
                 "dwell": (GRN, "o-", "longer dwell (same 9 beams)"),
                 "mixed": (BLU, "^", "a bit of both")}
    base = [r for r in rows if r["family"] == "base"][0]
    ax[0].axhspan(0, 2.5, color=GRN, alpha=0.10)
    for fam, (c, m, lab) in fam_style.items():
        pts = sorted([r for r in rows if r["family"] in (fam, "base")],
                     key=lambda r: r["scan_s"])
        if fam == "mixed":
            pts = [r for r in rows if r["family"] == "mixed"]
        ax[0].plot([r["scan_s"] for r in pts], [r["worst"] for r in pts], m,
                   color=c, lw=1.6, ms=6, label=lab)
    wb = [r for r in rows if r["family"] == "wideband"]
    if wb:
        ax[0].plot(wb[0]["scan_s"], wb[0]["worst"], "*", color=GREY, ms=15,
                   label="full band, 9 beams · 64")
    ax[0].set_xlabel("total scan time, seconds")
    ax[0].set_ylabel("worst azimuth error, degrees")
    ax[0].set_title("7 · Spend the scan budget on dwell, not on beams")
    ax[0].legend(fontsize=8, loc="upper right")
    ax[0].annotate("2.5° budget", (0.52, 0.06), xycoords="axes fraction",
                   color=GRN, fontsize=8.5)
    for r in rows:
        if r["family"] in ("dwell", "beams") and r["scan_s"] > 9:
            ax[0].annotate(r["label"], (r["scan_s"], r["worst"] + 0.15),
                           fontsize=7.5, color=GREY, ha="center")

    # -- right: the limit that outranks both ---------------------------
    v = np.linspace(0.08, 3.0, 300)
    t_budget = 2.5 * TARGET_R * math.pi / 180 / v          # stay inside 2.5 deg
    t_beam = 34.0 * TARGET_R * math.pi / 180 / v           # stay inside one beamwidth
    ax[1].fill_between(v, 1e-2, t_budget, color=GRN, alpha=0.13)
    ax[1].plot(v, t_budget, color=GRN, lw=1.8, label="scan must finish inside 2.5°")
    ax[1].plot(v, t_beam, color=GREY, lw=1.4, ls="--", label="…inside one 34° beamwidth")
    for t, lab, c in [(base["scan_s"], f"9 beams · 64  ({base['scan_s']:.1f} s)", ACC),
                      (10.7, "9 beams · 160  (10.7 s)", BLU)]:
        ax[1].axhline(t, color=c, lw=1.3, ls=":")
        vmax = 2.5 * TARGET_R * math.pi / 180 / t
        ax[1].plot([vmax], [t], "o", color=c, ms=6)
        ax[1].annotate(f"{lab}\nneeds v < {vmax:.2f} m/s", (0.30, t * 1.15),
                       color=c, fontsize=8)
    ax[1].set_yscale("log")
    ax[1].set_xlim(0, 3)
    ax[1].set_ylim(0.05, 60)
    ax[1].set_xlabel("target's tangential speed at 10 m, m/s")
    ax[1].set_ylabel("longest usable scan, seconds")
    ax[1].set_title("but a moving drone outruns any mechanical scan")
    ax[1].legend(fontsize=8, loc="upper right")
    save(fig, "07-scan-budget.png")


# ======================================================================
# 8 — the alternative: bearing from two receivers in one dwell
# ======================================================================
def fig_interferometer():
    """Reads interferometer.json, written by interferometer.py."""
    import json as _json
    f = HERE / "interferometer.json"
    if not f.exists():
        print("skip 08: run interferometer.py first")
        return
    D = _json.loads(f.read_text())
    fig, ax = plt.subplots(1, 3, figsize=(11.5, 3.5))

    # -- accuracy across the beam --------------------------------------
    acc = D["accuracy"]
    t = np.array([r["truth"] for r in acc], float)
    e = np.array([r["err"] for r in acc], float)
    sp = np.array([r["spread"] for r in acc], float)
    ax[0].axhspan(-2.5, 2.5, color=GRN, alpha=0.12)
    ax[0].axhline(2.7, color=ACC, ls="--", lw=1.3)
    ax[0].axhline(-2.7, color=ACC, ls="--", lw=1.3)
    ax[0].errorbar(t, e, yerr=sp, fmt="o-", color=GRN, lw=1.5, ms=4, capsize=2)
    ax[0].axhline(0, color=GREY, lw=0.9)
    ax[0].set_ylim(-3.4, 3.4)
    ax[0].set_xlabel("true azimuth, degrees")
    ax[0].set_ylabel("bearing error, degrees")
    ax[0].set_title("8 · Two receivers, ONE dwell")
    ax[0].annotate("scanning, 9 beams × 64 (4.3 s)", (-15.5, 2.85), color=ACC, fontsize=8)
    ax[0].annotate(f"interferometer, 0.47 s:\nrms {np.sqrt(np.mean(e**2)):.2f}°, "
                   f"worst {np.max(np.abs(e)):.2f}°", (-15.5, -2.9), color=GRN, fontsize=8.5)
    ax[0].annotate(f"unambiguous to ±{D['unambiguous_deg']:.1f}°\non a {D['baseline']*1000:.0f} mm baseline",
                   (0.52, 0.60), xycoords="axes fraction", color=GREY, fontsize=8)

    # -- how far out it keeps working ----------------------------------
    sn = D["vs_snr"]
    x = np.array([r["rcs_db"] for r in sn], float)
    y = np.array([r["rms"] for r in sn], float)
    rng_equiv = TARGET_R * 10 ** (-x / 40.0)          # R^4: -10 dB of echo = 1.78x range
    ax[1].semilogy(rng_equiv, np.maximum(y, 0.02), "o-", color=GRN, lw=1.5, ms=5)
    ax[1].axhline(2.5, color=ACC, ls="--", lw=1.2)
    ax[1].set_xlabel("equivalent range for the same echo, metres")
    ax[1].set_ylabel("bearing rms, degrees")
    ax[1].set_title("holds until detection itself fails")
    ax[1].annotate("2.5° budget", (11, 3.2), color=ACC, fontsize=8)
    ax[1].annotate("the cliff is the CFAR losing\nthe target, not the phase\nmeasurement degrading",
                   (0.05, 0.55), xycoords="axes fraction", color=GREY, fontsize=8)

    # -- the one thing you must control --------------------------------
    cal = D["vs_cal"]
    mm = np.array([r["mm"] for r in cal], float)
    cy = np.array([r["rms"] for r in cal], float)
    ax[2].plot(mm, cy, "o-", color=BLU, lw=1.6, ms=5)
    ax[2].axhline(2.5, color=ACC, ls="--", lw=1.2)
    ax[2].set_xlabel("uncorrected cable-length mismatch, mm")
    ax[2].set_ylabel("bearing rms, degrees")
    ax[2].set_title("calibration is the real requirement")
    ax[2].annotate("2.5° budget", (13.5, 2.8), color=ACC, fontsize=8)
    ax[2].annotate("1 mm of coax = 4.3° of phase\n= 0.43° of bearing, because a\n"
                   "wave is 30 % slower in PTFE.\nThe budget is gone at ~6 mm.\n"
                   "Match the cables, or null the\noffset once on boresight.",
                   (0.04, 0.46), xycoords="axes fraction", color=GREY, fontsize=8)
    save(fig, "08-interferometer.png")


# ======================================================================
if __name__ == "__main__":
    fig_chirp()
    beat, sync = make_audio()
    fig_soundcard(beat, sync)
    cube, timing = segment_chirps(beat, sync, FS, N_CHIRPS)
    assert cube is not None, "segmentation failed"
    t_up, pri = timing
    dets, spec = process(cube, FS, timing, N_CHIRPS, f0=F0, bw=BW)
    fig_segment(beat, sync, cube, timing)
    fig_range_fft(cube)
    fig_range_doppler(cube, timing, dets)
    t_az, a40, a80 = fig_azimuth()
    fig_scan_budget()
    fig_interferometer()

    print("\n--- numbers used in the doc -------------------------------")
    print(f"audio recorded      : {len(beat)} samples = {len(beat)/FS*1e3:.0f} ms per block")
    print(f"measured t_up       : {t_up*1e3:.3f} ms   (set: {T_UP*1e3:.3f})")
    print(f"measured PRI        : {pri*1e3:.3f} ms   (set: {(T_UP+RETRACE)*1e3:.3f})")
    print(f"cube                : {cube.shape} floats")
    print(f"range cell          : {C/(2*BW):.3f} m")
    print(f"beat slope          : {2*BW/(C*T_UP):.2f} Hz per metre")
    print(f"unambiguous vel     : +/- {(C/(F0+BW/2))/(4*pri):.2f} m/s")
    print(f"detections          : {[(round(d[0],2), round(d[1],2), round(d[2],1)) for d in dets]}")
    import numpy as _np
    print(f"azimuth worst error : {_np.nanmax(_np.abs(a40-t_az)):.1f} deg at 40 MHz, "
          f"{_np.nanmax(_np.abs(a80-t_az)):.1f} deg at 80 MHz")
    print(f"target FFT bin      : {2*40e6*TARGET_R/C:.2f} bins from DC at 40 MHz, "
          f"{2*BW*TARGET_R/C:.2f} on the {BW/1e6:.1f} MHz sweep now in use")
    n_blk = int((T_UP+RETRACE)*FS*(N_CHIRPS+2))
    print(f"audio per block     : {n_blk*2*2/1024:.0f} KB   cube {cube.nbytes/1024:.0f} KB   "
          f"RD map {N_CHIRPS*(cube.shape[1]//2)*8/1024:.0f} KB   fix ~100 B")
