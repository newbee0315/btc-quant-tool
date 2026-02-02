import ccxt
import pandas as pd

def test_ccxt_custom_host():
    print("Testing CCXT with custom hostname: data-api.binance.vision")
    try:
        # Manually override URLs for Binance
        exchange = ccxt.binance({
            'timeout': 10000,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot', 
            }
        })
        
        # Override the API urls
        exchange.urls['api'] = {
            'public': 'https://data-api.binance.vision/api/v3',
            'private': 'https://data-api.binance.vision/api/v3',
            'v1': 'https://data-api.binance.vision/api/v1',
            'v3': 'https://data-api.binance.vision/api/v3',
            'sapi': 'https://data-api.binance.vision/sapi/v1', # Probably won't work but we don't need it
        }
        
        # We need to suppress load_markets() automatic call or ensure it uses the new URL
        # By default fetch_ticker calls load_markets if not loaded.
        
        print("Urls overridden:", exchange.urls['api'])
        
        # Fetch Ticker
        ticker = exchange.fetch_ticker('BTC/USDT')
        print(f"SUCCESS: Ticker Price: {ticker['last']}")
        
        # Fetch OHLCV (History)
        print("Fetching OHLCV...")
        ohlcv = exchange.fetch_ohlcv('BTC/USDT', timeframe='1m', limit=5)
        print(f"SUCCESS: Fetched {len(ohlcv)} candles")
        print("Sample candle:", ohlcv[0])
        return True
    except Exception as e:
        print(f"FAILED: {e}")
        return False

if __name__ == "__main__":
    test_ccxt_custom_host()