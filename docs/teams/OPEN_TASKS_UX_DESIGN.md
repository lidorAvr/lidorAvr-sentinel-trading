# Open Tasks UX Design — `📋 משימות פתוחות`

> Team: Adaptive UX — Sprint 10
> Date: 2026-05-15
> Status: UX SPEC ONLY. No production code, no commits.
> Scope: Telegram UX around the Task model. Rules owned by Mark
> (`OPEN_TASKS_METHODOLOGY_SPEC.md`); engine owned by Architecture
> (`OPEN_TASKS_ENGINE_DESIGN.md`). This doc does NOT invent rules.

---

## 0. What this is (founder's real intent)

Day-3 audit (§3) recorded the founder asking for a "tasks split by
symbol, sorted, browsable" surface they could not find. The journal
walker (`get_next_missing`) is NOT that feature. This is.

A **Task** (model owned by Architecture / Mark — we only render it):

| Field | Used by UX for |
|-------|----------------|
| `task_id` | callback addressing |
| `task_type` | icon + verb (e.g. `stop_breach`, `trim_not_working`, `promote_1r`) |
| `symbol` | grouping key 2, row label |
| `urgency` (P0–P3) | grouping key 1, sort, badge |
| `recommended_action` | the one-line Hebrew imperative shown |
| `trigger_context` | honest "why now" block (state, open-R, days) |
| `status` (`open`/`done`/`skipped`) | filter + row state |
| `notes` | free-text the founder attaches |
| `data_quality` (`live`/`stale`/`fallback`) | honesty label (CLAUDE.md) |

Tasks are a **read-projection of engine state** (pull surface). They are
the single source of truth the user *acts on*. They do NOT add a new
recurring alert (AGENTS.md Red Line #9 / anti-spam invariant).

---

## 1. Entry point (discoverable — the button Day-3 was missing)

### 1a. Main reach: portfolio menu button

Add ONE button to `telegram_menus.get_portfolio_menu()`. Exact position:
**second row, directly under `📊 חדר מצב (פוזיציות)` and above
`🎯 קידום סטופ`** — tasks are the "what should I do now" surface, so it
sits at the top of the action stack, above the heavier room.

```python
def get_portfolio_menu():
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(telebot.types.KeyboardButton("📊 חדר מצב (פוזיציות)"))
    markup.add(telebot.types.KeyboardButton("📋 משימות פתוחות"))   # ← NEW (here)
    markup.add(telebot.types.KeyboardButton("🎯 קידום סטופ"))
    markup.add(telebot.types.KeyboardButton("🌡️ משטר שוק וסיכונים"))
    markup.add(telebot.types.KeyboardButton("⬅️ חזרה לתפריט ראשי"))
    return markup
```

Rationale: `📊 מצב תיק` is already on the main menu and is the
founder's mental home for "my positions". Putting tasks one tap inside
it (not buried at the bottom of a heavy message — that was the Day-3
stop-promotion blocker) makes it the first thing visible when they ask
"what now". A count badge is added live (see 1c).

### 1b. Command + button-text routing

In `telegram_bot.py`, mirror the existing `🎯 קידום סטופ` / `/promote`
block (currently lines 387-389). Add directly above it:

```python
if text in ["📋 משימות פתוחות", "/tasks"]:
    handle_open_tasks_entry(chat_id)   # new fn in a NEW module telegram_tasks.py
    return
```

`/tasks` is added to the canonical help string (`telegram_bot.py:283`,
the richer `/portfolio … ` list) so it is advertised, not folklore.
New logic lives in a **new additive module `telegram_tasks.py`**
(re-exported into `telegram_bot.py` exactly like `telegram_stop_promote`
is at lines 37-39) — `telegram_bot.py` is NOT rewritten (CLAUDE.md).

### 1c. Count badge

The reply-keyboard button text is static (Telegram limitation), so the
*badge* lives in the message the user gets when they enter
`📊 מצב תיק`: append a live line to the existing
`📊 *מצב תיק — בחר פעולה:*` prompt (`telegram_bot.py:110`), e.g.
`📋 משימות פתוחות: 🛑1 ⚠️3` — cheap count read only, no engine run.
If the count read fails, show `📋 משימות: —` (never fake a zero —
CLAUDE.md fallback honesty).

---

## 2. List view — grouped → sorted (the view promised on Day 3)

Sort contract (owned here, data owned by Architecture):

1. **Group 1 = urgency**, P0 → P1 → P2 → P3 (most urgent first).
2. Within a group, **group 2 = symbol** (A→Z).
3. Within a symbol, **sort by task date ascending** (oldest first —
   oldest unattended task is the most overdue).

Urgency band headers + count badges:

| Urgency | Header | Meaning |
|---------|--------|---------|
| P0 | `🛑 דחוף` | act now (hit stop / breach) |
| P1 | `⚠️ חשוב` | act today (broken / runner / breakeven) |
| P2 | `🟡 לתשומת לב` | review (checkpoint / trim candidate) |
| P3 | `🔵 מעקב` | informational watch |

Each task = **one tap-only inline row** (reuse the
`build_stop_promote_keyboard` one-button-per-row pattern,
`telegram_stop_promote.py:94-113`). Label =
`{icon} {SYM} — {short recommended_action}`. `callback_data =
"task_open|{task_id}"`. No typing, no scrolling-to-map (the Day-3 fix
principle).

### Wireframe — list (Hebrew RTL)

```
📋 משימות פתוחות — 6 משימות (4 סימולים)
מעודכן: 15/05 16:42 · נתונים: חי 🟢

🛑 דחוף (1)
┌─────────────────────────────────────────┐
│ 🛑 NVDA — נגע בסטופ, סגור עכשיו          │
└─────────────────────────────────────────┘

⚠️ חשוב (3)
┌─────────────────────────────────────────┐
│ ⚠️ AMD — 9 ימים מתחת לאסטרטגיה, שקול חיתוך│
│ ⚠️ CAT — הגיע ל-1R, קדם סטופ ל-break-even│
│ ⚠️ MSFT — מצב שבור, בדוק תזה             │
└─────────────────────────────────────────┘

🟡 לתשומת לב (2)
┌─────────────────────────────────────────┐
│ 🟡 CAT — צ'קפוינט 2R, שקול מימוש חלקי    │
│ 🟡 QQQ — סטיית סיכון בינונית             │
└─────────────────────────────────────────┘

[🔕 הוסתרו 2 שבוצעו]   [🔄 רענן]   [❌ סגור]
```

Notes:
- Header line states freshness + an honest data label
  (`חי 🟢` / `מאוחסן ⚠️` / `מוערך — לא מאומת ⛔`). If ANY task in the
  list is `data_quality != live`, the worst label wins and that row
  also carries a `⚠️` prefix instead of its normal icon.
- ALGO-derived tasks: see §5 (info-only, never an actionable verb).
- Pagination: if rows > ~8, add `[⬅️ הקודם] [➡️ הבא]`
  (`callback task_page|{n}`); same constraint the Day-3 grouped-backlog
  spec noted for Telegram message limits.
- `[🔕 הוסתרו N שבוצעו]` (`callback task_show_done`) toggles a
  read-only view of recently done/skipped tasks (status filter only —
  no mutation).

---

## 3. Task detail + actions

Tapping a row (`task_open|{task_id}`) opens a detail card. It shows the
**trigger context honestly** (state / open-R / days exactly as the
engine reports them; stale or fallback values are explicitly labelled —
CLAUDE.md), the recommended action, then three inline action buttons.

### Wireframe — detail

```
🛑 NVDA — משימה דחופה

🔎 מה קרה:
• מצב: BROKEN (נגע בסטופ)
• Open-R: −1.02R
• בקמפיין: 14 ימים
• מחיר: $108.40 · נתון: חי 🟢

🎯 פעולה מומלצת:
סגור את הפוזיציה מיד — הסטופ נפרץ. אל תרחיב, אל תתן צ'אנס.

(המלצה בלבד. Sentinel לא מבצע מסחר —
 בצע ב-IBKR ואז סמן כאן ✅ בוצע.)
─────────────────────────────
[✅ בוצע]  [⏭️ דלג]  [📝 הוסף הערה]
[⬅️ חזרה לרשימה]
```

Honesty rules in the "מה קרה" block:
- `מחיר: $108.40 · נתון: חי 🟢` — if price is a fallback:
  `מחיר: $108.40 · ⚠️ נתון מאוחסן (לא live)`.
- If open-R cannot be computed (no original risk):
  `Open-R: לא זמין (חסר סיכון מקורי)` — never print a fabricated R.
- The "(המלצה בלבד…)" disclaimer is mandatory on every detail card:
  Sentinel never executes; it recommends. Prevents the user reading a
  task as "done by the bot".

### Callbacks (all on the detail card)

| Button | `callback_data` | Effect |
|--------|-----------------|--------|
| `✅ בוצע` | `task_done\|{task_id}` | confirm sub-flow → mark `status=done` |
| `⏭️ דלג` | `task_skip\|{task_id}` | skip sub-flow (P0 requires reason) |
| `📝 הוסף הערה` | `task_note\|{task_id}` | free-text capture → append to `notes` |
| `⬅️ חזרה לרשימה` | `task_open\|list` | re-render §2 list (no engine re-run) |

Routing: add these `if data.startswith("task_…")` branches to the
`handle_queries` chain in `telegram_callbacks.py` (same place
`promote_pick|` / `loosen_confirm|` live, lines 60-83). Each branch
calls a `telegram_tasks.handle_*` function — no logic in the router.

### 3a. Done confirm sub-flow

Reuse the **defaulted-NO inline confirm** pattern proven in
`guard_stop_write` (`telegram_stop_promote.py:326-343`, callbacks
`loosen_confirm|yes/no`). Marking done changes engine/task state, so it
is confirmed — but it is low-risk (status flip, not a stop loosen), so
ONE tap to confirm, default-safe.

```
✅ לסמן בוצע? — NVDA
"סגור את הפוזיציה מיד"

האם ביצעת את הפעולה?
[✅ כן, בוצע]      [↩️ עוד לא]
```

`כן` → `task_done_confirm|{task_id}|yes` → task engine sets
`status=done` (write owned by Architecture's engine API; UX only calls
it). Reply: `✅ סומן כבוצע — NVDA. נשאר: ⚠️2 🟡2` and return to list.
`עוד לא` → `…|no` → back to detail, no change.

### 3b. Skip sub-flow — P0 requires an explicit reason (methodology guardrail)

- **P1–P3 skip:** single confirm (same widget as 3a):
  `⏭️ לדלג על המשימה? [⏭️ דלג] [↩️ ביטול]` →
  `task_skip_confirm|{task_id}|yes` sets `status=skipped`.
- **P0 skip:** confirm is NOT enough. Skipping a P0 (e.g. ignoring a
  stop breach) is the highest-methodology-risk action, mirroring the
  ratchet-loosen guardrail. Flow:
  1. `task_skip|{task_id}` on a P0 → message:
     `🛑 דילוג על משימה דחופה דורש סיבה מפורשת (יירשם).`
  2. Set free-text capture state (reuse the exact `risk_reject_reason`
     pattern, `telegram_bot.py:79-101`):
     `user_state[chat_id] = {"action": "task_skip_reason",
     "task_id": …, "urgency": "P0"}`.
  3. Top-of-handler branch in `telegram_bot.py` (next to the
     `risk_reject_reason` branch) reads the typed reason, hands it to
     the task engine (`status=skipped`, `notes += reason`,
     methodology-audit per Mark's spec), then:
     `📝 הדילוג נרשם — NVDA. סיבה: _<text>_`.
  4. Empty / blank reason → re-prompt, do NOT skip (cannot silently
     bypass a P0 guardrail).

```
🛑 דילוג על P0 — NVDA
דילוג על משימה דחופה דורש סיבה מפורשת
(תירשם ביומן השיטה).

📝 כתוב מדוע אתה מדלג:
[↩️ ביטול דילוג]
```

### 3c. Add-note sub-flow

Reuse the **same free-text capture pattern** (`management_notes` /
`risk_reject_reason`, `telegram_bot.py:79`,`522`). No confirm needed
(append-only, low risk):

1. `task_note|{task_id}` → set
   `user_state[chat_id]={"action":"task_add_note","task_id":…}`,
   prompt: `📝 כתוב הערה למשימה (NVDA):` + `[↩️ ביטול]`.
2. Typed text → branch near `risk_reject_reason` → task engine appends
   to `notes` (write owned by engine). Reply:
   `✅ ההערה נשמרה — NVDA.` then return to that task's detail card.
3. `↩️ ביטול` (`cancel_action`, already handled
   `telegram_callbacks.py:105`) clears state.

---

## 4. De-dup vs existing risk_monitor push alerts

`risk_monitor.py` already PUSHES P0–P3 alerts to `ADMIN_ID` via
`send_telegram` / `send_telegram_with_keyboard` (lines 503-510), gated
by the anti-spam state machine (`risk_monitor_state.json`,
`STATE_ALERT_COOLDOWN`, `should_alert`, lines 48-173). We must NOT
double-notify (AGENTS.md invariant #7 / Red Line #9).

**Model: push = doorbell, tasks list = the room. One source of truth.**

1. **Tasks add NO new push.** The tasks list is a *pull* surface only —
   opened by the user via the button/`/tasks`. No timer, no recurring
   send, no risk_monitor change. The anti-spam state machine is
   untouched.
2. **A task and its alert are the same underlying engine event**, keyed
   the same way risk_monitor already keys it
   (`build_position_alert_key`, line 130). Per Architecture's engine:
   the task's identity should derive from that same
   `(symbol, state/type)` key so the list never shows a task the push
   represents as a *separate* item — it is the SAME item, just the
   pull view of it.
3. **Push alerts link INTO the list, they don't duplicate its
   actions.** Recommendation to Architecture/risk_monitor owners (not
   built here): the existing alert messages get ONE extra inline button
   `📋 פתח כמשימה` (`callback task_open|{task_id}`) so the doorbell
   leads to the single room. Existing alert action buttons
   (`runner_decision|…`, `risk_confirm|…`) are unchanged — those remain
   the fast-path; the task list is the durable backlog of what is still
   open. This is a de-dup *link*, not a second notifier.
4. **Status flows one way: actions in the task list close the task;
   risk_monitor keeps owning when/whether to re-ping.** Marking a task
   done does NOT write `risk_monitor_state.json` (avoid cross-coupling
   two state machines). risk_monitor's own cooldowns already prevent
   re-spam; a done task simply drops off the pull list on next read.
   If the engine re-detects the condition later, that is a *new* task
   (same as risk_monitor legitimately re-alerting after cooldown) —
   expected, not duplication.

Net: the user is pinged AT MOST as often as today (no change to
risk_monitor cadence), and has exactly ONE place to see and resolve the
full open set.

---

## 5. Empty / edge states (Hebrew, RTL, honest)

### 5a. No open tasks

```
📋 משימות פתוחות

✅ אין משימות פתוחות.
התיק תחת שליטה — אין פעולה נדרשת כרגע.

[🔄 רענן]   [❌ סגור]
```

### 5b. Only ALGO positions → info-only (no actionable verb)

ALGO is externally managed; Sentinel never instructs ALGO actions
(DEC-20260511-001, mirrored from `telegram_stop_promote.py:99-104`).
ALGO-derived tasks render as a NON-tappable info row
(`callback task_algo_noop` → answer-callback alert, exactly like
`promote_algo_noop`, `telegram_callbacks.py:70-76`):

```
📋 משימות פתוחות

🟠 כל הפוזיציות הפתוחות מנוהלות חיצונית (ALGO).
Sentinel אינו מנפיק משימות פעולה ל-ALGO — מעקב בלבד:

┌─────────────────────────────────────────┐
│ 🟠 SPY — ALGO: צביר אדום (מידע בלבד)     │
└─────────────────────────────────────────┘

[🔄 רענן]   [❌ סגור]
```

Tapping it: popup `🟠 ALGO מנוהל חיצונית — אין פעולה ב-Sentinel.`

### 5c. Data incomplete / fallback

If the engine returns tasks but flags incomplete/fallback inputs
(CLAUDE.md: never present fallback as truth):

```
📋 משימות פתוחות — 3 משימות
⚠️ נתונים חלקיים: חלק מהמחירים מאוחסנים (לא live).
התייחס בזהירות — אמת מול IBKR לפני פעולה.

⚠️ דחוף (1)
┌─────────────────────────────────────────┐
│ ⚠️ NVDA — ייתכן נגיעת סטופ (נתון מאוחסן) │
└─────────────────────────────────────────┘
…
[🔄 רענן]   [❌ סגור]
```

The P0 icon is downgraded to `⚠️` + "(נתון מאוחסן)" and the verb is
softened ("ייתכן") — we never assert a stop breach off stale data.

### 5d. Engine/infra error

```
📋 משימות פתוחות

❌ לא ניתן לטעון משימות כרגע (שגיאת תשתית).
לא מוצגות משימות — זה לא אומר שאין.
נסה שוב, או בדוק `/health`.

[🔄 רענן]   [❌ סגור]
```

Explicitly says "absence of list ≠ absence of tasks" (CLAUDE.md
honesty), mirroring `handle_stop_promote_entry`'s infra-error message
(`telegram_stop_promote.py:135`).

---

## 6. Wireframe index (all six, consolidated)

| # | Screen | Trigger | Section |
|---|--------|---------|---------|
| 1 | List (grouped/sorted, badges) | `📋 משימות פתוחות` / `/tasks` | §2 |
| 2 | Task detail + 3 actions | `task_open\|{id}` | §3 |
| 3 | Done confirm (default-safe) | `task_done\|{id}` | §3a |
| 4 | Skip — P1-3 confirm / **P0 reason** | `task_skip\|{id}` | §3b |
| 5 | Add-note free-text capture | `task_note\|{id}` | §3c |
| 6 | Empty / ALGO-only / fallback / error | list with no actionable open | §5 |

Hebrew copy is kept short, imperative, RTL-prefixed (`{RTL}` per
existing convention), and explicit about live vs stale/fallback
(CLAUDE.md / AGENTS.md).

---

## 7. Patterns reused (no new interaction primitives invented)

| Need | Reused from | Where |
|------|-------------|-------|
| Tap-only one-row-per-item keyboard | `build_stop_promote_keyboard` | `telegram_stop_promote.py:94-113` |
| Lightweight entry (no heavy room) | `handle_stop_promote_entry` | `telegram_stop_promote.py:117` |
| Defaulted-safe inline confirm | `guard_stop_write` / `loosen_confirm` | `telegram_stop_promote.py:326` ; `telegram_callbacks.py:79` |
| Free-text capture (reason/note) | `risk_reject_reason` / `management_notes` | `telegram_bot.py:79` , `:522` |
| ALGO non-actionable info row | `promote_algo_noop` | `telegram_callbacks.py:70` |
| Universal cancel | `cancel_action` | `telegram_callbacks.py:105` |
| Additive module + re-export | `telegram_stop_promote` import block | `telegram_bot.py:37-39` |

## 8. Constraints honoured

- Admin guard / anti-spam (`telegram_bot_secure_runner.py`) untouched —
  no new push, pull-only.
- `telegram_bot.py` NOT rewritten — new logic in `telegram_tasks.py`,
  one routing line + one help line added, mirroring the proven
  `telegram_stop_promote` integration.
- No R / NAV / exposure / campaign math defined here — UX renders the
  Task model; numbers come from the engine (Architecture).
- No Supabase mutation from UX: done/skip/note call the task engine's
  API (owned by Architecture); the only reads here are count + list.
- Fallback/stale data always labelled; P0 never asserted off stale
  data; skipping a P0 always requires a logged reason.
- No double-notify: push = doorbell, list = room, same engine key.
