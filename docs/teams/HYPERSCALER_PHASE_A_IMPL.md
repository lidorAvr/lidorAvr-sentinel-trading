# Hyperscaler — Phase A Implementation Report

**Date:** 2026-05-15
**Team:** Hyperscaler
**Spec:** `docs/teams/HYPERSCALER_PHASE_A_SPEC.md`
**Interface spec:** `docs/teams/USER_CONTEXT_INTERFACE_SPEC.md`
**Governing decisions:** DEC-20260515-002 (single `minervini_strict` profile;
Red Lines stay hard-coded constants), DEC-20260515-005 (invited users, no
public signup, no billing).
**Status:** PR-A1 + PR-A2 implemented. PR-A3..A6 deferred (out of Phase-A
scope for this work item). No git commit (parent session consolidates).

---

## 1. What was implemented vs the spec

### PR-A1 — migrations (spec §3, §8)

| Deliverable | File | Notes |
|---|---|---|
| `user_id` on `trades` | `migrations/003_add_user_id_to_trades.sql` | Exactly as spec §3. UUID, `NOT NULL`, `DEFAULT '00000000-0000-0000-0000-000000000001'`, `IF NOT EXISTS` (idempotent), backfill, `idx_trades_user_id`, two verification SELECTs. |
| `user_id` on `audit_log` | `migrations/004_add_user_id_to_audit_log.sql` | Exactly as spec §3. Same column spec, backfill, `idx_audit_log_user_id`, verification SELECT. |
| Reverse DDL | inline comment in 003/004 **and** standalone `migrations/rollback_003.sql`, `migrations/rollback_004.sql` | The standalone files exist because the spec rollback runbook (§7.4) references `migrations/rollback_004.sql` / `migrations/rollback_003.sql` by name. Both DROPs are `IF EXISTS` and safe (DEFAULT-backed column, no FK in Phase A). |
| Verify ledger | `migrations/verify_migrations.py` | `MIGRATIONS` list extended with `003`→`trades`→`["user_id"]` and `004`→`audit_log`→`["user_id"]`, exactly as spec §3 "Update to verify_migrations.py". Order `003` then `004` keeps the ledger linear. |

File naming/format matches the existing `001_addon_phase2.sql` /
`002_audit_log.sql` convention (header comment, `IF NOT EXISTS`, trailing
`-- Verify` SELECT against `information_schema.columns`).

**Migrations were authored only. None were executed against any database**
(per task constraint and spec §3: "No production code modified today" /
PR-A1 applies migrations only to a staging clone via the operator runbook).

### PR-A2 — `user_context.py` (spec §4.1; interface spec §2-§9), scoped to DEC-20260515-002

| Surface | Implemented | Scope decision |
|---|---|---|
| `SENTINEL_USER_ID` | `"00000000-0000-0000-0000-000000000001"` constant | Used in exactly 2 places: `get_current_user_id()` fallback + asserted equal to the migration `DEFAULT` literal by a drift test. |
| `get_current_user_id()` | Reads `DEFAULT_USER_ID` env (stripped); falls back to sentinel with a **single one-shot stderr warning**; never None, never raises | Exactly spec §4.1. |
| `MethodologyProfile` enum | **Exactly one value: `MINERVINI_STRICT`** | DEC-20260515-002 — the 4-profile model is deferred to Sprint 13; full custom profile permanently rejected. The other interface-spec enums (`CapitalTier`, `RiskTolerance`, etc.) are included as the forward-compatible dataclass shape, all defaulting to Mark's current identity. |
| `UserProfile` (frozen dataclass) | Implemented with Mark's current production values as field defaults; `constants={}` always in Phase A | Per interface spec §3. `methodology_profile` is system-set (single value). |
| `MODULE_LEVEL_INVARIANTS` | `mix_algo_into_wr=False`, `admin_only_telegram=True`, `data_incomplete_in_stats=False`, `secure_runner_required=True`, `fallback_data_as_truth=False` | **MODULE-LEVEL constants, NOT `UserProfile` fields, NOT in `_BUILTIN_DEFAULTS`, NOT user-overridable, ignore `user_id`.** Enforced first in `get_user_constant()` so no profile or typo can shadow them. Mark directive #1 / DEC-20260515-002. |
| `_BUILTIN_DEFAULTS` | 44 keys mirroring the current production constants **exactly**, each with a `file:line` citation comment verified at HEAD | All citations re-checked against source (risk_monitor.py 40-52, adaptive_risk_engine.py 20/27-29/33, report_scheduler.py 15/35-40, engine_core.py 13/15/16/236-238/1887-1890, addon_risk_engine.py 15-21, telegram_menus.py 8/14-16, telegram_formatters.py 58). |
| `get_user_constant(name, user_id=None)` | Resolution: invariant → profile.constants → `_BUILTIN_DEFAULTS` → **`raise KeyError`** (fail-loud, never silent None). Mutable values deep-copied. | Interface spec §4. |
| `get_user_profile`, caching | Process-local dict, 5-min TTL, `threading.RLock`, `invalidate_user_cache()` | Interface spec §9. Phase A backend always returns `_DEFAULT_PROFILE`. |
| `effective_profile_dump()` | Debug helper returning resolved profile + invariants + all constants (copy-safe) | Interface spec §2 / open question Q3. |

### Wiring — `bot_core.py` (spec §4.2)

Three additive lines appended **after** the existing `RTL` line, alongside the
existing `TOKEN` / `ADMIN_ID` loading:

```python
from user_context import get_current_user_id  # noqa: E402
DEFAULT_USER_ID = get_current_user_id()
```

`DEFAULT_USER_ID` is now a `bot_core` module constant beside `TOKEN`/`ADMIN_ID`.
Existing imports of `bot_core` are unaffected. **Unset `DEFAULT_USER_ID` does
not crash** — it logs the one-shot warning and falls back to the sentinel, so
production deploys whose `.env` lacks the var still run byte-identically.

---

## 2. What is deferred (NOT in this work item)

Per spec §8, the following are explicitly out of scope here and were **not**
implemented (no behaviour-threading of `user_id` through call sites yet):

- **PR-A3** — thread `user_id` through `supabase_repository.py` *writes* +
  `audit_logger.log_action` `user_id` param + caller updates
  (`adaptive_risk_engine`, `telegram_devops`, `telegram_bot`,
  `telegram_callbacks`, `ibkr_trade_importer`, `dashboard`).
- **PR-A4** — thread `user_id` through `supabase_repository.py` *reads* +
  direct table reads in `risk_monitor`/`report_scheduler`/`dashboard`/
  `bot_health`/`telegram_callbacks` + optional `user_id` on
  `analytics_engine.compute_period_analytics` /
  `adaptive_risk_engine.compute_adaptive_risk_recommendation` +
  `risk_monitor._run_one_cycle_dry` helper.
- **PR-A5** — state-file readers/writers (deferred to Phase B per spec §5;
  pre-condition: Research Issue N3 atomic-write fix).
- **PR-A6** — signature cleanup (Phase B polish).
- `scripts/phase_a_smoke_compare.py` and `tests/snapshots/*_baseline.*` —
  these are PR-A1's CI/operator artefacts that require a production-equivalent
  Supabase to capture; not authored here (no DB access; out of scope for the
  additive code foundation). The in-repo equivalent of Mark directive #2 is
  delivered as the unit smoke test below.
- The 10 touchpoint migrations to `get_user_constant()` (PR-B1..B10) — a
  separate behaviour-preserving rollout. Phase A leaves every touchpoint
  reading its own module-level constant; `user_context` is a leaf with no
  callers except `bot_core` loading `DEFAULT_USER_ID`.

**Consequence:** because no call site threads `user_id` yet and no touchpoint
reads `get_user_constant()`, the resolver is dormant in production. The only
runtime effect of Phase A code is one extra module constant in `bot_core`
(`DEFAULT_USER_ID`) and, if `DEFAULT_USER_ID` is unset, one stderr warning at
import. Zero observable behaviour change for the existing user.

---

## 3. The single-user smoke test (Mark directive #2)

`tests/test_user_context.py` contains the in-repo realisation of Mark's
directive #2 ("if any number moves, the migration is rejected"):

- **`test_single_user_smoke_constants_equal_production`** (parametrised over
  all 44 constants): with **no `DEFAULT_USER_ID` set**, asserts every value
  returned by `get_user_constant(name)` equals the current hard-coded
  production value, restated independently in `_EXPECTED_PROD_CONSTANTS`.
  This proves that when the touchpoints are later wired (PR-B1..B10) the
  existing single user resolves byte-identical numbers.
- **`test_builtin_defaults_has_no_extra_keys`** — `_BUILTIN_DEFAULTS` is
  exactly the documented production set (no stray keys a touchpoint could
  later read with a drifted value).
- **`test_sentinel_matches_migration_default`** — regex-extracts the SQL
  `DEFAULT` UUID from migrations 003 **and** 004 and asserts both equal
  `SENTINEL_USER_ID`. Guards code↔SQL drift.
- **`test_returns_sentinel_when_unset` / `_when_blank` / `test_warns_once`** —
  the unset path is byte-identical to the sentinel and warns exactly once.
- **`test_unknown_constant_raises_keyerror_not_none` /
  `test_typo_does_not_silently_return_none`** — fail-loud on unknown name.
- **`test_invariants_cannot_be_overridden_by_profile_constants` /
  `_ignore_user_id` / `_not_in_user_profile_fields` /
  `_not_in_builtin_defaults`** — Red Lines unshadowable, not profile fields.
- **`test_methodology_profile_has_exactly_one_value`** — enforces
  DEC-20260515-002 (`["minervini_strict"]` only).

70 tests, all green in isolation (`pytest tests/test_user_context.py` →
`70 passed`).

---

## 4. Test results & zero-behaviour-change confirmation

| Run | Result |
|---|---|
| `tests/test_user_context.py` in isolation | **70 passed** |
| Full suite, **without** any Phase A change (clean worktree) | 1359 passed, **16 failed** |
| Full suite, **with** Phase A | 1435 passed, 10 failed (failure set non-deterministic: 10–12) |
| Full suite **with** Phase A, excluding the two pre-existing broken parallel-team files | **1424 passed, 0 failed** |

**Pre-existing breakage (NOT caused by Phase A):** the worktree already
contained uncommitted parallel-team work — modified `telegram_bot.py`,
`telegram_callbacks.py`, `telegram_menus.py` and new
`telegram_stop_promote.py` + `tests/test_telegram_callbacks_promote.py` +
`tests/test_telegram_stop_promote.py`. Those files fail under full-suite
collection-order pollution **before any Phase A file exists** (proven by
stashing all Phase A changes and re-running: still 16 failures). In isolation
`test_telegram_stop_promote.py` passes 15/15. None of the failures are in a
Phase-A file.

**Conclusion:** Phase A introduces **zero new failures**. With the
pre-existing broken parallel-team files excluded, the suite is fully green
(1424/1424). The 1424 = the project's prior logic tests + the 70 new
`test_user_context.py` tests. Behaviour for the existing single user is
byte-identical: no call site threads `user_id`, no touchpoint reads the
resolver, and `DEFAULT_USER_ID` unset is byte-identical to the sentinel.

---

## 5. Rollback

| Artefact | Rollback | Risk |
|---|---|---|
| `migrations/003` (if ever applied) | `migrations/rollback_003.sql` (`DROP INDEX idx_trades_user_id; ALTER TABLE trades DROP COLUMN user_id;`) | Safe — DEFAULT-backed column, no FK, index drop is free. Re-applying 003 re-backfills. |
| `migrations/004` (if ever applied) | `migrations/rollback_004.sql` | Same reasoning. |
| `user_context.py` + `tests/test_user_context.py` | Delete the two files. Leaf module — no production callers except the `bot_core` import. | Trivial. |
| `bot_core.py` 3-line addition | Remove the `from user_context import …` + `DEFAULT_USER_ID = …` lines. No other module references `bot_core.DEFAULT_USER_ID` in Phase A. | Trivial — additive only. |
| `migrations/verify_migrations.py` | Revert the 2 new `MIGRATIONS` tuples. Operator script only; no runtime impact. | Trivial. |

No database was mutated by this work item; no DB rollback is required unless
an operator later applies 003/004.

---

## 6. Red Lines / hard constraints honoured

- `telegram_bot_secure_runner.py` — untouched.
- `engine_core.is_stat_countable()` — untouched (no `user_id`/profile param).
- `RISK_LADDER`, `_TRAIL_*`, `DRAWDOWN_*`, `ALGO_*` constants — untouched
  (mirrored read-only into `_BUILTIN_DEFAULTS`; the live code still owns
  them; touchpoint rewiring is deferred to PR-B*).
- No R / NAV / exposure / campaign math changed.
- No Supabase mutation from any flow (migrations authored, not run).
- `telegram_bot.py` not rewritten (not touched by Phase A at all).
- No secrets committed. `DEFAULT_USER_ID` is a UUID, not a secret; loaded
  from env consistent with `TELEGRAM_BOT_TOKEN`.
- Red Lines (`mix_algo_into_wr` etc.) are module-level constants, never
  profile fields — enforced and tested.
