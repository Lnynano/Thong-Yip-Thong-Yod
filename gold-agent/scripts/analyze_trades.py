import pandas as pd

df = pd.read_csv('data/backtest_trades.csv')
print('=== Trade Analysis ===')
print(f'Total trades: {len(df)}')
wins = df[df['Profit'] > 0]
losses = df[df['Profit'] < 0]
breakeven = df[df['Profit'] == 0]
print(f'Wins: {len(wins)}')
print(f'Losses: {len(losses)}')
print(f'Break-even (0): {len(breakeven)}')

print()
print('=== Profit Distribution ===')
print(df['Profit'].describe())

print()
print('=== Days Held Distribution ===')
print(df['Days Held'].describe())

print()
print('=== Avg days held for wins vs losses ===')
print(f'Avg days held (wins): {wins["Days Held"].mean():.4f} = {wins["Days Held"].mean()*24:.1f}h')
print(f'Avg days held (losses): {losses["Days Held"].mean():.4f} = {losses["Days Held"].mean()*24:.1f}h')

print()
print('=== Short trades under 2 hours ===')
short = df[df['Days Held'] < 2/24]
print(f'Count: {len(short)} ({len(short)/len(df)*100:.1f}%)')
print(f'Profit sum: {short["Profit"].sum():.2f} THB')

print()
print('=== Worst 5 trades ===')
print(df.nsmallest(5, 'Profit')[['Buy Date','Sell Date','Days Held','Profit']].to_string())

print()
print('=== Best 5 trades ===')
print(df.nlargest(5, 'Profit')[['Buy Date','Sell Date','Days Held','Profit']].to_string())
