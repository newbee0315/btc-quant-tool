'use client';

import React, { useEffect, useRef, useState } from 'react';
import { createChart, ColorType, IChartApi, ISeriesApi, UTCTimestamp, CandlestickSeries, LineSeries } from 'lightweight-charts';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

interface KlineData {
    time: UTCTimestamp;
    open: number;
    high: number;
    low: number;
    close: number;
}

interface MAData {
    time: UTCTimestamp;
    value: number;
}

interface Trade {
    id: string;
    timestamp: number;
    datetime: string;
    side: 'buy' | 'sell';
    price: number;
    amount: number;
    cost: number;
    fee: {
        cost: number;
        currency: string;
    };
    realized_pnl: number;
}

interface KlineChartProps {
    data: KlineData[];
    ma7?: MAData[];
    ma25?: MAData[];
    ma99?: MAData[];
    trades?: Trade[];
    className?: string;
    colors?: {
        backgroundColor?: string;
        lineColor?: string;
        textColor?: string;
        areaTopColor?: string;
        areaBottomColor?: string;
    };
}

export const KlineChart: React.FC<KlineChartProps> = ({
    data,
    ma7,
    ma25,
    ma99,
    trades = [],
    className,
    colors = {
        backgroundColor: 'transparent',
        lineColor: '#2962FF',
        textColor: '#848E9C',
        areaTopColor: '#2962FF',
        areaBottomColor: 'rgba(41, 98, 255, 0.28)',
    },
}) => {
    const chartContainerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<IChartApi | null>(null);
    const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
    const markersRef = useRef<any>(null);
    const ma7SeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
    const ma25SeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
    const ma99SeriesRef = useRef<ISeriesApi<"Line"> | null>(null);

    const [tooltipData, setTooltipData] = useState<KlineData | null>(null);

    // Helper to create markers from trades
    const createMarkers = (tradesList: Trade[], candleData: KlineData[]) => {
        if (!candleData || candleData.length === 0) return [];

        // Get candle times (assuming sorted)
        const candleTimes = candleData.map(d => d.time as number);

        return tradesList.map(trade => {
            const tradeTime = trade.timestamp / 1000;
            
            // Find the closest candle time <= tradeTime
            // We want the candle that CONTAINS this trade.
            // Since data is OHLCV for a period starting at 'time', 
            // the trade belongs to the candle where candle.time <= tradeTime < next_candle.time
            // So finding the last candle with time <= tradeTime is correct.
            
            let matchedTime: number | null = null;
            
            // Binary search or simple reverse iteration
            // Since trades are few, reverse iteration is fine
            for (let i = candleTimes.length - 1; i >= 0; i--) {
                if (candleTimes[i] <= tradeTime) {
                    matchedTime = candleTimes[i];
                    break;
                }
            }
            
            if (matchedTime === null) return null; // Trade older than loaded data

            const isBuy = trade.side === 'buy';
            return {
                time: matchedTime as UTCTimestamp,
                position: (isBuy ? 'belowBar' : 'aboveBar') as any,
                color: isBuy ? '#0ECB81' : '#F6465D',
                shape: (isBuy ? 'arrowUp' : 'arrowDown') as any,
                text: isBuy ? 'B' : 'S',
                id: trade.id,
                size: 2, // Slightly larger
            };
        })
        .filter((m): m is NonNullable<typeof m> => m !== null)
        .sort((a, b) => (a.time as number) - (b.time as number));
    };

    // Initialize Chart
    useEffect(() => {
        if (!chartContainerRef.current) return;

        const handleResize = () => {
            if (chartContainerRef.current && chartRef.current) {
                chartRef.current.applyOptions({ 
                    width: chartContainerRef.current.clientWidth,
                    height: chartContainerRef.current.clientHeight
                });
            }
        };

        const chart = createChart(chartContainerRef.current, {
            layout: {
                background: { type: ColorType.Solid, color: colors.backgroundColor },
                textColor: colors.textColor,
            },
            width: chartContainerRef.current.clientWidth,
            height: chartContainerRef.current.clientHeight,
            grid: {
                vertLines: { color: '#2B3139' },
                horzLines: { color: '#2B3139' },
            },
            crosshair: {
                mode: 1, // CrosshairMode.Normal
                vertLine: {
                    width: 1,
                    color: '#848E9C',
                    style: 3, // LineStyle.Dashed
                    labelBackgroundColor: '#848E9C',
                },
                horzLine: {
                    width: 1,
                    color: '#848E9C',
                    style: 3,
                    labelBackgroundColor: '#848E9C',
                },
            },
            rightPriceScale: {
                borderColor: '#2B3139',
            },
            timeScale: {
                borderColor: '#2B3139',
                timeVisible: true,
            },
        });

        chartRef.current = chart;

        const candlestickSeries = chart.addSeries(CandlestickSeries, {
            upColor: '#0ECB81',
            downColor: '#F6465D',
            borderVisible: false,
            wickUpColor: '#0ECB81',
            wickDownColor: '#F6465D',
        });
        
        seriesRef.current = candlestickSeries;
        
        // Add MA Series
        const ma7Series = chart.addSeries(LineSeries, { color: '#F0B90B', lineWidth: 1, crosshairMarkerVisible: false });
        ma7SeriesRef.current = ma7Series;
        
        const ma25Series = chart.addSeries(LineSeries, { color: '#8739E5', lineWidth: 1, crosshairMarkerVisible: false });
        ma25SeriesRef.current = ma25Series;
        
        const ma99Series = chart.addSeries(LineSeries, { color: '#2962FF', lineWidth: 1, crosshairMarkerVisible: false });
        ma99SeriesRef.current = ma99Series;

        // Subscribe to crosshair move
        chart.subscribeCrosshairMove((param) => {
            if (param.time && param.seriesData && seriesRef.current) {
                const data = param.seriesData.get(seriesRef.current) as KlineData | undefined;
                if (data) {
                    setTooltipData(data);
                }
            } else {
                 // On mouse leave or no data, verify if we should reset
                 // For Binance style, we usually keep the last value or current candle.
                 // We will NOT clear it.
            }
        });

        window.addEventListener('resize', handleResize);
        
        const resizeObserver = new ResizeObserver(() => handleResize());
        resizeObserver.observe(chartContainerRef.current);

        return () => {
            window.removeEventListener('resize', handleResize);
            resizeObserver.disconnect();
            chart.remove();
            chartRef.current = null;
        };
    }, []); // Only run once on mount

    // Update Data
    useEffect(() => {
        if (!chartRef.current) return;

        if (seriesRef.current && data.length > 0) {
            // Save current visible logical range to preserve zoom
            const timeScale = chartRef.current.timeScale();
            const logicalRange = timeScale.getVisibleLogicalRange();
            
            seriesRef.current.setData(data);

            // Restore logical range if it exists and we have data
            if (logicalRange) {
                timeScale.setVisibleLogicalRange(logicalRange);
            } else {
                timeScale.fitContent();
            }
            
            // Set initial tooltip data to latest candle if not set
            if (!tooltipData) {
                setTooltipData(data[data.length - 1]);
            }
        }
        
        if (ma7SeriesRef.current && ma7 && ma7.length > 0) {
            ma7SeriesRef.current.setData(ma7);
        }
        if (ma25SeriesRef.current && ma25 && ma25.length > 0) {
            ma25SeriesRef.current.setData(ma25);
        }
        if (ma99SeriesRef.current && ma99 && ma99.length > 0) {
            ma99SeriesRef.current.setData(ma99);
        }

        if (seriesRef.current && trades && trades.length > 0 && data.length > 0) {
            try {
                // Ensure trades are sorted and have valid timestamps
                // Also, createMarkers handles the conversion.
                const markers = createMarkers(trades, data);
                (seriesRef.current as any).setMarkers(markers);
            } catch (e) {
                console.warn("setMarkers failed:", e);
            }
        }
    }, [data, ma7, ma25, ma99, trades]); // Run when data changes

    return (
        <div className={twMerge("w-full h-full relative", className)}>
            <div 
                ref={chartContainerRef} 
                className="w-full h-full"
            />
            {/* Tooltip Overlay - Binance Style Header */}
            <div 
                className="absolute top-2 left-2 flex gap-3 bg-white dark:bg-[#1E2329]/90 p-1.5 rounded text-gray-500 dark:text-[#848E9C] font-mono text-xs select-none pointer-events-none shadow-sm"
                style={{ zIndex: 50 }}
            >
                {tooltipData && (
                    <>
                        <span className={tooltipData.close >= tooltipData.open ? "text-green-600 dark:text-[#0ECB81]" : "text-red-600 dark:text-[#F6465D]"}>
                            O: <span className="text-gray-900 dark:text-[#EAECEF]">{tooltipData.open.toFixed(2)}</span>
                        </span>
                        <span className={tooltipData.close >= tooltipData.open ? "text-green-600 dark:text-[#0ECB81]" : "text-red-600 dark:text-[#F6465D]"}>
                            H: <span className="text-gray-900 dark:text-[#EAECEF]">{tooltipData.high.toFixed(2)}</span>
                        </span>
                        <span className={tooltipData.close >= tooltipData.open ? "text-green-600 dark:text-[#0ECB81]" : "text-red-600 dark:text-[#F6465D]"}>
                            L: <span className="text-gray-900 dark:text-[#EAECEF]">{tooltipData.low.toFixed(2)}</span>
                        </span>
                        <span className={tooltipData.close >= tooltipData.open ? "text-green-600 dark:text-[#0ECB81]" : "text-red-600 dark:text-[#F6465D]"}>
                            C: <span className="text-gray-900 dark:text-[#EAECEF]">{tooltipData.close.toFixed(2)}</span>
                        </span>
                        {/* Calculate Change % */}
                        <span className={tooltipData.close >= tooltipData.open ? "text-green-600 dark:text-[#0ECB81]" : "text-red-600 dark:text-[#F6465D]"}>
                            Change: <span className="text-gray-900 dark:text-[#EAECEF]">{((tooltipData.close - tooltipData.open) / tooltipData.open * 100).toFixed(2)}%</span>
                        </span>
                    </>
                )}
            </div>
        </div>
    );
};
