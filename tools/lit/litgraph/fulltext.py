"""PDF -> AI-parsable Markdown (spec §4 Stage B'), deterministic via pymupdf4llm.

Normalized so quotes pulled from it match verbatim: soft hyphens / zero-width chars
removed, hyphenation at line-ends joined, trailing whitespace trimmed.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

import pymupdf
import pymupdf4llm
from pymupdf4llm.helpers import document_layout as _pmu_layout
from pymupdf4llm.helpers import utils as _pmu_utils

# pymupdf4llm's layout FLAGS omit TEXT_CID_FOR_UNKNOWN_UNICODE, which MuPDF's own get_text()
# default (TEXTFLAGS_TEXT) sets. Without it, a PDF whose fonts are subsetted with a Custom
# encoding and no ToUnicode CMap — routine in pre-2005 publisher PDFs — extracts as U+FFFD for
# nearly every glyph: Trappe2001Nature came out 88% replacement characters and was silently
# written to the library as an unreadable .md. The flag makes MuPDF fall back to the glyph's
# CID when it cannot resolve a Unicode value, which recovers the real characters. Set on both
# helper modules because to_markdown reads whichever module-level FLAGS its path goes through.
for _mod in (_pmu_utils, _pmu_layout):
    _mod.FLAGS |= pymupdf.TEXT_CID_FOR_UNKNOWN_UNICODE

# The same legacy PDFs recover their characters but not their *encoding*: the Advent/Type-1C
# fonts Nature used around 2001 sit "fi" at 0xAE, "fl" at 0xAF, "=" at 0x88, an en dash at 0xB1
# and an em dash at 0xD0, so correctly-extracted text still reads "®xed", "re¯ects", "B \x88 0"
# and "139±141". These are glyph-slot collisions, not damage — the mapping is one-to-one and
# recoverable, unlike the fused words `_artifacts` only flags. Repaired rather than warned
# because a curator cannot quote "®xed" into the graph and have it mean anything.
#
# Deliberately NOT in this table: this family also sits "." at ":" and "×" at "3", so the same
# PDFs render numbers as "0:053" and "1:5 3 10". Those slots collide with characters that occur
# legitimately on every page, so no context-free substitution is safe. Numeric quotes from such
# a paper stay mangled and must be checked against the PDF by eye — see `legacy_glyph_damage`.
LEGACY_GLYPHS = {"\u00ae": "fi", "\u00af": "fl", "\x88": "=", "\u00b1": "\u2013", "\u00d0": "\u2014"}
# Signatures no correctly-encoded paper produces: a C1 control character in running text, or a
# registered-trademark sign welded to a lowercase letter ("®xed"). A real ® follows a name and
# is followed by space or punctuation, and a real ± by a digit or space — so gating on these two
# keeps the repair off the 117 papers in the library that extract cleanly.
_LEGACY_MARK = re.compile(r"\x88|\u00ae(?=[a-z])|\u00af(?=[a-z])")
# What the repair cannot reach, for the warning: a digit-colon-digit decimal, or a bare "3" being
# used as a multiplication sign between numbers.
_LEGACY_MATH = re.compile(r"\d:\d|\d\s3\s\d")


def is_legacy_encoded(text: str) -> bool:
    """True if `text` shows the pre-2005 publisher-font glyph-slot collisions LEGACY_GLYPHS fixes."""
    return bool(_LEGACY_MARK.search(text))


def repair_legacy_glyphs(text: str) -> tuple[str, tuple[str, ...]]:
    """`(repaired, residual)` — legacy glyph slots mapped back to the characters they render as,
    plus samples of the mangling the table deliberately leaves alone (decimals read as colons,
    multiplication signs read as "3") for the caller to warn about.

    One pass, because the two halves cannot be split: repairing removes the very signature that
    tells us the text is legacy-encoded, so the residual damage has to be sampled first. A no-op
    returning `(text, ())` on every normally-encoded PDF, so it is safe to call on any text."""
    if not is_legacy_encoded(text):
        return text, ()
    residual = tuple(dict.fromkeys(_LEGACY_MATH.findall(text)))[:5]
    for slot, real in LEGACY_GLYPHS.items():
        text = text.replace(slot, real)
    return text, residual


def _normalize(md: str) -> str:
    md = md.replace("­", "").replace("​", "")  # soft hyphen, zero-width space
    md = md.replace("‐", "-")  # unicode hyphen -> ascii
    # Join words split across a line break by hyphenation: "mechano-\nstructural".
    md = re.sub(r"(\w)-\n(\w)", r"\1\2", md)
    md = re.sub(r"[ \t]+\n", "\n", md)
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip() + "\n"


def to_markdown_report(pdf_path: str) -> tuple[str, tuple[str, ...]]:
    """`(markdown, residual)` — whole-PDF Markdown, normalized for verbatim-quote fidelity, plus
    any legacy-encoding damage left unrepaired (see `repair_legacy_glyphs`) for the caller to warn on.

    `use_ocr=False` because pymupdf4llm's layout path defaults it *on* and decides per page,
    via a bundled model, whether to run tesseract. That costs us both ways: it needs tesseract
    language data (absent here, and its absence is a hard error, not a skip), and OCR'd text is
    not reproducible — which would break the verbatim `quote` weld this whole module exists to
    serve. Publisher PDFs carry a real text layer; a page that genuinely needs OCR is one to
    notice and handle, not to silently guess at.
    """
    raw = pymupdf4llm.to_markdown(pdf_path, show_progress=False, use_ocr=False)
    repaired, residual = repair_legacy_glyphs(raw)
    return _normalize(repaired), residual


def to_markdown(pdf_path: str) -> str:
    """Whole-PDF Markdown, normalized for verbatim-quote fidelity. See `to_markdown_report`."""
    return to_markdown_report(pdf_path)[0]


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


# ── Abstract -> the paper's own full text (ingest Stage B'' fallback).
# Springer Nature and Elsevier deposit no abstract to Crossref, and OpenAlex mirrors Crossref
# here, so `abstract_inverted_index` comes back null — for most of the Nature family and all of
# Cell Press. The abstract is of course printed in the PDF, hence in our markdown; this recovers
# it from there. Two anchors, deliberately kept apart because they earn very different trust:
#
#   "heading" — a real `## Abstract` / `## SUMMARY` section label. The paper itself says where
#               the abstract is, so this is as good as a metadata fetch.
#   "byline"  — no label at all (Nature letters/articles run the abstract as an unlabelled lead
#               paragraph). Anchored on the *author line*, which we can find because ingest
#               already knows the author families from OpenAlex/Crossref — a far tighter anchor
#               than "the first longish paragraph", which would just as happily grab an
#               affiliation block. Held to stricter prose tests than the labelled path, and the
#               caller is told which anchor fired so a curator can spot-check the loose one.
#
# Never guesses silently: no anchor, or a candidate that fails the prose tests, returns None and
# the caller warns. A missing abstract is recoverable by hand; a wrong one is a lie in a curated
# file (SCHEMA §4), and this module's whole job is fidelity to the page.

_ABS_LABEL = re.compile(
    r"^[ \t]*#{0,6}[ \t]*\*{0,3}[ \t]*(abstract|summary)\b\*{0,3}[ \t]*[:.—-]?[ \t]*(.*)$",
    re.IGNORECASE | re.MULTILINE,
)
# Sections that end an abstract. `introduction` and the keyword line are the usual next thing;
# `significance`/`graphical abstract` are the front-matter blocks Cell Press and PNAS print.
_ABS_STOP = re.compile(
    r"^[ \t]*#{0,6}[ \t]*\*{0,3}[ \t]*"
    r"(key[ \t]?words|introduction|references|results|methods|significance|"
    r"graphical[ \t]+abstract|in[ \t]+brief|highlights|author[ \t]+summary|citation|"
    r"copyright|funding|acknowledge?ments?|author[ \t]+contributions|"
    r"conflict[ \t]+of[ \t]+interest|data[ \t]+availability|edited[ \t]+by|reviewed[ \t]+by)\b",
    re.IGNORECASE,
)
# Publisher furniture that is prose-shaped and therefore sails through every readability test:
# the licence block, the submission note, the copyright line. Frontiers prints its citation and
# copyright sidebar with the full author list in it, so the byline anchor lands squarely on the
# licence paragraph unless this rejects it.
_BOILERPLATE = re.compile(
    r"©|creative[ \t]commons|open[- \t]access article distributed|"
    r"this article was submitted to|use, distribution or reproduction",
    re.IGNORECASE,
)
# A structured abstract's own sub-labels — the one reason to keep reading past the first
# paragraph when that paragraph ended in a full stop (Cell Press, BMC, PLOS clinical style).
_ABS_PART = re.compile(
    r"^\*{0,2}(background|objectives?|aims?|purpose|design|setting|methods?|"
    r"materials?[ \t]+and[ \t]+methods|results?|findings|discussion|interpretation|"
    r"conclusions?|significance)\b\*{0,2}[ \t]*[:.]",
    re.IGNORECASE,
)
_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]")
_PICTURE = re.compile(r"^\s*\*\*==>.*<==\*\*\s*$")
_PARA_SPLIT = re.compile(r"\n\s*\n")
# A citation superscript the PDF prints inline: digits and separators only, so `[Ca2+]` and
# `[35S]` survive while `[1–3]` / `[4, 5]` go.
_REF_MARK = re.compile(r"\[[\d\s,;–—-]+\]")
_SENTENCE_END = re.compile(r"[.!?](?:\s|$)")
# PDF text layers drop the spaces between words often enough to matter ("tocontract
# anactomyosinringthat", "proliferation.Whenwetrigger"). Not repairable without a dictionary,
# but very visible — so flag it and let the human fix the one line.
#
# Length alone cannot be the test. This is a mechanobiology corpus: `mechanotransduction`,
# `metalloproteinases`, `microenvironment` and `pathophysiological` are ordinary vocabulary
# here, and a detector that flags them fires on a fifth of the library and gets tuned out —
# which costs more than the artifacts it finds. So a long run is only suspicious when it is
# *absurdly* long, or when it contains a function word no single English word contains
# (`anactomyosinringthat`, `selforganization`). Deliberately incomplete: precision buys a
# warning that is worth reading.
_FUSED_LONG = re.compile(r"\b[a-z]{26,}\b")
_FUSED_RUN = re.compile(r"\b[a-z]{14,}\b")
# Only words distinctive enough not to hide inside a morpheme. The short ones are traps:
# `for` sits in trans*for*mations, `not` in mecha*not*ransduction, `and` in lig*and*, `the` in
# hypo*the*sis, `but` in distri*but*ion — each one turns a real word into a false alarm.
_FUSED_JOIN = re.compile(r"that|this|with|from|which|were|have|been|their|these|when|while|such")
_FUSED_SENTENCE = re.compile(r"\w{4}[.,][A-Z]\w{3}")
_LABEL_LEAD = re.compile(r"^(abstract|summary)\b[:.—\s-]*", re.IGNORECASE)
# Markdown italics, the `**` case's quieter twin. Both delimiters must sit on a word boundary so
# that an identifier or a gene name written `Shh_a_` style is left alone.
_EMPHASIS = re.compile(r"(?<![\w_])_([^_\n]+?)_(?![\w_])")

_ABS_MIN_LABELLED = 150   # a labelled section is authoritative; only reject the obviously empty
_ABS_MIN_BYLINE = 400     # unlabelled: long enough that an affiliation block can't pass for one
_ABS_MAX = 4000           # past this we have run off the label into the body
_ABS_MAX_PARAS = 6        # structured abstracts (Background/Methods/Results/Conclusions)
# The byline lives on the title page, always. Without this window the anchor also matches a
# figure caption ("Adapted from Bendix et al.") and, far worse, the reference list — where the
# authors' own names recur and the paragraph after them is a *reference*, which sails through
# every prose test. Both were live failures on this corpus before the window went in.
_BYLINE_HEAD = 8000


@dataclass(frozen=True)
class AbstractHit:
    """An abstract recovered from a paper's full text, with the provenance the caller reports."""

    text: str
    anchor: str  # "heading" (a real section label) | "byline" (unlabelled lead paragraph)
    artifacts: tuple[str, ...] = ()  # PDF text-layer damage found in `text` — warn, don't fix


def _clean_abstract(s: str) -> str:
    """Markdown/PDF furniture off an abstract paragraph, leaving the authors' prose.

    Reference superscripts go too: the abstracts OpenAlex hands us carry none, and a stray
    `[1–3]` in half the corpus would make the field inconsistent to read and to search.
    Italics go for the same reason: a paper that emphasises `Xenopus` or a term of art should
    not read differently in this field from one whose abstract we fetched.
    """
    s = s.replace("**", "")
    s = _EMPHASIS.sub(r"\1", s)
    s = _HEADING.sub("", s)
    s = _LABEL_LEAD.sub("", s)
    s = _REF_MARK.sub("", s)
    s = re.sub(r"\s+([,.;:])", r"\1", s)  # space the superscript left behind
    return re.sub(r"\s+", " ", s).strip()


def _artifacts(s: str) -> tuple[str, ...]:
    """Samples of PDF text-layer damage in `s` (fused words / fused sentences), for a warning."""
    fused = [w for w in _FUSED_RUN.findall(s) if _FUSED_JOIN.search(w)]
    found = _FUSED_LONG.findall(s) + fused + _FUSED_SENTENCE.findall(s)
    seen: set[str] = set()
    out: list[str] = []
    for f in found:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return tuple(out[:3])


def _is_prose(s: str, *, min_chars: int) -> bool:
    """Does this paragraph read like an abstract rather than the page furniture around one?

    The paragraph after a byline is as often an affiliation block or a correspondence line as
    it is the abstract, and those are what these tests exclude: they carry emails, they are
    mostly comma-separated fragments rather than sentences, and they are dense with the
    superscript digits that key each author to an institution.
    """
    if not (min_chars <= len(s) <= _ABS_MAX):
        return False
    if "@" in s:  # correspondence / affiliation block
        return False
    if _BOILERPLATE.search(s):
        return False
    if len(_SENTENCE_END.findall(s)) < 3:
        return False
    tokens = s.split()
    return sum(t[0].isdigit() for t in tokens if t) <= len(tokens) * 0.15


def _ends_sentence(para: str) -> bool:
    """Does this paragraph close a sentence? Markdown emphasis and a trailing citation
    superscript sit *after* the full stop (`…tumour progression.**`, `…barrier[4] .`), so the
    tail has to be shaved before asking — otherwise no paragraph ever looks finished and the
    continuation rule in `_paragraphs_after` swallows the whole introduction."""
    return _REF_MARK.sub("", para).rstrip().rstrip("*_ \t").endswith((".", "!", "?", '."', ".'"))


def _paragraphs_after(text: str, pos: int) -> list[str]:
    """The paragraphs following `pos` that still belong to the abstract.

    Continuation is the whole difficulty: the markdown loses the heading that would say where
    the abstract ends, so "read until the next heading" quietly swallows the first paragraph of
    the introduction. Two reasons — and only these two — to keep reading past a paragraph:

    * it ended **mid-sentence**, so the abstract was broken across a column and the rest of the
      sentence is in the next paragraph; or
    * the next paragraph opens with a **structured-abstract label** (`Results:`, `Conclusions:`),
      which is the abstract explicitly continuing itself.

    A paragraph that ends in a full stop and is followed by ordinary prose ends the abstract.
    That is the common case, and getting it wrong in the other direction — appending body text —
    is the failure this rule exists to prevent.
    """
    out: list[str] = []
    for para in _PARA_SPLIT.split(text[pos:]):
        para = para.strip()
        if not para or _PICTURE.match(para):
            continue
        # `Results:` is both a stop-word and a structured-abstract label, so which one a
        # paragraph is gets decided by what follows it: a bare `## Results` heading starts the
        # body, while `Results: To understand how…` is the abstract continuing. Tested in this
        # order — the other way round, every structured abstract truncates at `Background:`.
        part = _ABS_PART.match(para)
        if not (part and len(para) - part.end() > 80):
            if _ABS_STOP.match(para) or (_HEADING.match(para) and out):
                break
            # A bare heading with no prose on it, before any content: page furniture sitting
            # between the label and the abstract (Nature Reviews prints a `## Sections` contents
            # block right there). Skipping it rather than taking it as the abstract's first
            # paragraph is the difference between recovering that paper's abstract and
            # recovering the word "Sections". Checked *after* the stop-list, or a bare
            # `## Introduction` gets skipped too and the body walks in behind it.
            if _HEADING.match(para) and len(para) < 60 and not _ends_sentence(para):
                continue
            # A column break splits a sentence in two: the part before has no terminator *and*
            # the part after opens lowercase. Requiring both is what separates a real split from
            # an abstract whose last sentence merely lost its full stop to the text layer —
            # where continuing would append the introduction's opening paragraph instead.
            if out and not (not _ends_sentence(out[-1]) and para[:1].islower()):
                break
        out.append(para)
        if len(out) >= _ABS_MAX_PARAS:
            break
    return out


def _from_label(text: str) -> AbstractHit | None:
    """The abstract under an explicit `Abstract` / `Summary` section label.

    Exact-matched on the label word so `Graphical Abstract` and `Author Summary` — the Cell
    Press and PLOS front-matter blocks that sit *above* the real one — can never anchor it.
    """
    for m in _ABS_LABEL.finditer(text):
        inline = m.group(2).strip()
        paras = [inline] if inline else []
        paras += _paragraphs_after(text, m.end())
        body = _clean_abstract(" ".join(p for p in paras if p))
        if _is_prose(body, min_chars=_ABS_MIN_LABELLED):
            return AbstractHit(body, "heading", _artifacts(body))
    return None


def _from_byline(text: str, families: Sequence[str]) -> AbstractHit | None:
    """The unlabelled lead paragraph of a Nature-style paper: the one right after the byline.

    The byline is located by the author families we already fetched, so this is anchored on the
    paper's own identity rather than on a guess about layout. Requires two families on one line
    (a single family also matches a running header or a citation), and only looks at the title
    page (`_BYLINE_HEAD`), where a byline is the only thing that can be.
    """
    fams = [f for f in families if len(f) >= 3]
    if len(fams) < 2:
        return None
    for m in re.finditer(r"^.*$", text[:_BYLINE_HEAD], re.MULTILINE):
        if sum(f in m.group(0) for f in fams) < 2:
            continue
        # Paragraphs are read from the *full* text: only the search is windowed, so an abstract
        # that straddles the window boundary still comes out whole. Joined, not just the first —
        # a two-column PDF splits the abstract mid-sentence often enough that taking only the
        # paragraph immediately after the byline lops the opening off (`_paragraphs_after`'s
        # continuation rule is what keeps the join from running into the body).
        body = _clean_abstract(" ".join(_paragraphs_after(text, m.end())))
        # An abstract is a complete unit: it ends on a full stop. A paragraph that stops
        # mid-sentence is the body's column flow, which is what sits directly under the byline
        # when the PDF's text layer carries no abstract block at all (some Nature layouts) —
        # and taking it hands back the paper's *introduction* dressed as its abstract. The
        # labelled path doesn't need this: there, the paper itself said where the abstract is.
        if _ends_sentence(body) and _is_prose(body, min_chars=_ABS_MIN_BYLINE):
            return AbstractHit(body, "byline", _artifacts(body))
    return None


def extract_abstract(text: str, author_families: Sequence[str] = ()) -> AbstractHit | None:
    """A paper's abstract, read out of its own full text. None when nothing anchors safely.

    Tries the explicit section label first, then the unlabelled-lead-paragraph anchor (which
    needs `author_families` to find the byline). See the module comment above for why the two
    are reported separately.
    """
    return _from_label(text) or _from_byline(text, author_families)


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
