
import pandas as pd
import numpy as np
from enum import Enum

class MarketRegime(Enum):
    TRENDING = "trending"
    RANGING = "ranging"
    VOLATILE = "volatile"
    UNCERTAIN = "uncertain"

class MarketRegimeClassifier:
    """
    Classifies market regime based on technical indicators.
    Uses ADX, ATR, and EMA Slopes.
    """
    
    def __init__(self, adx_threshold=25, atr_percentile=70, slope_threshold=0.0005):
        self.adx_threshold = adx_threshold
        self.atr_percentile = atr_percentile
        self.slope_threshold = slope_threshold
        
    def classify(self, df: pd.DataFrame) -> str:
        """
        Classify the current market regime.
        Requires DataFrame with 'adx', 'atr', 'close', 'ema_trend' columns.
        Returns: MarketRegime value as string.
        """
        if df.empty or len(df) < 50:
            return MarketRegime.UNCERTAIN.value
            
        row = df.iloc[-1]
        
        # Ensure required columns exist
        required_cols = ['adx', 'atr', 'close']
        for col in required_cols:
            if col not in df.columns:
                return MarketRegime.UNCERTAIN.value
                
        # 1. Trend Strength (ADX)
        adx = row.get('adx', 0)
        is_trending = adx > self.adx_threshold
        
        # 2. Volatility (ATR)
        # Compare current ATR to recent history (last 50 periods)
        recent_atr = df['atr'].tail(50)
        current_atr = row['atr']
        
        # Calculate percentile of current ATR
        # If current ATR is in top 30% of recent history -> High Volatility
        atr_rank = recent_atr.rank(pct=True).iloc[-1]
        is_high_volatility = atr_rank > 0.80 # Top 20%
        is_low_volatility = atr_rank < 0.30 # Bottom 30%
        
        # 3. Directional Bias (EMA Slope)
        # Calculate slope of EMA (if available) or Close
        slope = 0
        if 'ema_trend' in df.columns:
            # Simple slope: (Current - Previous) / Previous
            ema = df['ema_trend']
            slope = (ema.iloc[-1] - ema.iloc[-5]) / ema.iloc[-5] # 5-period slope
        
        # Classification Logic
        if is_high_volatility:
            # High Volatility often means turning points or strong breakout
            # If ADX is also high, it's a Volatile Trend (Crash or Pump)
            return MarketRegime.VOLATILE.value
            
        if is_trending:
            return MarketRegime.TRENDING.value
            
        if is_low_volatility and not is_trending:
            return MarketRegime.RANGING.value
            
        return MarketRegime.UNCERTAIN.value

    @staticmethod
    def get_regime_details(df: pd.DataFrame):
        """Returns detailed metrics for debugging"""
        classifier = MarketRegimeClassifier()
        regime = classifier.classify(df)
        
        if df.empty: return {}
        
        row = df.iloc[-1]
        recent_atr = df['atr'].tail(50) if 'atr' in df.columns else pd.Series([0])
        atr_rank = recent_atr.rank(pct=True).iloc[-1] if not recent_atr.empty else 0
        
        return {
            "regime": regime,
            "adx": row.get('adx', 0),
            "atr_rank": atr_rank,
            "volatility_score": atr_rank, # 0-1
            "trend_score": row.get('adx', 0) / 100.0
        }
