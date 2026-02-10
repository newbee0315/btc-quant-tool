import sys
import os
import logging
import pandas as pd
import numpy as np

# Add src to python path
sys.path.append(os.getcwd())

from src.trader.real_trader import RealTrader
from src.api.main import load_trader_config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def calculate_atr(exchange, symbol, period=14):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, '1m', limit=period+5)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        atr = true_range.rolling(period).mean().iloc[-1]
        return atr
    except Exception as e:
        logger.warning(f"Failed to calculate ATR: {e}")
        return None

def force_trade():
    logger.info("Starting manual trade execution...")
    config = load_trader_config()
    
    # Initialize Trader
    # Use explicit linear symbol for CCXT
    trader = RealTrader(
        symbol="BTC/USDT:USDT",
        api_key=config.api_key,
        api_secret=config.api_secret,
        proxy_url=config.proxy_url
    )
    
    if not trader.active:
        logger.error("Trader not active. Check credentials and connection.")
        return

    # 1. Determine Direction (Force LONG as per analysis of logs > 0.5)
    signal = 1 
    logger.info("Forcing Signal: LONG (1)")

    # 2. Get Market Data
    try:
        ticker = trader.exchange.fetch_ticker(trader.symbol)
        current_price = ticker['last']
        logger.info(f"Current Price: {current_price}")
        
        atr = calculate_atr(trader.exchange, trader.symbol)
        logger.info(f"Calculated ATR(14): {atr}")
    except Exception as e:
        logger.error(f"Failed to fetch market data: {e}")
        return

    # 3. Calculate Strategy Parameters (Mimic TrendMLStrategy High Leverage Logic)
    # Use 20x leverage to meet min notional requirement (100 USDT) with small capital
    leverage = 20 
    
    # Calculate Position Size (Full Position ~98%)
    # Use config total_capital if available, else fetch balance
    balance = trader.get_balance()
    logger.info(f"Current Balance: {balance} USDT")
    
    if balance < 2.0: # Minimum safety
        logger.error("Insufficient balance for trading.")
        return
        
    total_capital = balance
    margin_amount = total_capital * 0.98
    position_value = margin_amount * leverage
    position_size = position_value / current_price
    
    # Adjust precision
    position_size = float(trader.exchange.amount_to_precision(trader.symbol, position_size))
    
    logger.info(f"Trade Params: Leverage={leverage}x, Margin={margin_amount:.2f}, Size={position_size} BTC")

    # 4. Calculate SL/TP
    sl_price = None
    tp_price = None
    
    if atr:
        sl_mult = 2.0
        tp_mult = 3.0 # Slightly conservative for test
        
        sl_dist = atr * sl_mult
        tp_dist = atr * tp_mult
        
        # Check Liquidation Distance
        liq_dist_pct = 1 / leverage
        sl_dist_pct = sl_dist / current_price
        
        if sl_dist_pct >= (liq_dist_pct * 0.8):
            sl_dist = current_price * (liq_dist_pct * 0.8)
            logger.info("SL tightened to avoid liquidation")
            
        if signal == 1:
            sl_price = current_price - sl_dist
            tp_price = current_price + tp_dist
        else:
            sl_price = current_price + sl_dist
            tp_price = current_price - tp_dist
            
        logger.info(f"Dynamic SL: {sl_price:.2f}, TP: {tp_price:.2f}")

    # 5. Execute Trade
    trader.execute_trade(
        signal=signal,
        leverage=leverage,
        amount_coins=position_size,
        sl_price=sl_price,
        tp_price=tp_price
    )
    
    logger.info("Manual trade execution completed.")

if __name__ == "__main__":
    force_trade()
