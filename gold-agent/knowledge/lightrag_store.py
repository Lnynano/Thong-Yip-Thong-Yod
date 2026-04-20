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
  LLM        : gpt-4o-mini (entity/relation extraction)
  Embeddings : all-MiniLM-L6-v2 via sentence-transformers (384-dim, local)

Storage: data/lightrag/ (persisted alongside portfolio.json)
"""

import asyncio
import concurrent.futures
import hashlib
import os
from datetime import datetime

import numpy as np

WORKING_DIR   = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "lightrag"))
SEED_FILE     = os.path.join(os.path.dirname(__file__), "gold_knowledge.txt")
SEED_SENTINEL = os.path.join(WORKING_DIR, ".seeded")

_rag              = None
_openai_client    = None
# Single-threaded executor: all LightRAG ops run here, never in Gradio's loop
_executor         = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="lightrag")

# ── Persistent event loop for the LightRAG thread ────────────────────────────
# asyncio.run() creates a NEW loop each call — LightRAG's internal worker
# queues get bound to the first loop and break on the second call.
# Fix: create ONE loop and reuse it for every op in the lightrag thread.
_loop: asyncio.AbstractEventLoop | None = None

# ── Dedup guard: skip insert if exact same headlines were inserted before ──
# Saves ~5-10 Haiku calls per duplicate insert (LightRAG entity extraction)
_last_inserted_hash: str | None = None


def _run_async(coro):
    """
    Run an async coroutine on the persistent LightRAG event loop.
    Must only be called from inside _executor (the lightrag thread).
    """
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop.run_until_complete(coro)


def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI()
    return _openai_client



async def _llm_func(prompt, system_prompt=None, history_messages=None, **kwargs) -> str:
    """Sync OpenAI call wrapped as async for LightRAG compatibility."""
    client = _get_openai_client()
    messages = [
        {"role": "system", "content": system_prompt or "You are a helpful knowledge extraction assistant."},
        {"role": "user", "content": prompt},
    ]
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=512,
        temperature=0,
        messages=messages,
    )

    # Track LLM cost
    try:
        from logger.cost_tracker import track_usage
        track_usage(response.usage, source="lightrag")
    except Exception:
        pass

    return response.choices[0].message.content


async def _embed_func(texts: list[str]) -> np.ndarray:
    """
    Return embeddings as a numpy array using OpenAI's text-embedding-3-small API.
    """
    client = _get_openai_client()
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=texts
    )
    
    # Track LLM cost
    try:
        from logger.cost_tracker import track_usage
        track_usage(response.usage, source="lightrag")
    except Exception:
        pass
        
    embeddings = [item.embedding for item in response.data]
    return np.array(embeddings)


def _get_rag():
    """
    Initialise LightRAG exactly once inside the lightrag thread.
    Uses the persistent _loop so LightRAG's internal async workers
    stay bound to the same event loop across all calls.
    """
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
            embedding_dim=1536,
            max_token_size=8192,
            func=_embed_func,
        ),
    )

    # Newer lightrag-hku requires explicit storage initialisation.
    # Run on the persistent loop so workers bind to it permanently.
    try:
        _run_async(_rag.initialize_storages())
        print("[lightrag_store.py] Storages initialised.")
    except Exception as e:
        print(f"[lightrag_store.py] Storage init warning (ok on older versions): {e}")

    if not os.path.exists(SEED_SENTINEL):
        _seed(_rag)

    return _rag


def _seed(rag) -> None:
    """Insert static domain knowledge on first run and write sentinel."""
    try:
        with open(SEED_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if content:
            try:
                _run_async(rag.ainsert(content))
            except AttributeError:
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
    try:
        _run_async(rag.ainsert(text))
    except AttributeError:
        rag.insert(text)


def _query_in_thread(question: str) -> str:
    from lightrag import QueryParam
    rag = _get_rag()
    try:
        result = _run_async(rag.aquery(question, param=QueryParam(mode="hybrid")))
    except AttributeError:
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

    current_hash = hashlib.md5("|".join(headlines).encode()).hexdigest()
    if current_hash == _last_inserted_hash:
        print("[lightrag_store.py] Headlines unchanged -> skipping insert (saved Haiku calls)")
        return

    try:
        future = _executor.submit(_insert_in_thread, headlines)
        future.result(timeout=45)   # 45s max — avoid blocking Gradio UI
        _last_inserted_hash = current_hash
    except concurrent.futures.TimeoutError:
        print("[lightrag_store.py] Insert timed out (45s) — continuing anyway")
        _last_inserted_hash = current_hash  # still mark as done to avoid re-trying
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
        return future.result(timeout=45)   # 45s max — avoid blocking Gradio UI
    except concurrent.futures.TimeoutError:
        print("[lightrag_store.py] Query timed out (45s) — returning empty context")
        return ""
    except Exception as e:
        print(f"[lightrag_store.py] Query failed: {e}")
        return ""
