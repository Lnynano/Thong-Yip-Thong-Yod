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
    - Results saved to data/backtest_log.csv and data/backtest_trades.csv
"""

import sys
import os
import csv
import pandas as pd
from datetime import datetime
from unittest.mock import patch

# ── Path setup ───────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Load .env so BACKTEST_MAX_CANDLES and other vars are available ────────────
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

# ── Constants — pulled from paper_engine.py to stay in sync ──────────────────
try:
    from trader.paper_engine import (
        CONF_THRESHOLD   as CONFIDENCE_GATE,
        TAKE_PROFIT_PCT,
        STOP_LOSS_PCT,
        TRAILING_SL_PCT,
        COOLDOWN_ROUNDS,
        LOSS_COOLDOWN,
        TRADE_FEE_PCT,
        TRADE_FEE_FLAT_THB,
        DEFAULT_BALANCE  as INITIAL_BALANCE_THB,
        MIN_TRADE_THB    as MIN_BALANCE_THB,
        _size_pct_by_confidence,
    )
except ImportError:
    CONFIDENCE_GATE    = 65
    TAKE_PROFIT_PCT    = 0.015
    STOP_LOSS_PCT      = -0.010
    TRAILING_SL_PCT    = 0.007
    COOLDOWN_ROUNDS    = 0
    LOSS_COOLDOWN      = 1
    TRADE_FEE_PCT      = float(os.environ.get("TRADE_FEE_PCT", "0.005"))
    TRADE_FEE_FLAT_THB = float(os.environ.get("TRADE_FEE_FLAT_THB", "0"))
    INITIAL_BALANCE_THB = 1500.0
    MIN_BALANCE_THB    = 1000.0
    def _size_pct_by_confidence(conf):
        if conf >= 85: return 0.95
        elif conf >= 75: return 0.80
        else: return 0.60

from converter.thai import THAI_GOLD_PURITY

USD_THB_RATE      = float(os.environ.get("USD_THB_RATE", "34.5"))
TROY_OZ_GRAMS     = 31.1035
BAHT_WEIGHT_GRAMS = 15.244
PURITY            = THAI_GOLD_PURITY
MIN_ROWS          = 20
MAX_CANDLES       = int(os.environ.get("BACKTEST_MAX_CANDLES", "50"))

# ── Log file paths ────────────────────────────────────────────────────────────
_DATA_DIR      = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
_CANDLE_LOG    = os.path.join(_DATA_DIR, "backtest_log.csv")
_TRADE_LOG     = os.path.join(_DATA_DIR, "backtest_trades.csv")


# ── Helpers ───────────────────────────────────────────────────────────────────

def usd_to_thb_per_bw(price_usd: float) -> float:
    thb_per_oz   = price_usd * USD_THB_RATE
    thb_per_gram = thb_per_oz / TROY_OZ_GRAMS
    return round(thb_per_gram * BAHT_WEIGHT_GRAMS * PURITY, 2)


def _calc_fee(trade_value_thb: float) -> float:
    return round(trade_value_thb * TRADE_FEE_PCT + TRADE_FEE_FLAT_THB, 2)


def _bar(value: float, max_val: float, width: int = 20, fill: str = "#") -> str:
    """Simple ASCII progress bar."""
    if max_val == 0:
        return fill * 0
    filled = int(round(value / max_val * width))
    filled = max(0, min(filled, width))
    return fill * filled + "." * (width - filled)


def _write_candle_log(rows: list[dict]) -> None:
    """Write per-candle log to CSV."""
    if not rows:
        return
    os.makedirs(_DATA_DIR, exist_ok=True)
    fieldnames = ["candle", "date", "price_usd", "price_thb", "decision",
                  "confidence", "action", "pnl_thb", "equity_thb",
                  "llm_cost_thb", "cumulative_llm_cost_thb"]
    with open(_CANDLE_LOG, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_trade_log(trades: list[dict]) -> None:
    """Write closed trades to CSV."""
    if not trades:
        return
    os.makedirs(_DATA_DIR, exist_ok=True)
    fieldnames = ["trade_no", "entry_date", "exit_date", "entry_price",
                  "exit_price", "size_bw", "cost_thb", "open_fee",
                  "close_fee", "total_fees", "pnl_thb", "pnl_pct", "outcome"]
    with open(_TRADE_LOG, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for idx, t in enumerate(trades, 1):
            writer.writerow({"trade_no": idx, **t})


# ── Main backtest ─────────────────────────────────────────────────────────────

def run_backtest() -> dict:
    """
    Run the backtest and return structured results.

    Returns:
        dict: {
            "daily_log"     : list of per-candle records,
            "closed_trades" : list of completed trades,
            "summary"       : dict of key performance metrics,
            "open_position" : dict or None,
        }
    """
    import yfinance as yf

    # ── Cost tracker (backtest session only — separate from live costs) ────────
    _session_cost_usd = 0.0
    _session_cost_thb = 0.0
    _session_calls    = 0

    def _track_cost(usage, source: str = "backtest") -> float:
        """Track API cost for this backtest session (does NOT persist to llm_costs.json)."""
        nonlocal _session_cost_usd, _session_cost_thb, _session_calls
        if usage is None:
            return 0.0
        inp  = getattr(usage, "prompt_tokens",     0) or 0
        out  = getattr(usage, "completion_tokens", 0) or 0
        cost_usd = inp * (0.150 / 1_000_000) + out * (0.600 / 1_000_000)
        cost_thb = cost_usd * USD_THB_RATE
        _session_cost_usd += cost_usd
        _session_cost_thb += cost_thb
        _session_calls    += 1
        return cost_thb

    # ── Fetch data ────────────────────────────────────────────────────────────
    df_full       = None
    interval_used = ""

    print("")
    print("  Fetching price data from yfinance...")
    try:
        raw = yf.download("GC=F", period="60d", interval="1h", progress=False, auto_adjust=True)
        if not raw.empty and len(raw) >= MIN_ROWS + 5:
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            raw.index.name = "Date"
            df_full = raw[["Open", "High", "Low", "Close", "Volume"]].dropna()
            interval_used = "1h"
    except Exception as e:
        print(f"  1h fetch failed ({e}), trying daily...")

    if df_full is None or len(df_full) < MIN_ROWS + 5:
        try:
            raw = yf.download("GC=F", period="6mo", interval="1d", progress=False, auto_adjust=True)
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            raw.index.name = "Date"
            df_full = raw[["Open", "High", "Low", "Close", "Volume"]].dropna()
            interval_used = "1d"
        except Exception as e:
            return {"daily_log": [], "closed_trades": [], "open_position": None,
                    "summary": {"error": str(e)}}

    if df_full is None or df_full.empty:
        return {"daily_log": [], "closed_trades": [], "open_position": None,
                "summary": {"error": "No data fetched"}}

    if len(df_full) > MIN_ROWS + MAX_CANDLES:
        df_full = df_full.iloc[-(MIN_ROWS + MAX_CANDLES):]

    total_candles = len(df_full) - MIN_ROWS + 1

    # ── Header ────────────────────────────────────────────────────────────────
    print("")
    print("=" * 60)
    print("  GOLD AGENT BACKTEST")
    print("=" * 60)
    print(f"  Period   : {df_full.index[MIN_ROWS-1].date()} -> {df_full.index[-1].date()}")
    print(f"  Interval : {interval_used}  |  Candles : {total_candles}")
    print(f"  Capital  : B{INITIAL_BALANCE_THB:,.0f}  |  Gate : {CONFIDENCE_GATE}%  |  TP : +{TAKE_PROFIT_PCT*100:.1f}%  SL : {STOP_LOSS_PCT*100:.1f}%")
    print("=" * 60)
    print("")

    # ── State ─────────────────────────────────────────────────────────────────
    balance_thb   = INITIAL_BALANCE_THB
    open_position = None
    closed_trades = []
    daily_log     = []
    cooldown      = 0
    cum_llm_cost  = 0.0

    import data.fetch as fetch_module
    from agent.trading_agent import run_agent

    # Patch run_agent to capture usage for cost tracking
    _orig_run_agent = run_agent

    for i in range(MIN_ROWS - 1, len(df_full)):
        window    = df_full.iloc[: i + 1].copy()
        date      = df_full.index[i]
        price_usd = float(window["Close"].iloc[-1])
        price_thb = usd_to_thb_per_bw(price_usd)
        candle_no = i - MIN_ROWS + 2

        # Progress indicator
        pct_done = candle_no / total_candles * 100
        bar      = _bar(candle_no, total_candles, width=30)
        status   = f"[{bar}] {candle_no}/{total_candles} ({pct_done:.0f}%)"
        print(f"\r  Running {status}  B{balance_thb:,.0f}", end="", flush=True)

        with patch.object(fetch_module, "get_gold_price", return_value=window):
            agent = run_agent()

        # Track API cost from agent response if available
        candle_cost_thb = 0.0
        if hasattr(agent, "_usage"):
            candle_cost_thb = _track_cost(agent._usage, "backtest")
        cum_llm_cost += candle_cost_thb

        decision   = agent["decision"]
        confidence = agent["confidence"]
        reasoning  = agent["reasoning"]
        action     = "HOLD"
        pnl_thb    = 0.0

        # ── TP / Trailing stop / SL ───────────────────────────────────────────
        if open_position is not None:
            change_pct = (price_thb - open_position["entry_price"]) / open_position["entry_price"]
            if change_pct >= TAKE_PROFIT_PCT:
                decision   = "SELL"
                confidence = 100
            highest = max(open_position.get("highest_price", open_position["entry_price"]), price_thb)
            open_position["highest_price"] = highest
            trailing_sl_price = highest * (1 - TRAILING_SL_PCT)
            if price_thb <= trailing_sl_price and highest > open_position["entry_price"]:
                decision   = "SELL"
                confidence = 100
            elif change_pct <= STOP_LOSS_PCT:
                decision   = "SELL"
                confidence = 100

        # ── Gate / Cooldown ───────────────────────────────────────────────────
        if confidence < CONFIDENCE_GATE:
            action = "SKIP"
            if cooldown > 0:
                cooldown -= 1

        elif cooldown > 0 and decision == "BUY":
            action   = "SKIP"
            cooldown -= 1

        # ── BUY ───────────────────────────────────────────────────────────────
        elif decision == "BUY" and open_position is None:
            if balance_thb >= MIN_BALANCE_THB:
                size_pct = _size_pct_by_confidence(confidence)
                gross    = round(balance_thb * size_pct, 2)
                open_fee = _calc_fee(gross)
                cost     = round(gross + open_fee, 2)
                size_bw  = gross / price_thb
                balance_thb  -= cost
                open_position = {
                    "entry_date"   : str(date.date()),
                    "entry_price"  : price_thb,
                    "highest_price": price_thb,
                    "size_bw"      : size_bw,
                    "cost_thb"     : gross,
                    "open_fee"     : open_fee,
                    "tp_price"     : round(price_thb * (1 + TAKE_PROFIT_PCT), 0),
                    "sl_price"     : round(price_thb * (1 + STOP_LOSS_PCT), 0),
                    "confidence"   : confidence,
                    "size_pct"     : size_pct,
                }
                cooldown = 0
                action   = "OPENED"
            else:
                action = "SKIP"

        elif decision == "BUY" and open_position is not None:
            action = "SKIP"

        # ── SELL ──────────────────────────────────────────────────────────────
        elif decision == "SELL" and open_position is not None:
            gross_proceeds = open_position["size_bw"] * price_thb
            close_fee      = _calc_fee(gross_proceeds)
            open_fee       = open_position.get("open_fee", 0.0)
            net_proceeds   = round(gross_proceeds - close_fee, 2)
            total_fees     = round(open_fee + close_fee, 2)
            pnl_thb        = round(net_proceeds - open_position["cost_thb"], 2)
            pnl_pct        = round(pnl_thb / open_position["cost_thb"] * 100, 2)
            outcome        = "WIN" if pnl_thb >= 0 else "LOSS"
            balance_thb   += net_proceeds
            trade = {
                "entry_date" : open_position["entry_date"],
                "exit_date"  : str(date.date()),
                "entry_price": open_position["entry_price"],
                "exit_price" : price_thb,
                "size_bw"    : round(open_position["size_bw"], 6),
                "cost_thb"   : open_position["cost_thb"],
                "open_fee"   : open_fee,
                "close_fee"  : close_fee,
                "total_fees" : total_fees,
                "pnl_thb"    : pnl_thb,
                "pnl_pct"    : pnl_pct,
                "outcome"    : outcome,
            }
            closed_trades.append(trade)
            open_position = None
            cooldown      = LOSS_COOLDOWN if outcome == "LOSS" else COOLDOWN_ROUNDS
            action        = f"CLOSED [{outcome}]"

        elif decision == "SELL" and open_position is None:
            action = "SKIP"
            if cooldown > 0:
                cooldown -= 1

        unrealized = 0.0
        if open_position:
            unrealized = (open_position["size_bw"] * price_thb) - open_position["cost_thb"]
        equity = round(balance_thb + (open_position["size_bw"] * price_thb if open_position else 0), 2)

        daily_log.append({
            "candle"                : candle_no,
            "date"                  : str(date.date()),
            "price_usd"             : price_usd,
            "price_thb"             : price_thb,
            "decision"              : decision,
            "confidence"            : confidence,
            "action"                : action,
            "pnl_thb"               : pnl_thb,
            "equity_thb"            : equity,
            "llm_cost_thb"          : round(candle_cost_thb, 4),
            "cumulative_llm_cost_thb": round(cum_llm_cost, 4),
        })

    # Clear progress line
    print("\r" + " " * 70 + "\r", end="")

    # ── Summary calculations ──────────────────────────────────────────────────
    last_price_thb = daily_log[-1]["price_thb"] if daily_log else 0
    final_equity   = balance_thb
    if open_position:
        final_equity += open_position["size_bw"] * last_price_thb

    wins       = [t for t in closed_trades if t["outcome"] == "WIN"]
    losses     = [t for t in closed_trades if t["outcome"] == "LOSS"]
    total_pnl  = sum(t["pnl_thb"] for t in closed_trades)
    total_fees = sum(t.get("total_fees", 0.0) for t in closed_trades)
    win_rate   = len(wins) / len(closed_trades) * 100 if closed_trades else 0.0
    ret_pct    = (final_equity - INITIAL_BALANCE_THB) / INITIAL_BALANCE_THB * 100
    candles_run = len(daily_log)

    try:
        d0 = datetime.strptime(daily_log[0]["date"], "%Y-%m-%d")
        d1 = datetime.strptime(daily_log[-1]["date"], "%Y-%m-%d")
        calendar_days = (d1 - d0).days + 1
    except Exception:
        calendar_days = candles_run

    avg_win  = sum(t["pnl_thb"] for t in wins) / len(wins) if wins else 0.0
    avg_loss = abs(sum(t["pnl_thb"] for t in losses)) / len(losses) if losses else 0.0
    rr_ratio = round(avg_win / avg_loss, 2) if avg_loss > 0 else 0.0

    first_price_thb = daily_log[0]["price_thb"] if daily_log else 0
    if first_price_thb > 0 and last_price_thb > 0:
        bah_size_bw    = (INITIAL_BALANCE_THB * 0.95) / first_price_thb
        bah_final      = bah_size_bw * last_price_thb
        bah_pnl        = bah_final - (INITIAL_BALANCE_THB * 0.95)
        bah_return_pct = round(bah_pnl / INITIAL_BALANCE_THB * 100, 2)
    else:
        bah_pnl        = 0.0
        bah_return_pct = 0.0
    agent_alpha = round(ret_pct - bah_return_pct, 2)

    # ── Save logs ─────────────────────────────────────────────────────────────
    _write_candle_log(daily_log)
    _write_trade_log(closed_trades)

    # ── Pretty results ────────────────────────────────────────────────────────
    ret_sign  = "+" if ret_pct >= 0 else ""
    bah_sign  = "+" if bah_return_pct >= 0 else ""
    alp_sign  = "+" if agent_alpha >= 0 else ""
    pnl_sign  = "+" if total_pnl >= 0 else ""

    # Win/loss bar (max 20 chars)
    win_bar  = "#" * min(len(wins), 20)
    loss_bar = "x" * min(len(losses), 20)

    print("=" * 60)
    print("  BACKTEST COMPLETE")
    print("=" * 60)
    print(f"  Period     : {daily_log[0]['date'] if daily_log else '?'}  ->  {daily_log[-1]['date'] if daily_log else '?'}  ({calendar_days}d)")
    print(f"  Candles    : {candles_run} x {interval_used}  |  Trades : {len(closed_trades)}")
    print("")
    print("  PERFORMANCE")
    print(f"  {'Return':<14}: {ret_sign}{ret_pct:.2f}%   (B{INITIAL_BALANCE_THB:,.0f} -> B{final_equity:,.2f})")
    print(f"  {'Total P&L':<14}: {pnl_sign}B{total_pnl:,.2f}   Fees: B{total_fees:,.2f}")
    print("")
    print("  TRADE STATS")
    print(f"  {'Win Rate':<14}: {win_rate:.1f}%   ({len(wins)} wins / {len(losses)} losses)")
    print(f"  {'Wins':<14}: {win_bar}  avg B{avg_win:+.2f}")
    print(f"  {'Losses':<14}: {loss_bar}  avg B{avg_loss:.2f}")
    print(f"  {'R:R Ratio':<14}: {rr_ratio:.2f}")
    print("")
    print("  vs BUY-AND-HOLD")
    print(f"  {'Agent':<14}: {ret_sign}{ret_pct:.2f}%")
    print(f"  {'Buy & Hold':<14}: {bah_sign}{bah_return_pct:.2f}%")
    alpha_label = "AGENT WINS" if agent_alpha > 0 else "B&H WINS"
    print(f"  {'Alpha':<14}: {alp_sign}{agent_alpha:.2f}%  [{alpha_label}]")
    print("")
    print("  API COST (this run)")
    print(f"  {'Calls':<14}: {_session_calls}")
    print(f"  {'Cost USD':<14}: ${_session_cost_usd:.4f}")
    print(f"  {'Cost THB':<14}: B{_session_cost_thb:.4f}")
    print("")
    print("  LOGS SAVED")
    print(f"  Candle log  : data/backtest_log.csv    ({len(daily_log)} rows)")
    print(f"  Trade log   : data/backtest_trades.csv ({len(closed_trades)} trades)")
    print("=" * 60)
    print("")

    summary = {
        "period_start"     : daily_log[0]["date"] if daily_log else "—",
        "period_end"       : daily_log[-1]["date"] if daily_log else "—",
        "candles_run"      : candles_run,
        "calendar_days"    : calendar_days,
        "interval"         : interval_used,
        "days_run"         : candles_run,
        "total_trades"     : len(closed_trades),
        "wins"             : len(wins),
        "losses"           : len(losses),
        "win_rate"         : round(win_rate, 1),
        "total_pnl"        : round(total_pnl, 2),
        "total_fees"       : round(total_fees, 2),
        "initial"          : INITIAL_BALANCE_THB,
        "final_equity"     : round(final_equity, 2),
        "return_pct"       : round(ret_pct, 2),
        "avg_win"          : round(avg_win, 2),
        "avg_loss"         : round(avg_loss, 2),
        "rr_ratio"         : rr_ratio,
        "bah_return_pct"   : bah_return_pct,
        "agent_alpha"      : agent_alpha,
        "llm_cost_usd"     : round(_session_cost_usd, 6),
        "llm_cost_thb"     : round(_session_cost_thb, 4),
        "llm_calls"        : _session_calls,
        "rules": {
            "confidence_gate" : CONFIDENCE_GATE,
            "take_profit_pct" : TAKE_PROFIT_PCT * 100,
            "stop_loss_pct"   : STOP_LOSS_PCT   * 100,
            "cooldown_rounds" : COOLDOWN_ROUNDS,
            "fee_pct"         : TRADE_FEE_PCT   * 100,
            "trailing_sl_pct" : TRAILING_SL_PCT  * 100,
            "usd_thb_rate"    : USD_THB_RATE,
        },
    }

    return {
        "daily_log"     : daily_log,
        "closed_trades" : closed_trades,
        "summary"       : summary,
        "open_position" : open_position,
    }


if __name__ == "__main__":
    run_backtest()
