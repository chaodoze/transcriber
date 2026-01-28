"""Overcast URL resolution - extract episode metadata and audio URL."""

import re
from typing import Optional
from urllib.error import URLError
from urllib.request import urlopen

from .apple_podcasts import search_episode_by_title
from .url_resolver import InputType, ResolvedInput, parse_overcast_url


def fetch_overcast_page(url: str) -> Optional[str]:
    """Fetch Overcast page HTML content."""
    try:
        with urlopen(url, timeout=10) as response:
            return response.read().decode("utf-8")
    except (URLError, TimeoutError):
        return None


def extract_episode_metadata(html: str) -> tuple[Optional[str], Optional[str]]:
    """
    Extract episode title and podcast title from Overcast page HTML.

    Returns (episode_title, podcast_title).
    """
    episode_title = None
    podcast_title = None

    # Episode title is typically in <title> or an <h2> tag
    # Format: "Episode Title — Podcast Name" or similar
    title_match = re.search(r"<title>([^<]+)</title>", html, re.IGNORECASE)
    if title_match:
        full_title = title_match.group(1).strip()
        # Common separators: " — ", " - ", " | "
        for sep in [" — ", " - ", " | "]:
            if sep in full_title:
                parts = full_title.split(sep)
                if len(parts) >= 2:
                    episode_title = parts[0].strip()
                    podcast_title = parts[-1].strip()
                    # Remove "Overcast" suffix if present
                    if podcast_title.endswith(" — Overcast"):
                        podcast_title = podcast_title[:-11]
                    break

    # Try to find episode title from og:title meta tag
    if not episode_title:
        og_title_match = re.search(
            r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']',
            html,
            re.IGNORECASE,
        )
        if og_title_match:
            episode_title = og_title_match.group(1).strip()

    # Try to find podcast title from og:site_name meta tag
    if not podcast_title:
        og_site_match = re.search(
            r'<meta\s+property=["\']og:site_name["\']\s+content=["\']([^"\']+)["\']',
            html,
            re.IGNORECASE,
        )
        if og_site_match:
            podcast_title = og_site_match.group(1).strip()

    return episode_title, podcast_title


def extract_audio_url(html: str) -> Optional[str]:
    """
    Extract audio URL from Overcast page HTML.

    Looks for <source> or <audio> tags.
    """
    # Try <source src="...">
    source_match = re.search(r'<source\s+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
    if source_match:
        url = source_match.group(1)
        # Remove #t=N timestamp suffix
        return url.split("#")[0]

    # Try <audio src="...">
    audio_match = re.search(r'<audio[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
    if audio_match:
        url = audio_match.group(1)
        return url.split("#")[0]

    return None


def resolve_overcast_url(url: str) -> ResolvedInput:
    """
    Resolve Overcast URL by:
    1. Fetching the page to get episode metadata
    2. Searching Apple Podcasts cache for matching episode
    3. Extracting audio URL as fallback

    Returns ResolvedInput with either transcript path (if found in Apple cache)
    or audio URL for transcription.
    """
    episode_id = parse_overcast_url(url)

    # Fetch Overcast page
    html = fetch_overcast_page(url)
    if not html:
        return ResolvedInput(
            input_type=InputType.OVERCAST_URL,
            episode_id=episode_id,
        )

    # Extract metadata
    episode_title, podcast_title = extract_episode_metadata(html)

    # Search Apple Podcasts cache
    apple_episode = None
    if episode_title:
        apple_episode = search_episode_by_title(episode_title, podcast_title)

    # Check for cached transcript
    transcript_path = None
    apple_audio_url = None
    if apple_episode:
        from .apple_podcasts import get_ttml_path

        transcript_path = get_ttml_path(apple_episode)
        apple_audio_url = apple_episode.audio_url

    # Extract audio URL from Overcast as fallback
    overcast_audio_url = extract_audio_url(html)

    # Prefer Apple's audio URL if available (usually better quality)
    audio_url = apple_audio_url or overcast_audio_url

    return ResolvedInput(
        input_type=InputType.OVERCAST_URL,
        transcript_path=transcript_path,
        audio_url=audio_url,
        episode_id=episode_id,
        episode_title=episode_title,
        podcast_title=podcast_title,
    )
