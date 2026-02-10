import os
import sys
import shutil
import logging
import asyncio
import pandas as pd
import time
from datetime import datetime
import pytz

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.data.collector import CryptoDataCollector
from src.models.train import train_models, DATA_FILE, MODELS_DIR
from src.notification.feishu import FeishuBot
from src.optimizer.strategy_optimizer import StrategyOptimizer
import json
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DailyUpdateManager:
    def __init__(self):
        self.data_file = DATA_FILE
        self.backup_dir = os.path.join(os.path.dirname(DATA_FILE), "backups")
        self.collector = CryptoDataCollector()
        self.feishu = FeishuBot(os.getenv("FEISHU_WEBHOOK_URL"))
        
        # Ensure backup dir exists
        os.makedirs(self.backup_dir, exist_ok=True)

    async def run(self):
        """Main execution entry point"""
        start_time = time.time()
        logger.info("🚀 Starting Daily Update Task...")
        
        try:
            # 1. Backup Data
            self._backup_data()
            
            # 2. Update Data
            rows_added = await self._update_data()
            
            # 3. Retrain Models
            if rows_added > 0:
                logger.info("Data updated. Starting model retraining...")
                # Run training in thread pool to avoid blocking async loop
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, train_models)
                training_status = "Success"
            else:
                logger.info("No new data added. Skipping retraining.")
                training_status = "Skipped (No new data)"

            # 4. Auto-Optimization Analysis
            logger.info("🧠 Starting Strategy Optimization Analysis...")
            opt_summary = "Skipped"
            try:
                # Load config safely
                config_path = "trader_config.json"
                # Try to find config if running from src/scheduler
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

            # 5. Notify Success
            duration = time.time() - start_time
            await self._notify_success(rows_added, training_status, opt_summary, duration)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Daily Update Failed: {e}", exc_info=True)
            await self._notify_failure(str(e))
            # Restore backup if update failed? 
            # Ideally yes, but only if data file was corrupted. 
            # For now, we assume _update_data is atomic enough (reads then overwrites).
            return False

    def _backup_data(self):
        """Create a backup of the current data file"""
        if os.path.exists(self.data_file):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(self.backup_dir, f"btc_history_1m_{timestamp}.csv")
            shutil.copy2(self.data_file, backup_path)
            logger.info(f"✅ Data backup created: {backup_path}")
            
            # Cleanup old backups (keep last 7 days)
            self._cleanup_backups()
        else:
            logger.warning("⚠️ No existing data file to backup.")

    def _cleanup_backups(self):
        """Keep only last 7 backups"""
        try:
            files = sorted(
                [os.path.join(self.backup_dir, f) for f in os.listdir(self.backup_dir) if f.startswith("btc_history_1m_")],
                key=os.path.getmtime
            )
            if len(files) > 7:
                for f in files[:-7]:
                    os.remove(f)
                    logger.info(f"Deleted old backup: {f}")
        except Exception as e:
            logger.warning(f"Backup cleanup failed: {e}")

    async def _update_data(self):
        """Incremental update of data"""
        retry_count = 3
        for attempt in range(retry_count):
            try:
                return self._update_data_logic()
            except Exception as e:
                logger.warning(f"Update attempt {attempt+1}/{retry_count} failed: {e}")
                if attempt == retry_count - 1:
                    raise e
                await asyncio.sleep(5)
    
    def _update_data_logic(self):
        # 1. Load existing data
        if os.path.exists(self.data_file):
            df = pd.read_csv(self.data_file)
            if 'timestamp' not in df.columns or df.empty:
                logger.warning("Existing data invalid. Fetching full history.")
                last_ts = int((datetime.now().timestamp() - 365*24*3600) * 1000)
                df = pd.DataFrame()
            else:
                last_ts = int(df['timestamp'].max())
        else:
            last_ts = int((datetime.now().timestamp() - 365*24*3600) * 1000)
            df = pd.DataFrame()

        # 2. Fetch new data (from last_ts + 1ms to now)
        now_ts = int(time.time() * 1000)
        # Buffer: don't fetch if gap is too small (< 1 min)
        if now_ts - last_ts < 60000:
            logger.info("Data is already up to date.")
            return 0
            
        logger.info(f"Fetching data since {datetime.fromtimestamp(last_ts/1000)}")
        new_df = self.collector.fetch_data_range(last_ts + 1, now_ts)
        
        if new_df.empty:
            logger.info("No new data fetched.")
            return 0
            
        logger.info(f"Fetched {len(new_df)} new rows.")
        
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
        temp_file = self.data_file + ".tmp"
        try:
            updated_df.to_csv(temp_file, index=False)
            os.replace(temp_file, self.data_file)
            logger.info(f"✅ Data updated safely. Total rows: {len(updated_df)}")
        except Exception as e:
            if os.path.exists(temp_file):
                os.remove(temp_file)
            raise e
        
        return len(new_df)

    async def _notify_success(self, rows_added, training_status, opt_summary, duration):
        beijing_tz = pytz.timezone('Asia/Shanghai')
        bj_time = datetime.now(beijing_tz).strftime('%Y-%m-%d %H:%M:%S')
        
        msg = (
            f"✅ **每日任务执行成功 (Daily Task Success)**\n"
            f"时间: {bj_time}\n"
            f"新增数据: {rows_added} 条\n"
            f"训练状态: {training_status}\n"
            f"策略优化: {opt_summary}\n"
            f"耗时: {duration:.2f}s"
        )
        await self.feishu.send_text(msg)

    async def _notify_failure(self, error_msg):
        beijing_tz = pytz.timezone('Asia/Shanghai')
        bj_time = datetime.now(beijing_tz).strftime('%Y-%m-%d %H:%M:%S')
        
        msg = (
            f"❌ **每日任务执行失败 (Daily Task Failed)**\n"
            f"时间: {bj_time}\n"
            f"错误信息: {error_msg}"
        )
        await self.feishu.send_text(msg)

if __name__ == "__main__":
    # Test run
    manager = DailyUpdateManager()
    asyncio.run(manager.run())
