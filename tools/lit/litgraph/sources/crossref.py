"""Crossref client. Two jobs:

1. `author_names` — clean `family, given` for the focal paper (OpenAlex gives 'First Last',
   which is unreliable to re-split). Best-effort: any failure degrades to OpenAlex names.
2. `fetch_work` — a full focal/reference fallback when OpenAlex lacks a DOI (e.g. a paper
   published too recently to be indexed). Crossref carries the reference list with DOIs, so
   it lets us recover both the focal metadata and the citation stubs.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from urllib.parse import quote

import requests

from ..model import NormAuthor, Work

BASE = "https://api.crossref.org/works"
GetJson = Callable[[str], dict]


def _strip_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", doi.strip(), flags=re.IGNORECASE) or None


def _year(msg: dict) -> int | None:
    """Publication year from issued / published-print / published-online date-parts."""
    for key in ("issued", "published-print", "published-online", "published"):
        parts = (msg.get(key) or {}).get("date-parts") or []
        if parts and parts[0] and parts[0][0]:
            return parts[0][0]
    return None


def _plain_abstract(s: str | None) -> str | None:
    """Crossref abstracts arrive as JATS XML ('<jats:p>…'); strip the tags, collapse
    whitespace, and drop a leading 'Abstract' heading if the tags carried one."""
    if not s:
        return None
    text = re.sub(r"<[^>]+>", " ", s)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^abstract\b[:.\s]*", "", text, flags=re.IGNORECASE)
    return text or None


def normalize_work(msg: dict, fallback_doi: str | None = None) -> Work:
    """Crossref `message` -> Work (DOI-bearing references only)."""
    authors: list[NormAuthor] = []
    for a in msg.get("author") or []:
        fam = (a.get("family") or "").strip()
        given = (a.get("given") or "").strip()
        dn = f"{given} {fam}".strip()
        authors.append(NormAuthor(family=fam, given=given, display_name=dn))
    title = (msg.get("title") or [""])[0] or (msg.get("container-title") or [""])[0] or ""
    venue = (msg.get("container-title") or [None])[0]
    ref_dois = [_strip_doi(r.get("DOI")) for r in (msg.get("reference") or []) if r.get("DOI")]
    return Work(
        doi=_strip_doi(msg.get("DOI")) or _strip_doi(fallback_doi),
        title=title,
        year=_year(msg),
        type_raw=msg.get("type"),
        venue_display=venue,
        authors=authors,
        referenced_dois=[d for d in ref_dois if d],
        abstract=_plain_abstract(msg.get("abstract")),
    )


class Crossref:
    def __init__(self, mailto: str = "", get_json: GetJson | None = None, max_retries: int = 3):
        self.mailto = mailto
        self._get_json = get_json or self._http_get_json
        self._session = requests.Session()
        self.max_retries = max_retries

    def _http_get_json(self, url: str) -> dict:
        sep = "&" if "?" in url else "?"
        if self.mailto:
            url = f"{url}{sep}mailto={quote(self.mailto)}"
        last: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                r = self._session.get(url, timeout=30)
                if r.status_code == 404:
                    return {}
                r.raise_for_status()
                return r.json()
            except requests.RequestException as e:  # pragma: no cover - network
                last = e
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"Crossref request failed: {url}") from last

    def fetch_work(self, doi: str) -> Work | None:
        """Full metadata for a DOI as a Work, or None if Crossref lacks it."""
        try:
            data = self._get_json(f"{BASE}/{quote(doi)}")
        except Exception:
            return None
        msg = data.get("message") or {}
        if not msg or not (msg.get("title") or msg.get("author") or msg.get("DOI")):
            return None
        return normalize_work(msg, fallback_doi=doi)

    def author_names(self, doi: str) -> list[tuple[str, str]]:
        """Return ordered (family, given) pairs, or [] on any problem."""
        try:
            data = self._get_json(f"{BASE}/{quote(doi)}")
        except Exception:
            return []
        msg = data.get("message") or {}
        pairs: list[tuple[str, str]] = []
        for a in msg.get("author") or []:
            fam = (a.get("family") or "").strip()
            given = (a.get("given") or "").strip()
            if fam:
                pairs.append((fam, given))
        return pairs
