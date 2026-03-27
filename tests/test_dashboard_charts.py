# tests/test_dashboard_charts.py
import sys, os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "gold-agent")))

import matplotlib.pyplot as plt


def _dummy_df() -> pd.DataFrame:
    """90 rows of synthetic OHLCV data — enough for RSI/SMA calculations."""
    rng = np.random.default_rng(42)
    n = 90
    close = 2000.0 + np.cumsum(rng.normal(0, 5, n))
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    return pd.DataFrame({
        "Open":   close - rng.uniform(0, 3, n),
        "High":   close + rng.uniform(0, 5, n),
        "Low":    close - rng.uniform(0, 5, n),
        "Close":  close,
        "Volume": rng.integers(1000, 5000, n).astype(float),
    }, index=idx)


# ── CSS constants ─────────────────────────────────────
def test_pns_css_font_sizes():
    from ui.dashboard import PNS_CSS
    assert "font-size: 1.0em" in PNS_CSS, "Base font should be 1.0em"
    assert "font-size: 0.78em" in PNS_CSS, "Label font should be 0.78em"
    assert "font-size: 0.88em" in PNS_CSS, "Table cell font should be 0.88em"


def test_pns_css_responsive_breakpoint():
    from ui.dashboard import PNS_CSS
    assert "@media (max-width: 768px)" in PNS_CSS, "Mobile breakpoint missing"
    assert "flex-direction: column" in PNS_CSS, "Mobile column stacking missing"


def test_pns_css_readability():
    from ui.dashboard import PNS_CSS
    assert "line-height: 1.5" in PNS_CSS, "line-height fix missing"
    assert "word-break: break-word" in PNS_CSS, "word-break fix missing"


# ── Split chart functions ─────────────────────────────
def test_build_price_chart_returns_figure():
    from ui.dashboard import _build_price_chart
    df = _dummy_df()
    fig = _build_price_chart(df)
    assert isinstance(fig, plt.Figure)
    plt.close(fig)


def test_build_price_chart_figsize():
    from ui.dashboard import _build_price_chart
    df = _dummy_df()
    fig = _build_price_chart(df)
    w, h = fig.get_size_inches()
    assert w >= 10, f"Price chart width {w} too narrow for mobile"
    assert h >= 2.5, f"Price chart height {h} too short"
    plt.close(fig)


def test_build_rsi_chart_returns_figure():
    from ui.dashboard import _build_rsi_chart
    df = _dummy_df()
    fig = _build_rsi_chart(df)
    assert isinstance(fig, plt.Figure)
    plt.close(fig)


def test_build_rsi_chart_figsize():
    from ui.dashboard import _build_rsi_chart
    df = _dummy_df()
    fig = _build_rsi_chart(df)
    w, h = fig.get_size_inches()
    assert w >= 10, f"RSI chart width {w} too narrow for mobile"
    plt.close(fig)


# ── Old _build_chart should NOT exist (it's been split) ──
def test_build_chart_removed():
    import ui.dashboard as dash
    assert not hasattr(dash, "_build_chart"), \
        "_build_chart should be replaced by _build_price_chart and _build_rsi_chart"
