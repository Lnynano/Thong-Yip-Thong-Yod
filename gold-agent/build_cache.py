import os
import yfinance as yf
import pandas as pd
from datetime import datetime

# Define the data directory
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

def fetch_and_save(interval, period_or_start):
    print("=" * 60)
    print(f"  DOWNLOADING EXTENDED HISTORICAL DATA (INTERVAL: {interval})")
    print("=" * 60)
    
    tickers = ["GC=F", "USDTHB=X", "DX-Y.NYB", "^VIX"]
    
    print(f"  Fetching {interval} data for: {', '.join(tickers)}...")
    
    if interval == "1h":
        raw = yf.download(tickers, start=period_or_start, interval=interval, auto_adjust=True, progress=True)
    else:
        # 30m and 15m intervals have a strict 60-day limit in yfinance
        raw = yf.download(tickers, period=period_or_start, interval=interval, auto_adjust=True, progress=True)
        
    if raw.empty:
        print("  [Error] No data returned from yfinance.")
        return

    print("  Processing and merging data...")
    df_merged = pd.DataFrame(index=raw.index)
    
    df_merged["Open"] = raw[("Open", "GC=F")]
    df_merged["High"] = raw[("High", "GC=F")]
    df_merged["Low"] = raw[("Low", "GC=F")]
    df_merged["Close"] = raw[("Close", "GC=F")]
    df_merged["Volume"] = raw[("Volume", "GC=F")].fillna(0)
    
    df_merged["USDTHB"] = raw[("Close", "USDTHB=X")]
    df_merged["DXY"] = raw[("Close", "DX-Y.NYB")]
    df_merged["VIX"] = raw[("Close", "^VIX")]
    
    df_merged.dropna(subset=["Close"], inplace=True)
    
    df_merged["USDTHB"] = df_merged["USDTHB"].ffill().bfill()
    df_merged["DXY"] = df_merged["DXY"].ffill().bfill()
    df_merged["VIX"] = df_merged["VIX"].ffill().bfill()
    
    df_merged.index.name = "Date"
    
    output_path = os.path.join(DATA_DIR, f"historical_prices_{interval}_extended.csv")
    df_merged.to_csv(output_path)
    
    print(f"  Successfully saved extended data to: {output_path}")
    print(f"  Total records: {len(df_merged)}")
    print(f"  Date range: {df_merged.index.min()} to {df_merged.index.max()}")
    print("=" * 60)

def build_extended_cache():
    # 1h interval can go back 730 days
    fetch_and_save("1h", "2026-01-01")
    
    # 30m interval can only go back 60 days
    fetch_and_save("30m", "60d")

if __name__ == "__main__":
    build_extended_cache()
