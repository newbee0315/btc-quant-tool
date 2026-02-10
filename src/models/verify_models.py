import joblib
import os
import sys
import pandas as pd
sys.path.append(os.getcwd())

from src.models.features import FeatureEngineer

def verify():
    models_dir = "src/models/saved_models"
    horizons = [10, 30, 60]
    
    print("Verifying saved models...")
    for h in horizons:
        path = os.path.join(models_dir, f"xgb_model_{h}m.joblib")
        if os.path.exists(path):
            model = joblib.load(path)
            print(f"\nModel {h}m: {type(model)}")
            if hasattr(model, 'steps'):
                print("Pipeline steps:", [s[0] for s in model.steps])
                # Try to inspect selector
                selector = model.named_steps['selection']
                print(f"Selector threshold: {selector.threshold}")
                # We can't easily see feature names unless we have the input data, 
                # but we can check if it's ready for prediction.
            else:
                print("Not a pipeline.")
        else:
            print(f"Model {h}m not found.")

if __name__ == "__main__":
    verify()
