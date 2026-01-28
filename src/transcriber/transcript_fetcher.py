"""Fetch Apple Podcasts transcripts via native helper tool."""

import subprocess
from pathlib import Path
from typing import Optional

# Path to the compiled FetchTranscript binary
TOOLS_DIR = Path(__file__).parent.parent.parent / "tools"
FETCH_TRANSCRIPT_BIN = TOOLS_DIR / "FetchTranscript"

# Default output directory for transcripts
DEFAULT_OUTPUT_DIR = (
    Path.home()
    / "Library/Group Containers/243LU875E5.groups.com.apple.podcasts"
    / "Library/Cache/Assets/TTML"
)


def is_fetcher_available() -> bool:
    """Check if the FetchTranscript binary is compiled and available."""
    return FETCH_TRANSCRIPT_BIN.exists() and FETCH_TRANSCRIPT_BIN.is_file()


def fetch_transcript(
    episode_id: int,
    output_dir: Optional[Path] = None,
    cache_bearer_token: bool = True,
) -> Optional[Path]:
    """
    Fetch transcript from Apple's API using the native helper tool.

    Args:
        episode_id: Apple Podcasts episode ID (ZSTORETRACKID)
        output_dir: Directory to save transcript (default: Apple's TTML cache)
        cache_bearer_token: Whether to cache the Bearer token for 30 days

    Returns:
        Path to downloaded TTML file, or None if fetch failed
    """
    if not is_fetcher_available():
        return None

    if output_dir is None:
        output_dir = DEFAULT_OUTPUT_DIR

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build command
    cmd = [str(FETCH_TRANSCRIPT_BIN), str(episode_id), "--output-dir", str(output_dir)]
    if cache_bearer_token:
        cmd.append("--cache-bearer-token")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(TOOLS_DIR),  # Run from tools dir so bearer_token.txt is cached there
        )

        if result.returncode != 0:
            # Log error but don't raise - caller should fall back to STT
            return None

        # Output is the path to the downloaded file
        output_path = result.stdout.strip()
        if output_path:
            path = Path(output_path)
            if path.exists():
                return path

        return None

    except subprocess.TimeoutExpired:
        return None
    except Exception:
        return None


def fetch_transcript_for_episode(
    store_track_id: Optional[int],
    transcript_identifier: Optional[str] = None,
) -> Optional[Path]:
    """
    Fetch transcript for an episode, placing it in the expected cache location.

    Args:
        store_track_id: Apple's store track ID for the episode
        transcript_identifier: Optional transcript identifier from database
            (used to determine correct subdirectory structure)

    Returns:
        Path to downloaded TTML file, or None if fetch failed
    """
    if not store_track_id:
        return None

    # Determine output directory based on transcript identifier
    if transcript_identifier:
        # Extract directory path from identifier
        # e.g., "PodcastContent221/v4/44/bd/d4/44bdd4f0-.../transcript_xxx.ttml"
        # -> output to "TTML_CACHE/PodcastContent221/v4/44/bd/d4/44bdd4f0-.../"
        parts = transcript_identifier.rsplit("/", 1)
        if len(parts) == 2:
            subdir = parts[0]
            output_dir = DEFAULT_OUTPUT_DIR / subdir
        else:
            output_dir = DEFAULT_OUTPUT_DIR
    else:
        output_dir = DEFAULT_OUTPUT_DIR

    return fetch_transcript(store_track_id, output_dir)
