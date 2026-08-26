const board=document.getElementById("board");    // the scroll port
const stage=document.getElementById("stage");    // what the columns live on, and what zooms
const svg=document.getElementById("edges");
// The board's zoom factor, read straight off the CSS variable that applies it — one source of
// truth, so nothing can drift from what the reader is actually looking at. See #stage's CSS.
function boardZoom(){
  const z=parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--bz"));
  return z>0?z:1;
}
const tip=document.getElementById("tip");
let edges=[];            // {from:{cardId,sid},to:{cardId,sid},kind} — an endpoint anchors at the
                         // sid's row when drilling has made it visible, else at the card, so
                         // aggregate paper→paper edges sharpen to slice edges as the human drills
const cols={};           // level -> {el, keys:Set, label}
const open=new Set();    // "level:key" of focused cards — a set, so expansion is non-exclusive
const stubOpen=new Set();// citekeys of uncited stubs expanded to their bib record. Keyed by KEY and
                         // not by "level:key" like `open`, because a stub has no slices, no drill
                         // and no per-column role: the same uncited paper standing in two columns
                         // is one bibliography record, and there is nothing instance-specific for
                         // the two instances to disagree about. An expanded stub is an OPEN end as
                         // far as edgeVis is concerned — see toggleStub.
const absOpen=new Set(); // citekeys whose ABSTRACT is unfolded. Keyed by key and not by
                         // "level:key", for stubOpen's reason exactly: an abstract is a
                         // bibliographic fact about the paper, so the two instances of one paper
                         // standing in two columns have nothing to disagree about.
const sliceOpen=new Set();   // "level:key" whose slice graph is unfolded. An open card shows the
                             // paper — head, byline, folds — and the local subgraph is a SECOND
                             // thing to open, because 26 rows of prose and 34 arcs arriving with
                             // the title bury the very head they hang off.
const sliceSeeded=new Set(); // card ids whose slice fold has had its default applied once, so the
                             // seeding cannot re-fold what the reader has since unfolded. Cleared
                             // by a close, like grpSeeded — a reopened card is a fresh read.
const drill=new Map();   // "level:key" -> Set of expanded row paths ("c3", "c3/c1", …); AIM cards
                         // only — a paper's slices are a graph now, and a graph has no paths
const sFold=new Map();   // "level:key" -> Set of slice ids folded down to their badge. A paper's
                         // graph shows every slice at once, so folding is how the reader trades
                         // the text away for the topology, one node or all of them at a time.
const grpCollapsed=new Set();  // "level:key::<group label>" — entry sub-groups folded shut
const grpSeeded=new Set();     // aim cards whose default fold has been applied once. An aim opens
                               // on its ARGUMENT alone; the seeding must not re-fold what the
                               // reader has since unfolded, so it runs on first render only
                               // (and again after a close, which clears the id — a reopened card
                               // is a fresh read and should land back on the default view).
let ctxOpen=new Set();   // cards context-opened to reveal a sharpened target (recomputed)
let ctxDrill=new Map();  // row paths force-expanded to reveal a sharpened target (recomputed)
const stacks=new Set();  // source-stack ids the human explicitly unfolded (persists rebuilds)
let hover=null;          // {cardId,sid} — hovered slice row/broad node: redraw isolates its
                         // edges (bright) and highlights the counterpart papers, transiently
let pin=[];              // [{cardId,sid}] — clicked isolations that persist after the pointer
                         // leaves and ACCUMULATE: each click hardens another target. Lit set
                         // = every pinned target ∪ the current hover; see edgeVis for the rest.
                         // A pin names a ROW, and is dropped the moment that row leaves the board
                         // (pinLive) — state with no mark on screen is state you cannot release.
// The quiet mode: draw ONLY the arrows the reader asked for (a pin, or the row under the pointer)
// and none of the resting ones. It is the one input to edgeVis the reader sets directly — and it is
// still a STATE, not a gesture: a standing preference, read the same way on every redraw, so the
// board draws the same arrows however you arrived at it. See edgeVis clause 2c.
let quietEdges=false;
const SYNTH=1e6;         // synthesis band: the one column every broad node lives in
                         // (papers occupy small levels; builds-on growth stays left of it)
// A broad node's OWN leads_to (SCHEMA §4) can ladder it into a broader broad node, and the band is
// laid out as that nesting (see broadFamilies) rather than as columns of it.
// broadTier[slug] = the length of the longest chain of broad-to-broad leads_to edges ENDING at
// that slug, i.e. its altitude: 0 for a node only ever fed by papers (a plain head — nearest
// the papers), 1+max(tier of everything that ladders into it) otherwise. It no longer picks a
// column — it is what `broadKids` falls out of, and what orders a family's standing position.
// Recomputed once per rebuild() (cheap — tens of nodes), so a DRIVE window's hot-reloaded BROAD
// is picked up too.
let broadTier={};
let broadKids={};        // slug -> the broad nodes that ladder INTO it (one rung below), set by
