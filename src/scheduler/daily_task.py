
import os
import sys
import shutil
import logging
import asyncio
import pandas as pd
import time
from datetime import datetime
import pytz
import json
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.data.collector import CryptoDataCollector
# Use multi-coin training
from src.models.train_multicoin import main as train_multicoin_main
from src.notification.feishu import FeishuBot
from src.optimizer.strategy_optimizer import StrategyOptimizer

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
DATA_DIR = "data/raw"
SYMBOLS = [
    'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'DOGEUSDT',
    'XRPUSDT', 'PEPEUSDT', 'AVAXUSDT', 'LINKUSDT', 'ADAUSDT',
    'TRXUSDT', 'LDOUSDT', 'BCHUSDT', 'OPUSDT'
]

class DailyUpdateManager:
    def __init__(self):
        self.data_dir = DATA_DIR
        self.backup_dir = os.path.join(self.data_dir, "backups")
        self.feishu = FeishuBot(os.getenv("FEISHU_WEBHOOK_URL"))
        
        # Ensure dirs exist
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)

    async def run(self):
        """Main execution entry point"""
        start_time = time.time()
        logger.info("🚀 Starting Daily Update Task (Multi-Coin)...")
        
        try:
            # 1. Update Data for all symbols
            total_rows_added = 0
            updated_symbols = []
            
            for symbol in SYMBOLS:
                try:
                    rows = await self._update_symbol_data(symbol)
                    if rows > 0:
                        total_rows_added += rows
                        updated_symbols.append(symbol)
                except Exception as e:
                    logger.error(f"Failed to update {symbol}: {e}")
            
            # 2. Retrain Models (if any data updated)
            if total_rows_added > 0:
                logger.info(f"Data updated for {len(updated_symbols)} symbols. Starting model retraining...")
                # Run training in thread pool to avoid blocking async loop
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, train_multicoin_main)
                training_status = "Success"
            else:
                logger.info("No new data added for any symbol. Skipping retraining.")
                training_status = "Skipped (No new data)"

            # 3. Auto-Optimization Analysis
            logger.info("🧠 Starting Strategy Optimization Analysis...")
            opt_summary = "Skipped"
            try:
                # Load config safely
                config_path = "trader_config.json"
                if not os.path.exists(config_path):
                     config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "trader_config.json")
                
                if os.path.exists(config_path):
                    with open(config_path, "r") as f:
                        config = json.load(f)
                    
                    optimizer = StrategyOptimizer(
                        api_key=config.get("api_key", ""),
                        api_secret=config.get("api_secret", ""),
                        proxy_url=config.get("proxy_url")
                    )
                    
                    suggestions = await optimizer.run_analysis(days=7)
                    if suggestions:
                        opt_summary = f"Generated {len(suggestions)} suggestions"
                    else:
                        opt_summary = "No suggestions"
                else:
                    opt_summary = "Config not found"
            except Exception as e:
                logger.error(f"Optimization failed: {e}")
                opt_summary = f"Error: {str(e)[:50]}"

            # 4. Notify Success
            duration = time.time() - start_time
            await self._notify_success(total_rows_added, training_status, opt_summary, duration)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Daily Update Failed: {e}", exc_info=True)
            await self._notify_failure(str(e))
            return False

    async def _update_symbol_data(self, symbol):
        """Update data for a single symbol"""
        file_path = os.path.join(self.data_dir, f"{symbol}_1m.csv")
        collector = CryptoDataCollector(symbol=symbol)
        
        # 1. Load existing
        if os.path.exists(file_path):
            df = pd.read_csv(file_path)
            if 'timestamp' not in df.columns or df.empty:
                last_ts = int((datetime.now().timestamp() - 180*24*3600) * 1000) # 180 days default
                df = pd.DataFrame()
            else:
                last_ts = int(df['timestamp'].max())
        else:
            last_ts = int((datetime.now().timestamp() - 180*24*3600) * 1000)
            df = pd.DataFrame()

        # 2. Fetch new
        now_ts = int(time.time() * 1000)
        if now_ts - last_ts < 60000:
            return 0
            
        logger.info(f"[{symbol}] Fetching data since {datetime.fromtimestamp(last_ts/1000)}")
        new_df = collector.fetch_data_range(last_ts + 1, now_ts)
        
        if new_df.empty:
            return 0
            
        logger.info(f"[{symbol}] Fetched {len(new_df)} new rows.")
        
        # 3. Merge and Save
        if not df.empty:
            # Ensure columns match
            new_df = new_df[df.columns]
            updated_df = pd.concat([df, new_df], ignore_index=True)
        else:
            updated_df = new_df
            
        # Deduplicate just in case
        updated_df = updated_df.drop_duplicates(subset=['timestamp'])
        updated_df = updated_df.sort_values('timestamp').reset_index(drop=True)
        
        # 4. Save (Atomic Write)
        temp_file = file_path + ".tmp"
        try:
            updated_df.to_csv(temp_file, index=False)
            os.replace(temp_file, file_path)
            logger.info(f"[{symbol}] ✅ Data updated safely. Total rows: {len(updated_df)}")
        except Exception as e:
            if os.path.exists(temp_file):
                os.remove(temp_file)
            raise e
        
        return len(new_df)

    async def _notify_success(self, rows_added, training_status, opt_summary, duration):
        beijing_tz = pytz.timezone('Asia/Shanghai')
        now_str = datetime.now(beijing_tz).strftime("%Y-%m-%d %H:%M:%S")
        
        message = (
            f"✅ **Daily Update Completed**\n"
            f"🕒 Time: {now_str}\n"
            f"⏱️ Duration: {duration:.2f}s\n"
            f"📊 Rows Added: {rows_added}\n"
            f"🧠 Training: {training_status}\n"
            f"💡 Optimization: {opt_summary}"
        )
        
        self.feishu.send_text(message)

    async def _notify_failure(self, error):
        self.feishu.send_text(f"❌ **Daily Update Failed**\nError: {error}")

if __name__ == "__main__":
    manager = DailyUpdateManager()
    asyncio.run(manager.run())
