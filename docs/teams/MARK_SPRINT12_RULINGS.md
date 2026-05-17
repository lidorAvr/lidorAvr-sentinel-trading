# Mark — Sprint 12 Rulings

**Author:** Mark (Methodology Owner — Minervini SEPA canon)
**Branch:** `claude/review-system-audit-FBZ2h`
**Date:** 2026-05-15
**Sprint:** 12 — close the carried-open items (T7, `/clean` gate,
price-fallback labelling, missing-stops)
**Status:** authoritative. Operationalizes the carried items in
`SPRINT11_PLAN.md:43-46` / `SPRINT11_WAVE2_IMPL.md:38-39`. Extends
`OPEN_TASKS_METHODOLOGY_SPEC.md`; does not supersede `AGENTS.md` /
`CLAUDE.md` / `MARK_SPRINT11_RULINGS.md`. Standing principle unchanged:
**read-only presentation over the engine's existing output; zero new
R/NAV/exposure/campaign math** (`AGENTS.md:7`, invariant #2;
`CLAUDE.md` "Do not change R, NAV, exposure, or campaign math").

Code grounded (verified file:line): `adaptive_risk_engine.py:27-29,33`
(`DRAWDOWN_TRIGGER_PCT=-8.0`, `DRAWDOWN_CUT_TO_PCT=0.40`,
`DRAWDOWN_WINDOW_DAYS=30`, `RISK_SETTLE_HOURS=48.0`),
`:222-259` (`drawdown_auto_cut_recommendation`), `:84` (settle);
`risk_monitor.py:77` (`adaptive_risk` P3), `:938-997` (the existing
adaptive-risk PUSH alert), `:56-79` (`ALERT_PRIORITY`);
`telegram_bot.py:377-399` (`/clean`), `supabase_repository.py:55-56,63-64`
(`get_old_trades`/`update_trade`); `telegram_stop_promote.py:67-69`
(`_compute_open_r` price fallback), `:364-403` (`finalize_pending_loosen`
ratchet-confirm + `stop_loosen_override` audit),
`telegram_portfolio.py:74-76,173,256` (price fallbacks);
`audit_logger.py:28-36` (action constants), `:46-49` (fail-open);
`OPEN_TASKS_METHODOLOGY_SPEC.md:291-293` (T7 already declared
out-of-position-contract); `tests/test_open_tasks.py:549-636` (drift
test: bidirectional `set(spec.keys())==set(code.keys())`).

---

## 1. T7 — portfolio-level drawdown-acknowledgement task

### 1.1 Trigger — read-only over the engine's own computation

The trigger is **exactly** `adaptive_risk_engine.drawdown_auto_cut_recommendation(...)`
returning a non-`None` dict (`adaptive_risk_engine.py:222-259`). T7 does
**not** recompute drawdown, NAV, or PnL — it consumes that one engine call
(the same one `risk_monitor.py:938-997` already consumes). No constant is
invented: the cut fires at `drawdown_pct <= DRAWDOWN_TRIGGER_PCT` (−8.0,
`:27`) over `DRAWDOWN_WINDOW_DAYS` (30, `:29`), forcing risk to
`DRAWDOWN_CUT_TO_PCT` (0.40, `:28`); all three are read live from
`adaptive_risk_engine`, never copied (mirrors the `_TRAIL_MA_BUFFER_PCT`
discipline, `MARK_SPRINT11_RULINGS.md` §1.1). If the function returns
`None` (drawdown not bad enough, OR risk already ≤ floor, OR invalid
inputs — `:239,246,248`) there is **no T7** (never fabricate an ack for a
cut that did not happen — `AGENTS.md:9` #1).

### 1.2 Hebrew action text — descriptive acknowledgement, not an instruction

The cut **already happened automatically**. T7 is an "I saw this", never
"go change risk". Exact text (uses only engine-returned `drawdown_pct`
and the constants, no Sentinel-derived number):

```
‏🩸 ירידה של {drawdown_pct}% ב-30 יום — הסיכון כבר הורד אוטומטית ל-0.40%.
‏זו הודעה לאישור בלבד. אין פעולת מסחר. אשר שראית.
```

`{drawdown_pct}` is the engine's own `round(drawdown_pct,2)`
(`adaptive_risk_engine.py:252`); `0.40` is `DRAWDOWN_CUT_TO_PCT`
literal-from-constant. Zero imperative trading verb (no "הורד/שנה/צא").
This matches the §1 table T7 phrasing intent
(`OPEN_TASKS_METHODOLOGY_SPEC.md:46`) — kept descriptive.

### 1.3 Urgency — reuse existing tier, no new scale

**P3**, reusing `ALERT_PRIORITY["adaptive_risk"]="P3"` verbatim
(`risk_monitor.py:77`; `OPEN_TASKS_METHODOLOGY_SPEC.md` §4 G7). It is an
acknowledgement of an already-applied protection, not a critical action —
P3 is correct and is not a new severity.

### 1.4 Lifecycle — ack-only, with an honest auto-clear

- **Requires explicit user "done"** (the ack). It is NOT auto-satisfied
  by a state transition — there is no per-position state here
  (`OPEN_TASKS_METHODOLOGY_SPEC.md` §3 "Requires explicit user 'done':
  T7 — always").
- **Auto-clear (honest, not a state flip):** T7 auto-closes with
  `reason=condition_cleared` only when `drawdown_auto_cut_recommendation`
  **subsequently returns `None`** (drawdown recovered OR risk no longer
  above the 0.40 floor — `adaptive_risk_engine.py:246,248`) AND the risk
  settle window has elapsed (`get_risk_settle_info()["active"]==False`,
  built on `RISK_SETTLE_HOURS=48.0`, `:33,84`). Auto-clear is permitted
  here (unlike a P0 BROKEN exit, §3 K5) because the underlying *fact* —
  an active forced cut — genuinely no longer holds; nothing unactioned is
  being laundered (the cut was automatic, not a user duty). An
  un-acked-but-recovered T7 still records its un-ack: it closes
  `reason=condition_cleared`, never `done` (honesty — the user did not
  ack; do not pretend they did, `AGENTS.md:9` #1).

### 1.5 HARD anti-double-notify rule (binary — FAIL = do not ship T7)

The push already exists: `risk_monitor.py:938-997` emits the adaptive-risk
alert (with its 24h same-direction dedup `:951-954` and the 48h settle
gate `:956-960`). **T7 is the PULL surface only.** Mandatory rule:

> T7 MUST NOT emit, schedule, or trigger ANY Telegram message. It is
> created/closed silently inside the Open Tasks pipeline and is seen
> **only** when the user opens `📋 משימות פתוחות`. The push channel for
> the drawdown cut is and remains `risk_monitor.py:938-997` exclusively.
> A T7 that sends its own notification = FAIL (`AGENTS.md` invariant #7;
> Red Line `AGENTS.md:72` analogue / "recurring alert without
> per-position dedup"; `OPEN_TASKS_METHODOLOGY_SPEC.md` §4 G5; §5 K6).
> This is the same view-not-alerter contract every other task obeys.

T7 carries no second cooldown/dedup of its own; the monitor owns push,
the list owns lifecycle. They are different surfaces over the *one* engine
fact and must never duplicate it.

### 1.6 Keying + stats firewall (portfolio-level, not per-campaign)

T7 is portfolio-wide. Ruling: key it `(campaign_id="__PORTFOLIO__",
task_type="ACK_DRAWDOWN_CUT")` — a reserved sentinel that is **not** a
real `{SYMBOL}_{tradeID}` campaign_id (DEC-20260512-004 format), so the
existing one-open-task-per-`(campaign_id,task_type)` dedup
(`OPEN_TASKS_METHODOLOGY_SPEC.md` §3) gives exactly one live T7. HARD:

> `__PORTFOLIO__` MUST NOT enter `compute_position_state`, any per-campaign
> stat, WR, Expectancy, PF, `total_r`, or `is_stat_countable`
> (`engine_core.py` STAT buckets). It is a portfolio acknowledgement, never
> a campaign outcome (`AGENTS.md:16` invariant #8; Red Line
> `AGENTS.md:72`; `MARK_SPRINT11_RULINGS.md` 2.3 rule 2 analogue). Any
> stat aggregation MUST filter `campaign_id=="__PORTFOLIO__"` out.

### 1.7 Exact §6 spec edit + `_RULESET`-shape implication (drift test STAYS GREEN)

**Critical drift-test finding** (`tests/test_open_tasks.py:549-636`):
`_parse_spec_ruleset` parses every top-level `STATE:` row in the §6
fenced ```yaml block and `test_ruleset_matches_methodology_spec` asserts
`set(spec.keys()) == set(code.keys())`, where `code` keys are the
`ec.POSITION_STATE_*` constants in `open_tasks._RULESET`. T7 has **no**
`compute_position_state` state. Therefore:

> **RULING:** T7 MUST NOT be added as a row in the §6 fenced ```yaml block
> and MUST NOT be added to `open_tasks._RULESET`. Doing either adds a key
> on exactly one side of the bidirectional set-equality and **breaks the
> drift test**. T7 is, by construction, outside the position-driven
> `derive_tasks(positions, …)` contract — exactly as already declared at
> `OPEN_TASKS_METHODOLOGY_SPEC.md:291-293`.

`_RULESET`-shape implication: **`_RULESET` is unchanged** (still the 7
`POSITION_STATE_*` keys). T7 lives in a **separate, parallel constant**
in `open_tasks.py` (e.g. `_PORTFOLIO_TASKS`) NOT referenced by
`load_ruleset()` / the drift comparison, and is derived by a separate
portfolio-level path (e.g. `derive_portfolio_tasks(drawdown_rec)`) that
the list merges in alongside `derive_tasks(...)`. The drift test only
guards `_RULESET`; this keeps it green by design.

**Exact §6 edit (the ONLY change to the spec):** replace the existing
bullet at `OPEN_TASKS_METHODOLOGY_SPEC.md:291-293` with:

> - T7 (drawdown-ack) is **portfolio-level, not a per-position state** — it
>   is out of the position-driven `derive_tasks(positions, …)` contract
>   and is **deliberately NOT a row in the ```yaml block below and NOT in
>   `open_tasks._RULESET`** (adding it either side breaks the
>   bidirectional drift test `test_ruleset_matches_methodology_spec`). It
>   is derived by a separate portfolio path keyed
>   `(campaign_id="__PORTFOLIO__", task_type="ACK_DRAWDOWN_CUT")`, urgency
>   **P3** (`ALERT_PRIORITY["adaptive_risk"]`, `risk_monitor.py:77`),
>   `info_only:false` ack-task, triggered iff
>   `adaptive_risk_engine.drawdown_auto_cut_recommendation()`
>   (`adaptive_risk_engine.py:222-259`) returns non-`None` (read-only over
>   the engine; constants `:27-29,33` read live, never copied). It emits
>   **no** Telegram push (the push is `risk_monitor.py:938-997`; G5,
>   §1.5). It never enters WR/Expectancy/any stat (`AGENTS.md` #8). Ack-
>   only; auto-closes `reason=condition_cleared` when the engine call later
>   returns `None` and the 48h settle elapsed — never as `done` unless the
>   user acked (`AGENTS.md` #1; Mark Sprint-12 §1).

No ```yaml row changes. No `_RULESET` row changes. Drift test untouched.

---

## 2. `/clean` confirmation gate (bulk Supabase write)

`telegram_bot.py:377-399` runs **immediately on tap** — it iterates
`repo.get_old_trades` (`supabase_repository.py:55-56`) and calls
`repo.update_trade` (`:63-64`, a `trades` UPDATE) per row, with **no
confirmation**. This is a bulk Supabase mutation with no gate. Ruling:

### 2.1 Mandatory confirmation UX (reuse the ratchet-confirm pattern)

Adopt the exact pattern of `finalize_pending_loosen`
(`telegram_stop_promote.py:364-403`): stash a pending op in `user_state`,
require an explicit inline confirm, **default = NO**. The tap must FIRST
do a read-only dry-run (`get_old_trades` SELECT only — `:55-56` is already
SELECT) and show, before any write:

```
‏🧹 ניקוי ארכיון — *פעולה בכתיבה ל-Supabase*.
‏יעודכנו {n} עסקאות מעל 30 יום (השלמת שדות חסרים בלבד).
‏מוגן ולא ייגע: כל עסקה מ-30 הימים האחרונים, וכל קמפיין פתוח.
‏לאישור הקש "כן, נקה ארכיון". ברירת המחדל: *לא*.
```

Buttons: `❌ לא, בטל` (default / left, mirrors `:387-389`) and
`כן, נקה ארכיון`. No write happens until the explicit YES. Cancel/timeout
= no write, byte-identical to today's pre-tap state. `{n}` is the literal
dry-run row count, never an estimate (`AGENTS.md:9` #1).

### 2.2 Audit requirement

On confirmed execution, write **one** `audit_logger.log_action` row
(fail-open, `audit_logger.py:46-49`) using
`ACTION_SETTINGS_CHANGE` (`audit_logger.py:35` — same kind
`finalize_pending_loosen` uses for a bulk/override write, `:393`), with:

```
metadata = {"kind": "archive_sweep_clean",
            "candidates": <n_before>, "updated": <count_after>,
            "cutoff_date": <thirty_days_ago>}
```

`before` = `{"rows_to_update": n_before}`, `after` =
`{"rows_updated": count_after}`. This makes the sweep reviewable in the
DEC-008 surface (Mark Sprint-11 §4.2 SURFACE — it is a user-decided
write). No new action constant (new constants default to OMIT, Sprint-11
§4.2).

### 2.3 What must NEVER be deletable, even with confirm

- `/clean` does **UPDATE only** (field backfill), never DELETE. The gate
  must NOT add a delete path. Rows are mutated, never removed.
- The **30-day protection is absolute**: only trades with
  `trade_date < thirty_days_ago` (`telegram_bot.py:380`) are ever
  candidates. Confirmation does NOT widen this window. Anything inside 30
  days is untouchable regardless of confirm.
- **Open campaigns are never swept**: any `campaign_id` with open
  quantity is excluded even if old (an open position's risk fields are
  live methodology data, not legacy backfill — `AGENTS.md` #4;
  `CLAUDE.md` "Do not mutate Supabase from read-only flows"). If the
  current `get_old_trades` cannot guarantee this, the dry-run MUST filter
  open-campaign rows out before showing `{n}` and before any write.

---

## 3. Price-fallback labelling (invariant #1)

Sites where `ec.get_live_price()` returns `None` and the caller silently
substitutes `entry`/`last`: `telegram_stop_promote.py:67-69`
(`_compute_open_r` → `curr = entry`), `telegram_portfolio.py:74-76`
(`curr = entry`), `:173` (`or float(row["price"])`), `:256`. Today these
present a fallback-derived price/Open-R as if exact — a soft
fallback-as-truth (`AGENTS.md:9` invariant #1, Red Line `AGENTS.md:68`
"Silently fallback from live price… to old/default values"; `CLAUDE.md`
"be clear about fallback/cached data").

> **RULING — honest label standard.** Whenever a displayed price, Open-R,
> open-PnL, or weight is derived from a value substituted **because
> `ec.get_live_price()` returned `None`** (i.e. the live quote was
> unavailable and `entry`/`row["price"]`/last was used), the surface MUST
> append, immediately after that number, exactly:
>
> ```
> ‏⚠️ (מחיר לא חי — לפי מחיר כניסה, לא בזמן אמת)
> ```
>
> **WHEN to show it (precise):** show the label **iff** the
> `get_live_price()` call for that symbol returned `None` and a fallback
> was used for that displayed figure. If the live price WAS obtained, show
> **no** label (do not noise up the normal path). The decision is
> per-figure and binary on the actual `None` from `get_live_price()` —
> never a guess. If the fallback itself is also missing/invalid (no
> `entry`), show the existing honest "לא זמין" phrasing — never a
> fabricated number (`AGENTS.md` #1; `MARK_SPRINT11_RULINGS.md` §3
> precedent). The label describes the source; it never restates or
> recomputes the number (zero new math).

This is presentation-only at the four cited call sites; no R/NAV math
changes, no engine change.

---

## 4. Missing-stops (the 55 rows)

Finding #11 (`SPRINT11_PLAN.md:22`): Health shows "Missing Stops — 55 rows
(MSGE, SNEX, TSLA, JPM, HP)". Pre-existing data hygiene, NOT introduced by
the Open Tasks work.

> **RULING.** Surface it ONLY as a **non-numeric data-hygiene notice** —
> never an action-item, never counted. It is the exact
> `DATA_INCOMPLETE` / `COMPLETE_RISK_DATA` shape already ruled in
> `OPEN_TASKS_METHODOLOGY_SPEC.md` §1 ("DATA_INCOMPLETE produces no
> numeric task at all", `:49-55`) / §6 `DATA_INCOMPLETE` row: a
> "complete your data" prompt carrying **no R, no $, no urgency tier**,
> excluded from every stat (`AGENTS.md:16` invariant #8;
> `MARK_SPRINT11_RULINGS.md` checkpoint #8). It is allowed to state the
> **count and symbols verbatim from the existing Health check** (a
> factual hygiene readout — that is honest, not a fabricated metric),
> e.g.:
>
> ```
> ‏⚠️ נתוני סיכון חסרים: 55 רשומות (MSGE, SNEX, TSLA, JPM, HP).
> ‏השלם entry/stop כדי שייכללו. (אינו משימה, אינו נספר בסטטיסטיקה.)
> ```
>
> **NO fabricated stop, ever** — Sentinel must never invent, infer, or
> default a stop to "fix" these rows (`AGENTS.md` #1; Red Line
> `AGENTS.md:68`). It is a notice, not a repair. The remediation (the
> user completing entry/stop, or the separate data-hygiene pass
> `SPRINT11_PLAN.md:44`) stays out of Sprint-12 automated scope; only the
> honest *notice* is in scope.

---

## 5. Pass/fail checklist — Sprint-12 consolidation meeting

Run by the team-leads at consolidation. Any FAIL = that item does not
ship.

1. **T7 read-only.** Trigger is `drawdown_auto_cut_recommendation()`
   non-`None` only; constants read live from `adaptive_risk_engine`
   (`:27-29,33`), never copied; zero new R/NAV/PnL math. (AGENTS.md #2;
   DEC-20260515-007 discipline; §1.1.)
2. **T7 ack-only + honest text.** Descriptive Hebrew, zero imperative
   trading verb; states the cut already happened. (AGENTS.md #1; §1.2.)
3. **T7 anti-double-notify (HARD).** T7 emits NO Telegram push; push stays
   `risk_monitor.py:938-997` exclusively. (AGENTS.md #7; Red Line
   `AGENTS.md:72`; spec §4 G5; §1.5.)
4. **T7 keying + stats firewall.** `__PORTFOLIO__` sentinel; never enters
   `compute_position_state`/WR/Expectancy/PF/`total_r`. (AGENTS.md #8;
   Red Line `AGENTS.md:72`; §1.6.)
5. **T7 drift test green.** T7 NOT in §6 ```yaml block and NOT in
   `_RULESET`; only the §6 bullet at `:291-293` rewritten;
   `test_ruleset_matches_methodology_spec` passes. (Spec §6; §1.7.)
6. **`/clean` gate.** Defaulted-NO explicit confirm, dry-run names `{n}`
   rows + the 30-day/open-campaign protection BEFORE any write; reuses
   the ratchet-confirm pattern (`telegram_stop_promote.py:364-403`).
   (AGENTS.md #4; CLAUDE.md; §2.1.)
7. **`/clean` audit.** One `ACTION_SETTINGS_CHANGE` row,
   `kind=archive_sweep_clean`, before/after counts; fail-open.
   (DEC-20260515-008; Mark Sprint-11 §4.2; §2.2.)
8. **`/clean` protection absolute.** UPDATE-only (no delete path); <30d
   and open campaigns untouchable even with confirm. (AGENTS.md #4;
   Red Line `AGENTS.md:68` spirit; §2.3.)
9. **Price-fallback labelled.** Every fallback site
   (`telegram_stop_promote.py:67-69`, `telegram_portfolio.py:74-76,173,
   256`) shows the exact label iff `get_live_price()` returned `None`;
   no label on the live path; no fabricated number. (AGENTS.md #1;
   Red Line `AGENTS.md:68`; §3.)
10. **Missing-stops = notice only.** Non-numeric, never an action-item,
    never counted, no fabricated stop; reuses the `DATA_INCOMPLETE`
    shape. (AGENTS.md #8; spec §1 `:49-55`; §4.)
11. **Global invariants intact.** Admin-only, `telegram_bot_secure_runner.py`
    untouched (CLAUDE.md; AGENTS.md #3); no Supabase trade mutation from
    read-only flows (AGENTS.md #4); `telegram_bot.py` additive wiring
    only, no wholesale rewrite (CLAUDE.md).
12. **Suite green incl. drift test.** `pytest -q` fully green; baseline
    1569 (`SPRINT11_WAVE2_IMPL.md:5`); `test_ruleset_matches_methodology_spec`
    green (DEC-20260515-007 lockstep preserved).

---

— Mark
