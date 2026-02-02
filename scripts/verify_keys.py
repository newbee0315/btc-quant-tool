
import os
import ccxt
from dotenv import load_dotenv

# Load env vars
load_dotenv()

api_key = os.getenv("BINANCE_API_KEY")
secret = os.getenv("BINANCE_SECRET")

print(f"Testing connection with Key: {api_key[:5]}... and Secret: {secret[:5]}...")

try:
    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': secret,
        'options': {
            'defaultType': 'future',
        },
        'enableRateLimit': True
    })
    
    # Load markets to check connectivity
    exchange.load_markets()
    print("Markets loaded successfully.")
    
    # Check balance
    # specifically for futures
    balance = exchange.fetch_balance({'type': 'future'})
    usdt_balance = balance['total']['USDT']
    print(f"Connection Successful! USDT Balance: {usdt_balance}")
    
except Exception as e:
    print(f"Connection Failed: {str(e)}")
    import traceback
    traceback.print_exc()
