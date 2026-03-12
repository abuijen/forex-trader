import pandas as pd
import numpy as np
from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange

def create_features(df):

    df["ema50"] = EMAIndicator(df["close"],50).ema_indicator()
    df["ema200"] = EMAIndicator(df["close"],200).ema_indicator()

    df["rsi"] = RSIIndicator(df["close"],14).rsi()

    atr = AverageTrueRange(df["high"],df["low"],df["close"],14)

    df["atr"] = atr.average_true_range()

    df["return"] = df["close"].pct_change()

    df.dropna(inplace=True)

    return df