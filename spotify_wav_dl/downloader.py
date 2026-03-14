"""Download audio from YouTube via yt-dlp, prioritising lossless quality."""

from __future__ import annotations

import subprocess
import shutil
from pathlib import Path

from .spotify import TrackInfo

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


def search_and_download(
    track: TrackInfo,
    output_dir: Path,
    *,
    max_search_results: int = 5,
) -> Path | None:
    """Search YouTube for *track* and download the best-quality audio.

    Returns the path to the downloaded file, or ``None`` on failure.
    The file will be in its original codec (FLAC, Opus, etc.) — the
    caller is responsible for WAV conversion.
    """
    yt_dlp = _find_yt_dlp()
    _find_ffmpeg()  # Ensure ffmpeg exists early

    output_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(output_dir / f"{track.safe_filename}.%(ext)s")

    query = f"ytsearch{max_search_results}:{track.search_query}"

    cmd = [
        yt_dlp,
        "--no-playlist",
        # Audio only, best quality, prefer lossless codecs
        "-f", "bestaudio",
        "-S", _YDL_FORMAT_SORT,
        # Duration filter: skip results that differ from Spotify by >30 s
        "--match-filter", f"duration >? {(track.duration_ms // 1000) - 30} & duration <? {(track.duration_ms // 1000) + 30}",
        # Extract audio stream (no mux into video container)
        "-x",
        # Output path
        "-o", output_template,
        # Don't re-download if file exists
        "--no-overwrites",
        # Quiet but show errors
        "--no-warnings",
        "-q",
        # Search query
        query,
        # Only keep the first match that passes filters
        "--playlist-items", "1",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if result.returncode != 0:
        return None

    # yt-dlp may choose different extensions; find the actually-written file
    for ext in ("flac", "opus", "wav", "m4a", "ogg", "mp3", "webm"):
        candidate = output_dir / f"{track.safe_filename}.{ext}"
        if candidate.exists():
            return candidate

    return None
