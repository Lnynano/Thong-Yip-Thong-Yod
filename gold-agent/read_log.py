"""
read_logs.py
Script to fetch and display trade logs from the competition server.
"""

import os
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

def fetch_and_print_trade_logs():
    # Load environment variables from .env file
    load_dotenv()

    # Get the API key for the GoldTrade Logs API
    key = os.getenv('TRADE_LOG_API_KEY', '').strip()

    url = 'https://goldtrade-logs-api.poonnatuch.workers.dev/logs'
    headers = {'Authorization': f'Bearer {key}'}

    try:
        # Fetch data from the API with a 5-second timeout
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()  # Check for HTTP errors
        
        data = response.json().get('data', [])
        
        # Set timezone to Thai Time (UTC+7)
        THAI = timezone(timedelta(hours=7))
        
        # Iterate through the logs and format the output
        for r in data:
            dt = datetime.fromtimestamp(r['created_at'], tz=THAI).strftime('%Y-%m-%d %H:%M')
            action = r.get('action', '')
            
            # Safe default fallback for missing prices to prevent NoneType formatting errors
            price = r.get('price') or 0
            
            reason = r.get('reason', '')[:500]
            
            print(f"{dt}  {action:4}  {price:,.0f} THB  {reason}")
            
        print(f"--- Total: {len(data)} records ---")

    except Exception as e:
        # Fails silently with a print log
        print(f"[read_logs.py] Error fetching trade logs: {e}")

if __name__ == "__main__":
    fetch_and_print_trade_logs()