import sys
import os
import time
import logging
import pandas as pd
import numpy as np
import joblib
import json
import random
import signal
from xgboost import XGBClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score

# Add project root to path
sys.path.append(os.getcwd())

from src.models.features import FeatureEngineer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [Optimizer] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("auto_optimizer.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Config
DATA_DIR = "data/raw"
MODELS_DIR = "src/models/saved_models"
METRICS_FILE = os.path.join(MODELS_DIR, "multicoin_metrics.json")
TIMEFRAME = '1m'
HORIZONS = [10] # Focus on 10m first as it's the primary signal
# 14 Symbols Scope
TARGET_SYMBOLS = [
    'BTC', 'ETH', 'SOL', 'BNB', 'DOGE', 'XRP', 'PEPE', 
    'AVAX', 'LINK', 'ADA', 'TRX', 'LDO', 'BCH', 'OP'
]

# Performance Standards
MIN_ACCURACY = 0.55
MIN_PRECISION = 0.52
MAX_TRIALS_PER_RUN = 10  # More trials per optimization run

# Ensure models dir exists
os.makedirs(MODELS_DIR, exist_ok=True)

class AutoOptimizer:
    def __init__(self):
        self.running = True
        self.metrics = self.load_metrics()
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

    def stop(self, signum, frame):
        logger.info("Stopping optimizer...")
        self.running = False

    def load_metrics(self):
        if os.path.exists(METRICS_FILE):
            try:
                with open(METRICS_FILE, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load metrics: {e}")
                return {}
        return {}

    def save_metrics(self):
        with open(METRICS_FILE, 'w') as f:
            json.dump(self.metrics, f, indent=4)

    def load_data(self, symbol):
        filename = f"{symbol}USDT_{TIMEFRAME}.csv"
        filepath = os.path.join(DATA_DIR, filename)
        
        if not os.path.exists(filepath):
            # Try without USDT suffix just in case
            filename = f"{symbol}_{TIMEFRAME}.csv"
            filepath = os.path.join(DATA_DIR, filename)
            
        if not os.path.exists(filepath):
            logger.warning(f"[{symbol}] Data file not found.")
            return pd.DataFrame()
        
        try:
            df = pd.read_csv(filepath)
            if 'datetime' not in df.columns and 'timestamp' in df.columns:
                df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
            elif 'datetime' in df.columns:
                df['datetime'] = pd.to_datetime(df['datetime'])
            return df
        except Exception as e:
            logger.error(f"[{symbol}] Error reading CSV: {e}")
            return pd.DataFrame()

    def get_random_params(self):
        """Generate wider range of random hyperparameters"""
        return {
            'n_estimators': random.choice([100, 300, 500, 800, 1000]),
            'max_depth': random.choice([3, 4, 5, 6, 8, 10]),
            'learning_rate': random.uniform(0.005, 0.3),
            'subsample': random.uniform(0.5, 1.0),
            'colsample_bytree': random.uniform(0.5, 1.0),
            'gamma': random.uniform(0, 5),
            'min_child_weight': random.randint(1, 10),
            'random_state': random.randint(0, 10000),
            'n_jobs': 2, # Reduce threads to save memory
            'eval_metric': 'logloss'
        }

    def evaluate_model(self, model, X_test, y_test):
        y_pred = model.predict(X_test)
        y_prob = model.predict_proba(X_test)[:, 1]
        
        acc = accuracy_score(y_test, y_pred)
        prec = precision_score(y_test, y_pred, zero_division=0)
        rec = recall_score(y_test, y_pred, zero_division=0)
        f1 = f1_score(y_test, y_pred, zero_division=0)
        auc = roc_auc_score(y_test, y_prob)
        
        return {
            "accuracy": round(acc, 4),
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
            "auc": round(auc, 4)
        }

    def optimize_symbol(self, symbol, horizon=10):
        logger.info(f"[{symbol}] Starting optimization for {horizon}m horizon...")
        
        # 1. Load Data
        df = self.load_data(symbol)
        if df.empty or len(df) < 1000:
            logger.warning(f"[{symbol}] Insufficient data. Skipping.")
            return False

        # 2. Feature Engineering
        # logger.info(f"[{symbol}] Generating features...")
        try:
            df = FeatureEngineer.generate_features(df)
            df = df.dropna()
        except Exception as e:
            logger.error(f"[{symbol}] Feature engineering failed: {e}")
            return False

        # 3. Prepare Data
        future_close = df['close'].shift(-horizon)
        df[f'target_{horizon}m'] = (future_close > df['close'] * 1.001).astype(int)
        
        features = [c for c in df.columns if c not in ['timestamp', 'datetime', 'open', 'high', 'low', 'close', 'volume'] and not c.startswith('target_')]
        
        data_valid = df.dropna(subset=[f'target_{horizon}m'])
        if len(data_valid) < 500:
            logger.warning(f"[{symbol}] Not enough valid data after feature eng.")
            return False

        # Time-based split (Train on past, Test on recent)
        split_idx = int(len(data_valid) * 0.85)
        train_df = data_valid.iloc[:split_idx]
        test_df = data_valid.iloc[split_idx:]
        
        X_train = train_df[features]
        y_train = train_df[f'target_{horizon}m']
        X_test = test_df[features]
        y_test = test_df[f'target_{horizon}m']

        # Calculate scale_pos_weight for imbalanced classes
        num_pos = np.sum(y_train == 1)
        num_neg = np.sum(y_train == 0)
        scale_pos_weight = 1.0
        if num_pos > 0:
            scale_pos_weight = float(num_neg) / float(num_pos)
        
        logger.info(f"[{symbol}] Class balance: Pos={num_pos}, Neg={num_neg}, Scale={scale_pos_weight:.2f}")

        # Check current best
        current_metrics = self.metrics.get(f"{symbol}USDT", {}).get(f"{horizon}m", {})
        best_acc = current_metrics.get("accuracy", 0)
        best_prec = current_metrics.get("precision", 0)
        
        logger.info(f"[{symbol}] Current Best: Acc={best_acc}, Prec={best_prec}")
        
        best_model_run = None
        best_metrics_run = None
        best_score_run = -1

        # Optimization Loop
        for trial in range(MAX_TRIALS_PER_RUN):
            if not self.running: break
            
            params = self.get_random_params()
            # Inject scale_pos_weight to handle imbalance
            params['scale_pos_weight'] = scale_pos_weight
            
            try:
                model = XGBClassifier(**params)
                model.fit(X_train, y_train)
                metrics = self.evaluate_model(model, X_test, y_test)
                
                # Custom Score: Heavily penalize low precision
                score = (metrics['accuracy'] * 0.4) + (metrics['precision'] * 0.6)
                
                # Check if meets minimum standards
                if metrics['accuracy'] < MIN_ACCURACY or metrics['precision'] < MIN_PRECISION:
                    score = score * 0.5 # Penalty
                
                if score > best_score_run:
                    best_score_run = score
                    best_model_run = model
                    best_metrics_run = metrics
                    
                # Early exit if excellent model found
                if metrics['accuracy'] > 0.60 and metrics['precision'] > 0.55:
                    logger.info(f"[{symbol}] 🌟 Excellent model found! Acc={metrics['accuracy']}, Prec={metrics['precision']}")
                    break
                    
            except Exception as e:
                logger.error(f"[{symbol}] Trial failed: {e}")

        # Decide whether to save
        if best_metrics_run:
            is_qualified = (best_metrics_run['accuracy'] >= MIN_ACCURACY and 
                           best_metrics_run['precision'] >= MIN_PRECISION)
            
            # Improvement logic:
            # 1. If current is invalid (< standards) and new is valid -> SAVE
            # 2. If current is valid and new is better -> SAVE
            # 3. If current is invalid and new is invalid but better -> SAVE (Incremental improvement)
            
            current_is_qualified = (best_acc >= MIN_ACCURACY and best_prec >= MIN_PRECISION)
            
            should_save = False
            if is_qualified and not current_is_qualified:
                should_save = True
                logger.info(f"[{symbol}] ✅ New model qualified! Replacing invalid old model.")
            elif is_qualified and current_is_qualified:
                if best_metrics_run['accuracy'] > best_acc or best_metrics_run['precision'] > best_prec:
                    should_save = True
                    logger.info(f"[{symbol}] 🚀 New model improves performance.")
            elif not is_qualified and not current_is_qualified:
                if best_metrics_run['accuracy'] > best_acc and best_metrics_run['precision'] > best_prec:
                    should_save = True
                    logger.info(f"[{symbol}] 📈 Incremental improvement (still below standards).")
            
            if should_save:
                self.save_model(symbol, horizon, best_model_run, best_metrics_run)
                return True
            else:
                logger.info(f"[{symbol}] New model not better enough. Best run: Acc={best_metrics_run['accuracy']}, Prec={best_metrics_run['precision']}")
        
        return False

    def save_model(self, symbol, horizon, model, metrics):
        symbol_key = f"{symbol}USDT"
        model_filename = f"xgb_{symbol_key}_{horizon}m.joblib"
        tmp_path = os.path.join(MODELS_DIR, f"{model_filename}.tmp")
        final_path = os.path.join(MODELS_DIR, model_filename)
        
        # Atomic save
        joblib.dump(model, tmp_path)
        os.rename(tmp_path, final_path)
        
        metrics["model_path"] = model_filename
        metrics["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        
        if symbol_key not in self.metrics:
            self.metrics[symbol_key] = {}
        self.metrics[symbol_key][f"{horizon}m"] = metrics
        
        self.save_metrics()
        logger.info(f"[{symbol}] 💾 Model saved to {final_path}")

    def run(self):
        logger.info("Starting Auto Optimizer Loop...")
        logger.info(f"Target Symbols: {TARGET_SYMBOLS}")
        
        while self.running:
            # Shuffle symbols to be fair
            symbols = list(TARGET_SYMBOLS)
            random.shuffle(symbols)
            
            all_passed = True
            
            for symbol in symbols:
                if not self.running: break
                
                # Check status
                symbol_key = f"{symbol}USDT"
                metrics = self.metrics.get(symbol_key, {}).get("10m", {})
                acc = metrics.get("accuracy", 0)
                prec = metrics.get("precision", 0)
                
                passed = (acc >= MIN_ACCURACY and prec >= MIN_PRECISION)
                if not passed:
                    all_passed = False
                    logger.info(f"[{symbol}] Needs optimization (Acc={acc}, Prec={prec}). Starting...")
                try:
                    self.optimize_symbol(symbol)
                except Exception as e:
                    logger.error(f"[{symbol}] Critical error during optimization: {e}")
                    
                # Sleep to cool down
                time.sleep(5)
            else:
                # Randomly re-optimize even if passed, to find even better models (10% chance)
                # if random.random() < 0.1:
                #     logger.info(f"[{symbol}] Passed (Acc={acc}), but trying to improve...")
                #     try:
                #         self.optimize_symbol(symbol)
                #     except Exception as e:
                #         logger.error(f"[{symbol}] Critical error during improvement: {e}")
                # else:
                logger.info(f"[{symbol}] ✅ Passed standards. Skipping.")
                
            if all_passed:
                logger.info("🎉 All models passed standards! Optimizer stopping as requested.")
                break
            
            logger.info("Cycle complete. Sleeping 10s...")
            time.sleep(10)

if __name__ == "__main__":
    optimizer = AutoOptimizer()
    optimizer.run()
