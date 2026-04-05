"""Twitter/X API v2 client for reading tweets."""

import json
import os
import re
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import Tweet, TweetAuthor, TweetResult, TweetSearchResult

# Twitter API v2 base URL
API_BASE = "https://api.twitter.com/2"

# Fields to request from the API
TWEET_FIELDS = (
    "created_at,public_metrics,conversation_id,"
    "in_reply_to_user_id,note_tweet,referenced_tweets"
)
USER_FIELDS = "username,name"
EXPANSIONS = "author_id,attachments.media_keys"
MEDIA_FIELDS = "url,preview_image_url,type,variants,alt_text"


def parse_tweet_url(url_or_id: str) -> str:
    """Extract tweet ID from a Twitter/X URL or pass through a numeric ID.

    Supports:
    - https://twitter.com/user/status/1234567890
    - https://x.com/user/status/1234567890
    - 1234567890 (numeric ID)
    """
    url_or_id = url_or_id.strip()

    # Numeric ID
    if re.fullmatch(r"\d+", url_or_id):
        return url_or_id

    # URL pattern
    match = re.search(r"(?:twitter\.com|x\.com)/\w+/status/(\d+)", url_or_id)
    if match:
        return match.group(1)

    raise ValueError(
        f"Could not parse tweet ID from: {url_or_id}. "
        "Provide a tweet URL (x.com or twitter.com) or numeric tweet ID."
    )


def _get_bearer_token() -> str:
    """Read Twitter Bearer token from environment."""
    token = os.environ.get("TWITTER_BEARER_TOKEN")
    if not token:
        raise RuntimeError(
            "TWITTER_BEARER_TOKEN environment variable not set. "
            "Get one from https://developer.x.com/en/portal/dashboard"
        )
    return token


def _bearer_request(endpoint: str, params: Optional[dict] = None) -> dict:
    """Make an authenticated GET request to the Twitter API v2."""
    token = _get_bearer_token()

    url = f"{API_BASE}/{endpoint}"
    if params:
        url = f"{url}?{urlencode(params)}"

    req = Request(url, headers={"Authorization": f"Bearer {token}"})

    try:
        with urlopen(req, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Twitter API error {e.code}: {body}") from e
    except (URLError, TimeoutError) as e:
        raise RuntimeError(f"Twitter API request failed: {e}") from e


def _resolve_media_urls(data: dict, includes: Optional[dict] = None) -> tuple[list[str], list[str]]:
    """Extract image and video URLs from tweet attachments via includes.media."""
    image_urls: list[str] = []
    video_urls: list[str] = []
    if not includes:
        return image_urls, video_urls

    media_keys = data.get("attachments", {}).get("media_keys", [])
    if not media_keys:
        return image_urls, video_urls

    media_lookup = {m["media_key"]: m for m in includes.get("media", [])}
    for key in media_keys:
        media = media_lookup.get(key)
        if not media:
            continue
        media_type = media.get("type")
        if media_type == "photo":
            url = media.get("url")
            if url:
                image_urls.append(url)
        elif media_type in ("video", "animated_gif"):
            variants = media.get("variants", [])
            mp4s = [v for v in variants if v.get("content_type") == "video/mp4"]
            if mp4s:
                best = max(mp4s, key=lambda v: v.get("bit_rate", 0))
                video_urls.append(best["url"])

    return image_urls, video_urls


def _parse_tweet(data: dict, includes: Optional[dict] = None) -> Tweet:
    """Convert an API v2 tweet object into a Tweet model."""
    # Resolve author from includes
    author = None
    if includes:
        author_id = data.get("author_id")
        for user in includes.get("users", []):
            if user.get("id") == author_id:
                author = TweetAuthor(
                    id=user["id"],
                    username=user["username"],
                    name=user["name"],
                )
                break

    metrics = data.get("public_metrics", {})
    username = author.username if author else "unknown"

    # Prefer full note_tweet text over truncated text
    note = data.get("note_tweet", {})
    text = note.get("text", data["text"]) if note else data["text"]

    image_urls, video_urls = _resolve_media_urls(data, includes)

    return Tweet(
        id=data["id"],
        text=text,
        author=author,
        created_at=data.get("created_at"),
        retweet_count=metrics.get("retweet_count"),
        like_count=metrics.get("like_count"),
        reply_count=metrics.get("reply_count"),
        impression_count=metrics.get("impression_count"),
        url=f"https://x.com/{username}/status/{data['id']}",
        image_urls=image_urls,
        video_urls=video_urls,
    )


def get_tweet(url_or_id: str) -> TweetResult:
    """Fetch a single tweet by URL or ID.

    Args:
        url_or_id: Tweet URL (x.com or twitter.com) or numeric tweet ID.

    Returns:
        TweetResult with the tweet data.
    """
    tweet_id = parse_tweet_url(url_or_id)

    resp = _bearer_request(
        f"tweets/{tweet_id}",
        {
            "tweet.fields": TWEET_FIELDS,
            "expansions": EXPANSIONS,
            "user.fields": USER_FIELDS,
            "media.fields": MEDIA_FIELDS,
        },
    )

    if "data" not in resp:
        errors = resp.get("errors", [{}])
        msg = errors[0].get("detail", "Tweet not found") if errors else "Tweet not found"
        raise RuntimeError(msg)

    tweet = _parse_tweet(resp["data"], resp.get("includes"))

    # If this tweet is a reply, fetch the parent tweet (one level only)
    for ref in resp["data"].get("referenced_tweets", []):
        if ref.get("type") == "replied_to":
            try:
                parent_resp = _bearer_request(
                    f"tweets/{ref['id']}",
                    {
                        "tweet.fields": TWEET_FIELDS,
                        "expansions": EXPANSIONS,
                        "user.fields": USER_FIELDS,
                        "media.fields": MEDIA_FIELDS,
                    },
                )
                if "data" in parent_resp:
                    tweet.replied_to = _parse_tweet(
                        parent_resp["data"], parent_resp.get("includes")
                    )
            except RuntimeError:
                pass  # Parent tweet may be deleted or inaccessible
            break

    return TweetResult(tweet=tweet)


def search_tweets(query: str, max_results: int = 10) -> TweetSearchResult:
    """Search recent tweets (last 7 days) using Twitter API v2.

    Args:
        query: Twitter search query (supports operators like from:, has:, etc.)
        max_results: Number of results (10-100).

    Returns:
        TweetSearchResult with matching tweets.
    """
    max_results = max(10, min(100, max_results))

    resp = _bearer_request(
        "tweets/search/recent",
        {
            "query": query,
            "max_results": max_results,
            "tweet.fields": TWEET_FIELDS,
            "expansions": EXPANSIONS,
            "user.fields": USER_FIELDS,
            "media.fields": MEDIA_FIELDS,
        },
    )

    includes = resp.get("includes")
    tweets = [_parse_tweet(t, includes) for t in resp.get("data", [])]
    meta = resp.get("meta", {})

    return TweetSearchResult(
        tweets=tweets,
        result_count=meta.get("result_count", len(tweets)),
        newest_id=meta.get("newest_id"),
        oldest_id=meta.get("oldest_id"),
    )


def get_user_tweets(username: str, max_results: int = 10) -> TweetSearchResult:
    """Get recent tweets from a user's timeline.

    Two-step: resolve username to user ID, then fetch their tweets.

    Args:
        username: Twitter username (without @).
        max_results: Number of results (5-100).

    Returns:
        TweetSearchResult with the user's recent tweets.
    """
    username = username.lstrip("@")
    max_results = max(5, min(100, max_results))

    # Step 1: Resolve username to user ID
    user_resp = _bearer_request(f"users/by/username/{username}")
    if "data" not in user_resp:
        errors = user_resp.get("errors", [{}])
        default_msg = f"User @{username} not found"
        msg = errors[0].get("detail", default_msg) if errors else default_msg
        raise RuntimeError(msg)

    user_id = user_resp["data"]["id"]
    user_data = user_resp["data"]

    # Step 2: Fetch user's tweets
    resp = _bearer_request(
        f"users/{user_id}/tweets",
        {
            "max_results": max_results,
            "tweet.fields": TWEET_FIELDS,
            "expansions": EXPANSIONS,
            "user.fields": USER_FIELDS,
            "media.fields": MEDIA_FIELDS,
        },
    )

    # Build includes with the known user if API doesn't return them
    includes = resp.get("includes", {})
    if not includes.get("users"):
        includes["users"] = [user_data]

    tweets = [_parse_tweet(t, includes) for t in resp.get("data", [])]
    meta = resp.get("meta", {})

    return TweetSearchResult(
        tweets=tweets,
        result_count=meta.get("result_count", len(tweets)),
        newest_id=meta.get("newest_id"),
        oldest_id=meta.get("oldest_id"),
    )
