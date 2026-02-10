import sys
import os
sys.path.append(os.getcwd())

from src.backtest.backtest import SmartBacktester
import pandas as pd

if __name__ == "__main__":
    backtester = SmartBacktester(symbol='BTCUSDT')
    # Run for 30 days
    results = backtester.run(days=30, timeframe='1h')
    
    if results:
        print("\n=== Backtest Results ===")
        print(f"Final Balance: {results['final_balance']:.2f}")
        print(f"Return: {(results['final_balance'] - 1000)/1000:.2%}")
        print(f"Total Trades: {results['total_trades']}")
        print(f"Win Rate: {results['win_rate']:.2%}")
        
        if results['trades']:
            print("\nLast 5 Trades:")
            for t in results['trades'][-5:]:
                print(f"{t['datetime']} {t['side']} PnL: {t['realized_pnl']:.2f} Reason: {t['reason']}")
                
        # Save equity curve to csv for inspection
        pd.DataFrame(results['equity_curve']).to_csv('backtest_equity.csv', index=False)
        print("\nEquity curve saved to backtest_equity.csv")
    else:
        print("Backtest failed.")
