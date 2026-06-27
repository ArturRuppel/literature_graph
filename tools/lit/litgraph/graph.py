"""Pure graph core: load a data repo's YAML, resolve refs, validate (SCHEMA §6),
compute emergent properties (SCHEMA §7). No output/serialization here."""

from __future__ import annotations

import re

_LOCAL = re.compile(r"^[cqm]\d+$")
_CITEKEY = re.compile(r"^[A-Z][A-Za-z]*\d{4}[A-Za-z]")  # <Family><Year><Venue>


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
