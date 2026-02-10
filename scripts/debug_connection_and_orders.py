
import sys
import os
import json
import logging
import traceback
from pprint import pprint

# Add src to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.trader.real_trader import RealTrader

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_config():
    config_path = os.path.join(os.path.dirname(__file__), '../trader_config.json')
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return json.load(f)
    return None

def main():
    print("=== Debugging RealTrader Connection & Orders ===")
    
    config = load_config()
    if not config:
        print("❌ Error: trader_config.json not found!")
        return

    print(f"Loaded Config: Mode={config.get('mode')}, Proxy={config.get('proxy_url')}")
    
    # Initialize Trader
    try:
        trader = RealTrader(
            symbol="BTC/USDT:USDT",
            leverage=20, # Default
            api_key=config.get('api_key'),
            api_secret=config.get('api_secret'),
            proxy_url=config.get('proxy_url')
        )
        
        if not trader.exchange:
            print("❌ Trader initialized but exchange is None. Checking logs...")
            print(f"Connection Status: {trader.last_connection_status}")
            print(f"Connection Error: {trader.last_connection_error}")
            return
            
        print("✅ Exchange initialized successfully!")
        
        # Check Balance
        try:
            balance = trader.get_balance()
            equity = trader.get_total_balance()
            print(f"💰 Wallet Balance: {balance:.2f} USDT")
            print(f"💰 Equity (Total Margin Balance): {equity:.2f} USDT")
        except Exception as e:
            print(f"❌ Error fetching balance: {e}")
            traceback.print_exc()

        # Check Positions
        print("\n=== Open Positions ===")
        try:
            positions = trader.get_positions()
            if not positions:
                print("No open positions found.")
            else:
                for sym, pos in positions.items():
                    print(f"📌 {sym}:")
                    pprint(pos)
                    
                    # Check Open Orders for this symbol
                    print(f"   --- Open Orders for {sym} ---")
                    try:
                        # Ensure we use the correct symbol format for fetching orders
                        # RealTrader might store it as 'BTC/USDT:USDT' but fetch_open_orders needs 'BTC/USDT:USDT' or 'BTC/USDT' depending on ccxt
                        # The key in positions is usually clean symbol like 'BTCUSDT' or 'BTC/USDT:USDT'
                        
                        # We use the symbol from the position dict if available, or the key
                        market_symbol = pos.get('symbol', sym)
                        orders = trader.exchange.fetch_open_orders(market_symbol)
                        if not orders:
                            print("   No open orders.")
                        else:
                            for o in orders:
                                print(f"   - Order ID: {o['id']}")
                                print(f"     Type: {o['type']}, Side: {o['side']}")
                                print(f"     Price: {o.get('price')}, StopPrice: {o.get('stopPrice')}, TriggerPrice: {o.get('triggerPrice')}")
                                print(f"     Status: {o['status']}")
                    except Exception as order_e:
                        print(f"   ❌ Error fetching orders for {sym}: {order_e}")

        except Exception as e:
            print(f"❌ Error fetching positions: {e}")
            traceback.print_exc()
            
    except Exception as e:
        print(f"❌ CRITICAL: Failed to initialize RealTrader: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()
