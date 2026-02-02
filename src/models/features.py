import pandas as pd
import numpy as np
import requests
import os
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class FeatureEngineer:
    @staticmethod
    def fetch_fear_and_greed(limit=0):
        """
        Fetch Fear and Greed Index history.
        Limit 0 means all data.
        """
        url = f"https://api.alternative.me/fng/?limit={limit}&format=json"
        try:
            response = requests.get(url)
            data = response.json()
            if 'data' in data:
                fng_data = data['data']
                df = pd.DataFrame(fng_data)
                df['timestamp'] = pd.to_numeric(df['timestamp'])
                df['value'] = pd.to_numeric(df['value'])
                # Convert timestamp to datetime (it's in seconds)
                df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
                # Sort by date
                df = df.sort_values('datetime')
                return df[['datetime', 'value']]
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"Error fetching Fear & Greed: {e}")
            return pd.DataFrame()

    @staticmethod
    def generate_features(df: pd.DataFrame, fng_df: pd.DataFrame = None) -> pd.DataFrame:
        """
        Generate technical indicators and features for the given DataFrame.
        Expects columns: ['open', 'high', 'low', 'close', 'volume', 'timestamp']
        """
        df = df.copy()
        
        # Ensure numeric types
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        # Ensure timestamp is datetime for merging
        if 'timestamp' in df.columns:
             # If datetime column exists but might be string
            if 'datetime' in df.columns:
                 df['datetime'] = pd.to_datetime(df['datetime'])
            else:
                 df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
            
        # 1. Basic Returns
        df['log_return'] = np.log(df['close'] / df['close'].shift(1))
        
        # 2. Moving Averages
        for window in [7, 25, 99]:
            df[f'ma_{window}'] = df['close'].rolling(window=window).mean()
            df[f'ma_dist_{window}'] = df['close'] / df[f'ma_{window}'] - 1
            
        # 3. RSI (Relative Strength Index)
        def calculate_rsi(data, window=14):
            delta = data.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
            rs = gain / loss
            return 100 - (100 / (1 + rs))
            
        df['rsi_14'] = calculate_rsi(df['close'], 14)
        df['rsi_6'] = calculate_rsi(df['close'], 6)
        
        # 4. MACD
        exp1 = df['close'].ewm(span=12, adjust=False).mean()
        exp2 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = exp1 - exp2
        df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['signal']
        
        # 5. Bollinger Bands
        ma20 = df['close'].rolling(window=20).mean()
        std20 = df['close'].rolling(window=20).std()
        df['upper_band'] = ma20 + (std20 * 2)
        df['lower_band'] = ma20 - (std20 * 2)
        df['bb_width'] = (df['upper_band'] - df['lower_band']) / ma20
        df['bb_position'] = (df['close'] - df['lower_band']) / (df['upper_band'] - df['lower_band'])
        
        # 6. ATR (Average True Range)
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        df['atr_14'] = true_range.rolling(14).mean()
        df['atr_rel'] = df['atr_14'] / df['close']
        
        # CCI (Commodity Channel Index)
        tp = (df['high'] + df['low'] + df['close']) / 3
        df['cci_20'] = (tp - tp.rolling(20).mean()) / (0.015 * tp.rolling(20).std())
        
        # ROC (Rate of Change)
        df['roc_12'] = df['close'].pct_change(12) * 100
        
        # Williams %R
        highest_high = df['high'].rolling(14).max()
        lowest_low = df['low'].rolling(14).min()
        df['williams_r'] = -100 * ((highest_high - df['close']) / (highest_high - lowest_low))

        # ADX (Average Directional Index) - simplified
        # Directional Movement
        up_move = df['high'].diff()
        down_move = df['low'].diff()
        
        pdm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        mdm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
        
        pdm_s = pd.Series(pdm, index=df.index).rolling(14).mean()
        mdm_s = pd.Series(mdm, index=df.index).rolling(14).mean()
        
        # Avoid division by zero
        tr_s = true_range.rolling(14).mean().replace(0, 1)
        
        pdi = 100 * (pdm_s / tr_s)
        mdi = 100 * (mdm_s / tr_s)
        
        dx = 100 * np.abs(pdi - mdi) / (pdi + mdi).replace(0, 1)
        df['adx_14'] = dx.rolling(14).mean()
        
        # 7. Volatility
        df['volatility_30'] = df['log_return'].rolling(window=30).std()
        
        # 8. Momentum / Lagged Returns
        for lag in [3, 5, 10, 15, 30, 60]:
            df[f'ret_{lag}m'] = df['close'].pct_change(lag)
            
        # Lagged Volatility
        df['lag_vol_5'] = df['volatility_30'].shift(5)
            
        # 9. Volume Features
        df['volume_ma_20'] = df['volume'].rolling(window=20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma_20']

        # 10. Slope (Trend Angle) - simple linear regression slope over 10 periods
        def calculate_slope(series, window=10):
            # Optimized slope calculation using numpy
            x = np.arange(window)
            slopes = [np.nan] * (window - 1)
            for i in range(window, len(series) + 1):
                y = series[i-window:i]
                # If y contains NaN, slope is NaN
                if np.isnan(y).any():
                    slopes.append(np.nan)
                    continue
                # Simple linear regression slope
                # slope = cov(x, y) / var(x)
                slope = np.polyfit(x, y, 1)[0]
                slopes.append(slope)
            return np.array(slopes)
            
        # Using rolling correlation as a faster proxy for slope direction
        # Or just change in MA
        df['ma_25_slope'] = df['ma_25'].diff()
        
        # 11. Fear & Greed Integration
        if fng_df is not None and not fng_df.empty:
            # Merge on date. F&G is daily.
            # Create a date column for merging
            df['date'] = df['datetime'].dt.date
            fng_df['date'] = fng_df['datetime'].dt.date
            
            # Merge left
            df = pd.merge(df, fng_df[['date', 'value']], on='date', how='left')
            df.rename(columns={'value': 'fng_index'}, inplace=True)
            
            # Forward fill F&G data for missing days
            df['fng_index'] = df['fng_index'].ffill()
            
            # Drop temporary date column
            df = df.drop(columns=['date'])
        else:
            # If no F&G provided, use 50 (Neutral) as default
            df['fng_index'] = 50

        # Handle infinite values and NaNs
        df = df.replace([np.inf, -np.inf], np.nan)
        df = df.fillna(0)
        
        return df
