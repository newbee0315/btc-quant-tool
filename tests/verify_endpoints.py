import requests
import json
import time

API_URL = "http://localhost:8000"

def test_sensitivity():
    print("\n--- Testing Sensitivity Analysis ---")
    payload = {
        "symbol": "BTCUSDT",
        "horizon": 60,
        "threshold": 0.7,
        "days": 2
    }
    try:
        response = requests.post(f"{API_URL}/api/v1/backtest/sensitivity", json=payload)
        if response.status_code == 200:
            data = response.json()
            if data['status'] == 'success':
                print(f"Success! Returned {len(data['results'])} results.")
                if data['results']:
                    print(f"Sample: {data['results'][0]}")
            else:
                print(f"Failed: {data}")
        else:
            print(f"Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"Exception: {e}")

def test_optimization():
    print("\n--- Testing Optimization ---")
    payload = {
        "symbol": "BTCUSDT",
        "horizon": 60,
        "sl": 0.02,
        "tp": 0.04,
        "days": 2
    }
    try:
        response = requests.post(f"{API_URL}/api/v1/backtest/optimize", json=payload)
        if response.status_code == 200:
            data = response.json()
            if data['status'] == 'success':
                print(f"Success! Returned {len(data['results'])} results.")
                if data['results']:
                    print(f"Sample: {data['results'][0]}")
            else:
                print(f"Failed: {data}")
        else:
            print(f"Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"Exception: {e}")

def test_portfolio_scan():
    print("\n--- Testing Portfolio Scan ---")
    try:
        response = requests.post(f"{API_URL}/api/v1/portfolio/scan")
        if response.status_code == 200:
            data = response.json()
            if data['status'] == 'success':
                print(f"Success! Opportunities found: {len(data['opportunities'])}")
                for opp in data['opportunities']:
                    print(f"- {opp['symbol']}: {opp['signal']} ({opp['confidence']})")
            else:
                print(f"Failed: {data}")
        else:
            print(f"Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    # Wait for server to be ready
    print("Waiting for server...")
    time.sleep(2)
    
    test_sensitivity()
    test_optimization()
    test_portfolio_scan()
