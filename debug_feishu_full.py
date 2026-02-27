
import os
import sys
import json
import requests
from dotenv import load_dotenv

# Add src to path
sys.path.append(os.getcwd())

load_dotenv()

def debug_feishu():
    url = os.getenv("FEISHU_WEBHOOK_URL")
    print(f"URL from env: {url[:10]}...{url[-5:] if url else ''}")
    
    if not url:
        print("Error: No URL loaded from .env")
        return

    print("\n1. Testing Simple Text Message...")
    headers = {'Content-Type': 'application/json'}
    data = {
        "msg_type": "text",
        "content": {
            "text": "🔍 Debug Test: Simple Text Message\nTimestamp: " + os.popen("date").read().strip()
        }
    }
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data), timeout=10)
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {response.headers}")
        print(f"Response Body: {response.text}")
        
        try:
            json_resp = response.json()
            if json_resp.get("code") != 0:
                print(f"❌ Feishu Error Code: {json_resp.get('code')}")
                print(f"❌ Feishu Error Msg: {json_resp.get('msg')}")
            else:
                print("✅ Feishu Success (Code 0)")
        except:
            print("⚠️ Response is not JSON")
            
    except Exception as e:
        print(f"❌ Request Failed: {e}")

    print("\n2. Testing Card Message (Interactive)...")
    card_data = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "🔍 Debug Test: Card Message"
                },
                "template": "blue"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**Status**: Debugging\n**Check**: Please confirm if you see this."
                    }
                }
            ]
        }
    }
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(card_data), timeout=10)
        print(f"Status Code: {response.status_code}")
        print(f"Response Body: {response.text}")
    except Exception as e:
        print(f"❌ Card Request Failed: {e}")

if __name__ == "__main__":
    debug_feishu()
