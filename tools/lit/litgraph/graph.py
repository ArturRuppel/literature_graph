"""Pure graph core: load a data repo's YAML, resolve refs, validate (SCHEMA §6),
compute emergent properties (SCHEMA §7). No output/serialization here."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ruamel.yaml import YAML

_yaml = YAML(typ="safe")

_LOCAL = re.compile(r"^[cqm]\d+$")
_CITEKEY = re.compile(r"^[A-Z][A-Za-z]*\d{4}[A-Za-z]")  # <Family><Year><Venue>; no $ — venue varies in length


@dataclass
class Slice:
    id: str                         # "c1" | "q2" | "m3"
    kind: str                       # "claim" | "question" | "method"
    text: str
    grounded_in: list[str] = field(default_factory=list)
    leads_to: list[str] = field(default_factory=list)
    corroborates: list[str] = field(default_factory=list)
    contradicts: list[str] = field(default_factory=list)
    answers: list[str] = field(default_factory=list)
    floor_flag: bool = False        # authored `floor: true` (claim axiom)
    quote: str | None = None
    # computed (filled by build_graph in a later task):
    is_floor: bool = False
    grounded: bool = False
    borrowed: bool = False
    answered: bool = False
    color: str = ""


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
    authors: list[tuple[str, str, bool]] = field(default_factory=list)  # (name, position, corresponding)
    slices: list[Slice] = field(default_factory=list)
    head: list[str] = field(default_factory=list)                 # top-altitude claim texts


@dataclass
class BroadNode:
    slug: str
    kind: str                       # "broad claim" | "broad question" | "broad method"
    text: str
    # computed (filled by build_graph in a later task):
    support: int = 0
    contradict: int = 0


@dataclass
class Graph:
    papers: dict[str, Paper]        # curated papers AND stubs (stubs: curated=False, no slices)
    broad: dict[str, BroadNode]
    order: list[str]                # paper citekeys, landing-list order


class BuildError(Exception):
    """Raised on any SCHEMA §6 validation failure. Message names the offending ref/id."""


_SLICE_GROUPS = {"claims": "claim", "questions": "question", "methods": "method"}


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
        floor_flag=bool(raw.get("floor", False)),
        quote=raw.get("quote"),
    )


def _authors_from(raw: dict) -> list[tuple[str, str, bool]]:
    out: list[tuple[str, str, bool]] = []
    for a in raw.get("authors", []) or []:
        out.append((a["name"], a.get("position", "middle"), bool(a.get("corresponding", False))))
    return out


def load_repo(root: Path) -> tuple[dict[str, Paper], dict[str, BroadNode]]:
    """Parse curated/*.yaml, claims|questions|methods/*.yaml, and stubs.yaml into
    Papers (curated + stubs) and BroadNodes. No validation/computation yet."""
    root = Path(root)
    papers: dict[str, Paper] = {}

    for f in sorted((root / "curated").glob("*.yaml")):
        raw = _yaml.load(f.read_text()) or {}
        citekey = f.stem
        slices: list[Slice] = []
        for group, kind in _SLICE_GROUPS.items():
            for s in raw.get(group, []) or []:
                slices.append(_slice_from(s, kind))
        papers[citekey] = Paper(
            citekey=citekey, curated=True,
            title=raw.get("title", ""), type=raw.get("type", "original"),
            year=raw.get("year"), pass_=raw.get("pass"),
            doi=raw.get("doi"), note=raw.get("note"),
            authors=_authors_from(raw), slices=slices,
        )

    stubs_path = root / "stubs.yaml"
    if stubs_path.exists():
        for citekey, raw in (_yaml.load(stubs_path.read_text()) or {}).items():
            raw = raw or {}
            if citekey in papers:
                raise BuildError(f"{citekey} is both curated and a stub (SCHEMA §6.3)")
            papers[citekey] = Paper(
                citekey=citekey, curated=False,
                title=raw.get("title", ""), type=raw.get("type", "original"),
                year=raw.get("year"), doi=raw.get("doi"),
            )

    broad: dict[str, BroadNode] = {}
    for group, kind in (("claims", "broad claim"), ("questions", "broad question"),
                        ("methods", "broad method")):
        for f in sorted((root / group).glob("*.yaml")):
            raw = _yaml.load(f.read_text()) or {}
            broad[f.stem] = BroadNode(slug=f.stem, kind=kind, text=raw.get("text", ""))
    return papers, broad


def classify_ref(ref: str) -> str:
    """Classify an edge ref by its *form* (SCHEMA §3): local slice, sharpened
    cross-paper slice, container citekey, or broad slug."""
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


def answered_question_ids(papers: dict[str, Paper]) -> set[str]:
    """Global ids (citekey:qN) of questions answered by some claim's `answers` edge."""
    out: set[str] = set()
    for p in papers.values():
        if not p.curated:
            continue
        for s in p.slices:
            if s.kind == "claim":
                for r in s.answers:
                    out.add(_global(p.citekey, r))
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


_EDGE_FIELDS = ("grounded_in", "leads_to", "corroborates", "contradicts", "answers")


def validate(papers: dict[str, Paper], broad: dict[str, BroadNode]) -> None:
    """Enforce the SCHEMA §6 rules the build can check structurally: unique local ids,
    no dangling refs. Raises BuildError naming the offender. (Quote integrity and full
    cross-paper acyclicity are out of v1 scope; same-paper cycles are caught by
    reaches_floor's seen-set, not here.)"""
    for ck, p in papers.items():
        local_ids: set[str] = set()
        for s in p.slices:
            if s.id in local_ids:
                raise BuildError(f"{ck}: duplicate local id {s.id!r}")
            local_ids.add(s.id)

    broad_slugs = set(broad)
    for ck, p in papers.items():
        local_ids = {s.id for s in p.slices}
        for s in p.slices:
            for field_name in _EDGE_FIELDS:
                for r in getattr(s, field_name):
                    if not _ref_resolves(r, local_ids, broad_slugs, papers):
                        raise BuildError(
                            f"{ck}:{s.id} {field_name} -> dangling ref {r!r}")


def _ref_resolves(ref, local_ids, broad_slugs, papers) -> bool:
    kind = classify_ref(ref)
    if kind == "local":
        return ref in local_ids
    if kind == "broad":
        return ref in broad_slugs
    if kind == "container":
        return ref in papers
    # sharpened "Citekey:id"
    base = ref.split(":", 1)[0]
    return base in papers


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
