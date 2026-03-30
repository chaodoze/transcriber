"""Tests for Overcast URL resolution module."""

from unittest.mock import MagicMock, patch

from transcriber.overcast import (
    extract_audio_url,
    extract_episode_metadata,
    fetch_overcast_page,
    resolve_overcast_url,
)
from transcriber.url_resolver import InputType

# --- extract_episode_metadata tests (pure) ---


class TestExtractEpisodeMetadata:
    def test_title_with_mdash(self):
        html = "<title>Great Episode \u2014 Best Podcast \u2014 Overcast</title>"
        episode, podcast = extract_episode_metadata(html)
        assert episode == "Great Episode"
        assert podcast == "Best Podcast"

    def test_title_with_dash(self):
        html = "<title>Great Episode - Best Podcast</title>"
        episode, podcast = extract_episode_metadata(html)
        assert episode == "Great Episode"
        assert podcast == "Best Podcast"

    def test_title_with_pipe(self):
        html = "<title>Great Episode | Best Podcast</title>"
        episode, podcast = extract_episode_metadata(html)
        assert episode == "Great Episode"
        assert podcast == "Best Podcast"

    def test_og_title_fallback(self):
        html = """
        <html><head>
        <meta property="og:title" content="Episode Title \u2014 Podcast Name">
        </head></html>
        """
        episode, podcast = extract_episode_metadata(html)
        assert episode == "Episode Title"
        assert podcast == "Podcast Name"

    def test_og_site_name(self):
        html = """
        <html><head>
        <meta property="og:title" content="Episode Title">
        <meta property="og:site_name" content="Podcast Name">
        </head></html>
        """
        episode, podcast = extract_episode_metadata(html)
        assert episode == "Episode Title"
        assert podcast == "Podcast Name"

    def test_html_entities(self):
        html = "<title>Episode &amp; More &mdash; Podcast &mdash; Overcast</title>"
        episode, podcast = extract_episode_metadata(html)
        assert episode == "Episode & More"
        assert podcast == "Podcast"

    def test_no_title(self):
        html = "<html><body>No useful metadata here</body></html>"
        episode, podcast = extract_episode_metadata(html)
        assert episode is None
        assert podcast is None


# --- extract_audio_url tests (pure) ---


class TestExtractAudioUrl:
    def test_source_tag(self):
        html = '<audio><source src="https://cdn.example.com/ep.mp3" type="audio/mpeg"></audio>'
        assert extract_audio_url(html) == "https://cdn.example.com/ep.mp3"

    def test_audio_tag(self):
        html = '<audio src="https://cdn.example.com/ep.mp3" controls></audio>'
        assert extract_audio_url(html) == "https://cdn.example.com/ep.mp3"

    def test_strips_fragment(self):
        html = '<source src="https://cdn.example.com/ep.mp3#t=120">'
        assert extract_audio_url(html) == "https://cdn.example.com/ep.mp3"

    def test_not_found(self):
        html = "<html><body>No audio here</body></html>"
        assert extract_audio_url(html) is None


# --- fetch_overcast_page tests ---


class TestFetchOvercastPage:
    @patch("transcriber.overcast.urlopen")
    def test_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b"<html>page content</html>"
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = fetch_overcast_page("https://overcast.fm/+abc123")
        assert result == "<html>page content</html>"

    @patch("transcriber.overcast.urlopen")
    def test_url_error(self, mock_urlopen):
        from urllib.error import URLError

        mock_urlopen.side_effect = URLError("Connection refused")
        result = fetch_overcast_page("https://overcast.fm/+abc123")
        assert result is None

    @patch("transcriber.overcast.urlopen")
    def test_timeout(self, mock_urlopen):
        mock_urlopen.side_effect = TimeoutError("Timed out")
        result = fetch_overcast_page("https://overcast.fm/+abc123")
        assert result is None


# --- resolve_overcast_url tests ---


class TestResolveOvercastUrl:
    @patch("transcriber.apple_podcasts.get_or_fetch_ttml_path")
    @patch("transcriber.overcast.search_episode_by_title")
    @patch("transcriber.overcast.extract_episode_metadata")
    @patch("transcriber.overcast.fetch_overcast_page")
    @patch("transcriber.overcast.parse_overcast_url")
    def test_full_pipeline_with_transcript(
        self, mock_parse, mock_fetch, mock_metadata,
        mock_search, mock_ttml
    ):
        mock_parse.return_value = "abc123"
        mock_fetch.return_value = "<html>page</html>"
        mock_metadata.return_value = ("Episode Title", "Podcast Name")

        mock_episode = MagicMock()
        mock_episode.audio_url = "https://apple.com/audio.mp3"
        mock_episode.store_track_id = 12345
        mock_search.return_value = mock_episode
        mock_ttml.return_value = "/path/to/transcript.ttml"

        result = resolve_overcast_url("https://overcast.fm/+abc123")
        assert result.input_type == InputType.OVERCAST_URL
        assert result.transcript_path == "/path/to/transcript.ttml"
        assert result.episode_title == "Episode Title"
        assert result.podcast_title == "Podcast Name"

    @patch("transcriber.overcast.fetch_overcast_page")
    @patch("transcriber.overcast.parse_overcast_url")
    def test_page_fetch_fails(self, mock_parse, mock_fetch):
        mock_parse.return_value = "abc123"
        mock_fetch.return_value = None

        result = resolve_overcast_url("https://overcast.fm/+abc123")
        assert result.input_type == InputType.OVERCAST_URL
        assert result.episode_id == "abc123"
        assert result.transcript_path is None

    @patch("transcriber.transcript_fetcher.fetch_transcript")
    @patch("transcriber.itunes_api.find_episode_by_title")
    @patch("transcriber.apple_podcasts.get_or_fetch_ttml_path")
    @patch("transcriber.overcast.search_episode_by_title")
    @patch("transcriber.overcast.extract_episode_metadata")
    @patch("transcriber.overcast.fetch_overcast_page")
    @patch("transcriber.overcast.parse_overcast_url")
    def test_itunes_fallback(
        self, mock_parse, mock_fetch, mock_metadata,
        mock_search, mock_ttml, mock_itunes_find, mock_fetch_transcript
    ):
        mock_parse.return_value = "abc123"
        mock_fetch.return_value = "<html>page</html>"
        mock_metadata.return_value = ("Episode Title", "Podcast Name")

        # Apple search returns episode but no transcript
        mock_episode = MagicMock()
        mock_episode.audio_url = None
        mock_episode.store_track_id = None
        mock_search.return_value = mock_episode
        mock_ttml.return_value = None  # No cached transcript

        # iTunes API finds it
        mock_itunes_episode = MagicMock()
        mock_itunes_episode.track_id = 99999
        mock_itunes_episode.audio_url = "https://itunes.com/audio.mp3"
        mock_itunes_find.return_value = mock_itunes_episode
        mock_fetch_transcript.return_value = "/path/to/fetched.ttml"

        result = resolve_overcast_url("https://overcast.fm/+abc123")
        assert result.transcript_path == "/path/to/fetched.ttml"
        assert result.audio_url == "https://itunes.com/audio.mp3"

    @patch("transcriber.apple_podcasts.get_or_fetch_ttml_path")
    @patch("transcriber.overcast.search_episode_by_title")
    @patch("transcriber.overcast.extract_episode_metadata")
    @patch("transcriber.overcast.fetch_overcast_page")
    @patch("transcriber.overcast.parse_overcast_url")
    def test_prefers_apple_audio(
        self, mock_parse, mock_fetch, mock_metadata,
        mock_search, mock_ttml
    ):
        mock_parse.return_value = "abc123"
        mock_fetch.return_value = "<html>page</html>"
        mock_metadata.return_value = ("Episode", "Podcast")

        mock_episode = MagicMock()
        mock_episode.audio_url = "https://apple.com/audio.mp3"
        mock_episode.store_track_id = 12345
        mock_search.return_value = mock_episode
        mock_ttml.return_value = None

        result = resolve_overcast_url("https://overcast.fm/+abc123")
        assert result.audio_url == "https://apple.com/audio.mp3"

    @patch("transcriber.transcript_fetcher.fetch_transcript")
    @patch("transcriber.itunes_api.find_episode_by_title")
    @patch("transcriber.apple_podcasts.get_or_fetch_ttml_path")
    @patch("transcriber.overcast.search_episode_by_title")
    @patch("transcriber.overcast.extract_episode_metadata")
    @patch("transcriber.overcast.fetch_overcast_page")
    @patch("transcriber.overcast.parse_overcast_url")
    def test_no_audio_when_all_strategies_fail(
        self, mock_parse, mock_fetch, mock_metadata,
        mock_search, mock_ttml, mock_itunes_find, mock_fetch_transcript
    ):
        mock_parse.return_value = "abc123"
        mock_fetch.return_value = "<html>page</html>"
        mock_metadata.return_value = ("Episode", "Podcast")

        mock_episode = MagicMock()
        mock_episode.audio_url = None  # No Apple audio
        mock_episode.store_track_id = 12345
        mock_search.return_value = mock_episode
        mock_ttml.return_value = None
        mock_itunes_find.return_value = None  # iTunes also finds nothing

        result = resolve_overcast_url("https://overcast.fm/+abc123")
        assert result.audio_url is None
