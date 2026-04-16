"""
tests/test_paper_engine.py
Mock-based unit tests for trader/paper_engine.py.

All tests patch _load / _save so no portfolio.json is read or written.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

import trader.paper_engine as pe


# ─── helpers ──────────────────────────────────────────────────────────────────

PRICE = 45_000.0   # 45,000 THB / baht-weight — a round test price


def fresh() -> dict:
    """Return a clean in-memory state (mirrors _fresh_state)."""
    return {
        "initial_balance": 1500.0,
        "balance":         1500.0,
        "open_position":   None,
        "closed_trades":   [],
        "equity_history":  [{"time": "2026-01-01 00:00", "equity": 1500.0}],
    }


def state_with_position(entry_price: float = PRICE) -> dict:
    """State that already has an open BUY position."""
    s = fresh()
    cost = s["balance"] * 0.95        # 1425 THB
    size = cost / entry_price
    s["balance"] -= cost
    s["open_position"] = {
        "direction":   "BUY",
        "entry_price": entry_price,
        "size_bw":     round(size, 6),
        "cost_thb":    round(cost, 2),
        "entry_time":  "2026-01-01 09:00:00",
    }
    return s


def state_with_closed_trade(pnl: float = 100.0) -> dict:
    """State with one completed trade."""
    s = fresh()
    outcome = "WIN" if pnl >= 0 else "LOSS"
    s["closed_trades"].append({
        "entry_time":  "2026-01-01 09:00:00",
        "exit_time":   "2026-01-01 10:00:00",
        "entry_price": PRICE,
        "exit_price":  PRICE + (pnl / 0.03165),  # back-calculate exit price
        "size_bw":     0.03165,
        "cost_thb":    1425.0,
        "pnl_thb":     round(pnl, 2),
        "pnl_pct":     round(pnl / 1425.0 * 100, 2),
        "outcome":     outcome,
    })
    s["balance"] = 1500.0 + pnl
    return s


# ─── execute_paper_trade ──────────────────────────────────────────────────────

class TestExecutePaperTrade:

    def test_invalid_price_returns_skip(self):
        with patch.object(pe, "_load", return_value=fresh()), \
             patch.object(pe, "_save"):
            result = pe.execute_paper_trade("BUY", 80, 0)
        assert result["action"] == "SKIP"
        assert "Invalid price" in result["reason"]

    def test_low_confidence_returns_skip(self):
        with patch.object(pe, "_load", return_value=fresh()), \
             patch.object(pe, "_save"):
            result = pe.execute_paper_trade("BUY", 64, PRICE)
        assert result["action"] == "SKIP"
        assert "64%" in result["reason"]

    def test_confidence_at_threshold_is_accepted(self):
        with patch.object(pe, "_load", return_value=fresh()), \
             patch.object(pe, "_save"):
            result = pe.execute_paper_trade("BUY", 65, PRICE)
        assert result["action"] == "OPENED"

    def test_buy_opens_position(self):
        s = fresh()
        saved = {}

        def capture_save(state):
            saved.update(state)

        with patch.object(pe, "_load", return_value=s), \
             patch.object(pe, "_save", side_effect=capture_save):
            result = pe.execute_paper_trade("BUY", 70, PRICE)

        assert result["action"] == "OPENED"
        assert result["price_thb"] == PRICE
        assert saved["open_position"] is not None
        assert saved["open_position"]["direction"] == "BUY"
        # conf=70% → 60% size_pct → cost = 1500 * 0.60 = 900 THB
        assert abs(saved["open_position"]["cost_thb"] - 900.0) < 0.01
        # balance should be 1500 - 900 = 600 THB
        assert abs(saved["balance"] - 600.0) < 0.01

    def test_buy_size_calculation(self):
        """size_bw = cost / price_thb — conf=70% uses 60% of balance = 900 / 45000"""
        s = fresh()
        with patch.object(pe, "_load", return_value=s), \
             patch.object(pe, "_save"):
            result = pe.execute_paper_trade("BUY", 70, PRICE)
        expected_size = 900.0 / PRICE   # 60% allocation at conf=70%
        assert abs(result["size_bw"] - expected_size) < 1e-6

    def test_buy_when_position_already_open_skips(self):
        with patch.object(pe, "_load", return_value=state_with_position()), \
             patch.object(pe, "_save"):
            result = pe.execute_paper_trade("BUY", 80, PRICE)
        assert result["action"] == "SKIP"
        assert "Already holding" in result["reason"]

    def test_buy_when_balance_too_low_skips(self):
        s = fresh()
        s["balance"] = 500.0   # below 1000 THB minimum
        with patch.object(pe, "_load", return_value=s), \
             patch.object(pe, "_save"):
            result = pe.execute_paper_trade("BUY", 80, PRICE)
        assert result["action"] == "SKIP"
        assert "minimum" in result["reason"].lower()

    def test_sell_closes_position_with_profit(self):
        exit_price = PRICE * 1.02   # 2% higher → profit
        s = state_with_position(entry_price=PRICE)
        saved = {}

        def capture_save(state):
            saved.update(state)

        with patch.object(pe, "_load", return_value=s), \
             patch.object(pe, "_save", side_effect=capture_save):
            result = pe.execute_paper_trade("SELL", 75, exit_price)

        assert result["action"] == "CLOSED"
        assert result["outcome"] == "WIN"
        assert result["pnl_thb"] > 0
        assert saved["open_position"] is None
        assert len(saved["closed_trades"]) == 1

    def test_sell_closes_position_with_loss(self):
        exit_price = PRICE * 0.98   # 2% lower → loss
        s = state_with_position(entry_price=PRICE)
        with patch.object(pe, "_load", return_value=s), \
             patch.object(pe, "_save"):
            result = pe.execute_paper_trade("SELL", 75, exit_price)

        assert result["action"] == "CLOSED"
        assert result["outcome"] == "LOSS"
        assert result["pnl_thb"] < 0

    def test_sell_pnl_calculation(self):
        """Verify P&L math: proceeds - cost_thb"""
        entry_price = 45_000.0
        exit_price  = 46_000.0
        s = state_with_position(entry_price=entry_price)
        cost    = s["open_position"]["cost_thb"]
        size_bw = s["open_position"]["size_bw"]
        expected_pnl = (size_bw * exit_price) - cost

        with patch.object(pe, "_load", return_value=s), \
             patch.object(pe, "_save"):
            result = pe.execute_paper_trade("SELL", 70, exit_price)

        assert abs(result["pnl_thb"] - round(expected_pnl, 2)) < 0.01

    def test_sell_with_no_open_position_holds(self):
        with patch.object(pe, "_load", return_value=fresh()), \
             patch.object(pe, "_save"):
            result = pe.execute_paper_trade("SELL", 80, PRICE)
        assert result["action"] == "HOLD"

    def test_hold_decision_returns_hold(self):
        with patch.object(pe, "_load", return_value=fresh()), \
             patch.object(pe, "_save"):
            result = pe.execute_paper_trade("HOLD", 80, PRICE)
        assert result["action"] == "HOLD"

    def test_save_is_called_on_open(self):
        mock_save = MagicMock()
        with patch.object(pe, "_load", return_value=fresh()), \
             patch.object(pe, "_save", mock_save):
            pe.execute_paper_trade("BUY", 70, PRICE)
        mock_save.assert_called_once()

    def test_save_is_called_on_close(self):
        mock_save = MagicMock()
        with patch.object(pe, "_load", return_value=state_with_position()), \
             patch.object(pe, "_save", mock_save):
            pe.execute_paper_trade("SELL", 70, PRICE * 1.01)
        # _save is called at least once: once to persist trailing-stop peak,
        # once more to persist the closed trade — both are valid & expected
        mock_save.assert_called()

    def test_save_not_called_on_skip(self):
        mock_save = MagicMock()
        with patch.object(pe, "_load", return_value=fresh()), \
             patch.object(pe, "_save", mock_save):
            pe.execute_paper_trade("BUY", 10, PRICE)   # confidence too low
        mock_save.assert_not_called()


# ─── get_portfolio_summary ────────────────────────────────────────────────────

class TestGetPortfolioSummary:

    def test_fresh_portfolio_defaults(self):
        with patch.object(pe, "_load", return_value=fresh()):
            summary = pe.get_portfolio_summary(0.0)

        assert summary["initial_balance"] == 1500.0
        assert summary["cash_balance"]    == 1500.0
        assert summary["total_equity"]    == 1500.0
        assert summary["realized_pnl"]    == 0.0
        assert summary["unrealized_pnl"]  == 0.0
        assert summary["total_trades"]    == 0
        assert summary["win_rate"]        == 0.0
        assert summary["has_position"]    is False

    def test_win_rate_single_win(self):
        s = state_with_closed_trade(pnl=100.0)
        with patch.object(pe, "_load", return_value=s):
            summary = pe.get_portfolio_summary(0.0)
        assert summary["win_rate"] == 100.0
        assert summary["wins"]     == 1
        assert summary["losses"]   == 0

    def test_win_rate_single_loss(self):
        s = state_with_closed_trade(pnl=-50.0)
        with patch.object(pe, "_load", return_value=s):
            summary = pe.get_portfolio_summary(0.0)
        assert summary["win_rate"] == 0.0
        assert summary["wins"]     == 0
        assert summary["losses"]   == 1

    def test_realized_pnl_sum(self):
        s = state_with_closed_trade(pnl=200.0)
        with patch.object(pe, "_load", return_value=s):
            summary = pe.get_portfolio_summary(0.0)
        assert abs(summary["realized_pnl"] - 200.0) < 0.01

    def test_unrealized_pnl_with_open_position(self):
        s = state_with_position(entry_price=PRICE)
        current = PRICE * 1.05   # 5% up
        with patch.object(pe, "_load", return_value=s):
            summary = pe.get_portfolio_summary(current)

        assert summary["has_position"] is True
        assert summary["unrealized_pnl"] > 0
        open_info = summary["open_position"]
        assert open_info is not None
        assert open_info["entry_price"] == PRICE
        assert open_info["current_price"] == current

    def test_unrealized_pnl_zero_when_no_current_price(self):
        s = state_with_position(entry_price=PRICE)
        with patch.object(pe, "_load", return_value=s):
            summary = pe.get_portfolio_summary(0.0)
        assert summary["unrealized_pnl"] == 0.0

    def test_rr_ratio_calculation(self):
        """R:R = avg_win / avg_loss"""
        s = fresh()
        s["closed_trades"] = [
            {**state_with_closed_trade(100.0)["closed_trades"][0]},
            {**state_with_closed_trade(-50.0)["closed_trades"][0]},
        ]
        with patch.object(pe, "_load", return_value=s):
            summary = pe.get_portfolio_summary(0.0)
        assert abs(summary["rr_ratio"] - 2.0) < 0.01   # 100 / 50 = 2.0


# ─── get_trade_history ────────────────────────────────────────────────────────

class TestGetTradeHistory:

    def test_empty_history(self):
        with patch.object(pe, "_load", return_value=fresh()):
            history = pe.get_trade_history()
        assert history == []

    def test_returns_newest_first(self):
        s = fresh()
        s["closed_trades"] = [
            {"outcome": "WIN",  "exit_time": "2026-01-01 10:00:00"},
            {"outcome": "LOSS", "exit_time": "2026-01-02 10:00:00"},
        ]
        with patch.object(pe, "_load", return_value=s):
            history = pe.get_trade_history(10)
        assert history[0]["outcome"] == "LOSS"   # most recent first
        assert history[1]["outcome"] == "WIN"

    def test_n_limit(self):
        s = fresh()
        s["closed_trades"] = [{"outcome": "WIN"} for _ in range(25)]
        with patch.object(pe, "_load", return_value=s):
            history = pe.get_trade_history(5)
        assert len(history) == 5


# ─── get_equity_history ───────────────────────────────────────────────────────

class TestGetEquityHistory:

    def test_returns_initial_equity_entry(self):
        with patch.object(pe, "_load", return_value=fresh()):
            equity = pe.get_equity_history()
        assert len(equity) == 1
        assert equity[0]["equity"] == 1500.0

    def test_returns_list_of_dicts(self):
        with patch.object(pe, "_load", return_value=fresh()):
            equity = pe.get_equity_history()
        assert isinstance(equity, list)
        assert "time" in equity[0]
        assert "equity" in equity[0]


# ─── get_recent_outcomes ──────────────────────────────────────────────────────

class TestGetRecentOutcomes:

    def test_empty_when_no_trades(self):
        with patch.object(pe, "_load", return_value=fresh()):
            outcomes = pe.get_recent_outcomes()
        assert outcomes == []

    def test_outcomes_are_win_or_loss_strings(self):
        s = state_with_closed_trade(pnl=50.0)
        with patch.object(pe, "_load", return_value=s):
            outcomes = pe.get_recent_outcomes()
        assert all(o in ("WIN", "LOSS") for o in outcomes)

    def test_n_limit(self):
        s = fresh()
        s["closed_trades"] = [{"outcome": "WIN"} for _ in range(20)]
        with patch.object(pe, "_load", return_value=s):
            outcomes = pe.get_recent_outcomes(5)
        assert len(outcomes) == 5


# ─── reset_portfolio ─────────────────────────────────────────────────────────

class TestResetPortfolio:

    def test_reset_saves_fresh_state(self):
        captured = {}

        def capture_save(state):
            captured.update(state)

        with patch.object(pe, "_save", side_effect=capture_save):
            pe.reset_portfolio()

        assert captured["balance"] == 1500.0
        assert captured["open_position"] is None
        assert captured["closed_trades"] == []

    def test_reset_with_custom_balance(self):
        captured = {}

        def capture_save(state):
            captured.update(state)

        with patch.object(pe, "_save", side_effect=capture_save):
            pe.reset_portfolio(3000.0)

        assert captured["balance"] == 3000.0
        assert captured["initial_balance"] == 3000.0


# ─── edge cases ───────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_equity_history_capped_at_500(self):
        """_record_equity should trim history to last 500 entries."""
        s = fresh()
        s["equity_history"] = [{"time": "t", "equity": 1500.0}] * 500
        # Patch _load to return this state when BUY executes
        with patch.object(pe, "_load", return_value=s), \
             patch.object(pe, "_save") as mock_save:
            pe.execute_paper_trade("BUY", 70, PRICE)
            saved_state = mock_save.call_args[0][0]
        assert len(saved_state["equity_history"]) <= 500

    def test_exact_minimum_balance_is_allowed(self):
        """Balance exactly at MIN_TRADE_THB (1000) should be accepted."""
        s = fresh()
        s["balance"] = 1000.0
        with patch.object(pe, "_load", return_value=s), \
             patch.object(pe, "_save"):
            result = pe.execute_paper_trade("BUY", 70, PRICE)
        assert result["action"] == "OPENED"

    def test_one_below_minimum_balance_is_rejected(self):
        s = fresh()
        s["balance"] = 999.99
        with patch.object(pe, "_load", return_value=s), \
             patch.object(pe, "_save"):
            result = pe.execute_paper_trade("BUY", 70, PRICE)
        assert result["action"] == "SKIP"

    def test_sell_at_same_price_is_breakeven_win(self):
        """P&L can be slightly negative due to rounding; equal price → near-zero."""
        s = state_with_position(entry_price=PRICE)
        with patch.object(pe, "_load", return_value=s), \
             patch.object(pe, "_save"):
            result = pe.execute_paper_trade("SELL", 70, PRICE)
        assert result["action"] == "CLOSED"
        assert abs(result["pnl_thb"]) < 0.05   # practically zero P&L (rounding from 95% sizing)
