import os
import sys
import logging
import json
import time
from datetime import datetime
import ccxt
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.utils.trade_persistence import TradePersistence

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

def fetch_full_history():
    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_SECRET")
    proxy_url = os.getenv("PROXY_URL", "http://127.0.0.1:33210")

    if not api_key or not api_secret:
        logger.error("API credentials not found in .env")
        return

    # Initialize Exchange
    options = {
        'apiKey': api_key,
        'secret': api_secret,
        'options': {
            'defaultType': 'swap',
            'adjustForTimeDifference': True,
        },
        'enableRateLimit': True,
        'timeout': 60000,
    }

    if proxy_url:
        options['proxies'] = {
            'http': proxy_url,
            'https': proxy_url
        }
        logger.info(f"Using proxy: {proxy_url}")

    exchange = ccxt.binanceusdm(options)
    
    try:
        # Test connection
        exchange.load_markets()
        logger.info("Connected to Binance Futures")
        
        # Initialize Persistence
        persistence = TradePersistence()
        
        # 1. Get all symbols that have been traded?
        # Ideally we iterate over all symbols, or just the ones we care about.
        # But fetching *all* symbols might be slow.
        # Let's start with the monitored list + any common ones.
        
        # Symbols from monitored list (hardcoded for now as per project scope)
        target_symbols = [
            'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'DOGE/USDT',
            'XRP/USDT', 'PEPE/USDT', 'AVAX/USDT', 'LINK/USDT', 'ADA/USDT',
            'TRX/USDT', 'LDO/USDT', 'BCH/USDT', 'OP/USDT'
        ]
        
        # Also check for any existing positions or balance to find other symbols?
        # For now, let's stick to the target list + maybe fetch open orders to find others.
        
        total_fetched = 0
        
        for symbol in target_symbols:
            logger.info(f"Fetching history for {symbol}...")
            
            all_trades = []
            # Start from 2024-01-01 (or earlier if needed)
            # 1704067200000 = 2024-01-01 00:00:00 UTC
            since = 1704067200000 
            limit = 1000
            
            # Or just start from 0 to get EVERYTHING
            since = 0
            
            while True:
                try:
                    trades = exchange.fetch_my_trades(symbol, since=since, limit=limit)
                    if not trades:
                        break
                        
                    all_trades.extend(trades)
                    logger.info(f"  Fetched {len(trades)} trades for {symbol}. Total: {len(all_trades)}")
                    
                    # Update 'since' for next page
                    # ccxt returns trades sorted by timestamp (usually)
                    last_trade = trades[-1]
                    since = last_trade['timestamp'] + 1
                    
                    if len(trades) < limit:
                        break
                        
                    time.sleep(0.5) # Rate limit friendly
                    
                except Exception as e:
                    logger.error(f"Error fetching {symbol}: {e}")
                    break
            
            if all_trades:
                persistence.add_trades(all_trades)
                total_fetched += len(all_trades)
                logger.info(f"Saved {len(all_trades)} trades for {symbol}")
                
        logger.info(f"✅ Full history fetch complete. Total trades saved: {total_fetched}")
        
        # Verify Stats
        stats = persistence.get_stats()
        logger.info("Current Local Stats:")
        logger.info(f"  Total Trades: {stats.get('total_trades', 0)} (This might be wrong if get_stats returns dict structure differently)")
        # Actually get_stats in TradePersistence returns specific dict, let's print it raw or keys
        # Wait, I implemented get_stats in TradePersistence in previous step?
        # I saw it in Read output. It returns {win_rate, total_trades, total_pnl...} (Wait, no, I need to check TradePersistence source again to be sure of keys)
        
        # Let's re-read TradePersistence to be sure of get_stats return structure
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        # ccxt synchronous doesn't need close
        pass

if __name__ == "__main__":
    fetch_full_history()
