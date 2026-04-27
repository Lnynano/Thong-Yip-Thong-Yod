import pandas as pd
import matplotlib.pyplot as plt
import os

def plot_bt9_results():
    file_path = "data/bt9.csv"
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found.")
        return

    # Load trade data
    df = pd.read_csv(file_path)
    
    # Calculate Cumulative Profit starting from 1,500 THB
    initial_balance = 1500
    df['Cumulative_Profit'] = df['Profit'].cumsum()
    df['Equity'] = initial_balance + df['Cumulative_Profit']
    
    # Convert 'Sell Date' to datetime for better plotting
    df['Sell Date'] = pd.to_datetime(df['Sell Date'])
    
    # Create the plot with two subplots: Price/Trades and Equity Curve
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)
    
    # --- Subplot 1: Price and Buy/Sell Markers ---
    # Plot Buy points
    ax1.scatter(pd.to_datetime(df['Buy Date']), df['Buy_Price/Gold_Baht'], 
                color='green', marker='^', s=100, label='BUY Signal', zorder=5)
    # Plot Sell points
    ax1.scatter(pd.to_datetime(df['Sell Date']), df['Sell_Price/Gold_Baht'], 
                color='red', marker='v', s=100, label='SELL Signal', zorder=5)
    
    # Connect Buy/Sell pairs with a line to show the trade duration
    for i in range(len(df)):
        ax1.plot([pd.to_datetime(df['Buy Date'].iloc[i]), pd.to_datetime(df['Sell Date'].iloc[i])],
                 [df['Buy_Price/Gold_Baht'].iloc[i], df['Sell_Price/Gold_Baht'].iloc[i]],
                 color='gray', linestyle='--', alpha=0.3)

    ax1.set_title('Gold Trading: BUY and SELL Execution Points', fontsize=14, fontweight='bold')
    ax1.set_ylabel('Price (THB / Gold Baht)', fontsize=12)
    ax1.grid(True, alpha=0.3)
    ax1.legend()

    # --- Subplot 2: Equity Curve ---
    ax2.plot(df['Sell Date'], df['Equity'], color='#d4af37', linewidth=2, label='Equity (THB)')
    ax2.axhline(y=initial_balance, color='black', linestyle='--', alpha=0.5, label='Initial Balance')
    ax2.fill_between(df['Sell Date'], initial_balance, df['Equity'], 
                     where=(df['Equity'] >= initial_balance), color='green', alpha=0.1)
    ax2.fill_between(df['Sell Date'], initial_balance, df['Equity'], 
                     where=(df['Equity'] < initial_balance), color='red', alpha=0.1)
    
    ax2.set_title('Cumulative Equity Curve', fontsize=14, fontweight='bold')
    ax2.set_xlabel('Date', fontsize=12)
    ax2.set_ylabel('Balance (THB)', fontsize=12)
    ax2.grid(True, alpha=0.3)
    ax2.legend()

    # Save the plot
    output_file = "data/bt9_trade_plot.png"
    plt.tight_layout()
    plt.savefig(output_file)

    print(f"Success! Plot saved as {output_file}")

if __name__ == "__main__":
    plot_bt9_results()
