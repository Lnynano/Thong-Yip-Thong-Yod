#!/usr/bin/env python3
"""
backtest.py
Replay historical OHLCV data candle-by-candle through the gold trading agent.

Usage:
    cd gold-agent
    python backtest.py

Data source:
    yfinance GC=F (Gold Futures) — real historical prices.
    Default: 1-hour candles, last 60 days  (gives ~900 candles, ~60 trade sessions)
    Falls back to daily candles (last 6 months) if 1h fetch fails.

Notes:
    - Starts from candle 20 (minimum for Bollinger Bands to be valid)
    - Uses a fixed USD/THB rate of 34.5 for consistent conversion
    - News uses mock headlines (not real historical news)
    - Each candle makes 1 API call — use BACKTEST_MAX_CANDLES env var
      to cap the run (default 50 candles) and keep API costs reasonable
"""

import sys
import os
import pandas as pd
from unittest.mock import patch

# ── Path setup ───────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Constants ─────────────────────────────────────────────────────────────────
USD_THB_RATE        = 34.5      # fixed rate for consistent backtesting
TROY_OZ_GRAMS       = 31.1035
BAHT_WEIGHT_GRAMS   = 15.244
PURITY              = 0.965
INITIAL_BALANCE_THB = 1500.0
CONFIDENCE_GATE     = 65
MIN_BALANCE_THB     = 1000.0
POSITION_SIZE_PCT   = 0.95
MIN_ROWS            = 20        # need 20 rows for Bollinger Bands(20)
# Cap candles to run so API costs stay predictable (override with env var)
MAX_CANDLES         = int(os.environ.get("BACKTEST_MAX_CANDLES", "50"))


def usd_to_thb_per_bw(price_usd: float) -> float:
    """Convert USD/oz → THB per baht-weight (Thai 96.5% purity)."""
    thb_per_oz    = price_usd * USD_THB_RATE
    thb_per_gram  = thb_per_oz / TROY_OZ_GRAMS
    thb_per_bw    = thb_per_gram * BAHT_WEIGHT_GRAMS * PURITY
    return round(thb_per_bw, 2)


def run_backtest() -> dict:
    """
    Run the backtest and return structured results for both terminal and dashboard use.

    Returns:
        dict: {
            "daily_log"     : list of per-day records,
            "closed_trades" : list of completed trades,
            "summary"       : dict of key performance metrics,
            "open_position" : dict or None if position still open at end,
        }
    """
    # ── Load real historical data from yfinance ───────────────────────────────
    import yfinance as yf

    df_full = None
    interval_used = ""

    # Try 1-hour candles first (last 60 days — yfinance hard limit for 1h)
    try:
        print("  Fetching 1h candles from yfinance (GC=F, 60d)...")
        raw = yf.download("GC=F", period="60d", interval="1h", progress=False, auto_adjust=True)
        if not raw.empty and len(raw) >= MIN_ROWS + 5:
            # yfinance returns MultiIndex columns when auto_adjust=True
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            raw.index.name = "Date"
            df_full = raw[["Open", "High", "Low", "Close", "Volume"]].dropna()
            interval_used = "1h"
            print(f"  Got {len(df_full)} hourly candles.")
    except Exception as e:
        print(f"  1h fetch failed ({e}), falling back to daily...")

    # Fallback: daily candles (last 6 months)
    if df_full is None or len(df_full) < MIN_ROWS + 5:
        try:
            print("  Fetching daily candles from yfinance (GC=F, 6mo)...")
            raw = yf.download("GC=F", period="6mo", interval="1d", progress=False, auto_adjust=True)
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            raw.index.name = "Date"
            df_full = raw[["Open", "High", "Low", "Close", "Volume"]].dropna()
            interval_used = "1d"
            print(f"  Got {len(df_full)} daily candles.")
        except Exception as e:
            print(f"  Daily fetch also failed: {e}")
            return {
                "daily_log": [], "closed_trades": [], "open_position": None,
                "summary": {"error": str(e)},
            }

    if df_full is None or df_full.empty:
        print("  ERROR: Could not fetch any data from yfinance.")
        return {
            "daily_log": [], "closed_trades": [], "open_position": None,
            "summary": {"error": "No data fetched"},
        }

    # ── Cap candles to keep API costs reasonable ──────────────────────────────
    # Always take the LAST N candles so we replay the most recent market action
    if len(df_full) > MIN_ROWS + MAX_CANDLES:
        df_full = df_full.iloc[-(MIN_ROWS + MAX_CANDLES):]
        print(f"  Capped to last {MIN_ROWS + MAX_CANDLES} candles "
              f"({MIN_ROWS} warmup + {MAX_CANDLES} live).")

    print("=" * 65)
    print("  GOLD AGENT BACKTEST  (real yfinance data)")
    print(f"  Interval : {interval_used}")
    print(f"  Data  : {df_full.index[0]}  →  {df_full.index[-1]}")
    print(f"  Candles  : {len(df_full)}  |  Live candles: {len(df_full) - MIN_ROWS}")
    print(f"  Start : candle {MIN_ROWS} (Bollinger Bands require {MIN_ROWS} rows)")
    print(f"  Rate  : USD/THB = {USD_THB_RATE} (fixed)")
    print(f"  Capital: ฿{INITIAL_BALANCE_THB:,.0f}  |  Gate: {CONFIDENCE_GATE}% confidence")
    print("=" * 65)

    # ── Paper trading state (in-memory, no portfolio.json touched) ────────────
    balance_thb    = INITIAL_BALANCE_THB
    open_position  = None
    closed_trades  = []
    daily_log      = []

    import data.fetch as fetch_module
    from agent.trading_agent import run_agent

    for i in range(MIN_ROWS - 1, len(df_full)):
        window     = df_full.iloc[: i + 1].copy()
        date       = df_full.index[i]
        price_usd  = float(window["Close"].iloc[-1])
        price_thb  = usd_to_thb_per_bw(price_usd)

        print(f"\n{'─'*65}")
        print(f"  Candle {i+1:3d} | {date} | ${price_usd:,.2f} | ฿{price_thb:,.0f}/bw")
        print(f"{'─'*65}")

        with patch.object(fetch_module, "get_gold_price", return_value=window):
            agent = run_agent()

        decision    = agent["decision"]
        confidence  = agent["confidence"]
        reasoning   = agent["reasoning"]
        key_factors = agent.get("key_factors", [])

        print(f"  Decision   : {decision} @ {confidence}%")
        print(f"  Reasoning  : {reasoning[:120]}{'...' if len(reasoning) > 120 else ''}")
        if key_factors:
            print(f"  Key factors: {', '.join(key_factors[:3])}")

        action  = "HOLD"
        pnl_thb = 0.0

        if decision == "BUY" and confidence >= CONFIDENCE_GATE:
            if open_position is None:
                if balance_thb >= MIN_BALANCE_THB:
                    cost    = round(balance_thb * POSITION_SIZE_PCT, 2)
                    size_bw = cost / price_thb
                    balance_thb   -= cost
                    open_position  = {
                        "entry_date"  : str(date.date()),
                        "entry_price" : price_thb,
                        "size_bw"     : size_bw,
                        "cost_thb"    : cost,
                    }
                    action = "OPENED"
                    print(f"  >> BUY executed  | cost ฿{cost:,.2f} | size {size_bw:.6f} bw")
                else:
                    action = "SKIP (low balance)"
            else:
                action = "SKIP (already holding)"

        elif decision == "SELL" and confidence >= CONFIDENCE_GATE:
            if open_position is not None:
                proceeds = open_position["size_bw"] * price_thb
                pnl_thb  = round(proceeds - open_position["cost_thb"], 2)
                outcome  = "WIN" if pnl_thb >= 0 else "LOSS"
                balance_thb += proceeds
                trade = {
                    "entry_date"  : open_position["entry_date"],
                    "exit_date"   : str(date.date()),
                    "entry_price" : open_position["entry_price"],
                    "exit_price"  : price_thb,
                    "size_bw"     : open_position["size_bw"],
                    "cost_thb"    : open_position["cost_thb"],
                    "pnl_thb"     : pnl_thb,
                    "pnl_pct"     : round(pnl_thb / open_position["cost_thb"] * 100, 2),
                    "outcome"     : outcome,
                }
                closed_trades.append(trade)
                open_position = None
                action = f"CLOSED [{outcome}]"
                print(f"  >> SELL executed | proceeds ฿{proceeds:,.2f} | P&L {pnl_thb:+.2f} [{outcome}]")
            else:
                action = "SKIP (no position)"

        unrealized = 0.0
        if open_position:
            unrealized = (open_position["size_bw"] * price_thb) - open_position["cost_thb"]
        equity = round(balance_thb + (open_position["size_bw"] * price_thb if open_position else 0), 2)

        print(f"  Action     : {action}")
        print(f"  Equity     : ฿{equity:,.2f}  (cash ฿{balance_thb:,.2f} + unrealized ฿{unrealized:+.2f})")

        daily_log.append({
            "date"       : str(date.date()),
            "price_usd"  : price_usd,
            "price_thb"  : price_thb,
            "decision"   : decision,
            "confidence" : confidence,
            "action"     : action,
            "pnl_thb"    : pnl_thb,
            "equity_thb" : equity,
        })

    # ── Final summary ─────────────────────────────────────────────────────────
    last_price_thb = daily_log[-1]["price_thb"] if daily_log else 0
    final_equity   = balance_thb
    if open_position:
        final_equity += open_position["size_bw"] * last_price_thb

    wins      = [t for t in closed_trades if t["outcome"] == "WIN"]
    losses    = [t for t in closed_trades if t["outcome"] == "LOSS"]
    total_pnl = sum(t["pnl_thb"] for t in closed_trades)
    win_rate  = len(wins) / len(closed_trades) * 100 if closed_trades else 0.0
    ret_pct   = (final_equity - INITIAL_BALANCE_THB) / INITIAL_BALANCE_THB * 100

    summary = {
        "period_start"  : daily_log[0]["date"] if daily_log else "—",
        "period_end"    : daily_log[-1]["date"] if daily_log else "—",
        "days_run"      : len(daily_log),
        "total_trades"  : len(closed_trades),
        "wins"          : len(wins),
        "losses"        : len(losses),
        "win_rate"      : round(win_rate, 1),
        "total_pnl"     : round(total_pnl, 2),
        "initial"       : INITIAL_BALANCE_THB,
        "final_equity"  : round(final_equity, 2),
        "return_pct"    : round(ret_pct, 2),
    }

    print(f"\n{'='*65}")
    print("  BACKTEST RESULTS")
    print(f"{'='*65}")
    print(f"  Period       : {summary['period_start']} → {summary['period_end']}")
    print(f"  Days run     : {summary['days_run']}")
    print(f"  Closed trades: {summary['total_trades']}  (wins {summary['wins']}  losses {summary['losses']})")
    print(f"  Win rate     : {summary['win_rate']:.1f}%")
    print(f"  Total P&L    : ฿{summary['total_pnl']:+,.2f}")
    print(f"  Initial      : ฿{summary['initial']:,.2f}")
    print(f"  Final equity : ฿{summary['final_equity']:,.2f}")
    print(f"  Return       : {summary['return_pct']:+.2f}%")
    print(f"{'='*65}\n")

    return {
        "daily_log"     : daily_log,
        "closed_trades" : closed_trades,
        "summary"       : summary,
        "open_position" : open_position,
    }


if __name__ == "__main__":
    run_backtest()
