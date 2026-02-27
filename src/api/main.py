from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
import sys
import os
import logging
import asyncio
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

import pandas as pd
import json
from datetime import datetime
import pytz
from dotenv import load_dotenv
from logging.handlers import RotatingFileHandler

import requests
import subprocess
import time

# Load environment variables
load_dotenv()

# Add src to python path to allow imports from data and models
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.data.collector import CryptoDataCollector, FuturesDataCollector
from src.models.predictor import PricePredictor
from src.models.train import train_models
from src.backtest.backtest import SmartBacktester
from src.trader.paper_trader import PaperTrader
from src.trader.real_trader import RealTrader
from src.notification.feishu import FeishuBot
from src.strategies.trend_ml_strategy import TrendMLStrategy
from src.strategies.portfolio_manager import PortfolioManager
from src.utils.maintenance_scheduler import register_maintenance_tasks
from src.utils.strategy_optimizer import run_strategy_optimization
from src.utils.config_manager import config_manager as global_config_manager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add File Handler for better debugging
try:
    file_handler = RotatingFileHandler("api_server.log", maxBytes=10 * 1024 * 1024, backupCount=5)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
except Exception as e:
    print(f"Failed to setup file logging: {e}")

# --- Resource Manager for Multi-Symbol Support ---
class ResourceManager:
    def __init__(self):
        self.collectors: Dict[str, FuturesDataCollector] = {}
        self.predictors: Dict[str, PricePredictor] = {}
        self.default_symbol = "BTCUSDT"

    def get_collector(self, symbol: str) -> FuturesDataCollector:
        # Normalize symbol
        symbol = symbol.replace("/", "").replace(":", "") # e.g. BTC/USDT -> BTCUSDT
        if symbol not in self.collectors:
            logger.info(f"Initializing new collector for {symbol}")
            # Use proxy from trader_config if available
            proxy = trader_config.proxy_url if 'trader_config' in globals() and trader_config.proxy_url else None
            c = FuturesDataCollector(symbol=symbol)
            if proxy:
                c.set_proxy(proxy)
            self.collectors[symbol] = c
        return self.collectors[symbol]

    def get_predictor(self, symbol: str) -> PricePredictor:
        symbol = symbol.replace("/", "").replace(":", "")
        if symbol not in self.predictors:
            logger.info(f"Initializing new predictor for {symbol}")
            self.predictors[symbol] = PricePredictor(symbol=symbol)
        return self.predictors[symbol]

resource_manager = ResourceManager()
# -------------------------------------------------

# Initialize components
FEISHU_WEBHOOK_URL = os.getenv("FEISHU_WEBHOOK_URL")
if not FEISHU_WEBHOOK_URL:
    logger.warning("FEISHU_WEBHOOK_URL not set in .env file. Feishu notifications will be disabled.")

feishu_bot = FeishuBot(FEISHU_WEBHOOK_URL)

# Use FuturesDataCollector for better alignment with strategy
collector = FuturesDataCollector(symbol='BTCUSDT')
predictor = PricePredictor()
scheduler = AsyncIOScheduler(timezone=pytz.timezone('Asia/Shanghai'))
# Initialize backtester with default symbol, can be changed per request if we make it dynamic
backtester = SmartBacktester(symbol='BTCUSDT') 
strategy = TrendMLStrategy(ema_period=200, rsi_period=14, ml_threshold=0.75)

# TRADING_MODE env var is now only used as fallback default in load_trader_config
TRADING_MODE = os.getenv("TRADING_MODE", "paper").lower()

# Alias for compatibility with existing endpoints that use 'paper_trader'
# Will be assigned after config load
paper_trader = None

class StrategyConfig(BaseModel):
    ema_period: int = 200
    rsi_period: int = 14
    ml_threshold: float = 0.60
    leverage: int = Field(1, ge=1, le=10)
    max_portfolio_leverage: int = Field(10, ge=1, le=10)

class TraderConfig(BaseModel):
    mode: str = "paper"  # "paper" or "real"
    sl_pct: float = 0.02
    tp_pct: float = 0.06
    amount_usdt: float = 20.0
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    proxy_url: Optional[str] = None
    total_capital: float = 1000.0
    risk_per_trade: float = 0.02
    trailing_stop_trigger_pct: float = 0.01  # Trigger trailing stop when price moves 1% in favor
    trailing_stop_lock_pct: float = 0.02     # Lock profit when price moves 2% in favor
    preserve_proxy_on_update: bool = True    # Preserve existing proxy_url when updates omit it

# Global Config State
TRADER_CONFIG_FILE = os.path.join(os.path.dirname(__file__), '../../trader_config.json')

def load_trader_config():
    if os.path.exists(TRADER_CONFIG_FILE):
        try:
            with open(TRADER_CONFIG_FILE, 'r') as f:
                data = json.load(f)
                return TraderConfig(**data)
        except Exception as e:
            logger.error(f"Failed to load trader config: {e}")
    
    # Fallback to env
    return TraderConfig(
        mode=TRADING_MODE, 
        amount_usdt=float(os.getenv("TRADE_AMOUNT_USDT", "20.0")),
        total_capital=float(os.getenv("TOTAL_CAPITAL", "1000.0")),
        risk_per_trade=float(os.getenv("RISK_PER_TRADE", "0.02"))
    )

def save_trader_config(config: TraderConfig):
    try:
        with open(TRADER_CONFIG_FILE, 'w') as f:
            f.write(config.model_dump_json(indent=4))
    except Exception as e:
        logger.error(f"Failed to save trader config: {e}")

strategy_config = StrategyConfig()
# Sync initial config from file if present
try:
    _cfg = global_config_manager.get_config()
    strategy_config = StrategyConfig(
        ema_period=_cfg.get('ema_period', strategy_config.ema_period),
        rsi_period=_cfg.get('rsi_period', strategy_config.rsi_period),
        ml_threshold=_cfg.get('ml_threshold', strategy_config.ml_threshold),
        leverage=_cfg.get('leverage', strategy_config.leverage),
        max_portfolio_leverage=_cfg.get('max_portfolio_leverage', strategy_config.max_portfolio_leverage),
    )
except Exception as e:
    logger.error(f"Failed to load initial strategy config: {e}")
trader_config = load_trader_config()

# Configure Collector Proxy
if trader_config.proxy_url:
    logger.info(f"Setting collector proxy to {trader_config.proxy_url}")
    collector.set_proxy(trader_config.proxy_url)

# 30 Coins List for Monitoring
MONITORED_SYMBOLS = [
    'BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'BNB/USDT:USDT', 'DOGE/USDT:USDT',
    'XRP/USDT:USDT', '1000PEPE/USDT:USDT', 'AVAX/USDT:USDT', 'LINK/USDT:USDT', 'ADA/USDT:USDT',
    'TRX/USDT:USDT', 'LDO/USDT:USDT', 'BCH/USDT:USDT', 'OP/USDT:USDT'
]

# Initialize Trader based on loaded config
if trader_config.mode == "real":
    logger.info("⚠️ STARTING IN REAL TRADING MODE (from config) ⚠️")
    trader = RealTrader(
        symbol="BTC/USDT:USDT", 
        leverage=strategy_config.leverage, 
        notifier=None, # Disable notifications per user request
        api_key=trader_config.api_key,
        api_secret=trader_config.api_secret,
        proxy_url=trader_config.proxy_url,
        monitored_symbols=MONITORED_SYMBOLS
    )
    trader.set_amount(trader_config.amount_usdt)
    paper_trader = trader
else:
    logger.info("Starting in Paper Trading Mode (from config)")
    trader = PaperTrader(notifier=None)
    paper_trader = trader

# Bot Config for Threshold (existing)
class BotConfig(BaseModel):
    confidence_threshold: float
    notification_level: str

bot_config = BotConfig(confidence_threshold=0.75, notification_level="HIGH_ONLY") # Sync with default strategy_config

# Global state for signals
latest_signal = 0  # 0: Hold, 1: Buy, -1: Sell
last_notification = {"signal": 0, "timestamp": 0}

METRICS_FILE = os.path.join(os.path.dirname(__file__), '../../src/models/saved_models/multicoin_metrics.json')
DATA_DIR = os.path.join(os.path.dirname(__file__), '../../data/raw')

# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                pass

manager = ConnectionManager()

async def broadcast_market_data():
    """
    Fetch latest market data, run prediction, update paper trader, and broadcast to WebSocket clients.
    Run every 3 seconds (or custom interval).
    """
    try:
        loop = asyncio.get_running_loop()

        # 1. Fetch Real-time Ticker
        ticker = await loop.run_in_executor(None, collector.fetch_current_price)
        
        # 2. Fetch OHLCV for Prediction (every 1m or less frequently to save resources)
        # Here we do it every time for simplicity, but in production maybe throttle
        # Increase limit to 500 to ensure consistent feature generation
        df = await loop.run_in_executor(None, collector.fetch_ohlcv, '1m', 500)
        
        # 3. Predict
        # Using 30m horizon as primary signal for paper trading and notifications
        predictions = await loop.run_in_executor(None, predictor.predict_all, df)
        
        # 4. Generate Signal
        # Use Strategy (Hybrid Trend + ML)
        p30_data = predictions.get("30m", {})
        p10_data = predictions.get("10m", {})
        
        if isinstance(p30_data, dict):
            prob_30m = p30_data.get("probability", 0.5)
        else:
            prob_30m = 0.5
            
        # Update Strategy Threshold from Config
        threshold = bot_config.confidence_threshold
        strategy.ml_threshold = threshold
        strategy.ema_period = strategy_config.ema_period
        strategy.rsi_period = strategy_config.rsi_period
        
        # Analyze
        # Fetch real-time balance for accurate full-position calculation
        current_balance = trader_config.total_capital
        if trader and hasattr(trader, 'get_balance'):
            try:
                # Run in executor to avoid blocking loop if API call is slow
                bal = await loop.run_in_executor(None, trader.get_balance)
                if bal > 0:
                    current_balance = bal
            except Exception as e:
                logger.warning(f"Failed to fetch balance for strategy: {e}")

        extra_data = {
            'ml_prediction': p30_data,
            'ml_prediction_10m': p10_data,
            'total_capital': current_balance,
            'risk_per_trade': trader_config.risk_per_trade
        }
        analysis = strategy.analyze(df, extra_data=extra_data)
        strategy_signal = analysis['signal']
        strategy_reason = analysis['reason']
        indicators = analysis['indicators']
        trade_params = analysis.get('trade_params', {})
        
        # Signal for Paper Trader & Notification
        pt_signal = strategy_signal
        notify_signal = strategy_signal

        # 5. Update Paper Trader (Automated Trading)
        # Optimal params from sensitivity analysis: SL 3.0%, TP 2.5%
        if ticker and 'last' in ticker:
            current_price = ticker['last']
            
            # Use dynamic config for SL/TP
            sl_pct = trader_config.sl_pct
            tp_pct = trader_config.tp_pct
            
            if pt_signal != 0:
                 logger.info(f"Signal generated: {pt_signal}. Updating trader...")

            await loop.run_in_executor(
                None, 
                lambda: paper_trader.update(
                    current_price=current_price, 
                    signal=pt_signal, 
                    symbol="BTC/USDT", 
                    sl=sl_pct, 
                    tp=tp_pct, 
                    prob=prob_30m,
                    trailing_trigger_pct=trader_config.trailing_stop_trigger_pct,
                    trailing_lock_pct=trader_config.trailing_stop_lock_pct,
                    **trade_params
                )
            )
            
            # 6. Signal Alert (Feishu Notification) - REMOVED per user request
            # Strategy notifications are strictly disabled.
            # Only Hourly Monitor Report is allowed.
            pass
            
            # Broadcast to Frontend
            data = {
                "type": "ticker_update",
                "data": ticker,
                "predictions": predictions,
                "server_time": str(pd.Timestamp.now())
            }
            await manager.broadcast(json.dumps(data))
            
    except Exception as e:
        logger.error(f"Error in broadcast_market_data: {e}")

from src.scheduler.daily_task import DailyUpdateManager

# ... (other imports)

async def daily_update_task():
    """Task to update data and retrain models daily at 00:00"""
    logger.info("Starting daily update task...")
    try:
        manager = DailyUpdateManager()
        success = await manager.run()
        
        if success:
            # Reload models in the predictor to pick up new models
            logger.info("Reloading models in API...")
            predictor.load_models()
            logger.info("Daily update completed and models reloaded.")
        else:
            logger.warning("Daily update manager returned failure.")
            
    except Exception as e:
        logger.error(f"Daily update failed: {e}")

async def send_hourly_monitor_report():
    """Send hourly monitoring report to Feishu"""
    logger.info("Starting send_hourly_monitor_report task...")
    try:
        if not paper_trader: # Check if trader is initialized
             logger.error("Trader not initialized, skipping hourly report.")
             return

        # Fetch status in executor to avoid blocking
        loop = asyncio.get_running_loop()
        status = await loop.run_in_executor(None, paper_trader.get_status)
        
        # Extract Data
        equity = status.get('equity', 0.0)
        initial_balance = status.get('initial_balance', 0.0)
        unrealized_pnl = status.get('unrealized_pnl', 0.0)
        open_orders_count = status.get('open_orders_count', 0)
        
        stats = status.get('stats', {})
        realized_pnl = stats.get('total_pnl', 0.0)
        total_fees = stats.get('total_fees', 0.0)
        win_rate = stats.get('win_rate', 0.0)
        total_trades = stats.get('total_trades', 0)
        
        positions = status.get('positions', {})
        position_count = len(positions)
        
        total_position_value = sum(pos.get('position_value_usdt', 0.0) for pos in positions.values())
        
        roi = (realized_pnl / initial_balance * 100) if initial_balance > 0 else 0.0
        
        # Format Message
        beijing_tz = pytz.timezone('Asia/Shanghai')
        bj_time = datetime.now(beijing_tz).strftime('%Y-%m-%d %H:%M:%S')
        
        title = "【实盘交易监控日报】(Hourly)"
        msg = (
            f"💰 权益: **${equity:.2f}** | 📦 市值: **${total_position_value:.2f}**\n"
            f"(初始: ${initial_balance:.2f} | 敞口: {total_position_value/equity*100:.1f}%)\n"
            f"📈 未实现: **{unrealized_pnl:+.2f}** | 💵 已实现: **{realized_pnl:+.2f}**\n"
            f"(ROI: {roi:.2f}% | 手续费: ${total_fees:.2f})\n"
            f"🏆 胜率: **{win_rate:.1f}%** ({total_trades}笔) | 📝 挂单: **{open_orders_count}**\n"
        )
        
        # Add detailed positions if any
        if positions:
            msg += "\n"
            # Sort positions by unrealized_pnl in descending order (High to Low)
            sorted_positions = sorted(positions.items(), key=lambda item: item[1].get('unrealized_pnl', 0.0), reverse=True)
            
            for sym, pos in sorted_positions:
                side = "做多" if pos.get('side') == 'long' else "做空"
                pnl = pos.get('unrealized_pnl', 0.0)
                roi_val = pos.get('pnl_pct', 0.0)
                lev = pos.get('leverage', 1)
                
                # New fields
                pos_val = pos.get('position_value_usdt', 0.0)
                entry_price = pos.get('entry_price', 0.0)
                mark_price = pos.get('mark_price', 0.0)
                
                # Ensure symbol is clean (though get_positions should have cleaned it)
                clean_sym = sym.replace(':USDT', '')
                
                # Colorize PnL: Red for positive, Blue for negative
                pnl_str = f"{pnl:+.2f}U"
                if pnl > 0:
                    # Red and Bold
                    pnl_display = f"<font color='red'>**{pnl_str}**</font>"
                elif pnl < 0:
                    # Blue and Bold
                    pnl_display = f"<font color='blue'>**{pnl_str}**</font>"
                else:
                    pnl_display = f"**{pnl_str}**"

                msg += (
                    f"**{clean_sym} {lev}x {side}**\n"
                    f"持仓: **${pos_val:.2f}** | PnL: {pnl_display} ({roi_val:+.2f}%)\n"
                    f"开仓: {entry_price:.4f} | 现价: {mark_price:.4f}\n"
                )
            msg += "\n"

        msg += f"时间: {bj_time}"
        
        logger.info(f"Preparing to send hourly report to Feishu: {len(msg)} chars")
        await loop.run_in_executor(None, feishu_bot.send_markdown, msg, title)
        logger.info("Sent hourly monitor report to Feishu")
        return {"status": "success", "message": "Report sent"}
        
    except Exception as e:
        logger.error(f"Failed to send hourly report: {e}")
        return {"status": "error", "message": str(e)}



@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Schedule the daily task
    # Run at 00:00 every day
    scheduler.add_job(daily_update_task, CronTrigger(hour=0, minute=0))
    
    # Register Maintenance Tasks (Daily Data Update & 3-Day Retraining)
    # DEPRECATED: daily_update_task (DailyUpdateManager) handles both data update and retraining
    # register_maintenance_tasks(scheduler)
    
    # Schedule real-time data broadcast (every 3 seconds for lower latency)
    scheduler.add_job(broadcast_market_data, IntervalTrigger(seconds=3))
    
    # Hourly Monitor Report
    # Run every 30 minutes (minute=0, 30)
    scheduler.add_job(
        send_hourly_monitor_report, 
        CronTrigger(minute='0,30'), 
        id='hourly_monitor', 
        replace_existing=True,
        misfire_grace_time=7200,  # Increased to 7200s (2h) to prevent missed runs during sleep
        coalesce=True,
        max_instances=3
    )
    
    # Guard: ensure report is sent if missed for >45 minutes (e.g., system sleep)
    async def monitor_report_guard():
        try:
            stats = feishu_bot.get_stats()
            last_ts = stats.get('last_success_timestamp')
            tz = pytz.timezone('Asia/Shanghai')
            now = datetime.now(tz)
            last_dt = None
            if last_ts:
                try:
                    last_dt = datetime.fromisoformat(last_ts)
                    # If stored timestamp is naive, assume Asia/Shanghai
                    if last_dt.tzinfo is None:
                        last_dt = tz.localize(last_dt)
                except Exception:
                    last_dt = None
            gap_ok = True
            if last_dt:
                gap = (now - last_dt).total_seconds()
                gap_ok = gap > 2700  # 45 minutes
            if gap_ok:
                await send_hourly_monitor_report()
        except Exception as e:
            logger.error(f"Monitor report guard failed: {e}")
    
    scheduler.add_job(
        monitor_report_guard,
        IntervalTrigger(minutes=5),
        id='hourly_monitor_guard',
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
        max_instances=1
    )

    async def services_watchdog():
        try:
            jobs = scheduler.get_jobs()
            ids = set([j.id for j in jobs if j.id])
            funcs = set([getattr(j.func, "__name__", "") for j in jobs])
            if 'hourly_monitor' not in ids:
                scheduler.add_job(
                    send_hourly_monitor_report, 
                    CronTrigger(minute='0,30'), 
                    id='hourly_monitor', 
                    replace_existing=True,
                    misfire_grace_time=7200,
                    coalesce=True,
                    max_instances=3
                )
            if 'hourly_monitor_guard' not in ids:
                scheduler.add_job(
                    monitor_report_guard,
                    IntervalTrigger(minutes=5),
                    id='hourly_monitor_guard',
                    replace_existing=True,
                    misfire_grace_time=3600,
                    coalesce=True,
                    max_instances=1
                )
            need_record = isinstance(paper_trader, RealTrader) and paper_trader.active
            if need_record and 'record_equity' not in ids:
                scheduler.add_job(paper_trader.record_equity, IntervalTrigger(minutes=60), id='record_equity', replace_existing=True)
            if need_record and 'strategy_optimization' not in ids:
                scheduler.add_job(
                    run_strategy_optimization, 
                    IntervalTrigger(hours=12), 
                    args=[paper_trader],
                    id='strategy_optimization',
                    replace_existing=True
                )
            if 'broadcast_market_data' not in funcs:
                scheduler.add_job(broadcast_market_data, IntervalTrigger(seconds=10))
            log_path = os.path.join(os.getcwd(), "multicoin_bot.log")
            stale = True
            if os.path.exists(log_path):
                try:
                    mtime = os.path.getmtime(log_path)
                    stale = (datetime.now().timestamp() - mtime) > 300 # 5 minutes
                except:
                    stale = True
            # Throttle restarts to at most once per 5 minutes
            global _last_bot_start_ts
            if '_last_bot_start_ts' not in globals():
                _last_bot_start_ts = 0.0
            can_start = (time.time() - _last_bot_start_ts) > 300
            if stale and can_start:
                try:
                    # Check if process is already running
                    # Using pgrep -f run_multicoin_bot.py
                    process_running = False
                    try:
                        check = subprocess.run(["pgrep", "-f", "run_multicoin_bot.py"], capture_output=True)
                        if check.returncode == 0:
                            process_running = True
                            logger.info("run_multicoin_bot.py is running (pid found).")
                    except:
                        pass
                
                    if stale:
                        if process_running:
                            logger.warning("Process is running but log is stale. Killing process...")
                            subprocess.run(["pkill", "-f", "run_multicoin_bot.py"])
                            time.sleep(2) # Wait for kill

                        logger.info("Watchdog starting run_multicoin_bot.py...")
                        env = os.environ.copy()
                        env["PYTHONPATH"] = os.getcwd()
                        
                        subprocess.Popen(
                            [sys.executable, "scripts/run_multicoin_bot.py"],
                            cwd=os.getcwd(),
                            env=env,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                        logger.info("Watchdog started run_multicoin_bot.py")
                        _last_bot_start_ts = time.time()
                except Exception as e:
                    logger.error(f"Watchdog failed to start run_multicoin_bot.py: {e}")
        except Exception as e:
            logger.error(f"Services watchdog error: {e}")

    scheduler.add_job(services_watchdog, IntervalTrigger(minutes=5), id='services_watchdog', replace_existing=True, misfire_grace_time=600, coalesce=True, max_instances=1)

    if isinstance(paper_trader, RealTrader) and paper_trader.active:
        # Record every 1 hour
        scheduler.add_job(paper_trader.record_equity, IntervalTrigger(minutes=60), id='record_equity', replace_existing=True)
        # Also record once on startup
        paper_trader.record_equity()
        
        # Schedule Strategy Optimization (Every 12 hours)
        scheduler.add_job(
            run_strategy_optimization, 
            IntervalTrigger(hours=12), 
            args=[paper_trader],
            id='strategy_optimization',
            replace_existing=True
        )
        # Run once on startup to check
        # Run in background to avoid blocking startup
        asyncio.create_task(run_strategy_optimization(paper_trader))
    
    scheduler.start()
    logger.info("Scheduler started. Daily update set for 00:00. WebSocket broadcast every 10s.")
    
    yield
    
    # Shutdown
    scheduler.shutdown()

app = FastAPI(
    title="BTC Quant API", 
    description="Real-time BTC Analysis & Prediction API",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PriceData(BaseModel):
    timestamp: int
    datetime: str
    last: float
    high: float
    low: float
    volume: float
    price_change: Optional[float] = 0.0
    price_change_percent: Optional[float] = 0.0

class OHLCV(BaseModel):
    timestamp: int
    datetime: str
    open: float
    high: float
    low: float
    close: float
    volume: float

class BotConfig(BaseModel):
    confidence_threshold: float = 0.7
    notification_level: str = "HIGH_ONLY"  # 'ALL' or 'HIGH_ONLY'

# Global config
bot_config = BotConfig()

from typing import Any
from fastapi import Body

@app.get("/api/v1/tickers/24h")
async def get_monitored_tickers_24h():
    """Get 24h ticker data for all monitored symbols"""
    try:
        # Get all tickers (cost 40)
        # Use run_in_executor to avoid blocking event loop
        loop = asyncio.get_running_loop()
        all_tickers = await loop.run_in_executor(None, collector.fetch_all_tickers)
        
        if not all_tickers:
            return []
            
        # Filter for monitored symbols
        # MONITORED_SYMBOLS format: 'BTC/USDT:USDT' -> need 'BTCUSDT'
        monitored_map = {}
        for s in MONITORED_SYMBOLS:
            # s is like 'BTC/USDT:USDT'
            # Convert to 'BTCUSDT'
            clean_s = s.replace('/', '').split(':')[0]
            monitored_map[clean_s] = s
            
        result = []
        for t in all_tickers:
            # t['symbol'] is like 'BTCUSDT'
            if t['symbol'] in monitored_map:
                result.append(t)
                
        return result
    except Exception as e:
        logger.error(f"Error in get_monitored_tickers_24h: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/test-report")
async def test_report():
    """Trigger manual report for testing"""
    logger.info("Manual report trigger received")
    jobs = scheduler.get_jobs()
    job_info = [{"id": j.id, "next_run_time": str(j.next_run_time)} for j in jobs]
    logger.info(f"Current Jobs: {job_info}")
    return await send_hourly_monitor_report()

@app.get("/api/v1/bot/config", response_model=BotConfig)
async def get_bot_config():
    return bot_config

@app.post("/api/v1/bot/config")
async def update_bot_config(config: BotConfig):
    global bot_config, strategy_config
    bot_config = config
    # Sync to strategy config
    strategy_config.ml_threshold = config.confidence_threshold
    return {"status": "success", "config": bot_config}

@app.get("/api/v1/config/strategy", response_model=StrategyConfig)
async def get_strategy_config():
    return strategy_config

@app.post("/api/v1/config/strategy", response_model=StrategyConfig)
async def update_strategy_config(config: StrategyConfig):
    global strategy_config, bot_config
    strategy_config = config
    # Sync with bot_config which is used in frontend for now
    bot_config.confidence_threshold = config.ml_threshold
    logger.info(f"Updated strategy config: {config}")
    try:
        global_config_manager.update_config({
            "ema_period": config.ema_period,
            "rsi_period": config.rsi_period,
            "ml_threshold": config.ml_threshold,
            "leverage": config.leverage,
            "max_portfolio_leverage": config.max_portfolio_leverage
        })
    except Exception as e:
        logger.error(f"Failed to persist strategy config: {e}")
    return strategy_config

@app.get("/api/v1/config/trader", response_model=TraderConfig)
async def get_trader_config():
    # Mask secrets
    config_response = trader_config.copy()
    if config_response.api_key:
        config_response.api_key = config_response.api_key[:4] + "*" * 10
    if config_response.api_secret:
        config_response.api_secret = "*" * 10
    return config_response

@app.post("/api/v1/config/trader", response_model=TraderConfig)
async def update_trader_config(config: TraderConfig):
    global trader_config, trader, paper_trader
    
    # Preserve secrets if not provided
    if config.api_key is None and trader_config.api_key:
        config.api_key = trader_config.api_key
    if config.api_secret is None and trader_config.api_secret:
        config.api_secret = trader_config.api_secret
        
    # Preserve proxy if omitted and protection enabled
    if getattr(config, "preserve_proxy_on_update", True):
        if (config.proxy_url is None or str(config.proxy_url).strip() == "") and trader_config.proxy_url:
            config.proxy_url = trader_config.proxy_url
            logger.info("Preserved proxy_url from existing config during update")
        
    # Switch mode if needed or if keys updated in real mode
    keys_updated = (config.api_key and config.api_key != trader_config.api_key) or \
                   (config.api_secret and config.api_secret != trader_config.api_secret)
                   
    if config.mode != trader_config.mode or (config.mode == "real" and keys_updated):
        logger.info(f"Re-initializing trader (Mode: {config.mode}, Keys Updated: {keys_updated})")
        
        if config.mode == "real":
            # Need to re-init real trader with keys
            trader = RealTrader(
                symbol="BTC/USDT:USDT", 
                leverage=strategy_config.leverage, 
                notifier=None,
                api_key=config.api_key,
                api_secret=config.api_secret,
                proxy_url=config.proxy_url,
                monitored_symbols=MONITORED_SYMBOLS
            ) 
            trader.set_amount(config.amount_usdt)
            paper_trader = trader 
        else:
            trader = PaperTrader(notifier=None)
            paper_trader = trader
            
    # Update amount for RealTrader if already in real mode and just amount changed
    elif config.mode == "real" and hasattr(trader, 'set_amount'):
         trader.set_amount(config.amount_usdt)

    trader_config = config
    save_trader_config(config)
    logger.info(f"Updated trader config: {config}")
    
    # Mask secrets in response
    response = config.copy()
    if response.api_key:
        response.api_key = response.api_key[:4] + "*" * 10
    if response.api_secret:
        response.api_secret = "*" * 10
    return response

# Backtest endpoints
@app.post("/api/v1/backtest/run")
async def run_backtest(params: Dict[str, Any] = Body(...)):
    """Run backtest with custom params"""
    try:
        loop = asyncio.get_running_loop()
        horizon = params.get("horizon", 60)
        threshold = params.get("threshold", 0.75)
        days = params.get("days", 30)
        symbol = params.get("symbol", "BTCUSDT")
        sl = params.get("sl")
        tp = params.get("tp")
        initial_capital = params.get("initial_capital", 1000.0)
        
        # Map horizon to timeframe
        timeframe_map = {10: '10m', 30: '30m', 60: '1h', 240: '4h', 1440: '1d'}
        timeframe = timeframe_map.get(horizon, '1h')
        
        # If symbol differs from default backtester, re-init (simple approach)
        # Ideally we should pass symbol to run(), but SmartBacktester binds symbol in init
        # So we create a temporary instance
        
        def _run_task():
            proxy_url = trader_config.proxy_url
            bt = SmartBacktester(symbol=symbol, initial_capital=initial_capital, proxy_url=proxy_url)
            return bt.run(
                days=days, 
                timeframe=timeframe, 
                confidence_threshold=threshold,
                stop_loss=sl,
                take_profit=tp
            )
        
        # Run backtest
        run_result = await loop.run_in_executor(None, _run_task)
        
        if not run_result:
            return {"status": "error", "message": "Backtest returned no results (data might be missing)"}
            
        # SmartBacktester returns a dict with all results
        return {
            "status": "success", 
            "results": {
                "initial_capital": run_result["initial_capital"],
                "final_capital": run_result["final_balance"],
                "total_fees": run_result["total_fees"],
                "total_return_pct": run_result["total_return_pct"],
                "total_trades": run_result["total_trades"],
                "win_rate": run_result["win_rate"]
            },
            "trades": run_result["trades"],
            "equity_curve": run_result["equity_curve"]
        }
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/api/v1/strategy/signals")
async def get_strategy_signals():
    try:
        file_path = os.path.join(os.getcwd(), "data/strategy_signals.json")
        if os.path.exists(file_path):
             with open(file_path, "r") as f:
                 data = json.load(f)
                 return {"status": "success", "data": data}
        return {"status": "success", "data": []}
    except Exception as e:
        logger.error(f"Error serving strategy signals: {e}")
        return {"status": "error", "message": str(e), "data": []}

@app.post("/api/v1/test_notification")
async def test_notification():
    """Trigger an immediate Feishu notification for testing"""
    return await send_hourly_monitor_report()


@app.get("/api/v1/status")
async def get_system_status():
    """Get overall system status including trader status and strategy logs"""
    # Priority: Read from shared status file if in Real Mode
    # This ensures we see positions from the Multicoin Bot
    trader_status = None
    if trader_config.mode == "real":
         try:
             status_file = "data/real_trading_status.json"
             if os.path.exists(status_file):
                 with open(status_file, "r") as f:
                     status = json.load(f)
                     # Check freshness (e.g. < 5 mins old)
                     updated_at = float(status.get('updated_at', 0))
                     if time.time() - updated_at < 300: # 5 minutes
                         trader_status = status
                     else:
                         logger.warning(f"Status file stale (age: {time.time() - updated_at:.1f}s). Falling back to direct fetch.")
         except Exception as e:
             logger.error(f"Failed to read real trading status file: {e}")

    if not trader_status:
        trader_status = trader.get_status()
        
    strategy_logs = strategy.get_logs() if hasattr(strategy, 'get_logs') else []
    
    return {
        "trader": trader_status,
        "mode": trader_config.mode,
        "strategy": {
            "name": strategy.name,
            "config": strategy_config.model_dump(),
            "logs": strategy_logs
        },
        "server_time": datetime.now().isoformat()
    }

@app.get("/api/v1/feishu/history")
async def get_feishu_history():
    return feishu_bot.get_history()

@app.get("/api/v1/feishu/status")
async def get_feishu_status():
    """Get Feishu bot operational statistics"""
    return feishu_bot.get_stats()

@app.post("/api/v1/feishu/diagnose")
async def run_feishu_diagnosis():
    """Run diagnostic checks on Feishu bot"""
    try:
        # Run diagnosis in thread pool to avoid blocking
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, feishu_bot.diagnose)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    return {"status": "online", "service": "BTC Quant API"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


class OptimizationRequest(BaseModel):
    horizon: int = 60
    sl: float = 0.01
    tp: float = 0.02
    days: int = 30
    symbol: str = "BTCUSDT"

class SensitivityRequest(BaseModel):
    horizon: int = 60
    threshold: float = 0.7
    days: int = 30
    symbol: str = "BTCUSDT"

@app.post("/api/v1/backtest/sensitivity")
async def run_sensitivity(request: SensitivityRequest):
    try:
        loop = asyncio.get_running_loop()
        
        def _run_task():
            proxy_url = trader_config.proxy_url
            bt = SmartBacktester(symbol=request.symbol, proxy_url=proxy_url)
            return bt.run_sensitivity_analysis(
                horizon_minutes=request.horizon, 
                threshold=request.threshold,
                days=request.days
            )
            
        results = await loop.run_in_executor(None, _run_task)
        return {"status": "success", "results": results}
    except Exception as e:
        logger.error(f"Sensitivity analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/backtest/optimize")
async def optimize_strategy(request: OptimizationRequest):
    try:
        loop = asyncio.get_running_loop()
        
        def _run_task():
            proxy_url = trader_config.proxy_url
            bt = SmartBacktester(symbol=request.symbol, proxy_url=proxy_url)
            return bt.run_optimization(
                horizon_minutes=request.horizon,
                stop_loss=request.sl,
                take_profit=request.tp,
                days=request.days
            )
            
        results = await loop.run_in_executor(None, _run_task)
        return {"status": "success", "results": results}
    except Exception as e:
        logger.error(f"Optimization error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/portfolio/scan")
async def scan_portfolio():
    """Scan market for opportunities using PortfolioManager"""
    try:
        loop = asyncio.get_running_loop()
        
        def _scan_task():
            # Initialize with proxy if available
            pm = PortfolioManager(proxy_url=trader_config.proxy_url)
            return pm.scan_market()
            
        opportunities = await loop.run_in_executor(None, _scan_task)
        return {"status": "success", "opportunities": opportunities}
    except Exception as e:
        logger.error(f"Portfolio scan failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/market/fear-and-greed")
async def get_fear_and_greed():
    """Fetch Fear and Greed Index from alternative.me"""
    try:
        url = "https://api.alternative.me/fng/"
        loop = asyncio.get_running_loop()
        # Use lambda to pass timeout
        resp = await loop.run_in_executor(None, lambda: requests.get(url, timeout=5))
        
        if resp.status_code == 200:
            data = resp.json()
            if data.get('data') and len(data['data']) > 0:
                return data['data'][0]
        return {"value": "50", "value_classification": "Neutral"}
    except Exception as e:
        logger.error(f"Failed to fetch Fear & Greed Index: {e}")
        return {"value": "50", "value_classification": "Neutral"}

from deep_translator import GoogleTranslator

@app.get("/api/v1/market/news")
async def get_crypto_news():
    """Fetch Crypto News from CryptoCompare and translate to Chinese"""
    try:
        loop = asyncio.get_running_loop()
        # Fetch news in English
        url = "https://min-api.cryptocompare.com/data/v2/news/?lang=EN"
        resp = await loop.run_in_executor(None, lambda: requests.get(url, timeout=10))
        
        if resp.status_code == 200:
            data = resp.json()
            # Type 100 means success in CryptoCompare API
            if data.get('Type') >= 100: 
                news_list = data.get('Data', [])
                
                # Filter news: Select important categories and exclude low relevance
                # Categories to prioritize: Market, Trading, Regulation, BTC, ETH, Exchange, Business
                # Categories to exclude: Sponsored (if any), or specific low value ones
                
                important_keywords = ['Market', 'Trading', 'Regulation', 'BTC', 'ETH', 'Exchange', 'Business', 'Finance', 'Technology']
                
                filtered_news = []
                for item in news_list:
                    cats = item.get('categories', '').split('|')
                    # Check if any category matches important keywords
                    if any(keyword.upper() in [c.upper() for c in cats] for keyword in important_keywords):
                        filtered_news.append(item)
                
                # Take top 6 items (since display area is limited)
                top_news = filtered_news[:6] if filtered_news else news_list[:6]
                
                # Translate titles to Chinese
                translator = GoogleTranslator(source='auto', target='zh-CN')
                
                def translate_item(item):
                    try:
                        # Translate title
                        item['title'] = translator.translate(item['title'])
                        return item
                    except Exception as e:
                        logger.warning(f"Translation failed for news item {item.get('id')}: {e}")
                        return item

                # Run translation in parallel (using ThreadPoolExecutor implicitly via run_in_executor for the whole batch might be tricky, 
                # but deep_translator makes network calls, so better to run in executor)
                
                # We can run translations concurrently
                async def process_translation(items):
                    tasks = []
                    for item in items:
                        tasks.append(loop.run_in_executor(None, translate_item, item))
                    return await asyncio.gather(*tasks)

                translated_news = await process_translation(top_news)
                return translated_news

        return []
    except Exception as e:
        logger.error(f"Failed to fetch Crypto News: {e}")
        return []

@app.get("/api/v1/ticker", response_model=PriceData)
async def get_ticker(symbol: str = "BTCUSDT"):
    """Get latest ticker for a symbol"""
    collector = resource_manager.get_collector(symbol)
    ticker = await asyncio.to_thread(collector.fetch_current_price)
    if not ticker:
        raise HTTPException(status_code=503, detail="Could not fetch ticker data (likely API rate limit or connection error)")
    return ticker

@app.get("/api/v1/history", response_model=List[OHLCV])
async def get_history(limit: int = 100, timeframe: str = '1h', symbol: str = "BTCUSDT"):
    """Get historical OHLCV data for a symbol"""
    collector = resource_manager.get_collector(symbol)
    df = await asyncio.to_thread(collector.fetch_ohlcv, timeframe=timeframe, limit=limit)
    
    if df.empty:
        raise HTTPException(status_code=503, detail=f"Could not fetch historical data for {symbol}")
    
    records = df.to_dict('records')
    for record in records:
        if 'datetime' in record and not isinstance(record['datetime'], str):
             record['datetime'] = str(record['datetime'])
             
    return records

@app.get("/api/v1/predict")
async def get_prediction(symbol: str = "BTCUSDT"):
    """Get prediction for a symbol"""
    collector = resource_manager.get_collector(symbol)
    predictor = resource_manager.get_predictor(symbol)
    
    # Fetch recent data (need enough for indicators, e.g. 100 candles)
    # Using '1m' timeframe as that's what models are trained on
    # Increase limit to 500 to ensure enough history for MA99 and other indicators
    df = await asyncio.to_thread(collector.fetch_ohlcv, timeframe='1m', limit=500)
    
    if df.empty:
        raise HTTPException(status_code=503, detail=f"Could not fetch data for prediction for {symbol}")
    
    predictions = await asyncio.to_thread(predictor.predict_all, df)
    
    if not predictions:
        # Don't fail hard, return empty or status
        return {
            "symbol": symbol,
            "status": "calculating",
            "predictions": {}
        }
        
    return {
        "symbol": symbol,
        "timestamp": int(df.iloc[-1]['timestamp']),
        "datetime": str(df.iloc[-1]['datetime']),
        "predictions": predictions
    }

@app.get("/api/v1/model-info")
async def get_model_info():
    if not os.path.exists(METRICS_FILE):
        return {"status": "error", "message": "Model metrics not found. Please train models first."}
    try:
        with open(METRICS_FILE, 'r') as f:
            metrics = json.load(f)
            
        # Add training_date if missing, using file modification time
        if "training_date" not in metrics:
            mtime = os.path.getmtime(METRICS_FILE)
            metrics["training_date"] = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
            
        return metrics
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading model metrics: {str(e)}")

@app.get("/api/v1/data-summary")
async def get_data_summary():
    if not os.path.exists(DATA_DIR):
        return {"error": f"Data directory not found: {DATA_DIR}"}
    
    try:
        total_rows = 0
        total_size = 0
        start_dates = []
        end_dates = []
        
        loop = asyncio.get_running_loop()
        
        # Helper to process one file
        def process_file(filename):
            path = os.path.join(DATA_DIR, filename)
            if not filename.endswith('.csv'):
                return None
            
            # Filter only monitored symbols to avoid clutter
            # monitored_clean = [s.replace('/', '').split(':')[0] for s in MONITORED_SYMBOLS]
            # symbol = filename.split('_')[0]
            # if symbol not in monitored_clean:
            #    return None
                
            try:
                # Use pandas to read just what we need
                df = pd.read_csv(path)
                if df.empty:
                    return None
                    
                return {
                    "rows": len(df),
                    "start": str(df.iloc[0]['datetime']),
                    "end": str(df.iloc[-1]['datetime']),
                    "size": os.path.getsize(path)
                }
            except:
                return None

        # Process all files in parallel
        tasks = []
        files = [f for f in os.listdir(DATA_DIR) if f.endswith('.csv') and '1m' in f]
        
        for f in files:
            tasks.append(loop.run_in_executor(None, process_file, f))
            
        results = await asyncio.gather(*tasks)
        
        for res in results:
            if res:
                total_rows += res['rows']
                total_size += res['size']
                start_dates.append(res['start'])
                end_dates.append(res['end'])
        
        if not start_dates:
             return {"total_rows": 0}

        return {
            "total_rows": total_rows,
            "start_date": min(start_dates),
            "end_date": max(end_dates),
            "file_size_mb": round(total_size / (1024 * 1024), 2),
            "monitored_symbols_count": len([r for r in results if r])
        }
    except Exception as e:
        logger.error(f"Error in data summary: {e}")
        return {"error": str(e)}

# Paper Trading Endpoints
@app.post("/api/v1/paper/start")
async def start_paper_trading():
    paper_trader.start()
    return {"status": "started", "message": "Paper trading started"}

@app.post("/api/v1/paper/stop")
async def stop_paper_trading():
    paper_trader.stop()
    return {"status": "stopped", "message": "Paper trading stopped"}

@app.post("/api/v1/paper/reset")
async def reset_paper_trading():
    paper_trader.reset()
    return {"status": "reset", "message": "Paper trading reset"}

@app.get("/api/v1/paper/status")
async def get_paper_status():
    try:
        # Priority: Read from shared status file if in Real Mode
        # This avoids API rate limits and ensures consistency with the running bot
        if trader_config.mode == "real":
             try:
                 status_file = "data/real_trading_status.json"
                 if os.path.exists(status_file):
                     with open(status_file, "r") as f:
                         status = json.load(f)
                         # Check freshness (e.g. < 5 mins old)
                         updated_at = float(status.get('updated_at', 0))
                         if time.time() - updated_at < 300: # 5 minutes
                             return status
                         else:
                             logger.warning(f"Status file stale (age: {time.time() - updated_at:.1f}s). Falling back to direct fetch.")
             except Exception as e:
                 logger.error(f"Failed to read real trading status file: {e}")

        # Fallback: Direct Fetch (Paper Mode or Stale File)
        # We need current price for equity calc
        loop = asyncio.get_running_loop()
        ticker = await loop.run_in_executor(None, collector.fetch_current_price)
        # Use whatever active trader we have (could be real or paper)
        return paper_trader.get_status(ticker['last'])
    except Exception as e:
        logger.error(f"Error getting paper status: {e}")
        # Return last known state if price fetch fails
        return paper_trader.get_status(None)

@app.get("/api/v1/equity/history")
async def get_equity_history():
    try:
        file_path = os.path.join(os.getcwd(), "data/equity_history.json")
        if os.path.exists(file_path):
             with open(file_path, "r") as f:
                 data = json.load(f)
                 return {"status": "success", "data": data}
        return {"status": "success", "data": []}
    except Exception as e:
        logger.error(f"Error serving equity history: {e}")
        return {"status": "error", "message": str(e), "data": []}

@app.get("/api/v1/real/history")
async def get_real_trade_history():
    if not isinstance(paper_trader, RealTrader):
        return {"status": "error", "message": "Not in Real Trading mode"}
    
    try:
        loop = asyncio.get_running_loop()
        trades = await loop.run_in_executor(None, paper_trader.get_recent_trades, 50)
        return {"status": "success", "trades": trades}
    except Exception as e:
        logger.error(f"Error fetching real trades: {e}")
        return {"status": "error", "message": str(e)}

class RebalanceRequest(BaseModel):
    max_leverage: float = 15.0

@app.post("/api/v1/risk/rebalance")
async def rebalance_to_max_leverage(req: RebalanceRequest):
    """
    Proportionally reduce all open positions so that
    Total Notional <= max_leverage * Equity.
    """
    if not isinstance(paper_trader, RealTrader):
        return {"status": "error", "message": "Not in Real Trading mode"}
    try:
        loop = asyncio.get_running_loop()
        positions = await loop.run_in_executor(None, paper_trader.get_positions)
        equity = await loop.run_in_executor(None, paper_trader.get_total_balance)
        
        if equity <= 0:
            return {"status": "error", "message": "Equity not available"}
        
        total_notional = sum(p.get('position_value_usdt', 0.0) for p in positions.values())
        target_notional = req.max_leverage * equity
        
        if total_notional <= target_notional + 1e-6:
            return {
                "status": "success",
                "message": "No rebalance needed",
                "equity": equity,
                "total_notional": total_notional,
                "target_notional": target_notional
            }
        
        excess = total_notional - target_notional
        results = []
        
        for sym, pos in positions.items():
            pos_notional = pos.get('position_value_usdt', 0.0)
            if pos_notional <= 0:
                continue
            # Proportional reduction
            reduce_notional = excess * (pos_notional / total_notional)
            price = pos.get('mark_price') or pos.get('entry_price') or 0.0
            if price <= 0:
                continue
            amt_reduce = reduce_notional / price
            if amt_reduce <= 0:
                continue
            
            side = 'sell' if pos.get('side') == 'long' else 'buy'
            market_symbol = pos.get('symbol', sym)
            
            def _place_reduce_only():
                try:
                    order = paper_trader.exchange.create_order(
                        market_symbol, 'market', side, amt_reduce, params={'reduceOnly': True}
                    )
                    return {"symbol": market_symbol, "reduced_amount": amt_reduce, "order_id": order.get('id')}
                except Exception as e:
                    return {"symbol": market_symbol, "reduced_amount": 0.0, "error": str(e)}
            
            result = await loop.run_in_executor(None, _place_reduce_only)
            results.append(result)
        
        return {
            "status": "success",
            "equity": equity,
            "total_notional_before": total_notional,
            "target_notional": target_notional,
            "actions": results
        }
    except Exception as e:
        logger.error(f"Rebalance error: {e}")
        return {"status": "error", "message": str(e)}
