import requests
from config import BRIDGE_URL

def send_trade(symbol, signal, lot, sl, tp):
    # Get current price from bridge
    tick_response = requests.get(f"{BRIDGE_URL}/tick", params={"symbol": symbol})
    tick = tick_response.json()
    price = tick["ask"] if signal == "buy" else tick["bid"]

    # Send trade request to bridge
    payload = {
        "action": "trade",
        "symbol": symbol,
        "volume": lot,
        "type": "buy" if signal == "buy" else "sell",
        "price": price,
        "sl": sl,
        "tp": tp,
        "comment": "Pro AI Forex Bot"
    }
    
    response = requests.post(f"{BRIDGE_URL}/execute", json=payload)
    return response.json()