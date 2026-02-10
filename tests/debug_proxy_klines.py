import requests

proxy_url = "http://127.0.0.1:33210"
proxies = {
    "http": proxy_url,
    "https": proxy_url
}
# The failing URL from logs
url = "https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=1h&limit=1000"

print(f"Testing proxy with klines: {proxies}")

try:
    resp = requests.get(url, proxies=proxies, timeout=10)
    print(f"Status: {resp.status_code}")
    # print(f"Content: {resp.text[:100]}")
except Exception as e:
    print(f"Error: {e}")
