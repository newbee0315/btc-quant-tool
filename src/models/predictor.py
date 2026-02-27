import pandas as pd
import numpy as np
import joblib
import logging
import os
import sys
import time

# Add project root to path
sys.path.append(os.getcwd())

from src.models.features import FeatureEngineer

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PricePredictor:
    def __init__(self, models_dir="src/models/saved_models", symbol=None):
        self.models_dir = models_dir
        self.symbol = symbol
        self.models = {} # Structure: {horizon: {type: model}} e.g. {30: {'xgb': model, 'lgbm': model}}
        self.metrics = {}
        self.horizons = [10, 30]
        self.model_types = ['xgb', 'lgbm', 'rf'] # Supported types for ensemble
        self.last_reload_time = 0
        self.metrics_path = os.path.join(self.models_dir, "multicoin_metrics.json")
        self.load_models()

    def check_reload(self):
        """Check if metrics file has changed and reload if necessary"""
        if os.path.exists(self.metrics_path):
            try:
                mtime = os.path.getmtime(self.metrics_path)
                if mtime > self.last_reload_time:
                    logger.info(f"Metrics file changed. Reloading models for {self.symbol}...")
                    self.load_models()
            except Exception as e:
                logger.error(f"Error checking reload: {e}")

    def load_models(self):
        """Load trained models and metrics for all horizons"""
        self.last_reload_time = time.time()
        
        # Load metrics first to get thresholds
        if not os.path.exists(self.metrics_path):
             # Fallback
             old_metrics_path = os.path.join(self.models_dir, "model_metrics.json")
             if os.path.exists(old_metrics_path):
                 self.metrics_path = old_metrics_path
             
        if os.path.exists(self.metrics_path):
            try:
                import json
                with open(self.metrics_path, 'r') as f:
                    self.metrics = json.load(f)
                    # If using multicoin metrics, extract for specific symbol if provided
                    if self.symbol:
                        symbol_key = f"{self.symbol}USDT"
                        if symbol_key in self.metrics:
                            self.metrics = self.metrics[symbol_key]
                        elif self.symbol in self.metrics:
                             self.metrics = self.metrics[self.symbol]
                        
                logger.info(f"Loaded model metrics (Symbol: {self.symbol})")
            except Exception as e:
                logger.error(f"Error loading metrics: {e}")
        
        for h in self.horizons:
            self.models[h] = {}
            
            # Iterate through supported model types
            for m_type in self.model_types:
                paths_to_try = []
                # 1. Specific: type_Symbol_horizon.joblib (e.g. xgb_BTCUSDT_30m.joblib)
                if self.symbol:
                    paths_to_try.append(os.path.join(self.models_dir, f"{m_type}_{self.symbol}_{h}m.joblib"))
                
                # 2. Generic: type_model_horizon.joblib (e.g. xgb_model_30m.joblib)
                paths_to_try.append(os.path.join(self.models_dir, f"{m_type}_model_{h}m.joblib"))
                
                model_loaded = False
                for path in paths_to_try:
                    if os.path.exists(path):
                        try:
                            # Use joblib for most sklearn/xgboost models
                            # For LSTM (keras), we might need special handling later
                            self.models[h][m_type] = joblib.load(path)
                            logger.info(f"Loaded {m_type} model for {h}m horizon from {os.path.basename(path)}")
                            model_loaded = True
                            break
                        except Exception as e:
                            logger.error(f"Error loading {m_type} model from {path}: {e}")
                
                if not model_loaded and m_type == 'xgb': # Warn only for primary model
                    logger.warning(f"Primary {m_type} model not found for {h}m horizon (Symbol: {self.symbol})")

    def predict_single_model(self, model, X, h, m_type):
        """Helper to predict with a single model instance"""
        try:
            # Align features (same logic as before)
            current_X = X.copy()
            expected_cols = None
            
            try:
                if hasattr(model, 'named_steps') and 'selection' in model.named_steps:
                    selector = model.named_steps['selection']
                    if hasattr(selector, 'feature_names_in_'):
                        expected_cols = selector.feature_names_in_
                elif hasattr(model, 'feature_names_in_'):
                    expected_cols = model.feature_names_in_
                elif hasattr(model, 'estimators_'):
                    if hasattr(model.estimators_[0], 'feature_names_in_'):
                        expected_cols = model.estimators_[0].feature_names_in_
                elif hasattr(model, 'get_booster'):
                    try:
                        booster = model.get_booster()
                        if hasattr(booster, 'feature_names') and booster.feature_names:
                            expected_cols = booster.feature_names
                    except: pass

                if expected_cols is not None:
                    missing_cols = set(expected_cols) - set(current_X.columns)
                    if missing_cols:
                        for c in missing_cols: current_X[c] = 0
                    current_X = current_X[expected_cols]
            except Exception as e:
                logger.warning(f"Feature alignment warning ({m_type}): {e}")

            # Predict
            prob = model.predict_proba(current_X)[0][1]
            return prob
        except Exception as e:
            logger.error(f"Prediction failed for {h}m ({m_type}): {e}")
            return None

    def predict_all(self, recent_data: pd.DataFrame):
        """
        Make predictions for all horizons based on recent data
        :param recent_data: DataFrame with at least 50-100 recent 1m candles
        :return: Dict with predictions
        """
        self.check_reload()
        
        if recent_data.empty:
            return None
            
        # Try to fetch latest F&G for better accuracy
        fng_df = None
        try:
            # Create a minimal DF with today's F&G
            # Ideally we fetch it, but to avoid blocking, we could check a cache.
            # For now, let's do a quick fetch with short timeout
            import requests
            url = "https://api.alternative.me/fng/?limit=1&format=json"
            resp = requests.get(url, timeout=2)
            if resp.status_code == 200:
                data = resp.json()['data'][0]
                # Construct a DataFrame that features.py can merge
                # features.py merges on 'date'.
                # We need to provide a DataFrame with 'datetime' and 'value'
                fng_df = pd.DataFrame([{
                    'datetime': pd.to_datetime(int(data['timestamp']), unit='s'),
                    'value': int(data['value'])
                }])
        except Exception as e:
            logger.warning(f"Could not fetch F&G for prediction: {e}")
            
        # Generate features using the shared logic
        try:
            full_df = FeatureEngineer.generate_features(recent_data, fng_df)
        except Exception as e:
            logger.error(f"Feature generation failed: {e}")
            return None
        
        # Use the last row for prediction
        last_row = full_df.iloc[[-1]].copy()
        
        # Drop non-feature columns
        exclude_cols = ['timestamp', 'datetime', 'open', 'high', 'low', 'close', 'volume', 'target', 'date', 'future_return']
        # Also drop any target columns if they accidentally exist
        exclude_cols += [c for c in last_row.columns if c.startswith('target_')]
        
        feature_cols = [c for c in last_row.columns if c not in exclude_cols]
        
        # Ensure features match model expectation? 
        # XGBoost via sklearn interface is somewhat flexible with column names if dataframe is passed,
        # but order matters if numpy array. It's safer if we pass DataFrame.
        # However, we must ensure columns match what was used in training.
        # Since we use the exact same FeatureEngineer, the columns should be identical
        # provided the input data has the same base columns.
        
        X = last_row[feature_cols]
        
        # Debug logging
        try:
            logger.info(f"Predict X type: {type(X)}")
            logger.info(f"Predict X shape: {X.shape}")
            if hasattr(X, 'columns'):
                logger.info(f"Predict X columns: {X.columns.tolist()}")
            else:
                logger.info("Predict X has no columns attribute")
        except Exception as e:
            logger.error(f"Error logging X details: {e}")
        
        predictions = {}
        for h in self.horizons:
            if h in self.models and self.models[h]:
                try:
                    # Ensemble Prediction
                    probs = []
                    for m_type, model in self.models[h].items():
                        p = self.predict_single_model(model, X, h, m_type)
                        if p is not None:
                            probs.append(p)
                    
                    if not probs:
                        logger.warning(f"No valid predictions for {h}m horizon")
                        continue
                        
                    # Average Probability (Soft Voting)
                    prob = float(np.mean(probs))
                    
                    # Determine direction based on confidence thresholds
                    # Since we trained on filtered data, "0.5" might be ambiguous.
                    # Let's enforce a neutral zone for UI clarity if needed, 
                    # but the requirement is UP/DOWN.
                    # However, to be consistent with "High Accuracy", we can flag low confidence.
                    
                    direction = "UP" if prob > 0.5 else "DOWN"
                    confidence_score = abs(prob - 0.5) * 2 # 0 to 1 scale
                    
                    # Dynamic threshold from training metrics
                    threshold = 0.70 # default
                    if f"{h}m" in self.metrics and "threshold" in self.metrics[f"{h}m"]:
                        threshold = self.metrics[f"{h}m"]["threshold"]
                    
                    # Ensure threshold is symmetric for prob
                    # If threshold is 0.8, then prob > 0.8 or prob < 0.2
                    is_high_conf = bool(prob > threshold or prob < (1 - threshold))
                    
                    predictions[f"{h}m"] = {
                        "probability": float(prob),
                        "direction": direction,
                        "horizon_minutes": h,
                        "confidence": float(confidence_score),
                        "is_high_confidence": is_high_conf,
                        "threshold_used": float(threshold),
                        "models_used": list(self.models[h].keys())
                    }
                except Exception as e:
                    logger.error(f"Prediction failed for {h}m: {e}")
                    predictions[f"{h}m"] = {"error": str(e)}
            else:
                predictions[f"{h}m"] = {"error": "Model not loaded"}
                
        return predictions
