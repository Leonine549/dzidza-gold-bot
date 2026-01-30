# main.py

import requests

# Configuration for Binance API
BINANCE_API_URL = 'https://api.binance.com/api/v3'
GOLD_SYMBOL = 'XAUUSDT'  # Gold trading symbol in Binance

def fetch_gold_data():
    response = requests.get(f"{BINANCE_API_URL}/klines", params={
        'symbol': GOLD_SYMBOL,
        'interval': '1h',  # Fetch hourly data
        'limit': 100  # Fetch last 100 klines
    })
    data = response.json()
    
    # Parse the response to extract relevant information
    gold_data = []
    for entry in data:
        timestamp, open_price, high_price, low_price, close_price, volume, *_ = entry
        gold_data.append({
            'timestamp': timestamp,
            'open': float(open_price),
            'high': float(high_price),
            'low': float(low_price),
            'close': float(close_price),
            'volume': float(volume)
        })
    
    return gold_data

# Example usage of fetch_gold_data()
if __name__ == "__main__":
    gold_data = fetch_gold_data()
    print(gold_data)
