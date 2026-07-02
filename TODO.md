# TODO — viewer (paper-centric column view)

Open requests for the `lit build` viewer. Details deliberately left thin for now.

- [x] **Iterative expansion.** Expansion should drill in level by level, not jump straight
  to a single fixed level. (Spec the levels later.) — *Two axes, both iterative. Cross-paper:
  one click = one generation (a spawned card drills the next when clicked in turn).
  Within-paper: focusing shows only the top-level claims + questions; each row drills its
  own branch of the support DAG, one level per click, down to the exact quote. Edges start
  paper-level (aggregate) and sharpen to slices as rows are revealed.*

- [x] **Specifically link context claims.** A context/lateral claim must show *which claim
  belongs to which paper* — resolve the link to the specific claim, not just the container.
  — *Sharpened refs (`Chen2021Sys:c1`) survive into the emitted JSON (`tid`); the target
  card context-opens to reveal the slice and the edge anchors on it, falling back to the
  container while the target is collapsed (the wildcard un-sharpens visually).*

- [x] **Non-exclusive expansion.** Expanding one paper must not collapse another. Multiple
  papers stay open at once. — *Open state is a set; every toggle recomputes columns + edges
  from it, so fans accumulate and collapse independently.*

- [x] **Make substructure visible.** Within an expanded paper the slices currently render as
  a flat list (e.g. the methods of `Ruppel2023eLife`), but the graph has a dependency
  hierarchy among them — that hierarchy must be shown. — *The hierarchy IS the interaction:
  drilling a row nests its direct supports beneath it (outline-style; a shared support
  appears under each branch), a question nests the claims that `answer` it, and a drilled
  claim shows its weld — the exact quote.*

## Open

- [ ] **Citation-wall collapse.** A real paper carries 30–80 citations, so a curated paper's
  grounds column becomes a wall of stub cards (the example's two-stub column hides this).
  Spawn a borrowed claim's sources as a single collapsed "▸ N sources" stack, expandable on
  demand (design doc, "known gaps") — must stay folded even under "expand all".

- [ ] **Cross-paper `answers` edges.** Local answers now drill in place (a question nests
  its answering claims), but a sharpened `answers` ref into another paper
  (`Citekey:qN`) still draws nothing. Emit it from build.py and draw it like the other
  sharpened edges (context-reveal the target question).

- [ ] **Rightward "builds-on" column.** The right side only ever shows broad synthesis
  nodes; the design sketch also has *newer papers that build on the focus*. Derivable at
  build time by inverting `grounds`. Related hardening: `_cons` assumes every `leads_to`
  target is a broad slug — a cross-paper `leads_to` ref would be mis-rendered, and nothing
  validates against it.

- [ ] **Entry-row rule check after real use.** Entry rows = top-level claims + questions.
  On first focus a paper can look sparse (Chen's much-cited `c1` sits one drill below `c3`
  because `c3` builds on it). Deliberate, but revisit once a real paper is curated.

- [ ] **`lit serve`.** PDF hover-preview and click-to-open; the tooltip already stubs
  "PDF preview/open needs `lit serve`". Convenience, not a correctness gap.

## Beyond the viewer

- [ ] **Curate the first real paper.** Everything above is provisional until a real PDF has
  been through `lit ingest` + the four-pass CURATION.md sweep — real data decides which
  viewer gaps actually matter (citation walls, crowding, entry rows).
