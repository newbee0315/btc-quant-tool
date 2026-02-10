import sys
import os
import logging
import pandas as pd
import numpy as np
import optuna
from xgboost import XGBClassifier
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
import joblib
import json

# Add project root to path
sys.path.append(os.getcwd())

from src.models.train import get_data, get_fng_data
from src.models.features import FeatureEngineer

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MODELS_DIR = "src/models/saved_models"
BEST_PARAMS_FILE = os.path.join(MODELS_DIR, "best_params.json")

def objective(trial, X, y):
    """
    Optuna objective function for XGBoost tuning.
    """
    param = {
        'n_estimators': trial.suggest_int('n_estimators', 100, 1000),
        'learning_rate': trial.suggest_float('learning_rate', 0.005, 0.1, log=True),
        'max_depth': trial.suggest_int('max_depth', 3, 10),
        'min_child_weight': trial.suggest_int('min_child_weight', 1, 7),
        'gamma': trial.suggest_float('gamma', 0.0, 0.5),
        'subsample': trial.suggest_float('subsample', 0.6, 1.0),
        'colsample_bytree': trial.suggest_float('colsample_bytree', 0.6, 1.0),
        'reg_alpha': trial.suggest_float('reg_alpha', 1e-5, 1.0, log=True),
        'reg_lambda': trial.suggest_float('reg_lambda', 1e-5, 1.0, log=True),
        'objective': 'binary:logistic',
        'n_jobs': 1,
        'random_state': 42,
        'tree_method': 'hist',
        'eval_metric': 'logloss'
    }

    # Time Series Split Cross-Validation
    tscv = TimeSeriesSplit(n_splits=3)
    scores = []
    
    for train_idx, val_idx in tscv.split(X):
        X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]
        
        model = XGBClassifier(**param)
        model.fit(X_train, y_train, verbose=False)
        
        preds = model.predict(X_val)
        # Optimize for F1 Score to balance Precision and Recall
        score = f1_score(y_val, preds, zero_division=0)
        scores.append(score)
        
    return np.mean(scores)

def optimize_models():
    logger.info("Starting Hyperparameter Optimization...")
    
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
    best_params_all = {}
    
    for h in horizons:
        logger.info(f"\n--- Optimizing for {h}m Horizon ---")
        
        # Prepare targets
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
        
        # Split: Use last 20% for final test, optimize on first 80%
        split_idx = int(len(X) * 0.8)
        X_opt = X.iloc[:split_idx]
        y_opt = y.iloc[:split_idx]
        
        logger.info(f"Optimization dataset size: {len(X_opt)}")
        
        # Create Study
        study = optuna.create_study(direction='maximize')
        # Run for 20 trials (keep it fast for demo, increase for real prod)
        study.optimize(lambda trial: objective(trial, X_opt, y_opt), n_trials=20)
        
        logger.info(f"Best Trial for {h}m:")
        logger.info(f"  Value: {study.best_value:.4f}")
        logger.info(f"  Params: {study.best_params}")
        
        best_params_all[str(h)] = study.best_params
        
    # Save best params
    with open(BEST_PARAMS_FILE, 'w') as f:
        json.dump(best_params_all, f, indent=4)
    logger.info(f"Best parameters saved to {BEST_PARAMS_FILE}")
    
    return best_params_all

if __name__ == "__main__":
    optimize_models()
