"""Search Bandcamp for tracks and return downloadable URLs."""

from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

_SEARCH_URL = "https://bandcamp.com/search"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


def _parse_duration(text: str) -> int | None:
    """Parse a duration string like '03:45' into seconds."""
    m = re.match(r"(\d+):(\d+)", text.strip())
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    return None


def search_bandcamp(query: str, *, max_results: int = 5) -> list[dict]:
    """Search Bandcamp for tracks matching *query*.

    Returns a list of dicts with keys: ``url``, ``title``, ``artist``,
    and optionally ``duration_secs``.
    """
    resp = requests.get(
        _SEARCH_URL,
        params={"q": query, "item_type": "t"},
        headers=_HEADERS,
        timeout=10,
    )
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    results: list[dict] = []

    for item in soup.select(".searchresult"):
        heading = item.select_one(".heading a")
        subhead = item.select_one(".subhead")
        url_el = item.select_one(".itemurl a")

        if not heading or not url_el:
            continue

        url = url_el.get("href", "")
        if not url:
            continue

        entry: dict = {
            "url": url.strip(),
            "title": heading.get_text(strip=True),
            "artist": subhead.get_text(strip=True).lstrip("by ") if subhead else "",
        }

        length_el = item.select_one(".length")
        if length_el:
            secs = _parse_duration(length_el.get_text())
            if secs is not None:
                entry["duration_secs"] = secs

        results.append(entry)
        if len(results) >= max_results:
            break

    return results
