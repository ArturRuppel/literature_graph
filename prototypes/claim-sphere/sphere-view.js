/* sphere-view — canvas renderer for the claim sphere.
 *
 * Three layouts over one authored model: sphere, sectors (exploded families),
 * shells (radius unrolled into a stack of plates), plus four colour readings
 * (colour.js). Layout and colour are attributes, not separate pages — one
 * element, so the readings cannot drift apart and a selection survives a
 * change of either. No inference, no embedding: every coordinate comes from
 * derive-model.js, which reads dist/graph.json.
 *
 * 2D canvas with a hand-rolled perspective projection and a painter's-algorithm
 * depth sort — not WebGL. ~1000 nodes and ~1000 edges do not need a GPU, and 2D
 * canvas buys exact control of hairline weight, dash patterns and label
 * placement, which is what makes the treatment legible.
 *
 *   <sphere-view layout="sphere|sectors|shells" colour="status|family|generality|ink"
 *                src="graph.json" …>
 *
 * Attributes: layout, colour, src, shell-min, shell-max, edges, halo, isolate,
 * explode, spread, focus, focus-depth, halo-alpha, mark-scale, labels, view-id.
 * Events: sv-select, sv-hover, sv-cam, sv-model, sv-shown.  Method: resetView().
 *
 * Camera: orbit (drag), dolly (wheel / pinch), pan (right- or middle-drag,
 * shift-drag, two-finger drag). Pan moves the pivot, so an orbit after a pan
 * turns about what you panned to rather than about the origin.
 */
import { deriveModel } from './derive-model.js';
import { INK, RED, BOARD, colourOf, familyColours } from './colour.js';

const PLATE_DY = 0.55, PLATE_X = -0.85;

/* One GET, cached at module level. */
let modelPromise = null;
const loadModel = (src) => (modelPromise ||= fetch(src)
  .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status + ' for ' + src); return r.json(); })
  .then(deriveModel));

class SphereView extends HTMLElement {
  static get observedAttributes() {
    return ['layout', 'colour', 'shell-min', 'shell-max', 'edges', 'halo', 'isolate',
      'explode', 'spread', 'focus', 'focus-depth', 'halo-alpha', 'mark-scale', 'labels',
      'src', 'view-id'];
  }
  attr(name) { return this.getAttribute(name); }
  constructor() {
    super();
    /* tx/ty/tz is the pivot — the world point the camera orbits and looks at.
       Panning moves it; yaw/pitch/dist are polar coordinates around it. */
    this.cam = { yaw: 0.6, pitch: 0.25, dist: 3.4, tx: 0, ty: 0, tz: 0 };
    this.home = { ...this.cam };
    this.proj = [];
    this.labelHits = [];
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
      this.fams = familyColours(m.families.length);
      this.byKey = new Map(m.nodes.map((n, i) => [n.k, i]));
      this.dispatchEvent(new CustomEvent('sv-model', {
        bubbles: true, detail: { model: m, fams: this.fams }
      }));
      this.draw();
    }).catch(err => {
      this._error = err.message;
      this.draw();
    });
    this.resize();
  }
  disconnectedCallback() { this._ro?.disconnect(); }
  /* Per-layout home cameras. These frame the whole figure in the panel's
     viewport; they are not portable to a different aspect ratio. */
  homeCam() {
    const l = this.attr('layout') || 'sphere';
    const t = { tx: 0, ty: 0, tz: 0 };
    if (l === 'shells') return { yaw: 0.42, pitch: 0.34, dist: 7.0, ...t };
    if (l === 'sectors') return { yaw: 0.6, pitch: 0.22, dist: 4.8, ...t };
    return { yaw: 0.6, pitch: 0.22, dist: 4.3, ...t };
  }
  /* the expansion knob: one factor over the radial axis. In the ball and the
     sectors it scales the radius, so shells move apart while a mark keeps its
     size; in the stack the radial axis is height, so it scales plate spacing.
     Same quantity, drawn on whichever axis the layout gives it. */
  spreadFactor() {
    const v = parseFloat(this.attr('spread') || '1');
    return Number.isFinite(v) && v > 0.05 ? v : 1;
  }
  attributeChangedCallback(n, old, val) {
    /* Only a change of layout moves the camera — recentring on a colour change
       or a slider drag would throw away the reader's viewpoint. */
    if (n === 'layout' && old !== null && old !== val) {
      this.cam = this.homeCam(); this.home = { ...this.cam };
      this.emit('sv-cam', { dist: this.cam.dist });
    }
    this.draw();
  }
  /* ---------- interaction ---------- */
  /* Every live pointer is tracked, not just the first: one finger orbits, two
     pinch. A touchscreen has no wheel, so without the pinch the view is nailed
     to its home distance on a phone — and this is a figure whose whole point is
     flying in toward the apexes. Mouse behaviour is unchanged; a mouse simply
     never puts a second pointer down. */
  bindEvents() {
    const live = new Map();
    let drag = null, pinch = null;
    const spread = () => {
      const [a, b] = [...live.values()];
      return Math.hypot(a.x - b.x, a.y - b.y) || 1;
    };
    const centroid = () => {
      const p = [...live.values()];
      return { x: p.reduce((a, q) => a + q.x, 0) / p.length, y: p.reduce((a, q) => a + q.y, 0) / p.length };
    };
    const dolly = (d) => {
      /* the ceiling follows the expansion knob: spread the figure out and you
         must still be able to back off far enough to see all of it */
      const far = 11 * Math.max(1, this.spreadFactor());
      this.cam.dist = Math.max(0.35, Math.min(far, d));
      this.emit('sv-cam', { dist: this.cam.dist });
      this.draw();
    };
    const orbitFrom = (p, moved) =>
      ({ mode: 'orbit', x: p.x, y: p.y, yaw: this.cam.yaw, pitch: this.cam.pitch, moved });
    /* a pan is incremental, not anchored like the orbit: the pixels-per-world
       scale depends on the distance, which a pinch can change mid-gesture */
    const panFrom = (p, moved) => ({ mode: 'pan', x: p.x, y: p.y, moved });

    this.addEventListener('contextmenu', e => e.preventDefault());

    this.addEventListener('pointerdown', e => {
      live.set(e.pointerId, { x: e.clientX, y: e.clientY });
      try { this.setPointerCapture(e.pointerId); } catch (_) { }
      if (live.size === 2) {
        /* the second finger converts the gesture: the orbit stops where it is
           rather than being rewound, so a pinch mid-drag does not snap back.
           Two fingers do both jobs at once — the spread dollies, the centroid
           pans — which is the only pan gesture a touchscreen has to spare. */
        pinch = { d0: spread(), dist: this.cam.dist, c: centroid() };
        drag = null;
        this.tip.style.display = 'none';
      } else if (live.size === 1) {
        /* middle, right or shift+left is the pan; plain left still orbits, so
           nothing a mouse used to do has changed meaning */
        const pan = e.button === 1 || e.button === 2 || e.shiftKey;
        /* middle-down otherwise arms the browser's autoscroll, which hijacks
           the very gesture we are reading */
        if (e.button === 1) e.preventDefault();
        drag = (pan ? panFrom : orbitFrom)({ x: e.clientX, y: e.clientY }, 0);
        this.style.cursor = pan ? 'move' : 'grabbing';
      }
    });

    this.addEventListener('pointermove', e => {
      const prev = live.get(e.pointerId);
      if (prev) {
        /* path length measured from the tracked point, not e.movementX, which
           is unreliable (often 0) for touch pointers */
        if (drag) drag.moved += Math.abs(e.clientX - prev.x) + Math.abs(e.clientY - prev.y);
        prev.x = e.clientX; prev.y = e.clientY;
      }
      if (pinch && live.size === 2) {
        const c = centroid();
        this.panBy(c.x - pinch.c.x, c.y - pinch.c.y);
        pinch.c = c;
        dolly(pinch.dist * pinch.d0 / spread());
        return;
      }
      if (drag && drag.mode === 'pan') {
        this.panBy(e.clientX - drag.x, e.clientY - drag.y);
        drag.x = e.clientX; drag.y = e.clientY;
        this.draw();
        return;
      }
      if (drag) {
        this.cam.yaw = drag.yaw + (e.clientX - drag.x) * 0.006;
        this.cam.pitch = Math.max(-1.45, Math.min(1.45, drag.pitch + (e.clientY - drag.y) * 0.006));
        this.draw();
        return;
      }
      /* hover picking is a mouse affordance — a finger has no hover, and on
         touch this event only ever arrives mid-gesture anyway */
      if (e.pointerType !== 'touch') {
        const r = this.getBoundingClientRect();
        this.pick(e.clientX - r.left, e.clientY - r.top);
      }
    });

    const end = e => {
      const tap = drag && drag.mode === 'orbit' && drag.moved <= 6 && !pinch && e.type === 'pointerup';
      live.delete(e.pointerId);
      try { this.releasePointerCapture(e.pointerId); } catch (_) { }
      if (live.size < 2) pinch = null;
      if (live.size === 1) {
        /* one finger lifted out of a pinch — re-seat the orbit on the survivor
           at its current position so the view does not jump, and mark it moved
           so releasing it is not read as a tap */
        drag = orbitFrom([...live.values()][0], 99);
        return;
      }
      if (live.size) return;
      drag = null; this.style.cursor = 'grab';
      if (!tap) return;
      const r = this.getBoundingClientRect();
      this.pick(e.clientX - r.left, e.clientY - r.top);
      this.sel = this.hover && this.hover.n;
      this.emit('sv-select', this.hover);
      /* a finger leaves no cursor behind, so the tip would sit on the canvas
         until the next tap; the readout under the view has the full text */
      if (e.pointerType === 'touch') { this.hover = null; this.tip.style.display = 'none'; }
      this.draw();
    };
    this.addEventListener('pointerup', end);
    this.addEventListener('pointercancel', end);

    this.addEventListener('pointerleave', () => {
      if (drag || pinch) return;
      this.hover = null; this.tip.style.display = 'none'; this.draw();
    });
    this.addEventListener('wheel', e => {
      e.preventDefault();
      dolly(this.cam.dist * (1 + Math.sign(e.deltaY) * 0.09));
    }, { passive: false });
  }
  emit(name, node) {
    this.dispatchEvent(new CustomEvent(name, {
      bubbles: true, composed: true,
      detail: { view: this.attr('view-id'), node: node && node.n ? node.n : node }
    }));
  }
  /* Screen delta → pivot delta. The camera basis is read straight off the same
     yaw/pitch the projection uses, so the point under the cursor stays under it;
     the scale is taken at the pivot plane, which is where the figure is. */
  panBy(dx, dy) {
    const { yaw, pitch, dist } = this.cam;
    const cy = Math.cos(yaw), sy = Math.sin(yaw), cp = Math.cos(pitch), sp = Math.sin(pitch);
    const f = Math.min(this.w, this.h) * 1.012;
    const k = f / Math.max(0.12, dist);          /* pixels per world unit */
    const right = [cy, 0, -sy], up = [-sp * sy, cp, -sp * cy];
    const clamp = v => Math.max(-14, Math.min(14, v));
    this.cam.tx = clamp(this.cam.tx + (-dx * right[0] + dy * up[0]) / k);
    this.cam.ty = clamp(this.cam.ty + (-dx * right[1] + dy * up[1]) / k);
    this.cam.tz = clamp(this.cam.tz + (-dx * right[2] + dy * up[2]) / k);
  }
  resetView() { this.cam = { ...this.home }; this.emit('sv-cam', { dist: this.cam.dist }); this.draw(); }
  /* Marks first, then the text: a label is a much larger target than the 5px
     mark it names, so testing it first would make the marks unclickable. Both
     resolve to the same node, so clicking a family's name and clicking its
     apex are the same act. */
  pick(mx, my) {
    let best = null, bd = 144;   /* 12px, squared */
    for (const p of this.proj) {
      const d = (p.sx - mx) ** 2 + (p.sy - my) ** 2;
      if (d < bd) { bd = d; best = p; }
    }
    if (!best) {
      for (const h of this.labelHits) {
        if (mx >= h.x && mx <= h.x + h.w && my >= h.y && my <= h.y + h.h) { best = h; break; }
      }
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
  plateY(m, k) { return (k - (this.plateCount(m) - 1) / 2) * PLATE_DY * this.spreadFactor(); }
  pos(n) {
    const layout = this.attr('layout') || 'sphere';
    const sf = this.spreadFactor();
    if (layout === 'shells') {
      const m = this.model;
      const nf = m.families.length;
      if (n.lvl == null) {   /* the slab: rank-less claims, standing beside the stack */
        const s = Math.sin(n.x * 31.7) * 0.5 + 0.5, s2 = Math.sin(n.z * 17.3) * 0.5 + 0.5, s3 = Math.sin(n.y * 23.1) * 0.5 + 0.5;
        return [1.75 + s * 0.85, (s3 - 0.5) * 4.4 * sf, (s2 - 0.5) * 1.7];
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
      /* the wobble expands with the haze, not against it — the cloud stays the
         same cloud, further out */
      return [((n.x / m) * R + w) * sf, ((n.y / m) * R - w) * sf, ((n.z / m) * R + w * 0.5) * sf];
    }
    if (layout === 'sectors' && n.fam && n.fam.length) {
      const ex = parseFloat(this.attr('explode') || '0.4');
      const ax = n.fam.reduce((acc, k) => {
        const a = this.model.families[k].axis;
        return [acc[0] + a[0], acc[1] + a[1], acc[2] + a[2]];
      }, [0, 0, 0]);
      const mag = Math.hypot(...ax) || 1;
      return [n.x * sf + ax[0] / mag * ex, n.y * sf + ax[1] / mag * ex, n.z * sf + ax[2] / mag * ex];
    }
    return [n.x * sf, n.y * sf, n.z * sf];
  }
  project(p) {
    const { yaw, pitch, dist, tx, ty, tz } = this.cam;
    const cy = Math.cos(yaw), sy = Math.sin(yaw), cp = Math.cos(pitch), sp = Math.sin(pitch);
    const p0 = p[0] - tx, p1 = p[1] - ty, p2 = p[2] - tz;
    let x = p0 * cy - p2 * sy, z = p0 * sy + p2 * cy, y = p1;
    const y2 = y * cp - z * sp, z2 = y * sp + z * cp;
    const zc = z2 + dist;
    const f = Math.min(this.w, this.h) * 1.012;
    const k = f / Math.max(0.12, zc);
    return [this.w / 2 + x * k, this.h / 2 - y2 * k, zc, k / f];
  }
  /* ---------- focus ---------- */
  /* Adjacency over the edge kinds that are currently drawn, undirected and
     rebuilt only when that set changes. Undirected on purpose: "what is this
     claim connected to" is not a question about which way an arrow points, and
     obeying the edge filter means you can ask it of grounding alone. */
  adjacency(m, kinds) {
    const sig = [...kinds].sort().join(',');
    if (this._adjSig === sig && this._adj) return this._adj;
    const adj = m.nodes.map(() => []);
    for (const e of m.edges) {
      if (!kinds.has(e.k)) continue;
      adj[e.a].push(e.b); adj[e.b].push(e.a);
    }
    this._adjSig = sig; this._adj = adj;
    return adj;
  }
  /* The neighbourhood of the focused node, out to `focus-depth` hops. Returns
     null when nothing is focused — the caller reads null as "no restriction",
     never as "empty". */
  focusSet(m, kinds) {
    const key = this.attr('focus');
    if (!key || !this.byKey) return null;
    const start = this.byKey.get(key);
    if (start == null) return null;
    const adj = this.adjacency(m, kinds);
    const depth = Math.max(1, Math.min(6, parseInt(this.attr('focus-depth') || '1', 10) || 1));
    const seen = new Set([start]);
    let frontier = [start];
    for (let d = 0; d < depth && frontier.length; d++) {
      const next = [];
      for (const i of frontier) for (const j of adj[i]) if (!seen.has(j)) { seen.add(j); next.push(j); }
      frontier = next;
    }
    return seen;
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
    const mode = this.attr('colour') || 'status';
    const fams = this.fams;
    const haloAlpha = parseFloat(this.attr('halo-alpha') || '0.5');
    const markScale = parseFloat(this.attr('mark-scale') || '1');
    const layout = this.attr('layout') || 'sphere';
    const showHalo = this.attr('halo') !== '0';
    const kinds = new Set((this.attr('edges') || 'up,gen,cons,ladder,cite,lat').split(','));
    const iso = this.attr('isolate');
    const isoI = iso === null || iso === '' ? null : +iso;
    const smin = parseFloat(this.attr('shell-min') || '0') / 100 * 1.7;
    const smax = parseFloat(this.attr('shell-max') || '100') / 100 * 1.7;

    const focus = this.focusSet(m, kinds);

    const vis = new Array(m.nodes.length).fill(false);
    const pts = new Array(m.nodes.length);
    const stack = layout === 'shells';
    /* the stack splits on rank alone, because height is the only axis it draws;
       the ball and the sectors split on both coordinates. Intentional. */
    const off = n => stack ? n.lvl == null : n.halo;
    m.nodes.forEach((n, i) => {
      /* Focus overrides every other filter, in both directions: outside the
         neighbourhood nothing is drawn, inside it everything is — a peel or a
         halo toggle that could still swallow a neighbour would make "everything
         connected to this claim" a lie. */
      if (focus) {
        if (!focus.has(i)) return;
        vis[i] = true;
        if (n.j === undefined) n.j = i;
        pts[i] = this.project(this.pos(n));
        return;
      }
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

    /* edges — painted under the marks. Ink hairlines, except: a contradiction
       is always the accent, and in any colour mode the two edges that build the
       ladder (`cons`, broad `ladder`) take the board's broad violet, so the
       skeleton the view is about reads as one structure. */
    const ladderInk = mode === 'ink' ? INK : BOARD.broad;
    ctx.lineWidth = 1;
    let nEdges = 0;
    for (const e of m.edges) {
      if (!kinds.has(e.k) || !vis[e.a] || !vis[e.b]) continue;
      nEdges++;
      const A = pts[e.a], Bp = pts[e.b];
      if (A[2] <= 0.12 || Bp[2] <= 0.12) continue;
      const contra = e.k === 'lat' && e.sign === 'contra';
      const fade = Math.max(0.05, Math.min(1, 2.2 / ((A[2] + Bp[2]) / 2)));
      ctx.beginPath();
      ctx.setLineDash(e.k === 'lat' ? [3, 3] : e.k === 'cite' ? [6, 3] : []);
      ctx.strokeStyle = contra ? RED : (e.k === 'ladder' || e.k === 'cons') ? ladderInk : INK;
      ctx.globalAlpha = (e.k === 'ladder' ? 0.55 : e.k === 'cons' ? 0.24 : 0.15) * fade + (contra ? 0.25 : 0);
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
      ctx.globalAlpha = off(n) ? haloAlpha * Math.min(1, persp) : Math.min(1, 0.5 + persp * 0.5);
      /* `off` beats the colour mode: a node with no coordinate is red in all
         four readings, because that is what this view exists to show. */
      const col = off(n) ? RED : colourOf(mode, n, fams);
      ctx.strokeStyle = col; ctx.fillStyle = col; ctx.lineWidth = 1;
      if (n.t === 'b') {
        ctx.globalAlpha = 1;
        /* a broad question is the hollow square — the same open/filled
           distinction the board draws between asking and asserting */
        if (n.kind === 'broad question') { ctx.fillStyle = '#f3f2f2'; }
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
        /* ink, not the accent: with colour on, an accent bracket around a red
           haze node would be the same colour as the node it is pointing at */
        ctx.globalAlpha = 1; ctx.strokeStyle = INK; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.rect(p[0] - s - 4, p[1] - s - 4, s * 2 + 8, s * 2 + 8); ctx.stroke();
      }
      this.proj.push({ sx: p[0], sy: p[1], n });
    }
    ctx.globalAlpha = 1;

    this.labelHits = [];
    if (this.attr('labels') !== '0') this.drawLabels(ctx, m, pts, vis, mode, fams, isoI, focus);

    /* what actually survived the filters, for the readout under the view.
       Emitted only on a change, because _draw runs on every orbit frame. */
    const shown = {
      nodes: vis.reduce((a, v) => a + (v ? 1 : 0), 0), edges: nEdges,
      focused: !!focus, key: focus ? this.attr('focus') : null
    };
    /* the key is part of the signature: two different claims can easily have
       neighbourhoods of the same size, and the readout names the claim */
    if (!this._shown || this._shown.nodes !== shown.nodes || this._shown.edges !== shown.edges
      || this._shown.focused !== shown.focused || this._shown.key !== shown.key) {
      this._shown = shown;
      this.dispatchEvent(new CustomEvent('sv-shown', {
        bubbles: true, composed: true, detail: { view: this.attr('view-id'), ...shown, total: m.nodes.length }
      }));
    }
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
  drawLabels(ctx, m, pts, vis, mode, fams, isoI, focus) {
    const layout = this.attr('layout') || 'sphere';
    const sf = this.spreadFactor();
    const placed = [];
    const fits = (x, y, w, h) => {
      for (const b of placed) if (x < b[2] && x + w > b[0] && y < b[3] && y + h > b[1]) return false;
      placed.push([x, y, x + w, y + h]); return true;
    };
    /* every drawn label is clickable, and clicking it is clicking its node */
    const hit = (n, x, y, w, h) => this.labelHits.push({ n, x, y: y - 2, w, h: h + 4, sx: x + w / 2, sy: y + h });

    /* Focused: the neighbourhood is small enough to name every member, which is
       the point of having isolated it. Near labels are placed first so they win
       the collision test against the ones behind them. */
    if (focus) {
      ctx.font = '600 10px Archivo, system-ui, sans-serif';
      const near = [];
      m.nodes.forEach((n, i) => { if (vis[i] && pts[i] && pts[i][2] > 0.12) near.push(i); });
      near.sort((a, b) => pts[a][2] - pts[b][2]);
      for (const i of near) {
        const n = m.nodes[i], p = pts[i];
        const sel = this.sel && this.sel.k === n.k;
        const txt = n.t === 'b' ? n.title : (n.text || '').slice(0, 46) + ((n.text || '').length > 46 ? '…' : '');
        const w = ctx.measureText(txt).width;
        if (!fits(p[0] + 9, p[1] - 12, w, 13)) continue;
        ctx.globalAlpha = sel ? 1 : 0.8;
        ctx.fillStyle = sel ? RED : n.t === 'b' ? (mode === 'ink' ? INK : BOARD.broad) : INK;
        ctx.fillText(txt, p[0] + 9, p[1] - 3);
        hit(n, p[0] + 9, p[1] - 12, w, 13);
      }
      ctx.globalAlpha = 1;
      return;
    }

    if (layout === 'shells') return;
    const ex = layout === 'sectors' ? parseFloat(this.attr('explode') || '0.4') : 0;
    /* the top-level entries, labelled on the perimeter with a hairline leader.
       In `family` mode the leader and the label carry the family's own colour,
       which is what makes the strip under the viewport a legend. */
    ctx.font = '800 10.5px Archivo, system-ui, sans-serif';
    m.families.forEach((f, i) => {
      if (isoI != null && isoI !== i) return;
      const a = f.axis;
      /* the leader has to breathe with the expansion knob, or it detaches from
         the apex it points at */
      const ri = 0.13 * sf + ex, ro = 1.72 * sf + ex;
      const inner = this.project([a[0] * ri, a[1] * ri, a[2] * ri]);
      const outer = this.project([a[0] * ro, a[1] * ro, a[2] * ro]);
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
      const famCol = mode === 'family' ? fams[i] : INK;
      ctx.globalAlpha = behind ? 0.28 : 0.9;
      ctx.strokeStyle = famCol; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(inner[0], inner[1]); ctx.lineTo(outer[0], outer[1]); ctx.stroke();
      ctx.globalAlpha = behind ? 0.4 : 1;
      ctx.fillStyle = isoI === i ? RED : famCol;
      ctx.fillText(txt, x, y);
      /* the family's name is its top-level broad node — clicking one is
         clicking the other */
      const top = this.byKey && this.byKey.get('@' + f.slug);
      if (top != null) hit(m.nodes[top], x, y - 11, w, 14);
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
        ctx.globalAlpha = 0.75; ctx.fillStyle = mode === 'ink' ? INK : BOARD.broad;
        ctx.fillText(txt, p[0] + 9, p[1] - 3);
        hit(n, p[0] + 9, p[1] - 12, w, 13);
      });
    }
    ctx.globalAlpha = 1;
  }
}
customElements.define('sphere-view', SphereView);
