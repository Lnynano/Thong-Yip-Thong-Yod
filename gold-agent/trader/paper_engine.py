"""
trader/paper_engine.py
Paper trading engine — simulates trades with real market prices,
tracks portfolio state, P&L, win rate, and trade history.
No real money is touched.

Storage strategy (auto-detected):
  - MONGODB_URI set  →  MongoDB Atlas (persistent across deploys)
  - MONGODB_URI not set  →  local data/portfolio.json (dev fallback)

Starting balance : 1,500 THB  (configurable)
Min trade size   : 1,000 THB  (mirrors AOM NOW minimum)
Confidence gate  : >= 65%     (only trade high-conviction signals)
Position model   : Long-only  (BUY to open, SELL to close — no shorting)
Sizing           : 95% of available balance per trade
"""

import os
import json
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# Thai timezone UTC+7
_THAI_TZ = timezone(timedelta(hours=7))

load_dotenv()

PORTFOLIO_FILE  = os.path.join(os.path.dirname(__file__), "..", "data", "portfolio.json")
DEFAULT_BALANCE = 1500.0
MIN_TRADE_THB   = 1000.0
CONF_THRESHOLD  = 65

# ── Risk management constants ─────────────────────────────────
TAKE_PROFIT_PCT = 0.015   # +1.5% → auto SELL (lock profit)
STOP_LOSS_PCT   = -0.010  # -1.0% → auto SELL (cut loss)
COOLDOWN_ROUNDS = 2       # rounds to skip after closing a trade

# ─────────────────────────────────────────────────────────────
# MongoDB client (lazy init — only when MONGODB_URI is set)
# ─────────────────────────────────────────────────────────────
_mongo_client = None
_mongo_db     = None


def _get_mongo_collection(name: str):
    """Return a MongoDB collection, or None if MONGODB_URI is not configured."""
    global _mongo_client, _mongo_db
    uri = os.getenv("MONGODB_URI", "").strip()
    if not uri:
        return None
    try:
        if _mongo_client is None:
            from pymongo import MongoClient
            _mongo_client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            _mongo_db     = _mongo_client["gold_agent"]
            print("[paper_engine.py] Connected to MongoDB Atlas.")
        return _mongo_db[name]
    except Exception as e:
        print(f"[paper_engine.py] MongoDB connection failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# Load / Save  (MongoDB first, JSON fallback)
# ─────────────────────────────────────────────────────────────
def _load() -> dict:
    """Load portfolio state from MongoDB or local JSON fallback."""
    col = _get_mongo_collection("portfolio")
    if col is not None:
        try:
            doc = col.find_one({"_id": "main"})
            if doc:
                doc.pop("_id", None)
                return doc
        except Exception as e:
            print(f"[paper_engine.py] MongoDB load failed, using JSON: {e}")

    # JSON fallback
    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return _fresh_state()


def _save(state: dict) -> None:
    """Persist portfolio state to MongoDB or local JSON fallback."""
    col = _get_mongo_collection("portfolio")
    if col is not None:
        try:
            col.replace_one({"_id": "main"}, {"_id": "main", **state}, upsert=True)
            return
        except Exception as e:
            print(f"[paper_engine.py] MongoDB save failed, using JSON: {e}")

    # JSON fallback
    try:
        os.makedirs(os.path.dirname(PORTFOLIO_FILE), exist_ok=True)
        with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[paper_engine.py] JSON save failed: {e}")


# ─────────────────────────────────────────────────────────────
# State helpers
# ─────────────────────────────────────────────────────────────
def _fresh_state(initial_balance: float = DEFAULT_BALANCE) -> dict:
    """Return a blank portfolio state."""
    return {
        "initial_balance": initial_balance,
        "balance":         initial_balance,
        "open_position":   None,
        "closed_trades":   [],
        "equity_history":  [
            {"time": datetime.now(_THAI_TZ).strftime("%Y-%m-%d %H:%M"), "equity": initial_balance}
        ],
        "cooldown":        0,   # rounds remaining before next BUY allowed
    }


def _record_equity(state: dict, price_thb: float) -> None:
    """Append current total equity to history for the P&L curve."""
    pos    = state["open_position"]
    value  = (pos["size_bw"] * price_thb) if pos else 0.0
    equity = state["balance"] + value
    state["equity_history"].append({
        "time":   datetime.now(_THAI_TZ).strftime("%Y-%m-%d %H:%M"),
        "equity": round(equity, 2),
    })
    if len(state["equity_history"]) > 500:
        state["equity_history"] = state["equity_history"][-500:]


# ─────────────────────────────────────────────────────────────
# Core trading logic
# ─────────────────────────────────────────────────────────────
def execute_paper_trade(decision: str, confidence: int, price_thb: float) -> dict:
    """
    Evaluate the agent decision and simulate a trade if conditions are met.

    Logic:
      BUY  + conf >= 65% + no open position  ->  OPEN long
      SELL + conf >= 65% + open position     ->  CLOSE long (realise P&L)
      anything else                          ->  skip / hold

    Args:
        decision   : "BUY", "SELL", or "HOLD"
        confidence : 0-100 from the agent
        price_thb  : current gold price THB per baht-weight (96.5% purity)

    Returns:
        dict: action, reason, pnl_thb (if closed), trade record (if closed)
    """
    state = _load()

    if price_thb <= 0:
        return {"action": "SKIP", "reason": "Invalid price"}

    now = datetime.now(_THAI_TZ).strftime("%Y-%m-%d %H:%M:%S")

    # ── Auto TP/SL check (overrides agent decision) ─────────
    pos = state["open_position"]
    if pos is not None:
        change_pct = (price_thb - pos["entry_price"]) / pos["entry_price"]
        if change_pct >= TAKE_PROFIT_PCT:
            decision   = "SELL"
            confidence = 100
            print(f"[paper_engine.py] TAKE PROFIT triggered at {change_pct*100:+.2f}%")
        elif change_pct <= STOP_LOSS_PCT:
            decision   = "SELL"
            confidence = 100
            print(f"[paper_engine.py] STOP LOSS triggered at {change_pct*100:+.2f}%")

    # ── Confidence gate (skip TP/SL override) ────────────────
    if confidence < CONF_THRESHOLD:
        return {"action": "SKIP",
                "reason": f"Confidence {confidence}% < {CONF_THRESHOLD}% threshold"}

    # ── Cooldown check ────────────────────────────────────────
    cooldown = state.get("cooldown", 0)
    if cooldown > 0 and decision == "BUY":
        state["cooldown"] = cooldown - 1
        _save(state)
        return {"action": "SKIP",
                "reason": f"Cooldown active — {cooldown} round(s) remaining"}

    # ── Open long ────────────────────────────────────────────
    if decision == "BUY" and state["open_position"] is None:
        available = state["balance"]
        if available < MIN_TRADE_THB:
            return {"action": "SKIP",
                    "reason": f"Balance {available:.0f} THB < minimum {MIN_TRADE_THB:.0f} THB"}

        cost    = available * 0.95
        size_bw = cost / price_thb
        state["balance"]       -= cost
        state["open_position"]  = {
            "direction":   "BUY",
            "entry_price": price_thb,
            "size_bw":     round(size_bw, 6),
            "cost_thb":    round(cost, 2),
            "entry_time":  now,
        }
        state["cooldown"] = 0
        _record_equity(state, price_thb)
        _save(state)
        print(f"[paper_engine.py] OPENED  {size_bw:.5f} bw @ {price_thb:,.0f} THB  "
              f"TP={price_thb*(1+TAKE_PROFIT_PCT):,.0f}  SL={price_thb*(1+STOP_LOSS_PCT):,.0f}")
        return {"action": "OPENED", "size_bw": size_bw,
                "price_thb": price_thb, "cost_thb": cost,
                "tp_price": round(price_thb * (1 + TAKE_PROFIT_PCT), 0),
                "sl_price": round(price_thb * (1 + STOP_LOSS_PCT), 0)}

    # ── Close long ───────────────────────────────────────────
    if decision == "SELL" and state["open_position"] is not None:
        pos      = state["open_position"]
        proceeds = pos["size_bw"] * price_thb
        pnl      = proceeds - pos["cost_thb"]
        pnl_pct  = pnl / pos["cost_thb"] * 100

        state["balance"] += proceeds
        trade = {
            "entry_time":  pos["entry_time"],
            "exit_time":   now,
            "entry_price": pos["entry_price"],
            "exit_price":  price_thb,
            "size_bw":     pos["size_bw"],
            "cost_thb":    pos["cost_thb"],
            "pnl_thb":     round(pnl, 2),
            "pnl_pct":     round(pnl_pct, 2),
            "outcome":     "WIN" if pnl >= 0 else "LOSS",
        }
        state["closed_trades"].append(trade)
        state["open_position"] = None
        state["cooldown"]      = COOLDOWN_ROUNDS   # start cooldown after close
        _record_equity(state, price_thb)
        _save(state)
        print(f"[paper_engine.py] CLOSED  {trade['outcome']}  "
              f"P&L {pnl:+.2f} THB ({pnl_pct:+.2f}%)  "
              f"cooldown={COOLDOWN_ROUNDS} rounds")
        return {"action": "CLOSED", "pnl_thb": pnl,
                "pnl_pct": pnl_pct, "outcome": trade["outcome"], "trade": trade}

    if decision == "BUY" and state["open_position"] is not None:
        return {"action": "SKIP", "reason": "Already holding a position"}

    # Tick down cooldown on HOLD too
    if cooldown > 0:
        state["cooldown"] = cooldown - 1
        _save(state)

    return {"action": "HOLD", "reason": "Signal is HOLD or no matching position"}


# ─────────────────────────────────────────────────────────────
# Portfolio queries
# ─────────────────────────────────────────────────────────────
def get_portfolio_summary(current_price_thb: float = 0.0) -> dict:
    """
    Return all portfolio metrics for dashboard display.

    Args:
        current_price_thb: latest price to compute unrealised P&L.
    """
    state  = _load()
    closed = state["closed_trades"]
    pos    = state["open_position"]

    wins   = [t for t in closed if t["outcome"] == "WIN"]
    losses = [t for t in closed if t["outcome"] == "LOSS"]

    realized_pnl = sum(t["pnl_thb"] for t in closed)
    win_rate     = len(wins) / len(closed) if closed else 0.0
    avg_win      = sum(t["pnl_thb"] for t in wins)  / len(wins)  if wins   else 0.0
    avg_loss_val = abs(sum(t["pnl_thb"] for t in losses) / len(losses)) if losses else 0.0
    rr_ratio     = avg_win / avg_loss_val if avg_loss_val > 0 else 0.0

    unrealized_pnl = 0.0
    open_info      = None
    if pos and current_price_thb > 0:
        unrealized_pnl = (pos["size_bw"] * current_price_thb) - pos["cost_thb"]
        open_info = {
            "entry_price":    pos["entry_price"],
            "current_price":  current_price_thb,
            "size_bw":        pos["size_bw"],
            "cost_thb":       pos["cost_thb"],
            "unrealized":     round(unrealized_pnl, 2),
            "unrealized_pct": round(unrealized_pnl / pos["cost_thb"] * 100, 2),
            "entry_time":     pos["entry_time"],
        }

    pos_value    = (pos["size_bw"] * current_price_thb) if (pos and current_price_thb > 0) \
                   else (pos["cost_thb"] if pos else 0.0)
    total_equity = state["balance"] + pos_value
    total_pnl    = total_equity - state["initial_balance"]

    return {
        "initial_balance": state["initial_balance"],
        "cash_balance":    round(state["balance"], 2),
        "total_equity":    round(total_equity, 2),
        "realized_pnl":    round(realized_pnl, 2),
        "unrealized_pnl":  round(unrealized_pnl, 2),
        "total_pnl":       round(total_pnl, 2),
        "total_pnl_pct":   round(total_pnl / state["initial_balance"] * 100, 2),
        "win_rate":        round(win_rate * 100, 1),
        "wins":            len(wins),
        "losses":          len(losses),
        "total_trades":    len(closed),
        "rr_ratio":        round(rr_ratio, 2),
        "open_position":   open_info,
        "has_position":    pos is not None,
        "avg_win":         round(avg_win, 2),
        "avg_loss":        round(avg_loss_val, 2),
    }


def get_trade_history(n: int = 20) -> list:
    """Return last n closed trades, newest first."""
    state = _load()
    return list(reversed(state["closed_trades"]))[:n]


def get_equity_history() -> list:
    """Return equity history for P&L curve chart."""
    return _load().get("equity_history", [])


def get_recent_outcomes(n: int = 15) -> list:
    """Return last n outcomes as WIN/LOSS strings for the coloured bar."""
    return [t["outcome"] for t in reversed(get_trade_history(n))]


def reset_portfolio(initial_balance: float = DEFAULT_BALANCE) -> None:
    """Wipe all trades and reset to a fresh portfolio."""
    _save(_fresh_state(initial_balance))
    print(f"[paper_engine.py] Reset. Balance: {initial_balance:,.0f} THB")
