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

from .bandcamp import (
    BANDCAMP_ALBUM_URL_RE,
    BANDCAMP_ARTIST_URL_RE,
    get_album_tracks as get_bandcamp_album_tracks,
    get_artist_albums as get_bandcamp_artist_albums,
)
from .converter import to_aiff, write_id3_tags
from .downloader import search_and_download
from .spotify import get_album_tracks as get_spotify_album_tracks, get_playlist_tracks

console = Console()


_SPOTIFY_ALBUM_RE = re.compile(
    r"(?:https?://)?(?:open\.)?spotify\.com/album/([a-zA-Z0-9]+)"
)


def _detect_input_type(url: str) -> str:
    if _SPOTIFY_ALBUM_RE.search(url):
        return "spotify_album"
    if BANDCAMP_ALBUM_URL_RE.search(url):
        return "bandcamp_album"
    if BANDCAMP_ARTIST_URL_RE.search(url):
        return "bandcamp_artist"
    return "spotify_playlist"


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
        help="Spotify playlist/album URL or ID, or Bandcamp album URL",
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
    parser.add_argument(
        "-s",
        "--source",
        choices=["auto", "bandcamp", "youtube", "soundcloud"],
        default="auto",
        help="Audio source: auto (Bandcamp→YouTube→SoundCloud), bandcamp, youtube, or soundcloud (default: auto)",
    )
    return parser.parse_args(argv)


def _download_tracks(
    tracks: list,
    collection_name: str,
    collection_dir: "Path",
    source: str,
    keep_original: bool,
) -> tuple[int, list[str], dict[str, int]]:
    """Download *tracks* into *collection_dir*. Returns (succeeded, failed, source_counts)."""
    succeeded = 0
    failed: list[str] = []
    source_counts: dict[str, int] = {"bandcamp": 0, "youtube": 0, "soundcloud": 0}

    collection_dir.mkdir(parents=True, exist_ok=True)

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
                track_dir = (
                    collection_dir
                    / _sanitize_dirname(track.artist_string)
                    / _sanitize_dirname(track.album)
                )
                downloaded, source_used = search_and_download(
                    track, track_dir, source=source,
                )
                if downloaded is None:
                    failed.append(f"{track.artist_string} - {track.title}")
                    progress.advance(task)
                    continue

                to_aiff(
                    downloaded,
                    track_dir,
                    track=track,
                    playlist_name=collection_name,
                    keep_original=keep_original,
                )
                succeeded += 1
                if source_used in source_counts:
                    source_counts[source_used] += 1
            except Exception as exc:
                failed.append(f"{track.artist_string} - {track.title} ({exc})")

            progress.advance(task)

    return succeeded, failed, source_counts


def _print_summary(
    succeeded: int,
    failed: list[str],
    source_counts: dict[str, int],
    output_dir: "Path",
) -> None:
    console.print()
    console.print(f"[bold green]✓ {succeeded}[/bold green] tracks downloaded as .aiff")
    parts = []
    if source_counts["bandcamp"]:
        parts.append(f"[green]{source_counts['bandcamp']} from Bandcamp[/green]")
    if source_counts["youtube"]:
        parts.append(f"[yellow]{source_counts['youtube']} from YouTube[/yellow]")
    if source_counts["soundcloud"]:
        parts.append(f"[blue]{source_counts['soundcloud']} from SoundCloud[/blue]")
    if parts:
        console.print(f"  ({', '.join(parts)})")
    if failed:
        console.print(f"[bold red]✗ {len(failed)}[/bold red] tracks failed:")
        for name in failed:
            console.print(f"  • {name}")
    console.print(f"\nFiles saved to: [bold]{output_dir}[/bold]")


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    args = _parse_args(argv)

    console.print(
        f"\n[bold cyan]spotify-wav-dl[/bold cyan]  —  lossless playlist downloader\n"
    )

    if args.source == "auto":
        console.print("Sources: [green]Bandcamp (FLAC)[/green] → [yellow]YouTube[/yellow] → [blue]SoundCloud[/blue] fallback")
    elif args.source == "bandcamp":
        console.print("Sources: [green]Bandcamp (FLAC)[/green] only")
    elif args.source == "soundcloud":
        console.print("Sources: [blue]SoundCloud[/blue] only")
    else:
        console.print("Sources: [yellow]YouTube[/yellow] only")
    console.print()

    input_type = _detect_input_type(args.playlist)

    # --- Bandcamp artist: download all albums ---
    if input_type == "bandcamp_artist":
        with console.status("[bold green]Fetching artist discography from Bandcamp…"):
            try:
                artist_name, album_urls = get_bandcamp_artist_albums(args.playlist)
            except Exception as exc:
                console.print(f"[bold red]Error:[/bold red] {exc}")
                sys.exit(1)

        if not album_urls:
            console.print("[yellow]No albums found for this artist.[/yellow]")
            return

        console.print(f'Artist: [bold]{artist_name}[/bold]  ({len(album_urls)} albums)\n')
        artist_dir = args.output / _sanitize_dirname(artist_name)

        total_succeeded = 0
        total_failed: list[str] = []
        total_source_counts: dict[str, int] = {"bandcamp": 0, "youtube": 0, "soundcloud": 0}

        for i, album_url in enumerate(album_urls, 1):
            with console.status(f"[bold green]Fetching album {i}/{len(album_urls)}…"):
                try:
                    album_name, tracks = get_bandcamp_album_tracks(album_url)
                except Exception as exc:
                    console.print(f"[bold red]  Skipping album (error):[/bold red] {exc}")
                    continue

            console.print(f'  Album [bold]{i}/{len(album_urls)}[/bold]: [bold]{album_name}[/bold]  ({len(tracks)} tracks)')
            if not tracks:
                continue

            succeeded, failed, source_counts = _download_tracks(
                tracks, album_name, args.output, args.source, args.keep_original
            )
            total_succeeded += succeeded
            total_failed.extend(failed)
            for k in total_source_counts:
                total_source_counts[k] += source_counts[k]

        _print_summary(total_succeeded, total_failed, total_source_counts, args.output)
        return

    # --- Single album or playlist ---
    _labels = {
        "spotify_album":    ("Fetching album from Spotify…",    "Album"),
        "bandcamp_album":   ("Fetching album from Bandcamp…",   "Album"),
        "spotify_playlist": ("Fetching playlist from Spotify…", "Playlist"),
    }
    status_msg, kind_label = _labels[input_type]

    with console.status(f"[bold green]{status_msg}"):
        try:
            if input_type == "spotify_album":
                collection_name, tracks = get_spotify_album_tracks(args.playlist)
            elif input_type == "bandcamp_album":
                collection_name, tracks = get_bandcamp_album_tracks(args.playlist)
            else:
                collection_name, tracks = get_playlist_tracks(args.playlist)
        except Exception as exc:
            console.print(f"[bold red]Error:[/bold red] {exc}")
            sys.exit(1)

    console.print(
        f'{kind_label}: [bold]{collection_name}[/bold]  ({len(tracks)} tracks)\n'
    )

    if not tracks:
        console.print("[yellow]No tracks found.[/yellow]")
        return

    collection_dir = args.output / _sanitize_dirname(collection_name)
    succeeded, failed, source_counts = _download_tracks(
        tracks, collection_name, collection_dir, args.source, args.keep_original
    )
    _print_summary(succeeded, failed, source_counts, collection_dir)


if __name__ == "__main__":
    main()
