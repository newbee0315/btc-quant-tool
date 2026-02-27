import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import pandas as pd
import time
import logging
import numpy as np
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CryptoDataCollector:
    def __init__(self, symbol='BTCUSDT', proxies=None):
        self.symbol = symbol.replace('/', '') # Ensure format is BTCUSDT
        # Switch to main API for better real-time data access (Depth/Ticker)
        self.base_url = "https://api.binance.com/api/v3" 
        self.proxies = proxies
        self.last_valid_price = 69000.0  # Default fallback
        
        # Initialize session with retries
        self.session = requests.Session()
        retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        if self.proxies:
            self.session.proxies.update(self.proxies)
        
        # Caching configuration
        self._price_cache = None
        self._price_cache_time = 0
        self._price_ttl = 2  # Cache price for 2 seconds
        
        self._ohlcv_cache = {} # Key: (timeframe, limit, since)
        self._ohlcv_ttl = 5    # Default TTL for non-1m frames
        self._ohlcv_1m_ttl = 60  # Cache 1m OHLCV for 60 seconds
        
        logger.info(f"Initialized Binance Vision Collector for {self.symbol} with proxies: {proxies}")

    def set_proxy(self, proxy_url):
        if proxy_url:
            self.proxies = {
                "http": proxy_url,
                "https": proxy_url
            }
        else:
            self.proxies = {}
        
        self.session.proxies.update(self.proxies if self.proxies else {})
        logger.info(f"Updated proxies to: {self.proxies}")

    def fetch_current_price(self):
        """Fetch current ticker data using Binance Vision API with fallback"""
        # Check cache
        if time.time() - self._price_cache_time < self._price_ttl and self._price_cache:
            return self._price_cache

        try:
            url = f"{self.base_url}/ticker/24hr?symbol={self.symbol}"
            resp = self.session.get(url, timeout=5)
            if resp.status_code == 200:
                ticker = resp.json()
                price = float(ticker['lastPrice'])
                self.last_valid_price = price  # Update valid price
                
                result = {
                    'timestamp': int(time.time() * 1000),
                    'datetime': datetime.now().isoformat(),
                    'last': price,
                    'high': float(ticker['highPrice']),
                    'low': float(ticker['lowPrice']),
                    'volume': float(ticker['quoteVolume']),
                    'price_change': float(ticker.get('priceChange', 0.0)),
                    'price_change_percent': float(ticker.get('priceChangePercent', 0.0)),
                    'source': 'api'
                }
                
                # Update cache
                self._price_cache = result
                self._price_cache_time = time.time()
                
                return result
            else:
                logger.warning(f"Error fetching ticker: {resp.status_code}. Return None.")
                return None
        except Exception as e:
            logger.warning(f"Exception fetching ticker: {e}. Return None.")
            return None

    def _generate_dummy_ticker(self):
        """Generate a realistic looking dummy ticker based on recent data or random walk"""
        # Use last valid price instead of hardcoded 104000
        base_price = self.last_valid_price 
        random_move = (np.random.random() - 0.5) * 100
        price = base_price + random_move
        
        return {
            'timestamp': int(time.time() * 1000),
            'datetime': datetime.now().isoformat(),
            'last': price,
            'high': price + 500,
            'low': price - 500,
            'volume': 1000000.0,
            'price_change': random_move,
            'price_change_percent': (random_move / base_price) * 100,
            'source': 'dummy'
        }

    def fetch_ohlcv(self, timeframe='1h', limit=100, since=None):
        """
        Fetch historical OHLCV data via REST with fallback
        Supports '10m' by resampling '5m' data.
        """
        # Handle 10m timeframe (not supported by Binance natively)
        if timeframe == '10m':
            # Check cache for 10m explicitly if needed, but since it calls 5m, 
            # we rely on 5m cache or add specific cache here.
            # Let's add specific cache for 10m to avoid re-computation
            cache_key = (timeframe, limit, since)
            if cache_key in self._ohlcv_cache:
                ts, data = self._ohlcv_cache[cache_key]
                if time.time() - ts < self._ohlcv_ttl:
                    return data.copy()

            logger.info("Resampling 5m data for 10m timeframe...")
            # Fetch 2x limit of 5m data to ensure enough coverage
            df_5m = self.fetch_ohlcv(timeframe='5m', limit=limit * 2, since=since)
            if df_5m.empty:
                return df_5m
                
            # Resample logic
            df_5m['datetime'] = pd.to_datetime(df_5m['timestamp'], unit='ms')
            df_5m.set_index('datetime', inplace=True)
            
            ohlc_dict = {
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }
            
            df_10m = df_5m.resample('10min').agg(ohlc_dict)
            df_10m.dropna(inplace=True)
            
            # Reset index and restore timestamp
            df_10m.reset_index(inplace=True)
            df_10m['timestamp'] = df_10m['datetime'].astype(np.int64) // 10**6
            
            # Keep only requested limit
            result_df = df_10m.iloc[-limit:].reset_index(drop=True)
            
            # Cache result
            self._ohlcv_cache[cache_key] = (time.time(), result_df)
            return result_df.copy()

        # Check cache for standard timeframes
        cache_key = (timeframe, limit, since)
        if cache_key in self._ohlcv_cache:
            ts, data = self._ohlcv_cache[cache_key]
            ttl = self._ohlcv_1m_ttl if timeframe == '1m' else self._ohlcv_ttl
            if time.time() - ts < ttl:
                return data.copy()

        try:
            params = {
                'symbol': self.symbol,
                'interval': timeframe,
                'limit': limit
            }
            if since:
                params['startTime'] = since
                
            url = f"{self.base_url}/klines"
            resp = self.session.get(url, params=params, timeout=10)
            
            if resp.status_code != 200:
                logger.warning(f"API Error: {resp.status_code}. Return Empty DF.")
                return pd.DataFrame()
                
            data = resp.json()
            if not data:
                return pd.DataFrame()

            parsed_data = []
            for candle in data:
                parsed_data.append([
                    candle[0], # timestamp
                    float(candle[1]), # open
                    float(candle[2]), # high
                    float(candle[3]), # low
                    float(candle[4]), # close
                    float(candle[5]), # volume
                    float(candle[7]), # quote_volume
                    float(candle[9]), # taker_buy_volume
                    float(candle[10]) # taker_buy_quote_volume
                ])
                
            df = pd.DataFrame(parsed_data, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume', 
                'quote_volume', 'taker_buy_volume', 'taker_buy_quote_volume'
            ])
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # Cache result
            self._ohlcv_cache[cache_key] = (time.time(), df)
            
            return df.copy()
        except Exception as e:
            logger.warning(f"Error fetching OHLCV: {e}. Return Empty DF.")
            return pd.DataFrame()

    def fetch_order_book(self, limit=10):
        """Fetch current order book depth"""
        try:
            url = f"{self.base_url}/depth?symbol={self.symbol}&limit={limit}"
            resp = self.session.get(url, timeout=5)
            if resp.status_code == 200:
                return resp.json()
            else:
                logger.warning(f"Error fetching Order Book: {resp.status_code}")
                return None
        except Exception as e:
            logger.warning(f"Exception fetching Order Book: {e}")
            return None

    def _generate_dummy_ohlcv(self, limit, timeframe):
        """Generate dummy OHLCV data"""
        end_time = int(time.time() * 1000)
        
        # Determine interval in ms
        interval_map = {
            '1m': 60000,
            '5m': 300000,
            '15m': 900000,
            '30m': 1800000,
            '1h': 3600000,
            '4h': 14400000,
            '1d': 86400000
        }
        interval_ms = interval_map.get(timeframe, 3600000)
        
        timestamps = [end_time - (i * interval_ms) for i in range(limit)]
        timestamps.reverse()
        
        # Random walk
        base_price = 104000.0
        data = []
        
        current_price = base_price
        for ts in timestamps:
            move = np.random.normal(0, 50)
            open_p = current_price
            close_p = open_p + move
            high_p = max(open_p, close_p) + abs(np.random.normal(0, 20))
            low_p = min(open_p, close_p) - abs(np.random.normal(0, 20))
            volume = abs(np.random.normal(1000, 200))
            
            data.append([ts, open_p, high_p, low_p, close_p, volume])
            current_price = close_p
            
        df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df

    def fetch_data_range(self, start_ts, end_ts, timeframe='1m'):
        """
        Fetch data for a specific time range with pagination.
        start_ts, end_ts: timestamps in milliseconds
        """
        logger.info(f"Fetching data from {datetime.fromtimestamp(start_ts/1000)} to {datetime.fromtimestamp(end_ts/1000)}")
        all_ohlcv = []
        limit = 1000
        since = start_ts
        
        while since < end_ts:
            try:
                # Ensure we don't go beyond end_ts
                # But fetch_ohlcv logic relies on 'since' and limit. 
                # We can just fetch and filter later or just stop when we pass end_ts.
                
                df_batch = self.fetch_ohlcv(timeframe, limit=limit, since=since)
                if df_batch.empty:
                    break
                
                # Filter out data beyond end_ts if necessary, 
                # but fetch_ohlcv returns 1000 candles starting from 'since'.
                # So just check the last timestamp.
                
                raw_batch = df_batch[['timestamp', 'open', 'high', 'low', 'close', 'volume', 'quote_volume', 'taker_buy_volume', 'taker_buy_quote_volume']].values.tolist()
                
                # Filter duplicate/overlap if any (though 'since' logic should prevent it)
                if all_ohlcv and raw_batch[0][0] <= all_ohlcv[-1][0]:
                     # Skip overlap
                     raw_batch = [r for r in raw_batch if r[0] > all_ohlcv[-1][0]]
                
                if not raw_batch:
                    break
                    
                all_ohlcv.extend(raw_batch)
                last_time = raw_batch[-1][0]
                
                # Update 'since'
                since = int(last_time) + 1
                
                if len(raw_batch) < limit:
                    # End of available data
                    break
                
                # Rate limit
                time.sleep(0.2)
                
            except Exception as e:
                logger.error(f"Error fetching batch: {e}")
                time.sleep(2)
        
        if not all_ohlcv:
            return pd.DataFrame()
            
        df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        # Final filter to ensure range
        df = df[(df['timestamp'] >= start_ts) & (df['timestamp'] <= end_ts)]
        
        return df

    def fetch_historical_data(self, timeframe='1m', days=30):
        """
        Fetch a large amount of historical data with pagination
        """
        logger.info(f"Starting download of {days} days of {timeframe} data for {self.symbol}...")
        all_ohlcv = []
        limit = 1000  # Max limit for Binance
        
        # Calculate start time
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        since = int(start_time.timestamp() * 1000)
        
        while True:
            try:
                df_batch = self.fetch_ohlcv(timeframe, limit=limit, since=since)
                if df_batch.empty:
                    break
                
                ohlcv = df_batch.values.tolist()
                # Need to convert back to raw list for extending or just use df
                # But to keep logic similar, let's just append to a list of dicts or rows
                
                # Simpler: just concat DFs
                # But let's stick to list for loop loop
                
                # We need to extract the raw rows: [timestamp, open, high, low, close, volume]
                # df_batch has 'datetime' col which we don't need in raw list
                raw_batch = df_batch[['timestamp', 'open', 'high', 'low', 'close', 'volume', 'quote_volume', 'taker_buy_volume', 'taker_buy_quote_volume']].values.tolist()
                
                all_ohlcv.extend(raw_batch)
                last_time = raw_batch[-1][0]
                logger.info(f"Fetched {len(raw_batch)} candles, last candle: {datetime.fromtimestamp(last_time/1000)}")
                
                # Update 'since'
                since = int(last_time) + 1
                
                if len(raw_batch) < limit:
                    break
                
                # Rate limit sleep
                time.sleep(0.5) 
                
                if last_time > int(end_time.timestamp() * 1000):
                    break
                    
            except Exception as e:
                logger.error(f"Error fetching history batch: {e}")
                time.sleep(5)
                
        if not all_ohlcv:
            return pd.DataFrame()
            
        df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'quote_volume', 'taker_buy_volume', 'taker_buy_quote_volume'])
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df.drop_duplicates(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)
        
        logger.info(f"Completed download. Total {len(df)} rows.")
        return df


    def get_market_status(self):
        """Get exchange status"""
        try:
            url = f"{self.base_url}/ping"
            resp = self.session.get(url, timeout=5)
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"Error fetching status: {e}")
            return False

class FuturesDataCollector(CryptoDataCollector):
    def __init__(self, symbol='BTCUSDT', proxies=None):
        super().__init__(symbol, proxies)
        self.base_url = "https://fapi.binance.com/fapi/v1"
        
        # Additional caches for futures data
        self._funding_cache = {}
        self._oi_cache = {}
        self._futures_ttl = 60 # 1 minute cache
        
        logger.info(f"Initialized Binance Futures Collector for {self.symbol}")

    def fetch_all_tickers(self):
        """Fetch 24h ticker data for ALL symbols (Cost: 40)"""
        try:
            url = f"{self.base_url}/ticker/24hr"
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 200:
                return resp.json()
            else:
                logger.warning(f"Error fetching all tickers: {resp.status_code}")
                return []
        except Exception as e:
            logger.error(f"Exception fetching all tickers: {e}")
            return []

    def fetch_funding_rate_history(self, start_time=None, end_time=None, limit=1000):
        """Fetch funding rate history"""
        # Check cache
        cache_key = (start_time, end_time, limit)
        if cache_key in self._funding_cache:
            ts, data = self._funding_cache[cache_key]
            if time.time() - ts < self._futures_ttl:
                return data.copy()

        try:
            url = f"{self.base_url}/fundingRate"
            params = {'symbol': self.symbol, 'limit': limit}
            if start_time:
                params['startTime'] = start_time
            if end_time:
                params['endTime'] = end_time
                
            resp = self.session.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                df = pd.DataFrame(data)
                if not df.empty:
                    df['fundingTime'] = pd.to_datetime(df['fundingTime'], unit='ms')
                    df['fundingRate'] = df['fundingRate'].astype(float)
                
                # Cache result
                self._funding_cache[cache_key] = (time.time(), df)
                return df.copy()
            else:
                logger.error(f"Error fetching funding rate: {resp.text}")
                return pd.DataFrame()
        except Exception as e:
            logger.error(f"Exception fetching funding rate: {e}")
            return pd.DataFrame()

    def fetch_open_interest_history(self, period='1h', limit=500, start_time=None, end_time=None):
        """Fetch Open Interest Statistics"""
        # Check cache
        cache_key = (period, limit, start_time, end_time)
        if cache_key in self._oi_cache:
            ts, data = self._oi_cache[cache_key]
            if time.time() - ts < self._futures_ttl:
                return data.copy()

        try:
            # Note: openInterestHist is for valid periods: 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d
            # Endpoint is /futures/data/openInterestHist, not /fapi/v1/...
            url = "https://fapi.binance.com/futures/data/openInterestHist"
            params = {'symbol': self.symbol, 'period': period, 'limit': limit}
            if start_time:
                params['startTime'] = start_time
            if end_time:
                params['endTime'] = end_time
                
            resp = requests.get(url, params=params, proxies=self.proxies, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                df = pd.DataFrame(data)
                if not df.empty:
                    df['timestamp'] = df['timestamp'].astype(int)
                    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
                    df['sumOpenInterest'] = df['sumOpenInterest'].astype(float)
                    df['sumOpenInterestValue'] = df['sumOpenInterestValue'].astype(float)
                
                # Cache result
                self._oi_cache[cache_key] = (time.time(), df)
                return df.copy()
            else:
                logger.error(f"Error fetching open interest: {resp.text}")
                return pd.DataFrame()
        except Exception as e:
            logger.error(f"Exception fetching open interest: {e}")
            return pd.DataFrame()

if __name__ == "__main__":
    # Test usage
    collector = CryptoDataCollector()

    price = collector.fetch_current_price()
    print(f"Current Price: {price}")
    
    history = collector.fetch_ohlcv(limit=5)
    print("\nRecent History:")
    print(history.tail())
