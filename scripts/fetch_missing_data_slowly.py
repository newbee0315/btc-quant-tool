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
    """Return Top 14 Selected Coins (Focus Strategy)"""
    symbols = [
        'BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'BNB/USDT:USDT', 'DOGE/USDT:USDT',
        'XRP/USDT:USDT', '1000PEPE/USDT:USDT', 'AVAX/USDT:USDT', 'LINK/USDT:USDT', 'ADA/USDT:USDT',
        'TRX/USDT:USDT', 'LDO/USDT:USDT', 'BCH/USDT:USDT', 'OP/USDT:USDT'
    ]
    return symbols

def fetch_history_for_symbol(exchange, symbol, timeframe, days):
    """Fetch historical data for a single symbol and timeframe"""
    if '1000PEPE' in symbol:
        safe_symbol = 'PEPEUSDT'
    else:
        safe_symbol = symbol.split('/')[0] + "USDT"
    filepath = os.path.join(DATA_DIR, f"{safe_symbol}_{timeframe}.csv")
    
    # Check if exists and determine start time
    if os.path.exists(filepath):
        try:
            df_existing = pd.read_csv(filepath)
            if not df_existing.empty and 'timestamp' in df_existing.columns:
                last_ts = df_existing['timestamp'].iloc[-1]
                start_time = datetime.fromtimestamp(last_ts / 1000)
                logger.info(f"[{symbol} {timeframe}] Data exists. Last timestamp: {start_time}. Checking for updates...")
                since = int(last_ts) + 1
            else:
                logger.warning(f"[{symbol} {timeframe}] File exists but is empty or invalid. Deleting and re-fetching.")
                if os.path.exists(filepath):
                    os.remove(filepath)
                
                end_time = datetime.now()
                start_time = end_time - timedelta(days=days)
                since = int(start_time.timestamp() * 1000)
        except Exception as e:
            logger.error(f"[{symbol} {timeframe}] Error reading existing file: {e}. Deleting and re-fetching.")
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except OSError as err:
                    logger.error(f"Error deleting file {filepath}: {err}")
            
            end_time = datetime.now()
            start_time = end_time - timedelta(days=days)
            since = int(start_time.timestamp() * 1000)
    else:
        logger.info(f"[{symbol} {timeframe}] File not found. Downloading full history.")
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        since = int(start_time.timestamp() * 1000)

    # If since is close to now, skip
    if (datetime.now().timestamp() * 1000) - since < 60000 * 5: # Less than 5 mins gap
        logger.info(f"[{symbol} {timeframe}] Data is up to date. Skipping.")
        return

    all_ohlcv = []
    
    logger.info(f"[{symbol} {timeframe}] Starting download from {datetime.fromtimestamp(since/1000)}")
    
    end_ts_limit = int(datetime.now().timestamp() * 1000)
    
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
            if last_timestamp >= end_ts_limit:
                break
            
            # Sleep to be gentle
            time.sleep(0.5) 
            
            # Progress log
            if len(all_ohlcv) % 10000 == 0:
                 logger.info(f"[{symbol} {timeframe}] Downloaded {len(all_ohlcv)} candles...")

        # Save to CSV
        if all_ohlcv:
            new_df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            new_df['datetime'] = pd.to_datetime(new_df['timestamp'], unit='ms')
            
            if os.path.exists(filepath):
                try:
                     df_existing = pd.read_csv(filepath)
                     # Ensure timestamp is same type
                     df_existing['timestamp'] = df_existing['timestamp'].astype(float)
                     new_df['timestamp'] = new_df['timestamp'].astype(float)
                     
                     combined = pd.concat([df_existing, new_df])
                     combined = combined.drop_duplicates(subset=['timestamp'], keep='last')
                     combined = combined.sort_values(by='timestamp')
                     
                     combined.to_csv(filepath, index=False)
                     logger.info(f"[{symbol} {timeframe}] Appended {len(new_df)} rows. Total: {len(combined)}")
                except Exception as e:
                     logger.error(f"[{symbol} {timeframe}] Error appending: {e}")
                     # Fallback to overwrite if append fails? No, safe to not overwrite if error.
            else:
                new_df.to_csv(filepath, index=False)
                logger.info(f"[{symbol} {timeframe}] Saved {len(new_df)} rows to {filepath}")
        else:
            logger.warning(f"[{symbol} {timeframe}] No new data found.")
            
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
