import sys
import os
import logging
from datetime import datetime

# Add src to python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.data.collector import FuturesDataCollector

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    logger.info("Starting Futures Data Test...")
    
    # Use local proxy if needed
    proxies = {
        "http": "http://127.0.0.1:33210",
        "https": "http://127.0.0.1:33210"
    }
    
    collector = FuturesDataCollector(symbol='BTCUSDT', proxies=proxies)
    
    # Test 1: Fetch Funding Rate History
    logger.info("\n--- Testing Fetch Funding Rate ---")
    df_funding = collector.fetch_funding_rate_history(limit=5)
    if not df_funding.empty:
        logger.info("Funding Rate Data Sample:")
        print(df_funding[['fundingTime', 'fundingRate', 'markPrice']].head())
    else:
        logger.error("Failed to fetch funding rate data")
        
    # Test 2: Fetch Open Interest History
    logger.info("\n--- Testing Fetch Open Interest ---")
    df_oi = collector.fetch_open_interest_history(period='1h', limit=5)
    if not df_oi.empty:
        logger.info("Open Interest Data Sample:")
        print(df_oi[['datetime', 'sumOpenInterest', 'sumOpenInterestValue']].head())
    else:
        logger.error("Failed to fetch open interest data")

if __name__ == "__main__":
    main()
