import MetaTrader5 as mt5
import pandas as pd


def get_data(symbol: str, timeframe: int, bars: int = 5000) -> pd.DataFrame:
    """Fetch OHLCV bars from MT5 for *symbol* on *timeframe*."""
    if not mt5.symbol_select(symbol, True):
        print(f"[data_feed] ERROR: Cannot select symbol '{symbol}'")
        return pd.DataFrame()

    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
    if rates is None or len(rates) == 0:
        print(f"[data_feed] ERROR: No data for '{symbol}'")
        return pd.DataFrame()

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)

    # Rename to lower-case standard OHLCV names
    df.rename(columns={
        "tick_volume": "volume",
        "real_volume": "real_volume",
    }, inplace=True)

    return df[["open", "high", "low", "close", "volume"]].copy()