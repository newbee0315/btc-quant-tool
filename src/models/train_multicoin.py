import sys
import os
import logging
import pandas as pd
import numpy as np
import joblib
import json
from xgboost import XGBClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
from concurrent.futures import ThreadPoolExecutor

# Add project root to path
sys.path.append(os.getcwd())

from src.models.features import FeatureEngineer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("train_multicoin.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Config
DATA_DIR = "data/raw"
MODELS_DIR = "src/models/saved_models"
METRICS_FILE = os.path.join(MODELS_DIR, "multicoin_metrics.json")
TIMEFRAME = '1m' # We will resample this if needed, but for now stick to base TF logic
HORIZONS = [10, 30] # Prediction horizons in minutes

# Ensure models dir exists
os.makedirs(MODELS_DIR, exist_ok=True)

def load_data(symbol, timeframe='1m'):
    """Load raw data for a symbol"""
    filename = f"{symbol}_{timeframe}.csv"
    filepath = os.path.join(DATA_DIR, filename)
    
    if not os.path.exists(filepath):
        logger.warning(f"File not found: {filepath}")
        return pd.DataFrame()
    
    df = pd.read_csv(filepath)
    if 'datetime' not in df.columns and 'timestamp' in df.columns:
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
    elif 'datetime' in df.columns:
        df['datetime'] = pd.to_datetime(df['datetime'])
        
    return df

def train_for_symbol(symbol):
    """Train models for a single symbol"""
    logger.info(f"[{symbol}] Starting training pipeline...")
    
    # 1. Load Data
    df = load_data(symbol, TIMEFRAME)
    if df.empty:
        logger.error(f"[{symbol}] No data found. Skipping.")
        return None
        
    # 2. Feature Engineering
    logger.info(f"[{symbol}] Generating features...")
    # Note: FeatureEngineer might need FNG data, passing None for now to keep it simple/fast
    # If FNG is critical, we should load it once globally and pass it in.
    df = FeatureEngineer.generate_features(df)
    
    # Drop NaNs
    df = df.dropna()
    
    metrics_report = {}
    
    # 3. Train for each horizon
    for horizon in HORIZONS:
        logger.info(f"[{symbol}] Training for {horizon}m horizon...")
        
        # Create Target
        # 1 if price in 'horizon' minutes > current price * (1 + threshold)
        # For simplicity in this factory phase:
        # Target = 1 if Return(t+horizon) > 0.002 (0.2%), else 0 (Classify significant pump)
        # Or just Direction: 1 if Return > 0, 0 if Return <= 0
        
        # Using simple direction for now, or the same logic as original train.py
        # Original train.py used threshold 0.001 (0.1%)
        
        future_close = df['close'].shift(-horizon)
        df[f'target_{horizon}m'] = (future_close > df['close'] * 1.001).astype(int)
        
        # Prepare Train/Test Split (Time-based split)
        # Use last 20% for testing
        features = [c for c in df.columns if c not in ['timestamp', 'datetime', 'open', 'high', 'low', 'close', 'volume'] and not c.startswith('target_')]
        
        # Remove any future leaking columns if they exist
        features = [f for f in features if 'target' not in f]
        
        data_valid = df.dropna(subset=[f'target_{horizon}m'])
        
        split_idx = int(len(data_valid) * 0.8)
        train_df = data_valid.iloc[:split_idx]
        test_df = data_valid.iloc[split_idx:]
        
        X_train = train_df[features]
        y_train = train_df[f'target_{horizon}m']
        X_test = test_df[features]
        y_test = test_df[f'target_{horizon}m']
        
        # Train XGBoost
        # Using generic params for factory mode. 
        # In future, we can load optimized params from best_params.json
        model = XGBClassifier(
            n_estimators=500,
            learning_rate=0.05,
            max_depth=6,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            n_jobs=-1,
            eval_metric='logloss'
        )
        
        model.fit(X_train, y_train)
        
        # Evaluate
        y_pred = model.predict(X_test)
        y_prob = model.predict_proba(X_test)[:, 1]
        
        acc = accuracy_score(y_test, y_pred)
        prec = precision_score(y_test, y_pred, zero_division=0)
        rec = recall_score(y_test, y_pred, zero_division=0)
        f1 = f1_score(y_test, y_pred, zero_division=0)
        auc = roc_auc_score(y_test, y_prob)
        
        logger.info(f"[{symbol} {horizon}m] Acc: {acc:.4f} | AUC: {auc:.4f} | Prec: {prec:.4f}")
        
        # Save Model
        model_filename = f"xgb_{symbol}_{horizon}m.joblib"
        joblib.dump(model, os.path.join(MODELS_DIR, model_filename))
        
        metrics_report[f"{horizon}m"] = {
            "accuracy": round(acc, 4),
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
            "auc": round(auc, 4),
            "model_path": model_filename
        }
        
    return {symbol: metrics_report}

def main():
    # Identify symbols from raw data directory
    files = [f for f in os.listdir(DATA_DIR) if f.endswith('_1m.csv')]
    symbols = [f.replace('_1m.csv', '') for f in files]
    
    logger.info(f"Found {len(symbols)} symbols to train: {symbols}")
    
    all_metrics = {}
    
    # Train sequentially or parallel (Parallel might OOM if too many threads)
    # Using sequential for safety on this machine
    for symbol in symbols:
        try:
            result = train_for_symbol(symbol)
            if result:
                all_metrics.update(result)
        except Exception as e:
            logger.error(f"Failed to train {symbol}: {e}")
            
    # Save Metrics Report
    with open(METRICS_FILE, 'w') as f:
        json.dump(all_metrics, f, indent=4)
        
    logger.info(f"Training complete. Metrics saved to {METRICS_FILE}")

if __name__ == "__main__":
    main()
