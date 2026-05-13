# Sentinel Trading — Design System

**תאריך:** 2026-05-13  
**מטרה:** מסמך אחיד לאייקונים, אמוג'יים וסגנון הודעות טלגרם בכל רחבי המערכת.

---

## עקרונות כלליים

1. **RTL תמיד** — כל הודעה מתחילה בתו `‏` (RTL mark)
2. **Markdown mode** — `parse_mode="Markdown"` בכל הודעה
3. **קצר, ישיר, ניתן לפעולה** — כל הודעה חייבת להסביר מה לעשות
4. **מקור נתונים** — אם נתון הוא fallback/cached — לציין במפורש
5. **ללא emoji עודפים** — emoji אחד לסוג אירוע, עקבי לאורך כל המערכת

---

## 1. מד חום (Heat Thermometer) — S9 / M21 / L50

| ציון | צבע | תווית |
|---|---|---|
| 80–100 | 🔥 | חם מאוד |
| 60–79 | 🟠 | חם |
| 40–59 | 🟡 | מתון |
| 20–39 | 🔵 | קר |
| 0–19 | ❄️ | קר מאוד |

**פורמט בר:**  
```
[██████░░░░] 60/100 — 🟠 חם
```
- בלוקים מלאים: `█`  
- בלוקים ריקים: `░`  
- בר ראשי: 10 בלוקים  
- בר פר-חלון (S9/M21/L50): 5 בלוקים

---

## 2. Position States — Emoji מפת מצבים

| State | Emoji | תווית עברית |
|---|---|---|
| NEW | 🆕 | חדש |
| PROVING | 🔍 | מוכיח |
| WORKING | ✅ | עובד |
| PROFIT_PROTECTION | 🛡️ | הגנת רווח |
| RUNNER | 🏃 | Runner Mode |
| YELLOW_FLAG | 🟡 | דגל צהוב |
| BROKEN | 🔴 | שבור |
| DEAD_MONEY | ⏳ | Dead Money |
| ALGO_OBSERVED | 🤖 | ALGO — פיקוח בלבד |
| DATA_INCOMPLETE | ⚠️ | נתונים חלקיים |

---

## 3. Alert Priority — Actionability Labels

| רמה | Emoji | שימוש |
|---|---|---|
| `action_required` | 🔴 | פעולה נדרשת עכשיו (Broken, Stop Hit) |
| `review_required` | 🟡 | לבדוק לפני יום המסחר הבא |
| `observation_only` | ⚪ | מידע בלבד, ללא פעולה |
| `system_health` | 🔧 | בריאות שירותים פנימיים |
| `external_managed` | 🟠 | ALGO — Sentinel בפיקוח בלבד |

---

## 4. Trailing Stop — Basis Icons

| Basis | Emoji | משמעות |
|---|---|---|
| MA21 | 🎯 | הדק סטופ לאזור MA21 (8R+) |
| MA50 | 📐 | Trailing Stop ב-MA50 (5R+) |
| breakeven | 🔒 | העלה סטופ ל-Breakeven |
| none | ⚠️ | לא ניתן לחשב |

---

## 5. Separators

| שימוש | תו |
|---|---|
| קו הפרדה רגיל | `───────────────` |
| קו הפרדה כפול (חלוקת חלקים) | `〰️〰️〰️〰️〰️〰️〰️〰️〰️` |

---

## 6. Risk Direction Arrows

| כיוון | Arrow |
|---|---|
| הגדל סיכון | ⬆️ |
| שמור | ➡️ |
| הקטן | ⬇️ |
| הקטן מהיר | ⬇️⬇️ |

---

## 7. כללי שפה עברית בהודעות

- **קצרות:** עד 3 שורות עיקריות לכל הודעה
- **ישיר:** "הדק סטופ" לא "ייתכן שכדאי לשקול הדקת הסטופ"
- **מספרים:** `$1,234` (USD) | `1.5R` (R-multiple) | `12.3%` (אחוז)
- **Fallback:** "נתון מוערך — לאמת ב-IBKR" כשאין live data
- **כותרות:** `*bold*` עבור שם הסימול ומצב הפוזיציה
- **ערכים:** `` `monospace` `` עבור מחירים, R, אחוזים

---

## 8. Inline Keyboards — כפתורים סטנדרטיים

| פעולה | טקסט כפתור |
|---|---|
| אישור | ✅ אשר |
| ביטול | ❌ בטל |
| החזקה | ✅ להחזיק |
| הדקת סטופ | 🔒 הדק סטופ |
| מימוש חלקי | 📊 מימוש חלקי |
| חזרה | ⬅️ חזרה |

---

## 9. Healthcheck State Files

כל שירות כותב לקובץ `/app/state/<service>_last_cycle` בסוף כל מחזור:

| שירות | קובץ | מרווח מחזור | max_age |
|---|---|---|---|
| sentinel-bot | `sentinel_bot_last_cycle` | 900s | 1920s |
| telegram-bot | `telegram_bot_last_cycle` | 60s (thread) | 180s |
| risk-monitor | `risk_monitor_last_cycle` | 300s | 720s |
| reporting-service | `report_scheduler_last_cycle` | 60s | 150s |
