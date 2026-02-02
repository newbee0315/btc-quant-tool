import sys
import os
import pandas as pd
import numpy as np
import joblib
import xgboost as xgb

sys.path.append(os.getcwd())
from src.models.predictor import PricePredictor
from src.models.features import FeatureEngineer

def debug_prediction():
    print(f"XGBoost version: {xgb.__version__}")
    
    # Load predictor
    predictor = PricePredictor()
    print("Models loaded:", predictor.models.keys())
    
    # Create dummy data
    # We need enough rows for features (e.g. 100)
    dates = pd.date_range(end=pd.Timestamp.now(), periods=200, freq='1min')
    df = pd.DataFrame({
        'timestamp': dates.astype(np.int64) // 10**6,
        'datetime': dates,
        'open': np.random.randn(200) + 50000,
        'high': np.random.randn(200) + 50005,
        'low': np.random.randn(200) + 49995,
        'close': np.random.randn(200) + 50000,
        'volume': np.random.randn(200) * 100 + 1000
    })
    
    print("Dummy data shape:", df.shape)
    
    # Generate features
    full_df = FeatureEngineer.generate_features(df)
    print("Features generated shape:", full_df.shape)
    print("Columns:", full_df.columns.tolist())
    
    # Prepare X like predictor does
    last_row = full_df.iloc[[-1]].copy()
    exclude_cols = ['timestamp', 'datetime', 'open', 'high', 'low', 'close', 'volume', 'target']
    exclude_cols += [c for c in last_row.columns if c.startswith('target_')]
    feature_cols = [c for c in last_row.columns if c not in exclude_cols]
    
    X = last_row[feature_cols]
    print("X type:", type(X))
    print("X shape:", X.shape)
    print("X columns:", X.columns.tolist())
    
    # Predict
    for h in [10, 30, 60]:
        if h in predictor.models:
            model = predictor.models[h]
            print(f"\nTesting {h}m model...")
            try:
                if hasattr(model, "feature_names_in_"):
                    print("Model expects features:", model.feature_names_in_)
                
                # Try passing DataFrame
                print("Predicting with DataFrame...")
                prob = model.predict_proba(X)[0][1]
                print(f"Prediction success: {prob}")
                
            except Exception as e:
                print(f"Prediction failed: {e}")

if __name__ == "__main__":
    debug_prediction()
