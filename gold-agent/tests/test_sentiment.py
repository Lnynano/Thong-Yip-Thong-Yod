"""Tests for GPT-powered sentiment scoring with keyword fallback."""
from unittest.mock import MagicMock, patch


def test_agent_returns_bullish():
    mock_choice = MagicMock()
    mock_choice.message.content = '{"sentiment": "BULLISH", "reasoning": "positive headlines"}'
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}), \
         patch("news.sentiment.OpenAI") as mock_openai:
        mock_openai.return_value.chat.completions.create.return_value = mock_response
        from news.sentiment import get_sentiment_summary
        result = get_sentiment_summary(["Gold surges to record high"])

    assert result == "BULLISH"


def test_agent_returns_bearish():
    mock_choice = MagicMock()
    mock_choice.message.content = '{"sentiment": "BEARISH", "reasoning": "negative headlines"}'
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}), \
         patch("news.sentiment.OpenAI") as mock_openai:
        mock_openai.return_value.chat.completions.create.return_value = mock_response
        from news.sentiment import get_sentiment_summary
        result = get_sentiment_summary(["Gold prices fall sharply"])

    assert result == "BEARISH"


def test_fallback_on_api_exception():
    with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}), \
         patch("news.sentiment.OpenAI") as mock_openai:
        mock_openai.side_effect = Exception("API down")
        from news.sentiment import get_sentiment_summary
        # "surge" is a bullish keyword — fallback should catch it
        result = get_sentiment_summary(["Gold prices surge"])

    assert result == "BULLISH"


def test_fallback_on_bad_json():
    mock_choice = MagicMock()
    mock_choice.message.content = "not valid json"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}), \
         patch("news.sentiment.OpenAI") as mock_openai:
        mock_openai.return_value.chat.completions.create.return_value = mock_response
        from news.sentiment import get_sentiment_summary
        # "fall" is a bearish keyword
        result = get_sentiment_summary(["Gold prices fall"])

    assert result == "BEARISH"


def test_skips_agent_when_no_api_key():
    with patch.dict("os.environ", {"OPENAI_API_KEY": ""}), \
         patch("news.sentiment.OpenAI") as mock_openai:
        from news.sentiment import get_sentiment_summary
        result = get_sentiment_summary(["Gold prices surge amid demand"])
        # Should never call the API
        mock_openai.assert_not_called()

    assert result == "BULLISH"
