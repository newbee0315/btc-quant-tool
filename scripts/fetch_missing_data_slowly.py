import ccxt
import pandas as pd
import os
import time
from datetime import datetime, timedelta
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("fetch_missing_data.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'raw')
DAYS_TO_FETCH = 180
TIMEFRAMES = ['1m', '5m', '1h']

# Proxies
PROXY_URL = "http://127.0.0.1:33210"
PROXIES = {
    'http': PROXY_URL,
    'https': PROXY_URL
}

def get_exchange():
    """Initialize Binance Futures exchange connection"""
    exchange = ccxt.binance({
        'enableRateLimit': True,
        'options': {
            'defaultType': 'swap',
            'adjustForTimeDifference': True,
        },
        'proxies': PROXIES,
        'timeout': 30000,
    })
    return exchange

def get_all_symbols():
    """Return Top 30 Mainstream Coins"""
    symbols = [
        'BTC/USDT:USDT', 'ETH/USDT:USDT', 'BNB/USDT:USDT', 'SOL/USDT:USDT', 'AVAX/USDT:USDT',
        'XRP/USDT:USDT', 'DOGE/USDT:USDT', 'ADA/USDT:USDT', 'TRX/USDT:USDT', 'LINK/USDT:USDT',
        'LTC/USDT:USDT', 'DOT/USDT:USDT', 'BCH/USDT:USDT', 'SHIB/USDT:USDT', 'MATIC/USDT:USDT',
        'NEAR/USDT:USDT', 'APT/USDT:USDT', 'FIL/USDT:USDT', 'ATOM/USDT:USDT', 'ARB/USDT:USDT',
        'OP/USDT:USDT', 'ETC/USDT:USDT', 'ICP/USDT:USDT', 'RNDR/USDT:USDT', 'INJ/USDT:USDT',
        'STX/USDT:USDT', 'LDO/USDT:USDT', 'VET/USDT:USDT', 'XLM/USDT:USDT', 'PEPE/USDT:USDT'
    ]
    return symbols

def fetch_history_for_symbol(exchange, symbol, timeframe, days):
    """Fetch historical data for a single symbol and timeframe"""
    safe_symbol = symbol.split('/')[0] + "USDT"
    filepath = os.path.join(DATA_DIR, f"{safe_symbol}_{timeframe}.csv")
    
    # Check if exists
    if os.path.exists(filepath):
        logger.info(f"[{symbol} {timeframe}] Data exists. Skipping.")
        return
    
    # Calculate start time
    end_time = datetime.now()
    start_time = end_time - timedelta(days=days)
    since = int(start_time.timestamp() * 1000)
    
    all_ohlcv = []
    
    logger.info(f"[{symbol} {timeframe}] Starting download from {start_time}")
    
    try:
        while True:
            # Fetch candles
            try:
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
            except ccxt.NetworkError as e:
                logger.warning(f"Network error for {symbol}: {e}. Retrying in 5s...")
                time.sleep(5)
                continue
            except Exception as e:
                logger.error(f"Error fetching {symbol}: {e}")
                break
            
            if not ohlcv:
                break
                
            all_ohlcv.extend(ohlcv)
            
            # Update since
            last_timestamp = ohlcv[-1][0]
            since = last_timestamp + 1
            
            # Break if reached end
            if last_timestamp >= int(end_time.timestamp() * 1000):
                break
            
            # Sleep to be gentle
            time.sleep(0.5) 
            
            # Progress log
            if len(all_ohlcv) % 10000 == 0:
                 logger.info(f"[{symbol} {timeframe}] Downloaded {len(all_ohlcv)} candles...")

        # Save to CSV
        if all_ohlcv:
            df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            df.to_csv(filepath)
            logger.info(f"[{symbol} {timeframe}] Saved {len(df)} rows to {filepath}")
        else:
            logger.warning(f"[{symbol} {timeframe}] No data found.")
            
    except Exception as e:
        logger.error(f"Critical error fetching {symbol} {timeframe}: {e}")

def main():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        
    exchange = get_exchange()
    symbols = get_all_symbols()
    
    logger.info(f"Checking {len(symbols)} symbols for missing data...")
    
    for symbol in symbols:
        for tf in TIMEFRAMES:
            try:
                fetch_history_for_symbol(exchange, symbol, tf, DAYS_TO_FETCH)
                # Sleep between files to ensure low frequency
                time.sleep(1)
            except Exception as e:
                logger.error(f"Failed to process {symbol} {tf}: {e}")
                
    logger.info("All download tasks completed.")

if __name__ == "__main__":
    main()
