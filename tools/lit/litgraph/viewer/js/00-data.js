const PAPERS = GRAPH.papers;
const BROAD = GRAPH.broad;
const STUBS = GRAPH.stubs;
const ORDER = GRAPH.order;
// The topic axis (SCHEMA §9) — a saved-search tree over the paper `tags` vocabulary, computed
// once in Python (build.py's _topics_json: closure + curated membership already reduced, so
// this viewer never re-walks `broader`). `|| {}` covers both an untopiced repo (to_json_dict
// still emits "topics": {}) and `lit preview`'s isolated payload, which carries no "topics" key
// at all (preview.isolate() reduces to one paper — see preview.py).
const TOPICS = GRAPH.topics || {};

// slug -> every curated paper that links into that broad node (generalize / stance / answer),
// independent of expansion state. Lets a broad-node hover reach papers still collapsed in the
// landing column, not just the expanded ones whose edges happen to already be drawn.
const BROAD_LINKS = {};
function buildBroadLinks(){
  for(const k in BROAD_LINKS) delete BROAD_LINKS[k];   // idempotent: a live refresh rebuilds it
  const push=(slug,key,via,kind)=>{ (BROAD_LINKS[slug]=BROAD_LINKS[slug]||[]).push({key,via,kind}); };
  for(const [key,p] of Object.entries(PAPERS)){
    if(!p.cur) continue;
    (p.cons||[]).forEach(c=>push(c.slug,key,c.via,"leads"));
    (p.lateral||[]).forEach(l=>{ if(l.slug) push(l.slug,key,l.via,l.sign); });
    (p.ans||[]).forEach(a=>{ if(a.slug) push(a.slug,key,a.via,"answers"); });
  }
}
buildBroadLinks();

