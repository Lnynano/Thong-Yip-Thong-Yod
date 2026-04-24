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
Typical position size : 90%-100% of available balance (Aggressive).
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
TAKE_PROFIT_PCT = 0.015   # +1.5% -> auto SELL (lock profit)
STOP_LOSS_PCT   = -0.010  # -1.0% -> auto SELL (cut loss)
TRAILING_SL_PCT = 0.007   # trailing stop: 0.7% below highest price since entry
COOLDOWN_ROUNDS = 0       # normal cooldown (disabled)
LOSS_COOLDOWN   = 1       # extra cooldown after a LOSS trade — skip 1 cycle to avoid revenge trading

# ── Position sizing by confidence ────────────────────────────
# Higher confidence = larger position. Prevents betting big on weak signals.
#   65-74% -> 90% of balance
#   75-84% -> 95% of balance
#   85%+   -> 100% of balance
def _size_pct_by_confidence(confidence: int) -> float:
    """Return position size as fraction of balance based on confidence."""
    if confidence >= 85:
        return 1.00
    elif confidence >= 75:
        return 0.95
    else:
        return 0.90

# ── Trading fee constants (loaded from env) ───────────────────
# Applied on every transaction (both open and close).
# TRADE_FEE_PCT      : percentage of trade value (e.g. 0.005 = 0.5% spread)
# TRADE_FEE_FLAT_THB : flat fee in THB per transaction (e.g. 15 THB)
TRADE_FEE_PCT      = float(os.getenv("TRADE_FEE_PCT", "0.005"))
TRADE_FEE_FLAT_THB = float(os.getenv("TRADE_FEE_FLAT_THB", "0"))

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
    state = None
    col = _get_mongo_collection("portfolio")
    if col is not None:
        try:
            doc = col.find_one({"_id": "main"})
            if doc:
                doc.pop("_id", None)
                state = doc
        except Exception as e:
            print(f"[paper_engine.py] MongoDB load failed, using JSON: {e}")

    # JSON fallback
    if state is None and os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            pass
            
    if state is None:
        state = _fresh_state()
        
    if "open_position" in state and state["open_position"] is not None:
        state.setdefault("open_positions", []).append(state["open_position"])
    if "open_position" in state:
        del state["open_position"]
    if "open_positions" not in state:
        state["open_positions"] = []
        
    return state


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
        "open_positions":  [],
        "closed_trades":   [],
        "equity_history":  [
            {"time": datetime.now(_THAI_TZ).strftime("%Y-%m-%d %H:%M"), "equity": initial_balance}
        ],
        "cooldown":        0,   # rounds remaining before next BUY allowed
    }


def _record_equity(state: dict, price_thb: float) -> None:
    """Append current total equity to history for the P&L curve."""
    positions = state.get("open_positions", [])
    value     = sum(p["size_bw"] * price_thb for p in positions)
    equity    = state["balance"] + value
    state["equity_history"].append({
        "time":   datetime.now(_THAI_TZ).strftime("%Y-%m-%d %H:%M"),
        "equity": round(equity, 2),
    })
    if len(state["equity_history"]) > 500:
        state["equity_history"] = state["equity_history"][-500:]


# ─────────────────────────────────────────────────────────────
# Core trading logic
# ─────────────────────────────────────────────────────────────
def _calc_fee(trade_value_thb: float) -> float:
    """Calculate total fee for a single transaction (open or close)."""
    return round(trade_value_thb * TRADE_FEE_PCT + TRADE_FEE_FLAT_THB, 2)


def execute_paper_trade(decision: str, confidence: int, price_thb: float, min_confidence: int | None = None) -> dict:
    """
    Evaluate the agent decision and simulate a trade if conditions are met.

    Logic:
      BUY  + conf >= 65% + no open position  ->  OPEN long
      SELL + conf >= 65% + open position     ->  CLOSE long (realise P&L)
      anything else                          ->  skip / hold

    Fees (from env):
      TRADE_FEE_PCT      : % of trade value charged per transaction
      TRADE_FEE_FLAT_THB : flat THB fee per transaction
      Total fee = trade_value × TRADE_FEE_PCT + TRADE_FEE_FLAT_THB
      Applied on both open and close. P&L is always net of fees.

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

    # ── Auto TP/SL + trailing stop check (overrides agent decision) ──
    for pos in state.get("open_positions", []):
        entry = pos["entry_price"]
        change_pct = (price_thb - entry) / entry

        # Update highest price seen (for trailing stop)
        highest = max(pos.get("highest_price", entry), price_thb)
        pos["highest_price"] = highest

        # Trailing stop: if price drops TRAILING_SL_PCT below the peak
        trailing_sl_price = highest * (1 - TRAILING_SL_PCT)
        trailing_triggered = (price_thb <= trailing_sl_price and highest > entry)

        if change_pct >= TAKE_PROFIT_PCT or trailing_triggered or change_pct <= STOP_LOSS_PCT:
            decision   = "SELL"
            confidence = 100
            print(f"[paper_engine.py] TP/SL triggered for a position!")
            break
    _save(state)  # persist updated highest_price

    # ── Confidence gate (skip TP/SL override) ────────────────
    effective_gate = min_confidence if min_confidence is not None else CONF_THRESHOLD
    if confidence < effective_gate:
        return {"action": "SKIP",
                "reason": f"Confidence {confidence}% < {effective_gate}% threshold"}

    # ── Cooldown check ────────────────────────────────────────
    cooldown = state.get("cooldown", 0)
    if cooldown > 0 and decision == "BUY":
        state["cooldown"] = cooldown - 1
        _save(state)
        return {"action": "SKIP",
                "reason": f"Cooldown active — {cooldown} round(s) remaining"}

    # ── Open long ────────────────────────────────────────────
    if decision == "BUY":
        available = state["balance"]
        if available < MIN_TRADE_THB:
            return {"action": "SKIP",
                    "reason": f"Balance {available:.0f} THB < minimum {MIN_TRADE_THB:.0f} THB"}

        size_pct = _size_pct_by_confidence(confidence)
        gross   = available * size_pct      # confidence-scaled position    
        if gross < MIN_TRADE_THB:
            return {"action": "SKIP", "reason": f"Trade size {gross:.0f} THB < minimum 1000 THB"}
        fee     = _calc_fee(gross)          # fee on open
        cost    = round(gross + fee, 2)     # total deducted from balance
        size_bw = gross / price_thb         # gold bought with gross amount (fee is overhead)

        state["balance"]       -= cost
        state["open_positions"].append({
            "direction":    "BUY",
            "entry_price":  price_thb,
            "highest_price": price_thb,   # for trailing stop
            "size_bw":      round(size_bw, 6),
            "cost_thb":     round(gross, 2),  # gross cost (excluding fee) for P&L base
            "open_fee":     fee,
            "entry_time":   now,
            "confidence":   confidence,
            "size_pct":     size_pct,
        })
        state["cooldown"] = 0
        _record_equity(state, price_thb)
        _save(state)
        print(f"[paper_engine.py] OPENED  {size_bw:.5f} bw @ {price_thb:,.0f} THB  "
              f"conf={confidence}% size={size_pct*100:.0f}%  fee={fee:.2f} THB  "
              f"TP={price_thb*(1+TAKE_PROFIT_PCT):,.0f} (calculated)  "
              f"SL={price_thb*(1+STOP_LOSS_PCT):,.0f} (calculated)  "
              f"Trail={TRAILING_SL_PCT*100:.1f}%")
        return {"action": "OPENED", "size_bw": size_bw,
                "price_thb": price_thb, "cost_thb": gross, "fee_thb": fee,
                "tp_price": round(price_thb * (1 + TAKE_PROFIT_PCT), 0),
                "sl_price": round(price_thb * (1 + STOP_LOSS_PCT), 0)}

    # ── Close long ───────────────────────────────────────────
    if decision == "SELL" and state.get("open_positions"):
        total_pnl = 0.0
        any_loss = False
        for pos in state["open_positions"]:
            gross_proceeds = pos["size_bw"] * price_thb
            close_fee    = _calc_fee(gross_proceeds)              # fee on close
            open_fee     = pos.get("open_fee", 0.0)
            net_proceeds = round(gross_proceeds - close_fee, 2)  # actually received
            total_fees   = round(open_fee + close_fee, 2)
            pnl          = net_proceeds - pos["cost_thb"]        # net of ALL fees
            pnl_pct      = pnl / pos["cost_thb"] * 100
            
            total_pnl += pnl
            if pnl < 0: any_loss = True
            
            state["balance"] = max(0.0, state["balance"] + net_proceeds)  # floor at 0
            trade = {
                "entry_time":  pos["entry_time"],
                "exit_time":   now,
                "entry_price": pos["entry_price"],
                "exit_price":  price_thb,
                "size_bw":     pos["size_bw"],
                "cost_thb":    pos["cost_thb"],
                "open_fee":    open_fee,
                "close_fee":   close_fee,
                "total_fees":  total_fees,
                "pnl_thb":     round(pnl, 2),
                "pnl_pct":     round(pnl_pct, 2),
                "outcome":     "WIN" if pnl >= 0 else "LOSS",
            }
            state["closed_trades"].append(trade)
            
        state["open_positions"] = []
        # Cooldown: extra pause after a LOSS to prevent revenge trading
        cooldown_applied = LOSS_COOLDOWN if any_loss else COOLDOWN_ROUNDS
        state["cooldown"] = cooldown_applied
        print(f"[paper_engine.py] CLOSED  BASKET  "
              f"Total P&L {total_pnl:+.2f} THB  cooldown={cooldown_applied} rounds")
        return {"action": "CLOSED", "pnl_thb": total_pnl, "trade": state["closed_trades"][-1]}

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
    positions = state.get("open_positions", [])
    
    wins   = [t for t in closed if t["outcome"] == "WIN"]
    losses = [t for t in closed if t["outcome"] == "LOSS"]

    realized_pnl = sum(t["pnl_thb"] for t in closed)
    total_fees   = sum(t.get("total_fees", 0.0) for t in closed)
    win_rate     = len(wins) / len(closed) if closed else 0.0
    avg_win      = sum(t["pnl_thb"] for t in wins)  / len(wins)  if wins   else 0.0
    avg_loss_val = abs(sum(t["pnl_thb"] for t in losses) / len(losses)) if losses else 0.0
    rr_ratio     = avg_win / avg_loss_val if avg_loss_val > 0 else 0.0

    unrealized_pnl = 0.0
    open_info      = None
    if positions and current_price_thb > 0:
        unrealized_pnl = sum((pos["size_bw"] * current_price_thb) - pos["cost_thb"] for pos in positions)
        total_cost = sum(pos["cost_thb"] for pos in positions)
        open_info = {
            "entry_price":    positions[-1]["entry_price"],  # Just show latest for UI simplicity
            "current_price":  current_price_thb,
            "size_bw":        sum(pos["size_bw"] for pos in positions),
            "cost_thb":       total_cost,
            "unrealized":     round(unrealized_pnl, 2),
            "unrealized_pct": round(unrealized_pnl / total_cost * 100, 2) if total_cost > 0 else 0.0,
            "entry_time":     positions[-1]["entry_time"],
        }

    pos_value = sum((pos["size_bw"] * current_price_thb) if current_price_thb > 0 else pos["cost_thb"] for pos in positions)
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
        "has_position":    len(positions) > 0,
        "avg_win":         round(avg_win, 2),
        "avg_loss":        round(avg_loss_val, 2),
        "total_fees":      round(total_fees, 2),
        "fee_pct":         TRADE_FEE_PCT,
        "fee_flat":        TRADE_FEE_FLAT_THB,
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


def get_performance_report(current_price_thb: float = 0.0) -> str:
    """
    Generate a text performance report for export/presentation.

    Returns:
        str: Formatted multi-line performance summary.
    """
    p = get_portfolio_summary(current_price_thb)

    # LLM costs
    try:
        from logger.cost_tracker import get_cost_summary
        cost = get_cost_summary()
        llm_cost = cost["total_cost_thb"]
        llm_calls = cost["call_count"]
    except Exception:
        llm_cost = 0.0
        llm_calls = 0

    net_after_llm = p["total_equity"] - llm_cost

    lines = [
        "=" * 50,
        "  PERFORMANCE REPORT - Gold Trading Agent",
        "=" * 50,
        f"  Initial capital  : {p['initial_balance']:,.2f} THB",
        f"  Current equity   : {p['total_equity']:,.2f} THB",
        f"  Total P&L        : {p['total_pnl']:+,.2f} THB ({p['total_pnl_pct']:+.2f}%)",
        f"  Realized P&L     : {p['realized_pnl']:+,.2f} THB",
        f"  Unrealized P&L   : {p['unrealized_pnl']:+,.2f} THB",
        f"  Trading fees     : {p['total_fees']:,.2f} THB",
        "",
        f"  Total trades     : {p['total_trades']}",
        f"  Wins / Losses    : {p['wins']} / {p['losses']}",
        f"  Win rate         : {p['win_rate']:.1f}%",
        f"  Avg win          : {p['avg_win']:+,.2f} THB",
        f"  Avg loss         : {p['avg_loss']:,.2f} THB",
        f"  Risk/Reward      : {p['rr_ratio']:.2f}:1",
        "",
        f"  LLM API calls    : {llm_calls}",
        f"  LLM API cost     : {llm_cost:,.2f} THB",
        f"  Net after LLM    : {net_after_llm:,.2f} THB",
        "",
        f"  Rules: gate={CONF_THRESHOLD}%  TP=+{TAKE_PROFIT_PCT*100:.1f}%  "
        f"SL={STOP_LOSS_PCT*100:.1f}%  Trail={TRAILING_SL_PCT*100:.1f}%",
        f"  Loss cooldown    : {LOSS_COOLDOWN} round(s)",
        "=" * 50,
    ]
    return "\n".join(lines)


def reset_portfolio(initial_balance: float = DEFAULT_BALANCE) -> None:
    """Wipe all trades and reset to a fresh portfolio."""
    _save(_fresh_state(initial_balance))
    print(f"[paper_engine.py] Reset. Balance: {initial_balance:,.0f} THB")
