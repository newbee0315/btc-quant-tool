import json
import os
import logging
from datetime import datetime
from typing import List, Dict

logger = logging.getLogger(__name__)

class EquityRecorder:
    def __init__(self, filepath: str = "data/equity_history.json"):
        self.filepath = filepath
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        """Create the file with an empty list if it doesn't exist."""
        if not os.path.exists(os.path.dirname(self.filepath)):
            os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
            
        if not os.path.exists(self.filepath):
            with open(self.filepath, 'w') as f:
                json.dump([], f)

    def record(self, total_equity: float, total_balance: float, unrealized_pnl: float):
        """
        Record the current equity state.
        :param total_equity: Total Margin Balance (Wallet + Unrealized PnL)
        :param total_balance: Wallet Balance
        :param unrealized_pnl: Unrealized Profit/Loss
        """
        try:
            entry = {
                "timestamp": datetime.now().isoformat(),
                "total_equity": float(total_equity),
                "wallet_balance": float(total_balance),
                "unrealized_pnl": float(unrealized_pnl)
            }
            
            # Read existing history
            history = self.get_history()
            history.append(entry)
            
            # Keep only last 30 days (assuming hourly ~ 720 points, maybe keep all for now)
            # For now, let's just append.
            
            with open(self.filepath, 'w') as f:
                json.dump(history, f, indent=2)
                
            logger.debug(f"Recorded equity: {total_equity}")
            
        except Exception as e:
            logger.error(f"Failed to record equity history: {e}")

    def get_history(self) -> List[Dict]:
        """Retrieve the full equity history."""
        try:
            if not os.path.exists(self.filepath):
                return []
                
            with open(self.filepath, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read equity history: {e}")
            return []
