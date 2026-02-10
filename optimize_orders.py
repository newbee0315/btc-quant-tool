import sys
import os
import logging
import json
import time
from dotenv import load_dotenv

# Add src to path
sys.path.append(os.getcwd())

from src.trader.real_trader import RealTrader

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("OrderOptimizer")

def load_config():
    try:
        with open('trader_config.json', 'r') as f:
            return json.load(f)
    except:
        return {}

def main():
    load_dotenv()
    config = load_config()
    
    # Force real mode params for this script
    api_key = config.get('api_key') or os.getenv("BINANCE_API_KEY")
    api_secret = config.get('api_secret') or os.getenv("BINANCE_SECRET")
    proxy_url = config.get('proxy_url') or "http://127.0.0.1:33210"
    
    logger.info(f"Initializing RealTrader with proxy {proxy_url}...")
    
    trader = RealTrader(
        symbol="BTC/USDT:USDT", # Default, but we'll scan all
        api_key=api_key,
        api_secret=api_secret,
        proxy_url=proxy_url
    )
    
    if not trader.active:
        logger.error("Failed to initialize trader. Check connection/proxy.")
        return

    logger.info("Fetching active positions...")
    positions = trader.get_positions()
    
    if not positions:
        logger.info("No active positions found.")
        return

    logger.info(f"Found {len(positions)} active positions.")
    
    for symbol, pos in positions.items():
        amount = float(pos['amount'])
        entry_price = float(pos['entry_price'])
        side = pos['side']
        pnl_pct = pos['pnl_pct']
        
        logger.info(f"Processing {symbol}: {side} {amount} @ {entry_price} (PnL: {pnl_pct:.2f}%)")
        
        # 1. Cancel existing orders
        try:
            logger.info(f"  Cancelling existing orders for {symbol}...")
            trader.exchange.cancel_all_orders(symbol)
        except Exception as e:
            logger.error(f"  Failed to cancel orders: {e}")
            continue
            
        # 2. Calculate New SL/TP (Optimization)
        # Using "Normal" mode defaults or Config
        # SL: 2% (0.02) - Conservative for now
        # TP: 3% (0.03)
        
        sl_pct = 0.02
        tp_pct = 0.03
        
        sl_price = 0.0
        tp_price = 0.0
        
        if side == 'long':
            sl_price = entry_price * (1 - sl_pct)
            tp_price = entry_price * (1 + tp_pct)
            sl_side = 'sell'
        else:
            sl_price = entry_price * (1 + sl_pct)
            tp_price = entry_price * (1 - tp_pct)
            sl_side = 'buy'
            
        # Precision
        sl_price = float(trader.exchange.price_to_precision(symbol, sl_price))
        tp_price = float(trader.exchange.price_to_precision(symbol, tp_price))
        
        logger.info(f"  Placing New SL: {sl_price}, TP: {tp_price}")
        
        # 3. Place New Orders (ReduceOnly)
        try:
            # Stop Loss
            trader.exchange.create_order(symbol, 'STOP_MARKET', sl_side, amount, params={
                'stopPrice': sl_price,
                'reduceOnly': True
            })
            logger.info("  ✅ SL Order Placed")
            
            # Take Profit
            trader.exchange.create_order(symbol, 'TAKE_PROFIT_MARKET', sl_side, amount, params={
                'stopPrice': tp_price,
                'reduceOnly': True
            })
            logger.info("  ✅ TP Order Placed")
            
        except Exception as e:
            logger.error(f"  ❌ Failed to place orders: {e}")

    logger.info("Optimization complete.")

if __name__ == "__main__":
    main()
