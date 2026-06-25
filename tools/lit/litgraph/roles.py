"""Resolve author positions + corresponding flags by unioning OpenAlex with PDF markers.

OpenAlex gives order and a *partial* `is_corresponding` (it missed Balland on the eLife
target); the PDF's `*`/`For correspondence:` block is the authority. We take the union so
neither source's omission drops a corresponding author. Co-first authors (PDF `†`
"contributed equally") become additional `first`s (spec §3).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from .citekey import fold_ascii
from .model import Author, NormAuthor


@dataclass
class AuthorMarkers:
    """Corresponding/equal-contribution signals parsed from the PDF (by family name)."""

    corresponding_families: set[str]  # folded-lowercase family names
    equal_contrib_families: set[str]


def _fam_key(family: str) -> str:
    return fold_ascii(family).lower().strip()


def resolve_roles(authors: list[NormAuthor], markers: AuthorMarkers | None) -> list[Author]:
    """Combine byline order + metadata + PDF markers into final Author records.

    position:
      - `first`  if byline index 0, OR family is in the PDF equal-contribution group
      - `last`   if byline index n-1 (and not already first)
      - else middle (None)
    corresponding: union(OpenAlex is_corresponding, PDF corresponding markers)
    """
    n = len(authors)
    corr_fams = markers.corresponding_families if markers else set()
    equal_fams = markers.equal_contrib_families if markers else set()
    out: list[Author] = []
    for idx, a in enumerate(authors):
        fam = _fam_key(a.family)
        is_first = idx == 0 or (fam and fam in equal_fams)
        is_last = idx == n - 1 and not is_first
        position = "first" if is_first else "last" if is_last else None
        corresponding = a.is_corresponding or (fam in corr_fams if fam else False)
        out.append(Author(name=_format_name(a), position=position, corresponding=corresponding))
    return out


def _format_name(a: NormAuthor) -> str:
    """Prefer clean 'Family, Given'; fall back to the display name. Stored as NFC."""
    if a.family and a.given:
        name = f"{a.family}, {a.given}"
    elif a.family:
        name = a.family
    else:
        name = a.display_name
    return unicodedata.normalize("NFC", name)
