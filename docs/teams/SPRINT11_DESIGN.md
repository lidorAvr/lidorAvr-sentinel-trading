# Sprint 11 — Architecture + Adaptive-UX Design

**Sprint:** 11 — Wave 1 (design)
**Team:** 🏗️ Architecture + 🤝 Adaptive UX
**Status:** DESIGN ONLY. No production code, no migration, no git commit/push.
**Branch:** `claude/review-system-audit-FBZ2h`
**Date:** 2026-05-15
**Inputs:** `SPRINT11_PLAN.md` (findings #2,#3,#4,#5,#7,#9), `DECISIONS.md`
DEC-20260515-006/-007/-008/-009, `OPEN_TASKS_UX_DESIGN.md`,
`OPEN_TASKS_ENGINE_DESIGN.md`, `OPEN_TASKS_WAVE2_IMPL.md`, the live code
(`telegram_tasks.py`, `telegram_stop_promote.py`, `telegram_menus.py`,
`telegram_callbacks.py`, `audit_logger.py`, `open_tasks.py`).

> **Gate.** Items keyed to Mark consume `MARK_SPRINT11_RULINGS.md` (Wave 1,
> authored in parallel — not yet on disk at design time). Every place that
> needs Mark's text is marked **`⟨MARK:…⟩`** — a literal slot the Wave-2
> build copies **verbatim** from the rulings doc. Engineering invents **no**
> methodology wording. If a slot is unresolved at the checkpoint, that sub-
> item does **not** ship (the rest is independent and ships).

This doc **extends** the Sprint-10 designs; it does not contradict them. All
Sprint-10 guardrails (G1–G9 in `OPEN_TASKS_WAVE2_IMPL.md` §3) remain in force.

---

## 1. #3 — Post-action cache-and-update-in-place (HIGH, UX/perf)

### 1.1 The problem (verified in code)

`telegram_tasks.py` today: `handle_task_done_confirm`, `handle_task_skip_confirm`,
`handle_task_skip_reason` all end with `handle_open_tasks_entry(chat_id)`
(lines 457, 509, 548). `handle_open_tasks_entry` → `_load_tasks` (line 305)
which every time:

1. `repo.get_all_trades(supabase)` (full trades fetch),
2. `ec.get_open_positions_campaign(df)` (campaign aggregation),
3. `_enrich_positions(...)` — **per position**: `ec.get_live_price` (×2 on
   line 151!), `ec.get_campaign_risk_metrics`, `ec.classify_management_mode`,
   `ec.compute_position_state`, plus `ec.get_ma_levels` +
   `ec.compute_suggested_trail_stop` for RUNNERs,
4. `open_tasks.list_tasks` (derive + Supabase lifecycle SELECT).

So a single ✅/⏭️ pays the **entire derive pipeline + N×network** again, only
to reflect a one-field status flip the engine already knows nothing about
(lifecycle lives in `open_tasks`, not the engine). This is exactly the Day-3
"re-run the heavy room per stop" anti-pattern that
`telegram_stop_promote.py` already solved with `temp_positions` reuse
(`telegram_stop_promote.py:152-154` caches `records`; `handle_stop_promote_pick`
reads `st.get("temp_positions")` with **no re-run**, `:191-200`).

### 1.2 Pattern: cache the derived list + enriched positions, mutate in place

Mirror the stop-promote batch-cache contract. `_load_tasks` already stashes
`st["task_records"]` (`telegram_tasks.py:204-219`) — that snapshot is *already*
the render source for detail/done/skip (`_get_record`, line 365). We extend it
into an explicit, invalidatable **task cache** and add an in-place mutate path
so lifecycle actions re-render from the cache with **zero re-fetch / zero
re-derive**.

#### Cache shape (in `user_state[chat_id]`, the established store)

```
user_state[chat_id]["tasks_cache"] = {
    "records":      [ <the existing task_records dicts>, ... ],  # render source
    "enriched":     [ <the _enrich_positions output dicts>, ... ],# §1.4 reuse
    "data_quality": "live" | "stale",
    "built_ts":     <float epoch, time.time() at build>,
    "built_iso":    "DD/MM HH:MM",   # already shown in the list header
}
```

- **Cache key:** `chat_id` (single admin user; the existing `user_state`
  keying — consistent with `temp_positions`). No symbol/task key: the whole
  derived set is one snapshot, exactly like `temp_positions` is one list.
- `records` replaces today's `st["task_records"]`; `_get_record` reads
  `tasks_cache["records"]` (one-line change, backward-shaped).
- `enriched` is added so an *explicit* refresh can re-derive without the
  trades fetch if still warm (optional optimization; see 1.5). The
  correctness path does not depend on it.

#### Build (unchanged derive, now also caches)

`_load_tasks` is the **only** builder. It runs the full pipeline (the engine
stays the single source of truth on every true build) and writes
`tasks_cache` with `built_ts = time.time()`. `handle_open_tasks_entry` calls
`_load_tasks` only when the cache is **absent or invalid** (1.3); otherwise it
renders straight from `tasks_cache["records"]`.

#### In-place mutate (the new fast path — no engine, no network)

New private helper `_apply_local_status(chat_id, idx, status)`:

1. Read `cache = user_state[chat_id]["tasks_cache"]`; if missing → fall back
   to a full `_load_tasks` (cache-miss is always safe; never a hard error).
2. `rec = cache["records"][idx]`; set `rec["status"] = status`
   (`"done"` / `"skipped"`) and `rec["closed_local_ts"] = built_iso-style now`.
   The Supabase write is **still** `open_tasks.mark_done/skip_task` (unchanged,
   authoritative, audited) — only the *re-render* is served from cache.
3. Re-render: rebuild the keyboard from the **same cached `records`**, with
   acted/closed rows either dropped or shown greyed (✓/⏭ glyph, non-tappable
   `task_done_noop`). Counts in the header recomputed from the cached list
   (`len([r for r in records if r["status"]=="open"])`) — no engine call.

`handle_task_done_confirm` / `handle_task_skip_confirm` /
`handle_task_skip_reason` replace their trailing
`handle_open_tasks_entry(chat_id)` with:

```
open_tasks.mark_done(supabase, rec["campaign_id"], rec["task_type"])  # unchanged write
_apply_local_status(chat_id, idx, open_tasks.STATUS_DONE)             # cache + re-render
```

This is **additive** in `telegram_tasks.py` only — `telegram_bot.py`,
`telegram_callbacks.py`, `open_tasks.py`, the engine, and Supabase write
paths are all untouched (no wholesale rewrite; CLAUDE.md).

### 1.3 Invalidation rule — when a true re-derive IS required

A cache hit serves *only* lifecycle re-renders. A genuine rebuild
(`_load_tasks`) is forced when **any** of:

| Trigger | Why a rebuild is mandatory |
|---|---|
| **Explicit `task_refresh`** (the existing 🔄 רענן button / `task_refresh` callback, `telegram_callbacks.py:87-90`) | User explicitly asks for live truth. **Always** discards the cache and re-derives. This is the user-facing "the engine is the source of truth" lever. |
| **Cache absent** (first open, restart, `cancel_action` cleared `user_state`) | Nothing to render from. |
| **Staleness TTL exceeded** | Prices/states drift. `TTL = 180s` — matches the `engine_core` `YF_CACHE` TTL (DEC-20260509-001 / -003 cadence) so the cache never out-lives the price layer it was derived from. `now - built_ts > 180` → rebuild on next entry. |
| **Entry via menu/`/tasks`** when TTL exceeded | Same TTL check; opening the list fresh after a gap re-derives. |

Lifecycle actions (`done`/`skip`/`note`) **never** invalidate — they only
mutate the acted row. Rationale: a status flip changes *user intent stored in
`open_tasks`*, not *engine position state*; re-deriving would recompute the
exact same positions for no benefit (the precise #3 waste).

### 1.4 How it stays correct (engine remains source of truth)

- **Bounded staleness.** The cache can only serve renders for ≤ 180s, the
  same window the underlying price cache is valid for. Any decision the user
  takes off it is no more stale than the price layer already is.
- **Explicit refresh is authoritative.** 🔄 רענן and `/tasks` re-entry past
  TTL run the *full* engine pipeline; the snapshot is the "why at creation",
  the engine re-derives live — exactly the contract stated to the founder
  (SPRINT11_PLAN "When is Open-R verified?" / finding #2).
- **No engine state is faked.** The in-place mutate touches only
  `status`/`closed_local_ts` in the *cached projection*; the authoritative
  status lives in the `open_tasks` table via the unchanged
  `mark_done`/`skip_task` upsert. On the next true rebuild, `list_tasks`
  re-joins the stored overlay (`open_tasks.list_tasks:431-441`) — the cached
  flip and the DB row reconcile to the same value (idempotent upsert,
  `OPEN_TASKS_ENGINE_DESIGN.md` §3).
- **Honesty label preserved.** The cached header keeps the original
  `נתונים: חי 🟢/מאוחסן ⚠️` plus `מעודכן: {built_iso}`; after the TTL it
  rebuilds, so a stale snapshot is never presented as fresh (CLAUDE.md).
- **No new push, no double-notify.** Still pull-only; risk_monitor untouched
  (G5).

### 1.5 Optional (non-blocking) warm-refresh

If `tasks_cache["enriched"]` is present and `task_refresh` is pressed within
TTL, `_load_tasks` *may* skip `repo.get_all_trades`+`get_open_positions_campaign`
and re-run only `open_tasks.list_tasks(supabase, enriched, now=...)` (re-reads
the lifecycle overlay, cheap SELECT). This is a pure optimization; if omitted,
`task_refresh` does the full rebuild. **Either way the engine is re-consulted
for state on explicit refresh** — we never serve `task_refresh` purely from a
status-mutated cache.

---

## 2. #4 — Short inline button labels (MEDIUM, UX)

### 2.1 Constraint and scheme

Telegram inline-button text has no hard char cap but practical legibility on a
phone (esp. RTL Hebrew + the persistent reply keyboard taking width) degrades
past ~**28–32 visible chars**. Today `build_tasks_keyboard`
(`telegram_tasks.py:230-252`) truncates `recommended_action` at **48** — still
too long, and it puts the full imperative on the *button*.

**New label scheme (button only):**

```
{urgency-glyph} {SYMBOL} — {short-tag}
```

- `urgency-glyph`: the existing `_BAND_ICON` map (`🛑/⚠️/🟡/🔵`,
  `telegram_tasks.py:52-58`) — no new vocabulary.
- `SYMBOL`: ticker (≤5 chars in practice).
- `short-tag`: a fixed **≤ 14-char** Hebrew noun-phrase keyed by
  `task_type` (table below) — NOT the sentence.
- Total budget ≈ `2 + 1 + 5 + 3 + 14 ≈ 25` visible chars → comfortably legible.

The full `recommended_action` (the engine/ruleset sentence, incl. RUNNER's
`{basis}, ${stop}`) appears **only in the detail card** (`handle_task_open`,
already renders `🎯 פעולה מומלצת:` at `telegram_tasks.py:402-403`) — unchanged
there. This is a render-only change in `build_tasks_keyboard`; the ruleset
text (Mark-owned) is not edited.

### 2.2 Per-`task_type` short tag

Tags are display sugar derived from the existing `_RULESET` task_types
(`OPEN_TASKS_METHODOLOGY_SPEC.md` §6). They are **not** methodology text (no
threshold, no instruction) so they are engineering-ownable; final wording
confirmation slot: **`⟨MARK: confirm tags are methodology-neutral⟩`**.

| `task_type` | urgency | short-tag (≤14, RTL) | gloss |
|---|---|---|---|
| `EXECUTE_EXIT` | P0 | `סגור עכשיו` | stop crossed / broken |
| `PROTECT_RUNNER_PROFIT` | P1 | `הדק (Runner)` | trail stop, runner |
| `TIGHTEN_STOP_PROFIT` | P2 | `הדק 2R+` | profit-protect |
| `REVIEW_YELLOW_FLAG` | P2 | `דגל צהוב` | review violation |
| `TRIM_OR_EXIT_DEAD_MONEY` | P3 | `הון מת` | trim/exit |
| `ALGO_OBSERVE_ONLY` | P3 | *(consolidated — see §3)* | not a per-row label |
| `COMPLETE_RISK_DATA` | — | `השלם נתונים` | data-incomplete info |

Unknown/future `task_type` → fall back to a 14-char trim of
`recommended_action` (the current behaviour, but at 14 not 48). The detail
card always carries the full text, so truncation never loses information.

---

## 3. #5 — Consolidated ALGO entry (FEATURE; gated on Mark / DEC-006)

### 3.1 What changes

Today ALGO surfaces as **one info-only row per ALGO position** via
`ALGO_OBSERVE_ONLY` (`_RULESET[ALGO_OBSERVED]`, `info_only=True`) →
`build_tasks_keyboard` renders each as a non-tappable `task_algo_noop` button
(`telegram_tasks.py:240-244`) whose tap is the dead-end popup the founder
flagged (SPRINT11_PLAN #5; `telegram_callbacks.py:79-85`).

**New:** collapse all ALGO-observed positions into **ONE** list entry:

```
🤖 ALGO (k) — בקרה
```

`k` = count of ALGO-observed positions. Tapping it opens a **read-out card**
(NOT a popup, NOT a Task): the disclaimer + a per-position observed line.

### 3.2 It is NOT a Task (hard invariant)

- The `ALGO_OBSERVE_ONLY` rule still produces `info_only=True` items in
  `open_tasks.derive_tasks` (engine/methodology unchanged — DEC-006 is UX-only;
  AGENTS.md #5/#8, DEC-20260511-001). They **never** count, never enter
  Win-Rate/Expectancy, never have `done`/`skip`/`note`, never instruct an
  ALGO stop write — exactly as today.
- The consolidated entry is a **pure UX projection** built in
  `telegram_tasks.py` at render time: `build_tasks_keyboard` filters the
  `info_only && task_type==ALGO_OBSERVE_ONLY` items out of the per-row loop
  and, if any exist, appends ONE synthetic button. No new dataclass, no
  lifecycle, no Supabase row. The `task_algo_noop` per-row path is removed
  from the ALGO case (the popup dies).

### 3.3 Callback + render contract

| Element | Value |
|---|---|
| Button label | `🤖 ALGO ({k}) — בקרה` |
| `callback_data` | `task_algo_panel` (new, fixed; no index — it is the whole ALGO set) |
| Router | new branch in `telegram_callbacks.handle_queries` next to `task_algo_noop` (`:79`): `if data == "task_algo_panel": bot.answer_callback_query(call.id); _tb.handle_algo_panel(chat_id); return` |
| Render fn | `telegram_tasks.handle_algo_panel(chat_id)` |
| Back | reuses existing `task_open|list` → `handle_open_tasks_entry` (cache-served per §1) |

**`handle_algo_panel(chat_id)` contract:**

- Source: the **cached** task list (§1) — read the `info_only` ALGO items
  from `tasks_cache["records"]`; never re-derives (consistent with #3). If
  cache absent → `_load_tasks` first (safe).
- Output shape (Hebrew RTL, short):
  1. **Disclaimer block (verbatim from Mark):** `⟨MARK: DEC-006 observer-safe
     disclaimer — exact non-binding Hebrew⟩`. Engineering does **not** invent
     this. Fallback if Mark cannot define a safe form: render only the
     red-line-safe alternative `⟨MARK: fallback "consolidated, no
     recommendations" wording⟩` (DEC-006 fallback option) — i.e. a single
     line "מנוהל חיצונית — אין פעולת Sentinel" and **no** per-position
     read-out at all.
  2. **Per-position observed read-out** (only if Mark authorises the
     advisory form): one line per ALGO position —
     `{SYMBOL}: {observed read-out}` where the read-out text is the
     engine's existing observed string rendered through
     **`⟨MARK: per-position observed read-out shape/label⟩`**. The number/
     state is the engine's own (carried on the cached enriched record —
     `state`, `open_r` snapshot) — never recomputed here (G1), always
     labelled snapshot (CLAUDE.md), never an instruction (G2/G4).
  3. Honest source label line (same `נתונים: חי 🟢/מאוחסן ⚠️` the list uses).
- Keyboard: single `⬅️ חזרה לרשימה` (`callback task_open|list`). No
  done/skip/note (it is not a Task).
- Empty ALGO set → the entry is simply not rendered (no button).

This satisfies DEC-006's hard constraint: descriptive of the engine's
observation only, explicitly non-binding, produces no `Task`, never feeds
stats, never instructs an ALGO stop.

---

## 4. #7 — ALGO out of stop-promote (MEDIUM, UX)

### 4.1 Exact change

`telegram_stop_promote.build_stop_promote_keyboard` (`:83-114`) currently
renders an ALGO position as a non-actionable `🟠 {sym} — מנוהל חיצונית
(ALGO)` / `promote_algo_noop` button (`:99-104`). The module already computes
`disc` (discretionary-only) in `handle_stop_promote_entry`
(`telegram_stop_promote.py:156`) and the doc-stated intent is
"discretionary only". The ALGO rows are pure noise in this flow (founder
finding #7).

**Change (additive, minimal):** in `build_stop_promote_keyboard`, **skip**
ALGO rows entirely instead of emitting an info button:

```
setup = str(row.get("setup_type", "")).upper()
if setup == "ALGO":
    continue          # was: markup.add(... promote_algo_noop ...)
```

`promote_algo_noop` callback handler (`telegram_callbacks.py:70-76`) is left
in place (harmless, still used nowhere else's regression risk) but is no
longer reachable from this keyboard. The discretionary buttons and the
existing header logic in `handle_stop_promote_entry` (`:156-166`, which
already counts `algo_n` and warns) are unchanged.

### 4.2 Empty-state copy if ALL positions are ALGO

`handle_stop_promote_entry` already branches on `if not disc:`
(`telegram_stop_promote.py:163-164`). With ALGO rows no longer rendered, that
branch must stand alone (the keyboard would otherwise be just `❌ סגור`).
Replace the appended-warning behaviour with an explicit early empty-state
(mirrors the module's own `אין פוזיציות פתוחות` path, `:145-147`):

> `{RTL}🎯 *קידום סטופ*\n`
> `{RTL}אין פוזיציות דיסקרציוניות לקידום סטופ.\n`
> `{RTL}כל הפוזיציות הפתוחות מנוהלות חיצונית (ALGO) — Sentinel אינה מנהלת סטופים של אלגו.`

with `reply_markup=get_portfolio_menu()` (same as the other empty/early
returns in that function). The mixed case (some ALGO, some not) keeps the
existing one-liner `_(פוזיציות ALGO … מנוהל חיצונית.)_` note — but since the
ALGO buttons are gone it is reworded to: `_(פוזיציות ALGO אינן מוצגות — מנוהל
חיצונית.)_`. Final Hebrew confirmation slot: **`⟨MARK: confirm #7 empty/mixed
copy is methodology-neutral⟩`** (it is pure UX; expected trivially OK).

---

## 5. #9 — User-facing audit review surface (DEC-008)

### 5.1 (a) Additive read function on `audit_logger.py`

`audit_logger.py` is **write-only by design** (module docstring lines 1-16).
DEC-008 adds a *deliberate, additive, clearly-named READ path* — it does not
relax the write-only spirit; it is a separate SELECT-only function alongside
`log_action`, same DI-`sb` pattern, never mutating.

**Signature / contract:**

```python
def read_recent_actions(
    sb: Any,
    *,
    chat_id: Optional[int] = None,
    limit: int = 20,
    actions: Optional[list[str]] = None,
) -> list[dict]:
    """Read-only, bounded retrospective view of recorded actions.

    SELECT-only. NEVER inserts/updates/deletes. Returns at most `limit`
    rows (hard-capped at _MAX_READ = 50), most-recent-first
    (ORDER BY created_at DESC — relies on audit_log's own timestamp;
    no fabricated ordering). `actions` optionally filters to a whitelist
    of action constants. On any error returns [] and logs to stderr
    (same fail-soft posture as log_action — a read failure must never
    raise into a user flow). Honest: returns rows exactly as stored;
    callers must label data source and must NOT derive performance
    numbers from these rows (Mark guardrail, AGENTS.md #1).
    """
```

- **SELECT-only enforcement:** body issues exactly one
  `sb.table(_AUDIT_TABLE).select(...).order("created_at", desc=True)
  .limit(min(limit, _MAX_READ)).execute()` (+ optional `.in_("action",
  actions)`). No `.insert/.update/.delete/.upsert`. `_MAX_READ = 50`
  module constant — bounded N (DEC-008 / Mark read-only guardrail).
- **No new imports** (keeps `audit_logger` importable from any layer, as its
  docstring requires). Fail-soft `try/except → []`, stderr print (mirrors
  `log_action`'s `except` at `:65-69`).
- Returned dicts are the raw stored rows (`action`, `chat_id`,
  `before_state`, `after_state`, `metadata`, `created_at`) — **no
  computation, no derived PnL/win-rate** (Mark: actions only, AGENTS.md #1).

### 5.2 (b) Menu placement — NORMAL user menu (not dev)

DEC-008 requires the NORMAL menu. The natural home is the portfolio
sub-menu, which already hosts the user-action surfaces
(`get_portfolio_menu()`, `telegram_menus.py:30-37`: חדר מצב / משימות פתוחות /
קידום סטופ / משטר שוק). Add ONE button **as the new last action row, directly
above `⬅️ חזרה לתפריט ראשי`**:

```python
def get_portfolio_menu():
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(telebot.types.KeyboardButton("📊 חדר מצב (פוזיציות)"))
    markup.add(telebot.types.KeyboardButton("📋 משימות פתוחות"))
    markup.add(telebot.types.KeyboardButton("🎯 קידום סטופ"))
    markup.add(telebot.types.KeyboardButton("🌡️ משטר שוק וסיכונים"))
    markup.add(telebot.types.KeyboardButton("🧾 הפעולות שלי"))          # ← NEW (here)
    markup.add(telebot.types.KeyboardButton("⬅️ חזרה לתפריט ראשי"))
    return markup
```

Rationale: it is a retrospective review of the user's *own* portfolio
decisions (DEC-008: "first-class user need, not dev/forensic"), so it sits at
the bottom of the same action stack — discoverable, never in `get_developer_menu()`.
It is **not** added to `get_developer_menu()` (`telegram_menus.py:20-27`).

### 5.3 (c) Hebrew RTL most-recent-first wireframe

A new additive module function (mirrors `telegram_tasks` / `telegram_stop_promote`
discipline — new logic in a small module, re-exported into `telegram_bot.py`;
no wholesale rewrite). Proposed home: extend `telegram_tasks.py` (it already
owns the user-review surface family) with `handle_my_actions(chat_id)`, or a
new sibling `telegram_audit_review.py` re-exported the same way (Wave-2's
call — both honour CLAUDE.md). It calls `audit_logger.read_recent_actions`.

Rendered actions (per DEC-008 / Mark guardrail — **actions only, NO fabricated
performance numbers, honest source labels**). Map raw `action`+`metadata` to
friendly Hebrew, most-recent-first:

| Stored | Friendly Hebrew line |
|---|---|
| `settings_change` + `metadata.kind=="stop_loosen_override"` | `🔓 ריפוי סטופ — {symbol}: ${before}→${after}` |
| `settings_change` (open-task done) | `✅ משימה בוצעה — {symbol} ({task_type})` |
| `settings_change` (open-task skip / `skipped_critical_exit`) | `⏭️ דילוג משימה — {symbol}` (+ `🛑 P0` if critical) |
| `risk_pct_change` | `🎚️ שינוי % סיכון: {before}%→{after}%` |
| other recorded constant | generic `• {action}` (never invented detail) |

**Wireframe:**

```
🧾 הפעולות שלי — 20 אחרונות
מקור: יומן ביקורת (audit_log) · ללא חישובי ביצועים

• 15/05 16:42  🔓 ריפוי סטופ — MRVL: $157.70→$1.00
• 15/05 16:41  🎚️ שינוי % סיכון: 1.00%→1.25%
• 15/05 12:03  ✅ משימה בוצעה — CAT (TIGHTEN_STOP_PROFIT)
• 14/05 21:18  ⏭️ דילוג משימה — NVDA  🛑 P0
…

(רשומות פעולה בלבד — לא ביצועים, לא רווח/הפסד.
 מוצג כפי שנשמר ביומן הביקורת.)
[🔄 רענן]   [⬅️ חזרה]
```

Honesty rules (CLAUDE.md / AGENTS.md #1 / Mark guardrail):
- Header states the source explicitly (`מקור: יומן ביקורת`) and
  `ללא חישובי ביצועים` — no win-rate, no PnL, no R aggregation is ever
  computed or shown here.
- Timestamps are the stored `created_at` rendered `DD/MM HH:MM` — no
  reordering beyond `ORDER BY created_at DESC`.
- Empty → `✅ אין פעולות מתועדות עדיין.` (never a fake row).
- Read error → `❌ לא ניתן לטעון את יומן הפעולות כעת. זה לא אומר שאין —
  נסה שוב.` (absence ≠ none; mirrors the tasks infra-error copy).
- Final wording confirmation slot: **`⟨MARK: confirm friendly labels carry
  no implied performance claim⟩`**.

### 5.4 (d) Command

Add a slash command alias `/myactions` alongside the button, mirroring the
`📋 משימות פתוחות`/`/tasks` pairing (`telegram_bot.py:407-408`). Wiring (all
additive, mirrors the existing tasks block exactly):

- `telegram_bot.py`: re-export `handle_my_actions` in the
  `from telegram_tasks import (...)` block (`:44-52`); add a routing line
  next to the tasks one (`:407`):
  `if text in ["🧾 הפעולות שלי", "/myactions"]: handle_my_actions(chat_id); return`.
- Help string (`telegram_bot.py:303` area): add
  `{RTL}/myactions — הפעולות שלי (יומן ביקורת)\n`.
- `telegram_callbacks.py`: a `myactions_refresh` callback branch next to
  `task_refresh` (`:87-90`) → `handle_my_actions(chat_id)`.

No change to `telegram_bot_secure_runner.py`; the surface is reached only
through the existing admin-gated message/callback handlers (same gate as
`/tasks` and `/promote`) — admin-only preserved (DEC-008, DEC-009).

---

## 6. #2 — Snapshot wording (LOW, UX)

The misleading string is in `handle_task_open` (`telegram_tasks.py:399`):

```
f"{RTL}• Open-R: `{r_str}` _(snapshot — לא מאומת כעת)_\n"
```

"לא מאומת כעת" implies a pending verification that never comes (finding #2).
The truth (SPRINT11_PLAN §"Direct answers"): it is the value **at task
creation**; the list re-derives live on every open. Replacement per Mark's
ruling — **`⟨MARK: DEC-#2 exact replacement Hebrew for the snapshot label⟩`**.

Engineering does not finalise this string. The methodology-neutral intent Mark
confirms is: *"value at task creation; the live list re-derives on every open"*
(SPRINT11_PLAN — Mark Wave-1 item (c) confirms #2 reword is
methodology-neutral). Proposed slot content for Mark's approval (NOT shipped
unless Mark returns it):

> `_(צילום בעת יצירת המשימה — הרשימה נגזרת מחדש בכל פתיחה)_`

The same token may appear in the cached-render header (§1) — wherever the
snapshot is shown, the *single* Mark-approved string is used (one source).

---

## 7. Risk classification, NOT-changing list, Wave-2 test plan

### 7.1 Risk classification (per CLAUDE.md)

| Item | Risk | Why |
|---|---|---|
| #3 cache-in-place | **MEDIUM** | New `user_state` cache + render-path change in `telegram_tasks.py`. Mitigated: additive, single module, bounded TTL, explicit-refresh always re-derives, writes unchanged, cache-miss safe-falls-back. |
| #4 short labels | **LOW** | Render-only string change in one function; detail card unchanged; ruleset text untouched. |
| #5 consolidated ALGO | **MEDIUM** (red-line-adjacent) | UX projection only, but DEC-006 is gated on Mark; wording is a verbatim slot. No engine/stat/Task change. Falls back to no-recommendation form if Mark cannot certify. |
| #7 ALGO out of stop-promote | **LOW** | One `continue`; empty-state copy; existing `disc` filter already intended this. |
| #9 audit read + menu + cmd | **MEDIUM** | New SELECT-only fn on a write-only module + new user surface. Mitigated: clearly-named separate fn, hard-capped N, no mutation, fail-soft, no derived numbers, admin gate unchanged. |
| #2 wording | **LOW** | One Mark-supplied string swap. |

Affected service: `telegram-bot` only (render + one additive read).
**Not affected:** `sentinel-bot`, `risk-monitor`, `reporting-service`,
`dashboard`, `engine_core`.

### 7.2 What we will NOT change (explicit)

- **`telegram_bot_secure_runner.py`** — admin guard & rate-limit (8/60s)
  untouched (CLAUDE.md, DEC-20260515-009).
- **R / NAV / exposure / campaign / Win-Rate / Expectancy math** — zero new
  or changed math; `_enrich_positions`/`derive_tasks` consume the engine
  verbatim (G1, AGENTS.md #2/#8).
- **Ratchet-up loosen guard** (`guard_stop_write`/`finalize_pending_loosen`,
  `telegram_stop_promote.py:301-395`) — untouched; it remains the only
  loosen path and the `stop_loosen_override` audit row stays the read
  surface's input, not its output.
- **`telegram_bot.py`** — NOT rewritten: only additive re-export entries,
  routing lines, one help line (mirrors the proven `telegram_stop_promote` /
  `telegram_tasks` integration).
- **ALGO observer red line** — ALGO never becomes a Task, never counted,
  never instructed (DEC-20260511-001, AGENTS.md #5/#8); #5 is UX projection
  only.
- **`open_tasks.py` engine/lifecycle contract** — unchanged; the Supabase
  write path (`mark_done`/`skip_task`/`add_note` + `audit_logger`
  fail-open) is unchanged; the cache is a render layer above it.
- **No new Telegram push / no double-notify** — all surfaces pull-only;
  risk_monitor anti-spam untouched (AGENTS.md #7, G5).
- **`audit_logger.log_action`** — unchanged; the read fn is strictly
  additive and SELECT-only (write-only spirit preserved).
- **No migration** — #9 reads the existing `audit_log` (migration 002); #3
  uses in-memory `user_state` only. (If Wave-2 finds a schema need it
  follows the 003 pattern and is flagged — none expected.)

### 7.3 Wave-2 test plan (enumerated)

Pure-unit, deterministic, no network (per `tests/` rules); extends
`tests/test_telegram_tasks.py` + a new `tests/test_audit_review.py`.
Baseline to keep green: **1523**.

**#3 cache-and-update-in-place**
1. `_load_tasks` populates `tasks_cache` with `records/enriched/built_ts`.
2. `done`/`skip`/`skip_reason` → `open_tasks.mark_done`/`skip_task` called
   **exactly once** AND `handle_open_tasks_entry` does **not** trigger
   `repo.get_all_trades`/`ec.get_open_positions_campaign`/
   `ec.compute_position_state` (mock-asserts: zero engine/repo calls on the
   post-action re-render).
3. Cache-staleness: `built_ts` aged > 180s → next entry **does** re-derive
   (full pipeline mocks fire exactly once).
4. Explicit `task_refresh` → always re-derives even within TTL (engine
   re-consulted); cached status flip does not survive a refresh that the DB
   overlay contradicts (reconcile to DB value).
5. Cache-miss (no `tasks_cache`) on a lifecycle action → safe fallback to
   full `_load_tasks`, no crash.
6. In-place mutate flips only the acted row's `status`; other rows and
   `enriched` untouched; header counts recomputed from cache (no engine).
7. `cancel_action` clears `user_state` → next entry rebuilds (no stale
   serve).

**#4 labels**
8. Every `task_type` → label matches `{glyph} {SYM} — {tag}` and visible
   length ≤ 32; unknown `task_type` → 14-char trim fallback.
9. Detail card still shows the **full** `recommended_action` (incl. RUNNER
   `{basis}/{stop}`) — unchanged.

**#5 ALGO consolidated**
10. ALGO-not-a-task: with k ALGO + m discretionary, `build_tasks_keyboard`
    emits exactly ONE `task_algo_panel` button and **zero**
    `task_algo_noop`; ALGO items never have `done/skip/note`; never in any
    count; never in Win-Rate/Expectancy inputs (assert `info_only`
    preserved, status never settable).
11. `handle_algo_panel`: renders the Mark-slot disclaimer, per-position
    read-out from the **cache** (no engine call), honest source label, only
    `⬅️ חזרה לרשימה`. With Mark fallback set → no per-position
    recommendation lines at all.
12. Zero ALGO positions → no `task_algo_panel` button rendered.

**#7 stop-promote ALGO filter**
13. `build_stop_promote_keyboard` with ALGO rows → **no** ALGO buttons, **no**
    `promote_algo_noop`; discretionary buttons unchanged.
14. All-ALGO → explicit empty-state copy + `get_portfolio_menu()`; mixed →
    reworded note, discretionary buttons present.

**#9 audit read**
15. `read_recent_actions` issues **only** a `.select(...).order(...).limit(...)`
    chain — assert no `.insert/.update/.delete/.upsert` ever called
    (SELECT-only).
16. `limit` honoured and hard-capped at `_MAX_READ=50` (request 999 → ≤50).
17. Most-recent-first ordering (`created_at DESC`); empty table → `[]` (and
    UI shows the empty copy, not a fake row).
18. `sb` raising → returns `[]`, never raises into the handler (fail-soft).
19. `actions` whitelist filters correctly when provided.
20. Renderer maps `stop_loosen_override`, task done/skip(+P0), `risk_pct_change`
    to the friendly Hebrew lines; **no** PnL/win-rate/R aggregation computed
    anywhere in the path (assert no engine import in the read surface).
21. `/myactions` + button + `myactions_refresh` callback all route to
    `handle_my_actions`; admin gate path identical to `/tasks` (no new
    unauthenticated entry; secure_runner untouched).

**#2 wording**
22. Detail card no longer contains the literal `לא מאומת כעת`; contains the
    Mark-approved snapshot string (single source, same token in the cached
    header).

**Regression**
23. Full suite stays green at ≥1523; no change to `open_tasks.py`,
    `engine_core.py`, `telegram_bot_secure_runner.py`, migrations; existing
    `test_open_tasks.py` / `test_telegram_tasks.py` Sprint-10 cases unaffected.

---

## 8. Patterns reused (no new primitives)

| Need | Reused from |
|---|---|
| Batch cache, mutate-in-place, no heavy re-run | `telegram_stop_promote` `temp_positions` (`:152-200`) |
| `user_state[chat_id]` as the cache store | existing `task_records` / `temp_positions` convention |
| One tap-only inline row per item | `build_tasks_keyboard` / `build_stop_promote_keyboard` |
| Additive module + re-export into `telegram_bot.py` | `telegram_stop_promote` / `telegram_tasks` block (`:37-52`) |
| Callback routing branch | `telegram_callbacks.handle_queries` `task_*` chain (`:78-147`) |
| SELECT-only DI-`sb`, fail-soft | `audit_logger.log_action` posture (`:36-69`) |
| Honest "absence ≠ none" infra-error copy | `handle_open_tasks_entry` (`:312-324`) |
| Menu button placement convention | `get_portfolio_menu()` action stack (`:30-37`) |

— Architecture + Adaptive UX, Sprint 11 Wave 1
