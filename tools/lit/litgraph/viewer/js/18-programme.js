// ── the programme lane: aims + the narrative that orders them (programme design §4, §7) ──
// `include_aims` (build.py) rides both axes into this payload; this is where they get a place
// to stand. Deliberately NOT wired into the board's column system (cols{}/ensureCol/rebuild,
// see 06-layout.js): that machinery exists to make a paper's grounds/builds spawn generations
// of neighbouring columns as you click deeper, and an aim has no such generation to spawn
// (its own cross-paper "grounds" is the point of `lit preview '@slug'`, which already renders
// it in the full column system, isolated). Registering this lane there would also mean
// teaching rebuild()'s column-teardown loop about a THIRD persistent column (today only col 0
// is exempt) for a lane that never needs to be torn down in the first place — it is built once,
// at boot, from a fixed population, exactly like col 0's own "curated papers" (see
// syncLanding's header comment) but with nothing that ever changes it afterward. Simplest
// thing that renders the lane correctly and can't be un-rendered by an unrelated click
// elsewhere on the board.
//
// A card placed here still runs through the ordinary `paperCard`/`cardClick`/`renderSlices`
// machinery (03-card.js, 04-hover-pin.js, 05-slices.js already branch on `p.aim` — this is
// exactly what `lit preview` exercises today, just inside the main board instead of isolated),
// so clicking an aim open still reveals its own outline, fold/drill and all. What it will NOT
// do is spawn a grounds/builds column: `expandCard` (07-expand.js) is only ever reached by
// rebuild()'s sweep over cards actually registered in `cols{}`, and this lane isn't. No edges
// are drawn to or from it either, for the same reason — `addEdge` is only ever called from
// that same sweep. That is a real, deliberate limit, not an oversight: it is the "own lane" of
// job 2's ask, not the full cross-paper drill of job 2's stretch goal.
//
// AIMLANE itself is declared in 01-state.js beside SYNTH, not here — see the comment there for
// why a module-local const would throw when boot() calls renderProgrammeLane() as its very
// first statement (12-landing.js), before this file's own top-level code has run.
function aimKeys(){ return Object.keys(PAPERS).filter(k => PAPERS[k].aim); }

// A narrative bullet's `refs` are rendered as plain, inert chips — never as drawn edges and
// never clickable to jump. That is not a shortcut: the narrative axis "carries no edges and
// derives nothing" (design §7, and the extension in narrative.py's own docstring) precisely so
// deleting it can never change the graph. Drawing a line for one here, however tempting, would
// hand the model a relation the schema deliberately does not give it.
function narrativePanel(grant, n){
  const el = document.createElement("div");
  el.className = "card narrative";
  el.dataset.key = "narrative::" + grant;
  const budget = n.page_budget != null
    ? `<span class="cyr">${esc(String(n.page_budget))}p</span>` : "";
  let body = `<div class="chd"><span class="ckey">${esc(n.title || grant)}</span>${budget}</div>`;
  body += (n.sections || []).map(sec => {
    const bullets = (sec.bullets || []).map(b => {
      const refs = (b.refs || []).map(r => `<span class="nref">${esc(r)}</span>`).join("");
      return `<div class="nbullet"><div class="ntx">${esc(b.text)}</div>`
           + (refs ? `<div class="nrefs">${refs}</div>` : "") + `</div>`;
    }).join("");
    return `<div class="nsec"><div class="nsechd">${esc(sec.title)}</div>${bullets}</div>`;
  }).join("");
  el.innerHTML = body;
  return el;
}

function renderProgrammeLane(){
  const keys = aimKeys(), narr = GRAPH.narrative || {};
  if(!keys.length && !Object.keys(narr).length) return;
  const col = document.createElement("div");
  col.className = "col";
  col.innerHTML = `<div class="colhd">programme</div>`;
  for(const k of keys) col.appendChild(paperCard(k, AIMLANE));
  for(const grant in narr) col.appendChild(narrativePanel(grant, narr[grant]));
  // Always first: inserting at the current firstChild works whether this runs before or after
  // col 0 exists (boot() happens to call it first, but nothing here depends on that order).
  stage.insertBefore(col, stage.firstChild);
}
