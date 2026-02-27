import os
import sys
import logging
import ccxt
import time
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.getcwd())

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Config
PROXY_URL = "http://127.0.0.1:33210"
PROXIES = {
    'http': PROXY_URL,
    'https': PROXY_URL
}

# New Strategy Parameters
SL_PCT = 0.02  # 2%
TP_PCT = 0.06  # 6%

# Monitored Symbols
SYMBOLS = [
    'BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'BNB/USDT:USDT', 'DOGE/USDT:USDT',
    'XRP/USDT:USDT', '1000PEPE/USDT:USDT', 'AVAX/USDT:USDT', 'LINK/USDT:USDT', 'ADA/USDT:USDT',
    'TRX/USDT:USDT', 'LDO/USDT:USDT', 'BCH/USDT:USDT', 'OP/USDT:USDT'
]

def get_exchange():
    load_dotenv()
    api_key = os.getenv("BINANCE_API_KEY")
    secret = os.getenv("BINANCE_SECRET")
    
    if not api_key or not secret:
        logger.error("API credentials missing")
        return None
        
    exchange = ccxt.binanceusdm({
        'apiKey': api_key,
        'secret': secret,
        'enableRateLimit': True,
        'options': {'defaultType': 'swap'},
        'proxies': PROXIES,
        'timeout': 30000,
    })
    return exchange

def reset_orders():
    exchange = get_exchange()
    if not exchange:
        return
        
    try:
        exchange.load_markets()
        logger.info("Connected to Binance Futures")
        
        logger.info(f"Targeting {len(SYMBOLS)} symbols: {SYMBOLS}")
        
        # 1. Cancel All Orders
        for symbol in SYMBOLS:
            try:
                # Cancel all open orders
                exchange.cancel_all_orders(symbol)
                logger.info(f"[{symbol}] Cancelled all open orders.")
            except Exception as e:
                logger.warning(f"[{symbol}] Cancel failed (might be no orders): {e}")

        # 2. Fetch Active Positions and Reset SL/TP
        logger.info("Fetching active positions to reset SL/TP...")
        try:
            # fetch_positions might behave differently depending on exchange
            # For Binance, fetch_positions(symbols) is supported
            positions = exchange.fetch_positions(SYMBOLS)
            
            active_positions = []
            for pos in positions:
                amt = float(pos['contracts'])
                if amt > 0:
                    active_positions.append(pos)
            
            logger.info(f"Found {len(active_positions)} active positions.")
            
            for pos in active_positions:
                symbol = pos['symbol']
                side = pos['side'] # 'long' or 'short'
                entry_price = float(pos['entryPrice'])
                amount = float(pos['contracts']) # Position size
                
                logger.info(f"Resetting orders for {symbol} ({side} {amount} @ {entry_price})")
                
                # Calculate New SL/TP
                sl_price = 0.0
                tp_price = 0.0
                
                if side == 'long':
                    sl_price = entry_price * (1 - SL_PCT)
                    tp_price = entry_price * (1 + TP_PCT)
                    sl_side = 'sell'
                else: # short
                    sl_price = entry_price * (1 + SL_PCT)
                    tp_price = entry_price * (1 - TP_PCT)
                    sl_side = 'buy'
                
                # Precision
                sl_price = exchange.price_to_precision(symbol, sl_price)
                tp_price = exchange.price_to_precision(symbol, tp_price)
                
                # Place STOP_MARKET (SL)
                try:
                    params = {
                        'stopPrice': sl_price,
                        'reduceOnly': True
                    }
                    exchange.create_order(symbol, 'STOP_MARKET', sl_side, amount, None, params)
                    logger.info(f"[{symbol}] Placed New SL at {sl_price}")
                except Exception as e:
                    logger.error(f"[{symbol}] Failed to place SL: {e}")
                
                # Place TAKE_PROFIT_MARKET (TP)
                try:
                    params = {
                        'stopPrice': tp_price,
                        'reduceOnly': True
                    }
                    exchange.create_order(symbol, 'TAKE_PROFIT_MARKET', sl_side, amount, None, params)
                    logger.info(f"[{symbol}] Placed New TP at {tp_price}")
                except Exception as e:
                    logger.error(f"[{symbol}] Failed to place TP: {e}")
                    
        except Exception as e:
            logger.error(f"Error processing positions: {e}")
            
        logger.info("Reset complete.")
        
    except Exception as e:
        logger.error(f"Global error: {e}")

if __name__ == "__main__":
    reset_orders()
