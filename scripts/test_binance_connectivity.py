
import os
import sys
import json
import requests
import ccxt
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def get_public_ip(proxy_url):
    try:
        proxies = {
            'http': proxy_url,
            'https': proxy_url
        } if proxy_url else None
        
        response = requests.get('https://api.ipify.org?format=json', proxies=proxies, timeout=10)
        if response.status_code == 200:
            return response.json().get('ip')
    except Exception as e:
        print(f"Error fetching IP: {e}")
    return "Unknown"

def test_connectivity():
    print("Testing Binance Futures Connectivity...")
    
    # Load config
    try:
        with open('trader_config.json', 'r') as f:
            config = json.load(f)
    except Exception as e:
        print(f"Error loading trader_config.json: {e}")
        return

    api_key = config.get('api_key') or os.getenv('BINANCE_API_KEY')
    api_secret = config.get('api_secret') or os.getenv('BINANCE_API_SECRET')
    proxy_url = config.get('proxy_url') or os.getenv('PROXY_URL')

    print(f"Proxy URL: {proxy_url}")
    current_ip = get_public_ip(proxy_url)
    print(f"Current Public IP (via Proxy): {current_ip}")
    print(f"API Key: {api_key[:4]}...{api_key[-4:] if api_key else 'None'}")

    if not api_key or not api_secret:
        print("Error: API Key or Secret missing.")
        return

    try:
        exchange = ccxt.binanceusdm({
            'apiKey': api_key,
            'secret': api_secret,
            'timeout': 30000,
            'enableRateLimit': True,
            'proxies': {
                'http': proxy_url,
                'https': proxy_url
            } if proxy_url else None
        })

        # Test public endpoint
        print("\n1. Testing Public Endpoint (Server Time)...")
        time = exchange.fetch_time()
        print(f"Success! Server Time: {time}")

        # Test private endpoint
        print("\n2. Testing Private Endpoint (Balance)...")
        balance = exchange.fetch_balance()
        print("Success! Balance fetched.")
        # print(f"USDT Free: {balance['USDT']['free']}") # Avoid error if key missing

    except Exception as e:
        print(f"\n❌ Connection Failed: {e}")

if __name__ == "__main__":
    test_connectivity()
