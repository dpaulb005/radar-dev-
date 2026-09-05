#!/usr/bin/env python3
"""
fmcw_sim.py — simulator + link budget for an MIT-style 2.4 GHz FMCW radar.

Build the radar in software before you buy $400 of RF parts. This models the
real signal chain of the MIT "coffee can" radar (RES.LL-003) and answers the
questions that decide whether the build is worth it:

  * what range resolution and max range do I get for a given sweep?
  * how far can it actually see a small drone (RCS ~0.01 m^2)?
  * what does the TX->RX leakage do to me at 5-10 m, and does background
    subtraction rescue it?

Physics
-------
An FMCW radar sweeps its carrier linearly over bandwidth B in time T. A target
at range R returns a copy delayed by tau = 2R/c; mixing it with the outgoing
chirp gives a *beat* tone

    f_beat = (B/T) * tau = 2*B*R / (c*T)        -> range is a frequency

    range resolution   dR   = c / (2B)
    max unambiguous R  Rmax = c*T*(fs/2) / (2B)   (fs = ADC/soundcard rate)
    Doppler            f_d  = 2*v/lambda          (from chirp-to-chirp phase)

So a range FFT per chirp gives a range profile, and a second FFT across chirps
gives velocity -> the range-Doppler map.

Usage
-----
    python fmcw_sim.py                    # spec sheet for the MIT build
    python fmcw_sim.py --budget           # detection range vs target RCS
    python fmcw_sim.py --rdmap out.png    # simulated range-Doppler map
    python fmcw_sim.py --leakage          # TX leakage + background subtraction
    python fmcw_sim.py --sweep-bw 400     # what a wider VCO would buy you
"""

import argparse
import math

import numpy as np

C = 299_792_458.0
K_BOLTZ = 1.380649e-23
T0 = 290.0


# ----------------------------------------------------------------------
class RadarSpec:
    """The MIT coffee-can radar as built, with everything overridable."""

    def __init__(self, **kw):
        self.f0 = 2.36e9          # sweep start (Hz)   measured 2.36-2.50 GHz
        self.bw = 140e6           # sweep bandwidth (Hz)
        self.t_chirp = 20e-3      # sweep period (s)   MIT default ~20 ms
        self.fs = 44_100.0        # sound-card sample rate (Hz)
        self.pt_dbm = 13.0        # transmit power (+13 dBm ~ 20 mW)
        self.gt_dbi = 9.0         # TX antenna gain (coffee can ~9, Vivaldi ~8-10)
        self.gr_dbi = 9.0         # RX antenna gain
        self.nf_db = 4.0          # system noise figure
        self.losses_db = 3.0      # cable/connector/mismatch losses
        self.snr_req_db = 13.0    # SNR needed for a confident detection
        self.n_chirps = 64        # chirps integrated for the Doppler FFT
        self.isolation_db = 35.0  # TX->RX antenna isolation (separate cans)
        self.adc_bits = 16        # laptop sound card
        self.adc_derate_db = 12.0 # real SFDR falls short of 6.02*bits
        self.__dict__.update(kw)

    # ---- derived ----
    @property
    def fc(self):
        return self.f0 + self.bw / 2

    @property
    def lam(self):
        return C / self.fc

    @property
    def range_res(self):
        return C / (2 * self.bw)

    @property
    def r_max(self):
        """Range at the Nyquist beat frequency (fs/2)."""
        return C * self.t_chirp * (self.fs / 2) / (2 * self.bw)

    @property
    def v_max(self):
        """Unambiguous velocity from chirp-to-chirp phase (+/-)."""
        return self.lam / (4 * self.t_chirp)

    @property
    def v_res(self):
        return self.lam / (2 * self.n_chirps * self.t_chirp)

    def beat_hz(self, r):
        return 2 * self.bw * r / (C * self.t_chirp)

    def range_of_beat(self, f):
        return f * C * self.t_chirp / (2 * self.bw)

    # ---- link budget ----
    def noise_floor_dbm(self):
        """Noise in one range-FFT bin, after coherent Doppler integration."""
        bin_bw = 1.0 / self.t_chirp                       # range-FFT bin width
        n_w = K_BOLTZ * T0 * bin_bw
        n_dbm = 10 * math.log10(n_w / 1e-3) + self.nf_db
        n_dbm -= 10 * math.log10(self.n_chirps)           # coherent gain
        return n_dbm

    def rx_dbm(self, r, rcs):
        """Radar equation: received echo power (dBm) from RCS at range r."""
        if r <= 0:
            return float("inf")
        num_db = (self.pt_dbm + self.gt_dbi + self.gr_dbi
                  + 20 * math.log10(self.lam) + 10 * math.log10(rcs))
        den_db = 30 * math.log10(4 * math.pi) + 40 * math.log10(r)
        return num_db - den_db - self.losses_db

    def max_range(self, rcs):
        """Range where SNR falls to snr_req_db."""
        mds = self.noise_floor_dbm() + self.snr_req_db
        # solve rx_dbm(r) == mds  ->  r^4 scaling, invert analytically
        num_db = (self.pt_dbm + self.gt_dbi + self.gr_dbi
                  + 20 * math.log10(self.lam) + 10 * math.log10(rcs)
                  - 30 * math.log10(4 * math.pi) - self.losses_db)
        return 10 ** ((num_db - mds) / 40)

    def snr_db(self, r, rcs):
        return self.rx_dbm(r, rcs) - self.noise_floor_dbm()

    # ---- the budget that actually decides performance ----
    def leakage_dbm(self):
        """TX power that leaks straight into the RX chain."""
        return self.pt_dbm - self.isolation_db

    def usable_dr_db(self):
        """Usable dynamic range of the digitiser, plus coherent FFT gain."""
        raw = 6.02 * self.adc_bits - self.adc_derate_db
        fft_gain = 10 * math.log10(self.fs * self.t_chirp * self.n_chirps / 2)
        return raw + fft_gain

    def practical_mds_dbm(self):
        """Smallest echo you can dig out, given leakage eats the ADC range.

        A short-range FMCW radar is almost never thermal-noise limited: the
        TX->RX leakage sits at the ADC input and everything more than the
        converter's dynamic range below it is unrecoverable. This is why RF
        leakage cancellation (not a better LNA) is the real upgrade path.
        """
        return max(self.leakage_dbm() - self.usable_dr_db(),
                   self.noise_floor_dbm() + self.snr_req_db)

    def max_range_practical(self, rcs):
        mds = self.practical_mds_dbm()
        num_db = (self.pt_dbm + self.gt_dbi + self.gr_dbi
                  + 20 * math.log10(self.lam) + 10 * math.log10(rcs)
                  - 30 * math.log10(4 * math.pi) - self.losses_db)
        return 10 ** ((num_db - mds) / 40)


# ----------------------------------------------------------------------
def spec_sheet(s: RadarSpec):
    print("=" * 70)
    print("  FMCW RADAR SPEC — MIT coffee-can architecture")
    print("=" * 70)
    print(f"  carrier            : {s.fc/1e9:.3f} GHz  (sweep {s.f0/1e9:.2f}"
          f"-{(s.f0+s.bw)/1e9:.2f} GHz)")
    print(f"  sweep bandwidth    : {s.bw/1e6:.0f} MHz")
    print(f"  chirp period       : {s.t_chirp*1e3:.0f} ms")
    print(f"  sample rate        : {s.fs/1e3:.1f} kHz  (laptop sound card)")
    print(f"  transmit power     : {s.pt_dbm:.0f} dBm ({10**(s.pt_dbm/10):.0f} mW)")
    print(f"  antenna gain       : {s.gt_dbi:.0f} dBi TX / {s.gr_dbi:.0f} dBi RX")
    print("-" * 70)
    print(f"  RANGE RESOLUTION   : {s.range_res:.2f} m      <- set by bandwidth, c/2B")
    print(f"  max unambig. range : {s.r_max:.0f} m       <- set by sound-card Nyquist")
    print(f"  velocity window    : +/-{s.v_max:.1f} m/s")
    print(f"  velocity resolution: {s.v_res:.2f} m/s   ({s.n_chirps} chirps"
          f" = {s.n_chirps*s.t_chirp:.2f} s dwell)")
    print(f"  noise floor / bin  : {s.noise_floor_dbm():.1f} dBm")
    print(f"  beat freq @ 10 m   : {s.beat_hz(10):.0f} Hz")
    print("=" * 70)


TARGETS = [
    ("small quad drone (ESP-BLAST class)", 0.01),
    ("larger quad (DJI Phantom class)", 0.10),
    ("human", 1.0),
    ("car", 10.0),
]


def budget(s: RadarSpec):
    print("\n  DETECTION RANGE vs TARGET")
    print(f"  thermal floor      : {s.noise_floor_dbm():.1f} dBm/bin "
          f"({s.n_chirps}-chirp coherent)")
    print(f"  TX leakage into RX : {s.leakage_dbm():.1f} dBm "
          f"(at {s.isolation_db:.0f} dB isolation)")
    print(f"  usable dynamic rng : {s.usable_dr_db():.1f} dB "
          f"({s.adc_bits}-bit ADC + FFT gain)")
    print(f"  PRACTICAL MDS      : {s.practical_mds_dbm():.1f} dBm  <- what limits you\n")
    print(f"  {'target':<34} {'RCS':>6} | {'echo @10m':>10} | {'SNR @10m':>9} | {'range*':>7}")
    print(f"  {'-'*34} {'-'*6}-+-{'-'*10}-+-{'-'*9}-+-{'-'*7}")
    for name, rcs in TARGETS:
        rp = min(s.max_range_practical(rcs), s.r_max)
        echo = s.rx_dbm(10.0, rcs)
        snr = echo - s.practical_mds_dbm()
        print(f"  {name:<34} {rcs:>5.2f}  | {echo:>7.0f} dBm | {snr:>6.0f} dB | {rp:>5.0f} m")
    print("\n  * free-space range, Nyquist-capped. Treat it as an UPPER BOUND:")
    print("    beyond a few tens of metres, ground/tree/building clutter fills the")
    print("    range bins long before thermal noise does. The number that matters")
    print("    for a 5-10 m drone cage is the SNR column, and it has huge margin.")
    print("\n  'practical' assumes the leakage is digitised along with the echo,")
    print("  which is the normal case for a two-antenna FMCW radar. 'thermal' is")
    print("  the unreachable upper bound if leakage were perfectly cancelled.")
    if s.v_max < 5:
        print(f"\n  !! Doppler window is only +/-{s.v_max:.1f} m/s at a "
              f"{s.t_chirp*1e3:.0f} ms chirp.")
        print(f"     A drone flying faster than that ALIASES. Shorten the chirp:")
        for tc in (5e-3, 2e-3, 1e-3):
            vm = s.lam / (4 * tc)
            rm = C * tc * (s.fs / 2) / (2 * s.bw)
            print(f"       {tc*1e3:>4.0f} ms chirp -> +/-{vm:5.1f} m/s, "
                  f"max range {rm:5.0f} m")


# ----------------------------------------------------------------------
def simulate(s: RadarSpec, targets, seed=0, leakage=True):
    """Generate the beat-signal data cube: (n_chirps, n_samples).

    targets: list of (range_m, velocity_mps, rcs_m2)
    """
    rng = np.random.default_rng(seed)
    n_s = int(s.fs * s.t_chirp)
    t = np.arange(n_s) / s.fs
    cube = np.zeros((s.n_chirps, n_s), dtype=complex)

    noise_w = K_BOLTZ * T0 * (s.fs / 2) * 10 ** (s.nf_db / 10)
    noise_amp = math.sqrt(noise_w * 1e3)          # to sqrt(mW) amplitude units

    for k in range(s.n_chirps):
        tk = k * s.t_chirp
        sig = np.zeros(n_s, dtype=complex)
        for (r, v, rcs) in targets:
            rt = r + v * tk                        # range walks with velocity
            amp = 10 ** (s.rx_dbm(rt, rcs) / 20) / 10 ** (0 / 20)
            amp = math.sqrt(10 ** (s.rx_dbm(rt, rcs) / 10))   # sqrt(mW)
            fb = s.beat_hz(rt)
            phase = 2 * math.pi * (fb * t) + 4 * math.pi * rt / s.lam
            sig += amp * np.exp(1j * phase)
        if leakage:
            # TX->RX leakage: strong, ~zero range, static
            lk = math.sqrt(10 ** ((s.pt_dbm - s.isolation_db) / 10))
            sig += lk * np.exp(1j * (2 * math.pi * s.beat_hz(0.3) * t))
        sig += noise_amp * (rng.normal(size=n_s) + 1j * rng.normal(size=n_s)) / math.sqrt(2)
        cube[k] = sig
    return cube


def range_doppler(cube, s: RadarSpec, bg_subtract=False):
    """Range FFT then Doppler FFT. Returns (rd_db, range_axis, vel_axis)."""
    c = cube.copy()
    if bg_subtract:
        c -= c.mean(axis=0, keepdims=True)     # kill static leakage + clutter
    win_r = np.hanning(c.shape[1])
    # complex (I/Q) beat signal -> full FFT, keep the positive-range half.
    # NOTE: the stock MIT radar has a single real mixer output, so on real
    # hardware you get |Doppler| without its sign until you add an I/Q mixer.
    n_half = c.shape[1] // 2
    rng_fft = np.fft.fft(c * win_r, axis=1)[:, :n_half]
    win_d = np.hanning(c.shape[0])[:, None]
    rd = np.fft.fftshift(np.fft.fft(rng_fft * win_d, axis=0), axes=0)
    rd_db = 20 * np.log10(np.abs(rd) + 1e-15)
    n_bins = rng_fft.shape[1]
    freqs = np.arange(n_bins) * s.fs / c.shape[1]
    ranges = s.range_of_beat(freqs)
    vels = np.fft.fftshift(np.fft.fftfreq(c.shape[0], s.t_chirp)) * s.lam / 2
    return rd_db, ranges, vels


def leakage_demo(s: RadarSpec):
    tgt = [(8.0, 2.0, 0.01)]     # drone at 8 m closing at 2 m/s
    print("\n  TX LEAKAGE TEST — drone (RCS 0.01 m^2) at 8 m, 2 m/s")
    print(f"  antenna isolation assumed {s.isolation_db:.0f} dB\n")
    for bg in (False, True):
        cube = simulate(s, tgt, leakage=True)
        rd, ranges, vels = range_doppler(cube, s, bg_subtract=bg)
        # look only at plausible ranges
        m = (ranges > 2) & (ranges < 40)
        peak = rd[:, m].max()
        # noise estimate away from the target
        # noise reference: the far half of whatever range window this
        # chirp length actually supports (avoids an empty slice)
        far = ranges > (0.6 * ranges.max())
        floor = np.median(rd[:, far]) if far.any() else np.median(rd)
        # is the drone the strongest thing in the search window?
        idx = np.unravel_index(np.argmax(rd[:, m]), rd[:, m].shape)
        r_det = ranges[m][idx[1]]
        v_det = vels[idx[0]]
        label = "WITH background subtraction" if bg else "raw (leakage present)"
        print(f"   {label:<30} peak {peak-floor:5.1f} dB over floor | "
              f"detected R={r_det:5.1f} m  v={v_det:+5.1f} m/s"
              + ("   <-- correct" if abs(r_det - 8) < 2 else "   <-- WRONG (leakage wins)"))
    print("\n  Background subtraction removes anything that doesn't move, which is")
    print("  exactly what TX leakage and ground clutter are. It is the single most")
    print("  important line of DSP in a short-range FMCW radar.")


def micro_doppler(s: RadarSpec, rpm=20000, prop_in=2.5, n_blades=3):
    """Rotor micro-Doppler — how you see a HOVERING drone.

    Background subtraction deletes zero-Doppler returns, so a hovering drone
    vanishes as body-clutter. But its rotors don't hover: the blades sweep at
    tens of m/s, painting Doppler sidebands ("rotor lines") far from DC. That
    signature is what distinguishes a drone from a bird, a person, or a tree,
    and it survives clutter cancellation.
    """
    r_tip = prop_in * 0.0254 / 2
    rev_s = rpm / 60.0
    v_tip = 2 * math.pi * r_tip * rev_s
    f_tip = 2 * v_tip / s.lam                      # Doppler at blade tip
    f_blade = n_blades * rev_s                     # blade-flash rate
    print("\n  ROTOR MICRO-DOPPLER — seeing a drone that is NOT translating")
    print(f"    prop {prop_in}\" , {rpm} RPM, {n_blades} blades")
    print(f"    blade tip speed      : {v_tip:.0f} m/s")
    print(f"    tip Doppler          : +/-{f_tip/1e3:.2f} kHz "
          f"(equivalent to +/-{v_tip:.0f} m/s of 'velocity')")
    print(f"    blade flash rate     : {f_blade:.0f} Hz")
    print(f"    audible in the beat signal? {'YES' if f_tip < s.fs/2 else 'NO - above Nyquist'}"
          f"  (sound card Nyquist {s.fs/2/1e3:.1f} kHz)")
    print(f"    body Doppler if hovering: 0 Hz  -> removed by clutter cancellation")
    print("\n    => Detect a hovering drone on the ROTOR LINES, not the body return.")
    print("       In the MIT radar's CW 'Doppler mode' these appear directly in the")
    print("       audio spectrum. Look for a symmetric pair of sidebands out at")
    print(f"       ~{f_tip/1e3:.1f} kHz that switch on and off with the throttle.")
    if f_tip > s.v_max * 2 / s.lam * 2:
        pass
    print(f"\n    NOTE: this is far outside the +/-{s.v_max:.1f} m/s range-Doppler")
    print("       window, so it lives in the raw spectrum, not the RD map.")


def rdmap(s: RadarSpec, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    targets = [(8.0, 2.5, 0.01),     # our drone, closing
               (18.0, -1.5, 0.10),   # a bigger quad, receding
               (30.0, 0.0, 1.0)]     # a person, static-ish
    cube = simulate(s, targets)
    rd, ranges, vels = range_doppler(cube, s, bg_subtract=True)
    m = ranges <= 60
    rd = rd[:, m]; ranges = ranges[m]
    rd -= rd.max()

    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(9, 6))
    fig.patch.set_facecolor("#0d0d0d"); ax.set_facecolor("#0d0d0d")
    im = ax.pcolormesh(ranges, vels, rd, cmap="turbo", vmin=-45, vmax=0,
                       shading="auto")
    for (r, v, rcs) in targets:
        ax.plot(r, v, "o", mfc="none", mec="w", ms=14, mew=1.5)
        ax.annotate(f"RCS {rcs} m²", (r, v), textcoords="offset points",
                    xytext=(12, 8), color="w", fontsize=8)
    ax.set_xlabel("range [m]"); ax.set_ylabel("radial velocity [m/s]")
    ax.set_title(f"Simulated range-Doppler map — {s.bw/1e6:.0f} MHz sweep, "
                 f"ΔR={s.range_res:.2f} m, {s.n_chirps} chirps",
                 color="#c3c2b7", fontsize=10)
    fig.colorbar(im, ax=ax, label="dB (rel. peak)")
    fig.tight_layout(); fig.savefig(path, dpi=110)
    print(f"  wrote {path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--budget", action="store_true")
    ap.add_argument("--rdmap", metavar="PNG")
    ap.add_argument("--leakage", action="store_true")
    ap.add_argument("--microdoppler", action="store_true",
                    help="rotor micro-Doppler: how to see a hovering drone")
    ap.add_argument("--rpm", type=float, default=20000)
    ap.add_argument("--sweep-bw", type=float, help="override sweep bandwidth (MHz)")
    ap.add_argument("--f0", type=float, help="override sweep start frequency (GHz)")
    ap.add_argument("--chirp-ms", type=float, help="override chirp period (ms)")
    ap.add_argument("--gain", type=float, help="override antenna gain (dBi, both)")
    ap.add_argument("--fs", type=float, help="override sample rate (Hz)")
    args = ap.parse_args()

    kw = {}
    if args.sweep_bw: kw["bw"] = args.sweep_bw * 1e6
    if args.f0: kw["f0"] = args.f0 * 1e9
    if args.chirp_ms: kw["t_chirp"] = args.chirp_ms * 1e-3
    if args.gain is not None: kw["gt_dbi"] = kw["gr_dbi"] = args.gain
    if args.fs: kw["fs"] = args.fs
    s = RadarSpec(**kw)

    if args.microdoppler:
        spec_sheet(s); micro_doppler(s, rpm=args.rpm)
    elif args.rdmap:
        rdmap(s, args.rdmap)
    elif args.leakage:
        spec_sheet(s); leakage_demo(s)
    elif args.budget:
        spec_sheet(s); budget(s)
    else:
        spec_sheet(s); budget(s)


if __name__ == "__main__":
    main()
