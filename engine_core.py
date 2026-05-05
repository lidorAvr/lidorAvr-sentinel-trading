import time
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
import threading
import requests
import random
from bs4 import BeautifulSoup

ALGO_SYMBOL_LIMITS = {"QQQ": 10.0, "TSLA": 7.0, "JPM": 7.0, "PLTR": 6.0, "HOOD": 6.0}
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
        "lower_lows_3": bool(len(df) >= 4 and df["Low"].iloc[-1] < df["Low"].iloc[-2] < df["Low"].iloc[-3]),
        "rs20_market": rs_bundle["rs20_market"], "rs20_sector_market": rs_bundle["rs20_sector_market"],
        "rs20_stock_sector": rs_bundle["rs20_stock_sector"]
    }

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


POSITION_STATE_HE = {
    "New Entry": "כניסה חדשה",
    "Working": "עובד תקין",
    "Tennis Ball": "התאוששות חזקה",
    "Squat Watch": "פריצה בלי המשכיות",
    "Violation": "הפרות ניהול",
    "Breakeven Protect": "הגנת איזון",
    "Profit Protect": "הגנת רווח",
    "Climactic": "מהלך מתוח",
    "Dead Money": "הון תקוע",
    "Broken": "הטרייד נכשל",
    "ALGO Guard": "בקרת אלגו",
}

def classify_position_state(features, status, stage, total_r, current_stop, entry_price, mgt_state, days_held, setup_type, hard_rule=None):
    setup = str(setup_type).upper()
    close = float(features.get("close", 0) or 0)
    ma20 = features.get("ma20")
    ma50 = features.get("ma50")
    stretch = features.get("stretch_ma20_atr")
    violations = []

    if current_stop and current_stop > 0 and close > 0 and close <= current_stop:
        violations.append("סטופ נחצה")
    if features.get("consecutive_below_ma20"):
        violations.append("שתי סגירות מתחת MA20")
    elif features.get("close_below_ma20"):
        violations.append("סגירה מתחת MA20")
    if features.get("close_below_ma50"):
        violations.append("סגירה מתחת MA50")
    if features.get("bad_closes_10", 0) > features.get("good_closes_10", 0):
        violations.append("יותר סגירות חלשות מחזקות")
    if features.get("dist_12d", 0) >= 3:
        violations.append("3 ימי פיזור ב-12 ימים")
    elif features.get("dist_8d", 0) >= 2:
        violations.append("2 ימי פיזור ב-8 ימים")
    if features.get("lower_lows_3"):
        violations.append("רצף שפלים יורדים")
    if features.get("time_efficiency") == "dead_money":
        violations.append("אין התקדמות מספקת בזמן")
    if days_held >= 5 and total_r < 0.5 and setup != "ALGO":
        violations.append("אין Follow-through מספיק אחרי הכניסה")

    hard_rule_name = hard_rule.get("rule") if hard_rule else None
    is_climactic = status == "⚠️ Climactic" or (stretch is not None and stretch > 3.0)
    violation_count = len(violations)

    if setup == "ALGO":
        state = "ALGO Guard"
    elif hard_rule_name in ("stop_breach", "heavy_distribution", "runner_ma20_break") or status == "🚨 קריטי":
        state = "Broken"
    elif is_climactic:
        state = "Climactic"
    elif violation_count >= 3:
        state = "Violation"
    elif status == "🔴 Broken":
        state = "Broken"
    elif features.get("time_efficiency") == "dead_money":
        state = "Dead Money"
    elif total_r >= 3.0:
        state = "Profit Protect"
    elif total_r >= 2.0:
        state = "Breakeven Protect"
    elif days_held <= 3:
        state = "New Entry"
    elif total_r >= 0.5 and violation_count == 0:
        state = "Working"
    elif total_r >= 0.5 and features.get("close_below_ma20") is False and features.get("bad_closes_10", 0) <= features.get("good_closes_10", 0):
        state = "Tennis Ball"
    elif days_held <= 7 and total_r < 0.5 and violation_count <= 1:
        state = "Squat Watch"
    else:
        state = "Working" if violation_count <= 1 else "Violation"

    if state == "Broken":
        preferred_action = "לצאת ללא ויכוח / לסגור בברוקר"
        priority = "קריטי"
    elif state == "Violation":
        preferred_action = "לא להוסיף. להפחית חצי או לצאת אם אין התאוששות מהירה"
        priority = "גבוה"
    elif state == "Dead Money":
        preferred_action = "לשקול שחרור הון אם אין טריגר ברור להמשך"
        priority = "בינוני"
    elif state == "Climactic":
        preferred_action = "מכירה לחוזק או הידוק סטופ"
        priority = "גבוה"
    elif state == "Profit Protect":
        preferred_action = "להגן על רווח: מימוש חלקי או סטופ נגרר"
        priority = "גבוה"
    elif state == "Breakeven Protect":
        preferred_action = "לקדם סטופ לאזור כניסה / סיכון אפס"
        priority = "בינוני"
    elif state == "Squat Watch":
        preferred_action = "לתת זמן מוגבל בלבד. לא להוסיף עד Follow-through"
        priority = "בינוני"
    elif state == "Tennis Ball":
        preferred_action = "אפשר להחזיק כל עוד ההתאוששות מחזיקה"
        priority = "נמוך"
    elif state == "ALGO Guard":
        preferred_action = "ניהול לפי מגבלות חשיפה וסיכון אלגו"
        priority = "לפי חשיפה"
    else:
        preferred_action = "להחזיק ולעקוב"
        priority = "נמוך"

    if violation_count >= 3:
        summary = "הטרייד לא עומד בציפיות. יש {} הפרות: {}.".format(violation_count, ", ".join(violations[:4]))
    elif violation_count > 0:
        summary = "יש {} סימני אזהרה: {}.".format(violation_count, ", ".join(violations[:3]))
    else:
        summary = "אין הפרות ניהול משמעותיות כרגע."

    return {
        "state": state,
        "state_he": POSITION_STATE_HE.get(state, state),
        "violation_count": violation_count,
        "violations": violations,
        "preferred_action": preferred_action,
        "decision_priority": priority,
        "decision_summary": summary,
    }


def _evaluate_position_engine_base(symbol, entry_price, entry_date_str, current_stop, setup_type, mgt_state, weight_pct, total_r, target_risk_usd=0, actual_risk_usd=0, spy_hist=None):
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
            state_card = classify_position_state(features, hard_rule["status"], stage, total_r, current_stop, entry_price, mgt_state, days_held, setup_type, hard_rule)
            return {"ok": True, "error": None, "data": {"status": hard_rule["status"], "sizing_status": sizing_status, "issues": issues, "action": action, "trigger": hard_rule["trigger"], "suggested_stop": current_stop, "score": None, "stage": stage, "features": features, "position_state": state_card["state"], "state_he": state_card["state_he"], "violation_count": state_card["violation_count"], "violations": state_card["violations"], "preferred_action": state_card["preferred_action"], "decision_priority": state_card["decision_priority"], "decision_summary": state_card["decision_summary"]}}
        
        score = score_position(features, stage)
        status = map_score_to_status(score, features=features)
        action, trigger, suggested_stop = build_management_action(status, features, stage, current_stop, total_r, mgt_state)
        
        state_card = classify_position_state(features, status, stage, total_r, current_stop, entry_price, mgt_state, days_held, setup_type, None)
        return {"ok": True, "error": None, "data": {"status": status, "sizing_status": sizing_status, "issues": issues, "action": action, "trigger": trigger, "suggested_stop": suggested_stop, "score": score, "stage": stage, "features": features, "position_state": state_card["state"], "state_he": state_card["state_he"], "violation_count": state_card["violation_count"], "violations": state_card["violations"], "preferred_action": state_card["preferred_action"], "decision_priority": state_card["decision_priority"], "decision_summary": state_card["decision_summary"]}}
    except Exception as e: return {"ok": False, "error": str(e), "data": None}


def _decision_reason_line(text, reasons):
    if text and text not in reasons:
        reasons.append(text)

def build_decision_card_v1(symbol, setup_type, mgt_state, total_r, current_stop, entry_price, engine_data):
    features = engine_data.get("features", {}) or {}
    status = engine_data.get("status", "")
    state = engine_data.get("position_state", "")
    state_he = engine_data.get("state_he") or state
    violations = list(engine_data.get("violations") or [])
    violation_count = int(engine_data.get("violation_count", 0) or 0)

    close = float(features.get("close", 0) or 0)
    ma10 = features.get("ma10")
    ma20 = features.get("ma20")
    stretch = features.get("stretch_ma20_atr")
    bad = int(features.get("bad_closes_10", 0) or 0)
    good = int(features.get("good_closes_10", 0) or 0)
    dist_12d = int(features.get("dist_12d", 0) or 0)
    lower_lows = bool(features.get("lower_lows_3"))

    reasons = []
    alternatives = []
    consequence = ""
    bias = "HOLD"
    bias_he = "החזקה / מעקב"
    primary_action = "להחזיק ולעקוב לפי התוכנית"
    urgency = "נמוכה"
    protection_stage = "מעקב"

    if current_stop and current_stop > 0 and close > 0 and close <= current_stop:
        bias = "SELL_WEAKNESS"
        bias_he = "מכירה לחולשה"
        primary_action = "הסטופ נחצה: לסגור בברוקר ללא ויכוח"
        urgency = "קריטית"
        protection_stage = "כשלון טרייד"
        _decision_reason_line("המחיר הנוכחי מתחת/שווה לסטופ", reasons)
        consequence = "אי פעולה משאירה פוזיציה אחרי שבירת כלל ההגנה."
    elif status in ("🚨 קריטי", "🔴 Broken") or state == "Broken":
        bias = "SELL_WEAKNESS"
        bias_he = "מכירה לחולשה"
        primary_action = "לצאת או להפחית משמעותית לפי הכללים"
        urgency = "גבוהה"
        protection_stage = "כשלון טרייד"
        _decision_reason_line("המנוע מסמן שבירת מבנה", reasons)
        consequence = "המתנה עלולה להפוך הפסד/רווח מוגן לנזק גדול יותר."
    elif violation_count >= 3:
        bias = "SELL_WEAKNESS"
        bias_he = "מכירה לחולשה"
        primary_action = "הטרייד לא עומד בציפיות: להפחית חצי או לצאת"
        urgency = "גבוהה"
        protection_stage = "הפרות ניהול"
        _decision_reason_line("{} הפרות ניהול".format(violation_count), reasons)
        consequence = "כשיש כמה הפרות יחד, לא מחכים לנס."
    elif status == "⚠️ Climactic" or state == "Climactic" or (stretch is not None and stretch >= 3.0):
        bias = "SELL_STRENGTH"
        bias_he = "מכירה לחוזק"
        primary_action = "מהלך מתוח: מימוש חלקי 25%-50% או הידוק סטופ"
        urgency = "גבוהה"
        protection_stage = "Climactic"
        if stretch is not None:
            _decision_reason_line("מתיחה של {:.1f} ATR מעל MA20".format(stretch), reasons)
        else:
            _decision_reason_line("המניה מתוחה אחרי מהלך חד", reasons)
        alternatives = ["מימוש חלקי", "הידוק סטופ ל-MA10/Back Stop", "החזקה רק אם יש תוכנית Runner"]
        consequence = "אי נעילת רווח עלולה להחזיר חלק גדול מהמהלך."
    elif total_r >= 3.0:
        bias = "SELL_STRENGTH"
        bias_he = "מכירה לחוזק"
        primary_action = "מעל 3R: לשקול מימוש 25%-50% או סטופ נגרר"
        urgency = "בינונית-גבוהה"
        protection_stage = "Profit Protect"
        _decision_reason_line("הפוזיציה מעל 3R", reasons)
        alternatives = ["מימוש חלקי", "סטופ נגרר", "Runner Mode אחרי מימוש"]
        consequence = "רווח גדול בלי הגנה יכול להימחק בתיקון רגיל."
    elif total_r >= 2.0:
        bias = "PROTECT"
        bias_he = "הגנת רווח"
        primary_action = "מעל 2R: לקדם סטופ לאזור כניסה / סיכון אפס"
        urgency = "בינונית"
        protection_stage = "Breakeven Protect"
        _decision_reason_line("הפוזיציה מעל 2R", reasons)
        alternatives = ["קידום סטופ", "החזקה אם המבנה חזק", "מימוש קטן רק אם יש חולשה"]
        consequence = "אחרי 2R לא נותנים לטרייד טוב להפוך להפסד."
    elif state == "Dead Money":
        bias = "ROTATE"
        bias_he = "שחרור הון"
        primary_action = "הון תקוע: לשקול יציאה אם אין טריגר ברור"
        urgency = "בינונית"
        protection_stage = "Time Stop"
        _decision_reason_line("אין התקדמות מספקת בזמן", reasons)
        consequence = "הון תקוע מפחית יכולת לנצל הזדמנויות טובות יותר."
    elif state == "Squat Watch":
        bias = "WATCH"
        bias_he = "מעקב מוגבל"
        primary_action = "לתת זמן מוגבל, לא להוסיף עד Follow-through"
        urgency = "בינונית"
        protection_stage = "בדיקת המשכיות"
        _decision_reason_line("עדיין אין הוכחת המשכיות מספקת", reasons)
        consequence = "תוספת מוקדמת לפני אישור מגדילה סיכון בלי יתרון."
    elif state == "Tennis Ball":
        bias = "HOLD"
        bias_he = "החזקה"
        primary_action = "התאוששות טובה: אפשר להחזיק כל עוד MA20/סטופ נשמרים"
        urgency = "נמוכה"
        protection_stage = "Working"
        _decision_reason_line("התאוששות לאחר Pullback", reasons)
    else:
        if bad > good:
            _decision_reason_line("יותר סגירות חלשות מחזקות", reasons)
        if dist_12d >= 2:
            _decision_reason_line("{} ימי פיזור ב-12 ימים".format(dist_12d), reasons)
        if lower_lows:
            _decision_reason_line("רצף שפלים יורדים", reasons)
        if not reasons:
            _decision_reason_line("אין סימן חריג שמחייב פעולה מיידית", reasons)

    if not alternatives:
        alternatives = ["פעולה לפי הכללים", "החזקה רק אם הסטופ והתוכנית נשמרים"]

    return {
        "symbol": symbol,
        "bias": bias,
        "bias_he": bias_he,
        "primary_action": primary_action,
        "urgency": urgency,
        "protection_stage": protection_stage,
        "reasons": reasons[:4],
        "alternatives": alternatives[:4],
        "consequence": consequence,
        "state": state,
        "state_he": state_he,
        "violation_count": violation_count,
    }

def evaluate_position_engine(symbol, entry_price, entry_date_str, current_stop, setup_type, mgt_state, weight_pct, total_r, target_risk_usd=0, actual_risk_usd=0, spy_hist=None):
    res = _evaluate_position_engine_base(
        symbol=symbol,
        entry_price=entry_price,
        entry_date_str=entry_date_str,
        current_stop=current_stop,
        setup_type=setup_type,
        mgt_state=mgt_state,
        weight_pct=weight_pct,
        total_r=total_r,
        target_risk_usd=target_risk_usd,
        actual_risk_usd=actual_risk_usd,
        spy_hist=spy_hist,
    )
    try:
        if not res.get("ok") or not res.get("data"):
            return res
        data = res["data"]
        card = build_decision_card_v1(symbol, setup_type, mgt_state, total_r, current_stop, entry_price, data)
        data["decision_card"] = card
        data["profit_engine"] = {
            "bias": card["bias"],
            "bias_he": card["bias_he"],
            "primary_action": card["primary_action"],
            "protection_stage": card["protection_stage"],
            "urgency": card["urgency"],
        }

        if card.get("bias") in ("SELL_WEAKNESS", "SELL_STRENGTH", "PROTECT", "ROTATE"):
            data["preferred_action"] = card["primary_action"]

        return res
    except Exception as e:
        try:
            res["data"]["decision_card_error"] = str(e)
        except Exception:
            pass
        return res



def enrich_risk_governor_with_performance(gov, perf_summary):
    try:
        if not gov or not isinstance(gov, dict) or not gov.get("ok"):
            return gov
        if not perf_summary or not perf_summary.get("ok"):
            return gov

        data = gov.get("data", {})
        w10 = perf_summary["windows"]["10"]
        w20 = perf_summary["windows"]["20"]
        w50 = perf_summary["windows"]["50"]

        exp10 = float(w10.get("expectancy", 0) or 0)
        exp20 = float(w20.get("expectancy", 0) or 0)
        exp50 = float(w50.get("expectancy", 0) or 0)
        win20 = float(w20.get("win_rate", 0) or 0)
        pf20 = float(w20.get("profit_factor", 0) or 0)
        payoff20 = float(w20.get("payoff", 0) or 0)
        streak = int(w20.get("loss_streak", 0) or 0)
        dd20 = float(w20.get("max_drawdown_r", 0) or 0)

        perf_lines = [
            "Exp10 {:+.2f}R | Exp20 {:+.2f}R | Exp50 {:+.2f}R".format(exp10, exp20, exp50),
            "Win20 {:.0f}% | PF20 {:.2f} | Payoff20 {:.2f}".format(win20, pf20, payoff20),
            "Loss Streak {} | MaxDD20 {:.1f}R".format(streak, dd20),
        ]

        trend = "mixed"
        if exp10 > exp20 > exp50:
            trend = "improving"
            perf_lines.append("מגמת ביצוע משתפרת: 10 > 20 > 50")
        elif exp10 < exp20 < exp50:
            trend = "deteriorating"
            perf_lines.append("מגמת ביצוע נחלשת: 10 < 20 < 50")
        else:
            perf_lines.append("מגמת ביצוע מעורבת")

        performance_grade = "neutral"
        if exp20 > 0.35 and pf20 >= 1.5 and streak <= 1:
            performance_grade = "strong"
        elif exp20 > 0 and pf20 >= 1.1 and streak <= 2:
            performance_grade = "positive_mixed"
        elif exp20 < 0 or pf20 < 1.0 or streak >= 3:
            performance_grade = "weak"

        data["performance_bridge"] = {
            "exp10": exp10,
            "exp20": exp20,
            "exp50": exp50,
            "win20": win20,
            "profit_factor20": pf20,
            "payoff20": payoff20,
            "loss_streak20": streak,
            "max_dd20": dd20,
            "trend": trend,
            "grade": performance_grade,
            "lines": perf_lines,
        }

        existing_reason = str(data.get("reason", "") or "")

        # Conservative override: do not allow AGGRESSIVE when performance is not clean.
        mode = str(data.get("mode", "") or "").upper()
        allowed_risk = float(data.get("allowed_risk_pct", 0) or 0)
        allowed_exposure = float(data.get("allowed_exposure_pct", 0) or 0)

        if performance_grade == "weak":
            if allowed_risk > 0.35:
                data["allowed_risk_pct"] = 0.35
            if allowed_exposure > 40:
                data["allowed_exposure_pct"] = 40
            data["mode"] = "CAUTION"
            data["reason"] = (existing_reason + " ביצועים חלשים/לא יציבים: הסיכון מוגבל עד שיפור מוכח.").strip()

        elif performance_grade == "positive_mixed":
            if mode in ("AGGRESSIVE", "POWER") or allowed_risk > 0.50:
                data["allowed_risk_pct"] = 0.50
                data["allowed_exposure_pct"] = min(allowed_exposure if allowed_exposure else 60, 60)
                data["mode"] = "NORMAL"
                data["reason"] = (existing_reason + " הביצועים חיוביים אך לא נקיים: לא מעלים מעל סיכון רגיל.").strip()

        elif performance_grade == "strong" and trend == "improving":
            data["reason"] = (existing_reason + " ביצועים אחרונים חזקים ומשתפרים: ניתן לשקול העלאת סיכון רק אם השוק תומך ואין חריגות משמעת.").strip()

        gov["data"] = data
        return gov
    except Exception as e:
        try:
            gov.setdefault("data", {})["performance_bridge_error"] = str(e)
        except Exception:
            pass
        return gov


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

            target_vals = pd.to_numeric(buys["target_risk_usd"], errors="coerce") if "target_risk_usd" in buys.columns else pd.Series(dtype=float)
            target_vals = target_vals[(target_vals > 0) & target_vals.notna()]
            campaign_target_risk = float(target_vals.iloc[0]) if not target_vals.empty else 37.5
            
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
                "target_risk_usd": campaign_target_risk,
            })
        if not open_positions: return {"ok": True, "error": None, "data": pd.DataFrame()}
        return {"ok": True, "error": None, "data": pd.DataFrame(open_positions).sort_values("symbol")}
    except Exception as e: return {"ok": False, "error": str(e), "data": pd.DataFrame()}

def compute_market_regime(spy_hist, qqq_hist=None):
    try:
        if spy_hist is None or len(spy_hist) < 50:
            return {
                "ok": False,
                "error": "no_data",
                "data": {
                    "status": "Unknown",
                    "color": "⚪",
                    "text": "אין מספיק נתונים",
                    "basis": ["אין מספיק היסטוריית SPY לחישוב משטר שוק."]
                }
            }

        spy_close = float(spy_hist["Close"].iloc[-1])
        spy_ma20 = float(spy_hist["Close"].rolling(20).mean().iloc[-1])
        spy_ma50 = float(spy_hist["Close"].rolling(50).mean().iloc[-1])

        score = 0
        max_score = 3
        basis = []

        if spy_close > spy_ma20:
            score += 1
            basis.append(f"SPY מעל MA20 ({spy_close:.1f} מול {spy_ma20:.1f})")
        else:
            basis.append(f"SPY מתחת MA20 ({spy_close:.1f} מול {spy_ma20:.1f})")

        if spy_close > spy_ma50:
            score += 1
            basis.append(f"SPY מעל MA50 ({spy_close:.1f} מול {spy_ma50:.1f})")
        else:
            basis.append(f"SPY מתחת MA50 ({spy_close:.1f} מול {spy_ma50:.1f})")

        if spy_ma20 > spy_ma50:
            score += 1
            basis.append("מגמת SPY חיובית: MA20 מעל MA50")
        else:
            basis.append("מגמת SPY חלשה: MA20 מתחת/שווה MA50")

        qqq_close = qqq_ma20 = None
        if qqq_hist is not None and not qqq_hist.empty and len(qqq_hist) >= 50:
            max_score += 1
            qqq_close = float(qqq_hist["Close"].iloc[-1])
            qqq_ma20 = float(qqq_hist["Close"].rolling(20).mean().iloc[-1])
            if qqq_close > qqq_ma20:
                score += 1
                basis.append(f"QQQ מעל MA20 ({qqq_close:.1f} מול {qqq_ma20:.1f})")
            else:
                basis.append(f"QQQ מתחת MA20 ({qqq_close:.1f} מול {qqq_ma20:.1f})")

        score_pct = score / max_score if max_score else 0

        if score_pct >= 0.75:
            status, color, text = "Hot", "🔥", "שוק שורי חזק - סביבה תומכת"
        elif score_pct >= 0.50:
            status, color, text = "Warm", "🟢", "שוק חיובי - לנהל סיכונים רגיל"
        elif score_pct >= 0.25:
            status, color, text = "Neutral", "🟡", "שוק מדשדש/מעורב - זהירות והקטנת סיכון"
        else:
            status, color, text = "Cold", "🔴", "שוק דובי - סביבה עוינת, הגנה מקסימלית"

        basis.insert(0, f"ניקוד משטר: {score}/{max_score}")

        return {
            "ok": True,
            "error": None,
            "data": {
                "status": status,
                "color": color,
                "text": text,
                "score": score,
                "max_score": max_score,
                "score_pct": score_pct,
                "basis": basis,
                "spy_close": spy_close,
                "spy_ma20": spy_ma20,
                "spy_ma50": spy_ma50,
                "qqq_close": qqq_close,
                "qqq_ma20": qqq_ma20,
            }
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "data": {
                "status": "Unknown",
                "color": "⚪",
                "text": f"שגיאה: {e}",
                "basis": [f"שגיאה בחישוב משטר שוק: {e}"]
            }
        }


def _campaign_target_risk(group, fallback=37.5):
    if "target_risk_usd" not in group.columns:
        return fallback
    vals = pd.to_numeric(group["target_risk_usd"], errors="coerce")
    vals = vals[(vals > 0) & vals.notna()]
    return float(vals.iloc[0]) if not vals.empty else fallback

def _campaign_original_risk(group):
    buys = group[group["side"].astype(str).str.upper() == "BUY"].copy()
    if buys.empty:
        return 0.0
    buys["trade_date_dt"] = pd.to_datetime(buys["trade_date"], errors="coerce")
    first_date = buys["trade_date_dt"].min()
    first_day = buys[buys["trade_date_dt"] == first_date]
    base_qty = float(pd.to_numeric(first_day["quantity"], errors="coerce").fillna(0).sum())
    if base_qty <= 0:
        return 0.0
    prices = pd.to_numeric(first_day["price"], errors="coerce").fillna(0)
    qtys = pd.to_numeric(first_day["quantity"], errors="coerce").fillna(0)
    base_price = float((prices * qtys).sum() / base_qty)

    if "initial_stop" not in first_day.columns:
        return 0.0
    init_vals = pd.to_numeric(first_day["initial_stop"], errors="coerce").fillna(0)
    init_vals = init_vals[(init_vals > 0) & (init_vals < base_price)]
    if init_vals.empty:
        return 0.0
    return float((base_price - float(init_vals.iloc[0])) * base_qty)

def build_closed_campaign_metrics(df, fallback_target_risk=37.5):
    try:
        if df is None or df.empty or "campaign_id" not in df.columns:
            return {"ok": True, "data": {"campaigns": pd.DataFrame(), "count": 0}}

        work = df.copy()
        for col in ["quantity", "price", "pnl_usd", "target_risk_usd", "initial_stop"]:
            if col not in work.columns:
                work[col] = 0
            work[col] = pd.to_numeric(work[col], errors="coerce").fillna(0)

        work["trade_date_dt"] = pd.to_datetime(work["trade_date"], errors="coerce")
        rows = []

        for cid, group in work[work["campaign_id"].notna()].groupby("campaign_id"):
            group = group.sort_values(["trade_date_dt", "trade_id"])
            if group["quantity"].sum() > 0.001:
                continue

            buys = group[group["side"].astype(str).str.upper() == "BUY"]
            sells = group[group["side"].astype(str).str.upper() == "SELL"]
            if buys.empty or sells.empty:
                continue

            setup = str(buys.iloc[0].get("setup_type", sells.iloc[-1].get("setup_type", "Unknown"))).upper()
            pnl = float(sells["pnl_usd"].sum())
            target_risk = _campaign_target_risk(group, fallback_target_risk)
            original_risk = _campaign_original_risk(group)

            portfolio_r = pnl / target_risk if target_risk > 0 else 0.0
            true_r = portfolio_r if setup == "ALGO" or original_risk <= 0 else pnl / original_risk

            rows.append({
                "campaign_id": cid,
                "symbol": buys.iloc[0].get("symbol"),
                "setup_type": setup,
                "close_date": sells["trade_date_dt"].max(),
                "pnl_usd": pnl,
                "portfolio_r": float(portfolio_r),
                "true_r": float(true_r),
                "total_r": float(portfolio_r),
                "target_risk_usd": target_risk,
                "original_risk_usd": original_risk,
            })

        out = pd.DataFrame(rows)
        if not out.empty:
            out = out.sort_values("close_date")
        return {"ok": True, "data": {"campaigns": out, "count": len(out)}}
    except Exception as e:
        return {"ok": False, "error": str(e), "data": {"campaigns": pd.DataFrame(), "count": 0}}

def build_open_campaign_metrics(df, fallback_target_risk=37.5):
    try:
        pos_res = get_open_positions_campaign(df)
        if not pos_res.get("ok") or pos_res["data"].empty:
            return {"ok": True, "data": pd.DataFrame()}

        rows = []
        for _, row in pos_res["data"].iterrows():
            sym = row.get("symbol")
            entry = float(row.get("price") or 0)
            qty = float(row.get("quantity") or 0)
            realized = float(row.get("realized_pnl") or 0)
            target_risk = float(row.get("target_risk_usd") or fallback_target_risk)

            curr = get_live_price(sym)
            if curr is None:
                curr = entry

            open_pnl = (float(curr) - entry) * qty
            total_pnl = open_pnl + realized
            portfolio_r = total_pnl / target_risk if target_risk > 0 else 0.0

            base_price = float(row.get("base_price") or entry)
            base_qty = float(row.get("base_qty") or qty)
            init_sl = float(row.get("initial_stop") or 0)
            original_risk = (base_price - init_sl) * base_qty if init_sl > 0 and init_sl < base_price else 0.0
            setup = str(row.get("setup_type", "Unknown")).upper()
            true_r = portfolio_r if setup == "ALGO" or original_risk <= 0 else total_pnl / original_risk

            rows.append({
                "campaign_id": row.get("campaign_id"),
                "symbol": sym,
                "setup_type": setup,
                "pnl_usd": float(total_pnl),
                "portfolio_r": float(portfolio_r),
                "true_r": float(true_r),
                "target_risk_usd": target_risk,
                "original_risk_usd": original_risk,
            })

        return {"ok": True, "data": pd.DataFrame(rows)}
    except Exception as e:
        return {"ok": False, "error": str(e), "data": pd.DataFrame()}

def _drawdown_stats(r_values):
    vals = pd.Series(r_values, dtype="float64").dropna().reset_index(drop=True)
    if vals.empty:
        return {"current_dd": 0.0, "max_dd": 0.0, "ending_r": 0.0, "peak_r": 0.0}
    equity = pd.concat([pd.Series([0.0]), vals.cumsum()], ignore_index=True)
    peaks = equity.cummax()
    dd = equity - peaks
    return {
        "current_dd": float(dd.iloc[-1]),
        "max_dd": float(dd.min()),
        "ending_r": float(equity.iloc[-1]),
        "peak_r": float(peaks.iloc[-1]),
    }

def compute_risk_governor(df, market_regime_result=None, account_size=0, current_risk_pct=0.5, include_open=True, open_weight=0.50):
    try:
        metrics = build_closed_campaign_metrics(df)
        camp = metrics["data"]["campaigns"] if metrics["ok"] else pd.DataFrame()

        market_status = "Unknown"
        market_color = "⚪"
        if market_regime_result and market_regime_result.get("ok"):
            md = market_regime_result.get("data", {})
            market_status = md.get("status", "Unknown")
            market_color = md.get("color", "⚪")

        base_exposure = {"Hot": 80, "Warm": 60, "Neutral": 40, "Cold": 20}.get(market_status, 40)

        open_df = pd.DataFrame()
        if include_open:
            open_res = build_open_campaign_metrics(df)
            if open_res.get("ok"):
                open_df = open_res["data"]

        open_portfolio_r = float(open_df["portfolio_r"].sum()) if not open_df.empty else 0.0
        open_portfolio_r_weighted = open_portfolio_r * float(open_weight)
        open_campaigns = int(len(open_df)) if not open_df.empty else 0

        if camp.empty:
            allowed = min(float(current_risk_pct), 0.50)
            return {"ok": True, "error": None, "data": {
                "trade_mode": "LEARNING",
                "allowed_risk_pct": allowed,
                "allowed_risk_usd": float(account_size) * allowed / 100 if account_size else 0,
                "allowed_exposure_pct": base_exposure,
                "rolling_expectancy_20": 0.0,
                "rolling_expectancy_10": 0.0,
                "loss_streak": 0,
                "personal_drawdown_r": 0.0,
                "recent_max_drawdown_r": 0.0,
                "all_time_drawdown_r": 0.0,
                "open_portfolio_r": open_portfolio_r,
                "open_portfolio_r_weighted": open_portfolio_r_weighted,
                "open_campaigns": open_campaigns,
                "market_status": market_status,
                "market_color": market_color,
                "risk_basis": "portfolio_r_plus_50pct_open_positions",
                "reason": "אין מספיק קמפיינים סגורים. לא מעלים סיכון עד שיש הוכחת ביצוע."
            }}

        r = camp["portfolio_r"].astype(float)
        last10 = r.tail(10)
        last15 = r.tail(15)
        last20 = r.tail(20)

        rolling_exp_10 = float(last10.mean()) if len(last10) else 0.0
        rolling_exp_20 = float(last20.mean()) if len(last20) else 0.0
        win_rate_15 = float((last15 > 0).mean()) if len(last15) else 0.0

        loss_streak = 0
        for val in reversed(r.tolist()):
            if val < 0:
                loss_streak += 1
            else:
                break

        recent_series = last20.reset_index(drop=True)
        if open_portfolio_r_weighted != 0:
            recent_series = pd.concat([recent_series, pd.Series([open_portfolio_r_weighted])], ignore_index=True)

        all_series = r.reset_index(drop=True)
        if open_portfolio_r_weighted != 0:
            all_series = pd.concat([all_series, pd.Series([open_portfolio_r_weighted])], ignore_index=True)

        recent_stats = _drawdown_stats(recent_series)
        all_stats = _drawdown_stats(all_series)

        recent_current_dd_r = recent_stats["current_dd"]
        recent_max_dd_r = recent_stats["max_dd"]
        all_time_max_dd_r = all_stats["max_dd"]
        all_time_current_dd_r = all_stats["current_dd"]

        allowed_risk = min(float(current_risk_pct), 0.50)
        allowed_exposure = base_exposure
        mode = "NORMAL"
        reasons = []

        strong_recent = rolling_exp_20 > 0.25 and rolling_exp_10 >= 0 and loss_streak == 0 and recent_current_dd_r > -2.0
        severe_current_dd = recent_current_dd_r <= -6.0
        moderate_current_dd = recent_current_dd_r <= -3.0

        if loss_streak >= 5:
            allowed_risk = 0.0
            allowed_exposure = 0.0
            mode = "BLOCKED"
            reasons.append("5 הפסדים רצופים: חסימת טריידים חדשים עד Review.")
        elif severe_current_dd and rolling_exp_20 < 0:
            allowed_risk = 0.25
            allowed_exposure = min(base_exposure, 20)
            mode = "PILOT"
            reasons.append("Drawdown נוכחי חריג וגם Expectancy שלילי: עוברים ל-Pilot.")
        elif severe_current_dd:
            allowed_risk = 0.35
            allowed_exposure = min(base_exposure, 40)
            mode = "REDUCED"
            reasons.append("Drawdown נוכחי עמוק, אבל Expectancy לא שלילי: מורידים סיכון, לא חוסמים.")
        elif loss_streak >= 3 or rolling_exp_20 < 0:
            allowed_risk = 0.35
            allowed_exposure = min(base_exposure, 40)
            mode = "REDUCED"
            reasons.append("רצף הפסדים או Expectancy שלילי: מורידים סיכון.")
        elif market_status == "Cold":
            if strong_recent:
                allowed_risk = 0.50
                allowed_exposure = min(base_exposure, 20)
                mode = "SELECTIVE"
                reasons.append("שוק אדום, אבל הביצוע האישי האחרון חיובי. סיכון רגיל רק ל-A+ וחשיפה נמוכה.")
            else:
                allowed_risk = 0.35
                allowed_exposure = min(base_exposure, 20)
                mode = "REDUCED"
                reasons.append("שוק אדום: מקטינים חשיפה וסיכון, אך לא יורדים ל-Pilot בלי חולשה אישית עדכנית.")
        elif moderate_current_dd:
            allowed_risk = 0.35
            allowed_exposure = min(base_exposure, 40)
            mode = "REDUCED"
            reasons.append("Drawdown נוכחי בינוני בתקופה האחרונה: מורידים הילוך זמנית.")
        elif market_status == "Hot" and len(last15) >= 10 and rolling_exp_20 > 0.35 and rolling_exp_10 > 0.20 and win_rate_15 >= 0.60 and loss_streak == 0 and recent_current_dd_r > -1.0:
            allowed_risk = 0.75
            allowed_exposure = max(base_exposure, 70)
            mode = "EXPANSION"
            reasons.append("שוק חזק וביצוע נקי: מותר להגדיל סיכון בצורה מדודה.")
        elif market_status in ["Hot", "Warm", "Neutral"] and rolling_exp_20 > 0 and loss_streak == 0:
            allowed_risk = 0.50
            allowed_exposure = base_exposure
            mode = "NORMAL"
            reasons.append("Expectancy חיובי ואין רצף הפסדים: סיכון רגיל.")
        else:
            allowed_risk = 0.35
            allowed_exposure = min(base_exposure, 40)
            mode = "CAUTION"
            reasons.append("אין הוכחה מספקת להעלאת סיכון. נשארים שמרניים.")

        allowed_risk_usd = float(account_size) * allowed_risk / 100 if account_size else 0.0
        if mode != "BLOCKED" and 0 < allowed_risk_usd < 30.0:
            allowed_risk = max(allowed_risk, 0.35)
            allowed_risk_usd = float(account_size) * allowed_risk / 100 if account_size else allowed_risk_usd
            reasons.append("עמלת מינימום הופכת סיכון נמוך מדי ללא יעיל; מופעלת רצפת סיכון תפעולית.")

        if recent_max_dd_r <= -6 and recent_current_dd_r > -3 and rolling_exp_20 > 0:
            reasons.append(f"היה MaxDD20 עמוק ({recent_max_dd_r:.1f}R), אבל הניהול מתבסס על DD נוכחי ולא מעניש התאוששות.")
        if all_time_max_dd_r <= -10 and recent_current_dd_r > -3 and rolling_exp_20 > 0:
            reasons.append(f"All-Time MaxDD עדיין עמוק ({all_time_max_dd_r:.1f}R), אבל אינו חוסם כי הביצוע האחרון השתפר.")
        if open_campaigns > 0:
            reasons.append(f"פוזיציות פתוחות נספרות במשקל {open_weight:.0%}: {open_portfolio_r_weighted:.1f}R מתוך {open_portfolio_r:.1f}R פתוח.")

        return {"ok": True, "error": None, "data": {
            "trade_mode": mode,
            "allowed_risk_pct": float(allowed_risk),
            "allowed_risk_usd": float(allowed_risk_usd),
            "allowed_exposure_pct": float(allowed_exposure),
            "rolling_expectancy_20": rolling_exp_20,
            "rolling_expectancy_10": rolling_exp_10,
            "loss_streak": int(loss_streak),
            "personal_drawdown_r": recent_current_dd_r,
            "recent_max_drawdown_r": recent_max_dd_r,
            "all_time_drawdown_r": all_time_max_dd_r,
            "all_time_current_drawdown_r": all_time_current_dd_r,
            "open_portfolio_r": open_portfolio_r,
            "open_portfolio_r_weighted": open_portfolio_r_weighted,
            "open_campaigns": open_campaigns,
            "win_rate_15": win_rate_15,
            "closed_campaigns": int(len(camp)),
            "market_status": market_status,
            "market_color": market_color,
            "risk_basis": "portfolio_r_closed_campaigns_plus_50pct_open_positions",
            "reason": " ".join(reasons)
        }}
    except Exception as e:
        return {"ok": False, "error": str(e), "data": None}

def compute_exposure_governor(df, market_regime_result=None, risk_governor_result=None, account_size=0):
    try:
        market_status = "Unknown"
        market_color = "⚪"
        if market_regime_result and market_regime_result.get("ok"):
            md = market_regime_result.get("data", {})
            market_status = md.get("status", "Unknown")
            market_color = md.get("color", "⚪")

        base_allowed = {"Hot": 80, "Warm": 60, "Neutral": 40, "Cold": 20}.get(market_status, 40)

        risk_mode = "UNKNOWN"
        allowed_exposure = base_allowed
        if risk_governor_result and risk_governor_result.get("ok"):
            gd = risk_governor_result.get("data", {})
            risk_mode = gd.get("trade_mode", "UNKNOWN")
            allowed_exposure = float(gd.get("allowed_exposure_pct", base_allowed) or base_allowed)

        pos_res = get_open_positions_campaign(df)
        if not pos_res.get("ok"):
            return {"ok": False, "error": pos_res.get("error"), "data": None}

        open_pos = pos_res.get("data")
        acc = float(account_size or 0)
        if acc <= 0:
            acc = 1.0

        by_setup = {}
        by_symbol = {}
        total_exposure_usd = 0.0
        algo_exposure_usd = 0.0

        if open_pos is not None and not open_pos.empty:
            for _, row in open_pos.iterrows():
                sym = str(row.get("symbol", "UNKNOWN"))
                setup = str(row.get("setup_type", "OTHER")).upper()
                qty = float(row.get("quantity") or 0)
                entry = float(row.get("price") or 0)
                curr = get_live_price(sym)
                if curr is None:
                    curr = entry

                value = max(float(curr) * qty, 0.0)
                total_exposure_usd += value
                by_setup[setup] = by_setup.get(setup, 0.0) + value
                by_symbol[sym] = by_symbol.get(sym, 0.0) + value

                if setup == "ALGO":
                    algo_exposure_usd += value

        total_exposure_pct = (total_exposure_usd / acc) * 100
        algo_exposure_pct = (algo_exposure_usd / acc) * 100
        utilization_pct = (total_exposure_pct / allowed_exposure) * 100 if allowed_exposure > 0 else 0
        cash_pct = max(0.0, 100.0 - total_exposure_pct)

        by_setup_pct = {k: (v / acc) * 100 for k, v in sorted(by_setup.items())}
        by_symbol_pct = {k: (v / acc) * 100 for k, v in sorted(by_symbol.items())}

        issues = []
        status = "BALANCED"
        severity = "green"
        action = "החשיפה תואמת את המצב. להמשיך לנהל לפי התוכנית."
        reason = "החשיפה הכוללת נמצאת בטווח סביר ביחס למצב השוק ול-Risk Governor."

        if risk_mode == "BLOCKED":
            status = "BLOCKED"
            severity = "red"
            action = "לא לפתוח עסקאות חדשות."
            reason = "Risk Governor חוסם טריידים חדשים, לכן חשיפה חדשה אינה מותרת."
        elif allowed_exposure <= 0:
            status = "CASH_ONLY"
            severity = "red"
            action = "להישאר במזומן או לצמצם חשיפה קיימת."
            reason = "החשיפה המותרת היא אפס."
        elif total_exposure_pct > allowed_exposure + 10:
            status = "OVEREXPOSED"
            severity = "red"
            action = "להפחית חשיפה או להימנע מכניסות חדשות עד חזרה לטווח."
            reason = "החשיפה בפועל גבוהה משמעותית מהחשיפה המותרת."
        elif total_exposure_pct > allowed_exposure:
            status = "FULL"
            severity = "yellow"
            action = "לא להוסיף פוזיציות חדשות בלי צמצום מקביל."
            reason = "החשיפה מלאה או מעט מעל הטווח המותר."
        elif market_status in ["Hot", "Warm"] and risk_mode in ["NORMAL", "EXPANSION"] and total_exposure_pct < min(20.0, allowed_exposure * 0.30):
            status = "UNDEREXPOSED"
            severity = "blue"
            action = "הסביבה תומכת ואתה קל מדי. להכין רשימת A+ ולשקול הגדלה מדודה."
            reason = "השוק תומך, הביצוע מאפשר סיכון רגיל, אך החשיפה נמוכה מאוד."
        elif market_status == "Hot" and risk_mode in ["NORMAL", "EXPANSION"] and total_exposure_pct < allowed_exposure * 0.50:
            status = "LIGHT"
            severity = "blue"
            action = "יש מקום לחשיפה נוספת, רק בסטאפים איכותיים."
            reason = "החשיפה נמוכה ביחס לסביבה תומכת."
        elif market_status in ["Neutral", "Cold"] and total_exposure_pct > allowed_exposure * 0.80:
            status = "CAUTION"
            severity = "yellow"
            action = "להיזהר מהוספת חשיפה. להעדיף ניהול הגנתי."
            reason = "השוק אינו חזק והחשיפה קרובה לתקרה המותרת."

        if algo_exposure_pct > ALGO_CLUSTER_CRITICAL_PCT:
            issues.append("חריגת ALGO קריטית")
            severity = "red"
            status = "ALGO_OVEREXPOSED"
            action = "להפחית חשיפת ALGO לפני כל הגדלה אחרת."
        elif algo_exposure_pct > ALGO_CLUSTER_WARNING_PCT:
            issues.append("חשיפת ALGO גבוהה")
            if severity != "red":
                severity = "yellow"

        return {"ok": True, "error": None, "data": {
            "status": status,
            "severity": severity,
            "market_status": market_status,
            "market_color": market_color,
            "risk_mode": risk_mode,
            "allowed_exposure_pct": float(allowed_exposure),
            "total_exposure_usd": float(total_exposure_usd),
            "total_exposure_pct": float(total_exposure_pct),
            "utilization_pct": float(utilization_pct),
            "cash_pct": float(cash_pct),
            "algo_exposure_pct": float(algo_exposure_pct),
            "by_setup_pct": by_setup_pct,
            "by_symbol_pct": by_symbol_pct,
            "issues": issues,
            "action": action,
            "reason": reason
        }}
    except Exception as e:
        return {"ok": False, "error": str(e), "data": None}

def get_minervini_analysis(symbol):
    try:
        symbol = str(symbol).upper().strip().replace("$", "")
        R = "\u200f"
        L = "\u200e"
        SEP = "━━━━━━━━━━━━"

        def money(v):
            try:
                return f"{L}${float(v):,.2f}{L}"
            except Exception:
                return "N/A"

        def pct(v, signed=False):
            try:
                val = float(v)
                sign = "+" if signed and val > 0 else ""
                return f"{L}{sign}{val:.1f}%{L}"
            except Exception:
                return "N/A"

        def pct_dec(v, signed=True):
            if v is None:
                return "N/A"
            return pct(float(v) * 100, signed=signed)

        def num(v, digits=1):
            try:
                return f"{L}{float(v):.{digits}f}{L}"
            except Exception:
                return "N/A"

        def ok_icon(v):
            return "✅" if bool(v) else "❌"

        hist = get_cached_history(symbol, "1y", "1d")
        if hist is None or hist.empty or len(hist) < 200:
            return {"ok": False, "error": "missing_data", "data": (f"{R}⚠️ אין מספיק היסטוריית מחירים לניתוח {symbol}.", 0)}

        df = compute_indicators(hist)
        df = detect_distribution_days(df)

        close = float(df["Close"].iloc[-1])
        prev_close = float(df["Close"].iloc[-2])
        high = float(df["High"].iloc[-1])
        low = float(df["Low"].iloc[-1])
        volume = float(df["Volume"].iloc[-1])
        ma10 = float(df["MA10"].iloc[-1])
        ma20 = float(df["MA20"].iloc[-1])
        ma50 = float(df["MA50"].iloc[-1])
        ma150 = float(df["MA150"].iloc[-1])
        ma200 = float(df["MA200"].iloc[-1])
        atr20 = float(df["ATR20"].iloc[-1]) if pd.notna(df["ATR20"].iloc[-1]) else 0.0
        atr100 = float(df["ATR100"].iloc[-1]) if pd.notna(df["ATR100"].iloc[-1]) else 0.0
        avg_vol20 = float(df["AvgVol20"].iloc[-1]) if pd.notna(df["AvgVol20"].iloc[-1]) else 0.0
        vol50 = float(df["Volume"].rolling(50).mean().iloc[-1])

        low_52w = float(df["Low"].min())
        high_52w = float(df["High"].max())
        prev_20 = df.iloc[-21:-1] if len(df) >= 21 else df.iloc[:-1]
        pivot_20 = float(prev_20["High"].max()) if not prev_20.empty else high_52w
        low_10 = float(df["Low"].tail(10).min())
        high_10 = float(df["High"].tail(10).max())
        range_10_pct = ((high_10 / low_10) - 1) * 100 if low_10 > 0 else 0

        dist_high_52 = (close / high_52w - 1) * 100 if high_52w > 0 else 0
        dist_low_52 = (close / low_52w - 1) * 100 if low_52w > 0 else 0
        dist_ma20 = (close / ma20 - 1) * 100 if ma20 > 0 else 0
        dist_ma50 = (close / ma50 - 1) * 100 if ma50 > 0 else 0
        stretch_ma20_atr = (close - ma20) / atr20 if atr20 > 0 else None
        atr_pct = (atr20 / close) * 100 if close > 0 and atr20 > 0 else 0
        atr_regime = atr20 / atr100 if atr100 > 0 else 1.0
        vol_ratio20 = volume / avg_vol20 if avg_vol20 > 0 else 0
        vol_ratio50 = volume / vol50 if vol50 > 0 else 0

        stock_ret20 = safe_return(df["Close"], 20)
        stock_ret60 = safe_return(df["Close"], 60)

        spy_hist = get_cached_history("SPY", "1y", "1d")
        qqq_hist = get_cached_history("QQQ", "1y", "1d")
        spy_ret20 = safe_return(spy_hist["Close"], 20) if spy_hist is not None and not spy_hist.empty else None
        spy_ret60 = safe_return(spy_hist["Close"], 60) if spy_hist is not None and not spy_hist.empty else None

        sector_bundle = get_sector_bundle(symbol)
        sector_etf = sector_bundle.get("sector_etf")
        sector_hist = get_cached_history(sector_etf, "1y", "1d") if sector_etf else None
        sector_ret20 = safe_return(sector_hist["Close"], 20) if sector_hist is not None and not sector_hist.empty else None
        sector_ret60 = safe_return(sector_hist["Close"], 60) if sector_hist is not None and not sector_hist.empty else None

        rs20_market = stock_ret20 - spy_ret20 if stock_ret20 is not None and spy_ret20 is not None else None
        rs60_market = stock_ret60 - spy_ret60 if stock_ret60 is not None and spy_ret60 is not None else None
        rs20_sector = stock_ret20 - sector_ret20 if stock_ret20 is not None and sector_ret20 is not None else None
        rs60_sector = stock_ret60 - sector_ret60 if stock_ret60 is not None and sector_ret60 is not None else None

        regime = compute_market_regime(spy_hist, qqq_hist)
        market_line = "לא ידוע"
        if regime.get("ok"):
            rd = regime.get("data", {})
            market_line = f"{rd.get('color', '⚪')} {rd.get('status', 'Unknown')} - {rd.get('text', '')}"

        good_10 = int(df["GoodClose"].tail(10).sum())
        bad_10 = int(df["BadClose"].tail(10).sum())
        accum_10 = int(df["AccumulationDay"].tail(10).sum())
        dist_12 = int(df["DistributionDay"].tail(12).sum())

        last10 = df.tail(10)
        up_vol = float(last10[last10["Close"] >= last10["Open"]]["Volume"].sum())
        down_vol = float(last10[last10["Close"] < last10["Open"]]["Volume"].sum())
        up_down_vol = up_vol / down_vol if down_vol > 0 else None

        r1 = close > ma150 and close > ma200
        r2 = ma150 > ma200
        r3 = ma200 > float(df["MA200"].iloc[-21]) if len(df) > 220 and pd.notna(df["MA200"].iloc[-21]) else False
        r4 = ma50 > ma150 and ma50 > ma200
        r5 = close > ma50
        r6 = close >= low_52w * 1.30
        r7 = close >= high_52w * 0.75
        template_pass = sum([r1, r2, r3, r4, r5, r6, r7])
        template_score = int(round((template_pass / 7) * 10))

        candidates = []
        for lvl in [ma20, low_10, ma50]:
            if lvl and lvl > 0 and lvl < close:
                candidates.append(lvl)
        invalidation = max(candidates) if candidates else close * 0.94
        risk_pct = ((close - invalidation) / close) * 100 if close > 0 else 0
        trigger_gap = ((pivot_20 / close) - 1) * 100 if close > 0 else 0

        extended = (stretch_ma20_atr is not None and stretch_ma20_atr >= 2.8) or dist_ma50 >= 15
        very_extended = (stretch_ma20_atr is not None and stretch_ma20_atr >= 3.5) or dist_ma50 >= 22
        leadership = (rs20_market is not None and rs20_market > 0) and (rs60_market is not None and rs60_market > 0)
        clean_behavior = good_10 >= bad_10 and dist_12 <= 1
        near_pivot = trigger_gap >= -2.0 and trigger_gap <= 3.5
        tight_enough = range_10_pct <= max(8.0, atr_pct * 3.0)

        score100 = 0
        score100 += template_pass / 7 * 30
        score100 += 20 if leadership else (10 if rs20_market is not None and rs20_market > 0 else 0)
        score100 += 15 if clean_behavior else 5
        score100 += 10 if accum_10 >= dist_12 else 4
        score100 += 10 if not extended else 2
        score100 += 10 if near_pivot else 4
        score100 += 5 if tight_enough else 0
        score100 = int(max(0, min(100, round(score100))))

        edge = []
        warnings = []

        if leadership:
            edge.append("מובילה את השוק גם בטווח 20 וגם 60 ימי מסחר")
        elif rs20_market is not None and rs20_market > 0:
            edge.append("מובילה את השוק בטווח קצר")
        else:
            warnings.append("אין הובלה ברורה מול SPY")

        if sector_etf and rs20_sector is not None:
            if rs20_sector > 0:
                edge.append(f"מובילה גם מול הסקטור ({sector_etf})")
            else:
                warnings.append(f"חלשה מול הסקטור ({sector_etf})")

        if good_10 > bad_10:
            edge.append(f"סגירות חזקות עדיפות: {good_10} מול {bad_10}")
        elif bad_10 > good_10:
            warnings.append(f"יותר סגירות חלשות מחזקות: {bad_10} מול {good_10}")

        if accum_10 > 0:
            edge.append(f"{accum_10} ימי איסוף ב-10 ימים")
        if dist_12 >= 2:
            warnings.append(f"{dist_12} ימי פיזור ב-12 ימים")

        if vol_ratio20 < 0.75 and close >= prev_close:
            edge.append("ייבוש מחזורים תוך שמירה על מחיר")
        elif vol_ratio20 > 1.5 and close < prev_close:
            warnings.append("ירידה במחזור גבוה מהממוצע")

        if very_extended:
            warnings.append("המניה מתוחה מאוד - לא לרדוף")
        elif extended:
            warnings.append("המניה מעט מתוחה, עדיף כניסה רק בטריגר איכותי")

        if risk_pct > 8:
            warnings.append(f"סיכון טכני רחב יחסית ({risk_pct:.1f}%)")
        elif risk_pct <= 4:
            edge.append(f"קו פסילה קרוב יחסית ({risk_pct:.1f}%)")

        if atr_regime >= 1.4:
            warnings.append("תנודתיות מתרחבת - ניהול גודל פוזיציה בזהירות")

        if template_score >= 8 and leadership and clean_behavior and not extended:
            verdict = "ראויה למעקב פעיל"
            action = "אפשר לעקוב לכניסה רק מעל טריגר ברור ובנפח תומך"
        elif template_score >= 8 and leadership and extended:
            verdict = "חזקה אבל מתוחה"
            action = "לא לרדוף. להמתין להתכנסות / Pullback / בסיס חדש"
        elif template_score >= 7 and clean_behavior:
            verdict = "מעניינת אך לא מושלמת"
            action = "להכניס ל-Watchlist, לא לפעול בלי אישור מחיר ונפח"
        else:
            verdict = "לא מספיק נקייה כרגע"
            action = "אין יתרון ברור. להמתין לשיפור מבנה או לוותר"

        if close >= pivot_20:
            trigger_text = f"כבר מעל שיא 20 ימים ({money(pivot_20)}). לא לרדוף בלי בסיס תוך-יומי"
        else:
            trigger_text = f"מעל {money(pivot_20)} ({pct(trigger_gap)} מעל המחיר)"

        if not edge:
            edge.append("אין יתרון חריג מעבר לצ׳קליסט המגמה")

        report = f"{R}🔬 *מודיעין מניה - {symbol}*\n{R}{SEP}\n\n"
        report += f"{R}*שורה תחתונה*\n"
        report += f"• מסקנה: *{verdict}*\n"
        report += f"• פעולה: {action}\n"
        report += f"• ציון Sentinel: `{score100}/100` | Trend Template: `{template_score}/10`\n"
        report += f"• משטר שוק: {market_line}\n\n"

        report += f"{R}*מחיר ומבנה*\n"
        report += f"• מחיר: {money(close)} | שינוי יומי: {pct((close / prev_close - 1) * 100, signed=True)}\n"
        report += f"• מול שיא 52ש: {pct(dist_high_52, signed=True)} | מעל שפל 52ש: {pct(dist_low_52)}\n"
        report += f"• MA20: {money(ma20)} ({pct(dist_ma20, signed=True)}) | MA50: {money(ma50)} ({pct(dist_ma50, signed=True)})\n"
        report += f"• מתיחות: `{num(stretch_ma20_atr, 1)} ATR` מעל MA20 | ATR20: `{pct(atr_pct)}`\n\n"

        report += f"{R}*יתרון יחסי*\n"
        report += f"• מול SPY: 20 ימים {pct_dec(rs20_market)} | 60 ימים {pct_dec(rs60_market)}\n"
        if sector_etf:
            report += f"• מול סקטור {sector_etf}: 20 ימים {pct_dec(rs20_sector)} | 60 ימים {pct_dec(rs60_sector)}\n"
        else:
            report += f"• סקטור: לא זוהה ETF סקטוריאלי\n"
        report += f"• סקטור/תעשייה: {sector_bundle.get('sector') or 'N/A'} / {sector_bundle.get('industry') or 'N/A'}\n\n"

        report += f"{R}*התנהגות ונפח*\n"
        report += f"• סגירות חזקות/חלשות 10 ימים: `{good_10}` / `{bad_10}`\n"
        report += f"• איסוף 10 ימים: `{accum_10}` | פיזור 12 ימים: `{dist_12}`\n"
        report += f"• נפח היום מול ממוצע 20: `{num(vol_ratio20, 2)}x` | מול 50: `{num(vol_ratio50, 2)}x`\n"
        if up_down_vol is not None:
            report += f"• יחס נפח בימים ירוקים/אדומים 10 ימים: `{num(up_down_vol, 2)}x`\n"
        report += f"• טווח 10 ימים: `{pct(range_10_pct)}` {'(יחסית הדוק)' if tight_enough else '(עדיין רחב)'}\n\n"

        report += f"{R}*רמות עבודה*\n"
        report += f"• טריגר אפשרי: {trigger_text}\n"
        report += f"• קו פסילה ראשוני: {money(invalidation)}\n"
        report += f"• סיכון טכני מהמחיר לפסילה: `{pct(risk_pct)}`\n"
        report += f"• קריאה מעשית: {'כניסה יעילה רק אם הסיכון נשאר נשלט' if risk_pct <= 8 else 'המרחק לסטופ רחב - צריך גודל קטן או כניסה טובה יותר'}\n\n"

        report += f"{R}*מה נותן יתרון*\n"
        for item in edge[:5]:
            report += f"• {item}\n"

        report += f"\n{R}*נורות אזהרה*\n"
        if warnings:
            for item in warnings[:6]:
                report += f"• {item}\n"
        else:
            report += "• אין נורת אזהרה חריגה כרגע\n"

        report += f"\n{R}*Trend Template*\n"
        report += f"{ok_icon(r1)} מחיר מעל MA150 ו-MA200\n"
        report += f"{ok_icon(r2)} MA150 מעל MA200\n"
        report += f"{ok_icon(r3)} MA200 במגמת עלייה\n"
        report += f"{ok_icon(r4)} MA50 מעל MA150 ו-MA200\n"
        report += f"{ok_icon(r5)} מחיר מעל MA50\n"
        report += f"{ok_icon(r6)} מעל 30% משפל 52 שבועות\n"
        report += f"{ok_icon(r7)} בטווח 25% משיא 52 שבועות\n"

        return {"ok": True, "error": None, "data": (report, template_score)}

    except Exception as e:
        return {"ok": False, "error": str(e), "data": ("❌ תקלה בשאיבת מודיעין מניה", 0)}

# --- BEGIN Sentinel concrete actions inline patch 2026-05-04 ---
def _sentinel_num(v, default=None):
    try:
        if v is None or pd.isna(v):
            return default
        x = float(v)
        if x != x or x in (float("inf"), float("-inf")):
            return default
        return x
    except Exception:
        return default

def classify_position_age(days_held):
    d = int(days_held or 0)
    if d <= 3:
        return {"key": "entry_validation", "label": "0-3 ימים: Entry validation", "days_left": max(0, 3 - d)}
    if d <= 10:
        return {"key": "follow_through", "label": "4-10 ימים: Follow-through window", "days_left": max(0, 10 - d)}
    if d <= 20:
        return {"key": "time_efficiency", "label": "11-20 ימים: Time efficiency", "days_left": max(0, 20 - d)}
    return {"key": "mature_runner", "label": "21+ ימים: Mature / Runner evaluation", "days_left": 0}

def _sentinel_money(v):
    x = _sentinel_num(v)
    return "N/A" if x is None else "${:,.2f}".format(x)

def _sentinel_qty(v):
    x = _sentinel_num(v, 0.0) or 0.0
    return str(int(round(x))) if abs(x - round(x)) < 0.0001 else "{:.2f}".format(x).rstrip("0").rstrip(".")

def _sentinel_valid_stop(v, close):
    x = _sentinel_num(v)
    c = _sentinel_num(close)
    if x is None or x <= 0:
        return None
    if c and c > 0 and x >= c:
        return None
    return x

def _sentinel_stop_candidate(features, current_stop, entry_price, prefer="max"):
    close = _sentinel_num(features.get("close"))
    current = _sentinel_valid_stop(current_stop, close) or 0.0
    entry = _sentinel_valid_stop(entry_price, close)
    ma10 = _sentinel_valid_stop(features.get("ma10"), close)
    ma20 = _sentinel_valid_stop(features.get("ma20"), close)
    candidates = []
    if current > 0:
        candidates.append(("סטופ נוכחי", current))
    if entry is not None:
        candidates.append(("כניסה / סיכון אפס", entry))
    if prefer in ("sma10", "tight", "max") and ma10 is not None:
        candidates.append(("SMA10", ma10))
    if prefer in ("sma20", "normal", "max") and ma20 is not None:
        candidates.append(("SMA20", ma20))
    if not candidates:
        return None, None
    return max(candidates, key=lambda x: x[1])

def _sentinel_partial(quantity, pct):
    qty = _sentinel_num(quantity, 0.0) or 0.0
    if qty <= 0:
        return None, "חסרה כמות פתוחה; לא שולח מימוש חלקי אוטומטי."
    if qty < 2:
        return None, "לא לממש חלקית כי הכמות היא {}.".format(_sentinel_qty(qty))
    sell_qty = max(1.0, round(qty * (float(pct) / 100.0)))
    if sell_qty >= qty:
        sell_qty = max(1.0, qty - 1.0)
    actual_pct = (sell_qty / qty) * 100.0
    if abs(actual_pct - pct) <= 4:
        return sell_qty, "לממש {}% מהפוזיציה ({} מתוך {})".format(int(pct), _sentinel_qty(sell_qty), _sentinel_qty(qty))
    return sell_qty, "לממש {} מתוך {} מניות (~{:.0f}% בפועל)".format(_sentinel_qty(sell_qty), _sentinel_qty(qty), actual_pct)

def _sentinel_stop_text(label, value, current_stop):
    if value is None:
        return "סטופ: חסר נתון תקין, לעדכן ידנית לפני החלטה נוספת"
    cur = _sentinel_num(current_stop, 0.0) or 0.0
    if cur > 0 and abs(float(value) - cur) < 0.01:
        return "סטופ: להשאיר {} ({})".format(_sentinel_money(value), label)
    return "לקדם סטופ ל-{}: {}".format(label, _sentinel_money(value))

def build_concrete_trade_action(symbol, setup_type, mgt_state, total_r, current_stop, entry_price, engine_data, quantity=0):
    features = engine_data.get("features", {}) or {}
    state = engine_data.get("position_state", "")
    status = engine_data.get("status", "")
    days_held = int(engine_data.get("days_held", 0) or 0)
    age = classify_position_age(days_held)
    violation_count = int(engine_data.get("violation_count", 0) or 0)
    close = _sentinel_num(features.get("close"), 0.0) or 0.0
    total_r = _sentinel_num(total_r, 0.0) or 0.0
    current_stop = _sentinel_num(current_stop, 0.0) or 0.0
    entry_price = _sentinel_num(entry_price, 0.0) or 0.0
    setup = str(setup_type or "").upper()
    qty = _sentinel_num(quantity, 0.0) or 0.0

    if setup == "ALGO":
        limit = ALGO_SYMBOL_LIMITS.get(str(symbol).upper(), 100.0)
        action = "ניהול ALGO: לא להוסיף. אם החשיפה מעל {:.1f}% בסימול, להפחית עד התקרה.".format(limit)
        return {"primary_action": action, "suggested_stop": current_stop, "stop_rule": "ALGO", "partial_pct": None, "age_bucket": age}

    if current_stop and close and close <= current_stop:
        return {"primary_action": "יציאה מלאה עכשיו: המחיר {} מתחת/שווה לסטופ {}.".format(_sentinel_money(close), _sentinel_money(current_stop)), "suggested_stop": current_stop, "stop_rule": "stop_hit", "partial_pct": 100, "age_bucket": age}

    if state == "Broken" or status in ("🚨 קריטי", "🔴 Broken"):
        action = "לסגור את יתרת ה-Runner; המבנה נשבר אחרי מימוש." if mgt_state == "runner_mode" else "יציאה מלאה לפי התוכנית; המבנה נשבר."
        return {"primary_action": action, "suggested_stop": current_stop, "stop_rule": "broken_structure", "partial_pct": 100, "age_bucket": age}

    if violation_count >= 3:
        _, part = _sentinel_partial(qty, 50)
        label, stop = _sentinel_stop_candidate(features, current_stop, entry_price, "max")
        return {"primary_action": "{}; {}.".format(part, _sentinel_stop_text(label, stop, current_stop)), "suggested_stop": stop or current_stop, "stop_rule": label, "partial_pct": 50, "age_bucket": age}

    if state == "Climactic" or status == "⚠️ Climactic":
        pct = 50 if total_r >= 3.5 or age["key"] in ("time_efficiency", "mature_runner") else 25
        _, part = _sentinel_partial(qty, pct)
        label, stop = _sentinel_stop_candidate(features, current_stop, entry_price, "sma10")
        return {"primary_action": "{}; {}.".format(part, _sentinel_stop_text(label, stop, current_stop)), "suggested_stop": stop or current_stop, "stop_rule": label, "partial_pct": pct, "age_bucket": age}

    if total_r >= 3.0:
        pct = 50 if total_r >= 4.0 or age["key"] in ("time_efficiency", "mature_runner") else 25
        _, part = _sentinel_partial(qty, pct)
        label, stop = _sentinel_stop_candidate(features, current_stop, entry_price, "sma10")
        return {"primary_action": "{}; {}.".format(part, _sentinel_stop_text(label, stop, current_stop)), "suggested_stop": stop or current_stop, "stop_rule": label, "partial_pct": pct, "age_bucket": age}

    if total_r >= 2.0:
        label, stop = _sentinel_stop_candidate(features, current_stop, entry_price, "max")
        return {"primary_action": "{}; לא לממש כרגע אלא אם מופיעה חולשה נוספת.".format(_sentinel_stop_text(label, stop, current_stop)), "suggested_stop": stop or current_stop, "stop_rule": label, "partial_pct": None, "age_bucket": age}

    if state == "Dead Money" or (age["key"] in ("time_efficiency", "mature_runner") and total_r < 1.0):
        _, part = _sentinel_partial(qty, 50)
        return {"primary_action": "{}; אם אין טריגר חדש עד סוף היום, לסגור את היתרה.".format(part), "suggested_stop": current_stop, "stop_rule": "time_stop", "partial_pct": 50, "age_bucket": age}

    if state == "Squat Watch":
        left = age.get("days_left", 0)
        window = "עוד {} ימי מסחר".format(left) if left > 0 else "עד סוף היום"
        return {"primary_action": "לא להוסיף ולא לממש כרגע. לתת {} ל-Follow-through; סטופ נשאר {}.".format(window, _sentinel_money(current_stop) if current_stop else "חסר"), "suggested_stop": current_stop, "stop_rule": "current_stop", "partial_pct": None, "age_bucket": age}

    if age["key"] == "entry_validation" and total_r < 1.0 and violation_count == 0:
        left = age.get("days_left", 0)
        window = "עוד {} ימי מסחר".format(left) if left > 0 else "עד סוף היום"
        return {"primary_action": "לא לממש כרגע. הפוזיציה בת {} ימים ו-{:.1f}R; לתת {}. סטופ נשאר {}.".format(days_held, total_r, window, _sentinel_money(current_stop) if current_stop else "חסר"), "suggested_stop": current_stop, "stop_rule": "current_stop", "partial_pct": None, "age_bucket": age}

    return {"primary_action": "להחזיק. אין פעולה מיידית; סטופ עבודה נשאר {}.".format(_sentinel_money(current_stop) if current_stop else "חסר"), "suggested_stop": current_stop, "stop_rule": "current_stop", "partial_pct": None, "age_bucket": age}

_sentinel_old_eval = evaluate_position_engine
def evaluate_position_engine(symbol, entry_price, entry_date_str, current_stop, setup_type, mgt_state, weight_pct, total_r, target_risk_usd=0, actual_risk_usd=0, spy_hist=None, quantity=0, initial_quantity=0):
    try:
        res = _sentinel_old_eval(symbol, entry_price, entry_date_str, current_stop, setup_type, mgt_state, weight_pct, total_r, target_risk_usd=target_risk_usd, actual_risk_usd=actual_risk_usd, spy_hist=spy_hist)
    except TypeError:
        res = _sentinel_old_eval(symbol, entry_price, entry_date_str, current_stop, setup_type, mgt_state, weight_pct, total_r, target_risk_usd, actual_risk_usd, spy_hist)
    try:
        if not res.get("ok") or not res.get("data"):
            return res
        data = res["data"]
        try:
            days_held = (datetime.now() - pd.to_datetime(entry_date_str)).days if pd.notnull(pd.to_datetime(entry_date_str)) else 0
        except Exception:
            days_held = 0
        data["days_held"] = int(days_held)
        data["age_bucket"] = classify_position_age(days_held)
        directive = build_concrete_trade_action(symbol, setup_type, mgt_state, total_r, current_stop, entry_price, data, quantity=quantity)
        card = data.get("decision_card") or {}
        card["primary_action"] = directive["primary_action"]
        card["management_directive"] = directive
        card["suggested_stop"] = directive.get("suggested_stop")
        card["stop_rule"] = directive.get("stop_rule")
        card["age_bucket"] = directive.get("age_bucket")
        reasons = list(card.get("reasons") or [])
        age_reason = "ותק: {}".format(data["age_bucket"]["label"])
        if age_reason not in reasons:
            reasons.insert(0, age_reason)
        card["reasons"] = reasons[:4]
        data["decision_card"] = card
        data["action"] = directive["primary_action"]
        data["suggested_action"] = directive["primary_action"]
        data["preferred_action"] = directive["primary_action"]
        data["suggested_stop"] = directive.get("suggested_stop")
        data["stop_rule"] = directive.get("stop_rule")
        data["partial_pct"] = directive.get("partial_pct")
        data["quantity"] = quantity
        data["initial_quantity"] = initial_quantity
        data["profit_engine"] = {
            "bias": card.get("bias"),
            "bias_he": card.get("bias_he"),
            "primary_action": directive["primary_action"],
            "protection_stage": card.get("protection_stage"),
            "urgency": card.get("urgency"),
        }
    except Exception as e:
        try:
            res["data"]["concrete_action_error"] = str(e)
        except Exception:
            pass
    return res

_sentinel_old_closed_metrics = build_closed_campaign_metrics
def build_closed_campaign_metrics(df, fallback_target_risk=37.5):
    res = _sentinel_old_closed_metrics(df, fallback_target_risk)
    try:
        camp = res["data"]["campaigns"]
        if camp is not None and not camp.empty and "true_r" in camp.columns:
            camp["target_r"] = camp.get("portfolio_r")
            camp["actual_r"] = camp.get("true_r")
            camp["total_r"] = camp["true_r"]
            camp["portfolio_r"] = camp["true_r"]
            res["data"]["campaigns"] = camp
    except Exception:
        pass
    return res

_sentinel_old_open_metrics = build_open_campaign_metrics
def build_open_campaign_metrics(df, fallback_target_risk=37.5):
    res = _sentinel_old_open_metrics(df, fallback_target_risk)
    try:
        out = res["data"]
        if out is not None and not out.empty and "true_r" in out.columns:
            out["target_r"] = out.get("portfolio_r")
            out["actual_r"] = out.get("true_r")
            out["total_r"] = out["true_r"]
            out["portfolio_r"] = out["true_r"]
            res["data"] = out
    except Exception:
        pass
    return res

_sentinel_old_governor = compute_risk_governor
def compute_risk_governor(*args, **kwargs):
    res = _sentinel_old_governor(*args, **kwargs)
    try:
        if res.get("ok") and res.get("data"):
            res["data"]["risk_basis"] = "actual_r_closed_campaigns_plus_50pct_open_positions_algo_uses_target_r"
    except Exception:
        pass
    return res
# --- END Sentinel concrete actions inline patch 2026-05-04 ---
