# News Sentiment + LightRAG Knowledge Base Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace keyword-based sentiment scoring with Claude Haiku, and add a LightRAG knowledge graph that accumulates headlines and surfaces historical/domain context to the trading agent.

**Architecture:** `get_sentiment_summary()` in `news/sentiment.py` gains a Claude Haiku call with keyword fallback. A new `knowledge/lightrag_store.py` module wraps LightRAG (sentence-transformers embeddings + Claude Haiku LLM). The agent's existing `get_news` tool handler is extended to call `insert_headlines()` and `query_gold_context()`, appending `historical_context` to its response — no agent prompt changes required.

**Tech Stack:** `anthropic` (already installed), `lightrag-hku`, `sentence-transformers` (`all-MiniLM-L6-v2`, 384-dim, free/local)

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Modify | `requirements.txt` | Add `lightrag-hku`, `sentence-transformers` |
| Modify | `news/sentiment.py` | Add Claude Haiku scoring + `_keyword_sentiment` fallback |
| Create | `knowledge/__init__.py` | Package marker |
| Create | `knowledge/gold_knowledge.txt` | Static seed: gold market domain knowledge |
| Create | `knowledge/lightrag_store.py` | LightRAG init, insert, query; lazy-loads model |
| Modify | `agent/claude_agent.py` | Wire `insert_headlines` + `query_gold_context` into `get_news` handler |
| Create | `tests/test_sentiment.py` | Tests for Claude scoring + fallback |
| Create | `tests/test_lightrag_store.py` | Tests for insert/query with mocked LightRAG |
| Create | `tests/test_agent_news_tool.py` | Tests for `historical_context` in tool response |

---

## Task 1: Add Dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add packages**

Replace the contents of `requirements.txt` with:

```
anthropic
gradio>=4.15.0
yfinance
pandas
numpy
matplotlib
python-dotenv
requests
lightrag-hku
sentence-transformers
```

- [ ] **Step 2: Install**

```bash
pip install lightrag-hku sentence-transformers
```

Expected: packages install without errors. `sentence-transformers` will download `all-MiniLM-L6-v2` (~90MB) on first use.

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add lightrag-hku and sentence-transformers dependencies"
```

---

## Task 2: Claude-Powered Sentiment

**Files:**
- Modify: `news/sentiment.py`
- Create: `tests/test_sentiment.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_sentiment.py`:

```python
"""Tests for Claude-powered sentiment scoring with keyword fallback."""
import json
from unittest.mock import MagicMock, patch

import pytest


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
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd D:\working\CN240\Gold_Agent\gold-agent
pytest tests/test_sentiment.py -v
```

Expected: `ImportError` or `AttributeError` because `anthropic` is not yet imported in `sentiment.py` and `_keyword_sentiment` doesn't exist.

- [ ] **Step 3: Implement**

Replace the entire content of `news/sentiment.py` with:

```python
"""
news/sentiment.py
Fetches gold-related news headlines from NewsAPI.
Falls back to a rotating pool of mock headlines if the API key is missing,
so the app always shows different headlines each refresh.

Sentiment scoring uses Claude Haiku for nuanced analysis.
Falls back to keyword counting if the API call fails.
"""

import json
import os
import random

import anthropic
import requests
from dotenv import load_dotenv

load_dotenv()

# Large pool of realistic mock headlines — 5 are randomly picked each refresh
# so users never see the same set twice when no API key is configured.
MOCK_HEADLINE_POOL = [
    "Gold prices surge amid global economic uncertainty and inflation fears",
    "Central banks increase gold reserves as dollar weakens",
    "Fed signals potential rate cuts, boosting gold demand",
    "Geopolitical tensions drive safe-haven buying in gold market",
    "Gold ETF inflows hit six-month high as investors seek protection",
    "US dollar weakness pushes gold to three-month high",
    "Goldman Sachs raises gold price target to $3,000 by year-end",
    "Middle East tensions fuel surge in safe-haven gold buying",
    "IMF warns of global recession risk — gold seen as key hedge",
    "Gold holds steady as traders await Fed interest rate decision",
    "Chinese central bank adds to gold reserves for fifth straight month",
    "Inflation data surprise sends gold futures sharply higher",
    "Gold miners report record profits as bullion prices climb",
    "BRICS nations accelerate de-dollarization, boosting gold demand",
    "Gold hits record high as US debt ceiling fears intensify",
    "Analysts warn of gold correction after overbought RSI reading",
    "Physical gold demand in Asia remains robust despite high prices",
    "Strong US jobs data dampens gold rally, dollar recovers",
    "Silver outperforms gold as industrial demand picks up",
    "Gold prices under pressure as Fed holds rates higher for longer",
]


def get_gold_news(max_headlines: int = 5) -> list[str]:
    """
    Fetch the latest gold-related news headlines from NewsAPI.

    If NEWS_API_KEY is missing or the request fails, returns a random
    selection from MOCK_HEADLINE_POOL so every refresh shows different headlines.

    Args:
        max_headlines (int): Maximum number of headlines to return. Default 5.

    Returns:
        list[str]: List of headline strings (real or mock).
    """
    api_key = os.getenv("NEWS_API_KEY", "").strip()

    if not api_key or api_key == "your_key_here":
        print("[sentiment.py] No NEWS_API_KEY. Using rotating mock headlines.")
        return random.sample(MOCK_HEADLINE_POOL, min(max_headlines, len(MOCK_HEADLINE_POOL)))

    try:
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": "gold price OR gold market OR XAU",
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": max_headlines,
            "apiKey": api_key,
        }

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()

        data = response.json()
        articles = data.get("articles", [])

        if not articles:
            print("[sentiment.py] No articles returned. Using mock headlines.")
            return random.sample(MOCK_HEADLINE_POOL, min(max_headlines, len(MOCK_HEADLINE_POOL)))

        headlines = [
            a.get("title", "").strip()
            for a in articles[:max_headlines]
            if a.get("title", "").strip() and a.get("title") != "[Removed]"
        ]

        if not headlines:
            return random.sample(MOCK_HEADLINE_POOL, min(max_headlines, len(MOCK_HEADLINE_POOL)))

        print(f"[sentiment.py] Fetched {len(headlines)} real headlines.")
        return headlines

    except requests.exceptions.Timeout:
        print("[sentiment.py] NewsAPI timed out. Using mock headlines.")
    except requests.exceptions.HTTPError as e:
        print(f"[sentiment.py] NewsAPI HTTP error: {e}. Using mock headlines.")
    except Exception as e:
        print(f"[sentiment.py] Error fetching news: {e}. Using mock headlines.")

    return random.sample(MOCK_HEADLINE_POOL, min(max_headlines, len(MOCK_HEADLINE_POOL)))


def _keyword_sentiment(headlines: list[str]) -> str:
    """Rule-based fallback: count bullish vs bearish keywords."""
    bullish_kw = [
        "surge", "rise", "gain", "rally", "jump", "soar", "high",
        "demand", "buying", "boost", "positive", "growth", "record", "higher",
    ]
    bearish_kw = [
        "fall", "drop", "decline", "plunge", "crash", "low", "sell",
        "loss", "weakness", "down", "negative", "risk", "pressure", "correction",
    ]
    combined = " ".join(headlines).lower()
    bull = sum(combined.count(kw) for kw in bullish_kw)
    bear = sum(combined.count(kw) for kw in bearish_kw)
    if bull > bear:
        return "BULLISH"
    elif bear > bull:
        return "BEARISH"
    return "NEUTRAL"


def get_sentiment_summary(headlines: list[str]) -> str:
    """
    Score gold news sentiment using Claude Haiku.

    Sends headlines to Claude Haiku (temperature=0) and asks for a JSON
    sentiment label. Falls back to keyword counting if the API key is
    missing or the call fails.

    Args:
        headlines (list[str]): List of news headline strings.

    Returns:
        str: "BULLISH", "BEARISH", or "NEUTRAL".
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return _keyword_sentiment(headlines)

    try:
        client = anthropic.Anthropic()
        headlines_text = "\n".join(f"- {h}" for h in headlines)
        prompt = (
            f"Analyze these gold market news headlines:\n{headlines_text}\n\n"
            "Return JSON only, no other text: "
            '{"sentiment": "BULLISH" or "BEARISH" or "NEUTRAL", "reasoning": "<1 sentence>"}'
        )
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        data = json.loads(response.content[0].text)
        label = data.get("sentiment", "").upper()
        if label in ("BULLISH", "BEARISH", "NEUTRAL"):
            print(f"[sentiment.py] Claude sentiment: {label}")
            return label
        return _keyword_sentiment(headlines)

    except Exception as e:
        print(f"[sentiment.py] Claude sentiment failed ({e}). Falling back to keywords.")
        return _keyword_sentiment(headlines)


# Allow standalone testing
if __name__ == "__main__":
    headlines = get_gold_news()
    print("\nHeadlines:")
    for i, h in enumerate(headlines, 1):
        print(f"  {i}. {h}")
    print(f"\nSentiment: {get_sentiment_summary(headlines)}")
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/test_sentiment.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add news/sentiment.py tests/test_sentiment.py
git commit -m "feat(news): replace keyword sentiment with Claude Haiku scoring"
```

---

## Task 3: LightRAG Knowledge Base Module

**Files:**
- Create: `knowledge/__init__.py`
- Create: `knowledge/gold_knowledge.txt`
- Create: `knowledge/lightrag_store.py`
- Create: `tests/test_lightrag_store.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_lightrag_store.py`:

```python
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
```

- [ ] **Step 2: Run tests — expect failure**

```bash
pytest tests/test_lightrag_store.py -v
```

Expected: `ModuleNotFoundError: No module named 'knowledge'`

- [ ] **Step 3: Create package marker**

Create `knowledge/__init__.py` (empty file):

```python
```

- [ ] **Step 4: Create static seed file**

Create `knowledge/gold_knowledge.txt`:

```
Gold Market Domain Knowledge — Static Seed for LightRAG Knowledge Base

## Gold Price Drivers

### USD/DXY Inverse Correlation
Gold prices move inversely to the US Dollar Index (DXY). When the dollar strengthens, gold becomes more expensive in other currencies, reducing demand and pushing prices down. When the dollar weakens, gold becomes cheaper globally, increasing demand and prices. This is the single strongest correlation in gold trading.

### Federal Reserve Interest Rates
Rising interest rates are bearish for gold because:
1. Higher rates increase the opportunity cost of holding gold (gold pays no yield)
2. Rate hikes signal economic strength, reducing safe-haven demand
3. Higher rates typically strengthen the USD, applying double downward pressure

Rate cuts are bullish for gold: lower rates reduce opportunity cost, may weaken USD, and signal economic concern.

### Safe-Haven Demand
Gold is the world's premier safe-haven asset. Demand surges during:
- Geopolitical conflicts and wars (Middle East, Russia-Ukraine, Taiwan Strait tensions)
- Banking crises or financial system stress
- Recession fears and equity market crashes
- Sovereign debt concerns or currency crises

### Inflation Hedge
Gold is a long-term inflation hedge. When CPI data surprises to the upside or inflation expectations rise, gold benefits as investors seek real assets. However, this effect can be offset by the Fed's response (rate hikes).

### Central Bank Buying
Central banks, especially from China, India, Russia, Turkey, and BRICS nations, have been net buyers of gold since 2022. Large purchase announcements from central banks are bullish catalysts. De-dollarization strategies among emerging market central banks support long-term gold demand.

### Gold ETF Flows
Rising ETF inflows (especially SPDR Gold Shares / GLD) signal institutional bullish positioning. Large outflows indicate institutional selling and are bearish. ETF inventory data is published daily.

## Thai Gold Market Specifics

### Baht-Weight (บาท)
Thai gold is priced per baht-weight (บาทหนึ่ง). One baht-weight = 15.244 grams. Thai retail gold uses 96.5% purity (not the international 99.99% standard). The Thai gold shop price is calculated as: (spot price USD/oz) × (USD/THB rate) / 31.1035 × 15.244 × 0.965.

### Thai Gold Shop Dynamics
Major Thai gold shop chains (Gold Now / Hua Seng Heng / Aurora) update prices approximately every 30 minutes during trading hours. Buy/sell spreads are typically 150-200 THB per baht-weight.

## Technical Analysis Context

### RSI (Relative Strength Index) — Wilder Smoothing
- RSI > 70: Overbought — potential reversal or correction
- RSI 40-65: Neutral zone — trend continuation or consolidation
- RSI < 30: Oversold — potential bounce or reversal
Wilder smoothing (used here) produces smoother RSI than simple EMA and is the industry standard.

### MACD Signal
- Positive histogram (MACD above signal line): Bullish momentum
- Negative histogram (MACD below signal line): Bearish momentum
- Histogram shrinking toward zero: Momentum weakening, possible reversal

### Bollinger Bands
- %B > 1.0: Price above upper band — overbought
- %B < 0.0: Price below lower band — oversold
- Bandwidth expansion: Volatility increasing, potential breakout
- Bandwidth contraction: Low volatility, potential breakout approaching

## Historical Patterns

### Gold Seasonality
Gold historically shows strength in Q1 (January-March) due to Asian New Year demand, and in Q3-Q4 due to Indian festival/wedding season (Diwali, Dhanteras).

### Correlation with Equities
Gold typically has a negative correlation with equities during risk-off events (investors flee to gold). During prolonged bull markets, the correlation can be positive as liquidity flows into all assets.

### Key Support/Resistance Levels (as of 2024-2025)
- Major psychological level: $2,000/oz (long-term support)
- Record highs area: $2,500-$2,800/oz (resistance)
- Strong bull market drivers: geopolitical tension + Fed easing cycle
```

- [ ] **Step 5: Create lightrag_store.py**

Create `knowledge/lightrag_store.py`:

```python
"""
knowledge/lightrag_store.py
LightRAG-backed knowledge store for gold market context.

Accumulates real news headlines over time and seeds static gold market
domain knowledge on first run. Exposes two functions used by the
agent's get_news tool handler.

Models:
  LLM        : claude-haiku-4-5-20251001 (entity/relation extraction)
  Embeddings : all-MiniLM-L6-v2 via sentence-transformers (384-dim, local)

Storage: data/lightrag/ (persisted alongside portfolio.json)
"""

import os
from datetime import datetime

WORKING_DIR   = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "lightrag"))
SEED_FILE     = os.path.join(os.path.dirname(__file__), "gold_knowledge.txt")
SEED_SENTINEL = os.path.join(WORKING_DIR, ".seeded")

_rag      = None
_st_model = None


def _get_st_model():
    global _st_model
    if _st_model is None:
        from sentence_transformers import SentenceTransformer
        _st_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _st_model


async def _llm_func(prompt, system_prompt=None, history_messages=None, **kwargs) -> str:
    import anthropic
    client = anthropic.Anthropic()
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


def insert_headlines(headlines: list[str]) -> None:
    """
    Append news headlines to the knowledge graph.

    Called after every successful news fetch so the graph accumulates
    real market events over time.

    Args:
        headlines: List of headline strings from get_gold_news().
    """
    if not headlines:
        return
    try:
        rag = _get_rag()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        text = (
            f"[{timestamp}] Gold market news headlines:\n"
            + "\n".join(f"- {h}" for h in headlines)
        )
        rag.insert(text)
    except Exception as e:
        print(f"[lightrag_store.py] Insert failed: {e}")


def query_gold_context(question: str) -> str:
    """
    Query the knowledge graph for relevant historical and domain context.

    Returns an empty string (not an exception) if LightRAG is unavailable,
    so the agent degrades gracefully when the store is cold or broken.

    Args:
        question: Natural language question to query the knowledge graph.

    Returns:
        str: Relevant context text, or "" on failure.
    """
    try:
        from lightrag import QueryParam
        rag = _get_rag()
        result = rag.query(question, param=QueryParam(mode="hybrid"))
        return result or ""
    except Exception as e:
        print(f"[lightrag_store.py] Query failed: {e}")
        return ""
```

- [ ] **Step 6: Run tests — expect pass**

```bash
pytest tests/test_lightrag_store.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add knowledge/__init__.py knowledge/gold_knowledge.txt knowledge/lightrag_store.py tests/test_lightrag_store.py
git commit -m "feat(knowledge): add LightRAG knowledge store with gold domain seed"
```

---

## Task 4: Wire LightRAG into Agent's get_news Tool

**Files:**
- Modify: `agent/claude_agent.py` (lines 237–253)
- Create: `tests/test_agent_news_tool.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_agent_news_tool.py`:

```python
"""Tests for the enhanced get_news tool handler in GoldTradingAgent."""
import json
from unittest.mock import MagicMock, patch


def _make_agent():
    from agent.claude_agent import GoldTradingAgent
    return GoldTradingAgent(api_key="sk-test")


def test_get_news_tool_includes_historical_context():
    agent = _make_agent()

    with patch("news.sentiment.get_gold_news", return_value=["Gold rises on safe-haven demand"]), \
         patch("news.sentiment.get_sentiment_summary", return_value="BULLISH"), \
         patch("knowledge.lightrag_store.insert_headlines"), \
         patch("knowledge.lightrag_store.query_gold_context",
               return_value="Gold inversely correlates with DXY."):
        raw = agent._execute_tool("get_news", {"count": 3})

    result = json.loads(raw)
    assert "historical_context" in result
    assert result["historical_context"] == "Gold inversely correlates with DXY."


def test_get_news_tool_omits_historical_context_when_empty():
    agent = _make_agent()

    with patch("news.sentiment.get_gold_news", return_value=["Gold holds steady"]), \
         patch("news.sentiment.get_sentiment_summary", return_value="NEUTRAL"), \
         patch("knowledge.lightrag_store.insert_headlines"), \
         patch("knowledge.lightrag_store.query_gold_context", return_value=""):
        raw = agent._execute_tool("get_news", {"count": 3})

    result = json.loads(raw)
    assert "historical_context" not in result


def test_get_news_tool_calls_insert_headlines():
    agent = _make_agent()
    headlines = ["Gold jumps 2% on inflation data"]

    with patch("news.sentiment.get_gold_news", return_value=headlines), \
         patch("news.sentiment.get_sentiment_summary", return_value="BULLISH"), \
         patch("knowledge.lightrag_store.insert_headlines") as mock_insert, \
         patch("knowledge.lightrag_store.query_gold_context", return_value=""):
        agent._execute_tool("get_news", {"count": 1})

    mock_insert.assert_called_once_with(headlines)
```

- [ ] **Step 2: Run tests — expect failure**

```bash
pytest tests/test_agent_news_tool.py -v
```

Expected: tests fail because `historical_context` is not in the response and `insert_headlines` is not called.

- [ ] **Step 3: Modify the get_news handler in agent/claude_agent.py**

Find lines 237–253 in `agent/claude_agent.py`:

```python
        # ── Tool: get_news ───────────────────────────────────────────────────
        elif tool_name == "get_news":
            from news.sentiment import get_gold_news, get_sentiment_summary
            count = min(int(tool_input.get("count", 5)), 5)
            headlines = get_gold_news(count)
            sentiment = get_sentiment_summary(headlines)

            # Structured news
            result = {
                "note": "Use these headlines to identify macro catalysts (The LLM Advantage)",
                "headlines": headlines,
                "count": len(headlines),
                "overall_sentiment": sentiment,
                "bullish_catalysts": ["Fed rate cuts", "Geopolitical tensions", "Inflation surge", "USD weakness"],
                "bearish_catalysts": ["Fed rate hikes", "Strong USD", "Risk-on rally", "Crypto competition"],
            }
            return json.dumps(result)
```

Replace with:

```python
        # ── Tool: get_news ───────────────────────────────────────────────────
        elif tool_name == "get_news":
            from news.sentiment import get_gold_news, get_sentiment_summary
            from knowledge.lightrag_store import insert_headlines, query_gold_context
            count = min(int(tool_input.get("count", 5)), 5)
            headlines = get_gold_news(count)
            sentiment = get_sentiment_summary(headlines)

            # Accumulate headlines in knowledge graph
            insert_headlines(headlines)

            # Query historical and domain context
            historical = query_gold_context(
                "What are the key macro drivers and historical patterns for gold price movements?"
            )

            # Structured news
            result = {
                "note": "Use these headlines to identify macro catalysts (The LLM Advantage)",
                "headlines": headlines,
                "count": len(headlines),
                "overall_sentiment": sentiment,
                "bullish_catalysts": ["Fed rate cuts", "Geopolitical tensions", "Inflation surge", "USD weakness"],
                "bearish_catalysts": ["Fed rate hikes", "Strong USD", "Risk-on rally", "Crypto competition"],
            }
            if historical:
                result["historical_context"] = historical
            return json.dumps(result)
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/test_agent_news_tool.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Run full test suite**

```bash
pytest -v
```

Expected: all tests PASS (existing paper engine tests + new sentiment + lightrag + agent news tests).

- [ ] **Step 6: Commit**

```bash
git add agent/claude_agent.py tests/test_agent_news_tool.py
git commit -m "feat(agent): wire LightRAG context into get_news tool response"
```

---

## Self-Review Checklist

- [x] **Spec coverage:** Claude Haiku sentiment ✓, fallback to keywords ✓, LightRAG accumulates headlines ✓, static domain seed ✓, `historical_context` in agent tool response ✓
- [x] **No placeholders:** All steps have complete code
- [x] **Type consistency:** `insert_headlines(headlines: list[str])` and `query_gold_context(question: str) -> str` match across tasks 3 and 4
- [x] **Interface unchanged:** `get_sentiment_summary()` still returns `str`, no callers in `dashboard.py` or elsewhere need updating
- [x] **Fallback chain complete:** No API key → skip Claude; API error → keyword fallback; LightRAG failure → empty string, key omitted from response
