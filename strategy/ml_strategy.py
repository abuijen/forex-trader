"""
ml_strategy.py
──────────────
Random-Forest-based feature engineering, training and prediction.
Supports live retraining from MT5 historical data.
"""

import os
import pickle
import numpy as np
import pandas as pd

from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator, ROCIndicator
from ta.volatility import AverageTrueRange, BollingerBands

from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import classification_report

from config import FEATURE_COLS, MODEL_FILE, N_ESTIMATORS, RF_MAX_DEPTH


# ─────────────────────────────────────────────────────────────────────────────
#  Feature Engineering
# ─────────────────────────────────────────────────────────────────────────────

def create_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add technical-indicator and price-action features to *df*.
    Expects columns: open, high, low, close, volume.
    All NaN rows are dropped at the end.
    """
    df = df.copy()

    # ── Trend ───────────────────────────────────────────────────────────────
    df["ema50"]  = EMAIndicator(df["close"], 50).ema_indicator()
    df["ema200"] = EMAIndicator(df["close"], 200).ema_indicator()
    df["ema_diff"] = (df["ema50"] - df["ema200"]) / df["close"]   # normalised

    # ── Momentum ────────────────────────────────────────────────────────────
    df["rsi"]   = RSIIndicator(df["close"], 14).rsi()
    df["roc_5"] = ROCIndicator(df["close"], 5).roc()
    df["roc_10"]= ROCIndicator(df["close"], 10).roc()

    # ── Volatility ──────────────────────────────────────────────────────────
    atr = AverageTrueRange(df["high"], df["low"], df["close"], 14)
    df["atr"] = atr.average_true_range()
    df["atr_pct"] = df["atr"] / df["close"] * 100

    bb  = BollingerBands(df["close"], 20, 2)
    df["bb_width"] = (bb.bollinger_hband() - bb.bollinger_lband()) / df["close"]

    df["volatility"] = df["close"].pct_change().rolling(10).std()

    # ── Price Change & Lags ──────────────────────────────────────────────── 
    df["pct_change"] = df["close"].pct_change()
    df["lag1"] = df["pct_change"].shift(1)
    df["lag2"] = df["pct_change"].shift(2)
    df["lag3"] = df["pct_change"].shift(3)

    # ── Candle Shape ────────────────────────────────────────────────────────
    rng = (df["high"] - df["low"]).replace(0, np.nan)
    df["body"]        = abs(df["close"] - df["open"]) / rng
    df["upper_wick"]  = (df["high"] - df[["close","open"]].max(axis=1)) / rng
    df["lower_wick"]  = (df[["close","open"]].min(axis=1) - df["low"]) / rng

    df.dropna(inplace=True)
    return df


# ─────────────────────────────────────────────────────────────────────────────
#  Label Generation
# ─────────────────────────────────────────────────────────────────────────────

def create_labels(df: pd.DataFrame, forward_bars: int = 3) -> pd.Series:
    """
    Simple forward-return label:
        1 (buy)   if price rises > 0 over next *forward_bars* bars
        0 (sell)  otherwise
    """
    future_return = df["close"].shift(-forward_bars) / df["close"] - 1
    labels = (future_return > 0).astype(int)
    return labels


# ─────────────────────────────────────────────────────────────────────────────
#  MLModel
# ─────────────────────────────────────────────────────────────────────────────

class MLModel:
    """Wraps a scikit-learn Pipeline (StandardScaler + RandomForest)."""

    def __init__(self):
        self.pipeline: Pipeline | None = None
        self.is_trained: bool = False

    # ── Training ─────────────────────────────────────────────────────────────
    def train(self, dfs: list[pd.DataFrame]) -> None:
        """
        Train on a list of DataFrames which must already have features attached.
        Labels are generated internally per-symbol before concatenation.
        """
        X_list = []
        y_list = []
        
        for df in dfs:
            if df.empty or len(df) <= 3:
                continue
            labels = create_labels(df)
            
            # Align: drop last rows where label would be NaN
            X = df[FEATURE_COLS].iloc[:-3]
            y = labels.iloc[:-3]

            # Drop any remaining NaN
            mask = X.notna().all(axis=1) & y.notna()
            X_list.append(X[mask])
            y_list.append(y[mask])

        if not X_list:
            print("[MLModel] Not enough data to train.")
            return
            
        X_all = pd.concat(X_list, ignore_index=True)
        y_all = pd.concat(y_list, ignore_index=True)

        if len(X_all) < 100:
            print("[MLModel] Not enough combined data to train.")
            return

        self.pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("clf",    RandomForestClassifier(
                n_estimators = N_ESTIMATORS,
                max_depth    = RF_MAX_DEPTH,
                class_weight = "balanced",
                n_jobs       = -1,
                random_state = 42,
            )),
        ])

        self.pipeline.fit(X_all, y_all)
        self.is_trained = True

        # Quick in-sample report
        preds = self.pipeline.predict(X_all)
        print("[MLModel] Training complete.")
        print(classification_report(y_all, preds, zero_division=0))

    # ── Prediction ───────────────────────────────────────────────────────────
    def predict(self, df: pd.DataFrame):
        """
        Return (signal, probability) for the last row of *df*.
        signal: 'buy' | 'sell' | None
        probability: float  (confidence of the predicted class)
        """
        if not self.is_trained or self.pipeline is None:
            return None, 0.0

        from config import MIN_SIGNAL_PROB
        row = df[FEATURE_COLS].iloc[[-1]]
        if row.isna().any().any():
            return None, 0.0

        prob_arr = self.pipeline.predict_proba(row)[0]
        class_idx = int(np.argmax(prob_arr))
        prob = float(prob_arr[class_idx])

        if prob < MIN_SIGNAL_PROB:
            return None, prob

        signal = "buy" if class_idx == 1 else "sell"
        return signal, prob

    # ── Persistence ──────────────────────────────────────────────────────────
    def save(self, path: str = MODEL_FILE) -> None:
        with open(path, "wb") as f:
            pickle.dump(self, f)
        print(f"[MLModel] Model saved to '{path}'")

    @classmethod
    def load(cls, path: str = MODEL_FILE) -> "MLModel":
        if not os.path.exists(path):
            print(f"[MLModel] No saved model at '{path}' – starting fresh.")
            return cls()
        with open(path, "rb") as f:
            model = pickle.load(f)
        model.is_trained = True
        print(f"[MLModel] Model loaded from '{path}'")
        return model