import ccxt
import pandas as pd
import os
import time
from datetime import datetime, timedelta
import logging
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("fetch_data.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'raw')
DAYS_TO_FETCH = 180
TIMEFRAMES = ['1m', '5m', '1h']
TOP_N = 10
MAX_WORKERS = 5  # Conservative worker count to avoid rate limits

# Proxies (Optional: Load from env or config if needed, using hardcoded for now based on project memory)
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

def get_top_volume_symbols(limit=30):
    """Return Top 30 Mainstream Coins"""
    # Expanded list
    symbols = [
        'BTC/USDT:USDT', 'ETH/USDT:USDT', 'BNB/USDT:USDT', 'SOL/USDT:USDT', 'AVAX/USDT:USDT',
        'XRP/USDT:USDT', 'DOGE/USDT:USDT', 'ADA/USDT:USDT', 'TRX/USDT:USDT', 'LINK/USDT:USDT',
        'LTC/USDT:USDT', 'DOT/USDT:USDT', 'BCH/USDT:USDT', 'SHIB/USDT:USDT', 'MATIC/USDT:USDT',
        'NEAR/USDT:USDT', 'APT/USDT:USDT', 'FIL/USDT:USDT', 'ATOM/USDT:USDT', 'ARB/USDT:USDT',
        'OP/USDT:USDT', 'ETC/USDT:USDT', 'ICP/USDT:USDT', 'RNDR/USDT:USDT', 'INJ/USDT:USDT',
        'STX/USDT:USDT', 'LDO/USDT:USDT', 'VET/USDT:USDT', 'XLM/USDT:USDT', 'PEPE/USDT:USDT'
    ]
    logger.info(f"Selected Top {len(symbols)} Coins: {symbols}")
    return symbols

def fetch_history_for_symbol(symbol, timeframe, days):
    """Fetch historical data for a single symbol and timeframe"""
    exchange = get_exchange()
    # Create symbol-specific directory or just use raw root
    # Using raw root with filename convention: {Symbol}_{Timeframe}.csv
    # Sanitize symbol for filename (BTC/USDT:USDT -> BTCUSDT)
    safe_symbol = symbol.split('/')[0] + "USDT"
    filepath = os.path.join(DATA_DIR, f"{safe_symbol}_{timeframe}.csv")
    
    # Check if exists and recent
    if os.path.exists(filepath):
        mtime = os.path.getmtime(filepath)
        # If less than 24 hours old, skip
        if (time.time() - mtime) < 86400:
            logger.info(f"[{symbol} {timeframe}] Data recent (skipping).")
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
            
            # Update 'since' to the timestamp of the last candle + 1ms
            last_timestamp = ohlcv[-1][0]
            since = last_timestamp + 1
            
            # Check if we've reached current time
            if last_timestamp >= int(end_time.timestamp() * 1000):
                break
                
            # Progress log every ~5000 candles
            if len(all_ohlcv) % 5000 == 0:
                logger.info(f"[{symbol} {timeframe}] Fetched {len(all_ohlcv)} candles...")
                
            # Rate limit sleep (ccxt handles it but being safe for parallel)
            time.sleep(0.5)
            
        if not all_ohlcv:
            logger.warning(f"[{symbol} {timeframe}] No data fetched.")
            return None

        # Convert to DataFrame
        df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        # Save to CSV
        df.to_csv(filepath, index=False)
        logger.info(f"[{symbol} {timeframe}] Saved {len(df)} rows to {filepath}")
        return filepath
        
    except Exception as e:
        logger.error(f"[{symbol} {timeframe}] Failed: {e}")
        return None
    # No close() needed for sync ccxt

def main():
    # Ensure data directory exists
    os.makedirs(DATA_DIR, exist_ok=True)
    
    # 1. Get Top Symbols
    symbols = get_top_volume_symbols(TOP_N)
    
    # 2. Prepare tasks
    tasks = []
    for symbol in symbols:
        for tf in TIMEFRAMES:
            tasks.append((symbol, tf))
            
    logger.info(f"Prepared {len(tasks)} download tasks (Symbols: {len(symbols)}, Timeframes: {len(TIMEFRAMES)})")
    
    # 3. Execute concurrently
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(fetch_history_for_symbol, symbol, tf, DAYS_TO_FETCH): (symbol, tf)
            for symbol, tf in tasks
        }
        
        for future in as_completed(futures):
            symbol, tf = futures[future]
            try:
                result = future.result()
                if result:
                    print(f"✅ Completed: {symbol} {tf}")
                else:
                    print(f"❌ Failed: {symbol} {tf}")
            except Exception as e:
                print(f"❌ Exception for {symbol} {tf}: {e}")

if __name__ == "__main__":
    main()
