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
    logger.addHandler(rfh)
    logger.addHandler(logging.StreamHandler())
except Exception as e:
    print(f"Failed to setup bot file logging: {e}")
logger = logging.getLogger(__name__)

# Config
# Map: Clean Symbol (for Model/PM) -> CCXT Symbol (for RealTrader)
SYMBOL_MAP = {
    'BTCUSDT': 'BTC/USDT:USDT',
    'ETHUSDT': 'ETH/USDT:USDT',
    'BNBUSDT': 'BNB/USDT:USDT',
    'SOLUSDT': 'SOL/USDT:USDT',
    'AVAXUSDT': 'AVAX/USDT:USDT',
    'XRPUSDT': 'XRP/USDT:USDT',
    'DOGEUSDT': 'DOGE/USDT:USDT',
    'ADAUSDT': 'ADA/USDT:USDT',
    'TRXUSDT': 'TRX/USDT:USDT',
    'LINKUSDT': 'LINK/USDT:USDT',
    # Expanded to 30 coins
    'LTCUSDT': 'LTC/USDT:USDT',
    'DOTUSDT': 'DOT/USDT:USDT',
    'BCHUSDT': 'BCH/USDT:USDT',
    'SHIBUSDT': 'SHIB/USDT:USDT',
    'MATICUSDT': 'MATIC/USDT:USDT',
    'NEARUSDT': 'NEAR/USDT:USDT',
    'APTUSDT': 'APT/USDT:USDT',
    'FILUSDT': 'FIL/USDT:USDT',
    'ATOMUSDT': 'ATOM/USDT:USDT',
    'ARBUSDT': 'ARB/USDT:USDT',
    'OPUSDT': 'OP/USDT:USDT',
    'ETCUSDT': 'ETC/USDT:USDT',
    'ICPUSDT': 'ICP/USDT:USDT',
    'RNDRUSDT': 'RNDR/USDT:USDT',
    'INJUSDT': 'INJ/USDT:USDT',
    'STXUSDT': 'STX/USDT:USDT',
    'LDOUSDT': 'LDO/USDT:USDT',
    'VETUSDT': 'VET/USDT:USDT',
    'XLMUSDT': 'XLM/USDT:USDT',
    'PEPEUSDT': 'PEPE/USDT:USDT'
}

PROXY_URL = os.getenv("PROXY_URL", "http://127.0.0.1:33210")

def main():
    load_dotenv()
    
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
            trader = RealTrader(symbol=ccxt_sym, notifier=None, proxy_url=PROXY_URL)
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
    pm = PortfolioManager(active_symbols=list(SYMBOL_MAP.keys()), proxy_url=PROXY_URL)
    
    logger.info("Bot initialized. Entering main loop...")
    
    while True:
        try:
            # Reload Strategy Config
            pm.reload_config()
            
            logger.info("--- Scanning Market ---")
            # Get ALL results for frontend display
            all_results = pm.scan_market(return_all=True)
            
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

            
            # --- AGGRESSIVE MODE: Scan Leaderboard ---
            try:
                # Find top movers NOT in our active list
                lb_candidates = pm.scan_leaderboard(limit=5) 
                
                for cand in lb_candidates:
                    sym = cand['symbol']
                    # logger.info(f"Checking Leaderboard: {sym} ({cand['change']:.2f}%)")
                    
                    # Analyze using Technicals Only (Aggressive)
                    opp = pm.analyze_technical_only(sym)
                    
                    if opp:
                        logger.info(f"🔥 AGGRESSIVE LEADERBOARD SIGNAL: {sym} {opp['signal']} (Conf: {opp['avg_probability']})")
                        
                        # Add to opportunities
                        opportunities.append(opp)
                        
                        # Dynamically Initialize Trader if needed
                        if sym not in traders:
                            ccxt_sym = cand['ccxt_symbol']
                            logger.info(f"Initializing Dynamic Trader for {sym}...")
                            try:
                                new_trader = RealTrader(symbol=ccxt_sym, notifier=None, proxy_url=PROXY_URL)
                                traders[sym] = new_trader
                                logger.info(f"Dynamic Trader for {sym} ready.")
                            except Exception as e:
                                logger.error(f"Failed to init dynamic trader for {sym}: {e}")
            except Exception as e:
                logger.error(f"Aggressive scan failed: {e}")
            # -----------------------------------------
            
            # Log top opportunities
            if opportunities:
                top_msg = "\n".join([f"{o['symbol']}: {o['signal']} ({o['avg_probability']:.4f})" for o in opportunities])
                logger.info(f"Signals:\n{top_msg}")
            else:
                logger.info("No signals generated.")
            
            # Get current held positions for Correlation Check
            all_active_positions = {}
            try:
                if traders:
                    # Use first active trader to fetch all positions
                    first_trader = next(iter(traders.values()))
                    all_active_positions = first_trader.get_positions()
            except Exception as e:
                logger.error(f"Failed to fetch active positions: {e}")

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
                # Re-calculate min_usdt logic here or move it up.
                
                # Fetch equity for calculations
                try:
                    total_equity = trader.get_total_balance()
                except Exception as e:
                    logger.error(f"Failed to fetch equity: {e}")
                    total_equity = 100.0 # Fallback

                # Calculate planned size
                # Min size = 1.5 * Equity (as per existing logic)
                min_usdt = total_equity * 1.5
                if min_usdt < 10.0: min_usdt = 10.0
                
                planned_notional = min_usdt
                amount_coins = trade_params.get('amount_coins') or trade_params.get('position_size')
                current_price = opp.get('price', 0.0)
                
                if amount_coins and current_price > 0:
                    calculated_notional = amount_coins * current_price
                    if calculated_notional > planned_notional:
                        planned_notional = calculated_notional
                
                cfg = pm.config_manager.get_config()
                max_portfolio_leverage = float(cfg.get('max_portfolio_leverage', 10.0))
                max_allowed_notional = total_equity * max_portfolio_leverage
                
                if current_total_notional + planned_notional > max_allowed_notional:
                    logger.warning(f"🚫 [Max Position Limit {max_portfolio_leverage:.0f}x] Skipping {symbol}. Total Notional ({current_total_notional:.2f}) + New ({planned_notional:.2f}) > Limit ({max_allowed_notional:.2f})")
                    continue

                # Per-coin cap: 3x equity
                per_coin_limit = total_equity * 3.0
                per_coin_current = 0.0
                for pos_sym, pos_data in all_active_positions.items():
                    clean = pos_sym.replace('/', '').replace(':USDT', '').replace(':BUSD', '')
                    if clean == symbol:
                        per_coin_current += float(pos_data.get('position_value_usdt', pos_data.get('notional', 0.0)))
                if per_coin_current + planned_notional > per_coin_limit:
                    logger.warning(f"🚫 [Per-Coin Limit 3x] Skipping {symbol}. Coin Notional ({per_coin_current:.2f}) + New ({planned_notional:.2f}) > Limit ({per_coin_limit:.2f})")
                    continue

                # Same-side net exposure cap: 6x equity
                side_limit = total_equity * 6.0
                same_side_current = 0.0
                for pos_sym, pos_data in all_active_positions.items():
                    pos_side = pos_data.get('side')
                    if (pos_side == 'long' and trade_signal == 1) or (pos_side == 'short' and trade_signal == -1):
                        same_side_current += float(pos_data.get('position_value_usdt', pos_data.get('notional', 0.0)))
                if same_side_current + planned_notional > side_limit:
                    logger.warning(f"🚫 [Side Limit 6x] Skipping {symbol}. Same-Side Notional ({same_side_current:.2f}) + New ({planned_notional:.2f}) > Limit ({side_limit:.2f})")
                    continue

                # Execute
                if trade_signal != 0:
                    # Use dynamic params from strategy if available
                    sl_price = trade_params.get('sl_price')
                    tp_price = trade_params.get('tp_price')
                    # Cap Leverage at 10x
                    raw_leverage = trade_params.get('leverage', 10)
                    leverage = min(int(raw_leverage), 10)
                    
                    # Support 'amount_coins' or 'position_size' from strategy
                    # amount_coins already extracted above
                    
                    # Enforce Minimum Position Size: 1.5 * Total Equity (User Rule)
                    # Logic moved/duplicated above for check, but final calc here
                    
                    logger.info(f"[{symbol}] Position Sizing: Equity={total_equity:.2f}, MinUSDT={min_usdt:.2f}, Planned={planned_notional:.2f}")

                    if amount_coins:
                        notional = amount_coins * current_price
                        if notional < min_usdt:
                            amount_coins = min_usdt / current_price
                            logger.info(f"[{symbol}] Enforcing Min Size ({min_usdt:.2f}u): Adjusted to {amount_coins:.6f} (was {notional:.2f}u)")
                    else:
                        # If no amount calculated yet, default to min size
                        amount_coins = min_usdt / current_price
                        logger.info(f"[{symbol}] Enforcing Min Size ({min_usdt:.2f}u): Set to {amount_coins:.6f}")

                    # Fallback to defaults if strategy didn't return price
                    # (Though TrendMLStrategy usually does)
                    # Optimized for High Frequency: Widen SL, Narrow TP
                    # Load Config for Defaults
                    config = pm.config_manager.get_config()
                    sl_pct = config.get('sl_pct', 0.03) # Default 3%
                    tp_pct = config.get('tp_pct', 0.015) # Default 1.5%
                    
                    trader.execute_trade(
                        signal=trade_signal, 
                        sl_pct=sl_pct, 
                        tp_pct=tp_pct,
                        sl_price=sl_price,
                        tp_price=tp_price,
                        leverage=int(leverage),
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
