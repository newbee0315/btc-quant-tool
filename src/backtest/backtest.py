import pandas as pd
import numpy as np
import joblib
import os
import sys
import logging
import json
from datetime import datetime
import matplotlib.pyplot as plt

# Add project root to path
sys.path.append(os.getcwd())

from src.models.features import FeatureEngineer
from src.data.collector import CryptoDataCollector

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MODELS_DIR = "src/models/saved_models"
DATA_FILE = "src/data/btc_history_1m.csv"

class Backtester:
    def __init__(self, initial_capital=10000, transaction_fee=0.0005):
        self.initial_capital = initial_capital
        self.transaction_fee = transaction_fee
        self.models = {}
        self.load_models()
        
    def load_models(self):
        for h in [10, 30, 60]:
            path = os.path.join(MODELS_DIR, f"xgb_model_{h}m.joblib")
            if os.path.exists(path):
                self.models[h] = joblib.load(path)
                
    def run_backtest(self, horizon_minutes=60, confidence_threshold=0.6, stop_loss=0.01, take_profit=0.02):
        """
        Smart backtest strategy:
        - Entry: If Prob(UP) > threshold.
        - Exit: 
            1. Stop Loss hit (-stop_loss)
            2. Take Profit hit (+take_profit)
            3. Signal Reversal (Prob < 0.5)
            4. Time Limit (horizon_minutes reached)
        """
        logger.info(f"Running backtest for {horizon_minutes}m horizon (SL={stop_loss}, TP={take_profit})...")
        
        # Load data
        if not os.path.exists(DATA_FILE):
            logger.error("Data file not found.")
            return
            
        df = pd.read_csv(DATA_FILE)
        
        # Need external data for features?
        try:
            fng_df = pd.read_csv("src/data/fng_history.csv")
            if 'datetime' in fng_df.columns:
                fng_df['datetime'] = pd.to_datetime(fng_df['datetime'])
        except:
            fng_df = None
            
        # Generate features
        data = FeatureEngineer.generate_features(df, fng_df)
        data = data.dropna()
        
        if horizon_minutes not in self.models:
            logger.error(f"Model for {horizon_minutes}m not found.")
            return
            
        model = self.models[horizon_minutes]
        
        # Prepare features for prediction
        exclude_cols = ['timestamp', 'datetime', 'open', 'high', 'low', 'close', 'volume', 'target', 'date']
        feature_cols = [c for c in data.columns if c not in exclude_cols]
        
        X = data[feature_cols]
        
        # Predict all probabilities at once
        probs = model.predict_proba(X)[:, 1]
        
        return self._simulate(data, probs, horizon_minutes, confidence_threshold, stop_loss, take_profit)

    def _simulate(self, data, probs, horizon_minutes, confidence_threshold, stop_loss, take_profit):
        # Simulation
        capital = self.initial_capital
        position = 0 # 0: None, 1: Long
        entry_price = 0
        entry_idx = 0
        trades = []
        equity_curve = [capital]
        total_fees = 0
        cooldown_counter = 0 # Candles to wait before next entry
        
        closes = data['close'].values
        highs = data['high'].values
        lows = data['low'].values
        timestamps = data['datetime'].values
        n = len(data)
        
        i = 0
        while i < n - 1:
            prob = probs[i]
            current_price = closes[i]
            current_time = timestamps[i]
            
            # Decrease cooldown
            if cooldown_counter > 0:
                cooldown_counter -= 1
            
            # --- Exit Logic (if in position) ---
            if position == 1:
                # Check for Stop Loss / Take Profit within the candle (Low/High)
                # We assume we entered at 'close' of previous candle, so we check current candle's High/Low
                # BUT: In this loop structure, 'current_price' is close[i]. 
                # If we entered at i-1, we are now at i.
                
                duration = i - entry_idx
                
                # Check High/Low of current candle for TP/SL
                # This is an approximation. In reality, we don't know which happened first (High or Low).
                # Conservative approach: Check SL on Low first.
                
                price_change_low = (lows[i] - entry_price) / entry_price
                price_change_high = (highs[i] - entry_price) / entry_price
                
                exit_reason = None
                exit_price = 0
                
                # 1. Stop Loss
                if price_change_low <= -stop_loss:
                    exit_reason = "SL"
                    exit_price = entry_price * (1 - stop_loss)
                
                # 2. Take Profit (only if SL not hit, or assuming TP happened before SL - tricky)
                # Let's stick to conservative: If SL hit, we exit at SL. If not, check TP.
                elif price_change_high >= take_profit:
                    exit_reason = "TP"
                    exit_price = entry_price * (1 + take_profit)
                
                # 3. Time Limit
                elif duration >= horizon_minutes:
                    exit_reason = "Time"
                    exit_price = closes[i]
                
                # 4. Signal Reversal (Dynamic Exit)
                # If probability drops significantly (e.g. < 0.4), exit early
                elif prob < 0.4: 
                    exit_reason = "Reversal"
                    exit_price = closes[i]
                    
                if exit_reason:
                    # Execute Sell
                    btc_amount = capital / entry_price
                    gross_capital = btc_amount * exit_price
                    fee = gross_capital * self.transaction_fee
                    capital = gross_capital - fee
                    total_fees += fee
                    
                    trades.append({
                        "entry_time": timestamps[entry_idx],
                        "entry_price": entry_price,
                        "exit_time": current_time,
                        "exit_price": exit_price,
                        "reason": exit_reason,
                        "return": (exit_price - entry_price) / entry_price,
                        "capital_after": capital
                    })
                    
                    position = 0
                    entry_price = 0
                    entry_idx = 0
                    cooldown_counter = 5 # Wait 5 minutes before re-entering
            
            # --- Entry Logic (if no position) ---
            elif position == 0 and cooldown_counter == 0:
                if prob > confidence_threshold:
                    # Buy at Close
                    position = 1
                    entry_price = current_price
                    entry_idx = i
                    fee = capital * self.transaction_fee
                    capital -= fee
                    total_fees += fee
            
            # Convert numpy datetime64 to Unix timestamp (seconds)
            ts = int(pd.Timestamp(current_time).timestamp())
            equity_curve.append({'time': ts, 'value': capital})
            i += 1
            
        # Force close at end
        if position == 1:
            btc_amount = capital / entry_price
            gross_capital = btc_amount * closes[-1]
            fee = gross_capital * self.transaction_fee
            capital = gross_capital - fee
            total_fees += fee
            
            trades.append({
                "entry_time": timestamps[entry_idx],
                "entry_price": entry_price,
                "exit_time": timestamps[-1],
                "exit_price": closes[-1],
                "reason": "End",
                "return": (closes[-1] - entry_price) / entry_price,
                "capital_after": capital
            })

        # Stats
        total_return = (capital - self.initial_capital) / self.initial_capital * 100
        win_rate = len([t for t in trades if t['return'] > 0]) / len(trades) if trades else 0
        
        # Date Range
        if len(timestamps) > 0:
            start_date = str(timestamps[0])
            end_date = str(timestamps[-1])
            try:
                duration_days = (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days
            except:
                duration_days = 0
        else:
            start_date = "N/A"
            end_date = "N/A"
            duration_days = 0

        results = {
            "initial_capital": self.initial_capital,
            "final_capital": capital,
            "total_fees": total_fees,
            "total_return_pct": total_return,
            "total_trades": len(trades),
            "win_rate": win_rate,
            "start_date": start_date,
            "end_date": end_date,
            "duration_days": duration_days
        }
        
        # Convert timestamps to strings for JSON serialization
        for t in trades:
            t['entry_time'] = str(t['entry_time'])
            t['exit_time'] = str(t['exit_time'])
            
        return results, trades, equity_curve
        
    def run_optimization(self, horizon_minutes=60, stop_loss=0.01, take_profit=0.02):
        """
        Run backtest for multiple thresholds (0.5 to 0.95)
        """
        # Load data (Same as run_backtest)
        if not os.path.exists(DATA_FILE):
            logger.error("Data file not found.")
            return []
            
        df = pd.read_csv(DATA_FILE)
        
        # Need external data for features?
        try:
            fng_df = pd.read_csv("src/data/fng_history.csv")
            if 'datetime' in fng_df.columns:
                fng_df['datetime'] = pd.to_datetime(fng_df['datetime'])
        except:
            fng_df = None
            
        # Generate features
        data = FeatureEngineer.generate_features(df, fng_df)
        data = data.dropna()
        
        if horizon_minutes not in self.models:
            logger.error(f"Model for {horizon_minutes}m not found.")
            return []
            
        model = self.models[horizon_minutes]
        
        # Prepare features for prediction
        exclude_cols = ['timestamp', 'datetime', 'open', 'high', 'low', 'close', 'volume', 'target', 'date']
        feature_cols = [c for c in data.columns if c not in exclude_cols]
        
        X = data[feature_cols]
        
        # Predict all probabilities at once
        probs = model.predict_proba(X)[:, 1]
        
        results_list = []
        
        # Loop thresholds from 0.5 to 0.95
        for threshold in [round(x * 0.05, 2) for x in range(10, 20)]:
            res, _, _ = self._simulate(data, probs, horizon_minutes, threshold, stop_loss, take_profit)
            results_list.append({
                "threshold": threshold,
                "total_return_pct": res["total_return_pct"],
                "total_trades": res["total_trades"],
                "win_rate": res["win_rate"]
            })
            
        return results_list

    def run_sensitivity_analysis(self, horizon_minutes=60, confidence_threshold=0.7):
        """
        Run backtest for a grid of SL and TP values to find the sweet spot.
        """
        # Load data once
        if not os.path.exists(DATA_FILE):
            logger.error("Data file not found.")
            return []
            
        df = pd.read_csv(DATA_FILE)
        
        # Need external data for features?
        try:
            fng_df = pd.read_csv("src/data/fng_history.csv")
            if 'datetime' in fng_df.columns:
                fng_df['datetime'] = pd.to_datetime(fng_df['datetime'])
        except:
            fng_df = None
            
        # Generate features
        data = FeatureEngineer.generate_features(df, fng_df)
        data = data.dropna()
        
        if horizon_minutes not in self.models:
            logger.error(f"Model for {horizon_minutes}m not found.")
            return []
            
        model = self.models[horizon_minutes]
        
        # Prepare features for prediction
        exclude_cols = ['timestamp', 'datetime', 'open', 'high', 'low', 'close', 'volume', 'target', 'date']
        feature_cols = [c for c in data.columns if c not in exclude_cols]
        X = data[feature_cols]
        probs = model.predict_proba(X)[:, 1]
        
        results_grid = []
        
        # Define Grid
        sl_range = [0.005, 0.01, 0.015, 0.02, 0.025, 0.03] # 0.5% to 3%
        tp_range = [0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05, 0.06] # 1% to 6%
        
        for sl in sl_range:
            for tp in tp_range:
                res, _, _ = self._simulate(data, probs, horizon_minutes, confidence_threshold, sl, tp)
                results_grid.append({
                    "sl": sl,
                    "tp": tp,
                    "total_return_pct": res["total_return_pct"],
                    "win_rate": res["win_rate"],
                    "total_trades": res["total_trades"]
                })
                
        return results_grid


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Run BTC Backtest')
    parser.add_argument('--horizon', type=int, default=60, help='Prediction horizon in minutes (10, 30, 60)')
    parser.add_argument('--threshold', type=float, default=0.6, help='Confidence threshold (0.5-1.0)')
    parser.add_argument('--sl', type=float, default=0.01, help='Stop Loss percentage (e.g. 0.01 for 1%)')
    parser.add_argument('--tp', type=float, default=0.03, help='Take Profit percentage (e.g. 0.03 for 3%)')
    
    args = parser.parse_args()
    
    bt = Backtester()
    bt.run_backtest(
        horizon_minutes=args.horizon, 
        confidence_threshold=args.threshold, 
        stop_loss=args.sl, 
        take_profit=args.tp
    )
