"""Download audio from multiple sources, prioritising lossless quality.

Source priority (in auto mode):
  1. Bandcamp – lossless FLAC / WAV when available
  2. YouTube – best available audio via yt-dlp (lossless-preferred format sort)
  3. SoundCloud – additional catalogue coverage via yt-dlp
"""

from __future__ import annotations

import subprocess
import shutil
from pathlib import Path

from .bandcamp import search_bandcamp
from .spotify import TrackInfo

# ── YouTube helpers ───────────────────────────────────────────────────

# Preferred yt-dlp audio quality sort order:
#   1. FLAC / ALAC / WAV (lossless codecs)
#   2. Highest bitrate available
#   3. Opus / Vorbis / AAC as fallback
_YDL_FORMAT_SORT = "acodec:flac,acodec:alac,acodec:wav,abr,acodec:opus,acodec:vorbis,acodec:aac"


def _find_yt_dlp() -> str:
    """Return the path to yt-dlp, raising a clear error if missing."""
    path = shutil.which("yt-dlp")
    if path is None:
        raise FileNotFoundError(
            "yt-dlp is not installed or not on PATH. "
            "Install it: pip install yt-dlp  (or brew install yt-dlp)"
        )
    return path


def _find_ffmpeg() -> str:
    """Return the path to ffmpeg, raising a clear error if missing."""
    path = shutil.which("ffmpeg")
    if path is None:
        raise FileNotFoundError(
            "ffmpeg is not installed or not on PATH. "
            "Install it: brew install ffmpeg  (or apt install ffmpeg)"
        )
    return path


# ── Bandcamp helpers ──────────────────────────────────────────────────


def _download_from_bandcamp(
    track: TrackInfo,
    output_dir: Path,
    *,
    max_search_results: int = 5,
) -> Path | None:
    """Search Bandcamp for *track* and download the best-quality audio."""
    yt_dlp = _find_yt_dlp()
    _find_ffmpeg()

    results = search_bandcamp(track.search_query, max_results=max_search_results)
    if not results:
        return None

    output_template = str(output_dir / f"{track.safe_filename}.%(ext)s")
    track_duration = track.duration_ms // 1000

    for result in results:
        if result.get("duration_secs") is not None:
            if abs(result["duration_secs"] - track_duration) > 30:
                continue

        cmd = [
            yt_dlp,
            "--no-playlist",
            "-f", "bestaudio",
            "-S", _YDL_FORMAT_SORT,
            "--match-filter",
            f"duration >? {track_duration - 30} & duration <? {track_duration + 30}",
            "-x",
            "-o", output_template,
            "--no-overwrites",
            "--no-warnings",
            "-q",
            result["url"],
        ]

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        if proc.returncode == 0:
            for ext in ("flac", "opus", "wav", "m4a", "ogg", "mp3", "webm"):
                candidate = output_dir / f"{track.safe_filename}.{ext}"
                if candidate.exists():
                    return candidate

    return None


# ── YouTube helpers ───────────────────────────────────────────────────


def _download_from_youtube(
    track: TrackInfo,
    output_dir: Path,
    *,
    max_search_results: int = 5,
) -> Path | None:
    """Search YouTube for *track* and download the best-quality audio."""
    yt_dlp = _find_yt_dlp()
    _find_ffmpeg()

    output_template = str(output_dir / f"{track.safe_filename}.%(ext)s")
    query = f"ytsearch{max_search_results}:{track.search_query}"

    cmd = [
        yt_dlp,
        "--no-playlist",
        "-f", "bestaudio",
        "-S", _YDL_FORMAT_SORT,
        "--match-filter", f"duration >? {(track.duration_ms // 1000) - 30} & duration <? {(track.duration_ms // 1000) + 30}",
        "-x",
        "-o", output_template,
        "--no-overwrites",
        "--no-warnings",
        "-q",
        query,
        "--playlist-items", "1",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if result.returncode != 0:
        return None

    for ext in ("flac", "opus", "wav", "m4a", "ogg", "mp3", "webm"):
        candidate = output_dir / f"{track.safe_filename}.{ext}"
        if candidate.exists():
            return candidate

    return None


# ── SoundCloud helpers ────────────────────────────────────────────────

def _download_from_soundcloud(
    track: TrackInfo,
    output_dir: Path,
    *,
    max_search_results: int = 5,
) -> Path | None:
    """Search SoundCloud for *track* and download the best-quality audio."""
    yt_dlp = _find_yt_dlp()
    _find_ffmpeg()

    output_template = str(output_dir / f"{track.safe_filename}.%(ext)s")
    query = f"scsearch{max_search_results}:{track.search_query}"

    cmd = [
        yt_dlp,
        "--no-playlist",
        "-f", "bestaudio",
        "-S", _YDL_FORMAT_SORT,
        "--match-filter", f"duration >? {(track.duration_ms // 1000) - 30} & duration <? {(track.duration_ms // 1000) + 30}",
        "-x",
        "-o", output_template,
        "--no-overwrites",
        "--no-warnings",
        "-q",
        query,
        "--playlist-items", "1",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if result.returncode != 0:
        return None

    for ext in ("flac", "opus", "wav", "m4a", "ogg", "mp3", "webm"):
        candidate = output_dir / f"{track.safe_filename}.{ext}"
        if candidate.exists():
            return candidate

    return None


# ── Unified download function ────────────────────────────────────────

def search_and_download(
    track: TrackInfo,
    output_dir: Path,
    *,
    source: str = "auto",
) -> tuple[Path | None, str]:
    """Download *track* to *output_dir*, returning (path, source_used).

    *source* controls where to look:
      - ``"auto"``       – try Bandcamp → YouTube → SoundCloud
      - ``"bandcamp"``   – Bandcamp only
      - ``"youtube"``    – YouTube only
      - ``"soundcloud"`` – SoundCloud only

    Returns ``(None, "")`` if every source fails.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    sources: list[str] = []

    if source == "auto":
        sources = ["bandcamp", "youtube", "soundcloud"]
    else:
        sources = [source]

    for src in sources:
        path: Path | None = None

        if src == "bandcamp":
            try:
                path = _download_from_bandcamp(track, output_dir)
            except Exception:
                path = None

        elif src == "youtube":
            try:
                path = _download_from_youtube(track, output_dir)
            except Exception:
                path = None

        elif src == "soundcloud":
            try:
                path = _download_from_soundcloud(track, output_dir)
            except Exception:
                path = None

        if path is not None:
            return path, src

    return None, ""
