"""Tests for Instagram URL resolution and audio download."""

from unittest.mock import patch

from transcriber.instagram import (
    parse_instagram_url,
    resolve_instagram_url,
)
from transcriber.url_resolver import InputType, detect_input_type


class TestParseInstagramUrl:
    def test_reel_url(self):
        url = "https://www.instagram.com/reel/DV_ZwfgDpvK/"
        assert parse_instagram_url(url) == "DV_ZwfgDpvK"

    def test_reels_url(self):
        url = "https://www.instagram.com/reels/DV_ZwfgDpvK/"
        assert parse_instagram_url(url) == "DV_ZwfgDpvK"

    def test_post_url(self):
        url = "https://www.instagram.com/p/ABC123_def/"
        assert parse_instagram_url(url) == "ABC123_def"

    def test_with_query_params(self):
        url = "https://www.instagram.com/reel/DV_ZwfgDpvK/?igsh=abc123"
        assert parse_instagram_url(url) == "DV_ZwfgDpvK"

    def test_invalid_url(self):
        assert parse_instagram_url("https://instagram.com/stories/user/123") is None

    def test_not_instagram(self):
        assert parse_instagram_url("https://example.com/reel/123") is None


class TestDetectInputType:
    def test_reel_url(self):
        url = "https://www.instagram.com/reel/DV_ZwfgDpvK/"
        assert detect_input_type(url) == InputType.INSTAGRAM_URL

    def test_reels_url(self):
        url = "https://www.instagram.com/reels/DV_ZwfgDpvK/"
        assert detect_input_type(url) == InputType.INSTAGRAM_URL

    def test_post_url(self):
        url = "https://www.instagram.com/p/ABC123/"
        assert detect_input_type(url) == InputType.INSTAGRAM_URL


class TestResolveInstagramUrl:
    @patch("transcriber.instagram.get_instagram_metadata")
    def test_success(self, mock_meta):
        mock_meta.return_value = ("Cooking video", "chefname")
        result = resolve_instagram_url(
            "https://www.instagram.com/reel/ABC123/"
        )
        assert result.input_type == InputType.INSTAGRAM_URL
        assert result.episode_id == "ABC123"
        assert result.episode_title == "Cooking video"
        assert result.podcast_title == "chefname"

    def test_invalid_url(self):
        result = resolve_instagram_url("https://example.com/not-instagram")
        assert result.input_type == InputType.INSTAGRAM_URL
        assert result.episode_id is None
