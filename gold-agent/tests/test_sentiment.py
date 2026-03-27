"""Tests for Claude-powered sentiment scoring with keyword fallback."""
from unittest.mock import MagicMock, patch


def test_claude_returns_bullish():
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text='{"sentiment": "BULLISH", "reasoning": "positive headlines"}')]

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}), \
         patch("news.sentiment.anthropic") as mock_ant:
        mock_ant.Anthropic.return_value.messages.create.return_value = mock_msg
        from news.sentiment import get_sentiment_summary
        result = get_sentiment_summary(["Gold surges to record high"])

    assert result == "BULLISH"


def test_claude_returns_bearish():
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text='{"sentiment": "BEARISH", "reasoning": "negative headlines"}')]

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}), \
         patch("news.sentiment.anthropic") as mock_ant:
        mock_ant.Anthropic.return_value.messages.create.return_value = mock_msg
        from news.sentiment import get_sentiment_summary
        result = get_sentiment_summary(["Gold prices fall sharply"])

    assert result == "BEARISH"


def test_fallback_on_api_exception():
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}), \
         patch("news.sentiment.anthropic") as mock_ant:
        mock_ant.Anthropic.side_effect = Exception("API down")
        from news.sentiment import get_sentiment_summary
        # "surge" is a bullish keyword — fallback should catch it
        result = get_sentiment_summary(["Gold prices surge"])

    assert result == "BULLISH"


def test_fallback_on_bad_json():
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text="not valid json")]

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}), \
         patch("news.sentiment.anthropic") as mock_ant:
        mock_ant.Anthropic.return_value.messages.create.return_value = mock_msg
        from news.sentiment import get_sentiment_summary
        # "fall" is a bearish keyword
        result = get_sentiment_summary(["Gold prices fall"])

    assert result == "BEARISH"


def test_skips_claude_when_no_api_key():
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}), \
         patch("news.sentiment.anthropic") as mock_ant:
        from news.sentiment import get_sentiment_summary
        result = get_sentiment_summary(["Gold prices surge amid demand"])
        # Should never call Claude
        mock_ant.Anthropic.assert_not_called()

    assert result == "BULLISH"
