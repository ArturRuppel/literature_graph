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
