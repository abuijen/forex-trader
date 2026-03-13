import MetaTrader5 as mt5

from config import RISK_PERCENT, MAX_LOT_SIZE, MIN_LOT_SIZE

def lot_size(symbol: str, sl_pips: float) -> float:
    """
    Calculate a risk-adjusted lot size.
    Falls back to MIN_LOT_SIZE if account info is unavailable.
    """
    account = mt5.account_info()
    if account is None:
        return MIN_LOT_SIZE

    balance = account.balance
    risk_amount = balance * (RISK_PERCENT / 100)

    # Pip value approximation: $10/pip for 1 standard lot on most USD pairs
    pip_value = 10.0
    if sl_pips > 0:
        lot = risk_amount / (sl_pips * pip_value)
    else:
        lot = MIN_LOT_SIZE

    # Clamp between the configured minimum and maximum
    return max(MIN_LOT_SIZE, min(round(lot, 2), MAX_LOT_SIZE))