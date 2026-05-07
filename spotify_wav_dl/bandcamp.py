"""Search Bandcamp for tracks and return downloadable URLs."""

from __future__ import annotations

import json
import re

import requests
from bs4 import BeautifulSoup

from .spotify import TrackInfo

_SEARCH_URL = "https://bandcamp.com/search"
BANDCAMP_ALBUM_URL_RE = re.compile(
    r"https?://[\w-]+\.bandcamp\.com/album/[\w-]+"
)
BANDCAMP_ARTIST_URL_RE = re.compile(
    r"https?://[\w-]+\.bandcamp\.com(?:/(?:music|releases)?)?/?$"
)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


def _parse_iso_duration(duration: str) -> int:
    """Parse ISO 8601 duration (e.g. PT4M30S) to milliseconds."""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", duration)
    if not m:
        return 0
    h = int(m.group(1) or 0)
    mn = int(m.group(2) or 0)
    s = float(m.group(3) or 0)
    return int((h * 3600 + mn * 60 + s) * 1000)


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


def get_album_tracks(url: str) -> tuple[str, list[TrackInfo]]:
    """Scrape a Bandcamp album page and return (album_name, tracks).

    Parses the JSON-LD embedded in the page to extract track metadata and
    per-track URLs for direct download.
    """
    resp = requests.get(url, headers=_HEADERS, timeout=10)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    ld_script = soup.find("script", {"type": "application/ld+json"})
    if not ld_script:
        raise ValueError(f"Could not find album metadata on Bandcamp page: {url}")

    data = json.loads(ld_script.string)
    album_name = data["name"]
    artist_name = data.get("byArtist", {}).get("name", "")
    release_date = data.get("datePublished", "")
    items = data.get("track", {}).get("itemListElement", [])
    total_tracks = len(items)

    tracks: list[TrackInfo] = []
    for item in items:
        td = item.get("item", {})
        tracks.append(
            TrackInfo(
                title=td.get("name", ""),
                artists=[artist_name],
                album=album_name,
                album_artist=artist_name,
                disc_number=1,
                duration_ms=_parse_iso_duration(td.get("duration", "")),
                isrc=None,
                track_number=item.get("position", 0),
                total_tracks=total_tracks,
                release_date=release_date,
                spotify_id="",
                source_url=td.get("@id") or None,
            )
        )

    return album_name, tracks


def get_artist_albums(url: str) -> tuple[str, list[str]]:
    """Scrape a Bandcamp artist page and return (artist_name, album_urls)."""
    m = re.match(r"(https?://[\w-]+\.bandcamp\.com)", url)
    if not m:
        raise ValueError(f"Invalid Bandcamp artist URL: {url}")
    base_url = m.group(1)

    resp = None
    for try_url in (f"{base_url}/music", base_url):
        r = requests.get(try_url, headers=_HEADERS, timeout=10)
        if r.status_code == 200:
            resp = r
            break
    if resp is None:
        raise ValueError(f"Could not fetch Bandcamp artist page: {url}")

    soup = BeautifulSoup(resp.text, "html.parser")

    artist_name = ""
    ld_script = soup.find("script", {"type": "application/ld+json"})
    if ld_script:
        try:
            data = json.loads(ld_script.string)
            artist_name = data.get("name", "")
        except (json.JSONDecodeError, AttributeError):
            pass
    if not artist_name:
        title_el = soup.select_one("#band-name-location .title")
        if title_el:
            artist_name = title_el.get_text(strip=True)
    if not artist_name:
        subdomain_m = re.match(r"https?://([\w-]+)\.bandcamp\.com", base_url)
        if subdomain_m:
            artist_name = subdomain_m.group(1)

    seen: set[str] = set()
    album_urls: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.match(r"^/album/[\w-]+", href):
            clean = href.split("?")[0].rstrip("/")
            full = base_url + clean
            if full not in seen:
                seen.add(full)
                album_urls.append(full)

    return artist_name, album_urls
