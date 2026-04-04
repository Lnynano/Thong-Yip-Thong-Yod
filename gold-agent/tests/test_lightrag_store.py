"""Tests for LightRAG knowledge store — insert and query with mocked LightRAG."""
from unittest.mock import MagicMock, patch


def test_insert_headlines_calls_rag_insert():
    mock_rag = MagicMock()
    with patch("knowledge.lightrag_store._get_rag", return_value=mock_rag):
        from knowledge.lightrag_store import insert_headlines
        insert_headlines(["Gold rises on Fed news", "Central banks buy gold"])

    mock_rag.insert.assert_called_once()
    inserted_text = mock_rag.insert.call_args[0][0]
    assert "Gold rises on Fed news" in inserted_text
    assert "Central banks buy gold" in inserted_text


def test_insert_headlines_skips_empty_list():
    mock_rag = MagicMock()
    with patch("knowledge.lightrag_store._get_rag", return_value=mock_rag):
        from knowledge.lightrag_store import insert_headlines
        insert_headlines([])

    mock_rag.insert.assert_not_called()


def test_insert_headlines_silent_on_failure():
    mock_rag = MagicMock()
    mock_rag.insert.side_effect = Exception("LightRAG write error")
    with patch("knowledge.lightrag_store._get_rag", return_value=mock_rag):
        from knowledge.lightrag_store import insert_headlines
        # Must not raise
        insert_headlines(["Gold headline"])


def test_query_gold_context_returns_string():
    mock_rag = MagicMock()
    mock_rag.query.return_value = "Gold inversely correlates with DXY index."
    with patch("knowledge.lightrag_store._get_rag", return_value=mock_rag):
        from knowledge.lightrag_store import query_gold_context
        result = query_gold_context("What drives gold prices?")

    assert isinstance(result, str)
    assert result == "Gold inversely correlates with DXY index."


def test_query_gold_context_returns_empty_string_on_failure():
    mock_rag = MagicMock()
    mock_rag.query.side_effect = Exception("LightRAG read error")
    with patch("knowledge.lightrag_store._get_rag", return_value=mock_rag):
        from knowledge.lightrag_store import query_gold_context
        result = query_gold_context("What drives gold prices?")

    assert result == ""


def test_query_gold_context_returns_empty_string_on_none_result():
    mock_rag = MagicMock()
    mock_rag.query.return_value = None
    with patch("knowledge.lightrag_store._get_rag", return_value=mock_rag):
        from knowledge.lightrag_store import query_gold_context
        result = query_gold_context("What drives gold prices?")

    assert result == ""
