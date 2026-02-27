'use client';

import React, { useState, useEffect, useRef, useMemo } from 'react';
import { createChart, ColorType, IChartApi, ISeriesApi, LineSeries, UTCTimestamp } from 'lightweight-charts';
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ComposedChart } from 'recharts';
import axios from 'axios';
import { Play, TrendingUp, AlertTriangle, CheckCircle, XCircle } from 'lucide-react';

interface BacktestResult {
    initial_capital: number;
    final_capital: number;
    total_fees: number;
    total_return_pct: number;
    total_trades: number;
    win_rate: number;
    start_date?: string;
    end_date?: string;
    duration_days?: number;
    config: {
        horizon: number;
        threshold: number;
        sl: number;
        tp: number;
    };
}

interface Trade {
    entry_time: string;
    entry_price: number;
    exit_time: string;
    exit_price: number;
    reason: string;
    return: number;
    capital_after: number;
}

interface OptimizationResult {
    threshold: number;
    total_return_pct: number;
    total_trades: number;
    win_rate: number;
}

interface SensitivityResult {
    sl: number;
    tp: number;
    total_return_pct: number;
    win_rate: number;
    total_trades: number;
}

export const BacktestPanel: React.FC<{ onClose: () => void, onBacktestResult?: (results: any, trades: any[], equityCurve: any[]) => void, defaultSymbol?: string }> = ({ onClose, onBacktestResult, defaultSymbol = 'BTCUSDT' }) => {
    const [activeTab, setActiveTab] = useState<'backtest' | 'sensitivity'>('backtest');
    const [config, setConfig] = useState({
        symbol: defaultSymbol,
        horizon: 60,
        threshold: 0.7,
        sl: 0.01,
        tp: 0.02,
        days: 30,
        initial_capital: 10000
    });
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState<BacktestResult | null>(null);
    const [trades, setTrades] = useState<Trade[]>([]);
    const [equityCurve, setEquityCurve] = useState<{time: number, value: number}[]>([]);
    const [optResults, setOptResults] = useState<OptimizationResult[]>([]);
    const [optLoading, setOptLoading] = useState(false);
    const [sensitivityResults, setSensitivityResults] = useState<SensitivityResult[]>([]);
    const [sensLoading, setSensLoading] = useState(false);

    const uniqueSLs = useMemo(() => Array.from(new Set(sensitivityResults.map(r => r.sl))).sort((a, b) => a - b), [sensitivityResults]);
    const uniqueTPs = useMemo(() => Array.from(new Set(sensitivityResults.map(r => r.tp))).sort((a, b) => a - b), [sensitivityResults]);
    
    const getSensResult = (sl: number, tp: number) => sensitivityResults.find(r => r.sl === sl && r.tp === tp);
    
    const chartContainerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<IChartApi | null>(null);
    const seriesRef = useRef<ISeriesApi<"Line"> | null>(null);

    const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

    const runSensitivity = async () => {
        setSensLoading(true);
        try {
            const res = await axios.post(`${API_URL}/api/v1/backtest/sensitivity`, {
                symbol: config.symbol,
                horizon: config.horizon,
                threshold: config.threshold,
                days: config.days
            });
            if (res.data.status === 'success') {
                setSensitivityResults(res.data.results);
            }
        } catch (error) {
            console.error("Sensitivity analysis failed:", error);
        } finally {
            setSensLoading(false);
        }
    };

    const runOptimization = async () => {
        setOptLoading(true);
        try {
            const res = await axios.post(`${API_URL}/api/v1/backtest/optimize`, {
                symbol: config.symbol,
                horizon: config.horizon,
                sl: config.sl,
                tp: config.tp,
                days: config.days
            });
            if (res.data.status === 'success') {
                setOptResults(res.data.results);
            }
        } catch (error) {
            console.error("Optimization failed:", error);
        } finally {
            setOptLoading(false);
        }
    };

    const runBacktest = async () => {
        setLoading(true);
        try {
            const res = await axios.post(`${API_URL}/api/v1/backtest/run`, config);
            if (res.data.status === 'success') {
                setResult(res.data.results);
                setTrades(res.data.trades);
                setEquityCurve(res.data.equity_curve);
                if (onBacktestResult) {
                    onBacktestResult(res.data.results, res.data.trades, res.data.equity_curve);
                }
            }
        } catch (error) {
            console.error("Backtest failed:", error);
        } finally {
            setLoading(false);
        }
    };

    // Render Chart when equityCurve changes
    useEffect(() => {
        if (activeTab !== 'backtest') return;
        if (!chartContainerRef.current || equityCurve.length === 0) return;

        // Cleanup existing chart if it exists (though cleanup function should have handled it)
        if (chartRef.current) {
            try {
                chartRef.current.remove();
            } catch (e) {
                // Ignore if already disposed
            }
            chartRef.current = null;
        }

        const chart = createChart(chartContainerRef.current, {
            layout: {
                background: { type: ColorType.Solid, color: '#1E2329' },
                textColor: '#848E9C',
            },
            width: chartContainerRef.current.clientWidth,
            height: 300,
            grid: {
                vertLines: { color: '#2B3139' },
                horzLines: { color: '#2B3139' },
            },
            rightPriceScale: {
                borderColor: '#2B3139',
            },
            timeScale: {
                borderColor: '#2B3139',
                timeVisible: false,
                secondsVisible: false,
            },
        });

        const handleResize = () => {
            if (chartContainerRef.current) {
                chart.applyOptions({ width: chartContainerRef.current.clientWidth });
            }
        };

        const resizeObserver = new ResizeObserver(() => handleResize());
        resizeObserver.observe(chartContainerRef.current);

        const lineSeries = chart.addSeries(LineSeries, {
            color: '#F0B90B',
            lineWidth: 2,
        });

        // Validate and sort data
        if (!equityCurve || equityCurve.length === 0) return;

        // Ensure data is sorted by time and has no duplicates
        const validData = equityCurve
            .filter(item => item && typeof item.time === 'number' && !isNaN(item.time) && typeof item.value === 'number')
            .map((item) => ({
                time: item.time as UTCTimestamp,
                value: item.value
            }))
            .sort((a, b) => (a.time as number) - (b.time as number));

        // Remove duplicates (keep last)
        const uniqueData: { time: UTCTimestamp; value: number }[] = [];
        const seenTimes = new Set<number>();
        
        for (const item of validData) {
            const t = item.time as number;
            if (!seenTimes.has(t)) {
                seenTimes.add(t);
                uniqueData.push(item);
            }
        }

        if (uniqueData.length > 0) {
            try {
                lineSeries.setData(uniqueData);
                chart.timeScale().fitContent();
            } catch (err) {
                console.error("Chart setData failed:", err);
            }
        }

        chartRef.current = chart;

        return () => {
            resizeObserver.disconnect();
            if (chartRef.current) {
                try {
                    chartRef.current.remove();
                } catch (e) {
                    // Ignore
                }
                chartRef.current = null;
            }
        };
    }, [equityCurve]);

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-2 md:p-4">
            <div className="bg-[#161A25] border border-gray-200 dark:border-[#2B3139] rounded-xl w-full max-w-[900px] h-[95vh] md:max-h-[90vh] overflow-hidden flex flex-col shadow-2xl">
                {/* Header */}
                <div className="px-4 py-3 md:px-6 md:py-4 border-b border-gray-200 dark:border-[#2B3139] flex justify-between items-center bg-white dark:bg-[#1E2329] shrink-0">
                    <div className="flex flex-col md:flex-row md:items-center gap-2 md:gap-6">
                        <h2 className="text-lg font-bold flex items-center gap-2 text-gray-900 dark:text-[#EAECEF]">
                            <TrendingUp className="w-5 h-5 text-yellow-600 dark:text-[#F0B90B]" />
                            <span className="hidden sm:inline">策略回测系统</span>
                            <span className="sm:hidden">回测系统</span>
                        </h2>
                        <div className="flex bg-[#161A25] rounded p-1 self-start md:self-auto">
                            <button 
                                onClick={() => setActiveTab('backtest')}
                                className={`px-3 py-1 md:px-4 md:py-1.5 rounded text-xs md:text-sm font-medium transition-colors ${activeTab === 'backtest' ? 'bg-gray-100 dark:bg-[#2B3139] text-gray-900 dark:text-[#EAECEF]' : 'text-gray-500 dark:text-[#848E9C] hover:text-gray-900 dark:text-[#EAECEF]'}`}
                            >
                                回测
                            </button>
                            <button 
                                onClick={() => setActiveTab('sensitivity')}
                                className={`px-3 py-1 md:px-4 md:py-1.5 rounded text-xs md:text-sm font-medium transition-colors ${activeTab === 'sensitivity' ? 'bg-gray-100 dark:bg-[#2B3139] text-gray-900 dark:text-[#EAECEF]' : 'text-gray-500 dark:text-[#848E9C] hover:text-gray-900 dark:text-[#EAECEF]'}`}
                            >
                                敏感度
                            </button>
                        </div>
                    </div>
                    <button onClick={onClose} className="text-gray-500 dark:text-[#848E9C] hover:text-gray-900 dark:text-[#EAECEF]">
                        <XCircle className="w-6 h-6" />
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto p-4 md:p-6 flex flex-col md:flex-row gap-4 md:gap-6 min-h-0">
                    {/* Sidebar - Config */}
                    <div className="w-full md:w-64 shrink-0 space-y-4">
                        <div className="grid grid-cols-2 md:grid-cols-1 gap-4">
                            <div className="space-y-3">
                                <label className="block text-sm text-gray-500 dark:text-[#848E9C]">交易对 (Symbol)</label>
                                <input 
                                    type="text" 
                                    value={config.symbol}
                                    onChange={(e) => setConfig({...config, symbol: e.target.value.toUpperCase()})}
                                    className="w-full bg-gray-100 dark:bg-[#2B3139] border border-gray-300 dark:border-[#474D57] rounded px-3 py-2 text-gray-900 dark:text-[#EAECEF] focus:outline-none focus:border-[#F0B90B] uppercase"
                                />
                            </div>

                            <div className="space-y-3">
                                <label className="block text-sm text-gray-500 dark:text-[#848E9C]">回测天数 (Days)</label>
                                <input 
                                    type="number" 
                                    min="1"
                                    max="365"
                                    value={config.days}
                                    onChange={(e) => setConfig({...config, days: parseInt(e.target.value)})}
                                    className="w-full bg-gray-100 dark:bg-[#2B3139] border border-gray-300 dark:border-[#474D57] rounded px-3 py-2 text-gray-900 dark:text-[#EAECEF] focus:outline-none focus:border-[#F0B90B]"
                                />
                            </div>

                            <div className="space-y-3">
                                <label className="block text-sm text-gray-500 dark:text-[#848E9C]">预测周期 (分钟)</label>
                                <select 
                                    value={config.horizon}
                                    onChange={(e) => setConfig({...config, horizon: parseInt(e.target.value)})}
                                    className="w-full bg-gray-100 dark:bg-[#2B3139] border border-gray-300 dark:border-[#474D57] rounded px-3 py-2 text-gray-900 dark:text-[#EAECEF] focus:outline-none focus:border-[#F0B90B]"
                                >
                                    <option value={10}>10 分钟 (10m)</option>
                                    <option value={30}>30 分钟 (30m)</option>
                                    <option value={60}>60 分钟 (60m)</option>
                                </select>
                            </div>

                            <div className="space-y-3">
                                <label className="block text-sm text-gray-500 dark:text-[#848E9C]">置信度阈值 (0.5-1.0)</label>
                                <input 
                                    type="number" 
                                    step="0.05"
                                    min="0.5"
                                    max="1.0"
                                    value={config.threshold}
                                    onChange={(e) => setConfig({...config, threshold: parseFloat(e.target.value)})}
                                    className="w-full bg-gray-100 dark:bg-[#2B3139] border border-gray-300 dark:border-[#474D57] rounded px-3 py-2 text-gray-900 dark:text-[#EAECEF] focus:outline-none focus:border-[#F0B90B]"
                                />
                            </div>
                        </div>

                        {activeTab === 'backtest' && (
                            <div className="grid grid-cols-2 md:grid-cols-1 gap-4">
                                <div className="space-y-3">
                                    <label className="block text-sm text-gray-500 dark:text-[#848E9C]">初始资金 (USDT)</label>
                                    <input 
                                        type="number" 
                                        value={config.initial_capital}
                                        onChange={(e) => setConfig({...config, initial_capital: parseFloat(e.target.value)})}
                                        className="w-full bg-gray-100 dark:bg-[#2B3139] border border-gray-300 dark:border-[#474D57] rounded px-3 py-2 text-gray-900 dark:text-[#EAECEF] focus:outline-none focus:border-[#F0B90B]"
                                    />
                                </div>
                                <div className="space-y-3">
                                    <label className="block text-sm text-gray-500 dark:text-[#848E9C]">止损比例 (%)</label>
                                    <input 
                                        type="number" 
                                        step="0.005"
                                        value={config.sl}
                                        onChange={(e) => setConfig({...config, sl: parseFloat(e.target.value)})}
                                        className="w-full bg-gray-100 dark:bg-[#2B3139] border border-gray-300 dark:border-[#474D57] rounded px-3 py-2 text-gray-900 dark:text-[#EAECEF] focus:outline-none focus:border-[#F0B90B]"
                                    />
                                </div>

                                <div className="space-y-3">
                                    <label className="block text-sm text-gray-500 dark:text-[#848E9C]">止盈比例 (%)</label>
                                    <input 
                                        type="number" 
                                        step="0.005"
                                        value={config.tp}
                                        onChange={(e) => setConfig({...config, tp: parseFloat(e.target.value)})}
                                        className="w-full bg-gray-100 dark:bg-[#2B3139] border border-gray-300 dark:border-[#474D57] rounded px-3 py-2 text-gray-900 dark:text-[#EAECEF] focus:outline-none focus:border-[#F0B90B]"
                                    />
                                </div>
                            </div>
                        )}

                        <button 
                            onClick={activeTab === 'backtest' ? runBacktest : runSensitivity}
                            disabled={activeTab === 'backtest' ? loading : sensLoading}
                            className="w-full bg-[#F0B90B] hover:bg-[#F0B90B]/90 text-black font-bold py-3 rounded-lg flex items-center justify-center gap-2 transition-colors disabled:opacity-50"
                        >
                            {activeTab === 'backtest' ? (
                                loading ? <div className="animate-spin w-5 h-5 border-2 border-black border-t-transparent rounded-full" /> : <Play className="w-5 h-5" />
                            ) : (
                                sensLoading ? <div className="animate-spin w-5 h-5 border-2 border-black border-t-transparent rounded-full" /> : <Play className="w-5 h-5" />
                            )}
                            {activeTab === 'backtest' ? '开始回测 (Start)' : '运行分析 (Run)'}
                        </button>
                    </div>

                    {/* Main Content - Results */}
                    <div className="flex-1 space-y-6">
                        {activeTab === 'backtest' ? (
                            <>
                                {/* Date Range Info */}
                                {result && result.start_date && (
                                    <div className="bg-white dark:bg-[#1E2329] p-3 rounded-xl border border-gray-200 dark:border-[#2B3139] flex justify-between items-center px-4">
                                        <div className="text-sm text-gray-500 dark:text-[#848E9C]">
                                            回测时间段 (Backtest Period)
                                        </div>
                                        <div className="text-sm font-medium text-gray-900 dark:text-[#EAECEF]">
                                            {new Date(result.start_date!).toLocaleString()} <span className="text-gray-500 dark:text-[#848E9C] mx-2">→</span> {new Date(result.end_date!).toLocaleString()} 
                                            <span className="ml-3 bg-gray-100 dark:bg-[#2B3139] px-2 py-0.5 rounded text-yellow-600 dark:text-[#F0B90B] text-xs">
                                                {result.duration_days} 天 (Days)
                                            </span>
                                        </div>
                                    </div>
                                )}

                                {/* Stats Cards */}
                                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 md:gap-4">
                                    <div className="bg-white dark:bg-[#1E2329] p-3 md:p-4 rounded-xl border border-gray-200 dark:border-[#2B3139]">
                                        <p className="text-gray-500 dark:text-[#848E9C] text-[10px] md:text-xs">初始资金 (Initial Cap)</p>
                                        <p className="text-sm md:text-xl font-bold text-gray-900 dark:text-[#EAECEF]">
                                            {result ? `$${Math.round(result.initial_capital).toLocaleString()}` : '$10,000'}
                                        </p>
                                    </div>
                                    <div className="bg-white dark:bg-[#1E2329] p-3 md:p-4 rounded-xl border border-gray-200 dark:border-[#2B3139]">
                                        <p className="text-gray-500 dark:text-[#848E9C] text-[10px] md:text-xs">最终资金 (Final Cap)</p>
                                        <p className={`text-sm md:text-xl font-bold ${result && result.total_return_pct >= 0 ? 'text-green-600 dark:text-[#0ECB81]' : 'text-red-600 dark:text-[#F6465D]'}`}>
                                            {result ? `$${Math.round(result.final_capital).toLocaleString()}` : '---'}
                                        </p>
                                    </div>
                                    <div className="bg-white dark:bg-[#1E2329] p-3 md:p-4 rounded-xl border border-gray-200 dark:border-[#2B3139]">
                                        <p className="text-gray-500 dark:text-[#848E9C] text-[10px] md:text-xs">总收益率 (Return)</p>
                                        <p className={`text-sm md:text-xl font-bold ${result && result.total_return_pct >= 0 ? 'text-green-600 dark:text-[#0ECB81]' : 'text-red-600 dark:text-[#F6465D]'}`}>
                                            {result ? `${result.total_return_pct.toFixed(2)}%` : '---'}
                                        </p>
                                    </div>
                                    <div className="bg-white dark:bg-[#1E2329] p-3 md:p-4 rounded-xl border border-gray-200 dark:border-[#2B3139]">
                                        <p className="text-gray-500 dark:text-[#848E9C] text-[10px] md:text-xs">交易手续费 (Fees)</p>
                                        <p className="text-sm md:text-xl font-bold text-red-600 dark:text-[#F6465D]">
                                            {result ? `-$${Math.round(result.total_fees).toLocaleString()}` : '---'}
                                        </p>
                                    </div>
                                    <div className="bg-white dark:bg-[#1E2329] p-3 md:p-4 rounded-xl border border-gray-200 dark:border-[#2B3139]">
                                        <p className="text-gray-500 dark:text-[#848E9C] text-[10px] md:text-xs">胜率 (Win Rate)</p>
                                        <p className="text-sm md:text-xl font-bold text-gray-900 dark:text-[#EAECEF]">
                                            {result ? `${(result.win_rate * 100).toFixed(1)}%` : '---'}
                                        </p>
                                    </div>
                                    <div className="bg-white dark:bg-[#1E2329] p-3 md:p-4 rounded-xl border border-gray-200 dark:border-[#2B3139]">
                                        <p className="text-gray-500 dark:text-[#848E9C] text-[10px] md:text-xs">交易次数 (Trades)</p>
                                        <p className="text-sm md:text-xl font-bold text-gray-900 dark:text-[#EAECEF]">
                                            {result ? result.total_trades : '---'}
                                        </p>
                                    </div>
                                </div>

                                {/* Chart */}
                                <div className="bg-white dark:bg-[#1E2329] p-4 rounded-xl border border-gray-200 dark:border-[#2B3139]">
                                    <h3 className="text-sm font-semibold text-gray-500 dark:text-[#848E9C] mb-4">资金权益曲线 (Equity Curve)</h3>
                                    <div ref={chartContainerRef} className="w-full h-[250px] md:h-[300px]" />
                                </div>

                                {/* Threshold Optimization Chart */}
                                <div className="bg-white dark:bg-[#1E2329] p-4 rounded-xl border border-gray-200 dark:border-[#2B3139]">
                                    <div className="flex justify-between items-center mb-4">
                                        <h3 className="text-sm font-semibold text-gray-500 dark:text-[#848E9C]">阈值敏感度分析 (Threshold Analysis)</h3>
                                        <button
                                            onClick={runOptimization}
                                            disabled={optLoading}
                                            className={`px-3 py-1 rounded text-xs font-bold transition-colors ${
                                                optLoading ? 'bg-gray-100 dark:bg-[#2B3139] text-gray-500 dark:text-[#848E9C] cursor-not-allowed' : 'bg-[#F0B90B] text-black hover:bg-[#FCD535]'
                                            }`}
                                        >
                                            {optLoading ? '分析中...' : '开始分析'}
                                        </button>
                                    </div>
                                    
                                    {optResults.length > 0 ? (
                                        <div className="h-[250px] md:h-[300px] w-full">
                                            <ResponsiveContainer width="100%" height="100%">
                                                <ComposedChart data={optResults}>
                                                    <CartesianGrid stroke="#2B3139" strokeDasharray="3 3" vertical={false} />
                                                    <XAxis 
                                                        dataKey="threshold" 
                                                        stroke="#848E9C" 
                                                        tick={{fontSize: 12}} 
                                                    />
                                                    <YAxis 
                                                        yAxisId="left" 
                                                        stroke="#0ECB81" 
                                                        tick={{fontSize: 12}} 
                                                    />
                                                    <YAxis 
                                                        yAxisId="right" 
                                                        orientation="right" 
                                                        stroke="#F0B90B" 
                                                        tick={{fontSize: 12}} 
                                                    />
                                                    <Tooltip 
                                                        contentStyle={{ backgroundColor: '#1E2329', borderColor: '#2B3139', color: '#EAECEF' }}
                                                        itemStyle={{ color: '#EAECEF' }}
                                                        labelStyle={{ color: '#848E9C' }}
                                                    />
                                                    <Legend wrapperStyle={{ paddingTop: '10px' }} />
                                                    <Bar yAxisId="right" dataKey="total_trades" name="交易次数 (Trades)" fill="#F0B90B" barSize={20} opacity={0.3} />
                                                    <Line yAxisId="left" type="monotone" dataKey="total_return_pct" name="收益率 (Return %)" stroke="#0ECB81" strokeWidth={2} dot={{r: 4}} />
                                                </ComposedChart>
                                            </ResponsiveContainer>
                                        </div>
                                    ) : (
                                        <div className="h-[200px] flex items-center justify-center text-gray-500 dark:text-[#848E9C] text-sm">
                                            点击“开始分析”查看阈值对收益的影响
                                        </div>
                                    )}
                                </div>
                            </>
                        ) : (
                            /* Sensitivity Analysis Heatmap */
                            <div className="bg-white dark:bg-[#1E2329] p-4 md:p-6 rounded-xl border border-gray-200 dark:border-[#2B3139] h-full overflow-hidden flex flex-col">
                                <h3 className="text-lg font-bold text-gray-900 dark:text-[#EAECEF] mb-4 md:mb-6 shrink-0">止损止盈敏感度分析 (SL/TP Sensitivity)</h3>
                                
                                {sensitivityResults.length > 0 ? (
                                    <div className="flex-1 overflow-auto">
                                        <div className="mb-2 text-xs text-gray-500 dark:text-[#848E9C] flex flex-wrap items-center gap-2 md:gap-4 sticky left-0">
                                            <span className="flex items-center gap-1"><div className="w-3 h-3 bg-[#0ECB81] opacity-80"></div> 正收益</span>
                                            <span className="flex items-center gap-1"><div className="w-3 h-3 bg-[#F6465D] opacity-80"></div> 负收益</span>
                                            <span className="md:ml-auto w-full md:w-auto mt-1 md:mt-0">纵轴: 止损 (SL) | 横轴: 止盈 (TP)</span>
                                        </div>
                                        <table className="w-full border-collapse text-center">
                                            <thead>
                                                <tr>
                                                    <th className="p-3 text-sm font-bold text-gray-500 dark:text-[#848E9C] bg-[#161A25] border border-gray-200 dark:border-[#2B3139] sticky left-0 z-10 min-w-[100px]">
                                                        <div className="flex flex-col items-center justify-center leading-tight">
                                                            <span>止盈 (TP) →</span>
                                                            <span className="w-full h-px bg-gray-100 dark:bg-[#2B3139] my-1 transform -rotate-12"></span>
                                                            <span>↓ 止损 (SL)</span>
                                                        </div>
                                                    </th>
                                                    {uniqueTPs.map(tp => (
                                                        <th key={tp} className="p-3 text-sm font-bold text-gray-900 dark:text-[#EAECEF] bg-[#161A25] border border-gray-200 dark:border-[#2B3139]">
                                                            {(tp * 100).toFixed(1)}%
                                                        </th>
                                                    ))}
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {uniqueSLs.map(sl => (
                                                    <tr key={sl}>
                                                        <td className="p-3 text-sm font-bold text-gray-900 dark:text-[#EAECEF] bg-[#161A25] border border-gray-200 dark:border-[#2B3139] sticky left-0 z-10">
                                                            {(sl * 100).toFixed(1)}%
                                                        </td>
                                                        {uniqueTPs.map(tp => {
                                                            const res = getSensResult(sl, tp);
                                                            const returnPct = res ? res.total_return_pct : 0;
                                                            let bgColor = '#1E2329';
                                                            if (res) {
                                                                if (returnPct > 0) {
                                                                    const opacity = Math.min(Math.abs(returnPct) / 50, 1) * 0.8 + 0.2;
                                                                    bgColor = `rgba(14, 203, 129, ${opacity})`;
                                                                } else {
                                                                    const opacity = Math.min(Math.abs(returnPct) / 50, 1) * 0.8 + 0.2;
                                                                    bgColor = `rgba(246, 70, 93, ${opacity})`;
                                                                }
                                                            }
                                                            
                                                            return (
                                                                <td 
                                                                    key={`${sl}-${tp}`} 
                                                                    className="p-3 text-center border border-gray-200 dark:border-[#2B3139] transition-colors hover:brightness-110 cursor-pointer relative group"
                                                                    style={{ backgroundColor: bgColor }}
                                                                >
                                                                    <span className="text-sm font-medium text-white shadow-sm block">
                                                                        {returnPct > 0 ? '+' : ''}{returnPct.toFixed(2)}%
                                                                    </span>
                                                                    
                                                                    {/* Custom Tooltip */}
                                                                    <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-48 bg-white dark:bg-[#1E2329] border border-gray-300 dark:border-[#474D57] rounded-lg shadow-xl p-3 z-50 hidden group-hover:block pointer-events-none">
                                                                        <div className="text-xs text-gray-500 dark:text-[#848E9C] mb-1 text-left">
                                                                            SL: {(sl * 100).toFixed(1)}% | TP: {(tp * 100).toFixed(1)}%
                                                                        </div>
                                                                        <div className="flex justify-between text-xs mb-1">
                                                                            <span className="text-gray-500 dark:text-[#848E9C]">胜率 (Win Rate):</span>
                                                                            <span className="text-gray-900 dark:text-[#EAECEF]">{((res?.win_rate || 0) * 100).toFixed(1)}%</span>
                                                                        </div>
                                                                        <div className="flex justify-between text-xs mb-1">
                                                                            <span className="text-gray-500 dark:text-[#848E9C]">交易次数 (Trades):</span>
                                                                            <span className="text-gray-900 dark:text-[#EAECEF]">{res?.total_trades || 0}</span>
                                                                        </div>
                                                                        <div className="flex justify-between text-xs font-bold border-t border-gray-200 dark:border-[#2B3139] pt-1 mt-1">
                                                                            <span className="text-gray-500 dark:text-[#848E9C]">收益率:</span>
                                                                            <span className={returnPct >= 0 ? 'text-green-600 dark:text-[#0ECB81]' : 'text-red-600 dark:text-[#F6465D]'}>
                                                                                {returnPct.toFixed(2)}%
                                                                            </span>
                                                                        </div>
                                                                    </div>
                                                                </td>
                                                            );
                                                        })}
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                ) : (
                                    <div className="flex flex-col items-center justify-center h-[400px] text-gray-500 dark:text-[#848E9C]">
                                        <div className="mb-4 bg-gray-100 dark:bg-[#2B3139] p-4 rounded-full">
                                            <TrendingUp className="w-8 h-8 opacity-50" />
                                        </div>
                                        <p className="text-sm">点击左侧“运行分析”开始网格搜索最优止损止盈参数</p>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};
