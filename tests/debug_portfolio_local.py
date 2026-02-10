import sys
import os
import logging
import asyncio

# Add project root
sys.path.append(os.getcwd())

from src.strategies.portfolio_manager import PortfolioManager

# Configure logging
logging.basicConfig(level=logging.DEBUG)

def run():
    print("Initializing PortfolioManager...")
    # Use proxy if needed
    proxy_url = "http://127.0.0.1:33210"
    
    pm = PortfolioManager(proxy_url=proxy_url)
    
    print("Running Scan...")
    results = pm.scan_market()
    print(f"Results: {len(results)}")
    if not results:
        print("No results returned.")
    else:
        print(f"Sample: {results[0]}")

if __name__ == "__main__":
    run()
