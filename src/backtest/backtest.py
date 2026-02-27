import pandas as pd
import numpy as np
import logging
import os
import sys
import joblib
from datetime import datetime
from typing import Dict, Any, List

# Add project root to path
sys.path.append(os.getcwd())

from src.strategies.trend_ml_strategy import TrendMLStrategy
from src.models.features import FeatureEngineer
from src.data.collector import FuturesDataCollector
from src.models.predictor import PricePredictor

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SmartBacktester:
    """
    Advanced Backtester supporting:
    - Futures Trading (Long/Short)
    - Dynamic Leverage & Margin Management
    - Liquidation Logic
    - Maker/Taker Fees
    - Integration with TrendMLStrategy
    """
    
    def __init__(self, initial_capital=1000.0, fee_rate=0.0005, symbol='BTCUSDT', proxy_url=None, enable_czsc=False):
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate
        self.symbol = symbol
        
        # Components
        self.strategy = TrendMLStrategy(enable_czsc=enable_czsc)
        self.predictor = PricePredictor(symbol=symbol)
        
        proxies = None
        if proxy_url:
            proxies = {"http": proxy_url, "https": proxy_url}
            
        self.collector = FuturesDataCollector(symbol=symbol, proxies=proxies)
    
    def run(self, days=30, timeframe='1m', confidence_threshold=0.75, stop_loss=None, take_profit=None):
        """
        Run backtest
        """
        logger.info(f"Starting backtest for {self.symbol} ({days} days, {timeframe})...")
        
        # 1. Fetch Historical Data
        # Note: fetch_historical_data uses self.symbol from collector init
        df = self.collector.fetch_historical_data(timeframe=timeframe, days=days)
        if df.empty:
            logger.error("No data fetched for backtest.")
            return None
            
        logger.info(f"Data fetched: {len(df)} candles.")
        
        # 2. Prepare Data (Features + ML Predictions + Indicators)
        full_df = self._prepare_data(df)
        if full_df is None or full_df.empty:
             return None

        # 3. Run Simulation
        results = self._simulate(full_df, confidence_threshold, stop_loss, take_profit)
        
        return results

    def _prepare_data(self, df):
        """
        Generate Features, Predictions and Indicators
        """
        try:
            # A. Generate Features for ML
            # Note: Using None for funding_df for now, assuming features don't strictly rely on it or it's handled
            full_df = FeatureEngineer.generate_features(df, None)
            
            # B. Generate Predictions (Batch)
            model_30m = self.predictor.models.get(30)
            model_10m = self.predictor.models.get(10)
            
            if not model_30m:
                logger.error("Model 30m not found. Cannot run backtest.")
                return None
                
            # Align features
            exclude_cols = ['timestamp', 'datetime', 'open', 'high', 'low', 'close', 'volume', 'target', 'date', 'future_return']
            exclude_cols += [c for c in full_df.columns if c.startswith('target_')]
            feature_cols = [c for c in full_df.columns if c not in exclude_cols]
            
            X = full_df[feature_cols]
            
            # Fix missing cols for 30m
            if hasattr(model_30m, "feature_names_in_"):
                 model_features = model_30m.feature_names_in_
                 missing_cols = set(model_features) - set(X.columns)
                 if missing_cols:
                      for c in missing_cols: X[c] = 0
                 X = X[model_features]
            
            full_df['ml_prob_30m'] = model_30m.predict_proba(X)[:, 1]
            
            # Fix missing cols for 10m
            if model_10m:
                X_10m = full_df[feature_cols]
                if hasattr(model_10m, "feature_names_in_"):
                     model_features = model_10m.feature_names_in_
                     missing_cols = set(model_features) - set(X_10m.columns)
                     if missing_cols:
                          for c in missing_cols: X_10m[c] = 0
                     X_10m = X_10m[model_features]
                full_df['ml_prob_10m'] = model_10m.predict_proba(X_10m)[:, 1]
            else:
                full_df['ml_prob_10m'] = 0.5
                
            # C. Calculate Strategy Indicators
            full_df = self.strategy.calculate_indicators(full_df)
            
            return full_df
            
        except Exception as e:
            logger.error(f"Data preparation failed: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _simulate(self, df, threshold, stop_loss=None, take_profit=None):
        balance = self.initial_capital
        equity_curve = []
        trades = []
        position = None 
        
        # Set threshold
        self.strategy.ml_threshold = threshold
        
        # Risk Management Settings
        risk_per_trade = 0.02 # 2% risk per trade
        max_position_pct = 0.5 # Max 50% of account per trade (Safety cap)

        logger.info("Running simulation loop...")
        
        for i in range(1, len(df)):
            current_row = df.iloc[i]
            prev_row = df.iloc[i-1]
            
            current_price = current_row['close']
            current_time = current_row['timestamp']
            
            # 1. Update Position Status (PnL, Liquidation)
            if position:
                mark_price = current_price
                entry_price = position['entry_price']
                side = position['side']
                amt = position['amount']
                leverage = position['leverage']
                margin = position['margin']
                
                # Calculate PnL
                if side == 'long':
                    u_pnl = (mark_price - entry_price) * amt
                else:
                    u_pnl = (entry_price - mark_price) * amt
                
                # Liquidation Check
                # Simple Logic: If loss >= margin, liquidated
                if u_pnl <= -margin:
                    logger.warning(f"LIQUIDATION at {current_time} Price: {mark_price}")
                    self._close_position(position, mark_price, current_time, balance, trades, "LIQUIDATION")
                    balance = trades[-1]['balance_after']
                    position = None
                    continue # Position gone
                
                # Check SL/TP (if set in position)
                sl_price = position.get('sl_price')
                tp_price = position.get('tp_price')
                
                exit_reason = None
                if side == 'long':
                    if sl_price and mark_price <= sl_price: exit_reason = "SL"
                    elif tp_price and mark_price >= tp_price: exit_reason = "TP"
                else:
                    if sl_price and mark_price >= sl_price: exit_reason = "SL"
                    elif tp_price and mark_price <= tp_price: exit_reason = "TP"
                    
                if exit_reason:
                    self._close_position(position, mark_price, current_time, balance, trades, exit_reason)
                    balance = trades[-1]['balance_after']
                    position = None
                    continue # Position closed, wait for next signal
            
            # 2. Get Strategy Signal
            # Construct extra_data as expected by strategy
            extra_data = {
                'ml_prediction': current_row['ml_prob_30m'],
                'ml_prediction_10m': current_row['ml_prob_10m'],
                'total_capital': balance,
                'risk_per_trade': 0.02 # Not used in full position mode but kept for compat
            }
            
            result = self.strategy.get_signal(current_row, prev_row, extra_data)
            signal = result['signal']
            trade_params = result['trade_params']
            
            # 3. Execute Signal
            # A. Close existing if reversal
            if position:
                if (position['side'] == 'long' and signal == -1) or \
                   (position['side'] == 'short' and signal == 1):
                    self._close_position(position, current_price, current_time, balance, trades, "Signal Reversal")
                    balance = trades[-1]['balance_after']
                    position = None
            
            # B. Open new position
            if not position and signal != 0:
                side = 'long' if signal == 1 else 'short'
                
                # Use strategy suggested params
                leverage = trade_params['leverage']
                sl_price = trade_params['sl_price']
                tp_price = trade_params['tp_price']
                
                # OVERRIDE if provided
                if stop_loss is not None:
                     if side == 'long': sl_price = current_price * (1 - stop_loss)
                     else: sl_price = current_price * (1 + stop_loss)
                
                if take_profit is not None:
                     if side == 'long': tp_price = current_price * (1 + take_profit)
                     else: tp_price = current_price * (1 - take_profit)
                
                # Calculate Position Size (Risk-Based Sizing)
                risk_amount = balance * risk_per_trade
                dist_to_sl = 0.05 # Default 5% if no SL
                
                if sl_price:
                    dist_to_sl = abs(current_price - sl_price) / current_price
                    if dist_to_sl == 0: dist_to_sl = 0.005 # Minimal distance
                
                # Position Value based on risk
                position_value = risk_amount / dist_to_sl
                
                # Cap position value based on account size and leverage (Safety)
                max_allowed_value = balance * leverage * max_position_pct
                position_value = min(position_value, max_allowed_value)
                
                # Calculate margin required
                margin_to_use = position_value / leverage
                amount = position_value / current_price
                
                # Fee
                fee = position_value * self.fee_rate
                
                if balance < (margin_to_use + fee):
                    # Adjust if not enough for fee
                    margin_to_use = balance - fee
                    position_value = margin_to_use * leverage
                    amount = position_value / current_price
                
                # Deduct Fee
                balance -= fee
                
                position = {
                    'side': side,
                    'amount': amount,
                    'entry_price': current_price,
                    'entry_time': current_time,
                    'leverage': leverage,
                    'margin': margin_to_use,
                    'fee_entry': fee,
                    'sl_price': sl_price,
                    'tp_price': tp_price,
                    'entry_reason': result.get('reason', [])
                }
                
            # Track Equity
            current_equity = balance
            if position:
                entry_price = position['entry_price']
                amt = position['amount']
                if position['side'] == 'long':
                    u_pnl = (current_price - entry_price) * amt
                else:
                    u_pnl = (entry_price - current_price) * amt
                current_equity += u_pnl
                
            equity_curve.append({
                'timestamp': current_time,
                'equity': current_equity,
                'drawdown': 0 # To calculate later
            })

        # End of Loop
        
        # Calculate Stats
        final_balance = balance
        total_trades = len(trades)
        winning_trades = [t for t in trades if t['realized_pnl'] > 0]
        win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0
        
        total_fees = sum(t['fee'] for t in trades)
        total_return_pct = ((final_balance - self.initial_capital) / self.initial_capital) * 100

        logger.info(f"Backtest completed. Initial: {self.initial_capital}, Final: {final_balance}")
        
        return {
            "initial_capital": self.initial_capital,
            "final_balance": final_balance,
            "total_trades": total_trades,
            "win_rate": win_rate,
            "total_fees": total_fees,
            "total_return_pct": total_return_pct,
            "equity_curve": equity_curve,
            "trades": trades
        }

    def _close_position(self, position, price, time, balance, trades, reason):
        side = position['side']
        amount = position['amount']
        entry_price = position['entry_price']
        leverage = position['leverage']
        
        # Calculate PnL
        if side == 'long':
            pnl = (price - entry_price) * amount
        else:
            pnl = (entry_price - price) * amount
            
        # Fee
        position_value = amount * price
        fee = position_value * self.fee_rate
        
        net_pnl = pnl - fee
        
        # Update Balance (Margin + PnL - Fee)
        # Note: 'balance' passed in already had entry fee deducted.
        # So we add back margin (which was "locked") + net_pnl
        # Wait, in my logic above: balance -= fee. Margin was NOT deducted from balance, just tracked as 'margin' locked.
        # Actually, usually balance = wallet balance. Margin is just a portion of it locked.
        # But here I treat 'balance' as 'available + locked'.
        # Let's refine:
        # In `_simulate`: balance -= fee. This is correct (wallet balance decreases).
        # When closing: balance += pnl - exit_fee.
        
        balance += (pnl - fee)
        
        # Ensure balance doesn't go negative (Liquidation should have caught this, but for safety)
        if balance < 0: balance = 0
        
        trades.append({
            "id": f"trade_{len(trades)+1}",
            "timestamp": int(time),
            "entry_time": int(position['entry_time']),
            "datetime": datetime.fromtimestamp(time/1000).strftime('%Y-%m-%d %H:%M:%S'),
            "side": "sell" if side == 'long' else 'buy',
            "entry_side": side,
            "price": price,
            "entry_price": entry_price,
            "amount": amount,
            "leverage": leverage,
            "pnl": pnl,
            "fee": fee + position['fee_entry'],
            "realized_pnl": pnl - (fee + position['fee_entry']),
            "reason": reason,
            "entry_reason": position.get('entry_reason', []),
            "balance_after": balance
        })
        
        return balance

    def run_sensitivity_analysis(self, horizon_minutes, threshold, days=30):
        """
        Run sensitivity analysis on SL/TP for a given threshold
        """
        results = []
        timeframe_map = {10: '10m', 30: '30m', 60: '1h', 240: '4h', 1440: '1d'}
        timeframe = timeframe_map.get(horizon_minutes, '1h')
        
        # Test ranges
        sl_range = [0.005, 0.01, 0.015, 0.02, 0.03]
        tp_range = [0.01, 0.015, 0.02, 0.03, 0.04, 0.05]
        
        # Fetch data once
        df = self.collector.fetch_historical_data(timeframe=timeframe, days=days)
        if df.empty: return []
        full_df = self._prepare_data(df)
        if full_df is None or full_df.empty: return []

        for sl in sl_range:
            for tp in tp_range:
                res = self._simulate(full_df, threshold, stop_loss=sl, take_profit=tp)
                results.append({
                    "sl": sl,
                    "tp": tp,
                    "total_return_pct": (res['final_balance'] - self.initial_capital) / self.initial_capital * 100,
                    "win_rate": res['win_rate'],
                    "total_trades": res['total_trades']
                })
        return results

    def run_optimization(self, horizon_minutes, stop_loss, take_profit, days=30):
        """
        Run optimization on Threshold for given SL/TP
        """
        results = []
        timeframe_map = {10: '10m', 30: '30m', 60: '1h', 240: '4h', 1440: '1d'}
        timeframe = timeframe_map.get(horizon_minutes, '1h')
        
        df = self.collector.fetch_historical_data(timeframe=timeframe, days=days)
        if df.empty: return []
        full_df = self._prepare_data(df)
        if full_df is None or full_df.empty: return []
        
        thresholds = [0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85]
        
        for th in thresholds:
            res = self._simulate(full_df, th, stop_loss=stop_loss, take_profit=take_profit)
            results.append({
                "threshold": th,
                "total_return_pct": (res['final_balance'] - self.initial_capital) / self.initial_capital * 100,
                "total_trades": res['total_trades'],
                "win_rate": res['win_rate']
            })
        return results

if __name__ == "__main__":
    backtester = SmartBacktester(symbol='BTCUSDT')
    results = backtester.run(days=7, timeframe='1h')
    
    if results:
        print(f"Backtest Complete.")
        print(f"Final Balance: {results['final_balance']:.2f}")
        print(f"Trades: {results['total_trades']}")
        print(f"Win Rate: {results['win_rate']:.2%}")
