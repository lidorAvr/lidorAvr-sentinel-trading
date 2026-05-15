# Hyperscaler — Sprint 10 Addendum: `open_tasks` Phase-A Compatibility

**Date:** 2026-05-15
**Team:** Hyperscaler
**Scope:** The Sprint 10 "Open Tasks" engine + new `open_tasks` Supabase table.
**Governing:** `HYPERSCALER_PHASE_A_IMPL.md`, `user_context.py`, migration-003
pattern, DEC-20260515-002 (single profile), DEC-20260515-005 (no billing
before Phase D; invited users).
**Status:** Doc only. No code, no migration executed, no commit.

This addendum is binding on the Architecture team's migration draft. It does
not introduce new behaviour; it constrains Sprint 10 so Phase B (per-user) is
a pure no-op swap.

---

## 1. `open_tasks` column contract — migration-003 pattern, exactly

The migration MUST be `migrations/005_add_open_tasks.sql` with reverse DDL in
`migrations/rollback_005.sql`, mirroring 003's format (header comment,
`IF NOT EXISTS`, trailing verification SELECTs). It MUST be additive, default-
backed, reversible, and perform **no mutation of any existing table**.

`user_id` is the only Phase-A-relevant column and MUST be byte-identical to
the 003/004 contract:

```sql
user_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001'
```

Mandatory column contract the Architecture team must use:

| Column | Type / Constraint | Notes |
|---|---|---|
| `id` | `UUID PRIMARY KEY DEFAULT gen_random_uuid()` | Surrogate key. |
| `user_id` | `UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001'` | **Exact 003 literal.** Equals `user_context.SENTINEL_USER_ID`. No FK in Phase A. |
| `title` | `TEXT NOT NULL` | Task summary. |
| `status` | `TEXT NOT NULL DEFAULT 'open'` | e.g. `open` / `done` / `dismissed`. |
| `source` | `TEXT` (nullable) | Origin (engine/module). |
| `payload` | `JSONB NOT NULL DEFAULT '{}'::jsonb` | Free-form task detail. |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |
| `updated_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |

Required index (003 pattern):

```sql
CREATE INDEX IF NOT EXISTS idx_open_tasks_user_id ON open_tasks (user_id);
```

`rollback_005.sql` MUST be: `DROP INDEX IF EXISTS idx_open_tasks_user_id;`
then `DROP TABLE IF EXISTS open_tasks;` (whole table is new — dropping it is
fully safe, loses no pre-existing data). Add `005 → open_tasks →
["user_id"]` to `verify_migrations.py`, after `004`, keeping the ledger
linear.

Because every read/write filter will be `WHERE user_id = <id>`, Phase B only
swaps the value supplied by `user_context.get_current_user_id()` — the schema
never changes. This makes Phase B a no-op swap.

## 2. Single-user behaviour MUST be byte-identical

- `DEFAULT_USER_ID` env unset → `user_context.get_current_user_id()` returns
  the sentinel with its existing one-shot warning. The tasks engine MUST
  **reuse** `get_current_user_id()` — never re-implement, hard-code, or
  inline the sentinel literal in engine code (the literal lives only in SQL
  DEFAULT + `user_context.SENTINEL_USER_ID`, kept in sync by
  `tests/test_user_context.py`).
- The tasks engine MUST NOT thread `user_id` through call sites yet. That is
  PR-A3+ (writes) / PR-A4 (reads) territory and stays deferred. Phase A
  behaviour: the engine simply **stamps the resolved sentinel on every
  `open_tasks` write** (one call to `get_current_user_id()` at the write
  boundary), and either omits the `user_id` filter on reads (DEFAULT-backed,
  single tenant) or filters by the same sentinel. No new `user_id` parameters
  on engine signatures.
- No touchpoint reads `get_user_constant()` for task tunables in Sprint 10;
  the resolver stays dormant. Net runtime delta vs. today: one new table and
  one sentinel stamp — zero observable change for the existing single user.

## 3. Zero billing / quota implications (DEC-20260515-005)

The `open_tasks` engine introduces **no billing, payments, quota, rate-limit,
or tier logic**. No task counts, caps, or paywalls. Beta is free and closed;
all billing work is deferred to Phase D. The table MUST NOT carry any
tier/plan/quota column. Onboarding assumption remains invited users, no
public signup — the engine does not branch on user type.

## 4. Consolidation checklist — verify on the Architecture migration draft

The parent consolidation MUST confirm all 5 before accepting the draft:

1. **Sentinel literal exact:** `user_id` is
   `UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001'` —
   character-identical to migration 003 and `user_context.SENTINEL_USER_ID`.
2. **Additive + reversible:** new table only, no `ALTER`/`UPDATE`/`DROP` on
   any existing table; `rollback_005.sql` exists, is `IF EXISTS`-guarded,
   and loses no pre-existing data; `idx_open_tasks_user_id` present; ledger
   updated linearly (`005` after `004`).
3. **No DB mutation now:** migration authored, not executed; no read-only
   flow writes Supabase outside the new table.
4. **No user_id threading:** engine reuses `get_current_user_id()`, adds no
   `user_id` params to call sites, hard-codes no UUID — PR-A3+ stays
   deferred.
5. **No billing/quota + Red Lines intact:** no tier/quota/paywall column or
   logic (DEC-005); `MODULE_LEVEL_INVARIANTS` untouched; `telegram_bot.py`,
   `telegram_bot_secure_runner.py`, and R/NAV/exposure/campaign math
   unaffected.
