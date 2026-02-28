import sys
import os
import logging
import pandas as pd
import numpy as np
import joblib
import json
import random
from xgboost import XGBClassifier
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit

# Add project root to path
sys.path.append(os.getcwd())

from src.data.collector import FuturesDataCollector
from src.models.features import FeatureEngineer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Config
MODELS_DIR = "src/models/saved_models/betting"
METRICS_FILE = os.path.join(MODELS_DIR, "betting_metrics.json")
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
HORIZONS = [10, 30] # Prediction horizons in minutes
DATA_LIMIT = 15000  # Number of 1m candles to fetch (~10 days)

# Betting Thresholds
CONFIDENCE_THRESHOLD = 0.65  # We only bet if prob > 0.65

os.makedirs(MODELS_DIR, exist_ok=True)

def fetch_data(symbol):
    """Fetch recent 1m data using Collector with pagination"""
    logger.info(f"[{symbol}] Fetching {DATA_LIMIT} 1m candles...")
    collector = FuturesDataCollector(symbol=symbol)
    # Use proxy if available (check env)
    proxy = os.getenv("PROXY_URL")
    if proxy:
        collector.set_proxy(proxy)
        
    all_data = []
    # Fetch in chunks of 1000
    chunk_size = 1000
    total_fetched = 0
    
    # Calculate start time: now - limit * 1m (in ms)
    end_time = int(pd.Timestamp.now().timestamp() * 1000)
    start_time = end_time - (DATA_LIMIT * 60 * 1000)
    
    current_start = start_time
    
    while total_fetched < DATA_LIMIT:
        try:
            # We use a slightly modified call to collector to respect limits
            # Or use ccxt directly if collector exposes it, but collector wraps requests.
            # Let's use collector.fetch_ohlcv but we need to pass start_time and limit=1000
            
            # Since collector.fetch_ohlcv takes 'since', we can use that.
            # But we need to make sure we don't get duplicates or gaps.
            
            # Actually, better to use the underlying session or just call repeatedly with 'endTime' moving backwards?
            # Or 'startTime' moving forwards.
            
            # Let's try moving forward from start_time
            df_chunk = collector.fetch_ohlcv(timeframe='1m', limit=chunk_size, since=current_start)
            
            if df_chunk is None or df_chunk.empty:
                logger.warning(f"[{symbol}] Empty chunk received at {current_start}")
                break
                
            all_data.append(df_chunk)
            fetched_count = len(df_chunk)
            total_fetched += fetched_count
            
            logger.info(f"[{symbol}] Fetched {fetched_count} candles. Total: {total_fetched}/{DATA_LIMIT}")
            
            if fetched_count < chunk_size:
                # No more data available
                break
                
            # Update current_start to the timestamp of the last candle + 1m
            last_timestamp = df_chunk['timestamp'].iloc[-1]
            current_start = last_timestamp + 60000
            
            # Safety break if we overshoot
            if current_start > end_time:
                break
                
        except Exception as e:
            logger.error(f"Error fetching chunk: {e}")
            break
            
    if not all_data:
        return pd.DataFrame()
        
    df = pd.concat(all_data).drop_duplicates(subset=['timestamp']).sort_values('timestamp')
    
    # Ensure datetime
    if 'datetime' not in df.columns and 'timestamp' in df.columns:
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
    
    return df.iloc[-DATA_LIMIT:] # Return exactly the limit requested


def train_betting_model(symbol):
    logger.info(f"[{symbol}] Starting betting model training...")
    
    # 1. Fetch Data
    df = fetch_data(symbol)
    if df.empty:
        return None
        
    # 2. Feature Engineering
    logger.info(f"[{symbol}] Generating features...")
    df = FeatureEngineer.generate_features(df)
    df = df.dropna()
    
    metrics_report = {}
    
    # 3. Train for each horizon
    for horizon in HORIZONS:
        logger.info(f"[{symbol} {horizon}m] Training Ensemble Model...")
        
        # Create Target: 1 if future close > current close (UP), 0 otherwise (DOWN)
        # For betting, we just need direction. 
        # Optional: Add small buffer for fees? 
        # Let's keep it simple direction first, but enforce high probability.
        future_close = df['close'].shift(-horizon)
        
        # Target: 1 (UP), 0 (DOWN)
        # We drop the last 'horizon' rows where target is NaN
        df[f'target'] = (future_close > df['close']).astype(int)
        
        # Features to use
        exclude_cols = ['timestamp', 'datetime', 'open', 'high', 'low', 'close', 'volume', 'target']
        feature_cols = [c for c in df.columns if c not in exclude_cols]
        
        data_valid = df.dropna(subset=['target'])
        
        # Time Series Split (Train on past, Test on recent)
        split_idx = int(len(data_valid) * 0.85) # Last 15% for testing
        
        X_train = data_valid[feature_cols].iloc[:split_idx]
        y_train = data_valid['target'].iloc[:split_idx]
        X_test = data_valid[feature_cols].iloc[split_idx:]
        y_test = data_valid['target'].iloc[split_idx:]
        
        # --- Model Definition ---
        # 1. XGBoost (Gradient Boosting)
        xgb = XGBClassifier(
            n_estimators=500,
            max_depth=5,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            n_jobs=-1,
            eval_metric='logloss'
        )
        
        # 2. Random Forest (Bagging)
        rf = RandomForestClassifier(
            n_estimators=200,
            max_depth=8,
            min_samples_leaf=4,
            random_state=42,
            n_jobs=-1
        )
        
        # Ensemble: Soft Voting
        ensemble = VotingClassifier(
            estimators=[('xgb', xgb), ('rf', rf)],
            voting='soft'
        )
        
        # Train
        ensemble.fit(X_train, y_train)
        
        # Evaluate
        y_pred = ensemble.predict(X_test)
        y_prob = ensemble.predict_proba(X_test)[:, 1] # Prob of Class 1 (UP)
        
        # Custom Evaluation: Precision at High Confidence
        # We only care about signals where prob > CONFIDENCE_THRESHOLD (for UP) or prob < (1-CONFIDENCE_THRESHOLD) (for DOWN)
        
        high_conf_indices = np.where((y_prob > CONFIDENCE_THRESHOLD) | (y_prob < (1 - CONFIDENCE_THRESHOLD)))[0]
        
        if len(high_conf_indices) > 0:
            y_test_hc = y_test.iloc[high_conf_indices]
            y_pred_hc = (y_prob[high_conf_indices] > 0.5).astype(int)
            
            hc_acc = accuracy_score(y_test_hc, y_pred_hc)
            hc_prec = precision_score(y_test_hc, y_pred_hc, zero_division=0) # Precision for UP signals
            
            # Check DOWN signals precision separately if needed, but accuracy covers both correct directions
            logger.info(f"[{symbol} {horizon}m] High Confidence ({CONFIDENCE_THRESHOLD}) Stats: Signals: {len(high_conf_indices)}, Accuracy: {hc_acc:.4f}")
        else:
            logger.warning(f"[{symbol} {horizon}m] No signals generated at confidence {CONFIDENCE_THRESHOLD}")
            hc_acc = 0
            
        # Standard Metrics
        acc = accuracy_score(y_test, y_pred)
        auc = roc_auc_score(y_test, y_prob)
        
        logger.info(f"[{symbol} {horizon}m] Overall Acc: {acc:.4f}, AUC: {auc:.4f}")
        
        # Save Model
        model_filename = f"ensemble_{symbol}_{horizon}m.joblib"
        joblib.dump(ensemble, os.path.join(MODELS_DIR, model_filename))
        
        metrics_report[f"{horizon}m"] = {
            "accuracy": round(acc, 4),
            "auc": round(auc, 4),
            "hc_accuracy": round(hc_acc, 4),
            "signals_count": len(high_conf_indices),
            "model_path": model_filename,
            "threshold": CONFIDENCE_THRESHOLD
        }
        
    return {symbol: metrics_report}

def main():
    all_metrics = {}
    for symbol in SYMBOLS:
        try:
            res = train_betting_model(symbol)
            if res:
                all_metrics.update(res)
        except Exception as e:
            logger.error(f"Failed to train {symbol}: {e}")
            
    with open(METRICS_FILE, 'w') as f:
        json.dump(all_metrics, f, indent=4)
        
    logger.info("Betting Model Training Complete.")

if __name__ == "__main__":
    main()
