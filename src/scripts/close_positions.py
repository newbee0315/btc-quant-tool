import sys
import os
import logging

# Add src to python path
sys.path.append(os.getcwd())

from src.trader.real_trader import RealTrader
from src.api.main import load_trader_config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def close_all():
    logger.info("Starting manual close position...")
    config = load_trader_config()
    
    # Initialize Trader with swap symbol
    trader = RealTrader(
        symbol="BTC/USDT:USDT",
        api_key=config.api_key,
        api_secret=config.api_secret,
        proxy_url=config.proxy_url
    )
    
    if not trader.active:
        logger.error("Trader not active. Check credentials and connection.")
        return

    try:
        logger.info("Attempting to close position...")
        trader.close_position()
        logger.info("Close command sent.")
    except Exception as e:
        logger.error(f"Failed to close position: {e}")

if __name__ == "__main__":
    close_all()
