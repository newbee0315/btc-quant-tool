'use client';

import React, { useState, useEffect } from 'react';
import { ArrowLeft, Save, RefreshCw, AlertCircle, Shield, Activity, Zap, History, DollarSign } from 'lucide-react';
import Link from 'next/link';
import axios from 'axios';

interface StrategyConfig {
    ema_period: number;
    rsi_period: number;
    ml_threshold: number;
    leverage: number;
}

interface TraderConfig {
    mode: 'paper' | 'real';
    sl_pct: number;
    tp_pct: number;
    amount_usdt: number;
    total_capital: number;
    risk_per_trade: number;
    api_key: string | null;
    api_secret: string | null;
    proxy_url?: string;
}

interface RealTrade {
    id: string;
    timestamp: number;
    datetime: string;
    side: string;
    price: number;
    amount: number;
    cost: number;
    fee: {
        cost: number;
        currency: string;
    } | null;
}

export default function SettingsPage() {
    const [strategyConfig, setStrategyConfig] = useState<StrategyConfig>({
        ema_period: 200,
        rsi_period: 14,
        ml_threshold: 0.75,
        leverage: 1
    });

    const [traderConfig, setTraderConfig] = useState<TraderConfig>({
        mode: 'paper',
        sl_pct: 0.03,
        tp_pct: 0.025,
        amount_usdt: 20.0,
        total_capital: 1000.0,
        risk_per_trade: 0.02,
        api_key: '',
        api_secret: '',
        proxy_url: ''
    });

    const [realTrades, setRealTrades] = useState<RealTrade[]>([]);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [message, setMessage] = useState<{type: 'success' | 'error', text: string} | null>(null);

    const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

    useEffect(() => {
        fetchConfigs();
    }, []);

    // Poll for trade history if in real mode
    useEffect(() => {
        if (traderConfig.mode === 'real') {
            fetchRealHistory();
            const interval = setInterval(fetchRealHistory, 10000); // Poll every 10s
            return () => clearInterval(interval);
        }
    }, [traderConfig.mode]);

    const fetchConfigs = async () => {
        setLoading(true);
        try {
            const [stratRes, tradeRes] = await Promise.all([
                axios.get(`${API_URL}/api/v1/config/strategy`),
                axios.get(`${API_URL}/api/v1/config/trader`)
            ]);
            setStrategyConfig(stratRes.data);
            setTraderConfig(tradeRes.data);
        } catch (error) {
            console.error("Failed to fetch configs", error);
            setMessage({ type: 'error', text: '获取配置失败' });
        } finally {
            setLoading(false);
        }
    };

    const fetchRealHistory = async () => {
        try {
            const res = await axios.get(`${API_URL}/api/v1/real/history`);
            if (res.data.status === 'success') {
                setRealTrades(res.data.trades);
            }
        } catch (error) {
            console.error("Failed to fetch real history", error);
        }
    };

    const handleSave = async () => {
        setSaving(true);
        setMessage(null);
        try {
            await Promise.all([
                axios.post(`${API_URL}/api/v1/config/strategy`, strategyConfig),
                axios.post(`${API_URL}/api/v1/config/trader`, traderConfig)
            ]);
            setMessage({ type: 'success', text: '设置保存成功' });
            fetchConfigs(); // Re-fetch
        } catch (error) {
            console.error("Failed to save settings", error);
            setMessage({ type: 'error', text: '保存设置失败' });
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="min-h-screen bg-[#0E1117] text-[#EAECEF] p-4 sm:p-8 font-sans">
            <div className="max-w-4xl mx-auto">
                {/* Header */}
                <div className="flex items-center gap-4 mb-8">
                    <Link href="/" className="p-2 hover:bg-[#2B3139] rounded-lg transition-colors">
                        <ArrowLeft className="w-5 h-5 text-[#848E9C]" />
                    </Link>
                    <h1 className="text-2xl font-bold">系统配置 (System Settings)</h1>
                </div>

                {message && (
                    <div className={`mb-6 p-4 rounded-lg flex items-center gap-2 ${message.type === 'success' ? 'bg-green-500/10 text-[#0ECB81] border border-green-500/20' : 'bg-red-500/10 text-[#F6465D] border border-red-500/20'}`}>
                        {message.type === 'success' ? <RefreshCw className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
                        {message.text}
                    </div>
                )}

                {loading ? (
                    <div className="flex justify-center py-12">
                        <Activity className="w-8 h-8 animate-spin text-[#F0B90B]" />
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        {/* Strategy Settings */}
                        <div className="bg-[#1E2329] rounded-xl border border-[#2B3139] p-6">
                            <div className="flex items-center gap-2 mb-6 border-b border-[#2B3139] pb-4">
                                <Zap className="w-5 h-5 text-[#F0B90B]" />
                                <h2 className="text-lg font-semibold">策略参数 (Strategy)</h2>
                            </div>
                            
                            <div className="space-y-4">
                                <div>
                                    <label className="block text-sm text-[#848E9C] mb-1">EMA 周期 (Trend Filter)</label>
                                    <input 
                                        type="number" 
                                        value={strategyConfig.ema_period}
                                        onChange={(e) => setStrategyConfig({...strategyConfig, ema_period: parseInt(e.target.value)})}
                                        className="w-full bg-[#2B3139] border border-[#474D57] rounded p-2 text-sm focus:border-[#F0B90B] outline-none transition-colors"
                                    />
                                    <p className="text-[10px] text-[#848E9C] mt-1">趋势判断均线周期 (默认 200)</p>
                                </div>

                                <div>
                                    <label className="block text-sm text-[#848E9C] mb-1">RSI 周期 (Momentum)</label>
                                    <input 
                                        type="number" 
                                        value={strategyConfig.rsi_period}
                                        onChange={(e) => setStrategyConfig({...strategyConfig, rsi_period: parseInt(e.target.value)})}
                                        className="w-full bg-[#2B3139] border border-[#474D57] rounded p-2 text-sm focus:border-[#F0B90B] outline-none transition-colors"
                                    />
                                    <p className="text-[10px] text-[#848E9C] mt-1">动量指标周期 (默认 14)</p>
                                </div>

                                <div>
                                    <label className="block text-sm text-[#848E9C] mb-1">ML 开单阈值 (Confidence Threshold)</label>
                                    <div className="flex items-center gap-4">
                                        <input 
                                            type="range" 
                                            min="0.5" 
                                            max="0.99" 
                                            step="0.01" 
                                            value={strategyConfig.ml_threshold}
                                            onChange={(e) => setStrategyConfig({...strategyConfig, ml_threshold: parseFloat(e.target.value)})}
                                            className="flex-1 accent-[#F0B90B]"
                                        />
                                        <span className="font-mono w-16 text-right">{(strategyConfig.ml_threshold * 100).toFixed(0)}%</span>
                                    </div>
                                    <p className="text-[10px] text-[#848E9C] mt-1">模型预测概率高于此值才开单</p>
                                </div>

                                <div>
                                    <label className="block text-sm text-[#848E9C] mb-1">合约杠杆 (Leverage)</label>
                                    <input 
                                        type="number" 
                                        min="1"
                                        max="125"
                                        value={strategyConfig.leverage}
                                        onChange={(e) => setStrategyConfig({...strategyConfig, leverage: parseInt(e.target.value)})}
                                        className="w-full bg-[#2B3139] border border-[#474D57] rounded p-2 text-sm focus:border-[#F0B90B] outline-none transition-colors"
                                    />
                                    <p className="text-[10px] text-[#848E9C] mt-1">合约杠杆倍数 (1x - 125x)</p>
                                </div>
                            </div>
                        </div>

                        {/* Trader Settings */}
                        <div className="bg-[#1E2329] rounded-xl border border-[#2B3139] p-6">
                            <div className="flex items-center gap-2 mb-6 border-b border-[#2B3139] pb-4">
                                <Shield className="w-5 h-5 text-[#0ECB81]" />
                                <h2 className="text-lg font-semibold">交易配置 (Trader)</h2>
                            </div>
                            
                            <div className="space-y-4">
                                <div>
                                    <label className="block text-sm text-[#848E9C] mb-1">交易模式 (Mode)</label>
                                    <div className="flex bg-[#2B3139] rounded p-1">
                                        <button
                                            onClick={() => setTraderConfig({...traderConfig, mode: 'paper'})}
                                            className={`flex-1 py-1.5 rounded text-xs font-medium transition-colors ${traderConfig.mode === 'paper' ? 'bg-[#474D57] text-white shadow' : 'text-[#848E9C] hover:text-[#EAECEF]'}`}
                                        >
                                            模拟盘 (Paper)
                                        </button>
                                        <button
                                            onClick={() => setTraderConfig({...traderConfig, mode: 'real'})}
                                            className={`flex-1 py-1.5 rounded text-xs font-medium transition-colors ${traderConfig.mode === 'real' ? 'bg-[#F6465D] text-white shadow' : 'text-[#848E9C] hover:text-[#EAECEF]'}`}
                                        >
                                            实盘 (Real)
                                        </button>
                                    </div>
                                    {traderConfig.mode === 'real' && (
                                        <div className="mt-2 p-2 bg-[#F6465D]/10 border border-[#F6465D]/20 rounded text-[10px] text-[#F6465D] flex items-center gap-2">
                                            <AlertCircle className="w-3 h-3" />
                                            警告：当前为实盘模式，将使用真实资金进行交易！
                                        </div>
                                    )}
                                </div>

                                <div>
                                    <label className="block text-sm text-[#848E9C] mb-1">账户总资金 (Total Capital)</label>
                                    <div className="relative">
                                        <input 
                                            type="number" 
                                            min="100"
                                            step="100"
                                            value={traderConfig.total_capital}
                                            onChange={(e) => setTraderConfig({...traderConfig, total_capital: parseFloat(e.target.value)})}
                                            className="w-full bg-[#2B3139] border border-[#474D57] rounded p-2 pl-8 text-sm focus:border-[#F0B90B] outline-none transition-colors"
                                        />
                                        <DollarSign className="w-4 h-4 text-[#848E9C] absolute left-2 top-2.5" />
                                    </div>
                                    <p className="text-[10px] text-[#848E9C] mt-1">用于计算动态仓位风险的基础资金</p>
                                </div>

                                <div>
                                    <label className="block text-sm text-[#848E9C] mb-1">单笔风险比例 (Risk Per Trade)</label>
                                    <div className="flex items-center gap-4">
                                        <input 
                                            type="range" 
                                            min="0.005" 
                                            max="0.05" 
                                            step="0.005" 
                                            value={traderConfig.risk_per_trade}
                                            onChange={(e) => setTraderConfig({...traderConfig, risk_per_trade: parseFloat(e.target.value)})}
                                            className="flex-1 accent-[#0ECB81]"
                                        />
                                        <span className="font-mono w-16 text-right">{(traderConfig.risk_per_trade * 100).toFixed(1)}%</span>
                                    </div>
                                    <p className="text-[10px] text-[#848E9C] mt-1">每笔交易愿意承担的本金亏损比例 (建议 1%-2%)</p>
                                </div>
                                
                                <div className="p-3 bg-[#2B3139] rounded border border-[#474D57]/50 my-4">
                                    <h4 className="text-xs font-semibold text-[#F0B90B] mb-2 flex items-center gap-1">
                                        <Zap className="w-3 h-3" />
                                        动态仓位说明
                                    </h4>
                                    <p className="text-[10px] text-[#848E9C] leading-relaxed">
                                        程序将根据 <strong>ATR波动率</strong> 自动计算止损距离，并结合 <strong>风险比例</strong> 动态决定开仓数量和杠杆倍数。<br/>
                                        计算公式: 仓位价值 = (总资金 × 风险比例) ÷ 止损距离
                                    </p>
                                </div>

                                <div>
                                    <label className="block text-sm text-[#848E9C] mb-1">备用固定金额 (Fallback Amount)</label>
                                    <div className="relative">
                                        <input 
                                            type="number" 
                                            min="10"
                                            step="1"
                                            value={traderConfig.amount_usdt}
                                            onChange={(e) => setTraderConfig({...traderConfig, amount_usdt: parseFloat(e.target.value)})}
                                            className="w-full bg-[#2B3139] border border-[#474D57] rounded p-2 pl-8 text-sm focus:border-[#F0B90B] outline-none transition-colors"
                                        />
                                        <DollarSign className="w-4 h-4 text-[#848E9C] absolute left-2 top-2.5" />
                                    </div>
                                    <p className="text-[10px] text-[#848E9C] mt-1">仅在动态计算失败时使用的固定开仓金额 (USDT)</p>
                                </div>

                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-sm text-[#848E9C] mb-1">止损比例 (Stop Loss %)</label>
                                        <input 
                                            type="number" 
                                            step="0.1"
                                            value={parseFloat((traderConfig.sl_pct * 100).toFixed(2))}
                                            onChange={(e) => setTraderConfig({...traderConfig, sl_pct: parseFloat(e.target.value) / 100})}
                                            className="w-full bg-[#2B3139] border border-[#474D57] rounded p-2 text-sm focus:border-[#F0B90B] outline-none transition-colors"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-sm text-[#848E9C] mb-1">止盈比例 (Take Profit %)</label>
                                        <input 
                                            type="number" 
                                            step="0.1"
                                            value={parseFloat((traderConfig.tp_pct * 100).toFixed(2))}
                                            onChange={(e) => setTraderConfig({...traderConfig, tp_pct: parseFloat(e.target.value) / 100})}
                                            className="w-full bg-[#2B3139] border border-[#474D57] rounded p-2 text-sm focus:border-[#F0B90B] outline-none transition-colors"
                                        />
                                    </div>
                                </div>

                                <div className="pt-4 border-t border-[#2B3139]">
                                    <h3 className="text-sm font-medium mb-3 text-[#EAECEF]">Binance API 配置</h3>
                                    
                                    <div className="space-y-3">
                                        <div>
                                            <label className="block text-xs text-[#848E9C] mb-1">API Key</label>
                                            <input 
                                                type="text" 
                                                value={traderConfig.api_key || ''}
                                                onChange={(e) => setTraderConfig({...traderConfig, api_key: e.target.value})}
                                                placeholder="Enter API Key"
                                                className="w-full bg-[#2B3139] border border-[#474D57] rounded p-2 text-xs focus:border-[#F0B90B] outline-none transition-colors font-mono"
                                            />
                                        </div>
                                        <div>
                                            <label className="block text-xs text-[#848E9C] mb-1">API Secret</label>
                                            <input 
                                                type="password" 
                                                value={traderConfig.api_secret || ''}
                                                onChange={(e) => setTraderConfig({...traderConfig, api_secret: e.target.value})}
                                                placeholder="Enter API Secret"
                                                className="w-full bg-[#2B3139] border border-[#474D57] rounded p-2 text-xs focus:border-[#F0B90B] outline-none transition-colors font-mono"
                                            />
                                        </div>
                                        <div>
                                            <label className="block text-xs text-[#848E9C] mb-1">HTTP Proxy URL (Optional)</label>
                                            <input 
                                                type="text" 
                                                value={traderConfig.proxy_url || ''}
                                                onChange={(e) => setTraderConfig({...traderConfig, proxy_url: e.target.value})}
                                                placeholder="http://127.0.0.1:7890"
                                                className="w-full bg-[#2B3139] border border-[#474D57] rounded p-2 text-xs focus:border-[#F0B90B] outline-none transition-colors font-mono"
                                            />
                                            <p className="text-[10px] text-[#848E9C] mt-1">
                                                如在中国大陆运行，请填写本地代理地址 (Clash通常为 http://127.0.0.1:7890)
                                            </p>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {/* Real Trading History Section */}
                {traderConfig.mode === 'real' && (
                    <div className="mt-8 bg-[#1E2329] rounded-xl border border-[#2B3139] p-6">
                        <div className="flex items-center justify-between mb-4 border-b border-[#2B3139] pb-4">
                            <div className="flex items-center gap-2">
                                <History className="w-5 h-5 text-[#F0B90B]" />
                                <h2 className="text-lg font-semibold">实盘交易明细 (Real Trade History)</h2>
                            </div>
                            <button 
                                onClick={fetchRealHistory}
                                className="p-1 hover:bg-[#2B3139] rounded text-[#848E9C] hover:text-[#EAECEF] transition-colors"
                            >
                                <RefreshCw className="w-4 h-4" />
                            </button>
                        </div>

                        {realTrades.length === 0 ? (
                            <div className="text-center py-8 text-[#848E9C] text-sm border border-dashed border-[#2B3139] rounded-lg">
                                暂无实盘交易记录
                            </div>
                        ) : (
                            <div className="overflow-x-auto">
                                <table className="w-full text-sm text-left">
                                    <thead>
                                        <tr className="text-[#848E9C] border-b border-[#2B3139]">
                                            <th className="pb-3 pl-4">时间 (Time)</th>
                                            <th className="pb-3">方向 (Side)</th>
                                            <th className="pb-3 text-right">价格 (Price)</th>
                                            <th className="pb-3 text-right">数量 (Amount)</th>
                                            <th className="pb-3 text-right">总额 (Cost)</th>
                                            <th className="pb-3 text-right pr-4">手续费 (Fee)</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-[#2B3139]">
                                        {realTrades.map((trade) => (
                                            <tr key={trade.id} className="group hover:bg-[#2B3139]/30 transition-colors">
                                                <td className="py-3 pl-4 text-[#EAECEF]">
                                                    {new Date(trade.timestamp).toLocaleString()}
                                                </td>
                                                <td className="py-3">
                                                    <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                                                        trade.side === 'buy' 
                                                        ? 'bg-green-500/10 text-[#0ECB81]' 
                                                        : 'bg-red-500/10 text-[#F6465D]'
                                                    }`}>
                                                        {trade.side.toUpperCase()}
                                                    </span>
                                                </td>
                                                <td className="py-3 text-right font-mono text-[#EAECEF]">
                                                    ${trade.price.toLocaleString()}
                                                </td>
                                                <td className="py-3 text-right font-mono text-[#EAECEF]">
                                                    {trade.amount}
                                                </td>
                                                <td className="py-3 text-right font-mono text-[#EAECEF]">
                                                    ${trade.cost.toLocaleString()}
                                                </td>
                                                <td className="py-3 text-right pr-4 text-[#848E9C]">
                                                    {trade.fee ? `${trade.fee.cost} ${trade.fee.currency}` : '-'}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </div>
                )}

                <div className="mt-8 flex justify-end">
                    <button
                        onClick={handleSave}
                        disabled={saving || loading}
                        className="flex items-center gap-2 bg-[#F0B90B] text-black font-bold px-6 py-3 rounded-lg hover:bg-[#F0B90B]/90 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-[#F0B90B]/20"
                    >
                        {saving ? (
                            <>
                                <Activity className="w-4 h-4 animate-spin" />
                                保存中...
                            </>
                        ) : (
                            <>
                                <Save className="w-4 h-4" />
                                保存配置 (Save Configuration)
                            </>
                        )}
                    </button>
                </div>
            </div>
        </div>
    );
}
