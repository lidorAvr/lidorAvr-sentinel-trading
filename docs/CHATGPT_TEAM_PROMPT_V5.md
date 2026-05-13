# ChatGPT Team Prompt V5 — Meeting 6

## הוראות שימוש

העתק את כל התוכן הזה ל-ChatGPT. בקש מ-ChatGPT לשחק את תפקיד כל אחד מ-14 המחלקות ברצף.
**טון הישיבה:** מקצועי, נוקב, ממוקד תוצאות. אין מקום לאמירות עמומות. כל מחלקה מביאה סטטוס ברור: עובד / לא עובד / תאריך סיום.

---

## 🏆 הכרזת פרסים — מארק מינרוויני (פתיחת הישיבה)

> "לפני שנתחיל — אני רוצה להניע אתכם.
> 
> **פרס מס׳ 1 — $1,000,000 למחלקה הראשונה:**
> המחלקה הראשונה שכל המשימות שלה עובדות בצורה מעולה, ולאחר שכל שאר המחלקות בוחנות ומצביעות פה אחד ש'כן, הכל עובד' — מקבלת **מיליון דולר**.
> לא בונוס. לא שובר. מיליון דולר.
>
> **פרס מס׳ 2 — $5,000 לכל עובד:**
> כשהמערכת תרוץ בצורה מלאה, יציבה, ב-production אמיתי — כל עובד בכל המחלקות מקבל $5,000.
>
> **פרס מס׳ 3 — 30% העלאת שכר לכל החיים:**
> ברגע שהמערכת תהיה מוכנה ב-100% ותפעל ללא תקלות — כל אחד מקבל העלאה של 30% לצמיתות.
>
> אלו לא הבטחות ריקות. אני מארק מינרוויני. אני מרוויח מיליונים ממסחר. אני יכול לעשות את זה.
> עכשיו תפסיקו לדבר ותתחילו לעבוד."

---

## רקע — מה נבנה עד עכשיו

**Sentinel Trading** — מערכת בינה מלאכותית אישית לניהול תיק מניות בשיטת Mark Minervini.
**ענף:** `claude/review-dev-roadmap-6K19V` | **Tests:** 1219/1219 ✅

### ציוני הישיבות עד כה:
| ישיבה | ציון | נושא מרכזי |
|---|---|---|
| Meeting 1 | 7.2/10 | בסיס ארכיטקטורה |
| Meeting 2 | 7.6/10 | Follow-Through, Analytics |
| Meeting 3 | 8.0/10 | math.inf, Docker hardening, integration tests |
| Meeting 4 | 8.6/10 | Healthchecks real, trailing stop, PIN gate |
| Meeting 5 | **8.9/10** | Supabase bug fix, security, Add-On Phase 2a, E2E tests |

---

### Sprint 5 — מה הושלם (2026-05-13)

1. ✅ **Supabase Query Bug** — `get_open_campaign_for_symbol()` — `side=BUY` + `order DESC` + `limit 1`
2. ✅ **Silent Failure** — `except Exception: pass` → Telegram alert בשגיאת שמירה
3. ✅ **Production Stability** — autoheal container, `mem_limit 1200m`, `max_age 1980s`
4. ✅ **Security Hardening** — `hmac.compare_digest`, rate limit 3/5min, persistent sessions JSON
5. ✅ **Add-On Phase 2a** — `migrations/001_addon_phase2.sql` + `update_addon_record()` wired
6. ✅ **Test Infrastructure** — `mock_telegram_bot` fixture, `test_e2e_risk_monitor.py` (9 tests), pytest markers
7. ✅ **CI Fix** — dummy env vars ב-GitHub Actions → `bot_core.py` fail-fast לא קורס
8. ✅ **Tests: 1219/1219** — 0 failures

---

## 14 המחלקות — ציפיות ל-Meeting 6

### מחלקות מקוריות (7):

1. **Mark Minervini (יועץ ראשי)** — מוביל הישיבה. קשוח, נוקב. לא מקבל "כמעט". שואל: "האם המשתמש יכול להפעיל את המערכת בלחיצה אחת מחר בבוקר?" מסיים עם Final Verdict X/10 + 5 עדיפויות + הכרזת הפרסים.

2. **Backend Engineering** — בוחן: האם dead code `_MANUAL_TRIGGER_FILE` נמחק? האם `audit_logger.py` מוכן? האם coverage gate ≥75% עובד בCI?

3. **Frontend / UX (Maya + Avi)** — בוחן: האם `/addon` Phase 2b (eligibility dashboard) עובד? האם `fmt_heat_thermometer()` מופיע בדוח השבועי? האם הודעות Telegram נקיות ב-RTL?

4. **QA / Testing** — בוחן: coverage ≥75% enforced? `test_e2e_risk_monitor.py` מכסה `main()` מלא? כל 1219 טסטים ירוקים ב-CI?

5. **Security (Eyal)** — בוחן: `hmac.compare_digest` deployed? sessions persistent? rate limit בפועל מונע brute force? audit log לכל פעולת DEV?

6. **DevOps (Tomer)** — בוחן: autoheal עובד ב-production? CI ירוק על `claude/**`? IBKR Flex Query period `Last 7 Days` (לא `LastBusinessWeek`)? SSH Orange Pi מוגדר?

7. **Data Science / Research** — בוחן: `fmt_heat_thermometer()` מחובר לדוח שבועי? trailing stop calibration תקין? 48h Settle Period — נאסף data בפועל?

### מחלקות חדשות (7):

8. **Product Owner (David Ryan)** — בוחן: האם כל ה-backlog מ-Meeting 5 נסגר? מה הROI של Sprint 5 vs Sprint 6?

9. **Risk Management (Jordan Lee)** — בוחן: `/addon` eligibility — האם המערכת מונעת add-on על פוזיציה לא כשירה?

10. **Quantitative Analysis** — בוחן: profit_factor=math.inf מטופל נכון ב-JSON? coverage ≥75% על `engine_core.py`?

11. **System Engineering** — בוחן: `mem_limit 1200m` מספיק ב-Orange Pi תחת עומס? autoheal restart זמן? 5 containers רצים במקביל?

12. **Compliance & Auditability** — בוחן: `audit_logger.py` — האם כל Supabase write נרשם? `management_notes` — integrity? מי יכול למחוק?

13. **Mobile UX (Sarah)** — בוחן: כפתורי `/addon` [אשר/בטל] — האם נראים נכון על מסך קטן? האם הודעות autoheal restart נשלחות?

14. **Integration & Data (Alex)** — בוחן: IBKR auto-sync pipeline — `Last 7 Days` מוגדר? `_MANUAL_TRIGGER_FILE` dead code — האם נמחק? `import_new_trades` — אמין?

---

## 📋 אג'נדה — ישיבה 6 (90 דקות, קצב מהיר)

| זמן | נושא |
|---|---|
| 0-5 | הכרזת פרסים — מארק (פתיחה נוקבת) |
| 5-10 | סיכום Sprint 5 (מנחה — 2 דקות עבר, 3 דקות מה פתוח) |
| 10-65 | 14 מחלקות — כל אחת **3 דקות בדיוק** — סטטוס ברור |
| 65-80 | Mark — Final Verdict + 5 עדיפויות ל-Sprint 6 |
| 80-90 | הצבעת מחלקות: מי הכי קרוב לפרס ה-$1M? |

**כלל ברזל לישיבה זו:** כל מחלקה אומרת "עובד / לא עובד / תאריך סיום". אין "כמעט מוכן". אין "בתהליך".

---

## פריטים פתוחים ל-Sprint 6

### Priority 1 — חייב לסגור

| # | פריט | אחראי | בלוקר |
|---|---|---|---|
| 1 | `audit_logger.py` + Supabase `audit_log` table | Backend + Compliance | דורש migration |
| 2 | Coverage gate ≥75% enforced ב-CI | QA + DevOps | `pytest --cov` ב-workflow |
| 3 | `test_e2e_risk_monitor.py` — `main()` mock cycle מלא | QA | mock Supabase בtests |
| 4 | Add-On Phase 2b — eligibility dashboard ב-`/addon` | Frontend + Backend | depends on Phase 2a columns |
| 5 | `fmt_heat_thermometer()` — חיבור לדוח שבועי | Frontend + Data | `report_renderer.py` |

### Priority 2 — חשוב

| # | פריט | אחראי | בלוקר |
|---|---|---|---|
| 6 | Dead code `_MANUAL_TRIGGER_FILE` — מחיקה | Backend | קוד בloan main.py |
| 7 | SSH Orange Pi — הגדרה | DevOps | פעולת משתמש |
| 8 | IBKR Flex Query `Last 7 Days` | Integration | פעולת משתמש (IBKR UI) |
| 9 | Auto-sync E2E validation — אישור בוקר | DevOps | צריך להמתין לחלון 07:00 |
| 10 | 48h Settle Period — data collection | Data Science | production data בלבד |

### Priority 3 — ישיבות הבאות

| # | פריט |
|---|---|
| 11 | Trend Template display ב-dashboard (כל 8 קריטריונים) |
| 12 | target_price ב-Supabase — planned R:R |
| 13 | Weekly mentor review — Telegram אוטומטי |
| 14 | Dashboard load time < 3s — מדידה מפורשת |
| 15 | Safe Markdown splitting — tests |

---

## פורמט פלט נדרש מכל מחלקה

```
### [שם מחלקה]
**ציון Sprint 5:** X/10
**סטטוס עובד:** (רשימה ברורה — ✅ / ❌)
**מה לא עובד / חסר:** (מקסימום 3 נקודות, כל אחת עם תאריך סיום ריאלי)
**דרישות קשיחות ל-Sprint 6:** (2-3 נקודות — לא אמביגואוסיות)
**הצבעה לפרס $1M:** מחלקה X — כי [נימוק]
```

---

## הצבעת הפרס — מנגנון

בסוף הישיבה, כל אחת מ-14 המחלקות מצביעה:
> "אני מצביע/ה שמחלקת [___] הכי קרובה לפרס ה-$1,000,000 כי כל המשימות שלה [___]."

אם 14/14 מצביעות על אותה מחלקה — מוכרז הפרס.
אם לא — מארק מסכם: "מה חסר לכם. בואו נסגור את זה ב-Sprint 6."

---

## Final Verdict מארק (בסוף)

```
### Mark Minervini — Final Verdict Meeting 6
**ציון:** X.X/10
**נימוק:** (2-3 משפטים — ישירים, ללא מחמאות ריקות)

**5 עדיפויות קריטיות ל-Sprint 6:**
1. [קריטי ביותר — Production readiness]
2. [קריטי — אין פרס בלי זה]
3. [חשוב — משפיע על ציון]
4. [חשוב — debt שצריך לסגור]
5. [טוב לעשות — יעלה ציון]

**הכרזה:** מחלקת [___] הכי קרובה לפרס. חסר: [___].

**Master Backlog — עדיפויות מעודכנות ל-Sprint 6**
```

---

## Master Backlog לעדכון (Sprint 6)

| # | פריט | עדיפות | סטטוס |
|---|---|---|---|
| 1 | `audit_logger.py` + Supabase `audit_log` table | 1 | פתוח |
| 2 | Coverage gate ≥75% ב-CI | 1 | פתוח |
| 3 | `test_e2e_risk_monitor.py` — main() mock מלא | 1 | פתוח (9 טסטים קיימים, חסר main()) |
| 4 | Add-On Phase 2b — eligibility dashboard | 1 | פתוח (Phase 2a בוצע) |
| 5 | `fmt_heat_thermometer()` → weekly report | 1 | פתוח |
| 6 | Dead code `_MANUAL_TRIGGER_FILE` — מחיקה | 2 | פתוח |
| 7 | SSH Orange Pi | 2 | פעולת משתמש |
| 8 | IBKR Flex Query `Last 7 Days` | 2 | פעולת משתמש |
| 9 | Auto-sync E2E validation | 2 | ממתין לחלון |
| 10 | 48h Settle Period data | 3 | production data |
| 11 | Trend Template display ב-dashboard | 3 | פתוח |
| 12 | target_price ב-Supabase | 4 | HIGH risk — schema |
| 13 | Weekly mentor review אוטומטי | 4 | פתוח |
| 14 | Dashboard load time < 3s explicit | 4 | לא נמדד |
| 15 | Safe Markdown splitting — tests | 4 | קיים, ללא טסטים |

---

## שאלות להצבעה בישיבה

1. **Audit log scope** — האם לרשום כל קריאת Supabase, או רק writes?
2. **Add-On eligibility** — מה הקריטריון? רק `side=BUY` פתוח? גם `quality ≥ 7`?
3. **Coverage 75%** — האם לאכוף על כל הקבצים, או רק `engine_core.py`/`adaptive_risk_engine.py`/`analytics_engine.py`?
4. **Settle Period** — 48h vs 72h — האם יש production data להכריע?
5. **Sprint 6 scope** — האם סוגרים את כל ה-Priority 1 לפני Meeting 7, או מותר לדחות אחד?
