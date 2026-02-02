import requests
import json
import logging
import datetime

logger = logging.getLogger(__name__)

class FeishuBot:
    def __init__(self, webhook_url: str = None):
        self.webhook_url = webhook_url

    def send_text(self, text: str):
        """发送普通文本消息"""
        if not self.webhook_url:
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
        except Exception as e:
            logger.error(f"Feishu send text error: {e}")

    def send_trade_card(self, action: str, symbol: str, price: float, amount: float, pnl: float = None, reason: str = "", prob: float = None, sl: float = None, tp: float = None):
        """发送交易卡片消息"""
        if not self.webhook_url:
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
            response = requests.post(self.webhook_url, headers={'Content-Type': 'application/json'}, data=json.dumps(data), timeout=5)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Feishu send card error: {e}")

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
