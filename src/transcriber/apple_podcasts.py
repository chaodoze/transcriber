"""Apple Podcasts transcript extraction from local cache."""

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .url_resolver import InputType, ResolvedInput, parse_apple_url

# Apple Podcasts container paths
PODCASTS_GROUP_CONTAINER = (
    Path.home() / "Library/Group Containers/243LU875E5.groups.com.apple.podcasts"
)
TTML_CACHE_DIR = PODCASTS_GROUP_CONTAINER / "Library/Cache/Assets/TTML"
LIBRARY_DB = PODCASTS_GROUP_CONTAINER / "Documents/MTLibrary.sqlite"


@dataclass
class AppleEpisodeInfo:
    """Episode info from Apple Podcasts database."""

    pk: int
    uuid: str
    store_track_id: Optional[int]
    title: str
    podcast_title: Optional[str]
    transcript_identifier: Optional[str]
    audio_url: Optional[str]
    duration: Optional[float]


def get_db_connection() -> sqlite3.Connection:
    """Get read-only connection to Apple Podcasts database."""
    if not LIBRARY_DB.exists():
        raise FileNotFoundError(f"Apple Podcasts database not found: {LIBRARY_DB}")

    # Open in read-only mode to avoid locking issues
    uri = f"file:{LIBRARY_DB}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def get_episode_by_track_id(track_id: int) -> Optional[AppleEpisodeInfo]:
    """
    Find episode by iTunes store track ID.

    The track ID comes from Apple Podcasts URLs (?i=XXXXX parameter).
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                e.Z_PK,
                e.ZUUID,
                e.ZSTORETRACKID,
                e.ZTITLE,
                e.ZTRANSCRIPTIDENTIFIER,
                e.ZENCLOSUREURL,
                e.ZDURATION,
                p.ZTITLE as ZPODCASTTITLE
            FROM ZMTEPISODE e
            LEFT JOIN ZMTPODCAST p ON e.ZPODCAST = p.Z_PK
            WHERE e.ZSTORETRACKID = ?
            """,
            (track_id,),
        )

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return AppleEpisodeInfo(
            pk=row["Z_PK"],
            uuid=row["ZUUID"] or "",
            store_track_id=row["ZSTORETRACKID"],
            title=row["ZTITLE"] or "",
            podcast_title=row["ZPODCASTTITLE"],
            transcript_identifier=row["ZTRANSCRIPTIDENTIFIER"],
            audio_url=row["ZENCLOSUREURL"],
            duration=row["ZDURATION"],
        )
    except sqlite3.Error:
        return None


def search_episode_by_title(
    episode_title: str, podcast_title: Optional[str] = None
) -> Optional[AppleEpisodeInfo]:
    """
    Search for episode by title (fuzzy match).

    Used when looking up episodes from Overcast URLs where we only have titles.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Normalize search terms
        episode_title_normalized = episode_title.lower().strip()

        if podcast_title:
            podcast_title_normalized = podcast_title.lower().strip()
            cursor.execute(
                """
                SELECT
                    e.Z_PK,
                    e.ZUUID,
                    e.ZSTORETRACKID,
                    e.ZTITLE,
                    e.ZTRANSCRIPTIDENTIFIER,
                    e.ZENCLOSUREURL,
                    e.ZDURATION,
                    p.ZTITLE as ZPODCASTTITLE
                FROM ZMTEPISODE e
                LEFT JOIN ZMTPODCAST p ON e.ZPODCAST = p.Z_PK
                WHERE LOWER(e.ZTITLE) LIKE ?
                AND LOWER(p.ZTITLE) LIKE ?
                LIMIT 1
                """,
                (f"%{episode_title_normalized}%", f"%{podcast_title_normalized}%"),
            )
        else:
            cursor.execute(
                """
                SELECT
                    e.Z_PK,
                    e.ZUUID,
                    e.ZSTORETRACKID,
                    e.ZTITLE,
                    e.ZTRANSCRIPTIDENTIFIER,
                    e.ZENCLOSUREURL,
                    e.ZDURATION,
                    p.ZTITLE as ZPODCASTTITLE
                FROM ZMTEPISODE e
                LEFT JOIN ZMTPODCAST p ON e.ZPODCAST = p.Z_PK
                WHERE LOWER(e.ZTITLE) LIKE ?
                LIMIT 1
                """,
                (f"%{episode_title_normalized}%",),
            )

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return AppleEpisodeInfo(
            pk=row["Z_PK"],
            uuid=row["ZUUID"] or "",
            store_track_id=row["ZSTORETRACKID"],
            title=row["ZTITLE"] or "",
            podcast_title=row["ZPODCASTTITLE"],
            transcript_identifier=row["ZTRANSCRIPTIDENTIFIER"],
            audio_url=row["ZENCLOSUREURL"],
            duration=row["ZDURATION"],
        )
    except sqlite3.Error:
        return None


def get_ttml_path(episode: AppleEpisodeInfo) -> Optional[Path]:
    """
    Get full path to cached TTML file if it exists.

    Returns None if transcript not cached locally.
    """
    if not episode.transcript_identifier:
        return None

    ttml_path = TTML_CACHE_DIR / episode.transcript_identifier

    if ttml_path.exists():
        return ttml_path

    return None


def list_cached_transcripts() -> list[tuple[Path, Optional[AppleEpisodeInfo]]]:
    """
    List all locally cached TTML transcripts with their episode info.

    Returns list of (ttml_path, episode_info) tuples.
    """
    if not TTML_CACHE_DIR.exists():
        return []

    results = []
    for ttml_path in TTML_CACHE_DIR.rglob("*.ttml"):
        # Try to match to database
        relative_path = str(ttml_path.relative_to(TTML_CACHE_DIR))
        episode = _find_episode_by_transcript_path(relative_path)
        results.append((ttml_path, episode))

    return results


def _find_episode_by_transcript_path(transcript_path: str) -> Optional[AppleEpisodeInfo]:
    """Find episode by transcript identifier path."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                e.Z_PK,
                e.ZUUID,
                e.ZSTORETRACKID,
                e.ZTITLE,
                e.ZTRANSCRIPTIDENTIFIER,
                e.ZENCLOSUREURL,
                e.ZDURATION,
                p.ZTITLE as ZPODCASTTITLE
            FROM ZMTEPISODE e
            LEFT JOIN ZMTPODCAST p ON e.ZPODCAST = p.Z_PK
            WHERE e.ZTRANSCRIPTIDENTIFIER = ?
            """,
            (transcript_path,),
        )

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return AppleEpisodeInfo(
            pk=row["Z_PK"],
            uuid=row["ZUUID"] or "",
            store_track_id=row["ZSTORETRACKID"],
            title=row["ZTITLE"] or "",
            podcast_title=row["ZPODCASTTITLE"],
            transcript_identifier=row["ZTRANSCRIPTIDENTIFIER"],
            audio_url=row["ZENCLOSUREURL"],
            duration=row["ZDURATION"],
        )
    except sqlite3.Error:
        return None


def resolve_apple_url(url: str) -> ResolvedInput:
    """
    Resolve Apple Podcasts URL to transcript or audio.

    Checks local cache for TTML transcript, falls back to audio URL.
    """
    podcast_id, episode_id, show_slug = parse_apple_url(url)

    if not episode_id:
        # URL is for a show, not an episode
        return ResolvedInput(
            input_type=InputType.APPLE_PODCASTS_URL,
        )

    # Look up episode by track ID
    episode = get_episode_by_track_id(int(episode_id))

    if not episode:
        return ResolvedInput(
            input_type=InputType.APPLE_PODCASTS_URL,
            episode_id=episode_id,
        )

    # Check for cached TTML transcript
    ttml_path = get_ttml_path(episode)

    return ResolvedInput(
        input_type=InputType.APPLE_PODCASTS_URL,
        transcript_path=ttml_path,
        audio_url=episode.audio_url,
        episode_id=episode_id,
        episode_title=episode.title,
        podcast_title=episode.podcast_title,
    )
