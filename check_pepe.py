import ccxt
print("Checking Binance Futures symbols...")
exchange = ccxt.binance({
    'options': {'defaultType': 'swap'},
    'proxies': {
        'http': 'http://127.0.0.1:33210',
        'https': 'http://127.0.0.1:33210'
    }
})
try:
    markets = exchange.load_markets()
    found = False
    for symbol in markets:
        if 'PEPE' in symbol:
            print(f"Found: {symbol}")
            found = True
    if not found:
        print("No PEPE found in swap markets")
except Exception as e:
    print(f"Error: {e}")
