import React, { useEffect, useState } from 'react';
import { Newspaper, ExternalLink, Clock } from 'lucide-react';
import axios from 'axios';

interface NewsItem {
    id: string;
    title: string;
    url: string;
    body: string;
    imageurl: string;
    published_on: number;
    source: string;
    categories: string;
    source_info?: {
        name: string;
        img: string;
        lang: string;
    }
}

export const NewsCard: React.FC = () => {
    const [news, setNews] = useState<NewsItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const fetchNews = async () => {
            try {
                const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
                const response = await axios.get(`${API_URL}/api/v1/market/news`);
                if (Array.isArray(response.data)) {
                    setNews(response.data);
                } else {
                    setNews([]);
                }
                setError(null);
            } catch (err) {
                console.error('Failed to fetch news:', err);
                setError('Failed to load news');
            } finally {
                setLoading(false);
            }
        };

        fetchNews();
        // Refresh every 5 minutes
        const interval = setInterval(fetchNews, 5 * 60 * 1000);
        return () => clearInterval(interval);
    }, []);

    if (loading && news.length === 0) {
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
                    <Newspaper className="w-4 h-4 text-yellow-600 dark:text-[#F0B90B]" />
                    Crypto News
                </h3>
                <span className="text-[10px] text-gray-500 dark:text-[#848E9C]">Source: CryptoCompare (Translated)</span>
            </div>

            <div className="flex-1 overflow-y-auto custom-scrollbar p-2 space-y-2">
                {news.length === 0 && !loading ? (
                    <div className="text-gray-500 dark:text-[#848E9C] text-center py-8 text-xs">No news available</div>
                ) : (
                    news.map((item) => (
                        <div key={item.id} className="group bg-gray-100 dark:bg-gray-200 dark:bg-[#2B3139]/20 hover:bg-gray-100 dark:bg-[#2B3139]/40 border border-gray-200 dark:border-gray-300 dark:border-[#2B3139]/50 rounded-lg p-3 transition-colors">
                            <a 
                                href={item.url} 
                                target="_blank" 
                                rel="noopener noreferrer"
                                className="block"
                            >
                                <div className="flex justify-between items-start gap-3">
                                    <div className="flex-1 min-w-0">
                                        <h4 className="text-sm font-medium text-gray-900 dark:text-[#EAECEF] group-hover:text-yellow-600 dark:text-[#F0B90B] transition-colors line-clamp-2 leading-snug mb-1.5">
                                            {item.title}
                                        </h4>
                                        <div className="flex items-center flex-wrap gap-2 text-[10px] text-gray-500 dark:text-[#848E9C]">
                                            <span className="flex items-center gap-1 bg-gray-100 dark:bg-[#2B3139] px-1.5 py-0.5 rounded">
                                                <Clock className="w-3 h-3" />
                                                {new Date(item.published_on * 1000).toLocaleString('zh-CN', { 
                                                    month: '2-digit', 
                                                    day: '2-digit', 
                                                    hour: '2-digit', 
                                                    minute: '2-digit' 
                                                })}
                                            </span>
                                            <span className="bg-gray-100 dark:bg-[#2B3139] px-1.5 py-0.5 rounded uppercase truncate max-w-[100px]">
                                                {item.source_info?.name || item.source}
                                            </span>
                                            {item.categories && (
                                                <span className="bg-gray-100 dark:bg-[#2B3139] px-1.5 py-0.5 rounded truncate max-w-[120px] text-gray-900 dark:text-[#EAECEF]/70">
                                                    {item.categories.split('|')[0]}
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                    {item.imageurl && (
                                        <div className="w-16 h-16 rounded overflow-hidden flex-shrink-0 border border-gray-200 dark:border-gray-300 dark:border-[#2B3139]/50 bg-gray-50 dark:bg-[#161A1E]">
                                            <img 
                                                src={item.imageurl} 
                                                alt="" 
                                                className="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity"
                                                onError={(e) => {
                                                    (e.target as HTMLImageElement).style.display = 'none';
                                                }}
                                            />
                                        </div>
                                    )}
                                </div>
                            </a>
                        </div>
                    ))
                )}
            </div>
        </div>
    );
};
