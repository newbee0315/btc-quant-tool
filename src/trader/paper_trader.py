import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional

from src.notification.feishu import FeishuBot

logger = logging.getLogger(__name__)

class PaperTrader:
    def __init__(self, initial_capital: float = 10000.0, transaction_fee: float = 0.0005, notifier: Optional[FeishuBot] = None):
        self.initial_capital = initial_capital
        self.balance = initial_capital
        self.transaction_fee = transaction_fee
        self.notifier = notifier
        self.positions: Dict[str, Dict] = {}  # symbol -> position_details
        self.trade_history: List[Dict] = []
        self.active = False
        
        # Persistence file
        self.state_file = "paper_trading_state.json"
        self.load_state()

    def load_state(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    self.balance = state.get('balance', self.initial_capital)
                    self.positions = state.get('positions', {})
                    self.trade_history = state.get('trade_history', [])
                    self.active = state.get('active', False)
                logger.info("Paper trading state loaded.")
            except Exception as e:
                logger.error(f"Failed to load paper trading state: {e}")

    def save_state(self):
        try:
            state = {
                'balance': self.balance,
                'positions': self.positions,
                'trade_history': self.trade_history,
                'active': self.active
            }
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save paper trading state: {e}")

    def start(self):
        self.active = True
        self.save_state()
        logger.info("Paper trading started.")

    def stop(self):
        self.active = False
        self.save_state()
        logger.info("Paper trading stopped.")

    def reset(self):
        self.balance = self.initial_capital
        self.positions = {}
        self.trade_history = []
        self.save_state()
        logger.info("Paper trading reset.")

    def update(self, current_price: float, signal: int, symbol: str = "BTC/USDT", sl: float = 0.03, tp: float = 0.025, prob: float = None):
        """
        Update trader state based on new price and signal.
        signal: 1 (Buy), -1 (Sell), 0 (Hold)
        prob: Probability of the signal (optional, for display)
        """
        if not self.active:
            return

        timestamp = datetime.now().isoformat()
        
        # Check existing position
        if symbol in self.positions:
            pos = self.positions[symbol]
            entry_price = pos['entry_price']
            amount = pos['amount']
            
            pnl_pct = (current_price - entry_price) / entry_price
            
            should_close = False
            reason = ""
            
            if pnl_pct <= -sl:
                should_close = True
                reason = "止损 (Stop Loss)"
            elif pnl_pct >= tp:
                should_close = True
                reason = "止盈 (Take Profit)"
            elif signal == -1: # Model says sell/down
                should_close = True
                reason = "模型信号卖出 (Signal Sell)"
            
            if should_close:
                # Close Position
                pnl = (current_price - entry_price) * amount - (current_price * amount * self.transaction_fee)
                self.balance += (current_price * amount) - (current_price * amount * self.transaction_fee)
                
                trade_record = {
                    "symbol": symbol,
                    "action": "SELL",
                    "price": current_price,
                    "amount": amount,
                    "timestamp": timestamp,
                    "reason": reason,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct
                }
                self.trade_history.append(trade_record)
                del self.positions[symbol]
                self.save_state()
                logger.info(f"Paper Trade SELL: {symbol} @ {current_price}, PnL: {pnl:.2f} ({pnl_pct*100:.2f}%)")
                
                if self.notifier:
                    self.notifier.send_trade_card(
                        action="SELL", 
                        symbol=symbol, 
                        price=current_price, 
                        amount=amount, 
                        pnl=pnl, 
                        reason=reason,
                        prob=prob
                    )

        # Open new position if no position and signal is Buy
        elif signal == 1:
            # Calculate position size (e.g., 95% of balance to account for fees)
            amount_usdt = self.balance * 0.95
            amount = amount_usdt / current_price
            
            cost = amount * current_price
            fee = cost * self.transaction_fee
            
            if self.balance >= (cost + fee):
                self.balance -= (cost + fee)
                
                self.positions[symbol] = {
                    "entry_price": current_price,
                    "amount": amount,
                    "timestamp": timestamp,
                    "sl": sl,
                    "tp": tp
                }
                
                trade_record = {
                    "symbol": symbol,
                    "action": "BUY",
                    "price": current_price,
                    "amount": amount,
                    "timestamp": timestamp,
                    "reason": "模型信号买入 (Signal Buy)"
                }
                self.trade_history.append(trade_record)
                self.save_state()
                logger.info(f"Paper Trade BUY: {symbol} @ {current_price}, Amount: {amount}")
                
                if self.notifier:
                    reason_desc = "模型信号强力看涨"
                    if prob:
                        reason_desc += f" (置信度: {prob*100:.1f}%)"
                    
                    self.notifier.send_trade_card(
                        action="BUY", 
                        symbol=symbol, 
                        price=current_price, 
                        amount=amount, 
                        reason=reason_desc,
                        prob=prob,
                        sl=sl,
                        tp=tp
                    )

    def get_status(self, current_price: Optional[float] = None):
        total_equity = self.balance
        
        # Calculate equity with open positions
        if current_price and self.positions:
            for symbol, pos in self.positions.items():
                amount = pos['amount']
                value = amount * current_price
                total_equity += value
        
        return {
            "active": self.active,
            "balance": self.balance,
            "equity": total_equity,
            "positions": self.positions,
            "trade_history": self.trade_history[-50:] # Last 50 trades
        }
