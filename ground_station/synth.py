#!/usr/bin/env python3
"""
synth.py — the synthetic sound card, and the sync segmentation that both the
synthetic and the real one go through.

    SynthSource     what the sound card WOULD see, given a list of targets.
    segment_chirps  cut a beat channel into an (n_chirps, n_samples) cube on
                    the sync square wave's edges, and MEASURE the two timings
                    (up-chirp, PRI) while doing it.

Moved out of radar_acquire.py so that there is exactly ONE generator: stage 1
(radar_acquire.py, test_radar.py) and stage 2 (stage2/acquire_az.py, sar.py,
test_stage2.py) all drive this same code.

SynthSource keeps its two-receiver parameters -- n_rx, switched, cal_rad,
marker/marker_after, baseline_m -- even though stage 1 never uses them. Stage 1
always asks for n_rx=1 and leaves switched False, and in that state every one
of them is inert: there is one channel, no interferometric phase, no chain
offset and no frame marker in the sync. They are kept because stage2/ depends
on them to model the second receiver, and deleting them would mean rewriting
the stage-2 code that is already written and passing. baseline_m defaults to
fmcw_sim.DEFAULT_BASELINE_M, which is the one definition of the horn spacing.
"""

import math

import numpy as np

import fmcw_sim
from dsp import beam_gain

F0_HZ = 2.400e9          # defaults: the whole ISM band, 2400-2483.5 MHz, which is what
BW_HZ = 83.5e6           # radar_ctl ships with. Overridden by radar_acquire's
                         # --f0-mhz/--bw-mhz, or by radar_ctl's status when --ctl is
                         # used. Keep this in step with SWEEP_BW_HZ in
                         # firmware/radar_ctl: the beat->range scale is linear in the
                         # bandwidth, so an 80 MHz assumption against an 83.5 MHz
                         # sweep over-reports every range by 4.4 %.
SYNC_FRAC = 0.5          # sync threshold as a fraction of the sync channel's peak
SETTLE_FRAC = 0.05       # drop the first 5 % of each chirp (PLL settle)


# ----------------------------------------------------------------------
# sync + segmentation
# ----------------------------------------------------------------------

def segment_chirps(beat, sync, fs, n_chirps, return_edges=False,
                   dc_per_chirp=False):
    """Cut the beat channel into an (n_chirps, n_samples) cube using the sync
    square wave. Returns (cube, t_chirp_s). t_chirp is MEASURED from the sync,
    never assumed — the stepped PLL sweep's real period is set by the ESP32's
    step_us and any drift shows up here first.

    dc_per_chirp is off; see the comment where it is applied. It is the reason
    near-range accuracy used to be a metre out at 3 m."""
    # Sound-card inputs are AC-coupled: an 86 %-duty square wave arrives as
    # a small positive plateau that droops, and a big negative retrace pulse.
    # Levels are useless; the EDGES survive coupling intact, so detect the
    # jumps in the derivative instead of thresholding the level.
    s = sync.astype(float)
    d = np.diff(s)
    dmax = max(float(np.max(d)), 1e-6); dmin = min(float(np.min(d)), -1e-6)
    up = np.flatnonzero(d > SYNC_FRAC * dmax) + 1      # chirp starts
    dn = np.flatnonzero(d < SYNC_FRAC * dmin) + 1      # chirp ends
    # collapse edge clusters (a jump can span 2-3 samples after the card's AA filter)
    def collapse(idx):
        if idx.size == 0:
            return idx
        keep = [idx[0]]
        for i in idx[1:]:
            if i - keep[-1] > 8:
                keep.append(i)
        return np.array(keep)
    edges, falls = collapse(up), collapse(dn)
    if len(edges) < n_chirps + 1:
        return (None, None, None) if return_edges else (None, None)
    # up-chirp length: median rising->falling gap
    lens = []
    for r in edges:
        f = falls[falls > r]
        if f.size:
            lens.append(f[0] - r)
    n_up = int(np.median(lens))
    skip = int(SETTLE_FRAC * n_up)
    n_s = n_up - skip
    rows = []
    for r in edges[:n_chirps]:
        seg = beat[r + skip:r + skip + n_s]
        if seg.size == n_s:
            rows.append(seg)
    if len(rows) < n_chirps:
        return (None, None, None) if return_edges else (None, None)
    cube = np.array(rows, dtype=float)
    if dc_per_chirp:
        # OFF by default, and it used to be on. Subtracting a constant from a
        # chirp removes a WINDOW-SHAPED lobe centred on range bin 0, about two
        # bins wide -- so it eats part of any target inside two bins of DC,
        # which on the 83.5 MHz sweep is everything closer than 3.6 m (it was
        # 7.5 m at 40 MHz), and biases the peak outward. Measured over 3-20 m it
        # cost a mean 0.27 m and 1.05 m at 3 m; without it, 0.04 m and 0.04 m. The DC it was meant to remove is
        # already gone twice over: the sound card is AC-coupled, and
        # range_doppler(bg_subtract=True) subtracts the average chirp. Keep the
        # switch only so the regression test can show the difference.
        cube -= cube.mean(axis=1, keepdims=True)
    pri = float(np.median(np.diff(edges[:n_chirps + 1]))) / fs
    if return_edges:
        return cube, (n_up / fs, pri), edges[:n_chirps + 1]
    return cube, (n_up / fs, pri)


# ----------------------------------------------------------------------
# the synthetic sound card
# ----------------------------------------------------------------------

class SynthSource:
    """What the sound card WOULD see, for one or two receivers.

    Same physics as fmcw_sim.simulate: a single-ended (real) beat signal per
    up-chirp, a retrace gap, and the sync square wave, at absolute 16-bit
    levels so beam-to-beam amplitude comparison works. The range walk between
    chirps uses the PRI (up-chirp + retrace), like the hardware.

    With n_rx=2 it also produces the second receiver. That channel carries the
    interferometric phase 2*pi*d*sin(az)/lam on every target -- the receive
    path is longer by d*sin(az), the transmit path is common -- plus whatever
    fixed chain offset you ask for with cal_rad, which is how the calibration
    step gets tested. Noise is independent between channels; the sync is one
    physical channel and is shared.

    switched=True models the RF-switch build instead: one receiver, but the
    antenna alternates chirp by chirp, so even chirps carry antenna A and odd
    chirps carry antenna B one PRI later.

    n_steps models the waveform the hardware ACTUALLY transmits. radar_ctl does
    not ramp: it steps an ADF4351 through n_steps discrete frequencies, so the
    beat is a staircase, not a tone. Leave it None for the ideal linear chirp
    (which is what every measurement in this repo used before it existed).

    read() returns (beats, sync) where beats is a list of channels.
    """

    ADC_SCALE = 3.0e5          # sqrt(mW) -> counts; leakage ~ -22 dBm fits int16

    def __init__(self, fs, t_chirp, n_chirps, targets, retrace_s=1e-3,
                 beam_az=0.0, bw_az=36.0, seed=0, isolation_db=35.0,
                 f0=None, bw=None, n_rx=1, baseline_m=fmcw_sim.DEFAULT_BASELINE_M,
                 cal_rad=0.0, switched=False, marker=True, marker_after=2,
                 n_steps=None, band_select_us=20.0, lock_tau_us=10.0,
                 clutter_cancel_db=None):
        self.fs, self.t_chirp, self.n_chirps = fs, t_chirp, n_chirps
        self.targets, self.retrace_s = targets, retrace_s
        self.beam_az, self.bw_az = beam_az, bw_az
        self.rng = np.random.default_rng(seed)
        self.n_rx = 1 if switched else int(n_rx)
        self.baseline_m = float(baseline_m)
        self.cal_rad = float(cal_rad)
        self.switched = bool(switched)
        self.marker, self.marker_after = bool(marker), int(marker_after)
        self.n_steps = None if n_steps is None else int(n_steps)
        # How well a STATIC target actually cancels chirp to chirp. None means
        # perfectly, which is what every measurement in this repo assumed until
        # a room was put in one. Real clutter does not repeat exactly: the mount
        # flexes, the air moves, the chain drifts. Modelled as a per-chirp gain
        # wobble at the stated ratio, which is crude but is the difference
        # between "the room subtracts away" and "the room is the noise floor".
        self.clutter_cancel_db = clutter_cancel_db
        self.band_select_us = float(band_select_us)
        self.lock_tau_us = float(lock_tau_us)
        self.spec = fmcw_sim.RadarSpec(f0=f0 or F0_HZ, bw=bw or BW_HZ, t_chirp=t_chirp, fs=fs,
                                       n_chirps=n_chirps, gt_dbi=13.4, gr_dbi=13.4,
                                       isolation_db=isolation_db)
        self.frames = None

    # -- what the transmitter is actually doing ------------------------
    def _t_held(self, t):
        """Map real time to the time the transmit frequency has reached.

        For an ideal linear ramp these are the same thing, and the beat is a
        tone. The hardware is not a ramp: radar_ctl writes the ADF4351 once per
        step and holds, so the transmit frequency is a staircase and the beat
        is that staircase sampled -- one plateau per step, ~4.8 audio samples
        wide at 48 kHz and 100 us steps.

        Two things happen at every step edge, and both are in here:

          band select   writing R0 retriggers the ADF4351's VCO band select.
                        20 us with R3 DB23 set (which radar_ctl does set; it is
                        80 us without, longer than most of the step). The output
                        is still on the OLD frequency through this.
          loop settling then the loop pulls in, modelled first-order with
                        lock_tau_us. 20 + 3*10 = 50 us of a 100 us step.

        Because phase is 4*pi*f(t)*r/c and the ramp is linear in t, quantising
        f is exactly quantising t -- so this returns a time and the caller's
        existing beat expression is unchanged."""
        if self.n_steps is None:
            return t
        t_step = self.t_chirp / self.n_steps
        k = np.floor(t / t_step + 1e-12)
        dt = t - k * t_step
        held = k * t_step                       # the settled staircase
        bs = self.band_select_us * 1e-6
        tau = self.lock_tau_us * 1e-6
        if bs > 0 or tau > 0:
            # during band select the frequency has not moved at all; after it,
            # relax from the previous step's value to this one
            prev = held - t_step
            settling = np.where(
                dt < bs, prev,
                held - t_step * np.exp(-np.maximum(dt - bs, 0.0) / max(tau, 1e-12)))
            held = settling
        return held

    # -- the extra phase antenna B sees, per target -------------------
    def _rx_phase(self, rx_index, az_deg):
        if rx_index == 0:
            return 0.0
        return (2.0 * math.pi * self.baseline_m * math.sin(math.radians(az_deg))
                / self.spec.lam) + self.cal_rad

    def read(self):
        s = self.spec
        n_up = int(round(self.fs * self.t_chirp))
        n_gap = int(round(self.retrace_s * self.fs))
        pri = (n_up + n_gap) / self.fs
        t = np.arange(n_up) / self.fs
        th = self._t_held(t)          # the ramp time the transmitter has reached
        noise_w = fmcw_sim.K_BOLTZ * fmcw_sim.T0 * (self.fs / 2) * 10 ** (s.nf_db / 10)
        noise_amp = math.sqrt(noise_w * 1e3)
        lk = math.sqrt(10 ** ((s.pt_dbm - s.isolation_db) / 10))

        n_out = self.n_rx
        beats = [[] for _ in range(n_out)]
        sync = []
        for k in range(self.n_chirps + 2):
            tk = k * pri
            # which antenna is connected on this chirp
            # A on even chirps counted from the chirp after the marker
            ant = ((k - self.marker_after - 1) % 2) if self.switched else None
            for j in range(n_out):
                rx = ant if self.switched else j
                sig = np.zeros(n_up)
                for (r, az, v, rcs) in self.targets:
                    g = beam_gain(az - self.beam_az, self.bw_az)
                    if g <= 1e-3:
                        continue
                    rt = r + v * tk
                    amp = math.sqrt(10 ** (s.rx_dbm(rt, rcs * g * g) / 10))
                    sig += amp * np.cos(2 * math.pi * s.beat_hz(rt) * th
                                        + 4 * math.pi * rt / s.lam
                                        + self._rx_phase(rx, az))
                sig += lk * np.cos(2 * math.pi * s.beat_hz(0.3) * th)
                sig += noise_amp * self.rng.normal(size=n_up)
                if self.clutter_cancel_db is not None:
                    sig = sig * (1.0 + 10 ** (-self.clutter_cancel_db / 20.0)
                                 * self.rng.normal())
                beats[j].append(sig)
                beats[j].append(np.zeros(n_gap))

            sync.append(np.ones(n_up))
            sync.append(np.zeros(n_gap))
            # radar_ctl marks each block by SKIPPING one chirp -- sync stays low
            # for a whole extra PRI -- just before the switch returns to antenna
            # A. The gap is then ~2x every other gap and unmistakable, which is
            # what lets the receiver tell the two antennas apart at all
            # (stage2/interferometer.py tdm_parity). It costs 1.5 % of the dwell.
            if self.switched and self.marker and k == self.marker_after:
                sync.append(np.zeros(n_up + n_gap))
                beats[0].append(np.zeros(n_up + n_gap))

        out = []
        for j in range(n_out):
            x = np.clip(np.concatenate(beats[j]) * self.ADC_SCALE, -32767, 32767)
            out.append(self._couple(x))
        return out, self._couple(np.concatenate(sync) * 20000.0)

    def _couple(self, x):
        """The sound card's AC coupling, ~10 Hz one-pole high-pass. The sync
        square wave droops and loses its DC level; the edges survive."""
        a = math.exp(-2 * math.pi * 10.0 / self.fs)
        try:
            from scipy.signal import lfilter
            return lfilter([a, -a], [1.0, -a], x)
        except Exception:                      # numpy-only fallback
            y = np.empty_like(x); px = py = 0.0
            for i, v in enumerate(x):
                py = a * (py + v - px); px = v; y[i] = py
            return y

    def close(self):
        pass
