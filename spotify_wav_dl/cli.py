"""CLI entry-point for spotify-wav-dl."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from .converter import to_wav
from .downloader import search_and_download
from .spotify import get_playlist_tracks

console = Console()


def _sanitize_dirname(name: str) -> str:
    """Make a string safe to use as a directory name."""
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="spotify-wav-dl",
        description="Download songs from a Spotify playlist as high-quality .wav files.",
    )
    parser.add_argument(
        "playlist",
        help="Spotify playlist URL or ID",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("downloads"),
        help="Base output directory (default: ./downloads)",
    )
    parser.add_argument(
        "--keep-original",
        action="store_true",
        help="Keep the intermediate (non-WAV) file after conversion",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    args = _parse_args(argv)

    console.print(
        f"\n[bold cyan]spotify-wav-dl[/bold cyan]  —  lossless playlist downloader\n"
    )

    # --- Fetch playlist metadata ---
    with console.status("[bold green]Fetching playlist from Spotify…"):
        try:
            playlist_name, tracks = get_playlist_tracks(args.playlist)
        except Exception as exc:
            console.print(f"[bold red]Error:[/bold red] {exc}")
            sys.exit(1)

    console.print(
        f'Playlist: [bold]{playlist_name}[/bold]  ({len(tracks)} tracks)\n'
    )

    if not tracks:
        console.print("[yellow]No tracks found.[/yellow]")
        return

    playlist_dir = args.output / _sanitize_dirname(playlist_name)
    playlist_dir.mkdir(parents=True, exist_ok=True)

    succeeded = 0
    failed: list[str] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Downloading", total=len(tracks))

        for track in tracks:
            progress.update(
                task,
                description=f"[cyan]{track.artist_string} - {track.title}[/cyan]",
            )

            try:
                downloaded = search_and_download(track, playlist_dir)
                if downloaded is None:
                    failed.append(f"{track.artist_string} - {track.title}")
                    progress.advance(task)
                    continue

                to_wav(
                    downloaded,
                    playlist_dir,
                    keep_original=args.keep_original,
                )
                succeeded += 1
            except Exception as exc:
                failed.append(f"{track.artist_string} - {track.title} ({exc})")

            progress.advance(task)

    # --- Summary ---
    console.print()
    console.print(f"[bold green]✓ {succeeded}[/bold green] tracks downloaded as .wav")
    if failed:
        console.print(f"[bold red]✗ {len(failed)}[/bold red] tracks failed:")
        for name in failed:
            console.print(f"  • {name}")

    console.print(f"\nFiles saved to: [bold]{playlist_dir}[/bold]")


if __name__ == "__main__":
    main()
