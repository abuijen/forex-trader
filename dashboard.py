"""
dashboard.py
────────────
Streamlit live dashboard for the ML Forex Scalping Bot.

Run with:
    streamlit run dashboard.py
"""

import os
import time
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import MetaTrader5 as mt5

from config import LOG_FILE, MT5_PATH, DASHBOARD_UPDATE_INTERVAL, SYMBOLS

# ─────────────────────────────────────────────────────────────────────────────
#  Page config
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="🤖 ML Forex Bot Dashboard",
    page_icon="📈",
    layout="wide",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    .stApp {
        background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
        color: #e0e0e0;
    }

    .metric-card {
        background: rgba(255,255,255,0.07);
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 16px;
        padding: 20px 24px;
        backdrop-filter: blur(12px);
        text-align: center;
    }
    .metric-card h3 { color: #9b9ec7; font-size: 0.85rem; margin-bottom: 6px; }
    .metric-card p  { color: #ffffff; font-size: 2rem; font-weight: 700; margin: 0; }
    .pos { color: #4ade80 !important; }
    .neg { color: #f87171 !important; }

    [data-testid="stSidebar"] { background: rgba(0,0,0,0.4); }

    div[data-testid="metric-container"] { display: none; } /* hide default metrics */
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
#  MT5 helpers
# ─────────────────────────────────────────────────────────────────────────────

def connect_mt5():
    kwargs = {"path": MT5_PATH} if MT5_PATH else {}
    if not mt5.initialize(**kwargs):
        return False
    return True


def get_account_info():
    if not connect_mt5():
        return None
    return mt5.account_info()


def get_open_positions():
    if not connect_mt5():
        return pd.DataFrame()
    positions = mt5.positions_get()
    if not positions:
        return pd.DataFrame()
    rows = []
    for p in positions:
        rows.append({
            "Ticket":  p.ticket,
            "Symbol":  p.symbol,
            "Type":    "BUY" if p.type == 0 else "SELL",
            "Lots":    p.volume,
            "Open Price": p.price_open,
            "Current": p.price_current,
            "P&L":     round(p.profit, 2),
            "SL":      p.sl,
            "TP":      p.tp,
        })
    return pd.DataFrame(rows)


def get_order_results(order_tickets):
    """Fetch realized profit and status for a list of order tickets."""
    if not connect_mt5() or not order_tickets:
        return {}
    
    # Check last 7 days; use future to_date to accommodate server time differences
    from_date = datetime.now() - timedelta(days=7)
    to_date   = datetime.now() + timedelta(days=1)
    deals = mt5.history_deals_get(from_date, to_date)
    if not deals:
        return {}
    
    # 1. Map entry orders to position IDs
    order_to_pos = {}
    for d in deals:
        if d.order in order_tickets and d.entry == 0: # entry=0 is DEAL_ENTRY_IN
            order_to_pos[d.order] = d.position_id
            
    # 2. Map position IDs to their "out" deal profit
    pos_to_results = {}
    for d in deals:
        if d.entry == 1: # entry=1 is DEAL_ENTRY_OUT
            profit = round(d.profit + d.commission + d.swap, 2)
            pos_to_results[d.position_id] = {
                "Result": "WIN ✅" if profit > 0 else "LOSS ❌",
                "Profit": f"${profit:,.2f}"
            }
            
    # 3. Final mapping: Entry Order Ticket -> Result
    final_results = {}
    for ticket in order_tickets:
        pos_id = order_to_pos.get(ticket)
        if pos_id and pos_id in pos_to_results:
            final_results[ticket] = pos_to_results[pos_id]
            
    return final_results



# ─────────────────────────────────────────────────────────────────────────────
#  Trade log helpers
# ─────────────────────────────────────────────────────────────────────────────

def load_trade_log() -> pd.DataFrame:
    if not os.path.exists(LOG_FILE):
        return pd.DataFrame()
    try:
        df = pd.read_csv(LOG_FILE, parse_dates=["time"])
        return df
    except Exception:
        return pd.DataFrame()


def compute_stats(df: pd.DataFrame) -> dict:
    """Calculate Win Rate and realized P&L from MT5 history for Bot Magic 202400."""
    total_orders = len(df[df["retcode"] == 10009]) if not df.empty else 0
    
    if not connect_mt5():
        return {"total": total_orders, "wins": 0, "win_rate": 0.0, "pnl": 0.0}
    
    # Get last 7 days of deals; use future to_date for timezone safety
    from_date = datetime.now() - timedelta(days=7)
    to_date   = datetime.now() + timedelta(days=1)
    deals = mt5.history_deals_get(from_date, to_date)
    
    if not deals:
        return {"total": total_orders, "wins": 0, "win_rate": 0.0, "pnl": 0.0}
        
    # 1. Find all bot positions by entry deals (DEAL_ENTRY_IN)
    bot_pos_ids = set()
    for d in deals:
        if d.magic == 202400 and d.entry == 0: # DEAL_ENTRY_IN
            bot_pos_ids.add(d.position_id)
            
    # 2. Sum profit from all exit deals (DEAL_ENTRY_OUT) for those positions
    wins = 0
    total_pnl = 0.0
    closed_count = 0
    
    for d in deals:
        if d.position_id in bot_pos_ids and d.entry == 1: # DEAL_ENTRY_OUT
            profit = d.profit + d.commission + d.swap
            total_pnl += profit
            closed_count += 1
            if profit > 0:
                wins += 1
                
    win_rate = (wins / closed_count * 100) if closed_count > 0 else 0.0
    
    return {
        "total": total_orders,
        "wins": wins,
        "win_rate": round(win_rate, 1),
        "pnl": round(total_pnl, 2)
    }



# ─────────────────────────────────────────────────────────────────────────────
#  Sidebar
# ─────────────────────────────────────────────────────────────────────────────

st.sidebar.image(
    "https://img.icons8.com/color/96/combo-chart--v1.png", width=64
)
st.sidebar.title("⚙️ Controls")
refresh_rate = st.sidebar.slider("Refresh (s)", 3, 60, DASHBOARD_UPDATE_INTERVAL)
selected_symbols = st.sidebar.multiselect("Symbols", SYMBOLS, default=SYMBOLS)
st.sidebar.markdown("---")
st.sidebar.info("Bot running in background.\nConnect MT5 to see live data.")


# ─────────────────────────────────────────────────────────────────────────────
#  Header
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("""
<div style='text-align:center; padding: 10px 0 30px 0;'>
  <h1 style='font-size: 2.4rem; font-weight: 700; color: #c4b5fd;'>
    🤖 ML Forex Scalping Bot
  </h1>
  <p style='color: #9ca3af; margin-top: -10px; font-size: 0.95rem;'>
    Live Dashboard &nbsp;|&nbsp; Random Forest Strategy &nbsp;|&nbsp; 24/7 Trading
  </p>
</div>
""", unsafe_allow_html=True)


# ── Live Data Fetching ────────────────────────────────────────────────────────
account = get_account_info()
trades  = load_trade_log()
stats   = compute_stats(trades)
open_pos = get_open_positions()

# ── Top Metric Row ────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)

balance  = f"${account.balance:,.2f}"  if account else "–"
equity   = f"${account.equity:,.2f}"   if account else "–"
pnl_val  = stats["pnl"]
pnl_str  = f"${pnl_val:,.2f}"
pnl_cls  = "pos" if pnl_val >= 0 else "neg"

connected = "🟢 Connected" if account else "🔴 Offline"
total_trades = stats["total"]
win_rate_str = f"{stats['win_rate']}%"

for col, label, value, cls in [
    (c1, "MT5 Status",   connected,    ""),
    (c2, "Balance",      balance,       "pos"),
    (c3, "Realized P&L", pnl_str,       pnl_cls),
    (c4, "Total Orders", total_trades,  ""),
    (c5, "Win Rate",     win_rate_str,  "pos"),
]:

    col.markdown(f"""
    <div class="metric-card">
        <h3>{label}</h3>
        <p class="{cls}">{value}</p>
    </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Charts row ────────────────────────────────────────────────────────────────
chart_col, pos_col = st.columns([2, 1])

with chart_col:
    st.markdown("### 📊 Trade History")
    if not trades.empty and "time" in trades.columns:
        t = trades.sort_values("time")
        t["cumulative"] = range(1, len(t) + 1)
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=t["time"], y=t["cumulative"],
            mode="lines+markers",
            line=dict(color="#a78bfa", width=2),
            marker=dict(size=5, color="#7c3aed"),
            name="Orders",
            fill="tozeroy",
            fillcolor="rgba(124,58,237,0.15)",
        ))
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e0e0e0"),
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.08)"),
            margin=dict(l=10, r=10, t=10, b=10),
            height=280,
        )
        st.plotly_chart(fig, width="stretch", key="trade_history_chart")
    else:
        st.info("No trade history yet.")

with pos_col:
    st.markdown("### 📌 Open Positions")
    if not open_pos.empty:
        def color_pnl(val):
            color = "#4ade80" if val >= 0 else "#f87171"
            return f"color: {color}"
        styled = open_pos.style.map(color_pnl, subset=["P&L"])
        st.dataframe(styled, width="stretch", height=280)
    else:
        st.info("No open positions.")

st.markdown("<br>", unsafe_allow_html=True)

# ── Signal breakdown ──────────────────────────────────────────────────────────
signal_col, log_col = st.columns([1, 2])

with signal_col:
    st.markdown("### 🎯 Signal Breakdown")
    if not trades.empty and "signal" in trades.columns:
        vc = trades["signal"].value_counts()
        labels = vc.index.tolist()
        values = vc.values.tolist()
        pie = go.Figure(go.Pie(
            labels=labels, values=values,
            hole=0.55,
            marker=dict(colors=["#4ade80", "#f87171"]),
        ))
        pie.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e0e0e0"),
            showlegend=True,
            margin=dict(l=0, r=0, t=10, b=10),
            height=220,
        )
        st.plotly_chart(pie, width="stretch", key="signal_breakdown_pie")
    else:
        st.info("No signal data yet.")

with log_col:
    st.markdown("### 📋 Recent Orders")
    if not trades.empty:
        # Fetch results from MT5
        tickets = trades["order"].unique().tolist()
        order_results = get_order_results(tickets)
        
        # Enrich trades DF
        trades_display = trades.copy()
        trades_display["Result"] = trades_display["order"].map(lambda x: order_results.get(x, {}).get("Result", "–"))
        trades_display["P&L"]    = trades_display["order"].map(lambda x: order_results.get(x, {}).get("Profit", "–"))
        
        # Sort and filter
        display = trades_display.sort_values("time", ascending=False).head(20)
        display = display[["time", "symbol", "signal", "lot", "price", "Result", "P&L"]]
        display.columns = ["Time", "Symbol", "Signal", "Lot", "Price", "Result", "P&L"]
        
        def color_rows(row):
            if "WIN" in str(row["Result"]):
                return ['background-color: rgba(74, 222, 128, 0.15); color: #4ade80; font-weight: bold;'] * len(row)
            elif "LOSS" in str(row["Result"]):
                return ['background-color: rgba(248, 113, 113, 0.15); color: #f87171; font-weight: bold;'] * len(row)
            return [''] * len(row)

        styled = display.style.apply(color_rows, axis=1)
        st.dataframe(styled, width="stretch", height=220)
    else:
        st.info("No orders logged yet.")

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div style='text-align:center; color:#4b5563; font-size:0.78rem; margin-top: 20px;'>
    Auto-refreshing every {refresh_rate}s &nbsp;|&nbsp;
    Log: <code>{LOG_FILE}</code> &nbsp;|&nbsp;
    Powered by scikit-learn + MetaTrader 5
</div>
""", unsafe_allow_html=True)

# ── Auto refresh ──────────────────────────────────────────────────────────
time.sleep(refresh_rate)
st.rerun()
