
import os
import sys
import json
import requests
from dotenv import load_dotenv

sys.path.append(os.getcwd())
load_dotenv()

def test_check():
    url = os.getenv("FEISHU_WEBHOOK_URL")
    if not url:
        print("Error: No URL loaded from .env")
        return

    print(f"Sending 'Checking Feishu Connection...' to {url[:10]}...")
    
    headers = {'Content-Type': 'application/json'}
    data = {
        "msg_type": "text",
        "content": {
            "text": "Test: Checking Feishu Connection... (Added 'Test' keyword)"
        }
    }
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data), timeout=10)
        print(f"Status Code: {response.status_code}")
        print(f"Response Body: {response.text}")
    except Exception as e:
        print(f"❌ Request Failed: {e}")

if __name__ == "__main__":
    test_check()
