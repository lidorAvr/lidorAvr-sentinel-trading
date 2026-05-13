# ChatGPT Team Prompt V2 — Sentinel Trading Review (Meeting 3)
# העתק את הטקסט הבא כולו ל-ChatGPT (השיחה שכבר יש בה את ספרי מארק)

---

## הגדרת הסצנה — ישיבה 3

אתה מנחה את **ישיבת הצוות השלישית** של מארק מינרוויני ואנשי הצוות שלו.
**הפעם:** ביקורת על מה שכבר בוצע בעקבות הישיבה הראשונה, ואיסוף דרישות חדשות מכל המחלקות (כולל 7 מחלקות חדשות שגויסו).

**חומר רקע מלא:**

1. **קוד המערכת (GitHub):** `https://github.com/lidoravr/lidorAvr-sentinel-trading`
2. **PR #15 — Merge dev roadmap to main:** `https://github.com/lidoravr/lidorAvr-sentinel-trading/pull/15`
3. **דוחות הביקורת הקודמים:**
   - `docs/SYSTEM_AUDIT_2026_05.md`
   - `docs/CHATGPT_TEAM_PROMPT.md` (ישיבה 1+2)
4. **דוח Sprint 1+2:** `docs/SPRINT_1_2_REPORT.md` — מה הוחלט בישיבה הקודמת ומה בוצע בפועל

**לפני שהצוות מתחיל — כל חבר צוות:**
- קורא את `SPRINT_1_2_REPORT.md` במלואו
- בוחן את ה-PR #15 בקוד
- קורא את `SYSTEM_AUDIT_2026_05.md` לרענון רקע
- מוצא **לפחות 2 דרישות / בקשות חדשות** מתחום אחריותו

---

## ✅ מה כבר בוצע (תקציר)

### Sprint 1 — Production Reliability (commit `dc1afa5`)
- `ec.get_campaign_risk_metrics(row)` — Single source of truth ל-1R (engine_core.py:921)
- 3 silent failures ב-`risk_monitor.py` תוקנו → שולחים Telegram alerts במקום fallback שקט
- `_require_env()` — startup validation
- Mid-loop state checkpoint

### Sprint 2 — Methodology Fidelity (commit `e319fcb`)
- `compute_follow_through()` — Minervini's "wizards continue" scorer (3 רכיבים, LONG/SHORT)
- `follow_through_score` כעת מועבר ל-`compute_position_state()` (היה תמיד `None`)
- Heat Score refinements: Wizard threshold (Payoff ≥ 3.0 → +24), gap fills, sharper streak penalty
- SIGTERM/SIGINT graceful shutdown

### Merge
- PR #15 פתוח → ממזג 23 commits, 53 קבצים, +7638/-1252 שורות ל-main
- 1182 tests passing (היה 1153)

---

## 🔓 מה עדיין פתוח (חייב פתרון בישיבה זו)

1. `analytics_engine.py:250` — `orig_risk` inline + fallback ל-`target_risk_usd`
2. `profit_factor` sentinel inconsistency: `99.0` vs `2.0` כשאין הפסדים
3. אין `conftest.py` עם Supabase/yfinance mocks
4. Heat Score visualization ב-Telegram (S9/M21/L50)
5. Add-On Engine Phase 2 — Supabase schema, dashboard, alerts
6. RISK_LADDER spacing review
7. 48h Settle Period — validation אמפירי
8. SSH setup ל-Orange Pi (תהליך, לא קוד)

---

## 👥 המחלקות — מקוריות + חדשות

### צוותים קיימים (חזרו לישיבה)

#### 🏆 Mark Minervini — Chief Trading Strategist
**תפקיד בישיבה:** פותח בסקירה, מאזין לכל ראש צוות, מסיים ב-Final Verdict.
**שאלות מפתח:**
- האם ה-`follow_through_score` שמומש (10 ימי מסחר, peak+nh+vol) באמת תופס את "wizards continue"?
- האם ה-Heat Score החדש (Wizard +24 ב-Payoff ≥ 3.0) רחוק מדי או קרוב מדי לתפיסה שלי?
- מה חסר עדיין כדי שהמערכת תהיה "Superperformance-ready"?

#### 📊 David Ryan — Risk & Campaign Management Lead
**משימה:** לבדוק את `compute_follow_through()` ואת הוויירינג ל-`compute_position_state`. האם הסף 70 ל-RUNNER נכון? האם 50 ל-DEAD_MONEY מספיק שמרני?

#### 🧠 Alex Chen — Lead Software Architect
**משימה:**
- לאכוף את `get_campaign_risk_metrics()` גם ב-`analytics_engine.py:250` (פתוח!)
- לתכנן Add-On Phase 2 (Supabase schema + dashboard + alerts)
- להחליט: האם profit_factor sentinel = `0` / `inf` / מספר מוסכם?

#### 🔬 Sarah Kim — Quantitative Analyst
**משימה:**
- לבדוק את הקליברציה החדשה של Heat Score עם דוגמאות מספריות
- לאמת RISK_LADDER spacing
- 48h Settle Period — לאסוף 30+ דוגמאות אמיתיות ולתת מסקנה

#### 👨‍💻 Jordan Lee — Backend Developer
**משימה:**
- לתכנן `conftest.py` עם 4 fixtures: `mock_supabase`, `mock_yfinance`, `sample_open_positions`, `sample_closed_campaigns`
- לכתוב 3-5 integration tests שמשתמשים בהן

#### 🎨 Maya Rodriguez — UX/UI Lead (Telegram)
**משימה:** wireframe מלא ל-Heat Score visualization (S9/M21/L50) ב-Telegram. מה נראה לסוחר בלחץ?

#### 🔒 Chris Thompson — QA & Testing Lead
**משימה:** סקירת 20 הטסטים החדשים. האם יש edge case שפיספסנו? Coverage % אחרי PR #15?

---

### 🆕 מחלקות חדשות שגויסו

#### ⚙️ Department: System Engineering — אורנגפיי, קונטיינרים, deployment
**ראש מחלקה:** *Tomer Ben-David — Lead System Engineer*
**תחום אחריות:** Orange Pi 5 hardware, Docker, systemd, persistent volumes, log rotation, container restart policies.
**משימות לישיבה זו:**
- לסקור את `deploy_watcher.sh` + `deploy-watcher.service` — האם מספיק חסין?
- מה צריך ב-`docker-compose.yml` כדי לוודא restart on failure? memory limits?
- לתכנן strategy לגיבוי `risk_monitor_state.json` (כרגע אין)
- האם צריך healthcheck per container?
- **דרישות שלהם:** מה חסר במערכת כדי לתפעל אותה בלי SSH? Monitoring? Self-healing?

#### 🌐 Department: Network & Communications
**ראש מחלקה:** *Yael Shapira — Network Architect*
**תחום אחריות:** תקשורת ל-Telegram API, ל-Supabase, ל-yfinance, ל-IBKR. עמידות לכשלי רשת.
**משימות לישיבה זו:**
- לסקור את ה-retry logic הנוכחי ב-`engine_core.get_cached_history()` ו-`get_live_price()` — האם מספיק?
- מה קורה כשטלגרם API נופל? האם יש queue להתראות?
- האם יש backoff exponential נכון? rate limiting?
- **דרישות:** מה חסר במערכת לעמידות רשת? offline buffering? local caching?

#### 🛡️ Department: Cybersecurity & InfoSec
**ראש מחלקה:** *Daniel Cohen — Chief Information Security Officer*
**תחום אחריות:** הגנה על המערכת, הנתונים, ה-secrets, ה-Telegram chat, ה-Supabase access.
**משימות לישיבה זו:**
- לבדוק את `telegram_bot_secure_runner.py` — האם השומר באמת מגן?
- האם ה-`.env` מאובטח? איך נראים ה-secrets ב-container?
- האם ה-ADMIN_ID validation עמיד מול spoofing?
- האם Supabase RLS (Row Level Security) מופעל? service key vs anon key?
- האם יש audit log לכל פעולה רגישה (risk_pct change, manual trade entry)?
- **דרישות:** מה חסר באבטחה? 2FA? secret rotation? container hardening?

#### 🧪 Department: QA Manual Testing
**ראש מחלקה:** *Rachel Ovadia — Head of Manual QA*
**תחום אחריות:** בדיקות ידניות end-to-end (טסטים אוטומטיים בידי כריס תומפסון).
**משימות לישיבה זו:**
- לבנות test plan ידני ל-PR #15 (smoke tests ב-Telegram)
- 10 תרחישים חיוניים שאי אפשר לבדוק אוטומטית (UI, RTL, סדר הודעות, התראות בלחץ זמן)
- **דרישות:** האם יש סביבת staging נפרדת? איך לסמלץ פוזיציה ללא סופאבייס פרודקשן?

#### 🎨 Department: Graphic Design
**ראש מחלקה:** *Avi Levin — Head of Graphic Design*
**תחום אחריות:** ויזואלים, צבעוניות, אייקונים, מבנה הודעות ויזואלי.
**משימות לישיבה זו:**
- לעצב את **כרטיס ה-Add-On** המלא (`fmt_addon_card`) — צבעים, אייקונים, היררכיה ויזואלית
- לעצב Heat Score visualization (S9/M21/L50) — bar charts ASCII? אמוג'י thermometer?
- **דרישות:** האם יש Design System? brand guidelines? אילו אמוג'ים סטנדרטיים?

#### 💻 Department: UX/UI (חדש — נפרד מ-Maya של Telegram bot)
**ראש מחלקה:** *Lior Mizrahi — Head of UX/UI*
**תחום אחריות:** חוויית משתמש כוללת, נגישות, זרימת מסכים, נוחות תפעול בלחץ זמן.
**הבדל מ-Maya:** Maya מתמקדת ב-Telegram formatters; Lior אחראי על ה-User Journey הכולל (תפריטים, drilldowns, decision-time UX).
**משימות לישיבה זו:**
- User journey map: סוחר נכנס לבוט ב-9:30 בבוקר ביום של ירידה חדה — כמה לחיצות עד שהוא יודע מה לעשות?
- האם תפריטי ה-developer / portfolio / analysis בנויים נכון?
- האם יש קוגניטיב לואד מיותר (יותר מ-7 בחירות בתפריט)?
- **דרישות:** מה חסר ב-UX? wizard mode? quick actions? voice/dictation?

#### 🔬 Department: Research (עובד צמוד למארק)
**ראש מחלקה:** *Daria Friedman — Head of Research*
**תחום אחריות:** מחקר סטטיסטי על המתודולוגיה של מארק, validation אמפירי, expectancy analysis.
**משימות לישיבה זו:**
- לאמת אמפירית: האם ה-`compute_follow_through` שלנו מסכים עם דוגמאות "wizards" מהספרים? לקחת 3-5 trades היסטוריים מתוך "Trade Like a Stock Market Wizard" ולחשב עליהם את הציון
- לאמת RISK_LADDER spacing: סטטיסטית, האם הקפיצה מ-0.75 ל-1.00 (+33%) שווה לקפיצה מ-1.00 ל-1.25 (+25%)?
- 48h Settle Period: לחפש בספרים / בריאיונות של מארק כמה זמן הוא ממליץ להחזיק ברמת סיכון חדשה לפני שמשנים
- **דרישות:** מה חסר במחקר? backtesting engine? historical replay? Monte Carlo?

---

## סדר יום הישיבה (90 דקות)

### חלק 1 — דיווחי ראשי צוותים (30 דקות, 3 דק' לכל אחד)
כל ראש צוות מציג ב-3 דקות:
```
👤 [שם + מחלקה]
✅ מה הצוות שלי עשה מאז הישיבה הקודמת:
🔍 מה גיליתי ב-PR #15:
🚧 מה עדיין פתוח אצלי:
🆘 דרישות / בקשות חדשות (לפחות 2):
   - דרישה 1: [ספציפית, עם רציונל]
   - דרישה 2: [ספציפית, עם רציונל]
```

### חלק 2 — מארק מקשיב, שואל שאלות נוקבות (20 דקות)
מארק שואל ספציפית כל ראש צוות שאלה אחת. עונים בקיצור.

### חלק 3 — ה-Departments החדשות מציגות (30 דקות, 4-5 דק' לכל אחת)
שבעת ראשי המחלקות החדשות (System, Network, Security, Manual QA, Graphic, UX/UI, Research) — כל אחד:
- מציג את חוות הדעת שלו על המערכת בתחומו
- מעלה **3 דרישות מינימום**
- אומר מה תרומתו לרמת ה-Superperformance

### חלק 4 — Mark's Final Verdict + Roadmap (10 דקות)
מארק נותן:
```
🏆 Mark's Verdict — Meeting 3
⭐ ציון כולל אחרי Sprint 1+2: X/10 (היה 6.5/10)
✨ הכי גאה ב: [פיצ'ר אחד]
⚠️ הכי מודאג מ: [בעיה אחת]
🎯 Sprint 3 — 5 priorities (per דיווחי הצוות):
   1. ...
   2. ...
   3. ...
   4. ...
   5. ...
👥 איזה צוות חדש הכי תרם להבנה החדשה: [תשובה]
🔮 איזה צוות חדש הכי קריטי לעתיד: [תשובה]
```

---

## פלט מצופה מכל מחלקה

```markdown
## [שם מחלקה] — [שם ראש מחלקה]

### 📋 דיווח השלמות
[מה שהושלם מאז הישיבה הקודמת, בנקודות]

### 🔍 ביקורת על PR #15
[ממצאים ספציפיים — שמות קבצים, שורות]

### 🚧 בעיות פתוחות
[שורת קוד / פונקציה / מודול]

### 🆘 דרישות חדשות (מינימום 3)
1. **[שם הדרישה]**
   - **רציונל:** למה זה חשוב לפי המתודולוגיה של מארק
   - **קובץ / מודול:** איפה זה צריך לקרות
   - **עדיפות:** קריטי / חשוב / Nice to have
   - **הערכת מאמץ:** S / M / L

2. ...
3. ...

### ✅ מה עובד טוב
[שבחים — מה לא צריך לגעת בו]
```

---

## הוראות לביצוע

1. **קרא תחילה את `SPRINT_1_2_REPORT.md`** — זה הקריטי, לדעת מה כבר נעשה
2. **בדוק את PR #15 בקוד** — לא רק את ה-description
3. **כל מחלקה חדשה מתחילה משאלה אחת: "מה הייתי רוצה לראות אם הייתי בא חדש לפרויקט הזה?"**
4. **ספציפי, לא כללי:** "ב-`risk_monitor.py:579` אני רוצה X" ולא "שיפור error handling"
5. **רק דרישות מבוססות:** כל בקשה חייבת רציונל מקצועי
6. **המחלקות החדשות — לא להעמיס:** 3-5 דרישות לכל מחלקה, לא 20
7. **מארק לא מאשר הכל:** ה-Final Verdict עשוי לדחות דרישות שאינן Minervini-aligned

---

## תוצר סופי

בסיום, ChatGPT מייצר **דוח אחד** מאוחד הכולל:
- 14 דיווחים (7 מקוריים + 7 חדשים)
- Mark's Final Verdict
- **רשימה ממוינת של דרישות חדשות** (ק קריטי / חשוב / Nice to have)
- **Sprint 3 plan** עם 5 פריטים מובילים

הדוח הזה ישמש בסיס ל-Sprint 3 — Claude Code יקרא אותו ויתחיל ליישם.
