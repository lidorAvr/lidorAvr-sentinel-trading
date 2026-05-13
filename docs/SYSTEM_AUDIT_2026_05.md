# Sentinel Trading — System Audit Report
**תאריך:** מאי 2026  
**מטרה:** סקירה עמוקה של כל שירות, קונטיינר, חישוב, תפריט וטסט — לזיהוי נקודות כשל, חוסר אחידות וסינרגיה בין חלקי המערכת.

---

## 1. ארכיטקטורה ותזרים נתונים

### שירותי Docker (docker-compose.yml)

| קונטיינר | פקודה | תפקיד |
|----------|-------|--------|
| `sentinel-bot` | `python3 main.py` | מנוע מסחר ראשי (לא נבדק לעומק) |
| `telegram-bot` | `python3 telegram_bot_secure_runner.py` | ממשק טלגרם + rate-limiting + admin guard |
| `dashboard` | `streamlit run dashboard.py` | דשבורד ויזואלי (לא נבדק) |
| `risk-monitor` | `python risk_monitor.py` | ניטור רציף של פוזיציות בלופ 60 שניות |
| `reporting-service` | `python report_scheduler.py` | דוחות שבועיים/חודשיים |

**כל הקונטיינרים חולקים את אותו volume:** `. : /app` — שינוי קובץ אחד ב-host נראה מיידית בכל הקונטיינרים.  
**תלויות:** `risk-monitor` ו-`reporting-service` מוגדרים `depends_on: telegram-bot` אך אין בדיקה שהבוט אכן "בריא" לפני שהם עולים.

### תזרים נתונים מרכזי

```
Supabase (trades table)
    ↓ fetch once per cycle
risk_monitor.py ──────────────────────────────────────────────┐
    ↓                                                         │
engine_core.py (חישובים)                              Telegram alerts
    ├── yfinance (live price / history, cache 5min)          │
    ├── sentinel_config.json (risk_pct, NAV, timestamps)     │
    └── risk_monitor_state.json (last alerts, streaks)       │
                                                             │
telegram_portfolio.py ────────────────────────────────────────┘
    ↓ (on user request)
telegram_formatters.py → Markdown → Telegram

adaptive_risk_engine.py
    ├── reads sentinel_config.json
    ├── reads risk_journal.json
    └── reads risk_recommendations.json

analytics_engine.py (pure functions, no I/O)
report_scheduler.py ──→ Supabase ──→ PDF ──→ Telegram
```

---

## 2. ניתוח שירות לשירות

### 2.1 bot_core.py — Singleton Layer

**מה הוא עושה:** מאתחל את שלושת ה-singletons שכל המודולים משתמשים בהם.

```python
TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_CHAT_ID")
bot      = telebot.TeleBot(TOKEN)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
```

**בעיות מזוהות:**
- אין validation — אם `.env` לא קיים, `TOKEN=None` ו-`ADMIN_ID=None`; הקריסה תגיע רק בשימוש הראשון בהם, לא בהפעלה
- `ADMIN_ID` מגיע כ-string מ-env; השוואה בקוד המאבטח כנגד `int(chat_id)` יכולה לכשול אם סוגים לא תואמים

---

### 2.2 telegram_bot_secure_runner.py — Security & Rate Limiting Gateway

**מה הוא עושה:**  
Monkey-patches את telebot ב-runtime — עוטף כל message_handler ו-callback_handler עם:
1. בדיקת admin authorization
2. Rate limiting: 8 הודעות / 60 שניות, cooldown 90 שניות לאחר חריגה
3. הזרקת "truth suffix" לכל הודעה יוצאת

**חישוב Rate Limit:**
```python
while events and now - events[0] > WINDOW_SECONDS:  # מנקה ישנים
    events.popleft()
if len(events) >= MAX_MESSAGES:
    _cooldown_until[chat_id] = now + COOLDOWN_SECONDS  # 90 שניות
```

**Truth Suffix Logic:**  
מזהה markers: `'חדר מצב'`, `'דו"ח'`, `'חשיפת תיק'`, `'משטר שוק'`, `'פוזיציות'` ← מוסיף:  
`"מקור נתונים: Live/Cached לפי זמינות. אם מחיר חי או NAV לא זמינים, יש להתייחס לנתון כהערכה"`

**בעיות מזוהות:**
- Rate limiting הוא **in-memory** (defaultdict + deque) — מתאפס על כל restart של קונטיינר
- Truth suffix מוזרק גם להודעות שכבר מכילות disclaimer → **כפילות אפשרית**
- Monkey-patch חייב לקרות **לפני** כל instantiation של `TeleBot` — אם bot_core.py נטען קודם, ה-patch מפספס; הסדר הנוכחי תלוי בסדר ה-import
- Exception בתוך callback handler נבלע (line 102) — המשתמש לא מקבל שום feedback

---

### 2.3 engine_core.py — ליבת החישובים (1917 שורות)

#### Phase 1: Data Fetching

**get_cached_history(symbol, ttl=300)**
- מקור: yfinance `Ticker().history()`
- Cache: in-memory dict, TTL 5 דקות
- **כשל:** מחזיר DataFrame ריק בשקט אם yfinance נכשל — calling code חייב לבדוק

**get_live_price(symbol)**  
ניסיון 3 אסטרטגיות בסדר:
1. `fast_info['last_price']` 
2. Yahoo HTML scraping
3. tail של cached history

**כשל:** מחזיר `None` ללא לוג אם כל 3 נכשלות

#### Phase 2: Position Scoring

**score_position(features, stage)** — ציון 0-95

| קריטריון | ניקוד |
|---------|-------|
| Not below MA10 | +8 / -8 |
| Not below MA20 | +12 / -15 |
| Not below MA50 | +10 / -12 |
| Good closes > bad (10d) | +8 |
| Accumulation days (max 6) | +2 each |
| Distribution days (8d) | -6 each |
| Distribution days (12d) | -5 each |
| RS vs SPY > 0 | +6 / -6 |
| RS vs Sector > 0 | +4 / -4 |
| Within 3% of 20d high | +6 |
| Below 8% of 20d high | -8 |
| Dead money flag | -12 |
| Slow flag | -6 |
| Down day > 1.3×ATR | -10 |
| Down move > 1.2×ATR | -8 |

Stage-specific penalties: Early/Developing/Advanced/Runner — ראה קוד לפרטים

#### Phase 3: Position State Machine (10 מצבים)

סדר עדיפויות מחמיר:

```
ALGO_OBSERVED      → setup_type == "algo_observed"
DATA_INCOMPLETE    → original_campaign_risk ≤ 0
BROKEN             → price ≤ stop OR violation_score ≥ 6
RUNNER             → open_r ≥ 5.0 OR (realized ≥ orig_risk AND follow_through ≥ 70%)
PROFIT_PROTECTION  → open_r ≥ 2.0
WORKING            → open_r ≥ 1.0 AND follow_through ≥ 60%
YELLOW_FLAG        → violation_score ≥ 2
DEAD_MONEY         → age ≥ 8d AND -0.5R ≤ open_r ≤ 0.75R AND FT < 50% AND no new high
PROVING            → 3d ≤ age ≤ 7d AND open_r ≤ 1.0R
NEW                → age ≤ 2d
Default            → PROVING
```

**בעיה קריטית:** `follow_through_score` מועבר כ-`None` מ-risk_monitor (לא מחושב בשום מקום בקוד הניטור). משמעות: `RUNNER` ו-`WORKING` מסתמכים על branch שמניח `None = ok`, מה שמקל אוטומטית על הדרישות.

#### Phase 4: פונקציות Risk Basis (Pure Functions)

**compute_original_campaign_risk(side, entry, initial_stop, qty, fees=0)**
```
LONG: risk = (entry - stop) × qty + fees
```
מחזיר 0.0 אם פרמטר לא תקין.

**compute_r_true(net_pnl, original_risk)**
```
R = net_pnl / original_risk  (אם > 0)
```

**compute_capital_at_risk_usd(side, avg_entry, current_stop, qty)**
```
LONG: at_risk = (avg_entry - stop) × qty  [floored at 0]
מחזיר 0 אם stop מעל entry (הגנה מלאה)
```

**compute_risk_deviation(open_pnl, target_risk)**
```
deviation_r = |open_pnl| / target_risk
≤1.0R: "normal" | 1.0-1.5R: "minor" | 1.5-2.0R: "moderate"
2.0-3.0R: "severe" | >3.0R: "system_event"
```

**compute_giveback_from_peak(peak_r, current_r)**
```
giveback_r = peak_r - current_r
giveback_pct = (giveback_r / peak_r) × 100
≤20%: "natural" | 20-35%: "watch" | 35-50%: "tighten" | >50%: "protection_failure"
```

#### Phase 5: Earnings Risk
**fetch_next_earnings_date(symbol)** — cache 6 שעות  
Verdict: `<0d="⚪ עבר"` | `1-7d="🔴"` | `8-21d="🟡"` | `>21d="🟢"`

#### Phase 6: ALGO Oversight
```python
ALGO_SYMBOL_LIMITS = {"QQQ": 10.0, "TSLA": 7.0, "JPM": 7.0, "PLTR": 6.0, "HOOD": 6.0}
ALGO_CLUSTER_WARNING_PCT  = 30.0
ALGO_CLUSTER_CRITICAL_PCT = 35.0
```
oversight_score = 5 מרכיבים × 20 נק' כל אחד (סימול ידוע, target_risk, R ניתן לחישוב, PnL≠0, quality>0)

---

### 2.4 adaptive_risk_engine.py — מנוע סיכון אדפטיבי

**RISK_LADDER:** `[0.35, 0.50, 0.75, 1.00, 1.25, 1.50, 2.00, 2.50]`  
**RISK_SETTLE_HOURS:** 48.0

#### חישוב Heat Score (מדורג לפי חלונות זמן)

| חלון | קמפיינים | משקל |
|------|----------|------|
| S9 | 9 האחרונים | 50% |
| M21 | 21 האחרונים | 30% |
| L50 | 50 האחרונים | 20% |

**רק קמפיינים דיסקרציונריים** (לא ALGO, לא DATA_INCOMPLETE)

**_window_heat_score:**
```
base = WR × 100
payoff bonus: ≥2.5→+20, ≥2.0→+15, ≥1.5→+8, ≥1.2→+3, <0.8→-10
PF bonus:     ≥2.5→+12, ≥2.0→+8, ≥1.5→+4, <1.0→-15
streak:       loss≥3→-15, loss≥2→-8
clip [0, 100]
```

**open_r bonus:**
```
combined_open_r = disc_r + algo_r × 0.25
≥5.0→+10 | ≥2.0→+5 | ≥1.0→+2 | <0→-3 | ≤-1.0→-8 | ≤-3.0→-15
```

**Direction Decision:**
```
heat ≥ 60 AND loss_streak < 2  → "up"      (+1 step)
heat < 40 OR loss_streak ≥ 3   → "down_fast" (-2 steps)
else                            → "hold"
```

**Settle Period (48h):**  
אחרי כל confirm של שינוי סיכון — no alert, no Sizing Leak for 48h in same direction.

#### קריאה ממדינות חיצוניות

| קובץ | מה נקרא | מה נכתב |
|------|---------|----------|
| sentinel_config.json | risk_pct_input, nav, risk_changed_ts/dir | risk_pct_input, risk_changed_ts/dir |
| risk_journal.json | last 500 entries | appends new entry |
| risk_recommendations.json | last recommendation | updates "followed" field |

---

### 2.5 addon_risk_engine.py — מנוע Add-On / Pyramid

**עיקרון:** pure math, אין API calls, אין DB writes. הסוחר מציע — המנוע בודק.

#### compute_campaign_lot_state

```python
original_risk_usd = (base_price - initial_stop) × base_qty
open_pnl_usd      = (current_price - base_price) × current_qty
locked_profit_usd = max(0, (stop_loss - base_price) × current_qty)  # רק אם stop > base
open_risk_usd     = max(0, (base_price - stop_loss) × current_qty)  # רק אם stop < base
net_result_if_stop_hit = realized_pnl + (stop_loss - base_price) × current_qty
open_r            = open_pnl / original_risk_usd
cushion_ratio     = locked_profit / original_risk_usd
```

#### 5 שערי כניסה (check_addon_eligibility)

| שער | תנאי | כשל |
|-----|------|-----|
| 1 - Data | data_complete == True | MANUAL_REVIEW |
| 2 - ALGO | setup != ALGO | BLOCKED |
| 3 - Cushion | open_r ≥ 1.0R OR locked ≥ 50% orig | BLOCKED |
| 4 - Open Risk | open_risk ≤ orig_risk | WATCH אם >50%, BLOCKED אם >100% |
| 5 - Chase | price ≤ MA10 × 1.07 | BLOCKED אם >7%, WATCH אם >4% |

#### נוסחת Sizing

```python
available_risk = locked_profit + realized_pnl - desired_buffer
raw_max_qty    = floor(available_risk / risk_per_share)
cap_original   = floor(base_qty × 1.0)   # לא יותר מגודל מקורי
cap_current    = floor(current_qty × 0.5) # לא יותר מ-50% פוזיציה פתוחה
max_qty        = min(raw_max_qty, cap_original, cap_current)
suggested_qty  = min(floor(base_qty × 0.40), max_qty)  # ברירת מחדל 40%
```

**Hard Floor Check:**
```python
result_if_stopped = net_result_if_stop_hit - addon_risk_usd
hard_floor        = -original_risk_usd × 0.25
if result_if_stopped < hard_floor → BLOCKED
```

**Stop Mode:**
- `locked_profit > 0` → LAYERED (סגור רק add-on על stop טקטי)
- `locked_profit = 0` → UNIFIED (סגור הכל על campaign stop)

---

### 2.6 risk_monitor.py — ניטור רציף (958 שורות)

**לופ ראשי:** כל ~60 שניות

**קבועים:**
```python
PROFIT_CHECKPOINTS        = [2.0, 3.0]
DEVIATION_COOLDOWN_SEC    = 3 * 3600   # 3 שעות
GIVEBACK_COOLDOWN_SEC     = 6 * 3600   # 6 שעות
LIVE_ALERT_REPEAT_COOLDOWN = 45 * 60   # 45 דקות
STATE_ALERT_COOLDOWN = {"RUNNER": 4h, "BROKEN": 4h, "DEAD_MONEY": 12h}
SIZING_LEAK_THRESHOLD     = 0.65       # <65% target risk → alert חד-פעמי
```

#### Phase 1 — Live Position Evaluation

לכל פוזיציה פתוחה:
1. `ec.get_live_price(symbol)` → אם None: **משתמש ב-entry_price בשקט** (לא מתריע!)
2. מחשב: open_pnl, weight_pct, original_risk, open_r, total_r
3. קורא ל-`ec.evaluate_position_engine()` → status/action/trigger
4. אם `engine_res["ok"] == False` → **skip with `continue`, אין alert**

#### Phase 2 — Risk Thresholds

- **Deviation alerts:** רק על הפסדים; escalation OR 3h cooldown
- **Profit checkpoints:** פעם אחת ב-2R ובR 3
- **Giveback monitor:** רק אם peak_open_r ≥ 1.5R; על מעברי zone

#### Phase 3 — Position State Machine

- בודק כל פוזיציה לגיל, earnings, מצב
- שולח alert רק על **מעבר מצב** + cooldown
- RUNNER: keyboard עם 3 אפשרויות פעולה
- Breakeven Protocol: פעם אחת אם open_r ≥ 3.0 AND capital_risk > 0

#### Phase 4 — ALGO Oversight

- Loss streak ≥ 3: אזהרה צהובה; ≥5: כתומה
- Deep loss (open_r ≤ -2.0R): alert חד-פעמי, reset ב->-1.0R
- Cluster: <30% = ירוק, 30-34% = צהוב, >35% = אדום (hysteresis)

#### Phase 5 — Adaptive Risk + Daily Digest

- Adaptive: direction != "hold" AND no same-dir in 24h AND not in settle period
- Digest: פעם ביום בין 21:00-22:00 UTC, ימי מסחר בלבד

**בעיות error handling:**

| מיקום | בעיה |
|-------|------|
| line 578-579 | live price = None → uses entry_price silently |
| line 604-605 | engine_res["ok"]=False → `continue` ללא alert |
| line 589-590 | initial_stop=0 → original_risk=0 → open_r=0 (מסכה עמדה ללא סטופ) |
| line 684-687 | entry_date parse exception → age_days=0, position treated as NEW |
| line 690-696 | earnings fetch exception → swallowed, continues silently |

---

### 2.7 telegram_portfolio.py — תפריטי משתמש

**handle_portfolio_room:** "חדר מצב"  
- שולף כל trades מ-Supabase
- מחשב לכל פוזיציה: status, sizing, R, lock/giveback
- טוטאלים: open_pnl, realized, locked_profit, giveback_risk, capital_risk
- מפריד ALGO vs. discretionary
- מציג adaptive risk + market regime

**handle_market_regime:** "🌡️ משטר שוק"  
- SPY + QQQ מ-yfinance
- market regime (Hot/Warm/Neutral/Cold)
- חשיפות: ALGO%, VCP%, EP%
- adaptive risk block עם settle_info

**handle_drilldown:** "🔍 {symbol}"  
- Distribution/accumulation days
- RS vs SPY, RS vs sector
- Volatility regime: ATR ratio, stretch

---

### 2.8 telegram_formatters.py — Markdown Formatters

פונקציות מרכזיות:

| פונקציה | מה מייצר |
|---------|----------|
| `fmt_position_card()` | כרטיס פוזיציה עם entry/current/pnl/status |
| `fmt_adaptive_risk_block()` | heat score + S9/M21/L50 + factors + recommendation |
| `fmt_addon_card()` | כרטיס add-on עם eligibility + sizing + stop mode |
| `fmt_minervini_trend_template()` | 8 קריטריונים ✅/❌ + ציון |
| `fmt_actionability()` | מיפוי level → תווית עברית |

---

### 2.9 analytics_engine.py — KPIs לדוחות (Pure Functions)

**compute_period_analytics(df, period_start, period_end, account_state)**

```python
net_r        = net_pnl / original_risk  (fallback: target_risk)
win_rate     = wins / n
expectancy   = WR × avg_win + (1-WR) × avg_loss
profit_factor = gross_profit / gross_loss  (sentinel: 99.0 אם no losses)
avg_r_per_day = mean(net_r / days_held)
missing_stop_rate = count(initial_stop ≤ 0) / n_buys
oversized_rate    = count(actual_risk > target × 1.25) / n_with_stops
```

**compute_trader_development_score(analytics)** — 0-100

| מרכיב | משקל |
|-------|------|
| Process discipline | 35 |
| Edge quality | 35 |
| Risk behavior | 20 |
| Execution efficiency | 10 |

Labels: ≥75 = מצוין 🟢 | ≥50 = טוב 🟡 | <50 = דורש 🔴

---

### 2.10 report_scheduler.py — דוחות אוטומטיים

| דוח | תזמון |
|-----|-------|
| שבועי | שבת 08:30 שעון ישראל |
| חודשי | ה-1 לחודש, 08:40 |

**לופ:** 60 שניות  
**תהליך:** Supabase → analytics_engine → PDF (לא נבדק) → Telegram

---

## 3. כיסוי טסטים

### מה מכוסה

| קובץ טסט | מה נבדק | מצב |
|----------|---------|------|
| test_calculations_comprehensive.py | R-multiple, profit_factor, expectancy, dev_score, adaptive_risk | ✅ |
| test_stat_bucket.py | classify_stat_bucket, algo_oversight_score | ✅ |
| test_phase5_anti_spam.py | STATE_ALERT_COOLDOWN, _should_fire_state_alert | ✅ |
| test_risk_deviation.py | deviation classifications | ✅ |
| test_risk_basis_engine.py | True/Target/Unknown basis, R calc | ✅ |
| test_earnings_module.py | fetch_next_earnings_date | ✅ |
| test_bot_helpers.py | rate limiting, guard functions | ✅ |
| test_telegram_formatters.py | Markdown formatting | ✅ |
| test_addon_risk_engine.py | 37 בדיקות: כל 8 test cases מהמפרט | ✅ |
| test_data_validation.py | input sanitization | ✅ |
| test_security.py | API key management | ✅ |

### מה **לא** מכוסה (פערים קריטיים)

| פיצ'ר | סיבה לחסך |
|-------|----------|
| `get_live_price()` fallback chain | אין mock ל-yfinance |
| Supabase queries | אין mock ל-supabase client |
| Position state machine scenarios | אין integration tests |
| follow_through_score computation | הפונקציה לא קיימת בקוד |
| PDF generation / delivery | קבצים לא נסרקו |
| Market regime thresholds | SPY/QQQ data לא מוקיים |
| ALGO cluster hysteresis state machine | לא נבדק |
| open_r bonus tiers (adaptive) | רק חישוב כולל נבדק |
| Discretionary filtering (adaptive) | אין test שמוודא ALGO מסונן |
| Concurrency / cache contention | אין |

### אי-התאמות בין טסטים לקוד

| פיצ'ר | קוד ייצור | כיסוי טסט | אי-התאמה |
|-------|----------|----------|---------|
| S9/M21/L50 weights | 50%/30%/20% | בדיקה עקיפה | ⚠️ משקלים לא verified |
| Open_r bonus | 5 רמות (1R/2R/5R/-1R/-3R) | לא נבדק | ❌ |
| Giveback severity buckets | 20%/35%/50% | לא נבדק | ❌ |
| Profit factor sentinel all-wins | 2.0 (adaptive) vs 99.0 (analytics) | נבדק כל אחד בנפרד | ⚠️ ערכים שונים |

---

## 4. חוסר עקביות בחישובים (קריטי)

### 4.1 original_campaign_risk — 3 הגדרות שונות

| מודול | אופן חישוב |
|-------|----------|
| engine_core.py (line 887) | `(init_sl) × qty` מ-initial_stop column |
| adaptive_risk_engine.py (line 147) | `(base_price - initial_stop) × base_qty` מ-first buy day בלבד |
| analytics_engine.py (line 250) | כמו adaptive, אבל fallback ל-`target_risk_usd` אם אין stop |

**השפעה:** אותו קמפיין עלול לקבל ערכי R שונים בדשבורד, בניטור ובדוחות.

### 4.2 Profit Factor Sentinel

| מודול | all-wins sentinel |
|-------|------------------|
| adaptive_risk_engine.py | 2.0 |
| analytics_engine.py | 99.0 |

**השפעה:** PF שמוצג בדוח חודשי ≠ PF שמשפיע על המלצת סיכון.

### 4.3 Win Rate Calculation

שניהם: `len(wins) / n` — **עקבי** אבל הגדרת "win" שונה:
- adaptive_risk: `is_win` = bool מ-compute_closed_campaigns
- analytics: `pnl > 0` ישירות

**השפעה:** קמפיין עם pnl=$0.01 = win בשניהם (בסדר), אבל עיגולים שונים בדוחות.

### 4.4 R עבור ALGO vs. Manual

- ALGO: תמיד משתמש ב-`target_risk_usd` (לא original_campaign_risk)
- Manual: משתמש ב-`original_campaign_risk` אם זמין, אחרת fallback ל-`target_risk`
- **Risk:** אחידות בין R חדר המצב (portfolio.py) ל-R דוח חודשי (analytics) לא מובטחת

---

## 5. נקודות כשל קריטיות

### 5.1 Silent Failures (כשל דומם)

| מיקום | תרחיש | מה קורה |
|-------|-------|----------|
| risk_monitor.py:578 | live price = None | משתמש ב-entry_price, אין alert |
| risk_monitor.py:604 | engine_res ok=False | skip position, אין alert |
| risk_monitor.py:589 | initial_stop = 0 | original_risk=0, open_r=0, position treats as breakeven |
| engine_core.py:66 | yfinance נכשל | DataFrame ריק, indicators = NaN |
| adaptive_risk_engine.py:104 | earnings fetch נכשל | {ok:False}, בלע exception, ממשיך |

### 5.2 Division by Zero

```python
# risk_monitor.py
open_r = open_pnl_usd / original_campaign_risk  # crash אם original_risk = 0

# engine_core.py — compute_r_true
R = net_pnl / original_campaign_risk  # protected: returns 0.0 if ≤ 0 ✅

# adaptive_risk_engine.py — _window_stats  
payoff = avg_win / avg_loss  # protected: returns 0.0 if no losses ✅
```

**risk_monitor.py לא מוגן** בצורה עקבית.

### 5.3 follow_through_score — פונקציה שלא קיימת

`compute_position_state()` מקבל פרמטר `follow_through_score` שמועבר כ-`None` מ-risk_monitor.  
כשהוא `None`:
- RUNNER gate: עובר אוטומטית (מקל דרישה)
- WORKING gate: עובר אוטומטית

**השפעה:** מצב RUNNER ו-WORKING מתקבלים קל יותר ממה שמוגדר במפרט.

### 5.4 State File Persistence

`risk_monitor_state.json` נשמר רק בסוף ה-main() loop.  
אם הקונטיינר קורס באמצע — כל state updates של הסייקל האחרון אובדים.  
**Risk:** alerts חוזרים שכבר נשלחו / אובדן streaks ו-checkpoints.

### 5.5 bot_core.py Startup Validation

```python
TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN")  # יכול להיות None
ADMIN_ID = os.getenv("ADMIN_CHAT_ID")       # יכול להיות None
bot      = telebot.TeleBot(TOKEN)           # לא קורס עכשיו...
```
קריסה ראשונה תהיה רק בפנייה הראשונה מ-Telegram — בלי הודעת שגיאה ברורה ב-log.

---

## 6. מפת סינרגיה בין שירותים

```
┌─────────────────────────────────────────────────────────────────┐
│                         SUPABASE                                │
│                    (trades table - source of truth)             │
└──────────────────┬──────────────────────────────────────────────┘
                   │ fetch all trades (once per cycle)
         ┌─────────▼──────────┐           ┌──────────────────────┐
         │   risk_monitor.py  │           │  report_scheduler.py │
         │  (loop 60 seconds) │           │  (weekly/monthly)    │
         └────────┬───────────┘           └──────────┬───────────┘
                  │                                  │
         ┌────────▼───────────────────────────────── ▼──────────┐
         │              engine_core.py                          │
         │  ┌─────────────────────────────────────────────────┐ │
         │  │ get_live_price → yfinance (cache 5min)          │ │
         │  │ evaluate_position_engine → score 0-95           │ │
         │  │ compute_position_state → 10 states              │ │
         │  │ compute_algo_oversight_summary                  │ │
         │  │ compute_market_regime (SPY/QQQ)                 │ │
         │  └─────────────────────────────────────────────────┘ │
         └────────┬──────────────────────────────────────────────┘
                  │
         ┌────────▼───────────────────┐
         │  adaptive_risk_engine.py   │
         │  ┌─────────────────────┐   │
         │  │ compute_closed_camp │   │
         │  │ S9/M21/L50 windows  │   │
         │  │ heat score 0-100    │   │
         │  │ direction up/hold/↓ │   │
         │  └─────────────────────┘   │
         │  reads/writes:             │
         │  sentinel_config.json      │
         │  risk_journal.json         │
         │  risk_recommendations.json │
         └────────┬───────────────────┘
                  │
         ┌────────▼──────────────────────────────────────────────┐
         │         telegram alerts (via bot_core.bot)            │
         └──────────────────┬────────────────────────────────────┘
                            │
         ┌──────────────────▼────────────────────────────────────┐
         │    telegram_bot_secure_runner.py                      │
         │    (rate limit 8/60s + admin guard + truth suffix)    │
         └──────────────────┬────────────────────────────────────┘
                            │
         ┌──────────────────▼────────────────────────────────────┐
         │         USER (Telegram)                               │
         │  ├── חדר מצב → telegram_portfolio.py                 │
         │  ├── משטר שוק → telegram_portfolio.py                │
         │  ├── מנטור/Trend Template → engine_core              │
         │  ├── /addon → addon_risk_engine.py                   │
         │  └── תפריט מפתח → git pull + config + logs          │
         └───────────────────────────────────────────────────────┘
```

---

## 7. טבלת התראות — מי שולח מה

| מודול | סוג התראה | טריגר | Cooldown |
|-------|-----------|-------|----------|
| risk_monitor | Live Position Status | escalation / 45min + key change | 45 דקות |
| risk_monitor | Risk Deviation | moderate+, escalation | 3 שעות |
| risk_monitor | Profit Checkpoint | open_r ≥ 2R או 3R | חד-פעמי |
| risk_monitor | Giveback Monitor | מעבר zone (watch/tighten/failure) | 6 שעות |
| risk_monitor | RUNNER State | open_r ≥ 5R | 4 שעות |
| risk_monitor | BROKEN State | price ≤ stop OR violation ≥ 6 | 4 שעות |
| risk_monitor | DEAD_MONEY | age ≥ 8d, weak FT | 12 שעות |
| risk_monitor | Breakeven Protocol | open_r ≥ 3R AND capital_risk > 0 | חד-פעמי |
| risk_monitor | ALGO Loss Streak | streak ≥ 3 צהוב, ≥ 5 כתום | escalation |
| risk_monitor | ALGO Deep Loss | open_r ≤ -2R | חד-פעמי (reset > -1R) |
| risk_monitor | ALGO Cluster | >30% צהוב, >35% אדום | state change / 6h |
| risk_monitor | Adaptive Risk | direction change + 24h | 24h + 48h settle |
| risk_monitor | Daily Digest | 21:00-22:00 UTC ימי מסחר | חד-פעמי |

**שכבות anti-spam:**
1. `telegram_bot_secure_runner.py`: 8 הודעות/60 שניות
2. `risk_monitor.py`: cooldowns לפי סוג alert
3. Settle period: 48h אחרי confirm שינוי סיכון
4. Market hours: חלק מ-alerts רק 11:00-21:00 UTC

---

## 8. הערכת בשלות לייצור

| קטגוריה | דירוג | עדות |
|---------|-------|------|
| **חישובים מרכזיים** | 🟢 גבוה | tested formulas, edge cases |
| **אחידות נתונים** | 🔴 נמוך | original_risk מחושב ב-3 מקומות שונים |
| **error handling** | 🟠 בינוני | try/catch קיים, אבל כשלים שקטים |
| **כיסוי טסטים** | 🟠 בינוני | pure functions מכוסות, integration לא |
| **ניטור תפעולי** | 🟡 בינוני | alerts קיימים, אין health metrics |
| **בטיחות concurrency** | 🔴 נמוך | in-memory cache ללא locks, state file בסוף loop |
| **ניהול config** | 🔴 נמוך | .env ללא validation, עריכה חיצונית לא נבדקת |

**מסקנה:** המערכת **פונקציונלית** ועובדת בפועל, אך **שבירה תפעולית**.

---

## 9. המלצות לפעולה (לפי עדיפות)

### דחוף
1. **אחד מקום לחישוב original_campaign_risk** — פונקציה אחת ב-engine_core שכל המודולים קוראים לה
2. **alert על live price = None** — לא להשתמש ב-entry_price בשקט
3. **alert על engine_res ok=False** — לא לדלג על פוזיציה בשקט
4. **startup validation** ב-bot_core.py — בדוק TOKEN/ADMIN_ID קיימים לפני `TeleBot()`

### בינוני
5. **implement follow_through_score** — כרגע None תמיד; מקל מצבים RUNNER/WORKING
6. **אחד sentinel לprofit_factor** — 99.0 בכל מקום (כמו analytics), לא 2.0
7. **שמירת state file לאחר כל alert** — לא רק בסוף loop
8. **tests לopen_r bonus tiers** + **giveback severity buckets**

### ארוך טווח
9. **Supabase mock בטסטים** — integration tests עם נתונים מציאותיים
10. **yfinance mock בטסטים** — בדיקת כל fallback chain
11. **sample-size context בהמלצות** — 5 עסקאות vs. 50 עסקאות
12. **state file save בעת interrupt** — `signal.signal(SIGTERM, ...)` בלופ

---

## נספח — קבועים מרכזיים

```python
# engine_core.py
ALGO_SYMBOL_LIMITS          = {"QQQ": 10.0, "TSLA": 7.0, "JPM": 7.0, "PLTR": 6.0, "HOOD": 6.0}
ALGO_CLUSTER_WARNING_PCT    = 30.0
ALGO_CLUSTER_CRITICAL_PCT   = 35.0
_R_RUNNER                   = 5.0
_R_PROFIT_PROTECT           = 2.0
_R_WORKING                  = 1.0
_DEAD_MONEY_MIN_DAYS        = 8
_DEAD_MONEY_MIN_R, MAX_R    = -0.5, 0.75
_DEAD_MONEY_FOLLOW_MAX      = 50.0
_VIOLATION_YELLOW_FLAG      = 2
_VIOLATION_BROKEN           = 6
_EVENT_RISK_RED_DAYS        = 3
_EVENT_RISK_ORANGE_DAYS     = 7
_EVENT_RISK_MAX_DAYS        = 15

# adaptive_risk_engine.py
RISK_LADDER                 = [0.35, 0.50, 0.75, 1.00, 1.25, 1.50, 2.00, 2.50]
RISK_SETTLE_HOURS           = 48.0

# risk_monitor.py
PROFIT_CHECKPOINTS          = [2.0, 3.0]
DEVIATION_COOLDOWN_SEC      = 10800  # 3h
GIVEBACK_COOLDOWN_SEC       = 21600  # 6h
LIVE_ALERT_REPEAT_COOLDOWN  = 2700   # 45min
SIZING_LEAK_THRESHOLD       = 0.65

# addon_risk_engine.py
MIN_OPEN_R_FOR_ADDON        = 1.0
MIN_CUSHION_RATIO           = 0.50
HARD_FLOOR_RATIO            = -0.25
MAX_SIZE_VS_ORIGINAL        = 1.0
MAX_SIZE_VS_CURRENT         = 0.50
DEFAULT_SIZE_RATIO          = 0.40
CHASE_EXT_LIMIT             = 0.07
```
