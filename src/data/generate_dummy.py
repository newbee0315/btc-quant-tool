import pandas as pd
import numpy as np
import time

def generate_dummy_data():
    end_time = int(time.time() * 1000)
    # 14 days of data
    start_time = end_time - (14 * 24 * 60 * 60 * 1000)
    
    timestamps = np.arange(start_time, end_time, 60000) # 1m interval
    n = len(timestamps)
    
    # Generate random walk price
    price = 50000 + np.cumsum(np.random.randn(n) * 10)
    
    data = {
        'timestamp': timestamps,
        'datetime': pd.to_datetime(timestamps, unit='ms'),
        'open': price,
        'high': price + np.random.rand(n) * 50,
        'low': price - np.random.rand(n) * 50,
        'close': price + np.random.randn(n) * 10,
        'volume': np.random.rand(n) * 100
    }
    
    df = pd.DataFrame(data)
    df.to_csv('src/data/btc_history_1m.csv', index=False)
    print(f"Generated {n} dummy records to src/data/btc_history_1m.csv")

if __name__ == "__main__":
    generate_dummy_data()