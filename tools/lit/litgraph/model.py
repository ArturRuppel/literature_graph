"""Normalized data structures + schema-conformant YAML serialization (SCHEMA §4)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Author:
    """One byline author. `position` is an authorship tier (first|last|None=middle);
    `corresponding` is the independent flag (spec §3)."""

    name: str  # "Family, Given"
    position: str | None = None  # "first" | "last" | None (middle)
    corresponding: bool = False


@dataclass
class NormAuthor:
    """An author as normalized from a metadata source, before role resolution."""

    family: str
    given: str = ""
    display_name: str = ""
    is_corresponding: bool = False  # as reported by OpenAlex (partial; unioned later)


@dataclass
class Work:
    """A paper normalized from OpenAlex (+ Crossref names). Focal or referenced."""

    doi: str | None
    title: str
    year: int | None
    type_raw: str | None
    venue_display: str | None
    authors: list[NormAuthor] = field(default_factory=list)
    referenced_works: list[str] = field(default_factory=list)  # OpenAlex ids (focal, from OpenAlex)
    referenced_dois: list[str] = field(default_factory=list)  # DOIs (focal, from Crossref fallback)
    abstract: str | None = None  # verbatim abstract (focal only; refs are fetched without it)


# --- paper type mapping (spec §4 Stage B) -----------------------------------

_TYPE_MAP = {
    "review": "review",
    "review-article": "review",
}


def map_type(type_raw: str | None) -> str:
    """OpenAlex/Crossref work type -> schema type. Defaults to 'original'."""
    if not type_raw:
        return "original"
    return _TYPE_MAP.get(type_raw.strip().lower(), "original")


@dataclass
class Stub:
    """A bib-only uncurated paper (one entry in stubs.yaml)."""

    citekey: str
    title: str
    year: int | None = None
    doi: str | None = None
    type: str | None = None

    def to_mapping(self) -> dict:
        """Stub body (without the citekey), in stubs.yaml field order."""
        body: dict = {"title": self.title}
        if self.year is not None:
            body["year"] = self.year
        if self.doi:
            body["doi"] = self.doi
        if self.type:
            body["type"] = self.type
        return body


@dataclass
class CuratedPaper:
    """A curated paper's skeleton: metadata + authors (no affirmations yet)."""

    citekey: str
    title: str
    type: str
    year: int | None
    doi: str | None
    url: str | None
    pdf: str | None
    abstract: str | None = None
    authors: list[Author] = field(default_factory=list)

    def to_yaml(self) -> str:
        """Render curated/<citekey>.yaml, matching the example's flow-author style."""
        lines: list[str] = []
        lines.append(f"# Curated paper skeleton — initialized by `lit ingest` (spec §4).")
        lines.append(f"# Filename stem `{self.citekey}` IS the citekey (SCHEMA §3).")
        lines.append(f"title: {_yaml_str(self.title)}")
        lines.append(f"type: {self.type}")
        if self.year is not None:
            lines.append(f"year: {self.year}")
        if self.doi:
            lines.append(f"doi: {self.doi}")
        if self.url:
            lines.append(f"url: {self.url}")
        if self.pdf:
            lines.append(f"pdf: {self.pdf}")
        if self.abstract:
            lines.append(f"abstract: {_yaml_str(self.abstract)}")
        lines.append("authors:")
        for a in self.authors:
            lines.append(f"  - {_author_flow(a)}")
        lines.append("")
        lines.append("# affirmations / questions are added later during curation (CONCEPT §12).")
        return "\n".join(lines) + "\n"


def _author_flow(a: Author) -> str:
    """A single author as a YAML flow mapping: {name: "...", position: first}."""
    parts = [f"name: {_yaml_str(a.name)}"]
    if a.position:
        parts.append(f"position: {a.position}")
    if a.corresponding:
        parts.append("corresponding: true")
    return "{" + ", ".join(parts) + "}"


def _yaml_str(s: str) -> str:
    """Double-quote a scalar, escaping quotes/backslashes — safe for titles/names."""
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
