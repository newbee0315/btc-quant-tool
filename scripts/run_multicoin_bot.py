import time
import logging
import os
import sys
from dotenv import load_dotenv

# Add project root
sys.path.append(os.getcwd())

from src.strategies.portfolio_manager import PortfolioManager
from src.trader.real_trader import RealTrader
from src.notification.feishu import FeishuBot

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("multicoin_bot.log"),
        logging.StreamHandler()
    ]
)
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
    
    # Initialize Feishu
    feishu = FeishuBot()
    feishu.send_text("🚀 Multi-Coin Strategy Bot Started (Phase 3 - Top 10)")
    
    # Initialize Traders (Parallel)
    traders = {}
    
    def init_trader(item):
        clean_sym, ccxt_sym = item
        logger.info(f"Initializing Trader for {clean_sym} ({ccxt_sym})...")
        try:
            return clean_sym, RealTrader(symbol=ccxt_sym, notifier=feishu, proxy_url=PROXY_URL)
        except Exception as e:
            logger.error(f"Failed to init trader for {clean_sym}: {e}")
            return clean_sym, None

    from concurrent.futures import ThreadPoolExecutor
    # Use max_workers based on symbol count
    with ThreadPoolExecutor(max_workers=len(SYMBOL_MAP)) as executor:
        results = executor.map(init_trader, SYMBOL_MAP.items())
        
    for clean_sym, trader in results:
        if trader and trader.active:
            traders[clean_sym] = trader
            logger.info(f"Trader for {clean_sym} ready.")
            
    if not traders:
        logger.error("No traders initialized. Exiting.")
        return
        
    # Initialize Portfolio Manager
    # Pass clean symbols keys and proxy
    pm = PortfolioManager(active_symbols=list(SYMBOL_MAP.keys()), proxy_url=PROXY_URL)
    
    logger.info("Bot initialized. Entering main loop...")
    
    while True:
        try:
            logger.info("--- Scanning Market ---")
            opportunities = pm.scan_market()
            
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
                                new_trader = RealTrader(symbol=ccxt_sym, notifier=feishu, proxy_url=PROXY_URL)
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
                    
                # Execute
                if trade_signal != 0:
                    # Use dynamic params from strategy if available
                    sl_price = trade_params.get('sl_price')
                    tp_price = trade_params.get('tp_price')
                    leverage = trade_params.get('leverage', 20)
                    amount_coins = trade_params.get('amount_coins', None)
                    
                    # Fallback to defaults if strategy didn't return price
                    # (Though TrendMLStrategy usually does)
                    sl_pct = 0.02
                    tp_pct = 0.04
                    
                    trader.execute_trade(
                        signal=trade_signal, 
                        sl_pct=sl_pct, 
                        tp_pct=tp_pct,
                        sl_price=sl_price,
                        tp_price=tp_price,
                        leverage=int(leverage),
                        amount_coins=amount_coins
                    )
            
            logger.info("Sleeping for 60s...")
            time.sleep(60) 
            
        except KeyboardInterrupt:
            logger.info("Bot stopped by user.")
            break
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
