"""Tests for URL resolution module."""


from src.transcriber.url_resolver import (
    InputType,
    detect_input_type,
    parse_apple_url,
    parse_overcast_url,
    parse_youtube_url,
)


class TestDetectInputType:
    """Tests for detect_input_type function."""

    def test_apple_podcasts_url(self):
        url = "https://podcasts.apple.com/us/podcast/the-daily/id1200361736?i=1000123456789"
        assert detect_input_type(url) == InputType.APPLE_PODCASTS_URL

    def test_apple_podcasts_url_no_episode(self):
        url = "https://podcasts.apple.com/us/podcast/the-daily/id1200361736"
        assert detect_input_type(url) == InputType.APPLE_PODCASTS_URL

    def test_apple_podcasts_url_different_country(self):
        url = "https://podcasts.apple.com/gb/podcast/some-show/id999888777?i=1000111222333"
        assert detect_input_type(url) == InputType.APPLE_PODCASTS_URL

    def test_overcast_url(self):
        url = "https://overcast.fm/+ABC123xyz"
        assert detect_input_type(url) == InputType.OVERCAST_URL

    def test_overcast_url_with_underscore(self):
        url = "https://overcast.fm/+ABC_123-xyz"
        assert detect_input_type(url) == InputType.OVERCAST_URL

    def test_local_file_path_absolute(self):
        path = "/Users/test/audio/podcast.mp3"
        assert detect_input_type(path) == InputType.FILE_PATH

    def test_local_file_path_home(self):
        path = "~/Downloads/episode.m4a"
        assert detect_input_type(path) == InputType.FILE_PATH

    def test_local_file_path_relative(self):
        path = "./audio/test.wav"
        assert detect_input_type(path) == InputType.FILE_PATH

    def test_youtube_url(self):
        url = "https://www.youtube.com/watch?v=B0hy-RcvNhc"
        assert detect_input_type(url) == InputType.YOUTUBE_URL

    def test_youtube_short_url(self):
        url = "https://youtu.be/B0hy-RcvNhc"
        assert detect_input_type(url) == InputType.YOUTUBE_URL

    def test_youtube_embed_url(self):
        url = "https://www.youtube.com/embed/B0hy-RcvNhc"
        assert detect_input_type(url) == InputType.YOUTUBE_URL

    def test_youtube_url_with_params(self):
        url = "https://www.youtube.com/watch?v=B0hy-RcvNhc&t=120"
        assert detect_input_type(url) == InputType.YOUTUBE_URL

    def test_strips_whitespace(self):
        url = "  https://overcast.fm/+ABC123  "
        assert detect_input_type(url) == InputType.OVERCAST_URL


class TestParseAppleUrl:
    """Tests for parse_apple_url function."""

    def test_full_url_with_episode(self):
        url = "https://podcasts.apple.com/us/podcast/the-daily/id1200361736?i=1000123456789"
        podcast_id, episode_id, show_slug = parse_apple_url(url)
        assert podcast_id == "1200361736"
        assert episode_id == "1000123456789"
        assert show_slug == "the-daily"

    def test_url_without_episode(self):
        url = "https://podcasts.apple.com/us/podcast/the-daily/id1200361736"
        podcast_id, episode_id, show_slug = parse_apple_url(url)
        assert podcast_id == "1200361736"
        assert episode_id is None
        assert show_slug == "the-daily"

    def test_invalid_url(self):
        url = "https://example.com/not-a-podcast"
        podcast_id, episode_id, show_slug = parse_apple_url(url)
        assert podcast_id is None
        assert episode_id is None
        assert show_slug is None


class TestParseOvercastUrl:
    """Tests for parse_overcast_url function."""

    def test_valid_url(self):
        url = "https://overcast.fm/+ABC123xyz"
        episode_id = parse_overcast_url(url)
        assert episode_id == "ABC123xyz"

    def test_url_with_special_chars(self):
        url = "https://overcast.fm/+ABC_123-xyz"
        episode_id = parse_overcast_url(url)
        assert episode_id == "ABC_123-xyz"

    def test_invalid_url(self):
        url = "https://example.com/not-overcast"
        episode_id = parse_overcast_url(url)
        assert episode_id is None


class TestParseYoutubeUrl:
    """Tests for parse_youtube_url function."""

    def test_standard_url(self):
        url = "https://www.youtube.com/watch?v=B0hy-RcvNhc"
        assert parse_youtube_url(url) == "B0hy-RcvNhc"

    def test_short_url(self):
        url = "https://youtu.be/B0hy-RcvNhc"
        assert parse_youtube_url(url) == "B0hy-RcvNhc"

    def test_embed_url(self):
        url = "https://www.youtube.com/embed/B0hy-RcvNhc"
        assert parse_youtube_url(url) == "B0hy-RcvNhc"

    def test_url_with_extra_params(self):
        url = "https://www.youtube.com/watch?v=B0hy-RcvNhc&t=120&list=PLxyz"
        assert parse_youtube_url(url) == "B0hy-RcvNhc"

    def test_invalid_url(self):
        url = "https://example.com/not-youtube"
        assert parse_youtube_url(url) is None
