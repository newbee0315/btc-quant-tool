
import sys
import os
import logging
import itertools
import pandas as pd
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())
from src.backtest.backtest import SmartBacktester
from src.utils.config_manager import config_manager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def run_optimization(days=30, symbol='BTCUSDT'):
    print(f"\n{'='*20} Running Strategy Parameter Optimization ({days} Days) {'='*20}")
    
    # Define Parameter Grid
    # Focused on ML Threshold and Risk/Reward Ratio (High Frequency)
    param_grid = {
        'ml_threshold': [0.65, 0.75, 0.85],
        'stop_loss': [0.01, 0.015, 0.02],
        'take_profit': [0.02, 0.03, 0.04], # Aim for 1:2 or 1:3 RR
        'ema_period': [100, 200], # Try faster EMA too
        'rsi_period': [14]   # Keep standard for now
    }
    
    keys = param_grid.keys()
    combinations = list(itertools.product(*param_grid.values()))
    
    print(f"Testing {len(combinations)} parameter combinations...")
    
    best_result = None
    best_params = None
    best_return = -999.0
    
    results_log = []
    
    # Initialize Backtester once to load data (optimization)
    # Note: SmartBacktester loads data in run(), so we might reload data each time unless we optimize that.
    # For now, let's just instantiate inside loop or rely on caching if implemented.
    # Actually, SmartBacktester fetches data in run(). To avoid re-fetching, we should hack it or modify it.
    # The Collector has caching, so repeated calls should be fast after first one.
    
    # Pre-warm cache
    print("Pre-fetching data...")
    temp_tester = SmartBacktester(symbol=symbol)
    temp_tester.collector.fetch_historical_data(timeframe='5m', days=days)
    
    count = 0
    for values in combinations:
        count += 1
        params = dict(zip(keys, values))
        
        # Skip invalid RR (TP should be > SL)
        if params['take_profit'] <= params['stop_loss']:
            continue
            
        print(f"\n[{count}/{len(combinations)}] Testing: {params}")
        
        try:
            # Update Strategy Config (Mocking or setting directly)
            # We need to set these on the strategy instance inside backtester
            
            backtester = SmartBacktester(initial_capital=1000.0, symbol=symbol)
            
            # Apply params
            backtester.strategy.ema_period = params['ema_period']
            backtester.strategy.rsi_period = params['rsi_period']
            # ml_threshold is passed to run()
            
            # Run Backtest
            res = backtester.run(
                days=days, 
                timeframe='5m',
                confidence_threshold=params['ml_threshold'],
                stop_loss=params['stop_loss'],
                take_profit=params['take_profit']
            )
            
            if res:
                final_bal = res['final_balance']
                profit = final_bal - 1000
                ret_pct = (profit / 1000) * 100
                trades_count = res['total_trades']
                win_rate = res['win_rate'] * 100
                
                print(f"  -> Return: {ret_pct:.2f}% | Trades: {trades_count} | WinRate: {win_rate:.1f}%")
                
                results_log.append({
                    **params,
                    'return': ret_pct,
                    'trades': trades_count,
                    'win_rate': win_rate,
                    'final_balance': final_bal
                })
                
                if ret_pct > best_return:
                    best_return = ret_pct
                    best_params = params
                    best_result = res
            
        except Exception as e:
            print(f"Error: {e}")
            
    # Summary
    print("\n" + "="*60)
    print("OPTIMIZATION RESULTS")
    print("="*60)
    
    if results_log:
        df_res = pd.DataFrame(results_log)
        df_res = df_res.sort_values('return', ascending=False)
        
        print("\nTop 5 Configurations:")
        print(df_res.head(5).to_string(index=False))
        
        if best_params:
            print(f"\nBest Parameters found: {best_params}")
            print(f"Best Return: {best_return:.2f}%")
            
            # Save to config recommendation file
            with open("recommended_config.json", "w") as f:
                import json
                json.dump(best_params, f, indent=4)
            print("Saved to recommended_config.json")
            
    else:
        print("No valid results found.")

if __name__ == "__main__":
    run_optimization()
