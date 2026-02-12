"""MCP server for podcast transcription."""

import os
import sys
import tempfile
import time
from collections import deque
from pathlib import Path
from urllib.request import urlretrieve

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
)
from .postprocess import process_transcript
from .transcribe import get_word_segments, transcribe_audio
from .ttml_parser import parse_ttml_file
from .url_resolver import InputType, resolve_input

# Initialize MCP server
mcp = FastMCP(
    name="Podcast Transcriber",
    instructions="""
    Transcribe podcasts and audio files with speaker diarization.
    Read EPUB ebooks chapter by chapter.

    Tools:
    - transcribe_url: Transcribe from Apple Podcasts URL, Overcast URL, YouTube URL, or file path
      (uses cached transcripts when available, falls back to speech-to-text)
    - transcribe_podcast: Full transcription with speaker diarization from audio file
    - transcribe_quick: Fast transcription without diarization
    - export_transcript: Export to SRT, VTT, or text format
    - ebook_toc: Get table of contents from an EPUB file (use first to see chapters)
    - ebook_chapter: Read a specific chapter by number, index, or title
    """,
)


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
    try:
        urlretrieve(url, temp_path)
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


@mcp.tool
def transcribe_url(
    url_or_path: str = Field(
        description="Apple Podcasts URL, Overcast URL, YouTube URL, or local file path"
    ),
    language: str = Field(default="en", description="Language code (e.g., 'en', 'es', 'fr')"),
    remove_fillers: bool = Field(default=True, description="Remove filler words (um, uh, etc.)"),
    identify_speakers: bool = Field(
        default=True, description="Attempt to identify speaker names from context"
    ),
    force_transcribe: bool = Field(
        default=False, description="Force speech-to-text even if cached transcript available"
    ),
) -> TranscriptResult:
    """
    Transcribe a podcast from URL or file path.

    Supports:
    - Apple Podcasts URLs: Uses cached transcript if available, falls back to STT
    - Overcast URLs: Looks up in Apple Podcasts cache, falls back to STT
    - YouTube URLs: Uses YouTube captions if available, falls back to STT
    - Local file paths: Direct transcription

    The tool automatically uses cached transcripts/captions when available,
    which is much faster than speech-to-text transcription.

    Returns structured transcript with speaker diarization.
    """
    # Resolve input to get transcript path or audio source
    resolved = resolve_input(url_or_path)

    # If we have a cached TTML transcript and not forcing transcription
    if resolved.transcript_path and not force_transcribe:
        result = parse_ttml_file(resolved.transcript_path, language=language)
        # Add metadata
        result.episode_title = resolved.episode_title
        result.podcast_title = resolved.podcast_title
        return result

    # For YouTube URLs, try captions first (fast path)
    if resolved.input_type == InputType.YOUTUBE_URL and not force_transcribe:
        from .youtube import get_youtube_captions

        caption_result = get_youtube_captions(resolved.episode_id, language)
        if caption_result:
            caption_result.episode_title = resolved.episode_title
            caption_result.podcast_title = resolved.podcast_title
            return caption_result

    # Otherwise, we need to transcribe audio
    audio_path = resolved.audio_path
    temp_audio = None

    if not audio_path:
        # For YouTube, download audio via yt-dlp
        if resolved.input_type == InputType.YOUTUBE_URL:
            from .youtube import download_youtube_audio

            audio_path = download_youtube_audio(resolved.episode_id)
            temp_audio = audio_path
        elif not resolved.audio_url:
            raise ValueError(
                f"Could not find audio source for: {url_or_path}. "
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

        # Add metadata
        result.episode_title = resolved.episode_title
        result.podcast_title = resolved.podcast_title

        return result
    finally:
        # Clean up temp file if we downloaded it
        if temp_audio:
            temp_audio.unlink(missing_ok=True)


@mcp.tool
def transcribe_podcast(
    audio_path: str = Field(description="Path to audio file (mp3, wav, m4a, etc.)"),
    language: str = Field(default="en", description="Language code (e.g., 'en', 'es', 'fr')"),
    remove_fillers: bool = Field(default=True, description="Remove filler words (um, uh, etc.)"),
    identify_speakers: bool = Field(
        default=True, description="Attempt to identify speaker names from context"
    ),
) -> TranscriptResult:
    """
    Transcribe a podcast with full speaker diarization.

    This performs:
    1. Speech-to-text transcription with word timestamps
    2. Speaker diarization to identify who said what
    3. Optional filler word removal
    4. Optional speaker name identification

    Returns structured transcript with segments labeled by speaker.
    """
    path = Path(audio_path).expanduser().resolve()

    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")

    return _transcribe_audio_file(
        path,
        language=language,
        remove_fillers=remove_fillers,
        identify_speakers=identify_speakers,
    )


@mcp.tool
def transcribe_quick(
    audio_path: str = Field(description="Path to audio file"),
    language: str = Field(default="en", description="Language code"),
    remove_fillers: bool = Field(default=True, description="Remove filler words"),
) -> QuickTranscriptResult:
    """
    Fast transcription without speaker diarization.

    Use this when you don't need to know who said what, just the text.
    Much faster than full transcription.
    """
    audio_path = Path(audio_path).expanduser().resolve()

    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    # Transcribe without word timestamps for speed
    transcription = transcribe_audio(
        audio_path,
        language=language if language != "auto" else None,
        word_timestamps=False,
    )

    text = transcription["text"]

    # Optionally remove fillers
    if remove_fillers:
        from .postprocess import remove_fillers_from_text

        text = remove_fillers_from_text(text)

    # Calculate duration from segments
    segments = transcription.get("segments", [])
    duration = segments[-1]["end"] if segments else 0.0

    return QuickTranscriptResult(
        text=text,
        segments=segments,
        duration=duration,
        language=transcription["language"],
    )


@mcp.tool
def export_transcript(
    transcript: dict = Field(description="Transcript result from transcribe_podcast"),
    format: str = Field(default="txt", description="Output format: 'txt', 'srt', or 'vtt'"),
) -> str:
    """
    Export transcript to different formats.

    Formats:
    - txt: Plain text with speaker labels
    - srt: SubRip subtitle format
    - vtt: WebVTT subtitle format
    """
    segments = transcript.get("segments", [])

    if format == "txt":
        return _export_txt(segments)
    elif format == "srt":
        return _export_srt(segments)
    elif format == "vtt":
        return _export_vtt(segments)
    else:
        raise ValueError(f"Unknown format: {format}. Use 'txt', 'srt', or 'vtt'")


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
def ebook_toc(
    file_path: str = Field(description="Path to an EPUB file"),
) -> EbookTocResult:
    """
    Get the table of contents of an EPUB ebook.

    Use this first to see the book's structure, then use ebook_chapter
    to read a specific chapter by its number, index, or title.
    """
    from .ebook import get_toc

    return get_toc(file_path)


@mcp.tool
def ebook_chapter(
    file_path: str = Field(description="Path to an EPUB file"),
    chapter: str = Field(
        description=(
            "Chapter to read. Can be a hierarchical number (e.g., '3.1'), "
            "an index (e.g., '0'), or a title substring (e.g., 'Introduction')"
        )
    ),
) -> EbookChapterResult:
    """
    Read a specific chapter from an EPUB ebook.

    Use ebook_toc first to see available chapters and their numbers/indices.
    """
    from .ebook import get_chapter

    return get_chapter(file_path, chapter)


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
