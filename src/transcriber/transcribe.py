"""Transcription module using mlx-whisper for Apple Silicon."""

import os
from pathlib import Path

import mlx_whisper

# Default model optimized for speed on Apple Silicon
DEFAULT_MODEL = os.environ.get("WHISPER_MODEL", "mlx-community/distil-whisper-large-v3")


def transcribe_audio(
    audio_path: str | Path,
    model: str = DEFAULT_MODEL,
    language: str | None = None,
    word_timestamps: bool = True,
) -> dict:
    """
    Transcribe audio file using mlx-whisper.

    Args:
        audio_path: Path to audio file
        model: Whisper model to use
        language: Language code (e.g., "en") or None for auto-detect
        word_timestamps: Whether to include word-level timestamps

    Returns:
        Dictionary with transcription results including segments and text
    """
    audio_path = str(audio_path)

    result = mlx_whisper.transcribe(
        audio_path,
        path_or_hf_repo=model,
        language=language,
        word_timestamps=word_timestamps,
        verbose=False,
    )

    return {
        "text": result["text"],
        "segments": result["segments"],
        "language": result.get("language", language or "en"),
    }


def get_word_segments(transcription_result: dict) -> list[dict]:
    """
    Extract word-level segments from transcription result.

    Returns list of dicts with: word, start, end
    """
    words = []
    for segment in transcription_result.get("segments", []):
        for word_info in segment.get("words", []):
            words.append({
                "word": word_info["word"].strip(),
                "start": word_info["start"],
                "end": word_info["end"],
            })
    return words
