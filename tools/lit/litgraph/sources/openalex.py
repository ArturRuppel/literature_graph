"""OpenAlex client + normalization to model.Work (spec §4).

The HTTP layer is a single injectable `get_json` callable so tests can feed recorded
fixtures with no network.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from urllib.parse import quote

import requests

from ..model import NormAuthor, Work

BASE = "https://api.openalex.org"
_SELECT = "id,doi,title,display_name,publication_year,type,authorships,primary_location,referenced_works"
# focal lookups also pull the abstract (inverted index); reference batches skip it — stubs
# don't carry abstracts and the extra field would balloon 50-work pages
_SELECT_FOCAL = _SELECT + ",abstract_inverted_index"

GetJson = Callable[[str], dict]


def _strip_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", doi.strip(), flags=re.IGNORECASE) or None


def _split_name(display_name: str) -> tuple[str, str]:
    """Fallback split of 'Given Names Family' -> (family, given)."""
    parts = display_name.split()
    if not parts:
        return "", ""
    return parts[-1], " ".join(parts[:-1])


def _deinvert(idx: dict | None) -> str | None:
    """OpenAlex ships abstracts as {word: [positions]}; rebuild the plain text."""
    if not idx:
        return None
    slots: dict[int, str] = {}
    for word, positions in idx.items():
        for pos in positions:
            slots[pos] = word
    return " ".join(slots[i] for i in sorted(slots)) or None


def normalize_work(raw: dict) -> Work:
    """OpenAlex work JSON -> Work."""
    authors: list[NormAuthor] = []
    for a in raw.get("authorships", []):
        dn = (a.get("author") or {}).get("display_name", "") or ""
        fam, given = _split_name(dn)
        authors.append(
            NormAuthor(family=fam, given=given, display_name=dn, is_corresponding=bool(a.get("is_corresponding")))
        )
    source = (raw.get("primary_location") or {}).get("source") or {}
    return Work(
        doi=_strip_doi(raw.get("doi")),
        title=raw.get("title") or raw.get("display_name") or "",
        year=raw.get("publication_year"),
        type_raw=raw.get("type"),
        venue_display=source.get("display_name"),
        authors=authors,
        referenced_works=list(raw.get("referenced_works") or []),
        abstract=_deinvert(raw.get("abstract_inverted_index")),
    )


class OpenAlex:
    def __init__(self, mailto: str = "", get_json: GetJson | None = None, max_retries: int = 3):
        self.mailto = mailto
        self._get_json = get_json or self._http_get_json
        self._session = requests.Session()
        self.max_retries = max_retries

    # --- HTTP (skipped entirely when get_json is injected) -------------------
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
        raise RuntimeError(f"OpenAlex request failed: {url}") from last

    # --- API ----------------------------------------------------------------
    def fetch_work(self, doi: str) -> Work | None:
        raw = self._get_json(f"{BASE}/works/https://doi.org/{quote(doi)}?select={_SELECT_FOCAL}")
        return normalize_work(raw) if raw and raw.get("id") else None

    def search_by_title(self, title: str) -> Work | None:
        data = self._get_json(f"{BASE}/works?search={quote(title)}&per-page=1&select={_SELECT_FOCAL}")
        results = data.get("results") or []
        return normalize_work(results[0]) if results else None

    def fetch_works(self, openalex_ids: list[str], chunk: int = 50) -> list[Work]:
        """Batch-fetch referenced works by OpenAlex id (paginated OR-filter)."""
        out: list[Work] = []
        short_ids = [i.rsplit("/", 1)[-1] for i in openalex_ids]
        for start in range(0, len(short_ids), chunk):
            batch = short_ids[start : start + chunk]
            flt = "openalex_id:" + "|".join(batch)
            data = self._get_json(f"{BASE}/works?filter={flt}&per-page={chunk}&select={_SELECT}")
            for raw in data.get("results") or []:
                out.append(normalize_work(raw))
        return out

    def fetch_works_by_doi(self, dois: list[str], chunk: int = 50) -> list[Work]:
        """Batch-fetch works by DOI (OR-filter). Used to resolve a Crossref reference list."""
        out: list[Work] = []
        for start in range(0, len(dois), chunk):
            batch = dois[start : start + chunk]
            flt = "doi:" + "|".join(quote(d, safe="") for d in batch)
            data = self._get_json(f"{BASE}/works?filter={flt}&per-page={chunk}&select={_SELECT}")
            for raw in data.get("results") or []:
                out.append(normalize_work(raw))
        return out
