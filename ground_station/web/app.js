/* app.js — stage-1 radar console.
 *
 * Stage 1 is one TX horn and one RX horn: the radar measures RANGE and
 * RADIAL VELOCITY. There is no azimuth, so there is no plan view here and
 * nothing in this file draws a bearing.
 *
 * Data in:
 *   GET  /api/state    snapshot (waterfall + track history, no RD map)
 *   GET  /api/stream   Server-Sent Events, one per block (RD map included)
 * Polling of /api/state takes over automatically if the stream drops.
 *
 * No frameworks, no CDN, no build step. Canvas only.
 */
'use strict';

/* ------------------------------------------------------------------ *
 * constants + tiny helpers
 * ------------------------------------------------------------------ */

const WF_ROWS_MAX = 900;      // client-side cap on waterfall history
const TRK_MAX = 1500;         // client-side cap on track history points
const TRK_WINDOW_S = 120;     // track chart time window (s)
const WF_DYN_DB = 50;         // waterfall display dynamic range (dB)

const $ = (id) => document.getElementById(id);
const clamp = (v, a, b) => (v < a ? a : (v > b ? b : v));
const fmt = (v, n) => (v === null || v === undefined || !isFinite(v))
  ? '--' : Number(v).toFixed(n);

function b64bytes(s) {
  const bin = atob(s);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

/* "inferno"-style LUT: dark -> magenta -> orange -> pale yellow.
 * Perceptually monotone, reads as magnitude on a dark instrument panel. */
const LUT = (function () {
  const stops = [[0, 0, 4], [18, 11, 53], [58, 9, 99], [106, 23, 110],
                 [151, 41, 93], [196, 60, 66], [229, 93, 31], [247, 143, 8],
                 [252, 199, 48], [252, 255, 164]];
  const lut = new Uint8Array(256 * 3);
  for (let i = 0; i < 256; i++) {
    const f = i / 255 * (stops.length - 1);
    const k = Math.min(stops.length - 2, Math.floor(f));
    const t = f - k, a = stops[k], b = stops[k + 1];
    lut[i * 3] = a[0] + (b[0] - a[0]) * t;
    lut[i * 3 + 1] = a[1] + (b[1] - a[1]) * t;
    lut[i * 3 + 2] = a[2] + (b[2] - a[2]) * t;
  }
  return lut;
})();

function niceTicks(lo, hi, target) {
  if (!isFinite(lo) || !isFinite(hi) || hi <= lo) return [];
  const raw = (hi - lo) / Math.max(1, target);
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  let step = mag;
  for (const m of [1, 2, 2.5, 5, 10]) { step = m * mag; if (step >= raw) break; }
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-6; v += step) {
    out.push(Math.abs(v) < step * 1e-6 ? 0 : v);
  }
  return out;
}

function tickLabel(v, step) {
  const d = step < 0.1 ? 2 : (step < 1 ? 1 : 0);
  return v.toFixed(d);
}

/* ------------------------------------------------------------------ *
 * client state
 * ------------------------------------------------------------------ */

const S = {
  map: null,          // {nv, nr, data, axes, lo, hi, img}
  radar: null,        // latest block (map stripped for our purposes)
  stats: null,
  track: null,        // latest track summary from the server
  trackHist: [],      // [{t, r, v, sr, rm, vm, coast}]
  wf: { rows: [], n_r: 0, r0: 0, dr: 1, kind: '' },
  floor: 0.35,        // dB-floor gate on the heatmap colour scale
  hold: false,
  link: 'init',
  lastBlockMs: 0,
  staleS: 3.0,
};

const dirty = { rd: true, wf: true, trk: true };
let rafPending = false;

function mark(what) {
  if (what) dirty[what] = true;
  else { dirty.rd = dirty.wf = dirty.trk = true; }
  if (!rafPending) {
    rafPending = true;
    requestAnimationFrame(render);
  }
}

function render() {
  rafPending = false;
  if (S.hold) return;
  try {
    if (dirty.rd) { dirty.rd = false; drawRD(); }
    if (dirty.wf) { dirty.wf = false; drawWF(); }
    if (dirty.trk) { dirty.trk = false; drawTRK(); }
  } catch (e) {
    console.error('draw failed', e);
  }
}

/* ------------------------------------------------------------------ *
 * canvas plumbing
 * ------------------------------------------------------------------ */

function surface(canvas) {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = Math.max(1, Math.round(canvas.clientWidth));
  const h = Math.max(1, Math.round(canvas.clientHeight));
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
  }
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = '#05080b';
  ctx.fillRect(0, 0, w, h);
  return { ctx, w, h };
}

function axisFrame(ctx, L, T, pw, ph) {
  ctx.strokeStyle = '#22303d';
  ctx.lineWidth = 1;
  ctx.strokeRect(L + 0.5, T + 0.5, pw, ph);
}

function label(ctx, text, x, y, align, colour, size) {
  ctx.fillStyle = colour || '#7c8fa1';
  ctx.font = (size || 10) + 'px "DejaVu Sans Mono", monospace';
  ctx.textAlign = align || 'left';
  ctx.fillText(text, x, y);
}

/* ------------------------------------------------------------------ *
 * 1. range-Doppler heatmap
 * ------------------------------------------------------------------ */

function mapImage(m) {
  /* Build an offscreen n_r x n_v image, velocity increasing upward, with the
   * dB-floor gate applied to the colour scale. Cached until the gate or the
   * map changes. */
  if (m.img && m.imgFloor === S.floor) return m.img;
  const cv = document.createElement('canvas');
  cv.width = m.nr; cv.height = m.nv;
  const ctx = cv.getContext('2d');
  const img = ctx.createImageData(m.nr, m.nv);
  const px = img.data;
  const g0 = S.floor * 255, span = Math.max(1, 255 - g0);
  for (let iv = 0; iv < m.nv; iv++) {
    const dstRow = (m.nv - 1 - iv) * m.nr;      // row 0 = most negative v
    const srcRow = iv * m.nr;
    for (let ir = 0; ir < m.nr; ir++) {
      let u = (m.data[srcRow + ir] - g0) / span;
      u = u < 0 ? 0 : (u > 1 ? 1 : u);
      const c = (u * 255) | 0;
      const o = (dstRow + ir) * 4;
      px[o] = LUT[c * 3]; px[o + 1] = LUT[c * 3 + 1];
      px[o + 2] = LUT[c * 3 + 2]; px[o + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  m.img = cv; m.imgFloor = S.floor;
  return cv;
}

function drawRD() {
  const { ctx, w, h } = surface($('rd'));
  const m = S.map;
  const msg = $('rd-msg');
  if (!m) {
    msg.hidden = false;
    msg.textContent = S.radar
      ? 'no range-Doppler map in the stream — run radar_acquire.py with --map'
      : 'waiting for a block on POST /api/radar …';
    return;
  }
  msg.hidden = true;

  const L = 54, R = 78, T = 12, B = 36;
  const pw = Math.max(10, w - L - R), ph = Math.max(10, h - T - B);
  const ax = m.axes || { r0: 0, dr: 1, v0: 0, dv: 0 };
  const rMin = ax.r0 - ax.dr * 0.5, rMax = ax.r0 + ax.dr * (m.nr - 0.5);
  const vMin = ax.v0 - ax.dv * 0.5, vMax = ax.v0 + ax.dv * (m.nv - 0.5);
  const xOf = (r) => L + (r - rMin) / (rMax - rMin) * pw;
  const yOf = (v) => T + ph - (v - vMin) / (vMax - vMin) * ph;

  ctx.imageSmoothingEnabled = true;
  ctx.drawImage(mapImage(m), L, T, pw, ph);

  /* grid + ticks */
  const rt = niceTicks(Math.max(0, rMin), rMax, 6);
  const rStep = rt.length > 1 ? rt[1] - rt[0] : 1;
  ctx.save();
  ctx.beginPath(); ctx.rect(L, T, pw, ph); ctx.clip();
  ctx.strokeStyle = 'rgba(170,200,225,.13)'; ctx.lineWidth = 1;
  for (const r of rt) {
    const x = Math.round(xOf(r)) + 0.5;
    ctx.beginPath(); ctx.moveTo(x, T); ctx.lineTo(x, T + ph); ctx.stroke();
  }
  const vt = ax.dv > 0 ? niceTicks(vMin, vMax, 6) : [];
  for (const v of vt) {
    const y = Math.round(yOf(v)) + 0.5;
    ctx.beginPath(); ctx.moveTo(L, y); ctx.lineTo(L + pw, y); ctx.stroke();
  }
  /* zero-Doppler line: clutter and TX leakage live here */
  if (ax.dv > 0 && vMin < 0 && vMax > 0) {
    ctx.strokeStyle = 'rgba(200,225,255,.45)';
    ctx.setLineDash([5, 4]);
    const y0 = Math.round(yOf(0)) + 0.5;
    ctx.beginPath(); ctx.moveTo(L, y0); ctx.lineTo(L + pw, y0); ctx.stroke();
    ctx.setLineDash([]);
  }

  /* CFAR detections */
  const dets = (S.radar && S.radar.dets) || [];
  for (let i = 0; i < dets.length; i++) {
    const d = dets[i];
    const x = xOf(d.range), y = ax.dv > 0 ? yOf(d.vel) : T + ph / 2;
    if (x < L - 6 || x > L + pw + 6) continue;
    const best = i === 0;
    ctx.strokeStyle = best ? '#7dfff0' : 'rgba(125,255,240,.55)';
    ctx.lineWidth = best ? 1.8 : 1.2;
    ctx.beginPath(); ctx.arc(x, y, best ? 9 : 6, 0, Math.PI * 2); ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(x - 13, y); ctx.lineTo(x - 4, y);
    ctx.moveTo(x + 4, y); ctx.lineTo(x + 13, y);
    ctx.stroke();
    if (best) {
      label(ctx, d.range.toFixed(2) + ' m  ' + d.vel.toFixed(2) + ' m/s  ' +
            d.snr.toFixed(1) + ' dB',
            clamp(x + 13, L + 2, L + pw - 150), clamp(y - 11, T + 11, T + ph - 4),
            'left', '#bdfff6', 10.5);
    }
  }
  /* Kalman track position on the same map */
  if (S.track && S.track.valid && ax.dv > 0) {
    const x = xOf(S.track.range_m), y = yOf(S.track.vel_ms);
    ctx.strokeStyle = '#37d7c4'; ctx.lineWidth = 1.4;
    ctx.beginPath();
    ctx.moveTo(x - 7, y - 7); ctx.lineTo(x + 7, y + 7);
    ctx.moveTo(x - 7, y + 7); ctx.lineTo(x + 7, y - 7);
    ctx.stroke();
  }
  ctx.restore();
  axisFrame(ctx, L, T, pw, ph);

  for (const r of rt) {
    const x = xOf(r);
    if (x < L - 1 || x > L + pw + 1) continue;
    ctx.strokeStyle = '#39495a';
    ctx.beginPath(); ctx.moveTo(x, T + ph); ctx.lineTo(x, T + ph + 4); ctx.stroke();
    label(ctx, tickLabel(r, rStep), x, T + ph + 15, 'center');
  }
  label(ctx, 'range (m)', L + pw / 2, T + ph + 30, 'center', '#9fb4c6', 11);
  const vStep = vt.length > 1 ? vt[1] - vt[0] : 1;
  for (const v of vt) {
    const y = yOf(v);
    label(ctx, tickLabel(v, vStep), L - 6, y + 3.5, 'right');
  }
  ctx.save();
  ctx.translate(12, T + ph / 2); ctx.rotate(-Math.PI / 2);
  label(ctx, ax.dv > 0 ? 'radial velocity (m/s)   [-] closing'
                       : 'velocity axis unavailable', 0, 0, 'center', '#9fb4c6', 11);
  ctx.restore();

  /* colour bar, labelled in dB */
  const cbX = L + pw + 20, cbW = 13, cbT = T + 4, cbH = ph - 8;
  const lo = m.lo + S.floor * (m.hi - m.lo), hi = m.hi;
  for (let i = 0; i < cbH; i++) {
    const c = clamp(Math.round((1 - i / (cbH - 1)) * 255), 0, 255);
    ctx.fillStyle = 'rgb(' + LUT[c * 3] + ',' + LUT[c * 3 + 1] + ',' + LUT[c * 3 + 2] + ')';
    ctx.fillRect(cbX, cbT + i, cbW, 1);
  }
  ctx.strokeStyle = '#39495a';
  ctx.strokeRect(cbX + 0.5, cbT + 0.5, cbW, cbH);
  const ct = niceTicks(lo, hi, 4);
  const cStep = ct.length > 1 ? ct[1] - ct[0] : 1;
  for (const d of ct) {
    const y = cbT + cbH - (d - lo) / (hi - lo) * cbH;
    ctx.strokeStyle = '#39495a';
    ctx.beginPath(); ctx.moveTo(cbX + cbW, y); ctx.lineTo(cbX + cbW + 3, y); ctx.stroke();
    label(ctx, tickLabel(d, cStep), cbX + cbW + 5, y + 3.5, 'left');
  }
  label(ctx, 'dB', cbX + cbW / 2, cbT - 3, 'center', '#9fb4c6', 10);
  $('rd-floor-val').textContent = fmt(lo, 0) + ' dB';
  $('rd-hint').textContent = 'magnitude dB · ' + m.nv + ' Doppler × ' +
    m.nr + ' range bins · Δr ' + fmt(ax.dr, 2) + ' m, Δv ' +
    fmt(ax.dv, 3) + ' m/s';
}

/* ------------------------------------------------------------------ *
 * 2. range vs time waterfall
 * ------------------------------------------------------------------ */

function drawWF() {
  const { ctx, w, h } = surface($('wf'));
  const wf = S.wf, rows = wf.rows, msg = $('wf-msg');
  if (!rows.length || !wf.n_r) {
    msg.hidden = false;
    msg.textContent = 'waiting for blocks …';
    return;
  }
  msg.hidden = true;

  const L = 54, R = 16, T = 12, B = 36;
  const pw = Math.max(10, w - L - R), ph = Math.max(10, h - T - B);
  const n = rows.length, nr = wf.n_r;

  let hi = -Infinity, lo = Infinity;
  for (const row of rows) {
    const d = row.db;
    for (let i = 0; i < d.length; i++) {
      if (d[i] > hi) hi = d[i];
      if (d[i] < lo) lo = d[i];
    }
  }
  if (!isFinite(hi)) { hi = 1; lo = 0; }
  lo = Math.max(lo, hi - WF_DYN_DB);
  const span = Math.max(hi - lo, 1e-6);

  const cv = document.createElement('canvas');
  cv.width = nr; cv.height = n;
  const ictx = cv.getContext('2d');
  const img = ictx.createImageData(nr, n);
  const px = img.data;
  for (let k = 0; k < n; k++) {              // row 0 = oldest, drawn at top
    const d = rows[k].db;
    const base = k * nr * 4;
    for (let i = 0; i < nr; i++) {
      const c = clamp(Math.round((d[i] - lo) / span * 255), 0, 255);
      const o = base + i * 4;
      px[o] = LUT[c * 3]; px[o + 1] = LUT[c * 3 + 1];
      px[o + 2] = LUT[c * 3 + 2]; px[o + 3] = 255;
    }
  }
  ictx.putImageData(img, 0, 0);
  ctx.imageSmoothingEnabled = true;
  ctx.drawImage(cv, L, T, pw, ph);

  const rMin = wf.r0 - wf.dr * 0.5, rMax = wf.r0 + wf.dr * (nr - 0.5);
  const xOf = (r) => L + (r - rMin) / (rMax - rMin) * pw;
  const yOfIdx = (k) => T + (k + 0.5) / n * ph;
  const tNow = rows[n - 1].t;

  /* Kalman range track drawn over the history it came from */
  const hist = S.trackHist;
  if (hist.length > 1) {
    ctx.save();
    ctx.beginPath(); ctx.rect(L, T, pw, ph); ctx.clip();
    ctx.strokeStyle = '#37d7c4'; ctx.lineWidth = 1.4;
    ctx.beginPath();
    let started = false;
    for (const p of hist) {
      if (p.t < rows[0].t - 1 || p.t > tNow + 1) { started = false; continue; }
      const k = idxForTime(rows, p.t);
      const x = xOf(p.r), y = yOfIdx(k);
      if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
    }
    ctx.stroke();
    ctx.restore();
  }
  axisFrame(ctx, L, T, pw, ph);

  const rt = niceTicks(Math.max(0, rMin), rMax, 6);
  const rStep = rt.length > 1 ? rt[1] - rt[0] : 1;
  ctx.save();
  ctx.beginPath(); ctx.rect(L, T, pw, ph); ctx.clip();
  ctx.strokeStyle = 'rgba(170,200,225,.10)';
  for (const r of rt) {
    const x = Math.round(xOf(r)) + 0.5;
    ctx.beginPath(); ctx.moveTo(x, T); ctx.lineTo(x, T + ph); ctx.stroke();
  }
  ctx.restore();
  for (const r of rt) {
    const x = xOf(r);
    if (x < L - 1 || x > L + pw + 1) continue;
    ctx.strokeStyle = '#39495a';
    ctx.beginPath(); ctx.moveTo(x, T + ph); ctx.lineTo(x, T + ph + 4); ctx.stroke();
    label(ctx, tickLabel(r, rStep), x, T + ph + 15, 'center');
  }
  label(ctx, 'range (m)', L + pw / 2, T + ph + 30, 'center', '#9fb4c6', 11);

  const nTicks = Math.min(6, n);
  for (let i = 0; i < nTicks; i++) {
    const k = Math.round(i / Math.max(1, nTicks - 1) * (n - 1));
    const y = yOfIdx(k);
    const age = tNow - rows[k].t;
    ctx.strokeStyle = '#39495a';
    ctx.beginPath(); ctx.moveTo(L - 4, y); ctx.lineTo(L, y); ctx.stroke();
    label(ctx, (age <= 0.05 ? 'now' : '-' + age.toFixed(age < 10 ? 1 : 0)),
          L - 6, y + 3.5, 'right');
  }
  ctx.save();
  ctx.translate(12, T + ph / 2); ctx.rotate(-Math.PI / 2);
  label(ctx, 'time (s, newest at bottom)', 0, 0, 'center', '#9fb4c6', 11);
  ctx.restore();

  $('wf-span').textContent = 'history ' + (tNow - rows[0].t).toFixed(0) + ' s · ' +
    n + ' blocks · ' + fmt(lo, 0) + ' to ' + fmt(hi, 0) + ' dB';
  $('wf-hint').textContent = wf.kind === 'dets'
    ? 'detections only (no --map): SNR in dB'
    : 'peak magnitude over all Doppler, dB';
}

function idxForTime(rows, t) {
  let lo = 0, hi = rows.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (rows[mid].t < t) lo = mid + 1; else hi = mid;
  }
  return lo;
}

/* ------------------------------------------------------------------ *
 * 4. track chart (range + radial velocity vs time)
 * ------------------------------------------------------------------ */

function drawTRK() {
  const { ctx, w, h } = surface($('trk'));
  const hist = S.trackHist;
  const L = 46, R = 50, T = 14, B = 28;
  const pw = Math.max(10, w - L - R), ph = Math.max(10, h - T - B);
  axisFrame(ctx, L, T, pw, ph);
  if (hist.length < 2) {
    label(ctx, 'no track yet', L + pw / 2, T + ph / 2, 'center', '#546579', 11);
    return;
  }
  const tEnd = hist[hist.length - 1].t;
  const tStart = Math.max(hist[0].t, tEnd - TRK_WINDOW_S);
  const pts = hist.filter((p) => p.t >= tStart);
  if (pts.length < 2) return;

  let rMax = 1, vAbs = 0.5;
  for (const p of pts) {
    rMax = Math.max(rMax, p.r + (p.sr || 0), p.rm || 0);
    vAbs = Math.max(vAbs, Math.abs(p.v), Math.abs(p.vm || 0));
  }
  rMax = Math.ceil(rMax * 1.1);
  vAbs = Math.ceil(vAbs * 1.25 * 10) / 10;

  const xOf = (t) => L + (t - tStart) / Math.max(1e-6, tEnd - tStart) * pw;
  const yR = (r) => T + ph - clamp(r / rMax, 0, 1) * ph;
  const yV = (v) => T + ph / 2 - clamp(v / vAbs, -1, 1) * ph / 2;

  /* grid: range on the left scale */
  const rt = niceTicks(0, rMax, 4);
  const rStep = rt.length > 1 ? rt[1] - rt[0] : 1;
  ctx.strokeStyle = 'rgba(170,200,225,.10)';
  for (const r of rt) {
    const y = Math.round(yR(r)) + 0.5;
    ctx.beginPath(); ctx.moveTo(L, y); ctx.lineTo(L + pw, y); ctx.stroke();
    label(ctx, tickLabel(r, rStep), L - 5, y + 3.5, 'right', '#37d7c4');
  }
  const tt = niceTicks(tStart, tEnd, 4);
  for (const t of tt) {
    const x = Math.round(xOf(t)) + 0.5;
    ctx.strokeStyle = 'rgba(170,200,225,.08)';
    ctx.beginPath(); ctx.moveTo(x, T); ctx.lineTo(x, T + ph); ctx.stroke();
    label(ctx, '-' + (tEnd - t).toFixed(0), x, T + ph + 14, 'center');
  }
  label(ctx, 'time (s ago)', L + pw / 2, T + ph + 25, 'center', '#9fb4c6', 10.5);

  /* zero velocity on the right scale */
  ctx.strokeStyle = 'rgba(255,179,71,.35)';
  ctx.setLineDash([4, 4]);
  const y0 = Math.round(yV(0)) + 0.5;
  ctx.beginPath(); ctx.moveTo(L, y0); ctx.lineTo(L + pw, y0); ctx.stroke();
  ctx.setLineDash([]);
  for (const v of niceTicks(-vAbs, vAbs, 4)) {
    label(ctx, v.toFixed(1), L + pw + 5, yV(v) + 3.5, 'left', '#ffb347');
  }

  ctx.save();
  ctx.beginPath(); ctx.rect(L, T, pw, ph); ctx.clip();

  /* +/-1 sigma range band */
  ctx.fillStyle = 'rgba(55,215,196,.16)';
  ctx.beginPath();
  for (let i = 0; i < pts.length; i++) {
    const p = pts[i];
    const x = xOf(p.t), y = yR(p.r + (p.sr || 0));
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  }
  for (let i = pts.length - 1; i >= 0; i--) {
    const p = pts[i];
    ctx.lineTo(xOf(p.t), yR(Math.max(0, p.r - (p.sr || 0))));
  }
  ctx.closePath(); ctx.fill();

  /* raw range measurements, faint */
  ctx.fillStyle = 'rgba(200,225,235,.45)';
  for (const p of pts) {
    if (p.rm === null || p.rm === undefined) continue;
    ctx.fillRect(xOf(p.t) - 0.8, yR(p.rm) - 0.8, 1.8, 1.8);
  }
  /* range track */
  ctx.strokeStyle = '#37d7c4'; ctx.lineWidth = 1.6;
  ctx.beginPath();
  pts.forEach((p, i) => { const x = xOf(p.t), y = yR(p.r); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
  ctx.stroke();
  /* velocity track */
  ctx.strokeStyle = '#ffb347'; ctx.lineWidth = 1.3;
  ctx.beginPath();
  pts.forEach((p, i) => { const x = xOf(p.t), y = yV(p.v); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
  ctx.stroke();
  /* coasting blocks (no detection): tick marks along the bottom */
  ctx.fillStyle = 'rgba(255,91,91,.8)';
  for (const p of pts) if (p.coast) ctx.fillRect(xOf(p.t) - 0.5, T + ph - 5, 1.4, 5);
  ctx.restore();

  label(ctx, 'range (m)', L + 4, T + 11, 'left', '#37d7c4', 10.5);
  label(ctx, 'radial velocity (m/s)', L + pw - 4, T + 11, 'right', '#ffb347', 10.5);
}

/* ------------------------------------------------------------------ *
 * 3. detections table + header/readout text
 * ------------------------------------------------------------------ */

function drawDets() {
  const tb = $('dets').tBodies[0];
  const dets = (S.radar && S.radar.dets) || [];
  if (!dets.length) {
    tb.innerHTML = '<tr class="empty"><td colspan="5">no detections in the last block</td></tr>';
  } else {
    const top = Math.max.apply(null, dets.map((d) => d.snr));
    let html = '';
    dets.forEach((d, i) => {
      const sense = d.vel < -0.15 ? ['closing', 'closing']
        : (d.vel > 0.15 ? ['opening', 'opening'] : ['static', 'static']);
      const barw = Math.max(2, Math.round(34 * clamp(d.snr / Math.max(top, 1), 0, 1)));
      html += '<tr' + (i === 0 ? ' class="best"' : '') + '><td>' + (i + 1) +
        '</td><td>' + d.range.toFixed(2) +
        '</td><td>' + (d.vel >= 0 ? '+' : '') + d.vel.toFixed(2) +
        '</td><td class="' + sense[0] + '">' + sense[1] +
        '</td><td>' + d.snr.toFixed(1) +
        '<span class="bar-cell" style="width:' + barw + 'px"></span></td></tr>';
    });
    tb.innerHTML = html;
  }
  const st = S.stats;
  $('dets-foot').textContent = 'block ' + (st ? st.seq : '-') +
    ' · source t ' + (S.radar && S.radar.t ? S.radar.t.toFixed(2) : '-') +
    ' s · ' + dets.length + ' detection(s)';
}

function syncView() {
  const st = S.stats;
  const chip = $('chip-sync');
  const ageLocal = S.lastBlockMs ? (Date.now() - S.lastBlockMs) / 1000 : null;
  let state = 'nodata', detail = 'no block received yet';
  if (st && st.sync) { state = st.sync.state; detail = st.sync.detail; }
  if (ageLocal !== null && ageLocal > S.staleS) {
    state = 'stale';
    detail = 'no block for ' + ageLocal.toFixed(1) + ' s (> ' +
      S.staleS.toFixed(0) + ' s): radar_acquire.py not posting?';
  }
  const text = { ok: 'OK', jitter: 'JITTER', stale: 'NO SYNC', nosync: 'NO SYNC',
                 nodata: 'NO DATA' }[state] || state.toUpperCase();
  $('sync-state').textContent = text;
  chip.className = 'chip ' + (state === 'ok' ? 'ok' : (state === 'jitter' ? 'warn' : 'bad'));
  $('sync-detail').textContent = detail;
}

function statusView() {
  const st = S.stats, tr = S.track;
  if (st) {
    S.staleS = st.stale_s || 3.0;
    $('stat-hz').textContent = fmt(st.block_hz, 2);
    $('stat-tchirp').textContent = st.t_chirp_ms ? fmt(st.t_chirp_ms.last, 3) : '--';
    $('stat-pri').textContent = st.pri_ms ? fmt(st.pri_ms.last, 3) : '--';
    $('chip-demo').hidden = !st.demo;
    $('ro-tchirp').textContent = st.t_chirp_ms ? fmt(st.t_chirp_ms.last, 3) : '--';
    const jit = st.t_chirp_ms && st.t_chirp_ms.pk_pk !== null
      ? st.t_chirp_ms.pk_pk * 1000 : null;
    $('ro-jit').textContent = jit === null ? '--' : fmt(jit, 0);
    $('ro-jit').parentNode.classList.toggle(
      'alarm', !!(st.t_chirp_ms && st.t_chirp_ms.pk_pk_pct > (st.jitter_warn_pct || 2)));
    $('ro-pri').textContent = st.pri_ms ? fmt(st.pri_ms.last, 3) : '--';
    $('ro-duty').textContent = fmt(st.duty_pct, 1);
    $('ro-hz').textContent = fmt(st.block_hz, 2);
    $('ro-blocks').textContent = st.blocks + ' / ' + st.bad_blocks;
  }
  if (tr && tr.valid) {
    $('ro-range').textContent = fmt(tr.range_m, 2);
    $('ro-vel').textContent = (tr.vel_ms >= 0 ? '+' : '') + fmt(tr.vel_ms, 2);
    $('ro-sr').textContent = fmt(tr.sigma_r_m, 3);
    $('ro-sv').textContent = fmt(tr.sigma_v_ms, 3);
    $('ro-pred').textContent = tr.predict ? fmt(tr.predict.range_m, 2) : '--';
    if (tr.predict) {
      $('ro-pred').nextElementSibling.textContent =
        'm @ +' + fmt(tr.predict.horizon_s, 1) + ' s';
    }
    $('ro-tca').textContent = tr.tca_s === null || tr.tca_s === undefined
      ? '--' : fmt(tr.tca_s, 1);
    ['ro-range', 'ro-vel'].forEach((id) =>
      $(id).parentNode.classList.toggle('stale', !!tr.coasting));
  } else {
    ['ro-range', 'ro-vel', 'ro-sr', 'ro-sv', 'ro-pred', 'ro-tca']
      .forEach((id) => { $(id).textContent = '--'; });
  }
  syncView();
}

function setLink(mode) {
  S.link = mode;
  const dot = $('link-dot');
  dot.className = 'dot ' + (mode === 'stream' ? 'live'
    : (mode === 'polling' ? 'poll' : (mode === 'init' ? '' : 'dead')));
  $('link-mode').textContent = mode;
  $('chip-link').title = mode === 'stream'
    ? 'live Server-Sent Events from /api/stream'
    : 'polling /api/state (the event stream is down)';
}

function logLine(s) { $('log').textContent = s; }

/* ------------------------------------------------------------------ *
 * data ingest
 * ------------------------------------------------------------------ */

function setMap(radar) {
  if (!radar || !radar.rd || !radar.rd_shape || !radar.rd_range) return;
  const nv = radar.rd_shape[0] | 0, nr = radar.rd_shape[1] | 0;
  const data = b64bytes(radar.rd);
  if (data.length !== nv * nr) { console.warn('rd length mismatch'); return; }
  S.map = { nv: nv, nr: nr, data: data, axes: radar.axes,
            lo: radar.rd_range.min, hi: radar.rd_range.max, img: null };
}

function wfGeometryChanged(wf) {
  return wf.n_r !== S.wf.n_r || Math.abs(wf.dr - S.wf.dr) > 1e-9
    || Math.abs(wf.r0 - S.wf.r0) > 1e-9 || wf.kind !== S.wf.kind;
}

function pushWfRow(wf) {
  if (!wf || !wf.n_r) return;
  if (wfGeometryChanged(wf)) {
    S.wf = { rows: [], n_r: wf.n_r, r0: wf.r0, dr: wf.dr, kind: wf.kind };
  }
  const u8 = b64bytes(wf.row);
  const db = new Float32Array(wf.n_r);
  const span = (wf.db_max - wf.db_min) / 255;
  for (let i = 0; i < wf.n_r && i < u8.length; i++) db[i] = wf.db_min + u8[i] * span;
  S.wf.rows.push({ t: wf.t, db: db });
  if (S.wf.rows.length > WF_ROWS_MAX) S.wf.rows.splice(0, S.wf.rows.length - WF_ROWS_MAX);
}

function applyWfSnapshot(wf) {
  if (!wf || !wf.rows_n || !wf.n_r) return;
  const u8 = b64bytes(wf.rows);
  const rows = [];
  const span = (wf.db_max - wf.db_min) / 255;
  for (let k = 0; k < wf.rows_n; k++) {
    const db = new Float32Array(wf.n_r);
    const base = k * wf.n_r;
    for (let i = 0; i < wf.n_r; i++) db[i] = wf.db_min + u8[base + i] * span;
    rows.push({ t: wf.t[k], db: db });
  }
  S.wf = { rows: rows, n_r: wf.n_r, r0: wf.r0, dr: wf.dr, kind: wf.kind };
}

function pushTrack(p) {
  if (!p) return;
  const h = S.trackHist;
  if (h.length && p.t <= h[h.length - 1].t) return;
  h.push(p);
  if (h.length > TRK_MAX) h.splice(0, h.length - TRK_MAX);
}

function onEvent(ev) {
  if (!ev || typeof ev !== 'object') return;
  if (ev.radar) {
    S.radar = ev.radar;
    // the map belongs to this block: if the sender stopped sending maps
    // (radar_acquire without --map) drop the old one rather than pairing a
    // stale heatmap with fresh detections.
    if (ev.radar.rd) setMap(ev.radar); else S.map = null;
  }
  if (ev.stats) S.stats = ev.stats;
  if (ev.track) S.track = ev.track;
  if (ev.wf) pushWfRow(ev.wf);
  if (ev.point) pushTrack(ev.point);
  S.lastBlockMs = Date.now();
  drawDets(); statusView(); mark();
}

function applyState(st) {
  if (!st || typeof st !== 'object') return;
  S.radar = st.radar || S.radar;      // /api/state never carries the RD map
  S.stats = st.stats || S.stats;
  S.track = st.track || S.track;
  if (st.track && st.track.history && st.track.history.length) {
    S.trackHist = st.track.history;
  }
  if (st.waterfall) applyWfSnapshot(st.waterfall);
  if (st.stats && st.stats.blocks > 0) S.lastBlockMs = Date.now() -
    (st.stats.age_s || 0) * 1000;
  if (st.log && st.log.length) logLine(st.log[st.log.length - 1].msg);
  drawDets(); statusView(); mark();
}

/* ------------------------------------------------------------------ *
 * transport: SSE with a polling fallback
 * ------------------------------------------------------------------ */

let es = null, pollTimer = null, reconnectTimer = null;

async function pollOnce() {
  try {
    const r = await fetch('/api/state', { cache: 'no-store' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    applyState(await r.json());
    if (S.link !== 'stream') setLink('polling');
  } catch (e) {
    setLink('down');
    logLine('/api/state unreachable: ' + e.message);
  }
}

function startPolling() {
  if (pollTimer) return;
  if (S.link !== 'stream') setLink('polling');
  pollOnce();
  pollTimer = setInterval(pollOnce, 1000);
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

function startStream() {
  if (typeof EventSource === 'undefined') { startPolling(); return; }
  try {
    es = new EventSource('/api/stream');
  } catch (e) {
    logLine('EventSource unavailable: ' + e.message);
    startPolling();
    return;
  }
  es.onopen = () => { setLink('stream'); logLine('event stream open'); };
  es.onmessage = (e) => {
    stopPolling();
    setLink('stream');
    try { onEvent(JSON.parse(e.data)); }
    catch (err) { console.warn('bad stream event', err); }
  };
  es.onerror = () => {
    // EventSource retries by itself unless it is CLOSED; either way fall back
    // to polling /api/state so the console keeps updating.
    if (es && es.readyState === 2) {
      setLink('down');
      if (!reconnectTimer) {
        reconnectTimer = setTimeout(() => {
          reconnectTimer = null;
          if (es) { es.close(); es = null; }
          startStream();
        }, 5000);
      }
    } else {
      setLink('polling');
    }
    startPolling();
  };
}

/* ------------------------------------------------------------------ *
 * boot
 * ------------------------------------------------------------------ */

function boot() {
  $('rd-floor').addEventListener('input', (e) => {
    S.floor = clamp(Number(e.target.value) / 100, 0, 0.9);
    if (S.map) S.map.img = null;
    mark('rd');
  });
  S.floor = clamp(Number($('rd-floor').value) / 100, 0, 0.9);
  $('hold').addEventListener('change', (e) => {
    S.hold = !!e.target.checked;
    if (!S.hold) mark();
  });
  window.addEventListener('resize', () => mark());
  setLink('init');
  pollOnce().then(startStream);          // snapshot first, then go live
  setInterval(() => { syncView(); }, 500);
  mark();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot);
} else {
  boot();
}
