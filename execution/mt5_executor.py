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


def close_position(position, tick):
    type_dict = {
        mt5.POSITION_TYPE_BUY: mt5.ORDER_TYPE_SELL,
        mt5.POSITION_TYPE_SELL: mt5.ORDER_TYPE_BUY
    }
    order_type = type_dict[position.type]
    price = tick.bid if order_type == mt5.ORDER_TYPE_SELL else tick.ask
    
    filling = _get_filling_mode(position.symbol)
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": position.symbol,
        "volume": position.volume,
        "type": order_type,
        "position": position.ticket,
        "price": price,
        "deviation": 20,
        "magic": 202400,
        "comment": "Time Close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling,
    }
    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"[executor] Closed position #{position.ticket} ({position.symbol}) due to time logic. Profit: {position.profit}")
    else:
        rc = result.retcode if result else "None"
        print(f"[executor] Failed to close position #{position.ticket}: {rc}")


def manage_time_based_closes(server_time):
    """
    Close all trades in profit after 11 PM.
    Close all trades at 11:30 PM.
    """
    hour = server_time.hour
    minute = server_time.minute

    # 1. Close all trades if >= 23:30
    close_all = False
    if hour == 23 and minute >= 30:
        close_all = True
    elif hour >= 24: # (Just in case)
        pass
    
    # 2. Close profitable trades if >= 23:00 and < 23:30
    close_profit = False
    if hour == 23 and minute >= 0 and not close_all:
        close_profit = True

    if not close_all and not close_profit:
        return

    positions = mt5.positions_get(magic=202400)
    if not positions:
        return

    for p in positions:
        symbol = p.symbol
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            continue
            
        should_close = False
        if close_all:
            should_close = True
        elif close_profit and p.profit > 0:
            should_close = True

        if should_close:
            close_position(p, tick)


def lock_in_profits():
    """
    Called when daily 15% target is reached.
    1. Close any position > $20 profit.
    2. Set TP to +$20 profit for others.
    """
    from config import PROFIT_LOCK_THRESH, PROFIT_LOCK_TP_TARGET
    
    positions = mt5.positions_get(magic=202400)
    if not positions:
        return

    for p in positions:
        symbol = p.symbol
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            continue
            
        if p.profit >= PROFIT_LOCK_THRESH:
            print(f"[executor] Locking profit: Closing #{p.ticket} ({symbol}) with ${p.profit:.2f}")
            close_position(p, tick)
        else:
            # Set TP to $20 profit
            # Formula: Profit = (Price - Open) * Vol * TickValue / TickSize
            # Price = Open + (TargetProfit * TickSize) / (Vol * TickValue)
            info = mt5.symbol_info(symbol)
            if info is None: continue
            
            direction = 1 if p.type == mt5.POSITION_TYPE_BUY else -1
            
            # Distance in price for $20 profit
            # tick_value is profit for 1 lot for 1 tick_size change
            # profit = (price_change / tick_size) * volume * tick_value
            # price_change = (profit * tick_size) / (volume * tick_value)
            
            price_dist = (PROFIT_LOCK_TP_TARGET * info.trade_tick_size) / (p.volume * info.trade_tick_value)
            new_tp = round(p.price_open + (direction * price_dist), info.digits)
            
            # Only update if new TP is better (tighter or exists) than current TP
            # For simplicity, we always update to lock in exactly $20 if it's currently < $20
            request = {
                "action":   mt5.TRADE_ACTION_SLTP,
                "symbol":   symbol,
                "position": p.ticket,
                "sl":       p.sl,
                "tp":       new_tp,
                "magic":    202400
            }
            res = mt5.order_send(request)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                print(f"[executor] Locking profit: TP updated for #{p.ticket} to target ${PROFIT_LOCK_TP_TARGET}")
            else:
                print(f"[executor] Failed to set lock-in TP for #{p.ticket}")