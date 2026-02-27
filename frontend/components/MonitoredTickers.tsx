import React, { useEffect, useState, useRef } from 'react';
import axios from 'axios';
import { Activity, TrendingUp, TrendingDown } from 'lucide-react';

interface Ticker24h {
    symbol: string;
    lastPrice: string;
    priceChange: string;
    priceChangePercent: string;
    highPrice: string;
    lowPrice: string;
    volume: string;
    quoteVolume: string;
}

export const MonitoredTickers: React.FC = () => {
    const [tickers, setTickers] = useState<Ticker24h[]>([]);
    const [loading, setLoading] = useState(true);
    const scrollRef = useRef<HTMLDivElement>(null);

    const fetchTickers = async () => {
        try {
            const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
            const res = await axios.get(`${API_URL}/api/v1/tickers/24h`);
            if (Array.isArray(res.data)) {
                // Sort by quote volume desc
                const sorted = res.data.sort((a, b) => parseFloat(b.quoteVolume) - parseFloat(a.quoteVolume));
                setTickers(sorted);
            }
            setLoading(false);
        } catch (error) {
            console.error('Error fetching monitored tickers:', error);
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchTickers();
        const interval = setInterval(fetchTickers, 10000); // Poll every 10s
        return () => clearInterval(interval);
    }, []);

    if (loading) {
        return (
            <div className="h-full bg-white dark:bg-[#1E2329] rounded-xl border border-gray-200 dark:border-[#2B3139] flex items-center justify-center text-gray-500 dark:text-[#848E9C]">
                <span className="animate-pulse flex items-center gap-2">
                    <Activity className="w-4 h-4 animate-spin" />
                    Loading Market Data...
                </span>
            </div>
        );
    }

    return (
        <div className="bg-white dark:bg-[#1E2329] rounded-xl border border-gray-200 dark:border-[#2B3139] p-4 overflow-hidden h-full flex flex-col justify-center relative group">
             <div className="flex items-center justify-between mb-3 px-1">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-[#EAECEF] flex items-center gap-2">
                    <Activity className="w-4 h-4 text-yellow-600 dark:text-[#F0B90B]" />
                    Monitored Markets (24h)
                </h3>
                <div className="flex items-center gap-3">
                    <div className="flex items-center gap-1.5 text-[10px] text-gray-500 dark:text-[#848E9C]">
                        <div className="w-1.5 h-1.5 rounded-full bg-[#0ECB81]"></div>
                        <span>Live</span>
                    </div>
                    <span className="text-xs text-gray-500 dark:text-[#848E9C] bg-gray-100 dark:bg-[#2B3139] px-2 py-0.5 rounded-md font-mono border border-[#363C45]">
                        {tickers.length} Assets
                    </span>
                </div>
            </div>
            
            <div 
                className="flex gap-3 overflow-x-auto pb-2 scrollbar-thin scrollbar-thumb-gray-300 dark:scrollbar-thumb-[#363C45] scrollbar-track-gray-100 dark:scrollbar-track-[#1E2329] hover:scrollbar-thumb-gray-400 dark:hover:scrollbar-thumb-[#474D57] transition-colors"
                ref={scrollRef}
            >
                {tickers.map((ticker) => {
                    const priceChange = parseFloat(ticker.priceChangePercent);
                    const isUp = priceChange >= 0;
                    const displaySymbol = ticker.symbol.replace('USDT', '');
                    const price = parseFloat(ticker.lastPrice);
                    
                    // Format price nicely
                    let formattedPrice = price.toString();
                    if (price < 1) formattedPrice = price.toFixed(4);
                    else if (price < 10) formattedPrice = price.toFixed(3);
                    else formattedPrice = price.toLocaleString();

                    return (
                        <div 
                            key={ticker.symbol} 
                            className="min-w-[140px] p-3 rounded-lg bg-gray-50 dark:bg-[#161A1E] border border-gray-200 dark:border-[#2B3139] hover:border-[#F0B90B]/50 transition-all hover:-translate-y-0.5 flex-shrink-0 cursor-pointer group/card relative overflow-hidden"
                        >
                            {/* Subtle Background Gradient for Gainers/Losers */}
                            <div className={`absolute top-0 right-0 w-16 h-16 bg-gradient-to-bl from-${isUp ? '[#0ECB81]' : '[#F6465D]'} to-transparent opacity-[0.03] group-hover/card:opacity-[0.08] transition-opacity pointer-events-none rounded-tr-lg`}></div>

                            <div className="flex justify-between items-start mb-2">
                                <span className="font-bold text-sm text-gray-900 dark:text-[#EAECEF] tracking-tight">{displaySymbol}</span>
                                <div className={`flex items-center gap-0.5 text-xs font-medium ${isUp ? 'text-green-600 dark:text-[#0ECB81]' : 'text-red-600 dark:text-[#F6465D]'}`}>
                                    {isUp ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                                    {Math.abs(priceChange).toFixed(2)}%
                                </div>
                            </div>
                            
                            <div className="text-lg font-mono font-medium text-gray-900 dark:text-[#EAECEF] mb-2 tracking-tight">
                                ${formattedPrice}
                            </div>
                            
                            <div className="text-[10px] text-gray-500 dark:text-[#848E9C] flex justify-between items-center border-t border-gray-200 dark:border-[#2B3139] pt-2 mt-auto">
                                <span className="uppercase">Vol 24h</span>
                                <span className="font-mono text-gray-900 dark:text-[#EAECEF]">{(parseFloat(ticker.quoteVolume) / 1000000).toFixed(1)}M</span>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
};
