import os
import sys
import logging
from dotenv import load_dotenv

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from notification.feishu import FeishuBot

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_feishu():
    load_dotenv()
    
    webhook_url = os.getenv("FEISHU_WEBHOOK_URL")
    
    if not webhook_url:
        logger.error("❌ FEISHU_WEBHOOK_URL is not set in .env file.")
        print("\nPlease configure your .env file with:")
        print("FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/...")
        return

    print(f"✅ Found Webhook URL: {webhook_url[:20]}...")
    
    bot = FeishuBot(webhook_url)
    
    print("\n1. Sending test text message...")
    try:
        bot.send_text("🔔 This is a test message from your Binance Tool!")
        print("✅ Text message sent successfully.")
    except Exception as e:
        print(f"❌ Failed to send text message: {e}")
        return

    print("\n2. Sending test trade card...")
    try:
        bot.send_trade_card(
            action="BUY",
            symbol="BTC/USDT",
            price=95000.0,
            amount=0.1,
            reason="Test Signal"
        )
        print("✅ Trade card sent successfully.")
    except Exception as e:
        print(f"❌ Failed to send trade card: {e}")

if __name__ == "__main__":
    test_feishu()
