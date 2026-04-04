# Design: Claude-Powered Sentiment + LightRAG Knowledge Base
**Date:** 2026-03-27
**Branch:** Team3
**Approach:** A (minimal touch — enrich existing `get_news` tool, no new agent tools)

---

## Overview

Two improvements to the news pipeline:

1. **Claude-powered sentiment** — replace keyword counting in `get_sentiment_summary()` with a Claude Haiku call that understands nuance
2. **LightRAG knowledge base** — accumulate headlines over time + static gold domain knowledge, surfaced to Claude via the existing `get_news` tool response

---

## Section 1: Claude-Powered Sentiment

### What changes
`news/sentiment.py` — `get_sentiment_summary(headlines)` only.

### Behaviour
1. Call `claude-haiku-4-5-20251001` with `temperature=0`
2. Prompt: given these gold headlines, return `{"sentiment": "BULLISH|BEARISH|NEUTRAL", "reasoning": "<1 sentence>"}`
3. Parse JSON response, return the `sentiment` field
4. **Fallback**: if API call fails or JSON unparseable → existing keyword method

### Interface (unchanged)
```python
def get_sentiment_summary(headlines: list[str]) -> str:
    # returns "BULLISH", "BEARISH", or "NEUTRAL"
```

No changes needed in `dashboard.py` or `claude_agent.py`.

### Cost
~$0.00025 per call (Haiku pricing). Fires once per 5-min dashboard refresh.

---

## Section 2: LightRAG Knowledge Base

### New files
```
knowledge/
├── __init__.py
├── lightrag_store.py     — LightRAG init, insert, query
└── gold_knowledge.txt    — static seed: gold market fundamentals
data/
└── lightrag/             — persisted graph + vector store (auto-created)
```

### Dependencies added to requirements.txt
```
lightrag-hku
sentence-transformers
```

### Models used
| Role | Model |
|---|---|
| LLM (entity/relation extraction) | `claude-haiku-4-5-20251001` via Anthropic API |
| Embeddings (vector search) | `all-MiniLM-L6-v2` via sentence-transformers (local, free) |

### lightrag_store.py API
```python
def insert_headlines(headlines: list[str]) -> None:
    """Append headlines to knowledge graph. Called after every news fetch."""

def query_gold_context(question: str) -> str:
    """Return relevant historical/domain context as plain text string."""
```

First run: automatically inserts `gold_knowledge.txt` seed and creates a sentinel file `data/lightrag/.seeded` to prevent re-insertion.

### gold_knowledge.txt contents (static seed)
- USD/DXY inverse correlation with gold
- Fed interest rate impact on gold (higher rates = bearish, cuts = bullish)
- Safe-haven demand drivers (geopolitical risk, recession fear)
- Central bank buying behaviour
- Gold/Silver ratio context
- Inflation hedge mechanics
- Thai gold market specifics (baht-weight, 96.5% purity, shop price vs spot)

### Agent integration
`agent/claude_agent.py` — `get_news` tool handler only.

After fetching headlines and keyword sentiment, call:
```python
context = query_gold_context("macro context and historical signals for gold right now")
```

Append to the tool response dict as `"historical_context": context`.

Claude already receives this in the tool result — no system prompt changes needed.

**Fallback**: if LightRAG query fails, omit `historical_context` key silently.

---

## Data Flow

```
Dashboard refresh (every 5 min)
  └─ run_full_analysis()
       ├─ get_gold_news()           → fetches headlines (NewsAPI or mock)
       ├─ get_sentiment_summary()   → Claude Haiku scores sentiment       [NEW]
       └─ agent: get_news tool
            ├─ insert_headlines()   → appends to LightRAG graph           [NEW]
            ├─ query_gold_context() → retrieves historical context        [NEW]
            └─ returns {headlines, sentiment, historical_context}
```

---

## Error Handling

| Failure | Behaviour |
|---|---|
| Claude API down (sentiment) | Fall back to keyword counting |
| LightRAG insert fails | Log warning, skip silently |
| LightRAG query fails | Omit `historical_context` from tool response |
| sentence-transformers not installed | LightRAG store raises ImportError at startup — surface clearly |

---

## Testing

- `tests/test_sentiment.py` — mock Claude API response, verify `get_sentiment_summary` returns correct label and falls back correctly
- `tests/test_lightrag_store.py` — mock LightRAG, verify insert and query are called with correct arguments
