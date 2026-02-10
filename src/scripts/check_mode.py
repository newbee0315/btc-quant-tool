import sys
import os
import logging
sys.path.append(os.getcwd())

from src.trader.real_trader import RealTrader
from src.api.main import load_trader_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_mode():
    config = load_trader_config()
    trader = RealTrader(
        symbol="BTC/USDT:USDT",
        api_key=config.api_key,
        api_secret=config.api_secret,
        proxy_url=config.proxy_url
    )
    
    if not trader.active:
        return

    try:
        # Check current mode
        # Binance specific: fapiPrivateGetPositionSideDual
        response = trader.exchange.fapiPrivateGetPositionSideDual()
        logger.info(f"Current Mode Response: {response}")
        # {'dualSidePosition': True} -> Hedge Mode
        # {'dualSidePosition': False} -> One-Way Mode
        
        is_hedge_mode = response.get('dualSidePosition')
        logger.info(f"Is Hedge Mode: {is_hedge_mode}")
        
        if is_hedge_mode:
            logger.info("Switching to One-Way Mode...")
            trader.exchange.fapiPrivatePostPositionSideDual({'dualSidePosition': 'false'})
            logger.info("Switched to One-Way Mode successfully.")
        else:
            logger.info("Already in One-Way Mode.")
            
    except Exception as e:
        logger.error(f"Error checking/setting mode: {e}")

if __name__ == "__main__":
    check_mode()
