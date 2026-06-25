"""Journal display name -> venue token for the citekey (SCHEMA §3, spec §3a).

Strategy: a small curated override map for brand names and titles where ISO-4 is
ugly/wrong; otherwise the ISO-4 abbreviation (`iso4`, LTWA-based) with dots and
non-alphanumerics stripped.
"""

from __future__ import annotations

import re

# Keys are normalized journal names (see _norm); values are the final tokens.
# Extend this as awkward journals show up in joint review.
_OVERRIDES: dict[str, str] = {
    "elife": "eLife",
    "proceedings of the national academy of sciences": "Pnas",
    "proceedings of the national academy of sciences of the united states of america": "Pnas",
    "biochimica et biophysica acta (bba) - molecular cell research": "BBA",
    "biochimica et biophysica acta molecular cell research": "BBA",
}


def _norm(display_name: str) -> str:
    """Lowercase + collapse whitespace, for stable override lookups."""
    return re.sub(r"\s+", " ", display_name.strip().lower())


def _strip(s: str) -> str:
    """Drop everything but ASCII letters/digits (removes ISO-4 dots, spaces)."""
    return re.sub(r"[^A-Za-z0-9]", "", s)


_WORDNET_READY = False


def _ensure_wordnet() -> None:
    """iso4 needs NLTK's wordnet corpus; fetch it once if missing."""
    global _WORDNET_READY
    if _WORDNET_READY:
        return
    import nltk

    try:
        nltk.data.find("corpora/wordnet")
    except LookupError:
        nltk.download("wordnet", quiet=True)
        nltk.download("omw-1.4", quiet=True)
    _WORDNET_READY = True


def venue_token(display_name: str | None) -> str:
    """Return the venue token for a journal name, or '' if unknown/empty.

    Examples (with the override map + iso4):
        "eLife"               -> "eLife"
        "Biophysical Journal" -> "BiophysJ"
        "Developmental Cell"  -> "DevCell"
        "Nature Physics"      -> "NatPhys"
        "...BBA... Molecular Cell Research" -> "BBA" (override)
    """
    if not display_name or not display_name.strip():
        return ""
    override = _OVERRIDES.get(_norm(display_name))
    if override is not None:
        return override

    from iso4 import abbreviate

    _ensure_wordnet()
    try:
        return _strip(abbreviate(display_name))
    except Exception:
        # iso4 can choke on odd titles; fall back to a CamelCase of the words.
        return _strip("".join(w.capitalize() for w in re.findall(r"[A-Za-z0-9]+", display_name)))
