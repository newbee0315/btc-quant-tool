import sys
import os
import logging
import pandas as pd
import numpy as np
from xgboost import XGBClassifier
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, classification_report

# Add project root to path
sys.path.append(os.getcwd())

from src.models.train import get_data, get_fng_data
from src.models.features import FeatureEngineer

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def evaluate_baseline():
    logger.info("Starting Baseline Evaluation...")
    
    # 1. Load Data
    df = get_data(days=365)
    fng_df = get_fng_data()
    
    if df.empty:
        logger.error("No data available.")
        return

    # 2. Generate Features
    logger.info("Generating features...")
    full_data = FeatureEngineer.generate_features(df, fng_df)
    
    horizons = [10, 30, 60]
    results = {}
    
    for h in horizons:
        logger.info(f"\n--- Evaluating {h}m Horizon ---")
        
        # Prepare targets (Same logic as train.py)
        data = full_data.copy()
        future_close = data['close'].shift(-h)
        data['future_return'] = (future_close - data['close']) / data['close']
        
        threshold = 0.003
        data = data[ (data['future_return'] > threshold) | (data['future_return'] < -threshold) ]
        data['target'] = (data['future_return'] > 0).astype(int)
        data = data.dropna()
        
        exclude_cols = ['timestamp', 'datetime', 'open', 'high', 'low', 'close', 'volume', 'target', 'date', 'future_return']
        feature_cols = [c for c in data.columns if c not in exclude_cols]
        
        X = data[feature_cols]
        y = data['target']
        
        # Time-series split (Last 20% as test)
        split_idx = int(len(X) * 0.8)
        X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
        
        logger.info(f"Train size: {len(X_train)}, Test size: {len(X_test)}")
        
        # Default Model (from train.py)
        model = XGBClassifier(
            n_estimators=1000,
            learning_rate=0.01,
            max_depth=4,
            subsample=0.7,
            colsample_bytree=0.7,
            min_child_weight=3,
            objective='binary:logistic',
            n_jobs=1,
            random_state=42,
            tree_method='hist',
            eval_metric='logloss',
            early_stopping_rounds=50
        )
        
        model.fit(
            X_train, y_train,
            eval_set=[(X_train, y_train), (X_test, y_test)],
            verbose=False
        )
        
        # Evaluate
        y_pred = model.predict(X_test)
        y_prob = model.predict_proba(X_test)[:, 1]
        
        acc = accuracy_score(y_test, y_pred)
        prec = precision_score(y_test, y_pred)
        rec = recall_score(y_test, y_pred)
        f1 = f1_score(y_test, y_pred)
        auc = roc_auc_score(y_test, y_prob)
        
        logger.info(f"Baseline Metrics ({h}m):")
        logger.info(f"Accuracy: {acc:.4f}")
        logger.info(f"Precision: {prec:.4f}")
        logger.info(f"Recall:    {rec:.4f}")
        logger.info(f"F1 Score:  {f1:.4f}")
        logger.info(f"AUC:       {auc:.4f}")
        
        results[h] = {
            "accuracy": acc,
            "precision": prec,
            "recall": rec,
            "f1": f1,
            "auc": auc
        }
        
    return results

if __name__ == "__main__":
    evaluate_baseline()
