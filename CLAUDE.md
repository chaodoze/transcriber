# Podcast Transcriber & Ebook Reader MCP Server

## Project Overview
MCP server for podcast transcription with speaker diarization and EPUB ebook reading, optimized for Apple Silicon.

## Tech Stack
- **Transcription**: mlx-whisper (distil-whisper-large-v3) - native Apple Silicon
- **Diarization**: pyannote-audio (speaker-diarization-3.1)
- **MCP Framework**: FastMCP
- **Audio Loading**: torchaudio (workaround for torchcodec issues)
- **YouTube**: youtube-transcript-api (captions), yt-dlp (audio download + metadata)
- **EPUB**: ebooklib (parsing), beautifulsoup4 + lxml (HTML-to-text)

## Key Learnings

### pyannote-audio API
- Use `token=` parameter, not `use_auth_token=` (deprecated)
- When passing waveform dict to pipeline, output may be `DiarizeOutput` instead of `Annotation`
- Handle both: check for `itertracks()` method or `speaker_diarization` attribute
- Requires HuggingFace token and model license acceptance

### Audio Loading
- torchcodec has FFmpeg compatibility issues on macOS
- Workaround: pre-load audio with `torchaudio.load()` and pass as dict:
  ```python
  waveform, sample_rate = torchaudio.load(audio_path)
  audio_input = {"waveform": waveform, "sample_rate": sample_rate}
  pipeline(audio_input)
  ```

### Speaker Name Detection
- Pattern matching prone to false positives ("all", "going" from "I'm going...")
- Use strict patterns with minimum length (3+ chars)
- Filter against common word list
- Best patterns: "my name is [Name]", "this is [Name]"

## Environment Variables
- `HF_TOKEN`: HuggingFace token for pyannote models (required)
- `WHISPER_MODEL`: Override default model (optional)

## Running the Server
```bash
source .venv/bin/activate
export HF_TOKEN="your_token_here"
python -m src.transcriber.server
```

## Performance (64-min podcast, M-series Mac)
- Transcription: ~8.5 minutes
- Diarization: ~10 minutes
- Total: ~20 minutes for full pipeline

## Apple Podcasts Transcript Extraction

### Data Locations (macOS)
- **SQLite Database**: `~/Library/Group Containers/243LU875E5.groups.com.apple.podcasts/Documents/MTLibrary.sqlite`
- **TTML Cache**: `~/Library/Group Containers/243LU875E5.groups.com.apple.podcasts/Library/Cache/Assets/TTML/`

### Database Schema (ZMTEPISODE table)
- `ZSTORETRACKID` - iTunes episode ID (matches Apple URL `?i=` parameter)
- `ZTITLE` - Episode title
- `ZTRANSCRIPTIDENTIFIER` - Relative path to TTML file (if transcript available)
- `ZENCLOSUREURL` - Direct audio URL (for fallback transcription)
- `ZPODCAST` - Foreign key to ZMTPODCAST table

### TTML Format
- Namespaces: `http://www.w3.org/ns/ttml`, `http://www.w3.org/ns/ttml#metadata`
- Speakers in `ttm:agent` attribute (e.g., "SPEAKER_1")
- Timestamps in `begin`/`end` attributes (formats: "0.860", "1:48.737", "1:02:03.456")
- Word-level spans with `podcasts:unit="word"` attribute

### Important Notes
- `ZTRANSCRIPTIDENTIFIER` exists even when file not cached (it's a remote path)
- Open database in read-only mode (`?mode=ro`) to avoid locking issues
- Overcast URLs can be resolved by searching Apple Podcasts by episode title

### URL Patterns
- Apple Podcasts: `podcasts.apple.com/{country}/podcast/{show-slug}/id{podcast_id}?i={episode_id}`
- Overcast: `overcast.fm/+{episode_id}`
- YouTube: `youtube.com/watch?v={video_id}`, `youtu.be/{video_id}`, `youtube.com/embed/{video_id}`

### Transcript Fetcher (tools/FetchTranscript)
Native macOS tool that fetches transcripts directly from Apple's API:
- Requires macOS 15.5+ (uses private AppleMediaServices framework)
- Build with: `./tools/build.sh`
- Authenticates via Apple's token service and signed requests
- Bearer token cached for 30 days in `tools/bearer_token.txt`
- Downloads TTML to Apple's cache directory structure

**API Endpoint:**
```
https://amp-api.podcasts.apple.com/v1/catalog/us/podcast-episodes/{episodeId}/transcripts
```

**Usage:** The Python wrapper (`transcript_fetcher.py`) automatically calls this tool when
a transcript is not cached locally. Falls back to speech-to-text if fetching fails.

### iTunes Search API (itunes_api.py)
Enables transcript fetching for ANY podcast episode without local subscription:
- Search endpoint: `https://itunes.apple.com/search?term={query}&entity=podcastEpisode`
- Lookup endpoint: `https://itunes.apple.com/lookup?id={trackId}&entity=podcastEpisode`
- Returns `trackId` (Apple episode ID) needed for transcript fetching
- Used as fallback when episode not in local Apple Podcasts database
- Overcast URL workflow: parse title from page → search iTunes → fetch transcript

## YouTube Transcript Support

### Architecture (youtube.py)
- Fast path: fetch captions via `youtube-transcript-api` (instant, no diarization)
- Fallback: download audio via `yt-dlp` → existing STT pipeline (slow, with diarization)
- Use `force_transcribe=True` to skip captions and get speaker-labeled STT

### youtube-transcript-api (v1.x)
- Instance-based API: `YouTubeTranscriptApi()` then `.fetch(video_id, languages=[...])`
- Returns `FetchedTranscript` with `.snippets` list
- Each snippet has `.text`, `.start` (seconds), `.duration` (seconds)
- Captions don't include speaker labels — uses "Speaker" as default
- Handles both manual and auto-generated captions transparently

### yt-dlp
- `extract_info(url, download=False)` for metadata (title, channel) without downloading
- Audio download: `format='bestaudio/best'` + `FFmpegExtractAudio` postprocessor for mp3
- Video ID is always 11 chars: `[a-zA-Z0-9_-]{11}`

## EPUB Ebook Support

### Architecture (ebook.py)
- Two tools: `ebook_toc` (get structure) and `ebook_chapter` (read one chapter)
- Designed for LLM conversations about books — fetch only the chapter being discussed
- Chapter lookup supports hierarchical numbers ("3.1"), flat indices ("0"), or title substrings

### ebooklib API
- `epub.read_epub(path)` returns `EpubBook`
- `book.toc` returns mixed types: `epub.Link` (leaf) and `tuple[Section, children]` (nested)
- `book.get_metadata("DC", "title")` returns list of `(value, attrs)` tuples
- `book.get_item_with_href(href)` to get chapter content by filename
- `item.get_content()` returns raw HTML bytes
- `epub.Section` has `.title` attribute; `epub.Link` has `.title`, `.href`, `.uid`

### HTML-to-Text Conversion
- Uses BeautifulSoup with `lxml` parser for speed
- Remove `<script>` and `<style>` tags before extracting text
- Insert paragraph breaks at block-level elements (p, div, h1-h6, blockquote, li, etc.)
- Fallback TOC: when `book.toc` is empty, build from spine using `<h1>`-`<h3>` headings
