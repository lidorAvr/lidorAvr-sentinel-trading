# Sprint-29 — Security review of ACTUAL Telegram history: sensitive-data leakage hunt (DOC-ONLY)

**Team:** Security (lead). **Date:** 2026-05-18. **Mode:** verification only —
no code, no additions. Defensive read of the real Telegram exports against the
live deployed tree.

**Inputs audited:** `/tmp/tg_report_1.txt` (11469 lines) +
`/tmp/tg_report_2.txt` (4515 lines) — the user's actual outbound/inbound
Telegram history. Cross-referenced against live HEAD `09dbec7`
("fix(phase-algo1): R-ALGO-2 … R-ALGO-3"), code in `telegram_bot.py`,
`telegram_callbacks.py`, `bot_helpers.py`, and
`docs/teams/SPRINT28_SECURITY_FINDINGS.md` + `DEC-20260518-001`.

> Data-sensitivity discipline: this committed doc is STRUCTURAL only. It
> contains NO live NAV/position/P&L values and quotes NO secret/token/PIN
> value. Leaked artefacts are described **by class and by file:line locator
> only** — the actual secret strings are deliberately NOT reproduced here.
> Anyone remediating must read the raw export, not this file, for values.

> Scope discipline: the exports PREDATE today's deploy
> (timestamps span 2026-05-12 → 2026-05-16). Each finding is classified
> fixed-by-deployed / still-open / new. **R-1 (dashboard :8501) is
> ACCEPTED via Tailscale per `DEC-20260518-001` — noted unchanged, NOT
> re-litigated here.**

---

## Verdict

**Leak found? YES — one HIGH-severity credential-leak class is real and STILL
OPEN at live HEAD `09dbec7`.** A second MEDIUM class (operator PIN echoed in
chat) is structural/Telegram-inherent. A third LOW class (raw library
exception text) is info-disclosure only (no secret). The C1 dev-PIN gate, the
admin boundary, the IBKR-token honesty wording, and the data-source footer all
behave **correctly** in the actual history — no privileged action was observed
without an authenticated session.

| # | Leak / disclosure class | Severity | Status |
|---|---|---|---|
| **L-1** | Raw service-log tail piped verbatim into a Telegram message via `📋 לוגים → devlog\|` — the log lines contain a **`requests` connection-error string that embeds the live Telegram bot token** (`bot<id>:<token>` in the `api.telegram.org/.../sendMessage` URL) **and the IBKR FlexStatement query token** (`...SendRequest?t=<token>&q=<id>`). Full bot-API credential + broker report-pull credential rendered into chat. | **HIGH** | **STILL OPEN** (no redaction at `09dbec7`) |
| L-2 | Operator's **dev-PIN typed in cleartext as a normal message** and thus persisted in chat history (correct PIN + a wrong attempt both visible). Inherent to a text-message PIN prompt. | MEDIUM | OPEN (structural / by-design tradeoff) |
| L-3 | Raw Python/library exception strings surfaced to the user (`Invalid comparison between dtype=datetime64[ns]…`, Telegram API `400 message is too long`) via the Probe error handler. Internal type/library info disclosure — **no secret, no DB connection string, no stack frame**. | LOW | OPEN (cosmetic info-disclosure) |
| R-1 | Dashboard `:8501` unauth + Supabase WRITE tab. | (prior) | **ACCEPTED — UNCHANGED** (`DEC-20260518-001`, Tailscale) — not re-litigated |

---

## L-1 — HIGH: live Telegram bot token + IBKR Flex token leaked via the logs button

**What the export shows.** The `📋 לוגים` dev-menu button → service picker →
`devlog|<service>` callback renders 50 raw log lines into a Telegram code
block. In the actual history (`tg_report_1.txt`, the `📋 לוגים — sentinel-main`
message bodies) the `sentinel-main` log tail, on a DNS-failure window,
contains `requests`-library `Max retries exceeded with url:` errors that
include, **verbatim and unredacted**:

- the **full Telegram bot token** — class: bot-API bearer credential
  (`/bot<numeric-id>:<35-char-secret>/sendMessage` inside the
  `api.telegram.org` HTTPSConnectionPool error). Possession of this token =
  full control of the bot (read all messages, send as the bot, hijack the
  admin channel).
- the **IBKR FlexStatement request token + query id** — class: broker
  report-pull credential (`www.interactivebrokers.com/.../FlexStatementService.SendRequest?t=<token>&q=<id>`).
  The matching query id is *also* independently printed by
  `🏥 בריאות מערכת` as `✅ IBKR Query ID — <id>` (cleartext); only the
  paired `t=` token is the sensitive half, and it leaks through L-1.

**Root cause at live HEAD `09dbec7` (confirmed by source, not assumed):**

- `telegram_callbacks.py:28-41` — `devlog|` branch:
  `lines = _read_last_log_lines(log_path, 50)` → sent in a ```code block```
  with **zero filtering**.
- `bot_helpers.py:42-51` — `_read_last_log_lines` returns the raw file tail
  (`"".join(lines[-n:]).strip()`). **No regex scrub, no token mask, no
  allow-list.** The only token-masking in the whole bot is
  `telegram_bot.py:469-475` (`⚙️ הצג Config` masks config *keys* named
  token/key/secret) — a different code path that does NOT touch logs.
- `git log -- bot_helpers.py telegram_callbacks.py` shows the last touch was
  the Phase-4 extraction commit (`80c4991`); Sprint-27/28/29 did **not** add
  redaction. A repo-wide grep for `redact|sanitiz|scrub|mask.*token|AAEN…`
  finds nothing on this path. **L-1 is not fixed by today's deploy.**

**Honest exploit bound.** The button is C1/admin-gated (verified: every
`📋 לוגים` press in the export is preceded by `✅ PIN מאומת` and the menu sits
behind `_require_active_dev_session`, `telegram_bot.py:391`). So the *trigger*
needs the admin + an active PIN session. **But the leak's blast radius is the
Telegram message store itself**: once rendered, the bot token sits in the
chat/cloud history, in this very export file, in any forward/backup, and in
any future paste of "the logs" — i.e. it survives far outside the gated
moment. A logs button that prints the bot's own credential is a
credential-exfiltration primitive regardless of who pressed it. **This is the
one thing to watch.**

**Class, not value:** the actual token strings exist at
`tg_report_1.txt` lines ~1991/1999/2032/2040/… (and every other
`sentinel-main` log dump) and are deliberately NOT copied into this doc.

---

## L-2 — MEDIUM: dev-PIN echoed in cleartext into chat history

`tg_report_2.txt` (the `🔐 תפריט מפתח — דרוש PIN` → user reply →
`✅ PIN מאומת` sequences) shows the operator typing the PIN as an ordinary
Telegram message; both a correct value and a wrong attempt are now permanently
in chat history (and in this export). The **gate logic is correct and
honest**: wrong PIN → `⛔ PIN שגוי — גישה נדחתה` (fail-CLOSED, no session
granted), correct PIN → `✅ PIN מאומת — פגישה פעילה ל-30 דקות`. The leak is
not a logic flaw — it is the inherent property of any text-prompt PIN: the
secret is keyed into a logged channel. Telegram has no native masked input.
Severity MEDIUM because the PIN only gates dev-tools *behind* the
already-fail-closed `secure_runner` admin boundary (a second factor: only
`ADMIN_ID` can reach the prompt at all), and the PIN is rotatable.
Status: structural / conscious-tradeoff — flag, don't "fix" silently.

## L-3 — LOW: raw exception text to the user

`tg_report_2.txt` `❌ שגיאת Probe:` messages surface
`str(e)[:300]` from `telegram_bot.py:515` — pandas/Telegram-API internals
(`dtype=datetime64[ns]`, `Bad Request: message is too long`). Info-disclosure
of library/type internals only; **no secret, no DB error string, no SQL, no
stack frame, no connection URL**. Cosmetic; honesty-neutral.

## Things verified CLEAN (no leak)

- **C1 fail-closed wording present & correct.** Wrong-PIN → explicit
  `גישה נדחתה`; expired/again-prompt path appears; no privileged output
  (`Git Pull`, `הצג Config`, `לוגים`, `Probe`) ever appears in the export
  without a preceding `✅ PIN מאומת`. No privileged action without a session.
- **IBKR/Telegram token honesty in `🏥 בריאות מערכת`.** Reports
  `✅ IBKR Token — מוגדר` / `✅ Telegram Admin — מוגדר` — *"configured",
  value withheld*. Correct fail-safe phrasing. (The bot token leak is L-1's
  log path, not this health line.)
- **`service_role` word.** `מקור: Supabase · הרשאה: service_role` (Probe)
  discloses the *role name* only — already accepted in Sprint-26/28 as the
  "JWT role word, no key". No Supabase URL/anon/service key value anywhere
  in either export (grepped: no `eyJ`, no `sb_secret`, no `SUPABASE_KEY=`).
- **Data-source footer honest.** `ℹ️ מקור נתונים: Live/Cached … יש
  להתייחס לנתון כהערכה ולאמת מול IBKR` — explicitly flags fallback/cached;
  no fallback-as-truth (CLAUDE.md #3 satisfied). Not a security issue.
- **Internal identifiers** (`campaign_id` like `PLTR_9417969543`, `q=`
  query id) are operational references, not credentials — acceptable
  exposure to the sole admin; noted, not escalated.

---

## למנכ״ל — בשפה פשוטה

**האם הדיווחים בטלגרם דולפים משהו שאסור? כן — נמצאה דליפה אחת חמורה.**

- **מה דלף (בלי לחשוף ערכים):** כשלוחצים על כפתור **"📋 לוגים"** בתפריט
  המפתח, הבוט מדביק לתוך הצ׳אט את הלוג הגולמי **כמו שהוא, בלי לסנן**.
  בתוך הלוג הזה, בשורות של שגיאת-רשת, מופיע **הטוקן המלא של בוט הטלגרם**
  (שווה ערך לסיסמת-על לבוט) **וגם טוקן משיכת הדוחות מ-IBKR**. ברגע שזה
  הודבק — זה נשאר בהיסטוריית הצ׳אט, בקובץ הייצוא הזה, ובכל גיבוי/העברה
  עתידית. **זו הדליפה האחת שחייבים לטפל בה.** היא עדיין פתוחה בקוד החי
  של היום (`09dbec7`) — שום פריסה לא תיקנה אותה.
- **דבר שני (בינוני, לא באג):** ה-PIN של תפריט המפתח **נכתב כטקסט רגיל**
  ולכן נשאר בהיסטוריית הצ׳אט. זו תכונה של טלגרם (אין שדה-סיסמה מוסתר),
  לא תקלת לוגיקה — מנגנון ה-PIN עצמו עובד נכון: PIN שגוי → "גישה נדחתה",
  נכון → פגישה ל-30 דק׳. כדאי לדעת, לא "לתקן בשקט".
- **דבר שלישי (נמוך):** לפעמים מוצגת הודעת שגיאה טכנית גולמית של פייתון.
  חושף פרטים פנימיים זניחים — **לא** סוד, לא מסד-נתונים.
- **מה תקין:** ה-PIN חוסם נכון, אין פעולה רגישה בלי PIN פעיל, הטוקנים
  ב"בריאות מערכת" מוצגים כ-"מוגדר" בלבד (בלי הערך), שורת מקור-הנתונים
  כנה לגבי נתון חי/מטמון. אין מפתח-Supabase שדלף.
- **R-1 (הדשבורד 8501):** הוחלט מודע ע״י המנכ״ל (`DEC-20260518-001`,
  מאחורי Tailscale) — **לא נפתח מחדש כאן, ללא שינוי.**

**שורה תחתונה:** כן — הדיווחים דולפים. הדליפה החמורה היא כפתור "לוגים"
שמדפיס את הטוקן של הבוט עצמו. לא סודי-קריטי מבחינת מי-יכול-ללחוץ (רק
האדמין, עם PIN), אבל הסוד נשאר לנצח בהיסטוריית הצ׳אט.

## מה צריך לעשות

1. **L-1 — דחוף, founder-gated (תיקון קוד, לא בסקירה הזו):** אפיון Phase
   שמסנן/ממסך טוקנים בלוג **לפני** ששולחים אותו לטלגרם (regex על
   `bot\d+:…` ועל `?t=…&q=…`), ב-`_read_last_log_lines` או בנתיב
   `devlog|`. עד אז — **לא ללחוץ "📋 לוגים" בטלגרם** (השתמש ב-SSH/דשבורד
   לקריאת לוגים).
2. **L-1 — תגובת-אירוע (Ops/founder, היום):** מאחר שהטוקן כבר בהיסטוריית
   הצ׳אט/בקובץ הייצוא — **לסובב (rotate) את טוקן בוט הטלגרם ואת טוקן
   IBKR Flex** ולוודא שהקובץ `/tmp/tg_report_*.txt` לא נשמר/מועבר עם
   ערכים חיים. (אין להעתיק את הערכים לשום מסמך מתועד.)
3. **L-2 — קבלה מודעת (founder):** לרשום ש"ה-PIN נכתב בצ׳אט מעצם
   טבעו; מוגן ע״י גבול ה-admin של secure_runner; יסובב מעת לעת". ללא
   שינוי קוד חד-צדדי.
4. **L-3 — ניקיון עתידי (נמוך):** למסך הודעת שגיאת Probe להודעה ידידותית
   קצרה במקום `str(e)`. תוספת — founder-gated, לא בוער.
5. **R-1:** ללא פעולה — מכוסה ב-`DEC-20260518-001` (Tailscale). לא
   נפתח מחדש.

---

## Final report (≤180 words)

**Honest verdict: a leak WAS found — YES.** Reading the actual Telegram
history against live HEAD `09dbec7`: **L-1 (HIGH, STILL OPEN)** — the
`📋 לוגים` button (`telegram_callbacks.py:28-41` → `bot_helpers.py:42-51`,
`_read_last_log_lines`, zero redaction) prints the raw service-log tail into
chat; on DNS-error windows that tail embeds the **live Telegram bot token**
and the **IBKR Flex request token** (class only — values not reproduced; they
sit at `tg_report_1.txt` ~L1991+). Admin/PIN-gated to *trigger*, but once
rendered the credential is permanent in chat/export history — a real
exfiltration primitive. Not fixed by any deploy. **L-2 (MEDIUM, structural):**
the dev-PIN is typed as plaintext into chat history (gate logic itself
correct/fail-closed). **L-3 (LOW):** raw library exception text to the user —
info only, no secret. Clean: C1 fail-closed wording, no privileged action
without a session, "Token — מוגדר" honesty, honest data-source footer, no
Supabase key anywhere.

**R-1 status:** ACCEPTED & UNCHANGED per `DEC-20260518-001` (Tailscale) — not
re-litigated.

**The one thing to watch:** L-1 — the logs button leaks the bot's own token
into permanent chat history; rotate tokens now and gate/redact before reuse.
