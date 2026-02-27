"use client";

import { useState, useEffect } from 'react';
import { 
  Activity, Settings, Save, RefreshCw, AlertTriangle, 
  CheckCircle, XCircle, Wifi, Shield, HelpCircle, 
  BarChart2, Server, MessageSquare, Clock, ChevronDown, ChevronUp, Key
} from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface FeishuMessage {
  timestamp: string;
  type: string;
  content: string;
  status: string;
  error?: string;
}

interface BotConfig {
  confidence_threshold: number;
  notification_level: string;
}

interface FeishuStats {
    total_sent: number;
    success_count: number;
    fail_count: number;
    last_success_timestamp: string | null;
    last_error_timestamp: string | null;
    daily_counts: {[key: string]: number};
}

interface DiagnosticResult {
    webhook_configured: boolean;
    network_connectivity: boolean;
    api_reachable: boolean;
    recent_errors: FeishuMessage[];
    timestamp: string;
}

export default function FeishuPage() {
  const [messages, setMessages] = useState<FeishuMessage[]>([]);
  const [stats, setStats] = useState<FeishuStats | null>(null);
  const [config, setConfig] = useState<BotConfig>({
    confidence_threshold: 0.7,
    notification_level: 'HIGH_ONLY'
  });
  const [diagnosticResult, setDiagnosticResult] = useState<DiagnosticResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [diagnosing, setDiagnosing] = useState(false);
  const [showTroubleshoot, setShowTroubleshoot] = useState(false);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000); // Poll every 10s
    return () => clearInterval(interval);
  }, []);

  const fetchData = async () => {
    try {
      // Parallel fetch
      const [historyRes, configRes, statsRes] = await Promise.all([
        fetch(`${API_URL}/api/v1/feishu/history`),
        fetch(`${API_URL}/api/v1/bot/config`),
        fetch(`${API_URL}/api/v1/feishu/status`)
      ]);

      if (historyRes.ok) setMessages(await historyRes.json());
      if (configRes.ok) setConfig(await configRes.json());
      if (statsRes.ok) setStats(await statsRes.json());
      
      setLoading(false);
    } catch (error) {
      console.error('Error fetching data:', error);
      setLoading(false);
    }
  };

  const handleConfigUpdate = async () => {
    setSaving(true);
    try {
      const res = await fetch(`${API_URL}/api/v1/bot/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });
      if (res.ok) {
        alert('配置已更新 (Configuration Updated)');
      } else {
        alert('更新失败 (Update Failed)');
      }
    } catch (error) {
      console.error('Error updating config:', error);
      alert('更新出错 (Error Updating)');
    } finally {
      setSaving(false);
    }
  };

  const runDiagnosis = async () => {
    setDiagnosing(true);
    setDiagnosticResult(null);
    try {
      const res = await fetch(`${API_URL}/api/v1/feishu/diagnose`, { method: 'POST' });
      const data = await res.json();
      setDiagnosticResult(data);
    } catch (error) {
      console.error("Diagnosis failed:", error);
      alert("诊断请求失败");
    } finally {
      setDiagnosing(false);
    }
  };

  // Helper to format date
  const formatDate = (isoStr: string | null) => {
    if (!isoStr) return 'Never';
    return new Date(isoStr).toLocaleString('zh-CN', {
      month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit'
    });
  };

  // Status Badge Component
  const StatusBadge = ({ active, text }: { active: boolean, text: string }) => (
    <div className={`flex items-center gap-1.5 px-2 py-1 rounded border text-xs font-medium ${
      active 
        ? 'bg-[#132F25] text-green-600 dark:text-[#0ECB81] border-[#0ECB81]/30' 
        : 'bg-[#2E1818] text-red-600 dark:text-[#F6465D] border-[#F6465D]/30'
    }`}>
      {active ? <CheckCircle className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
      {text}
    </div>
  );

  return (
    <div className="min-h-screen bg-[#0B0E11] text-gray-900 dark:text-[#EAECEF] p-4 md:p-8 font-sans">
      <header className="mb-8 flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-yellow-600 dark:text-[#F0B90B] flex items-center gap-2">
            <MessageSquare className="w-6 h-6" />
            飞书自定义机器人监控 (Feishu Bot Monitor)
          </h1>
          <p className="text-sm text-gray-500 dark:text-[#848E9C] mt-1">实时监控机器人状态、一键诊断与配置管理</p>
        </div>
        <a href="/" className="px-4 py-2 bg-gray-100 dark:bg-[#2B3139] rounded hover:bg-[#3A4049] text-sm flex items-center gap-2 transition-colors">
          <span>返回首页</span>
        </a>
      </header>

      {/* 1. Status Dashboard */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <div className="bg-white dark:bg-[#1E2329] p-4 rounded-lg border border-gray-200 dark:border-[#2B3139] flex items-center justify-between">
            <div>
                <p className="text-gray-500 dark:text-[#848E9C] text-xs uppercase mb-1">运行状态 (Status)</p>
                <div className="flex items-center gap-2">
                    <div className={`w-3 h-3 rounded-full ${stats?.last_success_timestamp ? 'bg-[#0ECB81] animate-pulse' : 'bg-gray-500'}`}></div>
                    <span className="text-lg font-bold">
                        {stats?.last_success_timestamp ? 'Online' : 'Offline'}
                    </span>
                </div>
            </div>
            <Server className="w-8 h-8 text-[#474D57]" />
        </div>

        <div className="bg-white dark:bg-[#1E2329] p-4 rounded-lg border border-gray-200 dark:border-[#2B3139] flex items-center justify-between">
            <div>
                <p className="text-gray-500 dark:text-[#848E9C] text-xs uppercase mb-1">发送成功率 (Success Rate)</p>
                <div className="flex items-baseline gap-1">
                    <span className="text-xl font-bold text-gray-900 dark:text-[#EAECEF]">
                        {stats && stats.total_sent > 0 
                            ? Math.round((stats.success_count / stats.total_sent) * 100) 
                            : 0}%
                    </span>
                    <span className="text-xs text-gray-500 dark:text-[#848E9C]">
                        ({stats?.success_count || 0}/{stats?.total_sent || 0})
                    </span>
                </div>
            </div>
            <Activity className="w-8 h-8 text-yellow-600 dark:text-[#F0B90B]" />
        </div>

        <div className="bg-white dark:bg-[#1E2329] p-4 rounded-lg border border-gray-200 dark:border-[#2B3139] flex items-center justify-between">
            <div>
                <p className="text-gray-500 dark:text-[#848E9C] text-xs uppercase mb-1">今日发送 (Today)</p>
                <span className="text-xl font-bold text-gray-900 dark:text-[#EAECEF]">
                    {stats?.daily_counts[new Date().toISOString().split('T')[0]] || 0}
                </span>
            </div>
            <BarChart2 className="w-8 h-8 text-gray-500 dark:text-[#848E9C]" />
        </div>

        <div className="bg-white dark:bg-[#1E2329] p-4 rounded-lg border border-gray-200 dark:border-[#2B3139] flex items-center justify-between">
            <div>
                <p className="text-gray-500 dark:text-[#848E9C] text-xs uppercase mb-1">最后活跃 (Last Active)</p>
                <span className="text-sm font-medium text-gray-900 dark:text-[#EAECEF]">
                    {formatDate(stats?.last_success_timestamp || null)}
                </span>
            </div>
            <Clock className="w-8 h-8 text-gray-500 dark:text-[#848E9C]" />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Left Column: Diagnostics & Config */}
        <div className="lg:col-span-1 space-y-6">
            
            {/* Diagnostic Module */}
            <div className="bg-white dark:bg-[#1E2329] p-6 rounded-lg border border-gray-200 dark:border-[#2B3139]">
                <div className="flex justify-between items-center mb-4">
                    <h2 className="text-lg font-semibold text-yellow-600 dark:text-[#F0B90B] flex items-center gap-2">
                        <Shield className="w-5 h-5" />
                        一键诊断 (Diagnosis)
                    </h2>
                </div>
                
                <p className="text-xs text-gray-500 dark:text-[#848E9C] mb-4">
                    机器人长时间未响应？点击下方按钮自动检测 Webhook 配置、网络连通性及 API 权限。
                </p>

                <button 
                    onClick={runDiagnosis}
                    disabled={diagnosing}
                    className={`w-full py-3 rounded-lg font-medium transition-colors flex items-center justify-center gap-2 ${
                        diagnosing 
                        ? 'bg-gray-100 dark:bg-[#2B3139] text-gray-500 dark:text-[#848E9C] cursor-not-allowed' 
                        : 'bg-[#F0B90B] hover:bg-[#D9A60A] text-black'
                    }`}
                >
                    {diagnosing ? (
                        <><RefreshCw className="w-4 h-4 animate-spin" /> 诊断中 (Diagnosing)...</>
                    ) : (
                        <><Activity className="w-4 h-4" /> 开始诊断 (Start Diagnosis)</>
                    )}
                </button>

                {diagnosticResult && (
                    <div className="mt-4 space-y-3 bg-white dark:bg-[#161A25] p-4 rounded border border-gray-200 dark:border-[#2B3139] animate-fade-in">
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-gray-500 dark:text-[#848E9C]">Webhook 配置</span>
                            <StatusBadge active={diagnosticResult.webhook_configured} text={diagnosticResult.webhook_configured ? "Correct" : "Missing"} />
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-gray-500 dark:text-[#848E9C]">网络连通性</span>
                            <StatusBadge active={diagnosticResult.network_connectivity} text={diagnosticResult.network_connectivity ? "Pass" : "Fail"} />
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-gray-500 dark:text-[#848E9C]">API 可达性</span>
                            <StatusBadge active={diagnosticResult.api_reachable} text={diagnosticResult.api_reachable ? "Reachable" : "Blocked"} />
                        </div>
                        
                        {diagnosticResult.recent_errors.length > 0 && (
                            <div className="mt-3 pt-3 border-t border-gray-200 dark:border-[#2B3139]">
                                <p className="text-xs text-red-600 dark:text-[#F6465D] font-bold mb-2 flex items-center gap-1">
                                    <AlertTriangle className="w-3 h-3" /> 最近错误日志:
                                </p>
                                <div className="text-[10px] text-red-600 dark:text-[#F6465D] bg-[#2E1818] p-2 rounded overflow-x-auto">
                                    {diagnosticResult.recent_errors[0].error || "Unknown Error"}
                                </div>
                            </div>
                        )}
                        
                        <div className="text-[10px] text-gray-500 dark:text-[#848E9C] text-center mt-2">
                            检测时间: {new Date(diagnosticResult.timestamp).toLocaleTimeString()}
                        </div>
                    </div>
                )}
            </div>

            {/* Configuration */}
            <div className="bg-white dark:bg-[#1E2329] p-6 rounded-lg border border-gray-200 dark:border-[#2B3139]">
                <h2 className="text-lg font-semibold mb-4 text-yellow-600 dark:text-[#F0B90B] flex items-center gap-2">
                    <Settings className="w-5 h-5" />
                    参数配置 (Settings)
                </h2>
                
                <div className="space-y-4">
                    <div>
                        <label className="block text-sm text-gray-500 dark:text-[#848E9C] mb-2">
                            置信度阈值 (Confidence Threshold)
                        </label>
                        <div className="flex items-center space-x-4">
                            <input 
                                type="range" 
                                min="0.5" 
                                max="0.95" 
                                step="0.01"
                                value={config.confidence_threshold}
                                onChange={(e) => setConfig({...config, confidence_threshold: parseFloat(e.target.value)})}
                                className="flex-1 accent-yellow-600 dark:accent-[#F0B90B] h-2 bg-gray-100 dark:bg-[#2B3139] rounded-lg appearance-none cursor-pointer"
                            />
                            <span className="text-gray-900 dark:text-[#EAECEF] font-mono w-12 text-right">
                                {Math.round(config.confidence_threshold * 100)}%
                            </span>
                        </div>
                    </div>

                    <div>
                        <label className="block text-sm text-gray-500 dark:text-[#848E9C] mb-2">
                            通知级别 (Notification Level)
                        </label>
                        <div className="grid grid-cols-2 gap-2">
                            <button
                                onClick={() => setConfig({...config, notification_level: 'HIGH_ONLY'})}
                                className={`px-4 py-2 rounded text-xs transition-colors ${
                                    config.notification_level === 'HIGH_ONLY' 
                                    ? 'bg-[#F0B90B] text-black font-bold' 
                                    : 'bg-gray-100 dark:bg-[#2B3139] text-gray-500 dark:text-[#848E9C] hover:bg-gray-200 dark:hover:bg-[#363C45]'
                                }`}
                            >
                                仅高置信度
                            </button>
                            <button
                                onClick={() => setConfig({...config, notification_level: 'ALL'})}
                                className={`px-4 py-2 rounded text-xs transition-colors ${
                                    config.notification_level === 'ALL' 
                                    ? 'bg-[#F0B90B] text-black font-bold' 
                                    : 'bg-gray-100 dark:bg-[#2B3139] text-gray-500 dark:text-[#848E9C] hover:bg-gray-200 dark:hover:bg-[#363C45]'
                                }`}
                            >
                                所有信号
                            </button>
                        </div>
                    </div>

                    <button 
                        onClick={handleConfigUpdate}
                        disabled={saving}
                        className={`w-full py-2 rounded font-medium transition-colors flex items-center justify-center gap-2 ${
                            saving 
                            ? 'bg-gray-100 dark:bg-[#2B3139] text-gray-500 dark:text-[#848E9C]' 
                            : 'bg-[#474D57] hover:bg-[#59606D] text-white'
                        }`}
                    >
                        {saving ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                        {saving ? '保存中...' : '保存配置 (Save Config)'}
                    </button>
                </div>
            </div>

            {/* Troubleshooting Guide */}
            <div className="bg-white dark:bg-[#1E2329] rounded-lg border border-gray-200 dark:border-[#2B3139] overflow-hidden">
                <button 
                    onClick={() => setShowTroubleshoot(!showTroubleshoot)}
                    className="w-full p-4 flex justify-between items-center text-left hover:bg-gray-100 dark:bg-[#2B3139] transition-colors"
                >
                    <div className="flex items-center gap-2 text-yellow-600 dark:text-[#F0B90B] font-semibold">
                        <HelpCircle className="w-5 h-5" />
                        <span>常见问题与指引 (Help & Guide)</span>
                    </div>
                    {showTroubleshoot ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                </button>
                
                {showTroubleshoot && (
                    <div className="p-4 bg-white dark:bg-[#161A25] border-t border-gray-200 dark:border-[#2B3139] text-xs space-y-4">
                        <div className="space-y-2">
                            <h3 className="font-bold text-gray-900 dark:text-[#EAECEF] flex items-center gap-1">
                                <Key className="w-3 h-3" /> Webhook 密钥失效
                            </h3>
                            <p className="text-gray-500 dark:text-[#848E9C] leading-relaxed">
                                如果诊断显示 API 不可达或 Webhook 配置错误，请前往 <a href="https://open.feishu.cn/" target="_blank" className="text-yellow-600 dark:text-[#F0B90B] hover:underline">飞书开放平台</a> 重新生成 Webhook 地址，并更新项目 <code>.env</code> 文件中的 <code>FEISHU_WEBHOOK_URL</code>。
                            </p>
                        </div>
                        
                        <div className="space-y-2">
                            <h3 className="font-bold text-gray-900 dark:text-[#EAECEF] flex items-center gap-1">
                                <Shield className="w-3 h-3" /> IP 白名单限制
                            </h3>
                            <p className="text-gray-500 dark:text-[#848E9C] leading-relaxed">
                                飞书机器人安全设置中如果开启了 IP 白名单，请确保部署服务器的 IP 地址 (当前: <code>106.15.73.181</code> 或本地 IP) 已被添加。建议测试阶段暂时关闭 IP 限制。
                            </p>
                        </div>

                        <div className="space-y-2">
                            <h3 className="font-bold text-gray-900 dark:text-[#EAECEF] flex items-center gap-1">
                                <Wifi className="w-3 h-3" /> 网络连通性
                            </h3>
                            <p className="text-gray-500 dark:text-[#848E9C] leading-relaxed">
                                确保服务器能够访问 <code>open.feishu.cn</code>。如果诊断中 DNS 解析失败，请检查服务器 DNS 配置。
                            </p>
                        </div>
                    </div>
                )}
            </div>
        </div>

        {/* Right Column: History & Trends */}
        <div className="lg:col-span-2 space-y-6">
            
            {/* Recent History */}
            <div className="bg-white dark:bg-[#1E2329] rounded-lg border border-gray-200 dark:border-[#2B3139] flex flex-col h-[600px]">
                <div className="p-4 border-b border-gray-200 dark:border-[#2B3139] flex justify-between items-center">
                    <h2 className="text-lg font-semibold text-yellow-600 dark:text-[#F0B90B]">发送记录 (Message History)</h2>
                    <span className="text-xs text-gray-500 dark:text-[#848E9C]">Last 100 messages</span>
                </div>
                
                <div className="flex-1 overflow-y-auto p-4 space-y-3">
                    {loading && messages.length === 0 ? (
                        <div className="flex flex-col items-center justify-center h-full text-gray-500 dark:text-[#848E9C] gap-2">
                            <RefreshCw className="w-6 h-6 animate-spin" />
                            <span>加载中...</span>
                        </div>
                    ) : messages.length === 0 ? (
                        <div className="flex flex-col items-center justify-center h-full text-gray-500 dark:text-[#848E9C]">
                            <span>暂无消息记录</span>
                        </div>
                    ) : (
                        messages.map((msg, idx) => (
                            <div key={idx} className="bg-white dark:bg-[#161A25] p-3 rounded border border-gray-200 dark:border-[#2B3139] text-sm hover:border-gray-300 dark:border-[#474D57] transition-colors">
                                <div className="flex justify-between items-start mb-2">
                                    <div className="flex items-center gap-2">
                                        <span className={`px-1.5 py-0.5 rounded text-[10px] uppercase font-bold ${
                                            msg.type === 'text' ? 'bg-gray-100 dark:bg-[#2B3139] text-gray-900 dark:text-[#EAECEF]' : 'bg-[#2E1818] text-yellow-600 dark:text-[#F0B90B]'
                                        }`}>
                                            {msg.type}
                                        </span>
                                        <span className="text-gray-500 dark:text-[#848E9C] text-xs font-mono">
                                            {formatDate(msg.timestamp)}
                                        </span>
                                    </div>
                                    {msg.status === 'success' ? (
                                        <div className="flex items-center gap-1 text-green-600 dark:text-[#0ECB81] text-xs">
                                            <CheckCircle className="w-3 h-3" />
                                            <span>Sent</span>
                                        </div>
                                    ) : (
                                        <div className="flex items-center gap-1 text-red-600 dark:text-[#F6465D] text-xs">
                                            <XCircle className="w-3 h-3" />
                                            <span>Failed</span>
                                        </div>
                                    )}
                                </div>
                                <div className="text-gray-900 dark:text-[#EAECEF] break-all font-mono text-xs leading-relaxed opacity-90">
                                    {msg.content}
                                </div>
                                {msg.error && (
                                    <div className="mt-2 text-red-600 dark:text-[#F6465D] text-xs bg-[#2E1818] p-2 rounded">
                                        Error: {msg.error}
                                    </div>
                                )}
                            </div>
                        ))
                    )}
                </div>
            </div>

            {/* Daily Trend Chart (Simple CSS Bar Chart) */}
            <div className="bg-white dark:bg-[#1E2329] p-4 rounded-lg border border-gray-200 dark:border-[#2B3139]">
                <h2 className="text-lg font-semibold mb-4 text-yellow-600 dark:text-[#F0B90B] flex items-center gap-2">
                    <BarChart2 className="w-5 h-5" />
                    近30天发送趋势 (30-Day Trend)
                </h2>
                
                <div className="h-40 flex items-end justify-between gap-1 pt-4">
                    {stats && Object.keys(stats.daily_counts).length > 0 ? (
                        // Sort dates and map
                        Object.entries(stats.daily_counts)
                            .sort((a, b) => new Date(a[0]).getTime() - new Date(b[0]).getTime())
                            .map(([date, count], idx, arr) => {
                                const max = Math.max(...Object.values(stats.daily_counts), 10); // Minimum scale of 10
                                const height = Math.max((count / max) * 100, 5); // Min 5% height
                                return (
                                    <div key={date} className="flex-1 flex flex-col items-center group relative">
                                        <div 
                                            className="w-full bg-gray-100 dark:bg-[#2B3139] hover:bg-[#F0B90B] transition-colors rounded-t"
                                            style={{ height: `${height}%` }}
                                        ></div>
                                        {/* Tooltip */}
                                        <div className="absolute bottom-full mb-2 hidden group-hover:block bg-white dark:bg-[#161A25] text-xs p-2 rounded border border-gray-300 dark:border-[#474D57] whitespace-nowrap z-10">
                                            {date}: {count} msgs
                                        </div>
                                    </div>
                                );
                            })
                    ) : (
                        <div className="w-full h-full flex items-center justify-center text-gray-500 dark:text-[#848E9C] text-sm">
                            No trend data available yet
                        </div>
                    )}
                </div>
                <div className="flex justify-between text-[10px] text-gray-500 dark:text-[#848E9C] mt-2 border-t border-gray-200 dark:border-[#2B3139] pt-2">
                    <span>30 days ago</span>
                    <span>Today</span>
                </div>
            </div>
        </div>
      </div>
    </div>
  );
}