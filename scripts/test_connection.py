
import ccxt
import os
import json
import logging
import traceback

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_connection():
    config_path = 'trader_config.json'
    if not os.path.exists(config_path):
        print("Config file not found")
        return

    with open(config_path, 'r') as f:
        config = json.load(f)
        
    api_key = config.get('api_key')
    secret = config.get('api_secret')
    
    print(f"Testing with Key: {api_key[:5]}... Secret: {secret[:5]}...")
    
    try:
        exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': secret,
            'options': {
                'defaultType': 'future',
            },
            'proxies': {
                'http': 'http://127.0.0.1:1080',
                'https': 'http://127.0.0.1:1080',
            },
            'enableRateLimit': True,
        })
        
        print("Loading markets...")
        try:
            exchange.load_markets()
            print("Markets loaded.")
        except Exception as e:
            print(f"Error loading markets: {e}")
            # Continue to try balance even if markets fail (might fail too)
        
        print("Fetching Balance...")
        balance = exchange.fetch_balance()
        print("Balance fetched successfully.")
        print(f"USDT Free: {balance['USDT']['free']}")
        
    except Exception as e:
        print("FATAL ERROR:")
        traceback.print_exc()

if __name__ == "__main__":
    test_connection()
