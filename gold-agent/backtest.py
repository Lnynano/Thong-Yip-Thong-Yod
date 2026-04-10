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

# ── Load .env so BACKTEST_MAX_CANDLES and other vars are available ────────────
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass  # python-dotenv not installed — rely on shell environment

# ── Constants — pulled from paper_engine.py to stay in sync ──────────────────
# Pull trading rules directly from paper_engine so backtest always matches live
try:
    from trader.paper_engine import (
        CONF_THRESHOLD   as CONFIDENCE_GATE,
        TAKE_PROFIT_PCT,
        STOP_LOSS_PCT,
        COOLDOWN_ROUNDS,
        TRADE_FEE_PCT,
        TRADE_FEE_FLAT_THB,
        DEFAULT_BALANCE  as INITIAL_BALANCE_THB,
        MIN_TRADE_THB    as MIN_BALANCE_THB,
    )
    POSITION_SIZE_PCT = 0.95   # matches paper_engine open logic (gross = balance * 0.95)
    print("[backtest] Loaded trading rules from paper_engine.py")
except ImportError:
    # Fallback if paper_engine can't be imported
    CONFIDENCE_GATE    = 65
    TAKE_PROFIT_PCT    = 0.015
    STOP_LOSS_PCT      = -0.010
    COOLDOWN_ROUNDS    = 2
    TRADE_FEE_PCT      = float(os.environ.get("TRADE_FEE_PCT", "0.005"))
    TRADE_FEE_FLAT_THB = float(os.environ.get("TRADE_FEE_FLAT_THB", "0"))
    INITIAL_BALANCE_THB = 1500.0
    MIN_BALANCE_THB    = 1000.0
    POSITION_SIZE_PCT  = 0.95
    print("[backtest] WARNING: could not import paper_engine — using fallback constants")

from converter.thai import THAI_GOLD_PURITY

USD_THB_RATE      = float(os.environ.get("USD_THB_RATE", "34.5"))  # env var, not hardcoded
TROY_OZ_GRAMS     = 31.1035
BAHT_WEIGHT_GRAMS = 15.244
PURITY            = THAI_GOLD_PURITY  # single source of truth
MIN_ROWS          = 20      # need 20 rows for Bollinger Bands(20)

# Cap candles to run so API costs stay predictable (override with env var)
MAX_CANDLES = int(os.environ.get("BACKTEST_MAX_CANDLES", "50"))


def usd_to_thb_per_bw(price_usd: float) -> float:
    """Convert USD/oz → THB per baht-weight (Thai 96.5% purity)."""
    thb_per_oz    = price_usd * USD_THB_RATE
    thb_per_gram  = thb_per_oz / TROY_OZ_GRAMS
    thb_per_bw    = thb_per_gram * BAHT_WEIGHT_GRAMS * PURITY
    return round(thb_per_bw, 2)


def _calc_fee(trade_value_thb: float) -> float:
    """Calculate total fee for a single transaction."""
    return round(trade_value_thb * TRADE_FEE_PCT + TRADE_FEE_FLAT_THB, 2)


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
    print(f"  Rate  : USD/THB = {USD_THB_RATE} (from env USD_THB_RATE)")
    print(f"  Capital: ฿{INITIAL_BALANCE_THB:,.0f}  |  Gate: {CONFIDENCE_GATE}% confidence")
    print(f"  TP: +{TAKE_PROFIT_PCT*100:.1f}%  |  SL: {STOP_LOSS_PCT*100:.1f}%  |  Cooldown: {COOLDOWN_ROUNDS} rounds")
    print(f"  Fees  : {TRADE_FEE_PCT*100:.2f}% per trade + ฿{TRADE_FEE_FLAT_THB:.0f} flat")
    print("=" * 65)

    # ── Paper trading state (in-memory, no portfolio.json touched) ────────────
    balance_thb    = INITIAL_BALANCE_THB
    open_position  = None
    closed_trades  = []
    daily_log      = []
    cooldown       = 0   # rounds before next BUY allowed (mirrors paper_engine)

    import data.fetch as fetch_module
    from agent.trading_agent import run_agent

    for i in range(MIN_ROWS - 1, len(df_full)):
        window     = df_full.iloc[: i + 1].copy()
        date       = df_full.index[i]
        price_usd  = float(window["Close"].iloc[-1])
        price_thb  = usd_to_thb_per_bw(price_usd)

        print(f"\n{'─'*65}")
        print(f"  Candle {i+1:3d} | {date} | ${price_usd:,.2f} | ฿{price_thb:,.0f}/bw"
              + (f"  [cooldown {cooldown}]" if cooldown > 0 else ""))
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

        # ── Step 1: Auto TP/SL — mirrors paper_engine exactly ────────────────
        if open_position is not None:
            change_pct = (price_thb - open_position["entry_price"]) / open_position["entry_price"]
            if change_pct >= TAKE_PROFIT_PCT:
                decision   = "SELL"
                confidence = 100
                print(f"  ** TAKE PROFIT triggered at {change_pct*100:+.2f}% (>= +{TAKE_PROFIT_PCT*100:.1f}%)")
            elif change_pct <= STOP_LOSS_PCT:
                decision   = "SELL"
                confidence = 100
                print(f"  ** STOP LOSS triggered at {change_pct*100:+.2f}% (<= {STOP_LOSS_PCT*100:.1f}%)")

        # ── Step 2: Confidence gate ───────────────────────────────────────────
        if confidence < CONFIDENCE_GATE:
            action = f"SKIP (confidence {confidence}% < {CONFIDENCE_GATE}%)"
            # tick down cooldown on skip too
            if cooldown > 0:
                cooldown -= 1

        # ── Step 3: Cooldown check (BUY only) ────────────────────────────────
        elif cooldown > 0 and decision == "BUY":
            action   = f"SKIP (cooldown {cooldown} rounds remaining)"
            cooldown -= 1
            print(f"  Cooldown: {cooldown} rounds remaining after this")

        # ── Step 4: BUY — open long ───────────────────────────────────────────
        elif decision == "BUY" and open_position is None:
            if balance_thb >= MIN_BALANCE_THB:
                gross    = round(balance_thb * POSITION_SIZE_PCT, 2)
                open_fee = _calc_fee(gross)
                cost     = round(gross + open_fee, 2)
                size_bw  = gross / price_thb
                balance_thb  -= cost
                open_position = {
                    "entry_date"  : str(date.date()),
                    "entry_price" : price_thb,
                    "size_bw"     : size_bw,
                    "cost_thb"    : gross,
                    "open_fee"    : open_fee,
                    "tp_price"    : round(price_thb * (1 + TAKE_PROFIT_PCT), 0),
                    "sl_price"    : round(price_thb * (1 + STOP_LOSS_PCT), 0),
                }
                cooldown = 0
                action   = "OPENED"
                print(f"  >> BUY executed  | gross ฿{gross:,.2f} | fee ฿{open_fee:.2f} | size {size_bw:.6f} bw")
                print(f"     TP @ ฿{open_position['tp_price']:,.0f}  |  SL @ ฿{open_position['sl_price']:,.0f}")
            else:
                action = f"SKIP (balance ฿{balance_thb:.0f} < min ฿{MIN_BALANCE_THB:.0f})"

        elif decision == "BUY" and open_position is not None:
            action = "SKIP (already holding)"

        # ── Step 5: SELL — close long ─────────────────────────────────────────
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
                "entry_date"  : open_position["entry_date"],
                "exit_date"   : str(date.date()),
                "entry_price" : open_position["entry_price"],
                "exit_price"  : price_thb,
                "size_bw"     : open_position["size_bw"],
                "cost_thb"    : open_position["cost_thb"],
                "open_fee"    : open_fee,
                "close_fee"   : close_fee,
                "total_fees"  : total_fees,
                "pnl_thb"     : pnl_thb,
                "pnl_pct"     : pnl_pct,
                "outcome"     : outcome,
            }
            closed_trades.append(trade)
            open_position = None
            cooldown      = COOLDOWN_ROUNDS   # start cooldown after close
            action        = f"CLOSED [{outcome}]"
            print(f"  >> SELL executed | net ฿{net_proceeds:,.2f} | fee ฿{total_fees:.2f} | P&L {pnl_thb:+.2f} ({pnl_pct:+.2f}%) [{outcome}]")
            print(f"     Cooldown started: {COOLDOWN_ROUNDS} rounds")

        elif decision == "SELL" and open_position is None:
            action = "SKIP (no position to sell)"
            if cooldown > 0:
                cooldown -= 1

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

    wins       = [t for t in closed_trades if t["outcome"] == "WIN"]
    losses     = [t for t in closed_trades if t["outcome"] == "LOSS"]
    total_pnl  = sum(t["pnl_thb"] for t in closed_trades)
    total_fees = sum(t.get("total_fees", 0.0) for t in closed_trades)
    win_rate   = len(wins) / len(closed_trades) * 100 if closed_trades else 0.0
    ret_pct    = (final_equity - INITIAL_BALANCE_THB) / INITIAL_BALANCE_THB * 100

    # Derive actual calendar days from date range
    candles_run   = len(daily_log)
    if daily_log:
        from datetime import datetime
        try:
            d0 = datetime.strptime(daily_log[0]["date"], "%Y-%m-%d")
            d1 = datetime.strptime(daily_log[-1]["date"], "%Y-%m-%d")
            calendar_days = (d1 - d0).days + 1
        except Exception:
            calendar_days = candles_run
    else:
        calendar_days = 0

    avg_win  = sum(t["pnl_thb"] for t in wins)   / len(wins)   if wins   else 0.0
    avg_loss = abs(sum(t["pnl_thb"] for t in losses)) / len(losses) if losses else 0.0
    rr_ratio = round(avg_win / avg_loss, 2) if avg_loss > 0 else 0.0

    summary = {
        "period_start"  : daily_log[0]["date"] if daily_log else "—",
        "period_end"    : daily_log[-1]["date"] if daily_log else "—",
        "candles_run"   : candles_run,
        "calendar_days" : calendar_days,
        "interval"      : interval_used,
        "days_run"      : candles_run,   # kept for dashboard compatibility
        "total_trades"  : len(closed_trades),
        "wins"          : len(wins),
        "losses"        : len(losses),
        "win_rate"      : round(win_rate, 1),
        "total_pnl"     : round(total_pnl, 2),
        "total_fees"    : round(total_fees, 2),
        "initial"       : INITIAL_BALANCE_THB,
        "final_equity"  : round(final_equity, 2),
        "return_pct"    : round(ret_pct, 2),
        "avg_win"       : round(avg_win, 2),
        "avg_loss"      : round(avg_loss, 2),
        "rr_ratio"      : rr_ratio,
        # Rules used — for transparency in results
        "rules"         : {
            "confidence_gate" : CONFIDENCE_GATE,
            "take_profit_pct" : TAKE_PROFIT_PCT * 100,
            "stop_loss_pct"   : STOP_LOSS_PCT   * 100,
            "cooldown_rounds" : COOLDOWN_ROUNDS,
            "fee_pct"         : TRADE_FEE_PCT   * 100,
            "position_size"   : POSITION_SIZE_PCT * 100,
            "usd_thb_rate"    : USD_THB_RATE,
        },
    }

    print(f"\n{'='*65}")
    print("  BACKTEST RESULTS  (rules match live paper_engine.py)")
    print(f"{'='*65}")
    print(f"  Period       : {summary['period_start']} → {summary['period_end']}  ({calendar_days} calendar days)")
    print(f"  Candles run  : {candles_run} x {interval_used} bars")
    print(f"  Rules        : gate={CONFIDENCE_GATE}%  TP=+{TAKE_PROFIT_PCT*100:.1f}%  SL={STOP_LOSS_PCT*100:.1f}%  cooldown={COOLDOWN_ROUNDS}")
    print(f"  Closed trades: {summary['total_trades']}  (wins {summary['wins']}  losses {summary['losses']})")
    print(f"  Win rate     : {summary['win_rate']:.1f}%")
    print(f"  Avg win      : ฿{avg_win:+.2f}  |  Avg loss : ฿{avg_loss:.2f}  |  R:R {rr_ratio:.2f}")
    print(f"  Total fees   : ฿{summary['total_fees']:,.2f}")
    print(f"  Total P&L    : ฿{summary['total_pnl']:+,.2f}  (net of fees)")
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
