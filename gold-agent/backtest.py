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
import logging
import pandas as pd
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import patch


@contextmanager
def _quiet():
    """Suppress all stdout, stderr, and logging during a block."""
    import io
    # Silence logging
    logging.disable(logging.CRITICAL)
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = io.StringIO()
    sys.stderr = io.StringIO()
    try:
        yield
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        logging.disable(logging.NOTSET)


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

CONFIDENCE_GATE = 65  # Overridden for comparison

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
                  "confidence", "action", "window", "pnl_thb", "equity_thb"]
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

def run_backtest(config: dict | None = None, use_cache: bool = True) -> dict:
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
    import time
    import yfinance as yf
    from logger.cost_tracker import get_cost_summary as _get_cost_summary

    # ── Timer ────────────────────────────────────────────────────────────────
    _start_time = time.time()

    # ── Cost tracker: snapshot before run, diff after ─────────────────────────
    _cost_before = _get_cost_summary()

    # ── Fetch data ────────────────────────────────────────────────────────────
    df_full       = None
    interval_used = ""

    print("")
    print("  Fetching price data...")
    try:
        with _quiet():
            raw = yf.download("GC=F", period="60d", interval="1h", progress=False, auto_adjust=True)
        if not raw.empty and len(raw) >= MIN_ROWS + 5:
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            raw.index.name = "Date"
            df_full = raw[["Open", "High", "Low", "Close", "Volume"]].dropna()
            interval_used = "1h"
    except Exception as e:
        pass  # try daily below

    if df_full is None or len(df_full) < MIN_ROWS + 5:
        try:
            with _quiet():
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
    _cfg = config or {}
    _flag_names = ["use_macd", "use_bb", "use_news", "use_dxy_vix", "use_h1_mtf", "use_daily_bias", "use_volume_spike"]
    _on  = [f for f in _flag_names if _cfg.get(f, True)]
    _off = [f for f in _flag_names if not _cfg.get(f, True)]

    print("")
    print("=" * 60)
    print("  GOLD AGENT BACKTEST")
    print("=" * 60)
    print(f"  Period   : {df_full.index[MIN_ROWS-1].date()} -> {df_full.index[-1].date()}")
    print(f"  Interval : {interval_used}  |  Candles : {total_candles}")
    print(f"  Capital  : B{INITIAL_BALANCE_THB:,.0f}  |  Gate : {CONFIDENCE_GATE}%  |  TP : +{TAKE_PROFIT_PCT*100:.1f}%  SL : {STOP_LOSS_PCT*100:.1f}%")
    print(f"  Cache    : {'YES (same price data)' if use_cache else 'NO (fresh fetch)'}")
    print(f"  ON  ({len(_on)}) : {', '.join(_on) if _on else '—'}")
    print(f"  OFF ({len(_off)}) : {', '.join(_off) if _off else '—'}")
    print("=" * 60)
    print("")

    # ── State ─────────────────────────────────────────────────────────────────
    balance_thb   = INITIAL_BALANCE_THB
    open_positions = []
    closed_trades = []
    daily_log     = []
    cooldown      = 0

    # ── Window tracking (mirrors trade_scheduler.py rules) ───────────────────
    from trader.trade_scheduler import _WEEKDAY_LOGICAL, _WEEKEND_LOGICAL
    import datetime as _dt
    _THAI_TZ = _dt.timezone(_dt.timedelta(hours=7))

    def _to_thai(dt):
        """Convert candle timestamp to Thai time, assuming UTC if tz-naive."""
        try:
            return dt.astimezone(_THAI_TZ)
        except Exception:
            return dt.replace(tzinfo=_dt.timezone.utc).astimezone(_THAI_TZ)

    def _get_candle_window(dt) -> str | None:
        """Return window name if candle falls inside a valid trading window, else None."""
        local   = _to_thai(dt)
        minutes = local.hour * 60 + local.minute
        windows = _WEEKEND_LOGICAL if local.weekday() >= 5 else _WEEKDAY_LOGICAL
        for w in windows:
            for start, end in w["ranges"]:
                if start <= minutes <= end:
                    return w["name"]
        return None

    def _minutes_until_window_end(dt) -> int | None:
        """Return minutes remaining in the candle's trading window, or None if outside."""
        local   = _to_thai(dt)
        minutes = local.hour * 60 + local.minute
        windows = _WEEKEND_LOGICAL if local.weekday() >= 5 else _WEEKDAY_LOGICAL
        for w in windows:
            for start, end in w["ranges"]:
                if start <= minutes <= end:
                    return end - minutes
        return None

    def _thai_date_str(dt) -> str:
        """Return Thai-timezone date string for grouping window trades."""
        return str(_to_thai(dt).date())

    # window_trades[date][window_name] = count
    _window_trades: dict = {}

    import data.fetch as fetch_module
    from agent.trading_agent import run_agent

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

        # ── Window gate — only run agent inside valid trading windows ────────
        candle_window = _get_candle_window(date)
        if candle_window is None:
            daily_log.append({
                "candle"    : candle_no,
                "date"      : _to_thai(date).strftime("%Y-%m-%d %H:%M"),
                "price_usd" : price_usd,
                "price_thb" : price_thb,
                "decision"  : "HOLD",
                "confidence": 0,
                "action"    : "OUT_OF_WINDOW",
                "pnl_thb"   : 0.0,
                "equity_thb": round(balance_thb + sum(p["size_bw"] * price_thb for p in open_positions), 2),
            })
            continue

        # Quota pressure: check if this window still needs trades
        date_str_today = _thai_date_str(date)
        _window_trades.setdefault(date_str_today, {})
        _window_used = _window_trades[date_str_today].get(candle_window, 0)
        _quota_pressure = _window_used < 2  # min 2 per window

        with _quiet(), patch.object(fetch_module, "get_gold_price", return_value=window):
            agent = run_agent(quota_pressure=_quota_pressure, config=config)

        decision   = agent["decision"]
        confidence = agent["confidence"]
        reasoning  = agent["reasoning"]
        action     = "HOLD"
        pnl_thb    = 0.0

        # ── TP / Trailing stop / SL ───────────────────────────────────────────
        for pos in open_positions:
            change_pct = (price_thb - pos["entry_price"]) / pos["entry_price"]
            highest = max(pos.get("highest_price", pos["entry_price"]), price_thb)
            pos["highest_price"] = highest
            trailing_sl_price = highest * (1 - TRAILING_SL_PCT)
            if change_pct >= TAKE_PROFIT_PCT or change_pct <= STOP_LOSS_PCT or (price_thb <= trailing_sl_price and highest > pos["entry_price"]):
                decision   = "SELL"
                confidence = 100
                break

        # ── Failsafe: window ending in ≤60 min, quota not met, still HOLD ────
        _mins_left = _minutes_until_window_end(date)
        if (decision == "HOLD" and
                _mins_left is not None and _mins_left <= 60 and
                _window_used < 2):
            with _quiet(), patch.object(fetch_module, "get_gold_price", return_value=window):
                agent = run_agent(quota_pressure=True, failsafe_pressure=True, config=config)
            decision   = agent["decision"]
            confidence = agent["confidence"]
            reasoning  = agent["reasoning"]
            if decision == "HOLD":
                decision   = "BUY"
                confidence = 51
                reasoning  = "[FAILSAFE] Window closing, quota not met. Forced BUY signal."

        # ── Count BUY/SELL decision toward window quota ───────────────────────
        if decision in ("BUY", "SELL"):
            date_str = _thai_date_str(date)
            _window_trades.setdefault(date_str, {})
            _window_trades[date_str][candle_window] = _window_trades[date_str].get(candle_window, 0) + 1

        # ── Gate / Cooldown ───────────────────────────────────────────────────
        _effective_gate = 50 if _quota_pressure else CONFIDENCE_GATE
        if confidence < _effective_gate:
            action = "SKIP"
            if cooldown > 0:
                cooldown -= 1

        elif cooldown > 0 and decision == "BUY":
            action   = "SKIP"
            cooldown -= 1

        # ── BUY ───────────────────────────────────────────────────────────────
        elif decision == "BUY":
            if balance_thb >= MIN_BALANCE_THB:
                size_pct = _size_pct_by_confidence(confidence)
                gross    = round(balance_thb * size_pct, 2)
                open_fee = _calc_fee(gross)
                cost     = round(gross + open_fee, 2)
                size_bw  = gross / price_thb
                balance_thb  -= cost
                open_positions.append({
                    "entry_date"   : _to_thai(date).strftime("%Y-%m-%d %H:%M"),
                    "entry_price"  : price_thb,
                    "highest_price": price_thb,
                    "size_bw"      : size_bw,
                    "cost_thb"     : gross,
                    "open_fee"     : open_fee,
                    "tp_price"     : round(price_thb * (1 + TAKE_PROFIT_PCT), 0),
                    "sl_price"     : round(price_thb * (1 + STOP_LOSS_PCT), 0),
                    "confidence"   : confidence,
                    "size_pct"     : size_pct,
                })
                cooldown = 0
                action   = "OPENED"
            else:
                action = "SKIP"

        # ── SELL ──────────────────────────────────────────────────────────────
        elif decision == "SELL" and open_positions:
            total_pnl_thb = 0.0
            any_loss = False
            for pos in open_positions:
                gross_proceeds = pos["size_bw"] * price_thb
                close_fee      = _calc_fee(gross_proceeds)
                open_fee       = pos.get("open_fee", 0.0)
                net_proceeds   = round(gross_proceeds - close_fee, 2)
                total_fees     = round(open_fee + close_fee, 2)
                pos_pnl_thb    = round(net_proceeds - pos["cost_thb"], 2)
                pnl_pct        = round(pos_pnl_thb / pos["cost_thb"] * 100, 2)
                outcome        = "WIN" if pos_pnl_thb >= 0 else "LOSS"
                if pos_pnl_thb < 0: any_loss = True
                total_pnl_thb += pos_pnl_thb
                balance_thb   += net_proceeds
                trade = {
                    "entry_date" : pos["entry_date"],
                    "exit_date"  : _to_thai(date).strftime("%Y-%m-%d %H:%M"),
                    "entry_price": pos["entry_price"],
                    "exit_price" : price_thb,
                    "size_bw"    : round(pos["size_bw"], 6),
                    "cost_thb"   : pos["cost_thb"],
                    "open_fee"   : open_fee,
                    "close_fee"  : close_fee,
                    "total_fees" : total_fees,
                    "pnl_thb"    : pos_pnl_thb,
                    "pnl_pct"    : pnl_pct,
                    "outcome"    : outcome,
                }
                closed_trades.append(trade)
            open_positions = []
            pnl_thb = total_pnl_thb
            cooldown = LOSS_COOLDOWN if any_loss else COOLDOWN_ROUNDS
            action = "CLOSED [BASKET]"

        elif decision == "SELL" and not open_positions:
            action = "SKIP"
            if cooldown > 0:
                cooldown -= 1

        unrealized = sum((p["size_bw"] * price_thb) - p["cost_thb"] for p in open_positions)
        equity = round(balance_thb + sum(p["size_bw"] * price_thb for p in open_positions), 2)

        daily_log.append({
            "candle"    : candle_no,
            "date"      : _to_thai(date).strftime("%Y-%m-%d %H:%M"),
            "price_usd" : price_usd,
            "price_thb" : price_thb,
            "decision"  : decision,
            "confidence": confidence,
            "action"    : action,
            "window"    : candle_window,
            "pnl_thb"   : pnl_thb,
            "equity_thb": equity,
        })

    # Clear progress line
    print("\r" + " " * 70 + "\r", end="")

    # ── Summary calculations ──────────────────────────────────────────────────
    last_price_thb = daily_log[-1]["price_thb"] if daily_log else 0
    final_equity   = balance_thb
    for pos in open_positions:
        final_equity += pos["size_bw"] * last_price_thb

    wins       = [t for t in closed_trades if t["outcome"] == "WIN"]
    losses     = [t for t in closed_trades if t["outcome"] == "LOSS"]
    total_pnl  = sum(t["pnl_thb"] for t in closed_trades)
    total_fees = sum(t.get("total_fees", 0.0) for t in closed_trades)
    win_rate   = len(wins) / len(closed_trades) * 100 if closed_trades else 0.0
    ret_pct    = (final_equity - INITIAL_BALANCE_THB) / INITIAL_BALANCE_THB * 100
    candles_run = len(daily_log)

    try:
        d0 = datetime.strptime(daily_log[0]["date"], "%Y-%m-%d %H:%M")
        d1 = datetime.strptime(daily_log[-1]["date"], "%Y-%m-%d %H:%M")
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

    # ── Cost delta + timer ────────────────────────────────────────────────────
    _cost_after    = _get_cost_summary()
    _session_calls = _cost_after["call_count"]     - _cost_before["call_count"]
    _session_usd   = round(_cost_after["total_cost_usd"] - _cost_before["total_cost_usd"], 6)
    _session_thb   = round(_cost_after["total_cost_thb"] - _cost_before["total_cost_thb"], 4)
    _elapsed       = time.time() - _start_time
    _mins, _secs   = divmod(int(_elapsed), 60)

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
    # ── Window compliance ─────────────────────────────────────────────────────
    trading_days   = [d for d in _window_trades]
    days_compliant = 0
    days_total     = len(trading_days)
    for day, windows in _window_trades.items():
        is_weekday      = datetime.strptime(day, "%Y-%m-%d").weekday() < 5
        min_required    = 6 if is_weekday else 2
        total_day_trades = sum(windows.values())
        if total_day_trades >= min_required:
            days_compliant += 1

    print("  WINDOW COMPLIANCE")
    print(f"  {'Min trades/day':<14}: weekday=6 (2x3 windows)  weekend=2 (1 window)")
    if trading_days:
        print(f"  {'Days traded':<14}: {days_total}")
        print(f"  {'Days met quota':<14}: {days_compliant}/{days_total}", end="")
        print(f"  {'[OK]' if days_compliant == days_total else '[BELOW QUOTA]'}")
        for day, windows in sorted(_window_trades.items()):
            is_weekday   = datetime.strptime(day, "%Y-%m-%d").weekday() < 5
            min_required = 6 if is_weekday else 2
            total        = sum(windows.values())
            marker       = "[OK]" if total >= min_required else f"[NEED {min_required - total} MORE]"
            win_str      = "  ".join(f"{k}:{v}" for k, v in windows.items())
            print(f"    {day}  {win_str:<30} total={total} {marker}")
    else:
        print("  No trades recorded in any window.")
    print("")
    print("  API COST (this run)")
    print(f"  {'Calls':<14}: {_session_calls}")
    print(f"  {'Cost USD':<14}: ${_session_usd:.4f}")
    print(f"  {'Cost THB':<14}: B{_session_thb:.4f}")
    print("")
    print(f"  Time taken  : {_mins}m {_secs}s")
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
        "llm_cost_usd"     : _session_usd,
        "llm_cost_thb"     : _session_thb,
        "llm_calls"        : _session_calls,
        "elapsed_seconds"  : round(_elapsed, 1),
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
        "open_position" : open_positions[0] if open_positions else None,
        "open_positions": open_positions,
    }


if __name__ == "__main__":
    run_backtest(config= { "use_cache": True })