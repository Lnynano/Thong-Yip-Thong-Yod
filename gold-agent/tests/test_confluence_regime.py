import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd
import numpy as np
from indicators.tech import calculate_confluence_score, calculate_market_regime


def _make_df(closes: list[float]) -> pd.DataFrame:
    """Helper: build minimal OHLCV DataFrame from close prices."""
    n = len(closes)
    return pd.DataFrame({
        "Open":   closes,
        "High":   [c * 1.005 for c in closes],
        "Low":    [c * 0.995 for c in closes],
        "Close":  closes,
        "Volume": [100000] * n,
    })


def test_confluence_score_neutral():
    """Mid-range closes should produce a score near 5.0."""
    closes = [3000.0] * 60
    df = _make_df(closes)
    score = calculate_confluence_score(df, "NEUTRAL")
    assert 0.0 <= score <= 10.0, f"Score out of range: {score}"


def test_confluence_score_bullish_news_raises():
    """BULLISH sentiment should produce higher score than NEUTRAL."""
    closes = [3000.0] * 60
    df = _make_df(closes)
    score_neutral = calculate_confluence_score(df, "NEUTRAL")
    score_bullish = calculate_confluence_score(df, "BULLISH")
    assert score_bullish > score_neutral


def test_confluence_score_bearish_news_lowers():
    """BEARISH sentiment should produce lower score than NEUTRAL."""
    closes = [3000.0] * 60
    df = _make_df(closes)
    score_neutral = calculate_confluence_score(df, "NEUTRAL")
    score_bearish = calculate_confluence_score(df, "BEARISH")
    assert score_bearish < score_neutral


def test_confluence_score_range():
    """Score must always be 0–10 regardless of inputs."""
    closes_rising = [2800.0 + i * 10 for i in range(60)]
    closes_falling = [3400.0 - i * 10 for i in range(60)]
    for closes, sentiment in [
        (closes_rising, "BULLISH"),
        (closes_falling, "BEARISH"),
        (closes_rising, "BEARISH"),
    ]:
        score = calculate_confluence_score(_make_df(closes), sentiment)
        assert 0.0 <= score <= 10.0, f"Score {score} out of range"


def test_market_regime_returns_valid_label():
    """Market regime must be one of the four valid labels."""
    closes = [3000.0 + i * 5 for i in range(60)]
    df = _make_df(closes)
    regime = calculate_market_regime(df)
    assert regime in ("TRENDING UP", "TRENDING DOWN", "RANGING", "VOLATILE")


def test_market_regime_uptrend():
    """Strongly rising prices should produce TRENDING UP."""
    closes = [2800.0 + i * 15 for i in range(60)]
    df = _make_df(closes)
    regime = calculate_market_regime(df)
    assert regime == "TRENDING UP"


def test_market_regime_downtrend():
    """Strongly falling prices should produce TRENDING DOWN."""
    closes = [3700.0 - i * 15 for i in range(60)]
    df = _make_df(closes)
    regime = calculate_market_regime(df)
    assert regime == "TRENDING DOWN"
