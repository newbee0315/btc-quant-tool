import ccxt
import os
import sys
import logging
from dotenv import load_dotenv

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check():
    load_dotenv()
    
    # Get config
    from src.api.main import load_trader_config
    config = load_trader_config()
    
    options = {
        'apiKey': config.api_key,
        'secret': config.api_secret,
        'options': {
            'defaultType': 'future', 
        },
        'enableRateLimit': True
    }
    
    if config.proxy_url:
        options['proxies'] = {
            'http': config.proxy_url,
            'https': config.proxy_url,
        }
        
    logger.info("Initializing ccxt.binanceusdm...")
    try:
        exchange = ccxt.binanceusdm(options)
        logger.info("ccxt instance created")
        exchange.load_markets()
        logger.info("Connected!")
        logger.info(f"Markets loaded: {len(exchange.markets)}")
    except Exception as e:
        logger.error(f"Failed: {e}")

if __name__ == "__main__":
    check()
