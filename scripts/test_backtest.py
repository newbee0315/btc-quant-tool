import sys
import os
import pandas as pd
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# Add project root to path
sys.path.append(os.getcwd())
from src.backtest.backtest import SmartBacktester

def run_test(enable_czsc, days=7):
    print(f"\n{'='*20} Running Backtest (CZSC={enable_czsc}) {'='*20}")
    try:
        backtester = SmartBacktester(symbol='BTCUSDT', enable_czsc=enable_czsc)
        results = backtester.run(days=days, timeframe='5m')
        return results
    except Exception as e:
        print(f"Error running backtest: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    days = 14 # Run for 2 weeks to get significant data
    
    print(f"Starting comparison test for {days} days...")
    
    # 1. Without CZSC
    results_base = run_test(enable_czsc=False, days=days)
    
    # 2. With CZSC
    results_czsc = run_test(enable_czsc=True, days=days)
    
    if results_base and results_czsc:
        # 3. Comparison
        print("\n" + "="*60)
        print(f"COMPARISON REPORT ({days} Days)")
        print("="*60)
        
        headers = ["Metric", "Without CZSC", "With CZSC", "Diff"]
        print(f"{headers[0]:<20} {headers[1]:<15} {headers[2]:<15} {headers[3]:<15}")
        print("-" * 65)
        
        # Calculate Max Drawdown manually
        def calculate_max_drawdown(equity_curve):
            if not equity_curve: return 0.0
            equities = [e['equity'] for e in equity_curve]
            max_eq = equities[0]
            max_dd = 0.0
            for eq in equities:
                if eq > max_eq: max_eq = eq
                dd = (max_eq - eq) / max_eq if max_eq > 0 else 0
                if dd > max_dd: max_dd = dd
            return max_dd

        metrics = [
            ("Final Balance", results_base['final_balance'], results_czsc['final_balance']),
            ("Return %", (results_base['final_balance']-1000)/10, (results_czsc['final_balance']-1000)/10),
            ("Total Trades", results_base['total_trades'], results_czsc['total_trades']),
            ("Win Rate %", results_base['win_rate'] * 100, results_czsc['win_rate'] * 100),
            ("Total PnL", results_base['final_balance'] - 1000, results_czsc['final_balance'] - 1000),
            ("Max Drawdown %", calculate_max_drawdown(results_base['equity_curve']) * 100, calculate_max_drawdown(results_czsc['equity_curve']) * 100),
        ]
        
        for name, v1, v2 in metrics:
            diff = v2 - v1
            print(f"{name:<20} {v1:<15.2f} {v2:<15.2f} {diff:<15.2f}")
            
        print("-" * 65)
        
        # Save results
        pd.DataFrame(results_base['equity_curve']).to_csv('backtest_equity_base.csv', index=False)
        pd.DataFrame(results_czsc['equity_curve']).to_csv('backtest_equity_czsc.csv', index=False)
        print("\nEquity curves saved to CSV files.")
        
        # Analyze specific CZSC trades
        czsc_trades = results_czsc['trades']
        print(f"\nTotal trades in CZSC mode: {len(czsc_trades)}")
             
        czsc_triggered_trades = []
        for t in czsc_trades:
            # Check entry reasons
            entry_reasons = t.get('entry_reason', [])
            
            is_czsc = False
            if isinstance(entry_reasons, str):
                 if "缠论" in entry_reasons: is_czsc = True
            elif isinstance(entry_reasons, list):
                 if any("缠论" in r for r in entry_reasons): is_czsc = True
            
            if is_czsc:
                czsc_triggered_trades.append(t)
                
        print(f"\nTotal trades triggered/confirmed by CZSC (Filtered): {len(czsc_triggered_trades)}")
                
    else:
        print("One or both backtests failed.")
