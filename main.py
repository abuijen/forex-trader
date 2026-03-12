import MetaTrader5 as mt5
import time

from config import *
from data.data_feed import get_data
from strategy.ml_strategy import create_features
from risk.risk_manager import lot_size
from execution.mt5_executor import send_trade

mt5.initialize()

while True:
    for symbol in SYMBOLS:
        df = get_data(symbol, mt5.TIMEFRAME_M5)
        df = create_features(df)
        last = df.iloc[-1]
        signal = None
        if last["ema50"] > last["ema200"] and last["rsi"] > 55:
            signal = "buy"
        if last["ema50"] < last["ema200"] and last["rsi"] < 45:
            signal = "sell"
        if signal:
            atr = last["atr"]
            lot = lot_size(RISK_PERCENT)
            price = mt5.symbol_info_tick(symbol).ask
            sl = price - atr*ATR_SL_MULT if signal=="buy" else price + atr*ATR_SL_MULT
            tp = price + atr*ATR_TP_MULT if signal=="buy" else price - atr*ATR_TP_MULT
            send_trade(symbol, signal, lot, sl, tp)
    time.sleep(300)