"""Download FLAC audio from Deezer using track ISRC or search matching.

Deezer provides true lossless FLAC streams, making it the preferred source
for high-quality audio.  Falls back gracefully when a track cannot be found.
"""

from __future__ import annotations

import hashlib
import json
import os
import struct
from pathlib import Path

import requests
from Crypto.Cipher import Blowfish

from .spotify import TrackInfo

# ── Deezer API endpoints ──────────────────────────────────────────────
_API_BASE = "https://api.deezer.com"
_PRIVATE_API = "https://www.deezer.com/ajax/gw-light.php"

# Quality tiers (highest first)
_QUALITY_FLAC = 9   # FLAC 16-bit/44.1 kHz
_QUALITY_320 = 3    # MP3 320 kbps
_QUALITY_128 = 1    # MP3 128 kbps

_QUALITIES = [
    (_QUALITY_FLAC, "FLAC", "flac"),
    (_QUALITY_320, "MP3 320", "mp3"),
    (_QUALITY_128, "MP3 128", "mp3"),
]


class DeezerError(Exception):
    pass


# ── Session management ────────────────────────────────────────────────

class _DeezerSession:
    """Manages authentication and API calls to Deezer."""

    def __init__(self, arl: str) -> None:
        self._session = requests.Session()
        self._session.cookies.set("arl", arl, domain=".deezer.com")
        self._csrf_token: str = ""
        self._license_token: str = ""
        self._user_id: str = ""
        self._authenticate()

    def _authenticate(self) -> None:
        """Initialize the session and retrieve tokens."""
        resp = self._gw_call("deezer.getUserData")
        user = resp.get("USER", {})
        self._user_id = str(user.get("USER_ID", "0"))
        if self._user_id == "0":
            raise DeezerError(
                "Invalid Deezer ARL token.  Log into deezer.com, open browser "
                "DevTools → Application → Cookies, and copy the 'arl' value."
            )
        self._csrf_token = resp.get("checkForm", "")
        self._license_token = user.get("OPTIONS", {}).get("license_token", "")

    def _gw_call(self, method: str, params: dict | None = None) -> dict:
        """Call the Deezer private gateway API."""
        url = _PRIVATE_API
        query = {
            "method": method,
            "input": "3",
            "api_version": "1.0",
            "api_token": self._csrf_token or "null",
        }
        resp = self._session.post(url, params=query, json=params or {})
        resp.raise_for_status()
        data = resp.json()
        if data.get("error"):
            raise DeezerError(f"Deezer API error: {data['error']}")
        return data.get("results", {})

    def get_track_info(self, track_id: str) -> dict:
        """Fetch full track info including download tokens."""
        return self._gw_call("song.getData", {"SNG_ID": track_id})

    def get_track_url(self, track_info: dict, quality: int) -> str | None:
        """Resolve the CDN download URL for a given quality tier."""
        track_token = track_info.get("TRACK_TOKEN")
        if not track_token:
            return None

        # Use the media endpoint to get the actual URL
        media_url = "https://media.deezer.com/v1/get_url"
        payload = {
            "license_token": self._license_token,
            "media": [{
                "type": "FULL",
                "formats": [{"cipher": "BF_CBC_STRIPE", "format": self._format_name(quality)}],
            }],
            "track_tokens": [track_token],
        }
        resp = self._session.post(media_url, json=payload)
        resp.raise_for_status()
        data = resp.json()

        try:
            sources = data["data"][0]["media"][0]["sources"]
            return sources[0]["url"]
        except (KeyError, IndexError):
            return None

    @staticmethod
    def _format_name(quality: int) -> str:
        return {
            _QUALITY_FLAC: "FLAC",
            _QUALITY_320: "MP3_320",
            _QUALITY_128: "MP3_128",
        }[quality]


# ── Crypto helpers ────────────────────────────────────────────────────

def _get_blowfish_key(track_id: str) -> bytes:
    """Derive the per-track Blowfish key used to decrypt Deezer streams."""
    secret = b"g4el58wc0zvf9na1"
    md5_id = hashlib.md5(track_id.encode("ascii")).hexdigest()
    key = bytes(
        md5_id[i] ^ md5_id[i + 16] ^ secret[i]
        for i in range(16)
    )
    return key


def _decrypt_chunk(chunk: bytes, key: bytes) -> bytes:
    """Decrypt a single 2048-byte chunk with Blowfish CBC."""
    iv = bytes([i for i in range(8)])
    cipher = Blowfish.new(key, Blowfish.MODE_CBC, iv)
    return cipher.decrypt(chunk)


def _download_and_decrypt(url: str, track_id: str, dest: Path) -> None:
    """Stream-download from *url*, decrypting every third 2048-byte chunk."""
    key = _get_blowfish_key(track_id)

    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()

    chunk_size = 2048
    chunk_index = 0

    with dest.open("wb") as f:
        buffer = b""
        for data in resp.iter_content(chunk_size=chunk_size):
            buffer += data
            while len(buffer) >= chunk_size:
                chunk = buffer[:chunk_size]
                buffer = buffer[chunk_size:]

                if chunk_index % 3 == 0:
                    chunk = _decrypt_chunk(chunk, key)

                f.write(chunk)
                chunk_index += 1

        # Write any remaining data (last partial chunk, unencrypted)
        if buffer:
            f.write(buffer)


# ── Public API ────────────────────────────────────────────────────────

def _find_track_id(track: TrackInfo) -> str | None:
    """Try to find a Deezer track ID via ISRC, then fall back to search."""
    # Try ISRC first (exact match)
    if track.isrc:
        resp = requests.get(
            f"{_API_BASE}/2.0/track/isrc:{track.isrc}",
            timeout=10,
        )
        if resp.ok:
            data = resp.json()
            if "id" in data and not data.get("error"):
                return str(data["id"])

    # Fall back to search
    query = f"{track.artist_string} {track.title}"
    resp = requests.get(
        f"{_API_BASE}/search/track",
        params={"q": query, "limit": 5},
        timeout=10,
    )
    if not resp.ok:
        return None

    data = resp.json()
    for result in data.get("data", []):
        # Basic sanity check: duration should be within 5 seconds
        if abs(result.get("duration", 0) - track.duration_ms // 1000) <= 5:
            return str(result["id"])

    # If no duration match, return the first result
    results = data.get("data", [])
    if results:
        return str(results[0]["id"])

    return None


def download_from_deezer(
    track: TrackInfo,
    output_dir: Path,
    arl: str,
) -> Path | None:
    """Download *track* from Deezer in the highest available quality.

    Returns the path to the downloaded file, or ``None`` if the track
    could not be found or downloaded.
    """
    # Find the Deezer track ID
    track_id = _find_track_id(track)
    if track_id is None:
        return None

    session = _DeezerSession(arl)
    track_info = session.get_track_info(track_id)

    # Try each quality tier from highest to lowest
    for quality, label, ext in _QUALITIES:
        url = session.get_track_url(track_info, quality)
        if url is None:
            continue

        output_dir.mkdir(parents=True, exist_ok=True)
        dest = output_dir / f"{track.safe_filename}.{ext}"

        if dest.exists():
            return dest

        try:
            sng_id = track_info.get("SNG_ID", track_id)
            _download_and_decrypt(url, sng_id, dest)
            return dest
        except Exception:
            dest.unlink(missing_ok=True)
            continue

    return None
