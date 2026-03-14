"""Download audio with Deezer (FLAC) as primary source and YouTube as fallback.

Source priority:
  1. Deezer – true lossless FLAC via ISRC / search matching
  2. YouTube – best available audio via yt-dlp (lossless-preferred format sort)
"""

from __future__ import annotations

import os
import subprocess
import shutil
from pathlib import Path

from .deezer import download_from_deezer
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


# ── Unified download function ────────────────────────────────────────

def search_and_download(
    track: TrackInfo,
    output_dir: Path,
    *,
    source: str = "auto",
) -> tuple[Path | None, str]:
    """Download *track* to *output_dir*, returning (path, source_used).

    *source* controls where to look:
      - ``"auto"``    – try Deezer first, fall back to YouTube
      - ``"deezer"``  – Deezer only
      - ``"youtube"`` – YouTube only

    Returns ``(None, "")`` if every source fails.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    deezer_arl = os.environ.get("DEEZER_ARL", "")

    sources: list[str] = []

    if source == "auto":
        if deezer_arl:
            sources = ["deezer", "youtube"]
        else:
            sources = ["youtube"]
    else:
        sources = [source]

    for src in sources:
        path: Path | None = None

        if src == "deezer":
            if not deezer_arl:
                continue
            try:
                path = download_from_deezer(track, output_dir, deezer_arl)
            except Exception:
                path = None

        elif src == "youtube":
            try:
                path = _download_from_youtube(track, output_dir)
            except Exception:
                path = None

        if path is not None:
            return path, src

    return None, ""
