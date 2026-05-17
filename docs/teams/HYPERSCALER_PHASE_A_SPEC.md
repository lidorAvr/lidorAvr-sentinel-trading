# Hyperscaler — Phase A Spec (V1)

**Date:** 2026-05-14 (afternoon shift)
**Author:** Hyperscaler Team Lead
**Branch:** `claude/review-system-audit-FBZ2h`
**Supersedes:** Phase A sketch in `docs/teams/HYPERSCALER_DESIGN_V0.md` §"Phase A"
**Status:** Reviewable spec. **No production code modified today.**

Read alongside:
- `docs/teams/HYPERSCALER_DESIGN_V0.md` (target architecture, 4-phase plan)
- `docs/teams/MARK_ALIGNMENT_REVIEW.md` §4 directives 1 & 2 (HARD constants, per-PR smoke test)
- `docs/teams/DAY1_MIDDAY_STANDUP.md` §"Sprint 10 candidate priority list" (P0 Phase A unblocks every Day-2 team)
- `docs/teams/RESEARCH_FINDINGS_DAY1.md` Issue N3 (state-file race conditions — Sprint 10 P0)

---

## 1. Goal & non-goals

### Goal

After Phase A ships, **every** Supabase write and **every** state-file read/write either tags or filters by `user_id`. The single existing user (Mark) becomes user UUID `00000000-0000-0000-0000-000000000001`, and **his observable behavior is byte-identical** to pre-Phase-A:

- Same `/portfolio` row count and ordering.
- Same R-multiples, NAV, exposure, target_risk_usd, heat score, adaptive risk recommendation.
- Same Telegram alert count, alert text, alert ordering, alert cadence per 60s monitor cycle.
- Same audit_log content (with `user_id` populated as additional metadata only).
- Same weekly/monthly PDF byte-output (timestamps ignored).

Phase A is **plumbing only**. It introduces the concept of `user_id` everywhere; it does not enable a second user.

### Non-goals (explicitly out of scope)

| Out of scope | Reason | Phase |
|---|---|---|
| Second real user / signup flow | No auth UI yet | Phase C |
| Supabase Row-Level Security (RLS) | RLS is enabled only after every code path filters; turning it on early breaks Mark | Phase C |
| Auth UI / Supabase Auth integration | Founder decisions on pricing/dashboard rewrite pending | Phase C |
| Dashboard rewrite or multi-tenant UI | Streamlit stays single-page; no per-user pages | Phase C |
| Methodology profiles activation | `is_stat_countable`, `RISK_LADDER`, drawdown constants stay hardcoded | Phase B |
| `algo_universe`, `methodology_profiles`, `users` tables populated as live config | Phase A creates schemas only when strictly needed for `user_id` plumbing | Phase B |
| Moving JSON state files into DB | High-risk migration; deferred to Phase B; see §5 | Phase B |
| Changing `telegram_bot_secure_runner.py` admin guard | Hard constraint from `CLAUDE.md:21` and Mark conflict #3 resolution | Phase C |
| Removing `7500.0` fallback NAV | Per-user fallback is Phase B concern | Phase B |

**Hard invariant from Mark (`MARK_ALIGNMENT_REVIEW.md` directive #1):**
`mix_algo_into_wr` stays a HARD-CODED Python constant. `engine_core.is_stat_countable()` must keep its current parameter-free signature. Phase A does not touch this function at all.

---

## 2. Environment variable

### New env: `DEFAULT_USER_ID`

- **Type:** UUID string (lowercased, hyphenated).
- **Production value:** generated once per deployment by ops; written into `.env` alongside `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_ID`, `SUPABASE_URL`, `SUPABASE_KEY`.
- **Recommended production value for Mark's prod:** `00000000-0000-0000-0000-000000000001`. This makes log grep trivial during Phase B/C cutover.
- **Behavior when unset:**
  - Code logs a single startup warning to stderr (`"[user_context] DEFAULT_USER_ID unset — using sentinel UUID. Phase A is single-user; this is expected on dev boxes."`).
  - Returns the sentinel UUID constant `00000000-0000-0000-0000-000000000001`.
  - **Does not crash, does not refuse to start.** Mark's existing `.env` does not have `DEFAULT_USER_ID` today; if Phase A ships and the env var is missed in the deploy, production must still run byte-identically.

### Sentinel UUID constant

Defined once in `user_context.py`:

```python
SENTINEL_USER_ID = "00000000-0000-0000-0000-000000000001"
```

Used in two places only:
1. `user_context.get_current_user_id()` fallback.
2. Migration SQL `DEFAULT` clause (same literal — kept in sync by a unit test, see §6).

---

## 3. Database migrations (additive, reversible)

Inspection of `supabase_repository.py` and `migrations/00{1,2}_*.sql` shows two tables today:

- `trades` — every per-tenant business row.
- `audit_log` — compliance trail (migration `002_audit_log.sql`).

There are no other Supabase tables. (`sector_cache.json`, `risk_monitor_state.json`, `risk_journal.json`, `risk_recommendations.json`, `sentinel_config.json` are all on-disk JSON — Phase B concern, see §5.)

Phase A adds **two** migration files. Both are additive, default-backed, reversible.

### Migration `003_add_user_id_to_trades.sql`

```sql
-- Phase A — add user_id to trades.
-- Additive, default-backed, reversible. Backfills every existing row to the
-- DEFAULT_USER_ID sentinel so that Mark's data is owned by a real user UUID.
-- Safe: IF NOT EXISTS / no-op if already applied.

-- 1. Forward DDL
ALTER TABLE trades
    ADD COLUMN IF NOT EXISTS user_id UUID
    NOT NULL
    DEFAULT '00000000-0000-0000-0000-000000000001';

-- 2. Backfill (no-op if column was just added with DEFAULT — every row already
--    has the default value; this is a belt-and-suspenders guard for the case
--    where the column existed before this migration applied).
UPDATE trades
SET    user_id = '00000000-0000-0000-0000-000000000001'
WHERE  user_id IS NULL;

-- 3. Index (cheap on small tables; required once we filter by user_id).
CREATE INDEX IF NOT EXISTS idx_trades_user_id ON trades (user_id);

-- 4. Verification (must return 0)
SELECT COUNT(*) AS null_user_id_rows FROM trades WHERE user_id IS NULL;
-- Expected output: 0

-- 5. Verification (must return >= 1 with the sentinel UUID)
SELECT COUNT(*) AS sentinel_owned_rows
FROM   trades
WHERE  user_id = '00000000-0000-0000-0000-000000000001';
-- Expected output: equal to total row count of trades pre-migration.
```

**Reverse DDL (safe — column has DEFAULT, no FK constraints in Phase A):**

```sql
DROP INDEX IF EXISTS idx_trades_user_id;
ALTER TABLE trades DROP COLUMN IF EXISTS user_id;
```

### Migration `004_add_user_id_to_audit_log.sql`

```sql
-- Phase A — add user_id to audit_log.
-- audit_log today has chat_id BIGINT but no user_id (see migrations/002_audit_log.sql:7).
-- chat_id is the only proxy for "who did this" — fine for single-user, ambiguous later.

-- 1. Forward DDL
ALTER TABLE audit_log
    ADD COLUMN IF NOT EXISTS user_id UUID
    NOT NULL
    DEFAULT '00000000-0000-0000-0000-000000000001';

-- 2. Backfill
UPDATE audit_log
SET    user_id = '00000000-0000-0000-0000-000000000001'
WHERE  user_id IS NULL;

-- 3. Index
CREATE INDEX IF NOT EXISTS idx_audit_log_user_id ON audit_log (user_id);

-- 4. Verification (must return 0)
SELECT COUNT(*) AS null_user_id_rows FROM audit_log WHERE user_id IS NULL;
-- Expected output: 0
```

**Reverse DDL:**

```sql
DROP INDEX IF EXISTS idx_audit_log_user_id;
ALTER TABLE audit_log DROP COLUMN IF EXISTS user_id;
```

### Migration order

`003` then `004`. They are independent (no FK between `trades` and `audit_log` involving `user_id` in Phase A), but ordering keeps the migration ledger linear for `migrations/verify_migrations.py`.

### Update to `migrations/verify_migrations.py`

In PR-A1, extend the `MIGRATIONS` list:

```python
MIGRATIONS: list[tuple[str, str, list[str] | None]] = [
    ("001_addon_phase2.sql", "trades", ["is_addon", "base_campaign_lot_id", "addon_sequence"]),
    ("002_audit_log.sql",    "audit_log", None),
    ("003_add_user_id_to_trades.sql",    "trades",    ["user_id"]),
    ("004_add_user_id_to_audit_log.sql", "audit_log", ["user_id"]),
]
```

### What Phase A does NOT add to the DB

- No `users` table. (Phase B.)
- No `telegram_links` table. (Phase C.)
- No `broker_links`, `account_profiles`, `methodology_profiles`, `algo_universe`. (Phase B.)
- No FK from `trades.user_id` to `users.id`. (Cannot add — `users` does not exist yet. Phase B adds the FK as a separate migration.)
- No RLS, no policies. (Phase C, after every code path filters.)

This is intentional. Phase A is the minimum DB change that lets us thread `user_id` through code without changing behavior.

---

## 4. Code changes (additive only)

Every change in this section is **backwards-compatible**: existing call sites continue to work without modification. The new `user_id` parameter is always optional and defaults to `get_current_user_id()` resolution.

### 4.1 New module: `user_context.py`

A single tiny module is the source of truth for "who is the current user?" Phase A returns one UUID; Phase C swaps the body to consult `telegram_links` per request context.

```python
# user_context.py
"""
Phase A — single-user context resolver.

In Phase A, every code path has implicit "current user = Mark". This module
centralizes that assumption so Phase B/C can swap the resolution strategy
(per-request context from webhook handler, per-worker context from job
metadata) without touching every call site.

Hard contract:
  get_current_user_id() ALWAYS returns a valid UUID string. It never returns
  None, never raises. If DEFAULT_USER_ID env var is missing, it logs a single
  warning at first call and returns SENTINEL_USER_ID.
"""
from __future__ import annotations
import os
import sys

SENTINEL_USER_ID = "00000000-0000-0000-0000-000000000001"

_warned = False  # one-shot warning latch


def get_current_user_id() -> str:
    """Return the active user_id for the current execution context.

    Phase A: env-var driven, process-wide.
    Phase B: still env-var driven but reads from DB-backed account_profiles.
    Phase C: per-request context from telegram_links / webhook handler.

    Never None, never raises.
    """
    global _warned
    val = os.environ.get("DEFAULT_USER_ID", "").strip()
    if val:
        return val
    if not _warned:
        print(
            "[user_context] DEFAULT_USER_ID unset — using sentinel UUID. "
            "Phase A is single-user; this is expected on dev boxes.",
            file=sys.stderr,
            flush=True,
        )
        _warned = True
    return SENTINEL_USER_ID
```

**Tests** (`tests/test_user_context.py`):
- `test_returns_env_when_set` — set env, call function, assert.
- `test_returns_sentinel_when_unset` — `monkeypatch.delenv("DEFAULT_USER_ID")`, assert returns `SENTINEL_USER_ID`.
- `test_warns_once` — capture stderr, call twice, assert one warning.
- `test_sentinel_matches_migration_default` — read `migrations/003_*.sql`, regex-match the DEFAULT clause, assert it equals `SENTINEL_USER_ID`. **Guards against drift between code and SQL.**

### 4.2 `bot_core.py` — load `DEFAULT_USER_ID` at import

**Current** (`bot_core.py:13-23`):

```python
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise SystemExit("TELEGRAM_BOT_TOKEN is not set")

_admin_raw = os.getenv("TELEGRAM_ADMIN_ID")
try:
    ADMIN_ID = int(_admin_raw)
except (TypeError, ValueError):
    raise SystemExit(...)
```

**New** (additive — TOKEN/ADMIN_ID untouched):

```python
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise SystemExit("TELEGRAM_BOT_TOKEN is not set")

_admin_raw = os.getenv("TELEGRAM_ADMIN_ID")
try:
    ADMIN_ID = int(_admin_raw)
except (TypeError, ValueError):
    raise SystemExit(...)

# Phase A: DEFAULT_USER_ID resolution. Unset is allowed (logs warning + falls
# back to sentinel UUID). Crashing on missing DEFAULT_USER_ID would block
# existing production deploys that don't yet have it in their .env.
from user_context import get_current_user_id  # noqa: E402
DEFAULT_USER_ID = get_current_user_id()
```

`DEFAULT_USER_ID` becomes a module-level constant alongside `TOKEN` and `ADMIN_ID`. Existing imports of `bot_core` are unaffected.

### 4.3 `supabase_repository.py` — thread `user_id` through every function

Every function in `supabase_repository.py` gets a new optional `user_id` parameter. **Order of operations:** PR-A3 covers writes, PR-A4 covers reads.

The pattern is the same everywhere:

```python
# Before
def get_all_trades(sb):
    return sb.table("trades").select("*").execute().data or []

# After (PR-A4)
def get_all_trades(sb, user_id: str | None = None):
    uid = user_id or _resolve_user_id()
    return (
        sb.table("trades")
        .select("*")
        .eq("user_id", uid)
        .execute()
        .data or []
    )
```

With:

```python
# top of supabase_repository.py
from user_context import get_current_user_id as _resolve_user_id
```

**Full inventory of writes (PR-A3 scope):**

| Function | Current signature | New signature | Mutation |
|---|---|---|---|
| `update_trade` | `(sb, trade_id, fields)` | `(sb, trade_id, fields, user_id=None)` | Add `.eq("user_id", uid)` to UPDATE. Inject `user_id` into `fields` dict if absent — Supabase upserts won't overwrite the column on UPDATE, but the explicit-eq prevents one-tenant-overwriting-another's-row in Phase C. |
| `update_stop_for_campaign` | `(sb, campaign_id, stop_price)` | `(sb, campaign_id, stop_price, user_id=None)` | Add `.eq("user_id", uid)`. |
| `update_management_notes` | `(sb, campaign_id, note)` | `(sb, campaign_id, note, user_id=None)` | Add `.eq("user_id", uid)` to UPDATE and to the internal `get_management_notes` read. Propagate `uid` into the `audit_logger.log_action(...)` call (see §4.7). |
| `update_addon_record` | `(sb, trade_id, base_campaign_lot_id, addon_sequence)` | `(sb, trade_id, base_campaign_lot_id, addon_sequence, user_id=None)` | Add `.eq("user_id", uid)`. |
| `insert_trades` | `(sb, trades: list)` | `(sb, trades: list, user_id=None)` | For each dict in `trades`, set `d.setdefault("user_id", uid)`. **Does not overwrite** — caller-supplied user_id wins (matters for IBKR importer future per-account flows). |

**Full inventory of reads (PR-A4 scope):**

| Function | Current signature | New signature | Filter |
|---|---|---|---|
| `get_all_trades` | `(sb)` | `(sb, user_id=None)` | `.eq("user_id", uid)` |
| `get_trades_by_symbol` | `(sb, symbol)` | `(sb, symbol, user_id=None)` | `.eq("user_id", uid)` |
| `get_incomplete_trades` | `(sb, limit=100)` | `(sb, limit=100, user_id=None)` | `.eq("user_id", uid)` before the `.or_(...)` |
| `get_earlier_buys_for_campaign` | `(sb, campaign_id, before_date)` | `(sb, campaign_id, before_date, user_id=None)` | `.eq("user_id", uid)` |
| `get_old_trades` | `(sb, before_date)` | `(sb, before_date, user_id=None)` | `.eq("user_id", uid)` |
| `get_campaigns_pnl` | `(sb)` | `(sb, user_id=None)` | `.eq("user_id", uid)` |
| `get_management_notes` | `(sb, campaign_id)` | `(sb, campaign_id, user_id=None)` | `.eq("user_id", uid)` |
| `get_latest_buy_trade_id` | `(sb, symbol, campaign_id)` | `(sb, symbol, campaign_id, user_id=None)` | `.eq("user_id", uid)` |
| `get_open_campaign_for_symbol` | `(sb, symbol)` | `(sb, symbol, user_id=None)` | `.eq("user_id", uid)` |
| `get_existing_trade_ids` | `(sb)` | `(sb, user_id=None)` | `.eq("user_id", uid)` |

**Backwards compatibility test** (`tests/test_repository_user_id.py`):
- For each function, call it with no `user_id` arg. Assert it resolves to the sentinel UUID via `user_context`.
- Call it with explicit `user_id="..."`. Assert it filters/tags with that value.
- Insert a row under a second UUID (test-only). Assert default-resolving callers do not see it.

### 4.4 `bot_health.py` — direct `supabase.table("trades")` reads

Four direct table calls (`bot_health.py:64, 74, 90, 99`). PR-A4 replaces each with a repository call that threads `user_id`:

| Line | Current | New |
|---|---|---|
| 64 | `supabase.table("trades").select("trade_date").order(...).limit(1)` | Add `.eq("user_id", DEFAULT_USER_ID)` (or migrate to a new `repo.get_latest_trade_date(sb, user_id=...)` — recommended). |
| 74 | `supabase.table("trades").select("symbol,stop_loss,quantity,side")` | Add `.eq("user_id", DEFAULT_USER_ID)`. |
| 90 | `supabase.table("trades").select("trade_id,campaign_id")` | Add `.eq("user_id", DEFAULT_USER_ID)`. |
| 99 | `supabase.table("trades").select("symbol,setup_type,quantity,side")` | Add `.eq("user_id", DEFAULT_USER_ID)`. |
| 139 | `supabase.table("audit_log").select("id").limit(1)` | Add `.eq("user_id", DEFAULT_USER_ID)`. |

Recommended: introduce thin repo helpers (`repo.get_health_metrics(sb, user_id=...)`) in a follow-up PR; for now, the literal `.eq` is acceptable.

### 4.5 `dashboard.py`, `risk_monitor.py`, `report_scheduler.py`, `telegram_callbacks.py` — direct table calls

These each have a direct `supabase.table("trades")` call that bypasses the repository (`dashboard.py:61, 1314`, `risk_monitor.py:572`, `report_scheduler.py:118`, `telegram_callbacks.py:168`). For PR-A4:

| File:line | Action |
|---|---|
| `risk_monitor.py:572` | Replace with `repo.get_all_trades(sb, user_id=DEFAULT_USER_ID)`. |
| `report_scheduler.py:118` | Add `.eq("user_id", DEFAULT_USER_ID)` to the existing `.gte("trade_date", since)` chain. Could be migrated to a new `repo.get_trades_since(sb, since, user_id=...)`, but not required in Phase A. |
| `dashboard.py:61` | Replace with `repo.get_all_trades(sb, user_id=DEFAULT_USER_ID)`. |
| `dashboard.py:1314` | The UPDATE for an edited trade row — add `.eq("user_id", DEFAULT_USER_ID)`. |
| `telegram_callbacks.py:168` | Addon sequence query — add `.eq("user_id", DEFAULT_USER_ID)`. |
| `telegram_bot.py:520` | Inline trades fetch — replace with `repo.get_all_trades(supabase, user_id=DEFAULT_USER_ID)`. |

`DEFAULT_USER_ID` is imported from `bot_core` or `user_context` depending on what each file already imports (prefer not to add new imports if `bot_core` is already in scope).

### 4.6 `main.py`, `risk_monitor.py`, `report_scheduler.py` — top-level loops

These three each have a "fetch all trades once per cycle" path. After §4.5, the fetch is filtered. **No further plumbing** is needed for Phase A: every downstream function operates on the already-filtered DataFrame, so threading `user_id` deeper into `engine_core`, `analytics_engine`, `adaptive_risk_engine` is not required in Phase A. (Phase B threads it for per-user methodology profile resolution.)

The one exception is **writes initiated mid-loop**:

- `risk_monitor.py` writes to `audit_log` via `audit_logger.log_action(...)` for `ACTION_TELEGRAM_ALERT` — must thread `user_id=DEFAULT_USER_ID` (see §4.7).
- `risk_monitor.py` writes `risk_monitor_state.json` — JSON file, Phase A leaves it shared (see §5).
- `adaptive_risk_engine.py:60` writes `ACTION_RISK_PCT_CHANGE` — thread `user_id` (see §4.7).

### 4.7 `audit_logger.log_action` — add `user_id` parameter

**Current signature** (`audit_logger.py:36`):

```python
def log_action(
    sb,
    action: str,
    *,
    chat_id: Optional[int] = None,
    before: Optional[dict] = None,
    after: Optional[dict] = None,
    metadata: Optional[dict] = None,
) -> bool:
```

**New signature:**

```python
def log_action(
    sb,
    action: str,
    *,
    user_id: Optional[str] = None,   # NEW — defaults to get_current_user_id()
    chat_id: Optional[int] = None,
    before: Optional[dict] = None,
    after: Optional[dict] = None,
    metadata: Optional[dict] = None,
) -> bool:
```

Body change:

```python
from user_context import get_current_user_id

row = {"action": action, "user_id": user_id or get_current_user_id()}
if chat_id is not None:
    row["chat_id"] = int(chat_id)
# ... rest unchanged
```

**Caller updates (PR-A3):**

| File:line | Action | Pass-through |
|---|---|---|
| `supabase_repository.py:116` (addon confirm) | Pass `user_id=user_id` from the caller (PR-A3 already threads `user_id` into `update_management_notes`). | yes |
| `adaptive_risk_engine.py:60` (risk pct change) | Pass `user_id=get_current_user_id()`. | yes |
| `telegram_devops.py:99, 136` (dev PIN activate/fail) | Pass `user_id=get_current_user_id()`. | yes |

`log_action` is fail-open — keep that property. If `get_current_user_id()` somehow returns a malformed value, the function still tries the insert; if Supabase rejects it, the existing `except` swallows the error and prints to stderr.

### 4.8 `ibkr_trade_importer.py:174` — `insert_trades` call

Current:

```python
existing = repo.get_all_trades(sb)
# ... filter for new ...
repo.insert_trades(sb, new)
```

After PR-A3/A4:

```python
uid = get_current_user_id()
existing = repo.get_all_trades(sb, user_id=uid)
# ... filter for new ...
repo.insert_trades(sb, new, user_id=uid)
```

`insert_trades` injects `user_id` into each dict only if not already set, so the importer doesn't need to set it per row.

### 4.9 What does NOT change in Phase A code

- `engine_core.py` — every function. Math runs on filtered DataFrames; no `user_id` plumbing needed.
- `analytics_engine.py` — same.
- `adaptive_risk_engine.py` — except the one `log_action` call site in §4.7.
- `addon_risk_engine.py` — pure math.
- `telegram_formatters.py`, `telegram_menus.py`, `telegram_portfolio.py` — display only.
- `telegram_bot_secure_runner.py` — admin guard untouched (Mark conflict #3 resolution; `CLAUDE.md:21`).
- All Hebrew Telegram message templates.
- `docker-compose.yml` — services and command unchanged.
- `account_state.py` — still reads `sentinel_config.json`. (Phase B moves NAV to DB.)

---

## 5. State files in Phase A

JSON state files **stay shared** in Phase A. The five files in scope:

- `sentinel_config.json` — NAV + risk_pct (read by 8 modules).
- `risk_monitor_state.json` — anti-spam dedup, peak_open_r, checkpoints.
- `risk_journal.json` — adaptive risk journal (500-row buffer).
- `risk_recommendations.json` — adherence tracking.
- `sector_cache.json` — globally safe (market data, not user data).

**Rationale for not moving them in Phase A:**

Moving these files into DB is high-risk because they encode anti-spam timing state (`last_alert_ts`, cooldown windows). A subtle migration bug = duplicate alerts in Mark's Telegram, which is the worst possible UX regression. The Phase B plan (`HYPERSCALER_DESIGN_V0.md` §"Phase B") uses dual-write for 1 week before flipping the read path; that's deliberately more involved than Phase A's scope.

**Phase A leaves the JSON files alone.** This is a known limitation, documented here.

### 5.1 Cross-reference: Issue N3 must land BEFORE Phase A goes to prod

Research's `RESEARCH_FINDINGS_DAY1.md` Issue N3 (Sprint 10 P0) identifies a real race condition on `risk_monitor_state.json`:

- Non-atomic writes at `risk_monitor.py:106-107`.
- Non-atomic read-modify-write from a different container at `bot_helpers.py:49-66` (`_write_runner_decision`).
- Unprotected concurrent reads at `dashboard.py:495` and `bot_health.py:121`.

**Today** (single user, single risk_monitor container, infrequent dashboard reads) the race is rare and the consequence is one missed cooldown — annoying but not catastrophic.

**After Phase A** — if Mark's deployment is the only one, nothing changes. The race risk is unchanged.

**After Phase C** — if a second user is added without N3 being fixed first, every cycle of every user can interleave on the same `/app/risk_monitor_state.json` file. Lost updates become routine, and "duplicate alert for user A because user B's cycle clobbered the cooldown timestamp" becomes a daily incident.

**Decision:** N3 ships as a Sprint 10 P0 PR **independently of Phase A** (it doesn't require any of this spec). But Phase B/C must not ship while N3 is unresolved. Document the dependency in the Phase B kickoff doc.

**Phase A acceptance criterion** (§10) does NOT block on N3; N3 is a separate, parallel Sprint 10 P0 owned by Jordan (per `DAY1_MIDDAY_STANDUP.md` priority table). Phase A on its own does not exacerbate the race because no new writer is introduced.

---

## 6. Smoke test plan (Mark's directive #2)

Mark's directive (`MARK_ALIGNMENT_REVIEW.md` §4 #2):

> All Hyperscaler migrations must include a "single-user identity" smoke test. Test fixture: original-single-user prod database. Run analytics. Assert WR, Expectancy, PF, total_r, profit_factor are byte-for-byte identical to pre-Hyperscaler `main`. If any number moves, the migration is rejected.

### 6.1 What we capture as the baseline

Before applying migrations 003/004 to the production-equivalent DB, snapshot the following for the existing user:

| Surface | Capture method | File |
|---|---|---|
| `/portfolio` Telegram message | Trigger `/portfolio` once; save the raw markdown bytes | `tests/snapshots/portfolio_baseline.md` |
| Heat score + adaptive recommendation | `adaptive_risk_engine.compute_adaptive_risk_recommendation(...)` | `tests/snapshots/adaptive_baseline.json` |
| `analytics_engine.compute_period_analytics()` for last 30/90/365 days | direct call | `tests/snapshots/analytics_baseline.json` |
| NAV, target_risk_usd, exposure_pct | `account_state.load()` + `engine_core` exposure helper | `tests/snapshots/nav_baseline.json` |
| Active alert digest for one risk_monitor cycle | Mock send_telegram, run one cycle, capture all `send_message` calls | `tests/snapshots/alerts_baseline.json` |
| `audit_log` row count + last 100 rows (excluding ts) | SELECT | `tests/snapshots/audit_baseline.json` |
| Total `trades` row count + checksum (hash of trade_ids) | SELECT | `tests/snapshots/trades_baseline.json` |

### 6.2 Comparison script

Run after each Phase A PR ships against the production-equivalent DB. Pseudocode (`scripts/phase_a_smoke_compare.py`):

```python
"""
Phase A smoke comparison.

Diffs the live system's outputs against tests/snapshots/*_baseline.* and
fails (exit 1) on any mismatch beyond an allowed delta (timestamps only).

Usage:
    SUPABASE_URL=... SUPABASE_KEY=... DEFAULT_USER_ID=00000000-... \
      python3 scripts/phase_a_smoke_compare.py
"""
from __future__ import annotations
import json, hashlib, sys
from pathlib import Path

import account_state
import analytics_engine
import adaptive_risk_engine as are
import engine_core as ec
import supabase_repository as repo
from bot_core import supabase, DEFAULT_USER_ID
from risk_monitor import _run_one_cycle_dry  # to be exposed as a test entrypoint

SNAP = Path("tests/snapshots")
TIMESTAMP_KEYS = {"ts", "updated_at", "last_alert_ts", "nav_updated_at",
                  "trade_date", "risk_changed_ts"}


def _strip_timestamps(obj):
    """Recursively drop timestamp-shaped values so diffs ignore wall-clock."""
    if isinstance(obj, dict):
        return {k: _strip_timestamps(v) for k, v in obj.items()
                if k not in TIMESTAMP_KEYS}
    if isinstance(obj, list):
        return [_strip_timestamps(x) for x in obj]
    return obj


def _diff(label, baseline, current):
    b = _strip_timestamps(baseline)
    c = _strip_timestamps(current)
    if b == c:
        print(f"✓ {label}")
        return True
    print(f"✗ {label} DIVERGES")
    # Print a structural diff (first-level keys for dicts).
    if isinstance(b, dict) and isinstance(c, dict):
        for k in sorted(set(b) | set(c)):
            if b.get(k) != c.get(k):
                print(f"    [{k}] baseline={b.get(k)!r} current={c.get(k)!r}")
    else:
        print(f"    baseline={b!r}")
        print(f"    current={c!r}")
    return False


def compare_trades():
    rows = repo.get_all_trades(supabase, user_id=DEFAULT_USER_ID)
    ids = sorted(str(r["trade_id"]) for r in rows)
    checksum = hashlib.sha256("|".join(ids).encode()).hexdigest()
    baseline = json.loads((SNAP / "trades_baseline.json").read_text())
    return _diff("trades count+checksum",
                 baseline,
                 {"count": len(rows), "checksum": checksum})


def compare_analytics():
    out = {}
    for window in (30, 90, 365):
        out[str(window)] = analytics_engine.compute_period_analytics(
            supabase, days=window, user_id=DEFAULT_USER_ID)
    baseline = json.loads((SNAP / "analytics_baseline.json").read_text())
    return _diff("analytics WR/Expectancy/PF", baseline, out)


def compare_nav():
    acc = account_state.load()
    baseline = json.loads((SNAP / "nav_baseline.json").read_text())
    return _diff("nav", baseline, acc)


def compare_adaptive():
    rec = are.compute_adaptive_risk_recommendation(supabase, user_id=DEFAULT_USER_ID)
    baseline = json.loads((SNAP / "adaptive_baseline.json").read_text())
    return _diff("adaptive risk recommendation", baseline, rec)


def compare_alerts():
    alerts = _run_one_cycle_dry(supabase, user_id=DEFAULT_USER_ID)
    baseline = json.loads((SNAP / "alerts_baseline.json").read_text())
    return _diff("risk_monitor cycle alerts", baseline, alerts)


def main() -> int:
    ok = all([
        compare_trades(),
        compare_nav(),
        compare_analytics(),
        compare_adaptive(),
        compare_alerts(),
    ])
    if ok:
        print("\n✅ Phase A smoke test passed — byte-identical for existing user.")
        return 0
    print("\n🔴 Phase A smoke test FAILED — see diffs above. Migration rejected.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

**Notes:**
- The `_run_one_cycle_dry` helper does not exist yet; PR-A4 adds it as a thin wrapper around `risk_monitor`'s main loop that captures `send_message` calls instead of sending them.
- `analytics_engine.compute_period_analytics` and `adaptive_risk_engine.compute_adaptive_risk_recommendation` gain optional `user_id` parameters in PR-A4. (Internally they call `repo.get_all_trades(sb, user_id=...)`.)

### 6.3 When to run the smoke test

- **Locally, before pushing PR-A1.** Captures the baseline snapshot. Commit it under `tests/snapshots/`.
- **In CI, on every Phase A PR.** Runs `phase_a_smoke_compare.py` against a CI Supabase using the same baseline. Must pass.
- **In production (staging clone first, then prod), after applying migrations 003/004.** Manual operator step.

---

## 7. Rollback plan

### 7.1 Per-migration rollback

| Migration | Rollback | Risk |
|---|---|---|
| `003_add_user_id_to_trades.sql` | `DROP INDEX idx_trades_user_id; ALTER TABLE trades DROP COLUMN user_id;` | Safe. Column has DEFAULT — no app data lost. No FK constraints. Index drop is free. |
| `004_add_user_id_to_audit_log.sql` | `DROP INDEX idx_audit_log_user_id; ALTER TABLE audit_log DROP COLUMN user_id;` | Safe. Same reasoning. |

Both DROPs are reversible by re-applying the forward migration; the DEFAULT clause re-backfills.

### 7.2 Per-PR code rollback

| PR | Rollback | Risk |
|---|---|---|
| PR-A1 (migrations + verify_migrations.py update) | `git revert` the PR; run the rollback SQL above. | Low. |
| PR-A2 (`user_context.py` + bot_core load) | `git revert`. Module is leaf — no callers in PR-A2. | Trivial. |
| PR-A3 (writes thread `user_id`) | `git revert`. Callers stop passing `user_id`; functions still work because the param is optional. **DB column stays** (no rollback of 003/004 needed). | Low — kwargs are additive. |
| PR-A4 (reads thread `user_id`) | `git revert`. Same — reads stop filtering, fall back to unfiltered SELECT. Behavior reverts to pre-A4 single-tenant fetch. | Low. |
| PR-A5 (state files — see §5: deferred) | n/a (Phase B). | n/a |

### 7.3 Trigger conditions for rollback

Roll back **immediately** (within one risk_monitor cycle, ~60s) if any of the following diverge from the baseline captured in §6.1:

| Surface | Tolerance |
|---|---|
| Total `trades` row count | 0 (byte-identical) |
| R-multiples for any open position | 0 (byte-identical to 4 decimals) |
| Heat score | ±0.0 (the formula is deterministic on filtered data) |
| Adaptive risk recommendation direction (`up` / `down_fast` / `down` / `flat`) | identical |
| NAV from `account_state.load()` | identical |
| Per-cycle alert count | identical (±0) |
| Alert text content (any chunk) | identical bytes (ignoring timestamps) |
| `audit_log` insertion rate | identical (±1 row tolerance for any in-flight rows during the cutover minute) |

If `pytest -q` fails on the production-equivalent CI, do not deploy. If smoke compare fails, do not promote.

### 7.4 Rollback runbook (operator)

1. SSH to production host.
2. `cd /app && git checkout <previous-merge-commit>`
3. `docker-compose down && docker-compose up -d` (no SQL needed if DEFAULT column rollback not required).
4. If migrations need rollback too:
   - `SUPABASE_URL=... SUPABASE_KEY=... psql -f migrations/rollback_004.sql`
   - `SUPABASE_URL=... SUPABASE_KEY=... psql -f migrations/rollback_003.sql`
   - Re-run `python3 migrations/verify_migrations.py` — must show migrations 003/004 as missing.
5. Confirm Telegram bot startup notification arrives.
6. Run `phase_a_smoke_compare.py` against the rolled-back state vs. the original baseline — must match.

---

## 8. PR breakdown

Per Mark directive #2: **single-user smoke test for every Hyperscaler PR.** Each PR below ships with a CI run of `phase_a_smoke_compare.py`.

### PR-A1 — migrations + verify_migrations

- **Files touched:** `migrations/003_add_user_id_to_trades.sql` (new), `migrations/004_add_user_id_to_audit_log.sql` (new), `migrations/verify_migrations.py` (extend `MIGRATIONS` list), `tests/snapshots/*_baseline.*` (baseline capture).
- **Line-count estimate:** ~80 SQL + ~10 Python + ~500 lines of baseline snapshot JSON.
- **Dependencies:** none.
- **Smoke-test scope:** apply migrations to staging clone of prod, run `phase_a_smoke_compare.py`. Pre-migration baseline must equal post-migration result. (Reads are still unfiltered, so behavior unchanged.)
- **Risk:** low. Migrations are idempotent, additive, default-backed.

### PR-A2 — `user_context.py` + `bot_core` load

- **Files touched:** `user_context.py` (new, ~40 lines), `bot_core.py` (add 3 lines at end), `tests/test_user_context.py` (new, ~50 lines).
- **Line-count estimate:** ~100 lines total.
- **Dependencies:** PR-A1 merged (so the constant matches the SQL DEFAULT).
- **Smoke-test scope:** no behavior change — module is unused outside its own tests. `pytest -q` must pass. `phase_a_smoke_compare.py` must pass.
- **Risk:** trivial. Leaf module, no callers.

### PR-A3 — thread `user_id` through `supabase_repository` writes

- **Files touched:** `supabase_repository.py` (5 write functions), `audit_logger.py` (add `user_id` param), `adaptive_risk_engine.py` (one log_action call), `telegram_devops.py` (two log_action calls), `telegram_bot.py` (4 repo write calls — `update_trade`, `update_stop_for_campaign`), `telegram_callbacks.py` (1 update), `ibkr_trade_importer.py` (`insert_trades` call), `dashboard.py` (1 update), `tests/test_repository_user_id.py` (new).
- **Line-count estimate:** ~200 lines code + ~150 lines test.
- **Dependencies:** PR-A2 merged.
- **Smoke-test scope:** every write now tags `user_id`. Read-side still unfiltered, so Mark continues to see all rows (his and any test-injected second-user rows would be visible). Smoke compare must pass: same row count, same audit cadence, same R values (because no read path changed).
- **Risk:** low. Writes are now strictly more specific; no caller is forced to pass `user_id`.

### PR-A4 — thread `user_id` through `supabase_repository` reads + direct table reads

- **Files touched:** `supabase_repository.py` (10 read functions), `risk_monitor.py:572`, `report_scheduler.py:118`, `dashboard.py:61`, `telegram_bot.py:520`, `bot_health.py:64/74/90/99/139`, `telegram_callbacks.py:168`, `analytics_engine.py` (optional `user_id` on `compute_period_analytics`), `adaptive_risk_engine.py` (`compute_adaptive_risk_recommendation` gets optional `user_id`).
- **Line-count estimate:** ~250 lines code + ~100 lines test extension.
- **Dependencies:** PR-A3 merged.
- **Smoke-test scope:** **this is the highest-risk PR.** Every read now filters by `user_id`. Because every existing row was backfilled in PR-A1, Mark continues to see all his rows. Smoke compare must pass byte-identically. Specifically: total trades count, total open positions, all R-values, alert text.
- **Risk:** medium. If `user_context.get_current_user_id()` ever returns a UUID that doesn't match the backfilled rows (e.g., `DEFAULT_USER_ID` env mismatch), Mark would see an empty portfolio — visible immediately, easy to roll back.

### PR-A5 — state-file readers/writers (DEFERRED to Phase B per §5)

Not in Phase A. Documented here so the PR backlog is clear:

- `bot_helpers.py` (`_write_runner_decision`, `get_account_settings`), `dashboard.py:495`, `bot_health.py:121, 129`, `risk_monitor.py:30,106-107`, `account_state.py:load()`, `adaptive_risk_engine.py:31,95-150,575-620`.
- These migrate to DB in Phase B with dual-write semantics. Phase A does not touch them.
- **Pre-condition:** Issue N3 (atomic writes + `flock`) must land first (Sprint 10 P0, separate PR).

### PR-A6 — cleanup (optional, post-A5)

- Remove dead branches where `user_id` was conditionally None.
- Tighten signatures: drop the `| None = None` default on internal repo functions called only by tooling that always passes `user_id`.
- Consider this a Phase B polish PR, not Phase A.

### Estimated total

- PR-A1: 1 dev-day.
- PR-A2: 0.5 dev-day.
- PR-A3: 2 dev-days.
- PR-A4: 3 dev-days.
- PR-A5: out of Phase A.
- PR-A6: out of Phase A.

**Phase A total: ~6.5 dev-days** (vs. ~10 estimated in V0). Lower because we explicitly scoped state files out.

---

## 9. Open questions

These do not block PR-A1 but should be answered before PR-A3 merges.

1. **`DEFAULT_USER_ID` storage: `.env` or `sentinel_config.json`?** Founder has said "no secrets in repo." A UUID is not a secret per se, but `.env` is consistent with `TELEGRAM_BOT_TOKEN`, `SUPABASE_KEY`, etc. Recommendation: `.env`. Need founder ack.

2. **Should we add a `users` table now (empty) or wait for Phase B?** Adding it now lets us FK `trades.user_id → users.id` immediately, which is more idiomatic Postgres. But the FK would force us to seed at least one `users` row before backfill — fine, but it spreads Phase B's data model into Phase A. Recommendation: defer. Phase A keeps `trades.user_id` as a bare UUID column.

3. **`DEFAULT_USER_ID` env var validation: strict UUID regex or lax string?** Lax is forgiving (works with `"mark"` on a dev box); strict catches typos in prod. Recommendation: strict in `bot_core` (regex check at import) but **fail-open** (warn + use sentinel, like the unset case). The smoke test will catch any real mismatch.

4. **What does the `tests/snapshots/*_baseline.*` lifecycle look like?** These snapshots will drift the moment Mark trades. Three options:
   - (a) regenerate manually before each Phase A PR.
   - (b) commit baselines once, accept that PRs near a trading day will show drift, ignore via timestamp-strip + checksum-only comparison.
   - (c) maintain a separate "frozen reference DB" copy for snapshot testing.
   Recommendation: (b) with checksum-only on the trades surface; analytics/heat-score are deterministic on the same filtered DataFrame so they don't drift between consecutive runs.

5. **Should `audit_log.user_id` be NOT NULL with DEFAULT, or NULL-allowed?** NOT NULL DEFAULT is what migration `004` specifies. The trade-off: NOT NULL forces every code path that inserts to provide a value (via the DEFAULT, transparently). NULL-allowed would let us deploy `004` independently of `audit_logger` changes. Recommendation: keep NOT NULL DEFAULT — the DEFAULT covers any insert that forgets the column. PR-A3 then explicitly threads `user_id` for forensic clarity.

6. **`telegram_callbacks.py:168` — is there a guarantee the addon-sequence query is always Mark's data?** Today yes (single user). After PR-A4 the `.eq("user_id", DEFAULT_USER_ID)` makes the assumption explicit. But what if a future PR uses this callback for an admin querying another user's trades? Recommendation: in Phase A, hardwire `DEFAULT_USER_ID`. In Phase C, replace with a per-request `user_id` resolved from `telegram_links`.

7. **Does `bot_health.py`'s health check stay per-user-scoped, or become system-wide?** Today the health check counts all trades, validates all stop_losses, etc. In multi-tenant, a per-user health is more useful; a system-wide health is also valuable for ops. Recommendation: per-user for Phase A (preserves identity); add a `repo.get_system_health_metrics(sb)` admin-only helper in Phase B.

8. **Sentinel UUID `00000000-0000-0000-0000-000000000001` — is this fine as a literal in two places (Python + SQL), or do we need a single source?** Today there's a unit test (§4.1) that asserts they match. Sufficient for Phase A. In Phase B, when `users` table seeds Mark's row, the migration SQL itself can read the env var via a templating step in `migrations/verify_migrations.py`.

---

## 10. Acceptance criteria (Mark's gate)

Phase A is considered shipped when **all** of the following are true:

- [ ] Migrations `003` and `004` applied to the production-equivalent Supabase without errors.
- [ ] `migrations/verify_migrations.py` exits 0 against production. Lists `003` and `004` as applied with their expected columns.
- [ ] `SELECT COUNT(*) FROM trades WHERE user_id IS NULL` returns 0.
- [ ] `SELECT COUNT(*) FROM audit_log WHERE user_id IS NULL` returns 0.
- [ ] All `trades` and `audit_log` rows have `user_id = '00000000-0000-0000-0000-000000000001'` (the sentinel — Mark's UUID for Phase A).
- [ ] `pytest -q` passes on the branch.
- [ ] `scripts/phase_a_smoke_compare.py` exits 0 against production-equivalent DB. Specifically:
  - Trades count + checksum identical to baseline.
  - `compute_period_analytics(days=30/90/365)` returns identical WR / Expectancy / PF / total_r / profit_factor.
  - `compute_adaptive_risk_recommendation()` returns identical heat_score, direction, recommended_risk_pct.
  - `account_state.load()` returns identical NAV / target_risk_usd / freshness_label.
  - One dry-run `risk_monitor` cycle produces identical alert count and alert text bytes (timestamps stripped).
- [ ] No production behavior change visible to Mark:
  - `/portfolio` returns the same row count, same R values, same status emojis.
  - Daily digest fires at the same UTC hour with the same content.
  - No new error logs in `docker-compose logs` during a 24h post-deploy window.
- [ ] `tests/test_user_context.py`, `tests/test_repository_user_id.py` pass.
- [ ] Rollback runbook (§7.4) executed end-to-end in staging at least once.
- [ ] CLAUDE.md hard constraints honored:
  - `telegram_bot_secure_runner.py` untouched.
  - `engine_core.is_stat_countable()` signature untouched.
  - `RISK_LADDER`, `_R_RUNNER`, `_R_PROFIT_PROTECT`, `_R_WORKING`, `DRAWDOWN_TRIGGER_PCT` constants untouched.
  - `7500.0` fallback NAV not removed (Phase B).
- [ ] AGENTS.md Red Lines preserved — verified by smoke test #2 (WR/Expectancy on mixed-bucket fixture returns identical numbers to pre-Phase-A `main`).

When all boxes are checked, Phase A is done. Phase B kickoff requires the founder to answer the 5 blocking decisions in `DAY1_MIDDAY_STANDUP.md` §"Blocking founder decisions" plus the 12 questions in `HYPERSCALER_DESIGN_V0.md` §"Phase 4".

---

## Appendix — File touch list

Files modified by Phase A (read-only inventory; nothing written today):

**Phase A migrations (new):**
- `/home/user/lidorAvr-sentinel-trading/migrations/003_add_user_id_to_trades.sql`
- `/home/user/lidorAvr-sentinel-trading/migrations/004_add_user_id_to_audit_log.sql`

**Phase A code (modified or new):**
- `/home/user/lidorAvr-sentinel-trading/user_context.py` (new)
- `/home/user/lidorAvr-sentinel-trading/bot_core.py` (additive: 3 lines)
- `/home/user/lidorAvr-sentinel-trading/supabase_repository.py` (additive: optional `user_id` kwarg on every function)
- `/home/user/lidorAvr-sentinel-trading/audit_logger.py` (additive: optional `user_id` kwarg)
- `/home/user/lidorAvr-sentinel-trading/adaptive_risk_engine.py` (one call site: pass `user_id=`)
- `/home/user/lidorAvr-sentinel-trading/telegram_devops.py` (two call sites)
- `/home/user/lidorAvr-sentinel-trading/telegram_bot.py` (four call sites)
- `/home/user/lidorAvr-sentinel-trading/telegram_callbacks.py` (one call site)
- `/home/user/lidorAvr-sentinel-trading/ibkr_trade_importer.py` (one call site)
- `/home/user/lidorAvr-sentinel-trading/dashboard.py` (two call sites — read + update)
- `/home/user/lidorAvr-sentinel-trading/risk_monitor.py` (one direct fetch → repo call)
- `/home/user/lidorAvr-sentinel-trading/report_scheduler.py` (one direct fetch → repo call)
- `/home/user/lidorAvr-sentinel-trading/bot_health.py` (five direct table calls)
- `/home/user/lidorAvr-sentinel-trading/analytics_engine.py` (one signature extension)
- `/home/user/lidorAvr-sentinel-trading/migrations/verify_migrations.py` (extend MIGRATIONS list)

**Phase A tests (new):**
- `/home/user/lidorAvr-sentinel-trading/tests/test_user_context.py`
- `/home/user/lidorAvr-sentinel-trading/tests/test_repository_user_id.py`
- `/home/user/lidorAvr-sentinel-trading/tests/snapshots/*_baseline.*` (5 files)
- `/home/user/lidorAvr-sentinel-trading/scripts/phase_a_smoke_compare.py`

**Files NOT touched by Phase A (verify in PR review):**
- `/home/user/lidorAvr-sentinel-trading/telegram_bot_secure_runner.py`
- `/home/user/lidorAvr-sentinel-trading/engine_core.py`
- `/home/user/lidorAvr-sentinel-trading/addon_risk_engine.py`
- `/home/user/lidorAvr-sentinel-trading/account_state.py`
- `/home/user/lidorAvr-sentinel-trading/telegram_formatters.py`
- `/home/user/lidorAvr-sentinel-trading/telegram_menus.py`
- `/home/user/lidorAvr-sentinel-trading/telegram_portfolio.py`
- `/home/user/lidorAvr-sentinel-trading/docker-compose.yml`
- `/home/user/lidorAvr-sentinel-trading/sentinel_config.json`
- `/home/user/lidorAvr-sentinel-trading/risk_monitor_state.json` and other state JSON files (Phase B).
