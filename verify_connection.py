
import sys
import os
import logging
from dotenv import load_dotenv

import json

# Add project root to path
sys.path.append(os.getcwd())

from src.trader.real_trader import RealTrader

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_config():
    config_path = os.path.join(os.getcwd(), 'trader_config.json')
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Failed to load config: {e}")
    return {}

def check_connection():
    load_dotenv()
    config = load_config()
    
    print("Checking Real Trader Connection...")
    try:
        # Prioritize config file, fallback to env vars (handled by RealTrader internally if None passed)
        api_key = config.get('api_key')
        api_secret = config.get('api_secret')
        proxy_url = config.get('proxy_url')
        
        print(f"Using Proxy: {proxy_url}")
        
        trader = RealTrader(api_key=api_key, api_secret=api_secret, proxy_url=proxy_url)
        
        if not trader.active:
            print(f"❌ Trader not active. Error: {trader.last_connection_error}")
            return
            
        print("✅ Trader Initialized Successfully")
        
        # Check Balance
        balance = trader.get_balance()
        print(f"💰 Available Balance: {balance} USDT")
        
        total_balance = trader.get_total_balance()
        print(f"💰 Total Balance: {total_balance} USDT")
        
        # Check Position
        pos = trader.get_position()
        if pos:
            print(f"📊 Current Position: {pos}")
        else:
            print("⚪ No active position")
            
        # Check Stats (Win Rate)
        if hasattr(trader, 'get_stats'):
            stats = trader.get_stats()
            print(f"📈 Stats: {stats}")
        else:
            print("⚠️ get_stats method missing!")
            
    except Exception as e:
        print(f"❌ Exception during check: {e}")

if __name__ == "__main__":
    check_connection()
