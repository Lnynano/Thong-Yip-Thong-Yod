"""
risk/metrics.py
Risk management metrics for gold trading analysis.

Calculates:
  - Sharpe Ratio (annualized, 2% risk-free rate)
  - Maximum Drawdown
  - Kelly Criterion for position sizing
"""

import numpy as np
import pandas as pd


def calculate_sharpe(df: pd.DataFrame, risk_free_rate: float = 0.02) -> float:
    """
    Calculate the annualized Sharpe Ratio from a price DataFrame.

    Sharpe Ratio = (Mean Daily Return - Daily Risk-Free Rate) / Std of Daily Returns
    Annualized by multiplying by sqrt(252) (trading days per year).

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

        # Convert annual rate to daily
        daily_rf = risk_free_rate / 252

        excess_returns = daily_returns - daily_rf
        sharpe = (excess_returns.mean() / excess_returns.std()) * np.sqrt(252)

        return round(float(sharpe), 4)

    except Exception as e:
        print(f"[metrics.py] Error calculating Sharpe Ratio: {e}")
        return 0.0


def calculate_max_drawdown(df: pd.DataFrame) -> float:
    """
    Calculate the Maximum Drawdown from a price series.

    Max Drawdown = Maximum peak-to-trough decline over the period.
    Expressed as a negative percentage (e.g., -0.15 = -15%).

    Args:
        df (pd.DataFrame): DataFrame with a 'Close' column.

    Returns:
        float: Maximum drawdown as a fraction (e.g., -0.15 for -15%).
               Returns 0.0 on failure.
    """
    try:
        if df.empty or "Close" not in df.columns or len(df) < 2:
            return 0.0

        close = df["Close"].copy()

        # Rolling maximum (peak)
        rolling_max = close.cummax()

        # Drawdown at each point = (price - peak) / peak
        drawdown = (close - rolling_max) / rolling_max

        max_dd = float(drawdown.min())
        return round(max_dd, 4)

    except Exception as e:
        print(f"[metrics.py] Error calculating Max Drawdown: {e}")
        return 0.0


def calculate_kelly(df: pd.DataFrame, win_loss_ratio: float = None) -> float:
    """
    Calculate the Kelly Criterion for optimal position sizing.

    Kelly % = (Win Rate * (Win/Loss Ratio + 1) - 1) / (Win/Loss Ratio)
    Simplified: Kelly % = (bp - q) / b
      where b = win/loss ratio, p = win probability, q = 1 - p

    Uses daily returns to estimate win rate and average win/loss.
    Kelly fraction is capped at 25% (0.25) as a safety measure.

    Args:
        df (pd.DataFrame): DataFrame with a 'Close' column.
        win_loss_ratio (float, optional): Override the calculated win/loss ratio.

    Returns:
        float: Recommended position size as a fraction of portfolio (0–0.25).
               Returns 0.0 on failure.
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
        loss_rate = 1 - win_rate

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

        kelly = (win_rate * (b + 1) - 1) / b

        # Cap at 25% for conservative risk management
        kelly = max(0.0, min(kelly, 0.25))
        return round(float(kelly), 4)

    except Exception as e:
        print(f"[metrics.py] Error calculating Kelly Criterion: {e}")
        return 0.0


def calculate_risk(df: pd.DataFrame) -> dict:
    """
    Calculate all risk metrics from the gold price DataFrame.

    Args:
        df (pd.DataFrame): DataFrame with a 'Close' column.

    Returns:
        dict: {
            'sharpe'       : float,  # Annualized Sharpe Ratio
            'max_drawdown' : float,  # Maximum Drawdown (negative fraction)
            'kelly'        : float,  # Kelly Criterion position size (0–0.25)
            'sharpe_label' : str,    # Human-readable Sharpe interpretation
            'drawdown_pct' : str,    # Max drawdown as percentage string
            'kelly_pct'    : str,    # Kelly as percentage string
        }
    """
    sharpe = calculate_sharpe(df)
    max_dd = calculate_max_drawdown(df)
    kelly = calculate_kelly(df)

    # Interpret Sharpe
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

    result = {
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "kelly": kelly,
        "sharpe_label": sharpe_label,
        "drawdown_pct": f"{max_dd * 100:.2f}%",
        "kelly_pct": f"{kelly * 100:.2f}%",
    }

    print(f"[metrics.py] Sharpe={sharpe:.4f} ({sharpe_label}), "
          f"MaxDD={result['drawdown_pct']}, Kelly={result['kelly_pct']}")
    return result


# Allow standalone testing
if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from data.fetch import get_gold_price

    df = get_gold_price()
    if not df.empty:
        metrics = calculate_risk(df)
        print("\n--- Risk Metrics ---")
        print(f"Sharpe Ratio  : {metrics['sharpe']} ({metrics['sharpe_label']})")
        print(f"Max Drawdown  : {metrics['drawdown_pct']}")
        print(f"Kelly Criterion: {metrics['kelly_pct']} of portfolio")
