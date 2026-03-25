"""
main.py
───────
24/7 ML Scalping Bot for MetaTrader 5.
– Trains / retrains a Random-Forest model on MT5 historical data.
– Generates buy/sell signals every scan cycle.
– Sends orders via mt5_executor with ATR-based SL/TP.
"""

import sys
import time
import traceback
import argparse
from datetime import datetime, timedelta, timezone

import MetaTrader5 as mt5

import config
from config import (
    MT5_PATH, SYMBOLS, TRAIN_BARS, TIMEFRAME,
    RETRAIN_INTERVAL, ATR_SL_MULT, ATR_TP_MULT,
    TRADE_START_HOUR, TRADE_STOP_HOUR,
    DAILY_PROFIT_TARGET_PCT
)
from data.data_feed import get_data
from strategy.ml_strategy import create_features, MLModel
from risk.risk_manager import lot_size
from execution.mt5_executor import send_trade, manage_trailing_stops, manage_time_based_closes, lock_in_profits
from execution.trade_sync import sync_closed_trades


# ─────────────────────────────────────────────────────────────────────────────
#  MT5 Initialisation
# ─────────────────────────────────────────────────────────────────────────────

def init_mt5() -> None:
    kwargs = {}
    if MT5_PATH:
        kwargs["path"] = MT5_PATH
    if not mt5.initialize(**kwargs):
        print(f"[main] MT5 init failed: {mt5.last_error()}")
        sys.exit(1)
    info = mt5.account_info()
    if info:
        print(f"[main] Connected – Account #{info.login}  Balance: {info.balance:.2f} {info.currency}")
    else:
        print("[main] WARNING: could not retrieve account info.")

def get_mt5_timeframe(tf_minutes: int) -> int:
    mapping = {
        1: mt5.TIMEFRAME_M1, 5: mt5.TIMEFRAME_M5, 15: mt5.TIMEFRAME_M15,
        30: mt5.TIMEFRAME_M30, 60: mt5.TIMEFRAME_H1, 240: mt5.TIMEFRAME_H4,
        1440: mt5.TIMEFRAME_D1
    }
    return mapping.get(tf_minutes, mt5.TIMEFRAME_M5)


# ─────────────────────────────────────────────────────────────────────────────
#  Training helper
# ─────────────────────────────────────────────────────────────────────────────

def train_model(model: MLModel) -> None:
    print(f"[main] Training model on all symbols ({TRAIN_BARS} bars each)…")
    tf = get_mt5_timeframe(TIMEFRAME)
    dfs = []
    
    for symbol in SYMBOLS:
        df = get_data(symbol, tf, bars=TRAIN_BARS)
        if df.empty:
            print(f"[main] No data for {symbol}, skipping in training.")
            continue
        df = create_features(df)
        if df.empty:
            continue
        dfs.append(df)
        
    if dfs:
        model.train(dfs)
        model.save()
    else:
        print("[main] No data available to train model.")


# ─────────────────────────────────────────────────────────────────────────────
#  Main loop
# ─────────────────────────────────────────────────────────────────────────────

def run() -> None:
    parser = argparse.ArgumentParser(description="ML Forex Bot")
    parser.add_argument("--tester", action="store_true", help="Run in Paper Trading (Tester) mode")
    args = parser.parse_args()

    # Override config if --tester is passed
    if args.tester:
        config.PAPER_TRADING = True
        print("[main] --tester flag detected. Overriding PAPER_TRADING to True.")

    init_mt5()

    # Load or train the model
    model = MLModel.load()
    if not model.is_trained:
        train_model(model)

    next_retrain = datetime.now(timezone.utc) + timedelta(hours=RETRAIN_INTERVAL)
    
    # Detect if running against a terminal
    terminal = mt5.terminal_info()
    if terminal:
        print(f"[main] Connected to Terminal: {terminal.name} (Build {terminal.build})")
    
    mode_str = "PAPER TRADING (TESTER)" if config.PAPER_TRADING else "LIVE TRADING"
    print(f"[main] Bot Mode: {mode_str}")

    # Track midnight retraining using server date
    server_info = mt5.symbol_info_tick(SYMBOLS[0])
    last_daily_retrain = datetime.fromtimestamp(server_info.time, timezone.utc).date() if server_info else datetime.now(timezone.utc).date()
    
    # Track daily profit target
    account = mt5.account_info()
    start_day_capital = account.balance if account else 0
    target_hit_today = False

    print("[main] Bot started. Press Ctrl+C to stop.\n")

    while True:
        try:
            # Fetch server time at start of loop to avoid scope errors
            tick0 = mt5.symbol_info_tick(SYMBOLS[0])
            if not tick0:
                time.sleep(1)
                continue
            server_time = datetime.fromtimestamp(tick0.time, timezone.utc)

            # ── Periodic retraining ────────────────────────────────────────
            if datetime.now(timezone.utc) >= next_retrain:
                train_model(model)
                next_retrain = datetime.now(timezone.utc) + timedelta(hours=RETRAIN_INTERVAL)

            # ── Midnight Retraining & Capital Reset ────────────────────────
            if server_time.date() > last_daily_retrain:
                print(f"[main] Midnight reached ({server_time.date()}).")
                train_model(model)
                last_daily_retrain = server_time.date()
                next_retrain = datetime.now(timezone.utc) + timedelta(hours=RETRAIN_INTERVAL)
                
                # Reset daily capital tracking
                account = mt5.account_info()
                start_day_capital = account.balance if account else start_day_capital
                target_hit_today = False
                print(f"[main] Daily capital reset to {start_day_capital:.2f}")

            # ── Daily Profit Target Check ──────────────────────────────────
            account = mt5.account_info()
            if account and not target_hit_today:
                # current equity includes open trades
                current_profit = account.equity - start_day_capital
                profit_pct = (current_profit / start_day_capital * 100) if start_day_capital > 0 else 0
                
                if profit_pct >= DAILY_PROFIT_TARGET_PCT:
                    print(f"🎯 [main] DAILY TARGET HIT: {profit_pct:.2f}% profit reached (${current_profit:.2f})")
                    lock_in_profits()
                    target_hit_today = True

            # ── Signal scanning ───────────────────────────────────────────
            # Weekend restriction: No trading on Saturday (5) or Sunday (6)
            is_weekend = server_time.weekday() >= 5
            
            in_window = False
            if not is_weekend:
                if TRADE_START_HOUR < TRADE_STOP_HOUR:
                    in_window = TRADE_START_HOUR <= server_time.hour < TRADE_STOP_HOUR
                else: # Overnight window
                    in_window = server_time.hour >= TRADE_START_HOUR or server_time.hour < TRADE_STOP_HOUR

            if target_hit_today:
                 # Already locked in, skip news signals
                 pass
            elif is_weekend:
                print(f"[main] Server time {server_time.strftime('%A %H:%M')}. Weekend - No trading.")
            elif not in_window:
                print(f"[main] Server time {server_time.strftime('%H:%M')} is outside trading window ({TRADE_START_HOUR:02}:00 - {TRADE_STOP_HOUR:02}:00). Skipping signal scanning.")
            else:
                tf = get_mt5_timeframe(TIMEFRAME)
                for symbol in SYMBOLS:
                    df = get_data(symbol, tf, bars=500)
                    if df.empty:
                        continue

                    df = create_features(df)
                    if df.empty or len(df) < 10:
                        continue

                    signal, prob = model.predict(df)

                    if signal is None:
                        continue

                    last     = df.iloc[-1]
                    atr      = last["atr"]
                    tick     = mt5.symbol_info_tick(symbol)
                    if tick is None:
                        continue

                    sym_info = mt5.symbol_info(symbol)
                    point    = sym_info.point

                    if signal == "buy":
                        price = tick.ask
                        sl    = price - atr * ATR_SL_MULT
                        tp    = price + atr * ATR_TP_MULT
                    else:
                        price = tick.bid
                        sl    = price + atr * ATR_SL_MULT
                        tp    = price - atr * ATR_TP_MULT

                    sl_pips = abs(price - sl) / point / 10
                    lot     = lot_size(symbol, sl_pips)

                    print(f"[main] {symbol}  {signal.upper()}  prob={prob:.2f}  "
                          f"lot={lot}  sl={sl:.5f}  tp={tp:.5f}")

                    send_trade(symbol, signal, lot, sl, tp, prob)

        except KeyboardInterrupt:
            print("\n[main] Stopped by user.")
            mt5.shutdown()
            break
        except Exception:
            print("[main] Unhandled exception – continuing after 10 s:")
            traceback.print_exc()

        # Sync closed trade results to CSV
        sync_closed_trades()

        # Manage active trailing stops
        manage_trailing_stops()
        
        # Manage time-based closes (Server Time)
        server_info = mt5.symbol_info_tick(SYMBOLS[0])
        if server_info:
            manage_time_based_closes(datetime.fromtimestamp(server_info.time, timezone.utc))

        time.sleep(30)  # scan every 30 seconds


if __name__ == "__main__":
    run()