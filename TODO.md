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

- [x] **`lit serve`.** PDF hover-preview and click-to-open; the tooltip already stubs
  "PDF preview/open needs `lit serve`". Convenience, not a correctness gap. — *`lit serve
  [--root] [--port] [--pdf-dir]`: the viewer on loopback, rebuilt from the YAML on every
  refresh (edit → refresh is the curation loop; a broken edit returns the BuildError as a
  500 and the server survives). Over HTTP the tooltip upgrades: `pdfs.json` lists which
  citekeys have a PDF in `pdf_dir` (config.toml, else `<root>/pdfs`), hovering shows the
  first page rendered server-side (`/preview/<citekey>.png`, mtime-cached — an `<img>`
  previews everywhere, unlike embedding a PDF), and clicking the preview opens
  `/pdf/<citekey>.pdf` (flat `<citekey>.<ext>` names only — no traversal). The `lit build`
  file:// output stays inert as before.*

- [x] **Viewer polish (post-`lit serve` review).** — *(1) Edges paint above the cards
  unconditionally (`svg#edges` z-index), so an arrow reaches the target row/box without
  hovering — hover-isolation now only disentangles. (2) The tooltip is pinned beside the
  hovered card (right, flipping left on overflow) instead of following the cursor, so the
  pointer can travel into the PDF preview and click it. (3) The tooltip shows the paper's
  abstract, not the curator note: `abstract` is a new curated-YAML field, written by `lit
  ingest` (OpenAlex inverted-index de-inverted / Crossref JATS stripped), plumbed through
  `graph` → `build` (`abs`) → tooltip. (4) Hovering a broad synthesis node isolates its
  incident edges and highlights the papers linked into it — the same treatment as hovering
  a slice row (limited to focused papers, since a paper's outgoing edges exist only once
  it's focused).*

## Open

- [ ] **Entry-row rule check after real use.** Entry rows = top-level claims + questions.
  On first focus a paper can look sparse (Chen's much-cited `c1` sits one drill below `c3`
  because `c3` builds on it). Deliberate, but revisit once a real paper is curated.

# TODO — `tools/lit` maintainability

From the 2026-07-03 maintainability review (`docs/2026-07-03-maintainability-review.md`); the
applied cleanups landed in PR #6. These are the proposed larger moves, left for review per the
repo's *propose, don't impose* rule. Ordered high→low leverage.

- [ ] **Collapse the two serving layers behind one endpoint core.** `serve.py`'s stdlib
  `_Handler` and the Flask ELN plugin implement the same ~11 endpoints twice — same paths,
  regexes, error→status mapping (~150 lines apiece) — and that routing/validation layer is
  exactly where they'll silently drift (the ELN side has *no test coverage* in this repo). Lift
  a framework-neutral `viewer/endpoints.py` (frozen `Request`/`Response` dataclasses, a ~15-line
  `Router` with validation regexes baked into route patterns, a `dispatch()` owning the error
  policy); each server becomes a thin bytes-in/bytes-out shim (stdlib `_run(method)`; Flask
  catch-all Blueprint). Payoff: the whole HTTP surface becomes socket-free unit-testable, so the
  offline-deterministic test rule finally covers it. **Trigger: do this when the endpoint set
  next grows** — a few hundred lines reorganized across two files, one currently untested.

- [ ] **Atomic, race-safe quote-loc writes.** `store.write_quote_loc[s]` does read→parse→mutate→
  dump straight onto the target, and `_Server` is threaded — two concurrent `POST /quote_loc`
  for one citekey could lose an update, and a crash mid-`dump` truncates the YAML. Near-impossible
  for a single-curator loopback tool (low priority), but cheap once the endpoint core above lands:
  a module-level `threading.Lock` around the read-modify-write + temp-file `os.replace`. Fold into
  the item above.

- [ ] **De-dup the viewer's two PDF-window mounts.** `template.html`'s `mountPage` and `mountDoc`
  share ~40 near-verbatim lines (the `zoomTo` closure, ctrl/⌘-wheel zoom, pointer-drag pan, the
  `.pw-tools` toggle, highlight-rect placement, the selectable text layer). Extract
  `wirePanZoom` / `addHighlights` / `buildTextLayer`; both mounts shrink to their layout
  difference. No behavior change — but the viewer has no automated tests, so it needs a manual
  `lit serve` pass.

- [ ] **One polite HTTP-JSON client for OpenAlex + Crossref.** `sources/openalex.py` and
  `sources/crossref.py` carry byte-identical `__init__` / `_http_get_json` (mailto append,
  session, 3-try backoff, 404→`{}`), differing only in a `RuntimeError` message. Lift a shared
  `_PoliteJsonClient` base (or a free `polite_get_json(...)`). ~30 duplicated lines → one; the
  path is `# pragma: no cover` (network), so verify by hand or add an injected-`get_json` test.

- [ ] **One DOI-prefix helper.** Three near-identical strippers: `citekey._norm_doi`
  (strip+lowercase) and `openalex._strip_doi` / `crossref._strip_doi` (strip, case-preserving,
  byte-identical to each other). Consolidate to `doi.strip_prefix()` (case-preserving) with
  `normalize = strip_prefix().lower()` on top. Small, but kills a fix-it-in-three-places trap.

- [ ] **Centralize the `pdf_dir` default.** `cfg.pdf_dir or cfg.root / "pdfs"` is spelled out
  ~5 times (three in `cli.py`, once in serve wiring, once in the ELN plugin). A
  `Config.pdf_dir_or_default` property puts the policy in one place.
