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
import adaptive_risk_engine as are
import account_state as acc_state  # Sprint-27 W1: canonical NAV single-source (closes the dashboard fallback-as-truth gap; mirrors Telegram B1)
from dashboard_nav import nav_sidebar_render as _nav_sidebar_render  # Sprint-27 W1: pure B1-style sidebar NAV honesty helper
import telegram_formatters as tf  # Sprint-15: import-pure helpers (no telebot/supabase/engine import inside tf)
import algo_backtest_store as abs_store  # Phase ALGO-BT-1 W-BT4: pure read-only BACKTEST stats (no network/Supabase/write/live-ALGO coupling)
import algo_divergence  # Phase ALGO-2A W-2A1: pure observe-only live↔backtest edge-shape divergence (single-source-of-truth formatter, no engine/analytics/Supabase/network import)
import state_io
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

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



@st.cache_data(ttl=600, show_spinner=False)
def get_cached_market_regime():
    """מחשב משטר שוק ומאחסן ב-Streamlit cache 10 דקות — ללא קריאת רשת בכל re-run."""
    s = ec.get_cached_history("SPY", "1y", "1d")
    q = ec.get_cached_history("QQQ", "1y", "1d")
    return ec.compute_market_regime(s, q)

def load_settings():
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
    except: pass
    return {"total_deposited": 7500.0, "risk_pct_input": 0.5}

def save_settings(total_deposited, risk_pct_input, saved_nav=None):
    existing = load_settings()
    existing["total_deposited"] = total_deposited
    existing["risk_pct_input"] = risk_pct_input
    with open(SETTINGS_FILE, "w") as f:
        json.dump(existing, f)

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
regime = get_cached_market_regime()
# spy_hist נשלף מ-cache של engine_core (כבר חם) לשימוש הלאה
spy_hist = ec.get_cached_history("SPY", "1y", "1d")
if regime['ok']:
    rd = regime['data']
    st.sidebar.markdown(f"**{rd['color']} {rd['status']}**")
    st.sidebar.caption(rd['text'])
else:
    st.sidebar.caption("⏳ מחשב משטר שוק...")
st.sidebar.markdown("---")

st.sidebar.subheader("💼 Account Settings")

# Sprint-27 W1 — read NAV via the CANONICAL single source
# (`account_state.load()`), closing the divergence Data D-F1 flagged between
# this sidebar's own bare-`except` reader and the canonical resolver. The
# value is the same canonical NAV (D1: explicit-0 kept); only the *render*
# now tells the truth about freshness/source/fallback.
_acc = acc_state.load()
saved_nav = float(_acc["nav"])

_nav_kind, _nav_text = _nav_sidebar_render(_acc)
if _nav_kind == "success":
    st.sidebar.success(_nav_text)        # broker+fresh — unchanged green box
else:
    st.sidebar.warning(_nav_text)        # stale / fallback / unknown — honest

current_acc_size = saved_nav
total_deposited = st.sidebar.number_input("Base Capital (All-Time):", value=float(settings.get("total_deposited", 7500.0)), step=500.0)
risk_pct_input = st.sidebar.number_input("Target Risk (% per trade):", value=float(settings.get("risk_pct_input", 0.5)), step=0.1, max_value=5.0)

if total_deposited != settings.get("total_deposited") or risk_pct_input != settings.get("risk_pct_input"):
    save_settings(total_deposited, risk_pct_input, saved_nav)

target_risk_usd = current_acc_size * (risk_pct_input / 100)
st.sidebar.info(f"⚖️ **Risk Profile:** You are risking **{risk_pct_input:.2f}%** (${target_risk_usd:,.0f}) per trade.")

# Sprint-15 / DEC-20260515-012 — Risk Capital Basis declaration (labelling
# only; the engine still derives target risk from NAV — no basis change).
_nav_source = "broker" if "nav" in settings else "deposited"
st.sidebar.caption(tf.fmt_risk_capital_basis(current_acc_size, target_risk_usd,
                                             nav_source=_nav_source, ai_copy=True))

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

@st.cache_data(ttl=300, show_spinner=False)
def compute_live_portfolio_data(open_trades_dict, _acc_size, _target_risk_usd, _spy_hist):
    live_positions = []
    if not open_trades_dict: return pd.DataFrame(live_positions)

    # שלב 1: מחמם במקביל — סמבולים + SPY/QQQ לכל הפונקציות (MAE, TT, RS)
    all_symbols = list({row['symbol'] for row in open_trades_dict})
    prefetch_symbols_parallel(all_symbols + ["SPY", "QQQ"])

    # שלב 2: הלולאה הסדרתית — כל קריאה לרשת היא cache hit מיידי
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

        # מדדי מינרביני — חדשים
        init_risk = ec.compute_initial_risk_metrics(base_price, init_sl, base_qty, _acc_size)
        days_held = max((datetime.now() - pd.to_datetime(row['entry_date'])).days, 1) if row.get('entry_date') else 1
        r_eff = ec.compute_r_efficiency(total_campaign_r, days_held)
        mfe_mae = ec.compute_mfe_mae(sym, row.get('entry_date'), base_price, init_sl)

        # Sprint-15 / DEC-20260515-011 — dual R via the EXISTING engine
        # functions, SAME open_pnl input as the inline open_r_val above (no
        # new R math). Open_R stays the byte-identical PRIMARY number; a
        # sibling Account_R column is ADDED (design §2.2 — no format change to
        # Open_R).
        _is_algo_dash = str(setup).upper() == 'ALGO'
        _structure_r_dash = ec.compute_r_true(open_pnl, original_campaign_risk)
        _account_r_dash = ec.compute_r_target(open_pnl, _target_risk_usd)
        _rbasis_dash = tf.dual_r_basis(
            original_campaign_risk=original_campaign_risk,
            frozen_target_risk_usd=_target_risk_usd,
            is_algo=_is_algo_dash,
        )
        live_positions.append({
            'Symbol': sym, 'Setup': setup, 'Exposure_USD': pos_value, 'Exposure_Pct': weight_pct,
            'PnL': open_pnl, 'Open_R': open_r_val, 'Total_R': total_campaign_r, 'Score': score, 'Status': status, 'Sizing': sizing_status,
            'Structure_R': (_structure_r_dash if _rbasis_dash['structure_valid'] else None),
            'Account_R': (_account_r_dash if _rbasis_dash['account_valid'] else None),
            'R_Basis': _rbasis_dash['primary_basis_label'],
            'Sector': sec_b.get('sector') or "Other", 'Entry': entry, 'Current': curr,
            'OriginalRisk': original_campaign_risk, 'GivebackRisk': giveback_risk_usd, 'LockedProfit': locked_profit_usd,
            'CapitalRisk': current_open_loss_risk,
            'CampaignId': row.get('campaign_id'),
            'Qty': qty, 'Stop': sl, 'InitStop': init_sl, 'TargetRisk': _target_risk_usd,
            # מינרביני — סיכון
            'InitRisk_USD': init_risk['initial_risk_usd'],
            'InitRisk_Pct': init_risk['initial_risk_pct'],
            'SizingGrade': init_risk['sizing_grade'],
            # מינרביני — יעילות זמן
            'DaysHeld': days_held,
            'R_per_Day': r_eff['r_per_day'],
            'EfficiencyLabel': r_eff['efficiency_label'],
            'EfficiencyColor': r_eff['efficiency_color'],
            # מינרביני — MAE/MFE
            'MFE_R': mfe_mae.get('mfe_r'),
            'MAE_R': mfe_mae.get('mae_r'),
            'MFE_Pct': mfe_mae.get('mfe_pct'),
            'MAE_Pct': mfe_mae.get('mae_pct'),
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

def _warm_symbol_cache(sym):
    """מושך מחיר חי, היסטוריה שנתית, ומידע סקטור לסמל — לשימוש מקבילי.
    "1y" נדרש גם ל-MAE/MFE וגם ל-Trend Template (compute_trend_template_full)."""
    try:
        ec.get_live_price(sym)
        ec.get_cached_history(sym, "1y", "1d")
        ec.get_sector_bundle(sym)
    except Exception:
        pass

def prefetch_symbols_parallel(symbols, max_workers=8):
    """מחמם את כל ה-cache של engine_core לכל הסמלים במקביל.
    הלולאה הסדרתית שאחריה מקבלת cache hits מיידיים במקום קריאות רשת."""
    if not symbols:
        return
    with ThreadPoolExecutor(max_workers=min(len(symbols), max_workers)) as ex:
        futures = {ex.submit(_warm_symbol_cache, sym): sym for sym in symbols}
        for f in as_completed(futures):
            f.result()

if df.empty:
    st.warning("No data found. Check your filters.")
else:
    df_sorted = df.sort_values('trade_date')
    pos_res = ec.get_open_positions_campaign(df_sorted)
    actual_open_trades = pos_res["data"] if pos_res["ok"] else pd.DataFrame()

    # בניית lookup של קמפיין → רשימת BUY rows לחישוב Add-on quality
    campaign_buy_records = {}
    if not actual_open_trades.empty and 'campaign_id' in actual_open_trades.columns:
        for _, op in actual_open_trades.iterrows():
            cid = op.get('campaign_id')
            if cid and 'campaign_id' in df_sorted.columns:
                buys = df_sorted[(df_sorted['campaign_id'] == cid) & (df_sorted['side'].str.upper() == 'BUY')]
                campaign_buy_records[cid] = buys[['trade_date', 'price', 'quantity']].to_dict('records')
    
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

            stat_bucket = ec.classify_stat_bucket(setup, original_campaign_risk, target_risk_usd)
            algo_oversight = ec.compute_algo_risk_oversight_score(
                buys.iloc[0]['symbol'], total_pnl, target_risk_usd,
                original_campaign_risk, r_realized, quality_val
            ) if is_algo else None

            mgt_state_last = sells.iloc[-1].get('management_state', '')
            days_held_camp = max((sells.iloc[-1]['trade_date'] - first_date).days, 1)
            n_addons = max(len(buys) - 1, 0)
            intent = ec.classify_intent(setup, str(mgt_state_last), r_realized, days_held_camp, n_addons)
            mistake = ec.classify_mistake(intent, stat_bucket, total_pnl, str(mgt_notes_val or ''))

            closed_campaigns.append({
                'campaign_id': cid, 'symbol': buys.iloc[0]['symbol'], 'close_date': sells.iloc[-1]['trade_date'],
                'entry_date': first_date, 'avg_entry': avg_entry, 'avg_exit': avg_exit,
                'pnl_usd': total_pnl, 'setup_type': setup, 'quality': quality_val,
                'score': sells.iloc[-1]['score'], 'Total_Campaign_R': r_realized, 'is_algo': is_algo,
                'original_campaign_risk': original_campaign_risk, 'init_sl_clean': init_sl,
                'image_url': images[-1] if images else None, 'events': events, 'management_notes': mgt_notes_val,
                'stat_bucket': stat_bucket, 'algo_oversight': algo_oversight,
                'intent': intent, 'mistake': mistake,
            })
    camp_df = pd.DataFrame(closed_campaigns)

    _EMPTY_BUCKET = {
        "win_rate": 0, "adj_rr": 0, "expectancy_r": 0,
        "total_pnl": 0, "total_r": 0, "count": 0,
        "avg_win_r": 0, "avg_loss_r": 0,
        "profit_factor": 0, "payoff_consistency": None, "max_loss_r": 0,
    }

    def _bucket_stats(df):
        """Compute win rate, adj R/R, expectancy, and full edge metrics for a campaign DataFrame."""
        if df.empty:
            return _EMPTY_BUCKET.copy()
        wins = df[df['pnl_usd'] > 0]
        losses = df[df['pnl_usd'] < 0]
        wr = len(wins) / len(df)
        aw = float(wins['Total_Campaign_R'].mean()) if not wins.empty else 0.0
        al = float(abs(losses['Total_Campaign_R'].mean())) if not losses.empty else 1.0
        gross_profit_r = float(wins['Total_Campaign_R'].sum()) if not wins.empty else 0.0
        gross_loss_r = float(abs(losses['Total_Campaign_R'].sum())) if not losses.empty else 0.0
        pf = round(gross_profit_r / gross_loss_r, 2) if gross_loss_r > 0 else (99.0 if gross_profit_r > 0 else 0.0)
        pc = None
        if not wins.empty and len(wins) >= 2:
            median_win = float(wins['Total_Campaign_R'].median())
            pc = round(median_win / aw, 2) if aw > 0 else None
        max_loss = float(abs(losses['Total_Campaign_R'].min())) if not losses.empty else 0.0
        return {
            "win_rate": wr,
            "adj_rr": round(aw / al, 2) if al > 0 else 0,
            "expectancy_r": round((wr * aw) - ((1 - wr) * al), 2),
            "total_pnl": float(df['pnl_usd'].sum()),
            "total_r": float(df['Total_Campaign_R'].sum()),
            "count": len(df),
            "avg_win_r": round(aw, 2),
            "avg_loss_r": round(al, 2),
            "profit_factor": pf,
            "payoff_consistency": pc,
            "max_loss_r": round(max_loss, 2),
        }

    if not camp_df.empty:
        # Combined stats — exclude DATA_INCOMPLETE from Win Rate / Expectancy
        countable_df = camp_df[camp_df['stat_bucket'].apply(ec.is_stat_countable)]
        disc_df = camp_df[camp_df['stat_bucket'].apply(ec.is_discretionary_bucket)]
        algo_df = camp_df[camp_df['stat_bucket'] == ec.STAT_BUCKET_ALGO]
        ep_df   = camp_df[camp_df['stat_bucket'] == 'EP_MANUAL']
        vcp_df  = camp_df[camp_df['stat_bucket'] == 'VCP_MANUAL']

        combined_stats = _bucket_stats(countable_df)
        disc_stats = _bucket_stats(disc_df)
        algo_stats = _bucket_stats(algo_df)
        ep_stats   = _bucket_stats(ep_df)
        vcp_stats  = _bucket_stats(vcp_df)

        win_rate = combined_stats["win_rate"]
        adj_rr = combined_stats["adj_rr"]
        expectancy_r = combined_stats["expectancy_r"]
        total_pnl_net = camp_df['pnl_usd'].sum()
        total_r_net = camp_df['Total_Campaign_R'].sum()
    else:
        combined_stats = disc_stats = algo_stats = ep_stats = vcp_stats = _EMPTY_BUCKET.copy()
        disc_df = algo_df = countable_df = ep_df = vcp_df = pd.DataFrame()
        win_rate, adj_rr, expectancy_r, total_pnl_net, total_r_net = 0, 0, 0, 0, 0

    open_dict = actual_open_trades.to_dict('records') if not actual_open_trades.empty else []
    n_pos = len(open_dict)
    spinner_msg = f"מושך נתונים חיים ל-{n_pos} פוזיציות במקביל..." if n_pos > 0 else "מחשב..."
    with st.spinner(spinner_msg):
        live_df = compute_live_portfolio_data(open_dict, current_acc_size, target_risk_usd, spy_hist)
        
    total_open_pnl = live_df['PnL'].sum() if not live_df.empty else 0
    db_equity_expected = total_deposited + total_pnl_net + total_open_pnl
    reconciliation_gap = current_acc_size - db_equity_expected

    st.sidebar.markdown("---")
    st.sidebar.subheader("⚖️ Data Reconciliation")
    st.sidebar.write(f"Broker NAV: **${current_acc_size:,.2f}**")
    st.sidebar.write(f"Expected DB Equity: **${db_equity_expected:,.2f}**")
    # Sprint-15 / DEC-20260515-013 — classify the ALREADY-computed
    # reconciliation_gap (dashboard.py:404-405, reused read-only — NOT
    # recomputed) into Mark's 4 bands. dashboard.py:412 previously ASSERTED a
    # single cause ("Unrecorded Legacy PnL … עסקאות/הפקדות ישנות") which
    # violates invariant #1 — replaced with Mark's verbatim non-asserting
    # "cause unverified … manual verification required" wording.
    try:
        _max_open_risk = float(live_df["OriginalRisk"].max()) if (not live_df.empty and "OriginalRisk" in live_df) else 0.0
    except Exception:
        _max_open_risk = 0.0
    _recon_status = tf.classify_broker_reconciliation(
        current_acc_size, total_deposited, total_pnl_net,
        reconciliation_gap=reconciliation_gap,
        risk_pct_input=risk_pct_input,
        nav_source=_nav_source,
        max_open_campaign_risk=_max_open_risk,
    )
    _recon_line = tf.fmt_broker_reconciliation(_recon_status, ai_copy=True)
    if _recon_status["band"] == "Balanced":
        st.sidebar.success(_recon_line)
    elif _recon_status["band"] in ("Minor Difference", "Material Gap"):
        st.sidebar.warning(_recon_line)
    else:
        st.sidebar.error(_recon_line)

    st.sidebar.markdown("---")
    st.sidebar.subheader("🎯 Adaptive Risk")

    try:
        _closed_for_rec = are.compute_closed_campaigns(raw_df) if not raw_df.empty else []
        _risk_rec = are.compute_adaptive_risk(_closed_for_rec, risk_pct_input, current_acc_size)
    except Exception:
        _risk_rec = {"ok": False, "error": "compute_failed"}

    if _risk_rec.get("ok"):
        _rec_pct = _risk_rec["recommended_risk_pct"]
        _rec_usd = _risk_rec["recommended_risk_usd"]
        _dir = _risk_rec.get("direction", "hold")
        _dir_emoji = {"up": "⬆️", "down_fast": "⬇️", "hold": "➡️"}.get(_dir, "➡️")
        st.sidebar.write(
            f"{_dir_emoji} **המלצה:** `{_rec_pct:.2f}%` (${_rec_usd:,.0f}) — "
            f"_{_risk_rec.get('step_type', '')}_"
        )

        _delta_pct = risk_pct_input - _rec_pct
        if abs(_delta_pct) < 0.01:
            st.sidebar.success(f"🟢 מוגדר תואם המלצה ({risk_pct_input:.2f}%)")
        elif _delta_pct > 0:
            st.sidebar.warning(
                f"⚠️ חורג לחיוב — מוגדר {risk_pct_input:.2f}% > מומלץ {_rec_pct:.2f}% "
                f"(+{_delta_pct:.2f}% יותר אגרסיבי)"
            )
        else:
            st.sidebar.info(
                f"💡 חורג לשלילה — מוגדר {risk_pct_input:.2f}% < מומלץ {_rec_pct:.2f}% "
                f"({_delta_pct:.2f}% פחות אגרסיבי)"
            )
    else:
        st.sidebar.caption(_risk_rec.get("message", "לא ניתן לחשב המלצה"))

    if not live_df.empty and 'OriginalRisk' in live_df.columns and target_risk_usd > 0:
        _disc_open = live_df[live_df['Setup'].astype(str).str.upper() != 'ALGO']
        _disc_open = _disc_open[_disc_open['OriginalRisk'] > 0]
        if not _disc_open.empty:
            _avg_sizing = (_disc_open['OriginalRisk'] / target_risk_usd).mean()
            _n_open = len(_disc_open)
            _dev_pct = (_avg_sizing - 1.0) * 100
            if 0.95 <= _avg_sizing <= 1.15:
                st.sidebar.success(
                    f"🟢 פוזיציות פתוחות ({_n_open}): {_avg_sizing:.2f}x — Ideal"
                )
            elif _avg_sizing < 0.95:
                st.sidebar.info(
                    f"🟡 פוזיציות פתוחות ({_n_open}): {_avg_sizing:.2f}x — "
                    f"חורג לשלילה ({_dev_pct:+.0f}% Undersized)"
                )
            else:
                st.sidebar.warning(
                    f"🔴 פוזיציות פתוחות ({_n_open}): {_avg_sizing:.2f}x — "
                    f"חורג לחיוב ({_dev_pct:+.0f}% Oversized)"
                )

    _target_wr = 0.50
    _actual_wr = disc_stats.get('win_rate', 0)
    _wr_n = disc_stats.get('count', 0)
    if _wr_n > 0:
        _wr_delta = (_actual_wr - _target_wr) * 100
        if abs(_wr_delta) < 2:
            st.sidebar.success(f"🟢 Win Rate {_actual_wr*100:.1f}% (N={_wr_n}) — תואם יעד 50%")
        elif _wr_delta > 0:
            st.sidebar.success(
                f"🟢 Win Rate {_actual_wr*100:.1f}% (N={_wr_n}) — "
                f"חורג {_wr_delta:+.1f}% לחיוב מיעד 50%"
            )
        else:
            st.sidebar.warning(
                f"🟡 Win Rate {_actual_wr*100:.1f}% (N={_wr_n}) — "
                f"חורג {_wr_delta:.1f}% מיעד 50%"
            )

    st.sidebar.markdown("---")
    st.sidebar.subheader("🤖 AI Master Context Export")

    # Phase 6: load persisted position states from risk monitor
    try:
        # Sprint 14: state file relocated to the /app/state named volume
        # (state_io.RM_STATE_FILE) — read-only consumer, path follows the
        # single shared constant so it never drifts from the writer.
        with open(state_io.RM_STATE_FILE, "r", encoding="utf-8") as _f:
            _rm_positions = json.load(_f).get("positions", {})
    except Exception:
        _rm_positions = {}

    # Phase 6: precompute context data per campaign (used in Section 2 + 4)
    _pos_context_map: dict = {}

    ai_str = f"# 🛡️ Sentinel AI - Master Context Report\n\n"
    ai_str += f"## ⚠️ Sentinel Observer Note\n"
    ai_str += f"- ALGO positions (management_mode=algo_observed) are managed externally. "
    ai_str += f"Sentinel provides oversight only. Never issue exit or stop instructions for ALGO positions.\n"
    ai_str += f"- DATA_INCOMPLETE campaigns are excluded from Win Rate and Expectancy calculations.\n\n"
    ai_str += f"## 📊 1. Performance Matrix & Risk Profile\n"
    ai_str += f"- Broker NAV: ${current_acc_size:,.2f} | Base Capital: ${total_deposited:,.2f}\n"
    ai_str += f"- Target Risk Per Trade: {risk_pct_input:.2f}% (${target_risk_usd:,.2f})\n"
    ai_str += f"- All-Time Return (NAV): {all_time_return_pct:.2f}%\n"
    ai_str += f"- Win Rate (Discretionary only, excl. DATA_INCOMPLETE): {disc_stats['win_rate']*100:.1f}% ({disc_stats['count']} trades)\n"
    ai_str += f"- Win Rate (Combined countable): {combined_stats['win_rate']*100:.1f}% ({combined_stats['count']} trades)\n"
    ai_str += f"- ALGO campaigns: {algo_stats['count']} | ALGO Net PnL: ${algo_stats['total_pnl']:,.2f}\n"
    ai_str += f"- DB Net PnL (all): ${total_pnl_net:.2f}\n"
    # Sprint-15 / DEC-20260515-012 — Risk Capital Basis declaration (NAV).
    ai_str += f"- {tf.fmt_risk_capital_basis(current_acc_size, target_risk_usd, nav_source=_nav_source, ai_copy=True)}\n"
    # Sprint-15 / DEC-20260515-013 — Broker Reconciliation Status (reuses the
    # same dashboard.py:404-405 gap; non-asserting wording, Mark §3).
    try:
        ai_str += f"- {tf.fmt_broker_reconciliation(_recon_status, ai_copy=True)}\n"
    except Exception:
        pass
    ai_str += f"- Expectancy: {expectancy_r:.2f}R per trade | Adjusted R/R: {adj_rr:.2f}:1\n\n"
    ai_str += f"## 🔭 2. Live Battlefield (Open Positions)\n"
    # שימוש במחירים שכבר חושבו ב-live_df — ללא קריאת רשת כפולה
    _live_price_lookup = dict(zip(live_df['Symbol'], live_df['Current'])) if not live_df.empty else {}
    if not actual_open_trades.empty:
        for _, row in actual_open_trades.iterrows():
            sym, qty, entry, setup, sl, init_sl = row['symbol'], row['quantity'], row['price'], row['setup_type'], row['stop_loss'], row['initial_stop']
            curr_p = _live_price_lookup.get(sym, entry)
            open_pnl = (curr_p - entry) * qty
            base_price = row.get('base_price', entry)
            base_qty = row.get('base_qty', qty)
            
            init_sl_clean = init_sl if (init_sl > 0 and init_sl < base_price) else 0
            original_campaign_risk = (base_price - init_sl_clean) * base_qty if init_sl_clean > 0 else 0
            
            is_algo_pos = str(setup).upper() == 'ALGO'
            # Sprint-15 / Mark §1 — the conflated single OpenR + standalone
            # RiskBasis token (the clearest mislabel: a manual Structure-R
            # number printed next to `RiskBasis: Target`) is replaced by the
            # canonical dual-R fragment. Both numbers come from the EXISTING
            # engine functions with the SAME open_pnl input — Structure R
            # (compute_r_true) is byte-identical to today's manual OpenR;
            # Account R (compute_r_target) is byte-identical to today's ALGO
            # OpenR. risk_basis stays an internal field (not displayed).
            _struct_r_ai = ec.compute_r_true(open_pnl, original_campaign_risk)
            _acct_r_ai = ec.compute_r_target(open_pnl, target_risk_usd)
            _rbasis_ai = tf.dual_r_basis(
                original_campaign_risk=original_campaign_risk,
                frozen_target_risk_usd=target_risk_usd,
                is_algo=is_algo_pos,
            )
            open_r_str = tf.fmt_dual_r(
                _struct_r_ai, _acct_r_ai,
                structure_valid=_rbasis_ai["structure_valid"],
                account_valid=_rbasis_ai["account_valid"],
                is_algo=is_algo_pos, ai_copy=True,
            )
            if is_algo_pos:
                risk_dev = ""
            elif original_campaign_risk > 0:
                risk_dev = f" | Planned Risk: ${target_risk_usd:.0f} | Original Campaign Risk: ${original_campaign_risk:,.0f}"
            else:
                risk_dev = " | ⚠️ Missing Initial Stop Data"

            mgmt_mode = ec.classify_management_mode(setup, sym)
            risk_basis = ec.classify_risk_basis(sl, base_price, setup, target_risk_usd)
            risk_vis = ec.compute_risk_visibility_score(setup, sl, base_price, target_risk_usd)
            if is_algo_pos:
                stop_display = "External / Unknown (ALGO managed)"
                init_stop_str = "External / Unknown"
            else:
                init_stop_str = f"${init_sl_clean:.2f}" if init_sl_clean > 0 else "N/A"
                stop_display = f"${sl:.2f}"
            earnings_info = ec.fetch_next_earnings_date(sym)
            earnings_str = earnings_info['cushion_verdict']
            if earnings_info.get('date'):
                earnings_str += f" ({earnings_info['date'].strftime('%d/%m/%Y')})"
            _days_to_earn = earnings_info.get('days_to_event') if earnings_info.get('ok') else None

            # Phase 6 — enriched context block
            _campaign_id = row.get('campaign_id', '')
            _rm_pos = _rm_positions.get(_campaign_id, {})
            _ctx = ec.build_position_context_data(
                sym=sym, setup=setup, entry=entry, curr_p=curr_p,
                qty=qty, sl=sl, init_sl=init_sl,
                base_price=base_price, base_qty=base_qty,
                realized_pnl=float(row.get('realized_pnl', 0.0)),
                target_risk_usd=target_risk_usd,
                management_mode=mgmt_mode,
                days_to_earnings=_days_to_earn,
                position_state=_rm_pos.get('position_state', ''),
                state_label=_rm_pos.get('state_label', ''),
                breakeven_alerted=_rm_pos.get('breakeven_alerted', False),
            )
            _pos_context_map[_campaign_id] = _ctx

            _sizing = _ctx['sizing']
            _sizing_known = _sizing.get('classification', 'Unknown') != 'Unknown'
            _sizing_str = (f"{_sizing['classification']} ({_sizing['sizing_ratio']:.2f}x)"
                           if _sizing_known else "N/A (missing data)")
            _ev = _ctx['event_risk']
            _ev_str = (f"⚠️ Event Risk ({_ev['days']}d, {_ev['severity']})"
                       if _ev.get('active') else "Clear")
            _state_str = _ctx['state_label'] or _ctx['position_state'] or "unknown"

            # Sprint-15 / Mark §1: standalone misleading `RiskBasis:` display
            # token removed (it could read `Target` next to a Structure-R
            # number). risk_basis kept as an internal/runtime field only. The
            # dual labelled R fragment carries the correct basis now.
            ai_str += f"- {sym} [{setup}] | Mode: {mgmt_mode} | Visibility: {risk_vis}/100\n"
            ai_str += f"  Entry: ${entry:.2f} | Curr: ${curr_p:.2f} | InitStop: {init_stop_str} | CurrStop: {stop_display} | OpenPnL: ${open_pnl:.2f} | {open_r_str}{risk_dev}\n"
            ai_str += f"  Earnings: {earnings_str} | EventRisk: {_ev_str}\n"
            ai_str += f"  State: {_state_str} | Sizing: {_sizing_str}\n"
            if not is_algo_pos and _ctx['has_profit']:
                ai_str += (f"  Protected Profit: ${_ctx['protected_profit']:.0f}"
                           f" | Giveback to Stop: ${_ctx['giveback_usd']:.0f}"
                           f" ({_ctx['giveback_pct']:.0f}%)\n")
            if not is_algo_pos and _ctx['capital_at_risk'] > 0:
                _be_str = "✅ Done" if _ctx['breakeven_alerted'] else "⚠️ Pending"
                ai_str += (f"  Capital at Risk: ${_ctx['capital_at_risk']:.0f}"
                           f" | Breakeven Protocol: {_be_str}\n")
    else: ai_str += "No open positions.\n"
    
    ai_str += f"\n## 📅 3. Execution Archive (Recent Campaigns)\n"
    if not camp_df.empty:
        for _, row in camp_df.sort_values('close_date', ascending=False).head(20).iterrows():
            r_val = row['Total_Campaign_R']
            if row['is_algo']: t_r_str = f"{r_val:.2f}R (Target Risk Base)"
            elif row['original_campaign_risk'] == 0: t_r_str = "N/A (Missing Initial Stop Data)"
            else: t_r_str = f"{r_val:.2f}R (True Risk Base)"
                
            bucket = row.get('stat_bucket', 'UNKNOWN')
            ai_str += f"\n### {row['symbol']} [{row['setup_type']}] | Net PnL: ${row['pnl_usd']:.2f} | Total Campaign R: {t_r_str} | Bucket: {bucket}\n"
            q_str = f"{int(row['quality'])}/10" if row['quality'] > 0 else "N/A"
            s_str = f"{int(row['score'])}/10" if row['score'] > 0 else "N/A"
            algo_ov = row.get('algo_oversight')
            oversight_str = f" | ALGO Oversight: {algo_ov['score']}/100 ({algo_ov['label']})" if algo_ov else ""
            intent_str = ec.INTENT_LABELS.get(row.get('intent', 'unknown'), '⚪ Unknown')
            mistake_str = ec.MISTAKE_LABELS.get(row.get('mistake', ''), '') if row.get('mistake') else ''
            ai_str += f"- Strategy Quality: {q_str} | Execution Score: {s_str}{oversight_str}\n"
            ai_str += f"- Intent: {intent_str}"
            if mistake_str:
                ai_str += f" | Loss Type: {mistake_str}"
            ai_str += "\n"
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

    # ── Next Required Decisions ──────────────────────────────────────────────
    ai_str += f"\n## 🧭 4. Next Required Decisions\n"
    if not live_df.empty:
        for _, pos in live_df.iterrows():
            decisions = []
            is_algo_pos = str(pos['Setup']).upper() == 'ALGO'
            _sym_cid = pos.get('campaign_id', '')
            _pctx = _pos_context_map.get(_sym_cid, {})

            if pos['CapitalRisk'] > 0 and not is_algo_pos:
                decisions.append(f"סטופ מתחת לבסיס — סיכון הון פתוח ${pos['CapitalRisk']:,.0f}")
            if pos['GivebackRisk'] > 0:
                decisions.append(f"Giveback ${pos['GivebackRisk']:,.0f} — לבחון האם לקדם סטופ")
            if pos['Total_R'] >= 2.0 and not is_algo_pos:
                decisions.append(f"הגעה ל-{pos['Total_R']:.1f}R — לשקול חלוקת רווחים / הזזת סטופ")
            earnings_info = ec.fetch_next_earnings_date(pos['Symbol'])
            if earnings_info['ok'] and earnings_info.get('days_to_event', 99) <= 14:
                decisions.append(f"דוח רווחים תוך {earnings_info['days_to_event']} ימים — לקבל החלטה על גודל פוזיציה")

            # Phase 6 — state-machine & sizing context
            _p_state = _pctx.get('position_state', '')
            if _p_state == 'BROKEN':
                decisions.append("מצב BROKEN — לבחון יציאה לפי תוכנית מוגדרת מראש")
            elif _p_state == 'DEAD_MONEY':
                decisions.append("מצב Dead Money — לשקול צמצום אם יש הזדמנות טובה יותר")
            _ev = _pctx.get('event_risk', {})
            if _ev.get('active') and _ev.get('days') is not None and _ev['days'] <= 7:
                decisions.append(f"Event Risk קריטי — דוחות בעוד {_ev['days']} ימים ({_ev['severity']})")
            _sz = _pctx.get('sizing', {})
            if _sz.get('alert_level') in ('warning', 'danger') and not is_algo_pos:
                decisions.append(f"Sizing: {_sz.get('label', '')} — לבדוק יחס סיכון")

            if decisions:
                ai_str += f"- **{pos['Symbol']}**: " + " | ".join(decisions) + "\n"
        if not any(True for _ in live_df.iterrows()):
            ai_str += "- אין פוזיציות פתוחות.\n"
    else:
        ai_str += "- אין פוזיציות פתוחות.\n"

    # NAV freshness note at end of export
    nav_info_export = ec.get_nav_with_freshness()
    ai_str += f"\n---\n_NAV freshness: {nav_info_export['freshness_label']}_\n"

    st.sidebar.text_area("📋 העתק (Ctrl+A -> Ctrl+C):", value=ai_str, height=450)

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("All-Time Return (NAV)", f"{all_time_return_pct:+.1f}%")
    m2.metric("Win Rate (DB)", f"{win_rate*100:.1f}%")
    m3.metric("Payoff Ratio (R:R)", f"{adj_rr:.2f}")
    m4.metric("Total R Realized (DB)", f"{total_r_net:.1f}R")
    m5.metric("Total Net PnL (DB)", f"${total_pnl_net:,.2f}")

    tabs = st.tabs(["🚀 Command Center (Live)", "📊 Performance Matrix", "🎯 Strategy Forensics", "📅 Visual Journal", "🧠 Minervini Mentor", "🛠️ DB Manager"])

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

            # ── Portfolio Heat Map — חשיפה לפי אשכול ────────────────────────
            st.markdown("---")
            st.subheader("🔥 Portfolio Heat Map — חשיפה לפי אשכול")
            hm_rows = []
            for cluster, grp in live_df.groupby('Setup'):
                hm_rows.append({
                    "אשכול": cluster,
                    "פוזיציות": len(grp),
                    "חשיפה $": grp['Exposure_USD'].sum(),
                    "חשיפה %": grp['Exposure_Pct'].sum(),
                    "Open R": grp['Open_R'].sum(),
                    "סיכון הון $": grp['CapitalRisk'].sum(),
                    "Giveback $": grp['GivebackRisk'].sum(),
                })
            cash_exposure = max(current_acc_size - live_df['Exposure_USD'].sum(), 0)
            hm_rows.append({
                "אשכול": "💵 מזומן",
                "פוזיציות": 0,
                "חשיפה $": cash_exposure,
                "חשיפה %": cash_exposure / current_acc_size * 100 if current_acc_size > 0 else 0,
                "Open R": 0,
                "סיכון הון $": 0,
                "Giveback $": 0,
            })
            hm_df = pd.DataFrame(hm_rows)
            st.dataframe(
                hm_df.style.format({
                    "חשיפה $": "${:,.0f}", "חשיפה %": "{:.1f}%",
                    "Open R": "{:+.2f}R", "סיכון הון $": "${:,.0f}", "Giveback $": "${:,.0f}",
                }),
                use_container_width=True, hide_index=True,
            )

            # ── תכנון vs בפועל — מינרביני ─────────────────────────────────
            st.markdown("---")
            st.subheader("📐 ניתוח סיכונים — תכנון vs בפועל (Minervini)")
            for _, pos in live_df.iterrows():
                is_algo = str(pos['Setup']).upper() == 'ALGO'
                with st.expander(f"{pos['EfficiencyColor']} {pos['Symbol']} | {pos['Status']} | {pos['Total_R']:.2f}R | {pos['DaysHeld']}d"):
                    dq_primary, dq_risk, dq_label = ec.compute_data_quality_badge(
                        pos['Setup'], pos['Entry'], pos['Qty'], pos['Stop'], pos['InitStop'], pos['TargetRisk']
                    )
                    badge_str = f"{dq_primary} {dq_risk} `{dq_label}`" if dq_risk else f"{dq_primary} `{dq_label}`"
                    earnings_info = ec.fetch_next_earnings_date(pos['Symbol'])
                    earnings_str = earnings_info['cushion_verdict']
                    if earnings_info.get('date'):
                        earnings_str += f" ({earnings_info['date'].strftime('%d/%m/%Y')})"
                    st.caption(f"🏷️ Data Quality: {badge_str}   |   📅 דו\"ח רווחים: {earnings_str}")
                    pa1, pa2, pa3, pa4 = st.columns(4)

                    # עמודה 1: סיכון
                    with pa1:
                        st.markdown("**⚖️ סיכון**")
                        planned_r = target_risk_usd
                        actual_r = pos['InitRisk_USD']
                        if not is_algo and actual_r > 0:
                            dev_pct = (actual_r - planned_r) / planned_r * 100 if planned_r > 0 else 0
                            grade_map = {"ok": "✅ תקין", "oversized": "⚠️ גדול מדי", "undersized": "📉 קטן מדי", "missing_data": "❓ חסר סטופ"}
                            grade_label = grade_map.get(pos['SizingGrade'], "❓")
                            st.metric("תכנון", f"${planned_r:,.0f} ({risk_pct_input:.1f}%)")
                            st.metric("בפועל", f"${actual_r:,.0f} ({pos['InitRisk_Pct']:.2f}%)", delta=f"{dev_pct:+.1f}%")
                            st.caption(f"שיפוט מינרביני: {grade_label}")
                        else:
                            st.caption("ALGO — סיכון לפי מגבלת סמל")

                    # עמודה 2: ביצועים
                    with pa2:
                        st.markdown("**📈 ביצועים**")
                        st.metric("Total R", f"{pos['Total_R']:.2f}R")
                        st.metric("R ליום", f"{pos['R_per_Day']:.3f}", help="R שהושג חלקי מספר ימי ההחזקה")
                        st.caption(f"יעילות הון: {pos['EfficiencyLabel']}")

                    # עמודה 3: MAE / MFE
                    with pa3:
                        st.markdown("**🎯 MAE / MFE**")
                        if pos['MFE_R'] is not None:
                            st.metric("MFE (שיא)", f"{pos['MFE_R']:.2f}R ({pos['MFE_Pct']:.1f}%)", help="המקסימום שהמניה עלתה מאז הכניסה")
                            st.metric("MAE (תחתית)", f"{pos['MAE_R']:.2f}R ({pos['MAE_Pct']:.1f}%)", help="המקסימום שהמניה ירדה מאז הכניסה")
                            if pos['MFE_R'] > 0 and pos['Total_R'] < pos['MFE_R'] * 0.5:
                                st.warning(f"⚠️ בשיא הגעת ל-{pos['MFE_R']:.1f}R — נוצל רק {pos['Total_R']/pos['MFE_R']*100:.0f}% מהפוטנציאל")
                        else:
                            st.caption("MAE/MFE: אין נתון (כניסה > 12 חודשים)")

                    # עמודה 4: Trend Template + Add-on Quality
                    with pa4:
                        st.markdown("**📋 Trend Template (Minervini)**")
                        tt = ec.compute_trend_template_full(pos['Symbol'])
                        if tt['ok']:
                            td = tt['data']
                            cmap_tt = {True: "✅", False: "❌", None: "➖"}
                            score_color = "🟢" if td['passed'] >= 7 else ("🟡" if td['passed'] >= 5 else "🔴")
                            st.metric("ציון", f"{td['passed']}/8 {score_color}")
                            tt_labels = ["מחיר>MA150/200", "MA150>MA200", "MA200↑", "MA50>MA150/200", "מחיר>MA50", "30%↑שפל", "25%↓שיא", "RS>SPY"]
                            for lbl, val in zip(tt_labels, td['criteria'].values()):
                                st.caption(f"{cmap_tt[val]} {lbl}")
                        else:
                            st.caption("Trend Template: אין נתונים")

                        st.markdown("**🔺 Add-on Quality**")
                        cid = pos.get('CampaignId')
                        buy_recs = campaign_buy_records.get(cid, [])
                        addon_res = ec.analyze_addon_quality(buy_recs)
                        if addon_res['has_addons']:
                            worst = addon_res['worst_addon_vs_base']
                            if addon_res['all_addons_higher']:
                                st.caption(f"✅ פירמידה תקינה ({addon_res['addon_count']} חיזוקים, גרוע: {worst:+.1f}%)")
                            else:
                                st.caption(f"⚠️ Average Down! ({addon_res['addon_count']} חיזוקים, גרוע: {worst:+.1f}%)")
                        else:
                            st.caption("➖ ללא חיזוקים (כניסה אחת)")
        else:
            st.info("No open positions to display.")

    with tabs[1]:
        # ── Trader Edge Panel ─────────────────────────────────────────────────
        st.subheader("📊 Trader Edge Panel")
        st.caption("כל מדד מסוכם לפי scope עם פרשנות מינרביני והחלטה.")

        if not camp_df.empty:
            def _sizing_eff(df):
                if df.empty or target_risk_usd <= 0:
                    return None
                v = df[df['original_campaign_risk'] > 0]
                return float((v['original_campaign_risk'] / target_risk_usd).mean()) if not v.empty else None

            _se_disc = _sizing_eff(disc_df)
            _se_ep   = _sizing_eff(ep_df)
            _se_vcp  = _sizing_eff(vcp_df)

            def _fr(v): return f"{v:.2f}R" if v is not None else "—"
            def _fpct(v): return f"{v*100:.1f}%" if v is not None else "—"
            def _fx(v): return f"{v:.2f}x" if v is not None else "—"
            def _fusd(v): return f"${v:+,.0f}" if v is not None else "—"
            def _fv(v): return f"{v:.2f}" if v is not None else "—"

            _panel_rows = [
                ("N (עסקאות)",         disc_stats["count"],             ep_stats["count"],             vcp_stats["count"],             algo_stats["count"]),
                ("Win Rate",           _fpct(disc_stats["win_rate"]),   _fpct(ep_stats["win_rate"]),   _fpct(vcp_stats["win_rate"]),   "—"),
                ("Avg Win R",          _fr(disc_stats["avg_win_r"]),    _fr(ep_stats["avg_win_r"]),    _fr(vcp_stats["avg_win_r"]),    "—"),
                ("Avg Loss R",         _fr(disc_stats["avg_loss_r"]),   _fr(ep_stats["avg_loss_r"]),   _fr(vcp_stats["avg_loss_r"]),   "—"),
                ("W/L Ratio",          _fv(disc_stats["adj_rr"]),       _fv(ep_stats["adj_rr"]),       _fv(vcp_stats["adj_rr"]),       "—"),
                ("Expectancy",         _fr(disc_stats["expectancy_r"]), _fr(ep_stats["expectancy_r"]), _fr(vcp_stats["expectancy_r"]), "—"),
                ("Profit Factor",      _fv(disc_stats["profit_factor"]),_fv(ep_stats["profit_factor"]),_fv(vcp_stats["profit_factor"]),"—"),
                ("Payoff Consistency", _fv(disc_stats["payoff_consistency"]) if disc_stats["payoff_consistency"] else "—",
                                       _fv(ep_stats["payoff_consistency"]) if ep_stats["payoff_consistency"] else "—",
                                       _fv(vcp_stats["payoff_consistency"]) if vcp_stats["payoff_consistency"] else "—", "—"),
                ("Max Loss R",         _fr(disc_stats["max_loss_r"]),   _fr(ep_stats["max_loss_r"]),   _fr(vcp_stats["max_loss_r"]),   "—"),
                ("Sizing Efficiency",  _fx(_se_disc) if _se_disc else "—", _fx(_se_ep) if _se_ep else "—", _fx(_se_vcp) if _se_vcp else "—", "—"),
                ("Net PnL ($)",        _fusd(disc_stats["total_pnl"]),  _fusd(ep_stats["total_pnl"]),  _fusd(vcp_stats["total_pnl"]),  _fusd(algo_stats["total_pnl"])),
            ]
            _panel_df = pd.DataFrame(_panel_rows, columns=["מדד", "ידני (Disc)", "EP", "VCP", "ALGO"])
            st.dataframe(_panel_df, use_container_width=True, hide_index=True)

            # ── Decision Matrix for Manual scope ─────────────────────────────
            st.markdown("#### 🎯 Decision Matrix — ידני")
            _dm1, _dm2 = st.columns(2)

            with _dm1:
                _e = disc_stats["expectancy_r"]
                _n = disc_stats["count"]
                if _e < 0:
                    st.error(f"🚨 Expectancy {_e:.2f}R — שלילי. עצור הגדלת סיכון מיידית.")
                elif _e < 0.25:
                    st.warning(f"⚠️ Expectancy {_e:.2f}R (N={_n}) — Edge חלש. פעל בסיכון מינימלי.")
                elif _e >= 0.60 and _n >= 30:
                    st.success(f"🔥 Expectancy {_e:.2f}R (N={_n}) — חזק. ניתן לשקול הגדלה הדרגתית.")
                elif _e >= 0.60:
                    st.info(f"✅ Expectancy {_e:.2f}R — טוב אך N={_n} קטן. אל תגדיל עדיין.")
                else:
                    st.success(f"✅ Expectancy {_e:.2f}R (N={_n}) — תקין. המשך בגודל רגיל.")

                _wlr = disc_stats["adj_rr"]
                if _wlr >= 2.0:
                    st.success(f"🔥 W/L Ratio {_wlr:.2f}:1 — חזק. שמור על חיתוך הפסדים.")
                elif _wlr >= 1.5:
                    st.success(f"✅ W/L Ratio {_wlr:.2f}:1 — טוב.")
                elif _wlr >= 1.2:
                    st.warning(f"⚠️ W/L Ratio {_wlr:.2f}:1 — בינוני. שפר ניהול רווחים.")
                else:
                    st.error(f"🚨 W/L Ratio {_wlr:.2f}:1 — אין Edge ברור. עצור הגדלה.")

                _pf = disc_stats["profit_factor"]
                if _pf >= 1.7:
                    st.success(f"🔥 Profit Factor {_pf:.2f} — חזק.")
                elif _pf >= 1.3:
                    st.info(f"✅ Profit Factor {_pf:.2f} — תקין.")
                elif _pf >= 1.0:
                    st.warning(f"⚠️ Profit Factor {_pf:.2f} — חלש. שפר או צמצם.")
                else:
                    st.error(f"🚨 Profit Factor {_pf:.2f} — מפסיד. בדוק דחוף.")

            with _dm2:
                _ml = disc_stats["max_loss_r"]
                if _ml > 1.25:
                    st.error(f"🚨 Max Loss {_ml:.2f}R — חריגת סטופ. בדוק ביצוע.")
                elif _ml > 1.0:
                    st.warning(f"⚠️ Max Loss {_ml:.2f}R — גבולי. לבדוק.")
                else:
                    st.success(f"✅ Max Loss {_ml:.2f}R — בשליטה.")

                _pc = disc_stats["payoff_consistency"]
                if _pc is not None:
                    if _pc >= 0.70:
                        st.success(f"✅ Payoff Consistency {_pc:.2f} — עקבי, לא תלוי בחריגים.")
                    elif _pc >= 0.40:
                        st.info(f"💡 Payoff Consistency {_pc:.2f} — סביר.")
                    else:
                        st.warning(f"⚠️ Payoff Consistency {_pc:.2f} — תוצאות תלויות בחריגים.")

                if _se_disc is not None:
                    if _se_disc < 0.60:
                        st.warning(f"📉 Sizing Efficiency {_se_disc:.2f}x — נמוך מדי. הגדל גודל בכניסות עתידיות.")
                    elif _se_disc < 0.85:
                        st.info(f"💡 Sizing Efficiency {_se_disc:.2f}x — Undersized. שפר בהדרגה.")
                    elif _se_disc <= 1.15:
                        st.success(f"✅ Sizing Efficiency {_se_disc:.2f}x — אידיאלי.")
                    elif _se_disc <= 1.40:
                        st.warning(f"⚠️ Sizing Efficiency {_se_disc:.2f}x — מוגדל. עקוב.")
                    else:
                        st.error(f"🚨 Sizing Efficiency {_se_disc:.2f}x — חריגה. בדוק דחוף.")

            _algo_drag = algo_stats["total_pnl"]
            _algo_msg = f"🤖 ALGO Drag: ${_algo_drag:+,.0f} | {algo_stats['count']} קמפיינים — מנוהל חיצונית. לא לערבב עם ידני בסטטיסטיקה."
            if _algo_drag < -200:
                st.warning(_algo_msg)
            else:
                st.info(_algo_msg)
        else:
            st.info("אין קמפיינים סגורים עדיין.")

        st.markdown("---")
        if not camp_df.empty:
            # ── סטטיסטיקות נפרדות: Discretionary / ALGO / Combined ─────────────
            st.subheader("📊 ביצועים לפי דלי סטטיסטיקה")
            bs1, bs2, bs3 = st.columns(3)
            with bs1:
                st.markdown("**🎯 Discretionary (Manual)**")
                st.metric("עסקאות", disc_stats["count"])
                st.metric("Win Rate", f"{disc_stats['win_rate']*100:.1f}%")
                st.metric("Expectancy", f"{disc_stats['expectancy_r']:.2f}R")
                st.metric("Adj R/R", f"{disc_stats['adj_rr']:.2f}:1")
                st.metric("Net R", f"{disc_stats['total_r']:.1f}R")
                if disc_stats["count"] == 0:
                    st.caption("⚪ אין קמפיינים דיסקרשן")
            with bs2:
                st.markdown("**🟠 ALGO Observed**")
                st.metric("עסקאות", algo_stats["count"])
                st.metric("Net PnL", f"${algo_stats['total_pnl']:,.0f}")
                st.metric("Net R (Target Base)", f"{algo_stats['total_r']:.1f}R")
                st.caption("Win Rate / Expectancy: לא רלוונטי לאלגו — מנוהל חיצונית")
                if not algo_df.empty:
                    avg_oversight = algo_df['algo_oversight'].apply(
                        lambda x: x['score'] if x else 0
                    ).mean()
                    st.metric("ALGO Oversight Score (avg)", f"{avg_oversight:.0f}/100")
            with bs3:
                st.markdown("**📈 Combined (Countable)**")
                st.metric("עסקאות", combined_stats["count"])
                st.metric("Win Rate", f"{combined_stats['win_rate']*100:.1f}%")
                st.metric("Expectancy", f"{combined_stats['expectancy_r']:.2f}R")
                st.metric("Adj R/R", f"{combined_stats['adj_rr']:.2f}:1")
                incomplete_count = len(camp_df[camp_df['stat_bucket'] == ec.STAT_BUCKET_DATA_INCOMPLETE])
                if incomplete_count > 0:
                    st.caption(f"⚠️ {incomplete_count} קמפיינים ב-DATA_INCOMPLETE — לא נספרים")
            st.caption(
                "ℹ️ **Discretionary** = עסקאות ידניות עם סטופ התחלתי ידוע. "
                "**Combined** = כל הקמפיינים הניתנים לספירה (ידני + סטופ ידוע, ללא ALGO). "
                "אם Combined = Discretionary, כל עסקאותיך הידניות כבר כוללות סטופ — זה טוב! "
                "**DATA_INCOMPLETE** = חסר סטופ → מוחרג מ-Win Rate/Expectancy. "
                "**ALGO** = מנוהל חיצונית, נמדד בנפרד."
            )

            # ── ALGO Risk Oversight Score per position ────────────────────────
            if not algo_df.empty:
                st.markdown("---")
                st.subheader("🟠 ALGO Risk Oversight — פירוט")
                for _, row in algo_df.iterrows():
                    ov = row.get('algo_oversight') or {}
                    score = ov.get('score', 0)
                    label = ov.get('label', '—')
                    det = ov.get('details', {})
                    with st.expander(f"{row['symbol']} | {label} ({score}/100) | PnL: ${row['pnl_usd']:+,.0f}"):
                        d1, d2, d3, d4, d5 = st.columns(5)
                        chk = lambda v: "✅" if v else "❌"
                        d1.metric("סמל מוכר", chk(det.get("symbol_known")))
                        d2.metric("Target Risk", chk(det.get("target_risk_known")))
                        d3.metric("R ניתן לחישוב", chk(det.get("r_computable")))
                        d4.metric("PnL קיים", chk(det.get("pnl_present")))
                        d5.metric("Quality נרשם", chk(det.get("quality_recorded")))

            st.markdown("---")
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

        # ── Phase ALGO-BT-1 W-BT4 — ADDITIVE read-only BACKTEST panel ────────
        # Purely additive: renders the externally-managed ALGO bot's
        # TrendSpider backtest edge-shape stats from the git-ignored in-repo
        # dir via the pure read-only `algo_backtest_store`. It alters /
        # reorders / recomputes NO existing dashboard section or number, reads
        # NO Supabase and NO live-ALGO state, degrades to the honest
        # empty-state when the dir is empty, and never raises (boundary-safe
        # loader). Observe-only doctrine (DEC-20260511-001 #8): zero alerts /
        # zero directives — display-only BACKTEST data, not live, not a
        # forward promise.
        st.markdown("---")
        st.subheader("📊 ALGO — בסיס בקטסט (פיקוח בלבד)")
        _bt_loaded = abs_store.load_algo_backtests()
        _bt_stats = abs_store.compute_algo_backtest_stats(_bt_loaded)
        st.caption(f"⚠️ {abs_store.BACKTEST_LABEL} · {abs_store.OBSERVE_ONLY_LABEL}")
        _bt_strats = _bt_stats.get("strategies", {})
        if not _bt_strats:
            st.info(abs_store.EMPTY_STATE_TEXT)
        else:
            _bt_rows = []
            for _sid in sorted(_bt_strats.keys()):
                _s = _bt_strats[_sid]
                _mix = _s["exit_reason_mix"]
                _bt_rows.append({
                    "סמל": _s["symbol"],
                    "אסטרטגיה": _s["strategy_id"],
                    "N": _s["n"],
                    "WR %": round(_s["win_rate_pct"], 1),
                    "ממוצע %": round(_s["avg_return_pct"], 2),
                    "חציון %": round(_s["median_return_pct"], 2),
                    "סכום %": round(_s["sum_return_pct"], 2),
                    "PF": _s["profit_factor_label"],
                    "תוחלת %": round(_s["expectancy_pct"], 2),
                    "Max DD %": (round(_s["max_trade_drawdown_pct"], 2)
                                 if _s["max_trade_drawdown_pct"] is not None else None),
                    "אורך ממוצע": (round(_s["avg_length_candles"], 1)
                                   if _s["avg_length_candles"] is not None else None),
                    "TP": _mix["take_profit"], "SL": _mix["stop_loss"],
                    "time": _mix["time_stop"], "signal": _mix["signal"],
                    "רצף W": _s["longest_win_streak"],
                    "רצף L": _s["longest_loss_streak"],
                    "טווח": f"{_s['date_span']['first']}→{_s['date_span']['last']}",
                })
            st.dataframe(pd.DataFrame(_bt_rows), use_container_width=True, hide_index=True)
            st.caption(
                "מקור: ייצוא TrendSpider Strategy Tester (Volume=1, Trade cost=0%) — "
                "מדדי edge לכל טרייד, לא P&L חשבון, לא נתון חי, לא הבטחה קדימה.")

        # ── Phase ALGO-2A W-2A2 — ADDITIVE observe-only divergence section ───
        # Purely additive: ONE marker-delimited section that surfaces the
        # per-symbol live↔backtest EDGE-SHAPE divergence via the W-2A1
        # SINGLE-SOURCE-OF-TRUTH formatter `algo_divergence
        # .format_symbol_divergence`. The Telegram ALGO panel calls the SAME
        # formatter so the two surfaces are byte-identical (anti-drift, the
        # core "both" requirement). Observe-only doctrine
        # (DEC-20260511-001 #8 / AGENTS.md #8): ZERO alerts, ZERO directives,
        # ZERO push, ZERO Supabase write, ZERO state mutation; neutral 🔭
        # only (no 🔴/🟢), never fed into WR/Expectancy/PF; below the hard
        # min-live-sample gate it shows the honest "אין מספיק מדגם חי"
        # marker, never a delta/zero. It alters / reorders / recomputes NO
        # existing dashboard number or string. Boundary-safe — degrades to
        # the honest empty marker and never raises.
        st.markdown("<!-- ALGO-2A divergence section START -->",
                    unsafe_allow_html=True)
        st.markdown("---")
        st.subheader("🔭 ALGO — הפרש חי↔בקטסט (תצפית בלבד, אפס איתות)")
        try:
            _div_live_aggs = {}
            if not camp_df.empty:
                _algo_live_df = camp_df[
                    camp_df['stat_bucket'] == ec.STAT_BUCKET_ALGO]
                if (not _algo_live_df.empty
                        and 'symbol' in _algo_live_df.columns):
                    for _sym, _grp in _algo_live_df.groupby('symbol'):
                        if 'Total_Campaign_R' not in _grp.columns:
                            continue
                        _vals = [
                            float(_x) for _x in _grp['Total_Campaign_R']
                            .tolist() if _x is not None]
                        if not _vals:
                            continue
                        _wins = sum(1 for _v in _vals if _v > 0)
                        import algo_metrics as _div_am
                        _div_live_aggs[str(_sym).upper()] = {
                            "n": len(_vals),
                            "win_rate_pct": _wins / len(_vals) * 100.0,
                            "avg_return_pct": _div_am._expectancy(_vals),
                            "profit_factor": _div_am._profit_factor(_vals),
                            "loss_streak": _div_am._max_loss_streak(_vals),
                        }
            # Union of symbols present on either side (honest empty per side).
            _div_syms = set(_div_live_aggs.keys())
            for _s in (_bt_stats.get("strategies", {}) or {}).values():
                if isinstance(_s, dict) and _s.get("symbol"):
                    _div_syms.add(str(_s["symbol"]).upper())
            if not _div_syms:
                st.info(algo_divergence.INSUFFICIENT_LIVE_SAMPLE_HE)
            else:
                for _dsym in sorted(_div_syms):
                    # SINGLE SOURCE OF TRUTH — identical per-symbol LINE
                    # formatter the Telegram ALGO panel calls (cross-surface
                    # byte-identity). Phase ALGO-2A.1: ONE concise line per
                    # symbol; the mandatory honesty bundle is emitted ONCE
                    # below (de-duplicated, never removed).
                    st.text(algo_divergence.format_symbol_divergence_line(
                        _dsym, _div_live_aggs, _bt_stats))
                # The mandatory divergence honesty footer (join banner +
                # observe-only + backtest label + the full 5-disclaimer
                # bundle + the non-suppressible backtest caveat) emitted
                # EXACTLY ONCE — byte-identical to the Telegram panel's
                # footer (anti-drift, SINGLE SOURCE OF TRUTH).
                st.text(algo_divergence.format_divergence_footer())
        except Exception:
            # Honest: a failed read-only build must not blank the panel and
            # must not fabricate a delta (absence ≠ data; AGENTS.md #1).
            st.info(algo_divergence.INSUFFICIENT_LIVE_SAMPLE_HE)
        st.markdown("<!-- ALGO-2A divergence section END -->",
                    unsafe_allow_html=True)

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
                                    
                                bucket_tag = row.get('stat_bucket', '')
                                st.caption(f"Strategy: {row['setup_type']} • Entry Quality: {qual_str} • Exit Score: {score_str} • Risk Discipline: {risk_disp} • Bucket: `{bucket_tag}`")
                                
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

                                # מטריקות מינרביני לקמפיין סגור
                                entry_d = row.get('entry_date')
                                close_d = row.get('close_date')
                                if entry_d is not None and close_d is not None:
                                    days_h = max((pd.to_datetime(close_d) - pd.to_datetime(entry_d)).days, 1)
                                    r_day = r_realized / days_h if days_h > 0 else 0
                                    act_risk_pct = (act_risk / current_acc_size * 100) if act_risk > 0 and current_acc_size > 0 else None
                                    mc1, mc2, mc3, mc4 = st.columns(4)
                                    mc1.metric("ימי אחזקה", f"{days_h}d")
                                    mc2.metric("R ליום", f"{r_day:.3f}R", help="יעילות הון לפי מינרביני")
                                    if act_risk > 0:
                                        mc3.metric("סיכון בפועל", f"${act_risk:.0f}", delta=f"{act_risk_pct:.2f}%" if act_risk_pct else None)
                                    else:
                                        mc3.metric("סיכון בפועל", "N/A")
                                    mc4.metric("יעד סיכון", f"${target_risk_usd:.0f} ({risk_pct_input:.1f}%)")

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
        st.subheader("🧠 Minervini Mentor — ניתוח מעמיק ואסטרטגיה")
        st.caption("המנטור מנתח את הביצועים שלך ומספק תובנות לפי מתודולוגיית מארק מינרביני.")

        # ─── ציון מנטור כולל (Trend Template ממוצע) ────────────────────
        st.markdown("---")
        st.subheader("📊 ציון Trend Template — פוזיציות פתוחות")
        if not live_df.empty:
            tt_scores = []
            for sym in live_df['Symbol'].unique():
                tt = ec.compute_trend_template_full(sym)
                if tt['ok']:
                    tt_scores.append((sym, tt['data']['passed'], tt['data']['score_10']))
            if tt_scores:
                avg_tt = sum(s[1] for s in tt_scores) / len(tt_scores)
                mentor_color = "🟢" if avg_tt >= 6.5 else ("🟡" if avg_tt >= 5 else "🔴")
                tt_cols = st.columns(len(tt_scores) + 1)
                with tt_cols[0]:
                    st.metric(f"ממוצע {mentor_color}", f"{avg_tt:.1f}/8")
                for i, (sym, passed, score) in enumerate(tt_scores):
                    c_icon = "🟢" if passed >= 7 else ("🟡" if passed >= 5 else "🔴")
                    tt_cols[i+1].metric(f"{sym} {c_icon}", f"{passed}/8")
            else:
                st.info("אין נתוני Trend Template לפוזיציות הפתוחות.")
        else:
            st.info("אין פוזיציות פתוחות.")

        # ─── שרשרת ניצחונות / הפסדים ───────────────────────────────────
        st.markdown("---")
        st.subheader("🔥 שרשרת (Streak) — קמפיינים אחרונים")
        if not camp_df.empty:
            last_results = camp_df.sort_values('close_date')['pnl_usd'].apply(lambda x: 'W' if x > 0 else 'L').tolist()
            if last_results:
                streak_type = last_results[-1]
                streak_count = 0
                for r in reversed(last_results):
                    if r == streak_type:
                        streak_count += 1
                    else:
                        break
                streak_label = f"{'🏆 שרשרת ניצחונות' if streak_type == 'W' else '💔 שרשרת הפסדים'} — {streak_count} רצוף"
                streak_color = C_WIN if streak_type == 'W' else C_LOSS
                st.markdown(f"<div style='font-size:1.4em; font-weight:bold; color:{streak_color}; direction:rtl;'>{streak_label}</div>", unsafe_allow_html=True)
                st.caption(f"סה״כ קמפיינים: {len(camp_df)} | שיעור הצלחה: {win_rate*100:.1f}%")
                # הצגת 10 אחרונים
                last10 = last_results[-10:]
                st.markdown(" ".join(["🟢" if r == 'W' else "🔴" for r in last10]) + " ← אחרון")
        else:
            st.info("אין קמפיינים סגורים עדיין.")

        # ─── חוזקות וחולשות ─────────────────────────────────────────────
        st.markdown("---")
        st.subheader("💪 חוזקות ⚡ חולשות")
        c_strength, c_weakness = st.columns(2)
        with c_strength:
            st.markdown("**💪 חוזקות**")
            if win_rate >= 0.50:
                st.success(f"✅ שיעור הצלחה טוב: {win_rate*100:.1f}%")
            if expectancy_r > 0:
                st.success(f"✅ Expectancy חיובית: {expectancy_r:.2f}R לטרייד")
            if adj_rr >= 2.0:
                st.success(f"✅ Payoff Ratio מצוין: {adj_rr:.2f}:1")
            if not live_df.empty:
                best_pos = live_df.loc[live_df['Total_R'].idxmax()]
                if best_pos['Total_R'] > 1.0:
                    st.success(f"✅ פוזיציית ריצה: {best_pos['Symbol']} ב-{best_pos['Total_R']:.2f}R")
            if not camp_df.empty:
                if total_r_net > 0:
                    st.success(f"✅ סה״כ R מצטבר חיובי: +{total_r_net:.1f}R")
        with c_weakness:
            st.markdown("**⚡ חולשות — לשים לב**")
            found_weakness = False

            if win_rate < 0.40 and combined_stats["count"] >= 3:
                st.error(f"🔴 שיעור הצלחה נמוך: {win_rate*100:.1f}% — מינרביני: 'למד מכל כישלון'")
                found_weakness = True
            elif 0.40 <= win_rate < 0.50 and combined_stats["count"] >= 5:
                st.warning(f"⚠️ שיעור הצלחה מתחת ל-50%: {win_rate*100:.1f}% — שאף ל-50%+ לפי מינרביני")
                found_weakness = True

            if expectancy_r < 0:
                st.error(f"🔴 Expectancy שלילית: {expectancy_r:.2f}R — 'אל תוסיף עד שזה חיובי'")
                found_weakness = True
            elif 0 <= expectancy_r < 0.3 and combined_stats["count"] >= 5:
                st.warning(f"⚠️ Expectancy נמוכה: {expectancy_r:.2f}R — כוון ל-0.3R+ לטרייד")
                found_weakness = True

            if adj_rr < 1.5 and adj_rr > 0 and combined_stats["count"] >= 5:
                st.warning(f"⚠️ Payoff Ratio נמוך: {adj_rr:.2f}:1 — מינרביני: 'כוון ל-2:1, תן לרווחים לרוץ'")
                found_weakness = True

            if not live_df.empty:
                oversized = live_df[live_df['SizingGrade'] == 'oversized']
                if not oversized.empty:
                    st.warning(f"⚠️ {len(oversized)} פוזיציות בסיכון מעל 2.5%: {', '.join(oversized['Symbol'].tolist())}")
                    found_weakness = True
                high_mae = live_df[live_df['MAE_R'].notna() & (live_df['MAE_R'] < -1.5)]
                if not high_mae.empty:
                    st.warning(f"⚠️ MAE גבוה: {', '.join(high_mae['Symbol'].tolist())} — 'בדוק תקפות הסטופ'")
                    found_weakness = True

            if not camp_df.empty:
                incomplete_count = len(camp_df[camp_df['stat_bucket'] == ec.STAT_BUCKET_DATA_INCOMPLETE])
                if incomplete_count > 0:
                    st.warning(f"⚠️ {incomplete_count} קמפיינים ב-DATA_INCOMPLETE — הזן סטופ התחלתי לספירה בסטטיסטיקה")
                    found_weakness = True

            if regime.get('ok') and regime.get('data', {}).get('status', '').lower() in ['downtrend', 'ירידה']:
                st.error("🔴 שוק בירידה — מינרביני: 'עמוד על הגנה, 0-25% חשיפה'")
                found_weakness = True

            if not found_weakness:
                st.success("✅ אין חולשות מזוהות — המשך לפי הכללים")

        # ─── תובנות המנטור ───────────────────────────────────────────────
        st.markdown("---")
        st.subheader("🎓 מה מינרביני היה אומר עכשיו?")
        regime_status = regime.get('data', {}).get('status', '') if regime.get('ok') else ''
        oversized_count = len(live_df[live_df['SizingGrade'] == 'oversized']) if not live_df.empty else 0
        streak_losses = streak_count if (not camp_df.empty and last_results and streak_type == 'L') else 0
        insights = ec.generate_minervini_coaching(
            win_rate=win_rate, expectancy_r=expectancy_r, adj_rr=adj_rr,
            oversized_count=oversized_count, market_regime_status=regime_status,
            streak_losses=streak_losses, total_r_net=total_r_net
        )
        if insights:
            for insight in insights:
                st.markdown(f"<div style='background:#1a1e24; border-right:4px solid #f0a500; padding:12px; border-radius:8px; margin-bottom:8px; direction:rtl; text-align:right;'>{insight}</div>", unsafe_allow_html=True)
        else:
            st.success("✅ מינרביני: 'מצוין! המערכת במצב תקין. המשך לפעול לפי הכללים.'")

    with tabs[5]:
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
