import os
import sys
import logging
import joblib
import pandas as pd
import numpy as np
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# Add project root to path
sys.path.append(os.getcwd())

from src.data.collector import CryptoDataCollector
from src.models.features import FeatureEngineer
from src.models.predictor import PricePredictor
from src.strategies.trend_ml_strategy import TrendMLStrategy

logger = logging.getLogger(__name__)

class PortfolioManager:
    """
    Manages multi-coin strategy execution.
    1. Selects best coins based on model metrics.
    2. Fetches real-time data for selected coins.
    3. Generates signals using TrendMLStrategy (combining ML + Technicals).
    4. Ranks opportunities by confidence/probability.
    """
    
    def __init__(self, active_symbols=None, max_workers=10, proxy_url=None):
        # Default to Top 30
        if active_symbols is None:
            self.active_symbols = [
                'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'AVAXUSDT',
                'XRPUSDT', 'DOGEUSDT', 'ADAUSDT', 'TRXUSDT', 'LINKUSDT',
                'LTCUSDT', 'DOTUSDT', 'BCHUSDT', 'SHIBUSDT', 'MATICUSDT',
                'NEARUSDT', 'APTUSDT', 'FILUSDT', 'ATOMUSDT', 'ARBUSDT',
                'OPUSDT', 'ETCUSDT', 'ICPUSDT', 'RNDRUSDT', 'INJUSDT',
                'STXUSDT', 'LDOUSDT', 'VETUSDT', 'XLMUSDT', 'PEPEUSDT'
            ]
        else:
            self.active_symbols = active_symbols
            
        self.collectors = {}
        self.predictors = {}
        self.strategies = {}
        self.max_workers = max_workers
        self.proxy_url = proxy_url
        
        # Initialize collectors and predictors
        self._initialize_infrastructure()
        
    def _initialize_infrastructure(self):
        """Setup collectors, predictors, and strategies for each symbol"""
        logger.info(f"Initializing PortfolioManager for: {self.active_symbols} (Proxy: {self.proxy_url})")
        
        proxies = None
        if self.proxy_url:
            proxies = {"http": self.proxy_url, "https": self.proxy_url}
        
        for symbol in self.active_symbols:
            # 1. Setup Data Collector
            self.collectors[symbol] = CryptoDataCollector(symbol=symbol, proxies=proxies)
            
            # 2. Setup Price Predictor (handles model loading)
            self.predictors[symbol] = PricePredictor(symbol=symbol)

            # 3. Setup Strategy
            self.strategies[symbol] = TrendMLStrategy()

    def scan_leaderboard(self, limit=3):
        """
        Scan for top gainers/losers (Aggressive Mode).
        Returns list of symbols that are NOT in active_symbols.
        """
        try:
            # Use the first available collector's exchange
            if not self.collectors:
                return []
            
            # Grab any exchange instance
            first_symbol = list(self.collectors.keys())[0]
            exchange = self.collectors[first_symbol].exchange
            
            # Fetch all tickers
            tickers = exchange.fetch_tickers()
            
            # Filter for USDT Futures
            candidates = []
            for symbol, ticker in tickers.items():
                # Ensure it's a linear swap (USDT margined)
                if '/USDT:USDT' not in symbol:
                    continue
                
                # Exclude existing active symbols
                clean_sym = symbol.replace('/', '').replace(':USDT', '')
                if clean_sym in self.active_symbols:
                    continue
                
                # Filter out low volume coins to avoid scam wicks
                if ticker['quoteVolume'] < 10_000_000: # Min $10M volume
                    continue
                    
                candidates.append({
                    'symbol': clean_sym,
                    'ccxt_symbol': symbol,
                    'change': ticker['percentage'], # 24h change %
                    'volume': ticker['quoteVolume'],
                    'last': ticker['last']
                })
            
            # Sort by absolute change (Volatility)
            candidates.sort(key=lambda x: abs(x['change'] if x['change'] else 0), reverse=True)
            
            return candidates[:limit]
            
        except Exception as e:
            logger.error(f"Leaderboard scan failed: {e}")
            return []

    def analyze_technical_only(self, symbol):
        """
        Analyze a symbol using only technical indicators (for dynamic leaderboard coins).
        Creates a temporary collector and strategy.
        """
        try:
            # Create temp collector
            proxies = None
            if self.proxy_url:
                proxies = {"http": self.proxy_url, "https": self.proxy_url}
                
            collector = CryptoDataCollector(symbol=symbol, proxies=proxies)
            
            # Fetch data (enough for EMA200)
            df = collector.fetch_ohlcv(timeframe='1m', limit=300)
            
            if df is None or df.empty:
                return None
                
            # Use TrendMLStrategy but we need to trick it or use it without ML
            strategy = TrendMLStrategy()
            
            # Calculate indicators
            df = strategy.calculate_indicators(df)
            
            if len(df) < 2:
                return None
                
            row = df.iloc[-1]
            
            # Custom Aggressive Logic for Leaderboard
            # We don't use the standard get_signal because it requires ML
            # We look for "Extreme Certainty" via Technicals
            
            rsi = row['rsi']
            adx = 0 # If we had ADX
            ha_close = row['ha_close']
            ha_open = row['ha_open']
            ema_trend = row['ema_trend']
            volume = row['volume']
            vol_ma = row['vol_ma']
            
            signal = 0
            confidence = 0.0
            
            # Aggressive Long: Strong Uptrend + High Volume + RSI not completely blown
            if ha_close > ema_trend and ha_close > ha_open and volume > vol_ma * 1.5:
                if 30 < rsi < 85: # Allow higher RSI for momentum plays
                    signal = 1
                    confidence = 0.9 # Fake high confidence
            
            # Aggressive Short
            elif ha_close < ema_trend and ha_close < ha_open and volume > vol_ma * 1.5:
                if 15 < rsi < 70:
                    signal = -1
                    confidence = 0.9
                    
            if signal != 0:
                # Construct opportunity dict
                # Small position for aggressive trade (e.g. 10 USDT margin)
                margin_usdt = 10.0 
                leverage = 10
                amount_coins = (margin_usdt * leverage) / row['close']

                return {
                    "symbol": symbol,
                    "signal": "BUY" if signal == 1 else "SELL",
                    "avg_probability": confidence,
                    "strategy_result": {
                        "trade_params": {
                            "leverage": leverage,
                            "amount_coins": amount_coins,
                            "sl_price": 0, # Calculated dynamically later if needed or rely on trader defaults
                            "tp_price": 0
                        }
                    }
                }
            return None
            
        except Exception as e:
            logger.error(f"Technical analysis failed for {symbol}: {e}")
            return None

    def analyze_symbol(self, symbol):
        """
        Fetch data and generate prediction for a single symbol.
        Returns: dict with signal details or None if failed.
        """
        try:
            collector = self.collectors[symbol]
            predictor = self.predictors[symbol]
            strategy = self.strategies[symbol]
            
            # Fetch sufficient history for feature generation and indicators
            # TrendMLStrategy needs EMA200, so we need at least 200 bars. 500 is safe.
            df = collector.fetch_ohlcv(timeframe='1m', limit=500)
            
            if df is None or df.empty:
                logger.warning(f"[{symbol}] Failed to fetch live data.")
                return None
            
            # Get current price
            current_price = df.iloc[-1]['close']
                
            # Generate predictions (ML)
            preds = predictor.predict_all(df)
            
            if not preds:
                return None
            
            # Prepare extra_data for Strategy
            extra_data = {}
            if "30m" in preds:
                extra_data['ml_prediction'] = preds["30m"]
            if "10m" in preds:
                extra_data['ml_prediction_10m'] = preds["10m"]
                
            # Run Strategy Analysis (ML + Technicals)
            strat_result = strategy.analyze(df, extra_data=extra_data)
            
            result = {
                "symbol": symbol,
                "timestamp": datetime.now().isoformat(),
                "price": float(current_price),
                "predictions": {},
                "avg_probability": 0.5, # Default
                "signal": "NEUTRAL",
                "confidence": "NONE",
                "strategy_result": strat_result # Include full strategy output
            }
            
            # Populate predictions for reference
            total_prob = 0
            count = 0
            for h in [10, 30]:
                key = f"{h}m"
                if key in preds and "probability" in preds[key]:
                    prob = preds[key]["probability"]
                    result["predictions"][key] = float(prob)
                    total_prob += prob
                    count += 1
            
            if count > 0:
                result["avg_probability"] = float(total_prob / count)

            # Map Strategy Signal to PM Output
            # strat_result['signal'] is 1, -1, 0
            s_sig = strat_result.get('signal', 0)
            if s_sig == 1:
                result["signal"] = "LONG"
                result["confidence"] = "HIGH" 
            elif s_sig == -1:
                result["signal"] = "SHORT"
                result["confidence"] = "HIGH"
            else:
                result["signal"] = "NEUTRAL"
                result["confidence"] = "NONE"
                
            return result
            
        except Exception as e:
            logger.error(f"[{symbol}] Analysis failed: {e}")
            return None

    def scan_market(self):
        """
        Scan all active symbols concurrently.
        Returns sorted list of opportunities.
        """
        results = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(self.analyze_symbol, sym): sym for sym in self.active_symbols}
            
            for future in futures:
                res = future.result()
                if res and res.get("signal") in ["LONG", "SHORT"]:
                    results.append(res)
        
        # Sort by 'strength' (deviation from 0.5)
        # 0.9 -> 0.4 diff, 0.1 -> 0.4 diff
        results.sort(key=lambda x: abs(x["avg_probability"] - 0.5), reverse=True)
        
        return results

if __name__ == "__main__":
    # Test Run
    logging.basicConfig(level=logging.INFO)
    pm = PortfolioManager()
    opportunities = pm.scan_market()
    print("\n--- Market Scan Results ---")
    for opp in opportunities:
        print(f"{opp['symbol']}: {opp['signal']} ({opp['confidence']}) - Prob: {opp['avg_probability']:.4f}")
