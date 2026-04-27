import pandas as pd
from datetime import timedelta

df = pd.read_csv('data/bt10Improve.csv')
df['Buy Date'] = pd.to_datetime(df['Buy Date'])
df['Sell Date'] = pd.to_datetime(df['Sell Date'])

def get_window(dt):
    weekday = dt.weekday()
    h = dt.hour
    m = dt.minute
    if weekday >= 5:
        if (h > 9 or (h == 9 and m >= 30)) and h < 17:
            return 'daytime'
        elif h == 17 and m <= 30:
            return 'daytime'
        return None
    else:
        if 6 <= h < 12: return 'morning'
        if 12 <= h < 18: return 'afternoon'
        if 18 <= h or h < 3: return 'evening'
    return None

def get_date_key(dt):
    if dt.hour < 3:
        return (dt - timedelta(days=1)).strftime('%Y-%m-%d')
    return dt.strftime('%Y-%m-%d')

print("=== บรรทัดที่ถือข้าม Window (ผิดโควต้า) ===")
print(f"{'Line':>4}  {'Buy':>14}  {'BuyWin':>20}  {'Sell':>14}  {'SellWin':>20}  {'Held':>5}  {'Profit':>7}")
print("-" * 90)

for idx, row in df.iterrows():
    line_no = idx + 2  # +2 because header is line 1, and idx is 0-based
    buy_dt = row['Buy Date']
    sell_dt = row['Sell Date']
    buy_window = get_window(buy_dt)
    sell_window = get_window(sell_dt)
    buy_date = get_date_key(buy_dt)
    sell_date = get_date_key(sell_dt)

    if buy_window != sell_window or buy_date != sell_date:
        print(f"  L{line_no:>2}  {buy_dt.strftime('%m-%d %H:%M'):>14}  {buy_date+' '+str(buy_window):>20}  "
              f"{sell_dt.strftime('%m-%d %H:%M'):>14}  {sell_date+' '+str(sell_window):>20}  "
              f"{row['Days Held']*24:>4.1f}h  {row['Profit']:>+7.2f}")

print()
print("หมายเหตุ: L = บรรทัดใน bt10Improve.csv (รวม header)")
