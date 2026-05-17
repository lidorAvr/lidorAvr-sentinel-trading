# Mark — Sprint 11 Rulings

**Author:** Mark (Methodology Owner — Minervini SEPA canon)
**Branch:** `claude/review-system-audit-FBZ2h`
**Date:** 2026-05-15
**Sprint:** 11 — founder smoke-test fixes (Wave 1, methodology gate)
**Status:** authoritative. Operationalizes DEC-20260515-006/-007/-008. Does
not supersede `AGENTS.md` / `CLAUDE.md` / `MARK_DAY3_GUARDRAILS.md` /
`OPEN_TASKS_METHODOLOGY_SPEC.md` — it extends the last for Sprint 11.

Mandatory inputs read: `docs/teams/SPRINT11_PLAN.md`; `docs/DECISIONS.md`
(DEC-20260515-006:797-818, -007:821-837, -008:840-856, DEC-20260511-001:424-459,
DEC-20260515-002:700-720, DEC-20260515-004:748-769); `AGENTS.md` (invariants
#1/#5/#8 `AGENTS.md:9-16`, Red Lines `AGENTS.md:61-73`); `CLAUDE.md`;
`docs/teams/OPEN_TASKS_METHODOLOGY_SPEC.md` (§1 ruleset, §6 machine-readable
block, §4 G1–G9); `docs/teams/MARK_DAY3_GUARDRAILS.md` (§2.2/§5 C3, §2.5).
Code grounded: `engine_core.py:1887` (`_TRAIL_MA_BUFFER_PCT=0.02`),
`engine_core.py:1911-1960` (`compute_suggested_trail_stop()`),
`engine_core.py:457-464` (ALGO engine output),
`engine_core.py:2007-2010` (ALGO_OBSERVED state),
`telegram_tasks.py:399` (snapshot wording),
`audit_logger.py:23-31` (action constants).

**Standing principle (carried from `OPEN_TASKS_METHODOLOGY_SPEC.md:19-25`):**
Every Sprint-11 change here is a *read-only presentation/suppression* over the
engine's existing output. Zero new R / NAV / exposure / campaign thresholds.
Accuracy over confidence (`CLAUDE.md` "When uncertain").

---

## 1. DEC-007 — RUNNER suppression epsilon (methodology)

**Decision context.** DEC-20260515-007 (`docs/DECISIONS.md:821-837`):
`PROTECT_RUNNER_PROFIT` (T3, `OPEN_TASKS_METHODOLOGY_SPEC.md:42`, §6 `RUNNER`
block `:283-287`) is **not** emitted when the campaign's current stop already
satisfies the engine's own `compute_suggested_trail_stop()`. Mark must fix the
epsilon as a methodology threshold, NOT an invented number.

### 1.1 Epsilon — anchored, not invented

The only defensible anchor is the engine constant the suggested stop itself is
built on: **`_TRAIL_MA_BUFFER_PCT = 0.02`** (`engine_core.py:1887`). The
suggested stop is `MA × (1 − buffer)` for the MA21/MA50 cases
(`engine_core.py:1937,1941`). The buffer is *already* the engine's own
declared tolerance band between the structural MA and the actionable stop.
Re-using it as the suppression epsilon means: "a tighten smaller than the
engine's own MA-buffer is inside the noise the engine itself tolerates — not a
material methodology event." This invents nothing; it reads a shipped constant.

> **RULING — epsilon definition (methodology):**
> `epsilon = _TRAIL_MA_BUFFER_PCT * suggested_stop` (i.e. **2% of the engine's
> own suggested stop level**), `_TRAIL_MA_BUFFER_PCT` read live from
> `engine_core.py:1887` — never hard-copied into `open_tasks.py`. For the
> `breakeven` basis (no MA, `engine_core.py:1944-1946`) the same 2%-of-
> suggested-stop applies (entry price is the suggested stop there). If
> `suggested_stop is None` or `basis == "none"` (`engine_core.py:1960`) there
> is **no suggestion to compare** → T3 is emitted unchanged (never suppress on
> absent engine output — that would be fallback-as-truth, AGENTS.md #1).

Rationale for *percentage-of-suggested-stop* (not absolute $, not % of price):
the engine expresses its own tolerance as a fraction of the MA-derived level;
the epsilon must live in the same unit so a $158 name and a $15 name are
judged on the same methodological basis. The MRVL live case
(`SPRINT11_PLAN.md:12`): suggested $158.11 → epsilon ≈ $3.16; current $157.70
is `157.70 ≥ 158.11 − 3.16 = 154.95` → **True → suppressed**, exactly the
$0.41 (0.26%) no-op the founder flagged. A *material* tighten — e.g. current
$150 vs suggested $158.11 (gap $8.11 > $3.16) — stays `False` → **T3 still
surfaces**. Confirmed: a real tighten is never hidden.

### 1.2 Exact suppression boolean (long; read-only)

Let `S = compute_suggested_trail_stop(...).["suggested_stop"]` and
`B = .["basis"]` (engine_core.py:1928-1929); `C = ` the campaign's existing
`current_stop` (the value the engine is already fed, `engine_core.py:414`,
`build_management_action(...current_stop...)`). For a long:

```
suppress_runner_task = (
    S is not None
    and B != "none"
    and C is not None and C > 0
    and C >= S - (_TRAIL_MA_BUFFER_PCT * S)
)
```

- **Read-only over the engine's own output.** `S`, `B` come verbatim from
  `compute_suggested_trail_stop()`; `C` is the already-stored campaign stop;
  `_TRAIL_MA_BUFFER_PCT` is read from the engine module. **No new R / NAV /
  exposure / campaign math** — this is a comparison of two engine-produced
  numbers (`OPEN_TASKS_METHODOLOGY_SPEC.md` §4 G1; AGENTS.md #2; CLAUDE.md
  "Do not change R, NAV, exposure, or campaign math without tests"). It does
  not recompute `compute_suggested_trail_stop` — it consumes one call.
- **Direction is tighten-only.** Suppression triggers only when the stop is
  *already at or above* (suggested − ε): i.e. already protected. This never
  produces, recommends, or implies a *lower* stop — it only withholds a
  redundant *raise* task. It therefore cannot conflict with the ratchet-up
  rule (`MARK_DAY3_GUARDRAILS.md` §2.2 U3/U4, §5 C3; `OPEN_TASKS_METHODOLOGY_
  SPEC.md` §4 G4): suppression removes a no-op tighten, it never loosens.
- **Short side:** symmetric — `C <= S + (_TRAIL_MA_BUFFER_PCT * S)` with
  `C > 0`. (Engine already produces short suggestions, `engine_core.py:1948-
  1958`; same epsilon anchor.)
- **The RUNNER state itself is unchanged.** Only the *task emission* is
  suppressed. `compute_position_state()` still returns `RUNNER`; the position
  still appears in the portfolio/state surfaces with its real state. We
  suppress a redundant action-item, we do not hide the position
  (`OPEN_TASKS_METHODOLOGY_SPEC.md` §3 "do not erase the signal"; this is the
  opposite case — there is *no* unactioned signal, the stop is already
  compliant, so no action-item is the honest state).

### 1.3 Exact §6 wording change (drift test stays green)

`OPEN_TASKS_METHODOLOGY_SPEC.md` §6 fenced block `RUNNER:` entry
(`:283-287`) gains **one new key** `suppress_when` on the existing
`PROTECT_RUNNER_PROFIT` entry. `open_tasks._RULESET` and the drift test
(`tests/test_open_tasks.py::test_ruleset_matches_methodology_spec`) must be
updated in lockstep — the value is a declarative string the engine interprets,
not new math:

```yaml
RUNNER:
  - task_type: PROTECT_RUNNER_PROFIT
    urgency: P1
    info_only: false
    action_he: "‏🏃 Runner — הדק סטופ לפי ההמלצה ({basis}, ${stop}). אל תרופף."
    suppress_when: "current_stop_meets_suggested_within_trail_ma_buffer"
```

Plus this clause appended verbatim to §6's bullet list (after the
`DATA_INCOMPLETE` bullet `:268-269`):

> - `RUNNER.suppress_when` = `current_stop_meets_suggested_within_trail_ma_
>   buffer`: T3 `PROTECT_RUNNER_PROFIT` is **not emitted** when, for a long,
>   `current_stop >= suggested_stop − (_TRAIL_MA_BUFFER_PCT × suggested_stop)`
>   (short: symmetric, `+`), where `suggested_stop`/`basis` are
>   `compute_suggested_trail_stop()`'s own output (`engine_core.py:1911-1960`)
>   and `_TRAIL_MA_BUFFER_PCT` is read live from `engine_core.py:1887` (0.02).
>   If `suggested_stop is None` / `basis=="none"` / `current_stop<=0`, the
>   task **is** emitted (no suppression on absent/invalid engine output —
>   AGENTS.md #1). Read-only over engine output: zero new R/NAV/campaign math
>   (DEC-20260515-007; `OPEN_TASKS_METHODOLOGY_SPEC.md` §4 G1/G4). A *material*
>   tighten (gap > epsilon) surfaces unchanged.

No other §6 row changes. No `_RULESET` row other than `RUNNER` changes.

---

## 2. DEC-006 — ALGO observer-safe form (RED LINE — most important)

**Decision context.** DEC-20260515-006 (`docs/DECISIONS.md:797-818`) wants one
consolidated ALGO entry that, per ALGO position, shows the engine's *observed*
recommended action. This is **explicitly gated on this ruling**
(`:800`, `:810-812`; `SPRINT11_PLAN.md:16`). The Red Line: DEC-20260511-001
(`:424-459`) + AGENTS.md invariants #5 (`AGENTS.md:13` — existing ALGO flows
keep working / observer role) and #8 (`AGENTS.md:16` — ALGO never enters
WR/Expectancy); Red Line `AGENTS.md:72` "Mix ALGO campaigns into Win Rate or
Expectancy"; `OPEN_TASKS_METHODOLOGY_SPEC.md` §1 T8 + §4 G2.

### 2.1 Critical code finding (gates the wording)

`evaluate_position_engine()` for an `algo_observed` campaign returns
`action = "מנוהל חיצונית — בקרה בלבד"` and `suggested_stop = None`
(`engine_core.py:457-462`); `compute_position_state()` returns
`ALGO_OBSERVED` with note `"פוזיציית אלגו — פיקוח בלבד"`
(`engine_core.py:2007-2010`). **The engine does NOT compute a discretionary
per-ALGO-position recommended action.** It deliberately *refuses* to — that
refusal IS DEC-20260511-001 encoded in code (`DECISIONS.md:433-435`).

Therefore: a consolidated entry that shows, "per ALGO position, the engine's
*observed recommended action*" **cannot show a Sentinel-derived management
recommendation, because none exists and none may be created.** Inventing one
(running the discretionary ladder for ALGO) is a direct Red Line breach
(DEC-20260511-001 "Alternatives considered: Run full discretionary engine for
ALGO — produces wrong management instructions", `:453-454`).

### 2.2 RULING — a safe form IS possible, narrowly

A consolidated ALGO entry is permitted **if and only if** it surfaces ONLY the
engine's *already-existing observation fields* — never a synthesized
management action. The "observed" content is restricted to the **read-only
oversight/visibility data DEC-20260511-001 already exposes** (`:438-448`):
`management_mode`, `risk_basis` (`True`/`Target`/`Unknown`), the engine's own
state label (`POSITION_STATE_ALGO_OBSERVED` →
`"🤖 ALGO — פיקוח בלבד"`, `engine_core.py:1680`), and the *factual* current
price vs the *externally-known* stop **only when ALGO actually exposes one**
(else `External / Unknown`, `DECISIONS.md:445`). This is observation
("what Sentinel sees"), not instruction ("what to do").

**Exact observer-safe Hebrew wording.** One consolidated, non-tappable info
entry (replacing the per-ALGO `task_algo_noop` dead-end,
`telegram_tasks.py:243`). Header disclaimer is **mandatory and first**:

```
‏🤖 ALGO — מנוהל חיצונית. בקרה בלבד.
‏Sentinel אינו מנהל, אינו ממליץ, ואינו נספר בסטטיסטיקה.
‏המידע למטה הוא מה ש-Sentinel *רואה* — לא הוראת פעולה.
```

Then, per ALGO position, a **purely descriptive observation line** (no
imperative verb, no "הדק/צא/צמצם/מכור", no target stop number originating from
Sentinel):

```
‏• {SYMBOL}: מצב נצפה — {engine ALGO state label}.
‏  בסיס סיכון: {risk_basis he}. סטופ חיצוני: {external stop | "לא ידוע"}.
```

Where `{engine ALGO state label}` is taken **verbatim** from
`engine_core.py:1680`/`:2010` (always the ALGO-observed label — the engine
never returns BROKEN/RUNNER/etc. for ALGO, `engine_core.py:2007-2010`), and
`risk_basis` from `classify_risk_basis` (`DECISIONS.md:440`). No
Sentinel-computed stop, ever (`engine_core.py:462` `suggested_stop=None` is
respected literally — display "לא ידוע", never a fabricated level, AGENTS.md
#1).

### 2.3 Hard rules (binary — any breach = fallback to 2.4)

1. **Not a `Task` object.** No `task_type`, no `urgency` tier, no
   `done`/`skip`/`stale`/`superseded` lifecycle. It is an *info panel*, the
   §6 `ALGO_OBSERVED` entry stays `info_only: true`, `urgency: null`-class
   (it already is P3 info-only, `OPEN_TASKS_METHODOLOGY_SPEC.md` §6 `:303-307`;
   see 2.5). It is rendered as the existing non-tappable info row pattern
   (`telegram_tasks.py:232-243` `task_algo_noop`), now consolidated to one.
2. **Never counted.** Never enters WR / Expectancy / PF / total_r / any
   aggregation. Routes through nothing that touches `is_stat_countable`
   except to be excluded (`engine_core.py:1232` `STAT_BUCKET_ALGO`;
   AGENTS.md #8; `MARK_DAY3_GUARDRAILS.md` B1).
3. **No imperative.** Zero action verbs directed at the user. Descriptive
   mood only ("מצב נצפה", "בסיס סיכון") — never "הדק", "צא", "מכור",
   "העלה סטופ", "צמצם".
4. **Never an actionable stop instruction.** No Sentinel-originated stop
   number. External stop shown only if ALGO itself exposes it; otherwise
   "לא ידוע" (never `$0.00`, `DECISIONS.md:444-445`; never a Sentinel
   suggestion — `engine_core.py:462`).
5. **No state/action drawn from the discretionary ladder.** The only state
   shown is `ALGO_OBSERVED` (engine_core.py:2009-2010). If any code path
   would feed an ALGO campaign into `build_management_action` /
   `compute_suggested_trail_stop` to populate this panel = **FAIL**, fall
   back to 2.4. (`OPEN_TASKS_METHODOLOGY_SPEC.md` §4 G2; DEC-20260511-001.)
6. **Read-only / admin-only.** SELECT-only derivation; reachable only via the
   existing admin-gated path, no `secure_runner` bypass
   (`OPEN_TASKS_METHODOLOGY_SPEC.md` §4 G6/G9; `CLAUDE.md` hard constraints).

### 2.4 Fallback if any 2.3 rule cannot be met

If engineering cannot guarantee 2.3 (e.g. the only way to render "per
position" pulls discretionary state), **fall back to DEC-20260515-006's own
red-line-safe option**: one consolidated, non-tappable button —

```
‏🤖 מנוהל חיצונית — אין פעולת Sentinel.
```

— no per-position content at all (`DECISIONS.md:816`). This is strictly safe
because it surfaces nothing the engine computes for ALGO. Choose this over any
form that risks 2.3. (Accuracy over confidence — `CLAUDE.md`.)

### 2.5 Exact §6 change

The §6 `ALGO_OBSERVED` block (`OPEN_TASKS_METHODOLOGY_SPEC.md:303-307`) and
`open_tasks._RULESET` are **unchanged** (still `task_type:
ALGO_OBSERVE_ONLY`, `urgency: P3`, `info_only: true`,
`action_he: "‏🤖 ALGO — בקרה בלבד. אין פעולת ניהול מטעם Sentinel."`). The
consolidation + observation lines are a **presentation-layer change in
`telegram_tasks.py`/`open_tasks.py` rendering only**, not a ruleset change —
so the drift test (`test_ruleset_matches_methodology_spec`) is **not** touched
by DEC-006 (this is deliberate: the methodology of ALGO = info-only,
never-counted is already correctly encoded; only the screen layout changes).
One clarifying bullet is appended to §6's bullet list:

> - `ALGO_OBSERVED` may be rendered as a **single consolidated info panel**
>   (not one row per ALGO position) showing, per position, ONLY the engine's
>   existing observation fields (`management_mode`, `risk_basis`, the
>   `ALGO_OBSERVED` state label `engine_core.py:1680`, and an external stop
>   only if ALGO exposes one). It remains `info_only: true`, is **not** a
>   `Task` (no lifecycle, never counted), contains **no** Sentinel-originated
>   recommendation or stop, and uses descriptive (non-imperative) Hebrew only
>   (DEC-20260515-006 conditional on this ruling; DEC-20260511-001;
>   AGENTS.md #5/#8; `OPEN_TASKS_METHODOLOGY_SPEC.md` §4 G2). If unachievable,
>   fall back to a single "מנוהל חיצונית — אין פעולת Sentinel" button.

---

## 3. #2 — snapshot-label reword (methodology-neutral)

**Finding.** `SPRINT11_PLAN.md:13`: the current label
`_(snapshot — לא מאומת כעת)_` (`telegram_tasks.py:399`) implies a pending
verification that never happens. The founder was told (and it is true,
`SPRINT11_PLAN.md:25`): the engine **re-derives the value live every time the
list opens**; the snapshot is only the value *at task creation* — the "why".
`open_tasks.py:89-90` confirms `open_r`/`age_days` are "snapshot ONLY — copied
from engine, never recomputed" in the *task record*, while the list view
re-derives live each open.

**RULING — methodology-neutral, confirmed.** Re-wording this label is a pure
honesty/clarity fix with **zero methodology impact**: no R / NAV / campaign
number changes, no ruleset change, no §6 change, no drift-test impact. It only
makes the label tell the truth (AGENTS.md #1 — no fallback/stale-as-truth;
`MARK_DAY3_GUARDRAILS.md` §2.5 U10; `CLAUDE.md` "be clear about
fallback/cached data"). The *current* wording is the methodology risk (it
implies an unkept promise of verification = a soft fallback-as-truth); the
reword removes that risk.

**Exact honest Hebrew phrasing** (replaces the parenthetical at
`telegram_tasks.py:399`):

```
‏• Open-R: `{r_str}` _(ערך בעת יצירת המשימה — הרשימה מחושבת מחדש בכל פתיחה)_
```

This states plainly: it is the value at creation, and the list re-derives
live on every open. No "verification pending", nothing presented as
authoritative-but-stale. If `r_str` is itself unavailable
(`"לא זמין (חסר סיכון מקורי)"`, `telegram_tasks.py:392`) the existing honest
phrasing stands — do not dress missing data as a number (AGENTS.md #1).

---

## 4. DEC-008 — audit-review surface guardrails

**Decision context.** DEC-20260515-008 (`docs/DECISIONS.md:840-856`): expose
`audit_log` to the *user* as a read-only retrospective review surface in the
normal menu, friendly Hebrew, most-recent-first. `audit_logger.py` is
write-only by design (`audit_logger.py:1-7`); this adds a deliberate additive
read path.

### 4.1 Hard constraints (binary — any FAIL blocks the surface)

- [ ] **D1. Read-only / never mutates.** The new read function issues a
  Supabase **SELECT only** on `audit_log` (`audit_logger.py:33`). It must not
  `insert`/`update`/`delete` `audit_log` or any other table, and must not
  touch `trades` (AGENTS.md #4; `CLAUDE.md` "Do not mutate Supabase from
  read-only flows"; `OPEN_TASKS_METHODOLOGY_SPEC.md` §4 G6 analogue). It lives
  beside `log_action` but shares none of its write path.
- [ ] **D2. Fail-safe, never blocking.** Mirror `log_action`'s fail-open
  contract (`audit_logger.py:45-49`): on any Supabase error the read returns
  an honest "לא ניתן לטעון את יומן הפעולות כרגע" — it must **never** fabricate
  rows or fall back to cached/derived rows presented as the real log
  (AGENTS.md #1).
- [ ] **D3. No fallback/derived figure as authoritative (#1).** The surface
  shows **recorded `before_state`/`after_state`/`metadata` as stored**
  (`audit_logger.py:54-62`). It must not recompute, re-derive, or "enrich" any
  number (no live R, no NAV lookup, no PnL calc). Any value whose source is
  uncertain is labelled, never shown as exact truth (AGENTS.md #1;
  `MARK_DAY3_GUARDRAILS.md` §2.5 U10; `CLAUDE.md` "When uncertain").
- [ ] **D4. No fabricated PnL/performance numbers.** It shows **recorded
  actions, not computed returns**. It must NOT display win-rate, expectancy,
  PF, total return, or any performance figure derived from the trail
  (DEC-20260515-004 spirit `:748-769` — process/actions, not numbers;
  `MARK_DAY3_GUARDRAILS.md` M1). If a row's `metadata` happens to contain a
  number (e.g. before/after stop), show it **only as the recorded action's
  literal before/after**, never aggregated into a performance statistic.
- [ ] **D5. Admin-only, secure_runner unchanged.** Reachable only through the
  existing admin-gated bot path; `telegram_bot_secure_runner.py` untouched
  (`DECISIONS.md:855`; `CLAUDE.md` hard constraints; AGENTS.md #3).
- [ ] **D6. Honest source/most-recent-first.** Rows shown newest-first with
  their real timestamp; if a timestamp is missing it is labelled "זמן לא
  רשום", not invented (AGENTS.md #1).

### 4.2 `audit_log` action kinds — surface vs omit

Source of truth for action kinds: `audit_logger.py:23-31` plus the lifecycle
audit events mandated by `OPEN_TASKS_METHODOLOGY_SPEC.md` §3
(`skipped_critical_exit` `:166-168`) and `MARK_DAY3_GUARDRAILS.md` U4
(stop-loosen explicit-confirm audit `:182-185`).

**SURFACE (user self-review — these are the user's own decisions):**
- `risk_pct_change` (`audit_logger.py:23`) — the user's risk-sizing changes;
  show recorded before/after % literally (D4 — not aggregated).
- `addon_confirm` (`audit_logger.py:24`) — user confirmed an add-on; a real
  decision in their review scope.
- the **stop-loosen explicit-confirm** override event
  (`MARK_DAY3_GUARDRAILS.md` U4 `:182-185`; the MRVL
  `stop_loosen_override` artifact, `SPRINT11_PLAN.md:19`) — methodology-
  critical: the user *must* be able to review every time they consciously
  loosened a stop (before/after literal). High self-review value.
- task lifecycle `done` / `skip` (incl. `skipped_critical_exit`,
  `OPEN_TASKS_METHODOLOGY_SPEC.md` §3 `:160-168`) — the user's own
  action-item decisions; `skipped_critical_exit` is *especially* in scope
  (retrospective accountability over an unactioned P0, the founder's exact
  goal, `DECISIONS.md:851`). Show the recorded note verbatim, never as
  trading data (`OPEN_TASKS_METHODOLOGY_SPEC.md` §3 "notes are operational
  metadata only").
- `manual_trade` (`audit_logger.py:28`) — a user-initiated trade record (a
  decision the user took); show the recorded action, not a computed return.
- `settings_change` (`audit_logger.py:30`) — user-facing config the user
  changed (filter to user-meaningful keys only).

**OMIT (operational/forensic, not self-review; surfacing dilutes the
"my decisions" view and risks leaking internals):**
- `dev_pin_activate` / `dev_pin_fail` (`audit_logger.py:25-26`) — security
  /forensic, not a trading decision. Omit (also avoids advertising the dev
  surface to a normal user; AGENTS.md #3 spirit).
- `deploy_trigger` (`audit_logger.py:29`) — operational/devops, not user
  self-review.
- `telegram_alert_send` (`audit_logger.py:31`) — system emission, not a user
  decision; surfacing it would also re-expose alert content outside the
  anti-spam model (AGENTS.md #7 spirit). Omit.

Rule of thumb (methodology): **surface = "an action the user themself
decided"; omit = "something the system or the operator did."** When a kind is
ambiguous, omit (under-showing is honest; over-showing risks D3/D4). Any
*new* action constant added later defaults to **omit** until explicitly
classified here.

---

## 5. Pass/fail checklist — Sprint-11 checkpoint

The parent runs this at the Wave-1→Wave-2 checkpoint
(`SPRINT11_PLAN.md:34-35`). Any FAIL = Wave 2 does not ship that item.

1. **DEC-007 epsilon anchored, not invented.** `open_tasks` reads
   `_TRAIL_MA_BUFFER_PCT` live from `engine_core.py:1887`; no literal `0.02`
   (or any new threshold) copied into `open_tasks.py`. (DEC-20260515-007;
   AGENTS.md #2; `OPEN_TASKS_METHODOLOGY_SPEC.md` §4 G1.)
2. **DEC-007 read-only / tighten-only.** Suppression is a comparison of
   `compute_suggested_trail_stop()` output vs stored `current_stop`; no
   recompute of R/NAV/campaign; never emits/implies a lower stop; a
   material-gap tighten still surfaces (test required). (AGENTS.md #2;
   `MARK_DAY3_GUARDRAILS.md` §2.2 U3, §5 C3; `OPEN_TASKS_METHODOLOGY_SPEC.md`
   §4 G1/G4.)
3. **DEC-007 §6 lockstep.** §6 `RUNNER.suppress_when` added AND
   `open_tasks._RULESET` AND `test_ruleset_matches_methodology_spec` updated
   together and green. (DEC-20260515-007; spec §6.)
4. **DEC-006 no synthesized ALGO action.** No ALGO campaign reaches
   `build_management_action` / `compute_suggested_trail_stop` /
   discretionary state to populate the panel; only `ALGO_OBSERVED` state +
   `risk_basis` + external stop (if exposed) shown; no Sentinel-originated
   stop. (DEC-20260511-001; AGENTS.md #5/#8; spec §4 G2;
   `engine_core.py:457-462,2007-2010`.)
5. **DEC-006 not a Task / never counted.** ALGO panel has no
   lifecycle/urgency; never enters WR/Expectancy/PF; descriptive Hebrew only,
   zero imperative verbs; fallback (2.4) used if any of these cannot be
   guaranteed. (AGENTS.md #8; Red Line `AGENTS.md:72`; spec §6
   `ALGO_OBSERVED` unchanged.)
6. **#2 reword honest, methodology-neutral.** Label states "value at task
   creation; list re-derives live each open"; no "verification pending"; no
   ruleset/§6/drift-test change. (AGENTS.md #1; `MARK_DAY3_GUARDRAILS.md`
   §2.5 U10.)
7. **DEC-008 read-only.** Audit-review fn is SELECT-only on `audit_log`; zero
   writes to any table; `trades` untouched; fail-open with honest error, no
   fabricated rows. (AGENTS.md #4; DEC-20260515-008; `CLAUDE.md`.)
8. **DEC-008 no numbers fabricated.** Surface shows recorded actions/
   before-after literals only; no WR/PF/return/PnL aggregation; uncertain
   values labelled, never authoritative. (AGENTS.md #1; DEC-20260515-004
   spirit; `MARK_DAY3_GUARDRAILS.md` M1.)
9. **DEC-008 correct action set.** Surfaces only user-decision kinds (§4.2
   SURFACE list incl. `skipped_critical_exit` + stop-loosen override); omits
   `dev_pin_*` / `deploy_trigger` / `telegram_alert_send`; new kinds default
   to omit. (DEC-20260515-008; AGENTS.md #3/#7 spirit.)
10. **Global invariants intact + suite green.** Admin-only, secure_runner
    unchanged (`CLAUDE.md`; AGENTS.md #3); no Supabase trade mutation
    (AGENTS.md #4); `pytest -q` full suite green incl. the §6 drift test
    (baseline 1523, `SPRINT11_PLAN.md:38`). (`MARK_DAY3_GUARDRAILS.md` §6.7.)

---

— Mark
