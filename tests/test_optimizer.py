import sys
import os
import asyncio
import logging
import json

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.optimizer.strategy_optimizer import StrategyOptimizer

# Configure logging
logging.basicConfig(level=logging.INFO)

async def main():
    print("Testing StrategyOptimizer...")
    
    # Load config
    config_path = "trader_config.json"
    if not os.path.exists(config_path):
        print("Config not found, skipping.")
        return

    with open(config_path, "r") as f:
        config = json.load(f)
    
    optimizer = StrategyOptimizer(
        api_key=config.get("api_key", ""),
        api_secret=config.get("api_secret", ""),
        proxy_url=config.get("proxy_url")
    )
    
    # Run for 7 days
    suggestions = await optimizer.run_analysis(days=7)
    
    print("\n--- Suggestions ---")
    for s in suggestions:
        print(f"- {s}")
        
    print("\nCheck optimization_report.md for details.")

if __name__ == "__main__":
    asyncio.run(main())
