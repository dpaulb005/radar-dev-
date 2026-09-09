#!/usr/bin/env python3
"""
server.py — radar ground station with web GUI.

Runs the solver from locate.py and serves a real-time operator console
(web/) over HTTP + WebSocket on http://localhost:8080.

Usage:
    python server.py                  # start idle; connect from the GUI
    python server.py --hub /dev/ttyUSB0
    python server.py --sim            # synthetic flight, no hardware
    python server.py --port 9000

The GUI can: pick/connect serial ports, toggle sim mode, edit node
positions and path-loss config (persisted to config.json), run the
per-node RSSI calibration wizard, record sessions to JSONL, and shows a
PPI-style tactical plot plus node health with RSSI sparklines.
"""

import argparse
import asyncio
import json
import math
import pathlib
import queue
import threading
import time

import numpy as np
from aiohttp import web, WSMsgType

from locate import (
    rssi_to_distance,
    rssi_distance_sigma,
    solve_position,
    RSSI_SIGMA_DB,
    FTM_SIGMA_M,
)
import guidance
import geometry
from tracker import TrackKF, az_el, prediction_is_justified

BASE = pathlib.Path(__file__).resolve().parent
CONFIG_PATH = BASE / "config.json"
REC_DIR = BASE / "recordings"

SOLVE_HZ = 10.0
STATE_HZ = 10.0
MEAS_MAX_AGE_S = 1.0
EMA_ALPHA = 0.35


# ----------------------------------------------------------------------
# data sources (serial / sim) — threads feeding a queue, like locate.py
# ----------------------------------------------------------------------

class Sources:
    def __init__(self, station):
        self.station = station
        self.q = queue.Queue()
        self._serial_stop = threading.Event()
        self._serial_thread = None
        self._sim_stop = threading.Event()
        self._sim_thread = None
        self.port = None
        self.serial_ok = False

    # -- serial ---------------------------------------------------------
    def connect(self, port, baud=115200):
        self.disconnect()
        self._serial_stop = threading.Event()
        self.port = port
        self._serial_thread = threading.Thread(
            target=self._serial_loop, args=(port, baud, self._serial_stop),
            daemon=True)
        self._serial_thread.start()

    def disconnect(self):
        if self._serial_thread:
            self._serial_stop.set()
            self._serial_thread = None
        self.port = None
        self.serial_ok = False

    def _serial_loop(self, port, baud, stop):
        import serial
        while not stop.is_set():
            try:
                with serial.Serial(port, baud, timeout=1) as ser:
                    self.serial_ok = True
                    self.station.log(f"serial open: {port}")
                    while not stop.is_set():
                        line = ser.readline().decode(errors="replace").strip()
                        if not line.startswith("{"):
                            continue
                        try:
                            self.q.put(json.loads(line))
                        except json.JSONDecodeError:
                            pass
            except Exception as e:
                if self.serial_ok or True:
                    self.station.log(f"serial: {e}")
                self.serial_ok = False
                stop.wait(2)
        self.serial_ok = False

    # -- sim ------------------------------------------------------------
    def sim(self, on):
        if on and not self._sim_thread:
            self._sim_stop = threading.Event()
            self._sim_thread = threading.Thread(
                target=self._sim_loop, args=(self._sim_stop,), daemon=True)
            self._sim_thread.start()
            self.station.log("sim: started")
        elif not on and self._sim_thread:
            self._sim_stop.set()
            self._sim_thread = None
            self.station.log("sim: stopped")

    @property
    def sim_on(self):
        return self._sim_thread is not None

    def _sim_loop(self, stop):
        rng = np.random.default_rng()
        t0 = time.time()
        # interceptor state for the optional pursuit demo (horizontal plane)
        p_i = None
        v_i = np.zeros(2)
        a_state = np.zeros(2)
        t_prev = t0
        while not stop.is_set():
            cfg = self.station.cfg
            n = cfg["path_loss_n"]
            nodes = cfg["nodes"]
            anch = np.array([v["pos"] for v in nodes.values()])
            cx, cy = anch[:, 0].mean(), anch[:, 1].mean()
            r = max(2.5, 0.35 * (anch[:, :2].max() - anch[:, :2].min()))
            t = time.time() - t0
            true = np.array([cx + r * math.cos(0.35 * t),
                             cy + r * math.sin(0.55 * t),
                             cfg.get("drone_z", 1.5)])
            for nid, nc in nodes.items():
                d = float(np.linalg.norm(true - np.array(nc["pos"])))
                rssi = nc["rssi0"] - 10 * n * math.log10(max(d, 0.1))
                rssi += rng.normal(0, RSSI_SIGMA_DB)
                self.q.put({"node": int(nid), "rssi": round(rssi, 1), "n": 6})
            self.q.put({"_true": true.tolist()})

            # -------- optional interceptor pursuit demo --------
            if self.station.pursuit:
                if p_i is None:
                    p_i = anch[0, :2].astype(float).copy()
                    v_i = np.zeros(2)
                    a_state = np.zeros(2)
                a_max = guidance.max_accel(35.0)
                v_max = 12.0
                drag = a_max / v_max
                # noisy estimates of both drones (what the radar would give)
                est_i = p_i + rng.normal(0, 1.2, 2)
                est_t = true[:2] + rng.normal(0, 1.2, 2)
                # crude target velocity from the sim's analytic motion
                vt = np.array([-r * 0.35 * math.sin(0.35 * t),
                               r * 0.55 * math.cos(0.55 * t)])
                a_cmd = guidance.track(est_i, v_i, est_t, vt,
                                       v_max=v_max, a_max=a_max)
                # integrate a few physics substeps over this tick
                dt = min(0.3, time.time() - t_prev)
                sub = 6
                h = dt / sub
                for _ in range(sub):
                    a_state += (a_cmd - a_state) * (h / (0.15 + h))
                    v_i = v_i + (a_state - drag * v_i) * h
                    p_i = p_i + v_i * h
                rng_m = float(np.linalg.norm(true[:2] - p_i))
                self.q.put({"_pursuit": {
                    "i_true": [float(p_i[0]), float(p_i[1])],
                    "i_est": [float(est_i[0]), float(est_i[1])],
                    "t_est": [float(est_t[0]), float(est_t[1])],
                    "speed": float(np.linalg.norm(v_i)),
                    "range": round(rng_m, 2)}})
            else:
                p_i = None
            t_prev = time.time()
            stop.wait(0.25)


# ----------------------------------------------------------------------
# station core — measurements, solver, calibration, recording
# ----------------------------------------------------------------------

class Station:
    def __init__(self):
        self.cfg = json.loads(CONFIG_PATH.read_text())
        self.cfg["nodes"] = {str(k): v for k, v in self.cfg["nodes"].items()}
        self.sources = Sources(self)
        self.latest = {}        # node_id(str) -> dict(rssi, dist, sigma, ts, count, hz)
        self.rate_win = {}      # node_id -> [timestamps]
        self.fix = None         # dict(x,y,z,resid,nodes_used,t)
        self.est = None         # np.array(3), smoothed
        self.vel = np.zeros(2)
        self.true = None        # sim ground truth
        self.logbuf = []
        self.clients = set()
        self.cal = None         # active calibration dict
        self.rec_file = None
        self.rec_path = None
        self.pursuit = False    # two-drone pursuit demo (sim only)
        self.pursuit_state = None
        # Tier-1 tracking filter. Runs always (it supplies the covariance
        # ellipse and az/el), but only DRIVES the displayed fix when the
        # sensor is good enough for it to beat the EMA -- see tracker.py
        # _self_test, which measures exactly that.
        self.kf = TrackKF(sigma_a=float(self.cfg.get("sigma_a", 2.0)), model="cv")
        self.predict_horizon = float(self.cfg.get("predict_horizon_s", 0.5))
        self.ranging = self.cfg.get("ranging", "rssi")
        self.kf_drives = False   # decided per-fix by the gate
        self.radar = None        # latest active-radar fix (radar_acquire.py)

    # -- logging --------------------------------------------------------
    def log(self, msg):
        entry = {"t": round(time.time(), 1), "msg": msg}
        self.logbuf.append(entry)
        self.logbuf = self.logbuf[-200:]
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

    # -- config ---------------------------------------------------------
    def save_cfg(self):
        CONFIG_PATH.write_text(json.dumps(self.cfg, indent=2) + "\n")

    def update_cfg(self, patch):
        if "path_loss_n" in patch:
            self.cfg["path_loss_n"] = float(patch["path_loss_n"])
        if "drone_z" in patch:
            self.cfg["drone_z"] = float(patch["drone_z"])
        for nid, nc in patch.get("nodes", {}).items():
            node = self.cfg["nodes"].setdefault(str(nid), {"pos": [0, 0, 1], "rssi0": -40})
            if "pos" in nc:
                node["pos"] = [float(v) for v in nc["pos"]]
            if "rssi0" in nc:
                node["rssi0"] = float(nc["rssi0"])
        for nid in patch.get("remove_nodes", []):
            self.cfg["nodes"].pop(str(nid), None)
            self.latest.pop(str(nid), None)
        self.save_cfg()
        self.log("config updated")

    # -- ingest ---------------------------------------------------------
    def ingest_radar(self, m, now):
        """A fix from the active FMCW radar (radar_acquire.py -> /api/radar).

        Range comes from the beat frequency and azimuth from the phase between
        the two receivers (interferometer.py). The covariance is still polar,
        but no longer for the old reason: range is quantised by the 3.75 m cell
        while bearing is good to ~0.1 deg, which at 10 m is 2 cm of cross-range.
        Cross-range is now the TIGHTER axis, not the wider one."""
        try:
            r = float(m["range"]); az = math.radians(float(m["az"]))
        except (KeyError, ValueError, TypeError):
            return
        sig_r = float(self.cfg.get("radar_sigma_r", 0.15))
        sig_x = r * math.radians(float(self.cfg.get("radar_sigma_az_deg", 2.5)))
        c, s_ = math.cos(az), math.sin(az)
        rot = np.array([[c, -s_], [s_, c]])
        R2 = rot @ np.diag([sig_r ** 2, sig_x ** 2]) @ rot.T
        R = np.diag([0.0, 0.0, 4.0 ** 2]); R[:2, :2] = R2
        org = self.cfg.get("radar_origin", [0.0, 0.0, 1.0])
        pos = np.array([org[0] + r * c, org[1] + r * s_,
                        float(m.get("z", self.cfg.get("drone_z", 1.5)))])
        self.radar = {"pos": pos, "R": R, "vel_r": float(m.get("vel", 0.0)),
                      "snr": float(m.get("snr", 0.0)), "beams": int(m.get("beams", 0)),
                      "range": r, "az": float(m["az"]), "ts": now}
        if self.rec_file:
            self.rec_file.write(json.dumps({"t": now, "radar": m}) + "\n")

    def ingest(self, msg, now):
        if "radar" in msg:
            self.ingest_radar(msg["radar"], now)
            return
        if "_true" in msg:
            self.true = msg["_true"]
            return
        if "_pursuit" in msg:
            self.pursuit_state = msg["_pursuit"]
            return
        if "node" not in msg:
            return
        nid = str(msg["node"])
        if nid not in self.cfg["nodes"]:
            return
        nc = self.cfg["nodes"][nid]
        rec = self.latest.get(nid, {})
        if "dist" in msg:
            rec.update(dist=float(msg["dist"]), sigma=FTM_SIGMA_M,
                       rssi=None, ts=now)
        elif "rssi" in msg:
            rssi = float(msg["rssi"])
            d = rssi_to_distance(rssi, nc["rssi0"], self.cfg["path_loss_n"])
            rec.update(rssi=rssi, dist=d,
                       sigma=rssi_distance_sigma(d, self.cfg["path_loss_n"]),
                       ts=now)
            if self.cal and self.cal["node"] == nid:
                self.cal["samples"].append(rssi)
        else:
            return
        rec["count"] = rec.get("count", 0) + 1
        self.latest[nid] = rec
        win = self.rate_win.setdefault(nid, [])
        win.append(now)
        self.rate_win[nid] = [t for t in win if now - t < 3.0]

        if self.rec_file:
            self.rec_file.write(json.dumps({"t": now, **msg}) + "\n")

    # -- solve ----------------------------------------------------------
    def solve(self, now):
        anch = np.array([v["pos"] for v in self.cfg["nodes"].values()], float)
        radar_fresh = self.radar is not None and now - self.radar["ts"] <= 2.5
        if radar_fresh:
            # active radar: the fix IS the measurement, no multilateration
            if self.radar.get("used_ts") == self.radar["ts"]:
                return                       # one scan -> one update
            self.radar["used_ts"] = self.radar["ts"]
            pos, R = self.radar["pos"], self.radar["R"]
            resid, n_used = 0.0, self.radar["beams"]
            if self.est is None:
                self.est = pos.copy()
            prev = self.est.copy()
            self.est = pos.copy()            # no EMA: scans are ~1 s apart
            dt = max(now - self.radar.get("prev_ts", now - 1.0), 0.3)
            self.vel = (self.est[:2] - prev[:2]) / dt
            self.radar["prev_ts"] = now
        else:
            meas = []
            for nid, rec in self.latest.items():
                if now - rec["ts"] <= MEAS_MAX_AGE_S:
                    meas.append((np.array(self.cfg["nodes"][nid]["pos"]),
                                 rec["dist"], rec["sigma"]))
            if len(meas) < 3:
                return
            if self.est is None:
                self.est = np.array([anch[:, 0].mean(), anch[:, 1].mean(),
                                     self.cfg.get("drone_z", 1.5)])
            prev = self.est.copy()
            solve_3d = bool(self.cfg.get("solve_3d", False))
            pos, resid = solve_position(meas, self.est, self.cfg.get("drone_z", 1.5),
                                        solve_3d=solve_3d)
            n_used = len(meas)
            self.est = EMA_ALPHA * pos + (1 - EMA_ALPHA) * self.est
            dt = 1.0 / SOLVE_HZ
            self.vel = 0.3 * ((self.est[:2] - prev[:2]) / dt) + 0.7 * self.vel

            # --- Tier-1 Kalman filter, fed with a geometry-derived covariance ---
            R = geometry.position_cov(anch, pos, ranging=self.ranging)
            if R is None:
                R = np.diag([2.0 ** 2, 2.0 ** 2, 6.0 ** 2])
        self.kf.step(now, pos, R)
        sig = float(math.sqrt(max(R[0, 0], R[1, 1])))
        self.kf_drives = prediction_is_justified(sig, self.predict_horizon,
                                                 max(self.kf.speed, 0.5))

        # which estimate the operator sees
        if self.kf_drives and self.kf.initialised:
            shown = self.kf.predict_ahead(self.predict_horizon)[0]
            shown_v = self.kf.vel
        else:
            shown = self.est
            shown_v = np.array([self.vel[0], self.vel[1], 0.0])

        if radar_fresh:
            ref = np.array(self.cfg.get("radar_origin", [0.0, 0.0, 1.0]), float)
        else:
            ref = np.array([anch[:, 0].mean(), anch[:, 1].mean(), anch[:, 2].min()])
        az, el, slant = az_el(shown, ref)
        a_semi, b_semi, ang = TrackKF.ellipse(self.kf.P[:2, :2]) if self.kf.initialised \
            else (sig, sig, 0.0)
        pred_p, pred_P = self.kf.predict_ahead(self.predict_horizon)
        pa, pb, pang = TrackKF.ellipse(pred_P[:2, :2]) if pred_P is not None else (0, 0, 0)

        self.fix = {"x": round(float(shown[0]), 2),
                    "y": round(float(shown[1]), 2),
                    "z": round(float(shown[2]), 2),
                    "vx": round(float(shown_v[0]), 2),
                    "vy": round(float(shown_v[1]), 2),
                    "vz": round(float(shown_v[2]), 2),
                    "resid": round(resid, 2),
                    "nodes_used": n_used,
                    "source": "radar" if radar_fresh else self.ranging,
                    "az": round(az, 1), "el": round(el, 1), "slant": round(slant, 2),
                    "sigma": round(sig, 2),
                    "ell": [round(a_semi, 2), round(b_semi, 2), round(ang, 3)],
                    "kf": bool(self.kf_drives),
                    "pred": ([round(float(pred_p[0]), 2), round(float(pred_p[1]), 2),
                              round(float(pred_p[2]), 2)] if pred_p is not None else None),
                    "pred_ell": [round(pa, 2), round(pb, 2), round(pang, 3)],
                    "horizon": self.predict_horizon,
                    "t": round(now, 2)}
        if self.rec_file:
            self.rec_file.write(json.dumps({"fix": self.fix}) + "\n")

    # -- calibration ----------------------------------------------------
    def cal_start(self, nid, dist, seconds):
        self.cal = {"node": str(nid), "dist": float(dist),
                    "seconds": float(seconds), "t0": time.time(),
                    "samples": []}
        self.log(f"calibration: node {nid} @ {dist} m for {seconds:.0f}s")

    def cal_poll(self, now):
        """Returns a result dict when the capture window ends, else None."""
        if not self.cal or now - self.cal["t0"] < self.cal["seconds"]:
            return None
        cal, self.cal = self.cal, None
        s = sorted(cal["samples"])
        if not s:
            self.log("calibration: no samples received")
            return {"node": cal["node"], "ok": False, "n": 0}
        med = s[len(s) // 2]
        rssi0 = med + 10.0 * self.cfg["path_loss_n"] * math.log10(cal["dist"])
        self.log(f"calibration: node {cal['node']} median {med:.1f} dBm "
                 f"-> rssi0 {rssi0:.1f} ({len(s)} samples)")
        return {"node": cal["node"], "ok": True, "n": len(s),
                "median": round(med, 1), "rssi0": round(rssi0, 1)}

    # -- recording ------------------------------------------------------
    def record(self, on):
        if on and not self.rec_file:
            REC_DIR.mkdir(exist_ok=True)
            self.rec_path = REC_DIR / time.strftime("rec-%Y%m%d-%H%M%S.jsonl")
            self.rec_file = open(self.rec_path, "w")
            self.log(f"recording -> {self.rec_path.name}")
        elif not on and self.rec_file:
            self.rec_file.close()
            self.rec_file = None
            self.log(f"recording stopped ({self.rec_path.name})")

    # -- state snapshot for the GUI -------------------------------------
    def state(self, now):
        nodes = {}
        for nid, nc in self.cfg["nodes"].items():
            rec = self.latest.get(nid, {})
            age = now - rec["ts"] if "ts" in rec else None
            nodes[nid] = {
                "pos": nc["pos"], "rssi0": nc["rssi0"],
                "rssi": rec.get("rssi"), "dist": round(rec["dist"], 2) if "dist" in rec else None,
                "age": round(age, 2) if age is not None else None,
                "hz": round(len(self.rate_win.get(nid, [])) / 3.0, 1),
            }
        fix = None
        if self.fix and now - self.fix["t"] < 2.0:
            fix = self.fix
        return {"type": "state", "t": round(now, 2),
                "fix": fix, "nodes": nodes,
                "true": self.true if self.sources.sim_on else None,
                "cfg": {"path_loss_n": self.cfg["path_loss_n"],
                        "drone_z": self.cfg.get("drone_z", 1.5)},
                "link": {"port": self.sources.port,
                         "serial_ok": self.sources.serial_ok,
                         "sim": self.sources.sim_on},
                "cal": ({"node": self.cal["node"],
                         "progress": min(1.0, (now - self.cal["t0"]) / self.cal["seconds"]),
                         "n": len(self.cal["samples"])} if self.cal else None),
                "recording": self.rec_path.name if self.rec_file else None,
                "radar": ({"range": round(self.radar["range"], 2),
                           "az": round(self.radar["az"], 1),
                           "vel": round(self.radar["vel_r"], 2),
                           "snr": round(self.radar["snr"], 1),
                           "beams": self.radar["beams"],
                           "age": round(now - self.radar["ts"], 1)}
                          if self.radar else None),
                "pursuit": self.pursuit_state if self.pursuit else None,
                "log": self.logbuf[-40:]}


# ----------------------------------------------------------------------
# web app
# ----------------------------------------------------------------------

def list_ports():
    try:
        from serial.tools import list_ports as lp
        return [{"device": p.device, "desc": p.description} for p in lp.comports()]
    except Exception:
        return []


async def ws_handler(request):
    st: Station = request.app["station"]
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)
    st.clients.add(ws)
    await ws.send_json({"type": "hello", "ports": list_ports(),
                        "cfg_full": st.cfg})
    try:
        async for msg in ws:
            if msg.type != WSMsgType.TEXT:
                continue
            try:
                m = json.loads(msg.data)
            except json.JSONDecodeError:
                continue
            cmd = m.get("cmd")
            if cmd == "ports":
                await ws.send_json({"type": "ports", "ports": list_ports()})
            elif cmd == "connect":
                st.sources.connect(m["port"], int(m.get("baud", 115200)))
            elif cmd == "disconnect":
                st.sources.disconnect()
                st.log("serial disconnected")
            elif cmd == "sim":
                st.sources.sim(bool(m.get("on")))
            elif cmd == "pursuit":
                st.pursuit = bool(m.get("on"))
                if not st.pursuit:
                    st.pursuit_state = None
                st.log(f"pursuit demo {'on' if st.pursuit else 'off'}")
            elif cmd == "cfg":
                st.update_cfg(m.get("patch", {}))
                await broadcast(st, {"type": "cfg_full", "cfg_full": st.cfg})
            elif cmd == "calibrate":
                st.cal_start(m["node"], m.get("dist", 1.0), m.get("seconds", 15))
            elif cmd == "cal_cancel":
                st.cal = None
                st.log("calibration cancelled")
            elif cmd == "record":
                st.record(bool(m.get("on")))
    finally:
        st.clients.discard(ws)
    return ws


async def api_radar(request):
    """POST /api/radar  {range, az, vel, snr, beams, [x, y, z]} from radar_acquire.py"""
    st: Station = request.app["station"]
    try:
        m = await request.json()
    except Exception:
        return web.json_response({"ok": False, "err": "bad json"}, status=400)
    st.sources.q.put({"radar": m})
    return web.json_response({"ok": True})


async def broadcast(st, payload):
    dead = []
    for ws in st.clients:
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        st.clients.discard(ws)


async def pump(app):
    """Main loop: drain sources, solve, push state to clients."""
    st: Station = app["station"]
    solve_dt = 1.0 / SOLVE_HZ
    last_solve = 0.0
    try:
        while True:
            now = time.time()
            try:
                while True:
                    st.ingest(st.sources.q.get_nowait(), time.time())
            except queue.Empty:
                pass
            if now - last_solve >= solve_dt:
                last_solve = now
                st.solve(now)
                res = st.cal_poll(now)
                if res:
                    await broadcast(st, {"type": "cal_result", **res})
                await broadcast(st, st.state(now))
            await asyncio.sleep(0.02)
    except asyncio.CancelledError:
        pass


async def on_startup(app):
    app["pump"] = asyncio.create_task(pump(app))


async def on_cleanup(app):
    app["pump"].cancel()
    st: Station = app["station"]
    st.record(False)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hub", help="serial port to connect at startup")
    ap.add_argument("--sim", action="store_true", help="start in sim mode")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()

    st = Station()
    if args.hub:
        st.sources.connect(args.hub)
    if args.sim:
        st.sources.sim(True)

    app = web.Application()
    app["station"] = st
    app.router.add_get("/ws", ws_handler)
    app.router.add_post("/api/radar", api_radar)

    async def index(_):
        return web.FileResponse(BASE / "web" / "index.html")
    app.router.add_get("/", index)
    app.router.add_static("/", BASE / "web", show_index=False)

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    st.log(f"ground station on http://{args.host}:{args.port}")
    web.run_app(app, host=args.host, port=args.port, print=None)


if __name__ == "__main__":
    main()
