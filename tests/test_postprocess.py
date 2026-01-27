"""Tests for post-processing module."""

from transcriber.postprocess import (
    identify_speaker_names,
    remove_fillers_from_text,
)


def test_remove_basic_fillers():
    """Test removal of basic filler words."""
    text = "Um, I think, uh, this is basically a good idea."
    result = remove_fillers_from_text(text)
    assert "um" not in result.lower()
    assert "uh" not in result.lower()
    assert "basically" not in result.lower()


def test_remove_filler_phrases():
    """Test removal of multi-word filler phrases."""
    text = "So, you know, I mean, it's sort of complicated."
    result = remove_fillers_from_text(text)
    assert "you know" not in result.lower()
    assert "i mean" not in result.lower()
    assert "sort of" not in result.lower()


def test_preserve_meaningful_content():
    """Test that meaningful words are preserved."""
    text = "I actually like this approach."
    result = remove_fillers_from_text(text)
    assert "like" in result.lower()
    assert "approach" in result.lower()


def test_identify_speaker_names():
    """Test speaker name identification from text."""
    segments = [
        {"speaker": "SPEAKER_00", "text": "Hi, I'm John and welcome to the show."},
        {"speaker": "SPEAKER_01", "text": "Thanks for having me, my name is Sarah."},
    ]
    names = identify_speaker_names(segments)
    assert names.get("SPEAKER_00") == "John"
    assert names.get("SPEAKER_01") == "Sarah"


def test_no_false_positives():
    """Test that we don't identify names incorrectly."""
    segments = [
        {"speaker": "SPEAKER_00", "text": "The weather is nice today."},
    ]
    names = identify_speaker_names(segments)
    assert len(names) == 0
