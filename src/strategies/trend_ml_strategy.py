import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, Any
from .base_strategy import BaseStrategy

class TrendMLStrategy(BaseStrategy):
    """
    A hybrid strategy combining Technical Analysis (Trend Following) with Machine Learning.
    Inspired by popular open-source crypto bots (e.g., Binance-Futures-Trading-Bot).
    
    Logic:
    1. Trend Filter: EMA 200. Long if Price > EMA200, Short if Price < EMA200.
    2. Momentum Filter: RSI (14). Long if RSI < 70, Short if RSI > 30.
    3. ML Confirmation: Only enter if ML Model predicts high probability (> threshold).
    """
    
    def __init__(self, ema_period: int = 200, rsi_period: int = 14, ml_threshold: float = 0.75, atr_period: int = 14):
        super().__init__("TrendMLStrategy")
        self.ema_period = ema_period
        self.rsi_period = rsi_period
        self.ml_threshold = ml_threshold
        self.atr_period = atr_period
        self.logs = []  # Buffer to store strategy execution logs

    def log_execution(self, timestamp, close_price, ema_trend, rsi, ml_prob, signal, reasons, sl=0, tp=0, macd=0, macd_signal=0, macd_hist=0):
        """Buffer execution log"""
        log_entry = {
            "timestamp": timestamp,
            "close": round(close_price, 2),
            "ema": round(ema_trend, 2),
            "rsi": round(rsi, 2),
            "ml_prob": round(ml_prob, 3),
            "signal": signal,
            "reasons": reasons,
            "sl": round(sl, 2),
            "tp": round(tp, 2),
            "macd": round(macd, 2),
            "macd_signal": round(macd_signal, 2),
            "macd_hist": round(macd_hist, 2)
        }
        self.logs.insert(0, log_entry)
        if len(self.logs) > 50:  # Keep last 50 entries
            self.logs.pop()

    def get_logs(self):
        return self.logs

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        # Calculate Heikin Ashi Candles
        # HA_Close = (Open + High + Low + Close) / 4
        # HA_Open = (Previous HA_Open + Previous HA_Close) / 2
        
        df['ha_close'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4
        
        # Initialize ha_open with standard open
        ha_open = [df['open'].iloc[0]]
        for i in range(1, len(df)):
            ha_open.append((ha_open[-1] + df['ha_close'].iloc[i-1]) / 2)
        df['ha_open'] = ha_open
        
        df['ha_high'] = df[['high', 'ha_open', 'ha_close']].max(axis=1)
        df['ha_low'] = df[['low', 'ha_open', 'ha_close']].min(axis=1)
        
        # Calculate EMA 200 (Trend)
        df['ema_trend'] = df['close'].ewm(span=self.ema_period, adjust=False).mean()
        
        # Calculate EMA 50 (Fast Trend for confirmation)
        df['ema_fast'] = df['close'].ewm(span=50, adjust=False).mean()
        
        # Calculate RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # Calculate MACD
        exp12 = df['close'].ewm(span=12, adjust=False).mean()
        exp26 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = exp12 - exp26
        df['signal_line'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['histogram'] = df['macd'] - df['signal_line']
        
        # Calculate ATR
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df['atr'] = true_range.rolling(self.atr_period).mean()
        
        # Calculate Volume MA (20)
        df['vol_ma'] = df['volume'].rolling(window=20).mean()
        
        # Calculate Volatility Metrics for Multi-Mode
        df['returns'] = df['close'].pct_change()
        df['volatility'] = df['returns'].rolling(window=20).std()
        df['atr_ma'] = df['atr'].rolling(window=50).mean()
        
        return df

    def get_signal(self, row, prev_row, extra_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Generate signal from a single row of data (with indicators pre-calculated).
        Requires prev_row for trend change detection (e.g. MACD histogram slope).
        """
        close_price = row['close']
        ha_close = row['ha_close']
        ha_open = row['ha_open']
        ema_trend = row['ema_trend']
        ema_fast = row.get('ema_fast', 0)
        rsi = row['rsi']
        atr = row.get('atr', 0)
        atr_ma = row.get('atr_ma', atr)
        volatility = row.get('volatility', 0)
        
        macd = row.get('macd', 0)
        macd_signal = row.get('signal_line', 0)
        macd_hist = row['histogram']
        prev_macd_hist = prev_row['histogram']
        volume = row['volume']
        vol_ma = row.get('vol_ma', 0)
        
        # Determine Market Mode
        market_mode = "normal"
        if atr < (atr_ma * 0.7) and volatility < 0.008:
            market_mode = "low"
        elif atr > (atr_ma * 1.3) or volatility > 0.015:
            market_mode = "high"
            
        # 2. Get ML Prediction (Multi-Horizon Consensus)
        ml_prob = 0.5
        ml_prob_10m = 0.5
        
        if extra_data:
            # 30m Prediction (Primary)
            if 'ml_prediction' in extra_data:
                pred = extra_data['ml_prediction']
                if isinstance(pred, dict):
                    ml_prob = pred.get('probability', 0.5)
                else:
                    ml_prob = float(pred)
            
            # 10m Prediction (Secondary/Confirmation)
            if 'ml_prediction_10m' in extra_data:
                pred10 = extra_data['ml_prediction_10m']
                if isinstance(pred10, dict):
                    ml_prob_10m = pred10.get('probability', 0.5)
                else:
                    ml_prob_10m = float(pred10)

        # 3. Generate Signal
        signal = 0
        reason = []
        
        # Trend & Volume Strength
        is_strong_uptrend = ema_fast > ema_trend
        is_strong_downtrend = ema_fast < ema_trend
        is_volume_support = volume > vol_ma
        
        # Heikin Ashi Trend
        is_ha_bullish = ha_close > ha_open
        is_ha_bearish = ha_close < ha_open
        
        # ML Consensus (Adaptive Threshold)
        # Optimized: Lower threshold to 0.75 base to catch more moves
        effective_threshold = 0.75 
        
        if market_mode == 'low': effective_threshold = 0.8
        if market_mode == 'high': effective_threshold = 0.85
        
        is_ml_bullish = ml_prob >= effective_threshold
        is_ml_bearish = ml_prob <= (1 - effective_threshold)
        
        # Secondary confirmation (looser threshold, e.g. > 0.6 for bull, < 0.4 for bear)
        is_ml10_bullish = ml_prob_10m > 0.6
        is_ml10_bearish = ml_prob_10m < 0.4
        
        # Long Logic
        # Use HA Close for smoother trend check
        is_uptrend = ha_close > ema_trend 
        is_rsi_safe_long = rsi < 70
        is_macd_bullish = macd_hist > 0 and macd_hist > prev_macd_hist
        
        if is_uptrend and is_ha_bullish and is_rsi_safe_long and is_macd_bullish and is_ml_bullish:
            signal = 1
            reason.append(f"HA价格>EMA200")
            reason.append(f"HA阳线")
            reason.append(f"RSI({rsi:.1f})<70")
            reason.append(f"MACD金叉增强")
            reason.append(f"ML30m({ml_prob:.2f})>=Threshold")
            if is_ml10_bullish:
                reason.append(f"ML10m({ml_prob_10m:.2f})确认")
        
        # Short Logic
        is_downtrend = ha_close < ema_trend
        is_rsi_safe_short = rsi > 30
        is_macd_bearish = macd_hist < 0 and macd_hist < prev_macd_hist
        
        if is_downtrend and is_ha_bearish and is_rsi_safe_short and is_macd_bearish and is_ml_bearish:
            signal = -1
            reason.append(f"HA价格<EMA200")
            reason.append(f"HA阴线")
            reason.append(f"RSI({rsi:.1f})>30")
            reason.append(f"MACD死叉增强")
            reason.append(f"ML30m({ml_prob:.2f})<=Threshold")
            if is_ml10_bearish:
                reason.append(f"ML10m({ml_prob_10m:.2f})确认")

        # -----------------------------------------------------------
        # High Frequency Scalping Mode (Added to increase frequency)
        # -----------------------------------------------------------
        if signal == 0:
            # Scalp Long
            # 1. Trend: HA > EMA50 (Shorter term trend)
            # 2. ML: 10m Probability > 0.65 (Stronger short-term confidence)
            # 3. RSI: Not overbought (< 75)
            # 4. Volume: Above average (Confirmation)
            is_scalp_trend_up = ha_close > ema_fast
            is_ml10_strong_bull = ml_prob_10m >= 0.65
            is_rsi_scalp_long = rsi < 75
            
            if is_scalp_trend_up and is_ml10_strong_bull and is_rsi_scalp_long and is_volume_support:
                signal = 1
                reason.append(f"[Scalp]HA>EMA50")
                reason.append(f"ML10m({ml_prob_10m:.2f})>=0.65")
                reason.append(f"Vol>MA")
                reason.append(f"RSI({rsi:.1f})")

            # Scalp Short
            # 1. Trend: HA < EMA50
            # 2. ML: 10m Probability < 0.35
            # 3. RSI: Not oversold (> 25)
            # 4. Volume: Above average
            is_scalp_trend_down = ha_close < ema_fast
            is_ml10_strong_bear = ml_prob_10m <= 0.35
            is_rsi_scalp_short = rsi > 25
            
            if is_scalp_trend_down and is_ml10_strong_bear and is_rsi_scalp_short and is_volume_support:
                signal = -1
                reason.append(f"[Scalp]HA<EMA50")
                reason.append(f"ML10m({ml_prob_10m:.2f})<=0.35")
                reason.append(f"Vol>MA")
                reason.append(f"RSI({rsi:.1f})")
        
        # If no signal, add reasons for why (for debugging/transparency)
        if signal == 0:
            if not is_ml_bullish and not is_ml_bearish:
                reason.append(f"ML置信度不足({ml_prob:.2f})")
            elif is_ml_bullish and not is_uptrend:
                reason.append(f"ML看多但趋势不符(HA<EMA)")
            elif is_ml_bearish and not is_downtrend:
                reason.append(f"ML看空但趋势不符(HA>EMA)")
            elif is_ml_bullish and not is_macd_bullish:
                reason.append(f"ML看多但MACD未确认")
            elif is_ml_bearish and not is_macd_bearish:
                reason.append(f"ML看空但MACD未确认")
            else:
                reason.append("观望中")


        # 4. Multi-Mode Risk Management
        sl_price = 0.0
        tp_price = 0.0
        suggested_leverage = 1.0
        position_size = 0.0
        
        if signal != 0 and atr > 0:
            total_capital = extra_data.get('total_capital', 10.0) if extra_data else 10.0
            
            # Default Params (Normal Mode)
            lev_range = [8, 15] # Optimized: Increased upper range
            pos_pct_range = [0.3, 0.6]
            sl_mode = "atr"
            sl_mult = 2.0 # Optimized: Widened from 1.5
            tp_mult = 2.5
            
            if market_mode == 'low':
                lev_range = [5, 8] # Optimized: Increased from 3-5
                pos_pct_range = [0.2, 0.3]
                sl_mode = "fixed"
                sl_fixed_pct = 0.02 # Optimized: Widened
                tp_fixed_pct = 0.015
                
            elif market_mode == 'high':
                lev_range = [15, 30] # Optimized: Increased max to 30x
                pos_pct_range = [0.7, 0.9]
                sl_mode = "atr"
                sl_mult = 1.5 # Optimized: Widened from 1.0
                tp_mult = 5.0 
                
            # Calculate Leverage (Base + Boosters)
            base_leverage = lev_range[0]
            extra_leverage = 0
            
            # 1. Trend Booster
            if signal == 1 and is_strong_uptrend: extra_leverage += 3
            elif signal == -1 and is_strong_downtrend: extra_leverage += 3
            
            # 2. Volume Booster
            if is_volume_support: extra_leverage += 2
            
            # 3. High Confidence Booster
            if ml_prob > 0.85: 
                base_leverage = int(base_leverage * 1.5) # 50% boost for high confidence
                extra_leverage += 5
            
            suggested_leverage = min(lev_range[1], base_leverage + extra_leverage)
            
            # Adaptive Stop Loss (Widen for high confidence)
            if ml_prob > 0.8:
                sl_mult += 0.5
            
            # Calculate Position Size (Dynamic based on ML confidence)
            # Higher confidence -> Higher end of pos_pct_range
            confidence_score = (ml_prob - 0.5) * 2 # 0 to 1
            pos_pct = pos_pct_range[0] + (pos_pct_range[1] - pos_pct_range[0]) * confidence_score
            pos_pct = min(pos_pct_range[1], max(pos_pct_range[0], pos_pct))
            
            margin_amount = total_capital * pos_pct
            position_value = margin_amount * suggested_leverage
            position_size = position_value / close_price
            
            # Calculate SL/TP
            sl_dist = 0
            tp_dist = 0
            
            if sl_mode == 'fixed':
                sl_dist = close_price * sl_fixed_pct
                tp_dist = close_price * tp_fixed_pct
            else:
                sl_dist = atr * sl_mult
                tp_dist = atr * tp_mult
                # Min SL check for BTC
                min_sl_pct = 0.015
                if (sl_dist / close_price) < min_sl_pct:
                     sl_dist = close_price * min_sl_pct
                     tp_dist = max(tp_dist, sl_dist * 1.5)

            if signal == 1:
                sl_price = close_price - sl_dist
                tp_price = close_price + tp_dist
            else:
                sl_price = close_price + sl_dist
                tp_price = close_price - tp_dist
                
            reason.append(f"模式:{market_mode}")
            reason.append(f"仓位:{int(pos_pct*100)}%")
            reason.append(f"杠杆:{suggested_leverage}x")

        # Log execution
        self.log_execution(
            timestamp=datetime.now().isoformat(),
            close_price=close_price,
            ema_trend=ema_trend,
            rsi=rsi,
            ml_prob=ml_prob,
            signal=signal,
            reasons=reason,
            sl=sl_price,
            tp=tp_price,
            macd=macd,
            macd_signal=macd_signal,
            macd_hist=macd_hist
        )

        return {
            "signal": signal,
            "reason": ", ".join(reason) if reason else "No signal",
            "indicators": {
                "ema": ema_trend,
                "rsi": rsi,
                "atr": atr,
                "ml_prob": ml_prob
            },
            "trade_params": {
                "sl_price": sl_price,
                "tp_price": tp_price,
                "leverage": suggested_leverage,
                "position_size": position_size
            }
        }

    def analyze(self, df: pd.DataFrame, extra_data: Dict[str, Any] = None) -> Dict[str, Any]:
        if df.empty:
            return {"signal": 0, "reason": "No data"}
            
        # 1. Calculate Indicators
        df = self.calculate_indicators(df)
        
        # 2. Get Signal from last row
        if len(df) < 2:
             return {"signal": 0, "reason": "Not enough data"}
             
        return self.get_signal(df.iloc[-1], df.iloc[-2], extra_data)
