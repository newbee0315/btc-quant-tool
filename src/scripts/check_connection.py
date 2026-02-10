import sys
import os
import logging
from dotenv import load_dotenv

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.trader.real_trader import RealTrader
from src.api.main import TraderConfig, load_trader_config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check():
    load_dotenv()
    
    # Force real trading
    os.environ["TRADING_MODE"] = "real"
    
    trader_config = load_trader_config()
    
    logger.info("Initializing RealTrader...")
    try:
        trader = RealTrader(
            symbol="BTC/USDT:USDT", 
            leverage=20, 
            notifier=None,
            api_key=trader_config.api_key,
            api_secret=trader_config.api_secret,
            proxy_url=trader_config.proxy_url
        )
        logger.info("SUCCESS: Connected to Binance Futures Real Trading")
        
        # Check markets
        logger.info(f"Loaded {len(trader.exchange.markets)} markets")
        
        # Check position
        pos = trader.get_position()
        logger.info(f"Position: {pos}")
        
    except Exception as e:
        logger.error(f"FAILURE: {e}")

if __name__ == "__main__":
    check()
