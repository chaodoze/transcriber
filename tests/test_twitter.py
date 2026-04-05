"""Tests for Twitter/X API v2 service module."""

import json
import os
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from transcriber.twitter import (
    _bearer_request,
    _get_bearer_token,
    _parse_tweet,
    get_tweet,
    get_user_tweets,
    parse_tweet_url,
    search_tweets,
)

# --- parse_tweet_url tests ---


class TestParseTweetUrl:
    def test_numeric_id(self):
        assert parse_tweet_url("1234567890") == "1234567890"

    def test_x_url(self):
        assert parse_tweet_url("https://x.com/user/status/1234567890") == "1234567890"

    def test_twitter_url(self):
        url = "https://twitter.com/testuser/status/9876543210"
        assert parse_tweet_url(url) == "9876543210"

    def test_whitespace_stripped(self):
        assert parse_tweet_url("  1234567890  ") == "1234567890"

    def test_url_with_query_params(self):
        url = "https://x.com/user/status/1234567890?s=20&t=abc"
        assert parse_tweet_url(url) == "1234567890"

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="Could not parse tweet ID"):
            parse_tweet_url("not-a-tweet-url")

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            parse_tweet_url("https://example.com")


# --- _get_bearer_token tests ---


class TestGetBearerToken:
    def test_token_present(self):
        with patch.dict(os.environ, {"TWITTER_BEARER_TOKEN": "test_token_123"}):
            assert _get_bearer_token() == "test_token_123"

    def test_token_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            # Remove the key if it exists
            os.environ.pop("TWITTER_BEARER_TOKEN", None)
            with pytest.raises(RuntimeError, match="TWITTER_BEARER_TOKEN"):
                _get_bearer_token()


# --- _parse_tweet tests ---


class TestParseTweet:
    def test_basic_no_includes(self):
        data = {"id": "123", "text": "Hello world"}
        tweet = _parse_tweet(data)
        assert tweet.id == "123"
        assert tweet.text == "Hello world"
        assert tweet.author is None

    def test_with_author(self):
        data = {"id": "123", "text": "Hello", "author_id": "999"}
        includes = {"users": [{"id": "999", "username": "testuser", "name": "Test User"}]}
        tweet = _parse_tweet(data, includes)
        assert tweet.author is not None
        assert tweet.author.username == "testuser"
        assert tweet.author.name == "Test User"

    def test_with_metrics(self):
        data = {
            "id": "123",
            "text": "Hello",
            "public_metrics": {
                "retweet_count": 10,
                "like_count": 50,
                "reply_count": 5,
                "impression_count": 1000,
            },
        }
        tweet = _parse_tweet(data)
        assert tweet.retweet_count == 10
        assert tweet.like_count == 50
        assert tweet.reply_count == 5
        assert tweet.impression_count == 1000

    def test_note_tweet_preferred(self):
        """note_tweet.text should be used over truncated text."""
        data = {
            "id": "123",
            "text": "Truncated...",
            "note_tweet": {"text": "Full long-form tweet text that was truncated"},
        }
        tweet = _parse_tweet(data)
        assert tweet.text == "Full long-form tweet text that was truncated"

    def test_note_tweet_empty_dict(self):
        """Empty note_tweet dict should fall back to regular text."""
        data = {"id": "123", "text": "Regular text", "note_tweet": {}}
        tweet = _parse_tweet(data)
        assert tweet.text == "Regular text"

    def test_url_with_author(self):
        data = {"id": "123", "text": "Hello", "author_id": "999"}
        includes = {"users": [{"id": "999", "username": "alice", "name": "Alice"}]}
        tweet = _parse_tweet(data, includes)
        assert tweet.url == "https://x.com/alice/status/123"

    def test_url_without_author(self):
        data = {"id": "123", "text": "Hello"}
        tweet = _parse_tweet(data)
        assert tweet.url == "https://x.com/unknown/status/123"

    def test_author_not_in_includes(self):
        data = {"id": "123", "text": "Hello", "author_id": "999"}
        includes = {"users": [{"id": "888", "username": "other", "name": "Other"}]}
        tweet = _parse_tweet(data, includes)
        assert tweet.author is None
        assert tweet.url == "https://x.com/unknown/status/123"

    def test_image_urls(self):
        data = {"id": "123", "text": "Check this out", "attachments": {"media_keys": ["m1"]}}
        includes = {"media": [{"media_key": "m1", "type": "photo", "url": "https://pbs.twimg.com/media/img.jpg"}]}
        tweet = _parse_tweet(data, includes)
        assert tweet.image_urls == ["https://pbs.twimg.com/media/img.jpg"]
        assert tweet.video_urls == []

    def test_video_urls(self):
        data = {"id": "123", "text": "Watch this", "attachments": {"media_keys": ["m1"]}}
        includes = {"media": [{
            "media_key": "m1",
            "type": "video",
            "preview_image_url": "https://pbs.twimg.com/thumb.jpg",
            "variants": [
                {"content_type": "application/x-mpegURL", "url": "https://video.twimg.com/v.m3u8"},
                {"bit_rate": 256000, "content_type": "video/mp4", "url": "https://video.twimg.com/low.mp4"},
                {"bit_rate": 2176000, "content_type": "video/mp4", "url": "https://video.twimg.com/high.mp4"},
            ],
        }]}
        tweet = _parse_tweet(data, includes)
        assert tweet.video_urls == ["https://video.twimg.com/high.mp4"]
        assert tweet.image_urls == []

    def test_no_media(self):
        data = {"id": "123", "text": "Just text"}
        tweet = _parse_tweet(data)
        assert tweet.image_urls == []
        assert tweet.video_urls == []

    def test_media_key_missing_from_includes(self):
        data = {"id": "123", "text": "Missing", "attachments": {"media_keys": ["m_gone"]}}
        includes = {"media": [{"media_key": "m_other", "type": "photo", "url": "https://x.com/img.jpg"}]}
        tweet = _parse_tweet(data, includes)
        assert tweet.image_urls == []
        assert tweet.video_urls == []


# --- _bearer_request tests ---


class TestBearerRequest:
    @patch("transcriber.twitter._get_bearer_token", return_value="test_token")
    @patch("transcriber.twitter.urlopen")
    def test_success(self, mock_urlopen, mock_token):
        response_data = {"data": {"id": "123"}}
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(response_data).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = _bearer_request("tweets/123")
        assert result == response_data

    @patch("transcriber.twitter._get_bearer_token", return_value="test_token")
    @patch("transcriber.twitter.urlopen")
    def test_with_params(self, mock_urlopen, mock_token):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"data": {}}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        _bearer_request("tweets/123", {"tweet.fields": "created_at"})

        called_req = mock_urlopen.call_args[0][0]
        assert "tweet.fields=created_at" in called_req.full_url

    @patch("transcriber.twitter._get_bearer_token", return_value="test_token")
    @patch("transcriber.twitter.urlopen")
    def test_http_error(self, mock_urlopen, mock_token):
        from urllib.error import HTTPError

        error = HTTPError(
            url="https://api.twitter.com/2/tweets/123",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=BytesIO(b'{"errors": [{"detail": "Not found"}]}'),
        )
        mock_urlopen.side_effect = error

        with pytest.raises(RuntimeError, match="Twitter API error 404"):
            _bearer_request("tweets/123")

    @patch("transcriber.twitter._get_bearer_token", return_value="test_token")
    @patch("transcriber.twitter.urlopen")
    def test_timeout(self, mock_urlopen, mock_token):
        mock_urlopen.side_effect = TimeoutError("Connection timed out")

        with pytest.raises(RuntimeError, match="Twitter API request failed"):
            _bearer_request("tweets/123")

    @patch("transcriber.twitter._get_bearer_token", return_value="test_token")
    @patch("transcriber.twitter.urlopen")
    def test_url_error(self, mock_urlopen, mock_token):
        from urllib.error import URLError

        mock_urlopen.side_effect = URLError("Connection refused")

        with pytest.raises(RuntimeError, match="Twitter API request failed"):
            _bearer_request("tweets/123")


# --- get_tweet tests ---


class TestGetTweet:
    @patch("transcriber.twitter._bearer_request")
    def test_success(self, mock_request, sample_tweet_api_response):
        mock_request.return_value = sample_tweet_api_response
        result = get_tweet("1234567890")
        assert result.tweet.id == "1234567890"
        assert result.tweet.text == "Hello world from Twitter!"
        assert result.tweet.author.username == "testuser"

    @patch("transcriber.twitter._bearer_request")
    def test_with_url(self, mock_request, sample_tweet_api_response):
        mock_request.return_value = sample_tweet_api_response
        get_tweet("https://x.com/user/status/1234567890")
        mock_request.assert_called_once()
        assert "tweets/1234567890" in mock_request.call_args[0][0]

    @patch("transcriber.twitter._bearer_request")
    def test_not_found(self, mock_request):
        mock_request.return_value = {
            "errors": [{"detail": "Tweet not found"}]
        }
        with pytest.raises(RuntimeError, match="Tweet not found"):
            get_tweet("9999999999")

    @patch("transcriber.twitter._bearer_request")
    def test_not_found_no_errors(self, mock_request):
        mock_request.return_value = {}
        with pytest.raises(RuntimeError, match="Tweet not found"):
            get_tweet("9999999999")


# --- search_tweets tests ---


class TestSearchTweets:
    @patch("transcriber.twitter._bearer_request")
    def test_success(self, mock_request, sample_tweet_search_response):
        mock_request.return_value = sample_tweet_search_response
        result = search_tweets("test query")
        assert result.result_count == 2
        assert len(result.tweets) == 2
        assert result.newest_id == "222"
        assert result.oldest_id == "111"

    @patch("transcriber.twitter._bearer_request")
    def test_clamps_min(self, mock_request, sample_tweet_search_response):
        mock_request.return_value = sample_tweet_search_response
        search_tweets("test", max_results=3)
        params = mock_request.call_args[0][1]
        assert params["max_results"] == 10

    @patch("transcriber.twitter._bearer_request")
    def test_clamps_max(self, mock_request, sample_tweet_search_response):
        mock_request.return_value = sample_tweet_search_response
        search_tweets("test", max_results=500)
        params = mock_request.call_args[0][1]
        assert params["max_results"] == 100

    @patch("transcriber.twitter._bearer_request")
    def test_empty_results(self, mock_request):
        mock_request.return_value = {"meta": {"result_count": 0}}
        result = search_tweets("no results query")
        assert len(result.tweets) == 0
        assert result.result_count == 0


# --- get_user_tweets tests ---


class TestGetUserTweets:
    @patch("transcriber.twitter._bearer_request")
    def test_success(self, mock_request, sample_user_lookup_response, sample_tweet_search_response):
        mock_request.side_effect = [sample_user_lookup_response, sample_tweet_search_response]
        result = get_user_tweets("testuser")
        assert len(result.tweets) == 2
        assert mock_request.call_count == 2

    @patch("transcriber.twitter._bearer_request")
    def test_strips_at_sign(self, mock_request, sample_user_lookup_response,
                            sample_tweet_search_response):
        mock_request.side_effect = [sample_user_lookup_response, sample_tweet_search_response]
        get_user_tweets("@testuser")
        first_call_endpoint = mock_request.call_args_list[0][0][0]
        assert first_call_endpoint == "users/by/username/testuser"

    @patch("transcriber.twitter._bearer_request")
    def test_user_not_found(self, mock_request):
        mock_request.return_value = {
            "errors": [{"detail": "User @nonexistent not found"}]
        }
        with pytest.raises(RuntimeError, match="not found"):
            get_user_tweets("nonexistent")

    @patch("transcriber.twitter._bearer_request")
    def test_clamps_min(self, mock_request, sample_user_lookup_response,
                        sample_tweet_search_response):
        mock_request.side_effect = [sample_user_lookup_response, sample_tweet_search_response]
        get_user_tweets("testuser", max_results=2)
        second_call_params = mock_request.call_args_list[1][0][1]
        assert second_call_params["max_results"] == 5

    @patch("transcriber.twitter._bearer_request")
    def test_includes_fallback(self, mock_request, sample_user_lookup_response):
        """When tweet response lacks includes.users, uses user_data from lookup."""
        tweets_response = {
            "data": [
                {"id": "111", "text": "Hello", "author_id": "999",
                 "public_metrics": {}},
            ],
            "meta": {"result_count": 1},
        }
        mock_request.side_effect = [sample_user_lookup_response, tweets_response]
        result = get_user_tweets("testuser")
        assert result.tweets[0].author.username == "testuser"
