"""Convert downloaded audio files to high-quality WAV (PCM 24-bit / 48 kHz)."""

from __future__ import annotations

import subprocess
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .spotify import TrackInfo


# Target WAV parameters — CD-quality or better
SAMPLE_RATE = 48_000      # Hz
BIT_DEPTH = 24            # bits per sample
CHANNELS = 2              # stereo


def to_wav(
    source: Path,
    output_dir: Path | None = None,
    *,
    track: TrackInfo | None = None,
    playlist_name: str | None = None,
    keep_original: bool = False,
) -> Path:
    """Convert *source* to a PCM WAV file and return the output path.

    Parameters
    ----------
    source:
        Path to any audio file ffmpeg can decode.
    output_dir:
        Directory for the .wav.  Defaults to the same directory as *source*.
    track:
        Optional track metadata to embed as ID3v2 tags.
    playlist_name:
        Optional playlist name to embed as a grouping tag.
    keep_original:
        If ``False`` (default), the source file is deleted after conversion.
    """
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise FileNotFoundError("ffmpeg is required for WAV conversion.")

    if output_dir is None:
        output_dir = source.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    wav_path = output_dir / f"{source.stem}.wav"

    if wav_path.exists():
        if not keep_original:
            source.unlink(missing_ok=True)
        return wav_path

    cmd = [
        ffmpeg,
        "-y",
        "-i", str(source),
        "-vn",                          # drop video/artwork streams
        "-acodec", "pcm_s24le",         # signed 24-bit little-endian PCM
        "-ar", str(SAMPLE_RATE),
        "-ac", str(CHANNELS),
    ]

    # Embed metadata as ID3v2 tags (required for Apple Music to read them)
    if track is not None:
        cmd += ["-write_id3v2", "1"]
        cmd += ["-metadata", f"title={track.title}"]
        cmd += ["-metadata", f"artist={track.artist_string}"]
        cmd += ["-metadata", f"album={track.album}"]
        cmd += ["-metadata", f"album_artist={track.album_artist}"]
        cmd += ["-metadata", f"track={track.track_number}/{track.total_tracks}"]
        cmd += ["-metadata", f"disc={track.disc_number}"]
        if track.release_date:
            cmd += ["-metadata", f"date={track.release_date}"]
        if playlist_name:
            cmd += ["-metadata", f"grouping={playlist_name}"]

    cmd.append(str(wav_path))

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg conversion failed for {source.name}:\n{result.stderr}"
        )

    if not keep_original:
        source.unlink(missing_ok=True)

    return wav_path
