import requests
import pandas as pd
from config import BRIDGE_URL

def get_data(symbol, timeframe, bars=1000):
    params = {
        "action": "copy_rates",
        "symbol": symbol,
        "timeframe": timeframe,
        "count": bars
    }
    response = requests.get(f"{BRIDGE_URL}/data", params=params)
    data = response.json()
    
    df = pd.DataFrame(data)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df