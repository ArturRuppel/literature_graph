"""Quote polishing for display + integrity flagging (SCHEMA §6.4).

The stored `quote` is the *tight verbatim anchor* a curator welds to the paper's `.md`.
For the viewer we derive a `quote_display`: the anchor grown out to its enclosing
sentence(s) and stripped of citation / figure-callout artifacts. Nothing here mutates the
YAML — the anchor stays exactly as authored, and if the stripper improves, every quote
upgrades on the next build with no data migration.

Two tiers, exactly as SCHEMA §6.4 anticipates:
  * a plain anchor is located verbatim in the `.md`, expanded, stripped  -> status "verbatim"
  * an authored `[...]` join is non-contiguous by construction, so it is polished
    segment-by-segment (each segment located/stripped) and flagged  -> status "joined"
A quote that can't be located at all is stripped-only and flagged  -> status "not_found".

Stripping is deliberately conservative: a parenthetical is deleted only when it reads as a
citation (a Capitalized name followed by a year, nothing but name/year/punctuation inside),
so content parentheticals — (N = 16), (CeNuS), (tumor diameter, tumor grade, ...) — survive.
Clause-level trimming ("as illustrated in Fig. 3") is a curator judgement, authored via the
`[...]` join; it is never done automatically.
"""

from __future__ import annotations

import re
from pathlib import Path

from .fulltext import _normalize

JOIN = "[...]"          # authored non-contiguous marker in a stored quote (SCHEMA §6.4)
JOIN_DISPLAY = " […] "  # how a join reads in the polished text

# --- artifact stripping --------------------------------------------------------------

_BRACKET_NUM = re.compile(r"\s*\[\d+(?:[–,\-]\s*\d+)*\]")   # [1], [3-5], [3, 7]
_CALLOUT = re.compile(                                          # (Fig. 3b), (Table 1), (see Methods)
    r"\s*\((?:Fig(?:ure)?|Table|Eq(?:uation)?|Ref|see)\.?\s*[^)]*\)", re.I)
_EMPHASIS = re.compile(r"_?\*\*(.+?)\*\*_?")                    # _**...**_, **...** (markdown cite wrap)
_YEAR = re.compile(r"\b(?:19|20)\d{2}[a-z]?\b")
_CITEISH = re.compile(r"^[A-Za-zÀ-ÿ0-9'.,;:&\s\-–]+$")  # only name/year/punct chars
_NAME_THEN_YEAR = re.compile(r"[A-Z][A-Za-z'\-]+.*?\b(?:19|20)\d{2}")  # a Capitalized name ... then a year


def _drop_cite_paren(m: "re.Match[str]") -> str:
    """Delete a parenthetical iff it reads as an author-year citation; keep it otherwise."""
    inner = m.group(1)
    if _YEAR.search(inner) and _CITEISH.match(inner) and _NAME_THEN_YEAR.search(inner):
        return ""
    return m.group(0)


def strip_artifacts(text: str) -> str:
    """Remove inline citation / figure-callout noise from a sentence, delete-only."""
    # 1. Unwrap markdown emphasis — itself a rendering artifact, and it hides the
    #    author-year cites underneath from the paren scan below.
    text = _EMPHASIS.sub(r"\1", text)
    # 2. Close the whitespace seams the unwrap opens, so parens/commas read cleanly.
    text = re.sub(r"\(\s+", "(", text)
    text = re.sub(r"\s+\)", ")", text)
    text = re.sub(r"\s+([;,])", r"\1", text)
    # 3. Numeric-bracket cites and figure/table callouts.
    text = _BRACKET_NUM.sub("", text)
    text = _CALLOUT.sub("", text)
    # 4. Author-year parentheticals (semantic test — any chain length, keeps content parens).
    text = re.sub(r"\s*\(([^)]*)\)", _drop_cite_paren, text)
    # 5. Tidy the seams left behind.
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


# --- sentence expansion --------------------------------------------------------------

# Abbreviations whose trailing "." must NOT count as a sentence boundary.
_ABBR = (r"(?:Fig|Figs|Eq|Eqs|Ref|Refs|No|Nos|Dr|Mr|Ms|Prof|Inc|Ltd|St|vs|cf|ca|approx|"
         r"e\.g|i\.e|et al|resp|ca|Suppl|Vol)")
_ABBR_END = re.compile(_ABBR + r"$")


def _sentence_span(text: str, lo: int, hi: int) -> tuple[int, int]:
    """Grow [lo, hi) out to the enclosing sentence boundaries within `text`.

    A boundary is `.`/`!`/`?` followed by whitespace (not after a known abbreviation), or a
    blank line, or the text edge."""
    start = lo
    while start > 0:
        c = text[start - 1]
        if c == "\n" and start >= 2 and text[start - 2] == "\n":
            break
        if c in ".!?" and start < len(text) and text[start] in " \n":
            if not _ABBR_END.search(text[max(0, start - 6):start - 1]):
                break
        start -= 1
    end = hi
    while end < len(text):
        c = text[end]
        if c in ".!?":
            nxt = text[end + 1] if end + 1 < len(text) else " "
            if nxt in " \n" and not _ABBR_END.search(text[max(0, end - 6):end]):
                return start, end + 1
        if c == "\n" and end + 1 < len(text) and text[end + 1] == "\n":
            break
        end += 1
    return start, end


def _locate(text: str, needle: str) -> tuple[int | None, int | None]:
    """Find `needle` in `text`, tolerant of runs of whitespace differing (newline vs space)."""
    i = text.find(needle)
    if i >= 0:
        return i, i + len(needle)
    pat = re.sub(r"(?:\\ )+", r"\\s+", re.escape(needle))
    m = re.search(pat, text)
    return (m.start(), m.end()) if m else (None, None)


# --- top-level polish ----------------------------------------------------------------

def _polish_contiguous(anchor: str, fulltext: str) -> tuple[str, bool]:
    """Expand a single verbatim anchor to its sentence(s) and strip it. Returns
    (display, located)."""
    lo, hi = _locate(fulltext, anchor) if fulltext else (None, None)
    if lo is None:
        return strip_artifacts(anchor), False
    s0, s1 = _sentence_span(fulltext, lo, hi)
    sentence = " ".join(fulltext[s0:s1].split())
    return strip_artifacts(sentence), True


def polish(quote: str, fulltext: str) -> tuple[str, str]:
    """Polish a stored quote for display. Returns (quote_display, status) where status is
    'verbatim' | 'joined' | 'not_found'. `fulltext` is the paper's `.md` ("" if unavailable
    — then the quote is stripped but not expanded, and reported not_found)."""
    anchor = " ".join(quote.split())
    if JOIN in anchor:
        segs = [seg.strip() for seg in anchor.split(JOIN)]
        located_all = True
        out: list[str] = []
        for seg in segs:
            if not seg:
                continue
            disp, ok = _polish_contiguous(seg, fulltext)
            located_all = located_all and ok
            out.append(disp)
        return JOIN_DISPLAY.join(out), "joined"
    disp, ok = _polish_contiguous(anchor, fulltext)
    return disp, ("verbatim" if ok else "not_found")


# --- graph integration ---------------------------------------------------------------

def _read_fulltext(pdf_dir: Path | None, citekey: str) -> str:
    """The paper's normalized `.md` full text, or "" if there is no `.md` for it."""
    if pdf_dir is None:
        return ""
    f = Path(pdf_dir) / f"{citekey}.md"
    if not f.is_file():
        return ""
    return _normalize(f.read_text(encoding="utf-8"))


def polish_graph(graph, pdf_dir: Path | None) -> list[str]:
    """Set `quote_display` on every quoted slice of every curated paper, reading each
    paper's `.md` from `pdf_dir`. Returns human-readable flags (SCHEMA §6.4) for quotes
    that need curator review: authored `[...]` joins and anchors not found verbatim."""
    warnings: list[str] = []
    for ck, p in graph.papers.items():
        if not p.curated or not any(s.quote for s in p.slices):
            continue
        fulltext = _read_fulltext(pdf_dir, ck)
        for s in p.slices:
            if not s.quote:
                continue
            display, status = polish(s.quote, fulltext)
            s.quote_display = display
            if status == "not_found":
                where = "" if fulltext else f" (no {ck}.md)"
                warnings.append(f"{ck}:{s.id} quote not found verbatim in the full text{where}")
            elif status == "joined":
                warnings.append(f"{ck}:{s.id} authored [...] join — verify both segments")
    return warnings
