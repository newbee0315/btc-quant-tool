import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import os
import shutil
import pandas as pd
import sys
import asyncio

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.scheduler.daily_task import DailyUpdateManager

class TestDailyUpdateManager(unittest.TestCase):
    def setUp(self):
        # Mock paths
        self.test_data_file = "tests/test_data.csv"
        self.test_backup_dir = "tests/backups"
        
        # Create dummy data file
        df = pd.DataFrame({
            'timestamp': [1000, 2000, 3000],
            'close': [100, 101, 102]
        })
        df.to_csv(self.test_data_file, index=False)
        
        # Patch dependencies
        self.patcher_train = patch('src.scheduler.daily_task.train_models')
        self.mock_train = self.patcher_train.start()
        
        self.patcher_collector = patch('src.scheduler.daily_task.CryptoDataCollector')
        self.MockCollector = self.patcher_collector.start()
        
        self.patcher_feishu = patch('src.scheduler.daily_task.FeishuBot')
        self.MockFeishu = self.patcher_feishu.start()
        
    def tearDown(self):
        self.patcher_train.stop()
        self.patcher_collector.stop()
        self.patcher_feishu.stop()
        
        if os.path.exists(self.test_data_file):
            os.remove(self.test_data_file)
        if os.path.exists(self.test_backup_dir):
            shutil.rmtree(self.test_backup_dir)

    async def async_test_run(self):
        # Setup manager with test paths
        manager = DailyUpdateManager()
        manager.data_file = self.test_data_file
        manager.backup_dir = self.test_backup_dir
        os.makedirs(manager.backup_dir, exist_ok=True)
        
        # Mock collector return
        mock_new_df = pd.DataFrame({
            'timestamp': [4000, 5000],
            'close': [103, 104]
        })
        manager.collector.fetch_data_range.return_value = mock_new_df
        
        # Mock feishu
        manager.feishu.send_text = AsyncMock()
        
        # Run
        result = await manager.run()
        
        # Assertions
        self.assertTrue(result)
        
        # Check backup created
        backups = os.listdir(manager.backup_dir)
        self.assertTrue(len(backups) > 0)
        self.assertTrue(backups[0].startswith("btc_history_1m_"))
        
        # Check data updated
        updated_df = pd.read_csv(self.test_data_file)
        self.assertEqual(len(updated_df), 5) # 3 initial + 2 new
        
        # Check training called
        self.mock_train.assert_called_once()
        
        # Check notification
        manager.feishu.send_text.assert_called()

    def test_run(self):
        asyncio.run(self.async_test_run())

if __name__ == '__main__':
    unittest.main()
