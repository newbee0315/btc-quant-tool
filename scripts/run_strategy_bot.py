import sys
import os
import asyncio
import logging
import json
from datetime import datetime
import pandas as pd
from dotenv import load_dotenv

# Add src to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.data.collector import CryptoDataCollector, FuturesDataCollector
from src.models.predictor import PricePredictor
from src.trader.real_trader import RealTrader
from src.trader.paper_trader import PaperTrader
from src.notification.feishu import FeishuBot
from src.strategies.trend_ml_strategy import TrendMLStrategy

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log")
    ]
)
logger = logging.getLogger("BotRunner")

def load_trader_config():
    config_path = os.path.join(os.path.dirname(__file__), '../trader_config.json')
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load trader config: {e}")
    return {}

async def main():
    load_dotenv()
    
    # Load config
    config = load_trader_config()
    
    # 1. Configuration
    # Use explicit symbols for different components
    COLLECTOR_SYMBOL = "BTCUSDT"
    TRADING_SYMBOL = "BTC/USDT:USDT" # Important for ccxt swap
    
    TIMEFRAME = "1m" # Data collection timeframe
    STRATEGY_TIMEFRAME = "30m" # Model prediction horizon
    
    # Strategy Params
    EMA_PERIOD = 200
    RSI_PERIOD = 14
    ML_THRESHOLD = 0.75 # High confidence required
    LEVERAGE = 20 # Futures Leverage (updated to 20x)
    
    # Initialize Components
    # Propagate proxy to collector if present in config
    proxy_url = config.get('proxy_url') or os.getenv("HTTP_PROXY")
    
    collector = CryptoDataCollector(symbol=COLLECTOR_SYMBOL)
    futures_collector = FuturesDataCollector(symbol=COLLECTOR_SYMBOL)
    
    if proxy_url:
        collector.set_proxy(proxy_url)
        # futures_collector uses ccxt internally which might need proxy config if extended, 
        # but currently it uses public API or passed exchange. 
        # Check if FuturesDataCollector supports proxy setting? 
        # Usually it inherits or uses requests. 
        # For now assuming it works or uses env vars.
        
    predictor = PricePredictor()
    
    # Strategy
    strategy = TrendMLStrategy(
        ema_period=EMA_PERIOD, 
        rsi_period=RSI_PERIOD, 
        ml_threshold=ML_THRESHOLD
    )
    
    # Trader
    # Prioritize config file mode over env var
    TRADING_MODE = config.get('mode', os.getenv("TRADING_MODE", "paper")).lower()
    notifier = FeishuBot(os.getenv("FEISHU_WEBHOOK_URL"))
    
    amount_usdt = config.get('amount_usdt', 20.0)
    
    if TRADING_MODE == "real":
        logger.info(f"⚠️ STARTING IN REAL TRADING MODE ({TRADING_SYMBOL}, {LEVERAGE}x) ⚠️")
        trader = RealTrader(
            symbol=TRADING_SYMBOL, 
            leverage=LEVERAGE, 
            notifier=notifier,
            api_key=config.get('api_key') or os.getenv("BINANCE_API_KEY"),
            api_secret=config.get('api_secret') or os.getenv("BINANCE_SECRET"),
            proxy_url=proxy_url
        )
        trader.set_amount(amount_usdt)
    else:
        logger.info("Starting in Paper Trading Mode")
        trader = PaperTrader(notifier=notifier)
        
    trader.start()
    
    logger.info(f"Bot started. Strategy: {strategy.name} (EMA{EMA_PERIOD}, RSI{RSI_PERIOD}, ML>{ML_THRESHOLD})")
    
    # Main Loop
    while True:
        try:
            start_time = datetime.now()
            
            # 1. Fetch Data
            # We need enough data for EMA200
            # 200 periods + buffer
            limit = 500 
            df = collector.fetch_ohlcv(TIMEFRAME, limit=limit)
            
            if df is None or df.empty:
                logger.warning("Empty DataFrame received")
                await asyncio.sleep(60)
                continue
            
            # Convert list to DataFrame if needed
            if isinstance(df, list):
                df = pd.DataFrame(df)
                
            current_price = df.iloc[-1]['close']
            
            # Fetch Futures Data
            funding = futures_collector.fetch_funding_rate_history()
            oi_hist = futures_collector.fetch_open_interest_history(period="5m", limit=limit)
            
            # 2. ML Prediction
            predictions = predictor.predict_all(df)
            p30_data = predictions.get(STRATEGY_TIMEFRAME, {})
            p10_data = predictions.get("10m", {})
            ml_prob = p30_data.get("probability", 0.5)
            
            # 3. Strategy Analysis
            # For CLI, we use default risk params or load from env
            total_capital = float(os.getenv("TOTAL_CAPITAL", "1000.0"))
            risk_per_trade = float(os.getenv("RISK_PER_TRADE", "0.02"))
            
            extra_data = {
                'ml_prediction': p30_data,
                'ml_prediction_10m': p10_data,
                'funding_rate': funding,
                'oi_history': oi_hist,
                'total_capital': total_capital,
                'risk_per_trade': risk_per_trade
            }
            
            analysis = strategy.analyze(df, extra_data=extra_data)
            signal = analysis['signal']
            reason = analysis['reason']
            indicators = analysis['indicators']
            trade_params = analysis.get('trade_params', {})
            
            logger.info(f"Price: {current_price:.2f} | ML: {ml_prob:.2f} | EMA: {indicators.get('ema',0):.1f} | RSI: {indicators.get('rsi',0):.1f} | Signal: {signal} ({reason})")
            
            # 4. Execute/Update Trade
            # Always call update to manage positions (trailing stop, soft TP) even if signal is 0
            
            # Calculate dynamic SL/TP based on volatility (ATR) or fixed
            sl_pct = config.get('sl_pct', 0.03)
            tp_pct = config.get('tp_pct', 0.025)
            
            trader.update(
                current_price=current_price,
                signal=signal,
                symbol=TRADING_SYMBOL,
                sl=sl_pct,
                tp=tp_pct,
                prob=ml_prob,
                **trade_params
            )
            
            # Sleep until next candle (approx)
            # For 1m timeframe, maybe check every 10s
            await asyncio.sleep(10)
            
        except KeyboardInterrupt:
            logger.info("Stopping bot...")
            break
        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
            await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())
