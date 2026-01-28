"""Tests for TTML parser module."""

import pytest

from src.transcriber.models import TranscriptSource
from src.transcriber.ttml_parser import (
    clean_speaker_label,
    parse_ttml_string,
    parse_ttml_timestamp,
)


class TestParseTtmlTimestamp:
    """Tests for parse_ttml_timestamp function."""

    def test_seconds_only(self):
        assert parse_ttml_timestamp("0.860") == pytest.approx(0.860)
        assert parse_ttml_timestamp("45.123") == pytest.approx(45.123)

    def test_minutes_seconds(self):
        assert parse_ttml_timestamp("1:48.737") == pytest.approx(108.737)
        assert parse_ttml_timestamp("10:30.000") == pytest.approx(630.0)

    def test_hours_minutes_seconds(self):
        assert parse_ttml_timestamp("1:02:03.456") == pytest.approx(3723.456)
        assert parse_ttml_timestamp("0:05:30.000") == pytest.approx(330.0)

    def test_empty_string(self):
        assert parse_ttml_timestamp("") == 0.0

    def test_none_returns_zero(self):
        # Should handle None gracefully
        assert parse_ttml_timestamp(None) == 0.0


class TestCleanSpeakerLabel:
    """Tests for clean_speaker_label function."""

    def test_speaker_underscore_format(self):
        assert clean_speaker_label("SPEAKER_1") == "Speaker 1"
        assert clean_speaker_label("SPEAKER_10") == "Speaker 10"

    def test_speaker_space_format(self):
        assert clean_speaker_label("SPEAKER 2") == "Speaker 2"

    def test_lowercase_speaker(self):
        assert clean_speaker_label("speaker_1") == "Speaker 1"

    def test_custom_label(self):
        assert clean_speaker_label("John") == "John"
        assert clean_speaker_label("Host") == "Host"

    def test_empty_returns_unknown(self):
        assert clean_speaker_label("") == "Unknown"
        assert clean_speaker_label(None) == "Unknown"


class TestParseTtmlString:
    """Tests for parse_ttml_string function."""

    def test_basic_ttml(self):
        ttml = """<?xml version="1.0" encoding="UTF-8"?>
        <tt xmlns="http://www.w3.org/ns/ttml"
            xmlns:ttm="http://www.w3.org/ns/ttml#metadata">
            <body dur="60.0">
                <div>
                    <p begin="0.0" end="10.0" ttm:agent="SPEAKER_1">
                        Hello world
                    </p>
                    <p begin="10.0" end="20.0" ttm:agent="SPEAKER_2">
                        Hi there
                    </p>
                </div>
            </body>
        </tt>
        """
        result = parse_ttml_string(ttml)

        assert len(result.segments) == 2
        assert result.segments[0].speaker == "Speaker 1"
        assert result.segments[0].text == "Hello world"
        assert result.segments[0].start == 0.0
        assert result.segments[0].end == 10.0

        assert result.segments[1].speaker == "Speaker 2"
        assert result.segments[1].text == "Hi there"

        assert result.speakers == ["Speaker 1", "Speaker 2"]
        assert result.duration == 60.0
        assert result.source == TranscriptSource.APPLE_CACHE

    def test_ttml_with_word_spans(self):
        ttml = """<?xml version="1.0" encoding="UTF-8"?>
        <tt xmlns="http://www.w3.org/ns/ttml"
            xmlns:ttm="http://www.w3.org/ns/ttml#metadata"
            xmlns:podcasts="http://podcasts.apple.com/transcript-ttml-internal">
            <body dur="30.0">
                <div>
                    <p begin="0.0" end="5.0" ttm:agent="SPEAKER_1">
                        <span podcasts:unit="sentence">
                            <span podcasts:unit="word" begin="0.0" end="0.5">Hello</span>
                            <span podcasts:unit="word" begin="0.5" end="1.0">world</span>
                        </span>
                    </p>
                </div>
            </body>
        </tt>
        """
        result = parse_ttml_string(ttml)

        assert len(result.segments) == 1
        assert result.segments[0].text == "Hello world"

    def test_ttml_duration_from_last_segment(self):
        """When body has no dur attribute, duration should come from last segment."""
        ttml = """<?xml version="1.0" encoding="UTF-8"?>
        <tt xmlns="http://www.w3.org/ns/ttml"
            xmlns:ttm="http://www.w3.org/ns/ttml#metadata">
            <body>
                <div>
                    <p begin="0.0" end="45.5" ttm:agent="SPEAKER_1">
                        Test segment
                    </p>
                </div>
            </body>
        </tt>
        """
        result = parse_ttml_string(ttml)

        assert result.duration == 45.5

    def test_empty_paragraphs_skipped(self):
        ttml = """<?xml version="1.0" encoding="UTF-8"?>
        <tt xmlns="http://www.w3.org/ns/ttml"
            xmlns:ttm="http://www.w3.org/ns/ttml#metadata">
            <body dur="30.0">
                <div>
                    <p begin="0.0" end="5.0" ttm:agent="SPEAKER_1"></p>
                    <p begin="5.0" end="10.0" ttm:agent="SPEAKER_1">   </p>
                    <p begin="10.0" end="15.0" ttm:agent="SPEAKER_1">Real content</p>
                </div>
            </body>
        </tt>
        """
        result = parse_ttml_string(ttml)

        assert len(result.segments) == 1
        assert result.segments[0].text == "Real content"
