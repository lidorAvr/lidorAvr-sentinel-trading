# Hyperscaler — Sprint 13 Addendum: Phase-A Compatibility

**Date:** 2026-05-15
**Team:** Hyperscaler
**Scope:** Sprint 13 items — `deploy_watcher.sh` resilience (stale-network
fix on `--build` deploy) + missing-stops data-hygiene surface (55 rows:
MSGE, SNEX, TSLA, JPM, HP).
**Governing:** `SPRINT13_PLAN.md`, `HYPERSCALER_PHASE_A_IMPL.md`,
`HYPERSCALER_SPRINT12_ADDENDUM.md`, `user_context.py`,
`migrations/verify_migrations.py` (ledger ends at `005 → open_tasks`),
DEC-20260515-002, DEC-20260515-005.
**Status:** Doc only. No code, no migration, no commit. Phase B stays a
pure no-op swap.

---

## 1. `deploy_watcher.sh` change is host-infra only — zero Phase-A impact

The Sprint 13 watcher change (e.g. `down` then `up -d --build`, a
post-deploy connectivity self-check, the one-time host systemd re-read)
is **container/network orchestration on the Pi only**. It:

- does **not** touch any application Python module, signature, or import;
- does **not** touch `docker-compose.yml` service commands
  (`telegram_bot_secure_runner.py` stays — CLAUDE.md hard constraint);
- does **not** read, write, `ALTER`, or migrate the database;
- does **not** read `user_context`, thread `user_id`, or touch
  `MODULE_LEVEL_INVARIANTS`.

Net Phase-A delta of the watcher change: **zero** — no schema, no
`user_id`, no resolver code path. It only changes *how* the same
byte-identical containers are recreated and connectivity-verified.

## 2. Missing-stops surface — reuse existing contracts, no new migration

If the missing-stops remediation surfaces nothing persistent (notice-only,
per Mark's pending ruling), there is **zero** Phase-A surface at all.

If Mark rules it surfaces as actionable data-completion items that persist
lifecycle, it MUST reuse the **existing contracts already covered by the
ledger** — no new migration, no `ALTER`, no new column, no new `*.sql`:

- **Option A — `open_tasks`** (migration 005, applied 2026-05-15, verified
  `null_user_id_rows = 0`): write via the existing
  `(user_id, campaign_id, task_type)` unique key with a new
  `task_type` for the stop-completion item. Lifecycle-deltas-only; the
  open set stays engine-derived (same Sprint-10/12 contract).
- **Option B — journal-backlog**: it already writes `trades` (covered by
  migrations 001/003); a real, founder-supplied stop value completes an
  existing row. **No stop is ever fabricated** (AGENTS.md #1/#8); these
  rows never enter WR/Expectancy.

Either way: **no new migration**, `verify_migrations.py` unchanged. No
`user_id` is threaded through any engine/handler signature — that stays
**PR-A3+ deferred**. Every persisted row stamps the sentinel via a single
`user_context.get_current_user_id()` call at the write boundary (never an
inline UUID literal; the literal lives only in the SQL `DEFAULT` +
`SENTINEL_USER_ID`, kept in sync by `tests/test_user_context.py`).
`DEFAULT_USER_ID` unset → sentinel + one-shot warning, reads filter by /
omit the same sentinel (DEFAULT-backed, single tenant). Single-user
runtime stays **byte-identical**.

## 3. Zero billing / quota (DEC-20260515-005)

Sprint 13 introduces **no billing, payments, quota, rate-limit, tier, or
paywall** logic. `deploy_watcher.sh` is infra resilience; the missing-stops
surface is data hygiene over existing tables. No task caps, no plan column.
Closed free beta, invited users, no public signup; billing stays deferred
to Phase D.

## 4. Team-leads consolidation checklist (verify all 4)

1. **No new migration:** missing-stops surface (if persistent) reuses
   `open_tasks` (005) or `trades`/journal-backlog (001/003); no `ALTER`,
   no new column, no new `*.sql`; `verify_migrations.py` unchanged.
2. **No schema change:** existing contracts only; if notice-only, zero
   persistent surface.
3. **Host-infra-only for the watcher:** `deploy_watcher.sh` change touches
   no app code and no DB; `docker-compose.yml` service commands /
   `telegram_bot_secure_runner.py` untouched (CLAUDE.md hard constraint).
4. **Sentinel reuse for any data surface:** writes stamp the sentinel via
   `user_context.get_current_user_id()`; no hard-coded UUID; no `user_id`
   threading (PR-A3+ stays deferred); no fabricated stop, never in
   WR/Expectancy (AGENTS.md #1/#8); single-user byte-identical.
