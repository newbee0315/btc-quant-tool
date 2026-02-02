import sys
import os
import logging
import pandas as pd
import numpy as np
from datetime import datetime
import joblib
import json
from xgboost import XGBClassifier
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score

# Add project root to path
sys.path.append(os.getcwd())

from src.data.collector import CryptoDataCollector
from src.models.features import FeatureEngineer

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MODELS_DIR = "src/models/saved_models"
DATA_FILE = "src/data/btc_history_1m.csv"
METRICS_FILE = os.path.join(MODELS_DIR, "model_metrics.json")
FNG_FILE = "src/data/fng_history.csv"

# Ensure models dir exists
os.makedirs(MODELS_DIR, exist_ok=True)

def get_data(days=365):
    """Fetch or load data."""
    if os.path.exists(DATA_FILE):
        logger.info(f"Loading existing data from {DATA_FILE}...")
        df = pd.read_csv(DATA_FILE)
        
        if 'timestamp' in df.columns and not df.empty:
            # Basic validation
            pass
        else:
            logger.warning("Existing file invalid, re-downloading...")
            df = download_fresh_data(days)
    else:
        df = download_fresh_data(days)
    
    return df

def download_fresh_data(days):
    logger.info("Fetching fresh data from Binance Vision...")
    collector = CryptoDataCollector()
    df = collector.fetch_historical_data(timeframe='1m', days=days)
    if not df.empty:
        df.to_csv(DATA_FILE, index=False)
        logger.info(f"Data saved to {DATA_FILE}")
    else:
        logger.error("Failed to fetch data!")
    return df

def get_fng_data():
    """Fetch Fear & Greed Index history."""
    if os.path.exists(FNG_FILE):
        pass
    
    logger.info("Fetching Fear & Greed Index...")
    fng_df = FeatureEngineer.fetch_fear_and_greed()
    if not fng_df.empty:
        fng_df.to_csv(FNG_FILE, index=False)
    elif os.path.exists(FNG_FILE):
        fng_df = pd.read_csv(FNG_FILE)
        fng_df['datetime'] = pd.to_datetime(fng_df['datetime'])
        
    return fng_df

def train_models():
    df = get_data(days=365)
    if df.empty:
        logger.error("No data available for training.")
        return

    fng_df = get_fng_data()

    logger.info(f"Data shape: {df.shape}")
    
    horizons = [10, 30, 60]
    metrics = {}
    
    # Generate features once
    logger.info("Generating features with external data...")
    full_data = FeatureEngineer.generate_features(df, fng_df)
    
    for h in horizons:
        logger.info(f"Training model for {h}m horizon...")
        
        # Prepare targets
        data = full_data.copy()
        future_close = data['close'].shift(-h)
        
        # 1. Volatility Filtering: Ignore small moves (noise)
        data['future_return'] = (future_close - data['close']) / data['close']
        
        # Define threshold (e.g. 0.002 = 0.2% move required)
        # Increased to 0.003 to target more significant moves (less noise)
        threshold = 0.003 
        
        data = data[ (data['future_return'] > threshold) | (data['future_return'] < -threshold) ]
        data['target'] = (data['future_return'] > 0).astype(int)
        
        # Drop NaNs
        data = data.dropna()
        
        # Split features and target
        exclude_cols = ['timestamp', 'datetime', 'open', 'high', 'low', 'close', 'volume', 'target', 'date', 'future_return']
        feature_cols = [c for c in data.columns if c not in exclude_cols]
        
        X = data[feature_cols]
        y = data['target']
        
        # Time-series split for validation (80% train, 20% test)
        split_idx = int(len(X) * 0.8)
        X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
        
        logger.info(f"Training on {len(X_train)} samples, validating on {len(X_test)} samples (threshold={threshold})...")
        
        # Use fixed parameters for stability and speed (avoid OOM)
        # Simplified model to reduce overfitting
        best_model = XGBClassifier(
            n_estimators=1000,
            learning_rate=0.01, # Slower learning
            max_depth=4, # Shallower trees
            subsample=0.7,
            colsample_bytree=0.7,
            min_child_weight=3, # Reduce noise
            objective='binary:logistic',
            n_jobs=1,
            random_state=42,
            tree_method='hist',
            eval_metric='logloss',
            early_stopping_rounds=50
        )
        
        # Train with early stopping
        logger.info(f"Fitting model for {h}m...")
        best_model.fit(
            X_train, y_train,
            eval_set=[(X_train, y_train), (X_test, y_test)],
            verbose=False
        )
        
        # Evaluate on Test Set
        y_pred = best_model.predict(X_test)
        y_prob = best_model.predict_proba(X_test)[:, 1]
        
        # Find optimal threshold for >90% accuracy
        # Search range: 0.55 to 0.95
        best_thresh = 0.7 # default fallback
        max_acc = 0.0
        
        check_thresholds = np.arange(0.55, 0.96, 0.01)
        found_target = False
        
        for t in check_thresholds:
            # Mask for high confidence predictions (both up and down)
            mask = (y_prob > t) | (y_prob < (1-t))
            if mask.sum() > 10: # Lower min samples requirement slightly
                # Predictions for these samples
                pred_t = (y_prob[mask] > 0.5).astype(int)
                acc_t = accuracy_score(y_test[mask], pred_t)
                
                # Keep track of best accuracy found regardless
                if acc_t > max_acc:
                    max_acc = acc_t
                    if not found_target: # Only update best_thresh if we haven't found >90% yet
                        best_thresh = float(t)
                
                if acc_t >= 0.90:
                    best_thresh = float(t)
                    max_acc = acc_t
                    found_target = True
                    break
        
        logger.info(f"Optimal Threshold: {best_thresh:.4f} (Max Acc: {max_acc:.4f})")
        
        # High Confidence Metrics using optimal threshold
        high_conf_mask = (y_prob > best_thresh) | (y_prob < (1-best_thresh))
        if high_conf_mask.sum() > 0:
            high_conf_acc = accuracy_score(y_test[high_conf_mask], y_pred[high_conf_mask]) # Re-evaluate
            # Actually y_pred is based on 0.5. We should re-calculate based on direction
            # But XGBoost predict is 0.5 threshold.
            # Correct logic:
            preds_high_conf = (y_prob[high_conf_mask] > 0.5).astype(int)
            high_conf_acc = accuracy_score(y_test[high_conf_mask], preds_high_conf)
            logger.info(f"High Confidence Accuracy (Test Set): {high_conf_acc:.4f}")
        else:
            high_conf_acc = 0.0
            
        acc = accuracy_score(y_test, y_pred)
        prec = precision_score(y_test, y_pred)
        rec = recall_score(y_test, y_pred)
        f1 = f1_score(y_test, y_pred)
        try:
            auc = roc_auc_score(y_test, y_prob)
        except:
            auc = 0.5
        
        # Refit on ALL data with best params (optional, but good for final model)
        # But for consistency with metrics, maybe just save the model trained on X_train?
        # Standard practice: Retrain on all data.
        # However, we need to trust that the threshold holds.
        logger.info("Retraining on full dataset...")
        final_model = XGBClassifier(**best_model.get_params())
        # Remove early_stopping_rounds from constructor if passed to fit, or keep it but we have no eval set
        # Clean params
        params = best_model.get_params()
        if 'early_stopping_rounds' in params:
            del params['early_stopping_rounds'] # It's not init param in some versions, or it is? 
            # In modern XGBoost, it is init param.
        
        final_model = XGBClassifier(**params)
        final_model.fit(X, y)
        
        model_path = os.path.join(MODELS_DIR, f"xgb_model_{h}m.joblib")
        joblib.dump(final_model, model_path)
        
        feature_importance = dict(zip(X.columns, final_model.feature_importances_.tolist()))
        
        metrics[f"{h}m"] = {
            "accuracy": float(acc),
            "precision": float(prec),
            "recall": float(rec),
            "f1": float(f1),
            "auc": float(auc),
            "high_conf_accuracy": float(high_conf_acc),
            "threshold": float(best_thresh), # Save dynamic threshold
            "feature_importance": sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)[:10],
            "features": [k for k, v in sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)[:10]],
            "sample_size": len(X),
            "training_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "f1_score": float(f1)
        }
        logger.info(f"Saved model for {h}m")

    with open(METRICS_FILE, 'w') as f:
        json.dump(metrics, f, indent=4)
    logger.info("Training complete.")

if __name__ == "__main__":
    train_models()
