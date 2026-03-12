import requests
from config import BRIDGE_URL

def lot_size(risk_percent):
    response = requests.get(f"{BRIDGE_URL}/account")
    account = response.json()
    balance = account["balance"]
    
    risk = balance * (risk_percent / 100)
    lot = round(risk / 100, 2)
    return max(lot, 0.01)