"""Tests for LightRAG knowledge store — insert and query with mocked LightRAG."""
from unittest.mock import MagicMock, patch


def test_insert_headlines_calls_rag_insert():
    # Patch the thread-worker function so lightrag doesn't need to be installed
    with patch("knowledge.lightrag_store._insert_in_thread") as mock_worker:
        from knowledge.lightrag_store import insert_headlines
        insert_headlines(["Gold rises on Fed news", "Central banks buy gold"])

    mock_worker.assert_called_once_with(["Gold rises on Fed news", "Central banks buy gold"])


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
    expected = "Gold inversely correlates with DXY index."
    # Patch the thread-worker function so lightrag doesn't need to be installed
    with patch("knowledge.lightrag_store._query_in_thread", return_value=expected):
        from knowledge.lightrag_store import query_gold_context
        result = query_gold_context("What drives gold prices?")

    assert isinstance(result, str)
    assert result == expected


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
