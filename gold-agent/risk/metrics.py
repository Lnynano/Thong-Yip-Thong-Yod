"""
risk/metrics.py
Risk management metrics for gold trading analysis.

Implements formulas:
  - Sharpe Ratio          : E[Rp - rf] / sqrt(Var(Rp - rf))  × sqrt(252)
  - Sortino Ratio         : E[Rp - τ]  / sqrt(E[min(0, Rp - τ)^2])
  - Maximum Drawdown      : max over t of (max_τ Vτ - Vt) / max_τ Vτ
  - Kelly Criterion       : f* = W - (1-W)/R   where R = avg_win/avg_loss
  - Half-Kelly            : f*/2  (recommended for LLM agents — overconfidence)
  - Expected Value (EV)   : EV = (W × R_W) - (L × R_L)
"""

import numpy as np
import pandas as pd


# ─────────────────────────────────────────────────────────────
# Sharpe Ratio
# ─────────────────────────────────────────────────────────────
def calculate_sharpe(df: pd.DataFrame, risk_free_rate: float = 0.02) -> float:
    """
    Calculate the annualized Sharpe Ratio from a price DataFrame.

    Formula:
        S = E[Rp - rf] / sqrt(Var(Rp - rf))
    Annualized by multiplying by sqrt(252) trading days.

    Args:
        df (pd.DataFrame): DataFrame with a 'Close' column.
        risk_free_rate (float): Annual risk-free rate (default 2% = 0.02).

    Returns:
        float: Annualized Sharpe Ratio. Returns 0.0 on failure.
    """
    try:
        if df.empty or "Close" not in df.columns or len(df) < 2:
            return 0.0

        daily_returns = df["Close"].pct_change().dropna()
        if daily_returns.empty or daily_returns.std() == 0:
            return 0.0

        daily_rf = risk_free_rate / 252
        excess_returns = daily_returns - daily_rf
        sharpe = (excess_returns.mean() / excess_returns.std()) * np.sqrt(252)
        return round(float(sharpe), 4)

    except Exception as e:
        print(f"[metrics.py] Error calculating Sharpe Ratio: {e}")
        return 0.0


# ─────────────────────────────────────────────────────────────
# Sortino Ratio
# ─────────────────────────────────────────────────────────────
def calculate_sortino(df: pd.DataFrame, target_return: float = 0.0) -> float:
    """
    Calculate the annualized Sortino Ratio.

    Unlike Sharpe, Sortino penalizes ONLY downside volatility.

    Formula:
        Sortino = E[Rp - τ] / sqrt(E[min(0, Rp - τ)^2])
    Annualized by multiplying by sqrt(252).

    Args:
        df (pd.DataFrame): DataFrame with a 'Close' column.
        target_return (float): Minimum acceptable daily return (default 0.0).

    Returns:
        float: Annualized Sortino Ratio. Returns 0.0 on failure.
    """
    try:
        if df.empty or "Close" not in df.columns or len(df) < 2:
            return 0.0

        daily_returns = df["Close"].pct_change().dropna()
        if daily_returns.empty:
            return 0.0

        excess = daily_returns - target_return
        # Downside deviation: only negative deviations count
        downside = np.minimum(excess, 0.0)
        downside_std = np.sqrt(np.mean(downside ** 2))

        if downside_std == 0:
            return 0.0

        sortino = (excess.mean() / downside_std) * np.sqrt(252)
        return round(float(sortino), 4)

    except Exception as e:
        print(f"[metrics.py] Error calculating Sortino Ratio: {e}")
        return 0.0


# ─────────────────────────────────────────────────────────────
# Maximum Drawdown
# ─────────────────────────────────────────────────────────────
def calculate_max_drawdown(df: pd.DataFrame) -> float:
    """
    Calculate the Maximum Drawdown (MDD) from a price series.

    Formula:
        MDD = max over t of  (max_τ∈[0,t] Vτ  -  Vt)  /  max_τ∈[0,t] Vτ
    Expressed as a negative fraction (e.g., -0.15 means a 15% peak-to-trough drop).

    Args:
        df (pd.DataFrame): DataFrame with a 'Close' column.

    Returns:
        float: Maximum drawdown as a negative fraction. Returns 0.0 on failure.
    """
    try:
        if df.empty or "Close" not in df.columns or len(df) < 2:
            return 0.0

        close = df["Close"].copy()
        rolling_max = close.cummax()
        drawdown = (close - rolling_max) / rolling_max
        return round(float(drawdown.min()), 4)

    except Exception as e:
        print(f"[metrics.py] Error calculating Max Drawdown: {e}")
        return 0.0


# ─────────────────────────────────────────────────────────────
# Kelly Criterion + Half-Kelly
# ─────────────────────────────────────────────────────────────
def calculate_kelly(df: pd.DataFrame, win_loss_ratio: float = None) -> float:
    """
    Calculate the Full Kelly Criterion for optimal position sizing.

    Formula:
        f* = W  -  (1 - W) / R
    where:
        W = win rate (probability of a profitable day)
        R = win/loss payout ratio (avg_win / avg_loss)

    Note: "Because LLMs can be overconfident and market
    distributions are non-stationary, quantitative systems typically use
    Half-Kelly (f*/2) to reduce volatility and drawdown."

    Use calculate_half_kelly() for the recommended position size.
    Kelly fraction is capped at 25% (0.25) as a safety measure.

    Args:
        df (pd.DataFrame): DataFrame with a 'Close' column.
        win_loss_ratio (float, optional): Override the calculated win/loss ratio.

    Returns:
        float: Full Kelly fraction as a decimal (0.0 – 0.25).
    """
    try:
        if df.empty or "Close" not in df.columns or len(df) < 2:
            return 0.0

        daily_returns = df["Close"].pct_change().dropna()
        if daily_returns.empty:
            return 0.0

        wins = daily_returns[daily_returns > 0]
        losses = daily_returns[daily_returns < 0]

        if len(wins) == 0 or len(losses) == 0:
            return 0.0

        win_rate = len(wins) / len(daily_returns)

        if win_loss_ratio is None:
            avg_win = wins.mean()
            avg_loss = abs(losses.mean())
            if avg_loss == 0:
                return 0.0
            b = avg_win / avg_loss
        else:
            b = win_loss_ratio

        if b <= 0:
            return 0.0

        # Kelly formula: f* = W - (1 - W) / R
        kelly = win_rate - (1 - win_rate) / b

        # Cap at 25% for conservative risk management
        kelly = max(0.0, min(kelly, 0.25))
        return round(float(kelly), 4)

    except Exception as e:
        print(f"[metrics.py] Error calculating Kelly Criterion: {e}")
        return 0.0


def calculate_half_kelly(df: pd.DataFrame) -> float:
    """
    Calculate Half-Kelly position size — the recommended size for LLM agents.

    "Quantitative systems typically use Half-Kelly (f*/2) to
    reduce volatility and drawdown while maintaining strong growth."

    This is the safer, production-recommended position size, because:
    1. LLMs can be overconfident in their signal quality estimates.
    2. Gold market distributions are non-stationary (macro events shift regimes).

    Args:
        df (pd.DataFrame): DataFrame with a 'Close' column.

    Returns:
        float: Half-Kelly position size as a decimal (0.0 – 0.125).
    """
    full_kelly = calculate_kelly(df)
    return round(full_kelly / 2, 4)


# ─────────────────────────────────────────────────────────────
# Expected Value (EV) Analysis
# ─────────────────────────────────────────────────────────────
def calculate_expected_value(df: pd.DataFrame) -> dict:
    """
    Calculate the Expected Value (EV) of the trading strategy.

    Formula:
        EV = (W × R_W)  -  (L × R_L)
    where:
        W   = win rate (probability of profitable trade)
        R_W = average profit per winning trade
        L   = loss rate (1 - W)
        R_L = average loss per losing trade

    A positive EV means the strategy is mathematically profitable over time.
    "A well-designed system prompt can enforce a strict
    risk-reward ratio (e.g., R_W = 3 × R_L), allowing the strategy to
    remain profitable even with a win rate below 50%."

    Args:
        df (pd.DataFrame): DataFrame with a 'Close' column.

    Returns:
        dict: {
            'ev'          : float,  # Expected value per trade (fraction)
            'win_rate'    : float,  # Win probability (0–1)
            'loss_rate'   : float,  # Loss probability (0–1)
            'avg_win'     : float,  # Average win magnitude
            'avg_loss'    : float,  # Average loss magnitude
            'reward_ratio': float,  # R_W / R_L  (risk-reward ratio)
            'ev_pct'      : str,    # EV formatted as percentage string
            'is_positive' : bool,   # True if EV > 0 (profitable strategy)
        }
    """
    default = {
        "ev": 0.0, "win_rate": 0.0, "loss_rate": 0.0,
        "avg_win": 0.0, "avg_loss": 0.0, "reward_ratio": 0.0,
        "ev_pct": "0.00%", "is_positive": False,
    }

    try:
        if df.empty or "Close" not in df.columns or len(df) < 2:
            return default

        daily_returns = df["Close"].pct_change().dropna()
        if daily_returns.empty:
            return default

        wins = daily_returns[daily_returns > 0]
        losses = daily_returns[daily_returns < 0]

        if len(wins) == 0 or len(losses) == 0:
            return default

        win_rate = len(wins) / len(daily_returns)
        loss_rate = 1 - win_rate
        avg_win = float(wins.mean())
        avg_loss = float(abs(losses.mean()))
        reward_ratio = round(avg_win / avg_loss, 4) if avg_loss > 0 else 0.0

        # EV formula
        ev = (win_rate * avg_win) - (loss_rate * avg_loss)

        return {
            "ev": round(ev, 6),
            "win_rate": round(win_rate, 4),
            "loss_rate": round(loss_rate, 4),
            "avg_win": round(avg_win, 6),
            "avg_loss": round(avg_loss, 6),
            "reward_ratio": reward_ratio,
            "ev_pct": f"{ev * 100:.4f}%",
            "is_positive": ev > 0,
        }

    except Exception as e:
        print(f"[metrics.py] Error calculating Expected Value: {e}")
        return default


# ─────────────────────────────────────────────────────────────
# Master risk function (returns all metrics)
# ─────────────────────────────────────────────────────────────
def calculate_risk(df: pd.DataFrame) -> dict:
    """
    Calculate ALL risk metrics from the gold price DataFrame.

    Aggregates: Sharpe, Sortino, Max Drawdown, Full Kelly,
                Half-Kelly (recommended), and Expected Value.

    Half-Kelly is the recommended position size.

    Args:
        df (pd.DataFrame): DataFrame with a 'Close' column.

    Returns:
        dict: {
            'sharpe'          : float,  # Annualized Sharpe Ratio
            'sortino'         : float,  # Annualized Sortino Ratio (downside only)
            'max_drawdown'    : float,  # Max Drawdown (negative fraction)
            'kelly'           : float,  # Full Kelly fraction
            'half_kelly'      : float,  # Half-Kelly (RECOMMENDED for LLM agents)
            'ev'              : dict,   # Full Expected Value breakdown
            'sharpe_label'    : str,    # Human-readable Sharpe interpretation
            'sortino_label'   : str,    # Human-readable Sortino interpretation
            'drawdown_pct'    : str,    # Max drawdown as percentage string
            'kelly_pct'       : str,    # Full Kelly as percentage string
            'half_kelly_pct'  : str,    # Half-Kelly as percentage string (recommended)
        }
    """
    sharpe = calculate_sharpe(df)
    sortino = calculate_sortino(df)
    max_dd = calculate_max_drawdown(df)
    kelly = calculate_kelly(df)
    half_kelly = calculate_half_kelly(df)
    ev = calculate_expected_value(df)

    # Sharpe label interpretation
    if sharpe >= 2.0:
        sharpe_label = "Excellent"
    elif sharpe >= 1.0:
        sharpe_label = "Good"
    elif sharpe >= 0.5:
        sharpe_label = "Acceptable"
    elif sharpe >= 0.0:
        sharpe_label = "Poor"
    else:
        sharpe_label = "Negative"

    # Sortino label interpretation (same scale as Sharpe)
    if sortino >= 2.0:
        sortino_label = "Excellent"
    elif sortino >= 1.0:
        sortino_label = "Good"
    elif sortino >= 0.5:
        sortino_label = "Acceptable"
    elif sortino >= 0.0:
        sortino_label = "Poor"
    else:
        sortino_label = "Negative"

    result = {
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": max_dd,
        "kelly": kelly,
        "half_kelly": half_kelly,
        "ev": ev,
        "sharpe_label": sharpe_label,
        "sortino_label": sortino_label,
        "drawdown_pct": f"{max_dd * 100:.2f}%",
        "kelly_pct": f"{kelly * 100:.2f}%",
        "half_kelly_pct": f"{half_kelly * 100:.2f}%",
    }

    print(
        f"[metrics.py] Sharpe={sharpe:.4f} ({sharpe_label}) | "
        f"Sortino={sortino:.4f} ({sortino_label}) | "
        f"MaxDD={result['drawdown_pct']} | "
        f"Full Kelly={result['kelly_pct']} | "
        f"Half-Kelly={result['half_kelly_pct']} (recommended) | "
        f"EV={ev['ev_pct']} ({'Positive' if ev['is_positive'] else 'Negative'})"
    )
    return result


# ─────────────────────────────────────────────────────────────
# Standalone testing
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from data.fetch import get_gold_price

    df = get_gold_price()
    if not df.empty:
        metrics = calculate_risk(df)
        ev = metrics["ev"]
        print("\n--- Risk Metrics ---")
        print(f"Sharpe Ratio  : {metrics['sharpe']}  ({metrics['sharpe_label']})")
        print(f"Sortino Ratio : {metrics['sortino']}  ({metrics['sortino_label']})")
        print(f"Max Drawdown  : {metrics['drawdown_pct']}")
        print(f"Full Kelly    : {metrics['kelly_pct']} of portfolio")
        print(f"Half-Kelly RECOMMENDED  : {metrics['half_kelly_pct']} of portfolio")
        print(f"\n--- Expected Value ---")
        print(f"Win Rate               : {ev['win_rate']*100:.1f}%")
        print(f"Loss Rate              : {ev['loss_rate']*100:.1f}%")
        print(f"Avg Win                : {ev['avg_win']*100:.4f}%")
        print(f"Avg Loss               : {ev['avg_loss']*100:.4f}%")
        print(f"Reward Ratio (RW/RL)   : {ev['reward_ratio']:.2f}x")
        print(f"Expected Value (EV)    : {ev['ev_pct']}  ({'[OK] Positive' if ev['is_positive'] else '[X] Negative'})")
