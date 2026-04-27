import pandas as pd
import matplotlib.pyplot as plt
import os

def plot_gold_price_from_bl9():
    file_path = "data/bl9.csv"
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found.")
        return

    # Load candle data
    df = pd.read_csv(file_path)
    df['date'] = pd.to_datetime(df['date'])
    
    # Create the plot
    plt.figure(figsize=(15, 7))
    
    # Plot Gold Price (THB)
    plt.plot(df['date'], df['price_thb'], color='#d4af37', linewidth=1.5, label='Gold Price (THB / Baht Gold)')
    
    # Optional: Mark BUY/SELL actions on the price chart
    buys = df[df['action'] == 'OPENED']
    sells = df[df['action'] == 'CLOSED [BASKET]']
    
    plt.scatter(buys['date'], buys['price_thb'], color='green', marker='^', s=60, label='BUY Execution', zorder=5)
    plt.scatter(sells['date'], sells['price_thb'], color='red', marker='v', s=60, label='SELL Execution', zorder=5)
    
    # Formatting
    plt.title('Thai Gold Price (96.5%) - March 2026 (Backtest Data)', fontsize=16, fontweight='bold')
    plt.xlabel('Date', fontsize=12)
    plt.ylabel('Price (Baht Gold)', fontsize=12)
    plt.grid(True, alpha=0.3, linestyle='--')
    plt.legend()
    
    # Set x-axis date formatting
    plt.xticks(rotation=45)
    
    # Save the plot
    output_file = "data/gold_price_30d.png"
    plt.tight_layout()
    plt.savefig(output_file)
    print(f"Success! Gold price plot saved as {output_file}")

if __name__ == "__main__":
    plot_gold_price_from_bl9()
