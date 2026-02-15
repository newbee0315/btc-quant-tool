import React from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';

export interface EquityHistoryItem {
    timestamp: string;
    total_equity: number;
    wallet_balance: number;
    unrealized_pnl: number;
}

interface EquityHistoryChartProps {
    data: EquityHistoryItem[];
}

export const EquityHistoryChart: React.FC<EquityHistoryChartProps> = ({ data }) => {
    if (!data || data.length === 0) {
        return (
            <div className="w-full h-full min-h-[250px] bg-[#1E2329] p-4 rounded-xl border border-[#2B3139] flex items-center justify-center">
                <div className="text-gray-500 text-sm">No equity history data</div>
            </div>
        );
    }

    const formatXAxis = (tickItem: string) => {
        const date = new Date(tickItem);
        return `${date.getMonth() + 1}-${date.getDate()} ${date.getHours()}:${date.getMinutes().toString().padStart(2, '0')}`;
    };

    return (
        <div className="w-full h-full bg-[#1E2329] p-4 rounded-xl border border-[#2B3139]">
            <div className="text-sm font-medium text-gray-400 mb-4 flex justify-between items-center">
                <span>Total Equity History</span>
                <span className="text-xs text-gray-500">Hourly Updates</span>
            </div>
            <div className="h-[200px]">
                <ResponsiveContainer width="100%" height="100%">
                    <AreaChart
                        data={data}
                        margin={{
                            top: 5,
                            right: 10,
                            left: 0,
                            bottom: 5,
                        }}
                    >
                        <CartesianGrid strokeDasharray="3 3" stroke="#2B3139" vertical={false} />
                        <XAxis 
                            dataKey="timestamp" 
                            tickFormatter={formatXAxis} 
                            stroke="#848E9C" 
                            fontSize={10}
                            minTickGap={50}
                            tickLine={false}
                            axisLine={false}
                        />
                        <YAxis 
                            domain={['auto', 'auto']} 
                            stroke="#848E9C" 
                            fontSize={10}
                            tickFormatter={(value) => value.toFixed(0)}
                            tickLine={false}
                            axisLine={false}
                            width={40}
                        />
                        <Tooltip 
                            contentStyle={{ backgroundColor: '#1E2329', borderColor: '#2B3139', color: '#EAECEF', fontSize: '12px' }}
                            labelFormatter={(label) => new Date(label).toLocaleString()}
                            formatter={(value: any, name: any) => [value ? Number(value).toFixed(2) : "0.00", name]}
                        />
                        <Legend iconType="circle" wrapperStyle={{ fontSize: '12px', paddingTop: '10px' }}/>
                        <Area 
                            type="monotone" 
                            dataKey="total_equity" 
                            stroke="#F0B90B" 
                            fill="#F0B90B" 
                            fillOpacity={0.1} 
                            name="Total Equity"
                            strokeWidth={2}
                        />
                         <Area 
                            type="monotone" 
                            dataKey="wallet_balance" 
                            stroke="#3B82F6" 
                            fill="none" 
                            name="Wallet Balance"
                            strokeWidth={1}
                            strokeDasharray="5 5"
                        />
                    </AreaChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
};
