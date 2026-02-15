
import os
import sys
import logging
from dotenv import load_dotenv

# Add project root
sys.path.append(os.getcwd())

from src.trader.real_trader import RealTrader
from src.api.main import load_trader_config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    load_dotenv()
    
    config = load_trader_config()
    api_key = config.api_key or os.getenv("BINANCE_API_KEY")
    secret = config.api_secret or os.getenv("BINANCE_SECRET")
    proxy = config.proxy_url or os.getenv("PROXY_URL")
    
    if not api_key:
        logger.error("No API Key found!")
        return

    logger.info("Initializing RealTrader for Repairs...")
    trader = RealTrader(
        symbol="BTC/USDT:USDT",
        api_key=api_key,
        api_secret=secret,
        proxy_url=proxy
    )
    
    if not trader.active:
        logger.error("Trader failed to initialize.")
        return
        
    logger.info("Checking positions and repairing SL orders...")
    trader.repair_orders(sl_pct=0.02)
    logger.info("Repair complete.")

if __name__ == "__main__":
    main()
