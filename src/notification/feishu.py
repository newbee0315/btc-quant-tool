import requests
import json
import logging
import datetime
import os
import time
import socket
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class FeishuBot:
    def __init__(self, webhook_url: str = None, persistence_file: str = "feishu_data.json"):
        self.webhook_url = webhook_url
        self.persistence_file = persistence_file
        self.max_history = 100
        
        # Default stats
        self.stats = {
            "total_sent": 0,
            "success_count": 0,
            "fail_count": 0,
            "last_success_timestamp": None,
            "last_error_timestamp": None,
            "daily_counts": {}  # Format: "YYYY-MM-DD": count
        }
        self.message_history: List[Dict] = []
        
        self.load_data()

    def load_data(self):
        """Load history and stats from file"""
        if os.path.exists(self.persistence_file):
            try:
                with open(self.persistence_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.message_history = data.get("history", [])
                    saved_stats = data.get("stats", {})
                    # Merge saved stats with defaults to ensure all keys exist
                    self.stats.update(saved_stats)
            except Exception as e:
                logger.error(f"Failed to load Feishu data: {e}")

    def save_data(self):
        """Save history and stats to file"""
        try:
            data = {
                "history": self.message_history,
                "stats": self.stats
            }
            with open(self.persistence_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save Feishu data: {e}")

    def _log_message(self, msg_type: str, content: str, success: bool, error: str = None):
        timestamp = datetime.datetime.now().isoformat()
        record = {
            "timestamp": timestamp,
            "type": msg_type,
            "content": content,
            "status": "success" if success else "failed",
            "error": error
        }
        self.message_history.insert(0, record)
        if len(self.message_history) > self.max_history:
            self.message_history.pop()
            
        # Update Stats
        self.stats["total_sent"] += 1
        if success:
            self.stats["success_count"] += 1
            self.stats["last_success_timestamp"] = timestamp
        else:
            self.stats["fail_count"] += 1
            self.stats["last_error_timestamp"] = timestamp
            
        # Update Daily Count
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        self.stats["daily_counts"][today] = self.stats["daily_counts"].get(today, 0) + 1
        
        # Keep only last 30 days of daily counts
        sorted_dates = sorted(self.stats["daily_counts"].keys())
        if len(sorted_dates) > 30:
            for d in sorted_dates[:-30]:
                del self.stats["daily_counts"][d]
                
        self.save_data()

    def get_history(self) -> List[Dict]:
        return self.message_history
        
    def get_stats(self) -> Dict:
        return self.stats

    def diagnose(self) -> Dict[str, Any]:
        """Run self-diagnosis"""
        results = {
            "webhook_configured": False,
            "network_connectivity": False,
            "api_reachable": False,
            "recent_errors": [],
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        # 1. Check Webhook Config
        if self.webhook_url and self.webhook_url.startswith("http"):
            results["webhook_configured"] = True
        
        # 2. Check Network Connectivity (DNS Resolution)
        try:
            host = "open.feishu.cn"
            if self.webhook_url:
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(self.webhook_url)
                    host = parsed.netloc
                except:
                    pass
            
            socket.gethostbyname(host)
            results["network_connectivity"] = True
        except Exception as e:
            logger.error(f"DNS resolution failed: {e}")
            
        # 3. Check API Reachability (Ping)
        # Note: We can't easily ping the webhook URL without sending a message.
        # But we can try a GET request to the domain root or a known endpoint if possible.
        # Feishu Webhooks only accept POST. GET might return 404 or 405, but proves connectivity.
        try:
            if self.webhook_url:
                # Just check if we can connect to the server, even if we get 400/405
                # Using a very short timeout
                try:
                    requests.get(self.webhook_url, timeout=3)
                except requests.exceptions.RequestException as e:
                    # If it's a connection error, then reachable is False.
                    # If it's a 405 Method Not Allowed, it means we reached the server.
                    if isinstance(e, requests.exceptions.ConnectTimeout) or \
                       isinstance(e, requests.exceptions.ConnectionError):
                        raise e
                results["api_reachable"] = True
        except Exception as e:
            logger.error(f"API reachability check failed: {e}")
            
        # 4. Recent Errors
        recent_failures = [m for m in self.message_history if m['status'] == 'failed'][:5]
        results["recent_errors"] = recent_failures
        
        return results

    def send_text(self, text: str):
        """发送普通文本消息"""
        if not self.webhook_url:
            self._log_message("text", text, False, "No webhook URL configured")
            return
        
        headers = {'Content-Type': 'application/json'}
        data = {
            "msg_type": "text",
            "content": {
                "text": text
            }
        }
        try:
            response = requests.post(self.webhook_url, headers=headers, data=json.dumps(data), timeout=5)
            response.raise_for_status()
            self._log_message("text", text, True)
        except Exception as e:
            logger.error(f"Feishu send text error: {e}")
            self._log_message("text", text, False, str(e))

    def send_trade_card(self, action: str, symbol: str, price: float, amount: float, pnl: float = None, reason: str = "", prob: float = None, sl: float = None, tp: float = None):
        """发送交易卡片消息"""
        if not self.webhook_url:
            self._log_message("card", f"{action} {symbol}", False, "No webhook URL configured")
            return

        # 颜色配置
        color = "blue"
        emoji_title = "🤖"
        if action == "BUY":
            color = "green" 
            emoji_title = "🟢"
        elif action == "SELL":
            color = "red" if (pnl and pnl < 0) else "orange" # 止损红，止盈橙，普通卖出橙
            emoji_title = "🔴" if (pnl and pnl < 0) else "🟠"

        title = f"{emoji_title} 模拟交易提醒: {action} {symbol}"
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 构建内容
        content_lines = [
            f"**时间**: {current_time}",
            f"**价格**: ${price:,.2f}",
            f"**数量**: {amount:.6f} BTC",
            f"**原因**: {reason}"
        ]
        
        if prob:
            confidence_str = f"{prob*100:.1f}%"
            content_lines.append(f"**模型置信度**: {confidence_str}")
            
        if sl and tp:
            sl_price = price * (1 - sl)
            tp_price = price * (1 + tp)
            content_lines.append(f"**策略目标**: 止盈 ${tp_price:,.0f} (+{tp*100}%) | 止损 ${sl_price:,.0f} (-{sl*100}%)")
        
        if pnl is not None:
            emoji = "💰" if pnl >= 0 else "💸"
            content_lines.append(f"**本单盈亏**: {emoji} ${pnl:,.2f}")
            
            if pnl > 0:
                content_lines.append("🎉 恭喜赚钱！继续保持！")
            else:
                content_lines.append("🛡️ 严格止损，等待下一次机会。")

        card = {
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": title
                },
                "template": color
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "\n".join(content_lines)
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": "来自 Binance AI Quant Tool 的自动监控"
                        }
                    ]
                }
            ]
        }
        
        data = {
            "msg_type": "interactive",
            "card": card
        }
        
        try:
            response = requests.post(self.webhook_url, headers=headers, data=json.dumps(card), timeout=5)
            response.raise_for_status()
            self._log_message("card", f"{action} {symbol} - {reason}", True)
        except Exception as e:
            logger.error(f"Feishu send card error: {e}")
            self._log_message("card", f"{action} {symbol}", False, str(e))

    def send_signal_alert(self, symbol: str, horizon: int, prob: float, price: float):
        """发送强信号提醒"""
        if not self.webhook_url:
            return
            
        color = "green" if prob > 0.5 else "red"
        direction = "看涨 (Bullish)" if prob > 0.5 else "看跌 (Bearish)"
        
        card = {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"🚀 AI 强信号提醒: {symbol}"
                },
                "template": color
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**周期**: {horizon}分钟\n**方向**: {direction}\n**置信度**: {prob:.1%}\n**当前价**: ${price:,.2f}"
                    }
                }
            ]
        }
        
        data = {
            "msg_type": "interactive",
            "card": card
        }
        
        try:
            requests.post(self.webhook_url, headers={'Content-Type': 'application/json'}, data=json.dumps(data), timeout=5)
        except Exception as e:
            logger.error(f"Feishu signal alert error: {e}")
