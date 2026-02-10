import sys
import os
import json
import time
import logging
from datetime import datetime

# Add project root
sys.path.append(os.getcwd())

from scripts.fetch_multicoin_data import get_top_volume_symbols, fetch_history_for_symbol, DATA_DIR
from src.models.train_multicoin import main as train_main

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("slow_fetch.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

STATE_FILE = "fetch_state.json"
TIMEFRAMES = ['1m', '5m', '1h']
DAYS = 180

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {"done": []}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

def main():
    logger.info("🚀 Starting Slow Fetch & Train Process")
    
    target_symbols = get_top_volume_symbols(limit=30)
    # Sanitize symbols to match DATA_DIR filenames (BTC/USDT:USDT -> BTCUSDT)
    clean_targets = [s.split('/')[0] + "USDT" for s in target_symbols]
    # Map back for fetching
    symbol_map = {s.split('/')[0] + "USDT": s for s in target_symbols}
    
    # Check what we already have in disk (Initialize state if empty)
    # This avoids re-fetching what we manually downloaded
    state = load_state()
    if not state["done"]:
        existing_files = os.listdir(DATA_DIR)
        pre_existing = set()
        for f in existing_files:
            if f.endswith("_1m.csv"):
                sym = f.replace("_1m.csv", "")
                if sym in clean_targets:
                    pre_existing.add(sym)
        
        if pre_existing:
            logger.info(f"Found {len(pre_existing)} existing symbols on disk. Marking as done.")
            state["done"] = list(pre_existing)
            save_state(state)

    while True:
        state = load_state()
        done_list = state.get("done", [])
        
        # Identify pending
        pending = [s for s in clean_targets if s not in done_list]
        
        if not pending:
            logger.info("✅ All data fetched! Starting Model Training...")
            train_main()
            logger.info("🎉 Process Complete!")
            break
            
        # Pick next 2
        batch = pending[:2]
        logger.info(f"⏳ Fetching batch: {batch}")
        
        for clean_sym in batch:
            raw_sym = symbol_map[clean_sym]
            try:
                for tf in TIMEFRAMES:
                    fetch_history_for_symbol(raw_sym, tf, DAYS)
                
                # Mark as done
                done_list.append(clean_sym)
                state["done"] = done_list
                save_state(state)
                logger.info(f"✅ Finished {clean_sym}")
                
            except Exception as e:
                logger.error(f"❌ Failed {clean_sym}: {e}")
                # Don't mark as done, retry next time
        
        if len(pending) > 2:
            logger.info("💤 Sleeping for 2 hours...")
            time.sleep(2 * 60 * 60) # 2 hours
        else:
            # Last batch done, loop will break next time
            pass

if __name__ == "__main__":
    main()
