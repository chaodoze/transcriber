"""Speaker diarization module using pyannote-audio."""

import os
from pathlib import Path

import torch
import torchaudio
from pyannote.audio import Pipeline

# HuggingFace token for gated models
HF_TOKEN = os.environ.get("HF_TOKEN")

# Cache the pipeline to avoid reloading
_pipeline: Pipeline | None = None


def get_pipeline() -> Pipeline:
    """Get or create the diarization pipeline."""
    global _pipeline

    if _pipeline is None:
        if not HF_TOKEN:
            raise ValueError(
                "HF_TOKEN environment variable required for pyannote models. "
                "Get your token at https://huggingface.co/settings/tokens"
            )

        _pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            token=HF_TOKEN,
        )

        # Use MPS (Metal) on Apple Silicon if available
        if torch.backends.mps.is_available():
            _pipeline.to(torch.device("mps"))

    return _pipeline


def diarize_audio(audio_path: str | Path) -> list[dict]:
    """
    Perform speaker diarization on audio file.

    Args:
        audio_path: Path to audio file

    Returns:
        List of dicts with: speaker, start, end
    """
    pipeline = get_pipeline()
    audio_path = str(audio_path)

    # Load audio with torchaudio to avoid torchcodec issues
    waveform, sample_rate = torchaudio.load(audio_path)

    # pyannote expects a dict with waveform and sample_rate
    audio_input = {"waveform": waveform, "sample_rate": sample_rate}

    diarization = pipeline(audio_input)

    segments = []

    # Handle both Annotation (old API) and DiarizeOutput (new API)
    if hasattr(diarization, "itertracks"):
        # Standard Annotation object
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            segments.append({
                "speaker": speaker,
                "start": turn.start,
                "end": turn.end,
            })
    elif hasattr(diarization, "speaker_diarization"):
        # DiarizeOutput from newer pipelines (e.g., community-1)
        annotation = diarization.speaker_diarization
        for turn, _, speaker in annotation.itertracks(yield_label=True):
            segments.append({
                "speaker": speaker,
                "start": turn.start,
                "end": turn.end,
            })
    else:
        # Fallback: try to iterate directly or inspect the object
        # Print available attributes for debugging
        available = [attr for attr in dir(diarization) if not attr.startswith("_")]
        raise TypeError(
            f"Unknown diarization output type: {type(diarization).__name__}. "
            f"Available attributes: {available}"
        )

    return segments


def assign_speakers_to_words(
    word_segments: list[dict],
    diarization_segments: list[dict],
) -> list[dict]:
    """
    Assign speaker labels to word segments based on diarization.

    Uses the midpoint of each word to determine which speaker segment it belongs to.
    """
    result = []

    for word in word_segments:
        word_mid = (word["start"] + word["end"]) / 2
        speaker = "Unknown"

        # Find the diarization segment that contains this word's midpoint
        for seg in diarization_segments:
            if seg["start"] <= word_mid <= seg["end"]:
                speaker = seg["speaker"]
                break

        result.append({
            **word,
            "speaker": speaker,
        })

    return result


def merge_speaker_segments(word_segments: list[dict]) -> list[dict]:
    """
    Merge consecutive words from the same speaker into segments.

    Returns list of dicts with: speaker, text, start, end
    """
    if not word_segments:
        return []

    segments = []
    current_speaker = word_segments[0]["speaker"]
    current_words = []
    current_start = word_segments[0]["start"]
    current_end = word_segments[0]["end"]

    for word in word_segments:
        if word["speaker"] == current_speaker:
            current_words.append(word["word"])
            current_end = word["end"]
        else:
            # Save current segment
            segments.append({
                "speaker": current_speaker,
                "text": " ".join(current_words),
                "start": current_start,
                "end": current_end,
            })
            # Start new segment
            current_speaker = word["speaker"]
            current_words = [word["word"]]
            current_start = word["start"]
            current_end = word["end"]

    # Don't forget the last segment
    if current_words:
        segments.append({
            "speaker": current_speaker,
            "text": " ".join(current_words),
            "start": current_start,
            "end": current_end,
        })

    return segments
