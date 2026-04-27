#!/usr/bin/env python3
"""
backtest.py
Replay historical OHLCV data candle-by-candle through the gold trading agent.
"""

# ==============================================================================
# ── SECTION 1: IMPORTS & PATH SETUP ──
# ==============================================================================
from converter.thai import THAI_GOLD_PURITY
import sys
import os
import csv
import logging
import pandas as pd
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import patch


# ==============================================================================
# ── SECTION 2: UTILITIES (SILENCING OUTPUT) ──
# ==============================================================================
@contextmanager
def _quiet():
    """Suppress all stdout, stderr, and logging during a block."""
    import io
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass


# ==============================================================================
# ── SECTION 3: CONSTANTS & CONFIGURATIONS ──
# ==============================================================================
try:
    from trader.paper_engine import (
        TAKE_PROFIT_PCT,
        STOP_LOSS_PCT,
        TRAILING_SL_PCT,
        COOLDOWN_ROUNDS,
        LOSS_COOLDOWN,
        TRADE_FEE_PCT,
        TRADE_FEE_FLAT_THB,
        DEFAULT_BALANCE as INITIAL_BALANCE_THB,
        MIN_TRADE_THB as MIN_BALANCE_THB,
        _size_pct_by_confidence,
    )
except ImportError:
    TAKE_PROFIT_PCT = 0.015
    STOP_LOSS_PCT = -0.015  # ✅ Wider SL to survive gold volatility
    TRAILING_SL_PCT = 0.007
    COOLDOWN_ROUNDS = 0
    LOSS_COOLDOWN = 1
    TRADE_FEE_PCT = float(os.environ.get("TRADE_FEE_PCT", "0.005"))
    TRADE_FEE_FLAT_THB = float(os.environ.get("TRADE_FEE_FLAT_THB", "0"))
    INITIAL_BALANCE_THB = 1500.0
    MIN_BALANCE_THB = 1000.0

    def _size_pct_by_confidence(conf):
        if conf >= 85: return 1
        elif conf >= 75: return 0.95
        else: return 0.90

CONFIDENCE_GATE = 65
USD_THB_RATE = float(os.environ.get("USD_THB_RATE", "34.5"))
TROY_OZ_GRAMS = 31.1035
BAHT_WEIGHT_GRAMS = 15.244
PURITY = THAI_GOLD_PURITY
MIN_ROWS = 20
MAX_CANDLES = int(os.environ.get("BACKTEST_MAX_CANDLES", "50"))

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
_CANDLE_LOG = os.path.join(_DATA_DIR, "backtest_log.csv")
_TRADE_LOG = os.path.join(_DATA_DIR, "backtest_trades.csv")


# ==============================================================================
# ── SECTION 4: HELPER FUNCTIONS (MATH & EXPORTS) ──
# ==============================================================================
def usd_to_thb_per_bw(price_usd: float) -> float:
    thb_per_oz = price_usd * USD_THB_RATE
    thb_per_gram = thb_per_oz / TROY_OZ_GRAMS
    return round(thb_per_gram * BAHT_WEIGHT_GRAMS * PURITY, 2)

def _calc_fee(trade_value_thb: float) -> float:
    return round(trade_value_thb * TRADE_FEE_PCT + TRADE_FEE_FLAT_THB, 2)

def _bar(value: float, max_val: float, width: int = 20, fill: str = "#") -> str:
    if max_val == 0: return fill * 0
    filled = int(round(value / max_val * width))
    filled = max(0, min(filled, width))
    return fill * filled + "." * (width - filled)

def _write_candle_log(rows: list[dict]) -> None:
    if not rows: return
    os.makedirs(_DATA_DIR, exist_ok=True)
    fieldnames = ["candle", "date", "price_usd", "price_thb", "decision",
                  "confidence", "action", "window", "pnl_thb", "equity_thb", "reasoning"]
    with open(_CANDLE_LOG, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

def _write_trade_log(trades: list[dict]) -> None:
    if not trades: return
    os.makedirs(_DATA_DIR, exist_ok=True)
    fieldnames = [
        "Buy_Price/Gold_Baht", "Buy Date", "Buy Amount", "Buy Weight (g)",
        "Sell_Price/Gold_Baht", "Sell Date", "Sell Amount", "Profit",
        "Days Held", "%Profit/Deal", "%Profit/Year (Annual)", "Capital x days/year"
    ]
    with open(_TRADE_LOG, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for idx, t in enumerate(trades, 1):
            writer.writerow({"trade_no": idx, **t})


# ==============================================================================
# ── SECTION 5: CORE SIMULATION ENGINE ──
# ==============================================================================
def run_backtest(config: dict | None = None, use_cache: bool = True) -> dict:
    import time
    import yfinance as yf
    from logger.cost_tracker import get_cost_summary as _get_cost_summary

    _start_time = time.time()
    _cost_before = _get_cost_summary()

    _cfg = config or {}
    _start_date = _cfg.get("start_date")
    _end_date = _cfg.get("end_date")
    interval = _cfg.get("interval", "1h")

    print("")
    print("  Fetching price data...")
    df_full = None
    cache_file = os.path.join(_DATA_DIR, f"historical_prices_{interval}.csv")
    ext_cache_file = os.path.join(_DATA_DIR, f"historical_prices_{interval}_extended.csv")
    
    if use_cache:
        target_cache = ext_cache_file if os.path.exists(ext_cache_file) else cache_file
        if os.path.exists(target_cache):
            try:
                print(f"  [Info] Loading data from local cache ({target_cache})...")
                df_full = pd.read_csv(target_cache, index_col="Date", parse_dates=True)
                if _start_date:
                    start_dt = pd.to_datetime(_start_date, utc=True)
                    cache_min = df_full.index.min()
                    if cache_min.tz is None: cache_min = cache_min.tz_localize("UTC")
                    else: cache_min = cache_min.tz_convert("UTC")
                    if start_dt - pd.Timedelta(days=5) < cache_min:
                        print(f"  [Info] Local cache is too recent (starts {cache_min.date()}). Re-fetching...")
                        df_full = None
                if df_full is not None:
                    interval_used = interval
            except Exception as e:
                print(f"  [Error] Failed to load cache: {e}")
                df_full = None

    if df_full is None:
        try:
            with _quiet():
                period = "730d" if interval == "1h" else "60d"
                raw = yf.download("GC=F", period=period, interval=interval, progress=False, auto_adjust=True)
                
                valid_raw = False
                if not raw.empty and len(raw) >= MIN_ROWS + 5:
                    if isinstance(raw.columns, pd.MultiIndex): raw.columns = raw.columns.get_level_values(0)
                    raw.index.name = "Date"
                    
                    if _start_date:
                        start_dt = pd.to_datetime(_start_date, utc=True)
                        raw_min = raw.index.min()
                        if raw_min.tz is None: raw_min = raw_min.tz_localize("UTC")
                        else: raw_min = raw_min.tz_convert("UTC")
                        if start_dt - pd.Timedelta(days=5) < raw_min:
                            print(f"  [Info] YFinance {interval} data is truncated (starts {raw_min.date()}).")
                        else:
                            valid_raw = True
                    else:
                        valid_raw = True

                if valid_raw:
                    df_full = raw[["Open", "High", "Low", "Close", "Volume"]].dropna()
                    os.makedirs(_DATA_DIR, exist_ok=True)
                    df_full.to_csv(cache_file)
                    interval_used = interval
                elif interval in ["30m", "15m"]:
                    print(f"  [Info] Falling back to 1h data + resampling for {interval}...")
                    cache_1h = os.path.join(_DATA_DIR, "historical_prices_1h.csv")
                    raw_1h = None
                    if use_cache and os.path.exists(cache_1h):
                        raw_1h = pd.read_csv(cache_1h, index_col="Date", parse_dates=True)
                        if _start_date:
                            start_dt = pd.to_datetime(_start_date, utc=True)
                            c1h_min = raw_1h.index.min()
                            if c1h_min.tz is None: c1h_min = c1h_min.tz_localize("UTC")
                            else: c1h_min = c1h_min.tz_convert("UTC")
                            if start_dt - pd.Timedelta(days=5) < c1h_min:
                                raw_1h = None
                                
                    if raw_1h is None:
                        raw = yf.download("GC=F", period="730d", interval="1h", progress=False, auto_adjust=True)
                        if not raw.empty:
                            if isinstance(raw.columns, pd.MultiIndex): raw.columns = raw.columns.get_level_values(0)
                            raw.index.name = "Date"
                            raw_1h = raw[["Open", "High", "Low", "Close", "Volume"]].dropna()
                            raw_1h.to_csv(cache_1h)
                            
                    if raw_1h is not None and not raw_1h.empty:
                        df_full = raw_1h
                        pd_freq = interval.replace("m", "min")
                        df_full = df_full.resample(pd_freq).ffill()
                        interval_used = interval
        except Exception as e:
            print("FETCH ERROR:", e)

    if df_full is None or len(df_full) < MIN_ROWS + 5:
        try:
            with _quiet():
                raw = yf.download("GC=F", period="6mo", interval="1d", progress=False, auto_adjust=True)
            if isinstance(raw.columns, pd.MultiIndex): raw.columns = raw.columns.get_level_values(0)
            raw.index.name = "Date"
            df_full = raw[["Open", "High", "Low", "Close", "Volume"]].dropna()
            interval_used = "1d"
        except Exception as e:
            return {"daily_log": [], "closed_trades": [], "open_position": None, "summary": {"error": str(e)}}

    if df_full is None or df_full.empty:
        return {"daily_log": [], "closed_trades": [], "open_position": None, "summary": {"error": "No data fetched"}}

    # --- SYNTHETIC WEEKEND DATA ---
    if interval_used in ["1h", "30m", "15m"]:
        pd_freq = interval_used.replace("m", "min").replace("h", "H")
        try:
            if not isinstance(df_full.index, pd.DatetimeIndex):
                df_full.index = pd.to_datetime(df_full.index)
            if df_full.index.tz is None:
                df_full.index = df_full.index.tz_localize("UTC")
            else:
                df_full.index = df_full.index.tz_convert("UTC")

            start_th = df_full.index.min().tz_convert("Asia/Bangkok")
            end_th = df_full.index.max().tz_convert("Asia/Bangkok")
            
            all_hours = pd.date_range(
                start=start_th.replace(hour=0, minute=0, second=0), 
                end=end_th.replace(hour=23, minute=59, second=59), 
                freq=pd_freq
            )
            
            weekend_mask = (all_hours.dayofweek >= 5) & (all_hours.hour >= 9) & (all_hours.hour <= 17)
            weekend_hours = all_hours[weekend_mask].tz_convert("UTC")
            
            combined_index = df_full.index.union(weekend_hours).sort_values()
            df_full = df_full.reindex(combined_index)
            
            df_full["Close"] = df_full["Close"].ffill()
            df_full["Open"] = df_full["Open"].fillna(df_full["Close"])
            df_full["High"] = df_full["High"].fillna(df_full["Close"])
            df_full["Low"] = df_full["Low"].fillna(df_full["Close"])
            df_full["Volume"] = df_full["Volume"].fillna(0)
            for col in ["DXY", "VIX", "USDTHB"]:
                if col in df_full.columns:
                    df_full[col] = df_full[col].ffill()
            df_full.dropna(inplace=True)
        except Exception as e:
            print(f"Failed to generate synthetic weekend data: {e}")

    import numpy as np
    
    if len(df_full) > MIN_ROWS + MAX_CANDLES and not (_start_date and _end_date):
        df_full = df_full.iloc[-(MIN_ROWS + MAX_CANDLES):]
        total_candles = len(df_full) - MIN_ROWS + 1
    elif _start_date and _end_date:
        try:
            th_index = df_full.index.tz_convert("Asia/Bangkok")
        except TypeError:
            th_index = df_full.index.tz_localize("UTC").tz_convert("Asia/Bangkok")
        date_strs = th_index.strftime("%Y-%m-%d")
        in_window = (date_strs >= _start_date) & (date_strs <= _end_date)
        if not in_window.any():
            return {"daily_log": [], "closed_trades": [], "open_position": None, "summary": {"error": f"No data for {_start_date} to {_end_date}"}}
            
        first_idx = int(np.argmax(in_window))
        last_idx = len(in_window) - 1 - int(np.argmax(in_window[::-1]))
        
        start_idx = max(0, first_idx - (MIN_ROWS - 1))
        df_full = df_full.iloc[start_idx : last_idx + 1]
        
        total_candles = last_idx - first_idx + 1
    else:
        total_candles = len(df_full) - MIN_ROWS + 1

    _cfg = config or {}
    _flag_names = ["use_macd", "use_bb", "use_news", "use_dxy_vix",
                   "use_h1_mtf", "use_daily_bias", "use_volume_spike"]
    _on = [f for f in _flag_names if _cfg.get(f, True)]
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

    balance_thb = INITIAL_BALANCE_THB
    open_positions = []
    closed_trades = []
    daily_log = []
    cooldown = 0

    from trader.trade_scheduler import _WEEKDAY_LOGICAL, _WEEKEND_LOGICAL
    import datetime as _dt
    _THAI_TZ = _dt.timezone(_dt.timedelta(hours=7))

    def _to_thai(dt):
        try: return dt.astimezone(_THAI_TZ)
        except Exception: return dt.replace(tzinfo=_dt.timezone.utc).astimezone(_THAI_TZ)

    def _get_candle_window(dt) -> str | None:
        local = _to_thai(dt)
        minutes = local.hour * 60 + local.minute
        windows = _WEEKEND_LOGICAL if local.weekday() >= 5 else _WEEKDAY_LOGICAL
        for w in windows:
            for start, end in w["ranges"]:
                if start <= minutes <= end: return w["name"]
        return None

    def _minutes_until_window_end(dt) -> int | None:
        local = _to_thai(dt)
        minutes = local.hour * 60 + local.minute
        windows = _WEEKEND_LOGICAL if local.weekday() >= 5 else _WEEKDAY_LOGICAL
        for w in windows:
            total_end = max(end for start, end in w["ranges"])
            # If the window spans past midnight (e.g. evening ends at 02:00, but has a range ending at 23:59)
            if any(start == 0 for start, end in w["ranges"]) and any(end == 1439 for start, end in w["ranges"]):
                next_day_end = max(end for start, end in w["ranges"] if start == 0)
                if minutes >= 18 * 60:
                    return (1439 - minutes) + next_day_end + 1
                elif minutes <= next_day_end:
                    return next_day_end - minutes
            for start, end in w["ranges"]:
                if start <= minutes <= end: return end - minutes
        return None

    def _thai_date_str(dt) -> str:
        local = _to_thai(dt)
        minutes = local.hour * 60 + local.minute
        if 0 <= minutes <= 2 * 60:
            local -= _dt.timedelta(days=1)
        return str(local.date())

    _window_trades: dict = {}
    import data.fetch as fetch_module
    from agent.trading_agent import run_agent

    # ── [SUB-SECTION: THE MAIN CANDLE-BY-CANDLE LOOP] ─────────────────────────
    evaluated_candles = 0
    for i in range(MIN_ROWS - 1, len(df_full)):
        date = df_full.index[i]
        date_str_today_anchor = _thai_date_str(date)

        if _start_date and date_str_today_anchor < _start_date:
            continue
        if _end_date and date_str_today_anchor > _end_date:
            break

            
        evaluated_candles += 1
        window = df_full.iloc[: i + 1].copy()
        price_usd = float(window["Close"].iloc[-1])
        if "USDTHB" in window.columns:
            usd_thb_rate_dynamic = float(window["USDTHB"].iloc[-1])
            thb_per_oz = price_usd * usd_thb_rate_dynamic
            thb_per_gram = thb_per_oz / TROY_OZ_GRAMS
            price_thb = round(thb_per_gram * BAHT_WEIGHT_GRAMS * PURITY, 2)
        else:
            price_thb = usd_to_thb_per_bw(price_usd)

        pct_done = evaluated_candles / total_candles * 100 if total_candles > 0 else 100
        bar = _bar(evaluated_candles, total_candles, width=30)
        status = f"[{bar}] {evaluated_candles}/{total_candles} ({pct_done:.0f}%)"
        print(f"\r  Running {status}  B{balance_thb:,.0f}", end="", flush=True)

        candle_window = _get_candle_window(date)
        if candle_window is None:
            daily_log.append({
                "candle": evaluated_candles,
                "date": _to_thai(date).strftime("%Y-%m-%d %H:%M"),
                "price_usd": price_usd,
                "price_thb": price_thb,
                "decision": "HOLD",
                "confidence": 0,
                "action": "OUT_OF_WINDOW",
                "pnl_thb": 0.0,
                "equity_thb": round(balance_thb + sum(p["size_bw"] * price_thb for p in open_positions), 2),
                "reasoning": "Outside trading window.",
            })
            continue

        date_str_today = _thai_date_str(date)
        _window_trades.setdefault(date_str_today, {})
        _window_used = _window_trades[date_str_today].get(candle_window, 0)
        _is_weekend = _to_thai(date).weekday() >= 5
        # Competition rules: 2 trades per window on ALL days
        _window_quota = 2
        _quota_pressure = _window_used < _window_quota

        def _mock_daily_market():
            # Realistic trend estimation based on historical window only (NO LEAKAGE)
            if len(window) < 5: return {"daily_trend": "Sideways", "trend_strength": "Weak"}
            recent_close = window["Close"].tail(20)
            change = (recent_close.iloc[-1] - recent_close.iloc[0]) / recent_close.iloc[0]
            
            if change > 0.005: trend, strength = "Uptrend", "Strong"
            elif change > 0.002: trend, strength = "Uptrend", "Moderate"
            elif change < -0.005: trend, strength = "Downtrend", "Strong"
            elif change < -0.002: trend, strength = "Downtrend", "Moderate"
            else: trend, strength = "Sideways", "Weak"
            
            return {
                "daily_trend": trend,
                "trend_strength": strength,
                "daily_summary": f"Historical market analysis indicates {trend} bias."
            }

        def _mock_macro():
            d_val = float(window["DXY"].iloc[-1]) if "DXY" in window.columns else 100.0
            v_val = float(window["VIX"].iloc[-1]) if "VIX" in window.columns else 15.0
            return {
                "dxy": {"value": d_val, "change_pct": 0.0, "signal": "NEUTRAL"},
                "vix": {"value": v_val, "change_pct": 0.0, "signal": "MODERATE"}
            }

        def _mock_news():
            import json
            # ── Load REAL news file by month, fallback to Neutral ──────────
            curr_date = _to_thai(date).strftime("%Y-%m-%d")
            curr_ym = _to_thai(date).strftime("%Y_%m")
            news_file = os.path.join(_DATA_DIR, f"historical_news_{curr_ym}.json")
            try:
                with open(news_file, "r", encoding="utf-8") as f:
                    news_db = json.load(f)
                active_news = {"sentiment": "Neutral", "headline": "No major news.", "impact": "Low"}
                for d_key in sorted(news_db.keys()):
                    if d_key <= curr_date: active_news = news_db[d_key]
                    else: break
                # Strip internal _headlines key if present
                return {k: v for k, v in active_news.items() if not k.startswith("_")}
            except FileNotFoundError:
                return {"sentiment": "Neutral", "headline": "No news file for this period. Run scripts/fetch_historical_news.py first.", "impact": "Low"}
            except Exception:
                return {"sentiment": "Neutral", "headline": "Stable market conditions.", "impact": "Low"}

        import agent.daily_market_agent as dm_module
        import news.sentiment as news_module
        with _quiet(), \
             patch.object(fetch_module, "get_gold_price", return_value=window), \
             patch.object(fetch_module, "get_gold_price_intraday", return_value=window), \
             patch.object(dm_module, "get_daily_market", side_effect=_mock_daily_market), \
             patch.object(fetch_module, "get_macro_indicators", side_effect=_mock_macro), \
             patch.object(news_module, "get_gold_news", side_effect=_mock_news):
            
            # Ensure news is enabled in agent config for backtest
            config['use_news'] = True
            agent = run_agent(quota_pressure=_quota_pressure, open_positions=len(open_positions), config=config)
            
        decision = agent["decision"]
        confidence = agent["confidence"]
        reasoning = agent["reasoning"]
        action = "HOLD"
        pnl_thb = 0.0

        # ── [SUB-SECTION: RISK RULES & FAILSAFES] ─────────────────────────────
        for pos in open_positions:
            change_pct = (price_thb - pos["entry_price"]) / pos["entry_price"]
            highest = max(pos.get("highest_price", pos["entry_price"]), price_thb)
            pos["highest_price"] = highest
            trailing_sl_price = highest * (1 - TRAILING_SL_PCT)
            if change_pct >= TAKE_PROFIT_PCT or change_pct <= STOP_LOSS_PCT or (price_thb <= trailing_sl_price and highest > pos["entry_price"]):
                decision = "SELL"
                confidence = 100
                break

        _mins_left = _minutes_until_window_end(date)
        
        _int_mins = 60
        if interval_used == "30m": _int_mins = 30
        elif interval_used == "15m": _int_mins = 15
        
        _trades_needed = max(0, _window_quota - _window_used)
        # Failsafe activates only in the LAST 60 minutes of a window (2 candles at 30m)
        _failsafe_thresh = _int_mins * 2
        
        _is_invalid_sell = (decision == "SELL" and not open_positions)
        _is_invalid_buy = (decision == "BUY" and len(open_positions) >= 1)

        # ── CROSS-WINDOW PREVENTION (HARD RULE) ─────────────────────────────
        # If holding a position and window is about to end, force SELL immediately.
        # This guarantees the trade closes in the same window it opened.
        _window_almost_over = (_mins_left is not None and _mins_left <= _int_mins)
        if open_positions and _window_almost_over:
            decision = "SELL"
            confidence = 100
            reasoning = "[WINDOW-END] Forced SELL to keep trade within window boundary."

        # ── MINIMUM HOLD (within window only) ───────────────────────────────
        # Allow min-hold only if the window won't end before hold time is up.
        _min_hold_minutes = 90
        _too_early_to_sell = False
        if decision == "SELL" and open_positions and not _window_almost_over and (_mins_left is None or _mins_left > _failsafe_thresh):
            entry_dt = open_positions[0].get("entry_dt")
            if entry_dt is not None:
                held_minutes = (date - entry_dt).total_seconds() / 60
                mins_left_safe = _mins_left if _mins_left is not None else 9999
                # Only enforce min-hold if there's enough window time remaining
                if held_minutes < _min_hold_minutes and mins_left_safe > _min_hold_minutes:
                    _too_early_to_sell = True
                    decision = "HOLD"
                    reasoning = f"[HOLD] Min hold: {held_minutes:.0f}/{_min_hold_minutes}min"
        
        _needs_failsafe = (_window_used < _window_quota or len(open_positions) > 0)
        
        if ((decision == "HOLD" or _is_invalid_sell or _is_invalid_buy) and _mins_left is not None and _mins_left <= _failsafe_thresh and _needs_failsafe):


            with _quiet(), patch.object(fetch_module, "get_gold_price", return_value=window):
                agent = run_agent(quota_pressure=True, failsafe_pressure=True, open_positions=len(open_positions), config=config)
            decision = agent["decision"]
            confidence = agent["confidence"]
            reasoning = agent["reasoning"]
            
            _is_invalid_sell_fs = (decision == "SELL" and not open_positions)
            _is_invalid_buy_fs = (decision == "BUY" and len(open_positions) >= 1)
            if decision == "HOLD" or _is_invalid_sell_fs or _is_invalid_buy_fs:
                if open_positions:
                    decision = "SELL"
                    confidence = 100
                    reasoning = "[FAILSAFE] Forced SELL to exit window."
                else:
                    # ✅ Reverted to simple momentum-based failsafe (NO LEAKAGE)
                    recent_diff = window["Close"].iloc[-1] - window["Close"].iloc[-5] if len(window) >= 5 else 0
                    decision = "BUY" if recent_diff >= 0 else "SELL"
                    confidence = 51
                    reasoning = f"[FAILSAFE] Forced {decision} to meet quota based on short-term momentum."

        _effective_gate = 40 if _quota_pressure else CONFIDENCE_GATE
        
        # Decrement cooldown organically if agent outputs HOLD
        if decision == "HOLD" and cooldown > 0:
            cooldown -= 1
            
        if confidence < _effective_gate:
            action = "SKIP"
            if cooldown > 0: cooldown -= 1
            
        elif cooldown > 0 and decision == "BUY" and not _quota_pressure:
            action = "SKIP"
            cooldown -= 1

        elif decision == "BUY":
            if balance_thb >= MIN_BALANCE_THB:
                # ✅ DYNAMIC SIZING: If forced by failsafe OR low confidence, use 1,000 THB (minimum).
                # If normal high-confidence trade, use size based on confidence.
                if "[FAILSAFE]" in reasoning or confidence <= 55:
                    gross = 1000.0
                    size_pct = 0.0 # N/A
                else:
                    size_pct = _size_pct_by_confidence(confidence)
                    gross = round(balance_thb * size_pct, 2)

                if gross < 1000:
                    action = "SKIP"
                    continue
                open_fee = _calc_fee(gross)
                cost = round(gross + open_fee, 2)
                size_bw = gross / price_thb
                balance_thb -= cost
                open_positions.append({
                    "entry_date": _to_thai(date).strftime("%Y-%m-%d %H:%M"),
                    "entry_price": price_thb,
                    "entry_dt": date,   # raw datetime for min-hold calculation
                    "highest_price": price_thb,
                    "size_bw": size_bw,
                    "cost_thb": gross,
                    "open_fee": open_fee,
                    "tp_price": round(price_thb * (1 + TAKE_PROFIT_PCT), 0),
                    "sl_price": round(price_thb * (1 + STOP_LOSS_PCT), 0),
                    "confidence": confidence,
                    "size_pct": size_pct,
                })
                cooldown = 0
                action = "OPENED"
                _window_trades[date_str_today][candle_window] = _window_trades[date_str_today].get(candle_window, 0) + 1
            else:
                action = "SKIP"

        elif decision == "SELL" and open_positions:
            total_pnl_thb = 0.0
            any_loss = False
            for pos in open_positions:
                gross_proceeds = pos["size_bw"] * price_thb
                close_fee = _calc_fee(gross_proceeds)
                open_fee = pos.get("open_fee", 0.0)
                net_proceeds = round(gross_proceeds - close_fee, 2)
                total_fees = round(open_fee + close_fee, 2)
                pos_pnl_thb = round(net_proceeds - pos["cost_thb"], 2)
                pnl_pct = round(pos_pnl_thb / pos["cost_thb"] * 100, 2)
                outcome = "WIN" if pos_pnl_thb >= 0 else "LOSS"
                if pos_pnl_thb < 0: any_loss = True
                total_pnl_thb += pos_pnl_thb
                balance_thb += net_proceeds
                
                # Extended log metrics
                entry_dt = datetime.strptime(pos["entry_date"], "%Y-%m-%d %H:%M")
                exit_dt = datetime.strptime(_to_thai(date).strftime("%Y-%m-%d %H:%M"), "%Y-%m-%d %H:%M")
                days_held = max((exit_dt - entry_dt).total_seconds() / 86400.0, 0.0417) # Min 1 hour
                buy_weight_g = round(pos["size_bw"] * BAHT_WEIGHT_GRAMS, 4)
                pnl_frac = pos_pnl_thb / pos["cost_thb"]
                pct_profit_year = round(pnl_frac * (365.0 / days_held) * 100, 2)
                cap_x_days_year = round(pos["cost_thb"] * (days_held / 365.0), 2)

                trade = {
                    "Buy_Price/Gold_Baht": pos["entry_price"],
                    "Buy Date": pos["entry_date"],
                    "Buy Amount": pos["cost_thb"],
                    "Buy Weight (g)": buy_weight_g,
                    "Sell_Price/Gold_Baht": price_thb,
                    "Sell Date": exit_dt.strftime("%Y-%m-%d %H:%M"),
                    "Sell Amount": round(gross_proceeds, 2),
                    "Profit": pos_pnl_thb,
                    "Days Held": round(days_held, 4),
                    "%Profit/Deal": pnl_pct,
                    "%Profit/Year (Annual)": pct_profit_year,
                    "Capital x days/year": cap_x_days_year,
                    "outcome": outcome,
                }
                closed_trades.append(trade)
            open_positions = []
            pnl_thb = total_pnl_thb
            cooldown = LOSS_COOLDOWN if any_loss else COOLDOWN_ROUNDS
            action = "CLOSED [BASKET]"

        elif decision == "SELL" and not open_positions:
            action = "SKIP"
            if cooldown > 0: cooldown -= 1

        unrealized = sum((p["size_bw"] * price_thb) - p["cost_thb"] for p in open_positions)
        equity = round(balance_thb + sum(p["size_bw"] * price_thb for p in open_positions), 2)

        daily_log.append({
            "candle": evaluated_candles,
            "date": _to_thai(date).strftime("%Y-%m-%d %H:%M"),
            "price_usd": price_usd,
            "price_thb": price_thb,
            "decision": decision,
            "confidence": confidence,
            "action": action,
            "window": candle_window,
            "pnl_thb": pnl_thb,
            "equity_thb": equity,
            "reasoning": reasoning,
        })

    print("\r" + " " * 70 + "\r", end="")


    # ==============================================================================
    # ── SECTION 6: STATS & CALCULATIONS (LOGIC) ──
    # ==============================================================================
    last_price_thb = daily_log[-1]["price_thb"] if daily_log else 0
    final_equity = balance_thb
    for pos in open_positions:
        final_equity += pos["size_bw"] * last_price_thb

    wins = [t for t in closed_trades if t["outcome"] == "WIN"]
    losses = [t for t in closed_trades if t["outcome"] == "LOSS"]
    total_pnl = sum(t["Profit"] for t in closed_trades)
    total_fees = sum(t.get("total_fees", 0.0) for t in closed_trades)
    win_rate = len(wins) / len(closed_trades) * 100 if closed_trades else 0.0
    ret_pct = (final_equity - INITIAL_BALANCE_THB) / INITIAL_BALANCE_THB * 100
    candles_run = len(daily_log)

    try:
        d0 = datetime.strptime(daily_log[0]["date"], "%Y-%m-%d %H:%M")
        d1 = datetime.strptime(daily_log[-1]["date"], "%Y-%m-%d %H:%M")
        calendar_days = (d1 - d0).days + 1
    except Exception:
        calendar_days = candles_run

    import numpy as np

    avg_win = sum(t["Profit"] for t in wins) / len(wins) if wins else 0.0
    avg_loss = abs(sum(t["Profit"] for t in losses)) / len(losses) if losses else 0.0
    rr_ratio = round(avg_win / avg_loss, 2) if avg_loss > 0 else 0.0
    expectancy = round((win_rate/100.0 * avg_win) - ((1.0 - win_rate/100.0) * avg_loss), 2)

    if closed_trades:
        ann_rets = [t["%Profit/Year (Annual)"] for t in closed_trades]
        best_ann = round(np.max(ann_rets), 2)
        worst_ann = round(np.min(ann_rets), 2)
        median_ann = round(np.median(ann_rets), 2)
        top_10_ann = round(np.percentile(ann_rets, 90), 2)
        bot_10_ann = round(np.percentile(ann_rets, 10), 2)
        avg_cap_year = round(sum(t["Capital x days/year"] for t in closed_trades), 2)
    else:
        best_ann = worst_ann = median_ann = top_10_ann = bot_10_ann = avg_cap_year = 0.0

    unrealized = sum((p["size_bw"] * last_price_thb) - p["cost_thb"] for p in open_positions)

    # Calculate Sharpe Ratio
    daily_equity = {}
    for log in daily_log:
        daily_equity[log["date"][:10]] = log["equity_thb"]
    if len(daily_equity) > 1:
        eq_series = pd.Series(daily_equity)
        daily_rets = eq_series.pct_change().dropna()
        sharpe = round((daily_rets.mean() / daily_rets.std()) * np.sqrt(252), 2) if daily_rets.std() != 0 else 0.0
    else:
        sharpe = 0.0
        
    # XIRR substitute (CAGR)
    years = calendar_days / 365.25 if calendar_days > 0 else 1.0
    xirr = round(((final_equity / INITIAL_BALANCE_THB) ** (1 / years) - 1) * 100, 2)

    first_price_thb = daily_log[0]["price_thb"] if daily_log else 0
    if first_price_thb > 0 and last_price_thb > 0:
        bah_size_bw = (INITIAL_BALANCE_THB * 0.95) / first_price_thb
        bah_final = bah_size_bw * last_price_thb
        bah_pnl = bah_final - (INITIAL_BALANCE_THB * 0.95)
        bah_return_pct = round(bah_pnl / INITIAL_BALANCE_THB * 100, 2)
    else:
        bah_pnl = 0.0
        bah_return_pct = 0.0
    agent_alpha = round(ret_pct - bah_return_pct, 2)


    # ==============================================================================
    # ── SECTION 7: DATA EXPORTING (LOG SAVING) ──
    # ==============================================================================
    _write_candle_log(daily_log)
    _write_trade_log(closed_trades)

    _cost_after = _get_cost_summary()
    _session_calls = _cost_after["call_count"] - _cost_before["call_count"]
    _session_usd = round(_cost_after["total_cost_usd"] - _cost_before["total_cost_usd"], 6)
    _session_thb = round(_cost_after["total_cost_thb"] - _cost_before["total_cost_thb"], 4)
    _elapsed = time.time() - _start_time
    _mins, _secs = divmod(int(_elapsed), 60)


    # ==============================================================================
    # ── SECTION 8: CLI OUTPUT / PRINT STATS ──
    # ==============================================================================
    ret_sign = "+" if ret_pct >= 0 else ""
    bah_sign = "+" if bah_return_pct >= 0 else ""
    alp_sign = "+" if agent_alpha >= 0 else ""
    pnl_sign = "+" if total_pnl >= 0 else ""

    win_bar = "#" * min(len(wins), 20)
    loss_bar = "x" * min(len(losses), 20)

    print("=" * 60)
    print("  BACKTEST COMPLETE")
    print("=" * 60)
    print(f"  Period     : {daily_log[0]['date'] if daily_log else '?'}  ->  {daily_log[-1]['date'] if daily_log else '?'}  ({calendar_days}d)")
    print(f"  Candles    : {candles_run} x {interval_used}  |  Trades : {len(closed_trades)}")
    print("")
    print("  SUMMARY STATS")
    print(f"  {'Total Closed Trade':<30}: {len(closed_trades):.2f}")
    print(f"  {'Win Rate (%)':<30}: {win_rate/100:.2f}")
    print(f"  {'Total Profit (THB)':<30}: {total_pnl:,.2f}")
    print(f"  {'Unrealized P/L (Open Deals)':<30}: {unrealized:,.2f}")
    print(f"  {'Average Win (THB)':<30}: {avg_win:,.2f}")
    avg_loss_str = f"{avg_loss:,.2f}" if avg_loss > 0 else "-"
    print(f"  {'Average Loss (THB)':<30}: {avg_loss_str}")
    print(f"  {'Expectancy per Trade (THB)':<30}: {expectancy:,.2f}")
    print(f"  {'Best Annualized Trade (%)':<30}: {best_ann:.2f}%")
    print(f"  {'Worst Annualized Trade (%)':<30}: {worst_ann:.2f}%")
    print(f"  {'Median Annualized Trade (%)':<30}: {median_ann:.2f}%")
    print(f"  {'Top 10% Annualized Trade':<30}: {top_10_ann:.2f}%")
    print(f"  {'Bottom 10% Annualized Trade':<30}: {bot_10_ann:.2f}%")
    print(f"  {'XIRR':<30}: {xirr:.2f}%")
    print(f"  {'Avg Capital/Year (THB/Year)':<30}: {avg_cap_year:,.2f}")
    print(f"  {'Sharpe Ratio':<30}: {sharpe:.2f}")
    print("")
    print("  vs BUY-AND-HOLD")
    print(f"  {'Agent':<20}: {ret_sign}{ret_pct:.2f}%")
    print(f"  {'Buy & Hold':<20}: {bah_sign}{bah_return_pct:.2f}%")
    alpha_label = "AGENT WINS" if agent_alpha > 0 else "B&H WINS"
    print(f"  {'Alpha':<20}: {alp_sign}{agent_alpha:.2f}%  [{alpha_label}]")
    print("")

    trading_days = [d for d in _window_trades]
    days_compliant = 0
    days_total = len(trading_days)
    for day, windows in _window_trades.items():
        is_weekday = datetime.strptime(day, "%Y-%m-%d").weekday() < 5
        min_required = 6 if is_weekday else 1
        total_day_trades = sum(windows.values())
        if total_day_trades >= min_required: days_compliant += 1

    print("  WINDOW COMPLIANCE")
    print(f"  {'Min trades/day':<14}: weekday=6 (2x3 windows)  weekend=1 (1 window)")
    if trading_days:
        print(f"  {'Days traded':<14}: {days_total}")
        print(f"  {'Days met quota':<14}: {days_compliant}/{days_total}", end="")
        print(f"  {'[OK]' if days_compliant == days_total else '[BELOW QUOTA]'}")
        for day, windows in sorted(_window_trades.items()):
            is_weekday = datetime.strptime(day, "%Y-%m-%d").weekday() < 5
            min_required = 6 if is_weekday else 1
            total = sum(windows.values())
            marker = "[OK]" if total >= min_required else f"[NEED {min_required - total} MORE]"
            win_str = "  ".join(f"{k}:{v}" for k, v in windows.items())
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
    summary_file = os.path.join(_DATA_DIR, "backtest_summary.csv")
    with open(summary_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Metric", "Value"])
        writer.writerow(["Total Closed Trade", f"{len(closed_trades):.2f}"])
        writer.writerow(["Win Rate (%)", f"{win_rate/100:.2f}"])
        writer.writerow(["Total Profit (THB)", f"{total_pnl:.2f}"])
        writer.writerow(["Unrealized P/L (Open Deals)", f"{unrealized:.2f}"])
        writer.writerow(["Average Win (THB)", f"{avg_win:.2f}"])
        writer.writerow(["Average Loss (THB)", f"{avg_loss:.2f}" if avg_loss > 0 else "-"])
        writer.writerow(["Expectancy per Trade (THB)", f"{expectancy:.2f}"])
        writer.writerow(["Best Annualized Trade (%)", f"{best_ann:.2f}%"])
        writer.writerow(["Worst Annualized Trade (%)", f"{worst_ann:.2f}%"])
        writer.writerow(["Median Annualized Trade (%)", f"{median_ann:.2f}%"])
        writer.writerow(["Top 10% Annualized Trade", f"{top_10_ann:.2f}%"])
        writer.writerow(["Bottom 10% Annualized Trade", f"{bot_10_ann:.2f}%"])
        writer.writerow(["XIRR", f"{xirr:.2f}%"])
        writer.writerow(["Avg Capital/Year (THB/Year)", f"{avg_cap_year:.2f}"])
        writer.writerow(["Sharpe Ratio", f"{sharpe:.2f}"])

    print("  LOGS SAVED")
    print(f"  Candle log  : data/backtest_log.csv    ({len(daily_log)} rows)")
    print(f"  Trade log   : data/backtest_trades.csv ({len(closed_trades)} trades)")
    print(f"  Summary     : data/backtest_summary.csv")
    print("=" * 60)
    print("")

    summary = {
        "period_start": daily_log[0]["date"] if daily_log else "—",
        "period_end": daily_log[-1]["date"] if daily_log else "—",
        "candles_run": candles_run,
        "calendar_days": calendar_days,
        "interval": interval_used,
        "days_run": candles_run,
        "total_trades": len(closed_trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 1),
        "total_pnl": round(total_pnl, 2),
        "total_fees": round(total_fees, 2),
        "initial": INITIAL_BALANCE_THB,
        "final_equity": round(final_equity, 2),
        "return_pct": round(ret_pct, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "rr_ratio": rr_ratio,
        "bah_return_pct": bah_return_pct,
        "agent_alpha": agent_alpha,
        "llm_cost_usd": _session_usd,
        "llm_cost_thb": _session_thb,
        "llm_calls": _session_calls,
        "elapsed_seconds": round(_elapsed, 1),
        "rules": {
            "confidence_gate": CONFIDENCE_GATE,
            "take_profit_pct": TAKE_PROFIT_PCT * 100,
            "stop_loss_pct": STOP_LOSS_PCT * 100,
            "cooldown_rounds": COOLDOWN_ROUNDS,
            "fee_pct": TRADE_FEE_PCT * 100,
            "trailing_sl_pct": TRAILING_SL_PCT * 100,
            "usd_thb_rate": USD_THB_RATE,
        },
    }

    return {
        "daily_log": daily_log,
        "closed_trades": closed_trades,
        "summary": summary,
        "open_position": open_positions[0] if open_positions else None,
        "open_positions": open_positions,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Gold Agent Backtest")
    parser.add_argument("--start", type=str, help="Start date YYYY-MM-DD (e.g. 2026-01-01)", default=None)
    parser.add_argument("--end", type=str, help="End date YYYY-MM-DD (e.g. 2026-01-31)", default=None)
    parser.add_argument("--interval", type=str, help="Timeframe interval (e.g. 1h, 30m, 15m)", default="1h")
    parser.add_argument("--no-cache", action="store_true", help="Force fresh data fetch")
    args = parser.parse_args()
    
    config = {
        "use_cache": not args.no_cache,
        "start_date": args.start,
        "end_date": args.end,
        "interval": args.interval,
        "use_news": True,        # Now mocked with historical context
        "use_daily_bias": True,  # Now mocked correctly
        "use_h1_mtf": True       # Now mocked correctly
    }
    run_backtest(config=config)
