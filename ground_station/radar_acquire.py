#!/usr/bin/env python3
"""
radar_acquire.py — live FMCW radar processing for the horn-fed can radar.

The real-hardware twin of radar_twin.py. Same DSP (range_doppler from
fmcw_sim, cfar_detect + centroid from radar_twin), but the beat signal comes
from the sound card instead of the simulator:

    sound card L = beat signal (video amp out)
    sound card R = chirp SYNC from radar_ctl (HIGH during the up-chirp)

Stages:
    --range-only            stage 1: no azimuth drive, print range/velocity
    --ctl /dev/ttyUSB0      stage 2/3: step the horns with radar_ctl, centroid
    --server http://...     push fixes into the console (server.py /api/radar)

Test it with no hardware at all:
    python radar_acquire.py --selftest            # synthetic target at 8 m
    python radar_acquire.py --replay capture.wav  # a recorded session

Record raw audio for later replay with --record capture.wav.
"""

import argparse
import json
import math
import sys
import time
import wave

import numpy as np

import fmcw_sim
from radar_twin import ScanningRadar, cfar_detect

F0_HZ = 2.400e9
BW_HZ = 83.5e6
SYNC_FRAC = 0.5          # sync threshold as a fraction of the sync channel's peak
SETTLE_FRAC = 0.05       # drop the first 5 % of each chirp (PLL settle)


# ----------------------------------------------------------------------
# sync + segmentation
# ----------------------------------------------------------------------

def segment_chirps(beat, sync, fs, n_chirps):
    """Cut the beat channel into an (n_chirps, n_samples) cube using the sync
    square wave. Returns (cube, t_chirp_s). t_chirp is MEASURED from the sync,
    never assumed — the stepped PLL sweep's real period is set by the ESP32's
    step_us and any drift shows up here first."""
    s = sync.astype(float)
    thr = SYNC_FRAC * max(float(np.max(np.abs(s))), 1e-6)
    high = s > thr
    edges = np.flatnonzero(np.diff(high.astype(np.int8)) == 1) + 1
    falls = np.flatnonzero(np.diff(high.astype(np.int8)) == -1) + 1
    if len(edges) < n_chirps + 1:
        return None, None
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
        return None, None
    cube = np.array(rows, dtype=float)
    cube -= cube.mean(axis=1, keepdims=True)         # kill DC per chirp
    pri = float(np.median(np.diff(edges[:n_chirps + 1]))) / fs
    return cube, (n_up / fs, pri)


def process(cube, fs, timing, n_chirps, min_range=1.5, max_range=30.0,
            thresh_db=15.0):
    """Beat cube -> range-Doppler -> CFAR detections.

    timing = (t_up, pri): the up-chirp sets the beat->range scale, the pulse
    repetition interval (up-chirp + retrace) sets the Doppler axis. They are
    NOT the same number on this hardware, and both are measured from sync."""
    t_chirp, pri = timing
    spec = fmcw_sim.RadarSpec(f0=F0_HZ, bw=BW_HZ, t_chirp=t_chirp, fs=fs,
                              n_chirps=n_chirps)
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
    """Blocks of (beat, sync) from a live sound card."""

    def __init__(self, device, fs, block_s, record=None):
        import sounddevice as sd          # lazy: PortAudio only needed live
        self.sd = sd
        self.device = device
        self.fs = fs
        self.frames = int(block_s * fs)
        self.wav = None
        if record:
            self.wav = wave.open(record, "wb")
            self.wav.setnchannels(2)
            self.wav.setsampwidth(2)
            self.wav.setframerate(int(fs))

    def read(self):
        x = self.sd.rec(self.frames, samplerate=self.fs, channels=2,
                        dtype="int16", device=self.device, blocking=True)
        if self.wav:
            self.wav.writeframes(x.tobytes())
        return x[:, 0].astype(float), x[:, 1].astype(float)

    def close(self):
        if self.wav:
            self.wav.close()


class WavSource:
    def __init__(self, path, block_s):
        w = wave.open(path, "rb")
        assert w.getnchannels() == 2 and w.getsampwidth() == 2, "need 16-bit stereo"
        self.fs = w.getframerate()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        self.x = data.reshape(-1, 2).astype(float)
        self.frames = int(block_s * self.fs)
        self.pos = 0

    def read(self):
        if self.pos + self.frames > len(self.x):
            return None, None
        blk = self.x[self.pos:self.pos + self.frames]
        self.pos += self.frames
        return blk[:, 0], blk[:, 1]

    def close(self):
        pass


class SynthSource:
    """What the sound card WOULD see for a given target: a single-ended
    (real) beat signal per up-chirp, a retrace gap, and the sync square wave,
    at fixed 16-bit levels. Same physics as fmcw_sim.simulate, but the range
    walk between chirps uses the PRI (up-chirp + retrace) like the hardware,
    and the level is absolute so beam-to-beam amplitude comparison works."""

    ADC_SCALE = 3.0e5          # sqrt(mW) -> counts; leakage ~ -22 dBm fits int16

    def __init__(self, fs, t_chirp, n_chirps, targets, retrace_s=1e-3,
                 beam_az=0.0, bw_az=36.0, seed=0, isolation_db=35.0):
        self.fs, self.t_chirp, self.n_chirps = fs, t_chirp, n_chirps
        self.targets, self.retrace_s = targets, retrace_s
        self.beam_az, self.bw_az = beam_az, bw_az
        self.rng = np.random.default_rng(seed)
        self.spec = fmcw_sim.RadarSpec(f0=F0_HZ, bw=BW_HZ, t_chirp=t_chirp, fs=fs,
                                       n_chirps=n_chirps, gt_dbi=13.4, gr_dbi=13.4,
                                       isolation_db=isolation_db)
        self.frames = None

    def read(self):
        from radar_twin import beam_gain
        s = self.spec
        n_up = int(round(self.fs * self.t_chirp))
        n_gap = int(round(self.retrace_s * self.fs))
        pri = (n_up + n_gap) / self.fs
        t = np.arange(n_up) / self.fs
        noise_w = fmcw_sim.K_BOLTZ * fmcw_sim.T0 * (self.fs / 2) * 10 ** (s.nf_db / 10)
        noise_amp = math.sqrt(noise_w * 1e3)
        lk = math.sqrt(10 ** ((s.pt_dbm - s.isolation_db) / 10))
        beat, sync = [], []
        for k in range(self.n_chirps + 2):
            tk = k * pri
            sig = np.zeros(n_up)
            for (r, az, v, rcs) in self.targets:
                g = beam_gain(az - self.beam_az, self.bw_az)
                if g <= 1e-3:
                    continue
                rt = r + v * tk
                amp = math.sqrt(10 ** (s.rx_dbm(rt, rcs * g * g) / 10))
                sig += amp * np.cos(2 * math.pi * s.beat_hz(rt) * t + 4 * math.pi * rt / s.lam)
            sig += lk * np.cos(2 * math.pi * s.beat_hz(0.3) * t)
            sig += noise_amp * self.rng.normal(size=n_up)
            beat.append(sig); sync.append(np.ones(n_up))
            beat.append(np.zeros(n_gap)); sync.append(np.zeros(n_gap))
        beat = np.clip(np.concatenate(beat) * self.ADC_SCALE, -32767, 32767)
        return beat, np.concatenate(sync) * 20000.0

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


def run(args):
    n = args.n_chirps
    ctl = Ctl(args.ctl) if args.ctl else None
    if ctl:
        t_nom = ctl.status["t_chirp_ms"] / 1000.0 + ctl.status["retrace_us"] / 1e6
    else:
        t_nom = args.t_chirp_ms / 1000.0 + 1e-3
    block_s = (n + 3) * t_nom               # a few spare chirps for sync slop

    if args.selftest:
        targets = [(args.st_range, args.st_az, args.st_vel, 0.01)]
        src = SynthSource(args.fs, args.t_chirp_ms / 1000.0, n, targets)
        fs = args.fs
    elif args.replay:
        src = WavSource(args.replay, block_s)
        fs = src.fs
    else:
        src = AudioSource(args.device, args.fs, block_s, record=args.record)
        fs = args.fs

    scan_mode = bool(ctl) or (args.selftest and not args.st_range_only)
    radar = ScanningRadar(sector=args.sector) if scan_mode else None
    if radar:
        n_beams = int(round(args.sector / args.step)) + 1
        beams = list(np.linspace(-args.sector / 2, args.sector / 2, n_beams))
        print(f"# scanning {len(beams)} beams, {args.step:.0f} deg step, "
              f"{n} chirps/dwell", file=sys.stderr)

    try:
        while True:
            if not scan_mode:
                beat, sync = src.read()
                if beat is None:
                    break
                cube, t_chirp = segment_chirps(beat, sync, fs, n)
                if cube is None:
                    print("# no sync: check the R channel / SWEEP 1", file=sys.stderr)
                    time.sleep(0.2); continue
                dets, spec = process(cube, fs, t_chirp, n, thresh_db=args.thresh)
                out = {"t": round(time.time(), 2), "t_chirp_ms": round(t_chirp * 1e3, 3),
                       "dets": [{"range": round(r, 2), "vel": round(v, 2),
                                 "snr": round(s, 1)} for (r, v, s, _) in dets[:5]]}
                print(json.dumps(out), flush=True)
                if args.selftest:
                    return [dict(range=d[0], az=0.0, vel=d[1], snr=d[2], beams=1,
                                 x=d[0], y=0.0) for d in dets[:1]]
                continue

            per_beam = []
            for b in beams:
                if ctl:
                    ctl.az(b)
                else:
                    src.beam_az = b
                beat, sync = src.read()
                if beat is None:
                    return
                cube, t_chirp = segment_chirps(beat, sync, fs, n)
                if cube is None:
                    print(f"# beam {b:+.0f}: no sync", file=sys.stderr)
                    continue
                dets, spec = process(cube, fs, t_chirp, n, thresh_db=args.thresh)
                radar.spec = spec
                per_beam.append((b, dets))
            fixes = radar.centroid(per_beam)
            out = {"t": round(time.time(), 2), "beams": len(per_beam),
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


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--device", help="sound device index or name (see python -m sounddevice)")
    ap.add_argument("--fs", type=float, default=44100.0)
    ap.add_argument("--n-chirps", type=int, default=64)
    ap.add_argument("--t-chirp-ms", type=float, default=6.4,
                    help="nominal up-chirp (only for block sizing; measured live from sync)")
    ap.add_argument("--thresh", type=float, default=15.0, help="CFAR threshold dB")
    ap.add_argument("--ctl", help="radar_ctl serial port -> scanning mode")
    ap.add_argument("--sector", type=float, default=90.0)
    ap.add_argument("--step", type=float, default=12.0, help="beam step deg (3x oversample)")
    ap.add_argument("--server", help="console URL, e.g. http://localhost:8080")
    ap.add_argument("--record", metavar="WAV", help="save raw stereo audio")
    ap.add_argument("--replay", metavar="WAV")
    ap.add_argument("--range-only", action="store_true", help="(default without --ctl)")
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
        if not fixes:
            print("SELFTEST FAIL: no fix"); sys.exit(1)
        f = fixes[0]
        # the dwell is n_chirps x PRI long and the target keeps moving through
        # it, so the honest truth is the MID-DWELL range, not the t=0 range
        t_dwell = args.n_chirps * (args.t_chirp_ms / 1000.0 + 1e-3)
        r_true = args.st_range + args.st_vel * t_dwell / 2
        er = abs(f["range"] - r_true); ea = abs(f["az"] - args.st_az)
        edge = abs(args.st_az) > args.sector / 2 - args.step
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
