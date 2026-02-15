import os
import sys
import logging
import ccxt
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.getcwd())

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Config
PROXY_URL = "http://127.0.0.1:33210"
PROXIES = {
    'http': PROXY_URL,
    'https': PROXY_URL
}

def get_exchange():
    load_dotenv()
    api_key = os.getenv("BINANCE_API_KEY")
    secret = os.getenv("BINANCE_SECRET")
    
    if not api_key or not secret:
        logger.error("API credentials missing")
        return None
        
    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': secret,
        'enableRateLimit': True,
        'options': {'defaultType': 'swap'},
        'proxies': PROXIES,
        'timeout': 30000,
    })
    return exchange

def cancel_all_orders():
    exchange = get_exchange()
    if not exchange:
        return
        
    try:
        # 1. Fetch all open orders (this can be slow for many symbols, so better to iterate active ones if known)
        # But for safety, let's try to fetch open orders for Top 30 symbols we know we traded
        symbols = [
            'BTC/USDT:USDT', 'ETH/USDT:USDT', 'BNB/USDT:USDT', 'SOL/USDT:USDT', 'AVAX/USDT:USDT',
            'XRP/USDT:USDT', 'DOGE/USDT:USDT', 'ADA/USDT:USDT', 'TRX/USDT:USDT', 'LINK/USDT:USDT',
            'LTC/USDT:USDT', 'DOT/USDT:USDT', 'BCH/USDT:USDT', 'SHIB/USDT:USDT', 'MATIC/USDT:USDT',
            'NEAR/USDT:USDT', 'APT/USDT:USDT', 'FIL/USDT:USDT', 'ATOM/USDT:USDT', 'ARB/USDT:USDT',
            'OP/USDT:USDT', 'ETC/USDT:USDT', 'ICP/USDT:USDT', 'RNDR/USDT:USDT', 'INJ/USDT:USDT',
            'STX/USDT:USDT', 'LDO/USDT:USDT', 'VET/USDT:USDT', 'XLM/USDT:USDT', 'PEPE/USDT:USDT'
        ]
        
        logger.info(f"Checking {len(symbols)} symbols for open orders...")
        
        for symbol in symbols:
            try:
                orders = exchange.fetch_open_orders(symbol)
                if orders:
                    logger.info(f"Found {len(orders)} open orders for {symbol}. Cancelling...")
                    exchange.cancel_all_orders(symbol)
                    logger.info(f"Cancelled all orders for {symbol}")
                else:
                    # logger.info(f"No open orders for {symbol}")
                    pass
            except Exception as e:
                logger.error(f"Error checking/cancelling {symbol}: {e}")
                
        logger.info("Finished cancelling orders.")
        
    except Exception as e:
        logger.error(f"Global error: {e}")

if __name__ == "__main__":
    cancel_all_orders()
