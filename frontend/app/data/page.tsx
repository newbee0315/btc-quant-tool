'use client';

import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { ArrowLeft, Database, HardDrive, Calendar, FileText, Activity } from 'lucide-react';
import Link from 'next/link';

interface DataSummary {
    total_rows: number;
    start_date: string;
    end_date: string;
    file_size_mb: number;
}

export default function DataInfo() {
    const [summary, setSummary] = useState<DataSummary | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const fetchDataSummary = async () => {
            try {
                const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
                const res = await axios.get(`${API_URL}/api/v1/data-summary`);
                if (res.data.error) {
                    setError(res.data.error);
                } else {
                    setSummary(res.data);
                }
                setLoading(false);
            } catch (err) {
                console.error("Failed to fetch data summary:", err);
                setError("Failed to load data information. Please try again later.");
                setLoading(false);
            }
        };

        fetchDataSummary();
    }, []);

    if (loading) {
        return (
            <div className="min-h-screen bg-gray-50 dark:bg-[#0E1117] text-gray-900 dark:text-[#FAFAFA] flex items-center justify-center">
                <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-[#F0B90B]"></div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-gray-50 dark:bg-[#0E1117] text-gray-900 dark:text-[#FAFAFA] font-sans">
            {/* Header */}
            <header className="border-b border-gray-200 dark:border-[#2B3139] px-4 py-3 md:px-6 md:py-4 flex justify-between items-center bg-white dark:bg-[#161A25]">
                <div className="flex items-center gap-3">
                    <Link href="/" className="p-2 hover:bg-gray-100 dark:bg-[#2B3139] rounded-lg transition-colors">
                        <ArrowLeft className="w-5 h-5 text-gray-500 dark:text-[#848E9C]" />
                    </Link>
                    <div>
                        <h1 className="text-lg md:text-xl font-bold tracking-tight">Data Intelligence</h1>
                        <p className="text-[10px] md:text-xs text-gray-500 dark:text-[#848E9C]">Market Data Status</p>
                    </div>
                </div>
                <div className="flex items-center gap-2 px-3 py-1.5 bg-white dark:bg-[#1E2329] rounded-full border border-gray-200 dark:border-[#2B3139]">
                    <Database className="w-4 h-4 text-yellow-600 dark:text-[#F0B90B]" />
                    <span className="text-xs font-medium text-gray-900 dark:text-[#EAECEF]">Live</span>
                </div>
            </header>

            <main className="p-4 md:p-6 max-w-7xl mx-auto">
                {error ? (
                    <div className="bg-white dark:bg-[#1E2329] border border-red-500/30 text-red-400 p-6 rounded-xl text-center">
                        {error}
                    </div>
                ) : (
                    <div className="space-y-8">
                        {/* Summary Cards */}
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                            <div className="bg-white dark:bg-[#1E2329] p-6 rounded-xl border border-gray-200 dark:border-[#2B3139] relative overflow-hidden group hover:border-[#F0B90B]/50 transition-colors">
                                <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                                    <FileText className="w-24 h-24" />
                                </div>
                                <h3 className="text-gray-500 dark:text-[#848E9C] text-sm font-medium mb-2">Total Records</h3>
                                <p className="text-3xl font-bold text-gray-900 dark:text-[#EAECEF]">
                                    {summary?.total_rows.toLocaleString()}
                                </p>
                                <p className="text-xs text-gray-500 dark:text-[#848E9C] mt-2">1-minute candles</p>
                            </div>
                            
                            <div className="bg-white dark:bg-[#1E2329] p-6 rounded-xl border border-gray-200 dark:border-[#2B3139] relative overflow-hidden group hover:border-[#F0B90B]/50 transition-colors">
                                <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                                    <HardDrive className="w-24 h-24" />
                                </div>
                                <h3 className="text-gray-500 dark:text-[#848E9C] text-sm font-medium mb-2">Dataset Size</h3>
                                <p className="text-3xl font-bold text-gray-900 dark:text-[#EAECEF]">
                                    {summary?.file_size_mb} MB
                                </p>
                                <p className="text-xs text-gray-500 dark:text-[#848E9C] mt-2">CSV storage</p>
                            </div>

                            <div className="bg-white dark:bg-[#1E2329] p-6 rounded-xl border border-gray-200 dark:border-[#2B3139] relative overflow-hidden group hover:border-[#F0B90B]/50 transition-colors">
                                <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                                    <Calendar className="w-24 h-24" />
                                </div>
                                <h3 className="text-gray-500 dark:text-[#848E9C] text-sm font-medium mb-2">Data Range</h3>
                                <div className="flex flex-col">
                                    <span className="text-sm font-semibold text-gray-900 dark:text-[#EAECEF]">{summary?.start_date.split(' ')[0]}</span>
                                    <span className="text-xs text-gray-500 dark:text-[#848E9C]">to</span>
                                    <span className="text-sm font-semibold text-gray-900 dark:text-[#EAECEF]">{summary?.end_date.split(' ')[0]}</span>
                                </div>
                            </div>

                            <div className="bg-white dark:bg-[#1E2329] p-6 rounded-xl border border-gray-200 dark:border-[#2B3139] relative overflow-hidden group hover:border-[#F0B90B]/50 transition-colors">
                                <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                                    <Activity className="w-24 h-24" />
                                </div>
                                <h3 className="text-gray-500 dark:text-[#848E9C] text-sm font-medium mb-2">Status</h3>
                                <div className="flex items-center gap-2">
                                    <span className="w-2 h-2 rounded-full bg-[#0ECB81] animate-pulse"></span>
                                    <span className="text-xl font-bold text-green-600 dark:text-[#0ECB81]">Active</span>
                                </div>
                                <p className="text-xs text-gray-500 dark:text-[#848E9C] mt-2">Updating via WebSocket</p>
                            </div>
                        </div>

                        {/* Additional Info Section */}
                        <div className="bg-white dark:bg-[#1E2329] rounded-xl border border-gray-200 dark:border-[#2B3139] p-6">
                            <h2 className="text-lg font-bold mb-4 flex items-center gap-2">
                                <Database className="w-5 h-5 text-yellow-600 dark:text-[#F0B90B]" />
                                Data Specifications
                            </h2>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                                <div>
                                    <h3 className="text-sm font-semibold text-gray-900 dark:text-[#EAECEF] mb-3">Sources</h3>
                                    <ul className="space-y-2 text-sm text-gray-500 dark:text-[#848E9C]">
                                        <li className="flex items-center gap-2">
                                            <span className="w-1.5 h-1.5 rounded-full bg-[#F0B90B]"></span>
                                            Binance (Spot Market)
                                        </li>
                                        <li className="flex items-center gap-2">
                                            <span className="w-1.5 h-1.5 rounded-full bg-[#F0B90B]"></span>
                                            Alternative.me (Fear & Greed Index)
                                        </li>
                                    </ul>
                                </div>
                                <div>
                                    <h3 className="text-sm font-semibold text-gray-900 dark:text-[#EAECEF] mb-3">Features Engineered</h3>
                                    <div className="flex flex-wrap gap-2">
                                        {['RSI', 'MACD', 'Bollinger Bands', 'ATR', 'CCI', 'Volume MA', 'Log Returns', 'Volatility'].map(f => (
                                            <span key={f} className="px-2 py-1 bg-gray-100 dark:bg-[#2B3139] rounded text-xs text-gray-900 dark:text-[#EAECEF]">
                                                {f}
                                            </span>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                )}
            </main>
        </div>
    );
}
