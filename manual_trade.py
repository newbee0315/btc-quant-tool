import os
import sys
import json
import logging
import pandas as pd
from dotenv import load_dotenv

# Load env vars
load_dotenv()

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))

from src.trader.real_trader import RealTrader
from src.data.collector import CryptoDataCollector, FuturesDataCollector
from src.strategies.trend_ml_strategy import TrendMLStrategy
from src.models.predictor import PricePredictor

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ManualTrade")

TRADER_CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'trader_config.json')

def load_config():
    if os.path.exists(TRADER_CONFIG_FILE):
        try:
            with open(TRADER_CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
    return {}

def main():
    logger.info("Starting Manual Trade Script...")
    
    config = load_config()
    api_key = config.get('api_key') or os.getenv("BINANCE_API_KEY")
    api_secret = config.get('api_secret') or os.getenv("BINANCE_SECRET")
    proxy_url = config.get('proxy_url') or os.getenv("HTTP_PROXY")
    
    # Init Trader
    symbol = "BTC/USDT:USDT"
    leverage = 20 # Force 20x as per requirement
    
    trader = RealTrader(
        symbol=symbol,
        leverage=leverage,
        api_key=api_key,
        api_secret=api_secret,
        proxy_url=proxy_url
    )
    
    if not trader.active:
        logger.error("Trader not active. Check API keys.")
        return

    # Check Position
    try:
        pos = trader.get_position()
        if pos and float(pos['amount']) != 0:
            logger.info(f"EXISTING POSITION FOUND: {pos['side']} {pos['amount']} @ {pos['entry_price']}")
            logger.info("Skipping manual open to avoid conflict.")
            return
    except Exception as e:
        logger.error(f"Error checking position: {e}")
        return

    logger.info("No existing position. Analyzing market...")
    
    # Data
    collector = CryptoDataCollector(symbol="BTCUSDT")
    if proxy_url:
        collector.set_proxy(proxy_url)
        
    futures_collector = FuturesDataCollector(symbol="BTCUSDT")
    
    # Fetch Data
    # Fetch 1m data
    df = collector.fetch_ohlcv(timeframe="1m", limit=500)
    if df is None or len(df) == 0:
        logger.error("Failed to fetch OHLCV data.")
        return
        
    # Convert list to DataFrame if needed (fetch_ohlcv might return list)
    if isinstance(df, list):
         df = pd.DataFrame(df)
         
    funding = futures_collector.fetch_funding_rate_history()
    oi_hist = futures_collector.fetch_open_interest_history(period="5m", limit=500)
    
    # Predictor
    logger.info("Running ML Prediction...")
    predictor = PricePredictor()
    preds = predictor.predict_all(df)
    
    extra_data = {
        "funding_rate": funding,
        "oi_history": oi_hist,
        "ml_prediction": preds.get('30m') if preds else None,
        "ml_prediction_10m": preds.get('10m') if preds else None
    }
    
    # Strategy
    strategy = TrendMLStrategy()
    analysis_result = strategy.analyze(df, extra_data=extra_data)
    
    signal = analysis_result["signal"]
    reason = analysis_result["reason"]
    debug_info = analysis_result.get("indicators", {})
    
    logger.info(f"Strategy Signal: {signal}")
    logger.info(f"Reasons: {reason}")
    
    final_signal = signal
    
    # Force Logic if Signal is 0
    if final_signal == 0:
        logger.info("Strategy says HOLD. Forcing trade based on ML Probability...")
        
        prob_10m = 0.5
        if preds and '10m' in preds and 'probability' in preds['10m']:
            prob_10m = preds['10m']['probability']
            
        logger.info(f"ML Prob 10m: {prob_10m}")
        
        if prob_10m >= 0.5:
            final_signal = 1
            logger.info("Forcing LONG (Prob >= 0.5)")
        else:
            final_signal = -1
            logger.info("Forcing SHORT (Prob < 0.5)")
            
    # Execute
    if final_signal != 0:
        # Load params from config
        sl_pct = config.get('sl_pct', 0.03)
        tp_pct = config.get('tp_pct', 0.025)
        
        # Check balance
        available_balance = trader.get_balance()
        logger.info(f"Available Balance: {available_balance} USDT")
        
        # Determine amount (Margin)
        target_amount = config.get('amount_usdt', 20.0)
        
        if available_balance < target_amount:
            logger.warning(f"Balance ({available_balance}) < Target ({target_amount}). Adjusting...")
            amount_usdt = available_balance * 0.95
        else:
            amount_usdt = target_amount
            
        # Ensure min amount (Margin)
        if amount_usdt < 1.0:
            logger.error(f"Amount {amount_usdt} too small for margin.")
            return

        logger.info(f"Executing trade: Signal={final_signal}, Amount={amount_usdt} USDT")
        trader.set_amount(amount_usdt)
        trader.execute_trade(final_signal, sl_pct=sl_pct, tp_pct=tp_pct, leverage=leverage)
        logger.info("Trade Execution Command Sent.")
    else:
        logger.error("Could not determine direction.")

if __name__ == "__main__":
    main()
