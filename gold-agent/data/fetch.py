"""
data/fetch.py
Fetches live XAUUSD (Gold) price data using yfinance.
Returns the last 90 days of OHLCV as a pandas DataFrame.

Also provides get_hsh_price() — live gold price from Hua Seng Heng
(apicheckpricev3.huasengheng.com) which is the official price source
for the Thammasat University trading competition.
"""

import time
import yfinance as yf
import pandas as pd
import requests
from datetime import datetime, timedelta, timezone

# Thai timezone UTC+7
_THAI_TZ = timezone(timedelta(hours=7))

# Stores the last successful fetch time for display in the UI
_last_fetched_at: str = "Never"

# TTL cache — avoids redundant yfinance calls within the same refresh cycle
_FETCH_CACHE_TTL = 300  # 5 minutes
_price_cache: dict = {"df": None, "ts": 0.0}
_macro_cache: dict = {"data": None, "ts": 0.0}


def get_gold_price() -> pd.DataFrame:
    """
    Fetch the last 90 days of XAUUSD (Gold Futures) OHLCV data.

    Uses yfinance with ticker symbol 'GC=F' (COMEX Gold Futures).
    Stores a human-readable fetch timestamp accessible via get_fetch_time().
    Results are cached for 5 minutes to avoid redundant calls within one refresh cycle.

    Returns:
        pd.DataFrame: DataFrame with columns [Open, High, Low, Close, Volume]
                      indexed by Date. Returns empty DataFrame on failure.
    """
    global _last_fetched_at, _price_cache

    if _price_cache["df"] is not None and time.time() - _price_cache["ts"] < _FETCH_CACHE_TTL:
        return _price_cache["df"]

    try:
        end_date = datetime.today()
        start_date = end_date - timedelta(days=90)

        ticker = yf.Ticker("GC=F")
        df = ticker.history(
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
            interval="1d",
        )

        if df.empty:
            print("[fetch.py] Warning: No data returned from yfinance.")
            return pd.DataFrame()

        # Keep only standard OHLCV columns
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.index.name = "Date"
        df.dropna(inplace=True)

        # Record timestamp of this successful fetch
        _last_fetched_at = datetime.now(_THAI_TZ).strftime("%H:%M:%S")

        print(f"[fetch.py] Fetched {len(df)} rows. "
              f"Latest close: {df['Close'].iloc[-1]:.2f} USD  (at {_last_fetched_at})")
        _price_cache = {"df": df, "ts": time.time()}
        return df

    except Exception as e:
        print(f"[fetch.py] Error fetching gold price: {e}")
        return pd.DataFrame()


def get_latest_price() -> float:
    """
    Get just the most recent gold closing price.

    Returns:
        float: Latest gold price in USD per troy oz. Returns 0.0 on failure.
    """
    try:
        df = get_gold_price()
        return float(df["Close"].iloc[-1]) if not df.empty else 0.0
    except Exception as e:
        print(f"[fetch.py] Error getting latest price: {e}")
        return 0.0


def get_fetch_time() -> str:
    """
    Return the timestamp of the last successful data fetch.

    Returns:
        str: Time string like "14:32:05", or "Never" if not yet fetched.
    """
    return _last_fetched_at


def get_gold_price_intraday(interval: str = "1h", days: int = 5) -> pd.DataFrame:
    """
    Fetch recent intraday XAUUSD data for multi-timeframe analysis.

    Args:
        interval: yfinance interval string — "1h" or "15m". Default "1h".
        days: Number of calendar days to look back. Default 5.

    Returns:
        pd.DataFrame: OHLCV DataFrame indexed by datetime, or empty on failure.
    """
    try:
        end_date   = datetime.today()
        start_date = end_date - timedelta(days=days)

        ticker = yf.Ticker("GC=F")
        df = ticker.history(
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
            interval=interval,
        )

        if df.empty:
            print(f"[fetch.py] Intraday ({interval}): No data returned.")
            return pd.DataFrame()

        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.dropna(inplace=True)
        print(f"[fetch.py] Intraday ({interval}): {len(df)} bars fetched.")
        return df

    except Exception as e:
        print(f"[fetch.py] Error fetching intraday ({interval}): {e}")
        return pd.DataFrame()


def get_macro_indicators() -> dict:
    """
    Fetch DXY (US Dollar Index) and VIX (Fear Index) — key macro drivers for gold.

    Gold has strong inverse correlation with DXY and positive correlation with VIX.
        DXY up   → dollar strengthening → gold headwind
        DXY down → dollar weakening     → gold tailwind
        VIX > 20 → fear rising          → gold safe-haven demand rises
        VIX < 15 → complacency          → gold safe-haven demand falls

    Returns:
        dict: {
            "dxy": {"value", "change_pct", "signal", "raw"},
            "vix": {"value", "change_pct", "signal", "raw"},
        }
        Returns empty dicts for each on failure (non-critical).
    """
    global _macro_cache
    if _macro_cache["data"] is not None and time.time() - _macro_cache["ts"] < _FETCH_CACHE_TTL:
        return _macro_cache["data"]

    result = {"dxy": {}, "vix": {}}

    try:
        import yfinance as yf

        raw = yf.download(
            ["DX-Y.NYB", "^VIX"],
            period="5d",
            interval="1d",
            progress=False,
            auto_adjust=True,
        )

        close = raw["Close"] if "Close" in raw.columns else raw

        # ── DXY ──────────────────────────────────────────────────────────────
        try:
            dxy_s  = close["DX-Y.NYB"].dropna()
            if len(dxy_s) >= 2:
                dxy_now    = float(dxy_s.iloc[-1])
                dxy_prev   = float(dxy_s.iloc[-2])
                dxy_chg    = round((dxy_now - dxy_prev) / dxy_prev * 100, 3)
                if dxy_chg > 0.1:
                    dxy_sig = "BEARISH_GOLD"
                elif dxy_chg < -0.1:
                    dxy_sig = "BULLISH_GOLD"
                else:
                    dxy_sig = "NEUTRAL"
                result["dxy"] = {
                    "value"     : round(dxy_now, 2),
                    "change_pct": dxy_chg,
                    "signal"    : dxy_sig,
                    "label"     : f"{dxy_now:.2f}  ({dxy_chg:+.2f}%)  {dxy_sig}",
                }
        except Exception as e:
            print(f"[fetch.py] DXY parse error: {e}")

        # ── VIX ──────────────────────────────────────────────────────────────
        try:
            vix_s  = close["^VIX"].dropna()
            if len(vix_s) >= 2:
                vix_now  = float(vix_s.iloc[-1])
                vix_prev = float(vix_s.iloc[-2])
                vix_chg  = round(vix_now - vix_prev, 2)
                if vix_now >= 30:
                    vix_sig = "HIGH_FEAR (BULLISH_GOLD)"
                elif vix_now >= 20:
                    vix_sig = "ELEVATED (BULLISH_GOLD)"
                elif vix_now <= 15:
                    vix_sig = "LOW_FEAR (NEUTRAL_GOLD)"
                else:
                    vix_sig = "MODERATE"
                result["vix"] = {
                    "value"     : round(vix_now, 2),
                    "change_pct": vix_chg,
                    "signal"    : vix_sig,
                    "label"     : f"{vix_now:.2f}  ({vix_chg:+.2f})  {vix_sig}",
                }
        except Exception as e:
            print(f"[fetch.py] VIX parse error: {e}")

    except Exception as e:
        print(f"[fetch.py] Macro indicators fetch failed (non-critical): {e}")

    _macro_cache = {"data": result, "ts": time.time()}
    return result


# ─────────────────────────────────────────────────────────────
# Hua Seng Heng live price (official competition price source)
# ─────────────────────────────────────────────────────────────
_HSH_PRICE_URL  = "https://apicheckpricev3.huasengheng.com/api/Values/GetPrice"
_HSH_STATUS_URL = "https://apicheckpricev3.huasengheng.com/api/Values/GetMarketStatus"


def get_hsh_price() -> dict:
    """
    Fetch live gold price from Hua Seng Heng (ออมทอง API).

    Uses GoldType == "HSH" — Hua Seng Heng's own 96.5% purity gold prices,
    which are the official prices used in the Thammasat competition.

    Price semantics:
        Sell  — price YOU pay to buy gold from HSH  (entry price)
        Buy   — price YOU receive when selling back (exit price)

    Returns:
        dict: {
            "sell"         : float,   # entry price (THB per baht-weight)
            "buy"          : float,   # exit price  (THB per baht-weight)
            "mid"          : float,   # (sell + buy) / 2
            "spread"       : float,   # sell - buy
            "timestamp"    : str,     # e.g. "18:23:35"
            "market_status": str,     # "ON" or "OFF"
            "source"       : str,     # "hsh" always
        }
        Returns empty dict on failure — caller must handle fallback.
    """
    try:
        resp = requests.get(_HSH_PRICE_URL, timeout=5)
        resp.raise_for_status()
        data = resp.json()

        # Find the HSH entry (Hua Seng Heng own prices)
        hsh_entry = next(
            (item for item in data if item.get("GoldType") == "HSH"),
            None
        )
        if hsh_entry is None:
            print("[fetch.py] HSH price: GoldType 'HSH' not found in response.")
            return {}

        sell  = float(str(hsh_entry["Sell"]).replace(",", ""))
        buy   = float(str(hsh_entry["Buy"]).replace(",", ""))
        ts    = hsh_entry.get("StrTimeUpdate", hsh_entry.get("TimeUpdate", ""))

        try:
            print(f"[fetch.py] HSH price  Sell={sell:,.0f}  Buy={buy:,.0f}  "
                  f"Spread={sell - buy:,.0f} THB  @ {ts}")
        except UnicodeEncodeError:
            print(f"[fetch.py] HSH price  Sell={sell:,.0f}  Buy={buy:,.0f}  "
                  f"Spread={sell - buy:,.0f} THB")

        return {
            "sell"         : sell,
            "buy"          : buy,
            "mid"          : round((sell + buy) / 2, 2),
            "spread"       : round(sell - buy, 2),
            "timestamp"    : str(ts),
            "market_status": get_hsh_market_status(),
            "source"       : "hsh",
        }

    except Exception as e:
        print(f"[fetch.py] HSH price fetch failed: {e}")
        return {}


def get_hsh_market_status() -> str:
    """
    Return Hua Seng Heng market status: "ON" or "OFF".
    Returns "UNKNOWN" on failure.
    """
    try:
        resp = requests.get(_HSH_STATUS_URL, timeout=3)
        resp.raise_for_status()
        data = resp.json()
        return str(data.get("MarketStatus", "UNKNOWN")).upper()
    except Exception as e:
        print(f"[fetch.py] HSH market status fetch failed: {e}")
        return "UNKNOWN"


# Allow standalone testing
if __name__ == "__main__":
    df = get_gold_price()
    print(df.tail())
    print(f"\nLatest price : ${get_latest_price():.2f}")
    print(f"Fetched at   : {get_fetch_time()}")

    print("\n--- Macro Indicators ---")
    macro = get_macro_indicators()
    dxy = macro.get("dxy", {})
    vix = macro.get("vix", {})
    print(f"DXY : {dxy.get('label', 'N/A')}")
    print(f"VIX : {vix.get('label', 'N/A')}")

    print("\n--- Hua Seng Heng Live Price ---")
    hsh = get_hsh_price()
    if hsh:
        print(f"Sell (entry) : {hsh['sell']:,.2f} THB")
        print(f"Buy  (exit)  : {hsh['buy']:,.2f} THB")
        print(f"Mid          : {hsh['mid']:,.2f} THB")
        print(f"Spread       : {hsh['spread']:,.2f} THB")
        print(f"Market       : {hsh['market_status']}")
        print(f"Updated      : {hsh['timestamp']}")
    else:
        print("HSH price unavailable.")
