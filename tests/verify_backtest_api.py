import requests
import json

API_URL = "http://localhost:8000/api/v1/backtest/run"

payload = {
    "symbol": "BTCUSDT",
    "days": 5,  # Short duration for quick test
    "horizon": 60,
    "threshold": 0.6,
    "sl": 0.02,
    "tp": 0.04,
    "initial_capital": 10000.0
}

try:
    print(f"Sending request to {API_URL} with payload: {payload}")
    response = requests.post(API_URL, json=payload)
    
    if response.status_code == 200:
        data = response.json()
        print("Status Code: 200")
        if data.get("status") == "success":
            results = data.get("results", {})
            trades = data.get("trades", [])
            equity = data.get("equity_curve", [])
            
            print(f"Backtest Successful!")
            print(f"Initial Capital: {results.get('initial_capital')}")
            print(f"Final Capital: {results.get('final_capital')}")
            print(f"Total Trades: {results.get('total_trades')}")
            print(f"Win Rate: {results.get('win_rate')}%")
            print(f"Trades Count: {len(trades)}")
            print(f"Equity Points: {len(equity)}")
            
            if len(trades) > 0:
                print("Sample Trade:", trades[0])
        else:
            print("Backtest failed (logical error):", data.get("message"))
    else:
        print(f"Request failed with status {response.status_code}: {response.text}")

except Exception as e:
    print(f"Exception: {e}")
