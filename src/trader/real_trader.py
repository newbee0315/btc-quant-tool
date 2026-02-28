import ccxt
import logging
import os
import json
import time
from datetime import datetime
from typing import Dict, Optional

from src.notification.feishu import FeishuBot
from src.utils.history_recorder import EquityRecorder
from src.utils.config_manager import config_manager

logger = logging.getLogger(__name__)

class RealTrader:
    def __init__(self, symbol: str = "BTC/USDT", leverage: int = 1, notifier: Optional[FeishuBot] = None, api_key: str = None, api_secret: str = None, proxy_url: str = None, monitored_symbols: list = None):
        self.symbol = symbol
        self.monitored_symbols = monitored_symbols if monitored_symbols else [symbol]
        self.trade_history_cache = []
        self.last_history_update = 0
        self.leverage = min(leverage, 10)
        self.notifier = notifier
        self.proxy_url = proxy_url
        self.equity_recorder = EquityRecorder()
        self.config_manager = config_manager
        
        # Load leverage from config if available to override default
        try:
            cfg = self.config_manager.get_config()
            # Check for 'leverage' or 'max_portfolio_leverage'
            config_lev = cfg.get('leverage') or cfg.get('max_portfolio_leverage')
            if config_lev:
                self.leverage = min(int(float(config_lev)), 10)
                logger.info(f"Loaded leverage from config: {self.leverage}x")
        except Exception as e:
            logger.warning(f"Failed to load leverage from config: {e}")

        # Fallback: Load proxy from config if not provided
        if not self.proxy_url:
            try:
                cfg = self.config_manager.get_config()
                if cfg.get('proxy_url'):
                    self.proxy_url = cfg.get('proxy_url')
                    logger.info(f"Loaded proxy_url from config: {self.proxy_url}")
            except Exception as e:
                logger.warning(f"Failed to load proxy from config: {e}")
        
        # Cache for get_status
        self.cached_status = None
        self.last_status_update = 0
        self.status_cache_ttl = 5 # seconds

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
                    'recvWindow': 10000,
                    'fetchCurrencies': False, # Disable fetching currencies to avoid hitting sapi/api endpoints
                },
                'has': {
                    'fetchCurrencies': False
                },
                'enableRateLimit': True,
                'timeout': 60000, # Increased timeout to 60s
            }
            
            if self.proxy_url:
                options['proxies'] = {
                    'http': self.proxy_url,
                    'https': self.proxy_url
                }
                logger.info(f"Using proxy: {self.proxy_url}")
                
            self.exchange = ccxt.binanceusdm(options)
            logger.info("ccxt instance created")
            # Sync time difference to avoid timestamp errors
            try:
                self._sync_time_offset()
            except Exception as e:
                logger.warning(f"Failed to sync time offset: {e}")
            # Load markets to check connectivity
            self.exchange.load_markets()
            logger.info("Connected to Binance Futures Real Trading")
            
            # Set leverage with fallback logic
            try:
                self.exchange.set_leverage(self.leverage, self.symbol)
            except Exception as e:
                logger.warning(f"Could not set leverage {self.leverage}x: {e}. Retrying with fallback...")
                try:
                    self.exchange.set_leverage(10, self.symbol)
                    self.leverage = 10
                    logger.info("Fallback: Leverage set to 10x")
                except Exception as e2:
                    logger.warning(f"Could not set leverage 10x: {e2}. Retrying with 5x...")
                    try:
                        self.exchange.set_leverage(5, self.symbol)
                        self.leverage = 5
                        logger.info("Fallback: Leverage set to 5x")
                    except Exception as e3:
                        logger.error(f"Failed to set leverage (Initial, 10x, 5x): {e3}")
                
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
        self.position_entry_times = {} # Track entry time for active positions from history analysis
        self.open_orders_count = 0 # Track open orders count
        self.last_equity = 0.0
        
        # Cache for open orders to avoid rate limits
        self.cached_open_orders = []
        self.last_open_orders_fetch = 0
        self.open_orders_cache_ttl = 30 # 30 seconds cache for open orders
        
        # Backoff configuration
        self._max_retry = 5
        self._base_backoff = 1.0

    def _is_rate_limit_error(self, e: Exception) -> bool:
        msg = str(e).lower()
        return ('rate limit' in msg) or ('too many' in msg) or ('429' in msg) or ('-1003' in msg)

    def _is_timestamp_error(self, e: Exception) -> bool:
        msg = str(e).lower()
        return ('-1021' in msg) or ('timestamp for this request' in msg) or ('time difference' in msg)

    def _sync_time_offset(self):
        """Align local clock with exchange by computing timeDifference (ms)."""
        server_ms = self.exchange.fetch_time()
        local_ms = int(time.time() * 1000)
        # Positive when local clock is ahead of server
        self.exchange.timeDifference = local_ms - server_ms
        logger.info(f"[TimeSync] timeDifference set to {self.exchange.timeDifference} ms (local - server)")

    def _safe_exchange_call(self, method: str, *args, **kwargs):
        attempts = 0
        last_exc = None
        while attempts < self._max_retry:
            try:
                func = getattr(self.exchange, method)
                return func(*args, **kwargs)
            except Exception as e:
                last_exc = e
                if self._is_timestamp_error(e):
                    try:
                        self._sync_time_offset()
                        logger.warning(f"[TimeSync] Adjusted timeDifference={getattr(self.exchange, 'timeDifference', 'unknown')} ms due to -1021")
                    except Exception as te:
                        logger.warning(f"[TimeSync] Failed to sync time offset: {te}")
                    time.sleep(1.0)
                    attempts += 1
                    continue
                if self._is_rate_limit_error(e):
                    attempts += 1
                    sleep_s = min(self._base_backoff * (2 ** (attempts - 1)), 30)
                    logger.warning(f"[Backoff] {method} rate-limited. Attempt {attempts}/{self._max_retry}. Sleep {sleep_s:.1f}s")
                    time.sleep(sleep_s)
                    continue
                else:
                    raise
        raise last_exc

    def record_equity(self):
        """Record current equity state to history file."""
        if not self.exchange: return
        try:
            balance = self.exchange.fetch_balance()
            if balance:
                info = balance.get('info', {})
                # Try to get Total Equity (Margin Balance)
                if 'totalMarginBalance' in info:
                    total_equity = float(info['totalMarginBalance'])
                else:
                    total_equity = float(balance.get('total', {}).get('USDT', 0.0))
                
                # Try to get Wallet Balance
                if 'totalWalletBalance' in info:
                    total_balance = float(info['totalWalletBalance'])
                else:
                    total_balance = float(balance.get('free', {}).get('USDT', 0.0))
                
                # Try to get Unrealized PnL
                if 'totalUnrealizedProfit' in info:
                    unrealized_pnl = float(info['totalUnrealizedProfit'])
                else:
                    unrealized_pnl = 0.0
                
                self.equity_recorder.record(total_equity, total_balance, unrealized_pnl)
                logger.info(f"Recorded equity: {total_equity} (Wallet: {total_balance}, PnL: {unrealized_pnl})")
            else:
                logger.warning("Could not record equity: Failed to fetch balance.")
        except Exception as e:
            logger.error(f"Failed to record equity: {e}")

    def get_balance(self):
        if not self.exchange:
            logger.warning(f"get_balance: Exchange is None. Status was: {self.last_connection_status}")
            if self.last_connection_status != "Error":
                self.last_connection_status = "Disconnected"
            return 0.0
        try:
            balance = self._safe_exchange_call('fetch_balance')
            
            # Use totalMarginBalance if available (Wallet + Unrealized PnL)
            # This is the "Equity" that users typically care about
            if 'info' in balance and 'totalMarginBalance' in balance['info']:
                total_balance = float(balance['info']['totalMarginBalance'])
            else:
                total_balance = balance['USDT']['total']
            
            if self.initial_balance is None:
                self.initial_balance = total_balance
            if total_balance > 0:
                self.last_equity = total_balance
            
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
            balance = self._safe_exchange_call('fetch_balance')
            # Prefer totalMarginBalance (Equity)
            if 'info' in balance and 'totalMarginBalance' in balance['info']:
                equity = float(balance['info']['totalMarginBalance'])
            else:
                equity = float(balance['USDT']['total'])
            if equity > 0:
                self.last_equity = equity
            return equity
        except Exception as e:
            logger.error(f"Error fetching total balance: {e}")
            if self.last_equity > 0:
                return self.last_equity
            if self.initial_balance:
                try:
                    return float(self.initial_balance)
                except Exception:
                    return 0.0
            return 0.0

    def get_open_orders(self, symbol: str = None):
        """Fetch all open orders (standard + algo)"""
        if not self.exchange:
            return []
            
        try:
            # 1. Fetch Standard Open Orders
            open_orders = []
            if symbol:
                try:
                    open_orders = self._safe_exchange_call('fetch_open_orders', symbol)
                except Exception as e:
                    logger.warning(f"Failed to fetch open orders for {symbol}: {e}")
            else:
                # Try to use cache first
                import time
                now = time.time()
                if self.cached_open_orders and (now - self.last_open_orders_fetch < self.open_orders_cache_ttl):
                    open_orders = self.cached_open_orders
                else:
                    # Optimization: For Binance Futures, global fetch_open_orders is Weight 40.
                    # Per-symbol fetch is Weight 1.
                    # If we have < 40 monitored symbols, it's cheaper to loop.
                    use_global_fetch = True
                    if self.monitored_symbols and len(self.monitored_symbols) < 30:
                        use_global_fetch = False
                    
                    if use_global_fetch:
                        # Try global fetch first
                        try:
                            open_orders = self._safe_exchange_call('fetch_open_orders')
                            self.cached_open_orders = open_orders
                            self.last_open_orders_fetch = now
                        except Exception as e:
                            # Fallback to monitored symbols
                            use_global_fetch = False
                    
                    if not use_global_fetch:
                        # Fetch per symbol
                        unique_symbols = list(set(self.monitored_symbols))
                        temp_orders = []
                        for sym in unique_symbols:
                            try:
                                orders = self._safe_exchange_call('fetch_open_orders', sym)
                                temp_orders.extend(orders)
                            except Exception:
                                pass
                        open_orders = temp_orders
                        self.cached_open_orders = open_orders
                        self.last_open_orders_fetch = now

            # 2. Fetch Algo Orders
            algo_orders = []
            try:
                params = {}
                if symbol:
                    params['symbol'] = symbol.replace('/', '').replace(':USDT', '').replace(':BUSD', '')
                
                # fapiPrivateGetOpenAlgoOrders returns orders for all symbols if symbol param is omitted
                raw_algos = self._safe_exchange_call('fapiPrivateGetOpenAlgoOrders', params)
                algo_orders = raw_algos
            except Exception as e:
                logger.warning(f"Could not fetch algo orders: {e}")

            # 3. Format and Combine
            formatted_orders = []

            for o in open_orders:
                formatted_orders.append({
                    'id': str(o['id']),
                    'symbol': o['symbol'],
                    'type': o['type'],
                    'side': o['side'],
                    'price': float(o.get('price') or 0.0),
                    'amount': float(o.get('amount') or 0.0),
                    'filled': float(o.get('filled') or 0.0),
                    'remaining': float(o.get('remaining') or 0.0),
                    'status': o.get('status'),
                    'stop_price': float(o.get('stopPrice') or 0.0),
                    'reduce_only': o.get('reduceOnly', False),
                    'timestamp': o['timestamp'],
                    'datetime': o.get('datetime'),
                    'is_algo': False
                })

            for o in algo_orders:
                # Algo order structure is different
                # e.g. {'algoId': 123, 'symbol': 'BTCUSDT', 'side': 'BUY', 'orderType': 'STOP', ...}
                formatted_orders.append({
                    'id': str(o.get('algoId')),
                    'symbol': o.get('symbol'),
                    'type': o.get('orderType', 'ALGO'),
                    'side': o.get('side', '').lower(),
                    'price': float(o.get('price') or 0.0), # might be 0 for market
                    'amount': float(o.get('quantity') or o.get('executedQty') or 0.0),
                    'filled': float(o.get('executedQty') or 0.0),
                    'remaining': 0.0, # Not usually provided for algo orders until triggered
                    'status': 'NEW', # Algo orders are usually pending/new
                    'stop_price': float(o.get('stopPrice') or o.get('triggerPrice') or 0.0),
                    'reduce_only': o.get('reduceOnly', False),
                    'timestamp': o.get('bookTime') or o.get('updateTime'),
                    'datetime': None, # Client can convert
                    'is_algo': True
                })

            return formatted_orders

        except Exception as e:
            logger.error(f"Error in get_open_orders: {e}")
            return []

    def get_positions(self, symbol: str = None):
        """Fetch all active positions from the account, or only for a specific symbol"""
        if not self.exchange:
            return {}
        
        try:
            # 1. Fetch positions
            positions = self._safe_exchange_call('fetch_positions')

            # Filter if symbol provided
            if symbol:
                positions = [p for p in positions if p['symbol'] == symbol]

            # 2. Identify active symbols to fetch orders for
            active_symbols = []
            active_count = 0
            for pos in positions:
                amt = 0.0
                try:
                    amt = float(pos.get('contracts', 0) or 0)
                except Exception:
                    amt = 0.0
                if amt == 0:
                    info = pos.get('info', {})
                    try:
                        amt = float(info.get('positionAmt', 0) or 0)
                    except Exception:
                        amt = 0.0
                if abs(amt) > 0:
                    active_symbols.append(pos['symbol'])
                    active_count += 1
            
            if active_count > 0:
                 logger.info(f"DEBUG: fetch_positions found {active_count} active positions: {active_symbols}")

            if symbol and symbol not in active_symbols:
                active_symbols.append(symbol)

            # 3. Fetch Open Orders
            open_orders = []
            import time
            now = time.time()
            
            if symbol:
                try:
                    open_orders = self._safe_exchange_call('fetch_open_orders', symbol)
                except Exception as e:
                    logger.warning(f"Failed to fetch open orders for {symbol}: {e}")
            else:
                if self.cached_open_orders and (now - self.last_open_orders_fetch < self.open_orders_cache_ttl):
                    open_orders = self.cached_open_orders
                else:
                    open_orders = []
                    unique_symbols = list(set(active_symbols))
                    for sym in unique_symbols:
                        try:
                            orders = self._safe_exchange_call('fetch_open_orders', sym)
                            open_orders.extend(orders)
                        except Exception as e:
                            logger.warning(f"Failed to fetch open orders for {sym}: {e}")
                    self.cached_open_orders = open_orders
                    self.last_open_orders_fetch = now
                
            # 4. Fetch Algo Orders
            algo_orders = []
            try:
                params = {}
                if symbol:
                    params['symbol'] = symbol.replace('/', '').replace(':USDT', '')
                raw_algos = self._safe_exchange_call('fapiPrivateGetOpenAlgoOrders', params)
                algo_orders = raw_algos
            except Exception as e:
                logger.warning(f"Could not fetch algo orders: {e}")

            self.open_orders_count = len(open_orders) + len(algo_orders)

            orders_by_symbol = {}
            orders_by_raw_symbol = {} 

            for order in open_orders:
                sym = order['symbol']
                norm_sym = sym.replace('/', '').replace(':USDT', '').replace(':BUSD', '')
                if norm_sym not in orders_by_symbol:
                    orders_by_symbol[norm_sym] = {'sl': 0.0, 'tp': 0.0}
                
                order_type = order.get('type')
                stop_price = float(order.get('stopPrice') or 0.0)
                
                if stop_price > 0:
                     if 'STOP' in order_type:
                         orders_by_symbol[norm_sym]['sl'] = stop_price
                     elif 'TAKE_PROFIT' in order_type:
                         orders_by_symbol[norm_sym]['tp'] = stop_price

            for algo in algo_orders:
                raw_sym = algo['symbol']
                if raw_sym not in orders_by_raw_symbol:
                    orders_by_raw_symbol[raw_sym] = {'sl': 0.0, 'tp': 0.0}
                
                o_type = algo.get('orderType', '')
                stop_price = float(algo.get('triggerPrice') or 0.0)
                if stop_price == 0:
                    stop_price = float(algo.get('stopPrice') or 0.0)
                
                if stop_price > 0:
                    if 'STOP' in o_type:
                        orders_by_raw_symbol[raw_sym]['sl'] = stop_price
                    elif 'TAKE_PROFIT' in o_type:
                        orders_by_raw_symbol[raw_sym]['tp'] = stop_price

            active_positions = {}
            for pos in positions:
                amt = 0.0
                try:
                    amt = float(pos.get('contracts', 0) or 0)
                except Exception:
                    amt = 0.0
                if amt == 0:
                    info = pos.get('info', {})
                    try:
                        amt = float(info.get('positionAmt', 0) or 0)
                    except Exception:
                        amt = 0.0
                
                logger.info(f"DEBUG: Checking pos {pos['symbol']}, amt={amt}")
                
                if abs(amt) > 0:
                    try:
                        symbol = pos['symbol']
                        unrealized_pnl = float(pos.get('unrealizedPnl') or 0.0)
                        initial_margin = float(pos.get('initialMargin') or 0.0)
                        mark_price = float(pos.get('markPrice') or 0.0)
                        amount = abs(amt)
                        position_value_usdt = amount * mark_price
                        
                        leverage = self.leverage
                        # Prioritize raw info leverage as it is most reliable for Binance Futures
                        if 'info' in pos and 'leverage' in pos['info']:
                            try:
                                leverage = float(pos['info']['leverage'])
                            except:
                                pass
                        elif pos.get('leverage'):
                            leverage = float(pos['leverage'])
                        
                        if initial_margin == 0 and leverage > 0:
                            entry_value = float(pos.get('entryPrice') or 0.0) * amount
                            initial_margin = entry_value / leverage
                        
                        roi = (unrealized_pnl / initial_margin * 100) if initial_margin > 0 else 0.0
                        
                        sl_price = 0.0
                        tp_price = 0.0
                        
                        raw_symbol_lookup = symbol.replace('/', '').replace(':USDT', '').replace(':BUSD', '')
                        base_symbol = symbol.split('/')[0]
                        
                        if raw_symbol_lookup in orders_by_symbol:
                             if orders_by_symbol[raw_symbol_lookup]['sl'] > 0:
                                 sl_price = orders_by_symbol[raw_symbol_lookup]['sl']
                             if orders_by_symbol[raw_symbol_lookup]['tp'] > 0:
                                 tp_price = orders_by_symbol[raw_symbol_lookup]['tp']
                                 
                        if sl_price == 0:
                            if raw_symbol_lookup in orders_by_raw_symbol:
                                 sl_val = orders_by_raw_symbol[raw_symbol_lookup]['sl']
                                 if sl_val > 0: sl_price = sl_val
                            elif base_symbol + 'USDT' in orders_by_raw_symbol:
                                 sl_val = orders_by_raw_symbol[base_symbol + 'USDT']['sl']
                                 if sl_val > 0: sl_price = sl_val
                                 
                        if tp_price == 0:
                            if raw_symbol_lookup in orders_by_raw_symbol:
                                 tp_val = orders_by_raw_symbol[raw_symbol_lookup]['tp']
                                 if tp_val > 0: tp_price = tp_val
                            elif base_symbol + 'USDT' in orders_by_raw_symbol:
                                 tp_val = orders_by_raw_symbol[base_symbol + 'USDT']['tp']
                                 if tp_val > 0: tp_price = tp_val
                        
                        display_symbol = symbol.replace(':USDT', '')
                        
                        active_positions[display_symbol] = {
                            'symbol': display_symbol,
                            'side': pos.get('side', 'long' if amt > 0 else 'short'),
                            'amount': amount,
                            'position_value_usdt': position_value_usdt,
                            'entry_price': float(pos.get('entryPrice') or 0.0),
                            'unrealized_pnl': unrealized_pnl,
                            'pnl_pct': roi,
                            'liquidation_price': float(pos.get('liquidationPrice') or 0.0),
                            'mark_price': mark_price,
                            'initial_margin': initial_margin,
                            'roi': roi,
                            'leverage': leverage,
                            'sl_price': sl_price,
                            'tp_price': tp_price,
                            'entry_time': self.position_entry_times.get(raw_symbol_lookup)
                        }
                    except Exception as e:
                        logger.error(f"Error processing position {pos.get('symbol', 'unknown')}: {e}")
                        continue
            return active_positions
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return {}

    def get_position(self):
        """Legacy method: get position for current tracked symbol only"""
        # Optimized: use symbol param to reduce API weight
        all_pos = self.get_positions(self.symbol)
        if all_pos:
            return next(iter(all_pos.values()))
        return None

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
        Limit: Total Leverage <= 10x
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
            
            # Max Daily Loss Limit (from config)
            config = self.config_manager.get_config()
            max_dd_limit = config.get('max_drawdown_limit', 0.10)
            
            max_daily_loss = total_equity * max_dd_limit
            if daily_pnl < -max_daily_loss:
                logger.warning(f"Risk Check Failed: Daily Loss {daily_pnl:.2f} exceeds limit {-max_daily_loss:.2f} ({max_dd_limit*100}%)")
                return False
                
            current_total_notional = sum(pos['position_value_usdt'] for pos in positions.values())
            projected_total_notional = current_total_notional + new_position_value_usdt
            
            projected_leverage = projected_total_notional / total_equity
            config = self.config_manager.get_config()
            max_lev = float(config.get('max_portfolio_leverage', 10.0))
            if projected_leverage > max_lev:
                logger.warning(f"Risk Check Failed: Projected Leverage {projected_leverage:.2f}x > {max_lev:.0f}x Limit")
                return False
                
            return True
        except Exception as e:
            logger.error(f"Error checking risk limit: {e}")
            return False # Fail safe

    def _smart_entry(self, symbol: str, side: str, amount: float, timeout: int = 5):
        """
        Smart Entry Logic (Phase 4):
        1. Try to place Limit Order at Best Bid (Buy) or Best Ask (Sell) to be a Maker.
        2. Wait for `timeout` seconds.
        3. If not filled, Cancel and Chase with Market Order (Taker).
        """
        try:
            # 1. Fetch Ticker for Best Price
            ticker = self._safe_exchange_call('fetch_ticker', symbol)
            # Buy: Bid (Maker), Sell: Ask (Maker)
            price = float(ticker['bid']) if side == 'buy' else float(ticker['ask'])
            
            # Ensure price precision
            price = float(self.exchange.price_to_precision(symbol, price))
            
            # 2. Place Limit Order
            logger.info(f"⏳ Smart Entry: Placing LIMIT {side} {amount} @ {price}...")
            # Note: Binance Futures Limit Order requires timeInForce usually, default GTC is fine
            limit_order = self._safe_exchange_call('create_order', symbol, 'LIMIT', side, amount, price, params={'timeInForce': 'GTC'})
            
            # 3. Wait and Monitor
            start_time = time.time()
            filled_amount = 0.0
            
            while time.time() - start_time < timeout:
                time.sleep(1) # Check every 1s
                
                try:
                    updated_order = self._safe_exchange_call('fetch_order', limit_order['id'], symbol)
                    status = updated_order['status']
                    
                    if status == 'closed':
                        logger.info(f"✅ Smart Entry: LIMIT Filled @ {updated_order.get('average', price)}")
                        return updated_order
                        
                    if status == 'canceled':
                        logger.warning("Smart Entry: Order canceled externally. Switching to Market.")
                        break
                        
                except Exception as e:
                    logger.warning(f"Smart Entry: Error monitoring order: {e}")
            
            # 4. Timeout or Cancelled -> Chase with Market
            logger.info(f"⚡ Smart Entry: Timeout ({timeout}s). Canceling LIMIT and Chasing MARKET...")
            
            # Cancel Limit
            cancel_success = False
            try:
                self._safe_exchange_call('cancel_order', limit_order['id'], symbol)
                cancel_success = True
            except Exception as e:
                logger.warning(f"Smart Entry: Cancel failed (might be filled): {e}")
            
            # Check status one last time to avoid double fill
            try:
                final_check = self._safe_exchange_call('fetch_order', limit_order['id'], symbol)
                if final_check['status'] == 'closed':
                    logger.info("Smart Entry: Limit actually filled during cancel.")
                    return final_check
                
                filled_amount = float(final_check.get('filled', 0.0))
            except Exception as e:
                logger.error(f"Smart Entry: Failed final check. {e}")
                if not cancel_success:
                    logger.error("Smart Entry: CRITICAL - Cancel failed AND Fetch failed. Aborting chase to avoid double fill.")
                    raise Exception(f"Smart Entry Critical Error: Cancel & Fetch failed for {limit_order['id']}")
                else:
                    # If cancel succeeded but fetch failed, we assume 0 filled (risky but rare) or abort?
                    # Safest is to abort to prevent over-buying
                    logger.error("Smart Entry: Cancel success but Fetch failed. Aborting chase.")
                    raise e
                
            remaining = amount - filled_amount
            if remaining > 0:
                # Adjust precision
                remaining = float(self.exchange.amount_to_precision(symbol, remaining))
                logger.info(f"Smart Entry: Executing Market Order for remaining {remaining}...")
                market_order = self._safe_exchange_call('create_order', symbol, 'MARKET', side, remaining)
                
                # If we had partial fill, strictly speaking we should merge results, 
                # but returning the market order is sufficient for execute_trade to get 'average' price 
                # (which dominates the cost basis if limit fill was small).
                return market_order
            else:
                return final_check

        except Exception as e:
            logger.error(f"Smart Entry Failed: {e}. Fallback to Market.")
            return self._safe_exchange_call('create_order', symbol, 'MARKET', side, amount)

    def _grid_entry(self, symbol: str, side: str, amount: float, levels: int = 3, spacing_pct: float = 0.0015, wait_s: int = 6):
        try:
            ticker = self._safe_exchange_call('fetch_ticker', symbol)
            base_price = float(ticker['bid']) if side == 'buy' else float(ticker['ask'])
            base_price = float(self.exchange.price_to_precision(symbol, base_price))

            levels = max(1, int(levels or 1))
            spacing_pct = float(spacing_pct or 0.0)
            wait_s = max(1, int(wait_s or 1))

            chunk_size = amount / levels
            chunk_size = float(self.exchange.amount_to_precision(symbol, chunk_size))
            last_chunk = amount - (chunk_size * (levels - 1))
            last_chunk = float(self.exchange.amount_to_precision(symbol, last_chunk))

            placed_orders = []
            for i in range(levels):
                qty = last_chunk if i == levels - 1 else chunk_size
                if qty <= 0:
                    continue
                level_price = base_price * (1 - spacing_pct * i) if side == 'buy' else base_price * (1 + spacing_pct * i)
                level_price = float(self.exchange.price_to_precision(symbol, level_price))
                o = self._safe_exchange_call('create_order', symbol, 'LIMIT', side, qty, level_price, params={'timeInForce': 'GTC'})
                placed_orders.append(o)

            start_time = time.time()
            while time.time() - start_time < wait_s:
                time.sleep(1)

            total_filled = 0.0
            total_cost = 0.0
            for o in placed_orders:
                try:
                    st = self._safe_exchange_call('fetch_order', o['id'], symbol)
                except Exception:
                    continue

                filled = float(st.get('filled') or 0.0)
                avg = st.get('average')
                px = float(avg) if avg else float(st.get('price') or o.get('price') or base_price)

                total_filled += filled
                total_cost += filled * px

                if st.get('status') not in ('closed', 'canceled'):
                    try:
                        self._safe_exchange_call('cancel_order', o['id'], symbol)
                    except Exception:
                        pass

            remaining = amount - total_filled
            last_order = placed_orders[-1] if placed_orders else {}
            if remaining > 0:
                remaining = float(self.exchange.amount_to_precision(symbol, remaining))
                chase = self._smart_entry(symbol, side, remaining, timeout=3)
                chase_filled = float(chase.get('filled') or remaining)
                chase_avg = chase.get('average')
                chase_px = float(chase_avg) if chase_avg else base_price
                total_filled += chase_filled
                total_cost += chase_filled * chase_px
                last_order = chase

            avg_price = (total_cost / total_filled) if total_filled > 0 else base_price
            result = dict(last_order) if isinstance(last_order, dict) else {}
            result['filled'] = total_filled
            result['average'] = avg_price
            if total_filled >= amount * 0.999:
                result['status'] = 'closed'
            return result
        except Exception as e:
            logger.error(f"Grid Entry Failed: {e}. Fallback to Smart Entry.")
            return self._smart_entry(symbol, side, amount, timeout=5)

    def execute_trade(self, signal: int, sl_pct: float = None, tp_pct: float = None, sl_price: float = None, tp_price: float = None, leverage: int = None, amount_coins: float = None, symbol: str = None, entry_style: str = None, grid_levels: int = None, grid_spacing_pct: float = None, grid_wait_s: int = None):
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
            # Optimized: Explicitly fetch status (positions + open orders) for target_symbol
            # This ensures we don't miss any pending orders for the symbol we are about to trade.
            all_pos = self.get_positions(target_symbol)
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
                        lv = min(int(leverage), 10)
                        self.exchange.set_leverage(lv, target_symbol)
                        current_leverage = lv
                        # Don't update self.leverage globally if we are supporting multi-symbol with one instance, 
                        # but usually RealTrader is per-symbol. If using dynamic symbol, just log it.
                        logger.info(f"Set dynamic leverage to {current_leverage}x for {target_symbol}")
                    except Exception as e:
                        logger.warning(f"Could not set dynamic leverage: {e}")

                # Load SL/TP defaults from config if not provided
                try:
                    cfg = self.config_manager.get_config()
                    if sl_pct is None:
                        sl_pct = float(cfg.get('sl_pct', 0.02))
                    if tp_pct is None:
                        tp_pct = float(cfg.get('tp_pct', 0.06))
                except Exception:
                    sl_pct = sl_pct or 0.02
                    tp_pct = tp_pct or 0.06

                # Calculate amount
                try:
                    ticker = self._safe_exchange_call('fetch_ticker', target_symbol)
                except Exception as e:
                    logger.error(f"Failed to fetch ticker for {target_symbol}: {e}")
                    return
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
                
                # --- Execution Optimization: TWAP Logic for Large Orders ---
                # If order value > 5000 USDT, split into 3 parts to reduce slippage
                twap_threshold = 5000.0
                executed_amount = 0.0
                avg_entry_price = 0.0
                
                import time
                
                if notional_value > twap_threshold:
                    logger.info(f"🚀 Large Order Detected (${notional_value:.2f}). Executing TWAP (3 splits)...")
                    chunks = 3
                    chunk_size = amount / chunks
                    # Adjust chunk precision
                    chunk_size = float(self.exchange.amount_to_precision(target_symbol, chunk_size))
                    
                    # Recalculate last chunk to match total exactly (avoid precision drift)
                    last_chunk = amount - (chunk_size * (chunks - 1))
                    last_chunk = float(self.exchange.amount_to_precision(target_symbol, last_chunk))
                    
                    fills = []
                    
                    for i in range(chunks):
                        current_chunk = last_chunk if i == chunks - 1 else chunk_size
                        if current_chunk <= 0: continue
                        
                        try:
                            logger.info(f"TWAP Part {i+1}/{chunks}: {current_chunk} {target_symbol}")
                            order = self._safe_exchange_call('create_order', target_symbol, 'market', side, current_chunk)
                            fills.append(order)
                            if i < chunks - 1:
                                time.sleep(2) # 2s delay between chunks
                        except Exception as e:
                            logger.error(f"TWAP Part {i+1} failed: {e}")
                    
                    # Calculate weighted average entry price
                    total_cost = 0.0
                    total_qty = 0.0
                    for o in fills:
                        if o.get('average'):
                            filled = float(o['filled'])
                            avg_price = float(o['average'])
                            total_cost += filled * avg_price
                            total_qty += filled
                    
                    if total_qty > 0:
                        entry_price = total_cost / total_qty
                        executed_amount = total_qty
                        # Use the LAST order ID for reference, or a composite ID
                        order = fills[-1] if fills else {}
                        order['average'] = entry_price # Mock for later usage
                    else:
                        logger.error("TWAP Execution failed completely.")
                        return

                else:
                    # Standard Execution (Smart Entry Phase 4)
                    try:
                        if (entry_style or "").lower() == "grid":
                            order = self._grid_entry(
                                target_symbol,
                                side,
                                amount,
                                levels=grid_levels or 3,
                                spacing_pct=grid_spacing_pct if grid_spacing_pct is not None else 0.0015,
                                wait_s=grid_wait_s or 6,
                            )
                        else:
                            order = self._smart_entry(target_symbol, side, amount, timeout=5)
                        
                        logger.info(f"Order placed: {order['id']}")
                        executed_amount = float(order['filled']) if order.get('filled') else amount
                        entry_price = float(order['average']) if order.get('average') else price
                        
                        # Fallback if average is None
                        if entry_price == 0.0:
                            entry_price = price
                            
                    except Exception as e:
                        if "insufficient" in str(e).lower() or "margin" in str(e).lower():
                            logger.warning(f"Skipping trade due to insufficient margin: {e}")
                            return
                        else:
                            raise e
                
                # Place SL/TP
                # entry_price is now set correctly from either TWAP or Standard
                
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

                sltp_amount = float(self.exchange.amount_to_precision(target_symbol, executed_amount if executed_amount > 0 else amount))
                
                # Stop Loss (Hard SL is good for safety)
                # Use reduceOnly instead of closePosition to avoid API error -4130 if existing orders conflict
                self._safe_exchange_call('create_order', target_symbol, 'STOP_MARKET', sl_side, sltp_amount, params={
                    'stopPrice': self.exchange.price_to_precision(target_symbol, real_sl),
                    'reduceOnly': True 
                })
                
                # Take Profit (Hard TP)
                self._safe_exchange_call('create_order', target_symbol, 'TAKE_PROFIT_MARKET', sl_side, sltp_amount, params={
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

    def close_partial(self, amount: float, symbol: str = None):
        """
        Close a partial amount of the position for the given symbol (or default symbol).
        Uses reduceOnly=True to ensure we don't flip position.
        """
        target_symbol = symbol if symbol else self.symbol
        
        try:
            # Fetch positions for target symbol
            positions = self.get_positions(target_symbol)
            
            if not positions:
                 logger.warning(f"close_partial: No active position for {target_symbol}")
                 return

            # Take the first position found (should be only one if target_symbol provided)
            pos = next(iter(positions.values()))
            
            side = pos['side']
            # If long, we sell. If short, we buy.
            order_side = 'sell' if side == 'long' else 'buy'
            
            # Ensure amount is within limits
            current_qty = float(pos['amount'])
            if amount > current_qty:
                amount = current_qty
                
            # Execute
            logger.info(f"Executing Partial Close for {target_symbol}: {order_side} {amount} (reduceOnly)")
            
            # Use safe exchange call
            # Use target_symbol (CCXT symbol) for order creation
            # Note: pos['symbol'] might be display symbol, use target_symbol
            order = self._safe_exchange_call('create_order', target_symbol, 'market', order_side, amount, params={'reduceOnly': True})
            
            logger.info(f"Partial Close executed: {order['id']}")
            
            if self.notifier:
                self.notifier.send_text(f"💰 Partial Close (TP): {target_symbol}\nAmount: {amount}\nPrice: {order.get('average', 'Market')}")
                
        except Exception as e:
            logger.error(f"Error in close_partial: {e}")

    def _close_position_by_symbol(self, symbol, pos):
        """Helper to close position for a specific symbol"""
        try:
            side = 'sell' if pos['side'] == 'long' else 'buy'
            amount = float(pos['amount'])
            
            logger.info(f"Closing {pos['side']} position: {side} {amount} {symbol}")
            order = self._safe_exchange_call('create_order', symbol, 'market', side, amount)
            logger.info(f"Close order placed: {order['id']}")
            
            # Cancel all open orders (SL/TP)
            try:
                self._safe_exchange_call('cancel_all_orders', symbol)
            except Exception as e:
                logger.warning(f"Failed to cancel all orders for {symbol}: {e}")
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
            open_orders = []
            try:
                open_orders = self._safe_exchange_call('fetch_open_orders', target_symbol)
            except Exception as e:
                logger.warning(f"Failed to fetch open orders for {target_symbol}: {e}")
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
                self._safe_exchange_call('create_order', target_symbol, 'STOP_MARKET', sl_side, amount, params={
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
        # Auto-repair SL orders and clean stale pending orders on start
        try:
            self.cleanup_stale_orders()
            self.repair_orders()
        except Exception as e:
            logger.error(f"Failed to auto-repair orders on start: {e}")

    def stop(self):
        self.active = False
        logger.info("Real trading stopped.")

    def reset(self):
        logger.warning("Reset not supported for Real Trading. Please manage account manually.")

    def get_recent_trades(self, limit: int = 1000, symbols: list = None):
        if not self.exchange:
            return []
            
        # Cache Check
        import time
        current_time = time.time()
        if not symbols and self.trade_history_cache and (current_time - self.last_history_update < 60):
            return self.trade_history_cache

        try:
            trades = []
            target_symbols = symbols if symbols else self.monitored_symbols
            
            if target_symbols:
                # Multi-symbol fetch
                for sym in target_symbols:
                    try:
                        # Limit per coin to avoid fetching too much data
                        limit_per_coin = 500 if len(target_symbols) > 5 else limit
                        t = self.exchange.fetch_my_trades(sym, limit=limit_per_coin) 
                        trades.extend(t)
                    except Exception as e:
                        # logger.warning(f"Failed to fetch trades for {sym}: {e}")
                        pass
            else:
                # Fallback
                trades = self.exchange.fetch_my_trades(self.symbol, limit=limit)
            
            # --- Entry Time Matching Logic ---
            # Sort by timestamp ASC to simulate position history
            trades.sort(key=lambda x: x['timestamp'])
            symbol_state = {}
            closed_roundtrips = []

            def _fee_cost(fee_obj) -> float:
                if isinstance(fee_obj, dict):
                    try:
                        return float(fee_obj.get('cost', 0.0))
                    except Exception:
                        return 0.0
                if isinstance(fee_obj, (int, float)):
                    return float(fee_obj)
                return 0.0

            for t in trades:
                sym = t['symbol'].replace('/', '').replace(':USDT', '').replace(':BUSD', '')
                if sym not in symbol_state:
                    symbol_state[sym] = {
                        'qty': 0.0,
                        'entry_time': None,
                        'position_side': None,
                        'entry_qty': 0.0,
                        'entry_cost': 0.0,
                        'exit_qty': 0.0,
                        'exit_cost': 0.0,
                        'realized_pnl': 0.0,
                        'fee': 0.0,
                        'last_exit_ts': None
                    }

                st = symbol_state[sym]
                side = t['side']
                amount = float(t.get('amount') or 0.0)
                if amount <= 0:
                    continue

                qty_change = amount if side == 'buy' else -amount
                prev_qty = st['qty']
                new_qty = prev_qty + qty_change

                realized_pnl = 0.0
                if 'info' in t and 'realizedPnl' in t['info']:
                    try:
                        realized_pnl = float(t['info']['realizedPnl'])
                    except Exception:
                        realized_pnl = 0.0
                elif 'realizedPnl' in t:
                    try:
                        realized_pnl = float(t['realizedPnl'])
                    except Exception:
                        realized_pnl = 0.0

                fee_cost = _fee_cost(t.get('fee'))

                if prev_qty == 0 and new_qty != 0:
                    st['entry_time'] = t['timestamp']
                    st['position_side'] = 'LONG' if new_qty > 0 else 'SHORT'
                    st['entry_qty'] = amount
                    st['entry_cost'] = float(t.get('price') or 0.0) * amount
                    st['exit_qty'] = 0.0
                    st['exit_cost'] = 0.0
                    st['realized_pnl'] = 0.0
                    st['fee'] = fee_cost
                    st['last_exit_ts'] = None
                else:
                    st['fee'] += fee_cost

                    if prev_qty != 0 and (prev_qty > 0) == (new_qty > 0) and abs(new_qty) > abs(prev_qty):
                        st['entry_qty'] += amount
                        st['entry_cost'] += float(t.get('price') or 0.0) * amount

                    elif prev_qty != 0 and abs(new_qty) < abs(prev_qty):
                        st['exit_qty'] += amount
                        st['exit_cost'] += float(t.get('price') or 0.0) * amount
                        st['realized_pnl'] += realized_pnl
                        st['last_exit_ts'] = t['timestamp']

                    elif prev_qty != 0 and ((prev_qty > 0 and new_qty < 0) or (prev_qty < 0 and new_qty > 0)):
                        closing_amount = min(amount, abs(prev_qty))
                        opening_amount = max(0.0, amount - closing_amount)

                        st['exit_qty'] += closing_amount
                        st['exit_cost'] += float(t.get('price') or 0.0) * closing_amount
                        st['realized_pnl'] += realized_pnl
                        st['last_exit_ts'] = t['timestamp']

                        if st['entry_time'] and st['entry_qty'] > 0 and st['exit_qty'] > 0:
                            entry_price = st['entry_cost'] / st['entry_qty']
                            exit_price = st['exit_cost'] / st['exit_qty']
                            roi = (st['realized_pnl'] / (entry_price * st['exit_qty']) * 100) if entry_price * st['exit_qty'] > 0 else 0.0
                            exit_ts = st['last_exit_ts'] or t['timestamp']
                            from datetime import datetime as _dt
                            closed_roundtrips.append({
                                'id': f"{sym}:{st['entry_time']}:{exit_ts}",
                                'symbol': sym,
                                'timestamp': exit_ts,
                                'datetime': _dt.fromtimestamp(exit_ts / 1000).isoformat(),
                                'side': 'sell' if st['position_side'] == 'LONG' else 'buy',
                                'price': exit_price,
                                'amount': st['exit_qty'],
                                'cost': st['exit_cost'],
                                'fee': st['fee'],
                                'realized_pnl': st['realized_pnl'],
                                'entry_price': entry_price,
                                'exit_price': exit_price,
                                'roi': roi,
                                'entry_time': st['entry_time'],
                                'position_side': st['position_side']
                            })

                        st['entry_time'] = t['timestamp']
                        st['position_side'] = 'LONG' if new_qty > 0 else 'SHORT'
                        st['entry_qty'] = opening_amount
                        st['entry_cost'] = float(t.get('price') or 0.0) * opening_amount
                        st['exit_qty'] = 0.0
                        st['exit_cost'] = 0.0
                        st['realized_pnl'] = 0.0
                        st['fee'] = 0.0
                        st['last_exit_ts'] = None

                st['qty'] = new_qty

                if st['qty'] == 0 and st['entry_time'] and st['exit_qty'] > 0:
                    entry_price = (st['entry_cost'] / st['entry_qty']) if st['entry_qty'] > 0 else 0.0
                    exit_price = (st['exit_cost'] / st['exit_qty']) if st['exit_qty'] > 0 else float(t.get('price') or 0.0)
                    roi = (st['realized_pnl'] / (entry_price * st['exit_qty']) * 100) if entry_price * st['exit_qty'] > 0 else 0.0
                    exit_ts = st['last_exit_ts'] or t['timestamp']
                    from datetime import datetime as _dt
                    closed_roundtrips.append({
                        'id': f"{sym}:{st['entry_time']}:{exit_ts}",
                        'symbol': sym,
                        'timestamp': exit_ts,
                        'datetime': _dt.fromtimestamp(exit_ts / 1000).isoformat(),
                        'side': 'sell' if st['position_side'] == 'LONG' else 'buy',
                        'price': exit_price,
                        'amount': st['exit_qty'],
                        'cost': st['exit_cost'],
                        'fee': st['fee'],
                        'realized_pnl': st['realized_pnl'],
                        'entry_price': entry_price,
                        'exit_price': exit_price,
                        'roi': roi,
                        'entry_time': st['entry_time'],
                        'position_side': st['position_side']
                    })

                    st['entry_time'] = None
                    st['position_side'] = None
                    st['entry_qty'] = 0.0
                    st['entry_cost'] = 0.0
                    st['exit_qty'] = 0.0
                    st['exit_cost'] = 0.0
                    st['realized_pnl'] = 0.0
                    st['fee'] = 0.0
                    st['last_exit_ts'] = None

            closed_roundtrips.sort(key=lambda x: x['timestamp'], reverse=True)

            if not symbols:
                self.trade_history_cache = closed_roundtrips
                self.last_history_update = current_time

            self.position_entry_times = {}
            for sym, st in symbol_state.items():
                if abs(st.get('qty', 0.0)) > 0 and st.get('entry_time'):
                    self.position_entry_times[sym] = st['entry_time']

            return closed_roundtrips
        except Exception as e:
            logger.error(f"Error fetching trades: {e}")
            return []

    def repair_orders(self, sl_pct: float = None, tp_pct: float = None):
        """
        Check all active positions and place SL/TP orders if missing.
        Default SL: 2% from Entry (Strategy Document).
        Default TP: 6% from Entry (Strategy Document).
        """
        if not self.exchange: return
        
        # Load from config if not provided
        try:
            cfg = self.config_manager.get_config()
            if sl_pct is None:
                sl_pct = float(cfg.get('sl_pct', 0.02))
            if tp_pct is None:
                tp_pct = float(cfg.get('tp_pct', 0.06))
        except Exception as e:
            logger.warning(f"repair_orders: Failed to load config, using defaults: {e}")
            sl_pct = sl_pct or 0.02
            tp_pct = tp_pct or 0.06
        
        try:
            # Optimized: Only check positions for the current symbol to save API weight
            # get_positions(self.symbol) will try to fetch only for this symbol if possible
            # or filter the result.
            positions = self.get_positions(self.symbol)
            
            for symbol, pos in positions.items():
                # Double check symbol match
                # Normalized symbol comparison
                norm_sym = symbol.replace('/', '').replace(':USDT', '').replace(':BUSD', '')
                norm_self = self.symbol.replace('/', '').replace(':USDT', '').replace(':BUSD', '')
                
                if norm_sym != norm_self:
                    continue

                sl_price = pos.get('sl_price', 0.0)
                tp_price = pos.get('tp_price', 0.0)
                
                entry_price = float(pos['entry_price'])
                amount = float(pos['amount'])
                side = pos['side']
                
                # Repair SL
                if sl_price <= 0:
                    logger.warning(f"[{symbol}] Missing SL! Placing default SL ({sl_pct*100}%)...")
                    
                    new_sl = 0.0
                    sl_side = ''
                    
                    if side == 'long':
                        new_sl = entry_price * (1 - sl_pct)
                        sl_side = 'sell'
                    else:
                        new_sl = entry_price * (1 + sl_pct)
                        sl_side = 'buy'
                        
                    try:
                        self._safe_exchange_call('create_order', symbol, 'STOP_MARKET', sl_side, amount, params={
                            'stopPrice': self.exchange.price_to_precision(symbol, new_sl),
                            'reduceOnly': True
                        })
                        logger.info(f"[{symbol}] Repaired SL at {new_sl}")
                    except Exception as e:
                        logger.error(f"[{symbol}] Failed to repair SL: {e}")
                
                # Repair TP
                if tp_price <= 0:
                    logger.warning(f"[{symbol}] Missing TP! Placing default TP ({tp_pct*100}%)...")
                    
                    new_tp = 0.0
                    tp_side = ''
                    
                    if side == 'long':
                        new_tp = entry_price * (1 + tp_pct)
                        tp_side = 'sell'
                    else:
                        new_tp = entry_price * (1 - tp_pct)
                        tp_side = 'buy'
                        
                    try:
                        self._safe_exchange_call('create_order', symbol, 'TAKE_PROFIT_MARKET', tp_side, amount, params={
                            'stopPrice': self.exchange.price_to_precision(symbol, new_tp),
                            'reduceOnly': True
                        })
                        logger.info(f"[{symbol}] Repaired TP at {new_tp}")
                    except Exception as e:
                        logger.error(f"[{symbol}] Failed to repair TP: {e}")

        except Exception as e:
            logger.error(f"Error in repair_orders: {e}")

    def cleanup_stale_orders(self):
        """
        Cancel open orders that no longer have an associated active position.
        This is mainly used to clean up old pending orders that may block new trades.
        """
        if not self.exchange:
            return

        try:
            # OPTIMIZATION: If self.symbol is set, only check for that symbol
            # This reduces API weight significantly (1 vs 40 for open orders)
            if self.symbol:
                # 1. Check if we have an active position for this symbol
                # Use get_positions to leverage existing logic (returns dict)
                positions = self.get_positions(self.symbol)
                has_position = len(positions) > 0
                
                # 2. Fetch open orders for this symbol ONLY
                try:
                    open_orders = self._safe_exchange_call('fetch_open_orders', self.symbol)
                except Exception as e:
                    logger.warning(f"cleanup_stale_orders: Failed to fetch open orders for {self.symbol}: {e}")
                    return

                if not open_orders:
                    return

                # 3. If no active position, cancel all orders (stale SL/TP or entry)
                # If active position exists, we keep orders (likely active SL/TP)
                if not has_position:
                    logger.info(f"cleanup_stale_orders: No active position for {self.symbol}. Cancelling {len(open_orders)} stale orders.")
                    for order in open_orders:
                        try:
                            self._safe_exchange_call('cancel_order', order['id'], self.symbol)
                        except Exception as e:
                            logger.warning(f"cleanup_stale_orders: Failed to cancel order {order['id']}: {e}")
                else:
                    # Optional: Check if orders match current position size? 
                    # For now, just keeping them is safer than cancelling active SL/TP.
                    pass
                
                return

            # FALLBACK: Global cleanup (original logic)
            # 1. Fetch current positions and collect active symbols
            raw_positions = self._safe_exchange_call('fetch_positions')
            active_raw_symbols = set()

            for pos in raw_positions:
                try:
                    contracts = float(pos.get('contracts', 0) or 0)
                except Exception:
                    contracts = 0.0

                # Fallback: some exchanges may expose position size only in info
                if contracts == 0:
                    info = pos.get('info', {})
                    try:
                        contracts = float(info.get('positionAmt', 0) or 0)
                    except Exception:
                        contracts = 0.0

                if abs(contracts) > 0:
                    raw_sym = pos['symbol'].replace('/', '').replace(':USDT', '').replace(':BUSD', '')
                    active_raw_symbols.add(raw_sym)

            # 2. Fetch all standard open orders (global). This call is heavy; use sparingly.
            try:
                open_orders = self._safe_exchange_call('fetch_open_orders')
            except Exception as e:
                logger.warning(f"cleanup_stale_orders: Failed to fetch open orders: {e}")
                open_orders = []

            stale_count = 0

            for order in open_orders:
                sym = order.get('symbol')
                if not sym:
                    continue

                raw_sym = sym.replace('/', '').replace(':USDT', '').replace(':BUSD', '')
                if raw_sym not in active_raw_symbols:
                    order_id = order.get('id')
                    logger.info(f"cleanup_stale_orders: Cancel stale order {order_id} on {sym} (no active position)")
                    try:
                        self._safe_exchange_call('cancel_order', order_id, sym)
                        stale_count += 1
                    except Exception as e:
                        logger.warning(f"cleanup_stale_orders: Failed to cancel order {order_id} on {sym}: {e}")

            if stale_count > 0:
                logger.info(f"cleanup_stale_orders: Cancelled {stale_count} stale open orders.")

        except Exception as e:
            logger.error(f"cleanup_stale_orders: Unexpected error: {e}")

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
            
        # User requested ALL history
        # We try to fetch as many as possible (up to 1000 is usually the max for one call)
        # If user has > 1000 trades, we might need pagination, but let's start with max limit.
        trades = self.get_recent_trades(limit=1000)
        
        total_pnl = 0.0
        total_fees = 0.0
        
        closed_trades_count = 0
        winning_trades_count = 0
        
        for t in trades:
            pnl = t.get('realized_pnl', 0.0)
            fee = 0.0
            if t.get('fee'):
                if isinstance(t['fee'], dict):
                    fee = float(t['fee'].get('cost', 0.0))
                elif isinstance(t['fee'], (int, float)):
                    fee = float(t['fee'])
            
            # Aggregate Totals
            # PnL in trade history usually doesn't subtract fee, so we do it manually to get Net PnL
            net_pnl = pnl - fee
            
            total_pnl += net_pnl
            total_fees += fee
            
            if abs(pnl) > 0 or fee > 0:
                closed_trades_count += 1
                if net_pnl > 0:
                    winning_trades_count += 1
        
        win_rate = (winning_trades_count / closed_trades_count * 100) if closed_trades_count > 0 else 0.0
        
        duration = datetime.now() - self.start_time
        duration_str = str(duration).split('.')[0] # HH:MM:SS
        
        return {
            "win_rate": win_rate,
            "total_trades": closed_trades_count,
            "total_pnl": total_pnl,
            "total_fees": total_fees,
            "duration": duration_str,
            "start_time": self.start_time.isoformat()
        }

    def get_status(self, current_price: float = None):
        """
        Return status dict compatible with PaperTrader
        """
        # Check cache
        now = time.time()
        if self.cached_status and (now - self.last_status_update < self.status_cache_ttl):
            return self.cached_status

        try:
            # Call get_recent_trades FIRST to populate position_entry_times for active positions
            trade_history = self.get_recent_trades(limit=1000)
            
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
            
            # Fetch detailed open orders
            open_orders = self.get_open_orders()
            self.open_orders_count = len(open_orders)
                
            status = {
                "active": self.active,
                "balance": balance,
                "total_balance": wallet_balance, # Wallet Balance (for display consistency)
                "equity": equity, # Real Equity
                "unrealized_pnl": unrealized_pnl, # Added Unrealized PnL
                "positions": positions_dict,
                "open_orders": open_orders, # Detailed open orders list for frontend
                "trade_history": trade_history,
                "stats": stats,
                "initial_balance": self.initial_balance if self.initial_balance else wallet_balance,
                "open_orders_count": self.open_orders_count, # Added open orders count
                "connection_status": self.last_connection_status,
                "connection_error": self.last_connection_error
            }

            # Update cache
            self.cached_status = status
            self.last_status_update = now
            return status

        except Exception as e:
            logger.error(f"Error in get_status: {e}")
            if self.cached_status:
                logger.info("Returning stale cached status due to error")
                stale_status = self.cached_status.copy()
                stale_status['connection_status'] = "Warning" # Indicate stale data
                stale_status['connection_error'] = str(e)
                return stale_status
            
            # If no cache, return error state
            return {
                "active": self.active,
                "balance": 0.0,
                "total_balance": 0.0,
                "equity": 0.0,
                "unrealized_pnl": 0.0,
                "positions": {},
                "trade_history": [],
                "stats": {"win_rate": 0.0, "total_trades": 0, "total_pnl": 0.0},
                "initial_balance": 0.0,
                "connection_status": "Error",
                "connection_error": str(e)
            }
