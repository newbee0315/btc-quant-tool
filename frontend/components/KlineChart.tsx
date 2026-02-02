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

interface KlineChartProps {
    data: KlineData[];
    ma7?: MAData[];
    ma25?: MAData[];
    ma99?: MAData[];
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
    const ma7SeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
    const ma25SeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
    const ma99SeriesRef = useRef<ISeriesApi<"Line"> | null>(null);

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

        if (data.length > 0) {
            candlestickSeries.setData(data);
        }
        
        if (ma7 && ma7.length > 0) ma7Series.setData(ma7);
        if (ma25 && ma25.length > 0) ma25Series.setData(ma25);
        if (ma99 && ma99.length > 0) ma99Series.setData(ma99);

        window.addEventListener('resize', handleResize);
        
        // Also add ResizeObserver to handle container resize
        const resizeObserver = new ResizeObserver(() => handleResize());
        resizeObserver.observe(chartContainerRef.current);

        // Fit content to ensure chart fills the width
        chart.timeScale().fitContent();

        return () => {
            window.removeEventListener('resize', handleResize);
            resizeObserver.disconnect();
            chart.remove();
        };
    }, [data, colors]); // Re-create chart when data changes (simple approach, better to use update methods but this works for now)

    // Effect to update data without destroying chart if chart instance exists
    useEffect(() => {
        if (seriesRef.current && data.length > 0) {
            seriesRef.current.setData(data);
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
    }, [data, ma7, ma25, ma99]);

    return (
        <div 
            ref={chartContainerRef} 
            className={twMerge("w-full h-full relative", className)}
        />
    );
};
