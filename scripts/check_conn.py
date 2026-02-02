import ccxt
import time
import requests

def check_binance():
    print("Checking Binance connectivity via CCXT...")
    try:
        exchange = ccxt.binance({'timeout': 5000})
        ticker = exchange.fetch_ticker('BTC/USDT')
        print(f"SUCCESS: Binance BTC/USDT price: {ticker['last']}")
        return True
    except Exception as e:
        print(f"FAILED: Binance CCXT error: {e}")
        return False

def check_yfinance():
    print("\nChecking yfinance connectivity...")
    try:
        import yfinance as yf
        ticker = yf.Ticker("BTC-USD")
        hist = ticker.history(period="1d", interval="1m")
        if not hist.empty:
            print(f"SUCCESS: yfinance fetched {len(hist)} rows. Last close: {hist['Close'].iloc[-1]}")
            return True
        else:
            print("FAILED: yfinance returned empty data")
            return False
    except Exception as e:
        print(f"FAILED: yfinance error: {e}")
        return False

def check_coingecko():
    print("\nChecking CoinGecko API...")
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            print(f"SUCCESS: CoinGecko BTC price: {resp.json()['bitcoin']['usd']}")
            return True
        else:
            print(f"FAILED: CoinGecko status {resp.status_code}")
            return False
    except Exception as e:
        print(f"FAILED: CoinGecko error: {e}")
        return False

def check_okx():
    print("\nChecking OKX connectivity via CCXT...")
    try:
        exchange = ccxt.okx({'timeout': 5000})
        ticker = exchange.fetch_ticker('BTC/USDT')
        print(f"SUCCESS: OKX BTC/USDT price: {ticker['last']}")
        return True
    except Exception as e:
        print(f"FAILED: OKX CCXT error: {e}")
        return False

def check_bybit():
    print("\nChecking Bybit connectivity via CCXT...")
    try:
        exchange = ccxt.bybit({'timeout': 5000})
        ticker = exchange.fetch_ticker('BTC/USDT')
        print(f"SUCCESS: Bybit BTC/USDT price: {ticker['last']}")
        return True
    except Exception as e:
        print(f"FAILED: Bybit CCXT error: {e}")
        return False

def check_coincap():
    print("\nChecking CoinCap API...")
    try:
        url = "https://api.coincap.io/v2/assets/bitcoin"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            print(f"SUCCESS: CoinCap BTC price: {resp.json()['data']['priceUsd']}")
            return True
        else:
            print(f"FAILED: CoinCap status {resp.status_code}")
            return False
    except Exception as e:
        print(f"FAILED: CoinCap error: {e}")
        return False

def check_binance_vision():
    print("\nChecking Binance Vision (Public Data) API...")
    try:
        url = "https://data-api.binance.vision/api/v3/ticker/price?symbol=BTCUSDT"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            print(f"SUCCESS: Binance Vision BTC price: {resp.json()['price']}")
            return True
        else:
            print(f"FAILED: Binance Vision status {resp.status_code}")
            return False
    except Exception as e:
        print(f"FAILED: Binance Vision error: {e}")
        return False

if __name__ == "__main__":
    b = check_binance()
    y = check_yfinance()
    c = check_coingecko()
    o = check_okx()
    by = check_bybit()
    cc = check_coincap()
    bv = check_binance_vision()
    
    print("\nSummary:")
    print(f"Binance: {'OK' if b else 'FAIL'}")
    print(f"yfinance: {'OK' if y else 'FAIL'}")
    print(f"CoinGecko: {'OK' if c else 'FAIL'}")
    print(f"OKX: {'OK' if o else 'FAIL'}")
    print(f"Bybit: {'OK' if by else 'FAIL'}")
    print(f"CoinCap: {'OK' if cc else 'FAIL'}")
    print(f"Binance Vision: {'OK' if bv else 'FAIL'}")