#!/usr/bin/env python3
"""
radar_acquire.py — live FMCW radar processing for the horn-fed can radar.

STAGE 1: one TX horn, one RX horn, RANGE and RADIAL VELOCITY. There is no
azimuth here and nothing in this file measures a bearing. The second receiver,
the phase interferometer and the beam scan are stage 2 and live in stage2/,
which is written and passing but not built.

Same DSP as the simulator (range_doppler from fmcw_sim, cfar_detect from dsp),
but the beat signal comes from the sound card instead of fmcw_sim.simulate:

    sound card L = beat signal (video amp out)
    sound card R = chirp SYNC from radar_ctl (HIGH during the up-chirp)

    --ctl /dev/ttyUSB0      drive radar_ctl: turn the sweep on, and read the
                            sweep it is ACTUALLY transmitting back out of it
    --server http://...     push blocks into the console (server.py /api/radar)
    --map                   include the range-Doppler map in that POST

Test it with no hardware at all:
    python radar_acquire.py --selftest            # synthetic target at 8 m
    python radar_acquire.py --replay capture.wav  # a recorded session

Record raw audio for later replay with --record capture.wav.
"""

import argparse
import base64
import json
import sys
import time
import wave

import numpy as np

import fmcw_sim
from dsp import cfar_detect
from synth import BW_HZ, F0_HZ, SynthSource, segment_chirps


# ----------------------------------------------------------------------
# beat cube -> detections
# ----------------------------------------------------------------------

def process(cube, fs, timing, n_chirps, min_range=1.5, max_range=30.0,
            thresh_db=15.0, f0=None, bw=None):
    """Beat cube -> range-Doppler -> CFAR detections.

    Returns (dets, spec, rd_db, ranges, vels): the detections, the spec the
    transform used, and the map itself, which --map ships to the console.

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
    return dets, spec, rd, ranges, vels


# ----------------------------------------------------------------------
# sources
# ----------------------------------------------------------------------

class AudioSource:
    """Blocks from a live sound card: two channels, beat and sync.

    read() returns (beats, sync), where beats is a LIST of channels with one
    entry in it. The list survives from the two-receiver code in stage2/, which
    reads beat A, beat B and sync off one interface so that all of them ride
    the same sample clock; stage 1 only ever has the one beat channel.
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
    """Replay a recording. 2 channels = beat + sync, 3 = beat A + beat B + sync
    (a stage-2 capture; stage 1 processes its first beat channel)."""

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


def _det_json(d):
    r, v, s, _lvl = d
    return {"range": round(float(r), 2), "vel": round(float(v), 2),
            "snr": round(float(s), 1)}


def gui_payload(t, timing, dets, rd, ranges, vels, with_map=False):
    """The console payload: detections, the axes they sit on, and optionally
    the range-Doppler map itself as 8-bit greyscale.

    The map is the dB magnitude scaled linearly between rd_range.min and
    rd_range.max onto 0..255, row-major, rows = velocity (low to high),
    columns = range (near to far) -- the same orientation as the array, so the
    console can draw it without transposing anything."""
    t_up, pri = timing
    five = [_det_json(d) for d in dets[:5]]
    lo, hi = float(np.min(rd)), float(np.max(rd))
    out = {"t": round(t, 2),
           "t_chirp_ms": round(t_up * 1e3, 3), "pri_ms": round(pri * 1e3, 3),
           "dets": five,
           "best": (five[0] if five else None),
           "axes": {"r0": round(float(ranges[0]), 4),
                    "dr": round(float(ranges[1] - ranges[0]), 4),
                    "v0": round(float(vels[0]), 4),
                    "dv": round(float(vels[1] - vels[0]), 4)},
           "rd_shape": [int(rd.shape[0]), int(rd.shape[1])],
           "rd_range": {"min": round(lo, 1), "max": round(hi, 1)}}
    if with_map:
        span = hi - lo
        u8 = np.zeros(rd.shape, dtype=np.uint8) if span <= 0 else \
            np.clip(np.rint((rd - lo) * (255.0 / span)), 0, 255).astype(np.uint8)
        out["rd"] = base64.b64encode(u8.tobytes(order="C")).decode("ascii")
    return out


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

    if args.selftest:
        targets = [(args.st_range, 0.0, args.st_vel, 0.01)]
        src = SynthSource(args.fs, args.t_chirp_ms / 1000.0, n, targets,
                          f0=f0, bw=bw, n_rx=1)
        fs = args.fs
    elif args.replay:
        src = WavSource(args.replay, block_s)
        fs = src.fs
    else:
        src = AudioSource(args.device, args.fs, block_s, record=args.record)
        fs = args.fs

    if ctl:
        ctl.sweep(True)                      # the ESP32 boots with RF off

    try:
        while True:
            beats, sync = src.read()
            if beats is None:
                break
            cube, timing = segment_chirps(beats[0], sync, fs, n)
            if cube is None:
                print("# no sync: check the R channel / SWEEP 1", file=sys.stderr)
                time.sleep(0.2); continue
            dets, spec, rd, ranges, vels = process(cube, fs, timing, n,
                                                   thresh_db=args.thresh,
                                                   f0=f0, bw=bw)
            t = time.time()
            out = {"t": round(t, 2), "t_chirp_ms": round(timing[0] * 1e3, 3),
                   "pri_ms": round(timing[1] * 1e3, 3),
                   "dets": [_det_json(d) for d in dets[:5]]}
            print(json.dumps(out), flush=True)
            if args.server:
                post_fix(args.server, gui_payload(t, timing, dets, rd, ranges,
                                                  vels, with_map=args.map))
            if args.selftest:
                return [dict(range=d[0], vel=d[1], snr=d[2]) for d in dets[:1]]
            if args.once:
                return []
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
    ap.add_argument("--ctl", help="radar_ctl serial port (sweep on/off)")
    ap.add_argument("--server", help="console URL, e.g. http://localhost:8080")
    ap.add_argument("--map", action="store_true",
                    help="include the range-Doppler map (base64 uint8) in the POST")
    ap.add_argument("--record", metavar="WAV", help="save raw stereo audio")
    ap.add_argument("--replay", metavar="WAV")
    ap.add_argument("--selftest", action="store_true", help="synthetic target, no hardware")
    ap.add_argument("--st-range", type=float, default=8.0)
    ap.add_argument("--st-vel", type=float, default=1.0)
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
            print("SELFTEST FAIL: no detection"); sys.exit(1)
        f = fixes[0]
        # the dwell is n_chirps x PRI long and the target keeps moving through
        # it, so the honest truth is the MID-DWELL range, not the t=0 range
        t_dwell = args.n_chirps * (args.t_chirp_ms / 1000.0 + 1e-3)
        r_true = args.st_range + args.st_vel * t_dwell / 2
        er = abs(f["range"] - r_true)
        ok = er < 0.5
        print(f"SELFTEST {'PASS' if ok else 'FAIL'}: range {f['range']:.2f} m "
              f"(mid-dwell truth {r_true:.2f}), vel {f['vel']:.2f} m/s "
              f"(true {args.st_vel}), SNR {f['snr']:.1f} dB")
        sys.exit(0 if ok else 1)
    run(args)


if __name__ == "__main__":
    main()
