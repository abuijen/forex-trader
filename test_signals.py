"""
test_signals.py
───────────────
Diagnostic script: connects to MT5, loads (or trains) the model,
and checks whether buy/sell signals can be generated for each symbol.
Does NOT place real trades — prints what WOULD be sent.
"""

import sys
import MetaTrader5 as mt5

from config import MT5_PATH, SYMBOLS, ATR_SL_MULT, ATR_TP_MULT, MIN_SIGNAL_PROB
from data.data_feed import get_data
from strategy.ml_strategy import create_features, MLModel
from risk.risk_manager import lot_size

print("=" * 60)
print("  ML Forex Bot — Signal Diagnostic")
print("=" * 60)

# ── Connect ──────────────────────────────────────────────────
kwargs = {"path": MT5_PATH} if MT5_PATH else {}
if not mt5.initialize(**kwargs):
    print(f"[ERROR] MT5 init failed: {mt5.last_error()}")
    sys.exit(1)

ai = mt5.account_info()
print(f"\n✅  Connected  |  Account #{ai.login}  |  Balance: {ai.balance:.2f} {ai.currency}\n")

# ── Load model ───────────────────────────────────────────────
model = MLModel.load()
if not model.is_trained:
    print("⚠️  No saved model — training now on EURUSD …")
    df_train = get_data("EURUSD", mt5.TIMEFRAME_M5, bars=5000)
    df_train = create_features(df_train)
    model.train(df_train)
    model.save()

# ── Test signals ─────────────────────────────────────────────
print(f"{'Symbol':<10} {'Signal':<8} {'Prob':>6}  {'Lot':>6}  {'SL':>10}  {'TP':>10}")
print("-" * 60)

any_signal = False
for symbol in SYMBOLS:
    df = get_data(symbol, mt5.TIMEFRAME_M5, bars=500)
    if df.empty:
        print(f"{symbol:<10}  ⚠️  No data")
        continue

    df = create_features(df)
    if len(df) < 10:
        print(f"{symbol:<10}  ⚠️  Too few rows after feature engineering")
        continue

    signal, prob = model.predict(df)

    last = df.iloc[-1]
    atr  = last["atr"]

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        print(f"{symbol:<10}  ⚠️  Cannot get tick")
        continue

    info  = mt5.symbol_info(symbol)
    point = info.point

    if signal == "buy":
        price = tick.ask
        sl = price - atr * ATR_SL_MULT
        tp = price + atr * ATR_TP_MULT
    elif signal == "sell":
        price = tick.bid
        sl = price + atr * ATR_SL_MULT
        tp = price - atr * ATR_TP_MULT
    else:
        # No signal — show raw probabilities anyway
        proba = model.pipeline.predict_proba(df[model.pipeline.feature_names_in_ if hasattr(model.pipeline, 'feature_names_in_') else []].iloc[[-1]]) if model.pipeline else [[0.5, 0.5]]
        print(f"{symbol:<10}  {'–':<8}  {prob:>5.1%}  (below threshold {MIN_SIGNAL_PROB:.0%})")
        continue

    sl_pips = abs(price - sl) / point / 10
    lot     = lot_size(symbol, sl_pips)

    print(f"{symbol:<10}  {signal.upper():<8}  {prob:>5.1%}  {lot:>6.2f}  {sl:>10.5f}  {tp:>10.5f}")
    any_signal = True

print("-" * 60)
if any_signal:
    print("\n✅  Signals found — bot would place the trades above.")
else:
    print("\n⏳  No signals above threshold right now (this is normal).")
    print(f"    Tip: lower MIN_SIGNAL_PROB in config.py (currently {MIN_SIGNAL_PROB:.0%}) to see more signals.")

mt5.shutdown()
