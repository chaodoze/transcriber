"""Pydantic models for transcription output."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class TranscriptSource(str, Enum):
    """Source of transcript data."""

    SPEECH_TO_TEXT = "speech_to_text"
    APPLE_CACHE = "apple_cache"


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
