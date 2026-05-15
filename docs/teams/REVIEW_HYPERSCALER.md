# System Review — Multi-Tenant / Scaling Foundation (Hyperscaler)

**Reviewer:** Hyperscaler team lead
**Date:** 2026-05-15
**Branch:** `claude/review-system-audit-FBZ2h`
**Scope:** Honest state of the Phase A multi-tenant foundation. No code
changes. Verified against source at HEAD, not just docs.

---

## 1. What Phase A actually delivered (and what "dormant" means)

Phase A laid a **multi-tenant foundation that is switched off**. Three concrete things exist in the tree today:

1. **Additive `user_id` columns.** `migrations/003` (trades) and `004`
   (audit_log) add `user_id UUID NOT NULL DEFAULT
   '00000000-0000-0000-0000-000000000001'`, plus a per-table index and a
   backfill. They are additive, default-backed, and reversible
   (`rollback_003/004.sql`, both `IF EXISTS`-guarded). No existing column
   is altered or dropped.
2. **The sentinel UUID.** `00000000-0000-0000-0000-000000000001` is the
   single identity every existing row belongs to. Verified
   character-identical in 5 places: `user_context.SENTINEL_USER_ID`
   (`user_context.py:51`) and the SQL `DEFAULT`/backfill clauses in
   migrations 003, 004, 005. Code↔SQL drift is guarded by
   `tests/test_user_context.py`.
3. **The `user_context` resolver.** `get_current_user_id()` (env-driven,
   never None, never raises, sentinel + one-shot stderr warning when
   unset), a forward-shaped `UserProfile`, a 5-min cached
   `get_user_profile()`, `get_user_constant()` with a fail-loud
   resolution order, and `MODULE_LEVEL_INVARIANTS` holding the Red Lines
   as un-overridable module constants (not profile fields).

**Plain terms — what "dormant / byte-identical" means.** The plumbing
is laid but nothing flows through it for behaviour. Verified at HEAD:

- `get_user_constant()` has **zero real callers**. The only mentions
  outside `user_context.py`/tests are three *docstrings* in
  `open_tasks.py`. Every engine touchpoint still reads its own
  module-level constant; `_BUILTIN_DEFAULTS` is a read-only mirror, not
  a live source. So no number a user sees can move.
- `get_current_user_id()` has exactly two production consumers:
  `bot_core.py:42` (loads `DEFAULT_USER_ID` as a module constant beside
  `TOKEN`/`ADMIN_ID`) and `open_tasks.py` (stamps the resolved sentinel
  on every `open_tasks` write — lines 442, 556, 599). Neither threads
  `user_id` into any signature; the write boundary simply stamps the
  one sentinel.
- With `DEFAULT_USER_ID` unset, the resolver returns the sentinel —
  the exact value the SQL `DEFAULT` already wrote. So a deploy whose
  `.env` lacks the var runs **byte-identically** to today.

Net runtime delta of the entire foundation for the single existing
user: one extra `bot_core` constant, one sentinel stamp on task-lifecycle
rows, and (if the env var is unset) one stderr line at import. Zero
observable change to trading, risk, NAV, reports, or Telegram output.

## 2. Migration ledger

`migrations/verify_migrations.py` is the linear ledger. State at HEAD:

| Migration | Adds | Status |
|---|---|---|
| 001 | `trades` addon cols | applied (pre-existing) |
| 002 | `audit_log` table | applied (pre-existing) |
| 003 | `trades.user_id` | applied 2026-05-15 |
| 004 | `audit_log.user_id` | applied 2026-05-15 |
| 005 | `open_tasks` table (carries `user_id` sentinel, dedup key `(user_id, campaign_id, task_type)`) | applied 2026-05-15 (founder ran it; `null_user_id_rows = 0` confirmed) |

The ledger order is 001→005, contiguous. **No migration is pending.**
Every Phase-A-relevant table now carries the sentinel `user_id`. All
three Phase-A migrations have matching `IF EXISTS`-guarded rollbacks that
lose no pre-existing data (003/004 drop a default-backed column; 005
drops a wholly new table whose only contents are replayable
lifecycle deltas — the open set is always re-derived by `engine_core`).

## 3. What is explicitly deferred — and why

This is deliberate sequencing, not omission. The foundation is additive
precisely so the next phases are no-op swaps:

- **PR-A3+ (thread `user_id` through writes/reads).** Deferred because
  it is a behaviour-touching rollout across `supabase_repository`,
  `audit_logger`, `adaptive_risk_engine`, `telegram_*`,
  `ibkr_trade_importer`, `dashboard`. Phase A intentionally keeps it out
  so the foundation ships with **zero behaviour risk**. Today every
  write either stamps the single sentinel or relies on the SQL DEFAULT;
  reads are single-tenant so the `user_id` filter is moot.
- **Phase B (per-user profiles/config, DB-backed `get_user_profile`).**
  Deferred until there is a second user. The interface is already
  Phase-B-shaped: `_load_profile_from_backend()` is the only body that
  changes (Supabase table read); the public API does not. Scoped down by
  DEC-20260515-002 — exactly one `MethodologyProfile` value
  (`minervini_strict`); the 4-profile model waits for Sprint 13, full
  custom profile permanently rejected.
- **Phase C (per-request context, English/i18n).** Deferred to ~Q3 per
  DEC-20260515-003 (Israel/Hebrew-first launch). `language` defaults to
  `he`; per-request resolution (webhook/telegram_links) is a documented
  future swap of `get_current_user_id()`.
- **Per-user state split (PR-A5 — the `risk_monitor_state.json`
  touchpoint).** Deferred to Phase B. This file is per-host anti-spam
  dedup memory with no `user_id` and no risk/NAV math; in a multi-tenant
  world it becomes per-user. Pre-condition is the Research Issue N3
  atomic-write fix. No action required now.
- **Billing (Phase D).** Deferred per DEC-20260515-005: closed free
  beta, invited users, no public signup, beta testers get 1 year Pro
  free. No billing/quota/tier/paywall column or logic exists anywhere —
  every sprint addendum (10/12/13/14) re-confirms this. Correct: no
  billing should exist pre-beta.

## 4. Risk / watch-item from a scaling view

**One concrete watch-item (low severity, doc hygiene, not code):** the
Sprint 14 addendum asserts `risk_monitor_state.json` is git-tracked and
absent from `.gitignore`. At HEAD this is **stale** — the file is in
`.gitignore` (lines 11–12, with `state/risk_monitor_state.json`) and is
**not** git-tracked. The PR-A5 deferral logic is unaffected and still
correct, but the addendum's stated premise no longer matches the tree;
it should be footnoted so a future reader does not act on the wrong
assumption. No scaling defect found in the foundation itself: sentinel
literal is consistent everywhere, the ledger is linear and complete,
the resolver is genuinely dormant, and Red Lines are structurally
un-overridable. The only real-but-known structural debt is that PR-A3+
is a wide, multi-file rollout — that is expected and sequenced, not a
defect.

## 5. What unlocks the next phase

1. A **founder decision to onboard a second (beta) user** is the single
   trigger for PR-A3+ — until then threading `user_id` adds risk with
   zero benefit.
2. That decision turns on closed-beta recruitment (DEC-20260515-005);
   when the first invited tester is confirmed, PR-A3 (writes) → PR-A4
   (reads) → Phase B (`_load_profile_from_backend` → Supabase) proceed in
   order — the schema never changes again.
3. Phase C (English/i18n, per-request context) waits on the separate
   DEC-20260515-003 launch-geography decision (~Q3); it does not block
   the beta and rides on the Phase B infrastructure.
