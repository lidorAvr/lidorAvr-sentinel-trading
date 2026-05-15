# Sentinel Trading — System Audit Report
**גרסה:** V2 (revised 2026-05-14)
**מחבר:** Research Team (Sprint 10 directive #4)
**גרסה קודמת:** V1 May 2026 — superseded; see git history at commit `<see git log for V1>`
**שינויים מ-V1:** טבלת השוואה מתחת
**מטרה:** סקירה עמוקה של כל שירות, קונטיינר, חישוב, תפריט וטסט — לזיהוי נקודות כשל, חוסר אחידות וסינרגיה בין חלקי המערכת. גרסה זו מתעדת איזה מ-claims של V1 נסגרו, איזה שודרגו/הופחתו, ואיזה נמצאו חדשים.

---

## שינויים מאז V1

| Issue (V1 numbering) | V1 verdict | V2 verdict | Code evidence | Status |
|---|---|---|---|---|
| 4.1 `original_campaign_risk` | 3 definitions | 2 definitions | `adaptive_risk_engine.py:159-175` | DOWNGRADED, still real |
| 4.2 PF sentinel | 2.0 vs 99.0 | Both `math.inf` | `adaptive_risk_engine.py:281`, `analytics_engine.py:54` | RESOLVED |
| 4.3 WR rounding | Inconsistent definitions of "win" | Still cosmetic; not material | `adaptive_risk_engine.py:269-275`, `analytics_engine.py:43-44` | DOWNGRADED, cosmetic |
| 4.4 R for ALGO vs Manual | Fallback path divergence | Still real; analytics fallback at `analytics_engine.py:255` | `analytics_engine.py:255`, `risk_monitor.py:609-611` | UNCHANGED, low |
| 5.1.a Live price None silent | Bug | Alerts before fallback | `risk_monitor.py:594-602` | RESOLVED |
| 5.1.b engine_res ok=False silent | Bug | Alerts then `continue` | `risk_monitor.py:633-640` | RESOLVED |
| 5.1.c initial_stop=0 silent | Bug | Alerts via `get_campaign_risk_metrics` | `risk_monitor.py:612-618` | RESOLVED |
| 5.3 `follow_through_score=None` | Bug | Computed; but gate still bypasses `None` for first 5 trading days | `risk_monitor.py:741` + `engine_core.py:2030, 2043-2044` | DOWNGRADED, partially fixed |
| 5.4 State save at loop end | Data loss risk | Mid-loop checkpoint + SIGTERM handler | `risk_monitor.py:927`, `1038-1059` | RESOLVED |
| NEW Issue F | n/a | Analytics doesn't filter ALGO/DATA_INCOMPLETE | `analytics_engine._aggregate_campaigns` | NEW HIGH |
| NEW Issue N3 | n/a | Race on `risk_monitor_state.json` | `risk_monitor.py:106-107`, `bot_helpers.py:49-66` | NEW HIGH |
| NEW Issue N1 | n/a | `score_position` NaN handling fragility | `engine_core.py:417` | NEW MEDIUM |
| NEW Issue N2 | n/a | `open_r` vs `total_r` doc drift after partial sells | `addon_risk_engine.py:50-130` | NEW LOW |

V2 maintains the section structure of V1. Sections 1, 2, 6, 7, 8, and the Appendix have only line-number drift updates. Sections 3, 4, 5, and 9 are rewritten.

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

### 2.3 engine_core.py — ליבת החישובים (2155 שורות; היה 1917 ב-V1)

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

**כשל:** מחזיר `None` ללא לוג אם כל 3 נכשלות (אך כיום `risk_monitor` כן מתריע — ראה §5.1 לעדכון).

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

**עדכון V2:** `follow_through_score` **כן מחושב כיום** ב-`risk_monitor.py:741`. אבל הפונקציה מחזירה `None` למשך 5 ימי מסחר ראשונים (`engine_core.py:1821-1823`), ובאותו זמן ה-gates של RUNNER ו-WORKING מתייחסים ל-`None` כ-pass. ראה §5.3 לפרטים.

#### Phase 4: פונקציות Risk Basis (Pure Functions)

**compute_original_campaign_risk(side, entry, initial_stop, qty, fees=0)** (`engine_core.py:920-941`)
```
LONG: risk = (entry - stop) × qty + fees
```
מחזיר 0.0 אם פרמטר לא תקין.

**get_campaign_risk_metrics(row)** (`engine_core.py:943-977`) — wrapper עם `valid` flag ו-sanity check על הסטופ. זו ה-canonical function כיום; `analytics_engine` ו-`risk_monitor` קוראים לה. `adaptive_risk_engine` עדיין לא — ראה §4.1.

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

**RISK_LADDER:** `[0.25, 0.40, 0.60, 0.85, 1.15, 1.50, 2.00]` (`adaptive_risk_engine.py:20`)
*עדכון V2:* V1 תיעד `[0.35, 0.50, 0.75, 1.00, 1.25, 1.50, 2.00, 2.50]`. הסולם הוקטן ב-Sprint 8/9 — מוסר ה-2.50 הלא-מונוטוני, רכיב 0.25% התווסף כקומה תחתונה.

**RISK_SETTLE_HOURS:** 48.0 (`adaptive_risk_engine.py:33`)
**DRAWDOWN_TRIGGER_PCT:** -8.0 (`adaptive_risk_engine.py:27`)
**DRAWDOWN_CUT_TO_PCT:** 0.40 (`adaptive_risk_engine.py:28`)

#### חישוב Heat Score (מדורג לפי חלונות זמן)

| חלון | קמפיינים | משקל |
|------|----------|------|
| S9 | 9 האחרונים | 50% |
| M21 | 21 האחרונים | 30% |
| L50 | 50 האחרונים | 20% |

**רק קמפיינים דיסקרציונריים** (לא ALGO, לא DATA_INCOMPLETE) — `_is_disc` filter ב-`adaptive_risk_engine.py:431-437`.

**_window_heat_score:** (additive — Sprint 9 P4 מתוכנן להחליף ל-multiplicative)
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

*עדכון V2:* `open_r` הוא ratio של floating-only PnL על quantity הנוכחית, אבל ה-denominator הוא original_risk_usd שמוקפא על base_qty. אחרי partial sell, `open_r` יורד פרופורציונלית גם כשהמחיר לא משתנה. ראה §5.9 (Issue N2).

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

### 2.6 risk_monitor.py — ניטור רציף (1070 שורות; היה 958 ב-V1)

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
1. `ec.get_live_price(symbol)` → אם None: **שולח alert** ואז fallback ל-entry_price (`risk_monitor.py:594-602`). V1 דיווח על כשל דומם — תוקן.
2. מחשב: open_pnl, weight_pct, original_risk (דרך `ec.get_campaign_risk_metrics`, `risk_monitor.py:609-611`), open_r, total_r
3. אם `_risk_metrics["valid"]==False` ולא-ALGO → **שולח alert** על סטופ חסר (`risk_monitor.py:612-618`)
4. קורא ל-`ec.evaluate_position_engine()` → status/action/trigger
5. אם `engine_res["ok"] == False` → **שולח alert** ואז `continue` (`risk_monitor.py:633-640`)
6. מחשב `_ft_score = ec.compute_follow_through(...)` עבור פוזיציות לא-ALGO (`risk_monitor.py:738-746`)

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

**State persistence:** `save_state(state)` נקרא mid-loop (`risk_monitor.py:927`) ובסוף לופ (`:1016`). SIGTERM/SIGINT מטופלים ב-`_graceful_shutdown` (`:1038-1059`). אך writes לא atomic — ראה §5.7 (Issue N3).

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
profit_factor = gross_profit / gross_loss  (sentinel: math.inf אם no losses)
avg_r_per_day = mean(net_r / days_held)
missing_stop_rate = count(initial_stop ≤ 0) / n_buys
oversized_rate    = count(actual_risk > target × 1.25) / n_with_stops
```

*עדכון V2:* PF sentinel היה 99.0 ב-V1 — היום `math.inf` (`analytics_engine.py:54`). תקין.

**הערה קריטית (Issue F חדש):** ב-V1 לא דווח שהמודול הזה **לא מסנן** ALGO/DATA_INCOMPLETE. הקלט ל-`compute_period_analytics` הוא DataFrame של קמפיינים, ו-`_aggregate_campaigns` (`analytics_engine.py:235-267`) בונה records ללא `stat_bucket`. תוצאה: דוחות PDF שבועיים/חודשיים מכילים WR/Expectancy/PF מזוהמים. ראה §5.6.

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

הקריאה ל-`compute_period_analytics` מתבצעת ב-`report_scheduler.py:207` (שבועי) ו-`:266` (חודשי). שני הדוחות חשופים ל-Issue F.

---

## 3. כיסוי טסטים

### מה מכוסה (עדכון V2 — `tests/` כיום מכיל ~46 קבצי טסט; V1 תיעד 11)

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
| test_follow_through.py | פונקציית compute_follow_through שנוספה לאחר V1 | ✅ |
| test_position_state_machine.py | state-machine transitions (חדש) | ✅ |
| test_drawdown_auto_cut.py | Sprint 8 drawdown override (חדש) | ✅ |
| test_phase3_state_alerts.py / test_phase4_algo_oversight.py / test_phase6_context_export.py | phase-specific monitor logic | ✅ |
| test_e2e_risk_monitor.py | integration test לחלק מ-monitor flow | ✅ |
| test_adaptive_risk_engine.py | קבועי RISK_LADDER, S9/M21/L50 windows | ✅ |
| test_analytics_engine.py | period analytics — **אבל ללא bucket filter** | ⚠️ |
| test_audit_logger.py / test_supabase_repository.py | layer חדש לאחר V1 | ✅ |
| test_secure_runner.py | guard, rate limit | ✅ |
| test_trailing_stop.py / test_trade_metrics.py / test_nav_and_intent.py | אופציות חדשות | ✅ |
| test_ibkr_*.py / test_dev_pin_persistence.py / test_chart_generator.py / test_heat_*.py | infra חדש | ✅ |

### מה **לא** מכוסה (פערים קריטיים)

| פיצ'ר | סיבה לחסך |
|-------|----------|
| Analytics ALGO/DATA_INCOMPLETE exclusion | אין בדיקה ש-Issue F לא חוזר (`tests/test_analytics_engine.py` לא מזכיר `stat_bucket`, `ALGO`, או `DATA_INCOMPLETE`) |
| Concurrent state file access | אין test ל-Issue N3 — atomic write / file lock |
| `follow_through_score=None` gate semantics | אין assertion ש-`None` לא מקפיץ פוזיציה ל-RUNNER ביום 3 |
| `get_live_price()` fallback chain | אין mock ל-yfinance |
| Supabase queries | mock קיים חלקית ב-`test_supabase_repository.py`, לא בכל קריאה |
| PDF generation / delivery | קבצים לא נסרקו |
| Market regime thresholds | SPY/QQQ data לא מוקיים |
| ALGO cluster hysteresis state machine | לא נבדק |
| open_r bonus tiers (adaptive) | רק חישוב כולל נבדק |
| Multi-thread cache contention | אין |

### אי-התאמות בין טסטים לקוד

| פיצ'ר | קוד ייצור | כיסוי טסט | אי-התאמה |
|-------|----------|----------|---------|
| S9/M21/L50 weights | 50%/30%/20% | בדיקה עקיפה | ⚠️ משקלים לא verified |
| Open_r bonus | 5 רמות (1R/2R/5R/-1R/-3R) | לא נבדק | ❌ |
| Giveback severity buckets | 20%/35%/50% | לא נבדק | ❌ |
| Profit factor sentinel all-wins | `math.inf` בכל המודולים | נבדק כל אחד בנפרד | ✅ עקבי |
| analytics_engine bucket filter | **לא מסנן** | אין assertion | ❌ Issue F |

---

## 4. חוסר עקביות בחישובים (קריטי)

### 4.1 original_campaign_risk — 2 הגדרות שונות (היה 3 ב-V1)

ב-V1 דיווחנו על 3 הגדרות. עדכון: `engine_core.compute_original_campaign_risk` ו-`engine_core.get_campaign_risk_metrics` (`engine_core.py:920-977`) הם כיום הגרסה הקנונית; `analytics_engine.py:252-255` ו-`risk_monitor.py:609-611` שניהם קוראים ל-`ec.get_campaign_risk_metrics(...)`. רק `adaptive_risk_engine` נשאר עם חישוב inline.

| מודול | אופן חישוב |
|-------|----------|
| engine_core.py (920-941) — **canonical** | `compute_original_campaign_risk(side, entry, initial_stop, qty, fees)` עם sanity check |
| analytics_engine.py (252-255) | קורא ל-`ec.get_campaign_risk_metrics(_risk_row)`, נופל ל-`target_risk_usd` אם invalid |
| risk_monitor.py (609-611) | קורא ל-`ec.get_campaign_risk_metrics(dict(row))` |
| adaptive_risk_engine.py (159-175) — **outlier** | inline: `base_price = (price*qty).sum() / base_qty` ואז `(base_price - init_sl) * base_qty` |

**ההפרש הוא subtle:** adaptive מחשב weighted-average base price לפני שמכפיל ב-(base - stop), בעוד engine_core מקבל price/qty יחיד. למקרים של buy יחיד ביום הראשון הם זהים. למקרים של מספר buy rows ביום הראשון יש סיכון לסטייה אם משתמשים בנאיביות ב-`get_campaign_risk_metrics(row)` ללא חישוב מקדים של weighted base.

**השפעה:** אותו קמפיין עם first-day add-on עלול לקבל ערכי R מעט שונים בדשבורד, בניטור (canonical) ובהמלצת הסיכון (adaptive). אחרי איחוד יישבו זה לזה byte-for-byte.

### 4.2 Profit Factor Sentinel — RESOLVED

**V1:** דיווחנו על אי-התאמה: adaptive=2.0, analytics=99.0.
**V2:** שני המודולים משתמשים כיום ב-`math.inf`:
- `adaptive_risk_engine.py:281` — `pf = math.inf`
- `analytics_engine.py:54` — `math.inf if gross_profit > 0`

הסעיף נסגר. שורת `docs/MODULE_MAP.md:84` שעדיין כתוב בה "99.0" היא doc rot; ראה §9 (Sprint 10 P3 docs hygiene).

### 4.3 Win Rate Calculation — DOWNGRADED (cosmetic)

שניהם: `len(wins) / n` — **עקבי** אבל הגדרת "win" שונה:
- adaptive_risk: `is_win` = bool מ-compute_closed_campaigns
- analytics: `pnl > 0` ישירות

**השפעה:** קמפיין עם pnl=$0.01 = win בשניהם (בסדר). העיגול ב-display layer זהה לאחר verification. סעיף זה ירד מ-cosmetic concern בלבד; אינו מוקד תיקון.

### 4.4 R עבור ALGO vs. Manual

- ALGO: תמיד משתמש ב-`target_risk_usd` (לא original_campaign_risk)
- Manual: משתמש ב-`original_campaign_risk` אם זמין, אחרת fallback ל-`target_risk` ב-`analytics_engine.py:255`
- **Risk:** אחידות בין R חדר המצב (portfolio.py) ל-R דוח חודשי (analytics) לא מובטחת **כאשר ה-fallback נדרש**. ב-risk_monitor אין fallback ל-target_risk ב-canonical path — אם invalid, ה-position מטריגרת alert (§5.1) ו-`open_r=0`. ב-analytics נכנס fallback שקט.

---

## 5. נקודות כשל קריטיות

### 5.1 Silent Failures (V1 §5.1) — RESOLVED

V1 דיווח על 3 silent skips ב-risk_monitor. כולם תוקנו ב-Sprint 7/8:

| מיקום (V2) | תרחיש | מה קורה כיום |
|------------|-------|---------------|
| `risk_monitor.py:594-602` (היה 578) | live price = None | **שולח alert** "מחיר חי חסר" ואז fallback ל-entry_price |
| `risk_monitor.py:612-618` (היה 589) | `_risk_metrics["valid"]==False` ולא-ALGO | **שולח alert** "סטופ מקורי חסר" |
| `risk_monitor.py:633-640` (היה 604) | `engine_res["ok"]==False` | **שולח alert** "שגיאה בהערכת פוזיציה" ואז `continue` |

**Verdict:** Resolved. הסעיף נשאר רק כדי לתעד תיקון.

**Side-effect חדש שיש לפעול עליו:** שלושת ה-alerts הללו ללא per-symbol throttling. ביוזמת yfinance outage ארוכה ה-user יקבל את אותה התראה כל 5 דקות — חזרה על AGENTS.md anti-spam invariant. ראה §9 (Sprint 10 P1).

### 5.2 Division by Zero — verified

```python
# risk_monitor.py
# open_r מחושב רק אם _risk_metrics["valid"]==True, אחרת = 0
# כיום מוגן (post-§5.1 fix): שולח alert במקום לחלק ב-0

# engine_core.py — compute_r_true
R = net_pnl / original_campaign_risk  # protected: returns 0.0 if ≤ 0 ✅

# adaptive_risk_engine.py — _window_stats
payoff = avg_win / avg_loss  # protected: returns 0.0 if no losses ✅
```

risk_monitor מקבל הגנה הודות לתיקון §5.1 — אם `valid==False` הקוד שולח alert ומבסס `original_campaign_risk=0`, ואחר כך מבצע short-circuit ב-`open_r` (לא בכל path; verify ב-line 623). אין יותר crash סביר.

### 5.3 `follow_through_score` — DOWNGRADED (partially fixed)

V1 טען שהפונקציה לא קיימת ושכל ה-gates עוברים אוטומטית. עדכון:

**מה תוקן:**
- `engine_core.compute_follow_through(symbol, entry_date_str, entry_price, side)` קיים ב-`engine_core.py:1772-1862`
- `risk_monitor.py:738-746` מחשב את הציון לכל פוזיציה לא-ALGO ומעביר ל-state machine
- Test coverage חדש: `tests/test_follow_through.py`

**מה לא תוקן (residual issue):**
- `compute_follow_through` מחזיר `None` כאשר `len(post) < _FT_MIN_DAYS_FOR_SCORE` (5 ימי מסחר) — `engine_core.py:1821-1823`
- ב-`engine_core.py:2024-2031` (RUNNER gate):
  ```python
  runner_by_realized = (
      original_campaign_risk > 0
      and realized_pnl >= original_campaign_risk
      and has_open_quantity
      and (follow_through_score is None or follow_through_score >= _RUNNER_FOLLOW_THROUGH_MIN)
  )
  ```
- ב-`engine_core.py:2042-2046` (WORKING gate):
  ```python
  good_ft = (follow_through_score is None
             or follow_through_score >= _WORKING_FOLLOW_THROUGH_MIN)
  if open_r >= _R_WORKING and good_ft:
      return _make_state(POSITION_STATE_WORKING, er, ...)
  ```

**משמעות:** במהלך 5 ימי המסחר הראשונים פוזיציה יכולה להיכנס ל-RUNNER (by realized) או WORKING (by R) ללא שום quality gate. RUNNER-by-realized דורש `realized_pnl >= original_campaign_risk` שהוא bar גבוה, אבל WORKING מתחיל מ-`open_r ≥ 1.0R` שיכול להיווצר מתנודה ביום 2.

**Recommended action:** §9 P1 — replace "None=pass" with explicit `age_days < _FT_MIN_DAYS_FOR_SCORE` gating, asymmetric: RUNNER דורש FT מחושב, WORKING מקבל early-life default אם age<5.

### 5.4 State File Persistence (V1 §5.4) — RESOLVED

**V1:** טען ש-`risk_monitor_state.json` נשמר רק בסוף main() loop; crash מאבד state.

**V2 evidence:**
- `risk_monitor.py:925-927` — mid-loop checkpoint לאחר position evaluation
- `risk_monitor.py:1016` — end-of-loop save
- `risk_monitor.py:1038-1059` — `_graceful_shutdown(signum, frame)` שומר state ויוצא על SIGTERM/SIGINT
- `risk_monitor.py:1062-1070` — handlers רשומים ב-`__main__`

**Verdict:** Resolved. Caveat: SIGKILL/OOM/segfault עדיין מאבדים את ה-delta בין שני ה-saves. mitigation נוסף לא משתלם — save אחרי כל alert יחמיר את §5.7 (race condition).

### 5.5 bot_core.py Startup Validation — UNCHANGED

```python
TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN")  # יכול להיות None
ADMIN_ID = os.getenv("ADMIN_CHAT_ID")       # יכול להיות None
bot      = telebot.TeleBot(TOKEN)           # לא קורס עכשיו...
```
קריסה ראשונה תהיה רק בפנייה הראשונה מ-Telegram — בלי הודעת שגיאה ברורה ב-log. סעיף זה נשאר פתוח. עדיפות נמוכה כי המערכת לא משוחררת multi-tenant; ב-Hyperscaler Phase A נדרשת validation נוקשה (`docs/teams/HYPERSCALER_DESIGN_V0.md`).

### 5.6 Issue F (NEW, HIGH) — analytics_engine doesn't filter ALGO/DATA_INCOMPLETE — **RESOLVED (Sprint 10)**

> **STATUS: RESOLVED.** `analytics_engine.compute_period_analytics` now applies
> two distinct filters: edge stats (WR/Expectancy/PF/R/best-worst/setup-breakdown)
> count only `is_stat_countable` campaigns (excludes ALGO_OBSERVED + DATA_INCOMPLETE,
> mirroring `adaptive_risk_engine._is_disc` and `dashboard.py`); process-discipline
> stats (`missing_stop_rate`, `oversized_rate`) count manual campaigns including
> DATA_INCOMPLETE (a missing stop is exactly what they measure) and exclude only
> ALGO. New `excluded_count` / `excluded_pnl` fields added for report disclosure.
> 9 new tests in `tests/test_analytics_engine.py::TestStatBucketExclusion`; two
> pre-existing tests that encoded the bug were corrected. Full suite green
> (1329 passed). Follow-up: surface `excluded_count` in `report_renderer.py`.

**ההפרה (V2, pre-fix):** AGENTS.md invariant #8 — *"Win Rate and Expectancy must never include DATA_INCOMPLETE or ALGO_OBSERVED campaigns."*

**Code evidence:**

`adaptive_risk_engine.py:431-437` — מסנן נכון:
```python
def _is_disc(c: dict) -> bool:
    bucket = c.get("stat_bucket")
    if bucket:
        return ec.is_stat_countable(bucket)
    ...
disc_camps = [c for c in closed_campaigns if _is_disc(c)]
```

`dashboard.py:374-380` — מסנן נכון:
```python
countable_df = camp_df[camp_df['stat_bucket'].apply(ec.is_stat_countable)]
combined_stats = _bucket_stats(countable_df)
```

`analytics_engine.py:43-54` — **לא מסנן**:
```python
wins   = campaigns[campaigns["net_pnl"] > 0]
losses = campaigns[campaigns["net_pnl"] <= 0]
n      = len(campaigns)
win_rate    = len(wins) / n if n else 0
...
```

`analytics_engine.py:235-267` — `_aggregate_campaigns` בונה records ללא `stat_bucket` field, ואז `analytics_engine.py:255` נופל ל-`target_risk_usd` לקמפיינים invalid (כלומר DATA_INCOMPLETE / ALGO ללא original_risk תקין) — ומכניס אותם לצינור המטריקה.

**מסלולי השפעה:** `report_scheduler.py:207` (שבועי) ו-`:266` (חודשי) קוראים ל-`compute_period_analytics`. → דוחות PDF שהמשתמש קורא שבוע-שבוע מכילים WR/Expectancy/PF מזוהמים.

**אין test coverage:** `grep "stat_bucket\|ALGO\|DATA_INCOMPLETE" tests/test_analytics_engine.py` → 0 hits.

**Severity: HIGH.** זו הפרה ישירה של Red Line #8 ושל Prime Directive #2 (explainability of R math). מנעת marketing claim על WR או expectancy עד שמתקנים.

### 5.7 Issue N3 (NEW, HIGH) — Race on risk_monitor_state.json — **RESOLVED (Sprint 10)**

> **STATUS: RESOLVED.** New `state_io.py` provides `atomic_write_json`
> (tempfile + `os.replace`, atomic on POSIX) and `file_lock`
> (`fcntl.flock` on `<path>.lock`, cross-container via the shared /app
> inode). `risk_monitor.save_state` and `bot_helpers._write_runner_decision`
> now write under the same lock with atomic replace, so the file is never
> torn and the bot's RMW never interleaves with risk-monitor's rewrite.
> The catastrophic torn-read → silent-reset → empty-state-flush mode
> (anomaly #2) and the reader-crash mode (anomaly #3) are eliminated;
> the long-cycle stale-copy lost-update (anomaly #1) is greatly mitigated
> and fully closes only in Hyperscaler Phase B (state → DB). 15 tests in
> `tests/test_state_io.py` incl. a 20-thread concurrent-RMW stress test;
> existing `_write_runner_decision` tests still green. Full suite: 1341
> passed.

**שני writers ללא תיאום, על אותו קובץ, מקונטיינרים שונים (V2, pre-fix):**

Writer #1 — `risk_monitor.py:106-107` (קונטיינר `risk-monitor`):
```python
def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
```
`open(...,"w")` מקצץ מיד; בין truncate ל-json.dump-complete הקובץ partial.

Writer #2 — `bot_helpers.py:49-66` (קונטיינר `telegram-bot`, inline על callback מהמשתמש):
```python
def _write_runner_decision(campaign_id: str, decision: str) -> None:
    try:
        try:
            with open(_RM_STATE_FILE, "r", encoding="utf-8") as f:
                rm_state = json.load(f)
        except Exception:
            rm_state = {"positions": {}, "cluster": {}}   # ← reset אם read נכשל
        ...
        with open(_RM_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(rm_state, f, ensure_ascii=False, indent=2)
```

**שלוש anomalies:**
1. **Lost update.** risk_monitor reads ב-T0, bot reads ב-T1, bot writes ב-T2, risk_monitor writes ב-T3 → ה-`runner_decision` של ה-bot נדרס.
2. **Reset on partial read.** אם bot קורא בזמן writeלא-atomic של risk_monitor → `json.load` raises → `except` מאתחל ל-`{"positions": {}, "cluster": {}}` → next save פולט state ריק. **כל ה-state נמחק שקט.**
3. **Reader exposure.** `dashboard.py:495` ו-`bot_health.py:121` קוראים את אותו קובץ ללא try/except אקטיבי על JSONDecodeError → potential crash בקריאה partial.

`docker-compose.yml` mounts את ה-repo כ-`/app` בכל הקונטיינרים, אז כולם רואים אותו קובץ inode.

**Severity: HIGH.** זה הגורם ל"duplicate alerts" שאיש לא יודע להסביר, ול-checkpoints שנעלמים פתאום. הדרך לתקן: atomic write pattern (`tempfile` + `os.replace`) בשני ה-writers + `fcntl.flock` סביב ה-RMW של ה-bot.

### 5.8 Issue N1 (NEW, MEDIUM) — score_position NaN handling

`engine_core.compute_behavior_features` (`engine_core.py:215-245`) מחזיר booleans כמו `close_below_ma50 = close < ma50`. בפנדס/numpy `value < NaN` → False. אם MA50 הוא NaN (היסטוריה מספיק קצרה), `close_below_ma50=False` ו-`score_position` מוסיף **+10 במקום -12** (`engine_core.py:330`). swing של 22 נקודות לכל אינדיקטור.

**מה מציל היום:** `evaluate_position_engine` יש לו gate `len(hist) < 60` (`engine_core.py:417`) שמחזיר `ok=False`. עם 60 bars מובטחים, MA50 מקבל 10 ערכים תקפים אחרונים. **Safe in production.**

**Severity: MEDIUM** (low-likelihood, high-blast-radius). שביר: אם מישהו מקטין את ה-60 bars guard לטובת small-cap / IPO צעיר, ה-NaN behavior יחזור בשקט.

**Mitigation מומלץ:** `pd.notna()` guards מפורשים ב-`score_position` (`engine_core.py:326-355`), או להעלות שגיאה ב-`compute_behavior_features` עם NaN על MA50 ולתת ל-`evaluate_position_engine` להחזיר `ok=False, error="insufficient_history"`.

### 5.9 Issue N2 (NEW, LOW) — addon `open_r` vs `total_r` doc drift

`addon_risk_engine.compute_campaign_lot_state` (`addon_risk_engine.py:50-130`) מגדיר:
- `original_risk_usd = (base_price - initial_stop) × base_qty` — מוקפא על base_qty
- `open_pnl_usd = (current_price - base_price) × current_qty` — תלוי ב-current_qty
- `open_r = open_pnl / original_risk_usd`

**תוצאה:** אחרי partial sell של 50% (current_qty יורד מ-100 ל-50), אם המחיר לא משתנה, `open_r` נופל מ-1.0 ל-0.5 *בלי שום שינוי במצב המסחר*. הכוונה היא ש-`open_r` מודד "כמה מה-1R המקורי עדיין במחירים צפים על quantity הפתוחה" — design coherent — אבל ה-naming מבלבל. `total_r = (open_pnl + realized) / original_risk` נשאר 1.0 ב-scenario הזה ומייצג את ה-campaign performance הנכון.

**Severity: LOW.** Math correct, doc drift only. עלולה להוביל future agent לקבוע gate שגוי על `open_r`. ה-5-pt Eligibility Gate 3 (Cushion) משתמש ב-`open_r ≥ 1.0R OR locked ≥ 50% orig` — המכוון נכון (floating-only) אבל ה-naming שביר.

**Recommended action:** עדכון docstring + test שמאשר `total_r` invariant תחת partial sell.

---

### 5.10 Issue O (NEW, MEDIUM) — Observability: Python stdout unbuffered

**Discovered:** Day 1 evening shift, during smoke test on production Orange Pi.

**תיאור:** ארבעת שירותי הפייתון (`sentinel-bot`, `telegram-bot`, `risk-monitor`, `reporting-service`) רצים עם stdout מאופן רגיל (block-buffered כש-stdout אינו TTY). מצב זה גורם לכך ש-`docker logs <service>` מציג פלט ריק כל עוד ה-buffer לא מתמלא או שהפרוסס לא יוצא.

**ראיות:**
- `docker-compose.yml` שורה 95 (לפני התיקון): `command: python risk_monitor.py` — ללא `-u` ולא `PYTHONUNBUFFERED=1`
- `docker exec risk-monitor env | grep -i python` החזיר רק `PYTHON_VERSION` ו-`PYTHON_SHA256` — אישור שאין `PYTHONUNBUFFERED`
- Healthcheck (`docker-compose.yml:115`) בודק mtime של `/app/state/risk_monitor_last_cycle`, **לא לוגים** — לכן הקונטיינר "healthy" גם כשאין שום פלט גלוי

**Severity: MEDIUM.** אין השפעה על חישובים או trading logic — אבל מסכה את כל ה-`print()` ו-`logger.info()` שמתבצעים בקוד. מתחבר לשכבת ה-"silent failures" של V1 §5.1 (שתוקנה מבחינת alerts) אך משאיר שכבת observability שלמה במצב סלינט.

**Status: RESOLVED (Day 1).** Commit `<see git log>` הוסיף `PYTHONUNBUFFERED=1` ל-`environment:` בארבעת השירותים. נדרש `docker compose up -d --force-recreate` בפריסה הבאה כדי להחיל.

---

### 5.11 Issue P (NEW, MEDIUM) — secure_runner had zero observability — **RESOLVED (Sprint 10)**

> **STATUS: RESOLVED.** Discovered Day 1 evening: after `PYTHONUNBUFFERED`
> was fixed, `docker logs telegram-bot` was still empty even while the
> bot answered `/portfolio` correctly. Root cause: `telegram_bot_secure_runner.py`
> had **no `print` and no logging at all** — every admin-guard rejection,
> rate-limit trip, and data-source disclosure was invisible. This is the
> observability counterpart of §5.1 (which fixed missing alerts; this
> makes the guard's own actions visible).
>
> **Fix:** added a best-effort `_log()` helper (timestamped,
> `[secure_runner]`-prefixed, `flush=True`, never raises, never logs
> token/admin id). Instrumented: startup config summary (counts only),
> hardening installed, polling started, `unauthorized` rejection (with
> chat_id, for intrusion visibility), `rate_limited` trip, and
> data-source disclaimer append. Deliberately **not** logged: per-message
> `cooldown` rejections and the `ok` happy path — logging those would
> itself be a flood. **No guard logic changed** — additive logging only;
> regression tests assert the admin gate + rate-limit return values are
> byte-identical. 13 tests in `tests/test_secure_runner_logging.py`;
> existing source-content tests still green. Full suite: 1354 passed.
>
> Apply on the Pi with `docker compose up -d --force-recreate telegram-bot`.

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
         │  │ get_campaign_risk_metrics (canonical risk)      │ │
         │  │ compute_follow_through (FT score 0-100, None<5d)│ │
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
         │  │ drawdown_auto_cut   │   │
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

## 7. טבלת התראות — מי שולח מה (verified V2)

| מודול | סוג התראה | טריגר | Cooldown |
|-------|-----------|-------|----------|
| risk_monitor | Live Price Missing (NEW) | `get_live_price` returned None | **ללא throttle (Issue) — ראה §9** |
| risk_monitor | Missing Stop (NEW) | `_risk_metrics["valid"]==False` ולא-ALGO | **ללא throttle — ראה §9** |
| risk_monitor | Engine Eval Failed (NEW) | `engine_res["ok"]==False` | **ללא throttle — ראה §9** |
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
| risk_monitor | Drawdown Auto-Cut P0 (NEW Sprint 8) | 30d PnL ≤ -8% NAV | חד-פעמי, bypasses settle |
| risk_monitor | Daily Digest | 21:00-22:00 UTC ימי מסחר | חד-פעמי |

**שכבות anti-spam:**
1. `telegram_bot_secure_runner.py`: 8 הודעות/60 שניות
2. `risk_monitor.py`: cooldowns לפי סוג alert
3. Settle period: 48h אחרי confirm שינוי סיכון
4. Market hours: חלק מ-alerts רק 11:00-21:00 UTC

**פער: שלוש ההתראות החדשות (§5.1) חסרות throttling לכל סימול — ראה §9 P1.**

---

## 8. הערכת בשלות לייצור (V2 re-rated)

| קטגוריה | V1 דירוג | V2 דירוג | עדות |
|---------|---------|---------|------|
| **חישובים מרכזיים** | 🟢 גבוה | 🟢 גבוה | tested formulas, edge cases; FT computed |
| **אחידות נתונים** | 🔴 נמוך | 🟠 בינוני | original_risk כעת ב-2 מקומות (היה 3); ALGO leakage ב-analytics נותר |
| **error handling** | 🟠 בינוני | 🟠 בינוני | silent failures b-risk_monitor תוקנו; throttle חסר; race condition נמצא |
| **כיסוי טסטים** | 🟠 בינוני | 🟡 בינוני-טוב | 46 קבצי טסט (היה 11); FT, state machine, drawdown מכוסים; analytics filter לא |
| **ניטור תפעולי** | 🟡 בינוני | 🟡 בינוני | alerts קיימים, אין health metrics |
| **בטיחות concurrency** | 🔴 נמוך | 🔴 נמוך | race condition אובחנה (§5.7); atomic writes חסרים |
| **ניהול config** | 🔴 נמוך | 🔴 נמוך | .env ללא validation, עריכה חיצונית לא נבדקת |

**מסקנה V2:** התקדמות מוכחת מ-Sprint 7-8 (כשלים שקטים נסגרו, state persistence שופר, test coverage הוכפל). שני defects קריטיים נשארים פתוחים: (a) report PDF מציג WR/PF/Expectancy מזוהמים ב-ALGO (Issue F), (b) state file נתון ל-race condition בין שני קונטיינרים (Issue N3). שניהם דורשים תיקון לפני שניתן לסמן את המערכת כ-"production-clean" עבור user שני.

---

## 9. המלצות לפעולה (V2 priorities, after Sprint 7-8 fixes)

### דחוף (חדש — לאחר הסגירה של V1's "דחוף")

1. **Issue F — `analytics_engine` bucket filter.** הוסף `stat_bucket` ל-records ב-`_aggregate_campaigns` (`analytics_engine.py:235-267`), פצל ל-`countable_campaigns` לפני WR/Expectancy/PF, ופצל `total_r_net_disc` מ-`total_r_net_algo`. הוסף tests עם fixtures שבהם WR מחוץ ל-ALGO ≠ WR כולל ALGO. ~2 שעות. Owner: Daria + Jordan.

2. **Issue N3 — atomic writes + flock.** החלף את שני ה-writers (`risk_monitor.py:106-107`, `bot_helpers.py:49-66`) ל-`tempfile` + `os.replace`. הוסף `fcntl.flock` סביב ה-RMW ב-`bot_helpers`. עטוף readers ב-`dashboard.py:495` ו-`bot_health.py:121` ב-try/except. multi-thread regression test. ~3 שעות. Owner: Jordan.

3. **`follow_through_score=None` gate (residual §5.3).** ב-`engine_core.py:2024-2046` החלף "None=pass" ב-explicit `age_days < _FT_MIN_DAYS_FOR_SCORE` gating — RUNNER דורש FT מחושב, WORKING מקבל early-life default. 4 unit tests. ~2 שעות. Owner: Jordan.

4. **`original_campaign_risk` consolidation (§4.1).** ב-`adaptive_risk_engine.py:159-175`, בנה inline את ה-row dict עם base_price (weighted), base_qty, init_sl, side, ואז קרא ל-`ec.get_campaign_risk_metrics(_row)`. parametrised test ש-adaptive ו-canonical חוזרים זהים על 5 fixtures. ~1 שעה. Owner: Sarah.

### בינוני

5. **Throttle for new D-alerts (§5.1 side-effect).** הוסף `last_live_price_alert_ts`, `last_missing_stop_alert_ts`, `last_engine_fail_alert_ts` per-symbol, cooldown ≥ 1h. test: yfinance outage 12 cycles → ≤2 alerts. ~1 שעה.

6. **Heat score multiplicative (Sprint 9 P4).** מימוש ההצעה ב-`docs/SPRINT_9_PLAN.md:95-103` עם clamp floor `0.15` (per Mark directive #8). חישוב חוזר של `_build_what_to_improve` / `_build_heat_factors` שמסתמכים על arithmetic decomposition של ה-score הישן.

7. **Defensive NaN guards in `score_position` (§5.8).** `pd.notna()` checks על MA10/MA20/MA50 בתוך `score_position` (`engine_core.py:326-355`), או assert ב-`compute_behavior_features`. ~30 דקות.

8. **Soft-warning ל-stop > 8% (Mark directive #3).** `engine_core.validate_initial_stop_pct(entry, initial_stop, max_pct=0.08)`. wire ב-`telegram_backlog.py` journal flow. ~2 שעות.

9. **tests חסרים (§3):** open_r bonus tiers, giveback severity buckets, ALGO cluster hysteresis. בנוסף — `tests/test_analytics_engine.py::test_algo_excluded_from_win_rate`.

10. **docs hygiene.** עדכן `docs/MODULE_MAP.md:84` (PF sentinel `math.inf`, לא 99.0). עדכן `docs/DATA_CONTRACTS.md` עם enforcement note ל-invariant #8. עדכן `docs/SPRINT_9_PLAN.md` עם ה-RISK_LADDER החדש `[0.25, 0.40, 0.60, 0.85, 1.15, 1.50, 2.00]`.

### ארוך טווח

11. **Atomic-write audit לכל קבצי JSON state.** `sentinel_config.json`, `risk_journal.json`, `risk_recommendations.json`, `ibkr_sync_state.json`, `scheduler_state.json`. ככל הנראה אותו pattern של non-atomic writer קיים ב-2-3 מהם.

12. **Supabase mock בטסטים** — integration tests עם נתונים מציאותיים, replacement של בדיקות grep-only.

13. **yfinance mock בטסטים** — בדיקת כל fallback chain.

14. **bot_core.py startup validation (§5.5)** — בדוק TOKEN/ADMIN_ID קיימים לפני `TeleBot()`. דרוש לקראת Hyperscaler Phase A.

15. **`addon_risk_engine` docstring + test ל-partial sell semantics (§5.9).**

---

## נספח — קבועים מרכזיים (verified V2)

```python
# engine_core.py
ALGO_SYMBOL_LIMITS          = {"QQQ": 10.0, "TSLA": 7.0, "JPM": 7.0, "PLTR": 6.0, "HOOD": 6.0}  # line 13
ALGO_CLUSTER_WARNING_PCT    = 30.0   # line 15
ALGO_CLUSTER_CRITICAL_PCT   = 35.0   # line 16
_R_RUNNER                   = 5.0    # line 1685
_R_PROFIT_PROTECT           = 2.0    # line 1686
_R_WORKING                  = 1.0    # line 1687
_DEAD_MONEY_MIN_DAYS        = 8      # line 1696
_DEAD_MONEY_MIN_R, MAX_R    = -0.5, 0.75
_DEAD_MONEY_FOLLOW_MAX      = 50.0
_VIOLATION_YELLOW_FLAG      = 2
_VIOLATION_BROKEN           = 6
_EVENT_RISK_RED_DAYS        = 3
_EVENT_RISK_ORANGE_DAYS     = 7
_EVENT_RISK_MAX_DAYS        = 15
_FT_MIN_DAYS_FOR_SCORE      = 5      # follow_through returns None when post-entry bars < 5

# adaptive_risk_engine.py — V2 UPDATE: ladder is now 7 steps (was 8 in V1)
RISK_LADDER                 = [0.25, 0.40, 0.60, 0.85, 1.15, 1.50, 2.00]   # line 20
DRAWDOWN_TRIGGER_PCT        = -8.0   # line 27 — 30d NAV trigger (Sprint 8)
DRAWDOWN_CUT_TO_PCT         = 0.40   # line 28 — forced floor after auto-cut
RISK_SETTLE_HOURS           = 48.0   # line 33

# risk_monitor.py
PROFIT_CHECKPOINTS          = [2.0, 3.0]   # line 39
DEVIATION_COOLDOWN_SEC      = 10800        # line 40 — 3h
GIVEBACK_COOLDOWN_SEC       = 21600        # line 41 — 6h
LIVE_ALERT_REPEAT_COOLDOWN  = 2700         # line 42 — 45min
SIZING_LEAK_THRESHOLD       = 0.65         # line 45
STATE_ALERT_COOLDOWN        = {"RUNNER": 4h, "BROKEN": 4h, "DEAD_MONEY": 12h}  # line 48

# addon_risk_engine.py
MIN_OPEN_R_FOR_ADDON        = 1.0
MIN_CUSHION_RATIO           = 0.50
HARD_FLOOR_RATIO            = -0.25
MAX_SIZE_VS_ORIGINAL        = 1.0
MAX_SIZE_VS_CURRENT         = 0.50
DEFAULT_SIZE_RATIO          = 0.40
CHASE_EXT_LIMIT             = 0.07
```
