"""Citekey generation: <Family><Year><Venue>, CamelCase (SCHEMA §3, spec §3a)."""

from __future__ import annotations

import re
import unicodedata


def fold_ascii(s: str) -> str:
    """Strip diacritics to ASCII: 'Wörthmüller' -> 'Worthmuller', 'Méry' -> 'Mery'."""
    decomposed = unicodedata.normalize("NFKD", s)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def family_token(family: str) -> str:
    """First author's family name as a CamelCase, ASCII, alphanumeric token.

    'van der Berg' -> 'VanDerBerg'; "O'Brien" -> 'OBrien'; 'Méry' -> 'Mery'.
    """
    folded = fold_ascii(family)
    words = re.findall(r"[A-Za-z0-9]+", folded)
    return "".join(w[:1].upper() + w[1:] for w in words)


def base_citekey(family: str, year: int | str, venue: str) -> str:
    """Compose the un-disambiguated key. `venue` is already a venue token (may be '')."""
    return f"{family_token(family)}{year}{venue}"


def disambiguate(base: str, taken: dict[str, str | None], doi: str | None) -> str:
    """Resolve `base` against already-used keys.

    `taken` maps existing citekey -> its DOI (or None). Rules:
      - free base -> base
      - base taken by the SAME doi -> reuse base (idempotent re-ingest / shared cite)
      - otherwise append the first free a/b/c... suffix (reusing a same-doi suffix)
    """
    norm_doi = _norm_doi(doi)
    if base not in taken:
        return base
    if norm_doi and _norm_doi(taken[base]) == norm_doi:
        return base
    for i in range(26):
        cand = f"{base}{chr(ord('a') + i)}"
        if cand not in taken:
            return cand
        if norm_doi and _norm_doi(taken[cand]) == norm_doi:
            return cand
    raise ValueError(f"could not disambiguate citekey {base!r} after 26 suffixes")


def make_citekey(
    family: str,
    year: int | str,
    venue: str,
    taken: dict[str, str | None],
    doi: str | None = None,
) -> str:
    """Build a unique citekey for one paper given the keys already in use."""
    return disambiguate(base_citekey(family, year, venue), taken, doi)


def _norm_doi(doi: str | None) -> str | None:
    """Normalize a DOI for comparison: lowercase, strip URL prefix."""
    if not doi:
        return None
    d = doi.strip().lower()
    d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d)
    return d or None
