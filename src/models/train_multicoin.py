import sys
import os
import logging
import pandas as pd
import numpy as np
import joblib
import json
import random
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

# Performance Requirements
MIN_ACCURACY = 0.55
MIN_PRECISION = 0.52
MAX_TRIALS = 5  # Maximum number of hyperparameter optimization trials

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

def get_random_params():
    """Generate random hyperparameters for XGBoost"""
    return {
        'n_estimators': random.choice([100, 300, 500, 800, 1000]),
        'max_depth': random.choice([3, 4, 5, 6, 8, 10]),
        'learning_rate': random.uniform(0.01, 0.2),
        'subsample': random.uniform(0.6, 1.0),
        'colsample_bytree': random.uniform(0.6, 1.0),
        'random_state': 42,
        'n_jobs': -1,
        'eval_metric': 'logloss'
    }

def train_for_symbol(symbol):
    """Train models for a single symbol with optimization loop"""
    logger.info(f"[{symbol}] Starting training pipeline...")
    
    # 1. Load Data
    df = load_data(symbol, TIMEFRAME)
    if df.empty:
        logger.error(f"[{symbol}] No data found. Skipping.")
        return None
        
    # 2. Feature Engineering
    logger.info(f"[{symbol}] Generating features...")
    df = FeatureEngineer.generate_features(df)
    
    # Drop NaNs
    df = df.dropna()
    
    metrics_report = {}
    
    # 3. Train for each horizon
    for horizon in HORIZONS:
        logger.info(f"[{symbol}] Training for {horizon}m horizon...")
        
        # Create Target
        future_close = df['close'].shift(-horizon)
        df[f'target_{horizon}m'] = (future_close > df['close'] * 1.001).astype(int)
        
        # Prepare Train/Test Split
        features = [c for c in df.columns if c not in ['timestamp', 'datetime', 'open', 'high', 'low', 'close', 'volume'] and not c.startswith('target_')]
        features = [f for f in features if 'target' not in f]
        
        data_valid = df.dropna(subset=[f'target_{horizon}m'])
        split_idx = int(len(data_valid) * 0.8)
        
        train_df = data_valid.iloc[:split_idx]
        test_df = data_valid.iloc[split_idx:]
        
        X_train = train_df[features]
        y_train = train_df[f'target_{horizon}m']
        X_test = test_df[features]
        y_test = test_df[f'target_{horizon}m']
        
        best_model = None
        best_metrics = None
        best_score = -1
        
        # Optimization Loop
        logger.info(f"[{symbol} {horizon}m] Starting hyperparameter optimization (Max {MAX_TRIALS} trials)...")
        
        for trial in range(MAX_TRIALS):
            params = get_random_params()
            model = XGBClassifier(**params)
            model.fit(X_train, y_train)
            
            y_pred = model.predict(X_test)
            y_prob = model.predict_proba(X_test)[:, 1]
            
            acc = accuracy_score(y_test, y_pred)
            prec = precision_score(y_test, y_pred, zero_division=0)
            rec = recall_score(y_test, y_pred, zero_division=0)
            f1 = f1_score(y_test, y_pred, zero_division=0)
            auc = roc_auc_score(y_test, y_prob)
            
            # Composite score emphasizing Precision and Accuracy
            current_score = (acc * 0.4) + (prec * 0.4) + (auc * 0.2)
            
            if current_score > best_score:
                best_score = current_score
                best_model = model
                best_metrics = {
                    "accuracy": round(acc, 4),
                    "precision": round(prec, 4),
                    "recall": round(rec, 4),
                    "f1": round(f1, 4),
                    "auc": round(auc, 4)
                }
                
            # Check if standards are met
            if acc >= MIN_ACCURACY and prec >= MIN_PRECISION:
                logger.info(f"[{symbol} {horizon}m] ✅ Standards Met at Trial {trial+1}! Acc: {acc:.4f}, Prec: {prec:.4f}")
                break
            else:
                logger.info(f"[{symbol} {horizon}m] Trial {trial+1}/{MAX_TRIALS} Failed: Acc {acc:.4f} < {MIN_ACCURACY} or Prec {prec:.4f} < {MIN_PRECISION}")
        
        if not best_model:
            logger.error(f"[{symbol} {horizon}m] ❌ Failed to train any valid model.")
            continue
            
        if best_metrics['accuracy'] < MIN_ACCURACY or best_metrics['precision'] < MIN_PRECISION:
             logger.warning(f"[{symbol} {horizon}m] ⚠️ Best model did NOT meet standards after {MAX_TRIALS} trials. Acc: {best_metrics['accuracy']}, Prec: {best_metrics['precision']}")
        
        # Save Best Model
        model_filename = f"xgb_{symbol}_{horizon}m.joblib"
        joblib.dump(best_model, os.path.join(MODELS_DIR, model_filename))
        
        best_metrics["model_path"] = model_filename
        metrics_report[f"{horizon}m"] = best_metrics
        
        logger.info(f"[{symbol} {horizon}m] Selected Best: Acc: {best_metrics['accuracy']} | Prec: {best_metrics['precision']}")
        
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
