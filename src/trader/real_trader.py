import ccxt
import logging
import os
import json
from datetime import datetime
from typing import Dict, Optional

from src.notification.feishu import FeishuBot

logger = logging.getLogger(__name__)

class RealTrader:
    def __init__(self, symbol: str = "BTC/USDT", leverage: int = 1, notifier: Optional[FeishuBot] = None, api_key: str = None, api_secret: str = None, proxy_url: str = None):
        self.symbol = symbol
        self.leverage = leverage
        self.notifier = notifier
        self.proxy_url = proxy_url
        # Read amount from env, default to 20 USDT
        self.amount_usdt = float(os.getenv("TRADE_AMOUNT_USDT", "20.0")) 
        
        # Initialize Exchange
        # Priority: Constructor Args > Environment Variables
        self.api_key = api_key or os.getenv("BINANCE_API_KEY")
        self.secret = api_secret or os.getenv("BINANCE_SECRET")
        
        if self.api_key:
            logger.info(f"API Key loaded: {self.api_key[:4]}***")
        else:
            logger.warning("API Key NOT loaded")

        if not self.api_key or not self.secret:
            logger.warning("Binance API credentials not found. Real trading disabled.")
            self.exchange = None
            self.active = False
            self.last_connection_status = "Error"
            self.last_connection_error = "Missing API Credentials"
            return
            
        try:
            options = {
                'apiKey': self.api_key,
                'secret': self.secret,
                'options': {
                    'defaultType': 'swap',  # Use Swap (Perpetual) API
                    'adjustForTimeDifference': True,
                    'fetchCurrencies': False, # Disable fetching currencies to avoid hitting sapi/api endpoints
                },
                'has': {
                    'fetchCurrencies': False
                },
                'enableRateLimit': True,
                'timeout': 30000,
            }
            
            if self.proxy_url:
                options['proxies'] = {
                    'http': self.proxy_url,
                    'https': self.proxy_url
                }
                logger.info(f"Using proxy: {self.proxy_url}")
                
            self.exchange = ccxt.binanceusdm(options)
            logger.info("ccxt instance created")
            # Load markets to check connectivity
            self.exchange.load_markets()
            logger.info("Connected to Binance Futures Real Trading")
            
            # Set leverage
            try:
                self.exchange.set_leverage(self.leverage, self.symbol)
            except Exception as e:
                logger.warning(f"Could not set leverage: {e}")
                
            self.active = True
            self.last_connection_status = "Connected"
            self.last_connection_error = None
        except Exception as e:
            logger.error(f"Failed to connect to Binance: {e}")
            self.exchange = None
            self.active = False
            self.last_connection_status = "Error"
            self.last_connection_error = str(e)
            logger.error(f"Set status to Error: {str(e)}")
            
        self.current_position = None # { 'side': 'long'|'short', 'amount': float, 'entry_price': float }
        self.start_time = datetime.now()
        self.initial_balance = None # Will be set on first balance fetch or config
        self.position_highs = {} # Track highest price for dynamic exit

    def get_balance(self):
        if not self.exchange:
            logger.warning(f"get_balance: Exchange is None. Status was: {self.last_connection_status}")
            if self.last_connection_status != "Error":
                self.last_connection_status = "Disconnected"
            return 0.0
        try:
            balance = self.exchange.fetch_balance()
            
            # Use totalMarginBalance if available (Wallet + Unrealized PnL)
            # This is the "Equity" that users typically care about
            if 'info' in balance and 'totalMarginBalance' in balance['info']:
                total_balance = float(balance['info']['totalMarginBalance'])
            else:
                # Fallback: Wallet Balance + Unrealized PnL
                total_balance = balance['USDT']['total']
            
            if self.initial_balance is None:
                self.initial_balance = total_balance
            
            self.last_connection_status = "Connected"
            self.last_connection_error = None
            return balance['USDT']['free']
        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            self.last_connection_status = "Error"
            self.last_connection_error = str(e)
            return 0.0

    def get_total_balance(self):
        if not self.exchange:
            return 0.0
        try:
            balance = self.exchange.fetch_balance()
            # Prefer totalMarginBalance (Equity)
            if 'info' in balance and 'totalMarginBalance' in balance['info']:
                return float(balance['info']['totalMarginBalance'])
            return balance['USDT']['total']
        except Exception as e:
            logger.error(f"Error fetching total balance: {e}")
            return 0.0

    def get_positions(self):
        """Fetch all active positions from the account"""
        if not self.exchange:
            return {}
        
        try:
            # Fetch all positions (no symbol filter)
            positions = self.exchange.fetch_positions()
            
            # Fetch all open orders to find SL/TP
            try:
                open_orders = self.exchange.fetch_open_orders()
            except Exception as e:
                logger.warning(f"Could not fetch all open orders: {e}")
                open_orders = []
                
            # NEW: Fetch Algo Orders (SL/TP)
            algo_orders = []
            try:
                # Use raw call for algo orders which are not returned by fetch_open_orders
                raw_algos = self.exchange.fapiPrivateGetOpenAlgoOrders()
                algo_orders = raw_algos
            except Exception as e:
                logger.warning(f"Could not fetch algo orders: {e}")

            # Map open orders to symbols
            orders_by_symbol = {}
            
            # Helper for raw symbol matching
            orders_by_raw_symbol = {} 

            for order in open_orders:
                sym = order['symbol']
                if sym not in orders_by_symbol:
                    orders_by_symbol[sym] = {'sl': 0.0, 'tp': 0.0}
                
                order_type = order.get('type')
                stop_price = float(order.get('stopPrice', 0.0))
                
                if stop_price > 0:
                     if 'STOP' in order_type: # STOP, STOP_MARKET
                         orders_by_symbol[sym]['sl'] = stop_price
                     elif 'TAKE_PROFIT' in order_type: # TAKE_PROFIT, TAKE_PROFIT_MARKET
                         orders_by_symbol[sym]['tp'] = stop_price

            # Process Algo Orders
            for algo in algo_orders:
                raw_sym = algo['symbol'] # e.g. SOLUSDT
                if raw_sym not in orders_by_raw_symbol:
                    orders_by_raw_symbol[raw_sym] = {'sl': 0.0, 'tp': 0.0}
                
                o_type = algo.get('orderType', '')
                # triggerPrice is usually where the stop price is for algo orders
                stop_price = float(algo.get('triggerPrice', 0.0))
                if stop_price == 0:
                    stop_price = float(algo.get('stopPrice', 0.0))
                
                if stop_price > 0:
                    if 'STOP' in o_type:
                        orders_by_raw_symbol[raw_sym]['sl'] = stop_price
                    elif 'TAKE_PROFIT' in o_type:
                        orders_by_raw_symbol[raw_sym]['tp'] = stop_price

            active_positions = {}
            for pos in positions:
                if float(pos['contracts']) > 0:
                    symbol = pos['symbol']
                    
                    # Calculate ROI if not provided
                    unrealized_pnl = float(pos['unrealizedPnl'])
                    initial_margin = float(pos['initialMargin']) if pos.get('initialMargin') else 0.0
                    
                    mark_price = float(pos['markPrice']) if pos.get('markPrice') else 0.0
                    amount = float(pos['contracts'])
                    
                    # Calculate position value in USDT
                    position_value_usdt = amount * mark_price
                    
                    # Try to get leverage from standard field, then info, then fallback
                    leverage = self.leverage
                    if pos.get('leverage'):
                        leverage = float(pos['leverage'])
                    elif 'info' in pos and 'leverage' in pos['info']:
                        leverage = float(pos['info']['leverage'])
                    
                    # Fallback for margin calculation if API doesn't return it
                    if initial_margin == 0 and leverage > 0:
                        entry_value = float(pos['entryPrice']) * amount
                        initial_margin = entry_value / leverage
                    
                    # Calculate effective leverage if initial_margin > 0
                    if initial_margin > 0:
                        effective_leverage = position_value_usdt / initial_margin
                        if leverage == 1 and effective_leverage > 1.5:
                            leverage = round(effective_leverage)
                        
                    roi = (unrealized_pnl / initial_margin * 100) if initial_margin > 0 else 0.0
                    
                    # Get SL/TP for this symbol
                    sl_price = 0.0
                    tp_price = 0.0
                    
                    # Direct lookup (Standard Orders)
                    if symbol in orders_by_symbol:
                        sl_price = orders_by_symbol[symbol]['sl']
                        tp_price = orders_by_symbol[symbol]['tp']
                    
                    # Fallback lookup (Algo Orders) via raw symbol
                    # Normalize symbol: SOL/USDT:USDT -> SOLUSDT
                    raw_symbol_lookup = symbol.replace('/', '').replace(':USDT', '').replace(':BUSD', '')
                    if sl_price == 0 and raw_symbol_lookup in orders_by_raw_symbol:
                         sl_val = orders_by_raw_symbol[raw_symbol_lookup]['sl']
                         if sl_val > 0: sl_price = sl_val
                    
                    if tp_price == 0 and raw_symbol_lookup in orders_by_raw_symbol:
                         tp_val = orders_by_raw_symbol[raw_symbol_lookup]['tp']
                         if tp_val > 0: tp_price = tp_val

                    active_positions[symbol] = {
                        'side': pos['side'], # 'long' or 'short'
                        'amount': amount,
                        'position_value_usdt': position_value_usdt,
                        'entry_price': float(pos['entryPrice']),
                        'unrealized_pnl': unrealized_pnl,
                        'pnl_pct': roi,
                        'liquidation_price': float(pos['liquidationPrice']) if pos.get('liquidationPrice') else 0.0,
                        'mark_price': mark_price,
                        'initial_margin': initial_margin,
                        'roi': roi,
                        'leverage': leverage,
                        'sl_price': sl_price,
                        'tp_price': tp_price
                    }
            return active_positions
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return {}

    def get_position(self):
        """Legacy method: get position for current tracked symbol only"""
        all_pos = self.get_positions()
        return all_pos.get(self.symbol)

    def get_total_leverage(self):
        """Calculate total effective leverage across all positions"""
        try:
            positions = self.get_positions()
            total_equity = self.get_total_balance()
            
            if total_equity <= 0:
                return 0.0
                
            total_notional = sum(pos['position_value_usdt'] for pos in positions.values())
            return total_notional / total_equity
        except Exception as e:
            logger.error(f"Error calculating total leverage: {e}")
            return 0.0

    def check_risk_limit(self, new_position_value_usdt: float):
        """
        Check if opening a new position violates risk limits.
        Limit: Total Leverage <= 30x
        Limit: Daily Loss <= 2% of Capital
        """
        try:
            positions = self.get_positions()
            total_equity = self.get_total_balance()
            
            if total_equity <= 0:
                logger.warning("Risk Check Failed: Zero or negative equity")
                return False
            
            # 1. Check Daily Loss
            stats = self.get_stats()
            daily_pnl = stats.get('total_pnl', 0.0)
            
            # Max Daily Loss Limit (2% of Equity)
            max_daily_loss = total_equity * 0.02
            if daily_pnl < -max_daily_loss:
                logger.warning(f"Risk Check Failed: Daily Loss {daily_pnl:.2f} exceeds limit {-max_daily_loss:.2f}")
                return False
                
            current_total_notional = sum(pos['position_value_usdt'] for pos in positions.values())
            projected_total_notional = current_total_notional + new_position_value_usdt
            
            projected_leverage = projected_total_notional / total_equity
            
            if projected_leverage > 30.0:
                logger.warning(f"Risk Check Failed: Projected Leverage {projected_leverage:.2f}x > 30x Limit")
                return False
                
            return True
        except Exception as e:
            logger.error(f"Error checking risk limit: {e}")
            return False # Fail safe

    def execute_trade(self, signal: int, sl_pct: float = 0.03, tp_pct: float = 0.025, sl_price: float = None, tp_price: float = None, leverage: int = None, amount_coins: float = None, symbol: str = None):
        """
        Execute trade based on signal.
        signal: 1 (Buy Long), -1 (Sell Short), 0 (Close/Hold - not fully implemented for 0)
        symbol: Optional override for self.symbol
        """
        target_symbol = symbol if symbol else self.symbol
        
        logger.info(f"execute_trade called for {target_symbol} with signal: {signal}, sl_pct: {sl_pct}, tp_pct: {tp_pct}, leverage: {leverage}")
        
        if not self.active or not self.exchange:
            logger.warning("execute_trade skipped: Trader not active or Exchange not initialized")
            return

        try:
            # Sync current position state for target symbol
            # We need to filter get_positions() for target_symbol
            all_pos = self.get_positions()
            pos = all_pos.get(target_symbol)
            
            # If we have a position
            if pos:
                # logger.info(f"Current position found: {pos['side']} {pos['amount']}")
                # If signal is opposite, close it
                if (pos['side'] == 'long' and signal == -1) or (pos['side'] == 'short' and signal == 1):
                    logger.info(f"Closing existing {pos['side']} position due to opposite signal")
                    # Use internal helper or just replicate close logic for dynamic symbol
                    self._close_position_by_symbol(target_symbol, pos)
                    # Then open new if needed? For now just close.
                    return 
                elif signal != 0:
                    # logger.info(f"Skipping trade: Already have a {pos['side']} position and signal is same direction.")
                    return
                else:
                    # Signal is 0 (Hold), but check for dynamic exit (Trailing Stop / Soft TP)
                    pass

            # If no position, open new
            if not pos and signal != 0:
                side = 'buy' if signal == 1 else 'sell'
                
                # Dynamic Leverage
                current_leverage = self.leverage
                if leverage and leverage != self.leverage:
                    try:
                        self.exchange.set_leverage(int(leverage), target_symbol)
                        current_leverage = int(leverage)
                        # Don't update self.leverage globally if we are supporting multi-symbol with one instance, 
                        # but usually RealTrader is per-symbol. If using dynamic symbol, just log it.
                        logger.info(f"Set dynamic leverage to {current_leverage}x for {target_symbol}")
                    except Exception as e:
                        logger.warning(f"Could not set dynamic leverage: {e}")

                # Calculate amount
                ticker = self.exchange.fetch_ticker(target_symbol)
                price = ticker['last']
                
                if amount_coins and amount_coins > 0:
                    amount = amount_coins
                else:
                    # Calculate amount based on leverage and fixed USDT amount
                    # NOTE: This uses self.amount_usdt which is global config.
                    amount = (self.amount_usdt * current_leverage) / price
                
                # Check Risk Limit before placing order
                notional_value = amount * price
                if not self.check_risk_limit(notional_value):
                    logger.warning(f"Trade blocked by Risk Manager: {target_symbol} {side} ~${notional_value:.2f}")
                    if self.notifier:
                        self.notifier.send_text(f"⚠️ Trade Blocked: Risk Limit Exceeded\nSymbol: {target_symbol}\nValue: ${notional_value:.2f}")
                    return

                # Adjust precision (simple logic, better to use exchange.amount_to_precision)
                amount = float(self.exchange.amount_to_precision(target_symbol, amount))
                
                logger.info(f"Opening {side} position for {amount} {target_symbol} at ~{price}")
                
                # Place Market Order
                try:
                    order = self.exchange.create_order(target_symbol, 'market', side, amount)
                    logger.info(f"Order placed: {order['id']}")
                except Exception as e:
                    if "insufficient" in str(e).lower() or "margin" in str(e).lower():
                        logger.warning(f"Skipping trade due to insufficient margin: {e}")
                        return
                    else:
                        raise e
                
                # Place SL/TP
                entry_price = float(order['average']) if order['average'] else price
                
                if sl_price and tp_price:
                    real_sl = sl_price
                    real_tp = tp_price
                else:
                    if side == 'buy':
                        real_sl = entry_price * (1 - sl_pct)
                        real_tp = entry_price * (1 + tp_pct)
                    else:
                        real_sl = entry_price * (1 + sl_pct)
                        real_tp = entry_price * (1 - tp_pct)
                    
                if side == 'buy':
                    sl_side = 'sell'
                else:
                    sl_side = 'buy'
                
                # Stop Loss (Hard SL is good for safety)
                # Use reduceOnly instead of closePosition to avoid API error -4130 if existing orders conflict
                self.exchange.create_order(target_symbol, 'STOP_MARKET', sl_side, amount, params={
                    'stopPrice': self.exchange.price_to_precision(target_symbol, real_sl),
                    'reduceOnly': True 
                })
                
                # Take Profit (Hard TP)
                self.exchange.create_order(target_symbol, 'TAKE_PROFIT_MARKET', sl_side, amount, params={
                    'stopPrice': self.exchange.price_to_precision(target_symbol, real_tp),
                    'reduceOnly': True
                })
                
                logger.info(f"SL placed at {real_sl}. TP placed at {real_tp}")
                
                # Notify Feishu
                if self.notifier:
                    self.notifier.send_trade_card(
                        action=side.upper(),
                        symbol=target_symbol,
                        price=entry_price,
                        amount=amount,
                        reason="Real Trade Signal",
                        sl=real_sl,
                        tp=real_tp
                    )

        except Exception as e:
            logger.error(f"Trade execution failed: {e}")

    def _close_position_by_symbol(self, symbol, pos):
        """Helper to close position for a specific symbol"""
        try:
            side = 'sell' if pos['side'] == 'long' else 'buy'
            amount = float(pos['amount'])
            
            logger.info(f"Closing {pos['side']} position: {side} {amount} {symbol}")
            order = self.exchange.create_order(symbol, 'market', side, amount)
            logger.info(f"Close order placed: {order['id']}")
            
            # Cancel all open orders (SL/TP)
            self.exchange.cancel_all_orders(symbol)
            logger.info(f"Cancelled all open orders for {symbol}.")
            
            # Notify
            if self.notifier:
                 self.notifier.send_text(f"🛑 Position Closed: {symbol}")
        except Exception as e:
            logger.error(f"Failed to close position for {symbol}: {e}")

    def manage_position(self, current_price: float, signal: int, symbol: str = None, trailing_trigger_pct: float = 0.01, trailing_lock_pct: float = 0.02):
        """
        Dynamic position management:
        1. Trailing Stop
        2. Dynamic Take Profit (Retracement from High)
        3. Soft Take Profit (Hold if trend strong)
        
        Args:
            current_price: Current market price
            signal: Current strategy signal
            symbol: Symbol to manage (default self.symbol)
            trailing_trigger_pct: Price movement % to trigger break-even SL (default 1% = 20% ROE at 20x)
            trailing_lock_pct: Price movement % to trigger profit locking (default 2% = 40% ROE at 20x)
        """
        if not self.active or not self.exchange:
            return

        target_symbol = symbol if symbol else self.symbol

        try:
            all_pos = self.get_positions()
            pos = all_pos.get(target_symbol)
            
            if not pos:
                # Clean up high water mark if position closed
                if target_symbol in self.position_highs:
                    del self.position_highs[target_symbol]
                return

            entry_price = float(pos['entry_price'])
            amount = float(pos['amount'])
            side = pos['side']
            
            # --- High Water Mark Tracking ---
            if target_symbol not in self.position_highs:
                self.position_highs[target_symbol] = current_price
            else:
                if side == 'long':
                    self.position_highs[target_symbol] = max(self.position_highs[target_symbol], current_price)
                else:
                    self.position_highs[target_symbol] = min(self.position_highs[target_symbol], current_price)
            
            highest_price = self.position_highs[target_symbol]
            
            # --- Dynamic Retracement Exit ---
            # If Price retraces > 1.5% from High AND currently profitable
            should_dynamic_exit = False
            dynamic_exit_reason = ""
            
            retracement_threshold = 0.015
            
            pnl_pct = 0.0
            if side == 'long':
                pnl_pct = (current_price - entry_price) / entry_price
                retracement = (highest_price - current_price) / highest_price
                if pnl_pct > 0 and retracement > retracement_threshold:
                    should_dynamic_exit = True
                    dynamic_exit_reason = f"Long Retracement > {retracement_threshold*100}% from High"
            else:
                pnl_pct = (entry_price - current_price) / entry_price
                # For short, highest_price tracks the LOWEST price seen (best price)
                # Logic above: min(self.position_highs..., current) for short
                retracement = (current_price - highest_price) / highest_price 
                if pnl_pct > 0 and retracement > retracement_threshold:
                     should_dynamic_exit = True
                     dynamic_exit_reason = f"Short Retracement > {retracement_threshold*100}% from Low"
            
            if should_dynamic_exit:
                logger.info(f"Dynamic Exit Triggered: {dynamic_exit_reason}")
                self._close_position_by_symbol(target_symbol, pos)
                return
            
            # --- Trailing Stop Logic ---
            # If profit > trailing_trigger_pct (1%), move SL to Break-Even
            # If profit > trailing_lock_pct (2%), move SL to Entry + 1%
            
            # Check existing SL orders
            open_orders = self.exchange.fetch_open_orders(target_symbol)
            sl_order = next((o for o in open_orders if o['type'] == 'STOP_MARKET'), None)
            
            current_sl_price = float(sl_order['stopPrice']) if sl_order else 0.0
            
            new_sl_price = None
            
            if side == 'long':
                if pnl_pct > trailing_trigger_pct and current_sl_price < entry_price:
                    new_sl_price = entry_price * 1.001 # Break-even + fee
                    logger.info(f"Trailing Stop: Moving SL to Break-Even {new_sl_price} (PnL: {pnl_pct*100:.2f}%)")
                elif pnl_pct > trailing_lock_pct and current_sl_price < entry_price * 1.01:
                    new_sl_price = entry_price * 1.01
                    logger.info(f"Trailing Stop: Moving SL to Lock Profit {new_sl_price} (PnL: {pnl_pct*100:.2f}%)")
            else: # short
                if pnl_pct > trailing_trigger_pct and current_sl_price > entry_price:
                    new_sl_price = entry_price * 0.999 # Break-even + fee
                    logger.info(f"Trailing Stop: Moving SL to Break-Even {new_sl_price} (PnL: {pnl_pct*100:.2f}%)")
                elif pnl_pct > trailing_lock_pct and current_sl_price > entry_price * 0.99:
                    new_sl_price = entry_price * 0.99
                    logger.info(f"Trailing Stop: Moving SL to Lock Profit {new_sl_price} (PnL: {pnl_pct*100:.2f}%)")
            
            if new_sl_price:
                # Cancel old SL and place new SL
                if sl_order:
                    self.exchange.cancel_order(sl_order['id'], target_symbol)
                
                sl_side = 'sell' if side == 'long' else 'buy'
                self.exchange.create_order(target_symbol, 'STOP_MARKET', sl_side, amount, params={
                    'stopPrice': self.exchange.price_to_precision(target_symbol, new_sl_price),
                    'reduceOnly': True
                })
                if self.notifier:
                    self.notifier.send_text(f"🔄 移动止损 (Trailing SL)\nPrice: {new_sl_price}")

            # --- Soft TP Logic ---
            # If price hits "Target TP" (e.g. self.soft_tp_price), we check if we should close.
            # If signal is strong (same direction), we HOLD.
            # If signal weakens (0) or reverses (-1), we CLOSE.
            
            target_reached = False
            if hasattr(self, 'soft_tp_price') and self.soft_tp_price:
                if side == 'long' and current_price >= self.soft_tp_price:
                    target_reached = True
                elif side == 'short' and current_price <= self.soft_tp_price:
                    target_reached = True
            
            # Fallback if attribute missing
            if not target_reached and pnl_pct > 0.025: 
                target_reached = True

            if target_reached:
                should_close = False
                if signal == 0:
                    should_close = True
                    reason = "TP Reached & Trend Neutral"
                elif (side == 'long' and signal == -1) or (side == 'short' and signal == 1):
                    should_close = True
                    reason = "TP Reached & Signal Reversed"
                
                # If signal is still 1 (Long) or -1 (Short), we continue holding!
                
                if should_close:
                    logger.info(f"Dynamic Exit Triggered: {reason}")
                    self._close_position_by_symbol(target_symbol, pos)

        except Exception as e:
            logger.error(f"Error in manage_position: {e}")

    def update(self, current_price: float, signal: int, symbol: str = "BTC/USDT", sl: float = 0.03, tp: float = 0.025, prob: float = None, **kwargs):
        """
        Compatible interface with PaperTrader
        """
        sl_price = kwargs.get('sl_price')
        tp_price = kwargs.get('tp_price')
        leverage = kwargs.get('leverage')
        position_size = kwargs.get('position_size')
        trailing_trigger_pct = kwargs.get('trailing_trigger_pct', 0.01)
        trailing_lock_pct = kwargs.get('trailing_lock_pct', 0.02)
        
        # First check/manage existing position
        self.manage_position(current_price, signal, symbol, trailing_trigger_pct, trailing_lock_pct)
        
        # Then execute new trades if any
        self.execute_trade(signal, sl, tp, sl_price, tp_price, leverage, position_size, symbol)

    def start(self):
        self.active = True
        logger.info("Real trading started.")

    def stop(self):
        self.active = False
        logger.info("Real trading stopped.")

    def reset(self):
        logger.warning("Reset not supported for Real Trading. Please manage account manually.")

    def get_recent_trades(self, limit: int = 50):
        if not self.exchange:
            return []
        try:
            # Fetch latest 500 trades (Binance default is recent if since is None)
            # This ensures we get the most recent history for markers and stats
            trades = self.exchange.fetch_my_trades(self.symbol, limit=500)
            
            # Format trades for frontend
            formatted_trades = []
            for t in trades:
                # Extract Realized PnL from raw info if available (Binance Futures)
                realized_pnl = 0.0
                if 'info' in t and 'realizedPnl' in t['info']:
                    realized_pnl = float(t['info']['realizedPnl'])
                
                formatted_trades.append({
                    'id': t['id'],
                    'timestamp': t['timestamp'],
                    'datetime': t['datetime'],
                    'side': t['side'],
                    'price': t['price'],
                    'amount': t['amount'],
                    'cost': t['cost'],
                    'fee': t['fee'],
                    'realized_pnl': realized_pnl
                })
            # Sort by time desc
            formatted_trades.sort(key=lambda x: x['timestamp'], reverse=True)
            return formatted_trades
        except Exception as e:
            logger.error(f"Error fetching trades: {e}")
            return []

    def set_amount(self, amount_usdt: float):
        self.amount_usdt = amount_usdt
        logger.info(f"Updated trade amount to {amount_usdt} USDT")

    def get_stats(self):
        if not self.exchange:
            return {
                "win_rate": 0.0,
                "total_trades": 0,
                "total_pnl": 0.0,
                "duration": "0:00:00",
                "start_time": self.start_time.isoformat()
            }
            
        trades = self.get_recent_trades(limit=100)
        # Use 24h window for stats instead of process start time to persist stats across restarts
        since_ts = int((datetime.now().timestamp() - 86400) * 1000)
        trades = [t for t in trades if t['timestamp'] >= since_ts]
        
        # Calculate Total PnL (Realized PnL - Commission)
        # Binance realizedPnl usually includes commission for the trade pnl, but 'fee' field is separate.
        # Let's sum realized_pnl and subtract fee cost if not included. 
        # Actually, for Binance Futures, 'realizedPnl' is gross pnl usually? No, it is net of funding fees but maybe not trading fees.
        # However, to be safe and match user expectation: User sees -0.31 PnL and -0.1 Fee -> Total -0.41.
        # Let's check if realized_pnl already includes fee. 
        # If the user sees -0.31 in "Realized PnL" column and -0.1 in "Fee", and expects -0.41 total, 
        # it implies they want (Realized PnL - Fee).
        
        total_pnl = 0.0
        total_fees = 0.0
        for t in trades:
            pnl = t.get('realized_pnl', 0.0)
            fee = 0.0
            if t.get('fee'):
                 fee = float(t['fee']['cost']) if t['fee'].get('cost') else 0.0
            
            # If it's a closing trade (realized_pnl != 0), we sum it.
            # But fees apply to both opening and closing trades.
            # So we should sum realized_pnl for all trades (opening trades have 0 realized pnl)
            # and subtract all fees.
            
            total_pnl += pnl - fee
            total_fees += fee
        
        # Count winning/losing trades (only count those with realized pnl != 0 to avoid opening trades)
        closed_trades = [t for t in trades if abs(t['realized_pnl']) > 0]
        
        # Winning trade: Realized PnL - Fee > 0 (Net PnL)
        winning_trades = []
        for t in closed_trades:
             pnl = t.get('realized_pnl', 0.0)
             fee = 0.0
             if t.get('fee'):
                 fee = float(t['fee']['cost']) if t['fee'].get('cost') else 0.0
             
             if (pnl - fee) > 0:
                 winning_trades.append(t)
        total_closed = len(closed_trades)
        
        win_rate = (len(winning_trades) / total_closed * 100) if total_closed > 0 else 0.0
        
        duration = datetime.now() - self.start_time
        duration_str = str(duration).split('.')[0] # HH:MM:SS
        
        return {
            "win_rate": win_rate,
            "total_trades": total_closed, # Only counting closed for stats
            "total_pnl": total_pnl,
            "total_fees": total_fees,
            "duration": duration_str,
            "start_time": self.start_time.isoformat()
        }

    def get_status(self, current_price: float = None):
        """
        Return status dict compatible with PaperTrader
        """
        balance = self.get_balance() # This is free balance
        
        # Get Equity (totalMarginBalance)
        equity = self.get_total_balance()
        
        # Use get_positions to return ALL active positions
        positions_dict = self.get_positions()
        
        unrealized_pnl = 0.0
        # Sum unrealized pnl from all positions
        for pos in positions_dict.values():
            unrealized_pnl += pos['unrealized_pnl']
        
        # Calculate Wallet Balance (Equity - Unrealized PnL)
        # Note: If get_total_balance returns totalMarginBalance, it includes unrealized PnL.
        wallet_balance = equity - unrealized_pnl
        
        # Get Stats
        stats = self.get_stats()
            
        return {
            "active": self.active,
            "balance": balance,
            "total_balance": wallet_balance, # Wallet Balance (for display consistency)
            "equity": equity, # Real Equity
            "positions": positions_dict,
            "trade_history": self.get_recent_trades(limit=500),
            "stats": stats,
            "initial_balance": self.initial_balance if self.initial_balance else wallet_balance,
            "connection_status": self.last_connection_status,
            "connection_error": self.last_connection_error
        }

