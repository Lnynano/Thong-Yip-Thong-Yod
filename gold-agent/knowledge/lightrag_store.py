"""
knowledge/lightrag_store.py
LightRAG-backed knowledge store for gold market context.

Accumulates real news headlines over time and seeds static gold market
domain knowledge on first run. Exposes two functions used by the
agent's get_news tool handler.

All LightRAG calls run in a single-threaded executor to avoid conflicts
with Gradio's asyncio event loop (LightRAG uses loop.run_until_complete
internally, which raises RuntimeError if called from within a running loop).

Models:
  LLM        : claude-haiku-4-5-20251001 (entity/relation extraction)
  Embeddings : all-MiniLM-L6-v2 via sentence-transformers (384-dim, local)

Storage: data/lightrag/ (persisted alongside portfolio.json)
"""

import concurrent.futures
import hashlib
import os
from datetime import datetime

WORKING_DIR   = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "lightrag"))
SEED_FILE     = os.path.join(os.path.dirname(__file__), "gold_knowledge.txt")
SEED_SENTINEL = os.path.join(WORKING_DIR, ".seeded")

_rag              = None
_st_model         = None
_anthropic_client = None
# Single-threaded executor: all LightRAG ops run here, never in Gradio's loop
_executor         = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="lightrag")

# ── Dedup guard: skip insert if exact same headlines were inserted before ──
# Saves ~5-10 Haiku calls per duplicate insert (LightRAG entity extraction)
_last_inserted_hash: str | None = None


def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic
        _anthropic_client = anthropic.Anthropic()
    return _anthropic_client


def _get_st_model():
    global _st_model
    if _st_model is None:
        from sentence_transformers import SentenceTransformer
        _st_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _st_model


async def _llm_func(prompt, system_prompt=None, history_messages=None, **kwargs) -> str:
    # history_messages is provided by LightRAG for multi-turn extraction but not forwarded
    client = _get_anthropic_client()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        temperature=0,
        system=system_prompt or "You are a helpful knowledge extraction assistant.",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


async def _embed_func(texts: list[str]) -> list[list[float]]:
    model = _get_st_model()
    return model.encode(texts, convert_to_numpy=True).tolist()


def _get_rag():
    global _rag
    if _rag is not None:
        return _rag

    from lightrag import LightRAG
    from lightrag.utils import EmbeddingFunc

    os.makedirs(WORKING_DIR, exist_ok=True)

    _rag = LightRAG(
        working_dir=WORKING_DIR,
        llm_model_func=_llm_func,
        embedding_func=EmbeddingFunc(
            embedding_dim=384,
            max_token_size=8192,
            func=_embed_func,
        ),
    )

    if not os.path.exists(SEED_SENTINEL):
        _seed(_rag)

    return _rag


def _seed(rag) -> None:
    """Insert static domain knowledge on first run and write sentinel."""
    try:
        with open(SEED_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if content:
            rag.insert(content)
            with open(SEED_SENTINEL, "w", encoding="utf-8") as f:
                f.write(datetime.now().isoformat())
            print("[lightrag_store.py] Knowledge base seeded with gold market domain knowledge.")
    except Exception as e:
        print(f"[lightrag_store.py] Seeding failed: {e}")


def _insert_in_thread(headlines: list[str]) -> None:
    rag = _get_rag()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    text = (
        f"[{timestamp}] Gold market news headlines:\n"
        + "\n".join(f"- {h}" for h in headlines)
    )
    rag.insert(text)


def _query_in_thread(question: str) -> str:
    from lightrag import QueryParam
    rag = _get_rag()
    result = rag.query(question, param=QueryParam(mode="hybrid"))
    return result or ""


def insert_headlines(headlines: list[str]) -> None:
    """
    Append news headlines to the knowledge graph.

    Skips insert if the exact same headlines were already inserted this session
    (dedup by MD5 hash) — saves 5-10 Haiku API calls per skipped insert.

    Runs in a background thread to avoid conflicts with Gradio's event loop.
    Silent on any failure.

    Args:
        headlines: List of headline strings from get_gold_news().
    """
    global _last_inserted_hash
    if not headlines:
        return

    # Hash check — skip if identical to last insert
    current_hash = hashlib.md5("|".join(headlines).encode()).hexdigest()
    if current_hash == _last_inserted_hash:
        print("[lightrag_store.py] Headlines unchanged → skipping insert (saved Haiku calls)")
        return

    try:
        future = _executor.submit(_insert_in_thread, headlines)
        future.result(timeout=60)
        _last_inserted_hash = current_hash
    except Exception as e:
        print(f"[lightrag_store.py] Insert failed: {e}")


def query_gold_context(question: str) -> str:
    """
    Query the knowledge graph for relevant historical and domain context.

    Runs in a background thread to avoid conflicts with Gradio's event loop.
    Returns empty string on any failure for graceful degradation.

    Args:
        question: Natural language question to query the knowledge graph.

    Returns:
        str: Relevant context text, or "" on failure.
    """
    try:
        future = _executor.submit(_query_in_thread, question)
        return future.result(timeout=60)
    except Exception as e:
        print(f"[lightrag_store.py] Query failed: {e}")
        return ""
