import time
import requests
from config import *
from data.data_feed import get_data
from strategy.ml_strategy import create_features
from risk.risk_manager import lot_size
from execution.mt5_executor import send_trade

# Timeframe mapping (assuming bridge follows MT5 standard integers or strings)
TIMEFRAME_M5 = 5

while True:
    for symbol in SYMBOLS:
        try:
            df = get_data(symbol, TIMEFRAME_M5)
            df = create_features(df)
            last = df.iloc[-1]
            
            signal = None
            if last["ema50"] > last["ema200"] and last["rsi"] > 55:
                signal = "buy"
            elif last["ema50"] < last["ema200"] and last["rsi"] < 45:
                signal = "sell"

            if signal:
                atr = last["atr"]
                lot = lot_size(RISK_PERCENT)
                
                # Get current tick for SL/TP calculation
                tick_response = requests.get(f"{BRIDGE_URL}/tick", params={"symbol": symbol})
                tick = tick_response.json()
                price = tick["ask"] if signal == "buy" else tick["bid"]
                
                sl = price - atr * ATR_SL_MULT if signal == "buy" else price + atr * ATR_SL_MULT
                tp = price + atr * ATR_TP_MULT if signal == "buy" else price - atr * ATR_TP_MULT
                
                send_trade(symbol, signal, lot, sl, tp)
        except Exception as e:
            print(f"Error processing {symbol}: {e}")

    time.sleep(300)