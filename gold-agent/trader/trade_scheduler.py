"""
trader/trade_scheduler.py
Trade window and quota tracker for the Gold Trading Agent.

Schedule:
  Monday–Friday : 6 trades/day across 3 windows
    Window 1 : 06:00–11:59:59                   (1 full cycle: BUY + SELL)
    Window 2 : 12:00–17:59:59                   (1 full cycle: BUY + SELL)
    Window 3 : 18:00–23:59:59 and 00:00–02:00   (1 full cycle: BUY + SELL)

  Saturday–Sunday : 2 trades/day
    Window 1 : 09:30–17:30                      (1 full cycle: BUY + SELL)

Analysis runs every 30 minutes inside active windows.
A trade signal is only sent if the window quota is not yet filled.
"""

import json
import os
from datetime import datetime, timezone, timedelta

_THAI_TZ    = timezone(timedelta(hours=7))
_STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "scheduler_state.json")

# ─── Window definitions ───────────────────────────────────────────────────────

# Each window: (start_hour_min, end_hour_min, quota)
# Represented as (h*60+m) minutes-since-midnight for easy comparison

# M-F windows (Thai time):
#   morning:   06:00-11:59
#   afternoon: 12:00-17:59
#   evening:   18:00-23:59 + 00:00-02:00 (next calendar day, same logical window)
_WEEKDAY_LOGICAL = [
    {
        "name": "morning",
        "ranges": [(6*60+0, 11*60+59)],
        "min_trades": 2,
    },
    {
        "name": "afternoon",
        "ranges": [(12*60+0, 17*60+59)],
        "min_trades": 2,
    },
    {
        "name": "evening",
        "ranges": [(18*60+0, 23*60+59), (0*60+0, 2*60+0)],
        "min_trades": 2,
    },
]

_WEEKEND_LOGICAL = [
    {
        "name": "daytime",
        "ranges": [(9*60+30, 17*60+30)],
        "min_trades": 2,
    },
]


# ─── State persistence ────────────────────────────────────────────────────────

def _today_str() -> str:
    return datetime.now(_THAI_TZ).strftime("%Y-%m-%d")


def _window_anchor_date() -> str:
    """
    Return the anchor date for evening window.
    If time is 00:00–02:00 → still belongs to yesterday's evening.
    """
    now = datetime.now(_THAI_TZ)

    minutes = now.hour * 60 + now.minute

    # midnight continuation window
    if 0 <= minutes <= 2*60:
        anchor = now - timedelta(days=1)
    else:
        anchor = now

    return anchor.strftime("%Y-%m-%d")



def _load_state() -> dict:
    if os.path.exists(_STATE_FILE):
        try:
            with open(_STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            if state.get("date") == _window_anchor_date():
                return state
        except Exception:
            pass
    # Fresh state for today
    return {"date": _window_anchor_date(), "windows": {}}


def _save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
    with open(_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


# ─── Core logic ───────────────────────────────────────────────────────────────

def _get_windows() -> list[dict]:
    now = datetime.now(_THAI_TZ)
    return _WEEKEND_LOGICAL if now.weekday() >= 5 else _WEEKDAY_LOGICAL


def _current_window() -> dict | None:
    """Return the active window dict if we're inside one, else None."""
    now = datetime.now(_THAI_TZ)
    minutes = now.hour * 60 + now.minute
    for w in _get_windows():
        for start, end in w["ranges"]:
            if start <= minutes <= end:
                return w
    return None


def can_trade_now() -> bool:
    """
    Return True if we are inside an active trading window.
    There is no maximum cap — minimum 1 full cycle trade per window is a floor, not a ceiling.
    """
    return _current_window() is not None


def record_trade() -> None:
    """Increment the trade count for the current window."""
    window = _current_window()
    if window is None:
        return
    state = _load_state()
    state["windows"][window["name"]] = state["windows"].get(window["name"], 0) + 1
    _save_state(state)


def window_status() -> dict:
    """
    Return a summary of today's window quotas and usage.

    Returns:
        dict: {
            "date": "YYYY-MM-DD",
            "is_trading_day": bool,
            "current_window": str | None,
            "can_trade": bool,
            "windows": [{"name": str, "quota": int, "used": int, "remaining": int}]
        }
    """
    now = datetime.now(_THAI_TZ)
    state = _load_state()
    windows = _get_windows()
    window = _current_window()

    result = []
    for w in windows:
        used = state["windows"].get(w["name"], 0)
        result.append({
            "name":       w["name"],
            "min_trades": w["min_trades"],
            "used":       used,
            "still_need": max(0, w["min_trades"] - used),
        })

    return {
        "date":            _today_str(),
        "is_weekday":      now.weekday() < 5,
        "current_window":  window["name"] if window else None,
        "can_trade":       can_trade_now(),
        "windows":         result,
    }


def trades_remaining_today() -> int:
    """Return total minimum trades still required today (floor, not ceiling)."""
    state = _load_state()
    total = 0
    for w in _get_windows():
        used = state["windows"].get(w["name"], 0)
        total += max(0, w["min_trades"] - used)
    return total


def current_window_quota_met() -> bool:
    """Return True if the current window has already reached its minimum quota."""
    window = _current_window()
    if window is None:
        return True
    state = _load_state()
    used = state["windows"].get(window["name"], 0)
    return used >= window["min_trades"]


def minutes_until_window_end() -> int | None:
    """Return minutes remaining in the current window, or None if not in a window."""
    now = datetime.now(_THAI_TZ)
    minutes = now.hour * 60 + now.minute
    for w in _get_windows():
        for start, end in w["ranges"]:
            if start <= minutes <= end:
                return end - minutes
    return None


# ─── Standalone test ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    status = window_status()
    print(f"Date       : {status['date']}")
    print(f"Weekday    : {status['is_weekday']}")
    print(f"In window  : {status['current_window']}")
    print(f"Can trade  : {status['can_trade']}")
    print(f"Remaining  : {trades_remaining_today()}")
    print("\nWindow breakdown:")
    for w in status["windows"]:
        print(f"  {w['name']:12} {w['used']} used (min {w['min_trades']}, still need {w['still_need']})")
