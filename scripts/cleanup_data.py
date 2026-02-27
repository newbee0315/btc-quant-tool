import os
import shutil

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../src/data/raw') # Assuming running from scripts/
if not os.path.exists(DATA_DIR):
    # Fallback to absolute path or relative from root
    DATA_DIR = os.path.join(os.getcwd(), 'data/raw')

ARCHIVE_DIR = os.path.join(DATA_DIR, 'archive')
if not os.path.exists(ARCHIVE_DIR):
    os.makedirs(ARCHIVE_DIR)

KEEP_SYMBOLS = [
    'BTC', 'ETH', 'SOL', 'BNB', 'DOGE',
    'XRP', 'PEPE', 'AVAX', 'LINK', 'ADA',
    'TRX', 'LDO', 'BCH', 'OP'
]

def clean_data():
    files = os.listdir(DATA_DIR)
    moved_count = 0
    for f in files:
        if not f.endswith('.csv'):
            continue
            
        # Format is SYMBOL_TIMEFRAME.csv, e.g. BTCUSDT_1m.csv
        # Symbol usually has USDT appended if not present in the split logic, 
        # but fetch script saves as "BTCUSDT_1m.csv" from "BTC/USDT:USDT"
        
        # Extract base symbol
        base_name = f.split('_')[0] # e.g. BTCUSDT
        
        # Check if it starts with any of our keep symbols
        keep = False
        for sym in KEEP_SYMBOLS:
            # Check for exact match with USDT suffix
            if base_name == f"{sym}USDT":
                keep = True
                break
        
        if not keep:
            src = os.path.join(DATA_DIR, f)
            dst = os.path.join(ARCHIVE_DIR, f)
            print(f"Moving {f} to archive...")
            shutil.move(src, dst)
            moved_count += 1
            
    print(f"Cleanup complete. Moved {moved_count} files to {ARCHIVE_DIR}")

if __name__ == "__main__":
    clean_data()
