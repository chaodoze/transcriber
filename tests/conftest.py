"""Shared fixtures for transcriber tests."""

import pytest

from transcriber.models import (
    Segment,
    TranscriptResult,
    TranscriptSource,
)


@pytest.fixture
def sample_segments():
    """Three sample transcript segments with realistic data."""
    return [
        Segment(speaker="Alice", text="Hello everyone, welcome to the show.", start=0.0, end=5.5),
        Segment(speaker="Bob", text="Thanks for having me.", start=5.5, end=10.0),
        Segment(speaker="Alice", text="Let's dive right in.", start=10.0, end=15.0),
    ]


@pytest.fixture
def sample_transcript_result(sample_segments):
    """Complete TranscriptResult built from sample segments."""
    return TranscriptResult(
        segments=sample_segments,
        speakers=["Alice", "Bob"],
        duration=15.0,
        language="en",
        source=TranscriptSource.SPEECH_TO_TEXT,
        episode_title="Test Episode",
        podcast_title="Test Podcast",
    )


@pytest.fixture
def sample_transcript_dict():
    """Transcript data as plain dict (for testing export helpers)."""
    return {
        "segments": [
            {"speaker": "Alice", "text": "Hello everyone.", "start": 0.0, "end": 5.5},
            {"speaker": "Bob", "text": "Thanks for having me.", "start": 5.5, "end": 10.0},
            {"speaker": "Alice", "text": "Let's dive right in.", "start": 10.0, "end": 15.0},
        ]
    }


@pytest.fixture
def sample_tweet_api_response():
    """Twitter API v2 single tweet response."""
    return {
        "data": {
            "id": "1234567890",
            "text": "Hello world from Twitter!",
            "author_id": "999",
            "created_at": "2026-03-27T12:00:00.000Z",
            "public_metrics": {
                "retweet_count": 10,
                "like_count": 50,
                "reply_count": 5,
                "impression_count": 1000,
            },
            "attachments": {"media_keys": ["media_1"]},
        },
        "includes": {
            "users": [
                {"id": "999", "username": "testuser", "name": "Test User"},
            ],
            "media": [
                {"media_key": "media_1", "type": "photo", "url": "https://pbs.twimg.com/media/test.jpg"},
            ],
        },
    }


@pytest.fixture
def sample_tweet_search_response():
    """Twitter API v2 search response with multiple tweets."""
    return {
        "data": [
            {
                "id": "111",
                "text": "First tweet",
                "author_id": "999",
                "public_metrics": {"retweet_count": 1, "like_count": 2,
                                   "reply_count": 0, "impression_count": 100},
            },
            {
                "id": "222",
                "text": "Second tweet",
                "author_id": "999",
                "public_metrics": {"retweet_count": 3, "like_count": 4,
                                   "reply_count": 1, "impression_count": 200},
            },
        ],
        "includes": {
            "users": [
                {"id": "999", "username": "testuser", "name": "Test User"},
            ]
        },
        "meta": {
            "result_count": 2,
            "newest_id": "222",
            "oldest_id": "111",
        },
    }


@pytest.fixture
def sample_user_lookup_response():
    """Twitter API v2 user lookup response."""
    return {
        "data": {
            "id": "999",
            "username": "testuser",
            "name": "Test User",
        }
    }
