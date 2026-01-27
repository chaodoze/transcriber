"""Pydantic models for transcription output."""

from pydantic import BaseModel


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


class QuickTranscriptResult(BaseModel):
    """Fast transcription without diarization."""

    text: str
    segments: list[dict]
    duration: float
    language: str
