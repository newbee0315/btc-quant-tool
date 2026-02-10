
import requests
import json

def test_backtest_run():
    url = "http://localhost:8000/api/v1/backtest/run"
    payload = {
        "symbol": "BTCUSDT",
        "horizon": 60,
        "threshold": 0.7,
        "days": 30,
        "sl": 0.01,
        "tp": 0.02,
        "initial_capital": 10000
    }
    
    print(f"Calling {url} with payload: {payload}")
    try:
        response = requests.post(url, json=payload, timeout=120) # Increased timeout for backtest
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            if data['status'] == 'success':
                print("Backtest Success!")
                results = data['results']
                print(f"Final Capital: {results['final_capital']}")
                print(f"Total Trades: {results['total_trades']}")
                print(f"Win Rate: {results['win_rate']}")
                print(f"Total Fees: {results['total_fees']}")
            else:
                print(f"Backtest Failed: {data.get('message')}")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    test_backtest_run()
