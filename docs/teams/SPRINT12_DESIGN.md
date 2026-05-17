# Sprint 12 — Architecture + Adaptive-UX Design (carried-open closeout)

**Sprint:** 12 — Wave 1 (design)
**Team:** 🏗️ Architecture + 🤝 Adaptive UX
**Status:** DESIGN ONLY. No production code, no migration, no git commit/push.
**Branch:** `claude/review-system-audit-FBZ2h`
**Date:** 2026-05-15
**Inputs:** `SPRINT11_WAVE2_IMPL.md` (the shipped Open Tasks engine — suite
1569 green; drift test `test_ruleset_matches_methodology_spec` green),
`SPRINT11_DESIGN.md`, `SPRINT11_PLAN.md` carried items (§"Out of scope"),
`DECISIONS.md` DEC-20260515-007/-008, `MARK_SPRINT11_RULINGS.md`, the live
code (`open_tasks.py`, `telegram_tasks.py`, `telegram_stop_promote.py`,
`telegram_audit_review.py`, `audit_logger.py`, `adaptive_risk_engine.py`,
`risk_monitor.py`, `telegram_bot.py`, `supabase_repository.py`,
`telegram_portfolio.py`, `telegram_formatters.py`).

> **Gate.** Items keyed to Mark consume `MARK_SPRINT12_RULINGS.md` (Wave 1,
> authored in parallel — **not on disk at design time**, confirmed absent).
> Every place that needs Mark's methodology text/threshold is a literal slot
> **`⟨MARK:…⟩`** the Wave-2 build copies **verbatim**. Engineering invents
> **no** methodology wording, no threshold, no Hebrew compliance string. If a
> slot is unresolved at the checkpoint, that sub-item does **not** ship (the
> rest is independent and ships).

This doc **extends** the Sprint-10/11 designs; it contradicts none of them.
All Sprint-10 guardrails (G1–G9) and the Sprint-11 §7.2 NOT-changing list
remain in force.

Carried items closed here: **T7 portfolio drawdown-ack task**, **`/clean`
confirmation gate**, **price-fallback labelling**, **#11 missing-stops
surface** (SPRINT11_PLAN §"Out of scope (logged)" + §43-46;
SPRINT11_WAVE2_IMPL §38-39).

---

## 1. T7 — portfolio-level drawdown-ack task (EXTENSION of the Sprint-11 engine)

### 1.1 The hard structural constraint (verified in code + tests)

The Sprint-11 Open Tasks engine derives tasks from **per-position engine
state**. `open_tasks.derive_tasks(positions, *, now, ruleset)` is a pure
projection over a *list of position dicts*, each carrying `state_result`
(`open_tasks.py:351-436`). `_RULESET` is keyed by **`engine_core`
POSITION_STATE_* constants** (`open_tasks.py:140-215`), and the CI drift test
`tests/test_open_tasks.py::test_ruleset_matches_methodology_spec`
(`:593-620`) asserts `set(_RULESET.keys()) == set(spec.keys())` against
Mark's `OPEN_TASKS_METHODOLOGY_SPEC.md` §6 fenced `yaml` block
(`OPEN_TASKS_METHODOLOGY_SPEC.md:295-335`).

There is **no** `POSITION_STATE_PORTFOLIO` / `POSITION_STATE_DRAWDOWN`
constant in `engine_core` (grep-verified). Mark's §6 block §291-293 already
ruled: *"T7 (drawdown-ack) is **portfolio-level, not a per-position state** —
it is out of the position-driven `derive_tasks(positions,…)` contract."*

**Therefore the red line for T7:** it MUST NOT be added to `_RULESET`, MUST
NOT be added to the §6 yaml block, and MUST NOT be emitted by
`derive_tasks`. Doing any of those breaks the drift test (a new key in one
side, absent in the other) and the `set(...)==set(...)` assertion fails CI.
T7 is a **sibling derivation** that joins the *same lifecycle table + same
list/cache/render*, not a new ruleset row.

### 1.2 Source: read-only over the EXISTING drawdown output (zero new math)

`adaptive_risk_engine.drawdown_auto_cut_recommendation(closed_campaigns,
current_risk_pct, nav)` (`adaptive_risk_engine.py:222-259`) already returns,
when 30-day realised PnL ≤ `DRAWDOWN_TRIGGER_PCT` (-8% of NAV), a dict:
`{force_cut_to_pct, drawdown_pct, pnl_30d_usd, n_trades, window_days,
reason}`. `compute_adaptive_risk` surfaces the same under `override ==
"drawdown_auto_cut"` plus `drawdown_pct` / `drawdown_pnl_usd`
(`adaptive_risk_engine.py:549-568`).

T7 **reads that existing output** (the same `closed_campaigns` /
`current_risk_pct` / `nav` already gathered in `_load_tasks`'s lightweight
path — see `telegram_tasks.py:256-260` `get_nav_and_risk`). It computes
**zero** new R / NAV / exposure / campaign / drawdown math — it is a
read-only *presence test* over `drawdown_auto_cut_recommendation(...) is not
None` (G1; AGENTS.md #2; CLAUDE.md "do not change R/NAV/campaign math"). The
trigger threshold, the window, the cut target are **already methodology
constants owned by Jordan/Risk** (`DRAWDOWN_TRIGGER_PCT` etc.) — T7 does not
introduce or re-tune any of them.

### 1.3 Shape: a synthetic portfolio task, keyed `__PORTFOLIO__`, ack-only

A portfolio task is structurally a `Task` with:

| field | value |
|---|---|
| `task_type` | `PORTFOLIO_DRAWDOWN_ACK` (new constant, **not** in `_RULESET`) |
| `campaign_id` | `"__PORTFOLIO__"` (the per-Mark synthetic key; never a real `{SYMBOL}_{tradeID}` — DEC-20260512-004 format, so it can never collide with a campaign) |
| `symbol` | `"תיק"` (portfolio, not a ticker) |
| `urgency` | `⟨MARK: T7 urgency tier — P-band for a portfolio drawdown acknowledgement⟩` |
| `info_only` | **`True`** — ack-only; it is NOT an instruction to change risk (risk_monitor owns that flow, §1.5). Never counted in WR/Expectancy/PF/total_r (same invariant as ALGO/DATA_INCOMPLETE, G3). |
| `recommended_action` | `⟨MARK: T7 exact non-binding Hebrew — descriptive drawdown notice; states the observed 30d drawdown % and that risk_monitor handles the cut; NO imperative⟩` |
| `trigger_snapshot` | `state="PORTFOLIO_DRAWDOWN"` (a *snapshot label string only*, **never** an `engine_core.POSITION_STATE_*` and never added to `_RULESET`), `reason = dd["reason"]` verbatim from the engine output |

**Derivation seam (drift-test-safe).** Add a separate pure helper in
`open_tasks.py` — NOT a `_RULESET` entry, NOT inside `derive_tasks`'s
position loop:

```
PORTFOLIO_CID = "__PORTFOLIO__"
TASK_PORTFOLIO_DRAWDOWN_ACK = "PORTFOLIO_DRAWDOWN_ACK"

def derive_portfolio_tasks(*, drawdown_rec: Optional[dict], now: datetime,
                           ruleset=None) -> list[Task]:
    """Pure. drawdown_rec is the CALLER-supplied output of
    adaptive_risk_engine.drawdown_auto_cut_recommendation (or None).
    Returns [] when drawdown_rec is None (no fabricated task — AGENTS.md #1
    absence is not a task). Emits exactly ONE ack-only Task when present."""
```

`list_tasks` gains an optional `portfolio_drawdown` kwarg; when supplied it
appends `derive_portfolio_tasks(...)` to the derived list **before** the
lifecycle left-join, so the existing
`overlays.get((campaign_id, task_type))` join (`open_tasks.py:506-516`)
transparently carries a stored `done`/`skipped` overlay for
`("__PORTFOLIO__", "PORTFOLIO_DRAWDOWN_ACK")` — **the existing `open_tasks`
table + the existing `mark_done`/`skip_task` upsert handle it with zero
schema change** (keyed by `(user_id, campaign_id, task_type)`; the unique
index already makes a re-tap idempotent). No new migration.

**Why the drift test stays green:** `_RULESET` and the §6 yaml block are
**untouched** — not one key added on either side. `derive_portfolio_tasks`
is a parallel function that never reads `_RULESET`; the
`set(spec.keys())==set(code.keys())` assertion still compares the same 7
position states on both sides. New unit tests cover the new helper; the
drift test is unaffected by construction (explicitly asserted in §5.3 case
D).

### 1.4 Surfaced in the EXISTING list + cache + lifecycle

`telegram_tasks._load_tasks` (`telegram_tasks.py:239-324`) is the single
builder. It already fetches `target_risk_usd` via `get_nav_and_risk`
(`:256-260`); it additionally derives `closed_camps =
are.compute_closed_campaigns(df)` (df already built at `:244`) and `dd =
are.drawdown_auto_cut_recommendation(closed_camps, current_risk_pct, nav)`
(read-only; same call `risk_monitor` already makes — no new math), then
passes `portfolio_drawdown=dd` into `open_tasks.list_tasks`.

- The resulting ack Task flows through the **existing**
  `open_only`/`_grouped_sorted`/`cached_records` pipeline
  (`telegram_tasks.py:269-302`) unchanged — it is just another `Task`. It
  gets a `cached_records` dict like any other (its `campaign_id` is
  `"__PORTFOLIO__"`, `task_type` `"PORTFOLIO_DRAWDOWN_ACK"`).
- It appears in `📋 משימות פתוחות` rendered by `build_tasks_keyboard`
  (`telegram_tasks.py:395-433`). Because `info_only=True` and `task_type`
  is **not** `ALGO_OBSERVE_ONLY`, it takes the existing non-ALGO info-only
  branch (`telegram_tasks.py:411-418`) → a non-tappable info row. (`⟨MARK:
  T7 short-tag ≤14 RTL chars for the info row label⟩` added to
  `_TASK_SHORT_TAG`, `telegram_tasks.py:80-87` — display sugar only, same
  rule as the existing tags.)
- Cache: served from `tasks_cache` per Sprint-11 §1 with zero changes — it
  is one more record in `cached_records`. TTL/invalidation
  (`_cache_valid`, `telegram_tasks.py:332-348`) unchanged.
- Lifecycle: ack = the existing **`✅ בוצע`** path. Detail card
  (`handle_task_open`) for an `info_only` task already shows only
  `⬅️ חזרה לרשימה` (`_detail_keyboard`, `:436-441`). For T7 we want an
  explicit *acknowledge* affordance, so T7 is `info_only=True` for stats
  purposes **but** `handle_task_open` adds a single `✅ הבנתי` button for
  `task_type == PORTFOLIO_DRAWDOWN_ACK` that routes to the **existing**
  `task_done|{idx}` → `open_tasks.mark_done(supabase,"__PORTFOLIO__",
  "PORTFOLIO_DRAWDOWN_ACK")` (unchanged authoritative write + fail-open
  audit, `open_tasks.py:611-636`) then `_apply_local_status` re-render
  (Sprint-11 §1.2). **No skip, no note** (it is an acknowledgement, not a
  decision with alternatives). Ack-only confirmed: `⟨MARK: confirm T7 is
  ack-only — acknowledge, never skip/note⟩`.

### 1.5 The exact double-notify prevention vs risk_monitor (CRITICAL)

`risk_monitor.py:938-1017` already **pushes** an adaptive-risk alert
(`🎯 התראת סיכון אדפטיבי`) with YES/NO inline buttons when
`compute_adaptive_risk(...)["direction"] != "hold"` (which a drawdown
auto-cut forces to `down_fast`, `adaptive_risk_engine.py:562`). That push
is throttled to once / 24h per direction with a 48h settle gate
(`risk_monitor.py:951-962`; DEC-20260510-007).

T7 must **not** become a second notification of the same event. The
mechanism (defense in depth — all four hold simultaneously):

1. **T7 is PULL-ONLY. It adds zero push path.** It is rendered only when the
   user opens `📋 משימות פתוחות`. This is the same G5 invariant the whole
   Open Tasks surface already obeys (`telegram_tasks` docstring `:13-14`;
   SPRINT11_DESIGN §1.4 "No new push, no double-notify"). `risk_monitor` is
   **not touched** — its anti-spam state (`state["risk_alert"]`,
   `risk_monitor.py:1010-1015`) is untouched (Sprint-11 §7.2; AGENTS.md #7).
2. **Different channel, different intent.** risk_monitor's push is an
   *actionable risk-change confirmation* (it mutates `risk_pct` via the
   `risk_confirm` callback). T7 is a *passive acknowledgement record* in the
   pull-only task list — it never changes `risk_pct`, never offers a
   confirm-risk button, never calls `update_risk_pct`. They are not the same
   message type, so even if both are visible there is no duplicated
   *action*.
3. **One-shot dedupe via the existing lifecycle table.** Once acked, the
   `open_tasks` row `("__PORTFOLIO__","PORTFOLIO_DRAWDOWN_ACK")` has
   `status=done`; `list_tasks`'s existing left-join (`open_tasks.py:506-516`)
   marks it done so `_open_views_from_cache` (`telegram_tasks.py:482-491`,
   filters `status==open`) drops it from the list. It re-appears only if the
   *engine output* still says drawdown AND the user has not acked the
   *current* episode — see (4).
4. **Episode keying so an old ack doesn't mask a NEW drawdown, and a
   re-render doesn't re-notify.** The ack must be scoped to the drawdown
   *episode*, not forever. Per Mark: `⟨MARK: T7 episode key definition —
   what makes two drawdown observations "the same episode" vs a new one
   (engineering proposes: the engine's own DRAWDOWN_WINDOW_DAYS bucket /
   the rec's reason string; Mark rules the exact equivalence)⟩`. The episode
   token is stored in the `notes`/`metadata` of the existing lifecycle row
   (append-only, `_upsert_lifecycle` already supports notes) — **no schema
   change**. `derive_portfolio_tasks` emits the task with the current
   episode token; `list_tasks` treats a stored `done` overlay as
   satisfying-the-task **only when its episode token equals the current
   one** (else it is a *new* episode → surfaced again, exactly once, still
   pull-only). This guarantees: same episode + already acked → not shown
   (no double-notify, no nag); new episode → shown once. risk_monitor's
   independent 24h/48h throttle is the analog guard on *its* channel and is
   left exactly as is.

Net: the **only** thing that can ever notify is risk_monitor's existing
throttled push. T7 is a silent, pull-only, ack-once line in a list the user
chose to open. Zero new push. Verified by the §5.3 test cases (T7
no-stat-pollution, dedup, no-push).

### 1.6 `⟨MARK⟩` slots for T7 (verbatim, build copies; engineering invents none)

- `⟨MARK: T7 urgency tier⟩` — P-band (or null-class) for a portfolio
  drawdown ack.
- `⟨MARK: T7 exact non-binding Hebrew recommended_action⟩` — descriptive
  notice; states observed 30d drawdown % + that risk_monitor handles the
  forced cut; no imperative; honest (the engine's own `dd["drawdown_pct"]`
  number, never recomputed).
- `⟨MARK: T7 short-tag ≤14 RTL⟩` — info-row label.
- `⟨MARK: confirm T7 is ack-only (acknowledge; never skip/note)⟩`.
- `⟨MARK: T7 episode-key equivalence definition⟩` — when two drawdown
  observations are the same episode vs a new one.
- `⟨MARK: T7 audit kind⟩` — the `metadata.kind` for the ack lifecycle row
  (engineering proposes `portfolio_drawdown_ack`; Mark rules — it must be a
  surface-able kind so it shows in `🧾 הפעולות שלי`, see §3-note below).

---

## 2. `/clean` confirmation gate (defaulted-NO, reuse the ratchet pattern)

### 2.1 What `/clean` does today (verified)

`telegram_bot.py:377-399`: on `🧹 ארכיון עסקאות (Legacy)` / `/clean` the bot
**immediately**, with no confirmation, computes `thirty_days_ago` and loops
`repo.get_old_trades(supabase, thirty_days_ago)`
(`supabase_repository.py:55-56`, SELECT `trade_date < before_date`), and for
each row with a missing field issues `repo.update_trade`
(`supabase_repository.py:63-64`, an UPDATE) backfilling `setup_type=Legacy`,
`quality=-1`, sentinel stops `-1`, etc. It is a destructive-ish bulk write
fired on a single tap. The "30-day protection" exists (the `< before_date`
filter) but is silent and unconfirmed.

### 2.2 Design: explicit defaulted-NO inline confirm (reuse `guard_stop_write`)

Mirror the proven ratchet-up loosen gate exactly
(`telegram_stop_promote.guard_stop_write` / `finalize_pending_loosen`,
`telegram_stop_promote.py:319-413`; `loosen_confirm|yes/no` callback,
`telegram_callbacks.py:165`). That pattern is the house standard for
"dangerous bulk action → defaulted-safe confirm → audit row → then the
byte-identical write".

**Flow:**

1. `/clean` no longer writes. It runs **only the SELECT preview**:
   `rows = repo.get_old_trades(supabase, thirty_days_ago)` then computes,
   read-only (the *same* needs-update predicate as today, lifted into a pure
   helper — no logic change), `to_archive = N` (rows that *would* be
   updated) and `protected = M` (rows newer than 30 days are never in
   `get_old_trades`; additionally rows belonging to an **open campaign**
   must be excluded — see the protected-rows invariant below). It then
   sends a defaulted-NO inline confirm:

   > `{RTL}🧹 *ניקוי ארכיון — אישור נדרש*`
   > `{RTL}{N} שורות יסומנו כ-Legacy/יושלמו (מעל 30 יום).`
   > `{RTL}{M} שורות מוגנות (פחות מ-30 יום / קמפיין פתוח) — לא ייגעו.`
   > `{RTL}ברירת המחדל היא *לא לבצע*.`
   > buttons (row_width=1, NO first):
   > `[✅ לא — אל תבצע]  callback clean_confirm|no`
   > `[⚠️ כן, בצע ניקוי ({N} שורות)]  callback clean_confirm|yes`

2. State stash (mirrors `loosen_pending`): `user_state[chat_id] =
   {"action": "clean_pending", "pending": {"before_date":…, "n":N,
   "m":M}}`. The default / dismissal / `cancel_action` path = **no-op**
   (exactly like `finalize_pending_loosen`'s rejected branch,
   `telegram_stop_promote.py:384-390`).

3. **Reject (default, `clean_confirm|no` or any timeout/cancel):**
   `user_state.pop`, send `{RTL}✅ בוטל — לא בוצע ניקוי.`, no DB write. Zero
   side effects.

4. **Confirm (`clean_confirm|yes`):** write **one audit row FIRST**
   (fail-open, before the bulk write, exactly like
   `finalize_pending_loosen:392-403`):
   `audit_logger.log_action(supabase, audit_logger.ACTION_SETTINGS_CHANGE,
   chat_id=chat_id, metadata={"kind": ⟨MARK: /clean audit kind — engineering
   proposes "archive_clean_bulk"; Mark rules the exact kind string⟩,
   "before_date": before_date, "rows_to_archive": N, "rows_protected": M})`.
   Then run **the existing bulk-write loop UNCHANGED** — the exact
   `for t in repo.get_old_trades(...)` / `repo.update_trade(...)` body from
   `telegram_bot.py:382-395`, byte-identical, only relocated behind the
   gate. Then the existing success message + `get_next_missing(chat_id)`
   tail (`:396-399`) unchanged.

### 2.3 Protected-rows invariant (must never be deleted/mutated)

"Protected" = (a) `trade_date` within 30 days — already enforced by
`get_old_trades`'s `< before_date` filter (untouched), AND (b) any row whose
`campaign_id` is in the currently-open set
(`ec.get_open_positions_campaign`). Today's loop does NOT exclude open
campaigns; the gate's **preview** counts them as protected and the confirmed
write must **skip** them. This is the one behavioural hardening (a row in an
open campaign must never be back-filled with sentinel `-1` stops while the
position is live — that would corrupt live risk math). It is an *added
guard around* the write, not a change to the write's field logic (the
`upd={...}` dict construction is byte-identical). `⟨MARK: confirm open-
campaign rows are protected from /clean back-fill⟩` (expected trivially OK —
it only ever protects live data; it can never archive more than today).

### 2.4 Callback / state / audit summary

| element | value |
|---|---|
| confirm callback_data | `clean_confirm|yes` , `clean_confirm|no` (mirrors `loosen_confirm|yes/no`) |
| router | new branch in `telegram_callbacks.handle_queries` next to `loosen_confirm` (`telegram_callbacks.py:165`): `if data.startswith("clean_confirm|"): _tb.finalize_pending_clean(chat_id, data.split("|")[1]=="yes"); return` |
| user_state action | `"clean_pending"` (mirrors `"loosen_pending"`) |
| default | **NO** (defaulted-safe; reject = no-op) |
| audit kind | `⟨MARK: /clean audit kind⟩` (proposed `archive_clean_bulk`) on `ACTION_SETTINGS_CHANGE`, written **before** the bulk write, fail-open |
| handlers | `handle_clean_entry` (preview+confirm) and `finalize_pending_clean` — additive, mirror `guard_stop_write`/`finalize_pending_loosen`; the bulk-write *logic itself is unchanged* |

`telegram_bot.py:377-399` becomes: build preview → send confirm → return.
The write body moves verbatim into `finalize_pending_clean`. This is
additive routing + a gate, not a rewrite (Sprint-11 §7.2; CLAUDE.md no
`telegram_bot.py` wholesale rewrite).

---

## 3. Price-fallback labelling (label only — no math change anywhere)

When `ec.get_live_price(sym)` returns `None`, several sites silently
substitute the **entry price** as the current price. The number then looks
live but is a fallback — exactly the AGENTS.md #1 / CLAUDE.md
"fallback-as-truth" violation the founder flagged. The fix is **label
only**: where a displayed value derives from a fallen-back price, render
Mark's honest label string next to it. No formula, no threshold, no
fallback *behaviour* changes — the substitution stays (removing it would
blank the screen); only the honesty annotation is added.

Mark owns the exact label: **`⟨MARK: price-fallback honest label — short RTL
Hebrew, e.g. "מחיר לא חי — שווי לפי כניסה"; one canonical string reused at
every site⟩`** (single source, like `_SNAPSHOT_LABEL`,
`telegram_tasks.py:74`).

### 3.1 Enumerated flagged sites (file:line) and exact label point

| # | Site (file:line) | Fallback today | Where the label goes (non-invasive) |
|---|---|---|---|
| F1 | `telegram_stop_promote.py:67-68` (`_compute_open_r`: `curr = ec.get_live_price(...)`; `if curr is None: curr = entry`) | open-R for the button label computed off entry-as-price | `_compute_open_r` already returns `(open_r, curr)`; add a 3rd return flag `price_is_fallback` (no math change — pure bool of `ec.get_live_price() is None`). `build_stop_promote_keyboard` (`:103-111`) appends the Mark label to the button text / a header note when any row is fallback. |
| F2 | `telegram_portfolio.py:74-76` (single-position room: `curr=get_live_price`; `if None: curr=entry`) | position-card current price / weight / P&L all off entry | After the existing card render, append one `{RTL}_⟨MARK label⟩_` line **iff** `ec.get_live_price(symbol) is None` (the function already knows it fell back at `:75`). No recompute — only a conditional label append. |
| F3 | `telegram_portfolio.py:173` (`curr = ec.get_live_price(sym) or float(row["price"])`) | per-row current price falls back to entry | Track a per-row `fallback` bool at the same point; if any row fell back, add the Mark label to the existing footer note region (same place `nav_stale_label` is appended, `:191-192`). |
| F4 | `telegram_portfolio.py:256-258` (portfolio room loop: `curr=get_live_price`; `if None: curr=entry`) | per-position P&L / value / weight off entry | Same as F3: per-row fallback bool, aggregate into the existing footer (`:417-418` region where `nav_stale_label` is shown). |
| F5 | `telegram_formatters.py:38` (`fmt_position_card`: prints `נוכחי: ${curr:.2f}`) | `curr` is passed in by the caller; if the caller fell back, the card shows the fallback price unlabelled | `telegram_formatters` is a **pure formatter** (DEC-20260510-005 — no engine import). So the caller passes a new `price_is_fallback: bool` kwarg (default `False` → byte-identical for every existing caller/test); when `True`, `fmt_position_card` renders the Mark label inline after the price. The fallback *detection* stays in the caller (F2/F4), the formatter only displays the label. |

Note `telegram_tasks._enrich_positions` (`telegram_tasks.py:122-126`,
`218`) already sets `data_quality="stale"` / `_data_quality` on fallback and
the list header already shows `נתונים: מאוחסן ⚠️` + the partial-data warning
(`telegram_tasks.py:524-533`). That surface is **already honest** — Mark
confirms whether its existing wording is sufficient or should adopt the same
canonical label: `⟨MARK: confirm tasks-list stale label is sufficient or
unify with the canonical price-fallback string⟩` (no code change if "stays").

All five edits are: add a bool that mirrors an `is None` already evaluated,
and conditionally append/insert one Mark-supplied string. **No R / NAV /
weight / open-R / P&L number changes** (G1; AGENTS.md #2; CLAUDE.md). Risk:
LOW (string + bool only).

---

## 4. Missing-stops surface (#11) — data-hygiene notice, never a numeric task

SPRINT11_PLAN §22 / §44: "Health: Missing Stops — 55 rows (MSGE, SNEX,
TSLA, JPM, HP)" is **pre-existing data hygiene, not introduced by Sprint
10**, logged for a separate pass. Mark's §6 ruling and DEC framing keep
DATA_INCOMPLETE strictly **non-counted, non-numeric** (`open_tasks.py:
207-214`, `urgency=None`, `info_only=True`).

**Design (minimal, non-invasive, gated on Mark):** a *data-hygiene notice*,
**not** a Task, **never** counted, **never** in `_RULESET`/`derive_tasks`
(same red line as T7 §1.1 — adding it to the ruleset breaks the drift test).
Engineering proposes the smallest honest surface: a single read-only line in
the existing `/health` output (or the tasks-list footer) of the form
`⟨MARK: missing-stops notice — exact non-numeric Hebrew; states "N rows
lack a stop — data hygiene, not a trading signal"; explicitly NOT a task,
never counted⟩`, sourced read-only from the existing incomplete-trades
query (`supabase_repository.get_incomplete_trades`, no new query, no new
math).

**This sub-item is fully Mark-gated.** Per the task brief: design the
minimal surface OR mark out-of-scope **if Mark rules so**. Slot:
`⟨MARK: SPRINT12 ruling — is the missing-stops notice IN SCOPE for Sprint 12
(as the minimal non-task hygiene line above) or explicitly OUT OF SCOPE
(deferred to the standalone data-hygiene pass per SPRINT11_PLAN §44)?⟩`. If
Mark returns OUT-OF-SCOPE, nothing ships for #11 (the rest of Sprint 12 is
independent and ships). Engineering invents no wording and no threshold here.

---

## 5. Risk classification, NOT-changing list, Wave-2 test plan

### 5.1 Risk classification (per CLAUDE.md)

| Item | Risk | Why / mitigation |
|---|---|---|
| **T7 portfolio drawdown-ack** | **MEDIUM** (methodology-adjacent) | New sibling derivation + new lifecycle key on a methodology surface. Mitigated: read-only over an EXISTING engine output (zero new math, G1); NOT in `_RULESET` so the drift test is untouched by construction; pull-only (no new push, G5); reuses the existing `open_tasks` table + write path (no migration); ack-only; episode-keyed dedupe; all methodology strings/tiers/episode-equivalence are verbatim `⟨MARK⟩` slots. |
| **`/clean` confirm gate** | **MEDIUM** | Gates a destructive bulk write. Mitigated: reuses the proven `guard_stop_write` defaulted-NO + audit-first pattern; the bulk-write logic itself is byte-identical; default = no-op; adds a protected-rows guard that can only ever protect *more* data. |
| **Price-fallback labelling** | **LOW** | Label + bool only; no math, no threshold, no fallback-behaviour change; pure-formatter gets a defaulted kwarg (existing callers byte-identical). |
| **Missing-stops surface** | **LOW** | Read-only, non-numeric, never a task/count; fully Mark-gated (may be out-of-scope). |

Affected service: **`telegram-bot` only** (render + read-only derivation +
one gated bulk write that already existed). **Not affected:** `sentinel-bot`,
`risk-monitor` (explicitly untouched — §1.5), `report-scheduler`,
`dashboard`, `engine_core`, `adaptive_risk_engine` (read-only consumer only).

### 5.2 What we will NOT change (explicit)

- **`telegram_bot_secure_runner.py`** — admin guard & rate-limit (8/60s)
  untouched (CLAUDE.md; DEC-20260515-009).
- **R / NAV / exposure / campaign / Win-Rate / Expectancy / stop math** —
  zero new or changed math. T7 is a presence-read over
  `drawdown_auto_cut_recommendation`; fallback labels touch no number; the
  `/clean` field-fill dict is byte-identical (G1; AGENTS.md #2/#8;
  CLAUDE.md "do not change R/NAV/campaign math").
- **Ratchet-up loosen guard** (`guard_stop_write` /
  `finalize_pending_loosen`, `telegram_stop_promote.py:319-413`) —
  untouched; `/clean` *reuses its pattern*, it does not modify it.
- **The existing `/clean` bulk-write logic itself** — relocated verbatim
  behind the gate; the `upd={...}` construction and `repo.update_trade`
  calls are byte-identical.
- **`open_tasks._RULESET` + the §6 yaml block + `derive_tasks` position
  loop** — not one key/row changed; T7 is a separate function. The drift
  test `test_ruleset_matches_methodology_spec` stays green by construction.
- **`risk_monitor.py`** — its adaptive-risk push, anti-spam state, 24h/48h
  throttle (`:938-1017`) are untouched. T7 is pull-only — no second
  notification (AGENTS.md #7; SPRINT11 §7.2).
- **`audit_logger.log_action`** and the SELECT-only `read_recent_actions` —
  unchanged; `/clean` and T7 ack reuse `log_action` exactly (fail-open).
- **No new migration** — T7 reuses the existing `open_tasks` table (keyed
  `(user_id, campaign_id, task_type)`; `"__PORTFOLIO__"` is just a
  collision-proof `campaign_id` value); `/clean` writes the existing
  `audit_log` (migration 002). In-memory `user_state` for the confirm gate.
- **`telegram_bot.py`** — additive routing + a gate only; the surface and
  the write are not rewritten (CLAUDE.md).
- **No fallback presented as truth** — every fallback site gets an explicit
  honest label; T7's number is the engine's own `drawdown_pct`, never
  recomputed (AGENTS.md #1).

### 5.3 Wave-2 test plan (enumerated; deterministic, no network)

Extends `tests/test_open_tasks.py`, `tests/test_telegram_tasks.py`, a new
`tests/test_clean_gate.py`, `tests/test_price_fallback_label.py`.
**Baseline to keep green: 1569** (SPRINT11_WAVE2_IMPL §5).

**T7 portfolio drawdown-ack**
- **A. derive:** `derive_portfolio_tasks(drawdown_rec=None,…)` → `[]` (no
  fabricated task); a real `dd` dict → exactly ONE `Task` with
  `campaign_id="__PORTFOLIO__"`, `task_type="PORTFOLIO_DRAWDOWN_ACK"`,
  `info_only=True`, `reason==dd["reason"]` verbatim; `now`-pure
  (referential transparency).
- **B. dedup / lifecycle:** acked → `mark_done(supabase,"__PORTFOLIO__",
  "PORTFOLIO_DRAWDOWN_ACK")` called **exactly once**; `list_tasks`
  left-join marks it `done`; `_open_views_from_cache` drops it (not
  re-shown for the *same* episode). A *new* episode token → surfaced again
  exactly once (old ack does not mask it).
- **C. no-stat-pollution:** with T7 present, WR / Expectancy / PF /
  total_r / counts are byte-identical to without it (assert it is excluded
  exactly like ALGO/DATA_INCOMPLETE — `info_only`, never countable).
- **D. drift test green (regression):** `derive_portfolio_tasks` does NOT
  add any key to `_RULESET`; `set(_RULESET)==set(spec §6)` still holds;
  `test_ruleset_matches_methodology_spec` passes unchanged. Explicit assert
  `"PORTFOLIO_DRAWDOWN_ACK" not in {e.task_type for v in
  open_tasks._RULESET.values() for e in v}`.
- **E. no-push / no-double-notify:** building/rendering T7 issues **zero**
  `bot.send_message` push and **zero** `risk_monitor` calls; `risk_monitor`
  module not imported in the tasks render path; risk_monitor's
  `state["risk_alert"]` untouched.

**`/clean` confirm gate**
- **F. default-NO:** `/clean` sends the preview confirm and performs **zero**
  `repo.update_trade` calls before a `clean_confirm|yes`; the keyboard's
  default/first action is NO.
- **G. reject = no-op:** `clean_confirm|no` (and `cancel_action`) → zero
  `repo.update_trade`, `user_state` cleared, "בוטל" message.
- **H. confirm path:** `clean_confirm|yes` → audit row written **before**
  the first `repo.update_trade`; then the bulk write runs and is
  **byte-identical** to the legacy loop (same `upd` dicts for the same
  input rows — golden-compare against the pre-gate logic).
- **I. protected rows never deleted/mutated:** rows < 30 days
  (not in `get_old_trades`) AND rows whose `campaign_id` is in the open set
  receive **zero** `repo.update_trade`; preview `M` counts them.
- **J. idempotent / state:** double-tap `clean_confirm|yes` does not run the
  bulk write twice (pending cleared on first resolve, like
  `finalize_pending_loosen`).

**Price-fallback label**
- **K. appears only on fallback:** with `ec.get_live_price` mocked to return
  a real price → label string **absent** at F1–F5; mocked to `None` →
  label **present** (exactly once per affected surface); the displayed
  numbers are **unchanged** between the two runs except for the added
  label (assert no numeric diff).
- **L. pure-formatter default:** `fmt_position_card` without the new kwarg
  is byte-identical to today (every existing formatter test passes
  unchanged).

**Missing-stops surface** (only if Mark rules IN-SCOPE)
- **M.** the notice is read-only, non-numeric, produces no `Task`, never
  enters any count; absent if Mark ruled OUT-OF-SCOPE.

**Regression / baseline**
- **N.** full suite stays green at **≥1569**; `test_open_tasks.py` /
  `test_telegram_tasks.py` Sprint-10/11 cases unaffected; no change to
  `open_tasks._RULESET`, the §6 yaml block, `engine_core.py`,
  `adaptive_risk_engine.py` math, `telegram_bot_secure_runner.py`,
  `risk_monitor.py`, migrations.

---

## 6. Patterns reused (no new primitives)

| Need | Reused from |
|---|---|
| Defaulted-NO confirm + audit-first + then byte-identical write | `guard_stop_write` / `finalize_pending_loosen` (`telegram_stop_promote.py:319-413`) |
| `user_state[chat_id]` pending-action stash | `loosen_pending` convention |
| Callback routing branch | `telegram_callbacks.handle_queries` `loosen_confirm|` (`:165`) |
| Sibling derivation joining the same lifecycle table | `open_tasks.list_tasks` left-join (`:481-517`) + existing `open_tasks` table |
| Cache + in-place re-render for the new task | Sprint-11 `tasks_cache` (`telegram_tasks.py:239-622`) — unchanged |
| Single canonical honest label string, one source | `_SNAPSHOT_LABEL` (`telegram_tasks.py:74`) |
| Pure formatter gets a defaulted kwarg, callers byte-identical | DEC-20260510-005 `telegram_formatters` contract |
| Pull-only, no new push (no double-notify) | Whole Open Tasks surface (G5; SPRINT11 §1.4) |

— Architecture + Adaptive UX, Sprint 12 Wave 1
