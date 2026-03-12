import MetaTrader5 as mt5

def lot_size(risk_percent):
    account = mt5.account_info()
    balance = account.balance
    risk = balance * (risk_percent / 100)
    lot = round(risk / 100,2)
    return max(lot,0.01)