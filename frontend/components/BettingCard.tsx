import React, { useEffect, useState } from 'react';
import { Zap, TrendingUp, TrendingDown, Clock, Activity } from 'lucide-react';
import axios from 'axios';

interface BettingSignal {
    symbol: string;
    label: string; // 10m / 30m
    signal: string; // UP / DOWN
    direction: string; // CALL / PUT
    price: number;
    timestamp: number;
    time: string;
    reason: string;
    indicators: {
        rsi: number;
        macd: number;
    }
}

export const BettingCard: React.FC = () => {
    const [signals, setSignals] = useState<BettingSignal[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [lastUpdate, setLastUpdate] = useState<number | null>(null);

    const fetchSignals = async () => {
        try {
            const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
            // Use the new endpoint
            const response = await axios.get(`${API_URL}/api/v1/market/betting-signals`);
            
            if (response.data && response.data.signals && Array.isArray(response.data.signals)) {
                setSignals(response.data.signals);
                if (response.data.updated_at) {
                    setLastUpdate(response.data.updated_at);
                }
            } else if (Array.isArray(response.data)) {
                // Backward compatibility
                setSignals(response.data);
            } else {
                setSignals([]);
            }
            setError(null);
        } catch (err) {
            console.error('Failed to fetch betting signals:', err);
            setError('Failed to load signals');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchSignals();
        // Refresh every 30 seconds
        const interval = setInterval(fetchSignals, 30 * 1000);
        return () => clearInterval(interval);
    }, []);

    if (loading && signals.length === 0) {
        return (
            <div className="bg-white dark:bg-[#1E2329] rounded-xl border border-gray-200 dark:border-[#2B3139] h-full flex items-center justify-center shadow-md">
                 <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#F0B90B]"></div>
            </div>
        );
    }

    return (
        <div className="bg-white dark:bg-[#1E2329] rounded-xl border border-gray-200 dark:border-[#2B3139] flex flex-col h-full shadow-md">
            <div className="p-4 border-b border-gray-200 dark:border-[#2B3139] flex items-center justify-between bg-white dark:bg-[#1E2329]">
                <h3 className="font-semibold text-sm flex items-center gap-2 text-gray-900 dark:text-[#EAECEF]">
                    <Zap className="w-4 h-4 text-yellow-600 dark:text-[#F0B90B]" />
                    High Confidence Signals (10m/30m)
                </h3>
                <div className="flex flex-col items-end">
                    <span className="text-[10px] text-gray-500 dark:text-[#848E9C]">Auto-Refresh: 30s</span>
                    {lastUpdate && (
                        <span className="text-[10px] text-gray-400 dark:text-[#5E6673]">
                            Last: {new Date(lastUpdate).toLocaleTimeString()}
                        </span>
                    )}
                </div>
            </div>

            <div className="flex-1 overflow-y-auto custom-scrollbar p-2 space-y-2">
                {signals.length === 0 && !loading ? (
                    <div className="flex flex-col items-center justify-center h-full text-gray-500 dark:text-[#848E9C] space-y-2">
                        <Activity className="w-8 h-8 opacity-20" />
                        <span className="text-xs">Waiting for High Confidence Signals...</span>
                        <span className="text-[10px] opacity-60">Scanning BTC/ETH 10m & 30m</span>
                    </div>
                ) : (
                    signals.map((item, index) => {
                        const isCall = item.direction === 'CALL';
                        return (
                            <div key={`${item.timestamp}-${item.symbol}-${index}`} className="bg-gray-50 dark:bg-[#2B3139]/20 border border-gray-200 dark:border-[#2B3139] rounded-lg p-3">
                                <div className="flex justify-between items-start mb-2">
                                    <div className="flex items-center gap-2">
                                        <span className="font-bold text-gray-900 dark:text-[#EAECEF]">{item.symbol}</span>
                                        <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                                            item.label === '10m' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400' : 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400'
                                        }`}>
                                            {item.label}
                                        </span>
                                    </div>
                                    <div className={`flex items-center gap-1 font-bold ${
                                        isCall ? 'text-green-600 dark:text-[#0ECB81]' : 'text-red-600 dark:text-[#F6465D]'
                                    }`}>
                                        {isCall ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
                                        {item.direction}
                                    </div>
                                </div>
                                
                                <div className="flex justify-between items-end">
                                    <div className="space-y-1">
                                        <div className="text-xs text-gray-500 dark:text-[#848E9C] flex items-center gap-1">
                                            <Clock className="w-3 h-3" />
                                            {item.time} | Price: {item.price}
                                        </div>
                                        <div className="text-[10px] text-gray-500 dark:text-[#848E9C]">
                                            RSI: {item.indicators.rsi} | MACD: {item.indicators.macd}
                                        </div>
                                        <div className="text-[10px] text-gray-400 dark:text-gray-500 italic mt-1">
                                            {item.reason}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        );
                    })
                )}
            </div>
        </div>
    );
};
