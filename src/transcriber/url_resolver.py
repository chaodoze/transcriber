"""URL resolution for podcast URLs and file paths."""

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class InputType(Enum):
    """Type of input provided by user."""

    APPLE_PODCASTS_URL = "apple_podcasts"
    OVERCAST_URL = "overcast"
    FILE_PATH = "file_path"


@dataclass
class ResolvedInput:
    """Result of URL resolution."""

    input_type: InputType
    audio_path: Optional[Path] = None
    audio_url: Optional[str] = None
    transcript_path: Optional[Path] = None
    episode_id: Optional[str] = None
    episode_title: Optional[str] = None
    podcast_title: Optional[str] = None


# URL patterns
APPLE_PODCASTS_PATTERN = re.compile(
    r"podcasts\.apple\.com/(?P<country>[a-z]{2})/podcast/"
    r"(?P<show_slug>[^/]+)/id(?P<podcast_id>\d+)"
    r"(?:\?i=(?P<episode_id>\d+))?"
)

OVERCAST_PATTERN = re.compile(r"overcast\.fm/\+(?P<episode_id>[a-zA-Z0-9_-]+)")


def detect_input_type(url_or_path: str) -> InputType:
    """Detect whether input is Apple Podcasts URL, Overcast URL, or file path."""
    url_or_path = url_or_path.strip()

    if APPLE_PODCASTS_PATTERN.search(url_or_path):
        return InputType.APPLE_PODCASTS_URL

    if OVERCAST_PATTERN.search(url_or_path):
        return InputType.OVERCAST_URL

    return InputType.FILE_PATH


def parse_apple_url(url: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Parse Apple Podcasts URL.

    Returns (podcast_id, episode_id, show_slug).
    Episode ID may be None if URL is for a show, not an episode.
    """
    match = APPLE_PODCASTS_PATTERN.search(url)
    if not match:
        return None, None, None

    return (
        match.group("podcast_id"),
        match.group("episode_id"),
        match.group("show_slug"),
    )


def parse_overcast_url(url: str) -> Optional[str]:
    """Parse Overcast URL and return episode ID."""
    match = OVERCAST_PATTERN.search(url)
    if not match:
        return None
    return match.group("episode_id")


def resolve_input(url_or_path: str) -> ResolvedInput:
    """
    Resolve input to audio/transcript paths.

    For Apple Podcasts URLs: looks up local cache for TTML transcript.
    For Overcast URLs: fetches page to get episode metadata, then searches Apple cache.
    For file paths: returns path directly.
    """
    input_type = detect_input_type(url_or_path)

    if input_type == InputType.FILE_PATH:
        path = Path(url_or_path).expanduser().resolve()
        return ResolvedInput(
            input_type=input_type,
            audio_path=path,
        )

    if input_type == InputType.APPLE_PODCASTS_URL:
        from .apple_podcasts import resolve_apple_url

        return resolve_apple_url(url_or_path)

    if input_type == InputType.OVERCAST_URL:
        from .overcast import resolve_overcast_url

        return resolve_overcast_url(url_or_path)

    return ResolvedInput(input_type=input_type)
