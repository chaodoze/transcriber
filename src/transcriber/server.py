"""MCP server for podcast transcription."""

import base64
import os
import shutil
import sys
import tempfile
import time
from collections import deque
from pathlib import Path
from urllib.request import Request, urlopen

# Ensure ffmpeg is findable when launched from minimal environments (e.g. LaunchAgents)
if not shutil.which("ffmpeg"):
    for p in ("/opt/homebrew/bin", "/usr/local/bin"):
        if Path(p, "ffmpeg").exists():
            os.environ["PATH"] = p + ":" + os.environ.get("PATH", "")
            break

from fastmcp import FastMCP
from pydantic import Field

from .diarize import (
    assign_speakers_to_words,
    diarize_audio,
    merge_speaker_segments,
)
from .models import (
    EbookChapterResult,
    EbookTocResult,
    QuickTranscriptResult,
    Segment,
    TranscriptResult,
    TranscriptSource,
    TweetResult,
    TweetSearchResult,
)
from .postprocess import process_transcript
from .transcribe import get_word_segments, transcribe_audio
from .ttml_parser import parse_ttml_file
from .url_resolver import InputType, resolve_input

# Initialize MCP server
mcp = FastMCP(
    name="Reader",
    instructions="""
    Transcribe podcasts and audio files with speaker diarization.
    Read EPUB ebooks chapter by chapter.
    Fetch and search tweets from Twitter/X.

    Tools:
    - transcribe: Transcribe audio from URL (Apple Podcasts, Overcast, YouTube),
      file path, or base64 data. Modes: "auto" (use cached transcripts),
      "full" (force STT with diarization), "quick" (fast, no diarization).
      Can export directly to txt/srt/vtt via output_format parameter.
    - ebook: Read EPUB ebooks. Pass file_path alone to get table of contents,
      or with chapter parameter to read a specific chapter.
    - tweet: Interact with Twitter/X. Actions: "get" (single tweet by URL/ID),
      "search" (search recent tweets), "user" (user timeline).
    """,
)


def _convert_to_wav(audio_path: Path) -> Path | None:
    """Convert audio to WAV if not already WAV (torchaudio can't read m4a/mp3 reliably).

    Returns path to temp WAV file, or None if already WAV.
    """
    if audio_path.suffix.lower() == ".wav":
        return None

    import subprocess

    fd, temp_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        subprocess.run(
            ["ffmpeg", "-i", str(audio_path), "-ar", "16000", "-ac", "1", temp_path, "-y"],
            check=True,
            capture_output=True,
        )
        return Path(temp_path)
    except Exception as e:
        Path(temp_path).unlink(missing_ok=True)
        raise RuntimeError(f"Failed to convert audio to WAV: {e}") from e


def _download_audio(url: str) -> Path:
    """Download audio from URL to temporary file."""
    # Determine file extension from URL
    ext = ".mp3"
    if ".m4a" in url:
        ext = ".m4a"
    elif ".wav" in url:
        ext = ".wav"

    # Create temp file
    fd, temp_path = tempfile.mkstemp(suffix=ext)
    os.close(fd)
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=300) as resp, open(temp_path, "wb") as f:
            shutil.copyfileobj(resp, f)
        return Path(temp_path)
    except Exception as e:
        Path(temp_path).unlink(missing_ok=True)
        raise RuntimeError(f"Failed to download audio: {e}") from e


def _transcribe_audio_file(
    audio_path: Path,
    language: str,
    remove_fillers: bool,
    identify_speakers: bool,
) -> TranscriptResult:
    """Internal function to transcribe an audio file with diarization."""
    # Step 1: Transcribe with word timestamps
    transcription = transcribe_audio(
        audio_path,
        language=language if language != "auto" else None,
        word_timestamps=True,
    )

    # Step 2: Get word-level segments
    word_segments = get_word_segments(transcription)

    # Step 3: Diarize to identify speakers
    diarization_segments = diarize_audio(audio_path)

    # Step 4: Assign speakers to words
    words_with_speakers = assign_speakers_to_words(word_segments, diarization_segments)

    # Step 5: Merge into speaker segments
    segments = merge_speaker_segments(words_with_speakers)

    # Step 6: Post-process (filler removal, speaker naming)
    segments, speaker_names = process_transcript(
        segments,
        remove_fillers=remove_fillers,
        identify_speakers=identify_speakers,
    )

    # Get unique speakers
    speakers = list(dict.fromkeys(seg["speaker"] for seg in segments))

    # Calculate duration from last segment
    duration = segments[-1]["end"] if segments else 0.0

    return TranscriptResult(
        segments=[Segment(**seg) for seg in segments],
        speakers=speakers,
        duration=duration,
        language=transcription["language"],
        source=TranscriptSource.SPEECH_TO_TEXT,
    )


def _filter_segments_by_time(
    result: TranscriptResult, start_min: float, end_min: float
) -> TranscriptResult:
    """Filter transcript segments to a time range (in minutes)."""
    start_sec = start_min * 60
    end_sec = end_min * 60
    filtered = [s for s in result.segments if s.end > start_sec and s.start < end_sec]
    speakers = list(dict.fromkeys(s.speaker for s in filtered))
    duration = filtered[-1].end - filtered[0].start if filtered else 0.0
    return TranscriptResult(
        segments=filtered,
        speakers=speakers,
        duration=duration,
        language=result.language,
        source=result.source,
        episode_title=result.episode_title,
        podcast_title=result.podcast_title,
    )


def _decode_base64_to_temp(audio_data: str, filename: str) -> tuple[Path, Path]:
    """Decode base64 audio data to a temporary file. Returns (path, path_to_cleanup)."""
    try:
        audio_bytes = base64.b64decode(audio_data)
    except Exception as e:
        raise ValueError(f"Invalid base64 audio data: {e}") from e

    ext = Path(filename).suffix or ".m4a"
    fd, temp_path = tempfile.mkstemp(suffix=ext)
    with os.fdopen(fd, "wb") as f:
        f.write(audio_bytes)
    return Path(temp_path), Path(temp_path)


def _maybe_export(result: TranscriptResult, output_format: str) -> TranscriptResult | str:
    """If output_format is not 'json', export the transcript to the requested format."""
    if output_format == "json":
        return result
    segments = [seg.model_dump() for seg in result.segments]
    if output_format == "txt":
        return _export_txt(segments)
    elif output_format == "srt":
        return _export_srt(segments)
    elif output_format == "vtt":
        return _export_vtt(segments)
    raise ValueError(
        f"Unknown output_format: {output_format!r}. Use 'json', 'txt', 'srt', or 'vtt'."
    )


@mcp.tool
def transcribe(
    input: str = Field(
        description=(
            "Audio source: Apple Podcasts URL, Overcast URL, YouTube URL, "
            "local file path, or base64-encoded audio data"
        )
    ),
    input_filename: str = Field(
        default="",
        description=(
            "Original filename when input is base64 data (e.g., 'recording.m4a'). "
            "When set, signals that input contains base64-encoded audio."
        ),
    ),
    mode: str = Field(
        default="auto",
        description=(
            "Transcription mode: 'auto' (use cached transcripts when available), "
            "'full' (force speech-to-text with speaker diarization), "
            "'quick' (fast transcription without diarization)"
        ),
    ),
    language: str = Field(
        default="en", description="Language code (e.g., 'en', 'es', 'fr', 'auto')"
    ),
    remove_fillers: bool = Field(default=True, description="Remove filler words (um, uh, etc.)"),
    identify_speakers: bool = Field(
        default=True, description="Identify speaker names from context (ignored in quick mode)"
    ),
    start_minutes: float = Field(
        default=0, description="Start time in minutes (default: 0, beginning)"
    ),
    end_minutes: float = Field(
        default=0, description="End time in minutes (default: 0, meaning entire transcript)"
    ),
    output_format: str = Field(
        default="json",
        description="Output format: 'json' (structured result), 'txt', 'srt', or 'vtt'",
    ),
) -> TranscriptResult | QuickTranscriptResult | str:
    """
    Transcribe audio from a URL, file path, or base64-encoded data.

    Modes:
    - "auto": Uses cached transcripts/captions when available (fastest), falls back to STT
    - "full": Forces speech-to-text with full speaker diarization
    - "quick": Fast transcription without speaker diarization
    """
    if mode not in ("auto", "full", "quick"):
        raise ValueError(f"Unknown mode: {mode!r}. Use 'auto', 'full', or 'quick'.")

    if output_format not in ("json", "txt", "srt", "vtt"):
        raise ValueError(
            f"Unknown output_format: {output_format!r}. Use 'json', 'txt', 'srt', or 'vtt'."
        )

    # --- Quick mode (no diarization) ---
    if mode == "quick":
        if input_filename:
            audio_path, cleanup = _decode_base64_to_temp(input, input_filename)
        else:
            audio_path = Path(input).expanduser().resolve()
            cleanup = None

        try:
            if not audio_path.exists():
                raise FileNotFoundError(f"Audio file not found: {audio_path}")

            transcription = transcribe_audio(
                audio_path,
                language=language if language != "auto" else None,
                word_timestamps=False,
            )

            text = transcription["text"]
            if remove_fillers:
                from .postprocess import remove_fillers_from_text

                text = remove_fillers_from_text(text)

            segments = transcription.get("segments", [])
            duration = segments[-1]["end"] if segments else 0.0

            result = QuickTranscriptResult(
                text=text,
                segments=segments,
                duration=duration,
                language=transcription["language"],
            )

            if output_format != "json":
                return text

            return result
        finally:
            if cleanup:
                cleanup.unlink(missing_ok=True)

    # --- Base64 input ---
    if input_filename:
        audio_path, cleanup = _decode_base64_to_temp(input, input_filename)
        try:
            result = _transcribe_audio_file(
                audio_path,
                language=language,
                remove_fillers=remove_fillers,
                identify_speakers=identify_speakers,
            )
            return _maybe_export(result, output_format)
        finally:
            cleanup.unlink(missing_ok=True)

    # --- URL or file path (auto/full mode) ---
    force_transcribe = mode == "full"

    # For file paths without URL scheme, go directly to STT
    if not input.startswith(("http://", "https://")):
        path = Path(input).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {path}")
        result = _transcribe_audio_file(
            path,
            language=language,
            remove_fillers=remove_fillers,
            identify_speakers=identify_speakers,
        )
        return _maybe_export(result, output_format)

    resolved = resolve_input(input)

    def _maybe_filter(result: TranscriptResult) -> TranscriptResult:
        if end_minutes > 0:
            return _filter_segments_by_time(result, start_minutes, end_minutes)
        if start_minutes > 0:
            return _filter_segments_by_time(result, start_minutes, float("inf"))
        return result

    # If we have a cached TTML transcript and not forcing transcription
    if resolved.transcript_path and not force_transcribe:
        result = parse_ttml_file(resolved.transcript_path, language=language)
        result.episode_title = resolved.episode_title
        result.podcast_title = resolved.podcast_title
        return _maybe_export(_maybe_filter(result), output_format)

    # For YouTube URLs, try captions first (fast path)
    if resolved.input_type == InputType.YOUTUBE_URL and not force_transcribe:
        from .youtube import get_youtube_captions

        caption_result = get_youtube_captions(resolved.episode_id, language)
        if caption_result:
            caption_result.episode_title = resolved.episode_title
            caption_result.podcast_title = resolved.podcast_title
            return _maybe_export(_maybe_filter(caption_result), output_format)

    # Otherwise, we need to transcribe audio
    audio_path = resolved.audio_path
    temp_audio = None

    if not audio_path:
        if resolved.input_type == InputType.YOUTUBE_URL:
            from .youtube import download_youtube_audio

            audio_path = download_youtube_audio(resolved.episode_id)
            temp_audio = audio_path
        elif not resolved.audio_url:
            raise ValueError(
                f"Could not find audio source for: {input}. "
                "Episode may not be downloaded in Apple Podcasts."
            )
        else:
            audio_path = _download_audio(resolved.audio_url)
            temp_audio = audio_path

    try:
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        result = _transcribe_audio_file(
            audio_path,
            language=language,
            remove_fillers=remove_fillers,
            identify_speakers=identify_speakers,
        )
        result.episode_title = resolved.episode_title
        result.podcast_title = resolved.podcast_title

        return _maybe_export(_maybe_filter(result), output_format)
    finally:
        if temp_audio:
            temp_audio.unlink(missing_ok=True)


def _format_timestamp_srt(seconds: float) -> str:
    """Format seconds as SRT timestamp (HH:MM:SS,mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _format_timestamp_vtt(seconds: float) -> str:
    """Format seconds as VTT timestamp (HH:MM:SS.mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def _export_txt(segments: list) -> str:
    """Export as plain text with speaker labels."""
    lines = []
    for seg in segments:
        speaker = seg.get("speaker", "Unknown")
        text = seg.get("text", "")
        lines.append(f"{speaker}: {text}")
    return "\n\n".join(lines)


def _export_srt(segments: list) -> str:
    """Export as SRT subtitle format."""
    lines = []
    for i, seg in enumerate(segments, 1):
        start = _format_timestamp_srt(seg.get("start", 0))
        end = _format_timestamp_srt(seg.get("end", 0))
        speaker = seg.get("speaker", "Unknown")
        text = seg.get("text", "")
        lines.append(f"{i}\n{start} --> {end}\n[{speaker}] {text}")
    return "\n\n".join(lines)


def _export_vtt(segments: list) -> str:
    """Export as WebVTT subtitle format."""
    lines = ["WEBVTT", ""]
    for i, seg in enumerate(segments, 1):
        start = _format_timestamp_vtt(seg.get("start", 0))
        end = _format_timestamp_vtt(seg.get("end", 0))
        speaker = seg.get("speaker", "Unknown")
        text = seg.get("text", "")
        lines.append(f"{i}\n{start} --> {end}\n<v {speaker}>{text}")
    return "\n\n".join(lines)


@mcp.tool
def ebook(
    file_path: str = Field(description="Path to an EPUB file"),
    chapter: str = Field(
        default="",
        description=(
            "Chapter to read: hierarchical number ('3.1'), index ('0'), "
            "or title substring ('Introduction'). Leave empty to get table of contents."
        ),
    ),
) -> EbookTocResult | EbookChapterResult:
    """
    Read an EPUB ebook.

    Without chapter: returns the table of contents (use first to see structure).
    With chapter: returns the content of a specific chapter.
    """
    if chapter:
        from .ebook import get_chapter

        return get_chapter(file_path, chapter)
    else:
        from .ebook import get_toc

        return get_toc(file_path)


@mcp.tool
def tweet(
    action: str = Field(
        description="Action: 'get' (single tweet), 'search' (search recent), 'user' (user timeline)"
    ),
    query: str = Field(
        description=(
            "Tweet URL/ID for 'get', search query for 'search', "
            "username (without @) for 'user'"
        )
    ),
    max_results: int = Field(
        default=10,
        description="Results count for 'search' (10-100) and 'user' (5-100). Ignored for 'get'.",
    ),
) -> TweetResult | TweetSearchResult:
    """
    Fetch tweets from Twitter/X.

    Actions:
    - "get": Fetch a single tweet by URL or numeric ID
    - "search": Search recent tweets (last 7 days)
    - "user": Get recent tweets from a user's timeline
    """
    if action == "get":
        from .twitter import get_tweet as _get_tweet

        return _get_tweet(query)
    elif action == "search":
        from .twitter import search_tweets as _search_tweets

        return _search_tweets(query, max_results)
    elif action == "user":
        from .twitter import get_user_tweets as _get_user_tweets

        return _get_user_tweets(query, max_results)
    else:
        raise ValueError(f"Unknown action: {action!r}. Use 'get', 'search', or 'user'.")


def main():
    """Run the MCP server.

    Usage:
        python -m src.transcriber.server              # stdio (default, for local MCP)
        python -m src.transcriber.server --http        # Streamable HTTP on port 8000
        python -m src.transcriber.server --http 9000   # Custom port

    Set MCP_API_KEY to require bearer token auth (optional, for non-private networks).
    """
    args = sys.argv[1:]

    if "--http" in args:
        idx = args.index("--http")
        port = int(args[idx + 1]) if idx + 1 < len(args) and args[idx + 1].isdigit() else 51205
        host = os.environ.get("MCP_HOST", "0.0.0.0")

        from starlette.middleware import Middleware
        from starlette.responses import JSONResponse

        request_times: deque[float] = deque()
        max_requests_per_hour = 1000

        class RateLimitMiddleware:
            def __init__(self, app):
                self.app = app

            async def __call__(self, scope, receive, send):
                if scope["type"] == "http":
                    now = time.time()
                    cutoff = now - 3600
                    while request_times and request_times[0] < cutoff:
                        request_times.popleft()
                    if len(request_times) >= max_requests_per_hour:
                        resp = JSONResponse(
                            {"error": "Server overloaded. Try again later."}, status_code=429
                        )
                        await resp(scope, receive, send)
                        return
                    request_times.append(now)
                await self.app(scope, receive, send)

        middleware = [Middleware(RateLimitMiddleware)]

        print(
            f"Starting Streamable HTTP server on {host}:{port}/mcp"
            f" (rate limit: {max_requests_per_hour}/hr)"
        )
        mcp.run(transport="streamable-http", host=host, port=port, middleware=middleware)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
