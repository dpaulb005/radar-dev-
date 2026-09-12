#!/usr/bin/env python3
"""
radar_acquire.py — live FMCW radar processing for the horn-fed can radar.

The real-hardware twin of radar_twin.py. Same DSP (range_doppler from
fmcw_sim, cfar_detect from radar_twin, bearing from interferometer), but the
beat signal comes from the sound card instead of the simulator:

    sound card L = beat signal (video amp out)
    sound card R = chirp SYNC from radar_ctl (HIGH during the up-chirp)

Modes:
    --range-only            stage 1: range and velocity from one receiver
    --interferometer        stage 2: AZIMUTH, from the phase between two
                            receivers, in one dwell. This is how bearing is
                            measured. Needs 3 audio channels: beat A, beat B,
                            sync (a UMC404HD; two UCA202s cannot do phase).
    --switched              stage 2 on one chain and an RF switch: antennas
                            alternate chirp by chirp, and the one-PRI motion
                            phase is corrected from the measured velocity.
    --ctl /dev/ttyUSB0      drive the optional turntable. It POINTS the beam;
                            it no longer measures azimuth. The beam-scan
                            centroid below is legacy and only works on a
                            target that is nearly stationary.
    --server http://...     push fixes into the console (server.py /api/radar)

Test it with no hardware at all:
    python radar_acquire.py --selftest            # synthetic target at 8 m
    python radar_acquire.py --replay capture.wav  # a recorded session

Record raw audio for later replay with --record capture.wav.
"""

import argparse
import json
import math
import pathlib
import sys
import time
import wave

import numpy as np

import fmcw_sim
import interferometer as interf
from radar_twin import ScanningRadar, cfar_detect

F0_HZ = 2.400e9          # defaults: the whole ISM band, 2400-2483.5 MHz, which is what
BW_HZ = 83.5e6           # radar_ctl ships with. Overridden by --f0-mhz/--bw-mhz, or by
                         # radar_ctl's status when --ctl is used. Keep this in step with
                         # SWEEP_BW_HZ in firmware/radar_ctl: the beat->range scale is
                         # linear in the bandwidth, so an 80 MHz assumption against an
                         # 83.5 MHz sweep over-reports every range by 4.4 %.
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


def process(cube, fs, timing, n_chirps, min_range=1.5, max_range=30.0,
            thresh_db=15.0, f0=None, bw=None):
    """Beat cube -> range-Doppler -> CFAR detections.

    timing = (t_up, pri): the up-chirp sets the beat->range scale, the pulse
    repetition interval (up-chirp + retrace) sets the Doppler axis. They are
    NOT the same number on this hardware, and both are measured from sync."""
    t_chirp, pri = timing
    spec = fmcw_sim.RadarSpec(f0=f0 or F0_HZ, bw=bw or BW_HZ, t_chirp=t_chirp,
                              fs=fs, n_chirps=n_chirps)
    # the sim's range axis assumes n_s = fs*t_chirp samples; we trimmed the
    # settle, so rescale the beat->range mapping to the samples we kept
    # range_doppler derives the beat->range map from spec.t_chirp (the
    # MEASURED up-chirp) and the FFT bin width from the samples it is given,
    # so trimming the settle changes resolution slightly but not the scale.
    rd, ranges, vels = fmcw_sim.range_doppler(cube.astype(complex), spec,
                                              bg_subtract=True)
    vels = vels * (t_chirp / pri)          # Doppler FFT spacing is the PRI
    dets = cfar_detect(rd, ranges, vels, min_range=min_range,
                       max_range=max_range, thresh_db=thresh_db)
    return dets, spec


# ----------------------------------------------------------------------
# sources
# ----------------------------------------------------------------------

class AudioSource:
    """Blocks from a live sound card.

    Two channels (beat, sync) for stage 1 and for the switched interferometer.
    Three (beat A, beat B, sync) for the simultaneous interferometer, which is
    why the interface has to be a 4-input one: all of them must ride the same
    sample clock or the phase between them means nothing.

    read() always returns (beats, sync), where beats is a LIST of channels.
    """

    def __init__(self, device, fs, block_s, record=None, n_beats=1):
        import sounddevice as sd          # lazy: PortAudio only needed live
        self.sd = sd
        self.device = device
        self.fs = fs
        self.n_beats = n_beats
        self.channels = n_beats + 1
        self.frames = int(block_s * fs)
        self.wav = None
        if record:
            self.wav = wave.open(record, "wb")
            self.wav.setnchannels(self.channels)
            self.wav.setsampwidth(2)
            self.wav.setframerate(int(fs))

    def read(self):
        x = self.sd.rec(self.frames, samplerate=self.fs, channels=self.channels,
                        dtype="int16", device=self.device, blocking=True)
        if self.wav:
            self.wav.writeframes(x.tobytes())
        beats = [x[:, i].astype(float) for i in range(self.n_beats)]
        return beats, x[:, self.n_beats].astype(float)

    def close(self):
        if self.wav:
            self.wav.close()


class WavSource:
    """Replay a recording. 2 channels = beat + sync, 3 = beat A + beat B + sync."""

    def __init__(self, path, block_s):
        w = wave.open(path, "rb")
        assert w.getsampwidth() == 2, "need 16-bit PCM"
        nch = w.getnchannels()
        assert nch in (2, 3), f"need 2 or 3 channels, got {nch}"
        self.fs = w.getframerate()
        self.n_beats = nch - 1
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        self.x = data.reshape(-1, nch).astype(float)
        self.frames = int(block_s * self.fs)
        self.pos = 0

    def read(self):
        if self.pos + self.frames > len(self.x):
            return None, None
        blk = self.x[self.pos:self.pos + self.frames]
        self.pos += self.frames
        return [blk[:, i] for i in range(self.n_beats)], blk[:, self.n_beats]

    def close(self):
        pass


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
                 f0=None, bw=None, n_rx=1, baseline_m=interf.DEFAULT_BASELINE_M,
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
        from radar_twin import beam_gain
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
            # (interferometer.tdm_parity). It costs 1.5 % of the dwell.
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


# ----------------------------------------------------------------------
# radar_ctl link
# ----------------------------------------------------------------------

class Ctl:
    def __init__(self, port, baud=115200):
        import serial
        self.ser = serial.Serial(port, baud, timeout=2.0)
        time.sleep(1.5)                      # ESP32 reset on open
        self.ser.reset_input_buffer()
        self.status = self.cmd("?")

    def sweep(self, on):
        self.cmd(f"SWEEP {1 if on else 0}")
        self.status = self.cmd("?")

    def cmd(self, line):
        self.ser.write((line + "\n").encode())
        t0 = time.time()
        while time.time() - t0 < 8.0:
            resp = self.ser.readline().decode(errors="ignore").strip()
            if not resp:
                continue
            if resp.startswith("{"):
                try:
                    return json.loads(resp)
                except json.JSONDecodeError:
                    continue
            if resp.startswith("OK") or resp.startswith("ERR"):
                return resp
        raise TimeoutError(f"radar_ctl: no reply to {line!r}")

    def az(self, deg):
        r = self.cmd(f"AZ {deg:.2f}")
        if not str(r).startswith("OK"):
            raise RuntimeError(r)


# ----------------------------------------------------------------------
# main loop
# ----------------------------------------------------------------------

def post_fix(url, payload):
    import urllib.request
    req = urllib.request.Request(url.rstrip("/") + "/api/radar",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=1.0).read()
    except Exception as e:                       # console down: keep radaring
        print(f"# server: {e}", file=sys.stderr)


def _maps(beats, sync, fs, n, timing_hint, f0, bw, thresh):
    """Cut every beat channel on the SAME sync edges and transform each one.

    Returns (cubes, timing, rds, ranges, vels, dets) where rds are COMPLEX
    range-Doppler maps -- the interferometer needs the phase, not the dB.
    Cutting both channels on one sync is what keeps their cells aligned.
    """
    cubes, timing = [], None
    for bt in beats:
        cube, tm = segment_chirps(bt, sync, fs, n)
        if cube is None:
            return None, None, None, None, None, None
        cubes.append(cube)
        timing = timing or tm
    t_up, pri = timing
    spec = fmcw_sim.RadarSpec(f0=f0, bw=bw, t_chirp=t_up, fs=fs, n_chirps=cubes[0].shape[0])
    rds, ranges, vels = [], None, None
    for cube in cubes:
        rd, ranges, vels = fmcw_sim.range_doppler(cube.astype(complex), spec,
                                                  bg_subtract=True, complex_out=True)
        rds.append(rd)
    vels = vels * (t_up / pri)                 # the Doppler axis is set by the PRI
    dets = cfar_detect(20 * np.log10(np.abs(rds[0]) + 1e-15), ranges, vels,
                       min_range=1.5, max_range=30.0, thresh_db=thresh)
    return cubes, timing, rds, ranges, vels, dets


def run(args):
    n = args.n_chirps
    ctl = Ctl(args.ctl) if args.ctl else None
    f0, bw = args.f0_mhz * 1e6, args.bw_mhz * 1e6
    if ctl:
        t_nom = ctl.status["t_chirp_ms"] / 1000.0 + ctl.status["retrace_us"] / 1e6
        f0, bw = ctl.status["f0_mhz"] * 1e6, ctl.status["bw_mhz"] * 1e6   # the truth
    else:
        t_nom = args.t_chirp_ms / 1000.0 + 1e-3
    print(f"# sweep {f0/1e6:.1f}-{(f0+bw)/1e6:.1f} MHz, range cell {3e8/(2*bw):.2f} m",
          file=sys.stderr)
    block_s = (n + 3) * t_nom               # a few spare chirps for sync slop

    # ---- azimuth mode -------------------------------------------------
    interf_mode = args.interferometer or args.switched
    I = None
    if interf_mode:
        if args.cal_file and pathlib.Path(args.cal_file).exists() and not args.calibrate:
            I = interf.Interferometer.load(args.cal_file, f0_hz=f0, bw_hz=bw,
                                           baseline_m=args.baseline)
            print(f"# calibration loaded: {math.degrees(I.cal):+.2f} deg from "
                  f"{args.cal_file}", file=sys.stderr)
        else:
            I = interf.Interferometer(baseline_m=args.baseline, f0_hz=f0, bw_hz=bw)
            if not args.calibrate:
                print("# WARNING: no calibration. Bearings carry the fixed chain "
                      "offset until you run --calibrate against a boresight "
                      "reflector.", file=sys.stderr)
        if args.switched:
            print(f"# SWITCHED: velocity folds at +/-"
                  f"{interf.switched_v_max(t_nom, I.lam):.2f} m/s (half the "
                  f"simultaneous figure, because every other chirp is thrown "
                  f"away). Past that the BEARING is wrong, not just the "
                  f"velocity, so it is reported as no_az=velocity-fold.",
                  file=sys.stderr)
        print(f"# interferometer: baseline {I.d*1000:.1f} mm, unambiguous "
              f"+/-{I.unambiguous_deg:.1f} deg, {I.bearing_error_per_mm_coax():.2f} "
              f"deg of bearing per mm of cable mismatch"
              + ("  [SWITCHED: motion-corrected]" if args.switched else ""),
              file=sys.stderr)

    n_beats = 2 if args.interferometer else 1

    if args.selftest:
        targets = [(args.st_range, args.st_az, args.st_vel, 0.01)]
        src = SynthSource(args.fs, args.t_chirp_ms / 1000.0, n, targets, f0=f0, bw=bw,
                          n_rx=n_beats, baseline_m=args.baseline,
                          cal_rad=math.radians(args.st_cal_deg), switched=args.switched)
        fs = args.fs
    elif args.replay:
        src = WavSource(args.replay, block_s)
        fs = src.fs
    else:
        src = AudioSource(args.device, args.fs, block_s, record=args.record,
                          n_beats=n_beats)
        fs = args.fs

    if ctl:
        ctl.sweep(True)                      # the ESP32 boots with RF off
    # The beam-scan centroid is legacy: it only works on a nearly stationary
    # target (docs/radar-hardware.md § 8). It is never used in azimuth mode.
    scan_mode = (not interf_mode) and (
        (bool(ctl) and not args.range_only) or (args.selftest and not args.st_range_only))
    radar = ScanningRadar(sector=args.sector) if scan_mode else None
    if radar:
        n_beams = int(round(args.sector / args.step)) + 1
        beams = list(np.linspace(-args.sector / 2, args.sector / 2, n_beams))
        print(f"# LEGACY beam scan: {len(beams)} beams, {args.step:.0f} deg step, "
              f"{n} chirps/dwell. Use --interferometer for a moving target.",
              file=sys.stderr)

    try:
        while True:
            # ---------- azimuth from two receivers ----------
            if interf_mode:
                beats, sync = src.read()
                if beats is None:
                    break
                if args.switched:
                    cube, timing, edges = segment_chirps(beats[0], sync, fs, n,
                                                         return_edges=True)
                    if cube is None:
                        print("# no sync", file=sys.stderr); time.sleep(0.2); continue
                    parity = interf.tdm_parity(edges)
                    if parity is None:
                        print("# switched mode: no frame marker in the sync. The "
                              "antennas cannot be told apart and every bearing "
                              "would be sign-flipped. Flash radar_ctl with SWMODE 1.",
                              file=sys.stderr)
                        if args.selftest and args.once:
                            return []
                        time.sleep(0.2); continue
                    ca, cb = interf.tdm_split(cube, parity)
                    t_up, pri = timing
                    spec = fmcw_sim.RadarSpec(f0=f0, bw=bw, t_chirp=t_up, fs=fs,
                                              n_chirps=ca.shape[0])
                    rds = []
                    for c in (ca, cb):
                        rd, ranges, vels = fmcw_sim.range_doppler(
                            c.astype(complex), spec, bg_subtract=True, complex_out=True)
                        rds.append(rd)
                    vels = vels * (t_up / (2 * pri))    # every other chirp -> 2x PRI
                    vmax = interf.switched_v_max(pri, I.lam)
                    dets = cfar_detect(20 * np.log10(np.abs(rds[0]) + 1e-15), ranges,
                                       vels, min_range=1.5, max_range=30.0,
                                       thresh_db=args.thresh)
                else:
                    _, timing, rds, ranges, vels, dets = _maps(
                        beats, sync, fs, n, None, f0, bw, args.thresh)
                    if rds is None:
                        print("# no sync", file=sys.stderr); time.sleep(0.2); continue
                    t_up, pri = timing

                if not dets:
                    print(json.dumps({"t": round(time.time(), 2), "fix": None}), flush=True)
                    if args.selftest and args.once:
                        return []
                    continue

                if args.calibrate:
                    best = max(dets, key=lambda d: d[3])
                    vi, ri = interf.cell_of(ranges, vels, best[0], best[1])
                    cal = I.calibrate(rds[0], rds[1], vi, ri,
                                      true_az_deg=args.cal_az,
                                      v_mps=(best[1] if args.switched else None),
                                      pri_s=(pri if args.switched else None))
                    print(f"# CALIBRATED on the target at {best[0]:.2f} m, assumed "
                          f"{args.cal_az:+.1f} deg: offset {math.degrees(cal):+.2f} deg "
                          f"({math.degrees(cal)/I.bearing_error_per_mm_coax()*I.deg_bearing_per_deg_phase:.1f}"
                          f" mm equivalent)", file=sys.stderr)
                    if args.cal_file:
                        I.save(args.cal_file)
                        print(f"# written to {args.cal_file}", file=sys.stderr)
                    args.calibrate = False
                    if args.once:
                        return [dict(range=best[0], vel=best[1], snr=best[2],
                                     az=args.cal_az, cal_deg=math.degrees(cal),
                                     x=best[0], y=0.0, beams=1)]

                recs = interf.add_bearings(dets, rds[0], rds[1], ranges, vels, I,
                                           v_mps_for_tdm=args.switched, pri_s=pri)
                # The fix is the STRONGEST return, full stop. If that one has
                # no trustworthy bearing then there is no fix: promoting a
                # weaker sidelobe that happens to have a bearing would be
                # inventing an answer.
                best = max(recs, key=lambda r: r["level"]) if recs else None
                refused = best["az_reason"] if (best and best["az"] is None) else None
                if refused:
                    best = None
                out = {"t": round(time.time(), 2),
                       "t_chirp_ms": round(t_up * 1e3, 3), "pri_ms": round(pri * 1e3, 3),
                       "mode": "switched" if args.switched else "interferometer",
                       **({"v_unambiguous": round(vmax, 2)} if args.switched else {}),
                       "dets": [{"range": round(r["range"], 2), "vel": round(r["vel"], 2),
                                 "az": (None if r["az"] is None else round(r["az"], 2)),
                                 "snr": round(r["snr"], 1), "q": round(r["quality"], 2),
                                 **({"no_az": r["az_reason"]} if r["az"] is None else {})}
                                for r in recs[:5]],
                       **({"no_fix": refused} if refused else {}),
                       "fix": (None if best is None else
                               {"range": round(best["range"], 2), "az": round(best["az"], 2),
                                "vel": round(best["vel"], 2), "snr": round(best["snr"], 1),
                                "x": round(best["x"], 2), "y": round(best["y"], 2),
                                "beams": 1})}
                print(json.dumps(out), flush=True)
                if best and args.server:
                    post_fix(args.server, {"x": best["x"], "y": best["y"],
                                           "range": best["range"], "az": best["az"],
                                           "vel": best["vel"], "snr": best["snr"],
                                           "beams": 1, "t": time.time()})
                if args.selftest and args.once:
                    if out["fix"]:
                        return [out["fix"]]
                    return [{"refused": refused}] if refused else []
                continue

            # ---------- stage 1: range and velocity ----------
            if not scan_mode:
                beats, sync = src.read()
                if beats is None:
                    break
                cube, timing = segment_chirps(beats[0], sync, fs, n)
                if cube is None:
                    print("# no sync: check the R channel / SWEEP 1", file=sys.stderr)
                    time.sleep(0.2); continue
                dets, spec = process(cube, fs, timing, n, thresh_db=args.thresh, f0=f0, bw=bw)
                out = {"t": round(time.time(), 2), "t_chirp_ms": round(timing[0] * 1e3, 3),
                       "pri_ms": round(timing[1] * 1e3, 3),
                       "dets": [{"range": round(r, 2), "vel": round(v, 2),
                                 "snr": round(s, 1)} for (r, v, s, _) in dets[:5]]}
                print(json.dumps(out), flush=True)
                if args.selftest:
                    return [dict(range=d[0], az=0.0, vel=d[1], snr=d[2], beams=1,
                                 x=d[0], y=0.0) for d in dets[:1]]
                continue

            # ---------- legacy beam scan ----------
            per_beam = []
            for b in beams:
                if ctl:
                    ctl.az(b)
                else:
                    src.beam_az = b
                beats, sync = src.read()
                if beats is None:
                    return
                cube, timing = segment_chirps(beats[0], sync, fs, n)
                if cube is None:
                    print(f"# beam {b:+.0f}: no sync", file=sys.stderr)
                    continue
                dets, spec = process(cube, fs, timing, n, thresh_db=args.thresh, f0=f0, bw=bw)
                radar.spec = spec
                per_beam.append((b, dets))
            fixes = radar.centroid(per_beam)
            out = {"t": round(time.time(), 2), "beams": len(per_beam), "mode": "legacy-scan",
                   "fix": ({k: round(v, 2) if isinstance(v, float) else v
                            for k, v in fixes[0].items()} if fixes else None)}
            print(json.dumps(out), flush=True)
            if fixes and args.server:
                f = fixes[0]
                post_fix(args.server, {"x": f["x"], "y": f["y"], "range": f["range"],
                                       "az": f["az"], "vel": f["vel"], "snr": f["snr"],
                                       "beams": f["beams"], "t": time.time()})
            if args.selftest and args.once:
                return fixes
    finally:
        src.close()
        if ctl:
            try:
                ctl.sweep(False)             # leave the radar silent
            except Exception:
                pass


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--device", help="sound device index or name (see python -m sounddevice)")
    ap.add_argument("--fs", type=float, default=44100.0)
    ap.add_argument("--n-chirps", type=int, default=64)
    ap.add_argument("--t-chirp-ms", type=float, default=6.4,
                    help="nominal up-chirp (only for block sizing; measured live from sync)")
    ap.add_argument("--thresh", type=float, default=15.0, help="CFAR threshold dB")
    ap.add_argument("--f0-mhz", type=float, default=F0_HZ / 1e6,
                    help="sweep start; overridden by radar_ctl status when --ctl is given")
    ap.add_argument("--bw-mhz", type=float, default=BW_HZ / 1e6,
                    help="sweep width; 40 with --f0-mhz 2440 for WiFi-channel-1 coexistence")
    ap.add_argument("--ctl", help="radar_ctl serial port (sweep on/off; also the optional turntable)")
    # ---- azimuth ----
    g = ap.add_argument_group("azimuth (stage 2)")
    g.add_argument("--interferometer", action="store_true",
                   help="AZIMUTH from two receivers. Needs 3 audio channels: "
                        "beat A, beat B, sync, on ONE sample clock")
    g.add_argument("--switched", action="store_true",
                   help="azimuth on one chain with an RF switch alternating "
                        "antennas chirp by chirp; motion-corrected")
    g.add_argument("--baseline", type=float, default=interf.DEFAULT_BASELINE_M,
                   help="receive antenna spacing in metres (default 0.1931, "
                        "two rotated horns touching)")
    g.add_argument("--calibrate", action="store_true",
                   help="measure the fixed chain phase offset from the strongest "
                        "target, assumed to be at --cal-az, then continue")
    g.add_argument("--cal-az", type=float, default=0.0,
                   help="true bearing of the calibration reflector (default boresight)")
    g.add_argument("--cal-file", default="interferometer_cal.json",
                   help="where the calibration constant is stored and reloaded")
    g.add_argument("--st-cal-deg", type=float, default=0.0,
                   help="selftest only: inject this much chain phase offset, to "
                        "prove --calibrate removes it")
    # These defaults (9 beams over 90 deg) are the LEGACY scan geometry. The
    # geometry docs/radar-hardware.md § 8 recommends is --sector 48 --step 24,
    # and docs/radar-software.md § 7 passes it explicitly. The defaults are left
    # as they are deliberately: the scan is deprecated in favour of
    # --interferometer, and its published accuracy figures (0.74 deg rms at
    # rest, the 42.5 deg collapse at 83.5 MHz) are prose in radar-hardware.md
    # § 8 with no test pinning them -- they do not reproduce from the parameters
    # given there. Re-tune these only together with a regression test.
    ap.add_argument("--sector", type=float, default=90.0)
    ap.add_argument("--step", type=float, default=12.0,
                    help="beam step deg (legacy scan; § 8 recommends --sector 48 --step 24)")
    ap.add_argument("--server", help="console URL, e.g. http://localhost:8080")
    ap.add_argument("--record", metavar="WAV", help="save raw stereo audio")
    ap.add_argument("--replay", metavar="WAV")
    ap.add_argument("--range-only", action="store_true",
                    help="stage 1: no azimuth scan even with --ctl (which is still used for SWEEP)")
    ap.add_argument("--selftest", action="store_true", help="synthetic target, no hardware")
    ap.add_argument("--st-range", type=float, default=8.0)
    ap.add_argument("--st-az", type=float, default=15.0)
    ap.add_argument("--st-vel", type=float, default=1.0)
    ap.add_argument("--st-range-only", action="store_true",
                    help="selftest the stage-1 (no azimuth) path instead")
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        args.once = True
        if args.st_vel == 0.0:
            print("# note: a target with exactly zero Doppler is removed with the "
                  "clutter (bg_subtract) -- a real hover still shows rotor "
                  "micro-Doppler and body jitter; use --st-vel != 0", file=sys.stderr)
        fixes = run(args)
        if fixes and "refused" in fixes[0]:
            why = fixes[0]["refused"]
            vmax = interf.switched_v_max(args.t_chirp_ms / 1000.0 + 1e-3,
                                         interf.wavelength(args.f0_mhz * 1e6,
                                                           args.bw_mhz * 1e6))
            expected = args.switched and why == "velocity-fold" and abs(args.st_vel) > 0.8 * vmax
            print(f"SELFTEST {'PASS (correct refusal: ' + why + ')' if expected else 'FAIL (refused: ' + why + ')'}"
                  f": switched mode folds above +/-{vmax:.2f} m/s and the target "
                  f"is at {args.st_vel:+.2f}")
            sys.exit(0 if expected else 1)
        if not fixes:
            print("SELFTEST FAIL: no fix"); sys.exit(1)
        f = fixes[0]
        # the dwell is n_chirps x PRI long and the target keeps moving through
        # it, so the honest truth is the MID-DWELL range, not the t=0 range
        t_dwell = args.n_chirps * (args.t_chirp_ms / 1000.0 + 1e-3)
        r_true = args.st_range + args.st_vel * t_dwell / 2
        er = abs(f["range"] - r_true); ea = abs(f["az"] - args.st_az)
        edge = abs(args.st_az) > args.sector / 2 - args.step
        if args.st_range_only:
            ea, edge = 0.0, False          # stage 1 has no azimuth to check
        if args.interferometer or args.switched:
            # a phase interferometer is held to the real budget, not the
            # 4 deg the beam-scan centroid needed
            ok = er < 0.5 and ea < 2.5
            tag = "PASS" if ok else "FAIL"
            print(f"SELFTEST {tag} [{'switched' if args.switched else 'interferometer'}]: "
                  f"range {f['range']:.2f} m (mid-dwell truth {r_true:.2f}), "
                  f"az {f['az']:.2f} deg (true {args.st_az}, error {ea:.2f}), "
                  f"vel {f['vel']:.2f} m/s (true {args.st_vel})")
            sys.exit(0 if ok else 1)
        ok = er < 0.5 and (ea < 4.0 or (edge and ea < 8.0))
        tag = "PASS" if ok else "FAIL"
        if ok and edge and ea >= 4.0:
            tag = "PASS (sector edge: centroid biased inward, widen --sector)"
        print(f"SELFTEST {tag}: range {f['range']:.2f} m (mid-dwell truth "
              f"{r_true:.2f}), az {f['az']:.1f} deg (true {args.st_az}), "
              f"vel {f['vel']:.2f} m/s (true {args.st_vel}), {f['beams']} beams")
        sys.exit(0 if ok else 1)
    run(args)


if __name__ == "__main__":
    main()
