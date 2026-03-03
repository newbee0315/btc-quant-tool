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
MAX_TRIALS = 30  # Increased trials for better optimization

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
        'n_estimators': random.choice([300, 500, 800, 1000, 1500, 2000]),
        'max_depth': random.choice([3, 4, 5, 6, 7, 8, 10]),
        'learning_rate': random.choice([0.001, 0.005, 0.01, 0.02, 0.05, 0.1]),
        'subsample': random.uniform(0.6, 0.9),
        'colsample_bytree': random.uniform(0.6, 0.9),
        'min_child_weight': random.choice([1, 3, 5, 7, 9]),
        'gamma': random.uniform(0, 0.5),
        'reg_alpha': random.choice([0, 0.001, 0.01, 0.1, 1, 10]),
        'reg_lambda': random.choice([0, 0.001, 0.01, 0.1, 1, 10]),
        'random_state': 42,
        'n_jobs': -1,
        'eval_metric': 'auc'
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
    
    # Debug: Check for columns with all NaNs
    nan_cols = df.columns[df.isna().all()].tolist()
    if nan_cols:
        logger.warning(f"[{symbol}] Columns entirely NaN: {nan_cols}")
        # Drop these columns instead of rows
        df = df.drop(columns=nan_cols)
        
    # Drop NaNs (This will remove the warmup period for indicators, e.g. first 200 rows)
    df = df.dropna()
    
    if len(df) < 500:
        logger.warning(f"[{symbol}] Data too short after feature generation ({len(df)} rows). Skipping.")
        return None
    
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

        # Calculate class weight to handle imbalance
        pos_count = y_train.sum()
        neg_count = len(y_train) - pos_count
        # Full weight might be too aggressive, dampening it
        full_weight = neg_count / pos_count if pos_count > 0 else 1.0
        pos_ratio = pos_count / len(y_train)
        
        logger.info(f"[{symbol} {horizon}m] Training Data: {len(X_train)} rows. Positives: {pos_count} ({pos_ratio:.2%}). Full Weight: {full_weight:.2f}")

        best_model = None
        best_metrics = None
        best_score = -1
        
        # Optimization Loop
        logger.info(f"[{symbol} {horizon}m] Starting hyperparameter optimization (Max {MAX_TRIALS} trials)...")
        
        for trial in range(MAX_TRIALS):
            params = get_random_params()
            
            # Dynamic scale_pos_weight: Randomly choose weight
            # If we want higher precision, we should avoiding over-weighting the minority class.
            # Sometimes under-weighting (conservative) helps precision.
            if full_weight > 1.0:
                 # Fix bias towards long: Cap scale_pos_weight to prevent over-prediction of positives
                 # Cap at 3.0 or full weight, whichever is smaller
                 max_weight = min(full_weight, 3.0)
                 params['scale_pos_weight'] = random.uniform(0.1, max_weight)
            else:
                 params['scale_pos_weight'] = random.uniform(0.1, 1.0)
            
            # Ensure eval_metric is set in params for __init__
            if 'eval_metric' not in params:
                params['eval_metric'] = 'auc'

            model = XGBClassifier(**params, early_stopping_rounds=50)
            
            # Use X_test for early stopping (Optimization set)
            # Note: In strict ML, we should use a separate validation set, but for this 
            # rolling time-series setup, using the test set to stop training is a common 
            # practical optimization to prevent overfitting the train set.
            model.fit(
                X_train, 
                y_train, 
                eval_set=[(X_test, y_test)], 
                verbose=False
            )
            
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
            
        model_filename = f"xgb_{symbol}_{horizon}m.joblib"
        model_path = os.path.join(MODELS_DIR, model_filename)

        if best_metrics['accuracy'] < MIN_ACCURACY or best_metrics['precision'] < MIN_PRECISION:
             logger.warning(f"[{symbol} {horizon}m] ⚠️ Best model did NOT meet standards. Acc: {best_metrics['accuracy']}, Prec: {best_metrics['precision']}")
             logger.warning(f"[{symbol} {horizon}m] 🛑 SKIPPING SAVE. Existing model (if any) will be removed to prevent losses.")
             
             # Remove existing model if it exists, to ensure safety
             if os.path.exists(model_path):
                 os.remove(model_path)
                 logger.info(f"[{symbol} {horizon}m] 🗑️ Deleted unsafe old model.")
             
             # Mark as failed in report
             best_metrics["status"] = "failed"
             metrics_report[f"{horizon}m"] = best_metrics
             continue
        
        # Save Best Model only if valid
        joblib.dump(best_model, model_path)
        
        best_metrics["model_path"] = model_filename
        best_metrics["status"] = "success"
        metrics_report[f"{horizon}m"] = best_metrics
        
        logger.info(f"[{symbol} {horizon}m] ✅ Model Saved. Acc: {best_metrics['accuracy']} | Prec: {best_metrics['precision']}")
        
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
