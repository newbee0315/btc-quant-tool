import os
from dotenv import load_dotenv
load_dotenv()
proxy = os.getenv("PROXY_URL")
print(f"PROXY_URL: {proxy}")
