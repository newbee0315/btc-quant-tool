
import sys
import os
import logging
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())
from src.backtest.backtest import SmartBacktester

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def run_feasibility_check(days=30):
    print(f"\n{'='*20} Running Feasibility Check (30 Days) {'='*20}")
    try:
        # Use BTC as proxy for portfolio performance
        backtester = SmartBacktester(initial_capital=1000.0, symbol='BTCUSDT')
        results = backtester.run(days=days, timeframe='5m')
        
        if results:
            final_balance = results['final_balance']
            initial_balance = 1000.0
            profit = final_balance - initial_balance
            return_pct = (profit / initial_balance) * 100
            
            # Annual Projection (Compound)
            # monthly_return = return_pct / 100
            # annual_return = ((1 + monthly_return) ** 12 - 1) * 100
            
            print(f"\nResults for {days} days:")
            print(f"Initial Balance: {initial_balance:.2f}")
            print(f"Final Balance:   {final_balance:.2f}")
            print(f"Profit:          {profit:.2f}")
            print(f"Return:          {return_pct:.2f}%")
            
            if profit > 0:
                monthly_rate = return_pct / 100
                projected_annual = ((1 + monthly_rate) ** (365/days) - 1) * 100
                projected_final = initial_balance * ((1 + monthly_rate) ** (365/days))
                print(f"Projected Annual Return: {projected_annual:.2f}%")
                print(f"Projected Final Balance (1 Year): {projected_final:.2f}")
            else:
                print("Strategy lost money in this period. Cannot project positive growth.")
                
            return results
        else:
            print("Backtest returned no results.")
            return None
            
    except Exception as e:
        print(f"Error running backtest: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    run_feasibility_check()
