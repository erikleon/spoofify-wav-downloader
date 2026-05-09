"""Convert downloaded audio files to high-quality AIFF (PCM 24-bit / 48 kHz)."""

from __future__ import annotations

import subprocess
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from mutagen.aiff import AIFF
from mutagen.id3 import TIT1, TIT2, TALB, TDRC, TPOS, TPE1, TPE2, TRCK, Encoding

if TYPE_CHECKING:
    from .spotify import TrackInfo


# Target AIFF parameters — CD-quality or better
SAMPLE_RATE = 48_000      # Hz
BIT_DEPTH = 24            # bits per sample
CHANNELS = 2              # stereo


def write_id3_tags(
    aiff_path: Path,
    track: "TrackInfo",
    playlist_name: str | None = None,
) -> None:
    audio = AIFF(str(aiff_path))
    if audio.tags is None:
        audio.add_tags()

    enc = Encoding.UTF16  # UTF-8 (3) is ID3v2.4-only; UTF-16 is v2.3-safe

    audio.tags.add(TIT2(encoding=enc, text=track.title))
    audio.tags.add(TPE1(encoding=enc, text=track.artist_string))
    audio.tags.add(TALB(encoding=enc, text=track.album))
    audio.tags.add(TPE2(encoding=enc, text=track.album_artist))
    audio.tags.add(TRCK(encoding=enc, text=f"{track.track_number}/{track.total_tracks}"))
    audio.tags.add(TPOS(encoding=enc, text=str(track.disc_number)))
    if track.release_date:
        audio.tags.add(TDRC(encoding=enc, text=track.release_date))
    if playlist_name:
        audio.tags.add(TIT1(encoding=enc, text=playlist_name))

    # update_to_v23() converts TDRC → TYER (and other v2.4-only frames)
    audio.tags.update_to_v23()
    audio.save(v2_version=3)


def to_aiff(
    source: Path,
    output_dir: Path | None = None,
    *,
    track: TrackInfo | None = None,
    playlist_name: str | None = None,
    keep_original: bool = False,
) -> Path:
    """Convert *source* to a PCM AIFF file and return the output path.

    Parameters
    ----------
    source:
        Path to any audio file ffmpeg can decode.
    output_dir:
        Directory for the .aiff.  Defaults to the same directory as *source*.
    track:
        Optional track metadata to embed as ID3v2 tags.
    playlist_name:
        Optional playlist name to embed as a grouping tag.
    keep_original:
        If ``False`` (default), the source file is deleted after conversion.
    """
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise FileNotFoundError("ffmpeg is required for AIFF conversion.")

    if output_dir is None:
        output_dir = source.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    aiff_name = track.safe_title if track is not None else source.stem
    aiff_path = output_dir / f"{aiff_name}.aiff"

    if aiff_path.exists():
        if not keep_original:
            source.unlink(missing_ok=True)
        return aiff_path

    cmd = [
        ffmpeg,
        "-y",
        "-i", str(source),
        "-vn",                          # drop video/artwork streams
        "-acodec", "pcm_s24be",         # signed 24-bit big-endian PCM (AIFF standard)
        "-ar", str(SAMPLE_RATE),
        "-ac", str(CHANNELS),
        str(aiff_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg conversion failed for {source.name}:\n{result.stderr}"
        )

    if track is not None:
        write_id3_tags(aiff_path, track, playlist_name)

    if not keep_original:
        source.unlink(missing_ok=True)

    return aiff_path
