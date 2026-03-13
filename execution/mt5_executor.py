"""
mt5_executor.py
───────────────
Order sending with spread check, position limiting and result logging.
"""

import csv
import os
from datetime import datetime, timezone

import math
import pandas as pd
import MetaTrader5 as mt5

from config import SPREAD_LIMIT, MAX_TRADES_PER_PAIR, LOG_FILE


def _log_trade(symbol: str, signal: str, lot: float,
               price: float, sl: float, tp: float,
               result, prob: float) -> None:
    """Append a trade record to LOG_FILE (CSV)."""
    file_exists = os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "time", "symbol", "signal", "lot",
                "price", "sl", "tp", "prob",
                "retcode", "order", "result", "pnl"
            ])
        retcode = result.retcode if result else -1
        order   = result.order  if result else 0
        writer.writerow([
            datetime.now(timezone.utc).isoformat(), symbol, signal,
            lot, price, sl, tp, round(prob, 4),
            retcode, order, "", ""
        ])


def _count_open_positions(symbol: str) -> int:
    positions = mt5.positions_get(symbol=symbol)
    return len(positions) if positions else 0


def _get_filling_mode(symbol: str) -> int:
    """Detect the supported filling mode for this broker/symbol."""
    info = mt5.symbol_info(symbol)
    if info is None:
        return mt5.ORDER_FILLING_IOC
    
    filling = info.filling_mode
    if filling & 1: # SYMBOL_FILLING_FOK
        return mt5.ORDER_FILLING_FOK
    elif filling & 2: # SYMBOL_FILLING_IOC
        return mt5.ORDER_FILLING_IOC
    else:
        return mt5.ORDER_FILLING_RETURN



def send_trade(symbol: str, signal: str, lot: float,
               sl: float, tp: float, prob: float = 1.0):
    """
    Send a market order.
    Returns mt5.order_send result, or None on pre-flight failure.
    """
    # ── Guard: too many positions already open ────────────────────────────
    if _count_open_positions(symbol) >= MAX_TRADES_PER_PAIR:
        print(f"[executor] {symbol}: max open positions reached, skipping.")
        return None

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        print(f"[executor] {symbol}: cannot get tick, aborting.")
        return None

    # ── Guard: spread too wide ────────────────────────────────────────────
    info = mt5.symbol_info(symbol)
    spread = (tick.ask - tick.bid) / info.point
    if spread > SPREAD_LIMIT:
        print(f"[executor] {symbol}: spread {spread:.0f} pts > limit, skipping.")
        return None

    price = tick.ask if signal == "buy" else tick.bid
    filling = _get_filling_mode(symbol)

    request = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       symbol,
        "volume":       lot,
        "type":         mt5.ORDER_TYPE_BUY if signal == "buy" else mt5.ORDER_TYPE_SELL,
        "price":        price,
        "sl":           round(sl, info.digits),
        "tp":           round(tp, info.digits),
        "deviation":    20,
        "magic":        202400,
        "comment":      f"ML-Bot p={prob:.2f}",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": filling,
    }


    result = mt5.order_send(request)

    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        rc = result.retcode if result else "None"
        print(f"[executor] {symbol} {signal} FAILED  retcode={rc}")
    else:
        print(f"[executor] {symbol} {signal} OK  order={result.order}  lot={lot}  prob={prob:.2f}")

    _log_trade(symbol, signal, lot, price, sl, tp, result, prob)
    return result


def manage_trailing_stops():
    """
    Scan all open positions with Magic Number 202400.
    Apply dynamic trailing SL based on config thresholds.
    """
    from config import ENABLE_TRAILING_SL, TRAILING_SL_TRIGGER_PCT, TRAILING_SL_STEP_PCT, TRAILING_SL_BE_OFFSET_PCT
    if not ENABLE_TRAILING_SL:
        return

    positions = mt5.positions_get(magic=202400)
    if not positions:
        return

    trigger = TRAILING_SL_TRIGGER_PCT   / 100.0
    step    = TRAILING_SL_STEP_PCT      / 100.0
    be_off  = TRAILING_SL_BE_OFFSET_PCT / 100.0

    for p in positions:
        symbol = p.symbol
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            continue

        price_open = p.price_open
        current_sl = p.sl
        digits = mt5.symbol_info(symbol).digits

        # Direction: 1 for BUY, -1 for SELL
        direction = 1 if p.type == mt5.POSITION_TYPE_BUY else -1
        current_price = tick.bid if p.type == mt5.POSITION_TYPE_BUY else tick.ask
        digits = mt5.symbol_info(symbol).digits

        # ── 1. ATR Trailing Calculation (Highest Precedence) ──────────────
        from config import ENABLE_ATR_TRAILING, ATR_TRAILING_MULT
        atr_sl_price = None
        if ENABLE_ATR_TRAILING:
            # Fetch last 15 bars to calculate ATR(14)
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 15)
            if rates is not None and len(rates) >= 15:
                df = pd.DataFrame(rates)
                df['tr'] = pd.concat([
                    df['high'] - df['low'],
                    (df['high'] - df['close'].shift(1)).abs(),
                    (df['low'] - df['close'].shift(1)).abs()
                ], axis=1).max(axis=1)
                atr_val = df['tr'].rolling(14).mean().iloc[-1]
                
                if atr_val > 0:
                    dist = atr_val * ATR_TRAILING_MULT
                    atr_sl_price = round(current_price - (direction * dist), digits)

        # ── 2. Percentage Trailing Calculation ───────────────────────────
        # Calculate profit pct from open price
        profit_pct = (current_price - price_open) / price_open * direction
        pct_sl_price = None

        if profit_pct >= trigger:
            # Calculate steps past trigger. N=0 at trigger (SL = entry + offset).
            n_steps = math.floor((profit_pct - trigger + 1e-9) / step)
            pct_sl_price = price_open * (1 + direction * (be_off + n_steps * step))
            pct_sl_price = round(pct_sl_price, digits)

        # ── 3. Combine & Compare ──────────────────────────────────────────
        # Selection logic: If ATR trailing is enabled, it has strict precedence.
        candidate_sl = None

        if ENABLE_ATR_TRAILING and atr_sl_price is not None:
            candidate_sl = atr_sl_price
        else:
            candidate_sl = pct_sl_price

        if candidate_sl is not None:
            new_sl_price = candidate_sl
            # Check if new SL is an improvement
            is_better = False
            if p.type == mt5.POSITION_TYPE_BUY:
                if new_sl_price > current_sl + 1e-9:
                    is_better = True
            else: # SELL
                if current_sl == 0 or new_sl_price < current_sl - 1e-9:
                    is_better = True

            if is_better:
                request = {
                    "action":   mt5.TRADE_ACTION_SLTP,
                    "symbol":   symbol,
                    "position": p.ticket,
                    "sl":       new_sl_price,
                    "tp":       p.tp,
                    "magic":    202400
                }
                res = mt5.order_send(request)
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    source = "ATR" if new_sl_price == atr_sl_price else "PCT"
                    pnl_info = f"Profit: {profit_pct*100:.3f}%"
                    print(f"[executor] Trailing SL updated ({source}) symbol={symbol} ticket=#{p.ticket} -> {new_sl_price} ({pnl_info})")
                else:
                    rc = res.retcode if res else "None"
                    print(f"[executor] Failed to update Trailing SL for #{p.ticket}: {rc}")