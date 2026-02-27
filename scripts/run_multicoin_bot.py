import time
import logging
from logging.handlers import RotatingFileHandler
import os
import sys
import json
from dotenv import load_dotenv
import fcntl
import errno

# Add project root
sys.path.append(os.getcwd())

from src.strategies.portfolio_manager import PortfolioManager
from src.trader.real_trader import RealTrader
# from src.notification.feishu import FeishuBot

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
try:
    rfh = RotatingFileHandler("multicoin_bot.log", maxBytes=10 * 1024 * 1024, backupCount=5)
    rfh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    
    # Add handler to the ROOT logger so all modules (including RealTrader) log to file
    root_logger = logging.getLogger()
    root_logger.addHandler(rfh)
    root_logger.addHandler(logging.StreamHandler()) # Ensure stdout is also active
    
    # Also keep local logger for specific script messages if needed, but root covers it
    logger.info("Logging setup complete. Root logger configured.")
except Exception as e:
    print(f"Failed to setup bot file logging: {e}")
logger = logging.getLogger(__name__)

# Config
# Map: Clean Symbol (for Model/PM) -> CCXT Symbol (for RealTrader)
SYMBOL_MAP = {
    'BTCUSDT': 'BTC/USDT:USDT',
    'ETHUSDT': 'ETH/USDT:USDT',
    'SOLUSDT': 'SOL/USDT:USDT',
    'BNBUSDT': 'BNB/USDT:USDT',
    'DOGEUSDT': 'DOGE/USDT:USDT',
    'XRPUSDT': 'XRP/USDT:USDT',
    'PEPEUSDT': '1000PEPE/USDT:USDT',
    'AVAXUSDT': 'AVAX/USDT:USDT',
    'LINKUSDT': 'LINK/USDT:USDT',
    'ADAUSDT': 'ADA/USDT:USDT',
    'TRXUSDT': 'TRX/USDT:USDT',
    'LDOUSDT': 'LDO/USDT:USDT',
    'BCHUSDT': 'BCH/USDT:USDT',
    'OPUSDT': 'OP/USDT:USDT'
}

def main():
    load_dotenv()
    
    # Proxy Configuration
    # Priority: 1. Environment Variable (if set) 2. Default Local Proxy
    # To disable proxy (e.g. on cloud), set PROXY_URL="" in .env
    proxy_url = os.getenv("PROXY_URL")
    if proxy_url is None:
        proxy_url = "http://127.0.0.1:33210" # Default for local dev
    elif proxy_url == "":
        proxy_url = None # Explicitly disabled via empty string
    
    logger.info(f"Proxy Configuration: {'Enabled (' + proxy_url + ')' if proxy_url else 'Disabled (Direct Connection)'}")
    
    lock_path = "/tmp/btc_quant_multicoin.lock"
    try:
        lock_file = open(lock_path, "w")
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_file.write(str(os.getpid()))
        lock_file.flush()
    except OSError as e:
        if e.errno in (errno.EAGAIN, errno.EACCES):
            logger.warning("Another multicoin bot instance is running. Exiting.")
            return
        else:
            logger.error(f"Failed to acquire lock: {e}")
            return
    
    # Initialize Feishu
    # feishu = FeishuBot()
    # feishu.send_text("🚀 Multi-Coin Strategy Bot Started (Phase 3 - Top 30 + Optimization)")
    
    # Initialize Traders (Sequential with delay to avoid API limits)
    traders = {}
    
    logger.info(f"Initializing {len(SYMBOL_MAP)} traders sequentially to avoid API Rate Limits...")
    
    total_coins = len(SYMBOL_MAP)
    current_idx = 0
    
    for clean_sym, ccxt_sym in SYMBOL_MAP.items():
        current_idx += 1
        logger.info(f"[{current_idx}/{total_coins}] Initializing Trader for {clean_sym} ({ccxt_sym})...")
        try:
            # Disable trader notifications per user request (Only Hourly Report allowed)
            trader = RealTrader(symbol=ccxt_sym, notifier=None, proxy_url=proxy_url)
            if trader.active:
                trader.start() # Start to trigger repair_orders and other startup logic
                traders[clean_sym] = trader
                logger.info(f"Trader for {clean_sym} ready.")
            else:
                logger.warning(f"Trader for {clean_sym} not active.")
                
            # Sleep to respect rate limits (e.g. 1s per coin)
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"Failed to init trader for {clean_sym}: {e}")
            time.sleep(1) # Sleep even on error
            
    if not traders:
        logger.error("No traders initialized. Exiting.")
        return
        
    # Initialize Portfolio Manager
    # Pass clean symbols keys and proxy
    pm = PortfolioManager(active_symbols=list(SYMBOL_MAP.keys()), proxy_url=proxy_url)
    
    # Collect all CCXT symbols for consolidated history fetching
    all_ccxt_symbols = list(SYMBOL_MAP.values())
    
    # CRITICAL: Update monitored_symbols for ALL traders so they share the same global history view
    # This ensures check_risk_limit (Daily Loss) calculates TOTAL PnL, not just per-symbol PnL.
    for t in traders.values():
        t.monitored_symbols = all_ccxt_symbols
    
    logger.info("Bot initialized. Entering main loop...")
    
    while True:
        try:
            # Reload Strategy Config
            pm.reload_config()
            
            logger.info("--- Scanning Market ---")
            # Get ALL results for frontend display
            all_results = pm.scan_market(return_all=True)
            market_analysis_map = {r['symbol']: r for r in all_results}
            
            # Filter opportunities for trading
            opportunities = [r for r in all_results if r['signal'] in ['LONG', 'SHORT']]
            
            # Save all_results to JSON for frontend
            try:
                # Ensure data directory exists
                os.makedirs("data", exist_ok=True)
                with open("data/strategy_signals.json", "w") as f:
                    json.dump(all_results, f, indent=2)
            except Exception as e:
                logger.error(f"Failed to save strategy signals: {e}")

            
            # --- AGGRESSIVE MODE: Scan Leaderboard (DISABLED for 14-Coin Focus) ---
            # try:
            #     # Find top movers NOT in our active list
            #     lb_candidates = pm.scan_leaderboard(limit=5) 
                
            #     for cand in lb_candidates:
            #         sym = cand['symbol']
            #         # logger.info(f"Checking Leaderboard: {sym} ({cand['change']:.2f}%)")
                    
            #         # Analyze using Technicals Only (Aggressive)
            #         opp = pm.analyze_technical_only(sym)
                    
            #         if opp:
            #             logger.info(f"🔥 AGGRESSIVE LEADERBOARD SIGNAL: {sym} {opp['signal']} (Conf: {opp['avg_probability']})")
                        
            #             # Add to opportunities
            #             opportunities.append(opp)
                        
            #             # Dynamically Initialize Trader if needed
            #             if sym not in traders:
            #                 ccxt_sym = cand['ccxt_symbol']
            #                 logger.info(f"Initializing Dynamic Trader for {sym}...")
            #                 try:
            #                     new_trader = RealTrader(symbol=ccxt_sym, notifier=None, proxy_url=proxy_url)
            #                     traders[sym] = new_trader
            #                     logger.info(f"Dynamic Trader for {sym} ready.")
            #                 except Exception as e:
            #                     logger.error(f"Failed to init dynamic trader for {sym}: {e}")
            # except Exception as e:
            #     logger.error(f"Aggressive scan failed: {e}")
            # -----------------------------------------
            
            # Log top opportunities
            if opportunities:
                top_msg = "\n".join([f"{o['symbol']}: {o['signal']} ({o['avg_probability']:.4f})" for o in opportunities])
                logger.info(f"Signals:\n{top_msg}")
            else:
                logger.info("No signals generated.")
            
            # Get current held positions and account status
            all_active_positions = {}
            status = {}
            try:
                if traders:
                    # Use first active trader to fetch all positions and status
                    first_trader = next(iter(traders.values()))
                    
                    # Update monitored symbols to ensure we fetch history for ALL coins
                    first_trader.monitored_symbols = all_ccxt_symbols
                    
                    # Fetch Full Status (includes positions, balance, pnl, history)
                    status = first_trader.get_status()
                    all_active_positions = status.get('positions', {})
                    
                    # --- PARTIAL TAKE PROFIT LOGIC ---
                    try:
                        current_total_equity = status.get('equity', 0.0)
                        if current_total_equity <= 0:
                             current_total_equity = first_trader.get_total_balance()

                        for pos_sym, pos_data in all_active_positions.items():
                            clean_sym = pos_sym.replace('/', '').replace(':USDT', '').replace(':BUSD', '')
                            
                            if clean_sym not in traders:
                                continue
                                
                            trader = traders[clean_sym]
                            if not trader.active: continue

                            entry_price = float(pos_data.get('entry_price', 0.0))
                            mark_price = float(pos_data.get('mark_price', 0.0))
                            amount = float(pos_data.get('amount', 0.0))
                            side = pos_data.get('side')
                            
                            if entry_price > 0 and amount > 0:
                                if side == 'long':
                                    price_change_pct = (mark_price - entry_price) / entry_price
                                else:
                                    price_change_pct = (entry_price - mark_price) / entry_price
                                
                                # Check for CZSC Reversal Signals
                                market_res = market_analysis_map.get(clean_sym)
                                czsc_exit_signal = False
                                czsc_details = ""
                                
                                if market_res:
                                    strat_res = market_res.get('strategy_result', {})
                                    indicators = strat_res.get('indicators', {})
                                    czsc_details = indicators.get('czsc_details', "")
                                    
                                    if side == 'long':
                                        if "顶背驰" in czsc_details or "卖" in czsc_details:
                                            czsc_exit_signal = True
                                    elif side == 'short':
                                        if "底背驰" in czsc_details or "买" in czsc_details:
                                            czsc_exit_signal = True
                                
                                # Threshold Logic
                                should_close = False
                                close_reason = ""
                                
                                # 1. Hard Profit Target (3%)
                                if price_change_pct >= 0.03:
                                    should_close = True
                                    close_reason = f"Profit {price_change_pct*100:.2f}% >= 3%"
                                
                                # 2. CZSC Reversal (Profit > 0.5%)
                                elif price_change_pct >= 0.005 and czsc_exit_signal:
                                    should_close = True
                                    close_reason = f"Profit {price_change_pct*100:.2f}% > 0.5% & CZSC Reversal: {czsc_details}"

                                if should_close:
                                    # Execute Partial TP (50%)
                                    # We remove the size_threshold check to ensure we secure profits on ALL winning trades
                                    # as per strategy "Partial TP (50% at 3% profit)".
                                    
                                    logger.info(f"💰 [Partial TP] {clean_sym} {close_reason}. Closing 50% to secure profit...")
                                    
                                    close_amount = amount * 0.5
                                    close_amount = float(trader.exchange.amount_to_precision(trader.symbol, close_amount))
                                    
                                    if close_amount > 0:
                                        trader.close_partial(close_amount)

                    except Exception as e:
                        logger.error(f"Error in Partial TP Logic: {e}")
                    # ---------------------------------
                    
                    # Save status to file for API/Frontend
                    try:
                        os.makedirs("data", exist_ok=True)
                        temp_file = "data/real_trading_status.json.tmp"
                        target_file = "data/real_trading_status.json"
                        
                        with open(temp_file, "w") as f:
                            # Add timestamp
                            status['updated_at'] = time.time()
                            json.dump(status, f, indent=2, default=str)
                            f.flush()
                            os.fsync(f.fileno())
                        
                        # Atomic replace
                        os.replace(temp_file, target_file)
                        
                        logger.info(f"Saved real trading status with {len(all_active_positions)} positions")
                    except Exception as e:
                        logger.error(f"Failed to save real trading status: {e}")
                        
            except Exception as e:
                logger.error(f"Failed to fetch active positions/status: {e}")

            # Execute Trades
            for opp in opportunities:
                symbol = opp['symbol'] # Clean symbol e.g. BTCUSDT
                signal_str = opp['signal']
                
                # Extract Strategy Result
                strat_res = opp.get('strategy_result', {})
                trade_params = strat_res.get('trade_params', {})
                
                logger.info(f"Processing signal for {symbol}: {signal_str} | Params: {trade_params}")
                
                if symbol not in traders:
                    continue
                    
                trader = traders[symbol]
                
                if not trader.active:
                    logger.warning(f"Trader for {symbol} is not active. Skipping.")
                    continue
                
                # Convert signal string to int
                trade_signal = 0
                if signal_str == "LONG":
                    trade_signal = 1
                elif signal_str == "SHORT":
                    trade_signal = -1
                    
                # Check Correlation Risk (Only for New Positions)
                # If we are opening a NEW position, check if it correlates with existing positions of SAME direction.
                # Logic: If Longing BTC, check correlation with other Longs.
                is_new_position = True
                for pos_sym in all_active_positions:
                     clean = pos_sym.replace('/', '').replace(':USDT', '').replace(':BUSD', '')
                     if clean == symbol:
                         is_new_position = False
                         break
                
                # --- Trailing Stop & Position Management for Existing Positions ---
                if not is_new_position:
                    try:
                        current_price = opp.get('price')
                        if current_price:
                            cfg = pm.config_manager.get_config()
                            # Use configured trailing parameters or defaults
                            trailing_trigger = float(cfg.get('trailing_stop_trigger_pct', 0.01))
                            trailing_lock = float(cfg.get('trailing_stop_lock_pct', 0.02))
                            
                            logger.info(f"🛡️ Managing position for {symbol}: Price={current_price}, Signal={trade_signal}")
                            trader.manage_position(
                                current_price=float(current_price), 
                                signal=trade_signal, 
                                symbol=symbol,
                                trailing_trigger_pct=trailing_trigger,
                                trailing_lock_pct=trailing_lock
                            )
                    except Exception as e:
                        logger.error(f"Failed to manage position for {symbol}: {e}")
                # ----------------------------------------------------------------

                if is_new_position and trade_signal != 0:
                    same_side_clean = []
                    for pos_sym, pos_data in all_active_positions.items():
                        # Normalize
                        clean = pos_sym.replace('/', '').replace(':USDT', '').replace(':BUSD', '')
                        
                        # Check direction
                        pos_side = pos_data['side'] # 'long' or 'short'
                        if (pos_side == 'long' and trade_signal == 1) or \
                           (pos_side == 'short' and trade_signal == -1):
                            same_side_clean.append(clean)
                    
                    # Tighten correlation threshold from 0.70 -> 0.65
                    if not pm.correlation_manager.check_portfolio_correlation(symbol, same_side_clean, threshold=0.65):
                        logger.warning(f"🚫 [Correlation Risk] Skipping {symbol} ({signal_str}) due to high correlation with {same_side_clean}")
                        continue

                # Check Position Limits
                # 1) Max Total Position Limit (User Rule: Max 10x Equity)
                # 2) Per-coin Limit (3x Equity)
                # 3) Same-side Net Exposure Limit (6x Equity)
                # NOTE: Use 'position_value_usdt' if present, fallback to 'notional'
                current_total_notional = 0.0
                for pos_sym, pos_data in all_active_positions.items():
                    current_total_notional += float(pos_data.get('position_value_usdt', pos_data.get('notional', 0.0)))
                
                # Estimate new position size
                # We need to know the planned position size. 
                
                # Fetch equity for calculations
                total_equity = 0.0
                try:
                    # Retry logic for equity
                    for _ in range(3):
                        total_equity = trader.get_total_balance()
                        if total_equity > 0:
                            break
                        time.sleep(1)
                except Exception as e:
                    logger.error(f"Failed to fetch equity: {e}")
                
                if total_equity <= 0:
                    logger.warning("Could not fetch equity. Using fallback 100.0 USDT for calculation (Safe Mode).")
                    total_equity = 100.0 # Fallback

                # Calculate planned size
                # Strategy: Use PortfolioManager Safe Calculation
                
                # Extract Confidence for Leverage Check
                ml_prob = opp.get('avg_probability', 0.5)
                
                # Convert ML Prob to Directional Confidence (Win Rate)
                # If Signal is LONG, Conf = Prob
                # If Signal is SHORT, Conf = 1 - Prob
                effective_confidence = ml_prob
                if signal_str == "SHORT":
                    effective_confidence = 1.0 - ml_prob
                
                # Extract Market Data for Kelly Sizing
                indicators = strat_res.get('indicators', {})
                atr_val = float(indicators.get('atr', 0.0))
                market_mode = trade_params.get('market_mode', 'normal')
                current_price = float(opp.get('price', 0.0))
                
                # Check Global Leverage Limits First
                is_allowed, reason = pm.check_leverage_limits(
                    current_positions=all_active_positions, 
                    total_equity=total_equity,
                    confidence=effective_confidence
                )
                
                if not is_allowed:
                    logger.warning(f"🚫 [Risk Limit] Skipping {symbol}: {reason}")
                    continue

                # Calculate Safe Position Size (Notional USDT)
                allowed_notional = pm.calculate_position_size(
                    total_equity=total_equity,
                    current_positions=all_active_positions,
                    confidence=effective_confidence,
                    atr=atr_val,
                    price=current_price,
                    market_mode=market_mode
                )
                
                if allowed_notional < 20.0: 
                    logger.warning(f"🚫 [Size Limit] Skipping {symbol}: Allowed size {allowed_notional:.2f} < Min 20.0")
                    continue
                
                # Determine Target Leverage
                # Default 5x, High Conf 8x
                strategy_suggested_leverage = trade_params.get('leverage', 5)
                max_leverage = 8 if effective_confidence > 0.8 else 5
                final_leverage = min(int(strategy_suggested_leverage), max_leverage)
                
                # Calculate Amount in Coins
                # allowed_notional is the MAX allowed. We should use it, or a standard chunk if smaller?
                # The user wants "High Frequency" -> usage of funds.
                # We'll use the allowed_notional directly to maximize utilization up to the limit.
                planned_notional = allowed_notional
                amount_coins = planned_notional / opp.get('price', 1.0)
                
                logger.info(f"[{symbol}] Position Sizing: Equity=${total_equity:.2f}, Planned=${planned_notional:.2f} (MaxAllowed), Leverage={final_leverage}x")
                
                # Execute Trade
                if trade_signal != 0:
                    # Use dynamic params from strategy if available
                    sl_price = trade_params.get('sl_price')
                    tp_price = trade_params.get('tp_price')
                    
                    # Fallback to defaults (Risk:Reward 1:3 as per user request)
                    # User: "Risk-reward ratio 1:3 and 2% hard stop-loss"
                    # SL 2%, TP 6%
                    sl_pct = 0.02
                    tp_pct = 0.06
                    
                    # Adjust for Scalping Mode (Low Volatility)
                    # If the signal reason contains "[Scalp]", use tighter SL/TP
                    # We can check the strategy logs or infer from market mode if we had access.
                    # For now, we rely on the generic SL/TP or what strategy returned in trade_params.
                    
                    trader.execute_trade(
                        signal=trade_signal, 
                        sl_pct=sl_pct, 
                        tp_pct=tp_pct,
                        sl_price=sl_price,
                        tp_price=tp_price,
                        leverage=int(final_leverage),
                        amount_coins=amount_coins
                    )
            
            logger.info("Sleeping for 120s...")
            time.sleep(120) 
            
        except KeyboardInterrupt:
            logger.info("Bot stopped by user.")
            break
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            time.sleep(120)

if __name__ == "__main__":
    main()
