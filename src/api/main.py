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
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add src to python path to allow imports from data and models
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.data.collector import CryptoDataCollector
from src.models.predictor import PricePredictor
from src.models.train import train_models
from src.backtest.backtest import Backtester
from src.trader.paper_trader import PaperTrader
from src.trader.real_trader import RealTrader
from src.notification.feishu import FeishuBot

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize components
FEISHU_WEBHOOK_URL = os.getenv("FEISHU_WEBHOOK_URL")
if not FEISHU_WEBHOOK_URL:
    logger.warning("FEISHU_WEBHOOK_URL not set in .env file. Feishu notifications will be disabled.")

feishu_bot = FeishuBot(FEISHU_WEBHOOK_URL)

collector = CryptoDataCollector(symbol='BTCUSDT')
predictor = PricePredictor()
scheduler = AsyncIOScheduler()
backtester = Backtester()

# Trading Mode Selection
TRADING_MODE = os.getenv("TRADING_MODE", "paper").lower()
if TRADING_MODE == "real":
    logger.info("⚠️ STARTING IN REAL TRADING MODE ⚠️")
    # You might want to pass feishu_bot to RealTrader too if you add notification support later
    trader = RealTrader() 
else:
    logger.info("Starting in Paper Trading Mode")
    trader = PaperTrader(notifier=feishu_bot)

# Alias for compatibility with existing endpoints that use 'paper_trader'
paper_trader = trader

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
        # Using 60m horizon as primary signal for paper trading
        predictions = await loop.run_in_executor(None, predictor.predict_all, df)
        
        # 4. Generate Signal
        # Logic: If prob > threshold => Buy (1), if prob < (1-threshold) => Sell/Close (-1)
        # Fix: Access prediction by string key "60m"
        p60_data = predictions.get("60m", {})
        if isinstance(p60_data, dict):
            prob_60m = p60_data.get("probability", 0.5)
            is_high_conf = p60_data.get("is_high_confidence", False)
            direction = p60_data.get("direction", "HOLD")
        else:
            prob_60m = 0.5
            is_high_conf = False
            direction = "HOLD"
            
        # Signal for Paper Trader (based on user config)
        pt_signal = 0
        threshold = bot_config.confidence_threshold
        
        if prob_60m >= threshold:
            pt_signal = 1
        elif prob_60m <= (1 - threshold):
            pt_signal = -1
            
        # Signal for Notification (based on Model High Confidence)
        notify_signal = 0
        if is_high_conf:
            if direction == "UP":
                notify_signal = 1
            elif direction == "DOWN":
                notify_signal = -1

        # 5. Update Paper Trader (Automated Trading)
        # Optimal params from sensitivity analysis: SL 3.0%, TP 2.5%
        if ticker and 'last' in ticker:
            current_price = ticker['last']
            await loop.run_in_executor(
                None, 
                paper_trader.update, 
                current_price, 
                pt_signal, 
                "BTC/USDT", 
                0.03, 
                0.025, 
                prob_60m
            )
            
            # 6. Signal Alert (Feishu Notification)
            # Notify if notify_signal is active (High Confidence)
            # User request: "Directly push AI Strategy Signals high confidence strategies"
            if notify_signal != 0:
                  # Debounce: only notify if signal changed OR > 1 hour passed
                  current_ts = int(pd.Timestamp.now().timestamp())
                  if notify_signal != last_notification["signal"] or (current_ts - last_notification["timestamp"] > 3600):
                       msg = f"🚀 交易策略建议 (Strategy Signal)\n方向: {'做多 (LONG)' if notify_signal == 1 else '做空 (SHORT)'}\n当前价格: ${current_price:,.2f}\n置信度: {prob_60m:.2%}\n信号强度: HIGH"
                       
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

async def daily_update_task():
    """Task to update data and retrain models daily at 00:00"""
    logger.info("Starting daily update task...")
    try:
        # Run training in a separate thread to avoid blocking the event loop
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, train_models)
        
        # Reload models in the predictor
        predictor.load_models()
        logger.info("Daily update completed and models reloaded.")
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

@app.get("/api/v1/bot/config", response_model=BotConfig)
async def get_bot_config():
    return bot_config

@app.post("/api/v1/bot/config")
async def update_bot_config(config: BotConfig):
    global bot_config
    bot_config = config
    return {"status": "success", "config": bot_config}

@app.get("/")
async def root():
    return {"status": "online", "service": "BTC Quant API"}

@app.get("/api/v1/ticker", response_model=PriceData)
async def get_ticker(symbol: str = "BTC/USDT"):
    ticker = collector.fetch_current_price()
    return ticker

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

class BacktestRequest(BaseModel):
    horizon: int = 60
    threshold: float = 0.6
    sl: float = 0.01
    tp: float = 0.02
    initial_capital: float = 10000

@app.post("/api/v1/backtest")
async def run_backtest(request: BacktestRequest):
    try:
        backtester.initial_capital = request.initial_capital
        results, trades, equity_curve = backtester.run_backtest(
            horizon_minutes=request.horizon,
            confidence_threshold=request.threshold,
            stop_loss=request.sl,
            take_profit=request.tp
        )
        return {
            "status": "success",
            "results": results,
            "trades": trades,
            "equity_curve": equity_curve
        }
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class OptimizationRequest(BaseModel):
    horizon: int = 60
    sl: float = 0.01
    tp: float = 0.02

class SensitivityRequest(BaseModel):
    horizon: int = 60
    threshold: float = 0.7

@app.post("/api/v1/backtest/sensitivity")
async def run_sensitivity(request: SensitivityRequest):
    try:
        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(
            None, 
            backtester.run_sensitivity_analysis, 
            request.horizon, 
            request.threshold
        )
        return {"status": "success", "results": results}
    except Exception as e:
        logger.error(f"Sensitivity analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/backtest/optimize")
async def optimize_strategy(request: OptimizationRequest):
    try:
        results = backtester.run_optimization(
            horizon_minutes=request.horizon,
            stop_loss=request.sl,
            take_profit=request.tp
        )
        return {"status": "success", "results": results}
    except Exception as e:
        logger.error(f"Optimization error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/history", response_model=List[OHLCV])
async def get_history(limit: int = 100, timeframe: str = '1h'):
    df = collector.fetch_ohlcv(timeframe=timeframe, limit=limit)
    if df.empty:
        raise HTTPException(status_code=503, detail="Could not fetch historical data")
    
    records = df.to_dict('records')
    for record in records:
        if 'datetime' in record and not isinstance(record['datetime'], str):
             record['datetime'] = str(record['datetime'])
             
    return records

@app.get("/api/v1/predict")
async def get_prediction():
    # Fetch recent data (need enough for indicators, e.g. 100 candles)
    # Using '1m' timeframe as that's what models are trained on
    # Increase limit to 500 to ensure enough history for MA99 and other indicators
    df = collector.fetch_ohlcv(timeframe='1m', limit=500)
    
    if df.empty:
        raise HTTPException(status_code=503, detail="Could not fetch data for prediction")
    
    predictions = predictor.predict_all(df)
    
    if not predictions:
        # Don't fail hard, return empty or status
        return {
            "symbol": "BTC/USDT",
            "status": "calculating",
            "predictions": {}
        }
        
    return {
        "symbol": "BTC/USDT",
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
        return paper_trader.get_status(ticker['last'])
    except Exception as e:
        logger.error(f"Error getting paper status: {e}")
        # Return last known state if price fetch fails
        return paper_trader.get_status(None)

