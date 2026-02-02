'use client';

import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { ArrowLeft, Brain, CheckCircle, Clock, Database, TrendingUp } from 'lucide-react';
import Link from 'next/link';

interface ModelMetric {
    accuracy: number;
    precision: number;
    recall: number;
    f1_score: number;
    training_date: string;
    sample_size: number;
    features: string[];
}

interface ModelMetrics {
    [key: string]: ModelMetric;
}

export default function ModelInfo() {
    const [metrics, setMetrics] = useState<ModelMetrics | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

    useEffect(() => {
        const fetchMetrics = async () => {
            try {
                const res = await axios.get(`${API_URL}/api/v1/model-info`);
                setMetrics(res.data);
                setLoading(false);
            } catch (err) {
                console.error("Failed to fetch model metrics:", err);
                setError("Failed to load model information. Please try again later.");
                setLoading(false);
            }
        };

        fetchMetrics();
    }, []);

    if (loading) {
        return (
            <div className="min-h-screen bg-[#0E1117] text-[#FAFAFA] flex items-center justify-center">
                <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-[#F0B90B]"></div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-[#0E1117] text-[#FAFAFA] font-sans">
            {/* Header */}
            <header className="border-b border-[#2B3139] px-4 py-3 md:px-6 md:py-4 flex justify-between items-center bg-[#161A25]">
                <div className="flex items-center gap-3">
                    <Link href="/" className="p-2 hover:bg-[#2B3139] rounded-lg transition-colors">
                        <ArrowLeft className="w-5 h-5 text-[#848E9C]" />
                    </Link>
                    <div>
                        <h1 className="text-lg md:text-xl font-bold tracking-tight">Model Intelligence</h1>
                        <p className="text-[10px] md:text-xs text-[#848E9C]">AI Performance Metrics</p>
                    </div>
                </div>
                <div className="flex items-center gap-2 px-3 py-1.5 bg-[#1E2329] rounded-full border border-[#2B3139]">
                    <Brain className="w-4 h-4 text-[#F0B90B]" />
                    <span className="text-xs font-medium text-[#EAECEF]">v1.0.0</span>
                </div>
            </header>

            <main className="p-4 md:p-6 max-w-7xl mx-auto">
                {error ? (
                    <div className="bg-[#1E2329] border border-red-500/30 text-red-400 p-6 rounded-xl text-center">
                        {error}
                    </div>
                ) : (
                    <div className="space-y-8">
                        {/* Summary Stats */}
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                            <div className="bg-[#1E2329] p-6 rounded-xl border border-[#2B3139] relative overflow-hidden">
                                <div className="absolute top-0 right-0 p-4 opacity-10">
                                    <Database className="w-24 h-24" />
                                </div>
                                <h3 className="text-[#848E9C] text-sm font-medium mb-2">Training Data</h3>
                                <p className="text-3xl font-bold text-[#EAECEF]">
                                    {metrics && Object.values(metrics)[0]?.sample_size.toLocaleString()}
                                </p>
                                <p className="text-xs text-[#848E9C] mt-2">Historical data points used</p>
                            </div>
                            <div className="bg-[#1E2329] p-6 rounded-xl border border-[#2B3139] relative overflow-hidden">
                                <div className="absolute top-0 right-0 p-4 opacity-10">
                                    <Clock className="w-24 h-24" />
                                </div>
                                <h3 className="text-[#848E9C] text-sm font-medium mb-2">Last Updated</h3>
                                <p className="text-xl font-bold text-[#EAECEF]">
                                    {metrics && new Date(Object.values(metrics)[0]?.training_date).toLocaleString()}
                                </p>
                                <p className="text-xs text-[#848E9C] mt-2">Model training timestamp</p>
                            </div>
                            <div className="bg-[#1E2329] p-6 rounded-xl border border-[#2B3139] relative overflow-hidden">
                                <div className="absolute top-0 right-0 p-4 opacity-10">
                                    <TrendingUp className="w-24 h-24" />
                                </div>
                                <h3 className="text-[#848E9C] text-sm font-medium mb-2">Active Models</h3>
                                <p className="text-3xl font-bold text-[#EAECEF]">
                                    {metrics ? Object.keys(metrics).length : 0}
                                </p>
                                <p className="text-xs text-[#848E9C] mt-2">Time horizons monitored</p>
                            </div>
                        </div>

                        {/* Model Details */}
                        <h2 className="text-xl font-bold flex items-center gap-2 mt-8">
                            <CheckCircle className="w-5 h-5 text-[#0ECB81]" />
                            Performance by Horizon
                        </h2>
                        
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                            {metrics && Object.entries(metrics).map(([horizon, data]) => (
                                <div key={horizon} className="bg-[#1E2329] rounded-xl border border-[#2B3139] overflow-hidden">
                                    <div className="bg-[#2B3139] px-6 py-4 border-b border-[#2B3139] flex justify-between items-center">
                                        <h3 className="font-bold text-lg">{horizon} Prediction Model</h3>
                                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                                            data.accuracy > 0.55 ? 'bg-[#0ECB81]/20 text-[#0ECB81]' : 'bg-[#F0B90B]/20 text-[#F0B90B]'
                                        }`}>
                                            {(data.accuracy * 100).toFixed(1)}% Acc
                                        </span>
                                    </div>
                                    <div className="p-6 space-y-4">
                                        <div className="flex justify-between items-center">
                                            <span className="text-[#848E9C] text-sm">Accuracy</span>
                                            <div className="flex items-center gap-2">
                                                <div className="w-24 h-2 bg-[#2B3139] rounded-full overflow-hidden">
                                                    <div 
                                                        className="h-full bg-[#F0B90B] rounded-full"
                                                        style={{ width: `${data.accuracy * 100}%` }}
                                                    ></div>
                                                </div>
                                                <span className="text-sm font-mono">{(data.accuracy * 100).toFixed(1)}%</span>
                                            </div>
                                        </div>
                                        <div className="flex justify-between items-center">
                                            <span className="text-[#848E9C] text-sm">Precision</span>
                                            <div className="flex items-center gap-2">
                                                <div className="w-24 h-2 bg-[#2B3139] rounded-full overflow-hidden">
                                                    <div 
                                                        className="h-full bg-[#0ECB81] rounded-full"
                                                        style={{ width: `${data.precision * 100}%` }}
                                                    ></div>
                                                </div>
                                                <span className="text-sm font-mono">{(data.precision * 100).toFixed(1)}%</span>
                                            </div>
                                        </div>
                                        <div className="flex justify-between items-center">
                                            <span className="text-[#848E9C] text-sm">Recall</span>
                                            <div className="flex items-center gap-2">
                                                <div className="w-24 h-2 bg-[#2B3139] rounded-full overflow-hidden">
                                                    <div 
                                                        className="h-full bg-[#3B82F6] rounded-full"
                                                        style={{ width: `${data.recall * 100}%` }}
                                                    ></div>
                                                </div>
                                                <span className="text-sm font-mono">{(data.recall * 100).toFixed(1)}%</span>
                                            </div>
                                        </div>
                                        <div className="flex justify-between items-center">
                                            <span className="text-[#848E9C] text-sm">F1 Score</span>
                                            <span className="text-sm font-mono text-[#EAECEF]">{(data.f1_score * 100).toFixed(1)}%</span>
                                        </div>
                                        
                                        <div className="pt-4 border-t border-[#2B3139]">
                                            <p className="text-[#848E9C] text-xs mb-2">Input Features</p>
                                            <div className="flex flex-wrap gap-2">
                                                {data.features.map(f => (
                                                    <span key={f} className="text-[10px] px-2 py-1 bg-[#2B3139] rounded text-[#EAECEF]">
                                                        {f}
                                                    </span>
                                                ))}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </main>
        </div>
    );
}