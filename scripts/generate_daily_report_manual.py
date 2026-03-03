import sys
import os
import logging
import json
import asyncio
from dotenv import load_dotenv

# Add src to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.trader.real_trader import RealTrader
from src.content.social_media_generator import SocialMediaGenerator
from src.notification.feishu import FeishuBot

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    load_dotenv()
    
    # Initialize Feishu Bot
    webhook_url = os.getenv("FEISHU_WEBHOOK_URL")
    app_id = os.getenv("FEISHU_APP_ID")
    app_secret = os.getenv("FEISHU_APP_SECRET")
    
    feishu_bot = None
    if webhook_url:
        # Use keyword arguments to avoid mismatch with persistence_file arg
        feishu_bot = FeishuBot(webhook_url=webhook_url, app_id=app_id, app_secret=app_secret)
        logger.info("Feishu Bot initialized.")
    else:
        logger.warning("FEISHU_WEBHOOK_URL not set, cannot send report.")
    
    status = None
    
    # 1. Try to load from local cache file first (best for offline/connection issues)
    cache_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '../data/real_trading_status.json'))
    if os.path.exists(cache_file):
        logger.info(f"Loading status from cache: {cache_file}")
        try:
            with open(cache_file, 'r') as f:
                status = json.load(f)
                # Ensure stats exists
                if 'stats' not in status:
                    status['stats'] = {
                        'total_pnl': 0.0,
                        'win_rate': 0.0,
                        'total_trades': len(status.get('trade_history', []))
                    }
                    # Calculate PnL from trade history if missing
                    total_pnl = sum(t.get('realized_pnl', 0) for t in status.get('trade_history', []))
                    status['stats']['total_pnl'] = total_pnl
                    
                    # Calculate Win Rate
                    wins = sum(1 for t in status.get('trade_history', []) if t.get('realized_pnl', 0) > 0)
                    total = len(status.get('trade_history', []))
                    if total > 0:
                        status['stats']['win_rate'] = (wins / total) * 100
                        
        except Exception as e:
            logger.error(f"Failed to load cache: {e}")
    
    # 2. If cache failed or empty, try RealTrader (might fail due to connection)
    if not status or status.get('equity', 0) == 0:
        logger.info("Cache invalid or empty, trying RealTrader...")
        try:
            # Proxy Configuration (Same as run_multicoin_bot.py)
            proxy_url = os.getenv("PROXY_URL")
            if proxy_url is None:
                proxy_url = "http://127.0.0.1:7892" # Default for local dev
            elif proxy_url == "":
                proxy_url = None
                
            trader = RealTrader(symbol="BTC/USDT", proxy_url=proxy_url)
            status = trader.get_status()
        except Exception as e:
            logger.error(f"Failed to get status from RealTrader: {e}")
            if not status:
                status = {} # Empty dict to avoid crash, generator will handle defaults

    logger.info("Initializing SocialMediaGenerator...")
    generator = SocialMediaGenerator()
    
    logger.info("Generating report text...")
    report_text = ""
    try:
        report_text = generator.generate_report(status)
        print("\n" + "="*50)
        print("REPORT TEXT:")
        print("="*50)
        print(report_text)
        print("="*50 + "\n")
    except Exception as e:
        logger.error(f"Failed to generate report text: {e}")

    logger.info("Generating report image...")
    image_path = None
    try:
        image_path = generator.generate_image(status)
        print(f"IMAGE PATH: {image_path}")
        
        if os.path.exists(image_path):
            print("✅ Image generated successfully.")
        else:
            print("❌ Image file not found.")
            
    except Exception as e:
        logger.error(f"Failed to generate report image: {e}")
        
    # Send to Feishu
    if feishu_bot:
        logger.info("Sending to Feishu...")
        
        # 1. Send Image
        image_sent = False
        if image_path and os.path.exists(image_path):
            if app_id and app_secret:
                try:
                    logger.info(f"Uploading image: {image_path}")
                    image_key = feishu_bot.upload_image(image_path)
                    if image_key:
                        feishu_bot.send_image(image_key)
                        logger.info("✅ Image sent to Feishu.")
                        image_sent = True
                    else:
                        logger.error("❌ Failed to upload image (no key returned).")
                except Exception as e:
                    logger.error(f"❌ Failed to send image: {e}")
            else:
                logger.warning("⚠️ FEISHU_APP_ID or FEISHU_APP_SECRET missing, skipping image upload.")
                report_text += f"\n\n⚠️ Image generated locally at `{image_path}` but cannot be sent without App ID/Secret."
        
        # 2. Send Text
        if report_text:
            try:
                title = "📢 自动回本挑战日报 (Manual Trigger)"
                feishu_bot.send_markdown(report_text, title)
                logger.info("✅ Text report sent to Feishu.")
            except Exception as e:
                logger.error(f"❌ Failed to send text report: {e}")

if __name__ == "__main__":
    asyncio.run(main())
