"""Instagram URL resolution - download audio from reels/posts for transcription."""

import re
import tempfile
from pathlib import Path
from typing import Optional

from .url_resolver import InputType, ResolvedInput

INSTAGRAM_PATTERN = re.compile(
    r"instagram\.com/(?:reel|reels|p)/(?P<shortcode>[a-zA-Z0-9_-]+)"
)


def parse_instagram_url(url: str) -> Optional[str]:
    """Extract shortcode from an Instagram reel/post URL."""
    match = INSTAGRAM_PATTERN.search(url)
    if not match:
        return None
    return match.group("shortcode")


def get_instagram_metadata(shortcode: str) -> tuple[Optional[str], Optional[str]]:
    """Fetch video title and uploader via yt-dlp (no download).

    Returns (title, uploader).
    """
    try:
        import yt_dlp

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "cookiesfrombrowser": ("chrome",),
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(
                f"https://www.instagram.com/reel/{shortcode}/", download=False
            )
            if info:
                title = info.get("title") or info.get("description", "")[:80]
                uploader = info.get("uploader") or info.get("uploader_id")
                return title, uploader
    except Exception:
        pass
    return None, None


def download_instagram_audio(shortcode: str) -> Path:
    """Download Instagram audio to a temporary file using yt-dlp.

    Requires Chrome cookies for authentication.
    Returns path to the downloaded audio file.
    """
    import yt_dlp

    fd, temp_path = tempfile.mkstemp(suffix=".mp3")
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
        "cookiesfrombrowser": ("chrome",),
    }

    url = f"https://www.instagram.com/reel/{shortcode}/"
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        result_path = Path(output_template + ".mp3")
        if result_path.exists():
            return result_path

        if Path(temp_path).exists():
            return Path(temp_path)

        raise RuntimeError("yt-dlp did not produce an output file")
    except Exception as e:
        Path(temp_path).unlink(missing_ok=True)
        Path(output_template + ".mp3").unlink(missing_ok=True)
        raise RuntimeError(
            f"Failed to download Instagram audio: {e}. "
            "Ensure you're logged into Instagram in Chrome."
        ) from e


def resolve_instagram_url(url: str) -> ResolvedInput:
    """Resolve Instagram URL to a ResolvedInput with metadata."""
    shortcode = parse_instagram_url(url)
    if not shortcode:
        return ResolvedInput(input_type=InputType.INSTAGRAM_URL)

    title, uploader = get_instagram_metadata(shortcode)

    return ResolvedInput(
        input_type=InputType.INSTAGRAM_URL,
        episode_id=shortcode,
        episode_title=title,
        podcast_title=uploader,
    )
