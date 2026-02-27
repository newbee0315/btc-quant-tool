
import sys
import os
import pandas as pd
import logging
import warnings
from datetime import datetime

# Suppress warnings
warnings.filterwarnings("ignore")

# Add project root to path
sys.path.append(os.getcwd())

from src.data.collector import CryptoDataCollector
from src.strategies.trend_ml_strategy import TrendMLStrategy
from src.models.predictor import PricePredictor
from src.api.main import load_trader_config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("MarketScanner")

# Mute other loggers
logging.getLogger("src.data.collector").setLevel(logging.WARNING)
logging.getLogger("src.models.predictor").setLevel(logging.WARNING)
logging.getLogger("src.strategies.trend_ml_strategy").setLevel(logging.WARNING)

def scan_market():
    # 1. Load Configuration
    try:
        config = load_trader_config()
        proxies = None
        if config.proxy_url:
            proxies = {
                "http": config.proxy_url,
                "https": config.proxy_url
            }
        logger.info(f"Loaded config. Proxy: {config.proxy_url}")
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return

    # 2. Define Symbols (14 Core Coins)
    symbols = [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT", 
        "XRPUSDT", "PEPEUSDT", "AVAXUSDT", "LINKUSDT", "ADAUSDT", 
        "TRXUSDT", "LDOUSDT", "BCHUSDT", "OPUSDT"
    ]
    
    logger.info(f"Starting market scan for {len(symbols)} symbols...")
    logger.info("Strategy: TrendMLStrategy (Trend + ML + CZSC)")
    logger.info("-" * 60)
    
    opportunities = []

    for symbol in symbols:
        try:
            # 3. Initialize Components
            collector = CryptoDataCollector(symbol=symbol, proxies=proxies)
            predictor = PricePredictor(symbol=symbol)
            strategy = TrendMLStrategy(enable_czsc=True)
            
            # 4. Fetch Data (5m timeframe)
            # Need enough for EMA200 (200 * 5m)
            df_5m = collector.fetch_ohlcv(timeframe='5m', limit=500)
            
            if df_5m is None or df_5m.empty:
                logger.warning(f"No data for {symbol}")
                continue
                
            # 5. Predict
            # Predictor generates features from passed DF
            predictions = predictor.predict_all(df_5m)
            
            if not predictions:
                logger.warning(f"No predictions for {symbol}")
                continue

            # 6. Run Strategy Analysis
            df_analyzed = strategy.calculate_indicators(df_5m)
            
            # Check last row
            if len(df_analyzed) < 2:
                continue
                
            last_row = df_analyzed.iloc[-1]
            prev_row = df_analyzed.iloc[-2]
            
            # Construct extra_data
            extra_data = {
                'ml_prediction': predictions.get('30m', {}),
                'ml_prediction_10m': predictions.get('10m', {}),
                'total_capital': 1000.0 # Dummy capital for sizing calc
            }
            
            result = strategy.get_signal(last_row, prev_row, extra_data)
            
            signal = result.get('signal', 0)
            reason = result.get('reason', '')
            indicators = result.get('indicators', {})
            
            ml_prob = indicators.get('ml_prob', 0.5)
            close_price = last_row['close']
            
            # Print status for every coin
            status = "NEUTRAL"
            if signal == 1: status = "LONG"
            elif signal == -1: status = "SHORT"
            
            logger.info(f"{symbol:<10} | {status:<7} | Price: {close_price:<10.4f} | ML(30m): {ml_prob:.2f} | Reason: {reason}")
            
            if signal != 0:
                opportunities.append({
                    'symbol': symbol,
                    'direction': status,
                    'price': close_price,
                    'ml_prob': ml_prob,
                    'reason': reason,
                    'tp': result.get('trade_params', {}).get('tp_price'),
                    'sl': result.get('trade_params', {}).get('sl_price')
                })
                
        except Exception as e:
            logger.error(f"Error processing {symbol}: {e}")
            continue
            
    logger.info("-" * 60)
    logger.info(f"Scan Complete. Found {len(opportunities)} opportunities.")
    
    if opportunities:
        logger.info("\n=== OPPORTUNITIES FOUND ===")
        for opp in opportunities:
            logger.info(f"Symbol: {opp['symbol']}")
            logger.info(f"Action: {opp['direction']} @ {opp['price']}")
            logger.info(f"ML Confidence: {opp['ml_prob']:.2f}")
            logger.info(f"Reasons: {opp['reason']}")
            logger.info(f"Setup: SL {opp['sl']:.4f} | TP {opp['tp']:.4f}")
            logger.info("-" * 30)
    else:
        logger.info("No actionable signals found at this moment.")

if __name__ == "__main__":
    scan_market()
