// Where does `key` already sit? Prefer the instance nearest `near`; every paper the graph can
// point at is in the landing column (landingKeys keeps the referenced stubs), so level 0 is the
// guaranteed fallback. Callers that could still miss check for the element before using it.
function findCardLevel(key,near){
  let best=null;
  for(const lvl of Object.keys(cols).map(Number)){
    if(lvl>=SYNTH||!cols[lvl].keys.has(key)) continue;
    if(best===null||Math.abs(lvl-near)<Math.abs(best-near)) best=lvl;
  }
  return best===null?0:best;
}

// `grp` is which click this expansion belongs to; everything it spawns is stamped with it, so the
// cards land in one contiguous block per opened card rather than mixed in by year. See placeInCol.
function expandCard(level,key,p,grp){
  const cid=`card-${level}:${key}`;
  // LEFT — grounds spawn the previous generation. Curated sources get their own card; a
  // sharpened ref (tid) reveals the specific source slice there and anchors the edge on
  // it. Uncurated sources fold into one collapsed "▸ N sources" stack (citation-wall
  // collapse) — their edges anchor on the stack until the human unfolds it.
  const wall=[];
  (p.grounds||[]).forEach(g=>{
    if(!PAPERS[g.key]){ wall.push(g); return; }
    addPaper(level-1,g.key,"grounds ←",grp);
    if(g.tid) reveal(`${level-1}:${g.key}`,g.tid);
    addEdge({cardId:`card-${level-1}:${g.key}`,sid:g.tid||null},{cardId:cid,sid:g.via},"leads");
  });
  if(wall.length){
    const sid=addStack(level-1,key,wall,"grounds ←",grp);
    wall.forEach(g=>addEdge({cardId:sid,sid:g.key},{cardId:cid,sid:g.via},"leads"));
  }
  // LATERAL — never spawns a column: connect to the target wherever it already sits,
  // revealing the specific claim when the ref is sharpened (Kumar → Chen2021Sys:c1).
  (p.lateral||[]).forEach(l=>{
    const from={cardId:cid,sid:l.via};
    if(l.slug){                                      // stance toward a broad claim → synthesis band
      addBroad(SYNTH,l.slug,synthLabel(),grp);
      addEdge(from,{cardId:`card-${SYNTH}:${l.slug}`,sid:null},l.sign);
      return;
    }
    const tl=findCardLevel(l.key,level);
    if(l.tid&&PAPERS[l.key]) reveal(`${tl}:${l.key}`,l.tid);
    addEdge(from,{cardId:`card-${tl}:${l.key}`,sid:l.tid||null},l.sign);
  });
  // ANSWERS — cross-paper claim→question: like lateral, never spawns a column. The target
  // question is context-revealed (an entry row, so opening its card suffices) and the
  // edge anchors on it; a broad-question target routes to the synthesis band.
  (p.ans||[]).forEach(a=>{
    const from={cardId:cid,sid:a.via};
    if(a.slug){
      addBroad(SYNTH,a.slug,synthLabel(),grp);
      addEdge(from,{cardId:`card-${SYNTH}:${a.slug}`,sid:null},"answers");
      return;
    }
    const tl=findCardLevel(a.key,level);
    if(a.tid&&PAPERS[a.key]) reveal(`${tl}:${a.key}`,a.tid);
    addEdge(from,{cardId:`card-${tl}:${a.key}`,sid:a.tid||null},"answers");
  });
  // RIGHT — the papers that build on this one (inverted grounds) spawn the next
  // generation rightward; the edge runs ground→derived and sharpens as either side's
  // rows are drilled (b.tid = this paper's grounded slice, b.via = the building slice).
  (p.builds||[]).forEach(b=>{
    addPaper(level+1,b.key,"builds on →",grp);
    addEdge({cardId:cid,sid:b.tid||null},{cardId:`card-${level+1}:${b.key}`,sid:b.via},"leads");
  });
  // RIGHTMOST — synthesis band; the edge sharpens to the generalizing claim once it's drilled
  (p.cons||[]).forEach(c=>{
    addBroad(SYNTH,c.slug,synthLabel(),grp);
    addEdge({cardId:cid,sid:c.via},{cardId:`card-${SYNTH}:${c.slug}`,sid:null},"leads");
  });
}

// Context-reveal a sharpened target: open its card and force-expand the drill path from
// an entry row down to `sid` (climbing the local outline parents — the slice's dependents
// via `up`, or the broader claim it ladders into via `gen`), so the exact slice is on
// screen. If the target is itself an entry row, opening the card suffices.
function reveal(id,sid){
  ctxOpen.add(id);
  const p=PAPERS[id.slice(id.indexOf(":")+1)];
  if(!p) return;
  // A paper's card renders every slice, so opening it IS the reveal — there is no path to
  // force. Only an aim's outline still hides a slice behind a fold.
  if(!p.aim&&!p.cited) return;
  const dep={};
  p.slices.forEach(s=>{
    (s.up||[]).forEach(u=>{ (dep[u]=dep[u]||[]).push(s.id); });
    (s.gen||[]).forEach(g=>{ (dep[s.id]=dep[s.id]||[]).push(g); });
  });
  const chain=[sid];
  let cur=sid, guard=0;
  while(dep[cur]&&dep[cur].length&&guard++<64){ cur=dep[cur][0]; chain.push(cur); }
  chain.reverse();                                   // entry row … target
  let s=ctxDrill.get(id);
  if(!s){ s=new Set(); ctxDrill.set(id,s); }
  let path="";
  for(let i=0;i<chain.length-1;i++){                 // expand every row above the target
    path=path?`${path}/${chain[i]}`:chain[i];
    s.add(path);
  }
}

// ── edges ──────────────────────────────────────────────────────────────────────────────
// The slug of the isolated broad node (an active broad target carries sid===null), else null.
function broadIsoSlug(iso){
  if(!iso||iso.sid!==null) return null;
  const el=document.getElementById(iso.cardId);
  if(!el||!el.classList.contains("bn")) return null;
  const id=el.dataset.id||"";
  return id.slice(id.indexOf(":")+1)||null;
}
