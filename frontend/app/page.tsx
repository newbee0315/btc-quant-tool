'use client';

import React, { useEffect, useState } from 'react';
import { KlineChart } from '@/components/KlineChart';
import { BacktestPanel } from '@/components/BacktestPanel';
import { PortfolioPanel } from '@/components/PortfolioPanel';
import { PaperTradingPanel, PaperStatus } from '@/components/PaperTradingPanel';
import { UTCTimestamp } from 'lightweight-charts';
import { 
    ArrowUp, ArrowDown, Activity, Clock, BarChart2, TrendingUp, TrendingDown, ChevronDown, ChevronUp, 
    Beaker, Wallet, Settings, DollarSign, Shield, History, CheckCircle2, XCircle, RefreshCw, AlertCircle,
    LayoutGrid
} from 'lucide-react';
import axios from 'axios';

interface Trade {
    id: string;
    timestamp: number;
    datetime: string;
    side: 'buy' | 'sell';
    price: number;
    amount: number;
    cost: number;
    fee: {
        cost: number;
        currency: string;
    };
    realized_pnl: number;
}

interface Position {
    entry_price: number;
    amount: number;
    position_value_usdt?: number;
    side: 'long' | 'short';
    unrealized_pnl: number;
    pnl_pct: number;
    liquidation_price?: number;
    mark_price?: number;
    initial_margin?: number;
    leverage?: number;
    sl_price?: number;
    tp_price?: number;
}

interface StrategyStats {
    win_rate: number;
    total_trades: number;
    total_pnl: number;
    total_fees?: number;
    duration: string;
    start_time: string;
}

interface TraderStatus {
    active: boolean;
    balance: number;
    total_balance: number;
    equity: number;
    positions: { [key: string]: Position };
    trade_history: Trade[];
    stats: StrategyStats;
    initial_balance: number;
    connection_status?: string;
    connection_error?: string | null;
}

interface SystemStatus {
    trader: TraderStatus;
    mode: 'paper' | 'real';
    strategy: {
        name: string;
        config: any;
        logs: any[];
    };
    server_time: string;
}

interface TickerData {
    timestamp: number;
    datetime: string;
    last: number;
    high: number;
    low: number;
    volume: number;
}

interface KlineData {
    time: UTCTimestamp;
    open: number;
    high: number;
    low: number;
    close: number;
}

interface PredictionResult {
    direction: 'UP' | 'DOWN';
    probability: number;
    confidence: number;
    is_high_confidence: boolean;
}

interface PredictionData {
    symbol: string;
    timestamp: number;
    predictions: {
        [key: string]: PredictionResult; // "10m", "30m", "60m"
    };
}

interface StrategyLog {
    id: string;
    timestamp: number;
    timeString: string;
    direction: 'UP' | 'DOWN';
    entryPrice: number;
    tp: number;
    sl: number;
    horizon: string;
    isHighConf: boolean;
    probability?: number;
    confidence?: number;
    reasons?: string[] | string;
    ema?: number;
    rsi?: number;
    macd_hist?: number;
}

interface BotConfig {
    confidence_threshold: number;
    notification_level: 'ALL' | 'HIGH_ONLY';
}

export default function Home() {
    const [ticker, setTicker] = useState<TickerData | null>(null);
    const [klineData, setKlineData] = useState<KlineData[]>([]);
    const [prediction, setPrediction] = useState<PredictionData | null>(null);
    const [loading, setLoading] = useState(true);
    const [selectedTimeframe, setSelectedTimeframe] = useState('10m');
    const [strategyLogs, setStrategyLogs] = useState<StrategyLog[]>([]);
    const [showAllStrategies, setShowAllStrategies] = useState(false);
    const [isLogsLoaded, setIsLogsLoaded] = useState(false);

    // Monitor State
    const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
    const [monitorLastUpdated, setMonitorLastUpdated] = useState<Date | null>(null);
    const [monitorError, setMonitorError] = useState('');

    // Backtest Trades State
    const [backtestTrades, setBacktestTrades] = useState<Trade[]>([]);

    const handleBacktestResult = (results: any, trades: any[], equityCurve: any[]) => {
        const processedTrades: Trade[] = [];
        trades.forEach((t: any) => {
            // Entry Marker
            processedTrades.push({
                id: `${t.id}_entry`,
                timestamp: t.entry_time,
                datetime: new Date(t.entry_time).toISOString(),
                side: t.entry_side === 'long' ? 'buy' : 'sell',
                price: t.entry_price,
                amount: t.amount,
                cost: t.amount * t.entry_price,
                fee: { cost: 0, currency: 'USDT' }, 
                realized_pnl: 0
            });
            // Exit Marker
            processedTrades.push({
                id: `${t.id}_exit`,
                timestamp: t.timestamp,
                datetime: t.datetime,
                side: t.side as 'buy' | 'sell', 
                price: t.price,
                amount: t.amount,
                cost: t.amount * t.price,
                fee: { cost: typeof t.fee === 'number' ? t.fee : t.fee?.cost || 0, currency: 'USDT' },
                realized_pnl: t.realized_pnl
            });
        });
        setBacktestTrades(processedTrades);
    };

    // Load strategy logs from localStorage on mount
    useEffect(() => {
        const savedLogs = localStorage.getItem('strategyLogs');
        if (savedLogs) {
            try {
                setStrategyLogs(JSON.parse(savedLogs));
            } catch (e) {
                console.error("Failed to parse strategy logs", e);
            }
        }
        setIsLogsLoaded(true);
    }, []);

    // Save strategy logs to localStorage whenever they change
    useEffect(() => {
        if (isLogsLoaded) {
            localStorage.setItem('strategyLogs', JSON.stringify(strategyLogs));
        }
    }, [strategyLogs, isLogsLoaded]);

    // Monitor Fetch Logic
    const fetchStatus = async () => {
        try {
            const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
            const res = await axios.get(`${API_URL}/api/v1/status`);
            setSystemStatus(res.data);
            
            // Sync strategy logs from backend (Source of Truth for reasons)
            if (res.data.strategy && res.data.strategy.logs && res.data.strategy.logs.length > 0) {
                 const backendLogs = res.data.strategy.logs.map((log: any) => ({
                    id: `${log.timestamp}-${log.signal}`,
                    timestamp: new Date(log.timestamp).getTime(),
                    timeString: new Date(log.timestamp).toLocaleString('zh-CN', { 
                        month: '2-digit', 
                        day: '2-digit', 
                        hour: '2-digit', 
                        minute: '2-digit', 
                        second: '2-digit',
                        hour12: false
                    }),
                    direction: log.signal === 1 ? 'UP' : (log.signal === -1 ? 'DOWN' : 'NONE'),
                    entryPrice: log.close,
                    tp: log.tp,
                    sl: log.sl,
                    horizon: '30m', 
                    isHighConf: Math.abs(log.ml_prob - 0.5) > 0.2, 
                    probability: log.ml_prob,
                    confidence: log.ml_prob > 0.5 ? log.ml_prob : 1 - log.ml_prob,
                    reasons: log.reasons,
                    ema: log.ema,
                    rsi: log.rsi,
                    macd_hist: log.macd_hist
                 }));
                 // Merge with existing logs to keep history if needed, but backend usually returns full history (50 items)
                 // So we can just replace.
                 setStrategyLogs(backendLogs);
            }

            setMonitorLastUpdated(new Date());
            setMonitorError('');
        } catch (err) {
            console.error("Failed to fetch status:", err);
            setMonitorError('无法连接到策略引擎');
        }
    };

    useEffect(() => {
        fetchStatus();
        const interval = setInterval(fetchStatus, 3000); // Poll every 3 seconds
        return () => clearInterval(interval);
    }, []);

    const [showBacktest, setShowBacktest] = useState(false);
    const [showPortfolio, setShowPortfolio] = useState(false);
    
    // MA Data States
    const [ma7Data, setMa7Data] = useState<{time: UTCTimestamp, value: number}[]>([]);
    const [ma25Data, setMa25Data] = useState<{time: UTCTimestamp, value: number}[]>([]);
    const [ma99Data, setMa99Data] = useState<{time: UTCTimestamp, value: number}[]>([]);

    // Bot Config State
    const [botConfig, setBotConfig] = useState<BotConfig>({ confidence_threshold: 0.7, notification_level: 'HIGH_ONLY' });
    const [showConfig, setShowConfig] = useState(false);

    const fetchBotConfig = React.useCallback(async () => {
        try {
            const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
            const res = await axios.get(`${API_URL}/api/v1/bot/config`);
            if (res.data) setBotConfig(res.data);
        } catch (e) {
            console.error("Failed to fetch bot config", e);
        }
    }, []);

    const updateBotConfig = async (newConfig: BotConfig) => {
        try {
            // Optimistic update
            setBotConfig(newConfig);
            const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
            await axios.post(`${API_URL}/api/v1/bot/config`, newConfig);
        } catch (e) {
            console.error("Failed to update bot config", e);
            fetchBotConfig(); // Revert on error
        }
    };

    const calculateSMA = React.useCallback((data: KlineData[], period: number) => {
        const result = [];
        for (let i = 0; i < data.length; i++) {
            if (i < period - 1) continue;
            let sum = 0;
            for (let j = 0; j < period; j++) {
                sum += data[i - j].close;
            }
            result.push({
                time: data[i].time,
                value: sum / period,
            });
        }
        return result;
    }, []);

    // Process strategy logs logic extracted for reuse
    // DEPRECATED: We now use backend logs (via fetchStatus) to ensure reasons/notes are included.
    const processStrategyLogs = React.useCallback((currentPred: PredictionData, currentTicker: TickerData) => {
        // Disabled to prevent overwriting backend logs with local incomplete logs
        return;
        /*
        if (currentTicker && currentPred && currentPred.predictions) {
            setStrategyLogs(prevLogs => {
                const lastLog = prevLogs[0];
                if (lastLog && lastLog.timestamp === currentPred.timestamp) {
                    return prevLogs;
                }

                // Generate new strategy log
                const p60 = currentPred.predictions['60m'];
                const p30 = currentPred.predictions['30m'];
                const p10 = currentPred.predictions['10m'];
                
                let activeSignal = null;
                let timeHorizon = '';
                
                if (p60?.is_high_confidence) { activeSignal = p60; timeHorizon = '60m'; }
                else if (p30?.is_high_confidence) { activeSignal = p30; timeHorizon = '30m'; }
                else if (p10?.is_high_confidence) { activeSignal = p10; timeHorizon = '10m'; }
                else { activeSignal = p60; timeHorizon = '60m'; }

                if (!activeSignal) return prevLogs;

                const isBullish = activeSignal.direction === 'UP';
                const currentPrice = currentTicker.last;
                const slPercent = 0.03;  // SL 3.0%
                const tpPercent = 0.025; // TP 2.5%

                const newLog: StrategyLog = {
                    id: `${currentPred.timestamp}-${timeHorizon}`,
                    timestamp: currentPred.timestamp,
                    timeString: new Date().toLocaleString('zh-CN', { 
                        month: '2-digit', 
                        day: '2-digit', 
                        hour: '2-digit', 
                        minute: '2-digit', 
                        second: '2-digit',
                        hour12: false
                    }),
                    direction: activeSignal.direction,
                    entryPrice: currentPrice,
                    tp: isBullish ? currentPrice * (1 + tpPercent) : currentPrice * (1 - tpPercent),
                    sl: isBullish ? currentPrice * (1 - slPercent) : currentPrice * (1 + slPercent),
                    horizon: timeHorizon,
                    isHighConf: activeSignal.is_high_confidence,
                    probability: activeSignal.probability,
                    confidence: activeSignal.confidence
                };

                return [newLog, ...prevLogs].slice(0, 50); // Keep last 50
            });
        }
        */
    }, []);

    const fetchData = React.useCallback(async () => {
        try {
            const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
            
            // Parallelize requests to improve loading speed
            const [tickerRes, historyRes, predRes] = await Promise.all([
                axios.get(`${API_URL}/api/v1/ticker`),
                axios.get(`${API_URL}/api/v1/history?limit=200&timeframe=${selectedTimeframe}`),
                axios.get(`${API_URL}/api/v1/predict`).catch(e => {
                    console.warn("Prediction API not ready yet");
                    return { data: null };
                })
            ]);
            
            if (predRes.data) {
                setPrediction(predRes.data);
                
                // Update Strategy Logs
                processStrategyLogs(predRes.data, tickerRes.data);
            }

            setTicker(tickerRes.data);
            
            // Transform data for lightweight-charts
            const formattedData = historyRes.data.map((item: any) => ({
                time: (item.timestamp / 1000) as UTCTimestamp,
                open: item.open,
                high: item.high,
                low: item.low,
                close: item.close,
            }));
            
            setKlineData(formattedData);
            
            if (formattedData.length > 0) {
                setMa7Data(calculateSMA(formattedData, 7));
                setMa25Data(calculateSMA(formattedData, 25));
                setMa99Data(calculateSMA(formattedData, 99));
            }

            setLoading(false);
        } catch (error) {
            console.error("Failed to fetch data:", error);
            setLoading(false);
        }
    }, [selectedTimeframe, calculateSMA, processStrategyLogs]);

    useEffect(() => {
        fetchData();
        fetchBotConfig();
        
        const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        const WS_URL = API_URL.replace('http', 'ws') + '/ws';
        const ws = new WebSocket(WS_URL);
        
        ws.onopen = () => {
            console.log('Connected to WebSocket');
        };

        ws.onmessage = (event) => {
            try {
                const message = JSON.parse(event.data);
                if (message.type === 'ticker_update') {
                    const newTicker = message.data;
                    const newPredictions = message.predictions;
                    
                    setTicker(newTicker);
                    
                    if (newPredictions) {
                        const predData = {
                            symbol: 'BTCUSDT',
                            timestamp: Date.now(), // or server_time if available
                            predictions: newPredictions
                        };
                        setPrediction(predData);
                        processStrategyLogs(predData, newTicker);
                    }
                    
                    // Update last candle in chart for real-time effect
                    setKlineData(prevData => {
                        if (prevData.length === 0) return prevData;
                        const lastCandle = prevData[prevData.length - 1];
                        const newClose = newTicker.last;
                        
                        // Update high/low/close of the last candle
                        const updatedCandle = {
                            ...lastCandle,
                            close: newClose,
                            high: Math.max(lastCandle.high, newClose),
                            low: Math.min(lastCandle.low, newClose)
                        };
                        
                        return [...prevData.slice(0, -1), updatedCandle];
                    });
                }
            } catch (e) {
                console.error("WS Parse Error", e);
            }
        };

        const interval = setInterval(fetchData, 5000); 
        
        return () => {
            clearInterval(interval);
            ws.close();
        };
    }, [fetchData, fetchBotConfig, processStrategyLogs]);

    // Monitor Helpers
    const trader = systemStatus?.trader;
    const isReal = systemStatus?.mode === 'real';
    const pnlColor = (trader?.stats.total_pnl || 0) >= 0 ? 'text-[#0ECB81]' : 'text-[#F6465D]';
    const pnlSign = (trader?.stats.total_pnl || 0) >= 0 ? '+' : '';
    const roi = trader && trader.initial_balance > 0 ? (trader.stats.total_pnl / trader.initial_balance) * 100 : 0;
    const roiColor = roi >= 0 ? 'text-[#0ECB81]' : 'text-[#F6465D]';

    return (
        <div className="min-h-screen bg-[#0E1117] text-[#FAFAFA] font-sans flex flex-col">
            {/* Header */}
            <header className="border-b border-[#2B3139] px-4 py-3 md:px-6 md:py-4 flex justify-between items-center bg-[#161A25]">
                <div className="flex items-center gap-2 md:gap-3">
                    <div className="bg-[#F0B90B] p-1.5 rounded-lg">
                        <Activity className="w-4 h-4 md:w-5 md:h-5 text-black" />
                    </div>
                    <div>
                        <h1 className="text-lg md:text-xl font-bold tracking-tight">BTC Quant Pro</h1>
                        <p className="text-[10px] md:text-xs text-[#848E9C]">AI-Powered Market Analysis</p>
                    </div>
                </div>
                <div className="flex items-center gap-2 md:gap-4">
                    {/* Connection Status Indicator */}
                    <div className="flex flex-col items-end group relative mr-2">
                        <div className="flex items-center gap-1.5 cursor-help">
                            <div className={`w-2 h-2 rounded-full ${
                                trader?.connection_status === 'Connected' ? 'bg-[#0ECB81] animate-pulse' : 
                                trader?.connection_status === 'Error' ? 'bg-[#F6465D]' : 'bg-[#F0B90B]'
                            }`}></div>
                            <span className={`text-xs font-medium ${
                                trader?.connection_status === 'Connected' ? 'text-[#0ECB81]' : 
                                trader?.connection_status === 'Error' ? 'text-[#F6465D]' : 'text-[#F0B90B]'
                            }`}>
                                {trader?.connection_status === 'Connected' ? '已连接' : 
                                 trader?.connection_status === 'Error' ? '连接错误' : 
                                 '连接中...'}
                            </span>
                        </div>
                        {trader?.connection_error && (
                            <div className="absolute top-full right-0 mt-2 p-2 bg-[#1E2329] border border-red-900/50 rounded shadow-xl text-xs text-[#F6465D] w-64 z-50 hidden group-hover:block">
                                {trader.connection_error}
                            </div>
                        )}
                    </div>

                    <button 
                        onClick={() => setShowBacktest(true)}
                        className="flex items-center gap-2 px-2 py-1.5 md:px-3 bg-[#2B3139] hover:bg-[#363C45] text-[#EAECEF] text-xs md:text-sm font-medium rounded-lg transition-colors border border-[#474D57]"
                    >
                        <Beaker className="w-3 h-3 md:w-4 md:h-4 text-[#F0B90B]" />
                        <span className="hidden sm:inline">Backtest</span>
                    </button>
                    <button 
                        onClick={() => setShowPortfolio(true)}
                        className="flex items-center gap-2 px-2 py-1.5 md:px-3 bg-[#2B3139] hover:bg-[#363C45] text-[#EAECEF] text-xs md:text-sm font-medium rounded-lg transition-colors border border-[#474D57]"
                    >
                        <LayoutGrid className="w-3 h-3 md:w-4 md:h-4 text-[#F0B90B]" />
                        <span className="hidden sm:inline">Portfolio</span>
                    </button>
                    <a href="/data" className="hidden md:block text-sm text-[#848E9C] hover:text-[#F0B90B] transition-colors">
                        Data Info
                    </a>
                    <a href="/models" className="hidden md:block text-sm text-[#848E9C] hover:text-[#F0B90B] transition-colors">
                        Model Info
                    </a>
                    <div className="flex items-center gap-2 px-2 py-1 md:px-3 md:py-1.5 bg-[#1E2329] rounded-full border border-[#2B3139]">
                        <span className="w-1.5 h-1.5 md:w-2 md:h-2 bg-[#0ECB81] rounded-full animate-pulse"></span>
                        <span className="text-[10px] md:text-xs font-medium text-[#0ECB81] whitespace-nowrap">
                            {isReal ? 'REAL TRADING' : 'PAPER TRADING'}
                        </span>
                    </div>
                </div>
            </header>

            <main className="flex-1 p-2 space-y-2 overflow-y-auto">
                {/* Top Metrics Row */}
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2">
                    <div className="bg-[#1E2329] p-2 rounded-xl border border-[#2B3139]">
                        <p className="text-[#848E9C] text-[10px] mb-1">Last Price</p>
                        <div className="flex items-baseline gap-2">
                            <span className="text-lg font-bold text-[#EAECEF]">
                                {ticker ? `$${ticker.last.toLocaleString()}` : <span className="animate-pulse">Loading...</span>}
                            </span>
                        </div>
                    </div>
                    <div className="bg-[#1E2329] p-2 rounded-xl border border-[#2B3139]">
                        <p className="text-[#848E9C] text-[10px] mb-1">24h High</p>
                        <span className="text-base font-semibold text-[#EAECEF]">
                            {ticker ? `$${ticker.high.toLocaleString()}` : '---'}
                        </span>
                    </div>
                    <div className="bg-[#1E2329] p-2 rounded-xl border border-[#2B3139]">
                        <p className="text-[#848E9C] text-[10px] mb-1">24h Low</p>
                        <span className="text-base font-semibold text-[#EAECEF]">
                            {ticker ? `$${ticker.low.toLocaleString()}` : '---'}
                        </span>
                    </div>
                    <div className="bg-[#1E2329] p-2 rounded-xl border border-[#2B3139]">
                        <p className="text-[#848E9C] text-[10px] mb-1">24h Volume</p>
                        <span className="text-base font-semibold text-[#EAECEF]">
                            {ticker ? ticker.volume.toLocaleString().split('.')[0] : '---'}
                        </span>
                    </div>
                    <div className="bg-[#1E2329] p-2 rounded-xl border border-[#2B3139]">
                        <p className="text-[#848E9C] text-[10px] mb-1">Fear & Greed</p>
                         <div className="flex justify-between items-center">
                            <span className="text-base font-semibold text-[#F0B90B]">65 (Greed)</span>
                        </div>
                    </div>
                </div>

                {/* Main Chart Section */}
                <div className="grid grid-cols-1 lg:grid-cols-4 gap-2 h-[600px]">
                    <div className="lg:col-span-3 bg-[#1E2329] rounded-xl border border-[#2B3139] overflow-hidden flex flex-col">
                        {/* Chart Header */}
                        <div className="px-4 py-2 border-b border-[#2B3139] flex justify-between items-center bg-[#1E2329]">
                            <div className="flex items-center gap-4">
                                <h2 className="font-semibold text-sm">BTC/USDT Chart (Futures)</h2>
                                <div className="flex gap-1 bg-[#2B3139] p-0.5 rounded-lg">
                                    {['10m', '30m', '1h', '4h', '1d'].map((tf) => (
                                        <button
                                            key={tf}
                                            onClick={() => {
                                                if (selectedTimeframe !== tf) {
                                                    setSelectedTimeframe(tf);
                                                    setLoading(true);
                                                }
                                            }}
                                            className={`px-2 py-0.5 rounded text-xs font-medium transition-all ${
                                                selectedTimeframe === tf 
                                                ? 'bg-[#474D57] text-[#EAECEF] shadow-sm' 
                                                : 'text-[#848E9C] hover:text-[#EAECEF]'
                                            }`}
                                        >
                                            {tf}
                                        </button>
                                    ))}
                                </div>
                            </div>
                        </div>
                        
                        {/* Chart Body */}
                        <div className="flex-1 relative w-full h-full min-h-0">
                            {loading ? (
                                <div className="absolute inset-0 flex items-center justify-center">
                                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#F0B90B]"></div>
                                </div>
                            ) : (
                                <KlineChart 
                                    data={klineData} 
                                    ma7={ma7Data}
                                    ma25={ma25Data}
                                    ma99={ma99Data}
                                    trades={[...(trader?.trade_history || []), ...backtestTrades]}
                                />
                            )}
                        </div>
                    </div>

                    {/* Right Panel: Strategy & Config */}
                    <div className="flex flex-col gap-2">
                        {/* AI Prediction Card */}
                        <div className="bg-[#1E2329] rounded-xl border border-[#2B3139] p-4 flex-1">
                            <div className="flex justify-between items-center mb-4">
                                <h3 className="font-bold flex items-center gap-2 text-[#EAECEF]">
                                    <Activity className="w-4 h-4 text-[#F0B90B]" />
                                    AI Forecast
                                </h3>
                                <button 
                                    onClick={() => setShowConfig(!showConfig)}
                                    className="p-1 hover:bg-[#2B3139] rounded text-[#848E9C] transition-colors"
                                >
                                    <Settings className="w-4 h-4" />
                                </button>
                            </div>

                            {showConfig ? (
                                <div className="space-y-4 mb-4 bg-[#2B3139]/30 p-3 rounded-lg">
                                    <div>
                                        <label className="text-xs text-[#848E9C] block mb-1">Confidence Threshold</label>
                                        <input 
                                            type="range" 
                                            min="0.5" 
                                            max="0.95" 
                                            step="0.05"
                                            value={botConfig.confidence_threshold}
                                            onChange={(e) => updateBotConfig({...botConfig, confidence_threshold: parseFloat(e.target.value)})}
                                            className="w-full accent-[#F0B90B]"
                                        />
                                        <div className="flex justify-between text-xs text-[#EAECEF]">
                                            <span>0.5</span>
                                            <span className="font-bold text-[#F0B90B]">{botConfig.confidence_threshold}</span>
                                            <span>0.95</span>
                                        </div>
                                    </div>
                                    <div>
                                        <label className="text-xs text-[#848E9C] block mb-1">Notifications</label>
                                        <select 
                                            value={botConfig.notification_level}
                                            onChange={(e) => updateBotConfig({...botConfig, notification_level: e.target.value as any})}
                                            className="w-full bg-[#1E2329] border border-[#474D57] rounded px-2 py-1 text-xs text-[#EAECEF]"
                                        >
                                            <option value="ALL">All Signals</option>
                                            <option value="HIGH_ONLY">High Confidence Only</option>
                                        </select>
                                    </div>
                                </div>
                            ) : null}

                            <div className="space-y-3">
                                {['10m', '30m', '60m'].map((horizon) => {
                                    const pred = prediction?.predictions[horizon];
                                    if (!pred) return null;
                                    
                                    const isUp = pred.direction === 'UP';
                                    const confidence = pred.confidence ? (pred.confidence * 100).toFixed(1) : '0.0';
                                    const prob = pred.probability ? (pred.probability * 100).toFixed(1) : '0.0';
                                    
                                    return (
                                        <div key={horizon} className="flex items-center justify-between p-2 rounded-lg bg-[#2B3139]/30 hover:bg-[#2B3139]/50 transition-colors">
                                            <div className="flex items-center gap-3">
                                                <span className="text-xs font-mono text-[#848E9C] w-8">{horizon}</span>
                                                <div className={`flex items-center gap-1.5 ${isUp ? 'text-[#0ECB81]' : 'text-[#F6465D]'}`}>
                                                    {isUp ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
                                                    <span className="font-bold">{isUp ? 'BULL' : 'BEAR'}</span>
                                                </div>
                                            </div>
                                            <div className="text-right">
                                                <div className="text-xs font-bold text-[#EAECEF]">Prob: {prob}%</div>
                                                <div className={`text-[10px] ${pred.is_high_confidence ? 'text-[#F0B90B]' : 'text-[#848E9C]'}`}>
                                                    Conf: {confidence}%
                                                </div>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    </div>
                </div>

                {/* Strategy Monitor Section (New) */}
                <div className="mt-4">
                    <div className="flex items-center justify-between mb-2 px-1">
                        <h2 className="text-lg font-bold flex items-center gap-2">
                            <Activity className="w-5 h-5 text-[#F0B90B]" />
                            Strategy Monitor
                        </h2>
                        <span className="text-xs text-[#848E9C]">Last Updated: {monitorLastUpdated ? monitorLastUpdated.toLocaleTimeString() : '--:--:--'}</span>
                    </div>

                    {/* KPI Grid */}
                    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-2 mb-2">
                        {/* Total Capital */}
                        <div className="bg-[#1E2329] p-3 rounded-xl border border-[#2B3139] relative overflow-hidden">
                            <div className="absolute top-0 right-0 p-2 opacity-10">
                                <DollarSign className="w-10 h-10 text-[#EAECEF]" />
                            </div>
                            <p className="text-[#848E9C] text-[10px] font-medium uppercase mb-1">Total Equity</p>
                            <h3 className="text-xl font-bold font-mono tracking-tight text-[#EAECEF]">
                                ${trader?.equity ? trader.equity.toFixed(2) : '---'}
                            </h3>
                            <p className="text-[10px] text-[#848E9C] mt-1">
                                Initial: ${trader?.initial_balance ? trader.initial_balance.toFixed(2) : '---'}
                            </p>
                        </div>

                        {/* Total PnL */}
                        <div className="bg-[#1E2329] p-3 rounded-xl border border-[#2B3139] relative overflow-hidden">
                            <div className="absolute top-0 right-0 p-2 opacity-10">
                                <TrendingUp className="w-10 h-10 text-[#EAECEF]" />
                            </div>
                            <p className="text-[#848E9C] text-[10px] font-medium uppercase mb-1">Total PnL</p>
                            <h3 className={`text-xl font-bold font-mono tracking-tight ${pnlColor}`}>
                                {pnlSign}${trader?.stats.total_pnl ? trader.stats.total_pnl.toFixed(2) : '---'}
                            </h3>
                            <p className={`text-[10px] mt-1 font-medium ${roiColor}`}>
                                {pnlSign}{roi.toFixed(2)}% ROI
                            </p>
                            <p className="text-[10px] text-[#848E9C] mt-0.5">
                                Fees: ${trader?.stats.total_fees ? trader.stats.total_fees.toFixed(2) : '0.00'}
                            </p>
                        </div>

                        {/* Win Rate */}
                        <div className="bg-[#1E2329] p-3 rounded-xl border border-[#2B3139] relative overflow-hidden">
                            <div className="absolute top-0 right-0 p-2 opacity-10">
                                <CheckCircle2 className="w-10 h-10 text-[#EAECEF]" />
                            </div>
                            <p className="text-[#848E9C] text-[10px] font-medium uppercase mb-1">Win Rate</p>
                            <h3 className="text-xl font-bold font-mono tracking-tight text-[#F0B90B]">
                                {trader?.stats.win_rate !== undefined ? trader.stats.win_rate.toFixed(1) : '---'}%
                            </h3>
                            <p className="text-[10px] text-[#848E9C] mt-1">
                                {trader?.stats.total_trades || 0} Trades
                            </p>
                        </div>

                        {/* Active Position Summary */}
                        <div className="bg-[#1E2329] p-3 rounded-xl border border-[#2B3139] col-span-2 relative overflow-hidden">
                            <p className="text-[#848E9C] text-[10px] font-medium uppercase mb-2">Active Position</p>
                            
                            {trader?.positions && Object.keys(trader.positions).length > 0 ? (
                                Object.entries(trader.positions).map(([symbol, pos]) => {
                                    const posPnlColor = pos.unrealized_pnl >= 0 ? 'text-[#0ECB81]' : 'text-[#F6465D]';
                                    const posPnlSign = pos.unrealized_pnl >= 0 ? '+' : '';
                                    const leverage = pos.leverage || 1;
                                    const roiVal = pos.pnl_pct; 

                                    return (
                                        <div key={symbol} className="flex flex-col gap-2">
                                            <div className="flex items-center justify-between border-b border-[#2B3139] pb-1">
                                                <div className="flex items-center gap-2">
                                                    <span className={`px-1.5 py-0.5 text-[10px] font-bold rounded ${pos.side === 'long' ? 'bg-[#0ECB81]/20 text-[#0ECB81]' : 'bg-[#F6465D]/20 text-[#F6465D]'}`}>
                                                        {pos.side === 'long' ? 'LONG' : 'SHORT'}
                                                    </span>
                                                    <span className="font-bold text-sm">{symbol}</span>
                                                    <span className="text-[10px] text-[#848E9C] bg-[#2B3139] px-1 rounded">
                                                        {leverage}X
                                                    </span>
                                                </div>
                                                <div className={`text-sm font-bold font-mono ${posPnlColor}`}>
                                                    {posPnlSign}{pos.unrealized_pnl.toFixed(2)} ({posPnlSign}{roiVal.toFixed(2)}%)
                                                </div>
                                            </div>
                                            <div className="grid grid-cols-4 gap-2 text-[10px]">
                                                <div>
                                                    <p className="text-[#848E9C]">Entry</p>
                                                    <p className="font-mono text-[#EAECEF]">{pos.entry_price.toFixed(2)}</p>
                                                </div>
                                                <div>
                                                    <p className="text-[#848E9C]">Mark</p>
                                                    <p className="font-mono text-[#EAECEF]">{pos.mark_price ? pos.mark_price.toFixed(2) : '-'}</p>
                                                </div>
                                                <div>
                                                    <p className="text-[#848E9C]">SL</p>
                                                    <p className="font-mono text-[#F6465D]">{pos.sl_price ? pos.sl_price.toFixed(2) : '-'}</p>
                                                </div>
                                                <div>
                                                    <p className="text-[#848E9C]">TP</p>
                                                    <p className="font-mono text-[#0ECB81]">{pos.tp_price ? pos.tp_price.toFixed(2) : '-'}</p>
                                                </div>
                                            </div>
                                        </div>
                                    );
                                })
                            ) : (
                                <div className="flex items-center justify-center h-16 text-[#848E9C] gap-2">
                                    <Shield className="w-5 h-5 opacity-50" />
                                    <span className="text-xs">No Active Position</span>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Trade History & Strategy Logs Grid */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                        {/* Recent Trades */}
                        <div className="bg-[#1E2329] rounded-xl border border-[#2B3139] overflow-hidden h-[300px] flex flex-col">
                            <div className="p-3 border-b border-[#2B3139] flex items-center justify-between bg-[#1E2329]">
                                <h2 className="font-semibold text-sm flex items-center gap-2">
                                    <History className="w-4 h-4 text-[#F0B90B]" />
                                    Recent Trades
                                </h2>
                            </div>
                            <div className="overflow-y-auto flex-1">
                                <table className="w-full text-xs text-left">
                                    <thead className="bg-[#2B3139]/50 text-[#848E9C] sticky top-0">
                                        <tr>
                                            <th className="px-3 py-2 font-medium">Time</th>
                                            <th className="px-3 py-2 font-medium">Side</th>
                                            <th className="px-3 py-2 font-medium text-right">Price</th>
                                            <th className="px-3 py-2 font-medium text-right">PnL</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-[#2B3139]">
                                        {trader?.trade_history && trader.trade_history.length > 0 ? (
                                            trader.trade_history.slice(0, 50).map((trade) => {
                                                const isBuy = trade.side === 'buy';
                                                const pnl = trade.realized_pnl || 0;
                                                const tradePnlColor = pnl >= 0 ? 'text-[#0ECB81]' : 'text-[#F6465D]';
                                                return (
                                                    <tr key={trade.id} className="hover:bg-[#2B3139]/30 transition-colors">
                                                        <td className="px-3 py-2 font-mono text-[#EAECEF]">
                                                            {trade.datetime.split('T')[0].slice(5)} <span className="text-[#848E9C]">{trade.datetime.split('T')[1].slice(0, 5)}</span>
                                                        </td>
                                                        <td className="px-3 py-2">
                                                            <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${isBuy ? 'bg-[#0ECB81]/20 text-[#0ECB81]' : 'bg-[#F6465D]/20 text-[#F6465D]'}`}>
                                                                {isBuy ? 'BUY' : 'SELL'}
                                                            </span>
                                                        </td>
                                                        <td className="px-3 py-2 text-right font-mono text-[#EAECEF]">
                                                            {trade.price.toLocaleString()}
                                                        </td>
                                                        <td className={`px-3 py-2 text-right font-mono font-bold ${tradePnlColor}`}>
                                                            {pnl !== 0 ? pnl.toFixed(2) : '-'}
                                                        </td>
                                                    </tr>
                                                );
                                            })
                                        ) : (
                                            <tr>
                                                <td colSpan={4} className="px-3 py-8 text-center text-[#848E9C]">
                                                    No trades yet
                                                </td>
                                            </tr>
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </div>

                        {/* Strategy Logs */}
                        <div className="bg-[#1E2329] rounded-xl border border-[#2B3139] overflow-hidden h-[300px] flex flex-col">
                            <div className="p-3 border-b border-[#2B3139] flex items-center justify-between bg-[#1E2329]">
                                <h3 className="font-semibold text-sm flex items-center gap-2 text-[#EAECEF]">
                                    <Clock className="w-4 h-4 text-[#F0B90B]" />
                                    Strategy Signals
                                </h3>
                                <button 
                                    onClick={() => setShowAllStrategies(!showAllStrategies)}
                                    className="text-[10px] text-[#848E9C] hover:text-[#F0B90B]"
                                >
                                    {showAllStrategies ? 'Show Recent (7)' : 'Show All'}
                                </button>
                            </div>
                            <div className="overflow-y-auto flex-1">
                                <table className="w-full text-xs text-left">
                                    <thead className="bg-[#2B3139]/50 text-[#848E9C] sticky top-0">
                                        <tr>
                                            <th className="px-3 py-2 font-medium">Time</th>
                                            <th className="px-3 py-2 font-medium">Signal</th>
                                            <th className="px-3 py-2 font-medium">Prob.</th>
                                            <th className="px-3 py-2 font-medium">RSI</th>
                                            <th className="px-3 py-2 font-medium">MACD</th>
                                            <th className="px-3 py-2 font-medium text-right">Price</th>
                                            <th className="px-3 py-2 font-medium">Note</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-[#2B3139]">
                                        {strategyLogs.length === 0 ? (
                                            <tr>
                                                <td colSpan={7} className="px-3 py-8 text-center text-[#848E9C]">Waiting for signals...</td>
                                            </tr>
                                        ) : (
                                            (showAllStrategies ? strategyLogs : strategyLogs.slice(0, 7)).map((log) => {
                                                const isUp = log.direction === 'UP';
                                                return (
                                                    <tr key={log.id} className="hover:bg-[#2B3139]/30 border-b border-[#2B3139]/50">
                                                        <td className="px-3 py-2 font-mono text-[#848E9C]">
                                                            {log.timeString.split(' ')[1]}
                                                        </td>
                                                        <td className="px-3 py-2">
                                                            <div className={`flex items-center gap-1 ${isUp ? 'text-[#0ECB81]' : 'text-[#F6465D]'}`}>
                                                                {isUp ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />}
                                                                <span className="font-bold">{isUp ? 'BUY' : 'SELL'}</span>
                                                                {log.isHighConf && <span className="ml-1 text-[8px] bg-[#F0B90B] text-black px-1 rounded">HC</span>}
                                                            </div>
                                                        </td>
                                                        <td className="px-3 py-2 font-mono text-[#EAECEF]">
                                                            {log.probability ? `${(log.probability * 100).toFixed(1)}%` : '-'}
                                                        </td>
                                                        <td className={`px-3 py-2 font-mono ${log.rsi && (log.rsi > 70 || log.rsi < 30) ? 'text-[#F0B90B]' : 'text-[#EAECEF]'}`}>
                                                            {log.rsi ? log.rsi.toFixed(1) : '-'}
                                                        </td>
                                                        <td className={`px-3 py-2 font-mono ${log.macd_hist && log.macd_hist > 0 ? 'text-[#0ECB81]' : (log.macd_hist && log.macd_hist < 0 ? 'text-[#F6465D]' : 'text-[#EAECEF]')}`}>
                                                            {log.macd_hist ? log.macd_hist.toFixed(1) : '-'}
                                                        </td>
                                                        <td className="px-3 py-2 text-right font-mono text-[#EAECEF]">
                                                            {log.entryPrice.toFixed(0)}
                                                            {log.ema && <span className="text-[10px] text-[#848E9C] block">EMA:{log.ema.toFixed(0)}</span>}
                                                        </td>
                                                        <td className="px-3 py-2 text-xs text-[#848E9C] max-w-[200px] truncate" title={Array.isArray(log.reasons) ? log.reasons.join(', ') : log.reasons}>
                                                            {Array.isArray(log.reasons) ? log.reasons.join(', ') : log.reasons || '-'}
                                                        </td>
                                                    </tr>
                                                );
                                            })
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Backtest Panel */}
                {showBacktest && (
                    <BacktestPanel 
                        onClose={() => setShowBacktest(false)} 
                        onBacktestResult={handleBacktestResult}
                    />
                )}

                {/* Portfolio Panel */}
                {showPortfolio && (
                    <PortfolioPanel 
                        onClose={() => setShowPortfolio(false)} 
                        onSelectSymbol={(symbol) => {
                            console.log('Selected symbol:', symbol);
                            // Future: Switch current view to this symbol
                            setShowPortfolio(false);
                        }}
                    />
                )}
            </main>
        </div>
    );
}
