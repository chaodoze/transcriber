"""YouTube URL resolution - fetch captions or download audio for transcription."""

import tempfile
from pathlib import Path
from typing import Optional

from .models import Segment, TranscriptResult, TranscriptSource
from .url_resolver import InputType, ResolvedInput, parse_youtube_url


def get_youtube_metadata(video_id: str) -> tuple[Optional[str], Optional[str]]:
    """Fetch video title and channel name via yt-dlp (no download).

    Returns (video_title, channel_name).
    """
    try:
        import yt_dlp

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={video_id}", download=False
            )
            if info:
                return info.get("title"), info.get("channel") or info.get("uploader")
    except Exception:
        pass
    return None, None


def get_youtube_captions(
    video_id: str, language: str = "en"
) -> Optional[TranscriptResult]:
    """Fetch YouTube captions using youtube-transcript-api.

    Returns a TranscriptResult if captions are available, None otherwise.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        ytt_api = YouTubeTranscriptApi()
        transcript = ytt_api.fetch(video_id, languages=[language, "en"])

        segments = []
        for snippet in transcript.snippets:
            segments.append(
                Segment(
                    speaker="Speaker",
                    text=snippet.text,
                    start=snippet.start,
                    end=snippet.start + snippet.duration,
                )
            )

        if not segments:
            return None

        duration = segments[-1].end if segments else 0.0
        lang = transcript.language_code or language

        return TranscriptResult(
            segments=segments,
            speakers=["Speaker"],
            duration=duration,
            language=lang,
            source=TranscriptSource.YOUTUBE_CAPTIONS,
        )
    except Exception:
        return None


def download_youtube_audio(video_id: str) -> Path:
    """Download YouTube audio to a temporary file using yt-dlp.

    Returns path to the downloaded audio file.
    """
    import yt_dlp

    fd, temp_path = tempfile.mkstemp(suffix=".mp3")
    # yt-dlp adds its own extension, so use the path without extension as template
    output_template = temp_path.rsplit(".", 1)[0]

    ydl_opts = {
        "format": "bestaudio/best",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "outtmpl": output_template + ".%(ext)s",
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])

        # yt-dlp creates the file with .mp3 extension via postprocessor
        result_path = Path(output_template + ".mp3")
        if result_path.exists():
            return result_path

        # Fallback: check if file was created at the original temp_path
        if Path(temp_path).exists():
            return Path(temp_path)

        raise RuntimeError("yt-dlp did not produce an output file")
    except Exception as e:
        Path(temp_path).unlink(missing_ok=True)
        Path(output_template + ".mp3").unlink(missing_ok=True)
        raise RuntimeError(f"Failed to download YouTube audio: {e}") from e


def resolve_youtube_url(url: str) -> ResolvedInput:
    """Resolve YouTube URL by:
    1. Parsing video ID from URL
    2. Fetching video metadata (title, channel)
    3. Trying to get captions via youtube-transcript-api
    4. If no captions, downloading audio via yt-dlp for STT fallback

    Returns ResolvedInput with caption-based transcript or audio path.
    """
    video_id = parse_youtube_url(url)
    if not video_id:
        return ResolvedInput(input_type=InputType.YOUTUBE_URL)

    # Fetch metadata
    video_title, channel_name = get_youtube_metadata(video_id)

    return ResolvedInput(
        input_type=InputType.YOUTUBE_URL,
        episode_id=video_id,
        episode_title=video_title,
        podcast_title=channel_name,
    )
