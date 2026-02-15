
import os
import sys
import asyncio
from dotenv import load_dotenv

# Add src to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.notification.feishu import FeishuBot

async def main():
    load_dotenv()
    webhook_url = os.getenv("FEISHU_WEBHOOK_URL")
    print(f"FEISHU_WEBHOOK_URL: {webhook_url}")
    
    if not webhook_url:
        print("Error: FEISHU_WEBHOOK_URL is not set.")
        return

    bot = FeishuBot(webhook_url)
    print("Attempting to send test message...")
    
    try:
        # Use the exact header the user wants to see if it works
        msg = "【实盘交易监控日报】(Hourly)\nDiagnosis Test Message"
        # Note: The send_text method in feishu.py might prepend 'Test:'
        bot.send_text(msg)
        print("Message sent (check Feishu).")
    except Exception as e:
        print(f"Error sending message: {e}")

if __name__ == "__main__":
    asyncio.run(main())
