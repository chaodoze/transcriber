"""Pydantic models for transcription output."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class TranscriptSource(str, Enum):
    """Source of transcript data."""

    SPEECH_TO_TEXT = "speech_to_text"
    APPLE_CACHE = "apple_cache"
    YOUTUBE_CAPTIONS = "youtube_captions"


class Segment(BaseModel):
    """A single transcript segment with speaker and timing."""

    speaker: str
    text: str
    start: float
    end: float


class TranscriptResult(BaseModel):
    """Full transcription result."""

    segments: list[Segment]
    speakers: list[str]
    duration: float
    language: str
    source: TranscriptSource = TranscriptSource.SPEECH_TO_TEXT
    episode_title: Optional[str] = None
    podcast_title: Optional[str] = None


class QuickTranscriptResult(BaseModel):
    """Fast transcription without diarization."""

    text: str
    segments: list[dict]
    duration: float
    language: str


class TocEntry(BaseModel):
    """A single entry in an ebook table of contents."""

    index: int
    title: str
    level: int
    href: str
    number: Optional[str] = None


class EbookTocResult(BaseModel):
    """Table of contents for an ebook."""

    title: str
    authors: list[str]
    language: Optional[str] = None
    toc: list[TocEntry]
    total_chapters: int


class TweetAuthor(BaseModel):
    """Twitter/X user who authored a tweet."""

    id: str
    username: str
    name: str


class Tweet(BaseModel):
    """A single tweet from Twitter/X API v2."""

    id: str
    text: str
    author: Optional[TweetAuthor] = None
    created_at: Optional[str] = None
    retweet_count: Optional[int] = None
    like_count: Optional[int] = None
    reply_count: Optional[int] = None
    impression_count: Optional[int] = None
    url: Optional[str] = None
    replied_to: Optional["Tweet"] = None
    image_urls: list[str] = []
    video_urls: list[str] = []


class TweetResult(BaseModel):
    """Result of fetching a single tweet."""

    tweet: Tweet


class TweetSearchResult(BaseModel):
    """Result of searching or listing tweets."""

    tweets: list[Tweet]
    result_count: int
    newest_id: Optional[str] = None
    oldest_id: Optional[str] = None


class EbookChapterResult(BaseModel):
    """Content of a single ebook chapter."""

    book_title: str
    chapter_title: str
    chapter_number: Optional[str] = None
    chapter_index: int
    content: str
    word_count: int
    prev_chapter: Optional[str] = None
    next_chapter: Optional[str] = None
