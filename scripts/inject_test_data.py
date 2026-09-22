import sqlite3
import json
import os
from datetime import datetime

# Path to the database
DB_PATH = 'database/astral.db'

def inject_test_data():
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    curr = conn.cursor()

    # 1. Ensure mock-key is set in settings
    curr.execute('SELECT api_keys FROM settings WHERE id=1')
    row = curr.fetchone()
    keys = json.loads(row[0]) if row else {}
    keys['openai'] = 'mock-key'
    curr.execute('UPDATE settings SET api_keys=? WHERE id=1', (json.dumps(keys),))
    print("Updated OpenAI key to 'mock-key'")

    # 2. Insert a "System Test" RSI strategy
    # This is a basic RSI Strategy in Python that the backtester expects
    test_code = """import pandas as pd
import numpy as np

def strategy(data):
    \"\"\"
    Simple RSI Strategy for Testing.
    Returns: 1 for Buy, -1 for Sell, 0 for Hold
    \"\"\"
    close = data['close']
    
    # Calculate RSI
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    # Signals
    signals = pd.Series(0, index=data.index)
    signals[rsi < 30] = 1   # BUY
    signals[rsi > 70] = -1  # SELL
    
    return signals
"""
    
    strategy_payload = {
        "name": "System Test RSI",
        "code": test_code,
        "symbol": "BTC/USDT",
        "asset_type": "crypto",
        "tags": ["test", "rsi"],
        "last_modified": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    # Check if it already exists
    curr.execute('SELECT id FROM strategies WHERE name=?', (strategy_payload['name'],))
    existing = curr.fetchone()
    
    if existing:
        curr.execute('''
            UPDATE strategies 
            SET code=?, symbol=?, asset_type=?, tags=?, last_modified=?
            WHERE id=?
        ''', (strategy_payload['code'], strategy_payload['symbol'], strategy_payload['asset_type'], 
              json.dumps(strategy_payload['tags']), strategy_payload['last_modified'], existing[0]))
        print(f"Updated existing '{strategy_payload['name']}' strategy.")
    else:
        curr.execute('''
            INSERT INTO strategies (name, code, symbol, asset_type, tags, last_modified)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (strategy_payload['name'], strategy_payload['code'], strategy_payload['symbol'], 
              strategy_payload['asset_type'], json.dumps(strategy_payload['tags']), strategy_payload['last_modified']))
        print(f"Inserted new '{strategy_payload['name']}' strategy.")

    conn.commit()
    conn.close()
    print("Injection complete.")

if __name__ == "__main__":
    inject_test_data()
