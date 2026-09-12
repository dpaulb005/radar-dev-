#!/usr/bin/env python3
"""
server.py — STAGE 1 FMCW radar console (backend).

Stage 1 is one TX horn and one RX horn at 2.4 GHz. That geometry measures
RANGE and RADIAL VELOCITY and nothing else: there is no bearing, no azimuth,
no plan view. This console therefore shows the four things stage 1 actually
produces:

  1. the range-Doppler map (the real 2-D DSP output) with CFAR detections,
  2. range vs time (a scrolling waterfall, a few minutes deep),
  3. the detection list, strongest first,
  4. the range/velocity Kalman track plus the hardware timing — the
     SYNC-measured chirp time and PRI, the block rate, and a NO SYNC flag.

It eats the wire contract that radar_acquire.py emits:

  POST /api/radar
    {"t":1789.4,"t_chirp_ms":6.395,"pri_ms":7.392,
     "dets":[{"range":4.62,"vel":-1.31,"snr":38.4}],   # strongest first, <=5
     "best":{"range":4.62,"vel":-1.31,"snr":38.4}|null,
     "axes":{"r0":0.0,"dr":0.4104,"v0":-4.15,"dv":0.1297},
     "rd_shape":[n_v,n_r],                             # rows=velocity
     "rd_range":{"min":-128.0,"max":-41.2},            # dB mapped to 0..255
     "rd":"<base64 n_v*n_r uint8, row-major>"}         # only with --map

  GET  /            the GUI
  GET  /api/state   {"radar":...,"track":...,"waterfall":...,"stats":...}
  GET  /api/stream  Server-Sent Events, one event per ingested block

Usage:
    python3 server.py                 # wait for radar_acquire.py --server
    python3 server.py --demo          # synthetic blocks, no hardware needed
    python3 server.py --port 9000
"""

import argparse
import asyncio
import base64
import json
import math
import pathlib
import time
from collections import deque

import numpy as np
from aiohttp import web

from tracker import RangeVelocityKF, prediction_is_justified, range_sigma_from_snr

BASE = pathlib.Path(__file__).resolve().parent
WEB_DIR = BASE / "web"
CONFIG_PATH = BASE / "config.json"

MAX_DETS = 5                 # the contract caps the list at 5
WF_MAX_BINS = 256            # range bins kept per waterfall row
WF_MAX_ROWS = 2400           # hard cap on the rolling buffer
STATE_WF_ROWS = 420          # rows returned by /api/state (decimated)
TRACK_MAX = 4000
STATE_TRACK_POINTS = 700
TIMING_WINDOW = 64           # blocks used for the timing/jitter statistics
RD_MAX_CELLS = 512 * 512     # refuse absurd maps instead of eating the RAM


# ======================================================================
# payload parsing — be strict about shape, forgiving about missing keys
# ======================================================================

def _f(v, default=None):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    return x if math.isfinite(x) else default


class BadBlock(ValueError):
    pass


def parse_block(raw):
    """Validate one /api/radar payload.

    Returns (block, rd) where `block` is the payload without the map (exactly
    what /api/state reports as "radar") and `rd` is an (n_v, n_r) uint8 array
    or None when the sender did not pass --map.
    """
    if not isinstance(raw, dict):
        raise BadBlock("payload must be a JSON object")

    dets = []
    for d in (raw.get("dets") or []):
        if not isinstance(d, dict):
            continue
        r, v, s = _f(d.get("range")), _f(d.get("vel"), 0.0), _f(d.get("snr"), 0.0)
        if r is None:
            continue
        dets.append({"range": round(r, 3), "vel": round(v, 3), "snr": round(s, 2)})
    dets.sort(key=lambda d: d["snr"], reverse=True)      # strongest first
    dets = dets[:MAX_DETS]

    best = raw.get("best")
    if isinstance(best, dict) and _f(best.get("range")) is not None:
        best = {"range": round(_f(best["range"]), 3),
                "vel": round(_f(best.get("vel"), 0.0), 3),
                "snr": round(_f(best.get("snr"), 0.0), 2)}
    else:
        best = dict(dets[0]) if dets else None

    axes = None
    a = raw.get("axes")
    if isinstance(a, dict):
        r0, dr = _f(a.get("r0"), 0.0), _f(a.get("dr"))
        v0, dv = _f(a.get("v0")), _f(a.get("dv"))
        if dr is not None and dr > 0:
            axes = {"r0": r0, "dr": dr,
                    "v0": v0 if v0 is not None else 0.0,
                    "dv": dv if dv is not None and dv > 0 else 0.0}

    block = {
        "t": _f(raw.get("t"), 0.0),
        "t_chirp_ms": _f(raw.get("t_chirp_ms")),
        "pri_ms": _f(raw.get("pri_ms")),
        "dets": dets,
        "best": best,
        "axes": axes,
        "rd_shape": None,
        "rd_range": None,
    }

    rd = None
    shape = raw.get("rd_shape")
    rng = raw.get("rd_range")
    b64 = raw.get("rd")
    if shape is not None:
        try:
            n_v, n_r = int(shape[0]), int(shape[1])
        except (TypeError, ValueError, IndexError):
            raise BadBlock("rd_shape must be [n_v, n_r]")
        if n_v < 1 or n_r < 1 or n_v * n_r > RD_MAX_CELLS:
            raise BadBlock(f"rd_shape {n_v}x{n_r} out of range")
        block["rd_shape"] = [n_v, n_r]
        if isinstance(rng, dict):
            lo, hi = _f(rng.get("min")), _f(rng.get("max"))
            if lo is not None and hi is not None:
                if hi <= lo:
                    hi = lo + 1.0
                block["rd_range"] = {"min": lo, "max": hi}
        if isinstance(b64, str) and b64:
            try:
                buf = base64.b64decode(b64, validate=True)
            except Exception as e:
                raise BadBlock(f"rd is not valid base64: {e}")
            if len(buf) != n_v * n_r:
                raise BadBlock(f"rd is {len(buf)} bytes, rd_shape needs {n_v * n_r}")
            if block["rd_range"] is None:
                raise BadBlock("rd given without rd_range")
            rd = np.frombuffer(buf, dtype=np.uint8).reshape(n_v, n_r)
    return block, rd


def _b64(arr):
    return base64.b64encode(np.ascontiguousarray(arr, dtype=np.uint8).tobytes()).decode()


# ======================================================================
# station state
# ======================================================================

class Station:
    def __init__(self, cfg, demo=False):
        self.cfg = cfg
        self.demo = bool(demo)
        self.t_start = time.time()
        self.mono0 = time.monotonic()

        self.seq = 0
        self.blocks = 0
        self.bad_blocks = 0
        self.last_error = None

        self.block = None            # latest payload, map stripped
        self.map = None              # {"rd": b64, "shape": [n_v,n_r], "rd_range": {...}, "axes": {...}}
        self.last_mono = None

        self.arrivals = deque(maxlen=TIMING_WINDOW)
        self.t_chirp = deque(maxlen=TIMING_WINDOW)
        self.pri = deque(maxlen=TIMING_WINDOW)

        # waterfall: (t_rel, float32 row of dB) — bounded by time AND count
        self.wf = deque(maxlen=WF_MAX_ROWS)
        self.wf_r0 = 0.0
        self.wf_dr = 1.0
        self.wf_bins = 0
        self.wf_kind = "none"        # "map" (collapsed RD) or "dets"

        self.track_hist = deque(maxlen=TRACK_MAX)
        self.kf = RangeVelocityKF(
            sigma_a=_f(cfg.get("sigma_a"), 2.0),
            model=str(cfg.get("track_model", "cv")),
            gate_sigma=_f(cfg.get("track_gate_sigma"), 5.0),
            coast_s=_f(cfg.get("track_coast_s"), 2.0))

        self.log_lines = deque(maxlen=60)
        self.subs = set()

    # ------------------------------------------------------------------
    def log(self, msg):
        line = {"t": round(time.time() - self.t_start, 2), "msg": str(msg)}
        self.log_lines.append(line)
        print(f"[{line['t']:8.2f}] {msg}", flush=True)

    @property
    def now_rel(self):
        return time.monotonic() - self.mono0

    # ------------------------------------------------------------------
    # ingest — the ONE path into the state, used by POST and by --demo
    # ------------------------------------------------------------------
    def ingest(self, raw):
        block, rd = parse_block(raw)
        now = self.now_rel
        self.seq += 1
        self.blocks += 1
        self.block = block
        self.last_mono = now
        self.arrivals.append(now)
        if block["t_chirp_ms"] is not None:
            self.t_chirp.append(block["t_chirp_ms"])
        if block["pri_ms"] is not None:
            self.pri.append(block["pri_ms"])

        # the map belongs to THIS block only: a later block sent without --map
        # must not be shown against a stale heatmap.
        self.map = ({"shape": block["rd_shape"], "rd_range": block["rd_range"],
                     "axes": block["axes"], "rd": _b64(rd)}
                    if rd is not None else None)
        wf_row = self._push_waterfall(now, block, rd)
        point = self._update_track(now, block)

        event = {"seq": self.seq, "t_rel": round(now, 3),
                 "radar": self._radar_out(include_map=True),
                 "track": self.track_out(history=False),
                 "stats": self.stats_out(),
                 "point": point, "wf": wf_row}
        self._publish(event)
        return event

    # ------------------------------------------------------------------
    def _push_waterfall(self, t, block, rd):
        """One range profile per block, for the range-vs-time waterfall.

        With a map: collapse the range-Doppler map over velocity (peak hold),
        which is exactly "the strongest thing at this range, whatever its
        Doppler". Without a map (--map not given): a sparse profile built from
        the detection list, so the panel still shows something honest.
        """
        axes = block["axes"]
        if rd is not None and block["rd_range"] is not None:
            lo, hi = block["rd_range"]["min"], block["rd_range"]["max"]
            prof_u8 = rd.max(axis=0).astype(np.float32)
            prof = lo + (prof_u8 / 255.0) * (hi - lo)
            r0 = axes["r0"] if axes else 0.0
            dr = axes["dr"] if axes else 1.0
            kind = "map"
        else:
            n = 160
            r0 = axes["r0"] if axes else 0.0
            dr = axes["dr"] if axes else 0.1
            if axes and block["rd_shape"]:
                n = int(block["rd_shape"][1])
            prof = np.zeros(n, dtype=np.float32)
            for d in block["dets"]:
                i = int(round((d["range"] - r0) / dr))
                if 0 <= i < n:
                    for k, w in ((-1, 0.45), (0, 1.0), (1, 0.45)):
                        j = i + k
                        if 0 <= j < n:
                            prof[j] = max(prof[j], d["snr"] * w)
            kind = "dets"

        # decimate with a peak hold so a thin target cannot vanish
        n = prof.size
        if n > WF_MAX_BINS:
            g = int(math.ceil(n / WF_MAX_BINS))
            pad = (-n) % g
            if pad:
                prof = np.concatenate([prof, np.full(pad, prof.min(), np.float32)])
            prof = prof.reshape(-1, g).max(axis=1)
            dr = dr * g

        if (prof.size != self.wf_bins or abs(dr - self.wf_dr) > 1e-9
                or abs(r0 - self.wf_r0) > 1e-9 or kind != self.wf_kind):
            if self.wf:
                self.log(f"waterfall geometry changed ({self.wf_kind}->{kind}, "
                         f"{self.wf_bins}->{prof.size} bins): clearing history")
            self.wf.clear()
            self.wf_bins, self.wf_dr, self.wf_r0, self.wf_kind = prof.size, dr, r0, kind

        self.wf.append((t, prof))
        self._trim_waterfall()

        lo_db = float(prof.min())
        hi_db = float(prof.max())
        if hi_db - lo_db < 1e-6:
            hi_db = lo_db + 1.0
        u8 = np.clip((prof - lo_db) / (hi_db - lo_db) * 255.0, 0, 255).astype(np.uint8)
        return {"t": round(t, 3), "db_min": round(lo_db, 2), "db_max": round(hi_db, 2),
                "r0": self.wf_r0, "dr": self.wf_dr, "n_r": int(prof.size),
                "kind": kind, "row": _b64(u8)}

    def _trim_waterfall(self):
        keep = _f(self.cfg.get("waterfall_seconds"), 180.0)
        t_now = self.wf[-1][0] if self.wf else 0.0
        while self.wf and (t_now - self.wf[0][0]) > keep:
            self.wf.popleft()
        while self.track_hist and (t_now - self.track_hist[0]["t"]) > keep:
            self.track_hist.popleft()

    # ------------------------------------------------------------------
    def _update_track(self, t, block):
        """Kalman track on (range, radial velocity) only. No bearing exists."""
        sig_r0 = _f(self.cfg.get("radar_sigma_r"), 0.15)
        sig_v0 = _f(self.cfg.get("radar_sigma_v"), 0.10)
        snr_ref = _f(self.cfg.get("snr_ref_db"), 12.0)
        best = block["best"]
        if best is None:
            self.kf.step(t)
            meas = None
        else:
            sr = range_sigma_from_snr(best["snr"], sig_r0, snr_ref)
            sv = range_sigma_from_snr(best["snr"], sig_v0, snr_ref)
            self.kf.step(t, best["range"], best["vel"], sr, sv)
            meas = (best["range"], best["vel"], sr)
        if not self.kf.initialised:
            return None
        pt = {"t": round(t, 3),
              "r": round(self.kf.range, 3), "v": round(self.kf.vel, 3),
              "sr": round(self.kf.sigma_r, 3), "sv": round(self.kf.sigma_v, 3),
              "rm": round(meas[0], 3) if meas else None,
              "vm": round(meas[1], 3) if meas else None,
              "coast": meas is None}
        self.track_hist.append(pt)
        return pt

    # ------------------------------------------------------------------
    def _radar_out(self, include_map):
        """The latest block. /api/state omits the map (contract); the SSE
        stream carries it so the heatmap can be drawn live."""
        if self.block is None:
            return None
        out = dict(self.block)
        out["age_s"] = round(max(0.0, self.now_rel - (self.last_mono or 0.0)), 3)
        if include_map and self.map is not None:
            out["rd"] = self.map["rd"]
            out["rd_shape"] = self.map["shape"]
            out["rd_range"] = self.map["rd_range"]
            if self.map["axes"]:
                out["axes"] = self.map["axes"]
        else:
            out.pop("rd", None)
        return out

    def track_out(self, history=True):
        kf = self.kf
        out = {"valid": bool(kf.initialised), "model": kf.model,
               "updates": kf.updates, "rejects": kf.rejects, "misses": kf.misses}
        if kf.initialised:
            horizon = _f(self.cfg.get("predict_horizon_s"), 0.5)
            pr, pv, psr = kf.predict_ahead(horizon)
            out.update({
                "range_m": round(kf.range, 3),
                "vel_ms": round(kf.vel, 3),
                "sigma_r_m": round(kf.sigma_r, 3),
                "sigma_v_ms": round(kf.sigma_v, 3),
                "accel_ms2": round(kf.accel, 3),
                "cov_rv": kf.cov_rv,            # range/velocity only
                "age_s": round(max(0.0, self.now_rel - (kf.last_t or 0.0)), 2),
                "coasting": kf.misses > 0,
                "tca_s": (round(kf.time_to_closest(), 2)
                          if kf.time_to_closest() is not None else None),
                "predict": {"horizon_s": horizon, "range_m": round(pr, 3),
                            "vel_ms": round(pv, 3), "sigma_r_m": round(psr, 3)},
                "extrapolation_justified": bool(prediction_is_justified(
                    kf.sigma_r, _f(self.cfg.get("predict_horizon_s"), 0.5),
                    max(abs(kf.vel), 0.01))),
            })
        if history:
            h = list(self.track_hist)
            if len(h) > STATE_TRACK_POINTS:
                step = int(math.ceil(len(h) / STATE_TRACK_POINTS))
                h = h[::step] + [h[-1]]
            out["history"] = h
        return out

    def waterfall_out(self):
        rows = list(self.wf)
        if not rows:
            return {"n_r": 0, "rows_n": 0, "t": [], "rows": "",
                    "r0": self.wf_r0, "dr": self.wf_dr, "kind": self.wf_kind,
                    "db_min": 0.0, "db_max": 1.0,
                    "seconds": _f(self.cfg.get("waterfall_seconds"), 180.0)}
        if len(rows) > STATE_WF_ROWS:
            step = int(math.ceil(len(rows) / STATE_WF_ROWS))
            rows = rows[::step] + [rows[-1]]
        ts = [round(t, 3) for t, _ in rows]
        mat = np.stack([p for _, p in rows])
        lo = float(np.percentile(mat, 1.0))
        hi = float(mat.max())
        if hi - lo < 1e-6:
            hi = lo + 1.0
        u8 = np.clip((mat - lo) / (hi - lo) * 255.0, 0, 255).astype(np.uint8)
        return {"n_r": int(mat.shape[1]), "rows_n": int(mat.shape[0]), "t": ts,
                "r0": self.wf_r0, "dr": self.wf_dr, "kind": self.wf_kind,
                "db_min": round(lo, 2), "db_max": round(hi, 2),
                "span_s": round(ts[-1] - ts[0], 1),
                "seconds": _f(self.cfg.get("waterfall_seconds"), 180.0),
                "rows": _b64(u8)}

    # ------------------------------------------------------------------
    def stats_out(self):
        now = self.now_rel
        age = None if self.last_mono is None else max(0.0, now - self.last_mono)
        hz = None
        if len(self.arrivals) >= 2:
            span = self.arrivals[-1] - self.arrivals[0]
            if span > 0:
                hz = (len(self.arrivals) - 1) / span

        def summarise(dq):
            if not dq:
                return None
            a = np.asarray(dq, float)
            mean = float(a.mean())
            pk = float(a.max() - a.min())
            return {"last": round(float(a[-1]), 4), "mean": round(mean, 4),
                    "min": round(float(a.min()), 4), "max": round(float(a.max()), 4),
                    "pk_pk": round(pk, 4),
                    "pk_pk_pct": round(100.0 * pk / mean, 3) if mean else None,
                    "n": int(a.size)}

        tc = summarise(self.t_chirp)
        pr = summarise(self.pri)
        duty = None
        if tc and pr and pr["mean"]:
            duty = round(100.0 * tc["mean"] / pr["mean"], 1)

        # --- sync health -------------------------------------------------
        # t_chirp_ms/pri_ms are MEASURED off the hardware SYNC line on every
        # block. A chirp time that jumps block to block is the documented
        # symptom of a marginal sync divider, so it gets its own state.
        stale = _f(self.cfg.get("stale_s"), 3.0)
        warn = _f(self.cfg.get("chirp_jitter_warn_pct"), 2.0)
        if self.blocks == 0:
            sync = {"state": "nodata", "ok": False,
                    "detail": "no block received yet"}
        elif age is not None and age > stale:
            sync = {"state": "stale", "ok": False,
                    "detail": f"no block for {age:.1f} s (> {stale:.0f} s)"}
        elif tc is None or not tc["last"] or tc["last"] <= 0:
            sync = {"state": "nosync", "ok": False,
                    "detail": "no chirp time measured on the SYNC line"}
        elif tc["pk_pk_pct"] is not None and tc["pk_pk_pct"] > warn:
            sync = {"state": "jitter", "ok": False,
                    "detail": (f"chirp time jumping {tc['pk_pk']*1000:.0f} us pk-pk "
                               f"({tc['pk_pk_pct']:.2f}% > {warn:.1f}%): "
                               f"suspect a marginal sync divider")}
        else:
            sync = {"state": "ok", "ok": True,
                    "detail": f"chirp {tc['last']:.3f} ms, PRI {pr['last']:.3f} ms"
                              if pr else f"chirp {tc['last']:.3f} ms"}

        return {"seq": self.seq, "blocks": self.blocks, "bad_blocks": self.bad_blocks,
                "last_error": self.last_error,
                "block_hz": round(hz, 3) if hz else None,
                "age_s": round(age, 3) if age is not None else None,
                "uptime_s": round(now, 1),
                "t_chirp_ms": tc, "pri_ms": pr, "duty_pct": duty,
                "n_dets": len(self.block["dets"]) if self.block else 0,
                "has_map": bool(self.map), "sync": sync,
                "demo": self.demo, "clients": len(self.subs),
                "stale_s": stale, "jitter_warn_pct": warn,
                "t_source": round(self.block["t"], 2) if self.block else None}

    def state_out(self):
        """GET /api/state — the map is deliberately NOT included (contract)."""
        return {"radar": self._radar_out(include_map=False),
                "track": self.track_out(history=True),
                "waterfall": self.waterfall_out(),
                "stats": self.stats_out(),
                "log": list(self.log_lines)[-12:]}

    def snapshot_event(self):
        """The latest block, replayed to a client that has just connected so
        its heatmap is populated immediately instead of one block later."""
        if self.block is None:
            return None
        return {"seq": self.seq, "t_rel": round(self.last_mono or 0.0, 3),
                "replay": True,
                "radar": self._radar_out(include_map=True),
                "track": self.track_out(history=False),
                "stats": self.stats_out(),
                "point": self.track_hist[-1] if self.track_hist else None,
                "wf": None}

    # ------------------------------------------------------------------
    def _publish(self, event):
        for q in list(self.subs):
            if q.full():
                try:
                    q.get_nowait()          # slow client: drop its oldest block
                except asyncio.QueueEmpty:
                    pass
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass


# ======================================================================
# DEMO ONLY — synthetic blocks so the GUI runs with no radar attached
# ======================================================================

class DemoRadar:
    """DEMO-ONLY synthetic block generator. NOT a model of the hardware.

    There is a real simulator in fmcw_sim.py / synth.py; this is deliberately
    independent of both so the GUI can be opened on any machine with nothing
    but aiohttp and numpy. It fabricates:

      * thermal noise (exponential power -> dB), noise floor near -120 dB
      * one target: closes from 10 m at ~1 m/s, turns at ~1.5 m, opens again
      * a TX leakage ridge at zero Doppler near 0.3 m with range sidelobes
      * two static ground-clutter returns at zero Doppler
      * detections with realistic measurement scatter, R^-4 SNR, and an
        occasional dropout so the track has to coast
      * t_chirp_ms / pri_ms with small jitter, plus a deliberate periodic
        chirp-time excursion so the "marginal sync divider" warning can be
        seen working

    Nothing in here is used when a real radar is posting blocks.
    """

    C = 299792458.0

    def __init__(self, seed=3, n_v=64, n_r=48, f0=2.36e9, bw=140e6,
                 range_pad=2, t_chirp_ms=6.395, pri_ms=7.392, with_map=True):
        self.rng = np.random.default_rng(seed)
        self.n_v, self.n_r = int(n_v), int(n_r)
        self.with_map = bool(with_map)
        self.t_chirp_ms, self.pri_ms = float(t_chirp_ms), float(pri_ms)
        lam = self.C / (f0 + bw / 2.0)
        # range resolution is c/2B and nothing downstream changes it; the FFT
        # zero-pad only samples that same mainlobe more finely (fmcw_sim.py).
        self.res_r = self.C / (2.0 * bw)             # 1.07 m at 140 MHz
        self.dr = self.res_r / float(range_pad)
        self.lobe_r = 1.05 * float(range_pad)        # mainlobe width, in bins
        self.r0 = 0.0
        v_max = lam / (4.0 * (pri_ms * 1e-3))        # unambiguous +/- velocity
        self.v0 = -v_max
        self.dv = 2.0 * v_max / self.n_v
        self.period = self.n_v * pri_ms * 1e-3       # one block = n_v chirps
        self.r = 10.0
        self.v = -1.0
        self.hover_s = 0.0
        self.k = 0
        self.t_wall = time.time()
        r_idx = np.arange(self.n_r)
        self.r_axis = self.r0 + r_idx * self.dr
        self.v_axis = self.v0 + np.arange(self.n_v) * self.dv

    # -- a separable windowed point response, in power --------------------
    def _blob(self, r_m, v_ms, snr_db, v_width=1.0, r_tail=0.0):
        ir = (r_m - self.r0) / self.dr
        iv = (v_ms - self.v0) / self.dv if self.dv else 0.0
        dr_i = (np.arange(self.n_r) - ir) / self.lobe_r
        dv_i = (np.arange(self.n_v) - iv) / max(v_width, 1e-6)
        # Hanning mainlobe + a -32 dB sidelobe floor that decays with distance
        mr = np.exp(-dr_i ** 2) + 10 ** (-3.2) / (1.0 + dr_i ** 2)
        if r_tail > 0:                  # leakage smears along range
            mr = mr + r_tail * 10 ** (-1.6 * np.abs(dr_i))
        mv = np.exp(-(dv_i / 1.05) ** 2) + 10 ** (-3.2) / (1.0 + dv_i ** 2)
        return (10 ** (snr_db / 10.0)) * np.outer(mv, mr)

    def next_block(self):
        self.k += 1
        dt = self.period
        self.t_wall += dt
        # --- truth: close from 10 m at ~1 m/s, hover at ~1.5 m, back out --
        # self.v is the COMMANDED leg velocity; v_now is what it is doing this
        # block (zero while hovering, which parks it in the clutter row).
        if self.hover_s > 0.0:
            self.hover_s -= dt
            v_now = float(self.rng.normal(0.0, 0.04))
        else:
            v_now = self.v + float(self.rng.normal(0.0, 0.03))   # a little wander
        self.r += v_now * dt
        if self.hover_s <= 0.0:
            if self.r <= 1.5 and self.v < 0:
                self.v, self.hover_s = 0.45, 5.0     # stop, then drift out
            elif self.r >= 10.0 and self.v > 0:
                self.v, self.hover_s = -1.0, 3.0     # stop, then close again
        r_t = float(np.clip(self.r, 0.4, self.r_axis[-1] - 0.5))
        v_t = float(np.clip(v_now, self.v0 + 2 * self.dv, -self.v0 - 2 * self.dv))

        snr_t = 18.0 + 40.0 * math.log10(10.0 / max(r_t, 0.3))   # R^-4
        snr_t = float(min(snr_t, 48.0))

        power = self.rng.exponential(1.0, size=(self.n_v, self.n_r))   # thermal
        power += self._blob(r_t, v_t, snr_t)
        power += self._blob(0.30, 0.0, 52.0, v_width=0.9, r_tail=0.06)  # TX leakage
        power += self._blob(2.10, 0.0, 16.0, v_width=0.9)               # clutter
        power += self._blob(5.60, 0.0, 12.0, v_width=0.9)               # clutter
        rd_db = 10.0 * np.log10(power + 1e-12) - 120.0                  # to dBFS-ish

        # --- detections (what CFAR would hand over; r < 1 m is blanked) ---
        dets = []
        drop = (self.k % 31) in (0, 1)       # occasional miss -> track coasts
        if not drop:
            dets.append({"range": round(r_t + float(self.rng.normal(0, 0.10)), 3),
                         "vel": round(v_t + float(self.rng.normal(0, 0.07)), 3),
                         "snr": round(snr_t + float(self.rng.normal(0, 0.8)), 2)})
        if self.k % 7 == 0:
            dets.append({"range": round(5.60 + float(self.rng.normal(0, 0.12)), 3),
                         "vel": round(float(self.rng.normal(0, 0.05)), 3),
                         "snr": round(12.0 + float(self.rng.normal(0, 1.0)), 2)})
        dets.sort(key=lambda d: d["snr"], reverse=True)

        # --- timing off the SYNC line, with a deliberate divider glitch ---
        tc = self.t_chirp_ms + float(self.rng.normal(0, 0.003))
        if 120 <= (self.k % 240) < 124:      # DEMO: marginal sync divider
            tc += 0.16
        pri = self.pri_ms + float(self.rng.normal(0, 0.004))

        payload = {"t": round(self.t_wall, 2),
                   "t_chirp_ms": round(tc, 3), "pri_ms": round(pri, 3),
                   "dets": dets[:MAX_DETS],
                   "best": dict(dets[0]) if dets else None,
                   "axes": {"r0": round(self.r0, 4), "dr": round(self.dr, 4),
                            "v0": round(self.v0, 4), "dv": round(self.dv, 4)},
                   "rd_shape": [self.n_v, self.n_r]}
        if self.with_map:
            lo = float(np.percentile(rd_db, 0.5))
            hi = float(rd_db.max())
            u8 = np.clip((rd_db - lo) / max(hi - lo, 1e-6) * 255.0, 0, 255).astype(np.uint8)
            payload["rd_range"] = {"min": round(lo, 2), "max": round(hi, 2)}
            payload["rd"] = _b64(u8)
        return payload, dt


async def demo_loop(app):
    st = app["station"]
    src = app["demo_source"]
    st.log(f"DEMO MODE: synthesising blocks at {1.0/src.period:.2f} Hz "
           f"({src.n_v} chirps x {src.pri_ms:.3f} ms), "
           f"map {'on' if src.with_map else 'off'} — no hardware in use")
    try:
        while True:
            payload, dt = src.next_block()
            try:
                st.ingest(payload)
            except BadBlock as e:                 # would be a demo bug
                st.log(f"demo produced an invalid block: {e}")
            await asyncio.sleep(dt)
    except asyncio.CancelledError:
        pass


# ======================================================================
# HTTP
# ======================================================================

STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}


async def static_handler(request):
    name, ctype = STATIC[request.path]
    path = WEB_DIR / name
    if not path.is_file():
        return web.Response(status=404, text=f"{name} missing from {WEB_DIR}")
    return web.Response(body=path.read_bytes(), content_type=ctype.split(";")[0],
                        charset="utf-8",
                        headers={"Cache-Control": "no-store"})


async def api_radar(request):
    """POST /api/radar — ingest one block from radar_acquire.py."""
    st = request.app["station"]
    try:
        raw = await request.json()
    except Exception as e:
        st.bad_blocks += 1
        st.last_error = f"bad JSON: {e}"
        return web.json_response({"ok": False, "error": st.last_error}, status=400)
    try:
        ev = st.ingest(raw)
    except BadBlock as e:
        st.bad_blocks += 1
        st.last_error = str(e)
        st.log(f"rejected block: {e}")
        return web.json_response({"ok": False, "error": str(e)}, status=400)
    return web.json_response({"ok": True, "seq": ev["seq"],
                              "dets": len(ev["radar"]["dets"]),
                              "map": bool(st.map)})


async def api_state(request):
    return web.json_response(request.app["station"].state_out(),
                             headers={"Cache-Control": "no-store"})


async def api_stream(request):
    """GET /api/stream — Server-Sent Events, one event per ingested block."""
    st = request.app["station"]
    resp = web.StreamResponse(status=200, headers={
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache, no-store",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    })
    await resp.prepare(request)
    q = asyncio.Queue(maxsize=8)
    st.subs.add(q)

    async def send(obj):
        await resp.write(b"data: " + json.dumps(obj).encode() + b"\n\n")

    try:
        await resp.write(b"retry: 2000\n\n")
        snap = st.snapshot_event()
        if snap is not None:
            await send(snap)
        while True:
            try:
                ev = await asyncio.wait_for(q.get(), timeout=5.0)
            except asyncio.TimeoutError:
                # keepalive comment; also nudges the page's NO SYNC timer
                await resp.write(b": keepalive " + str(round(st.now_rel, 1)).encode()
                                 + b"\n\n")
                continue
            await send(ev)
    except (asyncio.CancelledError, ConnectionResetError):
        pass
    except Exception as e:                     # client vanished mid-write
        st.log(f"stream closed: {type(e).__name__}: {e}")
    finally:
        st.subs.discard(q)
    return resp


def load_config():
    try:
        cfg = json.loads(CONFIG_PATH.read_text())
        if not isinstance(cfg, dict):
            raise ValueError("config.json must contain an object")
    except FileNotFoundError:
        cfg = {}
    except Exception as e:
        print(f"config.json unreadable ({e}); using defaults", flush=True)
        cfg = {}
    # Stage 1 reads these and nothing else. Anything else in the file is left
    # over from a design this radar does not implement (there is no bearing
    # and no multilateration here), so say so rather than pretending to use it.
    known = {"radar_sigma_r", "radar_sigma_v", "snr_ref_db", "sigma_a",
             "track_model", "track_gate_sigma", "track_coast_s",
             "predict_horizon_s", "waterfall_seconds", "stale_s",
             "chirp_jitter_warn_pct"}
    for key in [k for k in cfg if not k.startswith("_") and k not in known]:
        print(f"config.json: ignoring '{key}' — not a stage-1 radar key",
              flush=True)
        cfg.pop(key)
    return cfg


def build_app(demo=False, demo_map=True, demo_seed=3):
    cfg = load_config()
    app = web.Application(client_max_size=8 * 1024 * 1024)
    app["station"] = Station(cfg, demo=demo)
    for route in STATIC:
        app.router.add_get(route, static_handler)
    app.router.add_post("/api/radar", api_radar)
    app.router.add_get("/api/state", api_state)
    app.router.add_get("/api/stream", api_stream)
    app.router.add_get("/api/config", lambda r: web.json_response(cfg))
    app.router.add_get("/favicon.ico", lambda r: web.Response(status=204))

    if demo:
        app["demo_source"] = DemoRadar(seed=demo_seed, with_map=demo_map)

        async def _start(a):
            a["demo_task"] = asyncio.create_task(demo_loop(a))

        async def _stop(a):
            t = a.get("demo_task")
            if t:
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass
        app.on_startup.append(_start)
        app.on_cleanup.append(_stop)
    return app


def main():
    ap = argparse.ArgumentParser(description="Stage-1 FMCW radar console")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--demo", action="store_true",
                    help="synthesise blocks so the GUI runs with no hardware")
    ap.add_argument("--demo-no-map", action="store_true",
                    help="demo without the range-Doppler map (as if radar_acquire "
                         "ran without --map)")
    ap.add_argument("--demo-seed", type=int, default=3)
    args = ap.parse_args()

    app = build_app(demo=args.demo, demo_map=not args.demo_no_map,
                    demo_seed=args.demo_seed)
    st = app["station"]
    st.log(f"stage-1 radar console on http://localhost:{args.port}"
           + ("  [DEMO DATA]" if args.demo else ""))
    st.log("POST blocks to /api/radar  (radar_acquire.py --server http://HOST:PORT --map)")
    web.run_app(app, host=args.host, port=args.port, print=None,
                access_log=None)


if __name__ == "__main__":
    main()
