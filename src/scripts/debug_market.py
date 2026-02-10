import sys
import os
import logging
# Add src to python path
sys.path.append(os.getcwd())

from src.trader.real_trader import RealTrader
from src.api.main import load_trader_config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_market():
    config = load_trader_config()
    trader = RealTrader(
        symbol="BTC/USDT",
        api_key=config.api_key,
        api_secret=config.api_secret,
        proxy_url=config.proxy_url
    )
    
    logger.info(f"Loaded Market Info for {trader.symbol}")
    
    # Try explicitly getting the swap symbol if BTC/USDT is spot
    try:
        market = trader.exchange.market(trader.symbol)
        logger.info(f"Symbol: {trader.symbol} -> Type: {market['type']}, Linear: {market.get('linear')}")
    except Exception as e:
        logger.info(f"Market {trader.symbol} not found: {e}")

    # Check for BTC/USDT:USDT
    try:
        swap_symbol = "BTC/USDT:USDT"
        market_swap = trader.exchange.market(swap_symbol)
        logger.info(f"Symbol: {swap_symbol} -> Type: {market_swap['type']}, Linear: {market_swap.get('linear')}")
        
        # Try setting leverage on THIS symbol
        trader.exchange.set_leverage(10, swap_symbol)
        logger.info(f"Set Leverage SUCCESS on {swap_symbol}")
        
        # Try create order (dry run or check price)
        ticker = trader.exchange.fetch_ticker(swap_symbol)
        logger.info(f"Ticker for {swap_symbol}: {ticker['last']}")
        
    except Exception as e:
        logger.error(f"Failed on swap symbol: {e}")

if __name__ == "__main__":
    check_market()
