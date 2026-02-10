import sys
import os
import logging
sys.path.append(os.getcwd())

from src.trader.real_trader import RealTrader
from src.api.main import load_trader_config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def check_pos():
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
        pos = trader.get_position()
        if pos:
            logger.info(f"✅ CURRENT POSITION: {pos['side'].upper()} {pos['amount']} BTC")
            logger.info(f"   Entry: {pos['entry_price']}")
            logger.info(f"   Unrealized PnL: {pos['unrealized_pnl']} USDT")
        else:
            logger.info("❌ No open positions found.")
            
    except Exception as e:
        logger.error(f"Error checking position: {e}")

if __name__ == "__main__":
    check_pos()
