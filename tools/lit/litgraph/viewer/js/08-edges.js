// ── the four states, decided in ONE place ──────────────────────────────────────────────
// Every edge is in exactly one of:
//
//   E_OFF       not drawn at all
//   E_GHOST     a whisper (0.07) — a relation that exists, between things you have not opened
//   E_SCAFFOLD  faint (0.2) — structure you did not ask about, between two nodes you can see
//   E_LIT       bright (0.85 / 0.95) — incident on a pin or the hover
//
// Nothing here reads a gesture. Every input is CURRENT STATE — what is open, what is pinned, where
// the anchors are — so the same board always draws the same arrows however you arrived at it, and
// an expand or a collapse moves the edge layer because it moved the state, not because a handler
// remembered to say so. (Verified: `fold to graph`, the band's `show statements` and a per-slice
// fold each leave a path set byte-identical to a full rebuild.)
//
// This used to be decided in five places: three `continue`s in the read loop, a special case for
// any edge touching the synthesis band, and an opacity ternary at the far end of the write loop.
// They were written at different times and never reconciled, so the board's answer to "why is
// that arrow there, and why is that one not" depended on which of the five relations you were
// looking at — a `cons` edge vanished at rest while an equally long `answers` edge stayed dim,
// for no reason a reader could recover. Two questions now, asked in order:
//
//   1. Is there an honest place to draw it? — geometry, never policy. An endpoint naming a slice
//      with no row on screen falls back to its card; when BOTH ends do that, the edge collapses
//      onto the container→container line it shares with every sibling — a stack of identical
//      arrows at the card border that no isolation can ever thin. Nothing left to say: off. An
//      intra-card rung with either node scrolled out of the card would be drawn straight across
//      the card's neighbours: off.
//   2. Lit? If not, is it scaffolding at all? — TWO clauses, for two genuinely different reasons,
//      both named here rather than one of them being left implicit:
//
//      a. ILLEGIBLE. An arrow whose two ends do not fit on the glass at once is not faint
//         structure, it is a line leaving the screen. Measured with four papers open, 155 of the
//         187 cross-card scaffolding arcs ran further than a screen vertically and the worst ran
//         17,500 px — a `corr` from an open card to a landing card a hundred cards below it,
//         drawn as a near-vertical stroke down the whole board whose other end you can never see.
//         That is the "it gets really messy" half of the report, and NOTHING in the old code
//         addressed it: the rule was written in terms of what an edge CONNECTS (broad or not),
//         while the thing that makes an edge unreadable is how far it REACHES.
//      b. UNINFORMATIVE EN MASSE. Every paper that reaches a broad claim throws an arrow at the
//         synthesis band, and the band collects all of them — a permanent fan that says only
//         "many things generalize", which you knew. Legible or not, it is noise until you ask.
//
//      They are different arguments — one about distance, one about density — and neither
//      subsumes the other, so neither is dressed up as the other. (a) is measured on the glass, so
//      it is zoom-aware for free: zoom out until both ends fit and the edge comes back as
//      scaffolding, which is the board-becomes-a-map reading working as intended. It is a test on
//      the DISTANCE between the anchors, never on where they sit, so scrolling changes nothing and
//      no arrow flickers under a scroll.
//   3. Are both its ends OPEN? — an arrow between two slice rows you can see says which claim rests
//      on which. An arrow that dies on the closed border of a card says only "something in here" —
//      it cannot name its own endpoint, because you have not opened the thing it lands on. Those
//      are not the same statement and they should not be the same ink: the second is a GHOST, a
//      whisper that there is a relation here if you open it. Measured with three papers open, 43 of
//      the 193 resting arrows are of that second kind, every one of them running into a shut card.
//      Open that card and the edge sharpens to scaffolding, and then to a lit fan if you pin it —
//      one continuum, driven by how much of the graph you have opened up rather than by what you
//      last clicked.
const E_OFF=0, E_GHOST=1, E_SCAFFOLD=2, E_LIT=3;
const OP_GHOST="0.07", OP_SCAFFOLD="0.2";   // the two resting weights; lit is set at the path
// Is the thing at this end of the arrow OPENED UP? A card the reader has opened renders its slice
// rows, so the arrow can land on a node and name what it means. A broad node needs no opening — it
// IS a node, one card one claim — and a stack card carries `.open` when it is unfolded, so the same
// class answers for all three. Pure state, one class check: deliberately NOT "did rowRect resolve",
// which also goes null for a row merely scrolled sideways inside an open card, and would make the
// edge layer shimmer under a scroll. (On the resting board the two agree exactly — 150 node+node /
// 43 card+node either way — but only one of them stays still while you scroll.)
function endOpen(end){
  const el=document.getElementById(end.cardId);
  return !!el&&(el.classList.contains("open")||el.classList.contains("bn"));
}
// Does this endpoint sit on a broad node? Read off the card id (`card-<level>:<key>`) rather than
// the DOM — the synthesis band owns every level at/after SYNTH, and this is asked once per edge
// inside redraw's read phase, where a lookup would be a lookup too many.
function isBandEnd(end){
  const i=end.cardId.indexOf(":");
  return i>0&&+end.cardId.slice(5,i)>=SYNTH;
}
// `fa` / `fb` are the endpoints' row rects (null = fell back to the card) and `ra` / `rb` the
// resolved anchors, passed in rather than re-measured: this runs inside redraw's read phase, where
// a second lookup is a lookup too many. Rects are GLASS pixels and so are clientWidth/Height, which
// is the whole point — the question is literally "would both ends be on screen at once".
function edgeVis(e,lit,fa,fb,ra,rb){
  if(e.intra) { if(!(fa&&fb)) return E_OFF; }
  else if(e.from.sid&&e.to.sid&&!fa&&!fb) return E_OFF;                     // 1
  if(lit) return E_LIT;
  if(isBandEnd(e.from)||isBandEnd(e.to)) return E_OFF;                      // 2b
  const dx=Math.abs((ra.left+ra.right)-(rb.left+rb.right))/2;
  const dy=Math.abs((ra.top+ra.bottom)-(rb.top+rb.bottom))/2;
  if(dx>board.clientWidth||dy>board.clientHeight) return E_OFF;             // 2a
  return (endOpen(e.from)&&endOpen(e.to))?E_SCAFFOLD:E_GHOST;               // 3
}
// A pin names a row, and it is live only while that row is on the board. The test used to be
// `document.getElementById(cardId)` — the CARD — so a pin outlived the card being collapsed, its
// entry group being folded away, or a rebuild that no longer renders that row. What was left was
// state with no mark on screen: arrows lit from an endpoint you cannot see, and no second click
// available to release them, because the row you would click on is gone. That is the "expand a
// few claims, collapse them, and the arrows stay" report, and it is why the escape hatches below
// exist as well as this.
// Laid out, not merely present, and not rowRect either — the two near-misses are both real:
//   * DOM presence alone is too weak. `.slices` is `display:none` until the card is `.open`, so a
//     collapsed card still ANSWERS a `[data-sid]` query with every row it ever rendered, and the
//     pin survived exactly the gesture that was supposed to release it.
//   * rowRect is too strong. It clips to the card's sideways scroller and returns null for a row
//     that is merely scrolled out of view — losing your pins to a scroll would be a worse bug
//     than the one this fixes.
// `offsetParent === null` is the line between them: null under `display:none` (collapsed card,
// folded group), non-null for a row that is on the board but off to one side.
function pinLive(p){
  const card=document.getElementById(p.cardId);
  if(!card) return false;
  if(!p.sid) return true;                              // a broad node pins its whole card
  const row=card.querySelector(`[data-sid="${CSS.escape(p.sid)}"]`);
  return !!row&&row.offsetParent!==null;
}
// Isolated broad node: synthesize an edge to every linked paper NOT already wired to this node
// by a real (expanded-paper) edge, anchored on its card wherever it sits — so collapsed
// landing-column papers light up and connect too, not just the expanded ones.
function broadExtraEdges(iso,slug){
  const have=new Set();
  for(const e of edges){
    const other=e.to.cardId===iso.cardId?e.from:(e.from.cardId===iso.cardId?e.to:null);
    if(other){ const oc=document.getElementById(other.cardId); if(oc&&oc.dataset.key) have.add(oc.dataset.key); }
  }
  const extra=[];
  for(const lk of (BROAD_LINKS[slug]||[])){
    if(have.has(lk.key)) continue;
    have.add(lk.key);                              // one arrow per paper, even if several slices feed the node
    const cardId=`card-${findCardLevel(lk.key,0)}:${lk.key}`;
    if(document.getElementById(cardId))
      extra.push({from:{cardId,sid:null},to:{cardId:iso.cardId,sid:null},kind:lk.kind});
  }
  return extra;
}
// Strictly two-phase: every layout READ happens before every DOM WRITE.
//
// This used to be one loop that measured an endpoint, then set .hl on a card, then measured the
// next endpoint — and each write invalidates layout, so each following read forces the browser to
// re-lay-out the whole board synchronously. With ~3.7k cards in the landing column that penalty
// was measured at 192x (1 µs for a clean getBoundingClientRect, 192 µs for one straight after a
// class write), paid once per edge. Splitting the phases means at most ONE relayout per redraw
// instead of one per edge, which is what made pinning a broad claim feel slow.
function redraw(){
  // Isolation: the bright set is every pinned target (persisted, accumulating) ∪ the current
  // hover (transient). An edge incident on any target is drawn bright and its counterpart card
  // gets .hl; every other edge stays dim — faint scaffolding rather than a bright tangle.
  pin=pin.filter(pinLive);                                    // drop pins whose row has left the board
  // deduped: the pointer usually rests on the target it just pinned, and a target counted twice
  // made broadExtraEdges synthesize its arrows twice — identical paths stacked on each other
  const all=hover?[...pin,hover]:pin;
  const targets=all.filter((t,i)=>all.findIndex(o=>samePin(o,t))===i);
  const atT=(end,t)=>end.cardId===t.cardId&&end.sid===t.sid;
  const isTarget=end=>targets.some(t=>atT(end,t));
  const inc=e=>targets.some(t=>atT(e.from,t)||atT(e.to,t));   // incident on any target
  let work=edges.slice();
  for(const t of targets){                                    // broad target → connect collapsed papers too
    const slug=broadIsoSlug(t);
    if(slug) work=work.concat(broadExtraEdges(t,slug));
  }
  work.sort((a,b)=>(inc(a)?1:0)-(inc(b)?1:0));     // draw incident (bright) last → on top of dim

  // ── phase 1: read ──────────────────────────────────────────────────────────────────────
  // Nothing here may touch the DOM, so the browser answers every measurement from one layout.
  // Everything below is in STAGE coordinates — the unzoomed space the columns and this overlay
  // are laid out in — because that is the space the SVG paints in and the space the zoom
  // transform then scales as a whole. Rects come back from the browser in viewport (glass)
  // pixels, so BZ divides them back down; offsets are already stage-space and don't.
  const BZ=boardZoom();
  const sb=stage.getBoundingClientRect();         // stage origin on the glass (scroll folded in)
  const X=v=>(v-sb.left)/BZ, Y=v=>(v-sb.top)/BZ;
  // Size the overlay from the COLUMNS, not from board.scrollWidth/scrollHeight. #edges is an
  // absolutely-positioned child of #stage, so it contributes to the board's own scroll extent —
  // measuring the board to size the SVG fed the SVG's height back into the number that sets it,
  // a ratchet that could only grow. Once the landing column made the board ~187k px tall at boot
  // it stayed that tall forever, even when the content collapsed to a few hundred px, leaving a
  // vast empty scroll region and making every forced relayout far more expensive than the visible
  // content warranted. Columns share the SVG's origin (#stage is the offsetParent), so their
  // extent is the right measure and reading it costs no extra layout.
  let W=0,H=0;
  for(const lvl of Object.keys(cols)){
    const el=cols[lvl].el;
    W=Math.max(W,el.offsetLeft+el.offsetWidth); H=Math.max(H,el.offsetTop+el.offsetHeight);
  }
  // always cover the viewport — which, zoomed out, is MORE stage than the port is wide
  W=Math.max(W,board.clientWidth/BZ); H=Math.max(H,board.clientHeight/BZ);
  const stroke={grounded:cssv('--grounded'),cross:cssv('--cross'),question:cssv('--question'),
               broad:cssv('--broad')};
  const plan=[];
  for(const e of work){
    // `rowRect` is the row's rect CLIPPED to the boxes that actually clip it, and null once
    // nothing is left — so an endpoint scrolled out of the card's sideways-scrolling slice graph
    // falls back to its card here rather than anchoring where only the layout can see it.
    const fa=rowRect(e.from), fb=rowRect(e.to);
    const ra=fa||cardRect(e.from), rb=fb||cardRect(e.to);
    if(!ra||!rb) continue;                          // no visible endpoint yet — nothing to anchor on
    const vis=edgeVis(e,inc(e),fa,fb,ra,rb);        // the ONE decision; see there for the rule
    if(vis===E_OFF) continue;
    plan.push({e,ra,rb,vis,on:vis===E_LIT});        // `on` is "lit", used by the .hl pass below
  }

  // ── phase 2: write ─────────────────────────────────────────────────────────────────────
  svg.setAttribute("width",W); svg.setAttribute("height",H);
  while(svg.firstChild) svg.removeChild(svg.firstChild);
  const defs=document.createElementNS(NS,"defs");   // arrowheads
  defs.innerHTML=`
    <marker id="ar" markerWidth="8" markerHeight="8" refX="0" refY="3" orient="auto">
      <path d="M0,0 L6,3 L0,6 Z" fill="${stroke.grounded}"/></marker>
    <marker id="arx" markerWidth="8" markerHeight="8" refX="0" refY="3" orient="auto">
      <path d="M0,0 L6,3 L0,6 Z" fill="${stroke.cross}"/></marker>
    <marker id="arq" markerWidth="8" markerHeight="8" refX="0" refY="3" orient="auto">
      <path d="M0,0 L6,3 L0,6 Z" fill="${stroke.question}"/></marker>
    <marker id="arg" markerWidth="8" markerHeight="8" refX="0" refY="3" orient="auto">
      <path d="M0,0 L6,3 L0,6 Z" fill="${stroke.broad}"/></marker>`;
  const frag=document.createDocumentFragment();
  frag.appendChild(defs);
  // .hl is recomputed as a set difference so a card that stays lit is never touched — a no-op
  // hover (the common case while the pointer drifts inside one card) writes nothing at all.
  const lit=new Set();
  for(const {e,on} of plan){
    if(!on) continue;                               // light up each non-target endpoint's card
    for(const end of [e.from,e.to]) if(!isTarget(end)) lit.add(end.cardId);
  }
  for(const el of document.querySelectorAll(".hl"))
    if(!lit.has(el.id)) el.classList.remove("hl"); else lit.delete(el.id);
  for(const id of lit){ const oc=document.getElementById(id); if(oc) oc.classList.add("hl"); }

  for(const {e,ra,rb,on,vis} of plan){
    const ya=Y((ra.top+ra.bottom)/2);
    const yb=Y((rb.top+rb.bottom)/2);
    const contra=e.kind==="contra"||e.kind==="contradict";
    const ans=e.kind==="answers";
    const lat=e.kind==="corr"||contra;
    const gen=e.kind==="gen";           // broad->broad generalization (SCHEMA §4) — its own
                                        // color/marker, solid like a support edge, never lateral
    let d;
    if(e.intra){
      // Within one card the two nodes are in adjacent-or-further columns, so this is the facing-
      // edge case — but always, never by the width test below: folding the card shrinks the
      // columns to badge width and that test would then mistake a real ladder rung for a
      // same-column hop and bow it out the right of the card.
      const x1=X(ra.right), x2=X(rb.left);
      const mx=(x1+x2)/2;
      d=`M${x1},${ya} C${mx},${ya} ${mx},${yb} ${x2},${yb}`;
      // the 80 is a stage-space distance (a fraction of a column), so this runs on stage
      // coordinates too — otherwise zooming out would start reading distinct columns as one
    } else if(Math.abs((ra.left+ra.right)-(rb.left+rb.right))/BZ<80){
      // same column (e.g. a lateral edge between two landing cards): bow out the right side
      const x1=X(ra.right), x2=X(rb.right);
      const bow=Math.max(x1,x2)+26;
      d=`M${x1},${ya} C${bow},${ya} ${bow},${yb} ${x2},${yb}`;
    } else {                                          // cross-paper: connect the facing edges
      const aLeft=(ra.left+ra.right)/2 < (rb.left+rb.right)/2;
      const x1=X(aLeft?ra.right:ra.left);
      const x2=X(aLeft?rb.left:rb.right);
      const mx=(x1+x2)/2;
      d=`M${x1},${ya} C${mx},${ya} ${mx},${yb} ${x2},${yb}`;
    }
    const path=document.createElementNS(NS,"path");
    path.setAttribute("d",d);
    path.setAttribute("fill","none");
    path.setAttribute("stroke",contra?stroke.cross:ans?stroke.question:gen?stroke.broad:stroke.grounded);
    path.setAttribute("stroke-width","1.6");
    if(lat) path.setAttribute("stroke-dasharray","5 4");
    else if(ans) path.setAttribute("stroke-dasharray","2 3");   // dotted: answers ≠ support
    // The state was decided in edgeVis; this only paints it. The 0.2 is lifted from a true hairline
    // because the canvas is light, and the ghost sits well under it — present if you look for it,
    // never something the eye has to step over on the way to what you opened.
    path.setAttribute("opacity",on?(lat||ans?"0.85":"0.95")
                                  :(vis===E_GHOST?OP_GHOST:OP_SCAFFOLD));
    if(ans) path.setAttribute("marker-end","url(#arq)");
    else if(gen) path.setAttribute("marker-end","url(#arg)");
    else if(!lat) path.setAttribute("marker-end","url(#ar)");
    else if(contra) path.setAttribute("marker-end","url(#arx)");
    frag.appendChild(path);
  }
  svg.appendChild(frag);                            // one insertion, not one per edge
  syncClearBtn();      // every state change ends here, so this is the one place the way out
}                      // can be sure it knows whether there is anything to clear
function cssv(n){return getComputedStyle(document.documentElement).getPropertyValue(n).trim();}
// The VISIBLE slab of an endpoint's row: its rect ∩ every box that clips it. A row's layout rect
// is not where the eye sees it — a card hides its own overflow (`.card{overflow:hidden}`) and the
// slice graph inside it scrolls sideways (`.snodes{overflow-x:auto}`), so a node scrolled out of
// view goes on reporting a rect, one that can sit clear outside the card and even left of the
// whole board. Anchoring an edge on that rect threw the arc across every column to an arrowhead
// planted in blank canvas — twenty of them at once when a paper's sources all ground slices that
// had been scrolled off. Clipping to the scroller answers "where is this node on screen"; null
// means nowhere, and the caller falls back to the card the way an un-drilled endpoint does.
// (Clipping is to the CARD's box, not the viewport: a row scrolled out of sight down the board is
// still a legitimate anchor, since the overlay spans the board rather than the window.)
function rowRect(end){
  const card=end.sid&&document.getElementById(end.cardId);
  if(!card) return null;
  // drilled rows may render the same slice at several paths — take the first one on screen
  for(const rowEl of card.querySelectorAll(`[data-sid="${end.sid}"]`)){
    const r=rowEl.getBoundingClientRect();
    if(r.width<=0) continue;                        // folded away, not merely scrolled
    let l=r.left,t=r.top,ri=r.right,b=r.bottom;
    for(const clip of [rowEl.closest(".snodes"),card]){
      if(!clip) continue;
      const c=clip.getBoundingClientRect();
      l=Math.max(l,c.left); ri=Math.min(ri,c.right);
      t=Math.max(t,c.top);  b=Math.min(b,c.bottom);
    }
    if(ri>l&&b>t) return {left:l,top:t,right:ri,bottom:b};
  }
  return null;
}
// The card itself — the aggregate anchor, and what an endpoint with no on-screen row falls back to.
function cardRect(end){
  const card=document.getElementById(end.cardId);
  if(!card) return null;
  const r=card.getBoundingClientRect();
  return r.width>0?r:null;
}
// Resolve an endpoint: its on-screen row (a slice row, or a stack's source row) else the card.
// Falling back to the card is what keeps un-drilled edges aggregate.
function anchorRect(end){ return rowRect(end)||cardRect(end); }

