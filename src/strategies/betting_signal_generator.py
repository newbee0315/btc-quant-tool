import logging
import pandas as pd
from datetime import datetime
import os
import time
import joblib
import numpy as np

from src.data.collector import FuturesDataCollector
from src.models.features import FeatureEngineer
from src.notification.feishu import FeishuBot

logger = logging.getLogger(__name__)

class BettingSignalGenerator:
    def __init__(self):
        self.collectors = {}
        self.symbols = ['BTCUSDT', 'ETHUSDT']
        self.feishu_bot = None
        webhook = os.getenv("FEISHU_WEBHOOK_URL")
        if webhook:
            self.feishu_bot = FeishuBot(webhook)
        
        # Cache to prevent duplicate alerts
        self.last_alert = {} 
        
        # Load Models
        self.models = {}
        self.models_dir = "src/models/saved_models/betting"
        self._load_models()

    def _load_models(self):
        """Load trained betting models"""
        if not os.path.exists(self.models_dir):
            logger.warning(f"Models directory {self.models_dir} not found.")
            return

        for symbol in self.symbols:
            self.models[symbol] = {}
            for horizon in [10, 30]:
                model_path = os.path.join(self.models_dir, f"ensemble_{symbol}_{horizon}m.joblib")
                if os.path.exists(model_path):
                    try:
                        self.models[symbol][horizon] = joblib.load(model_path)
                        logger.info(f"Loaded betting model: {symbol} {horizon}m")
                    except Exception as e:
                        logger.error(f"Failed to load model {model_path}: {e}")
                else:
                    logger.warning(f"Model not found: {model_path}")

    def get_collector(self, symbol):
        if symbol not in self.collectors:
            self.collectors[symbol] = FuturesDataCollector(symbol=symbol)
            proxy = os.getenv("PROXY_URL")
            if proxy:
                self.collectors[symbol].set_proxy(proxy)
        return self.collectors[symbol]

    def generate_signals(self):
        signals = []
        
        for symbol in self.symbols:
            collector = self.get_collector(symbol)
            
            # Use 1m data for ML models (as trained)
            try:
                # 10m Prediction
                sig_10m = self._analyze(collector, symbol, 10)
                if sig_10m:
                    signals.append(sig_10m)
                    
                # 30m Prediction
                sig_30m = self._analyze(collector, symbol, 30)
                if sig_30m:
                    signals.append(sig_30m)
                    
            except Exception as e:
                logger.error(f"Error analyzing {symbol}: {e}")
                
        return signals

    def _analyze(self, collector, symbol, horizon):
        # Fetch 1m data (enough for features)
        # We need ~100 candles for indicators
        df = collector.fetch_ohlcv(timeframe='1m', limit=100)
        
        if df is None or df.empty or len(df) < 60:
            return None
            
        # Add features
        df = FeatureEngineer.generate_features(df)
        df = df.dropna()
        
        if df.empty:
            return None
        
        # Add EMA 50 for trend filter
        df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
        
        # Use the last COMPLETED candle to avoid repainting
        # df.iloc[-1] is the current forming candle (incomplete)
        # df.iloc[-2] is the last closed candle (stable)
        curr = df.iloc[-2]
        prev = df.iloc[-3]
        
        # Check if data is too old (allow 2 mins lag)
        now_ts = int(time.time() * 1000)
        if now_ts - curr['timestamp'] > 120000:
            logger.warning(f"Data delayed for {symbol}: {now_ts - curr['timestamp']}ms lag")
            return None
        
        # --- ML Prediction ---
        ml_prob = 0.5
        model = self.models.get(symbol, {}).get(horizon)
        
        if model:
            # Prepare features for model
            exclude_cols = ['timestamp', 'datetime', 'open', 'high', 'low', 'close', 'volume', 'target']
            # We assume df has same columns as training. 
            # Filter columns that are not in exclude list
            feature_cols = [c for c in df.columns if c not in exclude_cols]
            
            # Check if model has feature_names_in_ (sklearn/xgboost specific)
            if hasattr(model, 'feature_names_in_'):
                # Ensure we strictly use the features the model was trained on
                X_input = pd.DataFrame([curr])
                
                # Check for missing columns
                missing = set(model.feature_names_in_) - set(X_input.columns)
                if missing:
                    logger.warning(f"Missing features for model: {missing}")
                    # Option: Return None to be safe, or fill with 0? 
                    # Given this is a betting signal, we should be strict.
                    return None
                
                # Reorder and filter columns to match training data exactly
                X_input = X_input[model.feature_names_in_]
                
            else:
                # Fallback: Model doesn't store feature names (e.g. older sklearn or custom wrapper)
                # We must rely on FeatureEngineer consistency, but we can check counts.
                X_input = pd.DataFrame([curr[feature_cols]])
                
                if hasattr(model, 'n_features_in_'):
                    if X_input.shape[1] != model.n_features_in_:
                        logger.error(f"Feature count mismatch! Model expects {model.n_features_in_}, got {X_input.shape[1]}")
                        return None
            
            try:
                ml_prob = model.predict_proba(X_input)[0][1] # Prob of UP
            except Exception as e:
                logger.error(f"Prediction error: {e}")
                return None
        else:
            # If no model, we can't give a "Very Certain" signal
            return None

        # --- Signal Strength & Direction ---
        strength = 0
        direction = None
        signal_type = None
        label = f"{horizon}m"
        
        if ml_prob > 0.5:
            direction = "CALL" # 看涨
            signal_type = "UP"
            strength = ml_prob * 100
        else:
            direction = "PUT" # 看跌
            signal_type = "DOWN"
            strength = (1 - ml_prob) * 100
            
        # --- Technical Filter (Strict Mode for >60% Win Rate) ---
        # Requirement: Strength > 70 (ML High Confidence) AND Technical Confirmation
        # Payout: Win +0.8, Loss -1.0 -> Breakeven 55.5% -> Target >60%
        
        rsi = curr['rsi_14']
        macd_hist = curr['macd_hist']
        close = curr['close']
        ema_20 = curr['ema_20']
        ema_50 = curr['ema_50']
        adx = curr.get('adx_14', 0) # ADX for trend strength
        
        is_valid = False
        reasons = []
        
        # Thresholds
        ML_HIGH_CONFIDENCE = 70.0
        ML_VERY_HIGH_CONFIDENCE = 75.0
        ADX_STRONG = 25.0
        ADX_MODERATE = 20.0
        
        if direction == "CALL":
            # Trend Check: EMA20 > EMA50 (Golden Cross / Up Trend)
            trend_aligned = ema_20 > ema_50
            
            # Reversal/Breakout Logic:
            # If price forcefully breaks EMA50 (and EMA20), allow signal even if EMAs haven't crossed yet.
            # Condition: Close > EMA50 AND Close > EMA20 (already checked in tech_ok)
            # This handles V-Reversals where EMAs lag.
            is_breakout = (close > ema_50) and (close > ema_20)
            
            # Strict Tech Check: 
            # 1. RSI 50-80 (Bullish but not extreme)
            # 2. ADX > 25 (Strong Trend)
            # 3. Price > EMA20 (Above trend)
            # 4. MACD Hist > 0 (Momentum up)
            # 5. Trend Aligned (EMA20 > EMA50) OR Breakout
            tech_ok_strict = (50 < rsi < 80) and (adx > ADX_STRONG) and (close > ema_20) and (macd_hist > 0) and (trend_aligned or is_breakout)
            
            # Loose Tech Check (for Very High Confidence):
            # 1. ADX > 20 (Moderate Trend)
            # 2. Trend Aligned OR Breakout
            # 3. Price > EMA20 (Immediate Momentum) - Added to prevent catching falling knives
            tech_ok_loose = (adx > ADX_MODERATE) and (trend_aligned or is_breakout) and (close > ema_20)
            
            if strength > ML_HIGH_CONFIDENCE and tech_ok_strict:
                is_valid = True
                reasons.append(f"ML模型强确信 ({strength:.1f})")
                reasons.append("技术面完美共振 (RSI/ADX/EMA)")
            elif strength > ML_VERY_HIGH_CONFIDENCE and tech_ok_loose:
                is_valid = True
                reasons.append(f"ML模型极强确信 ({strength:.1f})")
                if is_breakout and not trend_aligned:
                    reasons.append("强势突破反转 (Breakout)")
                else:
                    reasons.append("趋势确认 (EMA/ADX)")
                
        elif direction == "PUT":
            # Trend Check: EMA20 < EMA50 (Dead Cross / Down Trend)
            trend_aligned = ema_20 < ema_50
            
            # Reversal/Breakout Logic:
            # If price forcefully breaks EMA50 (and EMA20), allow signal even if EMAs haven't crossed yet.
            # Condition: Close < EMA50 AND Close < EMA20
            is_breakout = (close < ema_50) and (close < ema_20)
            
            # Strict Tech Check:
            # 1. RSI 20-50 (Bearish but not extreme)
            # 2. ADX > 25
            # 3. Price < EMA20
            # 4. MACD Hist < 0
            # 5. Trend Aligned OR Breakout
            tech_ok_strict = (20 < rsi < 50) and (adx > ADX_STRONG) and (close < ema_20) and (macd_hist < 0) and (trend_aligned or is_breakout)
            
            # Loose Tech Check
            # Added Price < EMA20 check for symmetry and safety
            tech_ok_loose = (adx > ADX_MODERATE) and (trend_aligned or is_breakout) and (close < ema_20)
            
            if strength > ML_HIGH_CONFIDENCE and tech_ok_strict:
                is_valid = True
                reasons.append(f"ML模型强确信 ({strength:.1f})")
                reasons.append("技术面完美共振 (RSI/ADX/EMA)")
            elif strength > ML_VERY_HIGH_CONFIDENCE and tech_ok_loose:
                is_valid = True
                reasons.append(f"ML模型极强确信 ({strength:.1f})")
                if is_breakout and not trend_aligned:
                    reasons.append("强势跌破反转 (Breakout)")
                else:
                    reasons.append("趋势确认 (EMA/ADX)")

        if not is_valid:
            logger.info(f"Skipped {symbol} {label}: Strength {strength:.1f}, Trend {trend_aligned}, Tech Strict {tech_ok_strict}, Tech Loose {tech_ok_loose}")
            return None
            
        # Construct Output
        reason_str = ", ".join(reasons)
        
        # --- Alert Deduplication ---
        alert_key = f"{symbol}_{label}"
        alert_id = f"{curr['timestamp']}_{direction}" # Alert once per candle per direction
        
        should_notify = False
        if self.last_alert.get(alert_key) != alert_id:
            should_notify = True
            self.last_alert[alert_key] = alert_id
        
        sig_data = {
            "symbol": symbol,
            "label": label,
            "signal": signal_type,
            "direction": direction,
            "price": close,
            "timestamp": int(curr['timestamp']),
            "time": datetime.fromtimestamp(curr['timestamp']/1000).strftime('%H:%M'),
            "reason": reason_str,
            "strength": round(strength, 1),
            "indicators": {
                "rsi": round(rsi, 2),
                "macd": round(curr['macd'], 4),
                "ml_prob": round(ml_prob, 4),
                "adx": round(adx, 2)
            }
        }
        
        # --- Feishu Notification (Chinese & Clean Markdown) ---
        if should_notify and self.feishu_bot:
            cn_direction = "看涨 (CALL)" if direction == "CALL" else "看跌 (PUT)"
            cn_symbol = symbol.replace("USDT", "")
            
            # Title with Blue Bar style (via send_markdown)
            title = f"🎰 高置信度信号: {cn_symbol} {label} {cn_direction}"
            
            # Emoji based on direction
            icon = "🟢" if direction == "CALL" else "🔴"
            
            # Markdown Body (No raw ** chars, use Markdown syntax supported by Feishu Interactive Cards)
            # Feishu Markdown supports **bold**, but we want to mimic the monitor report style which is clean.
            # Monitor Report uses **Value** for bolding values.
            
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            msg = (
                f"{icon} **方向**: {cn_direction}\n"
                f"💪 **信号强度**: {strength:.1f}/100\n"
                f"💰 **当前价格**: {close:.2f}\n"
                f"🧠 **推荐理由**: {reason_str}\n"
                f"📊 **技术指标**: RSI {round(rsi, 1)} | ADX {round(adx, 1)}\n"
                f"🎲 **赔率规则**: 赢+80% / 输-100% (目标胜率>60%)\n"
                f"⏰ **时间**: {now_str}"
            )
            
            try:
                # Use send_markdown to support the formatting and blue header
                self.feishu_bot.send_markdown(msg, title)
                logger.info(f"Sent Feishu alert for {symbol} {label}")
            except Exception as e:
                logger.error(f"Failed to send Feishu alert: {e}")
                
        return sig_data
