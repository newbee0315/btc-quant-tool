from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
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

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
scheduler = AsyncIOScheduler()
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
    ml_threshold: float = 0.75
    leverage: int = 1

class TraderConfig(BaseModel):
    mode: str = "paper"  # "paper" or "real"
    sl_pct: float = 0.03
    tp_pct: float = 0.025
    amount_usdt: float = 20.0
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    proxy_url: Optional[str] = None
    total_capital: float = 1000.0
    risk_per_trade: float = 0.02
    trailing_stop_trigger_pct: float = 0.01  # Trigger trailing stop when price moves 1% in favor
    trailing_stop_lock_pct: float = 0.02     # Lock profit when price moves 2% in favor

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
trader_config = load_trader_config()

# Configure Collector Proxy
if trader_config.proxy_url:
    logger.info(f"Setting collector proxy to {trader_config.proxy_url}")
    collector.set_proxy(trader_config.proxy_url)

# Initialize Trader based on loaded config
if trader_config.mode == "real":
    logger.info("⚠️ STARTING IN REAL TRADING MODE (from config) ⚠️")
    trader = RealTrader(
        symbol="BTC/USDT:USDT", 
        leverage=strategy_config.leverage, 
        notifier=None,
        api_key=trader_config.api_key,
        api_secret=trader_config.api_secret,
        proxy_url=trader_config.proxy_url
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

METRICS_FILE = os.path.join(os.path.dirname(__file__), '../../src/models/saved_models/model_metrics.json')
DATA_FILE = os.path.join(os.path.dirname(__file__), '../../src/data/btc_history_1m.csv')

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
            
            # 6. Signal Alert (Feishu Notification)
            # Notify if notify_signal is active
            if notify_signal != 0:
                  # Debounce: only notify if signal changed OR > 1 hour passed
                  current_ts = int(pd.Timestamp.now().timestamp())
                  if notify_signal != last_notification["signal"] or (current_ts - last_notification["timestamp"] > 3600):
                       # Use Beijing Time
                       beijing_tz = pytz.timezone('Asia/Shanghai')
                       bj_time = datetime.now(beijing_tz).strftime('%Y-%m-%d %H:%M:%S')
                       
                       direction_str = '做多 (LONG)' if notify_signal == 1 else '做空 (SHORT)'
                       msg = f"🚀 智能策略建议 (Smart Strategy Signal)\n时间: {bj_time}\n方向: {direction_str}\n当前价格: ${current_price:,.2f}\n原因: {strategy_reason}\nEMA200: {indicators.get('ema',0):.1f}\nRSI: {indicators.get('rsi',0):.1f}\n预测概率: {prob_30m:.2%}"
                       
                       await loop.run_in_executor(None, feishu_bot.send_text, msg)
                       last_notification["signal"] = notify_signal
                       last_notification["timestamp"] = current_ts
                     
            
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

async def send_heartbeat():
    """Send a heartbeat message to Feishu every few hours"""
    try:
        loop = asyncio.get_running_loop()
        ticker = await loop.run_in_executor(None, collector.fetch_current_price)
        price = ticker.get('last', 0)
        
        msg = f"💓 系统运行中 (System Online)\n当前 BTC 价格: ${price:,.2f}\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        await loop.run_in_executor(None, feishu_bot.send_text, msg)
        logger.info("Sent heartbeat to Feishu")
    except Exception as e:
        logger.error(f"Failed to send heartbeat: {e}")

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

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Schedule the daily task
    # Run at 00:00 every day
    scheduler.add_job(daily_update_task, CronTrigger(hour=0, minute=0))
    
    # Schedule real-time data broadcast (every 3 seconds)
    scheduler.add_job(broadcast_market_data, IntervalTrigger(seconds=3))
    
    # Heartbeat every 4 hours
    scheduler.add_job(send_heartbeat, IntervalTrigger(hours=4))
    
    scheduler.start()
    logger.info("Scheduler started. Daily update set for 00:00. WebSocket broadcast every 3s.")
    
    # Send startup notification
    try:
        await send_heartbeat()
    except:
        pass
    
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
        
    # Switch mode if needed or if keys updated in real mode
    keys_updated = (config.api_key and config.api_key != trader_config.api_key) or \
                   (config.api_secret and config.api_secret != trader_config.api_secret)
                   
    if config.mode != trader_config.mode or (config.mode == "real" and keys_updated):
        logger.info(f"Re-initializing trader (Mode: {config.mode}, Keys Updated: {keys_updated})")
        
        if config.mode == "real":
            # Need to re-init real trader with keys
            trader = RealTrader(
                symbol="BTC/USDT", 
                leverage=strategy_config.leverage, 
                notifier=None,
                api_key=config.api_key,
                api_secret=config.api_secret,
                proxy_url=config.proxy_url
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

@app.get("/api/v1/status")
async def get_system_status():
    """Get overall system status including trader status and strategy logs"""
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

@app.get("/api/v1/ticker", response_model=PriceData)
async def get_ticker(symbol: str = "BTCUSDT"):
    """Get latest ticker for a symbol"""
    collector = resource_manager.get_collector(symbol)
    ticker = await asyncio.to_thread(collector.fetch_current_price)
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
        return metrics
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading model metrics: {str(e)}")

@app.get("/api/v1/data-summary")
async def get_data_summary():
    if not os.path.exists(DATA_FILE):
        return {"error": "Data file not found"}
    
    try:
        # Read only header and some meta if possible, but pandas is fast enough
        df = pd.read_csv(DATA_FILE)
        if df.empty:
             return {"total_rows": 0}
             
        return {
            "total_rows": len(df),
            "start_date": str(df.iloc[0]['datetime']),
            "end_date": str(df.iloc[-1]['datetime']),
            "file_size_mb": round(os.path.getsize(DATA_FILE) / (1024 * 1024), 2)
        }
    except Exception as e:
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
        # We need current price for equity calc
        loop = asyncio.get_running_loop()
        ticker = await loop.run_in_executor(None, collector.fetch_current_price)
        # Use whatever active trader we have (could be real or paper)
        return paper_trader.get_status(ticker['last'])
    except Exception as e:
        logger.error(f"Error getting paper status: {e}")
        # Return last known state if price fetch fails
        return paper_trader.get_status(None)

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

