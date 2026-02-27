import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { ArrowUp, ArrowDown, RefreshCw, AlertCircle, Activity, X } from 'lucide-react';

interface Opportunity {
    symbol: string;
    price: number;
    signal: 'LONG' | 'SHORT' | 'NEUTRAL';
    confidence: 'HIGH' | 'LOW' | 'NONE';
    avg_probability: number;
    strategy_result?: {
        reason?: string;
        trade_params?: {
            leverage?: number;
        }
    };
}

export const PortfolioPanel: React.FC<{ 
    onClose?: () => void;
    onSelectSymbol?: (symbol: string) => void 
}> = ({ onClose, onSelectSymbol }) => {
    const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
    const [loading, setLoading] = useState(false);
    const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
    const [error, setError] = useState('');

    const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

    const scanMarket = async () => {
        setLoading(true);
        setError('');
        try {
            const res = await axios.post(`${API_URL}/api/v1/portfolio/scan`);
            if (res.data.status === 'success') {
                setOpportunities(res.data.opportunities);
                setLastUpdated(new Date());
            }
        } catch (err) {
            console.error("Scan failed:", err);
            setError('Failed to scan market');
        } finally {
            setLoading(false);
        }
    };

    // Auto-scan on mount
    useEffect(() => {
        scanMarket();
        // Refresh every 5 minutes
        const interval = setInterval(scanMarket, 5 * 60 * 1000);
        return () => clearInterval(interval);
    }, []);

    return (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center backdrop-blur-sm p-4">
            <div className="bg-white dark:bg-[#1E2329] rounded-lg shadow-xl w-full max-w-2xl border border-gray-200 dark:border-[#2B3139] flex flex-col max-h-[80vh]">
                <div className="flex justify-between items-center p-4 border-b border-gray-200 dark:border-[#2B3139]">
                    <div className="flex items-center gap-2">
                        <Activity className="w-5 h-5 text-yellow-600 dark:text-[#F0B90B]" />
                        <h2 className="text-lg font-bold text-gray-900 dark:text-[#EAECEF]">Market Scanner</h2>
                    </div>
                    <div className="flex items-center gap-2">
                        <button 
                            onClick={scanMarket} 
                            disabled={loading}
                            className="p-1.5 hover:bg-gray-100 dark:bg-[#2B3139] rounded-md transition-colors"
                            title="Refresh"
                        >
                            <RefreshCw className={`w-4 h-4 text-gray-500 dark:text-[#848E9C] ${loading ? 'animate-spin' : ''}`} />
                        </button>
                        {onClose && (
                            <button 
                                onClick={onClose}
                                className="p-1.5 hover:bg-gray-100 dark:bg-[#2B3139] rounded-md transition-colors text-gray-500 dark:text-[#848E9C] hover:text-gray-900 dark:text-[#EAECEF]"
                            >
                                <X className="w-5 h-5" />
                            </button>
                        )}
                    </div>
                </div>

                <div className="p-4 overflow-y-auto custom-scrollbar flex-1">
                    {error && (
                        <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded text-red-400 text-sm flex items-center gap-2">
                            <AlertCircle className="w-4 h-4" />
                            {error}
                        </div>
                    )}

                    <div className="space-y-3">
                        {opportunities.length === 0 && !loading && !error && (
                            <div className="text-center text-gray-500 dark:text-[#848E9C] py-12 flex flex-col items-center">
                                <Activity className="w-12 h-12 text-[#2B3139] mb-3" />
                                <p>No opportunities found at this moment</p>
                            </div>
                        )}

                        {opportunities.map((opp) => (
                            <div 
                                key={opp.symbol}
                                onClick={() => onSelectSymbol && onSelectSymbol(opp.symbol)}
                                className="bg-gray-100 dark:bg-[#2B3139]/30 p-4 rounded border border-gray-200 dark:border-[#2B3139] hover:border-[#F0B90B]/50 hover:bg-gray-100 dark:bg-gray-300 dark:bg-[#2B3139]/50 cursor-pointer transition-all group"
                            >
                                <div className="flex justify-between items-start mb-2">
                                    <div>
                                        <div className="flex items-baseline gap-2">
                                            <h3 className="font-bold text-gray-900 dark:text-[#EAECEF] text-lg">{opp.symbol}</h3>
                                            <span className="text-sm text-gray-500 dark:text-[#848E9C]">${opp.price.toFixed(2)}</span>
                                        </div>
                                    </div>
                                    <div className={`px-3 py-1 rounded-full text-xs font-bold flex items-center gap-1.5 ${
                                        opp.signal === 'LONG' ? 'bg-green-100 dark:bg-[#0ECB81]/20 text-green-600 dark:text-[#0ECB81] border border-[#0ECB81]/30' : 
                                        opp.signal === 'SHORT' ? 'bg-red-100 dark:bg-[#F6465D]/20 text-red-600 dark:text-[#F6465D] border border-[#F6465D]/30' : 
                                        'bg-[#848E9C]/20 text-gray-500 dark:text-[#848E9C]'
                                    }`}>
                                        {opp.signal === 'LONG' ? <ArrowUp className="w-3.5 h-3.5" /> : 
                                         opp.signal === 'SHORT' ? <ArrowDown className="w-3.5 h-3.5" /> : null}
                                        {opp.signal}
                                    </div>
                                </div>
                                
                                <div className="grid grid-cols-2 gap-4 mt-3">
                                    <div>
                                        <div className="text-[10px] text-gray-500 dark:text-[#848E9C] uppercase tracking-wider mb-1">Probability</div>
                                        <div className="text-sm font-mono text-gray-900 dark:text-[#EAECEF]">{(opp.avg_probability * 100).toFixed(1)}%</div>
                                    </div>
                                    <div>
                                        <div className="text-[10px] text-gray-500 dark:text-[#848E9C] uppercase tracking-wider mb-1">Confidence</div>
                                        <div className={`text-sm font-medium ${
                                            opp.confidence === 'HIGH' ? 'text-yellow-600 dark:text-[#F0B90B]' : 'text-gray-500 dark:text-[#848E9C]'
                                        }`}>
                                            {opp.confidence}
                                        </div>
                                    </div>
                                </div>
                                
                                {opp.strategy_result?.trade_params?.leverage && (
                                    <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-300 dark:border-[#2B3139]/50 flex items-center gap-4">
                                        <div className="text-xs text-gray-500 dark:text-[#848E9C]">
                                            Lev: <span className="text-gray-900 dark:text-[#EAECEF]">{opp.strategy_result.trade_params.leverage}x</span>
                                        </div>
                                        {opp.strategy_result.reason && (
                                            <div className="text-xs text-gray-500 dark:text-[#848E9C] truncate flex-1" title={opp.strategy_result.reason}>
                                                {opp.strategy_result.reason}
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                </div>
                
                <div className="p-3 border-t border-gray-200 dark:border-[#2B3139] bg-[#161A25] rounded-b-lg flex justify-between items-center text-xs text-gray-500 dark:text-[#848E9C]">
                    <div>
                        {lastUpdated ? `Last updated: ${lastUpdated.toLocaleTimeString()}` : 'Waiting for scan...'}
                    </div>
                    <div>
                        Auto-refresh: 5m
                    </div>
                </div>
            </div>
        </div>
    );
};