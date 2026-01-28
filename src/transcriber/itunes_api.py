"""iTunes Search API for looking up podcast episodes."""

import json
from dataclasses import dataclass
from typing import Optional
from urllib.error import URLError
from urllib.parse import quote_plus
from urllib.request import urlopen


@dataclass
class iTunesEpisode:
    """Episode info from iTunes API."""

    track_id: int
    track_name: str
    collection_name: str
    artist_name: str
    release_date: Optional[str] = None
    description: Optional[str] = None
    audio_url: Optional[str] = None


def search_episodes(
    query: str,
    limit: int = 10,
) -> list[iTunesEpisode]:
    """
    Search iTunes for podcast episodes.

    Args:
        query: Search query (episode title, podcast name, etc.)
        limit: Maximum number of results

    Returns:
        List of matching episodes
    """
    encoded_query = quote_plus(query)
    url = (
        f"https://itunes.apple.com/search"
        f"?term={encoded_query}"
        f"&entity=podcastEpisode"
        f"&limit={limit}"
    )

    try:
        with urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, json.JSONDecodeError):
        return []

    episodes = []
    for result in data.get("results", []):
        episodes.append(
            iTunesEpisode(
                track_id=result.get("trackId"),
                track_name=result.get("trackName", ""),
                collection_name=result.get("collectionName", ""),
                artist_name=result.get("artistName", ""),
                release_date=result.get("releaseDate"),
                description=result.get("description"),
                audio_url=result.get("episodeUrl"),
            )
        )

    return episodes


def find_episode_by_title(
    episode_title: str,
    podcast_title: Optional[str] = None,
) -> Optional[iTunesEpisode]:
    """
    Find a specific episode by title.

    Args:
        episode_title: Episode title to search for
        podcast_title: Optional podcast name to narrow search

    Returns:
        Best matching episode, or None if not found
    """
    # Build search query
    if podcast_title:
        query = f"{episode_title} {podcast_title}"
    else:
        query = episode_title

    episodes = search_episodes(query, limit=10)

    if not episodes:
        return None

    # Try to find exact or close match
    episode_title_lower = episode_title.lower()
    podcast_title_lower = podcast_title.lower() if podcast_title else None

    for ep in episodes:
        title_match = episode_title_lower in ep.track_name.lower()
        podcast_match = (
            podcast_title_lower is None
            or podcast_title_lower in ep.collection_name.lower()
        )

        if title_match and podcast_match:
            return ep

    # Return first result as fallback if no exact match
    return episodes[0] if episodes else None


def get_episode_by_id(track_id: int) -> Optional[iTunesEpisode]:
    """
    Look up a specific episode by its iTunes track ID.

    Args:
        track_id: iTunes track ID

    Returns:
        Episode info, or None if not found
    """
    url = f"https://itunes.apple.com/lookup?id={track_id}&entity=podcastEpisode"

    try:
        with urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, json.JSONDecodeError):
        return None

    results = data.get("results", [])
    # First result is usually the podcast, second is the episode
    for result in results:
        if result.get("wrapperType") == "podcastEpisode":
            return iTunesEpisode(
                track_id=result.get("trackId"),
                track_name=result.get("trackName", ""),
                collection_name=result.get("collectionName", ""),
                artist_name=result.get("artistName", ""),
                release_date=result.get("releaseDate"),
                description=result.get("description"),
                audio_url=result.get("episodeUrl"),
            )

    return None
