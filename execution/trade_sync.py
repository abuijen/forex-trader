import sys
import os
sys.path.append(os.getcwd())

import pandas as pd
from datetime import datetime, timedelta
import MetaTrader5 as mt5
from config import LOG_FILE

def sync_closed_trades():
    """
    Look for closed trades in MT5 history and update LOG_FILE with results.
    """
    if not os.path.exists(LOG_FILE):
        return

    try:
        df = pd.read_csv(LOG_FILE)
    except Exception as e:
        print(f"[sync] Error reading log: {e}")
        return

    # Ensure result and pnl columns exist
    if 'result' not in df.columns:
        df['result'] = ""
    if 'pnl' not in df.columns:
        df['pnl'] = ""

    # Convert result to object dtype to prevent incompatible dtype warnings
    df['result'] = df['result'].astype('object')

    # Identify rows that need updating (retcode 10009 and no result)
    # Using fillna or comparison to handle both NaN and empty strings
    mask = (df['retcode'] == 10009) & (df['result'].isna() | (df['result'] == ""))
    tickets_to_check = df.loc[mask, 'order'].tolist()

    if not tickets_to_check:
        return

    # Fetch history
    # Use wide range to handle timezone differences
    from_date = datetime.now() - timedelta(days=7)
    to_date   = datetime.now() + timedelta(days=1)
    deals = mt5.history_deals_get(from_date, to_date)
    
    if not deals:
        return

    # Logic: Match order ticket -> Position ID -> Deal ENTRY_OUT profit
    # 1. Map entry orders to positions
    order_to_pos = {}
    for d in deals:
        if d.order in tickets_to_check and d.entry == 0:
            order_to_pos[d.order] = d.position_id

    # 2. Map position IDs to their "out" deal results
    pos_to_results = {}
    for d in deals:
        if d.entry == 1: # DEAL_ENTRY_OUT
            profit = round(d.profit + d.commission + d.swap, 2)
            pos_to_results[d.position_id] = {
                "result": "WIN" if profit > 0 else "LOSS",
                "pnl": profit
            }

    # 3. Update the dataframe
    updated = False
    for idx, row in df.loc[mask].iterrows():
        ticket = row['order']
        pos_id = order_to_pos.get(ticket)
        if pos_id and pos_id in pos_to_results:
            res = pos_to_results[pos_id]
            df.at[idx, 'result'] = res['result']
            df.at[idx, 'pnl'] = res['pnl']
            updated = True

    if updated:
        try:
            df.to_csv(LOG_FILE, index=False)
            print(f"[sync] Updated {len(df.loc[mask][df.loc[mask, 'result'] != ''])} trades in log.")
        except Exception as e:
            print(f"[sync] Error writing log: {e}")

if __name__ == "__main__":
    # For manual testing
    if mt5.initialize():
        sync_closed_trades()
        mt5.shutdown()
