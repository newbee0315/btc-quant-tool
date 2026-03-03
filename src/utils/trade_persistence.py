import json
import os
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class TradePersistence:
    def __init__(self, filepath="data/trade_history.json"):
        self.filepath = filepath
        self._ensure_dir()
        self.trades = self._load_trades()

    def _ensure_dir(self):
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)

    def _load_trades(self) -> Dict[str, Any]:
        if not os.path.exists(self.filepath):
            return {"trades": {}, "last_update": 0}
        try:
            with open(self.filepath, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load trade history: {e}")
            return {"trades": {}, "last_update": 0}

    def save_trades(self):
        try:
            with open(self.filepath, 'w') as f:
                json.dump(self.trades, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save trade history: {e}")

    def add_trades(self, new_trades: List[Dict]):
        """
        Add new trades to history. Dedup based on trade 'id'.
        """
        count = 0
        for trade in new_trades:
            tid = str(trade.get('id'))
            if tid and tid not in self.trades['trades']:
                self.trades['trades'][tid] = trade
                count += 1
        
        if count > 0:
            logger.info(f"Persisted {count} new trades.")
            self.save_trades()

    def get_all_trades(self) -> List[Dict]:
        return list(self.trades['trades'].values())

    def get_stats(self) -> Dict:
        """
        Calculate stats from ALL persisted trades.
        """
        trades = self.get_all_trades()
        total_pnl = 0.0
        total_fees = 0.0
        winning_trades = 0
        losing_trades = 0
        
        for t in trades:
            # Normalize PnL and Fee
            pnl = 0.0
            fee = 0.0
            
            # Extract PnL
            if 'info' in t and isinstance(t['info'], dict):
                pnl = float(t['info'].get('realizedPnl', 0))
                # Fee might be in info or 'fee' field
                if 'commission' in t['info']:
                    fee = float(t['info'].get('commission', 0))
            elif 'realized_pnl' in t:
                pnl = float(t['realized_pnl'])
            
            # Extract Fee if not found in info
            if fee == 0 and 'fee' in t:
                if isinstance(t['fee'], dict):
                    fee = float(t['fee'].get('cost', 0))
                elif isinstance(t['fee'], (int, float)):
                    fee = float(t['fee'])

            # Net PnL (Approximation)
            # Note: realizedPnl in Binance Futures usually EXCLUDES commission?
            # Actually, realizedPnl is gross. We should subtract commission for Net.
            net_pnl = pnl - fee
            
            total_pnl += net_pnl
            total_fees += fee
            
            # Count only realized trades (closing)
            # Match RealTrader logic: check for non-zero PnL OR non-zero fee
            if abs(pnl) > 0 or fee > 0: 
                if net_pnl > 0:
                    winning_trades += 1
                else:
                    losing_trades += 1
        
        total_closed = winning_trades + losing_trades
        win_rate = (winning_trades / total_closed * 100) if total_closed > 0 else 0.0
        
        return {
            "total_pnl": total_pnl,
            "total_fees": total_fees,
            "win_rate": win_rate,
            "total_trades": total_closed,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades
        }
