import MetaTrader5 as mt5
from datetime import datetime, timezone
import sys

def main():
    if not mt5.initialize():
        print("MT5 init failed")
        return
    
    tick = mt5.symbol_info_tick('EURUSD')
    if tick:
        # What is the time in tick?
        t1 = datetime.fromtimestamp(tick.time)
        t2 = datetime.utcfromtimestamp(tick.time)
        
        print("tick.time epoch:", tick.time)
        print("fromtimestamp (Local shift):", t1, type(t1))
        print("utcfromtimestamp (No shift):", t2, type(t2))
        print("Current PC Local time:", datetime.now())
        print("Current PC UTC time:  ", datetime.now(timezone.utc))
        hour = t1.hour
        if not is_weekend:
            if TRADE_START_HOUR < TRADE_STOP_HOUR:
                in_window = TRADE_START_HOUR <= hour < TRADE_STOP_HOUR
            else: # Overnight window
                in_window = hour >= TRADE_START_HOUR or hour < TRADE_STOP_HOUR
                
        print(f"t1 hour: {hour}")
        print(f"in_window with fromtimestamp(): {in_window}")

        hour2 = t2.hour
        in_window2 = False
        if not is_weekend:
            if TRADE_START_HOUR < TRADE_STOP_HOUR:
                in_window2 = TRADE_START_HOUR <= hour2 < TRADE_STOP_HOUR
            else: # Overnight window
                in_window2 = hour2 >= TRADE_START_HOUR or hour2 < TRADE_STOP_HOUR
        print(f"t2 hour: {hour2}")
        print(f"in_window with utcfromtimestamp(): {in_window2}")

if __name__ == '__main__':
    main()
