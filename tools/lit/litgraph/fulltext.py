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
    """Whole-PDF Markdown, normalized for verbatim-quote fidelity.

    `use_ocr=False` because pymupdf4llm's layout path defaults it *on* and decides per page,
    via a bundled model, whether to run tesseract. That costs us both ways: it needs tesseract
    language data (absent here, and its absence is a hard error, not a skip), and OCR'd text is
    not reproducible — which would break the verbatim `quote` weld this whole module exists to
    serve. Publisher PDFs carry a real text layer; a page that genuinely needs OCR is one to
    notice and handle, not to silently guess at.
    """
    raw = pymupdf4llm.to_markdown(pdf_path, show_progress=False, use_ocr=False)
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


# ── Reference list -> DOIs (ingest Stage C fallback).
# Some publishers never deposit their reference list to Crossref, and OpenAlex mirrors
# Crossref for references — so `referenced_works`/`reference` come back empty and a paper
# ingests with zero stubs. The list is still printed in the PDF, hence in our extracted
# markdown; this recovers the DOIs from there.
_REF_HEADING = re.compile(
    r"^[ \t]*#{0,6}[ \t]*\*{0,3}[ \t]*(?:references|bibliography|literature[ \t]+cited)"
    r"[ \t]*\*{0,3}[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_DOI_LABEL = re.compile(r"\bdoi:", re.IGNORECASE)
_DOI_BODY = re.compile(r"^10\.\d{4,9}/\S+$")
_DOI_TRIM = ".,;:)]}"
# A reference entry ends at a blank line or at the next "- " bullet the markdown emits.
_ENTRY_SPLIT = re.compile(r"\n\s*\n|\n(?=-[ \t])")
_JOINABLE = (".", "/", "-", "_")
_MAX_JOINS = 4
_WS_SPLIT = re.compile(r"(\s+)")


def _stitch_doi(chunk: str) -> str | None:
    """Reassemble one DOI from the whitespace-broken pieces following a `doi:` label.

    PDF text layers break DOIs two ways, and the two need opposite treatment:

    * **wrapped across a line** — the DOI simply ran off the column ("10.1083/jcb.2015\\n05105",
      "10.1038/na\\nture21718"). The break can land anywhere, including mid-token, so a newline
      is always a join.
    * **spaced within a line** — a stray space from the text layer ("10.1016/j .devcel.2018").
      But a space just as often separates the DOI from prose that follows it on the same line
      ("10.1101/cshperspect.a041794 originally published online November 24, 2025"), and
      joining *that* yields a garbage DOI that poisons a whole API batch. So a space joins
      only across a seam: the left part ends with `.`/`/`/`-`/`_`, or the right part starts
      with one. Prose never leaves that seam.
    """
    parts = _WS_SPLIT.split(chunk.strip())
    if not parts or not parts[0]:
        return None
    doi, joins = parts[0], 0
    for i in range(1, len(parts) - 1, 2):
        whitespace, token = parts[i], parts[i + 1]
        if joins >= _MAX_JOINS or not token:
            break
        seam = doi.endswith(_JOINABLE) or token.startswith(_JOINABLE)
        if "\n" not in whitespace and not seam:
            break
        doi += token
        joins += 1
    doi = doi.rstrip(_DOI_TRIM)
    return doi if _DOI_BODY.match(doi) else None


def extract_reference_dois(text: str) -> list[str]:
    """DOIs printed in a paper's own reference list, in order, case-insensitively deduped.

    Scans from the *last* `References` heading (a mid-body occurrence would be prose, not
    the section) and reads one DOI per `doi:` label per entry. Returns [] when the paper
    prints no reference section or no DOIs — pre-DOI references (a 1995 paper, a book) are
    invisible here by construction, so this recovers most of a reference list, never all of
    it. Callers should drop the focal paper's own DOI: journal footers repeat it.
    """
    heading = None
    for heading in _REF_HEADING.finditer(text):
        pass
    if heading is None:
        return []

    out: list[str] = []
    seen: set[str] = set()
    for entry in _ENTRY_SPLIT.split(text[heading.end():]):
        labels = list(_DOI_LABEL.finditer(entry))
        for i, label in enumerate(labels):
            stop = labels[i + 1].start() if i + 1 < len(labels) else len(entry)
            doi = _stitch_doi(entry[label.end():stop])
            if doi and doi.lower() not in seen:
                seen.add(doi.lower())
                out.append(doi)
    return out
