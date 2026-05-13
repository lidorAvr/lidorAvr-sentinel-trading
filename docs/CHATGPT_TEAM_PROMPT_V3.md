# ChatGPT Team Prompt V3 — Sentinel Trading Review (Meeting 4)
# העתק את הטקסט הבא כולו ל-ChatGPT (השיחה שכבר יש בה את ספרי מארק)

---

## הגדרת הסצנה — ישיבה 4

אתה מנחה את **ישיבת הצוות הרביעית** של מארק מינרוויני ואנשי הצוות שלו (14 ראשי מחלקות).
**הפעם:** ביקורת על מה שבוצע ב-Sprint 3 בעקבות Meeting 3 (Final Verdict 8.0/10), ואיסוף דרישות חדשות לקראת Sprint 4.

**חומר רקע מלא:**

1. **קוד המערכת (GitHub):** `https://github.com/lidoravr/lidorAvr-sentinel-trading`
2. **PR #15 — Merge dev roadmap to main:** `https://github.com/lidoravr/lidorAvr-sentinel-trading/pull/15`
3. **דוחות ישיבות קודמות:**
   - `docs/SYSTEM_AUDIT_2026_05.md` — סקירת מערכת מקיפה
   - `docs/CHATGPT_TEAM_PROMPT.md` — ישיבות 1+2 (סקירה ראשונית)
   - `docs/CHATGPT_TEAM_PROMPT_V2.md` — ישיבה 3 (14 מחלקות, 7 חדשות)
4. **דוחות Sprint:**
   - `docs/SPRINT_1_2_REPORT.md` — מה הוחלט בישיבות 1+2 ובוצע
   - `docs/SPRINT_3_REPORT.md` — מה הוחלט בישיבה 3 ובוצע (חדש!)

**לפני שהצוות מתחיל — כל חבר צוות:**
- קורא את `SPRINT_3_REPORT.md` במלואו
- בוחן את 6 ה-commits של Sprint 3 (b050534..06e002f)
- קורא את Mark's Final Verdict מ-Meeting 3 (8.0/10)
- מוצא **לפחות 2 דרישות / בקשות חדשות** מתחום אחריותו

---

## ✅ מה כבר בוצע בעקבות Meeting 3 — Sprint 3 (1182 → 1191 tests)

### Step 1 — PR #15 Rebase
- Branch `claude/review-dev-roadmap-6K19V` סונכרן מול main
- Conflicts ב-docs (טבלאות markdown) — נפתרו עם `--ours`
- `git push --force-with-lease` ב-`ea56e98`

### Step 2 — Calibration Patches (`b050534`)
| שינוי | קובץ:שורה | היה → עכשיו |
|---|---|---|
| FT peak threshold | `engine_core.py:1767` | 10.0 → **7.0** (wizard threshold אמפירי) |
| Payoff < 0.8 penalty | `adaptive_risk_engine.py:228` | -12 → **-15** (Mark's red line) |
| RISK_LADDER spacing | `adaptive_risk_engine.py:20` | 8 פריטים → **7 פריטים** uniform cadence |
| profit_factor sentinel | 3 מקומות | 99.0/2.0 → **`math.inf`** + JSON safety |

### Step 3 — Single Source of Truth (`319e3a8`)
- `analytics_engine.py:250` עבר מ-inline calculation ל-`ec.get_campaign_risk_metrics()`
- תומך LONG + SHORT + fallback ל-`target_risk_usd`
- 2 טסטים חדשים ב-`TestAggregateGetCampaignRiskMetrics`

### Step 4 — Security: bot_core.py (`fc37d8b`)
- Fail-fast validation בהשרצה:
  - `TELEGRAM_BOT_TOKEN` — חובה
  - `TELEGRAM_ADMIN_ID` — חובה int (ולא str!)
  - `SUPABASE_URL` + `SUPABASE_KEY` — חובה
- מונע `TeleBot(None)` crashes ו-`int(None)` TypeErrors

### Step 5 — Production Hardening: docker-compose.yml (`e8ea7dc`)
- `mem_limit: 1536m` × 5 services (מונע OOM ב-Orange Pi)
- `logging: json-file 10m × 5` (מונע disk runaway)
- `healthcheck` × 5 services (30s interval, retries 3)
- Named volume `sentinel_state` עבור `risk-monitor` (state file שורד restart)

### Step 6+7 — Test Infrastructure (`13ae107`)
- `tests/conftest.py` — 4 fixtures משותפים (`mock_supabase`, `mock_yfinance`, `sample_open_positions`, `sample_closed_campaigns`)
- `tests/test_integration.py` — 7 cross-module tests:
  - 2 × Analytics calls `get_campaign_risk_metrics`
  - 3 × Follow-through wired to position state
  - 2 × Snapshot store inf serialization

### Step 8 — Coverage Tooling (`794814f`)
- `pytest-cov` ב-`requirements-dev.txt`
- pytest markers: `unit / integration / slow`
- Stray 99.0 assertion ב-`test_calculations_comprehensive.py` תוקן

### Docs Update (`06e002f`)
- `docs/SPRINT_3_REPORT.md` חדש
- `docs/ROADMAP.md` Phase 8 → complete

**סה"כ Sprint 3:** 7 commits, +9 tests (1182 → 1191), 0 failures, 12 קבצי קוד שונו, 2 קבצי טסט חדשים, 2 docs.

---

## 🔓 מה עדיין פתוח (חייב פתרון בישיבה זו)

| # | משימה | קובץ / מודול | מי מטפל | בלוק? |
|---|---|---|---|---|
| 1 | Heat Score visualization (S9/M21/L50) | `telegram_formatters.py` (`fmt_heat_thermometer`) | Maya + Avi | UX design |
| 2 | Add-On Engine Phase 2 | Supabase schema + dashboard + alerts | Alex + David | רחב-היקף |
| 3 | 48h Settle Period — empirical validation | מחקר | Sarah + Daria | זקוק production data |
| 4 | SSH setup ל-Orange Pi | תהליך הפעלה | משתמש | פעולת אדם |
| 5 | Safe Markdown splitting | `telegram_portfolio.py` | Jordan | low effort |
| 6 | Developer menu PIN gate | `telegram_devops.py` | Daniel (Security) | low effort |
| 7 | `docs/DESIGN_SYSTEM.md` — emoji palette | docs/ | Avi + Maya | docs only |

---

## 👥 המחלקות — דיווח Sprint 3 + דרישות לקראת Sprint 4

### צוותים קיימים (7)

#### 🏆 Mark Minervini — Chief Trading Strategist
**תפקיד בישיבה:** סוקר את Sprint 3, מאזין לכל ראש צוות, נותן Verdict סופי.
**שאלות מפתח:**
- האם ה-7.0 wizard threshold תופס את הסוחרים שאני עוקב אחריהם בספרים?
- האם RISK_LADDER החדש (`[0.25..2.00]`) באמת מונוטוני יותר מהקודם?
- האם המערכת מוכנה להיכנס לסטטוס "Superperformance-ready" אחרי Sprint 4?
- מה הצעד הבא ל-Heat Score visualization?

#### 📊 David Ryan — Risk & Campaign Management Lead
**משימה:**
- לסקור את הקליברציה של 7.0 / -15 / RISK_LADDER — האם הקצוות נכונים?
- לתכנן Add-On Phase 2 architecture (איך alerts ישתלבו עם state machine)
- לבקש: מה חסר ב-`compute_position_state` כדי להפוך לחלוטין Minervini-spec?

#### 🧠 Alex Chen — Lead Software Architect
**משימה:**
- לסקור את החלוקה השכבתית אחרי Sprint 3 — האם conftest.py / integration tests / docker hardening באמת מספיקים?
- לתכנן Add-On Phase 2 — Supabase schema, dashboard layout, alert flow
- להחליט: האם להוסיף `analytics_engine` ל-coverage gate? מה אחוז coverage המינימלי הגיוני?

#### 🔬 Sarah Kim — Quantitative Analyst
**משימה:**
- לאמת אמפירית את 7.0 wizard threshold על 5+ wizard trades מהספרים
- לחשב distribution של profit_factor — מתי באמת אין הפסדים? כמה פעמים זה קורה?
- 48h Settle Period — מצא את ה-N הנדרש (כמה דוגמאות אמיתיות יש לנו עכשיו?)

#### 👨‍💻 Jordan Lee — Backend Developer
**משימה:**
- לתכנן Safe Markdown splitting ב-`telegram_portfolio.py` (כעת ידוע שהודעות > 4096 נכשלות)
- להרחיב את `conftest.py` עם fixtures נוספים: `mock_telegram_bot`, `mock_ibkr_xml`
- לבקש: מה חסר בכלי הפיתוח? CI/CD על GitHub Actions?

#### 🎨 Maya Rodriguez — UX/UI Lead (Telegram)
**משימה:** wireframe מלא ל-`fmt_heat_thermometer()`:
- מה צריך להופיע (S9/M21/L50)?
- אילו אמוג'ים? איך RTL מתנהג עם bar charts?
- כמה שורות מקסימום?

#### 🔒 Chris Thompson — QA & Testing Lead
**משימה:**
- סקירת 9 הטסטים החדשים ב-Sprint 3 (TestAggregateGetCampaignRiskMetrics + 7 integration)
- האם integration tests מכסים את הכשלים האמיתיים שראינו ב-production?
- לבדוק coverage % אחרי Sprint 3 ולהציע יעדים ל-Sprint 4

---

### מחלקות חדשות (7) — דיווח מ-Meeting 3 + דרישות חדשות

#### ⚙️ Tomer Ben-David — System Engineering
**Sprint 3 השלמה:**
- ✅ `mem_limit: 1536m` × 5 services
- ✅ Log rotation (`max-size: 10m, max-file: 5`)
- ✅ `healthcheck` per service
- ✅ Named volume `sentinel_state`
**משימה לישיבה זו:**
- האם healthchecks באמת תופסים crashes? לבדוק עם dry-run
- מה חסר עוד? auto-restart על healthcheck failure? Watchtower?
- **דרישות:** monitoring stack (Prometheus + Grafana)? log aggregation (Loki)?

#### 🌐 Yael Shapira — Network Architect
**Sprint 3 השלמה:** אין (לא הוגדר ל-Sprint 3)
**משימה לישיבה זו:**
- לסקור את `engine_core.get_cached_history()` — האם cache invalidation נכון?
- מה קורה אם Supabase לא מגיב 30 שניות? האם יש circuit breaker?
- **דרישות:** offline queue להתראות טלגרם? local cache ל-yfinance?

#### 🛡️ Daniel Cohen — Cybersecurity / InfoSec
**Sprint 3 השלמה:**
- ✅ `bot_core.py` fail-fast (token + admin_id int + supabase keys)
**משימה לישיבה זו:**
- האם `int(TELEGRAM_ADMIN_ID)` מספיק להגנה מ-spoofing? צריך גם signature?
- האם Supabase service_key חשוף? איך הוא ב-container?
- **דרישות:** Developer menu PIN gate (TASK פתוח), secret rotation policy, audit log

#### 🧪 Rachel Ovadia — Manual QA
**Sprint 3 השלמה:** אין (לא הוגדר ל-Sprint 3)
**משימה לישיבה זו:**
- לבנות smoke test plan ידני ל-Sprint 3 (טלגרם flows שהשתנו: heat factor display עם ∞)
- האם יש סביבת staging? איך לבדוק את ה-named volume?
- **דרישות:** staging environment, test data generator, regression checklist

#### 🎨 Avi Levin — Graphic Design
**Sprint 3 השלמה:** אין (לא הוגדר ל-Sprint 3)
**משימה לישיבה זו:**
- לעצב את `fmt_heat_thermometer()` ויזואלית (אמוג'י thermometer? bar chart?)
- לסיים את `docs/DESIGN_SYSTEM.md` — אילו אמוג'ים מותרים ובאילו contexts?
- **דרישות:** brand identity מסמך, color palette, icon library

#### 💻 Lior Mizrahi — UX/UI (User Journey)
**Sprint 3 השלמה:** אין (לא הוגדר ל-Sprint 3)
**משימה לישיבה זו:**
- User Journey: סוחר בלחץ של 30 שניות לראות hot positions — האם זרימת התפריט נכונה?
- האם יש "quick action" mode לסוחר ב-9:30 בבוקר?
- **דרישות:** wizard mode, quick actions buttons, dark/light theme

#### 🔬 Daria Friedman — Research
**Sprint 3 השלמה:**
- ✅ wizard threshold 10% → 7% (validated empirically ב-ACME)
- ✅ RISK_LADDER spacing review (uniform cadence)
**משימה לישיבה זו:**
- לאמת על 5+ wizards מהספרים: NVDA 2023, AAPL 2004, AAPL 2020 — האם הציון שלהם > 70 ב-`compute_follow_through`?
- 48h Settle Period: לחפש בספרים של מארק כמה זמן מומלץ
- **דרישות:** backtesting engine, historical replay tool, Monte Carlo simulator

---

## סדר יום הישיבה (90 דקות)

### חלק 1 — דיווחי Sprint 3 (30 דקות)
כל ראש צוות מציג ב-3 דקות:
```
👤 [שם + מחלקה]
✅ מה הצוות שלי השלים ב-Sprint 3:
🔍 ביקורת על Sprint 3 (ספציפי — שמות קבצים, שורות, commit hash):
🚧 מה עדיין פתוח אצלי:
🆘 דרישות חדשות לקראת Sprint 4 (לפחות 2):
   - דרישה 1: [ספציפית, עם רציונל]
   - דרישה 2: [ספציפית, עם רציונל]
```

### חלק 2 — מארק מקשיב, שואל שאלות (20 דקות)
מארק שואל ספציפית כל ראש צוות שאלה אחת. עונים בקיצור.

### חלק 3 — דיון פתוח (20 דקות)
- היכן ה-test count צריך להיות בסוף Sprint 4? (יעד מוצע: 1250+)
- אילו דרישות חופפות בין מחלקות (Add-On Phase 2 משתתפים: David, Alex, Maya, Avi)?
- האם Sprint 4 צריך להתמקד ב-features או ב-stability?

### חלק 4 — Mark's Final Verdict + Sprint 4 Roadmap (20 דקות)
מארק נותן:
```
🏆 Mark's Verdict — Meeting 4
⭐ ציון כולל אחרי Sprint 3: X/10 (היה 8.0/10 ב-Meeting 3)
✨ הכי גאה ב: [פיצ'ר אחד]
⚠️ הכי מודאג מ: [בעיה אחת]
🎯 Sprint 4 — 5 priorities:
   1. ...
   2. ...
   3. ...
   4. ...
   5. ...
👥 איזה צוות הכי הוכיח את עצמו ב-Sprint 3: [תשובה]
🔮 איפה ייפתחו ה-bottlenecks ב-Sprint 4: [תשובה]
🚀 מתי המערכת תהיה Superperformance-ready: [תשובה]
```

---

## פלט מצופה מכל מחלקה

```markdown
## [שם מחלקה] — [שם ראש מחלקה]

### 📋 דיווח Sprint 3
[מה שהושלם, עם commit hashes / file:line]

### 🔍 ביקורת על Sprint 3
[ממצאים ספציפיים — שמות קבצים, שורות, hashes]

### 🚧 בעיות פתוחות אצלי
[שורת קוד / פונקציה / מודול]

### 🆘 דרישות חדשות (מינימום 2)
1. **[שם הדרישה]**
   - **רציונל:** למה זה חשוב לפי המתודולוגיה של מארק
   - **קובץ / מודול:** איפה זה צריך לקרות
   - **עדיפות:** קריטי / חשוב / Nice to have
   - **הערכת מאמץ:** S / M / L
   - **תלות:** באילו דרישות אחרות זה תלוי?

2. ...

### ✅ מה עובד טוב ב-Sprint 3
[שבחים — מה לא צריך לגעת בו]
```

---

## הוראות לביצוע

1. **קרא תחילה את `SPRINT_3_REPORT.md`** — זה הקריטי, לדעת מה כבר נעשה ב-Sprint 3
2. **בדוק את 6 ה-commits של Sprint 3** — b050534 (calibration), 319e3a8 (analytics migration), fc37d8b (bot_core), e8ea7dc (docker), 13ae107 (conftest+integration), 794814f (pytest-cov)
3. **כל מחלקה מתחילה משאלה אחת:** "מה Sprint 3 שיפר אצלי? מה עדיין חסר?"
4. **ספציפי, לא כללי:** "ב-`adaptive_risk_engine.py:228` אני רוצה X" ולא "שיפור penalty system"
5. **רק דרישות מבוססות:** כל בקשה חייבת רציונל מקצועי
6. **מארק לא מאשר הכל:** ה-Final Verdict עשוי לדחות דרישות שאינן Minervini-aligned
7. **חוצה-מחלקות:** דרישות עם תלויות בין מחלקות חייבות להיות מסומנות

---

## תוצר סופי

בסיום, ChatGPT מייצר **דוח אחד** מאוחד הכולל:

1. **14 דיווחים** (7 מקוריים + 7 חדשים) — כולל ביקורת על Sprint 3 + דרישות חדשות
2. **Mark's Final Verdict** עם ציון 0-10 (היעד: ≥ 9.0)
3. **רשימה ממוינת של דרישות חדשות** עם תלויות (קריטי / חשוב / Nice to have)
4. **Sprint 4 plan** עם 5 פריטים מובילים — כל פריט עם:
   - שם
   - מי מטפל (departments)
   - קבצים מעורבים
   - הערכת מאמץ (S/M/L)
   - תלויות
5. **רשימת פריטים שנדחו** עם נימוק (Mark's call)
