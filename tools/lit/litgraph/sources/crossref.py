"""Crossref client — used only to get clean `family, given` author names for the focal
paper (OpenAlex gives 'First Last', which is unreliable to re-split). Best-effort: any
failure degrades to the OpenAlex names."""

from __future__ import annotations

import time
from collections.abc import Callable
from urllib.parse import quote

import requests

BASE = "https://api.crossref.org/works"
GetJson = Callable[[str], dict]


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
