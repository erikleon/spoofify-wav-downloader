"""Spotify playlist and track metadata extraction using the Spotify Web API."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials


@dataclass
class TrackInfo:
    """Metadata for a single track."""

    title: str
    artists: list[str]
    album: str
    album_artist: str
    disc_number: int
    duration_ms: int
    isrc: str | None
    track_number: int
    total_tracks: int
    release_date: str
    spotify_id: str

    @property
    def artist_string(self) -> str:
        return ", ".join(self.artists)

    @property
    def safe_filename(self) -> str:
        """Return a filesystem-safe version of 'Artist - Title'."""
        name = f"{self.artist_string} - {self.title}"
        return re.sub(r'[<>:"/\\|?*]', "_", name).strip()

    @property
    def search_query(self) -> str:
        """Return a search query optimised for finding the track on YouTube."""
        return f"{self.artist_string} - {self.title}"


PLAYLIST_URL_RE = re.compile(
    r"(?:https?://)?(?:open\.)?spotify\.com/playlist/([a-zA-Z0-9]+)"
)


def _extract_playlist_id(url_or_id: str) -> str:
    """Extract a Spotify playlist ID from a URL or return the raw ID."""
    match = PLAYLIST_URL_RE.search(url_or_id)
    if match:
        return match.group(1)
    # Assume it's already a bare ID
    if re.fullmatch(r"[a-zA-Z0-9]{22}", url_or_id):
        return url_or_id
    raise ValueError(
        f"Invalid Spotify playlist URL or ID: {url_or_id!r}"
    )


def _build_client() -> spotipy.Spotify:
    """Build an authenticated Spotify client from environment variables."""
    client_id = os.environ.get("SPOTIPY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIPY_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise EnvironmentError(
            "SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET must be set. "
            "Copy .env.example to .env and fill in your credentials."
        )
    return spotipy.Spotify(
        auth_manager=SpotifyClientCredentials(
            client_id=client_id,
            client_secret=client_secret,
        )
    )


def get_playlist_tracks(url_or_id: str) -> tuple[str, list[TrackInfo]]:
    """Fetch every track in *url_or_id* and return (playlist_name, tracks).

    Handles Spotify's pagination automatically.
    """
    sp = _build_client()
    playlist_id = _extract_playlist_id(url_or_id)

    playlist = sp.playlist(playlist_id)
    playlist_name = playlist["name"]

    tracks: list[TrackInfo] = []
    results = playlist["tracks"]

    while True:
        for item in results["items"]:
            track = item.get("track")
            if track is None or track.get("is_local"):
                continue

            external_ids = track.get("external_ids", {})
            album = track["album"]
            tracks.append(
                TrackInfo(
                    title=track["name"],
                    artists=[a["name"] for a in track["artists"]],
                    album=album["name"],
                    album_artist=album["artists"][0]["name"] if album.get("artists") else "",
                    disc_number=track.get("disc_number", 1),
                    duration_ms=track["duration_ms"],
                    isrc=external_ids.get("isrc"),
                    track_number=track["track_number"],
                    total_tracks=album.get("total_tracks", 0),
                    release_date=album.get("release_date", ""),
                    spotify_id=track["id"],
                )
            )

        if results["next"]:
            results = sp.next(results)
        else:
            break

    return playlist_name, tracks
