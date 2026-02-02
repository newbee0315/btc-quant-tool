import ccxt
import logging
import os
import json
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class RealTrader:
    def __init__(self, symbol: str = "BTC/USDT", leverage: int = 1, amount_usdt: float = 100.0):
        self.symbol = symbol
        self.leverage = leverage
        self.amount_usdt = amount_usdt # Amount to trade per order in USDT
        
        # Initialize Exchange
        api_key = os.getenv("BINANCE_API_KEY")
        secret = os.getenv("BINANCE_SECRET")
        
        if not api_key or not secret:
            logger.warning("Binance API credentials not found. Real trading disabled.")
            self.exchange = None
            self.active = False
            return
            
        try:
            self.exchange = ccxt.binance({
                'apiKey': api_key,
                'secret': secret,
                'options': {
                    'defaultType': 'future',  # Use Futures API
                    'adjustForTimeDifference': True,
                },
                'enableRateLimit': True
            })
            # Load markets to check connectivity
            self.exchange.load_markets()
            logger.info("Connected to Binance Futures Real Trading")
            
            # Set leverage
            try:
                self.exchange.set_leverage(self.leverage, self.symbol)
            except Exception as e:
                logger.warning(f"Could not set leverage: {e}")
                
            self.active = True
        except Exception as e:
            logger.error(f"Failed to connect to Binance: {e}")
            self.exchange = None
            self.active = False
            
        self.current_position = None # { 'side': 'long'|'short', 'amount': float, 'entry_price': float }

    def get_balance(self):
        if not self.exchange:
            return 0.0
        try:
            balance = self.exchange.fetch_balance()
            return balance['USDT']['free']
        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            return 0.0

    def get_position(self):
        if not self.exchange:
            return None
        try:
            positions = self.exchange.fetch_positions([self.symbol])
            for pos in positions:
                if float(pos['contracts']) > 0:
                    return {
                        'side': pos['side'], # 'long' or 'short'
                        'amount': float(pos['contracts']),
                        'entry_price': float(pos['entryPrice']),
                        'unrealized_pnl': float(pos['unrealizedPnl'])
                    }
            return None
        except Exception as e:
            logger.error(f"Error fetching position: {e}")
            return None

    def execute_trade(self, signal: int, sl_pct: float = 0.03, tp_pct: float = 0.025):
        """
        Execute trade based on signal.
        signal: 1 (Buy Long), -1 (Sell Short), 0 (Close/Hold - not fully implemented for 0)
        """
        if not self.active or not self.exchange:
            return

        try:
            # Sync current position state
            pos = self.get_position()
            
            # If we have a position
            if pos:
                # If signal is opposite, close it
                if (pos['side'] == 'long' and signal == -1) or (pos['side'] == 'short' and signal == 1):
                    logger.info(f"Closing existing {pos['side']} position due to opposite signal")
                    self.close_position()
                    # Then open new if needed? For now just close.
                    # Or we can flip. Let's just close for safety first.
                    return 

            # If no position, open new
            if not pos and signal != 0:
                side = 'buy' if signal == 1 else 'sell'
                
                # Calculate amount based on price
                ticker = self.exchange.fetch_ticker(self.symbol)
                price = ticker['last']
                amount = (self.amount_usdt * self.leverage) / price
                
                # Adjust precision (simple logic, better to use exchange.amount_to_precision)
                amount = float(self.exchange.amount_to_precision(self.symbol, amount))
                
                logger.info(f"Opening {side} position for {amount} {self.symbol} at ~{price}")
                
                # Place Market Order
                order = self.exchange.create_order(self.symbol, 'market', side, amount)
                logger.info(f"Order placed: {order['id']}")
                
                # Place SL/TP
                # Note: Binance Futures allows placing STOP_MARKET and TAKE_PROFIT_MARKET
                entry_price = float(order['average']) if order['average'] else price
                
                if side == 'buy':
                    sl_price = entry_price * (1 - sl_pct)
                    tp_price = entry_price * (1 + tp_pct)
                    sl_side = 'sell'
                else:
                    sl_price = entry_price * (1 + sl_pct)
                    tp_price = entry_price * (1 - tp_pct)
                    sl_side = 'buy'
                
                # Stop Loss
                self.exchange.create_order(self.symbol, 'STOP_MARKET', sl_side, amount, params={
                    'stopPrice': self.exchange.price_to_precision(self.symbol, sl_price),
                    'closePosition': True # Important for futures
                })
                
                # Take Profit
                self.exchange.create_order(self.symbol, 'TAKE_PROFIT_MARKET', sl_side, amount, params={
                    'stopPrice': self.exchange.price_to_precision(self.symbol, tp_price),
                    'closePosition': True
                })
                
                logger.info(f"SL/TP placed. SL: {sl_price}, TP: {tp_price}")

        except Exception as e:
            logger.error(f"Trade execution failed: {e}")

    def close_position(self):
        if not self.exchange:
            return
        try:
            pos = self.get_position()
            if pos:
                side = 'sell' if pos['side'] == 'long' else 'buy'
                self.exchange.create_order(self.symbol, 'market', side, pos['amount'], params={'reduceOnly': True})
                logger.info("Position closed")
                # Also cancel open orders (SL/TP)
                self.exchange.cancel_all_orders(self.symbol)
        except Exception as e:
            logger.error(f"Error closing position: {e}")

    def update(self, current_price: float, signal: int, symbol: str = "BTC/USDT", sl: float = 0.03, tp: float = 0.025, prob: float = None):
        """
        Compatible interface with PaperTrader
        """
        self.execute_trade(signal, sl, tp)

    def start(self):
        self.active = True
        logger.info("Real trading started.")

    def stop(self):
        self.active = False
        logger.info("Real trading stopped.")

    def reset(self):
        logger.warning("Reset not supported for Real Trading. Please manage account manually.")

    def get_status(self, current_price: float = None):
        """
        Return status dict compatible with PaperTrader
        """
        balance = self.get_balance()
        pos = self.get_position()
        
        positions_dict = {}
        if pos:
            # Format to match PaperTrader's structure
            # PaperTrader: { symbol: { entry_price, amount, pnl, ... } }
            positions_dict[self.symbol] = {
                "entry_price": pos['entry_price'],
                "amount": pos['amount'],
                "side": pos['side'],
                "unrealized_pnl": pos['unrealized_pnl'],
                # Approximate pnl_pct
                "pnl_pct": (pos['unrealized_pnl'] / (pos['entry_price'] * pos['amount'])) if pos['amount'] > 0 else 0
            }
            
        return {
            "active": self.active,
            "balance": balance,
            "positions": positions_dict,
            "equity": balance + (pos['unrealized_pnl'] if pos else 0),
            "trade_history": [] # RealTrader history not locally tracked yet
        }

