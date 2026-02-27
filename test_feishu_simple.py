
import os
import sys
import json
import requests
from dotenv import load_dotenv

# Add src to path
sys.path.append(os.getcwd())

load_dotenv()

def test_simple():
    url = os.getenv("FEISHU_WEBHOOK_URL")
    if not url:
        print("Error: No URL loaded from .env")
        return

    print(f"Sending 'Test from CLI' to {url[:10]}...")
    
    headers = {'Content-Type': 'application/json'}
    data = {
        "msg_type": "text",
        "content": {
            "text": "Test from CLI"
        }
    }
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data), timeout=10)
        print(f"Status Code: {response.status_code}")
        print(f"Response Body: {response.text}")
    except Exception as e:
        print(f"❌ Request Failed: {e}")

if __name__ == "__main__":
    test_simple()
