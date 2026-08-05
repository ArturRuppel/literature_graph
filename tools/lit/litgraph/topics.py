"""The topic axis (SCHEMA §9) — keyword containers over the paper `tags` vocabulary.

Kept in its own module, and out of the slice graph entirely, on purpose. A topic asserts
nothing: it is never an edge target, no emergent property reads it, and `broader` runs only
topic -> topic. It answers *what papers do I have on X*; the `leads-to` claim ladder answers
*what is known*. Design: docs/2026-08-03-topics-and-claim-altitudes.md.

Membership is derived, never authored — a paper is in a topic iff any of its `tags` is one of
that topic's keywords, or of any topic beneath it via `broader`. Nothing is written on the
paper, and a paper never names a topic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

_yaml = YAML(typ="safe")


@dataclass
class Topic:
    slug: str
    title: str
    note: str | None = None
    keywords: list[str] = field(default_factory=list)   # tag strings this topic contains
    broader: list[str] = field(default_factory=list)    # topic slugs this one sits under


class TopicError(Exception):
    """Raised on a SCHEMA §9 validation failure. Message names the offending slug."""


def load_topics(root) -> dict[str, Topic]:
    """Parse topics/*.yaml. Returns {} when the repo has no topic tree — the axis is
    optional, exactly as the programme tree is."""
    topics: dict[str, Topic] = {}
    for f in sorted((Path(root) / "topics").glob("*.yaml")):
        # Name the file: ruamel is handed text, so its own errors say only
        # `in "<unicode string>", line N` — see graph.load_yaml for the same guard.
        try:
            raw = _yaml.load(f.read_text()) or {}
        except YAMLError as e:
            raise TopicError(f"{f}: {e}") from e
        topics[f.stem] = Topic(
            slug=f.stem,
            title=raw.get("title", ""),
            note=raw.get("note"),
            keywords=list(raw.get("keywords") or []),
            broader=list(raw.get("broader") or []),
        )
    return topics


def validate_topics(topics: dict[str, Topic], broad_slugs: set[str] | None = None) -> None:
    """SCHEMA §9: `broader` resolves and is acyclic, and topic slugs are disjoint from the
    broad-slice slugs. Disjointness is what keeps a topic from ever being mistaken for an
    edge target — refs resolve bare slugs against claims/questions/methods only, so an
    overlapping name would read as a claim in one place and a topic in another."""
    if broad_slugs:
        clash = sorted(set(topics) & broad_slugs)
        if clash:
            raise TopicError(
                f"topic slug also names a broad claim/question/method: {clash} (SCHEMA §9.2)")

    for slug, t in topics.items():
        for b in t.broader:
            if b not in topics:
                raise TopicError(f"{slug}: broader -> unknown topic {b!r} (SCHEMA §9.1)")

    # Cycle detection over `broader`, reporting the path so the fix is obvious.
    state: dict[str, int] = {}          # 0 = visiting, 1 = done

    def walk(slug: str, path: list[str]) -> None:
        if state.get(slug) == 1:
            return
        if state.get(slug) == 0:
            cycle = path[path.index(slug):] + [slug]
            raise TopicError(f"topic `broader` cycle: {' -> '.join(cycle)} (SCHEMA §9.1)")
        state[slug] = 0
        for b in topics[slug].broader:
            walk(b, path + [slug])
        state[slug] = 1

    for slug in topics:
        walk(slug, [])


def children(topics: dict[str, Topic]) -> dict[str, list[str]]:
    """Invert `broader`. A topic may have several parents — this axis is a DAG, not a tree."""
    kids: dict[str, list[str]] = {s: [] for s in topics}
    for slug, t in topics.items():
        for b in t.broader:
            kids[b].append(slug)
    return {s: sorted(v) for s, v in kids.items()}


def keyword_closure(topics: dict[str, Topic], slug: str) -> set[str]:
    """Every keyword this topic owns, including those of every topic beneath it. Lower-cased:
    SCHEMA §9 matches keywords against paper tags case-insensitively."""
    kids = children(topics)
    seen: set[str] = set()
    out: set[str] = set()

    def walk(s: str) -> None:
        if s in seen:
            return
        seen.add(s)
        out.update(k.lower() for k in topics[s].keywords)
        for c in kids[s]:
            walk(c)

    walk(slug)
    return out


def papers_in(topics: dict[str, Topic], slug: str, papers) -> list[str]:
    """Citekeys of the curated papers this topic reaches, in citekey order. Derived from
    tags alone — nothing on the paper knows the topic exists."""
    kw = keyword_closure(topics, slug)
    return sorted(ck for ck, p in papers.items()
                  if getattr(p, "curated", False) and {t.lower() for t in p.tags} & kw)


def roots(topics: dict[str, Topic]) -> list[str]:
    return sorted(s for s, t in topics.items() if not t.broader)


def coverage(topics: dict[str, Topic], papers) -> tuple[list[str], list[str], list[str]]:
    """The report that keeps this layer honest as the tag vocabulary grows:

      unfiled  — tags on a paper that no topic contains (the layer is falling behind)
      dead     — keywords in a topic that no paper carries (a typo, or a tag since renamed)
      stranded — curated papers no topic reaches at all

    All three are curation signals, not errors (SCHEMA §9.3); `lit topics --orphans`
    surfaces them and `--strict` is what turns them into a non-zero exit for CI.
    """
    owned = {k.lower() for t in topics.values() for k in t.keywords}
    tagged = {ck: {t.lower() for t in p.tags}
              for ck, p in papers.items() if getattr(p, "curated", False)}
    all_tags = set().union(*tagged.values()) if tagged else set()

    unfiled = sorted(all_tags - owned)
    dead = sorted(owned - all_tags)
    stranded = sorted(ck for ck, tags in tagged.items() if not (tags & owned))
    return unfiled, dead, stranded
