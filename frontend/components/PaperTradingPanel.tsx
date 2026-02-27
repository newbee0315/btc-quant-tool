import React, { useState } from 'react';
import axios from 'axios';
import { X, Play, Square, RefreshCw, TrendingUp, TrendingDown, Clock, Wallet, History, Activity } from 'lucide-react';

export interface PaperStatus {
    active: boolean;
    balance: number;
    equity: number;
    positions: Record<string, {
        entry_price: number;
        amount: number;
        side: string;
        timestamp: string;
    }>;
    trade_history: {
        timestamp: string;
        symbol: string;
        action: string;
        price: number;
        amount: number;
        reason?: string;
        pnl?: number;
        balance: number;
    }[];
}

interface PaperTradingPanelProps {
    isOpen: boolean;
    onClose: () => void;
    status: PaperStatus | null;
}

export const PaperTradingPanel: React.FC<PaperTradingPanelProps> = ({ isOpen, onClose, status }) => {
    const [loading, setLoading] = useState(false);

    if (!isOpen) return null;

    const handleAction = async (action: 'start' | 'stop' | 'reset') => {
        setLoading(true);
        const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        try {
            await axios.post(`${API_URL}/api/v1/paper/${action}`);
        } catch (error) {
            console.error(`Failed to ${action} paper trading:`, error);
        } finally {
            setLoading(false);
        }
    };

    const formatMoney = (val: number) => {
        return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val);
    };

    const formatPct = (val: number) => {
        return (val * 100).toFixed(2) + '%';
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-2 md:p-4">
            <div className="bg-white dark:bg-[#1E2329] w-full max-w-[900px] h-[95vh] md:max-h-[90vh] rounded-2xl border border-gray-200 dark:border-[#2B3139] shadow-2xl flex flex-col overflow-hidden animate-in fade-in zoom-in duration-200">
                {/* Header */}
                <div className="flex items-center justify-between p-3 md:p-4 border-b border-gray-200 dark:border-[#2B3139] bg-[#161A25] shrink-0">
                    <div className="flex items-center gap-2 md:gap-3">
                        <div className="bg-[#F0B90B] p-1.5 md:p-2 rounded-lg">
                            <Wallet className="w-4 h-4 md:w-5 md:h-5 text-black" />
                        </div>
                        <div>
                            <h2 className="text-base md:text-lg font-bold text-gray-900 dark:text-[#EAECEF]">Paper Trading <span className="hidden sm:inline">(模拟交易)</span></h2>
                            <p className="text-[10px] md:text-xs text-gray-500 dark:text-[#848E9C]">Real-time Strategy Simulation Environment</p>
                        </div>
                    </div>
                    <div className="flex items-center gap-2 md:gap-4">
                        <div className={`px-2 py-0.5 md:px-3 md:py-1 rounded-full text-[10px] md:text-xs font-bold flex items-center gap-1.5 md:gap-2 ${status?.active ? 'bg-green-100 dark:bg-[#0ECB81]/20 text-green-600 dark:text-[#0ECB81]' : 'bg-red-100 dark:bg-[#F6465D]/20 text-red-600 dark:text-[#F6465D]'}`}>
                            <span className={`w-1.5 h-1.5 md:w-2 md:h-2 rounded-full ${status?.active ? 'bg-[#0ECB81] animate-pulse' : 'bg-[#F6465D]'}`}></span>
                            {status?.active ? 'RUNNING' : 'STOPPED'}
                        </div>
                        <button 
                            onClick={onClose}
                            className="p-1.5 md:p-2 hover:bg-gray-100 dark:bg-[#2B3139] rounded-lg text-gray-500 dark:text-[#848E9C] hover:text-gray-900 dark:text-[#EAECEF] transition-colors"
                        >
                            <X className="w-4 h-4 md:w-5 md:h-5" />
                        </button>
                    </div>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6 min-h-0">
                    {/* Controls & Overview */}
                    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                        <div className="col-span-1 space-y-2">
                            <button
                                onClick={() => handleAction('start')}
                                disabled={loading || status?.active}
                                className="w-full py-3 bg-[#0ECB81] hover:bg-[#0ECB81]/90 disabled:opacity-50 disabled:cursor-not-allowed text-black font-bold rounded-lg flex items-center justify-center gap-2 transition-all"
                            >
                                <Play className="w-4 h-4" /> Start Trading
                            </button>
                            <button
                                onClick={() => handleAction('stop')}
                                disabled={loading || !status?.active}
                                className="w-full py-3 bg-[#F6465D] hover:bg-[#F6465D]/90 disabled:opacity-50 disabled:cursor-not-allowed text-white font-bold rounded-lg flex items-center justify-center gap-2 transition-all"
                            >
                                <Square className="w-4 h-4 fill-current" /> Stop Trading
                            </button>
                            <button
                                onClick={() => handleAction('reset')}
                                disabled={loading}
                                className="w-full py-3 bg-gray-100 dark:bg-[#2B3139] hover:bg-gray-200 dark:hover:bg-[#363C45] disabled:opacity-50 disabled:cursor-not-allowed text-gray-900 dark:text-[#EAECEF] font-bold rounded-lg flex items-center justify-center gap-2 transition-all border border-gray-300 dark:border-[#474D57]"
                            >
                                <RefreshCw className="w-4 h-4" /> Reset Account
                            </button>
                        </div>

                        {/* Stats Cards */}
                        <div className="col-span-1 md:col-span-3 grid grid-cols-1 sm:grid-cols-3 gap-4">
                            <div className="bg-[#161A25] p-4 rounded-xl border border-gray-200 dark:border-[#2B3139] relative overflow-hidden group">
                                <div className="absolute top-0 right-0 p-3 opacity-10 group-hover:opacity-20 transition-opacity">
                                    <Wallet className="w-16 h-16 text-yellow-600 dark:text-[#F0B90B]" />
                                </div>
                                <p className="text-gray-500 dark:text-[#848E9C] text-xs font-medium uppercase tracking-wider mb-1">Total Equity</p>
                                <div className="text-2xl font-bold text-gray-900 dark:text-[#EAECEF] font-mono">
                                    {status ? formatMoney(status.equity) : '---'}
                                </div>
                                <div className="text-xs text-gray-500 dark:text-[#848E9C] mt-1">
                                    Initial: $10,000.00
                                </div>
                            </div>

                            <div className="bg-[#161A25] p-4 rounded-xl border border-gray-200 dark:border-[#2B3139] relative overflow-hidden group">
                                <div className="absolute top-0 right-0 p-3 opacity-10 group-hover:opacity-20 transition-opacity">
                                    <Activity className="w-16 h-16 text-green-600 dark:text-[#0ECB81]" />
                                </div>
                                <p className="text-gray-500 dark:text-[#848E9C] text-xs font-medium uppercase tracking-wider mb-1">Available Balance</p>
                                <div className="text-2xl font-bold text-gray-900 dark:text-[#EAECEF] font-mono">
                                    {status ? formatMoney(status.balance) : '---'}
                                </div>
                                <div className="text-xs text-gray-500 dark:text-[#848E9C] mt-1">
                                    Cash on hand
                                </div>
                            </div>

                            <div className="bg-[#161A25] p-4 rounded-xl border border-gray-200 dark:border-[#2B3139] relative overflow-hidden group">
                                <div className="absolute top-0 right-0 p-3 opacity-10 group-hover:opacity-20 transition-opacity">
                                    <TrendingUp className="w-16 h-16 text-[#2962FF]" />
                                </div>
                                <p className="text-gray-500 dark:text-[#848E9C] text-xs font-medium uppercase tracking-wider mb-1">Total PnL</p>
                                <div className={`text-2xl font-bold font-mono ${status && status.equity >= 10000 ? 'text-green-600 dark:text-[#0ECB81]' : 'text-red-600 dark:text-[#F6465D]'}`}>
                                    {status ? formatMoney(status.equity - 10000) : '---'}
                                </div>
                                <div className={`text-xs mt-1 ${status && status.equity >= 10000 ? 'text-green-600 dark:text-[#0ECB81]' : 'text-red-600 dark:text-[#F6465D]'}`}>
                                    {status ? formatPct((status.equity - 10000) / 10000) : '---'}
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Active Positions */}
                    <div className="space-y-3">
                        <h3 className="text-gray-900 dark:text-[#EAECEF] font-bold flex items-center gap-2">
                            <Activity className="w-4 h-4 text-yellow-600 dark:text-[#F0B90B]" />
                            Active Positions (持仓)
                        </h3>
                        <div className="bg-[#161A25] rounded-xl border border-gray-200 dark:border-[#2B3139] overflow-hidden overflow-x-auto">
                            <table className="w-full text-sm text-left min-w-[600px]">
                                <thead className="bg-white dark:bg-[#1E2329] text-gray-500 dark:text-[#848E9C] font-medium border-b border-gray-200 dark:border-[#2B3139]">
                                    <tr>
                                        <th className="p-3">Symbol</th>
                                        <th className="p-3">Side</th>
                                        <th className="p-3">Entry Price</th>
                                        <th className="p-3">Amount</th>
                                        <th className="p-3">Value</th>
                                        <th className="p-3">Time</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-[#2B3139]">
                                    {status && Object.keys(status.positions).length > 0 ? (
                                        Object.entries(status.positions).map(([symbol, pos]) => (
                                            <tr key={symbol} className="hover:bg-gray-100 dark:bg-gray-300 dark:bg-[#2B3139]/50 transition-colors">
                                                <td className="p-3 font-bold text-gray-900 dark:text-[#EAECEF]">{symbol}</td>
                                                <td className="p-3">
                                                    <span className={`px-2 py-0.5 rounded text-xs font-bold ${pos.side === 'long' ? 'bg-green-100 dark:bg-[#0ECB81]/20 text-green-600 dark:text-[#0ECB81]' : 'bg-red-100 dark:bg-[#F6465D]/20 text-red-600 dark:text-[#F6465D]'}`}>
                                                        {pos.side.toUpperCase()}
                                                    </span>
                                                </td>
                                                <td className="p-3 font-mono text-gray-900 dark:text-[#EAECEF]">${pos.entry_price.toLocaleString()}</td>
                                                <td className="p-3 font-mono text-gray-900 dark:text-[#EAECEF]">{pos.amount.toFixed(6)}</td>
                                                <td className="p-3 font-mono text-gray-900 dark:text-[#EAECEF]">${(pos.amount * pos.entry_price).toLocaleString()}</td>
                                                <td className="p-3 text-gray-500 dark:text-[#848E9C] text-xs">{new Date(pos.timestamp).toLocaleString()}</td>
                                            </tr>
                                        ))
                                    ) : (
                                        <tr>
                                            <td colSpan={6} className="p-8 text-center text-gray-500 dark:text-[#848E9C]">
                                                No active positions
                                            </td>
                                        </tr>
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </div>

                    {/* Trade History */}
                    <div className="space-y-3">
                        <h3 className="text-gray-900 dark:text-[#EAECEF] font-bold flex items-center gap-2">
                            <History className="w-4 h-4 text-yellow-600 dark:text-[#F0B90B]" />
                            Recent Trades (交易历史)
                        </h3>
                        <div className="bg-[#161A25] rounded-xl border border-gray-200 dark:border-[#2B3139] overflow-hidden overflow-x-auto">
                            <table className="w-full text-sm text-left min-w-[600px]">
                                <thead className="bg-white dark:bg-[#1E2329] text-gray-500 dark:text-[#848E9C] font-medium border-b border-gray-200 dark:border-[#2B3139] sticky top-0">
                                    <tr>
                                        <th className="p-3">Time</th>
                                        <th className="p-3">Action</th>
                                        <th className="p-3">Symbol</th>
                                        <th className="p-3">Price</th>
                                        <th className="p-3">Amount</th>
                                        <th className="p-3">PnL</th>
                                        <th className="p-3">Reason</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-[#2B3139]">
                                    {status && status.trade_history.length > 0 ? (
                                        [...status.trade_history].reverse().map((trade, idx) => (
                                            <tr key={idx} className="hover:bg-gray-100 dark:bg-gray-300 dark:bg-[#2B3139]/50 transition-colors">
                                                <td className="p-3 text-gray-500 dark:text-[#848E9C] text-xs">{new Date(trade.timestamp).toLocaleString()}</td>
                                                <td className="p-3">
                                                    <span className={`px-2 py-0.5 rounded text-xs font-bold ${trade.action === 'BUY' ? 'bg-green-100 dark:bg-[#0ECB81]/20 text-green-600 dark:text-[#0ECB81]' : 'bg-red-100 dark:bg-[#F6465D]/20 text-red-600 dark:text-[#F6465D]'}`}>
                                                        {trade.action}
                                                    </span>
                                                </td>
                                                <td className="p-3 font-bold text-gray-900 dark:text-[#EAECEF]">{trade.symbol}</td>
                                                <td className="p-3 font-mono text-gray-900 dark:text-[#EAECEF]">${trade.price.toLocaleString()}</td>
                                                <td className="p-3 font-mono text-gray-900 dark:text-[#EAECEF]">{trade.amount.toFixed(6)}</td>
                                                <td className={`p-3 font-mono font-bold ${trade.pnl && trade.pnl > 0 ? 'text-green-600 dark:text-[#0ECB81]' : trade.pnl && trade.pnl < 0 ? 'text-red-600 dark:text-[#F6465D]' : 'text-gray-500 dark:text-[#848E9C]'}`}>
                                                    {trade.pnl ? formatMoney(trade.pnl) : '-'}
                                                </td>
                                                <td className="p-3 text-gray-900 dark:text-[#EAECEF] text-xs">{trade.reason || '-'}</td>
                                            </tr>
                                        ))
                                    ) : (
                                        <tr>
                                            <td colSpan={7} className="p-8 text-center text-gray-500 dark:text-[#848E9C]">
                                                No trade history
                                            </td>
                                        </tr>
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </div>

                </div>
            </div>
        </div>
    );
};
