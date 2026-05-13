# ChatGPT Team Prompt V4 — Meeting 5

## הוראות שימוש

העתק את כל התוכן הזה ל-ChatGPT. בקש מ-ChatGPT לשחק את תפקיד כל אחד מ-14 המחלקות ברצף, ולהגיב לממצאי Sprint 4 לפני ה-Verdict הסופי של מארק.

---

## רקע — מה נבנה עד עכשיו

**Sentinel Trading** — מערכת בינה מלאכותית אישית לניהול תיק מניות בשיטת Mark Minervini.  
**ענף:** `claude/review-dev-roadmap-6K19V` | **PR #15:** לא merge עדיין (main ב-`e57aa5b`)

### Sprint 4 — מה הושלם (2026-05-13)

1. ✅ **Real Healthchecks** — 4 שירותים עם mtime-based liveness probes (לא עוד fasade)
2. ✅ **GitHub Actions CI** — `claude/**` branch מכוסה
3. ✅ **Trailing Stop לסטייט RUNNER** — `compute_suggested_trail_stop()` + wiring
4. ✅ **fmt_heat_thermometer()** — S9/M21/L50 visual bar + labels
5. ✅ **`/addon` inline keyboard [אשר/בטל]** + שמירה ב-Supabase
6. ✅ **Developer menu PIN gate** — `DEV_PIN` env, 30-min session
7. ✅ **`ADMIN_ID > 0` validation** — fail-fast ב-bot_core.py
8. ✅ **docs/DESIGN_SYSTEM.md** — emoji/icon palette + healthcheck table
9. ✅ **Tests: 1203/1203** (+6 trailing stop, +6 healthcheck — real rm._touch_heartbeat, not mock)
10. ✅ **PR #15 → main** — merged

### ספרינטים קודמים (לרקע):

- Sprint 1 (Meeting 1): ציון 7.2/10 — מחלקות ראשונות, בסיס הארכיטקטורה
- Sprint 2 (Meeting 2): ציון 7.6/10 — Add-On engine, Follow-Through, Analytics
- Sprint 3 (Meeting 3): ציון 8.0/10 — math.inf, get_campaign_risk_metrics, Docker hardening, Integration tests
- Sprint 4 (Meeting 4): ציון 8.6/10 → **Sprint 4 הנוכחי**

---

## 14 המחלקות — תפקיד ופוקוס לכל ישיבה

### מחלקות מקוריות (7):

1. **Mark Minervini (יועץ ראשי)** — בוחן alignment עם SEPA methodology, אקספוז'ר, R-multiples, wizard-grade performance. מוסיף Final Verdict ציון X/10 עם נימוק.

2. **Backend Engineering** — בוחן ארכיטקטורה Python, edge cases, circular imports, type safety, async patterns.

3. **Frontend / UX (Maya + Avi)** — בוחנת חוויית משתמש בטלגרם: RTL, קצרות הודעות, ויזואליזציות, כפתורים, תגובה ל-user errors.

4. **QA / Testing** — בוחנת coverage, test isolation, fixtures, integration vs unit, pytest markers, edge cases.

5. **Security (Eyal)** — בוחן הרשאות, env var validation, admin gate, PIN sessions, Supabase write-safety.

6. **DevOps (Tomer)** — בוחן Docker (healthchecks, volumes, logging, mem_limit), CI/CD, deployment rollback.

7. **Data Science / Research** — בוחנת איכות מודלים: calibration, backtesting, R-distribution, trailing stop logic, MA thresholds.

### מחלקות חדשות (7):

8. **Product Owner (David Ryan)** — בוחן product roadmap, user stories, backlog prioritization, ROI vs effort.

9. **Risk Management (Jordan Lee)** — בוחן risk ladder, payoff ratio, drawdown limits, Kelly criterion alignment.

10. **Quantitative Analysis** — בוחנת profit factor, expectancy, Sharpe, win-rate significance testing.

11. **System Engineering** — בוחן reliability, failover, memory/CPU budgets, Orange Pi constraints.

12. **Compliance & Auditability** — בוחנת audit trail, הקלטת החלטות, management_notes integrity.

13. **Mobile UX (Sarah)** — בוחנת חוויית הטלגרם על מסך קטן: קיצור הודעות, כפתורים, RTL edge cases.

14. **Integration & Data (Alex)** — בוחן IBKR sync reliability, Supabase schema, yfinance cache, external API fallbacks.

---

## אג'נדה המפגש — 90 דקות

| זמן | נושא |
|---|---|
| 0-10 | סיכום Sprint 4 (מנחה מציג) |
| 10-60 | 14 מחלקות — כל אחת 3-4 דקות |
| 60-75 | Mark Minervini — Final Verdict + 5 עדיפויות ל-Sprint 5 |
| 75-90 | Master Backlog — עדכון ציוני עדיפות |

---

## Sprint 4 — תיאור לבחינה לכל מחלקה

### Healthchecks Real (תיקון healthcheck-fasade)
- **קודם:** `sys.exit(0)` תמיד — 4/5 שירותים לא נבדקים בפועל
- **עכשיו:** כל שירות כותב `/app/state/<service>_last_cycle` בסוף כל מחזור
- Docker healthcheck: `time.time() - mtime < max_age`
- max_age: sentinel-bot=1920s, telegram-bot=180s, risk-monitor=720s, reporting=150s
- telegram-bot משתמש ב-daemon thread (כי infinity_polling() חוסם)

### Trailing Stop לסטייט RUNNER
```python
# engine_core.py
def compute_suggested_trail_stop(side, current_price, ma21, ma50, open_r, entry_price):
    # >= 8R → trail under MA21 (2% buffer)
    # >= 5R → trail under MA50 (2% buffer)  
    # fallback → breakeven
```
- מחובר ל-`risk_monitor.py:_runner_state_alert()` — מוצג בהתראת Runner
- 6 טסטים unit (LONG/SHORT, 5R/8R, priority, fallback)

### fmt_heat_thermometer()
```
[██████░░░░] 60/100 — 🟠 חם
  S9  [████░] 78  M21 [███░░] 60  L50 [██░░░] 44
  Win Rate — S9: 67% | L50: 58%
  ⬆️ סיכון מומלץ: 0.75%
```
- 10 בלוקים ראשיים, 5 בלוקים לחלון
- `_score_to_bar()`, `_heat_label()` — pure functions

### /addon Keyboard [אשר/בטל]
- user_state שומר pending plan
- callback `addon_confirm|YES|SYMBOL|entry|stop|qty`
- אישור: `repo.update_management_notes(supabase, cid, note)`

### Developer PIN Gate
- `DEV_PIN` env var
- state `awaiting_dev_pin` → PIN → session 30 min
- `dev_pin_session_active(chat_id)` בכניסה לתפריט
- `ADMIN_ID <= 0` → SystemExit

---

## פורמט פלט נדרש מכל מחלקה

```
### [שם מחלקה]
**ציון Sprint 4:** X/10
**מה עבד:** (2-3 נקודות)
**מה חסר / בעיות שנותרו:** (2-3 נקודות)
**דרישות ל-Sprint 5:** (2-3 נקודות מדויקות)
```

---

## Final Verdict מארק (בסוף)

```
### Mark Minervini — Final Verdict Meeting 5
**ציון:** X.X/10
**נימוק:** (2-3 משפטים)
**5 עדיפויות קריטיות ל-Sprint 5:**
1. ...
2. ...
3. ...
4. ...
5. ...
**Master Backlog — 40 פריטים עם עדיפויות מעודכנות**
```

---

## Master Backlog לעדכון

להלן הבאקלוג הנוכחי. בקש מה-ChatGPT לעדכן ציוני עדיפות (1=גבוה ביותר):

| # | פריט | עדיפות קיימת | סטטוס |
|---|---|---|---|
| 1 | Merge PR #15 → main | 1 | ✅ בוצע |
| 2 | E2E test test_e2e_risk_monitor.py | 2 | פתוח |
| 3 | Coverage gate ≥75% (pytest-cov) | 2 | פתוח |
| 4 | Add-On Phase 2 Supabase schema | 2 | פתוח |
| 5 | 48h Settle Period — empirical validation | 3 | פתוח |
| 6 | SSH setup Orange Pi | 3 | פעולת משתמש |
| 7 | mock_telegram_bot fixture בconftest.py | 3 | פתוח |
| 8 | fmt_heat_thermometer חיבור לדוח שבועי | 3 | פתוח |
| 9 | Audit log table Supabase + audit_logger.py | 3 | פתוח |
| 10 | autoheal container ב-docker-compose.yml | 4 | פתוח |
| 11 | mem_limit 1536m → 1200m + 1GB swap | 4 | פתוח |
| 12 | pytest markers על 1201 הטסטים הקיימים | 4 | פתוח |
| 13 | Safe Markdown splitting — testing | 4 | קיים, ללא טסטים |
| 14 | /addon Phase 2 — eligibility dashboard | 4 | פתוח |
| 15 | DEV_PIN ב-.env — PIN לתפריט מפתח | 5 | יעד עתידי (לא דחוף) |

---

## שאלות פתוחות לצוות

1. **MA buffer 2%** — האם 2% מתחת ל-MA21/MA50 הוא ה-buffer הנכון ל-trailing stop?
2. **PIN session 30 min** — האם מספיק? האם צריך refresh אוטומטי?
3. **healthcheck max_age sentinel-bot=1920s** — LOOP_INTERVAL=900s × 2 + 120s. נראה סביר?
4. **Add-On Phase 2** — האם Supabase schema נדרש לפני שמייצרים dashboard?
5. **E2E tests** — mock Supabase או test DB נפרד?
