# Hyperscaler — Sprint 12 Addendum: Phase-A Compatibility

**Date:** 2026-05-15
**Team:** Hyperscaler
**Scope:** Sprint 12 items — T7 portfolio-level drawdown-ack task (in the
existing Open Tasks engine), `/clean` confirmation gate, price-fallback
labels, optional missing-stops notice.
**Governing:** `HYPERSCALER_PHASE_A_IMPL.md`,
`HYPERSCALER_SPRINT10_ADDENDUM.md`, `user_context.py`,
`migrations/005_create_open_tasks.sql` (APPLIED 2026-05-15),
`migrations/verify_migrations.py`, DEC-20260515-002, DEC-20260515-005.
**Status:** Doc only. No code, no migration, no commit. Phase B stays a
pure no-op swap.

---

## 1. T7 portfolio task — reuse `open_tasks`, no new migration

`open_tasks` already exists (migration 005, applied 2026-05-15, verified
`null_user_id_rows = 0`) with the dedup key
`UNIQUE (user_id, campaign_id, task_type)`
(`idx_open_tasks_user_campaign_type`). T7 is per-portfolio, not
per-campaign, but the table is campaign-keyed. **Exact contract if T7
stores lifecycle:**

- T7 MUST write to the existing `open_tasks` table. **No new migration,
  no `ALTER`, no new column, no schema change.** The table already holds
  the columns T7 needs (`status`, `urgency`, `trigger_*` snapshots,
  `notes`, timestamps).
- T7 MUST reuse the existing `(user_id, campaign_id, task_type)` unique
  key. Because T7 is portfolio-scoped (no real campaign), it MUST use a
  **portfolio sentinel `campaign_id` = `__PORTFOLIO__`** (a reserved
  literal that can never collide with a real campaign id), with
  `task_type` = the portfolio drawdown-ack type. This yields exactly one
  lifecycle row per user per portfolio-ack — the same idempotent,
  race-safe upsert semantics Sprint 10 relies on (a Telegram double-tap
  is a no-op upsert, not a duplicate row).
- The set of *open* tasks stays re-derived from the engine
  (`engine_core.compute_position_state()` / portfolio aggregation); the
  table stores **lifecycle deltas only** (done / skipped / notes), so it
  cannot drift. `__PORTFOLIO__` is never treated as a campaign by any
  read path — it is a sentinel partition of the same key space.
- `verify_migrations.py` is unchanged: the `005 → open_tasks → None`
  ledger entry already covers the table; T7 adds no migration.

## 2. No `user_id` threading; sentinel via `user_context`

- None of the Sprint-12 items (T7, `/clean` gate, price-fallback labels,
  missing-stops notice) thread `user_id` through any call site. That
  remains PR-A3+ (writes) / PR-A4 (reads) and stays deferred. No new
  `user_id` parameters on any engine/handler signature.
- Every `open_tasks` write (including T7's portfolio row) stamps the
  sentinel via a single `user_context.get_current_user_id()` call at the
  write boundary — **never re-implemented, never hard-coded, never an
  inline UUID literal** in engine code. The literal lives only in the SQL
  `DEFAULT` + `user_context.SENTINEL_USER_ID`, kept in sync by
  `tests/test_user_context.py`.
- `DEFAULT_USER_ID` unset → `get_current_user_id()` returns the sentinel
  with its existing one-shot warning. Reads either omit the `user_id`
  filter (DEFAULT-backed, single tenant) or filter by the same sentinel.
- No Sprint-12 touchpoint reads `get_user_constant()`; the resolver stays
  dormant. Single-user runtime is **byte-identical**: net delta is one
  portfolio-sentinel lifecycle row class plus presentational labels.

## 3. Zero billing / quota (DEC-20260515-005)

Sprint 12 introduces **no billing, payments, quota, rate-limit, tier, or
paywall** logic. The `/clean` confirmation gate and any audit-review path
add **no schema** — `/clean` is a confirm-before-act guard over existing
behaviour; audit-review reads existing tables. No task caps, no plan
column. Closed free beta, invited users, no public signup; billing stays
deferred to Phase D.

## 4. Team-leads consolidation checklist (verify all 5)

1. **No new migration / no schema change:** T7 reuses the existing
   `open_tasks` table; no `ALTER`/new column/new `*.sql`;
   `verify_migrations.py` unchanged.
2. **Sentinel-partition reuse:** T7 uses the existing
   `(user_id, campaign_id, task_type)` unique key with
   `campaign_id = '__PORTFOLIO__'`; idempotent race-safe upsert
   preserved; `__PORTFOLIO__` never read as a real campaign.
3. **No `user_id` threading:** all writes stamp the sentinel via
   `user_context.get_current_user_id()`; no hard-coded UUID; no new
   `user_id` params; PR-A3+ stays deferred.
4. **Additive-only:** lifecycle-deltas-only contract intact; open set
   still engine-derived; `/clean` and audit-review add no schema;
   presentational labels only.
5. **Red Lines / secure-runner / math intact:** `MODULE_LEVEL_INVARIANTS`
   untouched; price-fallback/cached data labelled (no fallback-as-truth);
   `telegram_bot.py` not rewritten; `telegram_bot_secure_runner.py`
   untouched; no R/NAV/exposure/campaign math changed.
