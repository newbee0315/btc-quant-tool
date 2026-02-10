import requests

proxy_url = "http://127.0.0.1:33210"
proxies = {
    "http": proxy_url,
    "https": proxy_url
}
url = "https://fapi.binance.com/fapi/v1/ping"

print(f"Testing proxy: {proxies}")

try:
    resp = requests.get(url, proxies=proxies, timeout=10)
    print(f"Status: {resp.status_code}")
    print(f"Content: {resp.text}")
except Exception as e:
    print(f"Error: {e}")
