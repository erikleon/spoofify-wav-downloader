"""Convert downloaded audio files to high-quality WAV (PCM 24-bit / 48 kHz)."""

from __future__ import annotations

import subprocess
import shutil
from pathlib import Path


# Target WAV parameters — CD-quality or better
SAMPLE_RATE = 48_000      # Hz
BIT_DEPTH = 24            # bits per sample
CHANNELS = 2              # stereo


def to_wav(
    source: Path,
    output_dir: Path | None = None,
    *,
    keep_original: bool = False,
) -> Path:
    """Convert *source* to a PCM WAV file and return the output path.

    Parameters
    ----------
    source:
        Path to any audio file ffmpeg can decode.
    output_dir:
        Directory for the .wav.  Defaults to the same directory as *source*.
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
        str(wav_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg conversion failed for {source.name}:\n{result.stderr}"
        )

    if not keep_original:
        source.unlink(missing_ok=True)

    return wav_path
