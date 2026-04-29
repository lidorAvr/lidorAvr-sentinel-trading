import streamlit as st



import pandas as pd
import os
import yfinance as yf
import plotly.graph_objects as go
import plotly.express as px
from supabase import create_client
from dotenv import load_dotenv
import numpy as np
import json
import xml.etree.ElementTree as ET
import engine_core as ec

st.set_page_config(page_title="Sentinel Command Center", page_icon="🎯", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #161b22; border-radius: 10px; padding: 15px; border: 1px solid #30363d; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
    div[data-testid="stExpander"] { border: 1px solid #30363d; border-radius: 8px; margin-bottom: 10px; background-color: #161b22; padding: 10px; }
    .stDataFrame { border-radius: 8px; overflow: hidden; }
    </style>
    """, unsafe_allow_html=True)

load_dotenv()
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

SETTINGS_FILE = "sentinel_config.json"



def load_settings():
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
    except: pass
    return {"total_deposited": 7500.0, "risk_pct_input": 0.5}

def save_settings(total_deposited, risk_pct_input):
    with open(SETTINGS_FILE, "w") as f:
        json.dump({"total_deposited": total_deposited, "risk_pct_input": risk_pct_input}, f)

settings = load_settings()

@st.cache_data(ttl=60)
def load_data():
    res = supabase.table("trades").select("*").execute()
    df = pd.DataFrame(res.data)
    if not df.empty:
        cols = ['image_url', 'notes', 'management_notes', 'setup_type', 'quality', 'score', 'symbol', 'side', 'pnl_usd', 'trade_date', 'stop_loss', 'initial_stop', 'price', 'quantity', 'campaign_id', 'management_state']
        for col in cols:
            if col not in df.columns: df[col] = None

        df['setup_type'] = df['setup_type'].fillna("Uncategorized")
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        for num_col in ['pnl_usd', 'price', 'quantity', 'stop_loss', 'initial_stop', 'quality', 'score']:
            df[num_col] = pd.to_numeric(df[num_col], errors='coerce').fillna(0)
        df['initial_stop'] = df.apply(lambda x: x['stop_loss'] if x['initial_stop'] == 0 else x['initial_stop'], axis=1)
    return df

raw_df = load_data()

st.sidebar.title("🛡️ Sentinel Intel")

cb_mode = st.sidebar.checkbox("👁️ מצב עיוורון צבעים (Blue/Orange)", value=False)
C_WIN = '#29B6F6' if cb_mode else '#00ffcc'
C_LOSS = '#FFA726' if cb_mode else '#ff3366'
E_WIN = '🔵' if cb_mode else '🟢'
E_LOSS = '🟠' if cb_mode else '🔴'
CMAP_HEATMAP = 'Bluered_r' if cb_mode else 'RdYlGn'

st.sidebar.markdown("---")

st.sidebar.subheader("🌡️ Market Regime")
spy_hist = ec.get_cached_history("SPY", "1y", "1d")
qqq_hist = ec.get_cached_history("QQQ", "1y", "1d")
regime = ec.compute_market_regime(spy_hist, qqq_hist)
if regime['ok']:
    rd = regime['data']
    st.sidebar.markdown(f"**{rd['color']} {rd['status']}**")
    st.sidebar.caption(rd['text'])
else:
    st.sidebar.caption("⏳ מחשב משטר שוק...")
st.sidebar.markdown("---")

st.sidebar.subheader("💼 Account Settings")

# קריאת הנתונים מקובץ ההגדרות העדכני
saved_nav = float(settings.get("current_nav", settings.get("total_deposited", 7500.0)))

st.sidebar.success(f"🏦 Live IBKR NAV: **${saved_nav:,.2f}**")

current_acc_size = saved_nav
total_deposited = st.sidebar.number_input("Base Capital (All-Time):", value=float(settings.get("total_deposited", 7500.0)), step=500.0)
risk_pct_input = st.sidebar.number_input("Target Risk (% per trade):", value=float(settings.get("risk_pct_input", 0.5)), step=0.1, max_value=5.0)

if total_deposited != settings.get("total_deposited") or risk_pct_input != settings.get("risk_pct_input"):
    save_settings(total_deposited, risk_pct_input, saved_nav)

target_risk_usd = current_acc_size * (risk_pct_input / 100)
st.sidebar.info(f"⚖️ **Risk Profile:** You are risking **{risk_pct_input:.2f}%** (${target_risk_usd:,.0f}) per trade.")

all_time_return_pct = ((current_acc_size - total_deposited) / total_deposited) * 100 if total_deposited > 0 else 0

st.sidebar.markdown("---")
selected_benchmarks = st.sidebar.multiselect("בחר מדדי השוואה:", ["QQQ (Nasdaq 100)", "SPY (S&P 500)"], default=["QQQ (Nasdaq 100)"])

if not raw_df.empty:
    st.sidebar.subheader("🔍 Filters")
    start_d, end_d = raw_df['trade_date'].min().date(), raw_df['trade_date'].max().date()
    date_range = st.sidebar.date_input("Date Range:", [start_d, end_d])
    all_setups = sorted([str(s) for s in raw_df['setup_type'].unique() if s is not None])
    selected_setups = st.sidebar.multiselect("Setups:", all_setups, default=all_setups)
    if len(date_range) == 2:
        mask = (raw_df['trade_date'].dt.date >= date_range[0]) & (raw_df['trade_date'].dt.date <= date_range[1]) & (raw_df['setup_type'].isin(selected_setups))
        df = raw_df.loc[mask]
    else: df = raw_df
else: df = raw_df

if st.sidebar.button("🔄 Force Refresh Sync"): st.cache_data.clear(); st.rerun()

st.title("🎯 Sentinel Pro Command Center (Institutional Edition)")

@st.cache_data(ttl=180, show_spinner=False)
def compute_live_portfolio_data(open_trades_dict, _acc_size, _target_risk_usd, _spy_hist):
    live_positions = []
    if not open_trades_dict: return pd.DataFrame(live_positions)
    
    for row in open_trades_dict:
        sym, setup, qty = row['symbol'], row['setup_type'], row['quantity']
        entry, sl, init_sl = row['price'], row['stop_loss'], row['initial_stop']
        curr = ec.get_live_price(sym) or entry
        open_pnl = (curr - entry) * qty
        pos_value = curr * qty
        weight_pct = (pos_value / _acc_size) * 100 if _acc_size > 0 else 0
        
        base_price = row.get('base_price', entry)
        base_qty = row.get('base_qty', qty)
        
        original_campaign_risk = (base_price - init_sl) * base_qty if (init_sl > 0 and init_sl < base_price) else 0
        
        if sl > base_price: 
            current_open_loss_risk = 0
            locked_profit_usd = (sl - base_price) * qty
            giveback_risk_usd = (curr - sl) * qty if curr > sl else 0
        else:
            current_open_loss_risk = (base_price - sl) * qty if sl > 0 else 0
            locked_profit_usd = 0
            giveback_risk_usd = 0

        open_r_val = (open_pnl / _target_risk_usd) if str(setup).upper() == 'ALGO' and _target_risk_usd > 0 else (open_pnl / original_campaign_risk if original_campaign_risk > 0 else 0)
        total_pnl = open_pnl + row['realized_pnl']
        total_campaign_r = (total_pnl / _target_risk_usd) if str(setup).upper() == 'ALGO' and _target_risk_usd > 0 else (total_pnl / original_campaign_risk if original_campaign_risk > 0 else 0)
        
        eval_res = ec.evaluate_position_engine(
            sym, entry, row['entry_date'], sl, setup, row['management_state'], 
            weight_pct, total_campaign_r, target_risk_usd=_target_risk_usd, actual_risk_usd=original_campaign_risk, spy_hist=_spy_hist
        )
        
        score = eval_res['data']['score'] if eval_res['ok'] and eval_res['data']['score'] else 50
        status = eval_res['data']['status'] if eval_res['ok'] else "Unknown"
        sizing_status = eval_res['data'].get('sizing_status', '✅ תקין') if eval_res['ok'] else "Unknown"
        
        sec_b = ec.get_sector_bundle(sym)
        live_positions.append({
            'Symbol': sym, 'Setup': setup, 'Exposure_USD': pos_value, 'Exposure_Pct': weight_pct,
            'PnL': open_pnl, 'Open_R': open_r_val, 'Total_R': total_campaign_r, 'Score': score, 'Status': status, 'Sizing': sizing_status,
            'Sector': sec_b.get('sector') or "Other", 'Entry': entry, 'Current': curr,
            'OriginalRisk': original_campaign_risk, 'GivebackRisk': giveback_risk_usd, 'LockedProfit': locked_profit_usd,
            'CapitalRisk': current_open_loss_risk
        })
    return pd.DataFrame(live_positions)

# --- THE FIX: Smart Cached Benchmark Fetcher ---
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_benchmark_data(ticker, start_date, end_date):
    try:
        ec.smart_delay() # Add human delay
        ec.yf_session.headers.update({'User-Agent': ec.get_random_agent()}) # Mask as browser
        start_str = start_date.strftime('%Y-%m-%d')
        end_str = (end_date + pd.Timedelta(days=2)).strftime('%Y-%m-%d')
        df = yf.download(ticker, start=start_str, end=end_str, session=ec.yf_session, progress=False)
        return df
    except Exception as e:
        return pd.DataFrame()

if df.empty:
    st.warning("No data found. Check your filters.")
else:
    df_sorted = df.sort_values('trade_date')
    pos_res = ec.get_open_positions_campaign(df_sorted)
    actual_open_trades = pos_res["data"] if pos_res["ok"] else pd.DataFrame()
    
    closed_campaigns = []
    if 'campaign_id' in df_sorted.columns:
        for cid, group in df_sorted[df_sorted['campaign_id'].notnull()].groupby('campaign_id'):
            group = group.sort_values(['trade_date', 'trade_id'])
            net_qty = group['quantity'].sum()
            if net_qty > 0.001: continue 
            
            buys = group[group['side'].str.upper() == 'BUY']
            sells = group[group['side'].str.upper() == 'SELL']
            if buys.empty or sells.empty: continue
            
            total_pnl = sells['pnl_usd'].sum()
            total_qty = buys['quantity'].sum()
            avg_entry = (buys['price'] * buys['quantity']).sum() / total_qty
            avg_exit = (sells['price'] * sells['quantity'].abs()).sum() / sells['quantity'].abs().sum()
            
            first_date = buys['trade_date'].min()
            first_day_buys = buys[buys['trade_date'] == first_date]
            base_qty = float(first_day_buys['quantity'].sum())
            base_price = float((first_day_buys['price'] * first_day_buys['quantity']).sum() / base_qty) if base_qty > 0 else float(first_day_buys.iloc[0]["price"])
            
            init_sl = first_day_buys.iloc[0].get('initial_stop')
            if pd.isna(init_sl) or init_sl == 0 or init_sl >= base_price: init_sl = 0 
            original_campaign_risk = (base_price - init_sl) * base_qty if (init_sl > 0) else 0
            
            setup = first_day_buys.iloc[0].get('setup_type')
            if str(setup).upper() in ["UNKNOWN", "NONE", "NAN"] or pd.isna(setup): setup = sells.iloc[-1].get('setup_type', 'Unknown')
            is_algo = str(setup).upper() == 'ALGO'
            
            r_realized = (total_pnl / target_risk_usd) if is_algo and target_risk_usd > 0 else ((total_pnl / original_campaign_risk) if original_campaign_risk > 0 else 0)
            images = [s['image_url'] for _, s in sells.iterrows() if isinstance(s['image_url'], str) and s['image_url'].startswith('http')]
            
            events = []
            for _, row in group.iterrows():
                is_addon = (row['side'].upper() == 'BUY' and row['trade_date'] > first_date)
                events.append({
                    'date': row['trade_date'], 'side': str(row['side']).upper(), 'is_addon': is_addon,
                    'qty': float(row['quantity']), 'price': float(row['price']),
                    'pnl': float(row.get('pnl_usd', 0)), 'stop': float(row.get('stop_loss', 0))
                })
                
            mgt_notes_val = sells.iloc[-1].get('management_notes')
            quality_val = first_day_buys.iloc[0].get('quality')
            if pd.isna(quality_val) or quality_val <= 0: quality_val = sells.iloc[-1].get('quality', -1)

            closed_campaigns.append({
                'campaign_id': cid, 'symbol': buys.iloc[0]['symbol'], 'close_date': sells.iloc[-1]['trade_date'],
                'entry_date': first_date, 'avg_entry': avg_entry, 'avg_exit': avg_exit,
                'pnl_usd': total_pnl, 'setup_type': setup, 'quality': quality_val,
                'score': sells.iloc[-1]['score'], 'Total_Campaign_R': r_realized, 'is_algo': is_algo,
                'original_campaign_risk': original_campaign_risk, 'init_sl_clean': init_sl,
                'image_url': images[-1] if images else None, 'events': events, 'management_notes': mgt_notes_val
            })
    camp_df = pd.DataFrame(closed_campaigns)

    if not camp_df.empty:
        wins = camp_df[camp_df['pnl_usd'] > 0]
        losses = camp_df[camp_df['pnl_usd'] < 0]
        win_rate = len(wins) / len(camp_df)
        avg_win_r = wins['Total_Campaign_R'].mean() if not wins.empty else 0
        avg_loss_r = abs(losses['Total_Campaign_R'].mean()) if not losses.empty else 1
        adj_rr = avg_win_r / avg_loss_r if avg_loss_r > 0 else 0
        expectancy_r = (win_rate * avg_win_r) - ((1 - win_rate) * avg_loss_r)
        total_pnl_net = camp_df['pnl_usd'].sum()
        total_r_net = camp_df['Total_Campaign_R'].sum()
    else:
        win_rate, adj_rr, expectancy_r, total_pnl_net, total_r_net = 0, 0, 0, 0, 0

    open_dict = actual_open_trades.to_dict('records') if not actual_open_trades.empty else []
    with st.spinner("Analyzing Live Battlefield..."):
        live_df = compute_live_portfolio_data(open_dict, current_acc_size, target_risk_usd, spy_hist)
        
    total_open_pnl = live_df['PnL'].sum() if not live_df.empty else 0
    db_equity_expected = total_deposited + total_pnl_net + total_open_pnl
    reconciliation_gap = current_acc_size - db_equity_expected

    st.sidebar.markdown("---")
    st.sidebar.subheader("⚖️ Data Reconciliation")
    st.sidebar.write(f"Broker NAV: **${current_acc_size:,.2f}**")
    st.sidebar.write(f"Expected DB Equity: **${db_equity_expected:,.2f}**")
    if abs(reconciliation_gap) > 10: 
        st.sidebar.warning(f"Unrecorded Legacy PnL: **${reconciliation_gap:,.2f}**\n\n*(הפרש נובע מעסקאות/הפקדות ישנות שאינן ב-DB)*")
    else: 
        st.sidebar.success(f"System completely synced. (Gap: ${reconciliation_gap:,.2f})")

    st.sidebar.markdown("---")
    st.sidebar.subheader("🤖 AI Master Context Export")
    ai_str = f"# 🛡️ Sentinel AI - Master Context Report\n\n"
    ai_str += f"## 📊 1. Performance Matrix & Risk Profile\n"
    ai_str += f"- Broker NAV: ${current_acc_size:,.2f} | Base Capital: ${total_deposited:,.2f}\n"
    ai_str += f"- Target Risk Per Trade: {risk_pct_input:.2f}% (${target_risk_usd:,.2f})\n"
    ai_str += f"- All-Time Return (NAV): {all_time_return_pct:.2f}%\n"
    ai_str += f"- Database Win Rate (YTD): {win_rate*100:.1f}% | DB Net PnL: ${total_pnl_net:.2f}\n"
    ai_str += f"- Expectancy: {expectancy_r:.2f}R per trade | Adjusted R/R: {adj_rr:.2f}:1\n\n"
    ai_str += f"## 🔭 2. Live Battlefield (Open Positions)\n"
    if not actual_open_trades.empty:
        for _, row in actual_open_trades.iterrows():
            sym, qty, entry, setup, sl, init_sl = row['symbol'], row['quantity'], row['price'], row['setup_type'], row['stop_loss'], row['initial_stop']
            curr_p = ec.get_live_price(sym) or entry
            open_pnl = (curr_p - entry) * qty
            base_price = row.get('base_price', entry)
            base_qty = row.get('base_qty', qty)
            
            init_sl_clean = init_sl if (init_sl > 0 and init_sl < base_price) else 0
            original_campaign_risk = (base_price - init_sl_clean) * base_qty if init_sl_clean > 0 else 0
            
            if str(setup).upper() == 'ALGO':
                open_r_str = f"{(open_pnl / target_risk_usd):.2f}R (Target Base)"
                risk_dev = ""
            elif original_campaign_risk > 0:
                open_r_str = f"{(open_pnl / original_campaign_risk):.2f}R"
                risk_dev = f" | Planned Risk: ${target_risk_usd:.0f} | Original Campaign Risk: ${original_campaign_risk:,.0f}"
            else:
                open_r_str = "N/A"
                risk_dev = " | ⚠️ Missing Initial Stop Data"
                
            init_stop_str = f"${init_sl_clean:.2f}" if init_sl_clean > 0 else "N/A"
            ai_str += f"- {sym} [{setup}]: Avg Entry: ${entry:.2f} | Curr: ${curr_p:.2f} | Initial Stop: {init_stop_str} | Current Stop: ${sl:.2f} | Open PnL: ${open_pnl:.2f} | Open R: {open_r_str}{risk_dev}\n"
    else: ai_str += "No open positions.\n"
    
    ai_str += f"\n## 📅 3. Execution Archive (Recent Campaigns)\n"
    if not camp_df.empty:
        for _, row in camp_df.sort_values('close_date', ascending=False).head(20).iterrows():
            r_val = row['Total_Campaign_R']
            if row['is_algo']: t_r_str = f"{r_val:.2f}R (Target Risk Base)"
            elif row['original_campaign_risk'] == 0: t_r_str = "N/A (Missing Initial Stop Data)"
            else: t_r_str = f"{r_val:.2f}R (True Risk Base)"
                
            ai_str += f"\n### {row['symbol']} [{row['setup_type']}] | Net PnL: ${row['pnl_usd']:.2f} | Total Campaign R: {t_r_str}\n"
            q_str = f"{int(row['quality'])}/10" if row['quality'] > 0 else "N/A"
            s_str = f"{int(row['score'])}/10" if row['score'] > 0 else "N/A"
            ai_str += f"- Strategy Quality: {q_str} | Execution Score: {s_str}\n"
            if row.get('original_campaign_risk', 0) > 0 and not row['is_algo']: ai_str += f"- Planned Risk: ${target_risk_usd:.2f} | Original Campaign Risk: ${row['original_campaign_risk']:.2f}\n"
            n_val = row.get('management_notes')
            if n_val and str(n_val) not in ["None", "Skipped", "nan"]: ai_str += f"- Management Notes: {n_val}\n"
            ai_str += f"- Timeline Events:\n"
            for ev in row['events']:
                action_str = f"BUY {'(ADD-ON) ' if ev['is_addon'] else ''}{ev['qty']} @ ${ev['price']:.2f}" if ev['side'] == 'BUY' else f"SELL {abs(ev['qty'])} @ ${ev['price']:.2f} (PnL: ${ev['pnl']:.2f})"
                if ev['side'] == 'BUY': stop_str = f" | Initial Stop: ${row.get('init_sl_clean', 0):.2f}" if row.get('init_sl_clean', 0) > 0 else ""
                else: stop_str = f" | Exit Stop: ${ev['stop']:.2f}" if ev['stop'] > 0 else ""
                ai_str += f"  * {ev['date'].strftime('%Y-%m-%d')}: {action_str}{stop_str}\n"
    else: ai_str += "No campaigns closed yet.\n"
    st.sidebar.text_area("📋 העתק (Ctrl+A -> Ctrl+C):", value=ai_str, height=450)

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("All-Time Return (NAV)", f"{all_time_return_pct:+.1f}%")
    m2.metric("Win Rate (DB)", f"{win_rate*100:.1f}%")
    m3.metric("Payoff Ratio (R:R)", f"{adj_rr:.2f}")
    m4.metric("Total R Realized (DB)", f"{total_r_net:.1f}R")
    m5.metric("Total Net PnL (DB)", f"${total_pnl_net:,.2f}")

    tabs = st.tabs(["🚀 Command Center (Live)", "📊 Performance Matrix", "🎯 Strategy Forensics", "📅 Visual Journal", "🛠️ DB Manager"])

    with tabs[0]:
        st.subheader("Live Portfolio Allocation & Risk Heatmap")
        if not live_df.empty:
            c1, c2 = st.columns([2, 1])
            with c1:
                live_df['Exposure_Plot'] = live_df['Exposure_USD'].apply(lambda x: max(x, 1))
                fig_tree = px.treemap(
                    live_df, path=[px.Constant("Portfolio"), 'Setup', 'Symbol'], values='Exposure_Plot',
                    color='Score', color_continuous_scale=CMAP_HEATMAP, range_color=[20, 100],
                    custom_data=['Status', 'Open_R', 'Exposure_Pct', 'Sizing']
                )
                fig_tree.update_traces(hovertemplate="<b>%{label}</b><br>Exposure: %{customdata[2]:.1f}%<br>Status: %{customdata[0]}<br>Open R: %{customdata[1]:.2f}R<br>%{customdata[3]}")
                fig_tree.update_layout(margin=dict(t=10, l=10, r=10, b=10), paper_bgcolor='#0e1117', plot_bgcolor='#0e1117')
                st.plotly_chart(fig_tree, use_container_width=True)
            with c2:
                fig_donut = px.pie(live_df, names='Sector', values='Exposure_USD', hole=0.5)
                fig_donut.update_traces(textposition='inside', textinfo='percent+label')
                fig_donut.update_layout(margin=dict(t=10, l=10, r=10, b=10), paper_bgcolor='#0e1117', showlegend=False)
                st.plotly_chart(fig_donut, use_container_width=True)
                
            st.dataframe(live_df[['Symbol', 'Setup', 'Status', 'Sizing', 'Open_R', 'GivebackRisk', 'LockedProfit', 'CapitalRisk']].style.format({'Open_R': '{:.2f}R', 'GivebackRisk': '${:.0f}', 'LockedProfit': '${:.0f}', 'CapitalRisk': '${:.0f}'}), use_container_width=True, hide_index=True)
        else:
            st.info("No open positions to display.")

    with tabs[1]:
        if not camp_df.empty:
            closed_sorted = camp_df.sort_values('close_date').copy()
            closed_sorted['cum_R'] = closed_sorted['Total_Campaign_R'].cumsum()
            closed_sorted['cum_pnl'] = closed_sorted['pnl_usd'].cumsum()
            closed_sorted['portfolio_pct'] = (closed_sorted['cum_pnl'] / current_acc_size) * 100

            st.subheader("📈 Portfolio Equity Curve vs Benchmarks")
            min_date, max_date = closed_sorted['close_date'].min(), closed_sorted['close_date'].max()
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=closed_sorted['close_date'], y=closed_sorted['portfolio_pct'], mode='lines+markers', name='Portfolio Return (%)', line=dict(color=C_WIN, width=3)))
            tickers_map = {"QQQ (Nasdaq 100)": ("QQQ", "#ff9900" if not cb_mode else "#FFC107"), "SPY (S&P 500)": ("SPY", "#bb86fc" if not cb_mode else "#9C27B0")}
            for selection in selected_benchmarks:
                ticker, color = tickers_map[selection]
                bm_data = fetch_benchmark_data(ticker, min_date, max_date)
                if not bm_data.empty:
                    if isinstance(bm_data.columns, pd.MultiIndex): bm_data.columns = bm_data.columns.get_level_values(0)
                    bm_data = bm_data.reset_index()
                    first_close = float(bm_data['Close'].iloc[0])
                    bm_data[f'{ticker}_pct'] = ((bm_data['Close'] - first_close) / first_close) * 100
                    fig.add_trace(go.Scatter(x=bm_data['Date'], y=bm_data[f'{ticker}_pct'], mode='lines', name=f'{ticker} (%)', line=dict(color=color, width=2, dash='dot')))
            
            fig.update_layout(plot_bgcolor='#0e1117', paper_bgcolor='#0e1117', font=dict(color='white'), hovermode="x unified", yaxis=dict(title="Return (%)"))
            st.plotly_chart(fig, use_container_width=True)
            
            c1, c2 = st.columns(2)
            with c1:
                dd_df = closed_sorted.copy()
                dd_df['peak'] = dd_df['cum_pnl'].cummax()
                dd_df['drawdown'] = dd_df['cum_pnl'] - dd_df['peak']
                fig_dd = go.Figure()
                fig_dd.add_trace(go.Scatter(x=dd_df['close_date'], y=dd_df['drawdown'], fill='tozeroy', mode='lines', line=dict(color=C_LOSS), name='Drawdown'))
                fig_dd.update_layout(title="Drawdown (USD)", plot_bgcolor='#0e1117', paper_bgcolor='#0e1117', font=dict(color='white'))
                st.plotly_chart(fig_dd, use_container_width=True)
            with c2:
                closed_sorted['Win/Loss'] = np.where(closed_sorted['Total_Campaign_R'] > 0, 'Win', 'Loss')
                fig_hist = px.histogram(closed_sorted, x="Total_Campaign_R", color="Win/Loss", color_discrete_map={"Win": C_WIN, "Loss": C_LOSS}, nbins=20, title="R-Multiple Distribution")
                fig_hist.update_layout(plot_bgcolor='#0e1117', paper_bgcolor='#0e1117', font=dict(color='white'))
                st.plotly_chart(fig_hist, use_container_width=True)

    with tabs[2]:
        st.subheader("🔬 Deep Dive: Strategy Forensics")
        if not camp_df.empty:
            setup_stats = camp_df.groupby('setup_type').agg(
                Trades=('campaign_id', 'count'), Net_R=('Total_Campaign_R', 'sum'),
                Win_Rate=('Total_Campaign_R', lambda x: (x > 0).mean() * 100)
            ).reset_index()
            fig_bar = px.bar(setup_stats, x='setup_type', y='Net_R', color='Net_R', color_continuous_scale=CMAP_HEATMAP, title="Net R by Strategy")
            fig_bar.update_layout(plot_bgcolor='#0e1117', paper_bgcolor='#0e1117', font=dict(color='white'))
            st.plotly_chart(fig_bar, use_container_width=True)

    with tabs[3]:
        st.subheader("Execution Archive (Visual Journal)")
        if not camp_df.empty:
            for m_key in sorted(camp_df['close_date'].dt.to_period('M').unique(), reverse=True):
                m_df = camp_df[camp_df['close_date'].dt.to_period('M') == m_key]
                with st.expander(f"📂 {m_key.strftime('%B %Y').upper()} | Monthly PnL: ${m_df['pnl_usd'].sum():,.2f}"):
                    for d in sorted(m_df['close_date'].dt.date.unique(), reverse=True):
                        st.markdown(f"#### 📅 {d}")
                        d_df = m_df[m_df['close_date'].dt.date == d]
                        for _, row in d_df.iterrows():
                            c1, c2 = st.columns([1, 3])
                            with c1:
                                img = row.get('image_url')
                                if img == "ScaleOut": st.info("📉 Scale-Out Event")
                                elif isinstance(img, str) and img.startswith('http'):
                                    if "/x/" in img:
                                        img_id = img.rstrip('/').split('/')[-1]
                                        if img_id: img = f"https://s3.tradingview.com/snapshots/{img_id[0].lower()}/{img_id}.png"
                                    st.image(img, use_container_width=True)
                                else: st.caption("🖼️ No Image")
                            with c2:
                                r_realized = row['Total_Campaign_R']
                                act_risk = row.get('original_campaign_risk', 0)
                                
                                if row['is_algo']: t_r_str = f"{r_realized:.2f}R (Target Base)"
                                elif act_risk == 0: t_r_str = "N/A"
                                else: t_r_str = f"{r_realized:.2f}R"
                                
                                if row['pnl_usd'] > 0: st.success(f"**{E_WIN} {row['symbol']} (WIN)** | Net PnL: **+${row['pnl_usd']:.2f}** ({t_r_str})")
                                else: st.error(f"**{E_LOSS} {row['symbol']} (LOSS)** | Net PnL: **${row['pnl_usd']:.2f}** ({t_r_str})")
                                
                                qual_str = f"{int(row['quality'])}/10" if pd.notnull(row['quality']) and row['quality'] > 0 else "N/A"
                                score_str = f"{int(row['score'])}/10" if pd.notnull(row['score']) and row['score'] > 0 else "N/A"
                                
                                risk_disp = "N/A"
                                if act_risk > 0:
                                    if act_risk > target_risk_usd * 1.25: risk_disp = "🔴 Poor (Oversized)"
                                    elif act_risk < target_risk_usd * 0.75: risk_disp = "🟡 Poor (Undersized)"
                                    else: risk_disp = "🟢 Excellent"
                                elif row['is_algo'] and r_realized <= -2.0:
                                    risk_disp = "🔴 Poor (Algo Leak)"
                                    
                                st.caption(f"Strategy: {row['setup_type']} • Entry Quality: {qual_str} • Exit Score: {score_str} • Risk Discipline: {risk_disp}")
                                
                                if not row['is_algo']:
                                    tgt_usd = target_risk_usd
                                    if act_risk == 0:
                                        st.markdown(f"""
                                        <div style="background-color: #3b2a2a; padding: 12px; border-radius: 8px; border-right: 5px solid #ff3366; margin-top: 10px; margin-bottom: 10px; direction: rtl; text-align: right;">
                                            <div style="font-size: 14px; font-weight: bold; margin-bottom: 5px; color: #ff9999;">⚠️ נתונים חסרים לניתוח סיכונים:</div>
                                            <div style="font-size: 13px; color: #e1e4e8;">הסטופ ההתחלתי לעסקה זו חסר, שגוי, או נקבע מעל מחיר הכניסה. לא ניתן לחשב True R.</div>
                                        </div>
                                        """, unsafe_allow_html=True)
                                    else:
                                        if act_risk > tgt_usd * 1.25: sizing_status = "⚠️ חריגה (סיכון גבוה מדי)"
                                        elif act_risk < tgt_usd * 0.75: sizing_status = "📉 חריגה (סיכון נמוך מדי)"
                                        else: sizing_status = "✅ גודל פוזיציה תקין"
                                        
                                        if r_realized <= -1.25: exec_status = "🚨 חריגה מהסטופ (הפסד משמעותי מ-1R)"
                                        elif r_realized < 0: exec_status = "✅ הפסד נשלט (לפי התוכנית)"
                                        elif r_realized < 1.0: exec_status = "⚖️ יציאה מוקדמת / Break-Even"
                                        elif r_realized >= 2.0: exec_status = "🏆 יעד רווח הושג (>2R)"
                                        else: exec_status = "👍 רווח חיובי"
                                        
                                        border_color = C_LOSS if r_realized < 0 else C_WIN
                                        
                                        st.markdown(f"""
                                        <div style="background-color: #1a1e24; padding: 12px; border-radius: 8px; border-right: 5px solid {border_color}; margin-top: 10px; margin-bottom: 10px; direction: rtl; text-align: right;">
                                            <div style="font-size: 14px; font-weight: bold; margin-bottom: 5px; color: #e1e4e8;">⚖️ בקרת סיכונים וביצוע:</div>
                                            <div style="font-size: 13px; color: #a3a3a3; margin-bottom: 3px;">
                                                <span style="color: #c9d1d9;">תכנון (Sizing):</span> Original Campaign Risk <b>${act_risk:.2f}</b> מול יעד מתוכנן <b>${tgt_usd:.2f}</b> ➔ <i>{sizing_status}</i>
                                            </div>
                                            <div style="font-size: 13px; color: #a3a3a3;">
                                                <span style="color: #c9d1d9;">תוצאה (Total R):</span> תנועה של <b>{r_realized:.2f}R</b> (PnL: ${row['pnl_usd']:.2f}) ➔ <i>{exec_status}</i>
                                            </div>
                                        </div>
                                        """, unsafe_allow_html=True)

                                n_val = row.get('management_notes')
                                if n_val and str(n_val) not in ["None", "Skipped", "nan"]:
                                    st.info(f"📝 **תובנות ניהול:** {n_val}")
                                
                                st.markdown("**📖 היסטוריית פעולות (Timeline):**")
                                for ev in row['events']:
                                    icon = "🛒" if ev['side'] == 'BUY' else ("💰" if ev['pnl'] > 0 else "🩸")
                                    dt_str = ev['date'].strftime('%Y-%m-%d')
                                    action = f"קנייה (חיזוק) {ev['qty']}" if ev['is_addon'] else (f"קנייה {ev['qty']}" if ev['side'] == 'BUY' else f"מכירה {abs(ev['qty'])}")
                                    pnl_str = f" | רווח: ${ev['pnl']:.2f}" if ev['side'] == 'SELL' else ""
                                    
                                    if ev['side'] == 'BUY': stop_str = f" | Initial Stop: ${row.get('init_sl_clean', 0):.2f}" if row.get('init_sl_clean', 0) > 0 else ""
                                    else: stop_str = f" | Exit Stop: ${ev['stop']:.2f}" if ev['stop'] > 0 else ""
                                    
                                    st.caption(f"> {icon} `{dt_str}` - {action} במחיר ${ev['price']:.2f}{pnl_str}{stop_str}")

                            st.markdown("---")
        else: st.info("No campaigns closed yet.")

    with tabs[4]:
        st.subheader("🛠️ DB Manager (Data Correction)")
        st.caption("כאן ניתן לתקן נתונים כולל סטופ התחלתי והערות ניהול.")
        if not df_sorted.empty:
            trade_list = [f"{r['trade_date'].strftime('%Y-%m-%d')} | {r['symbol']} ({r['side']}) | ID: {r['trade_id']}" for _, r in df_sorted.sort_values('trade_date', ascending=False).iterrows()]
            selected = st.selectbox("בחר טרייד לעריכה:", trade_list)
            t_id = selected.split("ID: ")[1]
            t_row = df_sorted[df_sorted['trade_id'] == t_id].iloc[0]
            
            with st.form("edit_form"):
                c1, c2, c3 = st.columns(3)
                n_setup = c1.text_input("Setup", value=str(t_row['setup_type']))
                n_qual = c2.number_input("Quality", value=int(t_row['quality']), step=1)
                n_score = c3.number_input("Score", value=int(t_row['score']), step=1)

                c4, c5, c6 = st.columns(3)
                n_sl = c4.number_input("Current Stop ($)", value=float(t_row['stop_loss']), step=0.01)
                n_init_sl = c5.number_input("Initial Stop ($)", value=float(t_row.get('initial_stop', t_row['stop_loss'])), step=0.01)
                n_img = c6.text_input("Image URL", value=str(t_row['image_url'] if t_row['image_url'] else ""))
                
                current_mgt_note = str(t_row.get('management_notes', '')) if str(t_row.get('management_notes')) not in ['None', 'Skipped', 'nan'] else ""
                n_mgt_notes = st.text_area("תובנות ניהול (Management Notes)", value=current_mgt_note)

                if st.form_submit_button("💾 Save to DB"):
                    supabase.table("trades").update({
                        "setup_type": n_setup, "quality": n_qual, "score": n_score,
                        "stop_loss": n_sl, "initial_stop": n_init_sl, "image_url": n_img if n_img else None,
                        "management_notes": n_mgt_notes if n_mgt_notes.strip() else "Skipped"
                    }).eq("trade_id", t_id).execute()
                    st.success("✅ Updated Successfully!"); st.rerun()
