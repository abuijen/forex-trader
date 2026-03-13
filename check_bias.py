"""
check_bias.py
─────────────
Diagnostic: checks the label distribution in the training data
and compares it with current live predictions.
"""

import MetaTrader5 as mt5
import pandas as pd
from config import MT5_PATH, SYMBOLS, TRAIN_BARS
from data.data_feed import get_data
from strategy.ml_strategy import create_features, create_labels, MLModel

# ── Connect ──────────────────────────────────────────────────
kwargs = {"path": MT5_PATH} if MT5_PATH else {}
if not mt5.initialize(**kwargs):
    print("MT5 init failed")
    exit()

# ── Check Label Distribution for Training ───────────────────
print("=== Training Data Label Distribution (EURUSD) ===")
df_train = get_data("EURUSD", mt5.TIMEFRAME_M5, bars=TRAIN_BARS)
df_t = create_features(df_train)
labels = create_labels(df_t)
counts = labels.value_counts()
percent = labels.value_counts(normalize=True)
print(f"Total bars: {len(labels)}")
print("Label 0 (Sell):", counts.get(0, 0), f"({percent.get(0, 0):.2%})")
print("Label 1 (Buy) :", counts.get(1, 0), f"({percent.get(1, 0):.2%})")


# ── Load and Check Model ────────────────────────────────────
model = MLModel.load()
if model.is_trained:
    print("\n=== Current Live Predictions ===")
    for symbol in SYMBOLS:
        df = get_data(symbol, mt5.TIMEFRAME_M5, bars=500)
        df = create_features(df)
        sig, prob = model.predict(df)

        
        # Get raw probabilities
        row = df[model.pipeline.feature_names_in_].iloc[[-1]]
        probs = model.pipeline.predict_proba(row)[0]
        
        print(f"{symbol}: Signal={sig}, Prob={prob:.2f} | Raw: Sell={probs[0]:.2f}, Buy={probs[1]:.2f}")

mt5.shutdown()
