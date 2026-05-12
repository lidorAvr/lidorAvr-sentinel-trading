import time
import json
import os
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import threading
import requests
import random
from bs4 import BeautifulSoup

ALGO_SYMBOL_LIMITS = {"QQQ": 10.0, "TSLA": 7.0, "JPM": 7.0, "PLTR": 6.0, "HOOD": 6.0}
ALGO_SYMBOLS = set(ALGO_SYMBOL_LIMITS.keys())
ALGO_CLUSTER_WARNING_PCT = 30.0
ALGO_CLUSTER_CRITICAL_PCT = 35.0
YF_CACHE = {}

SECTOR_ETF_MAP = {
    "Technology": "XLK", "Financial Services": "XLF", "Financial": "XLF", "Healthcare": "XLV",
    "Consumer Cyclical": "XLY", "Consumer Defensive": "XLP", "Industrials": "XLI",
    "Energy": "XLE", "Basic Materials": "XLB", "Communication Services": "XLC",
    "Utilities": "XLU", "Real Estate": "XLRE",
}

SECTOR_CACHE = {
    "QQQ": {"sector": "Technology", "industry": "Broad", "sector_etf": "XLK"},
    "TSLA": {"sector": "Consumer Cyclical", "industry": "Auto", "sector_etf": "XLY"},
    "JPM": {"sector": "Financial Services", "industry": "Banks", "sector_etf": "XLF"},
    "PLTR": {"sector": "Technology", "industry": "Software", "sector_etf": "XLK"},
    "HOOD": {"sector": "Financial Services", "industry": "Capital Markets", "sector_etf": "XLF"},
    "AEHR": {"sector": "Technology", "industry": "Semiconductors", "sector_etf": "XLK"},
    "MRVL": {"sector": "Technology", "industry": "Semiconductors", "sector_etf": "XLK"},
    "RVMD": {"sector": "Healthcare", "industry": "Biotechnology", "sector_etf": "XLV"},
    "MTZ": {"sector": "Industrials", "industry": "Engineering", "sector_etf": "XLI"},
    "SPY": {"sector": "Market", "industry": "Market", "sector_etf": None}
}

yf_session = requests.Session()
user_agents = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0'
]

def get_random_agent():
    return random.choice(user_agents)

def smart_delay():
    time.sleep(random.uniform(0.5, 1.5))

def direct_yahoo_scrape(symbol):
    try:
        url = f"https://finance.yahoo.com/quote/{symbol}"
        headers = {'User-Agent': get_random_agent()}
        response = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        price_tag = soup.find('fin-streamer', {'data-symbol': symbol, 'data-field': 'regularMarketPrice'})
        if price_tag:
            price_str = price_tag.text.replace(',', '')
            return float(price_str)
    except Exception as e:
        pass
    return None

def get_cached_history(symbol, period="1y", interval="1d", ttl=300):
    cache_key = f"{symbol}_{period}_{interval}"
    now = time.time()
    if cache_key in YF_CACHE and (now - YF_CACHE[cache_key]["time"]) < ttl: 
        return YF_CACHE[cache_key]["data"]
    
    smart_delay()
    try:
        
        hist = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=False)
        if hist is not None and not hist.empty:
            YF_CACHE[cache_key] = {"data": hist, "time": now}
            return hist
    except: 
        pass
    return pd.DataFrame()

def get_live_price(symbol):
    now = time.time()
    cache_key = f"{symbol}_live_price"
    if cache_key in YF_CACHE and (now - YF_CACHE[cache_key]["time"]) < 120:
        return YF_CACHE[cache_key]["data"]

    smart_delay()
    
    try:
        
        tk = yf.Ticker(symbol)
        if 'last_price' in tk.fast_info:
            price = float(tk.fast_info['last_price'])
            YF_CACHE[cache_key] = {"data": price, "time": now}
            return price
    except:
        pass
        
    scraped_price = direct_yahoo_scrape(symbol)
    if scraped_price is not None:
        YF_CACHE[cache_key] = {"data": scraped_price, "time": now}
        return scraped_price

    hist = get_cached_history(symbol, period="5d", interval="1d", ttl=300)
    if hist is not None and not hist.empty:
        try: 
            price = float(hist["Close"].iloc[-1])
            YF_CACHE[cache_key] = {"data": price, "time": now}
            return price
        except: pass
        
    return None

def df_safe_low(close, ref):
    if pd.isna(ref) or ref <= 0: return close
    return min(close, ref)

def _fetch_info(symbol, result):
    try:
        
        tk = yf.Ticker(symbol)
        result['info'] = tk.info or {}
    except: pass

def get_sector_bundle(symbol):
    if symbol in SECTOR_CACHE: return SECTOR_CACHE[symbol]
    result = {'info': {}}
    t = threading.Thread(target=_fetch_info, args=(symbol, result))
    t.start()
    t.join(timeout=2.0) 
    info = result.get('info', {})
    sector = info.get("sector")
    industry = info.get("industry")
    sector_etf = SECTOR_ETF_MAP.get(sector)
    bundle = {"sector": sector, "industry": industry, "sector_etf": sector_etf}
    if sector: SECTOR_CACHE[symbol] = bundle
    return bundle

def safe_return(series, lookback):
    try:
        if series is None or len(series) < lookback: return None
        a, b = float(series.iloc[-1]), float(series.iloc[-lookback])
        if b == 0: return None
        return a / b - 1
    except: return None

def calculate_atr_series(hist, window=14):
    high_low = hist["High"] - hist["Low"]
    high_close = (hist["High"] - hist["Close"].shift()).abs()
    low_close = (hist["Low"] - hist["Close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return true_range.rolling(window=window, min_periods=window).mean()

def compute_indicators(hist):
    df = hist.copy()
    df["MA10"] = df["Close"].rolling(10).mean()
    df["MA20"] = df["Close"].rolling(20).mean()
    df["MA50"] = df["Close"].rolling(50).mean()
    df["MA150"] = df["Close"].rolling(150).mean()
    df["MA200"] = df["Close"].rolling(200).mean()
    df["ATR20"] = calculate_atr_series(df, 20)
    df["ATR100"] = calculate_atr_series(df, 100)
    df["AvgVol20"] = df["Volume"].rolling(20).mean()
    df["Range"] = df["High"] - df["Low"]
    df["ClosePos"] = np.where(df["Range"] > 0, (df["Close"] - df["Low"]) / df["Range"], 0.5)
    df["UpDay"] = df["Close"] > df["Close"].shift(1)
    df["DownDay"] = df["Close"] < df["Close"].shift(1)
    df["GoodClose"] = df["ClosePos"] >= 0.6
    df["BadClose"] = df["ClosePos"] <= 0.4
    return df

def detect_distribution_days(df):
    out = df.copy()
    out["DistributionDay"] = (
        (out["Close"] < out["Open"]) & (out["Volume"] > 1.5 * out["AvgVol20"]) &
        (out["Range"] > 1.2 * out["ATR20"]) & (out["ClosePos"] <= 0.35)
    )
    out["AccumulationDay"] = (
        (out["Close"] > out["Open"]) & (out["Volume"] > 1.3 * out["AvgVol20"]) & (out["ClosePos"] >= 0.65)
    )
    return out

def classify_trade_stage(total_r, days_held):
    if total_r < 0: return "underwater"
    if total_r < 1.0: return "early"
    if total_r < 2.5: return "developing"
    if total_r < 4.0: return "advanced"
    return "runner"

def map_time_efficiency(days_held, total_r):
    if days_held >= 8 and total_r < 0.5: return "dead_money"
    if days_held >= 15 and total_r < 1.0: return "slow"
    return "ok"

def compute_relative_strength_bundle(symbol, df, spy_hist=None):
    bundle = get_sector_bundle(symbol)
    sector_etf = bundle.get("sector_etf")
    sector_hist = get_cached_history(sector_etf, "1y", "1d") if sector_etf else None
    stock_close = df["Close"]
    spy_close = spy_hist["Close"] if spy_hist is not None and len(spy_hist) >= 60 else None
    sector_close = sector_hist["Close"] if sector_hist is not None and len(sector_hist) >= 60 else None
    stock_ret20 = safe_return(stock_close, 20)
    spy_ret20 = safe_return(spy_close, 20)
    sector_ret20 = safe_return(sector_close, 20)
    return {
        "sector": bundle.get("sector"), "industry": bundle.get("industry"), "sector_etf": sector_etf,
        "rs20_market": stock_ret20 - spy_ret20 if stock_ret20 is not None and spy_ret20 is not None else None,
        "rs20_sector_market": sector_ret20 - spy_ret20 if sector_ret20 is not None and spy_ret20 is not None else None,
        "rs20_stock_sector": stock_ret20 - sector_ret20 if stock_ret20 is not None and sector_ret20 is not None else None,
    }

def compute_behavior_features(symbol, df, days_held, spy_hist=None):
    close, prev_close = df["Close"].iloc[-1], df["Close"].iloc[-2]
    ma10, ma20, ma50 = df["MA10"].iloc[-1], df["MA20"].iloc[-1], df["MA50"].iloc[-1]
    atr20, atr100 = df["ATR20"].iloc[-1], df["ATR100"].iloc[-1]
    daily_move = abs(close - prev_close)
    is_down_day = close < prev_close
    atr_pct = (atr20 / close * 100) if close > 0 and pd.notna(atr20) else 0
    atr_regime = atr20 / atr100 if pd.notna(atr20) and pd.notna(atr100) and atr100 > 0 else 1.0
    stretch_ma10_atr = (close - ma10) / atr20 if pd.notna(ma10) and pd.notna(atr20) and atr20 > 0 else None
    stretch_ma20_atr = (close - ma20) / atr20 if pd.notna(ma20) and pd.notna(atr20) and atr20 > 0 else None
    down_move_atr = (prev_close - close) / atr20 if is_down_day and pd.notna(atr20) and atr20 > 0 else None
    recent_high_20 = df["High"].tail(20).max()
    dist_from_high_20 = (close / recent_high_20 - 1) * 100 if recent_high_20 > 0 else 0
    ext10 = (close / ma10 - 1) * 100 if ma10 > 0 else 0
    ext20 = (close / ma20 - 1) * 100 if ma20 > 0 else 0
    rs_bundle = compute_relative_strength_bundle(symbol, df, spy_hist)
    return {
        "close": close, "prev_close": prev_close, "ma10": ma10, "ma20": ma20, "ma50": ma50,
        "atr20": atr20, "atr_pct": atr_pct, "atr_regime": atr_regime,
        "stretch_ma10_atr": stretch_ma10_atr, "stretch_ma20_atr": stretch_ma20_atr, "down_move_atr": down_move_atr,
        "daily_move": daily_move, "is_down_day": is_down_day,
        "dist_8d": int(df["DistributionDay"].tail(8).sum()),
        "dist_12d": int(df["DistributionDay"].tail(12).sum()),
        "accum_10d": int(df["AccumulationDay"].tail(10).sum()),
        "good_closes_10": int(df["GoodClose"].tail(10).sum()),
        "bad_closes_10": int(df["BadClose"].tail(10).sum()),
        "dist_from_high_20": dist_from_high_20, "ext10": ext10, "ext20": ext20,
        "close_below_ma10": close < ma10, "close_below_ma20": close < ma20, "close_below_ma50": close < ma50,
        "consecutive_below_ma20": int((df["Close"].tail(2) < df["MA20"].tail(2)).sum() == 2),
        "rs20_market": rs_bundle["rs20_market"], "rs20_sector_market": rs_bundle["rs20_sector_market"],
        "rs20_stock_sector": rs_bundle["rs20_stock_sector"]
    }

def is_algo_position(setup_type, symbol=None):
    """
    True if this position is managed by an external ALGO system.
    setup_type is the single source of truth. Symbol is only a fallback
    when setup_type is missing/unknown — it never overrides an explicit EP/VCP label.
    """
    st = str(setup_type).upper()
    if st == "ALGO":
        return True
    # Symbol fallback: only when setup_type carries no explicit intent
    if st in ("UNKNOWN", "NONE", "NAN", "", "UNCATEGORIZED"):
        if symbol and str(symbol).upper() in ALGO_SYMBOLS:
            return True
    return False


def classify_management_mode(setup_type, symbol=None):
    """
    Classify how a position is managed.
    Used to gate statistics, alerts, and display — not stored in Supabase (derived at runtime).
    """
    if is_algo_position(setup_type, symbol):
        return "algo_observed"
    return "manual_managed"


def classify_risk_basis(stop, base_price, setup_type, target_risk_usd=0):
    """
    Classify the basis used for R calculation.
    True   — real known stop, enters all quality statistics.
    Target — ALGO or missing stop, uses target_risk_usd as denominator.
    Unknown — no basis available, excluded from statistics.
    """
    if is_algo_position(setup_type):
        return "Target" if target_risk_usd > 0 else "Unknown"
    if stop > 0 and stop < base_price:
        return "True"
    if target_risk_usd > 0:
        return "Target"
    return "Unknown"


def compute_risk_visibility_score(setup_type, stop, base_price, target_risk_usd=0):
    """
    Score 0-100 expressing how clearly we can see a position's risk.
    100: stop known, risk known, quantity known (True Risk basis)
     60: Target Risk basis only (no real stop)
     40: external ALGO, target risk available
     20: external ALGO, no target risk; or no stop and no target
      0: broken data
    """
    if is_algo_position(setup_type):
        return 40 if target_risk_usd > 0 else 20
    if stop > 0 and stop < base_price:
        return 100
    if target_risk_usd > 0:
        return 60
    return 20


def evaluate_hard_rules(features, setup_type, weight_pct, symbol, current_stop, total_r, stage, mgt_state):
    if str(setup_type).upper() == "ALGO":
        limit = ALGO_SYMBOL_LIMITS.get(symbol, 100.0)
        if weight_pct > limit:
            return {"rule": "algo_sizing_breach", "status": "🚨 חריגת סיכון אלגו", "action": "להפחית חשיפה", "trigger": f"חריגת Sizing (מגבלה: {limit:.1f}%)"}
        return None
    if current_stop > 0 and features["close"] <= current_stop:
        return {"rule": "stop_breach", "status": "🚨 קריטי", "action": "יציאה מיידית 🚨" if mgt_state != "runner_mode" else "שקול סגירת יתרת Runner", "trigger": "מחיר נוכחי נמוך מסטופ"}
    if features["dist_12d"] >= 3:
        return {"rule": "heavy_distribution", "status": "🔴 Broken", "action": "יציאה / הידוק מידי" if mgt_state != "runner_mode" else "שקול סגירת יתרת Runner", "trigger": "3 ימי פיזור ב-12 ימים"}
    if stage == "runner" and features["consecutive_below_ma20"]:
        return {"rule": "runner_ma20_break", "status": "🔴 Broken", "action": "מימוש יתרה / יציאה לפי תוכנית", "trigger": "2 סגירות רצופות מתחת MA20"}
    if features.get('stretch_ma20_atr') is not None and features.get('stretch_ma10_atr') is not None:
        if features['stretch_ma20_atr'] > 3.0 and features['stretch_ma10_atr'] > 1.75:
            return {'rule': 'climactic_risk_atr', 'status': '⚠️ Climactic', 'action': 'PENDING_MGT_STATE', 'trigger': 'המניה מתוחה מאוד ביחס ל-ATR (תנודתיות גבוהה)'}
    if features["ext20"] > 18 and features["ext10"] > 10:
        return {"rule": "climactic_risk_pct", "status": "⚠️ Climactic", "action": "PENDING_MGT_STATE", "trigger": "המניה מתוחה מאוד מעל הממוצעים (>18%)"}
    return None

def score_position(features, stage):
    score = 50
    score += 8 if not features["close_below_ma10"] else -8
    score += 12 if not features["close_below_ma20"] else -15
    score += 10 if not features["close_below_ma50"] else -12
    if features["good_closes_10"] > features["bad_closes_10"]: score += 8
    elif features["bad_closes_10"] > features["good_closes_10"]: score -= 10
    score += min(features["accum_10d"] * 2, 6)
    score -= features["dist_8d"] * 6
    score -= features["dist_12d"] * 5
    if features.get("rs20_market") is not None: score += 6 if features["rs20_market"] > 0 else -6
    if features.get("rs20_stock_sector") is not None: score += 4 if features["rs20_stock_sector"] > 0 else -4
    if features["dist_from_high_20"] >= -3: score += 6
    elif features["dist_from_high_20"] <= -8: score -= 8
    te = features.get("time_efficiency", "ok")
    if te == "dead_money": score -= 12
    elif te == "slow": score -= 6
    if not pd.isna(features["atr20"]) and features["is_down_day"] and features["daily_move"] > 1.3 * features["atr20"]: score -= 10
    if features.get('down_move_atr') is not None and features['down_move_atr'] > 1.2: score -= 8
    if stage == "early":
        if features["close_below_ma10"]: score -= 8
    elif stage == "developing":
        if features["close_below_ma10"]: score -= 6
        if features["dist_8d"] >= 2: score -= 6
    elif stage == "advanced":
        if features["close_below_ma20"]: score -= 10
    elif stage == "runner":
        if features["close_below_ma20"]: score -= 12
        if features.get("stretch_ma20_atr") is not None and features["stretch_ma20_atr"] > 3.0: score -= 4
    return max(0, min(95, score))

def map_score_to_status(score, hard_rule=None, features=None):
    if hard_rule is not None: return hard_rule["status"]
    
    status = "🔴 Broken"
    if score >= 85: status = "🔥 Power"
    elif score >= 70: status = "🟢 Healthy"
    elif score >= 55: status = "🟡 Yellow Flag"
    elif score >= 40: status = "🟠 Weak"
    
    if status == "🟢 Healthy" and features is not None:
        if features.get("bad_closes_10", 0) > features.get("good_closes_10", 0):
            status = "🟡 תקין אך במעקב"
            
    return status

def build_management_action(status, features, stage, current_stop, total_r, mgt_state):
    close, ma10, ma20 = features["close"], features["ma10"], features["ma20"]
    suggested_stop = current_stop
    trigger, action = "", "מעקב"
    if status == "🔥 Power":
        if mgt_state == "runner_mode":
            action, trigger = "החזק Runner חופשי", "מובילה - עקוב אחרי מגמה"
        else: action, trigger = "החזקה (מובילה)", "המבנה תקין"
    elif status == "🟢 Healthy":
        if mgt_state == "runner_mode":
            action, trigger = "החזק Runner חופשי", "מבנה תקין לאחר מימוש"
            if total_r >= 1.5 and features["close_below_ma10"]:
                suggested_stop = min(current_stop if current_stop > 0 else close, df_safe_low(close, ma10))
                action, trigger = "קדם סטופ ל-Runner", "איבדה MA10 לאחר מימוש חלקי"
        else:
            action, trigger = "החזקה", "מבנה תקין"
            if total_r >= 1.5 and features["close_below_ma10"]:
                suggested_stop = min(current_stop if current_stop > 0 else close, df_safe_low(close, ma10))
                action, trigger = "קדם סטופ ל-BE לפחות", "איבדה MA10 לאחר מהלך יפה"
    elif "מעקב" in status or status == "🟡 Yellow Flag":
        if mgt_state == "runner_mode": action, trigger = "הידוק ל-Runner", "אובדן מומנטום אחרי מימוש חלקי"
        else: action, trigger = "לא להוסיף. שקול צמצום", "סגירות חלשות - להקטין חשיפה אם התמיכה נשברת"
        suggested_stop = current_stop if stage in ("early", "developing") else ma20
    elif status == "🟠 Weak":
        if mgt_state == "runner_mode": action, trigger = "הידוק אגרסיבי ל-Runner", "חולשה לאחר מימוש חלקי"
        else: action, trigger = "הידוק אגרסיבי", "חולשה - שבירת מבנה / פיזור"
        suggested_stop = ma20 if stage in ("advanced", "runner") else ma10
    elif status == "🔴 Broken":
        if mgt_state == "runner_mode": action, trigger = "שקול סגירת יתרת Runner", "המבנה נשבר לאחר מימוש חלקי"
        else: action, trigger = "יציאה / הידוק מידי", "המבנה נשבר"
        suggested_stop = current_stop
    elif status == "⚠️ Climactic":
        if mgt_state == "runner_mode":
            action, trigger = "Runner חופשי", "לשקול מימוש נוסף בשבירת MA10 או היפוך ווליום"
            suggested_stop = max(current_stop, ma10) if current_stop > 0 else ma10
        else:
            action, trigger = "שקול מימוש חלקי", "Climactic - מתוחה מאוד"
            suggested_stop = ma10
            
    if action == 'PENDING_MGT_STATE': action = "Runner חופשי - שקול מימוש נוסף בשבירת MA10" if mgt_state == "runner_mode" else "שקול מימוש חלקי"
    return action, trigger, suggested_stop

def evaluate_position_engine(symbol, entry_price, entry_date_str, current_stop, setup_type, mgt_state, weight_pct, total_r, target_risk_usd=0, actual_risk_usd=0, spy_hist=None):
    try:
        hist = get_cached_history(symbol, "6mo", "1d")
        if hist is None or hist.empty or len(hist) < 60: return {"ok": False, "error": "missing_data", "data": None}
        df = compute_indicators(hist)
        df = detect_distribution_days(df)
        try: days_held = (datetime.now() - pd.to_datetime(entry_date_str)).days if pd.notnull(pd.to_datetime(entry_date_str)) else 0
        except: days_held = 0
        stage = classify_trade_stage(total_r, days_held)
        features = compute_behavior_features(symbol, df, days_held=days_held, spy_hist=spy_hist)
        features["time_efficiency"] = map_time_efficiency(days_held, total_r)
        
        sizing_status = "✅ תקין"
        if str(setup_type).upper() != "ALGO" and target_risk_usd > 0 and actual_risk_usd > 0:
            if actual_risk_usd > target_risk_usd * 1.25:
                sizing_status = f"⚠️ סיכון גבוה (${actual_risk_usd:,.0f} מול יעד ${target_risk_usd:,.0f})"
            elif actual_risk_usd < target_risk_usd * 0.75:
                sizing_status = f"📉 סיכון נמוך (${actual_risk_usd:,.0f} מול יעד ${target_risk_usd:,.0f})"

        hard_rule = evaluate_hard_rules(features, setup_type, weight_pct, symbol, current_stop, total_r, stage, mgt_state)
        issues = []
        if str(setup_type).upper() != "ALGO":
            if features["dist_8d"] >= 2: issues.append("2 ימי פיזור (8d)")
            if features["dist_12d"] >= 3: issues.append("3 ימי פיזור (12d)")
            if features["time_efficiency"] == "dead_money": issues.append("הון מת")
            if not pd.isna(features["atr20"]) and features["is_down_day"] and features["daily_move"] > 1.3 * features["atr20"]: issues.append("חולשת ATR חריגה")
            if features["bad_closes_10"] > features["good_closes_10"]: issues.append("סגירות חלשות")
        
        if hard_rule is not None:
            action = hard_rule["action"]
            if action == 'PENDING_MGT_STATE': action = "Runner חופשי - שקול מימוש בשבירת MA10" if mgt_state == "runner_mode" else "שקול מימוש חלקי"
            mgmt_mode = classify_management_mode(setup_type, symbol)
            risk_basis = classify_risk_basis(current_stop, entry_price, setup_type, target_risk_usd)
            risk_vis = compute_risk_visibility_score(setup_type, current_stop, entry_price, target_risk_usd)
            return {"ok": True, "error": None, "data": {"status": hard_rule["status"], "sizing_status": sizing_status, "issues": issues, "action": action, "trigger": hard_rule["trigger"], "suggested_stop": current_stop, "score": None, "stage": stage, "features": features, "management_mode": mgmt_mode, "risk_basis": risk_basis, "risk_visibility_score": risk_vis}}

        score = score_position(features, stage)
        status = map_score_to_status(score, features=features)
        mgmt_mode = classify_management_mode(setup_type, symbol)
        risk_basis = classify_risk_basis(current_stop, entry_price, setup_type, target_risk_usd)
        risk_vis = compute_risk_visibility_score(setup_type, current_stop, entry_price, target_risk_usd)

        # ALGO: Sentinel is an observer only — do not apply discretionary management rules.
        if mgmt_mode == "algo_observed":
            return {"ok": True, "error": None, "data": {
                "status": status, "sizing_status": sizing_status, "issues": [],
                "action": "מנוהל חיצונית — בקרה בלבד",
                "trigger": "",
                "suggested_stop": None,
                "score": score, "stage": stage, "features": features,
                "management_mode": "algo_observed",
                "risk_basis": risk_basis,
                "risk_visibility_score": risk_vis,
            }}

        action, trigger, suggested_stop = build_management_action(status, features, stage, current_stop, total_r, mgt_state)
        return {"ok": True, "error": None, "data": {"status": status, "sizing_status": sizing_status, "issues": issues, "action": action, "trigger": trigger, "suggested_stop": suggested_stop, "score": score, "stage": stage, "features": features, "management_mode": mgmt_mode, "risk_basis": risk_basis, "risk_visibility_score": risk_vis}}
    except Exception as e: return {"ok": False, "error": str(e), "data": None}

def get_open_positions_campaign(df):
    try:
        open_positions = []
        if "campaign_id" not in df.columns: return {"ok": False, "error": "no_campaign_id", "data": pd.DataFrame()}
        work = df.copy()
        for col in ["quantity", "price", "stop_loss", "initial_stop", "pnl_usd"]: work[col] = pd.to_numeric(work[col], errors="coerce").fillna(0)
        valid_df = work[work["campaign_id"].notnull()]
        if valid_df.empty: return {"ok": True, "error": None, "data": pd.DataFrame()}
        for cid, group in valid_df.groupby("campaign_id"):
            group = group.sort_values(["trade_date", "trade_id"])
            net_qty = group["quantity"].sum()
            if net_qty <= 0.001: continue
            sym = group.iloc[0]["symbol"]
            realized_pnl = group[group["side"].str.upper() == "SELL"]["pnl_usd"].sum()
            buys = group[group["quantity"] > 0]
            if buys.empty: continue
            
            first_date = buys["trade_date"].min()
            first_day_buys = buys[buys["trade_date"] == first_date]
            base_qty = float(first_day_buys["quantity"].sum())
            base_price = float((first_day_buys["price"] * first_day_buys["quantity"]).sum() / base_qty) if base_qty > 0 else float(first_day_buys.iloc[0]["price"])
            
            subsequent_buys = buys[buys["trade_date"] > first_date]
            add_on_count = len(subsequent_buys)
            
            avg_price = (buys["price"] * buys["quantity"]).sum() / buys["quantity"].sum()
            initial_qty = base_qty 
            
            last_row = group.iloc[-1]
            valid_sls = group[(group["stop_loss"] > 0) & (group["side"].str.upper() == "BUY")]["stop_loss"]
            sl = valid_sls.iloc[-1] if not valid_sls.empty else 0
            
            valid_inits = first_day_buys[first_day_buys["initial_stop"] > 0]["initial_stop"]
            init_sl = valid_inits.iloc[0] if not valid_inits.empty else 0
            if init_sl >= base_price: init_sl = 0 
            
            has_sells = len(group[group["side"].str.upper() == "SELL"]) > 0
            db_mgt_state = last_row.get("management_state")
            mgt_state = "runner_mode" if has_sells else (db_mgt_state if pd.notna(db_mgt_state) and db_mgt_state else "full_position")
            
            open_positions.append({
                "campaign_id": cid, "symbol": sym, "quantity": net_qty, "initial_qty": initial_qty,
                "base_qty": base_qty, "base_price": base_price, "add_on_count": add_on_count,
                "price": avg_price, "stop_loss": sl, "initial_stop": init_sl,
                "setup_type": first_day_buys.iloc[0].get("setup_type", "Unknown"), "trade_id": first_day_buys.iloc[0].get("trade_id"),
                "entry_date": first_date, "management_state": mgt_state, "realized_pnl": realized_pnl,
            })
        if not open_positions: return {"ok": True, "error": None, "data": pd.DataFrame()}
        return {"ok": True, "error": None, "data": pd.DataFrame(open_positions).sort_values("symbol")}
    except Exception as e: return {"ok": False, "error": str(e), "data": pd.DataFrame()}

def compute_market_regime(spy_hist, qqq_hist=None):
    try:
        if spy_hist is None or len(spy_hist) < 50: return {"ok": False, "error": "no_data", "data": {"status": "Unknown", "color": "⚪", "text": "אין מספיק נתונים"}}
        spy_close = float(spy_hist['Close'].iloc[-1])
        spy_ma20 = float(spy_hist['Close'].rolling(20).mean().iloc[-1])
        spy_ma50 = float(spy_hist['Close'].rolling(50).mean().iloc[-1])
        score = 0
        s1 = spy_close > spy_ma20
        s2 = spy_close > spy_ma50
        s3 = spy_ma20 > spy_ma50
        if s1: score += 1
        if s2: score += 1
        if s3: score += 1
        qqq_close = qqq_ma20 = None
        s4 = None
        if qqq_hist is not None and not qqq_hist.empty and len(qqq_hist) >= 50:
            qqq_close = float(qqq_hist['Close'].iloc[-1])
            qqq_ma20 = float(qqq_hist['Close'].rolling(20).mean().iloc[-1])
            s4 = qqq_close > qqq_ma20
            if s4: score += 1
        signals = {
            "spy_close": round(spy_close, 2),
            "spy_ma20": round(spy_ma20, 2),
            "spy_ma50": round(spy_ma50, 2),
            "spy_above_ma20": s1,
            "spy_above_ma50": s2,
            "spy_ma20_above_ma50": s3,
            "qqq_close": round(qqq_close, 2) if qqq_close else None,
            "qqq_ma20": round(qqq_ma20, 2) if qqq_ma20 else None,
            "qqq_above_ma20": s4,
            "score": score,
            "max_score": 4 if s4 is not None else 3,
        }
        if score >= 3:
            status, color, text = "Hot", "🔥", "שוק שורי חזק - סביבה תומכת"
        elif score == 2:
            status, color, text = "Warm", "🟢", "שוק חיובי - לנהל סיכונים רגיל"
        elif score == 1:
            status, color, text = "Neutral", "🟡", "שוק מדשדש/מעורב - זהירות והקטנת סיכון"
        else:
            status, color, text = "Cold", "🔴", "שוק דובי - סביבה עוינת, הגנה מקסימלית"
        return {"ok": True, "error": None, "data": {"status": status, "color": color, "text": text, "signals": signals}}
    except Exception as e: return {"ok": False, "error": str(e), "data": {"status": "Unknown", "color": "⚪", "text": f"שגיאה: {e}"}}

def get_minervini_analysis(symbol):
    try:
        hist = get_cached_history(symbol, "1y", "1d")
        if hist is None or len(hist) < 200: 
            return {"ok": False, "error": "missing_data", "data": ("⚠️ אין מספיק היסטוריית מחירים לניתוח או שגיאת שרת.", 0)}
        close = hist['Close'].iloc[-1]
        ma50 = hist['Close'].rolling(window=50).mean().iloc[-1]
        ma150 = hist['Close'].rolling(window=150).mean().iloc[-1]
        ma200 = hist['Close'].rolling(window=200).mean().iloc[-1]
        low_52w = hist['Low'].min()
        high_52w = hist['High'].max()
        vol_curr = hist['Volume'].iloc[-1]
        vol_50 = hist['Volume'].rolling(window=50).mean().iloc[-1]
        r1 = close > ma150 and close > ma200
        r2 = ma150 > ma200
        r3 = close > ma50
        r4 = close >= (low_52w * 1.30)
        r5 = close >= (high_52w * 0.75)
        r6_volume = vol_curr < vol_50
        score = sum([r1, r2, r3, r4, r5]) * 2
        
        report = f"🔬 *דו\"ח מודיעין Trend Template - {symbol}:*\nמחיר נוכחי: `${close:.2f}`\n\n"
        report += f"{'✅' if r1 else '❌'} 1. מחיר מעל ממוצעים 150 ו-200\n"
        report += f"{'✅' if r2 else '❌'} 2. ממוצע 150 מעל ממוצע 200\n"
        report += f"{'✅' if r3 else '❌'} 3. מחיר מעל ממוצע קצר 50\n"
        report += f"{'✅' if r4 else '❌'} 4. מחיר מעל 30% משפל 52ש\n"
        report += f"{'✅' if r5 else '❌'} 5. מרחק עד 25% משיא 52ש\n\n"
        report += f"💡 *אינדיקציית VCP ווליום:*\n"
        report += f"{'📉 ייבוש מחזורים' if r6_volume else '📈 מחזור ער'} (נוכחי: {vol_curr/1e6:.1f}M מול ממוצע: {vol_50/1e6:.1f}M)\n\n"
        report += f"📊 *ציון תבנית מגמה:* {score}/10"
        
        return {"ok": True, "error": None, "data": (report, score)}
    except Exception as e:
        return {"ok": False, "error": str(e), "data": ("❌ תקלה בשאיבת נתונים", 0)}


# ---------------------------------------------------------------------------
# מדדים מינרביני — פונקציות חדשות (additive only, לא משנות קוד קיים)
# ---------------------------------------------------------------------------

def compute_initial_risk_metrics(base_price, initial_stop, base_qty, nav):
    """
    סיכון דולרי ו-% מהחשבון בכניסה.
    מינרביני: "לעולם אל תסכן יותר מ-1-2.5% מהחשבון בעסקה אחת."
    מחזיר מילון עם:
      initial_risk_usd   — כמה $ בסיכון אם מגיעים לסטופ
      initial_risk_pct   — % מה-NAV שבסיכון
      sizing_grade       — 'ok' / 'oversized' / 'undersized' / 'missing_data'
    """
    if not (initial_stop > 0 and initial_stop < base_price and base_qty > 0 and nav > 0):
        return {"initial_risk_usd": 0.0, "initial_risk_pct": 0.0, "sizing_grade": "missing_data"}
    risk_usd = (base_price - initial_stop) * base_qty
    risk_pct = (risk_usd / nav) * 100
    if risk_pct > 2.5:
        grade = "oversized"
    elif risk_pct < 0.5:
        grade = "undersized"
    else:
        grade = "ok"
    return {
        "initial_risk_usd": round(risk_usd, 2),
        "initial_risk_pct": round(risk_pct, 3),
        "sizing_grade": grade,
    }


def compute_r_efficiency(total_r, days_held):
    """
    R ליום — מדד יעילות הון של מינרביני.
    מניה שמשיגה 3R ב-30 יום עדיפה על 3R ב-90 יום.
    מחזיר מילון עם r_per_day ו-efficiency_label.
    """
    if days_held <= 0:
        return {"r_per_day": 0.0, "efficiency_label": "אין נתון", "efficiency_color": "⚪"}
    r_per_day = total_r / days_held
    if total_r < 0:
        label, color = "הפסד פעיל", "🔴"
    elif r_per_day >= 0.10:
        label, color = "יעיל מאוד", "🔥"
    elif r_per_day >= 0.05:
        label, color = "יעיל", "🟢"
    elif r_per_day >= 0.02:
        label, color = "סביר", "🟡"
    elif days_held >= 8 and total_r < 0.5:
        label, color = "הון מת", "🔴"
    else:
        label, color = "איטי", "🟠"
    return {"r_per_day": round(r_per_day, 4), "efficiency_label": label, "efficiency_color": color}


def compute_mfe_mae(symbol, entry_date_str, base_price, initial_stop):
    """
    MAE (Max Adverse Excursion) — הנקודה הגרועה ביותר מאז הכניסה.
    MFE (Max Favorable Excursion) — הנקודה הטובה ביותר מאז הכניסה.

    מינרביני משתמש ב-MAE/MFE לניתוח איכות ביצוע:
      - MAE נמוך → כניסה טובה, המניה לא ירדה הרבה לאחר הכניסה
      - MFE גבוה הרבה מעל exit R → יצאת מוקדם מדי ובזבזת פוטנציאל
    מגביל לחלון ה-cache (1y). אם הכניסה ישנה יותר — מחזיר None.
    """
    try:
        entry_dt = pd.to_datetime(entry_date_str)
        hist = get_cached_history(symbol, "1y", "1d")
        if hist is None or hist.empty:
            return {"mfe_pct": None, "mae_pct": None, "mfe_r": None, "mae_r": None}
        after_entry = hist[hist.index.normalize() >= entry_dt.normalize()]
        if len(after_entry) < 2:
            return {"mfe_pct": None, "mae_pct": None, "mfe_r": None, "mae_r": None}
        period_high = float(after_entry["High"].max())
        period_low = float(after_entry["Low"].min())
        if base_price <= 0:
            return {"mfe_pct": None, "mae_pct": None, "mfe_r": None, "mae_r": None}
        mfe_pct = round((period_high - base_price) / base_price * 100, 2)
        mae_pct = round((period_low - base_price) / base_price * 100, 2)
        initial_risk = base_price - initial_stop if (initial_stop > 0 and initial_stop < base_price) else None
        mfe_r = round((period_high - base_price) / initial_risk, 2) if initial_risk else None
        mae_r = round((period_low - base_price) / initial_risk, 2) if initial_risk else None
        return {"mfe_pct": mfe_pct, "mae_pct": mae_pct, "mfe_r": mfe_r, "mae_r": mae_r}
    except Exception:
        return {"mfe_pct": None, "mae_pct": None, "mfe_r": None, "mae_r": None}


def analyze_addon_quality(buy_records):
    """
    בדיקת איכות Pyramiding לפי מינרביני:
    "הוסף רק למניות מנצחות — לעולם לא average down."
    buy_records: רשימת dict עם {'trade_date': ..., 'price': ..., 'quantity': ...}
    מחזיר מילון עם:
      has_addons          — האם יש add-on בכלל
      all_addons_higher   — האם כל ה-add-ons במחיר גבוה מהבסיס (תקין לפי מינרביני)
      worst_addon_vs_base — הסטייה הגרועה ביותר מהבסיס (שלילי = average down)
      addon_count         — מספר ה-add-ons
    """
    if not buy_records or len(buy_records) <= 1:
        return {"has_addons": False, "all_addons_higher": True, "worst_addon_vs_base": 0.0, "addon_count": 0}
    records_sorted = sorted(buy_records, key=lambda r: pd.to_datetime(r["trade_date"]))
    first_date = pd.to_datetime(records_sorted[0]["trade_date"])
    base_price = float(records_sorted[0]["price"])
    addons = [r for r in records_sorted if pd.to_datetime(r["trade_date"]) > first_date]
    if not addons:
        return {"has_addons": False, "all_addons_higher": True, "worst_addon_vs_base": 0.0, "addon_count": 0}
    deviations = [(float(r["price"]) - base_price) / base_price * 100 for r in addons]
    worst = round(min(deviations), 2)
    return {
        "has_addons": True,
        "all_addons_higher": worst >= 0,
        "worst_addon_vs_base": worst,
        "addon_count": len(addons),
    }


def compute_trend_template_full(symbol):
    """
    Trend Template מלא — כל 8 הקריטריונים של מארק מינרביני
    (Trade Like a Stock Market Wizard, פרק 7).

    הפונקציה הקיימת get_minervini_analysis() בודקת 5 קריטריונים בלבד
    ומשמשת לתצוגת טלגרם — לא משנים אותה.
    פונקציה זו מחזירה dict מובנה לדאשבורד.

    קריטריונים:
      1. מחיר נוכחי > MA150 ו-MA200
      2. MA150 > MA200
      3. MA200 עולה לפחות חודש (21 יום מסחר)
      4. MA50 > MA150 וגם MA50 > MA200
      5. מחיר נוכחי > MA50
      6. מחיר ≥ 30% מעל שפל 52 שבועות
      7. מחיר ≤ 25% מתחת לשיא 52 שבועות
      8. RS — מניה חזקה ביחס ל-SPY ב-12 חודשים האחרונים (proxy)
    """
    try:
        hist = get_cached_history(symbol, "1y", "1d")
        if hist is None or len(hist) < 200:
            return {"ok": False, "error": "missing_data", "data": None}
        close = float(hist["Close"].iloc[-1])
        ma50 = float(hist["Close"].rolling(50).mean().iloc[-1])
        ma150 = float(hist["Close"].rolling(150).mean().iloc[-1])
        ma200_series = hist["Close"].rolling(200).mean()
        ma200_now = float(ma200_series.iloc[-1])
        ma200_month_ago = float(ma200_series.iloc[-22]) if len(ma200_series) >= 222 else None
        low_52w = float(hist["Low"].min())
        high_52w = float(hist["High"].max())
        spy_hist = get_cached_history("SPY", "1y", "1d")
        stock_ret12m = safe_return(hist["Close"], 252)
        spy_ret12m = safe_return(spy_hist["Close"], 252) if spy_hist is not None and len(spy_hist) >= 252 else None

        c1 = close > ma150 and close > ma200_now
        c2 = ma150 > ma200_now
        c3 = (ma200_now > ma200_month_ago) if ma200_month_ago is not None else None  # None = לא ניתן לחשב
        c4 = ma50 > ma150 and ma50 > ma200_now
        c5 = close > ma50
        c6 = close >= low_52w * 1.30
        c7 = close >= high_52w * 0.75
        c8 = (stock_ret12m > spy_ret12m) if (stock_ret12m is not None and spy_ret12m is not None) else None

        criteria = [c1, c2, c3, c4, c5, c6, c7, c8]
        passed = sum(1 for c in criteria if c is True)
        definitive = sum(1 for c in criteria if c is not None)
        score_10 = round((passed / 8) * 10, 1)

        return {
            "ok": True,
            "error": None,
            "data": {
                "close": close, "ma50": round(ma50, 2), "ma150": round(ma150, 2), "ma200": round(ma200_now, 2),
                "low_52w": round(low_52w, 2), "high_52w": round(high_52w, 2),
                "criteria": {
                    "c1_price_above_ma150_ma200": c1,
                    "c2_ma150_above_ma200": c2,
                    "c3_ma200_uptrend_1m": c3,
                    "c4_ma50_above_ma150_ma200": c4,
                    "c5_price_above_ma50": c5,
                    "c6_above_30pct_52w_low": c6,
                    "c7_within_25pct_52w_high": c7,
                    "c8_rs_above_spy_12m": c8,
                },
                "passed": passed,
                "definitive": definitive,
                "score_10": score_10,
            },
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "data": None}


def generate_minervini_coaching(win_rate, expectancy_r, adj_rr, oversized_count=0,
                                 market_regime_status="", streak_losses=0, total_r_net=0):
    """
    מייצר רשימת תובנות coaching לפי מתודולוגיית מארק מינרביני.
    כל insight הוא string בעברית עם emoji מתאים.
    משמש בטאב Minervini Mentor בדאשבורד ובסיכום /portfolio בטלגרם.
    """
    insights = []
    regime_lower = str(market_regime_status).lower()

    if regime_lower in ['downtrend', 'ירידה', 'correction', 'תיקון']:
        insights.append("🔴 <b>שוק בירידה</b> — מינרביני: 'הגן על ההון שלך. הקטן חשיפה ל-0-25%. אל תוסיף פוזיציות חדשות בסביבה כזו.'")

    if streak_losses >= 3:
        insights.append(f"⚠️ <b>{streak_losses} הפסדים רצופים</b> — מינרביני: 'הקטן גדלים ב-50% עד שהשוק חוזר לקנות ממך. זה הגנה, לא חולשה.'")

    if win_rate < 0.40 and win_rate > 0:
        insights.append(f"⚠️ <b>שיעור הצלחה {win_rate*100:.0f}%</b> — מינרביני: 'פחות מ-40% ניצחונות. רשום ולמד את הכשלונות — מה היה שגוי בסטאפ?'")

    if expectancy_r < 0:
        insights.append(f"🔴 <b>Expectancy שלילית ({expectancy_r:.2f}R)</b> — מינרביני: 'הפסק להוסיף פוזיציות עד שה-Expectancy חיובית. כל טרייד נוסף גורע מהחשבון.'")
    elif expectancy_r > 0 and expectancy_r < 0.3:
        insights.append(f"🟡 <b>Expectancy נמוכה ({expectancy_r:.2f}R)</b> — מינרביני: 'הדרך לשפר: הגדל R:R ממוצע, צמצם הפסדים מוקדם יותר.'")

    if adj_rr < 1.5 and adj_rr > 0:
        insights.append(f"🟡 <b>Payoff Ratio {adj_rr:.2f}:1</b> — מינרביני: 'כוון לפחות 2:1. תן לרווחים לרוץ — אל תמכור מוקדם מדי.'")

    if oversized_count > 0:
        insights.append(f"⚠️ <b>{oversized_count} פוזיציות בסיכון מעל 2.5% NAV</b> — מינרביני: 'הקטן גדלים. כלל ה-1-2.5% הוא קו ההגנה הראשון שלך.'")

    if total_r_net > 5:
        insights.append(f"💡 <b>+{total_r_net:.1f}R מצטבר</b> — מינרביני: 'תיק מצליח. שמור על הדיסציפלינה ואל תגדיל סיכון מתוך ביטחון יתר.'")

    return insights


def compute_risk_deviation(open_pnl_usd, target_risk_usd):
    """
    Measure how far a losing position has deviated from its target risk.

    open_pnl_usd    current open PnL (negative = loss)
    target_risk_usd planned risk per trade in USD

    Returns a dict with deviation_r (in R units), classification, Hebrew label,
    and alert_level. Meaningful only when open_pnl_usd < 0.
    """
    if target_risk_usd <= 0:
        return {
            "deviation_r": 0.0, "classification": "unknown",
            "label": "אין בסיס סיכון", "alert_level": "none",
        }

    deviation_r = abs(open_pnl_usd) / target_risk_usd

    if deviation_r <= 1.0:
        cls, label, alert = "normal",       "תקין",            "info"
    elif deviation_r <= 1.5:
        cls, label, alert = "minor",        "חריגה קלה",       "watch"
    elif deviation_r <= 2.0:
        cls, label, alert = "moderate",     "חריגה בינונית",   "alert"
    elif deviation_r <= 3.0:
        cls, label, alert = "severe",       "חריגה חמורה",     "severe"
    else:
        cls, label, alert = "system_event", "אירוע מערכת",     "system"

    return {
        "deviation_r": round(deviation_r, 2),
        "classification": cls,
        "label": label,
        "alert_level": alert,
    }


def compute_giveback_from_peak(peak_open_r, current_open_r):
    """
    Measure profit giveback from the peak open R.

    Returns giveback_r (absolute R lost from peak), giveback_pct_of_peak
    (percentage of peak profit surrendered), classification, and Hebrew label.
    Only meaningful when peak_open_r > 0.
    """
    if peak_open_r <= 0:
        return {
            "giveback_r": 0.0, "giveback_pct_of_peak": 0.0,
            "classification": "na", "label": "אין שיא רווח",
        }

    giveback_r = peak_open_r - current_open_r
    giveback_pct = (giveback_r / peak_open_r) * 100

    if giveback_pct <= 20:
        cls, label = "natural",           "ויתור טבעי"
    elif giveback_pct <= 35:
        cls, label = "watch",             "מעקב — ויתור מעל 20%"
    elif giveback_pct <= 50:
        cls, label = "tighten",           "להדק — ויתור מעל 35%"
    else:
        cls, label = "protection_failure", "כשל הגנת רווח — ויתור מעל 50%"

    return {
        "giveback_r": round(giveback_r, 2),
        "giveback_pct_of_peak": round(giveback_pct, 1),
        "classification": cls,
        "label": label,
    }


# ── Phase 1 — Risk Basis Engine ───────────────────────────────────────────────
# Standalone, pure functions.  No side-effects, no DB/yfinance calls.
# Every subsequent module (State Machine, Profit Protection, Runner) builds on
# these primitives.  All monetary values in USD; R values dimensionless ratios.
# ─────────────────────────────────────────────────────────────────────────────

# Data scope constants — attach to every reported metric so consumers know
# the coverage window of the underlying data.
DATA_SCOPE_YTD         = "YTD"
DATA_SCOPE_SINCE_IMPORT = "Since Import"
DATA_SCOPE_FULL_HISTORY = "Full History"
DATA_SCOPE_ESTIMATED   = "Estimated"
DATA_SCOPE_UNKNOWN     = "Unknown"

# ── Sample-size thresholds ────────────────────────────────────────────────────
_SAMPLE_INITIAL  = 30   # below → stats are preliminary
_SAMPLE_USABLE   = 30   # >= → useful for risk management
_SAMPLE_SIGNIFICANT = 100  # >= → can rely on expectancy


def compute_original_campaign_risk(
    side: str,
    entry_price: float,
    initial_stop: float,
    quantity: float,
    fees: float = 0.0,
) -> float:
    """
    True initial risk = (entry − initial_stop) × qty + fees.

    Returns 0.0 when any value is invalid (no stop, zero quantity, etc.).
    LONG:  entry_price > initial_stop.
    SHORT: initial_stop > entry_price.
    """
    if entry_price <= 0 or initial_stop <= 0 or quantity <= 0:
        return 0.0
    if side.upper() in ("BUY", "LONG"):
        risk_per_share = entry_price - initial_stop
    else:
        risk_per_share = initial_stop - entry_price
    return round(max(0.0, risk_per_share * quantity + fees), 2)


def compute_frozen_target_risk(
    base_capital: float,
    nav: float,
    target_risk_pct: float,
) -> dict:
    """
    Freeze both risk-USD values at the moment of entry.

    Always store BOTH.  Performance stats use target_risk_current_nav;
    risk-mode transitions use target_risk_base_capital for stability.
    """
    return {
        "target_risk_base_capital": round(base_capital * target_risk_pct, 2),
        "target_risk_current_nav":  round(nav * target_risk_pct, 2),
    }


def compute_r_true(net_pnl: float, original_campaign_risk: float) -> float:
    """R using actual initial risk (risk_basis = True)."""
    if original_campaign_risk <= 0:
        return 0.0
    return round(net_pnl / original_campaign_risk, 2)


def compute_r_target(net_pnl: float, frozen_target_risk_usd: float) -> float:
    """R using frozen target risk at entry (risk_basis = Target)."""
    if frozen_target_risk_usd <= 0:
        return 0.0
    return round(net_pnl / frozen_target_risk_usd, 2)


def compute_capital_at_risk_usd(
    side: str,
    avg_entry_price: float,
    current_stop: float,
    open_quantity: float,
) -> float:
    """
    Capital still at risk given current stop.

    Returns 0.0 when stop has moved above entry (long) or below (short) —
    meaning capital risk is fully protected, only giveback of open profit remains.
    """
    if open_quantity <= 0 or avg_entry_price <= 0 or current_stop <= 0:
        return 0.0
    if side.upper() in ("BUY", "LONG"):
        at_risk = (avg_entry_price - current_stop) * open_quantity
    else:
        at_risk = (current_stop - avg_entry_price) * open_quantity
    return round(max(0.0, at_risk), 2)


def compute_open_pnl_at_stop(
    side: str,
    avg_entry_price: float,
    current_stop: float,
    open_quantity: float,
    estimated_exit_fees: float = 0.0,
) -> float:
    """P&L if the remaining open position exits at the current stop right now."""
    if open_quantity <= 0 or avg_entry_price <= 0 or current_stop <= 0:
        return 0.0
    if side.upper() in ("BUY", "LONG"):
        pnl = (current_stop - avg_entry_price) * open_quantity - estimated_exit_fees
    else:
        pnl = (avg_entry_price - current_stop) * open_quantity - estimated_exit_fees
    return round(pnl, 2)


def compute_protected_profit_usd(
    realized_pnl: float,
    open_pnl_at_stop: float,
) -> float:
    """
    Profit locked in = realized PnL + what you'd net if you exited at stop now.

    open_pnl_at_stop can be negative (stop is below entry) — that portion is not
    'protected', so we floor it at 0 for this calculation.
    """
    return round(realized_pnl + max(0.0, open_pnl_at_stop), 2)


def compute_giveback_usd(open_pnl: float, open_pnl_at_stop: float) -> float:
    """
    Open profit that would be surrendered between current price and current stop.

    Only meaningful when open_pnl > 0.  Returns 0 when underwater.
    """
    if open_pnl <= 0:
        return 0.0
    return round(max(0.0, open_pnl - open_pnl_at_stop), 2)


def compute_giveback_pct_of_open_profit(
    giveback_usd: float, open_pnl: float
) -> float:
    """Giveback as % of current open profit.  Returns 0.0 when no open profit."""
    if open_pnl <= 0:
        return 0.0
    return round((giveback_usd / open_pnl) * 100, 1)


# Giveback severity buckets used by the anti-spam dedup system.
GIVEBACK_BUCKET_CONSERVATIVE = 25.0   # 0–25 %
GIVEBACK_BUCKET_NORMAL       = 40.0   # 25–40 %
GIVEBACK_BUCKET_WIDE         = 60.0   # 40–60 %
# > 60 % = Excessive


def classify_giveback_severity(giveback_pct_of_open_profit: float) -> str:
    """Returns 'conservative'|'normal'|'wide'|'excessive'."""
    g = giveback_pct_of_open_profit
    if g <= GIVEBACK_BUCKET_CONSERVATIVE:
        return "conservative"
    if g <= GIVEBACK_BUCKET_NORMAL:
        return "normal"
    if g <= GIVEBACK_BUCKET_WIDE:
        return "wide"
    return "excessive"


# ── Position Sizing Quality ───────────────────────────────────────────────────

_SIZING_TIERS = [
    # (upper_bound_exclusive, classification, score, countable, alert_level)
    (0.35, "Micro Probe",      30,  False, None),
    (0.60, "Probe",            50,  False, None),
    (0.85, "Undersized",       70,  True,  None),
    (1.15, "Ideal",            100, True,  None),
    (1.30, "Slight Oversize",  80,  True,  "yellow"),
    (1.50, "Oversized",        55,  True,  "orange"),
]
_SIZING_CRITICAL = ("Critical Oversize", 20, True, "red")


def compute_sizing_ratio(
    original_campaign_risk: float,
    frozen_target_risk_usd: float,
) -> dict:
    """
    sizing_ratio = original_campaign_risk / frozen_target_risk_usd.

    Returns:
      sizing_ratio          float
      classification        str  (e.g. "Ideal", "Oversized", "Micro Probe")
      score                 int  0–100
      countable_for_main_stats  bool
      alert_level           str | None  ("yellow"/"orange"/"red")
    """
    if frozen_target_risk_usd <= 0 or original_campaign_risk <= 0:
        return {
            "sizing_ratio": 0.0,
            "classification": "Unknown",
            "score": 0,
            "countable_for_main_stats": False,
            "alert_level": None,
        }
    ratio = original_campaign_risk / frozen_target_risk_usd
    for upper, label, score, countable, alert in _SIZING_TIERS:
        if ratio < upper:
            return {
                "sizing_ratio": round(ratio, 2),
                "classification": label,
                "score": score,
                "countable_for_main_stats": countable,
                "alert_level": alert,
            }
    label, score, countable, alert = _SIZING_CRITICAL
    return {
        "sizing_ratio": round(ratio, 2),
        "classification": label,
        "score": score,
        "countable_for_main_stats": countable,
        "alert_level": alert,
    }


# ── Data Scope helpers ────────────────────────────────────────────────────────

def get_sample_size_context(countable_trades: int) -> dict:
    """
    Returns context dict for any reported statistic.

    Keys:
      countable_trades   int
      warning            bool   True when trades < _SAMPLE_INITIAL (30)
      usable             bool   True when trades >= 30
      significant        bool   True when trades >= 100
      label              str    Hebrew description of the sample state
    """
    if countable_trades < _SAMPLE_INITIAL:
        label = "סטטיסטיקה ראשונית בלבד — אין לאשר הגדלת סיכון אגרסיבית"
    elif countable_trades < _SAMPLE_SIGNIFICANT:
        label = "המדגם מתחיל להיות שימושי לניהול סיכון"
    else:
        label = "מדגם משמעותי — ניתן להסתמך יותר על מדדי תוחלת"
    return {
        "countable_trades": countable_trades,
        "warning":     countable_trades < _SAMPLE_INITIAL,
        "usable":      countable_trades >= _SAMPLE_INITIAL,
        "significant": countable_trades >= _SAMPLE_SIGNIFICANT,
        "label":       label,
    }


def add_data_scope(value, scope: str, countable_trades: int | None = None) -> dict:
    """
    Wrap any metric value with its data scope and optional sample context.

    Usage:
        win_rate_obj = add_data_scope(0.444, DATA_SCOPE_YTD, countable_trades=9)
        # → {"value": 0.444, "scope": "YTD", "countable_trades": 9, "sample_warning": True}
    """
    result: dict = {"value": value, "scope": scope}
    if countable_trades is not None:
        result["countable_trades"] = countable_trades
        result["sample_warning"] = countable_trades < _SAMPLE_INITIAL
    return result


def compute_data_quality_badge(setup_type, entry_price, quantity, stop, init_sl, target_risk_usd=0):
    """
    Compute a data quality badge for a position.
    Returns (primary_badge, risk_badge, label).
      primary_badge: ✅ Verified | ⚠️ Partial | 🟠 External | 🔴 Broken
      risk_badge:    🧮 True-Risk | 📊 Target-Based | ""
      label:         short English descriptor
    """
    if is_algo_position(setup_type):
        primary, label = "🟠", "External"
    elif entry_price <= 0 or quantity <= 0:
        primary, label = "🔴", "Broken"
    elif stop > 0 and stop < entry_price and init_sl > 0 and init_sl < entry_price:
        primary, label = "✅", "Verified"
    elif (stop > 0 and stop < entry_price) or target_risk_usd > 0:
        primary, label = "⚠️", "Partial"
    else:
        primary, label = "🔴", "Broken"

    basis = classify_risk_basis(
        init_sl if (init_sl > 0 and init_sl < entry_price) else stop,
        entry_price, setup_type, target_risk_usd
    )
    risk_badge = {"True": "🧮", "Target": "📊"}.get(basis, "")

    return primary, risk_badge, label


# ── Statistical Bucket Classification ─────────────────────────────────────────
# stat_bucket separates ALGO (observed) from manual discretionary campaigns
# so that stats like Win Rate, Expectancy, and Avg-R are never contaminated.

STAT_BUCKET_ALGO = "ALGO_OBSERVED"
STAT_BUCKET_DATA_INCOMPLETE = "DATA_INCOMPLETE"

_MANUAL_SETUP_PREFIXES = ("VCP", "EP", "BREAKOUT", "SWING", "TREND", "MOMENTUM")


def classify_stat_bucket(setup_type: str, original_campaign_risk: float,
                         target_risk_usd: float = 0) -> str:
    """
    Derive stat_bucket for a closed campaign. Never stored in DB — always runtime.

    Buckets:
      ALGO_OBSERVED      — ALGO-managed positions (external, oversight only)
      VCP_MANUAL         — VCP discretionary with known initial risk
      EP_MANUAL          — EP discretionary with known initial risk
      <SETUP>_MANUAL     — other manual setups with known initial risk
      DATA_INCOMPLETE    — manual setup but initial stop missing → excluded from Expectancy
    """
    st = str(setup_type).upper().strip()
    if is_algo_position(setup_type):
        return STAT_BUCKET_ALGO
    if original_campaign_risk > 0:
        for prefix in _MANUAL_SETUP_PREFIXES:
            if st.startswith(prefix):
                return f"{prefix}_MANUAL"
        return f"{st}_MANUAL" if st and st not in ("UNKNOWN", "NONE", "NAN", "") else STAT_BUCKET_DATA_INCOMPLETE
    return STAT_BUCKET_DATA_INCOMPLETE


def is_stat_countable(stat_bucket: str) -> bool:
    """True if this campaign should count in Expectancy / Win Rate stats."""
    return stat_bucket != STAT_BUCKET_DATA_INCOMPLETE and stat_bucket != STAT_BUCKET_ALGO


def is_discretionary_bucket(stat_bucket: str) -> bool:
    return stat_bucket.endswith("_MANUAL")


# ── ALGO Risk Oversight Score ──────────────────────────────────────────────────

def compute_algo_risk_oversight_score(
    symbol: str,
    pnl_usd: float,
    target_risk_usd: float,
    original_campaign_risk: float,
    r_realized: float,
    quality_val,
) -> dict:
    """
    Weighted 5-factor score (0–100) measuring how well Sentinel could *observe*
    an ALGO campaign. Higher score = better data transparency.

    Factors:
      1. Symbol known and in ALGO_SYMBOL_LIMITS          — 20 pts
      2. target_risk_usd available                       — 20 pts
      3. R multiple computable (target_risk_usd > 0)     — 20 pts
      4. PnL data present (not zero / suspicious)        — 20 pts
      5. Entry quality recorded                          — 20 pts
    """
    score = 0
    details = {}

    sym = str(symbol).upper()
    if sym in ALGO_SYMBOLS:
        score += 20
        details["symbol_known"] = True
    else:
        details["symbol_known"] = False

    if target_risk_usd > 0:
        score += 20
        details["target_risk_known"] = True
    else:
        details["target_risk_known"] = False

    if target_risk_usd > 0 and r_realized != 0:
        score += 20
        details["r_computable"] = True
    else:
        details["r_computable"] = False

    if pnl_usd != 0:
        score += 20
        details["pnl_present"] = True
    else:
        details["pnl_present"] = False

    try:
        q = float(quality_val)
        if q > 0:
            score += 20
            details["quality_recorded"] = True
        else:
            details["quality_recorded"] = False
    except (TypeError, ValueError):
        details["quality_recorded"] = False

    label_map = {
        range(80, 101): "🟢 שקיפות גבוהה",
        range(60, 80):  "🟡 שקיפות חלקית",
        range(40, 60):  "🟠 שקיפות נמוכה",
        range(0, 40):   "🔴 מידע חסר",
    }
    label = "🔴 מידע חסר"
    for r, lbl in label_map.items():
        if score in r:
            label = lbl
            break

    return {"score": score, "label": label, "details": details}


# ── Phase 4: ALGO Oversight Summary ───────────────────────────────────────────

def compute_algo_oversight_summary(algo_positions: list, acc_size: float) -> dict:
    """
    Aggregate ALGO oversight metrics across all open ALGO positions.

    algo_positions: list of dicts with keys:
        symbol, pos_value, oversight_score, open_r, campaign_id
    acc_size: account NAV

    Returns:
        n_positions            int
        total_exposure_usd     float
        total_exposure_pct     float
        visibility_avg         float  (avg oversight_score, 0-100)
        visibility_below_threshold bool  (avg < 60)
        symbol_cap_breaches    list of {symbol, exposure_pct, cap_pct}
        deep_loss_positions    list of {symbol, open_r, campaign_id}  (open_r <= -2.0)
    """
    if not algo_positions:
        return {
            "n_positions": 0,
            "total_exposure_usd": 0.0,
            "total_exposure_pct": 0.0,
            "visibility_avg": 100.0,
            "visibility_below_threshold": False,
            "symbol_cap_breaches": [],
            "deep_loss_positions": [],
        }

    total_exp = sum(p["pos_value"] for p in algo_positions)
    total_exp_pct = (total_exp / acc_size * 100) if acc_size > 0 else 0.0
    vis_avg = sum(p["oversight_score"] for p in algo_positions) / len(algo_positions)

    # Aggregate per-symbol exposure across campaigns for the same symbol
    sym_exposure: dict = {}
    for p in algo_positions:
        sym = str(p["symbol"]).upper()
        sym_exposure[sym] = sym_exposure.get(sym, 0.0) + p["pos_value"]

    cap_breaches = []
    for sym, val in sym_exposure.items():
        exp_pct = (val / acc_size * 100) if acc_size > 0 else 0.0
        cap = ALGO_SYMBOL_LIMITS.get(sym, 100.0)
        if exp_pct > cap:
            cap_breaches.append({"symbol": sym,
                                  "exposure_pct": round(exp_pct, 1),
                                  "cap_pct": cap})

    deep_loss = [
        {"symbol": p["symbol"], "open_r": p["open_r"], "campaign_id": p["campaign_id"]}
        for p in algo_positions if p["open_r"] <= -2.0
    ]

    return {
        "n_positions": len(algo_positions),
        "total_exposure_usd": round(total_exp, 2),
        "total_exposure_pct": round(total_exp_pct, 2),
        "visibility_avg": round(vis_avg, 1),
        "visibility_below_threshold": vis_avg < 60.0,
        "symbol_cap_breaches": cap_breaches,
        "deep_loss_positions": deep_loss,
    }


# ── Earnings Risk Module ───────────────────────────────────────────────────────
_EARNINGS_CACHE_TTL = 6 * 3600  # 6 hours — earnings dates change rarely


def fetch_next_earnings_date(symbol: str) -> dict:
    """
    Fetch next earnings date for a symbol via yfinance calendar.
    Cached 6 hours to avoid hammering Yahoo on every dashboard load.

    Returns:
      {
        "date":           datetime | None,
        "days_to_event":  int | None,
        "cushion_verdict": str  (Hebrew + emoji),
        "ok":             bool,
      }
    """
    cache_key = f"{symbol}_earnings"
    now = time.time()
    if cache_key in YF_CACHE and (now - YF_CACHE[cache_key]["time"]) < _EARNINGS_CACHE_TTL:
        return YF_CACHE[cache_key]["data"]

    result = {"date": None, "days_to_event": None, "cushion_verdict": "⚪ אין מידע", "ok": False}
    try:
        smart_delay()
        tk = yf.Ticker(symbol)
        cal = tk.calendar
        if cal is None:
            YF_CACHE[cache_key] = {"data": result, "time": now}
            return result

        # yfinance returns dict or DataFrame depending on version
        if hasattr(cal, 'to_dict'):
            cal = cal.to_dict()

        earnings_date = None
        for key in ("Earnings Date", "earningsDate", "earnings_date"):
            val = cal.get(key)
            if val is not None:
                if isinstance(val, (list, tuple)) and len(val) > 0:
                    val = val[0]
                try:
                    from datetime import datetime as _dt
                    if hasattr(val, 'date'):
                        earnings_date = val
                    else:
                        earnings_date = _dt.fromisoformat(str(val))
                    break
                except Exception:
                    pass

        if earnings_date is None:
            YF_CACHE[cache_key] = {"data": result, "time": now}
            return result

        from datetime import datetime as _dt, timezone
        now_dt = _dt.now(tz=earnings_date.tzinfo) if earnings_date.tzinfo else _dt.now()
        days = (earnings_date.replace(tzinfo=None) - now_dt.replace(tzinfo=None)).days

        if days < 0:
            verdict = "⚪ עבר (אין תאריך הבא)"
        elif days <= 7:
            verdict = f"🔴 תוך {days} ימים — לבחון חשיפה"
        elif days <= 21:
            verdict = f"🟡 תוך {days} ימים"
        else:
            verdict = f"🟢 {days} ימים"

        result = {"date": earnings_date, "days_to_event": days, "cushion_verdict": verdict, "ok": True}
    except Exception:
        pass

    YF_CACHE[cache_key] = {"data": result, "time": now}
    return result


# ── NAV Freshness ──────────────────────────────────────────────────────────────
NAV_STALE_HOURS = 24   # warn if NAV not updated within this window
NAV_CRITICAL_HOURS = 48  # critical if older than this

_CONFIG_PATHS = ["/app/sentinel_config.json", "sentinel_config.json"]


def get_nav_with_freshness() -> dict:
    """
    Read NAV from sentinel_config.json and compute freshness.

    Returns:
      {
        "nav":          float,
        "source":       "ibkr_sync" | "manual" | "fallback",
        "updated_at":   datetime | None,
        "age_hours":    float | None,
        "is_stale":     bool,
        "is_critical":  bool,
        "freshness_label": str   (Hebrew, for Telegram display),
        "ok":           bool,
      }
    """
    fallback = {
        "nav": 7500.0, "source": "fallback", "updated_at": None,
        "age_hours": None, "is_stale": True, "is_critical": True,
        "freshness_label": "🔴 NAV: fallback — sentinel_config.json לא נמצא",
        "ok": False,
    }

    cfg_path = next((p for p in _CONFIG_PATHS if os.path.exists(p)), None)
    if cfg_path is None:
        return fallback

    try:
        with open(cfg_path, "r") as f:
            cfg = json.load(f)
    except Exception:
        return fallback

    nav = float(cfg.get("nav") or cfg.get("total_deposited") or 7500.0)
    updated_at_str = cfg.get("nav_updated_at")

    if updated_at_str:
        try:
            updated_at = datetime.fromisoformat(updated_at_str)
            age_hours = (datetime.now() - updated_at).total_seconds() / 3600
            is_stale = age_hours > NAV_STALE_HOURS
            is_critical = age_hours > NAV_CRITICAL_HOURS
            source = "ibkr_sync"
            if is_critical:
                label = f"🔴 NAV ${nav:,.0f} — ישן {age_hours:.0f}ש׳ (לא עודכן!)"
            elif is_stale:
                label = f"🟡 NAV ${nav:,.0f} — עודכן לפני {age_hours:.0f}ש׳"
            else:
                label = f"✅ NAV ${nav:,.0f} — עודכן לפני {age_hours:.1f}ש׳"
        except ValueError:
            updated_at, age_hours = None, None
            is_stale = is_critical = True
            source = "manual"
            label = f"⚠️ NAV ${nav:,.0f} — תאריך עדכון לא תקין"
    else:
        updated_at, age_hours = None, None
        is_stale = is_critical = True
        source = "manual"
        label = f"🟠 NAV ${nav:,.0f} — אין timestamp (הוגדר ידנית)"

    return {
        "nav": nav, "source": source, "updated_at": updated_at,
        "age_hours": age_hours, "is_stale": is_stale, "is_critical": is_critical,
        "freshness_label": label, "ok": True,
    }


# ── Position Intent Classification ────────────────────────────────────────────
# intent describes the ROLE of the position — affects how it's judged.
INTENT_LABELS = {
    "starter":       "🌱 Starter",
    "probe":         "🧪 Probe",
    "full_position": "🎯 Full Position",
    "runner":        "🏃 Runner",
    "earnings_hold": "📅 Earnings Hold",
    "algo_signal":   "🤖 ALGO Signal",
    "reentry":       "🔁 Re-entry",
    "unknown":       "⚪ Unknown",
}


def classify_intent(setup_type: str, management_state: str, total_campaign_r: float,
                    days_held: int, add_on_count: int = 0) -> str:
    """
    Derive intent from available runtime data.
    Intent is never stored in DB — always derived.
    """
    st = str(setup_type).upper()
    ms = str(management_state).lower()

    if is_algo_position(setup_type):
        return "algo_signal"
    if "probe" in ms or "test" in ms:
        return "probe"
    if "runner" in ms:
        return "runner"
    if "reentry" in ms or "re_entry" in ms:
        return "reentry"
    if "earnings" in ms:
        return "earnings_hold"
    if total_campaign_r >= 2.0 and add_on_count == 0:
        return "runner"
    if add_on_count == 0 and days_held <= 3:
        return "starter"
    if ms in ("full_position", "full"):
        return "full_position"
    return "full_position"


# ── Mistake Classification (closed campaigns with loss) ───────────────────────
MISTAKE_LABELS = {
    "good_loss":   "✅ Good Loss — לפי תוכנית",
    "bad_loss":    "🔴 Bad Loss — חריגה מהכללים",
    "system_loss": "🔧 System Loss — תקלת מערכת/פקודה",
    "market_loss": "🌊 Market Loss — גאפ / אירוע חיצוני",
    "data_loss":   "⚠️ Data Loss — חישוב לא אמין",
    "probe_loss":  "🧪 Probe Loss — הפסד מתוכנן",
    "unknown":     "⚪ Unknown",
}


def classify_mistake(intent: str, stat_bucket: str, pnl_usd: float,
                     management_notes: str = "") -> str:
    """
    Derive mistake classification for a closed campaign with a loss.
    For winning campaigns returns None.
    Always derived at runtime — never stored.
    """
    if pnl_usd >= 0:
        return None

    notes = str(management_notes).lower()
    if intent == "probe":
        return "probe_loss"
    if stat_bucket == STAT_BUCKET_DATA_INCOMPLETE:
        return "data_loss"
    if any(w in notes for w in ("gap", "גאפ", "halt", "news", "earnings miss")):
        return "market_loss"
    if any(w in notes for w in ("sync", "error", "system", "order", "execution")):
        return "system_loss"
    if any(w in notes for w in ("plan", "stop honored", "תוכנית", "לפי תוכנית")):
        return "good_loss"
    if any(w in notes for w in ("violated", "no stop", "moved stop", "averaged down", "חריגה")):
        return "bad_loss"
    return "unknown"


# ── Phase 2 — Position State Machine ─────────────────────────────────────────
# Pure classification — no DB, no yfinance, no side-effects.
# The caller (risk_monitor.py) fetches live prices, earnings dates, and
# follow-through scores, then passes them here.
#
# State priority (highest first):
#   1. ALGO_OBSERVED  — externally managed, oversight only
#   2. DATA_INCOMPLETE — missing critical data to compute R
#   3. BROKEN          — price traded through stop, or violation_score >= 6
#   4. RUNNER          — open_r >= 5R, or realized >= original_risk with trend
#   5. PROFIT_PROTECTION — open_r >= 2R
#   6. WORKING         — open_r >= 1R with acceptable follow-through
#   7. YELLOW_FLAG     — violation_score 2-5 (minor/major violations)
#   8. DEAD_MONEY      — age >= 8d, flat R, no new high, weak follow-through
#   9. PROVING         — age 3-7d, R in early range
#  10. NEW             — age <= 2d
#  11. Fallback        — PROVING (catch-all for edge cases)
#
# EVENT_RISK is always a secondary flag (can co-exist with any primary state).
# ─────────────────────────────────────────────────────────────────────────────

POSITION_STATE_NEW               = "NEW"
POSITION_STATE_PROVING           = "PROVING"
POSITION_STATE_WORKING           = "WORKING"
POSITION_STATE_PROFIT_PROTECTION = "PROFIT_PROTECTION"
POSITION_STATE_RUNNER            = "RUNNER"
POSITION_STATE_YELLOW_FLAG       = "YELLOW_FLAG"
POSITION_STATE_BROKEN            = "BROKEN"
POSITION_STATE_DEAD_MONEY        = "DEAD_MONEY"
POSITION_STATE_ALGO_OBSERVED     = "ALGO_OBSERVED"
POSITION_STATE_DATA_INCOMPLETE   = "DATA_INCOMPLETE"

_STATE_LABELS: dict[str, str] = {
    POSITION_STATE_NEW:               "🆕 חדש",
    POSITION_STATE_PROVING:           "🔍 מוכיח",
    POSITION_STATE_WORKING:           "✅ עובד",
    POSITION_STATE_PROFIT_PROTECTION: "🛡️ הגנת רווח",
    POSITION_STATE_RUNNER:            "🏃 Runner Mode",
    POSITION_STATE_YELLOW_FLAG:       "🟡 דגל צהוב",
    POSITION_STATE_BROKEN:            "🔴 שבור",
    POSITION_STATE_DEAD_MONEY:        "⏳ Dead Money",
    POSITION_STATE_ALGO_OBSERVED:     "🤖 ALGO — פיקוח בלבד",
    POSITION_STATE_DATA_INCOMPLETE:   "⚠️ נתונים חלקיים",
}

# R thresholds
_R_RUNNER          = 5.0
_R_PROFIT_PROTECT  = 2.0
_R_WORKING         = 1.0

# Runner via realized PnL: realized_pnl >= original_campaign_risk + follow-through OK
_RUNNER_FOLLOW_THROUGH_MIN = 70.0

# Working: follow-through must be OK (or unknown → benefit of the doubt)
_WORKING_FOLLOW_THROUGH_MIN = 60.0

# Dead Money
_DEAD_MONEY_MIN_DAYS          = 8
_DEAD_MONEY_MIN_R             = -0.5
_DEAD_MONEY_MAX_R             = 0.75
_DEAD_MONEY_FOLLOW_MAX        = 50.0   # follow_through_score < this → weak

# Proving window
_PROVING_MIN_DAYS = 3
_PROVING_MAX_DAYS = 7
_NEW_MAX_DAYS     = 2

# Violation score thresholds
_VIOLATION_YELLOW_FLAG = 2
_VIOLATION_BROKEN      = 6

# Event Risk windows
_EVENT_RISK_MAX_DAYS    = 15
_EVENT_RISK_ORANGE_DAYS = 7
_EVENT_RISK_RED_DAYS    = 3


def compute_event_risk_info(
    days_to_earnings: "int | None",
    management_mode: str,
) -> dict:
    """
    Compute event-risk flag and severity.

    Only active for manual_managed positions — ALGO positions carry their own
    event risk independently of Sentinel.

    Returns:
      active    bool
      severity  "yellow" | "orange" | "red" | None
      days      int | None
    """
    if days_to_earnings is None or management_mode == "algo_observed":
        return {"active": False, "severity": None, "days": days_to_earnings}
    if days_to_earnings <= _EVENT_RISK_RED_DAYS:
        severity = "red"
    elif days_to_earnings <= _EVENT_RISK_ORANGE_DAYS:
        severity = "orange"
    elif days_to_earnings <= _EVENT_RISK_MAX_DAYS:
        severity = "yellow"
    else:
        return {"active": False, "severity": None, "days": days_to_earnings}
    return {"active": True, "severity": severity, "days": days_to_earnings}


def _price_through_stop(side: str, current_price: float, current_stop: float) -> bool:
    """True when price has traded through the stop (position is broken)."""
    if current_price <= 0 or current_stop <= 0:
        return False
    if side.upper() in ("BUY", "LONG"):
        return current_price <= current_stop
    return current_price >= current_stop   # SHORT


def _make_state(state: str, event_risk: dict, reason: str) -> dict:
    return {
        "state":      state,
        "label":      _STATE_LABELS.get(state, state),
        "event_risk": event_risk,
        "reason":     reason,
    }


def compute_position_state(
    side: str,
    management_mode: str,
    age_days: float,
    open_r: float,
    realized_pnl: float,
    original_campaign_risk: float,
    current_price: float,
    current_stop: float,
    days_to_earnings: "int | None",
    follow_through_score: "float | None" = None,
    violation_score: int = 0,
    has_new_high_since_entry: bool = True,
    has_open_quantity: bool = True,
) -> dict:
    """
    Classify an open campaign into one of the 10 position states.

    Parameters
    ----------
    side                      "BUY" / "LONG" or "SELL" / "SHORT"
    management_mode           "manual_managed" | "algo_observed" | "unknown"
    age_days                  calendar days since first trade in the campaign
    open_r                    current open R (from Phase 1 compute_r_true/target)
    realized_pnl              total realized P&L in USD (partial-close profits)
    original_campaign_risk    Phase 1 result; 0 = data unavailable
    current_price             live market price (0 = unavailable)
    current_stop              current stop level (0 = unknown / ALGO)
    days_to_earnings          None = unknown; int = calendar days until event
    follow_through_score      0–100; None = not yet computed (treated as neutral)
    violation_score           cumulative violation points (Violation Engine)
    has_new_high_since_entry  False = price never made new high after entry
    has_open_quantity         False = position fully closed (caller should not call)

    Returns
    -------
    dict:
      state       str  — primary state constant
      label       str  — Hebrew/emoji display label
      event_risk  dict — compute_event_risk_info() result
      reason      str  — human-readable reason for logging
    """
    er = compute_event_risk_info(days_to_earnings, management_mode)

    # ── 1. ALGO_OBSERVED ─────────────────────────────────────────────────────
    if management_mode == "algo_observed":
        return _make_state(POSITION_STATE_ALGO_OBSERVED, er,
                           "פוזיציית אלגו — פיקוח בלבד")

    # ── 2. DATA_INCOMPLETE ───────────────────────────────────────────────────
    if management_mode == "unknown" or original_campaign_risk <= 0:
        return _make_state(POSITION_STATE_DATA_INCOMPLETE, er,
                           "נתוני סיכון חסרים — לא ניתן לחשב R")

    # ── 3. BROKEN ────────────────────────────────────────────────────────────
    if _price_through_stop(side, current_price, current_stop):
        return _make_state(POSITION_STATE_BROKEN, er, "מחיר עבר את הסטופ")
    if violation_score >= _VIOLATION_BROKEN:
        return _make_state(POSITION_STATE_BROKEN, er,
                           f"ניקוד חריגות {violation_score} — שבור")

    # ── 4. RUNNER ────────────────────────────────────────────────────────────
    runner_by_r = open_r >= _R_RUNNER
    runner_by_realized = (
        original_campaign_risk > 0
        and realized_pnl >= original_campaign_risk
        and has_open_quantity
        and (follow_through_score is None or follow_through_score >= _RUNNER_FOLLOW_THROUGH_MIN)
    )
    if runner_by_r or runner_by_realized:
        reason = (f"Runner: {open_r:.1f}R" if runner_by_r
                  else "רווח ממומש ≥ סיכון מקורי + יתרה פתוחה")
        return _make_state(POSITION_STATE_RUNNER, er, reason)

    # ── 5. PROFIT_PROTECTION ─────────────────────────────────────────────────
    if open_r >= _R_PROFIT_PROTECT:
        return _make_state(POSITION_STATE_PROFIT_PROTECTION, er,
                           f"הגנת רווח: {open_r:.1f}R")

    # ── 6. WORKING ───────────────────────────────────────────────────────────
    good_ft = (follow_through_score is None
               or follow_through_score >= _WORKING_FOLLOW_THROUGH_MIN)
    if open_r >= _R_WORKING and good_ft:
        return _make_state(POSITION_STATE_WORKING, er, f"עובד: {open_r:.1f}R")

    # ── 7. YELLOW_FLAG ───────────────────────────────────────────────────────
    if violation_score >= _VIOLATION_YELLOW_FLAG:
        return _make_state(POSITION_STATE_YELLOW_FLAG, er,
                           f"דגל צהוב: ניקוד חריגות {violation_score}")

    # ── 8. DEAD_MONEY ────────────────────────────────────────────────────────
    weak_ft = (follow_through_score is not None
               and follow_through_score < _DEAD_MONEY_FOLLOW_MAX)
    if (age_days >= _DEAD_MONEY_MIN_DAYS
            and _DEAD_MONEY_MIN_R <= open_r <= _DEAD_MONEY_MAX_R
            and weak_ft
            and not has_new_high_since_entry):
        return _make_state(POSITION_STATE_DEAD_MONEY, er,
                           f"הון מת: {age_days:.0f} ימים, {open_r:.1f}R, אין שיא חדש")

    # ── 9. PROVING ───────────────────────────────────────────────────────────
    if _PROVING_MIN_DAYS <= age_days <= _PROVING_MAX_DAYS and open_r <= _R_WORKING:
        return _make_state(POSITION_STATE_PROVING, er,
                           f"מוכיח: יום {age_days:.0f}, {open_r:.1f}R")

    # ── 10. NEW ──────────────────────────────────────────────────────────────
    if age_days <= _NEW_MAX_DAYS:
        return _make_state(POSITION_STATE_NEW, er, f"חדש: יום {age_days:.0f}")

    # ── Fallback ─────────────────────────────────────────────────────────────
    return _make_state(POSITION_STATE_PROVING, er,
                       f"פוזיציה מתפתחת: {open_r:.1f}R, {age_days:.0f} ימים")


def get_position_state_display_label(state_result: dict) -> str:
    """
    Build the combined display label for Telegram/dashboard.
    Merges primary state label with event risk when active.
    Example: "🏃 Runner Mode + 📅 Event Risk (7 ימים)"
    """
    label = state_result.get("label", "")
    er = state_result.get("event_risk", {})
    if er.get("active") and er.get("days") is not None:
        label = f"{label} + 📅 Event Risk ({er['days']} ימים)"
    return label
