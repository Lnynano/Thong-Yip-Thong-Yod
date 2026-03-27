"""Tests for the enhanced get_news tool handler in GoldTradingAgent."""
import json
from unittest.mock import MagicMock, patch


def test_get_news_tool_includes_historical_context():
    with patch("news.sentiment.get_gold_news", return_value=["Gold rises on safe-haven demand"]), \
         patch("news.sentiment.get_sentiment_summary", return_value="BULLISH"), \
         patch("knowledge.lightrag_store.insert_headlines"), \
         patch("knowledge.lightrag_store.query_gold_context",
               return_value="Gold inversely correlates with DXY."):
        from agent.claude_agent import _execute_tool
        raw = _execute_tool("get_news", {"count": 3})

    result = json.loads(raw)
    assert "historical_context" in result
    assert result["historical_context"] == "Gold inversely correlates with DXY."


def test_get_news_tool_omits_historical_context_when_empty():
    with patch("news.sentiment.get_gold_news", return_value=["Gold holds steady"]), \
         patch("news.sentiment.get_sentiment_summary", return_value="NEUTRAL"), \
         patch("knowledge.lightrag_store.insert_headlines"), \
         patch("knowledge.lightrag_store.query_gold_context", return_value=""):
        from agent.claude_agent import _execute_tool
        raw = _execute_tool("get_news", {"count": 3})

    result = json.loads(raw)
    assert "historical_context" not in result


def test_get_news_tool_calls_insert_headlines():
    headlines = ["Gold jumps 2% on inflation data"]

    with patch("news.sentiment.get_gold_news", return_value=headlines), \
         patch("news.sentiment.get_sentiment_summary", return_value="BULLISH"), \
         patch("knowledge.lightrag_store.insert_headlines") as mock_insert, \
         patch("knowledge.lightrag_store.query_gold_context", return_value=""):
        from agent.claude_agent import _execute_tool
        _execute_tool("get_news", {"count": 1})

    mock_insert.assert_called_once_with(headlines)
