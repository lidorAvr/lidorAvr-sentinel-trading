# Open Tasks (Action-Items) Engine — Implementation Design

**Sprint:** 10
**Team:** Architecture
**Status:** DESIGN ONLY. No production code written. No git commit/push. No existing
code modified. Migration files are DRAFTS (not executed).
**Branch:** `claude/review-system-audit-FBZ2h`

---

## 0. One-paragraph summary

`open_tasks.py` is a new **leaf module** that turns the engine's existing
authoritative position state (`engine_core.compute_position_state()`, 10 states)
into a list of concrete, dedup'd, prioritized **action items** ("Open Tasks").
It does **zero new R / NAV / campaign math** — it is a pure read-only projection.
The set of *open* tasks is **always re-derived** from the live engine; Supabase
stores **only lifecycle deltas** (done / skipped / user notes) keyed by
`(user_id, campaign_id, task_type)`. The trigger→task ruleset is a **data table
owned by Mark** (`OPEN_TASKS_METHODOLOGY_SPEC.md`); the engine *consumes* it and
hard-codes no thresholds.

---

## 1. Module `open_tasks.py` — public interface

### 1.1 Placement & import constraints

`open_tasks.py` is a **leaf**, in the same tier as `telegram_formatters.py` /
`audit_logger.py` / `user_context.py`:

- **MAY import:** `engine_core` (read-only, for the state constants only),
  `user_context` (for `get_current_user_id`), stdlib, `dataclasses`,
  `datetime`. Optionally `supabase_repository`/`audit_logger` are passed in by
  DI — never imported for module-level state.
- **MUST NOT import:** `telegram_bot`, `telegram_*`, `bot_core`,
  `risk_monitor`, `dashboard`. (Same rule as `telegram_formatters.py`: callers
  compute data and pass it in.)
- No module-level Supabase client. Every persistence function takes `sb` as
  first arg (DI — identical to `supabase_repository.py` / `audit_logger.py`).

### 1.2 The ruleset is DATA, not code (Mark owns it)

The exact trigger→task mapping is **NOT** in this module. `open_tasks.py`
exposes:

```python
def load_ruleset() -> dict          # parsed from Mark's spec table (see §1.6)
def derive_tasks(positions, *, now, ruleset=None) -> list[Task]
```

`derive_tasks` reads `ruleset` (defaults to `load_ruleset()`). No threshold,
age cutoff, R level, or urgency is literal in `open_tasks.py`. Mark's
`OPEN_TASKS_METHODOLOGY_SPEC.md` is the single source of truth for:
*which state → which task_type → which urgency → which Hebrew
recommended_action template*. Until Mark's spec lands, `load_ruleset()` raises
`RulesetUnavailable` (fail-loud, never a silent empty list — consistent with
`user_context.get_user_constant` raising `KeyError` rather than returning
`None`).

### 1.3 `Task` dataclass

```python
@dataclass(frozen=True)
class TriggerSnapshot:
    state: str          # engine_core.POSITION_STATE_* at creation
    open_r: float        # snapshot ONLY — copied from engine, never recomputed
    age_days: float      # snapshot ONLY — copied from engine, never recomputed

@dataclass
class Task:
    task_type:          str            # ruleset key, e.g. "PROTECT_RUNNER_PROFIT"
    campaign_id:        str
    symbol:             str
    urgency:            str            # "P0" | "P1" | "P2" | "P3" (from ruleset)
    trigger_snapshot:   TriggerSnapshot
    recommended_action: str            # Hebrew, rendered from ruleset template
    status:             str            # "open" | "done" | "skipped"
    notes:              list[str]       # timestamped, append-only
    created_ts:         str            # ISO8601 UTC
    closed_ts:          str | None
    user_id:            str            # additive; default = user_context sentinel
```

`urgency` reuses the existing P0–P3 vocabulary already defined in
`risk_monitor.ALERT_PRIORITY` (risk_monitor.py:56–79) — no new priority scheme.

### 1.4 `derive_tasks(positions, *, now, ruleset=None) -> list[Task]` — PURE

Signature mirrors the engine's existing pattern (`positions` = the list of
dicts from `engine_core.get_open_positions_campaign()["data"]`, fields:
`campaign_id, symbol, quantity, base_qty, base_price, price, stop_loss,
initial_stop, setup_type, entry_date, management_state, realized_pnl` —
engine_core.py:513–519).

Algorithm (no math, only projection + table lookup):

1. For each open position, the caller has **already** obtained the
   authoritative `compute_position_state(...)` result (engine_core.py:1963).
   `derive_tasks` accepts that state dict on each position (key
   `state_result`) — it **does not call the engine itself**, so it cannot
   accidentally re-derive R/NAV. (Caller responsibility = the same contract
   `telegram_formatters` uses: "callers compute data and pass it in".)
2. `state = position["state_result"]["state"]`.
3. **Exclusions (per Mark / AGENTS.md invariant #8):**
   - `POSITION_STATE_ALGO_OBSERVED` → **info-only or excluded** exactly as
     Mark's spec says (default per spec: emit at most an info-only P3 task
     with `recommended_action` = observe-only text, **never** a stop/exit
     instruction — DATA_CONTRACTS.md: "Sentinel must NEVER issue stop-raise or
     exit instructions to `algo_observed`").
   - `POSITION_STATE_DATA_INCOMPLETE` → **excluded** from actionable tasks
     (mirrors "DATA_INCOMPLETE must never appear in stats"); at most a single
     info-only "complete the data" task if Mark's ruleset opts in.
4. Look up `ruleset[state]` → 0..n `(task_type, urgency, action_template)`.
5. Build `Task` with `trigger_snapshot` = a **copy** of `state`, `open_r`,
   `age_days` *as the engine already computed them* (snapshot for audit/why —
   never authoritative; the live render always re-reads the engine).
6. `recommended_action` rendered from the ruleset's Hebrew template (RTL,
   short, direct — Risk-language contract). For RUNNER, the template MAY embed
   the engine's existing `compute_suggested_trail_stop()` output
   (engine_core.py:1911) **as passed in by the caller** — engine still owns
   the number.

`derive_tasks` is **referentially transparent**: same `positions` + same
`now` + same `ruleset` → identical list. No I/O, no Supabase, no clock except
the injected `now`.

### 1.5 Lifecycle API (the only Supabase-touching surface)

```python
DEDUP_KEY = (user_id, campaign_id, task_type)

def list_tasks(sb, positions, *, now, user_id=None) -> list[Task]
def mark_done(sb, campaign_id, task_type, *, user_id=None, note=None) -> bool
def skip_task(sb, campaign_id, task_type, *, user_id=None, note=None) -> bool
def add_note(sb, campaign_id, task_type, note, *, user_id=None) -> bool
```

- `user_id` defaults to `user_context.get_current_user_id()` (never None,
  never raises — same hard contract as Phase A).
- `list_tasks` = **derive (live) ⟕ lifecycle (stored)**:
  1. `derived = derive_tasks(positions, now=now)`.
  2. `overlays = _read_lifecycle(sb, user_id)` — only done/skip/notes rows.
  3. Left-join on `DEDUP_KEY`. A derived task whose overlay is `done`/`skipped`
     is returned with that status (so the bot can hide/grey it) until the
     **state supersedes** it (next rule).
  4. **Auto-close on state transition / supersede:** if the engine state for
     a campaign no longer maps to a given open `task_type` (state changed, or
     campaign closed → not in `positions`), that task is **closed
     automatically** — `closed_ts` set, status `done` (resolved by market) or
     `superseded`. This is pure derivation: a stored `open` overlay for a
     `task_type` the engine no longer emits is simply not surfaced; the next
     `mark_*` is a no-op. **No engine state is mutated.**
  5. Dedup: at most ONE row per `DEDUP_KEY`. A new state that maps to the same
     `task_type` while an older one is still `open` **supersedes** (single
     row, snapshot refreshed) — never a duplicate. Mirrors risk_monitor's
     per-position single-key anti-spam philosophy (DATA_CONTRACTS.md alert-key
     contract).
- `mark_done` / `skip_task`: upsert one lifecycle row keyed by
  `(user_id, campaign_id, task_type)`; append a timestamped note via the
  **same pattern** as `repo.update_management_notes` (append, not replace),
  and write an `audit_logger.log_action(sb, ACTION_SETTINGS_CHANGE,
  metadata={...})` row (fail-open — never blocks the user). It does **not**
  write to the `trades` table or `management_state` — Open Tasks lifecycle
  lives only in its own table (Supabase write contract: "Any new mutation
  path should be isolated and testable").

### 1.6 Ruleset format (consumed from Mark)

`load_ruleset()` parses Mark's `OPEN_TASKS_METHODOLOGY_SPEC.md` machine-readable
block (Mark owns the exact schema; Architecture only fixes the *shape*):

```yaml
# OWNED BY MARK — open_tasks.py only reads this; no thresholds in code.
PROFIT_PROTECTION:
  - task_type: PROTECT_RUNNER_PROFIT
    urgency: P2
    action_he: "הדק סטופ לאזור MA21 — שמור רווח"
BROKEN:
  - task_type: EXECUTE_EXIT
    urgency: P1
    action_he: "מחיר עבר את הסטופ — בצע יציאה"
ALGO_OBSERVED:
  - task_type: ALGO_OBSERVE_ONLY
    urgency: P3
    info_only: true
DATA_INCOMPLETE:
  - task_type: COMPLETE_RISK_DATA
    urgency: P3
    info_only: true
```

If Mark's spec is absent/unparseable → `RulesetUnavailable` (fail-loud).
`info_only: true` tasks are surfaced but carry **no** stop/exit instruction
and never enter any count.

---

## 2. Persistence — `open_tasks` Supabase table

### 2.1 Derived-vs-stored justification (the core architectural decision)

**The engine is the single source of truth.** Storing the *open task set*
would create a second, drift-prone copy of position state (the exact bug
class `verify_migrations.py`'s docstring describes for audit_log). Therefore:

| Concept            | Stored? | Why |
|--------------------|---------|-----|
| Whether a task is *open* | **NO** | Re-derived every render from `compute_position_state()`. Auto-closes when the engine state moves. Zero drift. |
| `done` / `skipped` decision | **YES** | User intent — not derivable from market data. |
| User notes         | **YES** | User-authored history (append-only, mirrors `update_management_notes`). |
| `created_ts` / `closed_ts` | **YES** (lifecycle row only) | Audit trail of the decision, not of the trigger. |
| `trigger_snapshot` | **YES, on the lifecycle row only** | Frozen "why" at decision time, for forensics. Never read back as authoritative R/state. |

So the table holds **lifecycle deltas only**. An untouched task has **no row**
— absence = "open, not yet acted on". This keeps the engine the sole authority
and makes the table small and append-mostly.

### 2.2 Schema (mirrors migration 003 exactly: additive, UUID `user_id`,
`NOT NULL DEFAULT` sentinel, dedicated index)

Columns: `id BIGSERIAL PK`, `user_id UUID NOT NULL DEFAULT
'00000000-0000-0000-0000-000000000001'`, `campaign_id TEXT NOT NULL`,
`task_type TEXT NOT NULL`, `status TEXT NOT NULL` (`done`|`skipped`),
`symbol TEXT`, `urgency TEXT`, `trigger_state TEXT`, `trigger_open_r
DOUBLE PRECISION`, `trigger_age_days DOUBLE PRECISION`, `notes JSONB DEFAULT
'[]'::jsonb`, `created_ts TIMESTAMPTZ NOT NULL DEFAULT now()`, `closed_ts
TIMESTAMPTZ`.

Unique dedup constraint: `UNIQUE (user_id, campaign_id, task_type)` — enforces
"at most one lifecycle row per task" at the DB layer (race-safety, §3).
Indexes: `idx_open_tasks_user_id`, `idx_open_tasks_campaign`,
`idx_open_tasks_user_campaign_type` (the unique one).

### 2.3 Migration DRAFTS

Authored (not executed): `migrations/005_create_open_tasks.sql` +
`migrations/rollback_005.sql`. Format matches `002_audit_log.sql` (header
comment, `IF NOT EXISTS`, trailing verify SELECT) and the 003 user_id pattern
(UUID, `NOT NULL`, sentinel `DEFAULT`, dedicated index, verification SELECTs).

### 2.4 `verify_migrations.py` ledger entry (documented here — file NOT edited)

Add after the `004` tuple (keeps the ledger linear, same as 003/004 were
appended):

```python
    (
        "005_create_open_tasks.sql",
        "open_tasks",
        None,  # whole table is new — existence is the test
    ),
```

(Per task: this is documented in the design only; `verify_migrations.py` is
**not** modified by this work item.)

---

## 3. Idempotency, dedup & race-safety

- **Idempotent derivation:** `derive_tasks` is pure; calling it N times yields
  the same list. No "fire-once" flag needed in code — the *engine state* is
  the dedup key (cf. risk_monitor's per-position state machine, but here we
  store nothing for the open case).
- **DB-level dedup:** `UNIQUE (user_id, campaign_id, task_type)` makes
  `mark_done`/`skip` upserts idempotent. A double-tap (Telegram retry) is a
  no-op upsert, not a duplicate row.
- **Concurrent risk_monitor + bot:** `open_tasks.py` **never writes to
  `risk_monitor_state.json` or `trades`** — zero shared mutable state with
  risk_monitor, so no lock contention with `state_io.file_lock`. The only
  writer is the bot (user pressing done/skip). Reads (`list_tasks`) are
  lock-free and consistent because they re-derive from the engine.
- **No double-notify:** Open Tasks is a **pull surface** (rendered when the
  user opens the menu). It does **not** push Telegram messages. risk_monitor's
  alerts remain the only push path. A task and an alert may describe the same
  situation, but only the alert notifies — preserving AGENTS.md invariant #7
  (no recurring alert without per-position dedup) because **we add no alert**.

### Phase-A byte-identical guarantee (single user)

- `user_id` defaults to `user_context.get_current_user_id()` →
  sentinel UUID for Mark, identical literal to migration 003's `DEFAULT`.
- With one user, every `DEDUP_KEY` is `(SENTINEL, campaign_id, task_type)` —
  the `user_id` dimension is constant, so behaviour is exactly the
  single-user behaviour. New table, additive column → zero change to any
  existing query, message, or number. No touchpoint reads
  `get_user_constant()`; `open_tasks.py` is dormant until the bot renders it.

---

## 4. Test plan (`tests/test_open_tasks.py`)

Pure-unit, deterministic, no network (per `tests/` rules):

1. **Derivation per state** — one case per constant: NEW, PROVING, WORKING,
   PROFIT_PROTECTION, RUNNER, YELLOW_FLAG, BROKEN, DEAD_MONEY → asserts
   `task_type` + `urgency` come from the ruleset, not literals.
2. **ALGO_OBSERVED** → info-only task only, `recommended_action` contains no
   stop/exit verb; `info_only` true.
3. **DATA_INCOMPLETE** → excluded (or info-only per ruleset); never an
   actionable P0–P2 task.
4. **Dedup** — same campaign re-derived twice → one task; second state
   mapping same `task_type` while open → supersede (single task, refreshed
   snapshot), never duplicate.
5. **Auto-close on transition** — campaign present in pass 1 (RUNNER) absent
   / different state in pass 2 → task closed (`closed_ts` set), no duplicate.
6. **Lifecycle** — `mark_done` / `skip` / `add_note`: upsert idempotent
   (double call = no extra row), notes append (not replace, mirrors
   `update_management_notes`), `audit_logger.log_action` called with
   `ACTION_SETTINGS_CHANGE` (mock `sb`).
7. **No-mutation-of-engine** — assert `derive_tasks` calls **no** engine
   function (it receives `state_result`); assert no write to `trades` /
   `management_state` from any lifecycle call (mock asserts only `open_tasks`
   table touched + one `audit_log` insert).
8. **Purity** — `derive_tasks` called twice with frozen `now` → equal lists;
   no clock read without injected `now`.
9. **Fail-loud** — `load_ruleset()` with missing spec → `RulesetUnavailable`,
   never silent `[]`.
10. **user_id default** — no `DEFAULT_USER_ID` env → sentinel UUID, equal to
    migration 003 `DEFAULT` literal (drift guard, mirrors
    `test_sentinel_matches_migration_default`).
11. **`audit_logger` fail-open** — `sb` raising on audit insert does not
    block `mark_done` returning True.

---

## 5. Risk classification & explicit non-goals

### Risk classification (per CLAUDE.md)

**LOW–MEDIUM.**
- New leaf module + new table + new draft migration = additive only.
- LOW: no engine math, no `telegram_bot.py` edit, no `risk_monitor` edit, no
  `docker-compose.yml` change, pull-only surface.
- MEDIUM factor (only one): a new Supabase **write** path
  (`mark_done`/`skip`/`add_note`). Mitigated by: isolated table, DI client,
  `UNIQUE` constraint, audit row, append-not-replace notes, full test
  coverage (Supabase write contract §"isolated and testable").

Affected services if later wired: `telegram-bot` (render + lifecycle
buttons). Not affected: `risk-monitor`, `sentinel-bot`, `reporting-service`,
`dashboard` (no changes proposed).

### What we will explicitly NOT do

- **No engine math change.** No new R / NAV / exposure / campaign / giveback
  calculation. `derive_tasks` consumes `compute_position_state()` output
  verbatim; `trigger_snapshot` is a copy, never a recomputation.
- **No new alert / no double-notify.** Open Tasks is pull-only. We add **zero**
  Telegram push paths, so AGENTS.md invariant #7 is untouched (the existing
  risk_monitor alerts remain the sole notifier).
- **No hard-coded thresholds.** All trigger→task→urgency mapping comes from
  Mark's `OPEN_TASKS_METHODOLOGY_SPEC.md` data table; absent spec = fail-loud.
- **No mutation of `trades` / `management_state` / `risk_monitor_state.json`.**
  Lifecycle lives only in the new `open_tasks` table.
- **No ALGO/DATA_INCOMPLETE in any count.** They are info-only or excluded,
  exactly as the engine already gates them for stats.
- **No bot/engine import into the leaf.** Same import discipline as
  `telegram_formatters.py`.
- **No git commit/push, no execution of migrations, no edit of existing files**
  (incl. `verify_migrations.py` — its required entry is documented in §2.4).
- **No rewrite of `telegram_bot.py`.** Wiring the render is a later, separate,
  small work item — out of scope for this design.
</content>
</invoke>
