# ─────────────────────────────────────────────
#  FOREX ML SCALPING BOT  –  Configuration
# ─────────────────────────────────────────────

# ── MT5 Connection ───────────────────────────
MT5_PATH = "C:\\Program Files\\MetaTrader 5\\terminal64.exe"
MT5_LOGIN  = 0          # 0 = use already-logged-in terminal
MT5_PASSWORD = ""
MT5_SERVER   = ""

# ── Symbols & Timeframe ───────────────────────
SYMBOLS   = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "EURCHF"]
# SYMBOLS are Gold-USD, Gold-EUR, OIL-USD, BTC-USD, ETH-USD
# Reserve SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "EURCHF", "XAUUSD", "XAUEUR","XTIUSD"]
TIMEFRAME = 5           # minutes (M5)

# ── Risk Management ───────────────────────────
RISK_PERCENT        = 1     # % of balance risked per trade
MAX_TRADES_PER_PAIR = 2
SPREAD_LIMIT        = 20    # max spread in points
MIN_LOT_SIZE        = 0.1   # minimum volume per trade
MAX_LOT_SIZE        = 1.0   # maximum volume per trade

# ── ATR Stops ────────────────────────────────
ATR_SL_MULT = 1.5
ATR_TP_MULT = 2.5

# ── ML Model ────────────────────────────────
MODEL_FILE        = "model.pkl"
TRAIN_BARS        = 5000    # bars used for initial training
RETRAIN_INTERVAL  = 4      # hours between automatic retrains
MIN_SIGNAL_PROB   = 0.55    # minimum predicted probability to act on a signal
N_ESTIMATORS      = 1000    # Random Forest trees
RF_MAX_DEPTH      = 10

# Feature column names used by the model
FEATURE_COLS = [
    "rsi", "atr_pct", "ema_diff",
    "pct_change", "volatility",
    "roc_5", "roc_10",
    "lag1", "lag2", "lag3",
    "body", "upper_wick", "lower_wick",
    "bb_width",
]

# ── Logging & Dashboard ───────────────────────
LOG_FILE                  = "trades_log.csv"
DASHBOARD_UPDATE_INTERVAL = 5   # seconds

# ── Dynamic Trailing Stop Loss ────────────────
ENABLE_TRAILING_SL        = False
TRAILING_SL_TRIGGER_PCT   = 0.015    # % profit to move to break-even (+offset)
TRAILING_SL_BE_OFFSET_PCT = 0.01     # % offset above/below break-even to lock in
TRAILING_SL_STEP_PCT      = 0.01     # % step to trail after trigger

# ── ATR Trailing Stop ─────────────────────────
ENABLE_ATR_TRAILING       = False
ATR_TRAILING_MULT         = 2.0      # ATR multiplier for trailing stop