"""Pure graph core: load a data repo's YAML, resolve refs, validate (SCHEMA §6),
compute emergent properties (SCHEMA §7). No output/serialization here."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from .topics import Topic, load_topics, validate_topics

_yaml = YAML(typ="safe")

# The one specific trap worth naming on parse failure: a sharpened cross-paper ref
# (`Key2026Journal:c4`) left unquoted inside a flow sequence. store.py's round-trip writer
# now quotes these itself (see store._quote_sharpened_refs), but a hand-edited file can still
# hit this — and when it does, ruamel's own message ("could not find expected ':'" or similar,
# at the *next* token) points nowhere near the fix. The lookbehind/lookahead require the ref
# to sit directly between `[`/`,`/whitespace and `,`/`]` with nothing else adjacent, which is
# exactly what an unquoted flow-sequence element looks like; a quoted ref has a `"` in that
# position instead and never matches, and a bare local id (no `:`) never matches either.
_UNQUOTED_SHARPENED_REF = re.compile(
    r"(?<=[\[,\s])([A-Z][A-Za-z]*\d{4}[A-Za-z][A-Za-z0-9]*:[cqmtk]\d+)(?=[,\]])"
)


def _unquoted_sharpened_ref_hint(path: Path, text: str) -> str | None:
    """If `text` contains the specific trap above, name every offending line; else None so
    the caller falls back to ruamel's own (generic, but still file-named) message."""
    hits = [(n, m.group(1)) for n, line in enumerate(text.splitlines(), start=1)
            for m in _UNQUOTED_SHARPENED_REF.finditer(line)]
    if not hits:
        return None
    detail = "; ".join(
        f'line {n}: unquoted cross-paper ref in a flow sequence — write ["{ref}"], not [{ref}]'
        for n, ref in hits
    )
    return f"{path}: {detail}"


def load_yaml(path: Path) -> dict:
    """Parse one YAML file, or fail with a BuildError that says *which* file.

    ruamel reports the location as `in "<unicode string>", line N` because it is handed
    text, not a path — so a single malformed character anywhere in the repo used to abort
    the whole build with a line number and no filename, which is a bad afternoon.

    Worth knowing about the parser this uses: `typ="safe"` is libyaml, and it is stricter
    than the round-trip parser `store.py` writes with. In particular a sharpened cross-paper
    ref inside a flow sequence — `corroborates: [Key2026Journal:c4]` — round-trips fine but
    is rejected here, because in flow context a plain scalar may not carry a `:`. Quote it
    (`["Key2026Journal:c4"]`) and both agree. The mismatch is why this message matters —
    and why, on failure, we scan for that exact shape before falling back to ruamel's message:
    a curator staring at "could not find expected ':'" has no idea what to fix; a curator
    staring at the offending ref and line does."""
    text = path.read_text()
    try:
        return _yaml.load(text) or {}
    except YAMLError as e:
        hint = _unquoted_sharpened_ref_hint(path, text)
        raise BuildError(hint if hint else f"{path}: {e}") from e


_LOCAL = re.compile(r"^[cqmtk]\d+$")    # c claim · q question · m method · t test · k capability
_CITEKEY = re.compile(r"^[A-Z][A-Za-z]*\d{4}[A-Za-z]")  # <Family><Year><Venue>; no $ — venue varies in length


@dataclass
class Slice:
    id: str                         # "c1" | "q2" | "m3" | "t1" | "k1"
    kind: str                       # "claim" | "question" | "method" | "test" | "capability"
    text: str
    grounded_in: list[str] = field(default_factory=list)
    leads_to: list[str] = field(default_factory=list)
    corroborates: list[str] = field(default_factory=list)
    contradicts: list[str] = field(default_factory=list)
    answers: list[str] = field(default_factory=list)
    # programme edges (programme design §3) — authored on a Test only
    discriminates: list[str] = field(default_factory=list)  # ≥2 claims this test separates
    enabled_by: list[str] = field(default_factory=list)     # feasibility axis → capabilities
    floor_flag: bool = False        # authored `floor: true` (claim axiom)
    quote: str | None = None
    quote_display: str | None = None  # polished for the viewer (quotes.polish_graph); anchor unchanged
    quote_loc: dict | None = None     # authored PDF anchor: {page:int, rects:[[x0,y0,x1,y1],...]}
                                      # rects are fractions (0..1) of the page — DPI-independent
    # computed (filled by build_graph in a later task):
    is_floor: bool = False
    grounded: bool = False
    borrowed: bool = False
    answered: bool = False
    color: str = ""
    # computed, programme slices only (programme design §8; filled by programme.compute)
    modality: str = ""              # claim: "established" | "proposed" | "speculation"
    load_bearing: bool = False      # claim: has dependents, no test discriminates it
    blast_radius: int = 0           # claim: size of the transitive dependent set
    at_risk: bool = False           # test: some enabled_by capability is aspirational
    aspirational: bool = False      # capability: claimed but not evidenced
    orphan: bool = False            # nothing depends on / uses this slice


@dataclass
class Paper:
    citekey: str
    curated: bool
    title: str
    type: str
    year: int | None
    pass_: int | None = None        # YAML/JSON key is "pass"; "pass" is a Python keyword
    doi: str | None = None
    note: str | None = None
    abstract: str | None = None     # verbatim abstract (written by `lit ingest`)
    journal: str | None = None      # venue display name; stubs carry it, curated fall back to venueFromKey
    authors: list[tuple[str, str, bool]] = field(default_factory=list)  # (name, position, corresponding)
    tags: list[str] = field(default_factory=list)                 # curator labels (curated only; SCHEMA §4)
    slices: list[Slice] = field(default_factory=list)
    head: list[str] = field(default_factory=list)                 # top-altitude claim texts


@dataclass
class BroadNode:
    slug: str
    kind: str                       # "broad claim" | "broad question" | "broad method"
    text: str
    title: str = ""                 # optional at-a-glance name; viewer falls back to `text`
    # generalizes further up the ladder (SCHEMA §4): a broad claim into a broader one, same
    # kind, `leads-to`'s broad-to-broad half. The claim ladder's own altitude, on top of the
    # slice-to-broad altitude `leads_to` already carries one level down.
    leads_to: list[str] = field(default_factory=list)
    # computed (filled by build_graph in a later task):
    support: int = 0
    contradict: int = 0


@dataclass
class Aim:
    """A programme container (programme design §4) — the unit of curation for proposed work.
    Kept out of `Graph.papers` on purpose: an aim is not a paper, and the viewer's
    paper-centric emit layer must not have to pretend otherwise."""

    slug: str                       # includes the sigil, e.g. "@fluid-solid-switch"
    title: str
    note: str | None = None
    tags: list[str] = field(default_factory=list)
    slices: list[Slice] = field(default_factory=list)

    @property
    def citekey(self) -> str:
        """The emit layer keys every container by `citekey`; for an aim that is its slug,
        so the edge helpers in build.py work on aims without a second code path."""
        return self.slug


@dataclass
class Graph:
    papers: dict[str, Paper]        # curated papers AND stubs (stubs: curated=False, no slices)
    broad: dict[str, BroadNode]
    order: list[str]                # paper citekeys, landing-list order
    aims: dict[str, Aim] = field(default_factory=dict)   # keyed by "@slug"; empty on a pure literature repo
    # The topic axis (SCHEMA §9) rides along so it is loaded and validated once, at build.
    # It is NOT graph: no edge targets it, no emergent property reads it, and the emit layer
    # ignores it. Membership is derived from paper `tags` on demand — see topics.papers_in.
    topics: dict[str, "Topic"] = field(default_factory=dict)


class BuildError(Exception):
    """Raised on any SCHEMA §6 validation failure. Message names the offending ref/id."""


_SLICE_GROUPS = {"claims": "claim", "questions": "question", "methods": "method"}
# An aim may additionally hold tests and capabilities; a paper may not (programme design §2).
_AIM_SLICE_GROUPS = {**_SLICE_GROUPS, "tests": "test", "capabilities": "capability"}


def _slice_from(raw: dict, kind: str) -> Slice:
    return Slice(
        id=raw["id"],
        kind=kind,
        text=raw.get("text", ""),
        grounded_in=list(raw.get("grounded_in", []) or []),
        leads_to=list(raw.get("leads_to", []) or []),
        corroborates=list(raw.get("corroborates", []) or []),
        contradicts=list(raw.get("contradicts", []) or []),
        answers=list(raw.get("answers", []) or []),
        discriminates=list(raw.get("discriminates", []) or []),
        enabled_by=list(raw.get("enabled_by", []) or []),
        floor_flag=bool(raw.get("floor", False)),
        quote=raw.get("quote"),
        quote_loc=raw.get("quote_loc"),
    )


def _authors_from(raw: dict) -> list[tuple[str, str, bool]]:
    out: list[tuple[str, str, bool]] = []
    for a in raw.get("authors", []) or []:
        out.append((a["name"], a.get("position", "middle"), bool(a.get("corresponding", False))))
    return out


def paper_from_raw(citekey: str, raw: dict) -> Paper:
    """Build a curated Paper from a parsed curated/<citekey>.yaml mapping. Shared by
    load_repo and the `lit preview` scratch overlay so both read a paper identically."""
    raw = raw or {}
    for group in ("tests", "capabilities"):
        if raw.get(group):
            raise BuildError(f"{citekey}: `{group}` belongs to an aim, not a paper "
                             "(programme design §2) — a paper records what was measured, "
                             "not what is planned")
    slices: list[Slice] = []
    for group, kind in _SLICE_GROUPS.items():
        for s in raw.get(group, []) or []:
            slices.append(_slice_from(s, kind))
    return Paper(
        citekey=citekey, curated=True,
        title=raw.get("title", ""), type=raw.get("type", "original"),
        year=raw.get("year"), pass_=raw.get("pass"),
        doi=raw.get("doi"), note=raw.get("note"), abstract=raw.get("abstract"),
        authors=_authors_from(raw), tags=list(raw.get("tags", []) or []), slices=slices,
    )


def load_repo(root: Path) -> tuple[dict[str, Paper], dict[str, BroadNode]]:
    """Parse curated/*.yaml, claims|questions|methods/*.yaml, and stubs.yaml into
    Papers (curated + stubs) and BroadNodes. No validation/computation yet."""
    root = Path(root)
    papers: dict[str, Paper] = {}

    for f in sorted((root / "curated").glob("*.yaml")):
        papers[f.stem] = paper_from_raw(f.stem, load_yaml(f))

    stubs_path = root / "stubs.yaml"
    if stubs_path.exists():
        for citekey, raw in load_yaml(stubs_path).items():
            raw = raw or {}
            if citekey in papers:
                raise BuildError(f"{citekey} is both curated and a stub (SCHEMA §6.3)")
            papers[citekey] = Paper(
                citekey=citekey, curated=False,
                title=raw.get("title", ""), type=raw.get("type", "original"),
                year=raw.get("year"), doi=raw.get("doi"),
                journal=raw.get("journal"),
                # stub authors are byline-order names only (no position/corresponding known
                # without the PDF); carry them in the shared tuple shape so authLine renders them
                authors=[(n, "", False) for n in (raw.get("authors") or [])],
            )

    broad: dict[str, BroadNode] = {}
    for group, kind in (("claims", "broad claim"), ("questions", "broad question"),
                        ("methods", "broad method")):
        for f in sorted((root / group).glob("*.yaml")):
            raw = load_yaml(f)
            broad[f.stem] = BroadNode(slug=f.stem, kind=kind, text=raw.get("text", ""),
                                      title=raw.get("title", ""),
                                      leads_to=list(raw.get("leads_to", []) or []))
    return papers, broad


def aim_from_raw(slug: str, raw: dict) -> Aim:
    """Build an Aim from a parsed programme/aims/<slug>.yaml mapping. Shared by
    load_programme and the `lit preview` scratch overlay, so both read an aim identically."""
    raw = raw or {}
    slices: list[Slice] = []
    for group, kind in _AIM_SLICE_GROUPS.items():
        for s in raw.get(group, []) or []:
            slices.append(_slice_from(s, kind))
    if not slug.startswith("@"):
        slug = f"@{slug}"
    return Aim(slug=slug, title=raw.get("title", ""), note=raw.get("note"),
               tags=list(raw.get("tags", []) or []), slices=slices)


def load_programme(root: Path) -> dict[str, Aim]:
    """Parse programme/aims/*.yaml into Aims, keyed by their sigil'd slug ("@<stem>").
    Returns {} when the repo has no programme tree (a pure literature repo)."""
    root = Path(root)
    aims: dict[str, Aim] = {}
    for f in sorted((root / "programme" / "aims").glob("*.yaml")):
        aim = aim_from_raw(f.stem, load_yaml(f))
        aims[aim.slug] = aim
    return aims


def classify_ref(ref: str) -> str:
    """Classify an edge ref by its *form* (SCHEMA §3, programme design §5): local slice,
    sharpened cross-container slice, container (citekey or "@aim"), or broad slug.

    The "@" sigil is what keeps a programme container distinguishable from a broad slug —
    both are kebab-case. Beyond that disambiguation, an aim ref classifies exactly like a
    paper ref, so every downstream consumer treats containers uniformly."""
    if ref.startswith("@"):
        return "sharpened" if ":" in ref else "container"
    if ":" in ref:
        return "sharpened"
    if _LOCAL.match(ref):
        return "local"
    if _CITEKEY.match(ref):
        return "container"
    return "broad"


def method_is_floor(s: Slice) -> bool:
    """A method is a floor iff it grounds only in containers (source papers) — i.e. it
    layers on no other method. A model has a local method ref in grounded_in (SCHEMA §7)."""
    return not any(classify_ref(r) == "local" for r in s.grounded_in)


def claim_is_borrowed(s: Slice) -> bool:
    """Borrowed (restated) iff grounded_in reaches a cross-paper container (CONCEPT §6.1)."""
    return any(classify_ref(r) in ("container", "sharpened") for r in s.grounded_in)


def _global(citekey: str, ref: str) -> str:
    """Resolve a same-paper local ref to its global id; pass sharpened refs through."""
    return f"{citekey}:{ref}" if classify_ref(ref) == "local" else ref


def answered_question_ids(papers: dict[str, Paper],
                          aims: dict[str, Aim] | None = None) -> set[str]:
    """Global ids (citekey:qN / @aim:qN) of questions answered by some claim's `answers`
    edge. Aims participate on equal footing — a programme claim may answer a programme
    question, or a paper's."""
    out: set[str] = set()
    for p in papers.values():
        if not p.curated:
            continue
        for s in p.slices:
            if s.kind == "claim":
                for r in s.answers:
                    out.add(_global(p.citekey, r))
    for a in (aims or {}).values():
        for s in a.slices:
            if s.kind == "claim":
                for r in s.answers:
                    out.add(_global(a.slug, r))
    return out


def broad_meter(slug: str, papers: dict[str, Paper]) -> tuple[int, int]:
    """v1 meter (spec §3): a broad claim is itself a claim, so lateral edges may target its
    slug directly (SCHEMA §6 allows "a claim"). support = #claims that generalize into it
    (leads_to) or corroborate it; contradict = #claims that contradict it."""
    support = 0
    contradict = 0
    for p in papers.values():
        for s in p.slices:
            if s.kind != "claim":
                continue
            if slug in s.leads_to or slug in s.corroborates:
                support += 1
            if slug in s.contradicts:
                contradict += 1
    return support, contradict


_EDGE_FIELDS = ("grounded_in", "leads_to", "corroborates", "contradicts", "answers",
                "discriminates", "enabled_by")

_BROAD_KIND = {"claim": "broad claim", "question": "broad question", "method": "broad method"}

# Test and Capability have no broad tier in v1 (programme design §9.3).
_NO_BROAD = ("test", "capability")


def validate(papers: dict[str, Paper], broad: dict[str, BroadNode],
             aims: dict[str, Aim] | None = None) -> None:
    """Enforce the SCHEMA §6 rules the build can check structurally: unique local ids,
    no dangling refs, kind coherence (§6.6). Raises BuildError naming the offender.
    (Quote integrity (§6.4) is a non-fatal flag, checked against the `.md` full text in
    quotes.polish_graph — it can't run here since this core reads only YAML. Full
    cross-paper acyclicity is out of v1 scope; same-paper cycles are caught by
    reaches_floor's seen-set, not here.)

    Aims validate identically to papers — same refs, same kind coherence — plus the
    programme-only rules in `_check_kinds` (programme design §9). The broad tier's own
    `leads_to` (a thin broad slice generalizing into a broader one, SCHEMA §4) is a separate,
    smaller check — `_validate_broad_ladder` — since it lives on BroadNode, not on a Slice."""
    aims = aims or {}
    containers: dict[str, Paper | Aim] = {**papers, **aims}
    if set(papers) & set(aims):
        raise BuildError(f"container id is both a paper and an aim: {sorted(set(papers) & set(aims))}")

    for ck, c in containers.items():
        local_ids: set[str] = set()
        for s in c.slices:
            if s.id in local_ids:
                raise BuildError(f"{ck}: duplicate local id {s.id!r}")
            local_ids.add(s.id)

    broad_slugs = set(broad)
    for ck, c in containers.items():
        local_ids = {s.id for s in c.slices}
        by_id = {t.id: t for t in c.slices}
        for s in c.slices:
            # Authoring-site rules first: they hold whether or not the ref resolves, and
            # their messages point at the right fix.
            _check_programme_kinds(ck, s, by_id)
            for field_name in _EDGE_FIELDS:
                for r in getattr(s, field_name):
                    if not _ref_resolves(r, local_ids, broad_slugs, containers):
                        raise BuildError(
                            f"{ck}:{s.id} {field_name} -> dangling ref {r!r}")
            _check_kinds(ck, s, broad, by_id)

    _validate_broad_ladder(broad)


def _validate_broad_ladder(broad: dict[str, BroadNode]) -> None:
    """The broad tier's own half of `leads-to` (SCHEMA §4/§6): a thin broad slice's
    `leads_to` generalizes it into a broader one, one rung up the same ladder a slice's
    `leads_to` climbs into the broad tier from below. The same two structural rules apply
    here, one level up: the target must resolve and be the **same kind** (§6.6 — a broad
    claim ladders into a broad claim, never into a broad question or method), and the
    broad-to-broad graph must be **acyclic** (§6.5)."""
    for slug, b in broad.items():
        for r in b.leads_to:
            if r not in broad:
                raise BuildError(f"{slug} leads_to -> unknown broad slug {r!r}")
            if broad[r].kind != b.kind:
                raise BuildError(f"{slug} leads_to -> {r!r} is a {broad[r].kind}; "
                                 f"a {b.kind} generalizes into a {b.kind}")

    state: dict[str, int] = {}          # 0 = visiting, 1 = done

    def walk(slug: str, path: list[str]) -> None:
        if state.get(slug) == 1:
            return
        if state.get(slug) == 0:
            cycle = path[path.index(slug):] + [slug]
            raise BuildError(f"broad leads_to cycle: {' -> '.join(cycle)}")
        state[slug] = 0
        for r in broad[slug].leads_to:
            walk(r, path + [slug])
        state[slug] = 1

    for slug in broad:
        walk(slug, [])


def _target_id(ref: str, kind: str) -> str:
    """The slice-id part of a local/sharpened ref (its kind is readable off the prefix)."""
    return ref.split(":", 1)[1] if kind == "sharpened" else ref


def _check_programme_kinds(ck: str, s: Slice, by_id: dict[str, Slice]) -> None:
    """The programme-only half of kind coherence (programme design §9.1–9.4)."""
    for field_name in ("discriminates", "enabled_by"):
        if getattr(s, field_name) and s.kind != "test":
            raise BuildError(f"{ck}:{s.id} {field_name} is authored on a test, "
                             f"not on a {s.kind}")

    if s.kind in _NO_BROAD:
        for field_name in ("answers", "corroborates", "contradicts"):
            if getattr(s, field_name):
                raise BuildError(f"{ck}:{s.id} {field_name} is not valid on a {s.kind}")
        if s.leads_to:
            raise BuildError(f"{ck}:{s.id} leads_to is not valid on a {s.kind} "
                             "(no broad tests/capabilities in v1)")
        if s.floor_flag:
            raise BuildError(f"{ck}:{s.id} floor: true is only valid on a claim "
                             "(a test's hollow-floor status is emergent, never authored)")

    if s.kind != "test":
        return

    if s.discriminates and len(s.discriminates) < 2:
        raise BuildError(
            f"{ck}:{s.id} discriminates -> {s.discriminates[0]!r} alone: a test that "
            "separates nothing is plain grounding — author it as that claim's "
            "`grounded_in: " + s.id + "` instead")
    for r in s.discriminates:
        kind = classify_ref(r)
        if kind in ("local", "sharpened") and not _target_id(r, kind).startswith("c"):
            raise BuildError(f"{ck}:{s.id} discriminates -> {r!r} does not target a claim")
    for r in s.enabled_by:
        kind = classify_ref(r)
        if kind not in ("local", "sharpened"):
            raise BuildError(f"{ck}:{s.id} enabled_by -> {r!r} must name a capability slice")
        if not _target_id(r, kind).startswith("k"):
            raise BuildError(f"{ck}:{s.id} enabled_by -> {r!r} is not a capability")


def _check_kinds(ck: str, s: Slice, broad: dict[str, BroadNode],
                 by_id: dict[str, Slice]) -> None:
    """SCHEMA §6.6 kind coherence, structurally: `leads_to` targets a same-kind broad slug
    *or* a same-kind local slice (a same-paper generalization ladder — a specific claim
    laddering up into a broader local claim). A cross-paper ref here has no home (it would
    mis-render as a synthesis node) — author cross-paper support as `grounded_in` on the
    derived slice. `answers` targets a question (a container ref is the un-sliced wildcard,
    allowed); laterals target a claim or a container; `floor: true` marks only a claim.
    Refs are known to resolve already.

    Programme rules (programme design §9): `discriminates` and `enabled_by` are authored on
    a Test only; `discriminates` needs **≥2** claims (one target is plain grounding, and the
    error says so); `enabled_by` targets a capability; Test/Capability have no broad tier."""
    if s.kind in _NO_BROAD:
        return                              # already fully checked in _check_programme_kinds
    want = _BROAD_KIND[s.kind]
    for r in s.leads_to:
        kind = classify_ref(r)
        if kind in ("container", "sharpened"):
            raise BuildError(f"{ck}:{s.id} leads_to -> {r!r} is a cross-paper ref "
                             "(author cross-paper support as grounded_in, not leads_to)")
        if kind == "local":
            if by_id[r].kind != s.kind:
                raise BuildError(f"{ck}:{s.id} leads_to -> {r!r} is a {by_id[r].kind}; "
                                 f"a {s.kind} generalizes into a {s.kind}")
            continue
        if broad[r].kind != want:               # broad slug
            raise BuildError(f"{ck}:{s.id} leads_to -> {r!r} is a {broad[r].kind}; "
                             f"a {s.kind} generalizes into a {want}")
    for r in s.answers:
        kind = classify_ref(r)
        if kind == "broad" and broad[r].kind != "broad question":
            raise BuildError(f"{ck}:{s.id} answers -> {r!r} is a {broad[r].kind}, "
                             "not a question")
        if kind in ("local", "sharpened") and not _target_id(r, kind).startswith("q"):
            raise BuildError(f"{ck}:{s.id} answers -> {r!r} does not target a question")
    for field_name in ("corroborates", "contradicts"):
        for r in getattr(s, field_name):
            kind = classify_ref(r)
            if kind == "broad" and broad[r].kind != "broad claim":
                raise BuildError(f"{ck}:{s.id} {field_name} -> {r!r} is a "
                                 f"{broad[r].kind}, not a claim")
            if kind in ("local", "sharpened") and not _target_id(r, kind).startswith("c"):
                raise BuildError(f"{ck}:{s.id} {field_name} -> {r!r} does not target a claim")
    if s.floor_flag and s.kind != "claim":
        raise BuildError(f"{ck}:{s.id} floor: true is only valid on a claim (SCHEMA §6.6)")


def _ref_resolves(ref, local_ids, broad_slugs, containers) -> bool:
    """`containers` holds papers *and* aims (aims keyed by "@slug"), so a programme ref
    resolves through the same two branches a paper ref does (programme design §5)."""
    kind = classify_ref(ref)
    if kind == "local":
        return ref in local_ids
    if kind == "broad":
        return ref in broad_slugs
    if kind == "container":
        return ref in containers
    # sharpened "Citekey:id" / "@aim:id"
    base = ref.split(":", 1)[0]
    return base in containers


def reaches_floor(s: Slice, by_id: dict[str, Slice], seen: set[str] | None = None) -> bool:
    """Does this slice's downward (grounded_in) chain reach a floor — a method floor or a
    `floor: true` claim? Only local refs are walkable; cross-paper refs are opaque here."""
    seen = set() if seen is None else seen
    if s.id in seen:
        return False
    seen.add(s.id)
    if s.kind == "method" and s.is_floor:
        return True
    if s.kind == "claim" and s.floor_flag:
        return True
    for r in s.grounded_in:
        if classify_ref(r) != "local":
            continue
        t = by_id.get(r)
        if t is not None and reaches_floor(t, by_id, seen):
            return True
    return False


def _slice_color(s: Slice) -> str:
    """Map a slice's kind + computed state to its display color (SCHEMA §7):
    question; method floor/model; claim borrowed/grounded/plausible."""
    if s.kind == "question":
        return "question"
    if s.kind == "method":
        return "floor" if s.is_floor else "model"
    # claim
    if s.borrowed:
        return "borrowed"
    return "grounded" if s.grounded else "plausible"


def _order(papers: dict[str, Paper]) -> list[str]:
    """Landing-list order: curated (by pass desc, year desc, citekey) before stubs
    (year desc, citekey). A missing `pass` encodes as -1 so it sorts last among curated."""
    curated = [p for p in papers.values() if p.curated]
    stubs = [p for p in papers.values() if not p.curated]
    curated.sort(key=lambda p: (
        -(p.pass_ if p.pass_ is not None else -1), -(p.year or 0), p.citekey))
    stubs.sort(key=lambda p: (-(p.year or 0), p.citekey))
    return [p.citekey for p in curated] + [p.citekey for p in stubs]


def compute_emergent(papers: dict[str, Paper], broad: dict[str, BroadNode],
                     aims: dict[str, Aim] | None = None) -> Graph:
    """Fill emergent properties (SCHEMA §7) + order on already-loaded, already-validated
    papers/broad, returning the Graph. Split from build_graph so `lit preview` can overlay
    a scratch paper between load and compute without re-reading the repo.

    Programme properties (programme design §8) are a second pass, delegated to
    `programme.compute` so this module stays the literature core."""
    aims = aims or {}
    answered = answered_question_ids(papers, aims)

    for p in papers.values():
        by_id = {s.id: s for s in p.slices}
        # Phase 1: set is_floor (methods + floor_flag axioms) — must precede Phase 2.
        for s in p.slices:
            if s.kind == "method":
                s.is_floor = method_is_floor(s)
            elif s.kind == "claim" and s.floor_flag:
                s.is_floor = True
        # Phase 2: emergent grounded/borrowed/answered + color (reads is_floor).
        for s in p.slices:
            if s.kind == "claim":
                s.borrowed = claim_is_borrowed(s)
                s.grounded = reaches_floor(s, by_id)
            elif s.kind == "question":
                s.answered = f"{p.citekey}:{s.id}" in answered
            s.color = _slice_color(s)
        p.head = [s.text for s in p.slices if s.kind == "claim" and not s.leads_to]

    for slug, b in broad.items():
        if b.kind == "broad claim":
            b.support, b.contradict = broad_meter(slug, papers)

    g = Graph(papers=papers, broad=broad, order=_order(papers), aims=aims)
    if aims:
        from .programme import compute as compute_programme
        compute_programme(g)
    return g


def build_graph(root) -> Graph:
    """Load -> validate -> compute emergent properties -> order. The pure core."""
    root = Path(root)
    papers, broad = load_repo(root)
    aims = load_programme(root)
    validate(papers, broad, aims)
    g = compute_emergent(papers, broad, aims)
    # The topic axis is loaded and validated here so every `lit build` checks it, but it is
    # deliberately the last step and touches nothing above it (SCHEMA §9).
    g.topics = load_topics(root)
    validate_topics(g.topics, set(broad))
    return g
