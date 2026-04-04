# Dashboard Mobile/Readability UX — Design Spec
Date: 2026-03-27
Status: Approved

## Problem
The Gradio dashboard is difficult to use on smaller screens and at lower resolutions:
- Monospace fonts at micro sizes (0.72–0.82em) are unreadable on mobile
- Multi-column `gr.Row()` layouts break or overflow below ~768px width
- Matplotlib charts are rasterised PNGs — they do not scale down gracefully
- The single-page scroll (~10 sections) is overwhelming on a phone
- Long strings (reasoning text, trade IDs) overflow their containers

## Goal
Make the dashboard readable and usable on mobile without breaking the desktop experience. Preserve the PNS-style dark terminal aesthetic.

---

## Approach: CSS Overhaul (Option A) + Tab Layout (Option C)

Two complementary changes applied together.

---

## Section 1: CSS & Font Fixes

### Font sizes
| Element | Before | After |
|---|---|---|
| Base body | 0.95em | 1.0em |
| Labels | 0.72em | 0.78em |
| Table cells | 0.82em | 0.88em |
| Countdown/status text | default | 0.92em |
| Minimum floor | none | 11px |

### Responsive breakpoint
Add `@media (max-width: 768px)` rules in `PNS_CSS`:
- All multi-column `gr.Row()` groups stack vertically (via `flex-direction: column`)
- Horizontal padding reduced so panels don't overflow viewport
- Chart `figsize` minimum: `(10, 4)`

### Readability
- `line-height: 1.5` on reasoning textareas and agent card text
- `word-break: break-word` on all text containers to prevent overflow
- Progress bar / countdown: bump to `0.92em`

---

## Section 2: Tab Layout Restructure

### Always visible (above the fold — no tabs)
1. Trade Mode toggle
2. Price panel (big THB number, USD, % change)
3. Agent decision card (BUY/SELL/HOLD badge + confidence + reasoning)
4. Refresh button + last-updated time
5. Countdown bar

### Wrapped in `gr.Tabs()` (below the fold)
| Tab label | Contents |
|---|---|
| Charts | 90-day price chart + RSI chart (separate `gr.Plot()` outputs) |
| Portfolio | Equity metrics, P&L summary, P&L curve chart |
| Trades | WIN/LOSS bar + trade journal table |
| Log | Analysis log CSV table |
| News | 5 headlines + sentiment badge |

### Status bar
Remains outside tabs at the very bottom (last action: OPENED / CLOSED / HOLD / SKIP).

### Charts
- Split the current combined matplotlib figure (price + RSI stacked) into two separate `gr.Plot()` outputs within the Charts tab
- Each chart renders full-width on narrow screens
- `figsize` set to `(12, 3)` per chart for tab-friendly height

---

## Files to Change
- `gold-agent/ui/dashboard.py` — only file that needs editing

## Files NOT changed
- `paper_engine.py`, `claude_agent.py`, indicator/data modules — no logic changes
- `data/portfolio.json` — untouched

---

## Out of Scope
- No new dependencies
- No changes to trading logic, confidence gate, or agent behaviour
- No backend/API changes
- No real-time WebSocket updates (not needed for this fix)
