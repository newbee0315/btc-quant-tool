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
        
        self.start_time = datetime.now()

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

    def update(self, current_price: float, signal: int, symbol: str = "BTC/USDT", sl: float = 0.03, tp: float = 0.025, prob: float = None, **kwargs):
        """
        Update trader state based on new price and signal.
        signal: 1 (Buy), -1 (Sell), 0 (Hold)
        prob: Probability of the signal (optional, for display)
        kwargs: dynamic params like sl_price, tp_price, leverage, position_size
        """
        if not self.active:
            return

        timestamp = datetime.now().isoformat()
        
        # Extract dynamic params
        sl_price = kwargs.get('sl_price')
        tp_price = kwargs.get('tp_price')
        leverage = kwargs.get('leverage', 1.0)
        suggested_amount = kwargs.get('position_size')
        
        # Check existing position
        if symbol in self.positions:
            pos = self.positions[symbol]
            entry_price = pos['entry_price']
            amount = pos['amount']
            pos_sl_price = pos.get('sl_price')
            pos_tp_price = pos.get('tp_price')
            
            # Calculate PnL %
            pnl_pct = (current_price - entry_price) / entry_price
            
            should_close = False
            reason = ""
            
            # Check Dynamic SL/TP first
            if pos_sl_price and current_price <= pos_sl_price:
                should_close = True
                reason = f"触发动态止损 (Dynamic SL @ {pos_sl_price:.2f})"
            elif pos_tp_price and current_price >= pos_tp_price:
                should_close = True
                reason = f"触发动态止盈 (Dynamic TP @ {pos_tp_price:.2f})"
            # Fallback to percentage SL/TP
            elif pnl_pct <= -sl:
                should_close = True
                reason = "触发固定止损 (Stop Loss)"
            elif pnl_pct >= tp:
                should_close = True
                reason = "触发固定止盈 (Take Profit)"
            elif signal == -1: # Model says sell/down
                should_close = True
                reason = "模型信号卖出 (Signal Sell)"
            
            if should_close:
                # Close Position
                # PnL = (Exit - Entry) * Amount
                # Note: This simple formula works for Long. If Short supported, need direction.
                raw_pnl = (current_price - entry_price) * amount
                fee = current_price * amount * self.transaction_fee
                net_pnl = raw_pnl - fee
                
                self.balance += net_pnl + (entry_price * amount * self.transaction_fee) # Revert initial fee deduction? No.
                # Balance logic in open was: balance -= (cost + fee)
                # Where cost = (amount * entry) / leverage
                # So on close: balance += (amount * entry) / leverage + net_pnl
                # But to keep it simple and consistent with previous spot logic:
                # Previous Open: balance -= (cost + fee), where cost = amount * price (Leverage=1)
                # Previous Close: balance += (current * amount) - fee
                
                # New Logic with Leverage:
                # Open: balance -= (Margin + Fee)
                # Close: balance += (Margin + PnL - Fee)
                margin_used = (entry_price * amount) / pos.get('leverage', 1.0)
                self.balance += margin_used + raw_pnl - fee
                
                trade_record = {
                    "symbol": symbol,
                    "action": "SELL",
                    "price": current_price,
                    "amount": amount,
                    "timestamp": timestamp,
                    "reason": reason,
                    "pnl": net_pnl,
                    "pnl_pct": pnl_pct * pos.get('leverage', 1.0) # ROE
                }
                self.trade_history.append(trade_record)
                del self.positions[symbol]
                self.save_state()
                logger.info(f"Paper Trade SELL: {symbol} @ {current_price}, PnL: {net_pnl:.2f}, Reason: {reason}")
                
                if self.notifier:
                    self.notifier.send_trade_card(
                        action="SELL", 
                        symbol=symbol, 
                        price=current_price, 
                        amount=amount, 
                        pnl=net_pnl, 
                        reason=reason,
                        prob=prob
                    )

        # Open new position if no position and signal is Buy
        elif signal == 1:
            # Use suggested amount if available, else calculate based on balance
            price = current_price
            
            if suggested_amount and suggested_amount > 0:
                amount = suggested_amount
            else:
                # Default to 95% of balance with 1x leverage if not specified
                amount_usdt = self.balance * 0.95
                amount = amount_usdt / price
            
            # Calculate Margin Required
            # Margin = (Price * Amount) / Leverage
            margin = (price * amount) / leverage
            fee = (price * amount) * self.transaction_fee
            
            if self.balance >= (margin + fee):
                self.balance -= (margin + fee)
                
                self.positions[symbol] = {
                    "entry_price": current_price,
                    "amount": amount,
                    "timestamp": timestamp,
                    "sl": sl,
                    "tp": tp,
                    "sl_price": sl_price,
                    "tp_price": tp_price,
                    "leverage": leverage
                }
                
                trade_record = {
                    "symbol": symbol,
                    "action": "BUY",
                    "price": current_price,
                    "amount": amount,
                    "leverage": leverage,
                    "timestamp": timestamp,
                    "reason": "模型信号买入 (Signal Buy)"
                }
                self.trade_history.append(trade_record)
                self.save_state()
                logger.info(f"Paper Trade BUY: {symbol} @ {current_price}, Amount: {amount}, Lev: {leverage}x, SL: {sl_price}, TP: {tp_price}")
                
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
                        sl=sl_price if sl_price else sl,
                        tp=tp_price if tp_price else tp
                    )

    def get_stats(self):
        # Calculate stats from history
        winning_trades = [t for t in self.trade_history if t.get('pnl', 0) > 0]
        total_closed = len([t for t in self.trade_history if 'pnl' in t]) # Only count closed trades (assuming 'pnl' key exists only on close or I need to infer)
        
        # PaperTrader history structure: 
        # Buy: { ..., reason: 'Buy' }
        # Sell: { ..., pnl: 123, reason: 'Sell' }
        # So check if 'pnl' is in keys
        
        closed_trades = [t for t in self.trade_history if 'pnl' in t]
        winning_trades = [t for t in closed_trades if t['pnl'] > 0]
        total_pnl = sum(t['pnl'] for t in closed_trades)
        
        win_rate = (len(winning_trades) / len(closed_trades) * 100) if len(closed_trades) > 0 else 0.0
        
        duration = datetime.now() - self.start_time
        duration_str = str(duration).split('.')[0]
        
        return {
            "win_rate": win_rate,
            "total_trades": len(closed_trades),
            "total_pnl": total_pnl,
            "duration": duration_str,
            "start_time": self.start_time.isoformat()
        }

    def get_status(self, current_price: Optional[float] = None):
        total_equity = self.balance
        
        unrealized_pnl = 0.0
        # Calculate equity with open positions
        if current_price and self.positions:
            for symbol, pos in self.positions.items():
                amount = pos['amount']
                # Unrealized PnL = (Current - Entry) * Amount (Assuming Long)
                pnl = (current_price - pos['entry_price']) * amount
                unrealized_pnl += pnl
                total_equity += pnl
        
        return {
            "active": self.active,
            "balance": self.balance,
            "total_balance": self.balance, # For consistency
            "equity": total_equity,
            "positions": self.positions,
            "trade_history": self.trade_history[-50:], # Last 50 trades
            "stats": self.get_stats(),
            "initial_balance": self.initial_capital,
            "connection_status": "Connected",
            "connection_error": None
        }
