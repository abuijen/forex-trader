# ─────────────────────────────────────────────
#  FOREX ML SCALPING BOT  –  Configuration
# ─────────────────────────────────────────────

# ── MT5 Connection ───────────────────────────
# Use the absolute path to your terminal64.exe
MT5_PATH = "C:\\Program Files\\MetaTrader 5\\terminal64.exe"
MT5_LOGIN  = 0          # 0 = use already-logged-in terminal
MT5_PASSWORD = ""
MT5_SERVER   = ""

# ── Symbols & Timeframe ───────────────────────
SYMBOLS   = ["EURUSD", "GBPUSD"]
# SYMBOLS are Gold-USD, Gold-EUR, OIL-USD, BTC-USD, ETH-USD
# Reserve SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "EURCHF", "XAUUSD", "XAUEUR","XTIUSD"]
TIMEFRAME = 5           # minutes (M5)

# ── Risk Management ───────────────────────────
RISK_PERCENT        = 1     # % of balance risked per trade
MAX_TRADES_PER_PAIR = 3
SPREAD_LIMIT        = 20    # max spread in points
MIN_LOT_SIZE        = 0.1   # minimum volume per trade
MAX_LOT_SIZE        = 1.0   # maximum volume per trade

# ── ATR Stops ────────────────────────────────
ATR_SL_MULT = 2.0
ATR_TP_MULT = 3.5

# ── ML Model ────────────────────────────────
MODEL_FILE        = "model.pkl"
TRAIN_BARS        = 5000    # bars used for initial training
RETRAIN_INTERVAL  = 4      # hours between automatic retrains
MIN_SIGNAL_PROB   = 0.65    # minimum predicted probability to act on a signal
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

# ── Trading Time Constraints ──────────────────
# Times are based on MT5 Server Time
TRADE_START_HOUR  = 0     # Start trading again at Midnight
TRADE_STOP_HOUR   = 20    # No new trades after 8 PM
CLOSE_PROFIT_HOUR = 23    # Close winning trades after 11 PM
CLOSE_ALL_HOUR    = 23    # Close all trades hour
CLOSE_ALL_MINUTE  = 30    # Close all trades at 11:30 PM

# ── Daily Profit Target ───────────────────────
DAILY_PROFIT_TARGET_PCT = 15.0  # Stop trading if daily profit > 15%
PROFIT_LOCK_THRESH      = 20.0  # Lock in profits above $20
PROFIT_LOCK_TP_TARGET   = 20.0  # Set TP to $20 profit for others

# ── Paper Trading (Strategy Tester) ──────────
PAPER_TRADING = False  # If True, use MT5 Strategy Tester instead of Live
TESTER_CONFIG_FILE = "tester.ini"