@echo off
echo ========================================================
echo   Starting Full Month Backtest (March 2026)
echo   Interval: 30m
echo   This may take 40-60 minutes to complete.
echo ========================================================
python backtest.py --start 2026-03-01 --end 2026-03-31 --interval 30m
echo.
echo ========================================================
echo   Backtest Complete! 
echo   Check data/backtest_log.csv and data/backtest_trades.csv
echo ========================================================
pause
