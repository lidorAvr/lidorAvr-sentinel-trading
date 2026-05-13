# Sprint 5 — דוח השלמת עבודה

**תאריך:** 2026-05-13  
**ענף:** `claude/review-dev-roadmap-6K19V`  
**מצב:** ✅ הושלם — 1219/1219 tests passing (היה 1210 לפני Sprint 5)

---

## רקע

לאחר ישיבת הצוות החמישית (Meeting 5) עם מארק מינרוויני וצוותו (14 מחלקות, ציון סופי **8.9/10**), ביקשנו לסגור את כל העדיפויות ולשחרר גרסה יציבה בטרם נמשיך לישיבה הבאה. דוח זה מסכם את Sprint 5.

---

## 🔧 Step 1 — תיקון Supabase Query Bug (Priority 1)

**קובץ:** `supabase_repository.py` + `telegram_callbacks.py`  
**בעיה:** שאילתת `/addon` אישור לא סיננה לפי `side=BUY` ולא מיינה — יכלה להחזיר קמפיין סגור/ישן.

**פתרון:**
- נוספה `get_open_campaign_for_symbol(sb, symbol)` — מסננת `side=BUY`, ממיינת `trade_date DESC`, מגבילה ל-1
- ה-callback משתמש בפונקציה החדשה במקום בשאילתה הישנה

---

## 🔕 Step 2 — תיקון Silent Failure (Priority 2)

**קובץ:** `telegram_callbacks.py`  
**בעיה:** `except Exception: pass` בלוק addon_confirm — שגיאת Supabase נבלעת בשקט.

**פתרון:**  
- שגיאה ראשית → הודעת Telegram "⚠️ שגיאה בשמירת Add-On"  
- קמפיין לא נמצא → הודעת Telegram "⚠️ לא נמצא קמפיין פתוח"

---

## 🐳 Step 3 — Production Stability (Priority 4)

**קובץ:** `docker-compose.yml`

### שינויים:
| שינוי | לפני | עכשיו |
|---|---|---|
| `mem_limit` | 1536m | **1200m** — מתאים ל-Orange Pi |
| sentinel-bot `max_age` | 1920s | **1980s** — LOOP_INTERVAL×2+180s |
| autoheal | אין | ✅ `willfarrell/autoheal:latest` |
| labels | אין | ✅ `autoheal=true` על כל שירות |

**autoheal** — מפעיל מחדש אוטומטית כל container עם `autoheal=true` שה-healthcheck שלו נכשל.

---

## 🔐 Step 4 — Security Hardening (Priority 4)

**קובץ:** `telegram_devops.py` + `telegram_bot.py`

### שינויים:
1. **`hmac.compare_digest`** — מחליף `==` ב-PIN validation (מניע timing attacks)
2. **Rate limiting** — 3 ניסיונות כושלים / 5 דקות → נעילה עם הודעה
3. **Persistent sessions** — `_pin_sessions` נשמר ל-`/app/state/dev_pin_sessions.json`; שורד restart
4. **`telegram_bot.py`** — handler `awaiting_dev_pin` מפעיל rate check לפני validate

### פונקציות חדשות ב-`telegram_devops.py`:
```python
dev_pin_rate_limited(chat_id)  → bool   # 3 ניסיונות / 5 דקות
dev_pin_record_failure(chat_id) → None  # מתעד ניסיון כושל
_load_pin_sessions()           → dict   # טוען מהדיסק בהפעלה
_save_pin_sessions()           → None   # שומר לדיסק אחרי הפעלה
```

---

## 📦 Step 5 — Add-On Phase 2a (Priority 3)

**קבצים:** `migrations/001_addon_phase2.sql` + `supabase_repository.py` + `telegram_callbacks.py`

### Migration SQL (למשתמש להריץ ב-Supabase):
```sql
ALTER TABLE trades ADD COLUMN IF NOT EXISTS is_addon BOOLEAN DEFAULT false;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS base_campaign_lot_id UUID;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS addon_sequence INT DEFAULT 1;
```

### פונקציות חדשות ב-`supabase_repository.py`:
```python
get_latest_buy_trade_id(sb, symbol, campaign_id) → str | None
update_addon_record(sb, trade_id, base_campaign_lot_id, addon_sequence) → None
```

### Callback:
- לאחר אישור ורישום ב-`management_notes`, מנסה לסמן את ה-trade האחרון כ-addon
- graceful fallback: אם העמודות לא קיימות (migration לא הורץ) — עובד בשקט

---

## 🧪 Step 6 — Test Infrastructure (Priority 5)

### `tests/conftest.py` — fixture חדש:
```python
@pytest.fixture
def mock_telegram_bot(monkeypatch):
    # מחזיר רשימה של הודעות שנשלחו דרך risk_monitor.send_telegram
```

### `tests/test_e2e_risk_monitor.py` — קובץ חדש (9 טסטים):
- `TestRunnerAlertWithTrailingStop` — שרשרת: `compute_suggested_trail_stop` → `_runner_state_alert`
- `TestAlertContentIntegrity` — תוכן Hebrew/RTL תקין
- `TestSendTelegramPath` — `send_telegram` מקבל את ההודעה הנכונה

### pytest markers — נוספו ל:
- `tests/test_supabase_repository.py` — כל 10 קלאסות: `@pytest.mark.unit`
- `tests/test_integration.py` — כל 3 קלאסות: `@pytest.mark.integration`
- `tests/test_e2e_risk_monitor.py` — `@pytest.mark.integration`

---

## 📊 מספרים

| מדד | לפני Sprint 5 | עכשיו | שינוי |
|---|---|---|---|
| Tests passing | 1210 | **1219** | +9 |
| mem_limit | 1536m | **1200m** | -336m/service |
| autoheal | אין | ✅ | חדש |
| PIN security | `==` | `hmac.compare_digest` + rate limit | שיפור |
| PIN sessions | in-memory | **persistent JSON** | שיפור |
| Add-On columns | אין | ✅ migration + code | חדש |
| mock_telegram_bot | אין | ✅ fixture | חדש |
| E2E tests | אין | ✅ 9 טסטים | חדש |
| pytest markers | 3 קבצים | **6 קבצים** | +3 |

---

## ⚠️ פעולת משתמש נדרשת

```sql
-- הרץ ב-Supabase → SQL Editor:
-- קובץ: migrations/001_addon_phase2.sql
ALTER TABLE trades ADD COLUMN IF NOT EXISTS is_addon BOOLEAN DEFAULT false;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS base_campaign_lot_id UUID;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS addon_sequence INT DEFAULT 1;
```

---

## 🔓 מה עדיין פתוח — לישיבה הבאה (Meeting 6)

1. `fmt_heat_thermometer()` — חיבור לדוח השבועי
2. Coverage gate ≥75% — אכיפה ב-CI
3. Add-On Phase 2b — eligibility dashboard (`/addon` מציג אם הפוזיציה כשירה)
4. Audit log — `audit_logger.py` + טבלת Supabase
5. `test_e2e_risk_monitor.py` הרחבה — מחזור `main()` מלא עם mock Supabase
