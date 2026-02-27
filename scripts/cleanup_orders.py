import os
import sys
import logging
import ccxt
import time
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.getcwd())

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load env
load_dotenv()

# 14 Target Symbols (Mapped to CCXT Futures format)
# Note: PEPE is 1000PEPE on Binance Futures usually
SYMBOL_MAP = {
    'BTC/USDT': 'BTC/USDT:USDT',
    'ETH/USDT': 'ETH/USDT:USDT',
    'SOL/USDT': 'SOL/USDT:USDT',
    'BNB/USDT': 'BNB/USDT:USDT',
    'DOGE/USDT': 'DOGE/USDT:USDT',
    'XRP/USDT': 'XRP/USDT:USDT',
    'PEPE/USDT': '1000PEPE/USDT:USDT',
    'AVAX/USDT': 'AVAX/USDT:USDT',
    'LINK/USDT': 'LINK/USDT:USDT',
    'ADA/USDT': 'ADA/USDT:USDT',
    'TRX/USDT': 'TRX/USDT:USDT',
    'LDO/USDT': 'LDO/USDT:USDT',
    'BCH/USDT': 'BCH/USDT:USDT',
    'OP/USDT': 'OP/USDT:USDT'
}

def cleanup():
    api_key = os.getenv("BINANCE_API_KEY")
    secret = os.getenv("BINANCE_SECRET")
    
    # Proxy Logic matching run_multicoin_bot.py
    proxy_url = os.getenv("PROXY_URL")
    if proxy_url is None:
        proxy_url = "http://127.0.0.1:33210" # Default for local dev
    elif proxy_url == "":
        proxy_url = None # Explicitly disabled
    
    if not api_key or not secret:
        logger.error("API credentials missing in .env")
        return

    options = {
        'apiKey': api_key,
        'secret': secret,
        'options': {
            'defaultType': 'swap',
            'fetchCurrencies': False  # Disable fetching currencies to avoid hitting sapi
        },
        'has': {
            'fetchCurrencies': False
        },
        'enableRateLimit': True
    }
    
    if proxy_url:
        options['proxies'] = {
            'http': proxy_url,
            'https': proxy_url
        }
        logger.info(f"Using proxy: {proxy_url}")

    exchange = ccxt.binanceusdm(options)
    
    try:
        logger.info("Connecting to Binance Futures...")
        exchange.load_markets()
    except Exception as e:
        logger.error(f"Failed to connect: {e}")
        return
    
    for symbol in SYMBOL_MAP.values():
        logger.info(f"--- Cleaning {symbol} ---")
        try:
            # 1. Fetch Open Orders
            orders = exchange.fetch_open_orders(symbol)
            if orders:
                logger.info(f"Found {len(orders)} standard open orders. Cancelling...")
                exchange.cancel_all_orders(symbol)
                logger.info("✅ Cancelled all standard open orders.")
            else:
                logger.info("No standard open orders found.")

            # 2. Check Algo Orders (using private API)
            # Some SL/TP orders might exist as Algo Orders
            try:
                raw_symbol = symbol.replace('/', '').replace(':USDT', '').replace(':BUSD', '')
                algo_orders = exchange.fapiPrivateGetOpenAlgoOrders({'symbol': raw_symbol})
                if algo_orders and len(algo_orders) > 0:
                    logger.info(f"Found {len(algo_orders)} algo orders. Cancelling...")
                    logger.info(f"Sample order: {algo_orders[0]}")
                    
                    for order in algo_orders:
                         oid = order.get('orderId')
                         if not oid:
                             oid = order.get('algoId') # Check if it's called algoId
                         
                         if oid:
                             try:
                                 # Use correct parameter name 'algoId'
                                 exchange.fapiPrivateDeleteAlgoOrder({'symbol': raw_symbol, 'algoId': oid})
                                 logger.info(f"Cancelled Algo Order {oid}")
                             except Exception as e:
                                 logger.error(f"Failed to cancel Algo Order {oid}: {e}")
                         else:
                             logger.warning(f"Could not find ID for order: {order}")
                else:
                    logger.info("No algo orders found.")
            except Exception as e:
                logger.warning(f"Error checking algo orders: {e}")

        except Exception as e:
            logger.error(f"Error processing {symbol}: {e}")
        
        time.sleep(0.5) # Avoid rate limits

    logger.info("Cleanup complete.")

if __name__ == "__main__":
    cleanup()
