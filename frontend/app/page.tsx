'use client';

import React, { useEffect, useState } from 'react';
import { KlineChart } from '@/components/KlineChart';
import { BacktestPanel } from '@/components/BacktestPanel';
import { PaperTradingPanel, PaperStatus } from '@/components/PaperTradingPanel';
import { UTCTimestamp } from 'lightweight-charts';
import { ArrowUp, ArrowDown, Activity, Clock, BarChart2, TrendingUp, ChevronDown, ChevronUp, Beaker, Wallet, Settings } from 'lucide-react';
import axios from 'axios';

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
    const [selectedTimeframe, setSelectedTimeframe] = useState('1h');
    const [strategyLogs, setStrategyLogs] = useState<StrategyLog[]>([]);
    const [showAllStrategies, setShowAllStrategies] = useState(false);
    const [showBacktest, setShowBacktest] = useState(false);
    const [showPaperTrading, setShowPaperTrading] = useState(false);
    const [paperStatus, setPaperStatus] = useState<PaperStatus | null>(null);
    
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

    const fetchData = React.useCallback(async () => {
        try {
            const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
            // In a real scenario, use environment variables for API URL
            const tickerRes = await axios.get(`${API_URL}/api/v1/ticker`);
            // Fetch more history points (1000) to fill the chart better
            const historyRes = await axios.get(`${API_URL}/api/v1/history?limit=1000&timeframe=${selectedTimeframe}`);
            
            // Try fetching prediction, but don't fail entire page if it fails (model might be loading)
            try {
                const predRes = await axios.get(`${API_URL}/api/v1/predict`);
                setPrediction(predRes.data);
                
                // Update Strategy Logs
                const currentTicker = tickerRes.data;
                const currentPred = predRes.data;
                
                if (currentTicker && currentPred && currentPred.predictions) {
                    setStrategyLogs(prevLogs => {
                        const lastLog = prevLogs[0];
                        // Avoid duplicates: check if timestamp is newer than last log
                        // The prediction timestamp comes from the last candle time (updates every minute)
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
                        // Optimized parameters based on sensitivity analysis (Max Return +250.09%)
                        const slPercent = 0.03;  // SL 3.0%
                        const tpPercent = 0.025; // TP 2.5%

                        const newLog: StrategyLog = {
                            id: `${currentPred.timestamp}-${timeHorizon}`,
                            timestamp: currentPred.timestamp,
                            timeString: new Date().toLocaleTimeString(), // Use current local time for display
                            direction: activeSignal.direction,
                            entryPrice: currentPrice,
                            tp: isBullish ? currentPrice * (1 + tpPercent) : currentPrice * (1 - tpPercent),
                            sl: isBullish ? currentPrice * (1 - slPercent) : currentPrice * (1 + slPercent),
                            horizon: timeHorizon,
                            isHighConf: activeSignal.is_high_confidence
                        };

                        return [newLog, ...prevLogs].slice(0, 50); // Keep last 50
                    });
                }
            } catch (e) {
                console.warn("Prediction API not ready yet");
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
            
            // Calculate MAs
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
    }, [selectedTimeframe, calculateSMA]);

    useEffect(() => {
        fetchData();
        fetchBotConfig();
        
        // Setup WebSocket
        const ws = new WebSocket('ws://localhost:8000/ws');
        
        ws.onopen = () => {
            console.log('Connected to WebSocket');
        };

        ws.onmessage = (event) => {
            try {
                const message = JSON.parse(event.data);
                if (message.type === 'ticker_update') {
                    setTicker(message.data);
                    // Note: We could also update the kline chart real-time here
                    // For now, we rely on the periodic fetch for full kline history
                    // but the ticker is instant.
                }
            } catch (e) {
                console.error("WS Parse Error", e);
            }
        };

        const interval = setInterval(fetchData, 5000); // Keep polling for prediction updates
        
        return () => {
            clearInterval(interval);
            ws.close();
        };
    }, [fetchData, fetchBotConfig]); // Re-fetch when dependencies change

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
                    <button 
                        onClick={() => setShowBacktest(true)}
                        className="flex items-center gap-2 px-2 py-1.5 md:px-3 bg-[#2B3139] hover:bg-[#363C45] text-[#EAECEF] text-xs md:text-sm font-medium rounded-lg transition-colors border border-[#474D57]"
                    >
                        <Beaker className="w-3 h-3 md:w-4 md:h-4 text-[#F0B90B]" />
                        <span className="hidden sm:inline">Backtest</span>
                    </button>
                    <a href="/data" className="hidden md:block text-sm text-[#848E9C] hover:text-[#F0B90B] transition-colors">
                        Data Info
                    </a>
                    <a href="/models" className="hidden md:block text-sm text-[#848E9C] hover:text-[#F0B90B] transition-colors">
                        Model Info
                    </a>
                    <div className="flex items-center gap-2 px-2 py-1 md:px-3 md:py-1.5 bg-[#1E2329] rounded-full border border-[#2B3139]">
                        <span className="w-1.5 h-1.5 md:w-2 md:h-2 bg-[#0ECB81] rounded-full animate-pulse"></span>
                        <span className="text-[10px] md:text-xs font-medium text-[#0ECB81] whitespace-nowrap">ONLINE</span>
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
                    {/* Market Sentiment (Moved from bottom) */}
                    <div className="bg-[#1E2329] p-2 rounded-xl border border-[#2B3139]">
                        <p className="text-[#848E9C] text-[10px] mb-1">Fear & Greed</p>
                         <div className="flex justify-between items-center">
                            <span className="text-base font-semibold text-[#F0B90B]">65 (Greed)</span>
                        </div>
                    </div>
                </div>

                {/* Main Content Grid */}
                <div className="grid grid-cols-12 gap-2 pb-2">
                    {/* Left Column - Chart (9/12) */}
                    <div className="col-span-12 lg:col-span-9 space-y-2">
                        {/* Chart Container */}
                        <div className="bg-[#1E2329] rounded-xl border border-[#2B3139] overflow-hidden flex flex-col h-[350px] md:h-[420px]">
                            <div className="p-2 border-b border-[#2B3139] flex justify-between items-center shrink-0">
                                <h2 className="font-semibold flex items-center gap-2 text-sm">
                                    <BarChart2 className="w-4 h-4 text-[#F0B90B]" />
                                    <span className="hidden sm:inline">BTC/USDT Price Action</span>
                                    <span className="sm:hidden">BTC/USDT</span>
                                </h2>
                                <div className="flex gap-2 overflow-x-auto no-scrollbar">
                                    {['1m', '5m', '15m', '30m', '1h', '4h', '1d'].map((tf) => (
                                        <button 
                                            key={tf}
                                            onClick={() => setSelectedTimeframe(tf)}
                                            className={`px-2 py-1 text-[10px] rounded-md transition-colors whitespace-nowrap ${
                                                tf === selectedTimeframe 
                                                ? 'bg-[#2B3139] text-[#F0B90B]' 
                                                : 'text-[#848E9C] hover:bg-[#2B3139] hover:text-[#EAECEF]'
                                            }`}
                                        >
                                            {tf}
                                        </button>
                                    ))}
                                </div>
                            </div>
                            <div className="flex-1 min-h-0 relative">
                                {loading && klineData.length === 0 ? (
                                    <div className="absolute inset-0 flex items-center justify-center bg-[#1E2329] z-10">
                                        <div className="flex flex-col items-center gap-3">
                                            <Activity className="w-8 h-8 text-[#F0B90B] animate-spin" />
                                            <span className="text-[#848E9C] text-sm">Loading Chart Data...</span>
                                        </div>
                                    </div>
                                ) : (
                                    <KlineChart 
                                        data={klineData} 
                                        ma7={ma7Data}
                                        ma25={ma25Data}
                                        ma99={ma99Data}
                                    />
                                )}
                            </div>
                            <div className="px-3 py-1.5 flex gap-4 border-t border-[#2B3139] bg-[#1E2329]">
                                <div className="flex items-center gap-1.5">
                                    <div className="w-2.5 h-0.5 bg-[#F0B90B]"></div>
                                    <span className="text-[10px] text-[#848E9C]">MA(7)</span>
                                </div>
                                <div className="flex items-center gap-1.5">
                                    <div className="w-2.5 h-0.5 bg-[#8739E5]"></div>
                                    <span className="text-[10px] text-[#848E9C]">MA(25)</span>
                                </div>
                                <div className="flex items-center gap-1.5">
                                    <div className="w-2.5 h-0.5 bg-[#2962FF]"></div>
                                    <span className="text-[10px] text-[#848E9C]">MA(99)</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Right Column - Predictions (3/12) */}
                    <div className="col-span-12 lg:col-span-3 flex flex-col h-auto lg:h-[420px]">
                        <h3 className="text-[#848E9C] text-xs font-semibold uppercase tracking-wider mb-2 flex items-center gap-2 shrink-0">
                            <TrendingUp className="w-3 h-3" />
                            AI 趋势预测 (Forecasts)
                        </h3>
                        
                        <div className="flex-1 flex flex-col gap-2 min-h-0">
                            {['10m', '30m', '60m'].map((tf) => {
                                const pred = prediction?.predictions?.[tf];
                                const isBullish = pred?.direction === 'UP';
                                const confidence = pred ? Math.round((pred.confidence || pred.probability) * 100) : 0;
                                const isHighConf = pred?.is_high_confidence;
                                
                                const color = isBullish ? '#0ECB81' : '#F6465D';
                                const Icon = isBullish ? ArrowUp : ArrowDown;

                                let explanation = "正在分析市场数据...";
                                let detailText = "等待信号确认...";
                                
                                if (pred) {
                                    if (isHighConf) {
                                        explanation = isBullish 
                                            ? `强力看涨信号`
                                            : `强力看跌信号`;
                                        detailText = isBullish
                                            ? `模型识别到强烈的上涨动能，建议关注做多机会。`
                                            : `模型识别到明显的下跌趋势，建议注意风险或做空。`;
                                    } else {
                                        explanation = isBullish
                                            ? `震荡偏多`
                                            : `震荡偏空`;
                                        detailText = isBullish
                                            ? `短期趋势略微向上，但信号强度一般，需结合其他指标。`
                                            : `短期走势偏弱，可能存在回调风险，建议观望。`;
                                    }
                                }
                                
                                const timeLabel = tf === '10m' ? '短线 (10分钟)' : tf === '30m' ? '中线 (30分钟)' : '长线 (60分钟)';
                                
                                return (
                                    <div key={tf} className={`flex-1 bg-[#1E2329] rounded-xl border ${isHighConf ? 'border-[#F0B90B] shadow-[0_0_15px_rgba(240,185,11,0.15)]' : 'border-[#2B3139]'} p-3 relative overflow-hidden group hover:border-[#848E9C] transition-colors flex flex-col justify-center`}>
                                        {isHighConf && (
                                            <div className="absolute top-0 right-0 bg-[#F0B90B] text-black text-[10px] font-bold px-2 py-0.5 rounded-bl-lg z-20">
                                                HIGH CONFIDENCE
                                            </div>
                                        )}
                                        <h3 className="text-[#848E9C] text-[10px] font-bold mb-2 flex items-center gap-2 uppercase tracking-wide">
                                            <Clock className="w-3 h-3" />
                                            {timeLabel}
                                        </h3>
                                        
                                        <div className="space-y-2 relative z-10">
                                            {pred ? (
                                                <>
                                                    <div className="flex items-center justify-between">
                                                        <div className="flex items-center gap-3">
                                                            <div className={`p-2 rounded-lg ${isBullish ? 'bg-green-500/10' : 'bg-red-500/10'}`}>
                                                                <Icon className="w-5 h-5" style={{ color }} />
                                                            </div>
                                                            <div>
                                                                <p className="text-lg font-bold leading-tight" style={{ color }}>
                                                                    {isBullish ? '看涨 (BULL)' : '看跌 (BEAR)'}
                                                                </p>
                                                                <p className="text-[10px] text-[#848E9C]">置信度: <span className="text-[#EAECEF] font-medium">{confidence}%</span></p>
                                                            </div>
                                                        </div>
                                                    </div>
                                                    
                                                    <div className="w-full bg-[#2B3139] rounded-full h-1.5">
                                                        <div 
                                                            className="h-1.5 rounded-full transition-all duration-1000" 
                                                            style={{ width: `${confidence}%`, backgroundColor: color }}
                                                        ></div>
                                                    </div>
                                                    
                                                    <div className="flex flex-col gap-0.5">
                                                        <p className={`text-[11px] font-bold ${isHighConf ? 'text-[#F0B90B]' : 'text-[#EAECEF]'}`}>
                                                            {explanation}
                                                        </p>
                                                        <p className="text-[10px] text-[#848E9C] leading-tight">
                                                            {detailText}
                                                        </p>
                                                    </div>
                                                </>
                                            ) : (
                                                <div className="flex flex-col items-center justify-center gap-2 text-[#848E9C] text-xs h-full py-2">
                                                    <Activity className="w-4 h-4 animate-spin" />
                                                    <span className="animate-pulse">正在分析市场数据...</span>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </div>

                    {/* Bottom Row - Strategy Logs (12/12) */}
                    <div className="col-span-12">
                        <div className="bg-[#1E2329] rounded-xl border border-[#2B3139] p-2">
                            <div className="flex justify-between items-center mb-2">
                                <h2 className="font-semibold flex items-center gap-2 text-sm">
                                    <Activity className="w-4 h-4 text-[#F0B90B]" />
                                    AI 交易策略建议 (Strategy Signals)
                                </h2>
                                <div className="flex items-center gap-3">
                                    <div className="flex items-center gap-1.5 px-2 py-1 bg-[#161A25] rounded border border-[#2B3139]">
                                        <div className={`w-2 h-2 rounded-full ${botConfig.confidence_threshold > 0 ? 'bg-[#0ECB81] animate-pulse' : 'bg-gray-500'}`}></div>
                                        <span className="text-[10px] text-[#848E9C]">Bot Active</span>
                                    </div>
                                    <button 
                                        onClick={() => setShowConfig(!showConfig)}
                                        className={`p-1 rounded hover:bg-[#2B3139] transition-colors ${showConfig ? 'text-[#F0B90B] bg-[#2B3139]' : 'text-[#848E9C]'}`}
                                        title="Bot Configuration"
                                    >
                                        <Settings className="w-4 h-4" />
                                    </button>
                                </div>
                            </div>
                            
                            {showConfig && (
                                <div className="mb-4 p-3 bg-[#161A25] rounded-lg border border-[#2B3139] text-xs">
                                    <div className="flex flex-col sm:flex-row sm:items-center gap-4">
                                        <div className="flex items-center gap-2">
                                            <label className="text-[#848E9C]">Confidence Threshold:</label>
                                            <div className="flex items-center gap-2">
                                                <input 
                                                    type="range" 
                                                    min="0.5" 
                                                    max="0.95" 
                                                    step="0.01" 
                                                    value={botConfig.confidence_threshold}
                                                    onChange={(e) => updateBotConfig({...botConfig, confidence_threshold: parseFloat(e.target.value)})}
                                                    className="w-24 accent-[#F0B90B] cursor-pointer"
                                                />
                                                <span className="font-mono text-[#EAECEF] w-10 text-right">{Math.round(botConfig.confidence_threshold * 100)}%</span>
                                            </div>
                                        </div>

                                        <div className="w-px h-4 bg-[#2B3139] hidden sm:block"></div>

                                        <div className="flex items-center gap-2">
                                            <label className="text-[#848E9C]">Feishu Notify:</label>
                                            <div className="flex bg-[#2B3139] rounded p-0.5">
                                                <button
                                                    onClick={() => updateBotConfig({...botConfig, notification_level: 'ALL'})}
                                                    className={`px-3 py-1 rounded text-[10px] transition-colors ${botConfig.notification_level === 'ALL' ? 'bg-[#474D57] text-white font-medium' : 'text-[#848E9C] hover:text-[#EAECEF]'}`}
                                                >
                                                    All Signals
                                                </button>
                                                <button
                                                    onClick={() => updateBotConfig({...botConfig, notification_level: 'HIGH_ONLY'})}
                                                    className={`px-3 py-1 rounded text-[10px] transition-colors ${botConfig.notification_level === 'HIGH_ONLY' ? 'bg-[#F0B90B] text-black font-bold' : 'text-[#848E9C] hover:text-[#EAECEF]'}`}
                                                >
                                                    High Only (&gt;70%)
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            )}
                            
                            {strategyLogs.length === 0 ? (
                                <div className="text-[#848E9C] text-sm flex items-center gap-2 py-6 justify-center bg-[#161A25] rounded-lg border border-[#2B3139] border-dashed">
                                    {loading ? (
                                        <>
                                            <Activity className="w-4 h-4 animate-spin" />
                                            正在分析市场数据以生成策略...
                                        </>
                                    ) : (
                                        <span>暂无交易策略信号</span>
                                    )}
                                </div>
                            ) : (
                                <div className="overflow-x-auto">
                                    <table className="w-full text-xs text-left">
                                        <thead>
                                            <tr className="text-[#848E9C] border-b border-[#2B3139]">
                                                <th className="pb-2 pl-4 font-medium">时间 (Time)</th>
                                                <th className="pb-2 font-medium">方向 (Signal)</th>
                                                <th className="pb-2 font-medium">周期 (Horizon)</th>
                                                <th className="pb-2 font-medium text-right">入场价 (Entry)</th>
                                                <th className="pb-2 font-medium text-right">止盈目标 (Take Profit)</th>
                                                <th className="pb-2 font-medium text-right">止损防守 (Stop Loss)</th>
                                                <th className="pb-2 pr-4 font-medium text-right">状态 (Status)</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-[#2B3139]">
                                            {(showAllStrategies ? strategyLogs : strategyLogs.slice(0, 5)).map((log) => {
                                                // Calculate profit/loss percentages for display
                                                // For LONG: TP > Entry (Positive ROI), SL < Entry (Negative ROI)
                                                // For SHORT: TP < Entry (Positive ROI), SL > Entry (Negative ROI)
                                                
                                                // Fixed percentages from logic above (tp=2%, sl=1%)
                                                // But let's calculate them dynamically in case logic changes
                                                const tpDiff = Math.abs((log.tp - log.entryPrice) / log.entryPrice * 100);
                                                const slDiff = Math.abs((log.sl - log.entryPrice) / log.entryPrice * 100);
                                                
                                                return (
                                                    <tr key={log.id} className="group hover:bg-[#2B3139]/30 transition-colors">
                                                        <td className="py-2 pl-4 text-[#EAECEF] whitespace-nowrap">
                                                            <div className="flex items-center gap-2">
                                                                <Clock className="w-3 h-3 text-[#848E9C]" />
                                                                {log.timeString}
                                                            </div>
                                                        </td>
                                                        <td className="py-2">
                                                            <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                                                log.direction === 'UP' 
                                                                ? 'bg-green-500/10 text-[#0ECB81]' 
                                                                : 'bg-red-500/10 text-[#F6465D]'
                                                            }`}>
                                                                {log.direction === 'UP' ? <ArrowUp className="w-2.5 h-2.5" /> : <ArrowDown className="w-2.5 h-2.5" />}
                                                                {log.direction === 'UP' ? '做多 (LONG)' : '做空 (SHORT)'}
                                                            </span>
                                                            {log.isHighConf && (
                                                                <span className="ml-2 text-[9px] bg-[#F0B90B] text-black px-1 py-0.5 rounded font-bold">HIGH</span>
                                                            )}
                                                        </td>
                                                        <td className="py-2 text-[#EAECEF]">{log.horizon}</td>
                                                        <td className="py-2 text-right font-mono text-[#EAECEF]">${log.entryPrice.toLocaleString()}</td>
                                                        <td className="py-2 text-right">
                                                            <div className="flex flex-col items-end">
                                                                <span className="font-mono text-[#0ECB81]">${log.tp.toLocaleString(undefined, {maximumFractionDigits: 2})}</span>
                                                                <span className="text-[10px] text-[#0ECB81]/80">
                                                                    (ROI +{tpDiff.toFixed(2)}%)
                                                                </span>
                                                            </div>
                                                        </td>
                                                        <td className="py-2 text-right">
                                                            <div className="flex flex-col items-end">
                                                                <span className="font-mono text-[#F6465D]">${log.sl.toLocaleString(undefined, {maximumFractionDigits: 2})}</span>
                                                                <span className="text-[10px] text-[#F6465D]/80">
                                                                    (Loss -{slDiff.toFixed(2)}%)
                                                                </span>
                                                            </div>
                                                        </td>
                                                        <td className="py-2 pr-4 text-right">
                                                            <span className="text-[10px] text-[#848E9C] bg-[#2B3139] px-2 py-0.5 rounded-full">Running</span>
                                                        </td>
                                                    </tr>
                                                );
                                            })}
                                        </tbody>
                                    </table>
                                    
                                    {strategyLogs.length > 5 && (
                                        <div className="mt-2 flex justify-center">
                                            <button 
                                                onClick={() => setShowAllStrategies(!showAllStrategies)}
                                                className="text-xs text-[#848E9C] hover:text-[#F0B90B] flex items-center gap-1 transition-colors"
                                            >
                                                {showAllStrategies ? (
                                                    <>收起 (Show Less) <ChevronUp className="w-3 h-3" /></>
                                                ) : (
                                                    <>查看更多历史策略 ({strategyLogs.length - 5}) <ChevronDown className="w-3 h-3" /></>
                                                )}
                                            </button>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            </main>
            {showBacktest && (
                <BacktestPanel onClose={() => setShowBacktest(false)} />
            )}

            {showPaperTrading && (
                <PaperTradingPanel
                    isOpen={showPaperTrading}
                    onClose={() => setShowPaperTrading(false)}
                    status={paperStatus}
                />
            )}
        </div>
    );
}
