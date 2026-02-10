import sys
import os
import logging

# Add project root
sys.path.append(os.getcwd())

from src.backtest.backtest import SmartBacktester

# Configure logging to stdout
logging.basicConfig(level=logging.DEBUG)

def run():
    print("Initializing Backtester...")
    # Use proxy if needed
    proxy_url = "http://127.0.0.1:33210"
    
    bt = SmartBacktester(symbol='BTCUSDT', proxy_url=proxy_url)
    
    print("Running Sensitivity Analysis...")
    results = bt.run_sensitivity_analysis(horizon_minutes=60, threshold=0.7, days=2)
    print(f"Results: {len(results)}")
    if not results:
        print("No results returned.")
    else:
        print(f"Sample: {results[0]}")

if __name__ == "__main__":
    run()
