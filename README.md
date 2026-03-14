# spotify-wav-downloader

Download songs from a Spotify playlist as high-quality lossless **.wav** files (PCM 24-bit / 48 kHz).

## How it works

1. Reads track metadata from the Spotify Web API (title, artist, duration, ISRC).
2. **Deezer (preferred):** Matches tracks by ISRC or search and downloads true **lossless FLAC** streams.
3. **YouTube (fallback):** If Deezer is unavailable or the track isn't found, searches YouTube via **yt-dlp**, prioritising lossless codecs (FLAC → ALAC → WAV) and highest bitrate.
4. Converts the downloaded audio to **WAV** (signed 24-bit PCM, 48 kHz stereo) using **ffmpeg**.

## Prerequisites

- **Python 3.10+**
- **ffmpeg** — `brew install ffmpeg` (macOS) or `apt install ffmpeg` (Linux)
- **yt-dlp** — installed automatically with pip, or `brew install yt-dlp`
- A **Spotify Developer** account with a Client ID and Secret → [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
- *(Optional)* A **Deezer** account — for lossless FLAC downloads (see [Deezer setup](#deezer-setup))

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
# Optionally add DEEZER_ARL for lossless FLAC (see below)
```

### Deezer setup

To enable lossless FLAC downloads from Deezer:

1. Log into [deezer.com](https://www.deezer.com) in your browser.
2. Open DevTools (`F12`) → **Application** → **Cookies** → `https://www.deezer.com`.
3. Copy the value of the `arl` cookie.
4. Add it to your `.env` file:
   ```
   DEEZER_ARL=your_arl_token_here
   ```

If `DEEZER_ARL` is not set, the tool will automatically use YouTube as the only source.

## Usage

```bash
# Using the installed CLI
spotify-wav-dl "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"

# Or run as a module
python -m spotify_wav_dl.cli "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"

# Custom output directory
spotify-wav-dl "https://open.spotify.com/playlist/..." -o ~/Music/playlists

# Keep intermediate (non-WAV) files
spotify-wav-dl "https://open.spotify.com/playlist/..." --keep-original

# Force a specific source
spotify-wav-dl "https://open.spotify.com/playlist/..." --source deezer
spotify-wav-dl "https://open.spotify.com/playlist/..." --source youtube
```

## Output

Files are saved to `./downloads/<Playlist Name>/` by default:

```
downloads/
  Today's Top Hits/
    Artist - Song Title.wav
    Artist - Another Song.wav
    ...
```

## Audio quality

The tool tries sources in order of quality:

### Source priority

| Priority | Source  | Format       | Quality                         |
|----------|---------|--------------|---------------------------------|
| 1        | Deezer  | FLAC         | Lossless 16-bit / 44.1 kHz     |
| 2        | Deezer  | MP3 320 kbps | High-quality lossy fallback     |
| 3        | YouTube | Best audio   | Lossless-preferred format sort  |

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
