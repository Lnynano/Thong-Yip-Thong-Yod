import pandas as pd
import matplotlib.pyplot as plt
import os

def plot_backtest_results():
    print("Analyzing trade data and generating chart...")
    
    # 1. Load Price Data
    price_file = "data/historical_prices_1h_extended.csv"
    if not os.path.exists(price_file):
        print(f"Error: {price_file} not found.")
        return
    
    df_price = pd.read_csv(price_file)
    # Normalize price columns
    df_price.columns = [c.strip() for c in df_price.columns]
    if 'Datetime' not in df_price.columns and 'Date' in df_price.columns:
        df_price = df_price.rename(columns={'Date': 'Datetime'})
    # ✅ Make timezone-naive to prevent comparison errors
    df_price['Datetime'] = pd.to_datetime(df_price['Datetime']).dt.tz_localize(None)
    
    # 2. Search for the correct trade log file
    possible_files = ["data/backtest_trades.csv", "data/backtest_log.csv", "data/bt9.csv", "data/backtest_log_1h.csv"]
    log_file = None
    for f in possible_files:
        if os.path.exists(f):
            log_file = f
            print(f"Found trade log: {f}")
            break
            
    if not log_file:
        print(f"Error: Could not find any of these files: {possible_files}")
        return

    # 3. Load and Normalize Trade Data
    df_trades = pd.read_csv(log_file)
    # Clean up column names (strip whitespace)
    df_trades.columns = [c.strip() for c in df_trades.columns]
    
    # Map common column names
    col_map = {
        'Buy Date': 'buy_dt', 'buy date': 'buy_dt', 'BuyDate': 'buy_dt',
        'Sell Date': 'sell_dt', 'sell date': 'sell_dt', 'SellDate': 'sell_dt'
    }
    for old_col, new_col in col_map.items():
        if old_col in df_trades.columns:
            df_trades = df_trades.rename(columns={old_col: new_col})
            
    if 'buy_dt' not in df_trades.columns:
        print(f"Error: Could not find 'Buy Date' column. Available columns: {list(df_trades.columns)}")
        return

    df_trades['buy_dt'] = pd.to_datetime(df_trades['buy_dt']).dt.tz_localize(None)
    if 'sell_dt' in df_trades.columns:
        df_trades['sell_dt'] = pd.to_datetime(df_trades['sell_dt']).dt.tz_localize(None)
    
    # Filter price data range
    start_date = df_trades['buy_dt'].min() - pd.Timedelta(days=1)
    end_date = (df_trades['sell_dt'].max() if 'sell_dt' in df_trades.columns else df_trades['buy_dt'].max()) + pd.Timedelta(days=1)
    df_price_filtered = df_price[(df_price['Datetime'] >= start_date) & (df_price['Datetime'] <= end_date)].copy()
    
    # 4. Plotting
    plt.figure(figsize=(16, 9))
    plt.plot(df_price_filtered['Datetime'], df_price_filtered['Close'], label='Gold Price (USD)', color='#333333', alpha=0.4, linewidth=1.5)
    
    # Helper to find closest price in USD for plotting markers
    def get_price_at(dt):
        idx = (df_price['Datetime'] - dt).abs().idxmin()
        return df_price.loc[idx, 'Close']

    # Plot BUY markers
    buy_y = [get_price_at(d) for d in df_trades['buy_dt']]
    plt.scatter(df_trades['buy_dt'], buy_y, marker='^', color='#2ecc71', label='BUY', s=120, edgecolors='white', linewidth=1, zorder=5)
    
    # Plot SELL markers
    if 'sell_dt' in df_trades.columns:
        sell_y = [get_price_at(d) for d in df_trades['sell_dt']]
        plt.scatter(df_trades['sell_dt'], sell_y, marker='v', color='#e74c3c', label='SELL', s=120, edgecolors='white', linewidth=1, zorder=5)
    
    plt.title(f'Backtest Trade Visualization ({os.path.basename(log_file)})', fontsize=16, fontweight='bold', pad=20)
    plt.xlabel('Date Time', fontsize=12)
    plt.ylabel('Price (USD/oz)', fontsize=12)
    plt.legend(frameon=True, facecolor='white', framealpha=0.9)
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.xticks(rotation=45)
    
    # Highlight the profit regions if possible
    plt.tight_layout()
    output_file = "backtest_chart_v2.png"
    plt.savefig(output_file, dpi=150)
    print(f"Success! Chart saved as {output_file}")
    plt.show()

if __name__ == "__main__":
    plot_backtest_results()
