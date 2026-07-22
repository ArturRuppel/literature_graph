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


# Author-supplied keyword line: `Keywords: a, b, c`, `Key words: …`, a markdown-header
# `## KEYWORDS` with the list on the next line, or a **bold** variant of any of these (the PDF→md
# pass often emits `**Keywords:**` / `## **Keywords**`). Anchored to line start (optional #/*
# prefixes) so a stray "keywords" mid-sentence doesn't match; first hit wins (section sits up top).
# Horizontal-whitespace only around the label — a \s* here would swallow the blank line after a
# lone `## KEYWORDS` header and grab the list (prefix and all) instead of leaving group(1) empty.
_KW_LABEL = re.compile(
    r"^[ \t]*#{0,6}[ \t]*\*{0,3}[ \t]*key[ \t]?words\b\*{0,3}[ \t]*[:.—-]?[ \t]*(.*)$",
    re.IGNORECASE | re.MULTILINE,
)
# Fallback for a run-on abstract that trails its list mid-line (e.g. `… ABSTRACT … KEYWORDS: a, b`).
# Case-SENSITIVE all-caps: only the deliberate section label, never a lowercase mid-sentence word.
_KW_INLINE = re.compile(r"KEY[ \t]?WORDS[ \t]*[:.][ \t]*(.*)$", re.MULTILINE)
_HDR_PREFIX = re.compile(r"^\s*#{1,6}\s*")
# List separators seen in the wild: semicolon, comma, or a middle-dot / bullet.
_KW_SPLIT = re.compile(r"[;,·•∙]")
_KW_TRIM = " \t*#"  # markdown emphasis / header leftovers to shave off each token's ends


def extract_keywords(text: str) -> list[str]:
    """Author keyword line from a paper's full text → ordered, case-insensitively deduped list.

    Splits the labelled line on `;`, `,`, or a `·`/`•` bullet. If the label sits alone on its line
    (a markdown header like `## KEYWORDS`), the list is read from the next non-empty line. Bold/
    header markup around the label and on each token is shaved off. Returns [] when no keyword line
    is present — the common case; most papers don't deposit one. Faithful to the authors' phrasing/
    casing (this only *proposes* tags; the curator normalizes).
    """
    m = _KW_LABEL.search(text) or _KW_INLINE.search(text)
    if not m:
        return []
    rest = m.group(1).strip()
    if not rest:  # header-only line → take the next non-empty line, minus any header prefix
        for line in text[m.end():].splitlines():
            if line.strip():
                rest = _HDR_PREFIX.sub("", line).strip()
                break
    seen: set[str] = set()
    out: list[str] = []
    for part in _KW_SPLIT.split(rest):
        kw = part.strip(_KW_TRIM).strip(".").strip(_KW_TRIM)
        if kw and kw.lower() not in seen:
            seen.add(kw.lower())
            out.append(kw)
    return out
