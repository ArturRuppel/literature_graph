"""The narrative layer (programme design §7) — one linearization of the programme into a
grant application's sections. Pure ordering: it carries no edges into the slice graph, no
emergent property reads it, and deleting it changes nothing about `papers` / `broad` /
`g.aims`' own computed state (SCHEMA §7 is exactly as untouched as it was before this axis
existed) — the same non-interference topics.py already holds for the keyword axis.

**One deliberate extension beyond design §7.** The design's `{section -> [refs]}` shape can
name evidence but cannot hold the argument: it has no field to ask "does this section assert
something the graph doesn't support" or "is anything load-bearing missing from the text"
against, because there is no *text* to check that against — a bare ref list is a citation
list, not a sentence. So a section here is a list of **bullets**, and a bullet is
`{text, refs}`: `text` is the curator's own plain-language sentence (the thing that would
actually appear in the grant), `refs` is what backs it. This is the aim schema's own idiom
one level up — a claim's `text` is the assertion and its `grounded_in` is the backing; a
narrative bullet is the same shape, just outside the slice graph. The two coverage questions
above are future queries over this field, not built here (programme design §10's own
"ship the model and the queries first, viewer later" applies again) — this module only
loads and validates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .graph import BuildError, Graph, classify_ref, load_yaml


@dataclass
class Bullet:
    text: str
    refs: list[str] = field(default_factory=list)   # fully-qualified refs only — see _resolves


@dataclass
class Section:
    title: str
    bullets: list[Bullet] = field(default_factory=list)


@dataclass
class Narrative:
    grant: str                       # filename stem — programme/narrative/<grant>.yaml
    title: str | None = None
    page_budget: float | None = None
    sections: list[Section] = field(default_factory=list)


def _bullet_from(raw: dict) -> Bullet:
    return Bullet(text=raw.get("text", ""), refs=list(raw.get("refs", []) or []))


def _section_from(raw: dict) -> Section:
    return Section(title=raw.get("title", ""),
                   bullets=[_bullet_from(b) for b in (raw.get("bullets", []) or [])])


def narrative_from_raw(grant: str, raw: dict) -> Narrative:
    """Build a Narrative from a parsed programme/narrative/<grant>.yaml mapping."""
    raw = raw or {}
    return Narrative(grant=grant, title=raw.get("title"), page_budget=raw.get("page_budget"),
                     sections=[_section_from(s) for s in (raw.get("sections", []) or [])])


def load_narratives(root) -> dict[str, Narrative]:
    """Parse programme/narrative/*.yaml. Returns {} when the repo has no narrative tree — the
    axis is optional, exactly as programme/aims/ and topics/ are.

    Reuses `graph.load_yaml` rather than a plain parse (the way topics.py does): a narrative
    bullet's `refs` carries the same sharpened cross-container forms (`@aim:c1`,
    `Key2026Journal:c4`) an aim's edges do, so it is exposed to the identical
    unquoted-ref-in-a-flow-sequence trap load_yaml's docstring explains — and that guard
    only fires on a field it recognizes (see graph._REF_FIELD_FLOW, which lists `refs`
    alongside the slice edge fields for exactly this reason)."""
    root = Path(root)
    out: dict[str, Narrative] = {}
    for f in sorted((root / "programme" / "narrative").glob("*.yaml")):
        out[f.stem] = narrative_from_raw(f.stem, load_yaml(f))
    return out


def _short(text: str, n: int = 60) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _resolves(ref: str, g: Graph) -> bool:
    """Whether a narrative ref resolves against the already-built graph.

    Stricter than an authored slice's own edges (`graph._ref_resolves`): a curated slice's
    `grounded_in`/etc. may sharpen ahead of curation — `Stub2019Conf:q1` is legal while
    `Stub2019Conf` is still un-sliced, the container wildcard resting until promotion (CONCEPT
    §2). A narrative bullet is not a frontier marker; it is citing a finished argument, so a
    sharpened ref here must name a slice that actually exists — `base:tid` where `tid` is a
    real id on that container, not merely a container that exists. `local` never resolves: a
    narrative file is not itself a container, so a bare `c1` has no "same file" to be local
    *to* — see validate_narratives for the message that explains this to a curator."""
    kind = classify_ref(ref)
    if kind == "local":
        return False
    if kind == "broad":
        return ref in g.broad
    if kind == "container":
        return ref in g.papers or ref in g.aims
    # sharpened: "base:tid" — the container must exist AND hold that exact slice id.
    base, _, tid = ref.partition(":")
    container = g.papers.get(base) or g.aims.get(base)
    if container is None:
        return False
    return any(s.id == tid for s in container.slices)


def validate_narratives(narratives: dict[str, Narrative], g: Graph) -> None:
    """Every bullet ref must resolve (programme design §5: papers, sharpened slices, broad
    slugs, `@aim` and `@aim:slice`) — a dangling one is a BuildError naming the file, the
    section and the bullet, exactly as a dangling slice ref names its container and id
    (graph.validate). Raised as `graph.BuildError`, not a private exception, because this is
    the same "ref must resolve" rule SCHEMA §6 / programme design §9 already enforce, one
    axis over — not a new failure mode a caller has to learn to catch."""
    for grant, n in narratives.items():
        for sec in n.sections:
            for b in sec.bullets:
                for r in b.refs:
                    if classify_ref(r) == "local":
                        raise BuildError(
                            f"programme/narrative/{grant}.yaml: {sec.title!r} / "
                            f"{_short(b.text)!r} -> ambiguous ref {r!r} — a narrative bullet "
                            "is not itself a container, so a bare local id has nothing to "
                            "resolve against; use a fully-qualified ref (Citekey, Citekey:id, "
                            "@aim, @aim:id, or a broad slug)")
                    if not _resolves(r, g):
                        raise BuildError(
                            f"programme/narrative/{grant}.yaml: {sec.title!r} / "
                            f"{_short(b.text)!r} -> dangling ref {r!r}")
