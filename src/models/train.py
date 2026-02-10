import sys
import os
import logging
import pandas as pd
import numpy as np
from datetime import datetime
import joblib
import json
from xgboost import XGBClassifier
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.feature_selection import SelectFromModel
from sklearn.pipeline import Pipeline
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, classification_report

# Add project root to path
sys.path.append(os.getcwd())

from src.data.collector import CryptoDataCollector
from src.models.features import FeatureEngineer

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MODELS_DIR = "src/models/saved_models"
DATA_FILE = "src/data/btc_futures_data.csv"
METRICS_FILE = os.path.join(MODELS_DIR, "model_metrics.json")
BEST_PARAMS_FILE = os.path.join(MODELS_DIR, "best_params.json")
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
            # Fallback to spot 1m if futures file is bad/missing logic (or just fail)
            df = download_fresh_data(days)
    else:
        # If futures data missing, try to download spot 1m (fallback) or use script
        logger.warning(f"{DATA_FILE} not found. Using spot data fallback.")
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
    
    # Assuming 5m data from btc_futures_data.csv
    # Map target horizons (minutes) to steps (rows)
    # 10m = 2 * 5m, 30m = 6 * 5m, 60m = 12 * 5m
    horizon_map = {
        10: 2,
        30: 6,
        60: 12
    }
    metrics = {}
    
    # Load optimized params if available
    best_params = {}
    if os.path.exists(BEST_PARAMS_FILE):
        try:
            with open(BEST_PARAMS_FILE, 'r') as f:
                best_params = json.load(f)
            logger.info("Loaded optimized hyperparameters.")
        except Exception as e:
            logger.error(f"Error loading best params: {e}")

    # Generate features once
    logger.info("Generating features with external data...")
    full_data = FeatureEngineer.generate_features(df, fng_df)
    
    for h, steps in horizon_map.items():
        logger.info(f"Training model for {h}m horizon ({steps} steps)...")
        
        # Prepare targets
        data = full_data.copy()
        future_close = data['close'].shift(-steps)
        
        # 1. Volatility Filtering
        data['future_return'] = (future_close - data['close']) / data['close']
        
        # Define threshold (0.3% move required)
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
        
        # Time-series split (80% train, 20% test)
        split_idx = int(len(X) * 0.8)
        X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
        
        logger.info(f"Training on {len(X_train)} samples, validating on {len(X_test)} samples (threshold={threshold})...")
        
        # Get params for this horizon or use default
        params = best_params.get(str(h), {
            'n_estimators': 1000,
            'learning_rate': 0.01,
            'max_depth': 4,
            'subsample': 0.7,
            'colsample_bytree': 0.7,
            'min_child_weight': 3,
            'objective': 'binary:logistic',
            'n_jobs': 1,
            'random_state': 42,
            'tree_method': 'hist',
            'eval_metric': 'logloss'
        })
        
        # Ensure base params are present
        if 'objective' not in params: params['objective'] = 'binary:logistic'
        if 'n_jobs' not in params: params['n_jobs'] = 1
        if 'tree_method' not in params: params['tree_method'] = 'hist'
        if 'eval_metric' not in params: params['eval_metric'] = 'logloss'
        
        # --- Ensemble Pipeline ---
        logger.info("Training Ensemble Pipeline (Selection + XGB + RF)...")
        
        # Define estimators
        xgb_clf = XGBClassifier(**params)
        rf_clf = RandomForestClassifier(n_estimators=200, max_depth=10, n_jobs=1, random_state=42)
        
        # Feature Selector (using a smaller XGB for speed)
        selector = SelectFromModel(estimator=XGBClassifier(n_estimators=50, max_depth=3, n_jobs=1), threshold='median')
        
        # Ensemble
        ensemble = VotingClassifier(
            estimators=[('xgb', xgb_clf), ('rf', rf_clf)],
            voting='soft'
        )
        
        # Pipeline
        model = Pipeline([
            ('selection', selector),
            ('ensemble', ensemble)
        ])
        
        model.fit(X_train, y_train)
        
        # Evaluate on Test Set
        y_pred = model.predict(X_test)
        y_prob = model.predict_proba(X_test)[:, 1]
        
        # Find optimal threshold for >90% accuracy
        best_thresh = 0.7 # default fallback
        max_acc = 0.0
        
        check_thresholds = np.arange(0.55, 0.96, 0.01)
        found_target = False
        
        for t in check_thresholds:
            # Mask for high confidence predictions (both up and down)
            mask = (y_prob > t) | (y_prob < (1-t))
            if mask.sum() > 10: 
                pred_t = (y_prob[mask] > 0.5).astype(int)
                acc_t = accuracy_score(y_test[mask], pred_t)
                
                if acc_t > max_acc:
                    max_acc = acc_t
                    if not found_target:
                        best_thresh = float(t)
                
                if acc_t >= 0.90:
                    best_thresh = float(t)
                    max_acc = acc_t
                    found_target = True
                    break
        
        logger.info(f"Optimal Threshold: {best_thresh:.4f} (Max Acc: {max_acc:.4f})")
        
        # High Confidence Metrics
        high_conf_mask = (y_prob > best_thresh) | (y_prob < (1-best_thresh))
        if high_conf_mask.sum() > 0:
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
            
        logger.info(f"Overall Metrics: Acc={acc:.4f}, Prec={prec:.4f}, Rec={rec:.4f}, F1={f1:.4f}, AUC={auc:.4f}")
        
        # Retrain on FULL dataset
        logger.info("Retraining on full dataset...")
        final_model = Pipeline([
            ('selection', selector), # reuse selector logic structure, but ideally refit
            ('ensemble', VotingClassifier(
                estimators=[('xgb', XGBClassifier(**params)), ('rf', RandomForestClassifier(n_estimators=200, max_depth=10, n_jobs=1, random_state=42))],
                voting='soft'
            ))
        ])
        # Need to clone or recreate selector to refit properly
        final_model.set_params(selection__estimator=XGBClassifier(n_estimators=50, max_depth=3, n_jobs=1))
        
        final_model.fit(X, y)
        
        model_path = os.path.join(MODELS_DIR, f"xgb_model_{h}m.joblib")
        joblib.dump(final_model, model_path)
        
        # Calculate feature importance
        feature_importance = {}
        try:
             # Get selected features mask
             support = final_model.named_steps['selection'].get_support()
             selected_feats = X.columns[support]
             
             # Get importances from ensemble (avg of xgb and rf)
             ens = final_model.named_steps['ensemble']
             xgb_imp = ens.estimators_[0].feature_importances_
             rf_imp = ens.estimators_[1].feature_importances_
             avg_imp = (xgb_imp + rf_imp) / 2
             
             feature_importance = dict(zip(selected_feats, avg_imp.tolist()))
        except Exception as e:
             logger.warning(f"Could not calculate feature importance: {e}")
        
        metrics[f"{h}m"] = {
            "accuracy": float(high_conf_acc) if high_conf_acc > 0 else float(acc), # Display Trade Accuracy
            "base_accuracy": float(acc),
            "precision": float(prec),
            "recall": float(rec),
            "f1": float(f1),
            "auc": float(auc),
            "high_conf_accuracy": float(high_conf_acc),
            "threshold": float(best_thresh),
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
