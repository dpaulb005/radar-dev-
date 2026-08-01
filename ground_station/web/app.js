/* Radar ground station console — WebSocket client + canvas PPI scope. */
"use strict";

const $ = id => document.getElementById(id);
/* Validated categorical order (dark column); drone track = slot 1 blue.
 * Node identity is never color-alone: every marker carries its N# label. */
const NODE_COLORS = ["#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9"];
const TRACK = "#3987e5";

/* ------------------------------------------------------------------ */
/* state                                                              */
/* ------------------------------------------------------------------ */
const S = {
  ws: null,
  connected: false,
  state: null,          // last state message
  cfgFull: null,        // full config incl. node positions
  trail: [],            // [{x,y,t}]
  puTrail: [],          // interceptor trail [{x,y,t}]
  spark: {},            // nodeId -> [{t,rssi}]
  rateWin: [],          // fix timestamps for solver-rate pill
  render: { x: 0, y: 0, has: false },   // interpolated blip
  view: { cx: 0, cy: 0, mpp: 0.02, user: false },  // meters-per-pixel view
  edit: false, sweep: true, sweepA: 0,
  drag: null, mouse: null,
  calArmed: false,
};

/* ------------------------------------------------------------------ */
/* websocket                                                          */
/* ------------------------------------------------------------------ */
function connectWS() {
  const ws = new WebSocket(`ws://${location.host}/ws`);
  S.ws = ws;
  ws.onopen = () => { S.connected = true; };
  ws.onclose = () => {
    S.connected = false;
    setTimeout(connectWS, 1500);
  };
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.type === "hello") { S.cfgFull = m.cfg_full; fillPorts(m.ports); syncCfgInputs(); buildCalNodes(); }
    else if (m.type === "ports") fillPorts(m.ports);
    else if (m.type === "cfg_full") { S.cfgFull = m.cfg_full; syncCfgInputs(); buildCalNodes(); }
    else if (m.type === "cal_result") calResult(m);
    else if (m.type === "state") onState(m);
  };
}
const send = obj => { if (S.ws && S.ws.readyState === 1) S.ws.send(JSON.stringify(obj)); };

function onState(m) {
  S.state = m;
  const now = m.t;
  if (m.fix) {
    const last = S.trail[S.trail.length - 1];
    if (!last || last.t !== m.fix.t) {
      S.trail.push({ x: m.fix.x, y: m.fix.y, t: m.fix.t });
      S.rateWin.push(m.fix.t);
    }
    S.trail = S.trail.filter(p => now - p.t < 12);
    S.rateWin = S.rateWin.filter(t => now - t < 3);
  }
  if (m.pursuit) {
    S.puTrail.push({ x: m.pursuit.i_true[0], y: m.pursuit.i_true[1], t: now });
    S.puTrail = S.puTrail.filter(p => now - p.t < 8);
  } else if (S.puTrail.length) {
    S.puTrail = [];
  }
  for (const [nid, n] of Object.entries(m.nodes)) {
    if (n.rssi != null && n.age != null && n.age < 1.5) {
      const arr = S.spark[nid] = S.spark[nid] || [];
      const last = arr[arr.length - 1];
      if (!last || now - last.t > 0.2) arr.push({ t: now, rssi: n.rssi });
      S.spark[nid] = arr.filter(p => now - p.t < 30);
    }
  }
  updatePanels(m);
}

/* ------------------------------------------------------------------ */
/* panels                                                             */
/* ------------------------------------------------------------------ */
function updatePanels(m) {
  // header pills
  const link = $("pill-link");
  if (m.link.sim)            { link.className = "pill warn"; link.innerHTML = "LINK&nbsp;<b>SIM</b>"; }
  else if (m.link.serial_ok) { link.className = "pill ok";   link.innerHTML = `LINK&nbsp;<b>${m.link.port}</b>`; }
  else if (m.link.port)      { link.className = "pill bad";  link.innerHTML = `LINK&nbsp;<b>RETRY ${m.link.port}</b>`; }
  else                       { link.className = "pill";      link.innerHTML = "LINK&nbsp;<b>OFFLINE</b>"; }

  const fixPill = $("pill-fix");
  if (m.fix) { fixPill.className = "pill ok"; fixPill.innerHTML = `FIX&nbsp;<b>${m.fix.nodes_used} NODES</b>`; }
  else       { fixPill.className = "pill";    fixPill.innerHTML = "FIX&nbsp;<b>NO SOLUTION</b>"; }

  $("pill-rec").classList.toggle("hidden", !m.recording);
  $("btn-record").classList.toggle("on", !!m.recording);
  $("btn-sim").classList.toggle("on", m.link.sim);
  $("btn-pursuit").classList.toggle("on", !!m.pursuit);
  const conn = $("btn-connect");
  conn.textContent = m.link.port ? "Disconnect" : "Connect";
  conn.classList.toggle("on", !!m.link.port);

  // fix tiles
  if (m.fix) {
    $("fx").textContent = m.fix.x.toFixed(1);
    $("fy").textContent = m.fix.y.toFixed(1);
    $("fv").textContent = Math.hypot(m.fix.vx, m.fix.vy).toFixed(1);
    $("fr").textContent = m.fix.resid.toFixed(1);
    $("fn").textContent = `${m.fix.nodes_used} / ${Object.keys(m.nodes).length}`;
  } else {
    for (const id of ["fx", "fy", "fv", "fr"]) $(id).textContent = "—";
    $("fn").textContent = `0 / ${Object.keys(m.nodes).length}`;
  }
  $("frate").textContent = `${(S.rateWin.length / 3).toFixed(1)} Hz`;

  // node cards
  const wrap = $("node-cards");
  const ids = Object.keys(m.nodes).sort((a, b) => +a - +b);
  for (const nid of ids) {
    let card = document.getElementById(`nc-${nid}`);
    if (!card) {
      card = document.createElement("div");
      card.className = "node-card"; card.id = `nc-${nid}`;
      card.innerHTML =
        `<div class="node-id" style="background:${nodeColor(nid)}">${nid}</div>
         <div class="node-main"><b class="nc-rssi">—</b><span>dBm</span>
           <span class="nc-dist"></span><span class="nc-hz"></span></div>
         <div class="node-status lost">LOST</div>
         <canvas class="node-spark" width="220" height="26"></canvas>`;
      wrap.appendChild(card);
    }
    const n = m.nodes[nid];
    card.querySelector(".nc-rssi").textContent = n.rssi != null ? n.rssi.toFixed(0) : "—";
    card.querySelector(".nc-dist").textContent = n.dist != null ? `≈${n.dist.toFixed(1)} m` : "";
    card.querySelector(".nc-hz").textContent = n.hz ? `${n.hz.toFixed(1)}/s` : "";
    const st = card.querySelector(".node-status");
    if (n.age == null || n.age > 2)  { st.className = "node-status lost"; st.textContent = "LOST"; }
    else if (n.age > 0.6)            { st.className = "node-status slow"; st.textContent = "SLOW"; }
    else                             { st.className = "node-status live"; st.textContent = "LIVE"; }
    drawSpark(card.querySelector(".node-spark"), S.spark[nid] || [], nodeColor(nid), m.t);
  }
  for (const card of [...wrap.children])
    if (!ids.includes(card.id.slice(3))) card.remove();

  // calibration progress
  if (m.cal) {
    $("cal-bar").firstElementChild.style.width = `${(m.cal.progress * 100).toFixed(0)}%`;
    $("cal-status").innerHTML =
      `Capturing node <b>${m.cal.node}</b>… <b>${m.cal.n}</b> samples`;
    $("btn-cal").textContent = "Cancel"; $("btn-cal").classList.add("on");
    S.calArmed = true;
  } else if (S.calArmed && !m.cal) {
    $("btn-cal").textContent = "Start"; $("btn-cal").classList.remove("on");
    $("cal-bar").firstElementChild.style.width = "0%";
    S.calArmed = false;
  }

  // log line
  if (m.log && m.log.length) {
    const last = m.log[m.log.length - 1];
    const d = new Date(last.t * 1000);
    $("log").textContent = `${d.toTimeString().slice(0, 8)}  ${last.msg}`;
  }
}

function nodeColor(nid) {
  const i = (parseInt(nid, 10) - 1) % NODE_COLORS.length;
  return NODE_COLORS[i >= 0 ? i : 0];
}

function drawSpark(cv, pts, color, now) {
  const ctx = cv.getContext("2d");
  const w = cv.width, h = cv.height;
  ctx.clearRect(0, 0, w, h);
  if (pts.length < 2) return;
  const rMin = Math.min(...pts.map(p => p.rssi)) - 2;
  const rMax = Math.max(...pts.map(p => p.rssi)) + 2;
  ctx.beginPath();
  for (let i = 0; i < pts.length; i++) {
    const x = w - (now - pts[i].t) / 30 * w;
    const y = h - 3 - (pts[i].rssi - rMin) / (rMax - rMin) * (h - 6);
    i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  }
  ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.lineJoin = "round";
  ctx.stroke();
}

/* ------------------------------------------------------------------ */
/* controls                                                           */
/* ------------------------------------------------------------------ */
function fillPorts(ports) {
  const sel = $("sel-port");
  const cur = sel.value;
  sel.innerHTML = "";
  for (const p of ports) {
    const o = document.createElement("option");
    o.value = p.device; o.textContent = `${p.device} — ${p.desc}`;
    sel.appendChild(o);
  }
  if (!ports.length) {
    const o = document.createElement("option");
    o.value = ""; o.textContent = "no serial ports found";
    sel.appendChild(o);
  }
  if ([...sel.options].some(o => o.value === cur)) sel.value = cur;
}

function syncCfgInputs() {
  if (!S.cfgFull) return;
  $("cfg-n").value = S.cfgFull.path_loss_n;
  $("cfg-z").value = S.cfgFull.drone_z ?? 1.5;
}

function buildCalNodes() {
  if (!S.cfgFull) return;
  const sel = $("cal-node");
  const cur = sel.value;
  sel.innerHTML = "";
  for (const nid of Object.keys(S.cfgFull.nodes).sort((a, b) => +a - +b)) {
    const o = document.createElement("option");
    o.value = nid; o.textContent = `Node ${nid}`;
    sel.appendChild(o);
  }
  if ([...sel.options].some(o => o.value === cur)) sel.value = cur;
}

function calResult(m) {
  if (!m.ok) {
    $("cal-status").innerHTML =
      `<b>No samples.</b> Check drone power, channel, and DRONE_MAC.`;
    return;
  }
  $("cal-status").innerHTML =
    `Node <b>${m.node}</b>: median <b>${m.median}</b> dBm over ${m.n} samples
     → rssi0 <b>${m.rssi0}</b>
     <button id="btn-cal-apply">Apply</button>`;
  $("btn-cal-apply").onclick = () => {
    send({ cmd: "cfg", patch: { nodes: { [m.node]: { rssi0: m.rssi0 } } } });
    $("cal-status").innerHTML = `Node <b>${m.node}</b> rssi0 set to <b>${m.rssi0}</b>. ✓`;
  };
}

function wireControls() {
  $("btn-ports").onclick = () => send({ cmd: "ports" });
  $("btn-connect").onclick = () => {
    if (S.state?.link?.port) send({ cmd: "disconnect" });
    else if ($("sel-port").value) send({ cmd: "connect", port: $("sel-port").value });
  };
  $("btn-sim").onclick = () => send({ cmd: "sim", on: !S.state?.link?.sim });
  $("btn-record").onclick = () => send({ cmd: "record", on: !S.state?.recording });
  $("btn-pursuit").onclick = () => {
    const on = !(S.state && S.state.pursuit);
    if (on && !S.state?.link?.sim) send({ cmd: "sim", on: true });  // demo needs sim
    send({ cmd: "pursuit", on });
  };
  $("btn-cal").onclick = () => {
    if (S.state?.cal) send({ cmd: "cal_cancel" });
    else send({ cmd: "calibrate", node: $("cal-node").value,
                dist: +$("cal-dist").value, seconds: +$("cal-secs").value });
  };
  $("cfg-n").onchange = () => send({ cmd: "cfg", patch: { path_loss_n: +$("cfg-n").value } });
  $("cfg-z").onchange = () => send({ cmd: "cfg", patch: { drone_z: +$("cfg-z").value } });
  $("btn-edit").onclick = () => {
    S.edit = !S.edit;
    $("btn-edit").classList.toggle("on", S.edit);
  };
  $("btn-sweep").onclick = () => {
    S.sweep = !S.sweep;
    $("btn-sweep").classList.toggle("on", S.sweep);
  };
  $("btn-reset").onclick = () => { S.view.user = false; };
  setInterval(() => {
    $("clock").textContent = new Date().toTimeString().slice(0, 8);
  }, 500);
}

/* ------------------------------------------------------------------ */
/* scope rendering                                                    */
/* ------------------------------------------------------------------ */
const scope = $("scope");
const sctx = scope.getContext("2d");
let DPR = 1;

function resize() {
  DPR = window.devicePixelRatio || 1;
  scope.width = scope.clientWidth * DPR;
  scope.height = scope.clientHeight * DPR;
}
window.addEventListener("resize", resize);

function fitView() {
  if (S.view.user || !S.cfgFull) return;
  const pts = Object.values(S.cfgFull.nodes).map(n => n.pos);
  if (S.state?.fix) pts.push([S.state.fix.x, S.state.fix.y, 0]);
  if (!pts.length) return;
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
  const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
  const span = Math.max(Math.max(...xs) - Math.min(...xs),
                        Math.max(...ys) - Math.min(...ys), 6) * 1.45;
  S.view.cx = cx; S.view.cy = cy;
  S.view.mpp = span / Math.min(scope.clientWidth, scope.clientHeight);
}

const W2S = (x, y) => [
  (scope.clientWidth / 2 + (x - S.view.cx) / S.view.mpp) * DPR,
  (scope.clientHeight / 2 - (y - S.view.cy) / S.view.mpp) * DPR,
];
const S2W = (px, py) => [
  S.view.cx + (px - scope.clientWidth / 2) * S.view.mpp,
  S.view.cy - (py - scope.clientHeight / 2) * S.view.mpp,
];

function niceStep(target) {
  const p = Math.pow(10, Math.floor(Math.log10(target)));
  for (const m of [1, 2, 5, 10]) if (m * p >= target) return m * p;
  return 10 * p;
}

function drawScope(tNow) {
  fitView();
  const w = scope.width, h = scope.height;
  sctx.clearRect(0, 0, w, h);
  const cs = getComputedStyle(document.documentElement);
  const C = n => cs.getPropertyValue(n).trim();

  // --- cartesian grid (1 m-ish) ---
  const step = niceStep(40 * S.view.mpp);   // ≥40 px between lines
  sctx.strokeStyle = C("--grid"); sctx.lineWidth = 1;
  const [x0, y1] = S2W(0, 0), [x1, y0] = S2W(scope.clientWidth, scope.clientHeight);
  sctx.beginPath();
  for (let x = Math.ceil(x0 / step) * step; x <= x1; x += step) {
    const [px] = W2S(x, 0); sctx.moveTo(px, 0); sctx.lineTo(px, h);
  }
  for (let y = Math.ceil(y0 / step) * step; y <= y1; y += step) {
    const [, py] = W2S(0, y); sctx.moveTo(0, py); sctx.lineTo(w, py);
  }
  sctx.stroke();

  // --- range rings centred on node centroid ---
  if (S.cfgFull && Object.keys(S.cfgFull.nodes).length) {
    const poss = Object.values(S.cfgFull.nodes).map(n => n.pos);
    const rcx = poss.reduce((s, p) => s + p[0], 0) / poss.length;
    const rcy = poss.reduce((s, p) => s + p[1], 0) / poss.length;
    const [pcx, pcy] = W2S(rcx, rcy);
    const ringStep = niceStep(70 * S.view.mpp);
    sctx.strokeStyle = C("--baseline");
    sctx.fillStyle = C("--ink-muted");
    sctx.font = `${10 * DPR}px ${C("--font") || "system-ui"}`;
    for (let r = ringStep; r <= ringStep * 6; r += ringStep) {
      sctx.beginPath();
      sctx.arc(pcx, pcy, r / S.view.mpp * DPR, 0, Math.PI * 2);
      sctx.stroke();
      sctx.fillText(`${r} m`, pcx + 4 * DPR, pcy - r / S.view.mpp * DPR - 4 * DPR);
    }

    // --- sweep (cosmetic phosphor wedge) ---
    if (S.sweep) {
      S.sweepA = (tNow / 2400) % (Math.PI * 2);
      const rMax = ringStep * 6 / S.view.mpp * DPR;
      const g = sctx.createConicGradient
        ? sctx.createConicGradient(-S.sweepA, pcx, pcy) : null;
      if (g) {
        g.addColorStop(0, "rgba(57,135,229,0.16)");
        g.addColorStop(0.10, "rgba(57,135,229,0)");
        g.addColorStop(1, "rgba(57,135,229,0)");
        sctx.fillStyle = g;
        sctx.beginPath();
        sctx.moveTo(pcx, pcy);
        sctx.arc(pcx, pcy, rMax, 0, Math.PI * 2);
        sctx.fill();
      }
    }
  }

  // --- nodes ---
  if (S.cfgFull) {
    for (const [nid, n] of Object.entries(S.cfgFull.nodes)) {
      const [px, py] = W2S(n.pos[0], n.pos[1]);
      const col = nodeColor(nid);
      const live = S.state?.nodes?.[nid]?.age != null && S.state.nodes[nid].age < 2;

      // measured-distance circle (dashed, node color, faint)
      const nd = S.state?.nodes?.[nid];
      if (live && nd.dist != null && nd.dist / S.view.mpp < 4000) {
        sctx.setLineDash([4 * DPR, 6 * DPR]);
        sctx.strokeStyle = col; sctx.globalAlpha = 0.35; sctx.lineWidth = 1 * DPR;
        sctx.beginPath();
        sctx.arc(px, py, nd.dist / S.view.mpp * DPR, 0, Math.PI * 2);
        sctx.stroke();
        sctx.setLineDash([]); sctx.globalAlpha = 1;
      }

      sctx.fillStyle = col;
      sctx.beginPath();               // triangle marker
      const s = 7 * DPR;
      sctx.moveTo(px, py - s); sctx.lineTo(px + s, py + s); sctx.lineTo(px - s, py + s);
      sctx.closePath(); sctx.fill();
      if (!live) {                    // hollow it out when lost
        sctx.fillStyle = C("--page");
        sctx.beginPath();
        sctx.moveTo(px, py - s + 3 * DPR); sctx.lineTo(px + s - 3 * DPR, py + s - 2 * DPR);
        sctx.lineTo(px - s + 3 * DPR, py + s - 2 * DPR); sctx.closePath(); sctx.fill();
      }
      sctx.fillStyle = C("--ink-2");
      sctx.font = `600 ${11 * DPR}px system-ui`;
      sctx.fillText(`N${nid}`, px + 10 * DPR, py + 4 * DPR);
    }
  }

  // --- ground truth (sim only) ---
  if (S.state?.true) {
    const [px, py] = W2S(S.state.true[0], S.state.true[1]);
    sctx.strokeStyle = C("--ink-muted");
    sctx.setLineDash([3 * DPR, 4 * DPR]);
    sctx.beginPath(); sctx.arc(px, py, 8 * DPR, 0, Math.PI * 2); sctx.stroke();
    sctx.setLineDash([]);
  }

  // --- trail (phosphor persistence) + blip ---
  if (S.state?.fix) {
    const f = S.state.fix;
    if (!S.render.has) { S.render.x = f.x; S.render.y = f.y; S.render.has = true; }
    S.render.x += (f.x - S.render.x) * 0.12;   // interpolate toward fix
    S.render.y += (f.y - S.render.y) * 0.12;

    for (const p of S.trail) {
      const a = Math.max(0, 1 - (S.state.t - p.t) / 12);
      const [px, py] = W2S(p.x, p.y);
      sctx.fillStyle = TRACK; sctx.globalAlpha = 0.45 * a * a;
      sctx.beginPath(); sctx.arc(px, py, 2.5 * DPR, 0, Math.PI * 2); sctx.fill();
    }
    sctx.globalAlpha = 1;

    const [bx, by] = W2S(S.render.x, S.render.y);
    // uncertainty halo from residual
    const rpx = Math.max(10 * DPR, (f.resid || 0.5) / S.view.mpp * DPR);
    const halo = sctx.createRadialGradient(bx, by, 0, bx, by, rpx);
    halo.addColorStop(0, "rgba(57,135,229,0.25)");
    halo.addColorStop(1, "rgba(57,135,229,0)");
    sctx.fillStyle = halo;
    sctx.beginPath(); sctx.arc(bx, by, rpx, 0, Math.PI * 2); sctx.fill();

    // velocity vector (1 s lookahead)
    const sp = Math.hypot(f.vx, f.vy);
    if (sp > 0.3) {
      const [ex, ey] = W2S(S.render.x + f.vx, S.render.y + f.vy);
      sctx.strokeStyle = TRACK; sctx.lineWidth = 2 * DPR;
      sctx.beginPath(); sctx.moveTo(bx, by); sctx.lineTo(ex, ey); sctx.stroke();
    }

    sctx.fillStyle = TRACK;
    sctx.beginPath(); sctx.arc(bx, by, 6 * DPR, 0, Math.PI * 2); sctx.fill();
    sctx.strokeStyle = C("--page"); sctx.lineWidth = 2 * DPR;   // surface ring
    sctx.stroke();

    sctx.fillStyle = C("--ink");
    sctx.font = `600 ${11 * DPR}px system-ui`;
    sctx.fillText("DRONE", bx + 10 * DPR, by - 8 * DPR);
  } else {
    S.render.has = false;
  }

  // --- pursuit demo: interceptor blip + intercept line ---
  if (S.state?.pursuit) {
    const pu = S.state.pursuit;
    const tgt = S.state.true || (S.state.fix ? [S.state.fix.x, S.state.fix.y] : pu.t_est);
    const [ix, iy] = W2S(pu.i_true[0], pu.i_true[1]);
    const [tx, ty] = W2S(tgt[0], tgt[1]);
    const GREEN = "#0ca30c";

    sctx.strokeStyle = GREEN; sctx.globalAlpha = 0.7; sctx.lineWidth = 1.5 * DPR;
    sctx.setLineDash([5 * DPR, 5 * DPR]);
    sctx.beginPath(); sctx.moveTo(ix, iy); sctx.lineTo(tx, ty); sctx.stroke();
    sctx.setLineDash([]); sctx.globalAlpha = 1;

    for (const p of S.puTrail) {
      const a = Math.max(0, 1 - (S.state.t - p.t) / 8);
      const [px, py] = W2S(p.x, p.y);
      sctx.fillStyle = GREEN; sctx.globalAlpha = 0.4 * a * a;
      sctx.beginPath(); sctx.arc(px, py, 2.3 * DPR, 0, Math.PI * 2); sctx.fill();
    }
    sctx.globalAlpha = 1;

    const s = 6 * DPR;                       // interceptor diamond
    sctx.fillStyle = GREEN;
    sctx.beginPath();
    sctx.moveTo(ix, iy - s); sctx.lineTo(ix + s, iy);
    sctx.lineTo(ix, iy + s); sctx.lineTo(ix - s, iy); sctx.closePath();
    sctx.fill();
    sctx.strokeStyle = C("--page"); sctx.lineWidth = 2 * DPR; sctx.stroke();
    sctx.fillStyle = C("--ink"); sctx.font = `600 ${11 * DPR}px system-ui`;
    sctx.fillText("INTERCEPTOR", ix + 9 * DPR, iy + 4 * DPR);

    sctx.fillStyle = GREEN; sctx.font = `600 ${11 * DPR}px system-ui`;
    sctx.fillText(`${pu.range.toFixed(1)} m`, (ix + tx) / 2 + 4 * DPR, (iy + ty) / 2 - 4 * DPR);

    sctx.fillStyle = C("--ink-2"); sctx.font = `${12 * DPR}px system-ui`;
    sctx.textAlign = "center";
    sctx.fillText(`PURSUIT  ·  range ${pu.range.toFixed(1)} m  ·  interceptor ${pu.speed.toFixed(1)} m/s`,
                  w / 2, 24 * DPR);
    sctx.textAlign = "left";
  }

  requestAnimationFrame(drawScope);
}

/* ------------------------------------------------------------------ */
/* scope interaction: pan / zoom / node drag                          */
/* ------------------------------------------------------------------ */
function wireScope() {
  scope.addEventListener("wheel", ev => {
    ev.preventDefault();
    const k = ev.deltaY > 0 ? 1.15 : 1 / 1.15;
    S.view.mpp = Math.min(1, Math.max(0.002, S.view.mpp * k));
    S.view.user = true;
  }, { passive: false });

  scope.addEventListener("pointerdown", ev => {
    const rect = scope.getBoundingClientRect();
    const px = ev.clientX - rect.left, py = ev.clientY - rect.top;
    if (S.edit && S.cfgFull) {
      for (const [nid, n] of Object.entries(S.cfgFull.nodes)) {
        const [nx, ny] = W2S(n.pos[0], n.pos[1]);
        if (Math.hypot(nx / DPR - px, ny / DPR - py) < 14) {
          S.drag = { node: nid }; scope.setPointerCapture(ev.pointerId); return;
        }
      }
    }
    S.drag = { pan: true, px, py, cx: S.view.cx, cy: S.view.cy };
    scope.setPointerCapture(ev.pointerId);
  });

  scope.addEventListener("pointermove", ev => {
    const rect = scope.getBoundingClientRect();
    const px = ev.clientX - rect.left, py = ev.clientY - rect.top;
    const [wx, wy] = S2W(px, py);
    $("scope-readout").textContent =
      `${wx.toFixed(1)}, ${wy.toFixed(1)} m` + (S.edit ? "  ·  EDIT MODE: drag nodes" : "");
    if (!S.drag) return;
    if (S.drag.node) {
      const n = S.cfgFull.nodes[S.drag.node];
      n.pos[0] = Math.round(wx * 10) / 10; n.pos[1] = Math.round(wy * 10) / 10;
    } else if (S.drag.pan) {
      S.view.cx = S.drag.cx - (px - S.drag.px) * S.view.mpp;
      S.view.cy = S.drag.cy + (py - S.drag.py) * S.view.mpp;
      S.view.user = true;
    }
  });

  scope.addEventListener("pointerup", () => {
    if (S.drag?.node) {
      const nid = S.drag.node, n = S.cfgFull.nodes[nid];
      send({ cmd: "cfg", patch: { nodes: { [nid]: { pos: n.pos } } } });
    }
    S.drag = null;
  });

  scope.addEventListener("dblclick", () => { S.view.user = false; });
}

/* ------------------------------------------------------------------ */
resize();
wireControls();
wireScope();
connectWS();
requestAnimationFrame(drawScope);
