
import os
import sys
import joblib
import numpy as np
import pandas as pd
from xgboost import XGBClassifier

# Add project root
sys.path.append(os.getcwd())

def create_dummy_models():
    models_dir = "src/models/saved_models"
    os.makedirs(models_dir, exist_ok=True)
    
    # Create a dummy dataset
    # 20 features
    X = np.random.rand(100, 20)
    y = np.random.randint(0, 2, 100)
    
    # Feature names
    feature_names = [f"feature_{i}" for i in range(20)]
    X_df = pd.DataFrame(X, columns=feature_names)
    
    horizons = [10, 30, 60]
    
    for h in horizons:
        print(f"Training dummy model for {h}m horizon...")
        model = XGBClassifier(n_estimators=10, max_depth=2, random_state=42)
        model.fit(X_df, y)
        
        # Save generic model
        path = os.path.join(models_dir, f"xgb_model_{h}m.joblib")
        joblib.dump(model, path)
        print(f"Saved {path}")
        
        # Save BTC specific model
        path_btc = os.path.join(models_dir, f"xgb_BTCUSDT_{h}m.joblib")
        joblib.dump(model, path_btc)
        print(f"Saved {path_btc}")
        
    print("Dummy models created successfully.")

if __name__ == "__main__":
    create_dummy_models()
