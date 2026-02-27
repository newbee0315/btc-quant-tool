import pandas as pd
import numpy as np
import requests
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
            response = requests.get(url, timeout=10)
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
        Generate comprehensive technical indicators and features.
        """
        df = df.copy()
        
        # Ensure numeric types
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        # Ensure timestamp is datetime
        if 'timestamp' in df.columns:
            if 'datetime' in df.columns:
                 df['datetime'] = pd.to_datetime(df['datetime'])
            else:
                 df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
            
        # --- 1. Basic Returns & Log Returns ---
        df['log_return'] = np.log(df['close'] / df['close'].shift(1))
        df['pct_change'] = df['close'].pct_change()
        
        # --- 2. Moving Averages & Distances ---
        for window in [7, 20, 25, 99, 200]:
            df[f'ma_{window}'] = df['close'].rolling(window=window).mean()
            df[f'ma_dist_{window}'] = df['close'] / df[f'ma_{window}'] - 1
            # Exponential MA
            df[f'ema_{window}'] = df['close'].ewm(span=window, adjust=False).mean()
            df[f'ema_dist_{window}'] = df['close'] / df[f'ema_{window}'] - 1
            
        # --- 3. RSI (Relative Strength Index) ---
        def calculate_rsi(data, window=14):
            delta = data.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
            rs = gain / loss
            return 100 - (100 / (1 + rs))
            
        df['rsi_14'] = calculate_rsi(df['close'], 14)
        df['rsi_6'] = calculate_rsi(df['close'], 6)
        df['rsi_24'] = calculate_rsi(df['close'], 24)
        
        # --- 4. MACD ---
        exp1 = df['close'].ewm(span=12, adjust=False).mean()
        exp2 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = exp1 - exp2
        df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['signal']
        
        # --- 5. Bollinger Bands ---
        ma20 = df['close'].rolling(window=20).mean()
        std20 = df['close'].rolling(window=20).std()
        df['upper_band'] = ma20 + (std20 * 2)
        df['lower_band'] = ma20 - (std20 * 2)
        df['bb_width'] = (df['upper_band'] - df['lower_band']) / ma20
        df['bb_position'] = (df['close'] - df['lower_band']) / (df['upper_band'] - df['lower_band'])
        
        # --- 6. ATR (Average True Range) ---
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        
        df['atr_14'] = true_range.rolling(window=14).mean()
        
        # --- 7. Market Microstructure Features (Proxies) ---
        
        # A. Amihud Illiquidity Proxy (Abs Return / Dollar Volume)
        # Higher value = Less Liquid (Price moves more per dollar traded)
        # Avoid division by zero
        dollar_volume = df['volume'] * df['close']
        df['amihud_illiquidity'] = df['pct_change'].abs() / (dollar_volume + 1e-9)
        # Smooth it
        df['amihud_illiquidity_24h'] = df['amihud_illiquidity'].rolling(window=24).mean()
        
        # B. Parkinson Volatility (High-Low based)
        # More efficient estimator than Close-to-Close
        # Formula: sqrt(1 / (4 * ln(2)) * (ln(High/Low))^2)
        # ln(High/Low) = ln(High) - ln(Low)
        hl_ratio_log = np.log(df['high'] / df['low'])
        df['volatility_parkinson'] = np.sqrt((1.0 / (4.0 * np.log(2.0))) * (hl_ratio_log ** 2))
        df['volatility_parkinson_24h'] = df['volatility_parkinson'].rolling(window=24).mean()
        
        # C. Effective Spread Proxy (High - Low) / Close
        # A simple measure of intraday bid-ask spread + volatility
        df['effective_spread'] = (df['high'] - df['low']) / df['close']
        
        # D. Volume Volatility (Stability of Liquidity)
        df['volume_volatility'] = df['volume'].rolling(window=24).std() / (df['volume'].rolling(window=24).mean() + 1e-9)
        
        # --- 8. Existing Feature Cleanup ---
        df['atr_14'] = true_range.rolling(14).mean()
        df['atr_rel'] = df['atr_14'] / df['close']
        
        # --- 7. Keltner Channels ---
        # KC Middle = EMA 20
        # KC Upper = EMA 20 + 2*ATR
        # KC Lower = EMA 20 - 2*ATR
        df['kc_middle'] = df['ema_20']
        df['kc_upper'] = df['kc_middle'] + (2 * df['atr_14'])
        df['kc_lower'] = df['kc_middle'] - (2 * df['atr_14'])
        df['kc_position'] = (df['close'] - df['kc_lower']) / (df['kc_upper'] - df['kc_lower'])
        
        # --- 8. Stochastic Oscillator ---
        # %K = (Current Close - Lowest Low) / (Highest High - Lowest Low) * 100
        # %D = 3-day SMA of %K
        low_14 = df['low'].rolling(14).min()
        high_14 = df['high'].rolling(14).max()
        df['stoch_k'] = 100 * (df['close'] - low_14) / (high_14 - low_14)
        df['stoch_d'] = df['stoch_k'].rolling(3).mean()
        
        # --- 9. CCI (Commodity Channel Index) ---
        tp = (df['high'] + df['low'] + df['close']) / 3
        df['cci_20'] = (tp - tp.rolling(20).mean()) / (0.015 * tp.rolling(20).std())
        
        # --- 10. ROC (Rate of Change) ---
        df['roc_12'] = df['close'].pct_change(12) * 100
        
        # --- 11. Williams %R ---
        df['williams_r'] = -100 * ((high_14 - df['close']) / (high_14 - low_14))

        # --- 12. ADX (Average Directional Index) ---
        up_move = df['high'].diff()
        down_move = df['low'].diff()
        pdm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        mdm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
        pdm_s = pd.Series(pdm, index=df.index).rolling(14).mean()
        mdm_s = pd.Series(mdm, index=df.index).rolling(14).mean()
        tr_s = true_range.rolling(14).mean().replace(0, 1)
        pdi = 100 * (pdm_s / tr_s)
        mdi = 100 * (mdm_s / tr_s)
        dx = 100 * np.abs(pdi - mdi) / (pdi + mdi).replace(0, 1)
        df['adx_14'] = dx.rolling(14).mean()
        
        # --- 13. Volatility & Rolling Stats ---
        df['volatility_30'] = df['log_return'].rolling(window=30).std()
        df['volatility_100'] = df['log_return'].rolling(window=100).std()
        
        # Rolling skewness (can detect crash risk)
        df['skew_30'] = df['log_return'].rolling(window=30).skew()
        
        # Rolling min/max relative to current
        df['max_60'] = df['high'].rolling(60).max() / df['close'] - 1
        df['min_60'] = df['low'].rolling(60).min() / df['close'] - 1
        
        # --- 14. Momentum / Lagged Returns ---
        for lag in [3, 5, 10, 15, 30, 60]:
            df[f'ret_{lag}m'] = df['close'].pct_change(lag)
            
        # Lagged Volatility
        df['lag_vol_5'] = df['volatility_30'].shift(5)
            
        # --- 15. Volume Features ---
        df['volume_ma_20'] = df['volume'].rolling(window=20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma_20']
        
        # On-Balance Volume (OBV)
        df['obv'] = (np.sign(df['close'].diff()) * df['volume']).fillna(0).cumsum()
        # Normalize OBV (e.g., against its own MA)
        df['obv_ma_20'] = df['obv'].rolling(20).mean()
        # Prevent division by zero or very small numbers
        df['obv_osc'] = (df['obv'] - df['obv_ma_20']) / (df['obv_ma_20'].replace(0, 1).abs())

        # --- 16. Slope / Trend ---
        df['ma_25_slope'] = df['ma_25'].diff()
        df['ma_99_slope'] = df['ma_99'].diff()
        
        # --- 17. Fear & Greed Integration ---
        if fng_df is not None and not fng_df.empty:
            df['date'] = df['datetime'].dt.date
            fng_df['date'] = fng_df['datetime'].dt.date
            df = pd.merge(df, fng_df[['date', 'value']], on='date', how='left')
            df.rename(columns={'value': 'fng_index'}, inplace=True)
            df['fng_index'] = df['fng_index'].ffill()
            df = df.drop(columns=['date'])
        else:
            df['fng_index'] = 50

        # --- 18. Interaction Features ---
        # RSI / Volatility (Is it oversold but high volatility?)
        df['rsi_vol_ratio'] = df['rsi_14'] / (df['volatility_30'] * 1000 + 1)
        
        # --- 19. Futures Data Features ---
        # Ensure base columns exist for consistency (important for model compatibility)
        if 'funding_rate' not in df.columns:
            df['funding_rate'] = 0.0
        if 'oi' not in df.columns:
            df['oi'] = 0.0
            
        # Ensure oi_value exists (required by model)
        if 'oi_value' not in df.columns:
            # Approximate oi_value if not provided
            # OI (in coins) * Price = OI Value (in USDT)
            df['oi_value'] = df['oi'] * df['close']
            
        # Funding Rate MA
        df['funding_ma_3'] = df['funding_rate'].rolling(window=3).mean()
        # Funding Rate Trend (is it increasing?)
        df['funding_change'] = df['funding_rate'].diff()
        
        # Open Interest Change
        df['oi_pct_change'] = df['oi'].pct_change()
        df['oi_ma_20'] = df['oi'].rolling(window=20).mean()
        # OI vs Price (Divergence?)
        df['oi_price_corr'] = df['oi'].rolling(20).corr(df['close'])
        
        # --- 20. Lagged Features for Key Indicators (NEW) ---
        # Capture the rate of change of indicators
        new_features = {}
        for col in ['rsi_14', 'macd', 'volume_ratio', 'bb_position', 'atr_rel']:
            if col in df.columns:
                for lag in [1, 3, 5]:
                    new_features[f'{col}_lag_{lag}'] = df[col].shift(lag)
        
        # --- 21. Time Features (Cyclical) (NEW) ---
        # Crypto trades 24/7, so Hour and Day of Week are useful
        if 'datetime' in df.columns:
            hour = df['datetime'].dt.hour
            dayofweek = df['datetime'].dt.dayofweek
            
            # Cyclical encoding
            new_features['hour_sin'] = np.sin(2 * np.pi * hour / 24)
            new_features['hour_cos'] = np.cos(2 * np.pi * hour / 24)
            new_features['day_sin'] = np.sin(2 * np.pi * dayofweek / 7)
            new_features['day_cos'] = np.cos(2 * np.pi * dayofweek / 7)
            
        if new_features:
            new_features_df = pd.DataFrame(new_features, index=df.index)
            df = pd.concat([df, new_features_df], axis=1)
        
        # Cleanup
        df = df.replace([np.inf, -np.inf], np.nan)
        df = df.fillna(0)
        
        return df
