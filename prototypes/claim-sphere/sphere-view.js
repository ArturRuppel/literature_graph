/* sphere-view — canvas renderer for the claim sphere (Modernist ink/red).
 *
 * Three layouts over one authored model: sphere, sectors (exploded families),
 * shells (radius unrolled into a stack of plates). No inference, no embedding:
 * every coordinate comes from derive-model.js, which reads dist/graph.json.
 *
 * 2D canvas with a hand-rolled perspective projection and a painter's-algorithm
 * depth sort — not WebGL. ~1000 nodes and ~1000 edges do not need a GPU, and 2D
 * canvas buys exact control of hairline weight, dash patterns and label
 * placement, which is what makes the ink-and-red treatment legible.
 *
 *   <sphere-view layout="sphere|sectors|shells" src="graph.json" …>
 *
 * Attributes: layout, src, shell-min, shell-max, edges, halo, isolate, explode,
 * accent, halo-alpha, mark-scale, labels, view-id.
 * Events: sv-select, sv-hover, sv-cam.  Method: resetView().
 */
import { deriveModel } from './derive-model.js';

const INK = '#201e1d', RED = '#ec3013';
const PLATE_DY = 0.55, PLATE_X = -0.85;

/* One GET, cached at module level and shared by all three views. */
let modelPromise = null;
const loadModel = (src) => (modelPromise ||= fetch(src)
  .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status + ' for ' + src); return r.json(); })
  .then(deriveModel));

class SphereView extends HTMLElement {
  static get observedAttributes() {
    return ['layout', 'shell-min', 'shell-max', 'edges', 'halo', 'isolate',
      'explode', 'accent', 'halo-alpha', 'mark-scale', 'labels', 'src', 'view-id'];
  }
  attr(name) { return this.getAttribute(name); }
  constructor() {
    super();
    this.cam = { yaw: 0.6, pitch: 0.25, dist: 3.4 };
    this.home = { ...this.cam };
    this.proj = [];
    this.hover = null;
    this.sel = null;
    this._raf = null;
  }
  connectedCallback() {
    if (this._built) return;
    this._built = true;
    this.style.display = 'block';
    this.style.position = 'relative';
    this.style.background = '#f3f2f2';
    this.style.cursor = 'grab';
    this.style.touchAction = 'none';
    this.canvas = document.createElement('canvas');
    Object.assign(this.canvas.style, { display: 'block', width: '100%', height: '100%' });
    this.appendChild(this.canvas);
    this.ctx = this.canvas.getContext('2d');
    /* the tooltip is DOM, not canvas, so it inherits the page font and stays crisp */
    this.tip = document.createElement('div');
    Object.assign(this.tip.style, {
      position: 'absolute', pointerEvents: 'none', display: 'none', maxWidth: '280px',
      background: INK, color: '#f3f2f2', font: '11px/1.35 Archivo, system-ui, sans-serif',
      padding: '5px 8px', transform: 'translate(-50%,-125%)', zIndex: 5, letterSpacing: '.01em'
    });
    this.appendChild(this.tip);
    this._ro = new ResizeObserver(() => this.resize());
    this._ro.observe(this);
    this.bindEvents();
    this.cam = this.homeCam(); this.home = { ...this.cam };
    loadModel(this.attr('src') || 'graph.json').then(m => {
      this.model = m;
      this.dispatchEvent(new CustomEvent('sv-model', { bubbles: true, detail: { model: m } }));
      this.draw();
    }).catch(err => {
      this._error = err.message;
      this.draw();
    });
    this.resize();
  }
  disconnectedCallback() { this._ro?.disconnect(); }
  homeCam() {
    const l = this.attr('layout') || 'sphere';
    if (l === 'shells') return { yaw: 0.42, pitch: 0.34, dist: 5.8 };
    if (l === 'sectors') return { yaw: 0.6, pitch: 0.22, dist: 4.8 };
    return { yaw: 0.6, pitch: 0.22, dist: 4.3 };
  }
  attributeChangedCallback(n) {
    if (n === 'layout') { this.cam = this.homeCam(); this.home = { ...this.cam }; }
    this.draw();
  }
  /* ---------- interaction ---------- */
  bindEvents() {
    let drag = null;
    this.addEventListener('pointerdown', e => {
      drag = { x: e.clientX, y: e.clientY, yaw: this.cam.yaw, pitch: this.cam.pitch, moved: 0 };
      this.setPointerCapture(e.pointerId); this.style.cursor = 'grabbing';
    });
    this.addEventListener('pointermove', e => {
      const r = this.getBoundingClientRect();
      if (drag) {
        drag.moved += Math.abs(e.movementX) + Math.abs(e.movementY);
        this.cam.yaw = drag.yaw + (e.clientX - drag.x) * 0.006;
        this.cam.pitch = Math.max(-1.45, Math.min(1.45, drag.pitch + (e.clientY - drag.y) * 0.006));
        this.draw();
      } else {
        this.pick(e.clientX - r.left, e.clientY - r.top);
      }
    });
    this.addEventListener('pointerup', e => {
      const wasDrag = drag && drag.moved > 6;
      drag = null; this.style.cursor = 'grab';
      try { this.releasePointerCapture(e.pointerId); } catch (_) { }
      if (!wasDrag) {
        const r = this.getBoundingClientRect();
        this.pick(e.clientX - r.left, e.clientY - r.top);
        this.sel = this.hover && this.hover.n;
        this.emit('sv-select', this.hover);
        this.draw();
      }
    });
    this.addEventListener('pointerleave', () => { this.hover = null; this.tip.style.display = 'none'; this.draw(); });
    this.addEventListener('wheel', e => {
      e.preventDefault();
      this.cam.dist = Math.max(0.35, Math.min(9, this.cam.dist * (1 + Math.sign(e.deltaY) * 0.09)));
      this.emit('sv-cam', { dist: this.cam.dist });
      this.draw();
    }, { passive: false });
  }
  emit(name, node) {
    this.dispatchEvent(new CustomEvent(name, {
      bubbles: true, composed: true,
      detail: { view: this.attr('view-id'), node: node && node.n ? node.n : node }
    }));
  }
  resetView() { this.cam = { ...this.home }; this.emit('sv-cam', { dist: this.cam.dist }); this.draw(); }
  pick(mx, my) {
    let best = null, bd = 144;   /* 12px, squared */
    for (const p of this.proj) {
      const d = (p.sx - mx) ** 2 + (p.sy - my) ** 2;
      if (d < bd) { bd = d; best = p; }
    }
    if (best !== this.hover) {
      this.hover = best;
      this.emit('sv-hover', best);
      this.draw();
    }
    if (best) {
      const n = best.n;
      this.tip.style.display = 'block';
      this.tip.style.left = best.sx + 'px';
      this.tip.style.top = best.sy + 'px';
      this.tip.textContent = (n.t === 'b' ? n.title : (n.text || '').slice(0, 130));
    } else this.tip.style.display = 'none';
  }
  /* ---------- geometry ---------- */
  resize() {
    const r = this.getBoundingClientRect();
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const w = Math.max(1, r.width), h = Math.max(1, r.height);
    /* Setting canvas.width clears the backing store, so a no-op resize would
       wipe the frame we just drew. The observer fires on every layout pass. */
    if (w === this.w && h === this.h && this.canvas.width === w * dpr) return;
    this.w = w; this.h = h;
    this.canvas.width = w * dpr; this.canvas.height = h * dpr;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.draw();
  }
  /* plate index: floors at 0, slice ranks 1…maxSlice, then the broad tiers
     stacked above them with the top level last. Derived, not hardcoded, so a
     fifth slice rank or a fourth broad tier does not collide. */
  plateCount(m) { return (m.stats.maxSlice + 1) + (m.stats.maxTier + 1); }
  plateOf(m, n) { return n.t === 'b' ? (m.stats.maxSlice + 1) + (m.stats.maxTier - n.lvl) : n.lvl; }
  plateY(m, k) { return (k - (this.plateCount(m) - 1) / 2) * PLATE_DY; }
  pos(n) {
    const layout = this.attr('layout') || 'sphere';
    if (layout === 'shells') {
      const m = this.model;
      const nf = m.families.length;
      if (n.lvl == null) {   /* the slab: rank-less claims, standing beside the stack */
        const s = Math.sin(n.x * 31.7) * 0.5 + 0.5, s2 = Math.sin(n.z * 17.3) * 0.5 + 0.5, s3 = Math.sin(n.y * 23.1) * 0.5 + 0.5;
        return [1.75 + s * 0.85, (s3 - 0.5) * 4.4, (s2 - 0.5) * 1.7];
      }
      const k = this.plateOf(m, n);
      const fi = n.fam && n.fam.length ? n.fam[0] : null;
      const a = fi == null ? 0 : (fi / nf) * Math.PI * 2;
      const rad = fi == null ? 0 : 0.66;          /* no family ⇒ the plate's centre */
      const anchor = [Math.cos(a) * rad, Math.sin(a) * rad];
      const j = n.j || 0;
      const u = Math.sqrt((j % 24 + 0.4) / 24) * 0.21, th = j * 2.39996;
      return [anchor[0] + Math.cos(th) * u + PLATE_X - 0.7, this.plateY(m, k), anchor[1] + Math.sin(th) * u];
    }
    if (n.halo) {
      const h = Math.abs(Math.sin((n.x + n.y * 3.1 + n.z * 7.7) * 91.3)) ** 0.7;
      const R = 1.1 + h * 0.95;
      const m = Math.hypot(n.x, n.y, n.z) || 1;
      const w = Math.sin((n.x - n.z) * 53.1) * 0.06;
      return [(n.x / m) * R + w, (n.y / m) * R - w, (n.z / m) * R + w * 0.5];
    }
    if (layout === 'sectors' && n.fam && n.fam.length) {
      const ex = parseFloat(this.attr('explode') || '0.4');
      const ax = n.fam.reduce((acc, k) => {
        const a = this.model.families[k].axis;
        return [acc[0] + a[0], acc[1] + a[1], acc[2] + a[2]];
      }, [0, 0, 0]);
      const mag = Math.hypot(...ax) || 1;
      return [n.x + ax[0] / mag * ex, n.y + ax[1] / mag * ex, n.z + ax[2] / mag * ex];
    }
    return [n.x, n.y, n.z];
  }
  project(p) {
    const { yaw, pitch, dist } = this.cam;
    const cy = Math.cos(yaw), sy = Math.sin(yaw), cp = Math.cos(pitch), sp = Math.sin(pitch);
    let x = p[0] * cy - p[2] * sy, z = p[0] * sy + p[2] * cy, y = p[1];
    const y2 = y * cp - z * sp, z2 = y * sp + z * cp;
    const zc = z2 + dist;
    const f = Math.min(this.w, this.h) * 1.012;
    const k = f / Math.max(0.12, zc);
    return [this.w / 2 + x * k, this.h / 2 - y2 * k, zc, k / f];
  }
  /* ---------- draw ---------- */
  draw() {
    if (this._raf) return;
    this._raf = requestAnimationFrame(() => { this._raf = null; this._draw(); });
  }
  _draw() {
    const ctx = this.ctx; if (!ctx) return;
    ctx.clearRect(0, 0, this.w, this.h);
    ctx.fillStyle = '#f3f2f2'; ctx.fillRect(0, 0, this.w, this.h);
    const m = this.model;
    if (!m) {
      ctx.fillStyle = this._error ? RED : '#9b9797';
      ctx.font = '11px Archivo, system-ui, sans-serif';
      ctx.fillText(this._error || 'reading graph.json…', 16, 24);
      return;
    }
    const accent = this.attr('accent') || RED;
    const haloAlpha = parseFloat(this.attr('halo-alpha') || '0.5');
    const markScale = parseFloat(this.attr('mark-scale') || '1');
    const layout = this.attr('layout') || 'sphere';
    const showHalo = this.attr('halo') !== '0';
    const kinds = new Set((this.attr('edges') || 'up,gen,cons,ladder,cite,lat').split(','));
    const iso = this.attr('isolate');
    const isoI = iso === null || iso === '' ? null : +iso;
    const smin = parseFloat(this.attr('shell-min') || '0') / 100 * 1.7;
    const smax = parseFloat(this.attr('shell-max') || '100') / 100 * 1.7;

    const vis = new Array(m.nodes.length).fill(false);
    const pts = new Array(m.nodes.length);
    const stack = layout === 'shells';
    /* 1c splits on rank alone, because height is the only axis it draws;
       1a/1b split on both coordinates. The difference is intentional. */
    const off = n => stack ? n.lvl == null : n.halo;
    m.nodes.forEach((n, i) => {
      if (off(n) && !showHalo) return;
      /* the haze is exempt from the shell window, so peeling never hides the finding */
      if (!stack && !n.halo && (n.r < smin - 1e-6 || n.r > smax + 1e-6)) return;
      if (isoI != null) {
        if (n.halo) return;
        if (!(n.fam && n.fam.includes(isoI))) return;
      }
      vis[i] = true;
      if (n.j === undefined) n.j = i;
      pts[i] = this.project(this.pos(n));
    });

    /* edges — painted under the marks, ink hairlines */
    ctx.lineWidth = 1;
    for (const e of m.edges) {
      if (!kinds.has(e.k) || !vis[e.a] || !vis[e.b]) continue;
      const A = pts[e.a], Bp = pts[e.b];
      if (A[2] <= 0.12 || Bp[2] <= 0.12) continue;
      const contra = e.k === 'lat' && e.sign === 'contra';
      const fade = Math.max(0.05, Math.min(1, 2.2 / ((A[2] + Bp[2]) / 2)));
      ctx.beginPath();
      ctx.setLineDash(e.k === 'lat' ? [3, 3] : e.k === 'cite' ? [6, 3] : []);
      ctx.strokeStyle = contra ? accent : INK;
      ctx.globalAlpha = (e.k === 'ladder' ? 0.5 : e.k === 'cons' ? 0.2 : 0.15) * fade + (contra ? 0.25 : 0);
      ctx.lineWidth = e.k === 'ladder' ? 2 : 1;
      ctx.moveTo(A[0], A[1]); ctx.lineTo(Bp[0], Bp[1]);
      ctx.stroke();
    }
    ctx.setLineDash([]); ctx.globalAlpha = 1;

    if (stack) this.drawPlates(ctx, m);

    /* marks — far to near */
    const order = [];
    m.nodes.forEach((n, i) => { if (vis[i] && pts[i][2] > 0.12) order.push(i); });
    order.sort((a, b) => pts[b][2] - pts[a][2]);
    this.proj = [];
    for (const i of order) {
      const n = m.nodes[i], p = pts[i];
      const persp = Math.max(0.35, Math.min(2.4, 2.6 / p[2]));
      const isSel = this.sel && this.sel.k === n.k;
      const isHov = this.hover && this.hover.n && this.hover.n.k === n.k;
      const s = (n.t === 'b' ? (n.lvl === 0 ? 6 : 4.2) : off(n) ? 2.1 : n.floor ? 2.9 : 2.5) * persp * markScale;
      ctx.globalAlpha = off(n) ? haloAlpha * Math.min(1, persp) : Math.min(1, 0.45 + persp * 0.5);
      const col = off(n) ? accent : INK;
      ctx.strokeStyle = col; ctx.fillStyle = col; ctx.lineWidth = 1;
      if (n.t === 'b') {
        ctx.globalAlpha = 1;
        ctx.fillStyle = n.kind === 'broad question' ? '#f3f2f2' : INK;
        ctx.beginPath(); ctx.rect(p[0] - s, p[1] - s, s * 2, s * 2); ctx.fill(); ctx.stroke();
      } else if (n.floor) {
        ctx.fillRect(p[0] - s, p[1] - s * 0.62, s * 2, s * 1.24);
      } else if (n.kind === 'method') {
        ctx.strokeRect(p[0] - s, p[1] - s, s * 2, s * 2);
      } else if (n.kind === 'question') {
        ctx.beginPath(); ctx.arc(p[0], p[1], s, 0, 6.284); ctx.stroke();
        ctx.beginPath(); ctx.arc(p[0], p[1], Math.max(0.6, s * 0.3), 0, 6.284); ctx.fill();
      } else if (n.grounded) {
        ctx.beginPath(); ctx.arc(p[0], p[1], s, 0, 6.284); ctx.fill();
      } else {
        ctx.beginPath(); ctx.arc(p[0], p[1], s, 0, 6.284); ctx.stroke();
      }
      if (isSel || isHov) {
        ctx.globalAlpha = 1; ctx.strokeStyle = accent; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.rect(p[0] - s - 4, p[1] - s - 4, s * 2 + 8, s * 2 + 8); ctx.stroke();
      }
      this.proj.push({ sx: p[0], sy: p[1], n });
    }
    ctx.globalAlpha = 1;

    if (this.attr('labels') !== '0') this.drawLabels(ctx, m, pts, vis, accent, isoI);
  }
  drawPlates(ctx, m) {
    const nP = this.plateCount(m), nS = m.stats.maxSlice;
    const labels = [];
    for (let k = 0; k < nP; k++) {
      if (k === 0) labels.push('floors');
      else if (k <= nS) labels.push('rank ' + k);
      else if (k === nP - 1) labels.push('top level');
      else labels.push('broad tier ' + (m.stats.maxTier - (k - nS - 1)));
    }
    const counts = new Array(nP).fill(0);
    m.nodes.forEach(n => {
      if (n.lvl == null) return;
      const k = this.plateOf(m, n);
      if (k >= 0 && k < nP) counts[k]++;
    });
    ctx.save();
    for (let k = 0; k < nP; k++) {
      const y = this.plateY(m, k);
      const c = [[PLATE_X - 1.7, y, -1.0], [PLATE_X + 0.3, y, -1.0], [PLATE_X + 0.3, y, 1.0], [PLATE_X - 1.7, y, 1.0]]
        .map(p => this.project(p));
      if (c.some(p => p[2] <= 0.12)) continue;
      ctx.beginPath(); ctx.moveTo(c[0][0], c[0][1]);
      for (let i = 1; i < 4; i++) ctx.lineTo(c[i][0], c[i][1]);
      ctx.closePath();
      ctx.globalAlpha = 0.22; ctx.strokeStyle = INK; ctx.lineWidth = 1; ctx.stroke();
      const lab = (labels[k] + ' · ' + counts[k]).toUpperCase();
      ctx.globalAlpha = 0.8; ctx.fillStyle = INK;
      ctx.font = '800 10px Archivo, system-ui, sans-serif';
      /* right-aligned off the plate's near-left corner, clamped into the frame:
         at the home camera the lowest plates otherwise run off the edge */
      const lw = ctx.measureText(lab).width;
      ctx.fillText(lab, Math.max(4, c[0][0] - 8 - lw), c[0][1] + 3);
    }
    ctx.restore(); ctx.globalAlpha = 1;
  }
  drawLabels(ctx, m, pts, vis, accent, isoI) {
    const layout = this.attr('layout') || 'sphere';
    if (layout === 'shells') return;
    const ex = layout === 'sectors' ? parseFloat(this.attr('explode') || '0.4') : 0;
    const placed = [];
    const fits = (x, y, w, h) => {
      for (const b of placed) if (x < b[2] && x + w > b[0] && y < b[3] && y + h > b[1]) return false;
      placed.push([x, y, x + w, y + h]); return true;
    };
    /* the sixteen, labelled on the perimeter with a hairline leader */
    ctx.font = '800 10.5px Archivo, system-ui, sans-serif';
    m.families.forEach((f, i) => {
      if (isoI != null && isoI !== i) return;
      const a = f.axis;
      const inner = this.project([a[0] * (0.13 + ex), a[1] * (0.13 + ex), a[2] * (0.13 + ex)]);
      const outer = this.project([a[0] * (1.72 + ex), a[1] * (1.72 + ex), a[2] * (1.72 + ex)]);
      if (outer[2] <= 0.12) return;
      const behind = outer[2] > inner[2];
      const txt = f.title.toUpperCase();
      const w = ctx.measureText(txt).width;
      const left = outer[0] < this.w / 2;
      let x = left ? outer[0] - w - 8 : outer[0] + 8;
      x = Math.max(6, Math.min(this.w - w - 6, x));
      const y = outer[1] + 3.5;
      if (y < 12 || y > this.h - 8) return;
      if (!fits(x, y - 11, w, 14)) return;
      ctx.globalAlpha = behind ? 0.28 : 0.9;
      ctx.strokeStyle = INK; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(inner[0], inner[1]); ctx.lineTo(outer[0], outer[1]); ctx.stroke();
      ctx.globalAlpha = behind ? 0.35 : 1;
      ctx.fillStyle = isoI === i ? accent : INK;
      ctx.fillText(txt, x, y);
    });
    /* the LOD merge: individual broad titles only once you have flown close */
    if (this.cam.dist < 2.9) {
      ctx.font = '600 10px Archivo, system-ui, sans-serif';
      m.nodes.forEach((n, i) => {
        if (n.t !== 'b' || !vis[i] || n.lvl === 0) return;
        const p = pts[i]; if (p[2] <= 0.12) return;
        const txt = n.title;
        const w = ctx.measureText(txt).width;
        if (!fits(p[0] + 9, p[1] - 12, w, 13)) return;
        ctx.globalAlpha = 0.75; ctx.fillStyle = INK;
        ctx.fillText(txt, p[0] + 9, p[1] - 3);
      });
    }
    ctx.globalAlpha = 1;
  }
}
customElements.define('sphere-view', SphereView);
