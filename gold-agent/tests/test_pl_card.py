import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from ui.dashboard import _build_pl_card


def test_pl_card_returns_png_path():
    portfolio = {
        "total_equity": 1650.0, "initial_balance": 1500.0,
        "total_pnl": 150.0, "total_pnl_pct": 10.0,
        "win_rate": 66.7, "wins": 2, "losses": 1,
        "total_trades": 3, "rr_ratio": 1.8, "realized_pnl": 150.0,
    }
    path = _build_pl_card(portfolio)
    assert path is not None
    assert os.path.exists(path)
    assert path.endswith(".png")
    assert os.path.getsize(path) > 1000


def test_pl_card_negative_pnl():
    portfolio = {
        "total_equity": 1400.0, "initial_balance": 1500.0,
        "total_pnl": -100.0, "total_pnl_pct": -6.67,
        "win_rate": 33.3, "wins": 1, "losses": 2,
        "total_trades": 3, "rr_ratio": 0.8, "realized_pnl": -100.0,
    }
    path = _build_pl_card(portfolio)
    assert path is not None
    assert os.path.exists(path)
