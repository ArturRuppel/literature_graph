"""PDF -> AI-parsable Markdown (spec §4 Stage B'), deterministic via pymupdf4llm.

Normalized so quotes pulled from it match verbatim: soft hyphens / zero-width chars
removed, hyphenation at line-ends joined, trailing whitespace trimmed.
"""

from __future__ import annotations

import re

import pymupdf4llm


def _normalize(md: str) -> str:
    md = md.replace("­", "").replace("​", "")  # soft hyphen, zero-width space
    md = md.replace("‐", "-")  # unicode hyphen -> ascii
    # Join words split across a line break by hyphenation: "mechano-\nstructural".
    md = re.sub(r"(\w)-\n(\w)", r"\1\2", md)
    md = re.sub(r"[ \t]+\n", "\n", md)
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip() + "\n"


def to_markdown(pdf_path: str) -> str:
    """Whole-PDF Markdown, normalized for verbatim-quote fidelity."""
    raw = pymupdf4llm.to_markdown(pdf_path, show_progress=False)
    return _normalize(raw)
