
import requests
import json
import time

def test_portfolio_scan():
    url = "http://localhost:8000/api/v1/portfolio/scan"
    print(f"Calling {url}...")
    try:
        response = requests.post(url, timeout=60)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print("Response:")
            print(json.dumps(data, indent=2))
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    test_portfolio_scan()
