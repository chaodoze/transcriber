"""Overcast URL resolution - extract episode metadata and audio URL."""

import html
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


def extract_episode_metadata(page_html: str) -> tuple[Optional[str], Optional[str]]:
    """
    Extract episode title and podcast title from Overcast page HTML.

    Returns (episode_title, podcast_title).
    """
    episode_title = None
    podcast_title = None

    # Episode title is typically in <title> or an <h2> tag
    # Format: "Episode Title — Podcast Name — Overcast"
    title_match = re.search(r"<title>([^<]+)</title>", page_html, re.IGNORECASE)
    if title_match:
        # Decode HTML entities like &mdash; -> —
        full_title = html.unescape(title_match.group(1).strip())
        # Common separators: " — ", " - ", " | "
        for sep in [" — ", " - ", " | "]:
            if sep in full_title:
                parts = full_title.split(sep)
                if len(parts) >= 2:
                    episode_title = parts[0].strip()
                    # Podcast title is second-to-last (last is "Overcast")
                    if len(parts) >= 3 and parts[-1].strip() == "Overcast":
                        podcast_title = parts[-2].strip()
                    else:
                        podcast_title = parts[-1].strip()
                    break

    # Try to find episode title from og:title meta tag
    if not episode_title:
        og_title_match = re.search(
            r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']',
            page_html,
            re.IGNORECASE,
        )
        if og_title_match:
            full_og_title = html.unescape(og_title_match.group(1).strip())
            # og:title may also have "Episode — Podcast" format
            for sep in [" — ", " - ", " | "]:
                if sep in full_og_title:
                    parts = full_og_title.split(sep)
                    episode_title = parts[0].strip()
                    if not podcast_title and len(parts) >= 2:
                        podcast_title = parts[-1].strip()
                    break
            if not episode_title:
                episode_title = full_og_title

    # Try to find podcast title from og:site_name meta tag
    if not podcast_title:
        og_site_match = re.search(
            r'<meta\s+property=["\']og:site_name["\']\s+content=["\']([^"\']+)["\']',
            page_html,
            re.IGNORECASE,
        )
        if og_site_match:
            podcast_title = html.unescape(og_site_match.group(1).strip())

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
    2. Searching Apple Podcasts local cache for matching episode
    3. If not in local cache, searching iTunes API for episode ID
    4. Fetching transcript from Apple's API
    5. Extracting audio URL as fallback for speech-to-text

    Returns ResolvedInput with transcript path (if available) or audio URL.
    """
    overcast_episode_id = parse_overcast_url(url)

    # Fetch Overcast page
    page_html = fetch_overcast_page(url)
    if not page_html:
        return ResolvedInput(
            input_type=InputType.OVERCAST_URL,
            episode_id=overcast_episode_id,
        )

    # Extract metadata
    episode_title, podcast_title = extract_episode_metadata(page_html)

    # Extract audio URL from Overcast (fallback for STT)
    overcast_audio_url = extract_audio_url(page_html)

    transcript_path = None
    apple_audio_url = None
    apple_track_id = None

    # Strategy 1: Search local Apple Podcasts database
    if episode_title:
        apple_episode = search_episode_by_title(episode_title, podcast_title)
        if apple_episode:
            from .apple_podcasts import get_or_fetch_ttml_path

            transcript_path = get_or_fetch_ttml_path(apple_episode)
            apple_audio_url = apple_episode.audio_url
            apple_track_id = apple_episode.store_track_id

    # Strategy 2: Search iTunes API if not found locally
    if not transcript_path and episode_title:
        from .itunes_api import find_episode_by_title
        from .transcript_fetcher import fetch_transcript

        itunes_episode = find_episode_by_title(episode_title, podcast_title)
        if itunes_episode and itunes_episode.track_id:
            apple_track_id = itunes_episode.track_id
            # Try to fetch transcript using iTunes track ID
            fetched_path = fetch_transcript(itunes_episode.track_id)
            if fetched_path:
                transcript_path = fetched_path
            # Use iTunes audio URL if available
            if not apple_audio_url and itunes_episode.audio_url:
                apple_audio_url = itunes_episode.audio_url

    # Prefer Apple's audio URL if available (usually better quality)
    audio_url = apple_audio_url or overcast_audio_url

    return ResolvedInput(
        input_type=InputType.OVERCAST_URL,
        transcript_path=transcript_path,
        audio_url=audio_url,
        episode_id=str(apple_track_id) if apple_track_id else overcast_episode_id,
        episode_title=episode_title,
        podcast_title=podcast_title,
    )
