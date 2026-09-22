import requests
import json

def test_backtest_endpoint():
    url = "http://127.0.0.1:8000/api/backtest/run"
    
    # Simple strategy code to test
    strategy_code = """
import pandas as pd
def strategy(data):
    df = data.copy()
    df['signal'] = 0
    if len(df) > 5:
        df.iloc[5, df.columns.get_loc('signal')] = 1  # Buy at 5th candle
    if len(df) > 10:
        df.iloc[10, df.columns.get_loc('signal')] = -1 # Sell at 10th candle
    return df
"""
    
    payload = {
        "symbol": "BTC/USDT",
        "asset_type": "crypto",
        "interval": "1h",
        "period": "1d",
        "initial_balance": 10000,
        "fee_pct": 0.1,
        "slippage_pct": 0.05,
        "strategy_code": strategy_code
    }
    
    try:
        print(f"Sending backtest request to {url}...")
        response = requests.post(url, json=payload, timeout=30)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            results = response.json()
            print("Backtest successful!")
            print(f"Total Return %: {results.get('total_return_pct')}")
            print(f"Trade Count: {results.get('trade_count')}")
            if results.get('trade_history'):
                print(f"First Trade: {results['trade_history'][0]}")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    test_backtest_endpoint()
