import sys
import os
import logging
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta

# Add src to python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.data.collector import FuturesDataCollector

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DATA_DIR = "src/data"
OUTPUT_FILE = os.path.join(DATA_DIR, "btc_futures_data.csv")

def collect_data(days=90, timeframe='5m'):
    """
    Collect OHLCV, Funding Rate, and Open Interest data for futures.
    days: Number of days of history to fetch
    timeframe: Candle timeframe (e.g., '5m', '15m')
    """
    logger.info(f"Starting futures data collection for last {days} days ({timeframe})...")
    
    # Use local proxy if needed (common in dev env)
    proxies = {
        "http": "http://127.0.0.1:33210",
        "https": "http://127.0.0.1:33210"
    }
    
    collector = FuturesDataCollector(symbol='BTCUSDT', proxies=proxies)
    
    # 1. Fetch OHLCV
    logger.info("Fetching OHLCV data...")
    # Using fetch_historical_data which handles pagination
    # Note: fetch_historical_data in collector.py defaults to 1m. 
    # We should override or use fetch_ohlcv loop.
    # The existing fetch_historical_data takes timeframe argument.
    df_ohlcv = collector.fetch_historical_data(timeframe=timeframe, days=days)
    
    if df_ohlcv.empty:
        logger.error("Failed to fetch OHLCV data.")
        return
    
    logger.info(f"Fetched {len(df_ohlcv)} candles.")
    
    # 2. Fetch Funding Rate
    logger.info("Fetching Funding Rate data...")
    # Funding rate is usually every 8 hours
    end_time = int(time.time() * 1000)
    start_time = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
    
    df_funding = collector.fetch_funding_rate_history(start_time=start_time, end_time=end_time, limit=1000)
    
    # Funding rate might need pagination if > 1000 records (1000 * 8h = 8000h = 333 days)
    # So 90 days is fine with one call usually, but let's be safe if days is large
    # Actually funding rate is sparse (3 times a day), so 1000 limit covers ~333 days.
    
    if not df_funding.empty:
        logger.info(f"Fetched {len(df_funding)} funding rate records.")
        # Rename for clarity
        df_funding = df_funding.rename(columns={'fundingTime': 'timestamp', 'fundingRate': 'funding_rate'})
        df_funding = df_funding[['timestamp', 'funding_rate']]
    else:
        logger.warning("No funding rate data found.")
    
    # 3. Fetch Open Interest
    logger.info("Fetching Open Interest data...")
    # Open Interest Hist limit is 500. 
    # If timeframe is 5m, 500 * 5m = 2500m = ~41 hours.
    # We need to loop for 90 days.
    
    # However, fetching 90 days of 5m OI data is slow (API limits).
    # Maybe use 1h OI data and forward fill? 
    # Or try to fetch as much as possible.
    # Let's try to fetch 1h OI data for the period.
    oi_period = '1h' 
    if timeframe == '5m' or timeframe == '15m':
         # If we use 1h OI, we can ffill.
         pass
         
    # Loop for OI
    all_oi = []
    current_start = start_time
    
    # Binance might limit historical data availability for OI (e.g. 30 days)
    # If start_time is too old, let's try to fetch from 30 days ago
    min_start_time = int((datetime.now() - timedelta(days=29)).timestamp() * 1000)
    if current_start < min_start_time:
        logger.warning(f"Adjusting start time for OI to 29 days ago (API limit).")
        current_start = min_start_time

    while current_start < end_time:
        # Fetch batch
        # limit 500
        # interval 1h -> 500 hours ~ 20 days
        try:
            df_batch = collector.fetch_open_interest_history(period=oi_period, limit=500, start_time=current_start)
            
            if df_batch.empty:
                logger.warning(f"Empty batch for OI at {current_start}")
                # Try to skip forward if stuck
                current_start += 3600000 * 24 # Skip 1 day
                continue
                
            all_oi.append(df_batch)
            
            last_ts = df_batch['timestamp'].max()
            if last_ts >= end_time or last_ts <= current_start:
                break
                
            current_start = last_ts + 1 # Next ms
            time.sleep(0.2)
        except Exception as e:
            logger.error(f"Error fetching OI batch: {e}")
            break
        
    if all_oi:
        df_oi = pd.concat(all_oi)
        df_oi = df_oi.drop_duplicates(subset=['timestamp']).sort_values('timestamp')
        logger.info(f"Fetched {len(df_oi)} OI records.")
        df_oi = df_oi[['timestamp', 'sumOpenInterest', 'sumOpenInterestValue']]
        df_oi = df_oi.rename(columns={'sumOpenInterest': 'oi', 'sumOpenInterestValue': 'oi_value'})
    else:
        df_oi = pd.DataFrame()
        logger.warning("No Open Interest data found.")

    # 4. Merge Data
    logger.info("Merging data...")
    
    # Convert timestamps to datetime for merging
    df_ohlcv['datetime'] = pd.to_datetime(df_ohlcv['timestamp'], unit='ms')
    
    # Funding Rate: Merge on nearest timestamp (ffill)
    # Funding rate comes every 8h. We want to forward fill it.
    if not df_funding.empty:
        df_funding['datetime'] = pd.to_datetime(df_funding['timestamp'], unit='ms')
        df_ohlcv = pd.merge_asof(df_ohlcv.sort_values('datetime'), 
                                 df_funding[['datetime', 'funding_rate']].sort_values('datetime'), 
                                 on='datetime', 
                                 direction='backward') # Use latest known funding rate
                                 
    # Open Interest: Merge on nearest timestamp
    if not df_oi.empty:
        df_oi['datetime'] = pd.to_datetime(df_oi['timestamp'], unit='ms')
        df_ohlcv = pd.merge_asof(df_ohlcv.sort_values('datetime'), 
                                 df_oi[['datetime', 'oi', 'oi_value']].sort_values('datetime'), 
                                 on='datetime', 
                                 direction='nearest', # OI is snapshot, nearest is okay or backward
                                 tolerance=pd.Timedelta('1h')) # Don't match if too far
    else:
        # Create empty columns if OI missing
        df_ohlcv['oi'] = 0
        df_ohlcv['oi_value'] = 0
                                 
    # Fill NaNs (if missing funding/oi at start)
    if 'funding_rate' in df_ohlcv.columns:
        df_ohlcv['funding_rate'] = df_ohlcv['funding_rate'].fillna(0)
    else:
        df_ohlcv['funding_rate'] = 0
        
    df_ohlcv['oi'] = df_ohlcv['oi'].fillna(method='ffill').fillna(method='bfill').fillna(0)
    df_ohlcv['oi_value'] = df_ohlcv['oi_value'].fillna(method='ffill').fillna(method='bfill').fillna(0)
    
    # Save
    logger.info(f"Saving merged data to {OUTPUT_FILE}...")
    df_ohlcv.to_csv(OUTPUT_FILE, index=False)
    logger.info("Done.")

if __name__ == "__main__":
    # Collect 180 days of 5m data as requested
    collect_data(days=180, timeframe='5m')
