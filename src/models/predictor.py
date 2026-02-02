import pandas as pd
import numpy as np
import joblib
import logging
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from src.models.features import FeatureEngineer

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PricePredictor:
    def __init__(self, models_dir="src/models/saved_models"):
        self.models_dir = models_dir
        self.models = {}
        self.metrics = {}
        self.horizons = [10, 30, 60]
        self.load_models()

    def load_models(self):
        """Load trained models and metrics for all horizons"""
        # Load metrics first to get thresholds
        metrics_path = os.path.join(self.models_dir, "model_metrics.json")
        if os.path.exists(metrics_path):
            try:
                import json
                with open(metrics_path, 'r') as f:
                    self.metrics = json.load(f)
                logger.info("Loaded model metrics and thresholds")
            except Exception as e:
                logger.error(f"Error loading metrics: {e}")
        
        for h in self.horizons:
            # Try XGBoost first
            path = os.path.join(self.models_dir, f"xgb_model_{h}m.joblib")
            if not os.path.exists(path):
                # Fallback to RF if exists
                path = os.path.join(self.models_dir, f"rf_model_{h}m.joblib")
            
            if os.path.exists(path):
                try:
                    self.models[h] = joblib.load(path)
                    logger.info(f"Loaded model for {h}m horizon from {os.path.basename(path)}")
                except Exception as e:
                    logger.error(f"Error loading model for {h}m: {e}")
            else:
                logger.warning(f"Model file not found for {h}m horizon")

    def predict_all(self, recent_data: pd.DataFrame):
        """
        Make predictions for all horizons based on recent data
        :param recent_data: DataFrame with at least 50-100 recent 1m candles
        :return: Dict with predictions
        """
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
        exclude_cols = ['timestamp', 'datetime', 'open', 'high', 'low', 'close', 'volume', 'target']
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
            if h in self.models:
                try:
                    model = self.models[h]
                    # Check if model expects specific features (if possible)
                    # For now, trust the FeatureEngineer consistency
                    
                    prob = model.predict_proba(X)[0][1] # Probability of class 1 (Up)
                    
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
                        "threshold_used": float(threshold)
                    }
                except Exception as e:
                    logger.error(f"Prediction failed for {h}m: {e}")
                    predictions[f"{h}m"] = {"error": str(e)}
            else:
                predictions[f"{h}m"] = {"error": "Model not loaded"}
                
        return predictions
