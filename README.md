# spotify-wav-downloader

Download songs from a Spotify playlist or album, a Bandcamp album, or an entire Bandcamp artist discography as high-quality lossless **.wav** files (PCM 24-bit / 48 kHz).

## How it works

1. Reads track metadata from Spotify or Bandcamp (title, artist, album, duration, ISRC).
2. **Bandcamp (preferred):** For Bandcamp URLs, downloads audio directly from the source page. For Spotify inputs, searches Bandcamp for lossless **FLAC / WAV** downloads.
3. **YouTube (fallback):** If Bandcamp doesn't have the track, searches YouTube via **yt-dlp**, prioritising lossless codecs (FLAC → ALAC → WAV) and highest bitrate.
4. **SoundCloud (fallback):** If neither Bandcamp nor YouTube has the track, searches SoundCloud via **yt-dlp**.
5. Converts the downloaded audio to **WAV** (signed 24-bit PCM, 48 kHz stereo) using **ffmpeg**.

## Prerequisites

- **Python 3.10+**
- **ffmpeg** — `brew install ffmpeg` (macOS) or `apt install ffmpeg` (Linux)
- **yt-dlp** — installed automatically with pip, or `brew install yt-dlp`
- A **Spotify Developer** account with a Client ID and Secret → [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)

## Setup

```bash
# Clone the repo
git clone https://github.com/your-user/spotify-wav-downloader.git
cd spotify-wav-downloader

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Or install as a CLI tool
pip install .

# Configure Spotify credentials
cp .env.example .env
# Edit .env and fill in SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET
```

## Usage

```bash
# Spotify playlist
spotify-wav-dl "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"

# Spotify album
spotify-wav-dl "https://open.spotify.com/album/4eLPsYPBmXABThSJ821sqY"

# Bandcamp album
spotify-wav-dl "https://artist.bandcamp.com/album/album-name"

# Bandcamp artist — downloads every album in the discography
spotify-wav-dl "https://artist.bandcamp.com"

# Custom output directory
spotify-wav-dl "https://open.spotify.com/playlist/..." -o ~/Music

# Keep intermediate (non-WAV) files
spotify-wav-dl "https://open.spotify.com/playlist/..." --keep-original

# Force a specific source
spotify-wav-dl "https://open.spotify.com/playlist/..." --source bandcamp
spotify-wav-dl "https://open.spotify.com/playlist/..." --source youtube
spotify-wav-dl "https://open.spotify.com/playlist/..." --source soundcloud
```

## Output

Tracks are saved under `./downloads/` organised by artist and album:

```
downloads/
  Playlist or Album Name/
    Artist Name/
      Album Name/
        Track Title.wav
        Track Title.wav
        ...
```

For a Bandcamp artist download all albums land directly under the output directory:

```
downloads/
  Artist Name/
    Album Name/
      Track Title.wav
      ...
  Another Album/
    Track Title.wav
    ...
```

## Audio quality

The tool tries sources in order of quality:

### Source priority

| Priority | Source     | Format     | Quality                        |
| -------- | ---------- | ---------- | ------------------------------ |
| 1        | Bandcamp   | FLAC       | Lossless (when available)      |
| 2        | YouTube    | Best audio | Lossless-preferred format sort |
| 3        | SoundCloud | Best audio | Lossless-preferred format sort |

### YouTube format sort order

| Priority | Codec / Format      | Notes                                     |
| -------- | ------------------- | ----------------------------------------- |
| 1        | FLAC                | Lossless, most common high-quality source |
| 2        | ALAC                | Apple Lossless                            |
| 3        | WAV                 | Uncompressed PCM                          |
| 4        | Highest bitrate     | Best available lossy if no lossless found |
| 5        | Opus / Vorbis / AAC | Common lossy fallbacks                    |

All downloaded audio is converted to **WAV PCM signed 24-bit little-endian, 48 kHz stereo** regardless of source format.

## License

MIT
