# CONCERNS
Generated: 2026-04-17
Focus: concerns

---

## CRITICAL

### C1 — No version pins in requirements.txt
**File:** `requirements.txt`
Any upstream breaking change silently breaks production. All dependencies should be pinned (e.g., `openai==1.x.x`).

### C2 — `quota_pressure` bypasses the 65% confidence gate
**Files:** `agent/trading_agent.py`, `ui/dashboard.py`, `backtest.py`
When quota pressure is active, the confidence threshold drops from 65% to 50%, directly violating the hard safety limit stated in CLAUDE.md. This is an undocumented override of a core safety constraint.

### C3 — `DEV_MODE = False` hardcoded in dashboard
**File:** `ui/dashboard.py`
`DEV_MODE: bool = False` disables the Trade Mode toggle, Reset, and backtest tab in the deployed Render UI with no environment variable override mechanism. Features are silently hidden in production.

---

## HIGH

### H1 — `sys.path.insert()` called on every ReAct iteration
**File:** `agent/trading_agent.py` → `_execute_tool()`
Called on every iteration of the ReAct loop — mutates global interpreter state and is not thread-safe.

### H2 — `daily_market_agent.py` creates new MongoClient on every call
**File:** `agent/daily_market_agent.py`
No connection caching, unlike `paper_engine.py` and `trade_log.py`. Creates a new connection on every invocation.

### H3 — Backtest uses random mock headlines with bullish bias
**File:** `backtest.py`
Mock headline pool has a bullish bias and historical news is not replayed. Backtest P&L results are unrepresentative of real conditions.

### H4 — No rate limiting on 8+ external API calls per refresh
**Files:** `ui/dashboard.py`, `agent/trading_agent.py`
At 15-second TEST mode interval, OpenAI budget burns rapidly. No circuit breaker or request queue.

### H5 — Portfolio JSON/MongoDB has no schema validation
**File:** `trader/paper_engine.py`
Malformed `open_position` dict causes silent failures downstream. No validation on read/write.

### H6 — LightRAG timeout silently skips headlines permanently
**File:** `knowledge/lightrag_store.py`
On timeout, headlines are marked as processed and never retried, permanently stopping context accumulation for those entries.

---

## MEDIUM

### M1 — USD/THB rate hardcoded at 34.5 in backtest
**File:** `backtest.py`
Distorts historical THB P&L calculations. Should use historical rates or at minimum a configurable constant.

### M2 — Risk metrics computed from price data, not trade P&L
**File:** `risk/metrics.py`
Sharpe, Sortino, and Kelly ratios are calculated from raw XAUUSD price data rather than actual trade returns. Metrics are misleading.

### M3 — `_analysis_in_progress` flag is not thread-safe
**File:** `ui/dashboard.py`
Boolean flag used as a mutex — not safe under concurrent access, could allow two simultaneous GPT calls.

### M4 — `run_full_analysis()` returns 18-value positional tuple
**File:** `agent/trading_agent.py`
Fragile API — callers must unpack by position. Adding or reordering return values breaks all callers silently.

### M5 — No test coverage for `run_full_analysis()` integration path
**File:** `tests/`
The main analysis pipeline has no integration test. Unit tests cover individual components but not the end-to-end flow.

---

## LOW

### L1 — Equity history truncated to 500 points
**File:** `trader/paper_engine.py`
~10 days of history at 30-min cycle. Full competition history is lost; P&L curve is incomplete.

### L2 — LightRAG docstring claims "Claude Haiku" but uses GPT-4o-mini
**File:** `knowledge/lightrag_store.py`
Documentation mismatch. Implementation uses GPT-4o-mini for knowledge graph operations.

### L3 — Live state JSON files likely committed to git
**File:** `data/portfolio.json`, `data/llm_costs.json`
Branch merges can silently reset portfolio state. These files should be in `.gitignore`.

### L4 — `generate_report.py` not integrated with dashboard
**File:** `generate_report.py`
Standalone script at project root with no dashboard integration. Unclear if maintained.

### L5 — `core/` directory is empty
**File:** `core/`
Appears to be an abandoned restructure. Dead directory adds confusion.

### L6 — `trade_scheduler._save_state()` has no exception handling
**File:** `agent/trade_scheduler.py`
Filesystem errors during state save crash the trade execution path with no recovery.

---

## Design vs. Implementation Gaps

| CLAUDE.md Stated Constraint | Actual Implementation |
|---|---|
| `claude_agent.py` — ReAct loop | `claude_agent.py` is a shim; actual logic in `trading_agent.py` |
| Auto-refresh every 5 min | Timer is 30 min in production (5 min only in TEST mode) |
| LightRAG uses Claude Haiku | LightRAG uses GPT-4o-mini |
| 65% confidence gate (hard limit) | Gate lowered to 50% under `quota_pressure` |
| temperature=0 (deterministic) | Not verified in all agent call sites |
| No global state | `sys.path.insert()` in hot path; `_analysis_in_progress` global flag |
