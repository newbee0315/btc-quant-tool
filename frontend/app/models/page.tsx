'use client';

import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { ArrowLeft, Brain, CheckCircle, Clock, Database, TrendingUp, Activity } from 'lucide-react';
import Link from 'next/link';

interface MetricStats {
    accuracy: number;
    precision: number;
    recall: number;
    f1: number;
    auc: number;
    model_path: string;
}

interface SymbolData {
    [horizon: string]: MetricStats;
}

interface ModelInfoResponse {
    [key: string]: SymbolData | string;
    training_date: string;
}

interface DataSummary {
    total_rows: number;
    start_date: string;
    end_date: string;
    file_size_mb: number;
    monitored_symbols_count: number;
}

export default function ModelInfo() {
    const [modelData, setModelData] = useState<ModelInfoResponse | null>(null);
    const [dataSummary, setDataSummary] = useState<DataSummary | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

    useEffect(() => {
        const fetchData = async () => {
            try {
                const [modelRes, summaryRes] = await Promise.all([
                    axios.get(`${API_URL}/api/v1/model-info`),
                    axios.get(`${API_URL}/api/v1/data-summary`)
                ]);
                setModelData(modelRes.data);
                setDataSummary(summaryRes.data);
                setLoading(false);
            } catch (err) {
                console.error("Failed to fetch data:", err);
                setError("Failed to load information. Please try again later.");
                setLoading(false);
            }
        };

        fetchData();
    }, []);

    if (loading) {
        return (
            <div className="min-h-screen bg-gray-50 dark:bg-[#0E1117] text-gray-900 dark:text-[#FAFAFA] flex items-center justify-center">
                <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-[#F0B90B]"></div>
            </div>
        );
    }

    const trainingDate = modelData?.training_date;
    const symbols = modelData ? Object.keys(modelData).filter(k => k !== 'training_date') : [];
    const activeModelsCount = symbols.reduce((acc, sym) => {
        const symData = modelData![sym] as SymbolData;
        return acc + Object.keys(symData).length;
    }, 0);

    return (
        <div className="min-h-screen bg-gray-50 dark:bg-[#0E1117] text-gray-900 dark:text-[#FAFAFA] font-sans">
            {/* Header */}
            <header className="border-b border-gray-200 dark:border-[#2B3139] px-4 py-3 md:px-6 md:py-4 flex justify-between items-center bg-white dark:bg-[#161A25]">
                <div className="flex items-center gap-3">
                    <Link href="/" className="p-2 hover:bg-gray-100 dark:bg-[#2B3139] rounded-lg transition-colors">
                        <ArrowLeft className="w-5 h-5 text-gray-500 dark:text-[#848E9C]" />
                    </Link>
                    <div>
                        <h1 className="text-lg md:text-xl font-bold tracking-tight">Model Intelligence</h1>
                        <p className="text-[10px] md:text-xs text-gray-500 dark:text-[#848E9C]">AI Performance Metrics ({symbols.length} Symbols)</p>
                    </div>
                </div>
                <div className="flex items-center gap-2 px-3 py-1.5 bg-white dark:bg-[#1E2329] rounded-full border border-gray-200 dark:border-[#2B3139]">
                    <Brain className="w-4 h-4 text-yellow-600 dark:text-[#F0B90B]" />
                    <span className="text-xs font-medium text-gray-900 dark:text-[#EAECEF]">v2.0.0</span>
                </div>
            </header>

            <main className="p-4 md:p-6 max-w-7xl mx-auto">
                {error ? (
                    <div className="bg-white dark:bg-[#1E2329] border border-red-500/30 text-red-400 p-6 rounded-xl text-center">
                        {error}
                    </div>
                ) : (
                    <div className="space-y-8">
                        {/* Summary Stats */}
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                            <div className="bg-white dark:bg-[#1E2329] p-6 rounded-xl border border-gray-200 dark:border-[#2B3139] relative overflow-hidden">
                                <div className="absolute top-0 right-0 p-4 opacity-10">
                                    <Database className="w-24 h-24" />
                                </div>
                                <h3 className="text-gray-500 dark:text-[#848E9C] text-sm font-medium mb-2">Total Data Points</h3>
                                <p className="text-3xl font-bold text-gray-900 dark:text-[#EAECEF]">
                                    {dataSummary?.total_rows.toLocaleString() || 'N/A'}
                                </p>
                                <p className="text-xs text-gray-500 dark:text-[#848E9C] mt-2">
                                    Across {dataSummary?.monitored_symbols_count || 0} symbols
                                </p>
                            </div>
                            <div className="bg-white dark:bg-[#1E2329] p-6 rounded-xl border border-gray-200 dark:border-[#2B3139] relative overflow-hidden">
                                <div className="absolute top-0 right-0 p-4 opacity-10">
                                    <Clock className="w-24 h-24" />
                                </div>
                                <h3 className="text-gray-500 dark:text-[#848E9C] text-sm font-medium mb-2">Last Training</h3>
                                <p className="text-xl font-bold text-gray-900 dark:text-[#EAECEF]">
                                    {trainingDate ? new Date(trainingDate).toLocaleString() : 'N/A'}
                                </p>
                                <p className="text-xs text-gray-500 dark:text-[#848E9C] mt-2">Model training timestamp</p>
                            </div>
                            <div className="bg-white dark:bg-[#1E2329] p-6 rounded-xl border border-gray-200 dark:border-[#2B3139] relative overflow-hidden">
                                <div className="absolute top-0 right-0 p-4 opacity-10">
                                    <TrendingUp className="w-24 h-24" />
                                </div>
                                <h3 className="text-gray-500 dark:text-[#848E9C] text-sm font-medium mb-2">Active Models</h3>
                                <p className="text-3xl font-bold text-gray-900 dark:text-[#EAECEF]">
                                    {activeModelsCount}
                                </p>
                                <p className="text-xs text-gray-500 dark:text-[#848E9C] mt-2">Total prediction horizons</p>
                            </div>
                        </div>

                        {/* Model Details Grid */}
                        <h2 className="text-xl font-bold flex items-center gap-2 mt-8">
                            <Activity className="w-5 h-5 text-green-600 dark:text-[#0ECB81]" />
                            Performance by Symbol
                        </h2>
                        
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                            {symbols.map((symbol) => {
                                const symData = modelData![symbol] as SymbolData;
                                return (
                                    <div key={symbol} className="bg-white dark:bg-[#1E2329] rounded-xl border border-gray-200 dark:border-[#2B3139] overflow-hidden">
                                        <div className="bg-gray-100 dark:bg-[#2B3139] px-6 py-4 border-b border-gray-200 dark:border-[#2B3139] flex justify-between items-center">
                                            <h3 className="font-bold text-lg">{symbol}</h3>
                                            <span className="text-xs text-gray-500 dark:text-[#848E9C] bg-white dark:bg-[#161A25] px-2 py-1 rounded">
                                                {Object.keys(symData).join(' / ')}
                                            </span>
                                        </div>
                                        <div className="p-4 space-y-4">
                                            {Object.entries(symData).map(([horizon, metrics]) => (
                                                <div key={horizon} className="bg-white dark:bg-[#161A25] p-3 rounded-lg">
                                                    <div className="flex justify-between items-center mb-2">
                                                        <span className="text-sm font-medium text-yellow-600 dark:text-[#F0B90B]">{horizon} Horizon</span>
                                                        <span className={`text-xs px-1.5 py-0.5 rounded ${
                                                            metrics.accuracy > 0.55 ? 'bg-green-100 dark:bg-[#0ECB81]/20 text-green-600 dark:text-[#0ECB81]' : 'bg-[#F0B90B]/20 text-yellow-600 dark:text-[#F0B90B]'
                                                        }`}>
                                                            {(metrics.accuracy * 100).toFixed(1)}% Acc
                                                        </span>
                                                    </div>
                                                    <div className="grid grid-cols-2 gap-2 text-xs">
                                                        <div className="flex justify-between">
                                                            <span className="text-gray-500 dark:text-[#848E9C]">Prec:</span>
                                                            <span>{(metrics.precision * 100).toFixed(1)}%</span>
                                                        </div>
                                                        <div className="flex justify-between">
                                                            <span className="text-gray-500 dark:text-[#848E9C]">Recall:</span>
                                                            <span>{(metrics.recall * 100).toFixed(1)}%</span>
                                                        </div>
                                                        <div className="flex justify-between">
                                                            <span className="text-gray-500 dark:text-[#848E9C]">F1:</span>
                                                            <span>{(metrics.f1 * 100).toFixed(1)}%</span>
                                                        </div>
                                                        <div className="flex justify-between">
                                                            <span className="text-gray-500 dark:text-[#848E9C]">AUC:</span>
                                                            <span>{(metrics.auc * 100).toFixed(1)}%</span>
                                                        </div>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                )}
            </main>
        </div>
    );
}