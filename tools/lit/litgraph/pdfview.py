"""Socket-free PDF page rendering for the viewer's quote windows.

Shared by ``lit serve`` (:mod:`litgraph.serve`) and the electronic-lab-notebook plugin
(``litgraph_eln``) so the two serving layers render identically and can't drift — the drift
that once left the plugin without a ``/page`` route, so the quote window rendered nothing.
Pure functions over a PDF path, each with an mtime-keyed module cache; no server object, no
HTTP. The HTTP layers own only validation, routing, and caching headers.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

import fitz  # pymupdf — a litgraph hard dependency

PREVIEW_WIDTH = 552  # px (2x the ~276px tooltip box — crisp on retina, still tiny)
PAGE_WIDTH = 1600    # px — full-page render for the floating quote window (crisp under zoom)
_MAX_PX = 4_000_000  # cap rasterized pixels (oversized-mediabox guard)

_PAGES: dict[tuple, tuple[float, bytes]] = {}   # (name, n, width) -> (mtime, png)
_WORDS: dict[tuple, tuple[float, list]] = {}    # (name, n)        -> (mtime, [word,...])
_SIZES: dict[str, tuple[float, list]] = {}      # name             -> (mtime, [[w,h],...])


def render_page(pdf: Path, n: int, width: int) -> bytes:
    """Page ``n`` of ``pdf`` rendered to a ``width``-px PNG, cached until the file's mtime
    changes. n=0 + :data:`PREVIEW_WIDTH` is the tooltip thumbnail; any page at
    :data:`PAGE_WIDTH` feeds the floating quote window. Raises ``IndexError`` on an out-of-range
    page (the HTTP layer turns that into a 404)."""
    pdf = Path(pdf)
    mtime = pdf.stat().st_mtime
    key = (pdf.name, n, width)
    hit = _PAGES.get(key)
    if hit and hit[0] == mtime:
        return hit[1]
    with fitz.open(pdf) as doc:
        page = doc[n]
        zoom = width / page.rect.width
        # clamp total pixels so an oversized mediabox (poster/foldout) can't blow up into a
        # multi-second render — cap the raster, the window still zooms into the bitmap
        px = width * (page.rect.height * zoom)
        if px > _MAX_PX:
            zoom *= (_MAX_PX / px) ** 0.5
        png = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom)).tobytes("png")
    _PAGES[key] = (mtime, png)
    return png


def page_sizes(pdf: Path) -> list[list[float]]:
    """Per-page point sizes ``[[w, h], ...]`` — the whole-document manifest the viewer uses to
    lay out (and lazily fill) one stacked page box per page. Cached until the PDF's mtime
    changes."""
    pdf = Path(pdf)
    mtime = pdf.stat().st_mtime
    hit = _SIZES.get(pdf.name)
    if hit and hit[0] == mtime:
        return hit[1]
    with fitz.open(pdf) as doc:
        sizes = [[p.rect.width, p.rect.height] for p in doc]
    _SIZES[pdf.name] = (mtime, sizes)
    return sizes


def page_words(pdf: Path, n: int) -> list[dict]:
    """Words of page ``n`` as page-fraction boxes for the selectable text overlay:
    ``[{t, x0,y0,x1,y1, ln}, ...]`` in reading order, ``ln`` a per-line ordinal so the client
    can keep line breaks. Same page.rect normalization as the highlight rects, so the overlay
    registers on the raster without re-derivation. Cached until the PDF's mtime changes."""
    pdf = Path(pdf)
    mtime = pdf.stat().st_mtime
    key = (pdf.name, n)
    hit = _WORDS.get(key)
    if hit and hit[0] == mtime:
        return hit[1]
    with fitz.open(pdf) as doc:
        page = doc[n]                         # IndexError on an out-of-range page → 404 upstream
        w, h = page.rect.width, page.rect.height
        raw = page.get_text("words")          # (x0, y0, x1, y1, text, block, line, word_no)
    out = []
    for x0, y0, x1, y1, t, block, line, _wn in sorted(raw, key=lambda o: (o[5], o[6], o[7])):
        t = "".join(c for c in t if not unicodedata.category(c).startswith("C"))  # strip control/zero-width
        if not t.strip():                     # nothing visible left → not a selectable word
            continue
        out.append({"t": t, "x0": x0 / w, "y0": y0 / h, "x1": x1 / w, "y1": y1 / h,
                    "ln": block * 10000 + line})
    _WORDS[key] = (mtime, out)
    return out


def preview(pdf: Path) -> bytes:
    """First page of ``pdf`` as a PNG for the tooltip thumbnail."""
    return render_page(pdf, 0, PREVIEW_WIDTH)
