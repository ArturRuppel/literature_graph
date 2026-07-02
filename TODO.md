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

- [x] **Citation-wall collapse.** A real paper carries 30–80 citations, so a curated paper's
  grounds column becomes a wall of stub cards (the example's two-stub column hides this).
  Spawn a borrowed claim's sources as a single collapsed "▸ N sources" stack, expandable on
  demand (design doc, "known gaps") — must stay folded even under "expand all". — *A focused
  paper's uncurated sources never spawn cards: they fold into one "▸ N sources" stack per
  focused card (curated sources keep their own cards). Only an explicit click unfolds it —
  reveal/rebuild never do — and edges anchor on the stack until unfolding sharpens them to
  the source rows.*

- [x] **Cross-paper `answers` edges.** Local answers now drill in place (a question nests
  its answering claims), but a sharpened `answers` ref into another paper
  (`Citekey:qN`) still draws nothing. Emit it from build.py and draw it like the other
  sharpened edges (context-reveal the target question). — *Emitted as a per-paper `ans`
  list (sharpened → `{key, tid}`, container → wildcard, broad slug → synthesis band) and
  drawn like lateral edges: no column spawned, target question context-revealed, dotted
  question-colored stroke with its own arrowhead.*

- [x] **Rightward "builds-on" column.** The right side only ever shows broad synthesis
  nodes; the design sketch also has *newer papers that build on the focus*. Derivable at
  build time by inverting `grounds`. Related hardening: `_cons` assumes every `leads_to`
  target is a broad slug — a cross-paper `leads_to` ref would be mis-rendered, and nothing
  validates against it. — *build.py inverts cross-paper `grounded_in` between curated papers
  into a `builds` list; a focused card spawns them one generation rightward (the synthesis
  band stays rightmost) and the rebuild sweep runs to a fixpoint since expansion now grows
  both ways. Hardening became SCHEMA §6.6 kind-coherence validation: `leads_to` → same-kind
  broad slug, `answers` → a question, laterals → claim/container, `floor` → claims only.*

- [x] **Draw the local generalization ladder.** A same-paper `leads_to` to a local slice
  (a specific claim laddering up into a broader local claim, e.g. Atia's `c3 <- {c5,c6,c7,c8}`)
  now validates and builds, but the substructure tree is `grounded_in`-only, so the ladder
  is stored yet invisible. Render it in the substructure view (or a gutter bow) so the
  generalization the curator authored actually shows. — *Local `leads_to` refs ride into the
  JSON (`gen`); drilling the broader claim nests the claims that ladder into it beside its
  supports (⤴-marked, broad-purple accent), each drillable in turn down to its own quote.
  Laddering claims leave the entry rows (they sit under their parent) and context-reveal
  climbs the ladder, so a sharpened ref into a rung still surfaces it.*

- [x] **Hover-isolate edges, drawn to the box.** Hovering a claim should hide every arrow
  except the ones pointing *at* it, and those arrows must run all the way to the claim box —
  they're currently clipped/occluded by the container (z-order or clip-path issue; lift the
  hovered edges above the cards and anchor on the box edge, not behind it). — *Hovering a
  slice row keeps only the edges incident on it (incoming and its own outgoing, so stance
  edges survive too); the survivors lift above the cards (`svg.top` z-order) and run all the
  way to the row box. Mouse-out restores everything.*

- [x] **Hover-highlight the cited papers.** Hovering a cross-paper claim should highlight the
  paper(s) it points to, so the target container is visible even before its slice is revealed.
  — *Each surviving edge's counterpart — paper card, source stack or synthesis node — lights
  up (`.hl`) for the duration of the hover, whether or not its slice is revealed.*

## Open

- [ ] **Entry-row rule check after real use.** Entry rows = top-level claims + questions.
  On first focus a paper can look sparse (Chen's much-cited `c1` sits one drill below `c3`
  because `c3` builds on it). Deliberate, but revisit once a real paper is curated.

- [ ] **`lit serve`.** PDF hover-preview and click-to-open; the tooltip already stubs
  "PDF preview/open needs `lit serve`". Convenience, not a correctness gap.
