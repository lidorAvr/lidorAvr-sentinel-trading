# Open Tasks (Action-Items) — Sprint-10 Wave-2 Implementation

**Sprint:** 10 — Wave 2 (build)
**Status:** IMPLEMENTED. Worktree left dirty for parent consolidation
(no git commit/push; migrations NOT executed; full suite green).
**Date:** 2026-05-15

This documents what was built vs the locked Wave-1 design, the one approved
checkpoint adjustment, the 9-guardrail self-verification, the test delta, what
was deferred and why, and the rollback note.

---

## 1. What was implemented vs the design

| Design item | Built? | Notes |
|---|---|---|
| `open_tasks.py` leaf — `Task`/`TriggerSnapshot` dataclasses | ✅ | `Task` adds `info_only` (needed to enforce G2/G3 at render). `TriggerSnapshot` carries `state/open_r/age_days/reason` — all **copied**, never recomputed. |
| `_RULESET` typed constant + `load_ruleset()` | ✅ | **Checkpoint adjustment** (see §2) — constant instead of runtime `.md` parse. `load_ruleset()` kept as the public seam (Phase B can swap). |
| `ruleset_for_state()` fail-loud | ✅ | Unknown state → `RulesetUnavailable` (never silent `None`/`[]`), mirroring `user_context.get_user_constant` raising `KeyError`. Known no-task states (NEW/PROVING/WORKING) return `[]` (explicit Mark ruling, not a typo). |
| pure `derive_tasks(positions, *, now, ruleset=None)` | ✅ | Consumes caller-supplied `state_result` per design §1.4 — **does not call the engine**. Zero R/NAV/campaign math. `trigger_snapshot` is a copy. Referentially transparent (frozen `now`). |
| Lifecycle `list_tasks/mark_done/skip_task/add_note` | ✅ | DI `sb` first arg; `user_id` defaults to `user_context.get_current_user_id()`; audit via `audit_logger.log_action(... ACTION_SETTINGS_CHANGE ...)` fail-open; notes append-not-replace; writes ONLY `open_tasks`. |
| `telegram_tasks.py` — full UX | ✅ | Mirrors `telegram_stop_promote.py`. Entry, grouped/sorted tap-only keyboard, detail card, ✅/⏭️/📝 handlers, P0-skip-typed-reason gate (reuses `risk_reject_reason` pattern), defaulted-safe confirm (mirrors `loosen_confirm`), honest stale/error labels. Pull-only — no new push. |
| Wiring (additive only) | ✅ | Re-export block in `telegram_bot.py` (mirrors lines 37-39); `📋 משימות פתוחות`/`/tasks` text+command handler; `/tasks` in help; menu button in `get_portfolio_menu()`; `task_*` callback routing in `telegram_callbacks.py`; P0-skip-reason + add-note free-text branches next to `risk_reject_reason`. |
| `verify_migrations.py` 005 ledger entry | ✅ | Linear, after `004`, exactly per ENGINE_DESIGN §2.4. Migrations NOT executed. |
| Tests | ✅ | `tests/test_open_tasks.py` (design §4 cases 1–11 + drift + ledger + sentinel-literal); `tests/test_telegram_tasks.py` (keyboard/grouping/sort/callbacks/P0-gate/ALGO/edge). |

### Schema target note
The build targets the **authored** `migrations/005_create_open_tasks.sql`
(BIGSERIAL PK, lifecycle-deltas-only — matches ENGINE_DESIGN §2.2). The
HYPERSCALER addendum sketched a different illustrative shape (`title`/`payload`
columns, `005_add_open_tasks.sql` name); per the task instruction the authored
migration is the schema of record and was **not modified** (no real bug). The
only HYPERSCALER-binding constraints — exact sentinel literal, additive +
reversible, linear ledger, no `user_id` threading, no billing column — are all
satisfied and asserted by `test_migration_005_sentinel_literal_exact` /
`test_verify_migrations_lists_005`.

---

## 2. Checkpoint adjustment as built

**Design rejected:** `load_ruleset()` parsing Mark's `.md` at runtime (fragile).

**Built instead:**
- `open_tasks._RULESET: dict[str, list[RuleEntry]]` — a typed Python constant,
  values transcribed **verbatim** from `OPEN_TASKS_METHODOLOGY_SPEC.md` §1/§2,
  each entry annotated with a `# spec:` comment citing the exact Mark row.
- `load_ruleset()` returns a deep copy of this constant (still the public seam
  — Phase B can swap the body). Fail-loud preserved.
- A **machine-readable block** was appended to
  `OPEN_TASKS_METHODOLOGY_SPEC.md` as a new **§6** (additive — Mark stays the
  owner; the `.md` is the **audit source of truth**, the constant is the
  **runtime source**).
- `tests/test_open_tasks.py::test_ruleset_matches_methodology_spec` re-reads
  the fenced `yaml` block in §6 and asserts `_RULESET` matches it exactly
  (task_type / urgency / info_only / Hebrew action), so any future divergence
  between Mark's ruling and the code **fails CI loudly**.

---

## 3. Mark's 9-guardrail self-verification

| # | Guardrail | Result | Evidence |
|---|---|---|---|
| G1 | Read-only over engine math | ✅ PASS | `derive_tasks` receives `state_result` (design §1.4) — `grep` of `open_tasks.py` shows zero `compute_position_state`/`compute_r_true`/`original_campaign_risk` *calls* (only docstrings). `test_derive_tasks_calls_no_engine_function` wraps every `engine_core` callable and asserts none fire. Zero numeric trading thresholds in the module. |
| G2 | ALGO → info-only, never action | ✅ PASS | `_RULESET[ALGO_OBSERVED]` = `ALGO_OBSERVE_ONLY`, `info_only=True`, P3. `test_algo_info_only_no_action_verb` asserts no סגור/צמצם/הדק/צא verb. UX renders it as a non-tappable `task_algo_noop` row. |
| G3 | DATA_INCOMPLETE → no numeric task, never counted | ✅ PASS | `_RULESET[DATA_INCOMPLETE]` = `COMPLETE_RISK_DATA`, `urgency=None`, `info_only=True`. `test_data_incomplete_info_only_no_urgency` + `test_data_incomplete_never_p0_p2`. |
| G4 | No task instructs a stop LOOSEN | ✅ PASS | RUNNER action embeds the engine's **own** `compute_suggested_trail_stop()` output verbatim (`{basis}/{stop}` from caller-supplied `trail_stop`); module never computes a stop. Missing detail → honest fallback, never a fabricated number. Text contains "אל תרופף". `test_runner_embeds_engine_trail_verbatim` + `test_runner_missing_trail_is_honest_not_fabricated`. |
| G5 | No double-notify / no new push | ✅ PASS | `telegram_tasks.py` is entered only by the user (button/`/tasks`/callbacks) — pull-only. No `send_telegram` timer, no `risk_monitor` change, anti-spam state machine untouched. |
| G6 | Read-only over Supabase; writes isolated | ✅ PASS | `grep .table(` in `open_tasks.py` → only `_TASKS_TABLE` (`open_tasks`). `test_lifecycle_never_touches_trades_table` asserts `trades`/`management_state` never touched. Derivation issues SELECTs only. |
| G7 | Reuse P0–P3; no new severity scale | ✅ PASS | `urgency` values are exactly `P0/P1/P2/P3` (or `None` for DATA_INCOMPLETE) transcribed from `ALERT_PRIORITY`. UX bands are display-only labels over the same tier (Mark K4). |
| G8 | P0 exits never silently auto-closed/skipped | ✅ PASS | `list_tasks` never mutates engine state; a P0 only drops off when the engine genuinely stops emitting BROKEN (not laundered by a bounce — it simply isn't re-derived; spec §3/K5). A P0 skip routes through the typed-reason gate in UX and is audited as `skipped_critical_exit` in `skip_task` (`test_p0_skip_audited_as_skipped_critical_exit`, `test_p0_skip_empty_reason_reprompts_does_not_skip`). |
| G9 | Admin-only; no bypass of secure runner | ✅ PASS | Entry is only via the existing admin-gated Telegram message/callback handlers (same gate as `/promote`). No new unauthenticated entry point; `telegram_bot_secure_runner.py` untouched; `telegram_bot.py` not rewritten (additive re-export + 1 routing block + 1 help line + 2 free-text branches). |

---

## 4. Test count before/after

- **Before (branch baseline):** `1466 passed`.
- **After:** `1523 passed, 1 warning` (the pre-existing unrelated
  `analytics_engine.py` dateutil warning).
- **Delta:** **+57** new tests, zero regressions:
  - `tests/test_open_tasks.py` — 38 (design §4 cases 1–11 across parametrized
    states, dedup/supersede, auto-close, lifecycle, no-engine-mutation,
    purity, fail-loud, user_id default, audit fail-open, the **drift test**,
    ledger-linearity, sentinel-literal).
  - `tests/test_telegram_tasks.py` — 19 (keyboard build, grouping/sort order,
    done/skip/note callbacks, P0-skip-reason gate incl. empty-reason
    re-prompt, ALGO info-only, edge/empty/infra-error states).

---

## 5. Deferred items (and why)

1. **T7 — drawdown risk-cut acknowledgment.** Mark's spec §1 T7 is
   **portfolio-level** (`adaptive_risk_engine` 30-day-PnL drawdown), not a
   per-position `compute_position_state()` output. The locked engine design's
   `derive_tasks(positions, …)` contract is strictly position-state-driven and
   must NOT call the engine (G1). Wiring a portfolio-level signal would require
   a new caller-supplied channel not specified in the position-state contract;
   inventing one risked an out-of-scope portfolio-math path. **Deferred** and
   documented in `OPEN_TASKS_METHODOLOGY_SPEC.md` §6 (no `_RULESET` row). It is
   a clean follow-up: add a `portfolio_signals` argument to `derive_tasks` and
   a `T7` rule entry, with the caller passing the existing
   `adaptive_risk_engine` drawdown result (still zero new math). No guardrail
   blocks it; it is purely additive.
2. **Count badge on the `📊 מצב תיק` prompt (UX §1c).** The UX doc proposes
   appending a live `📋 משימות פתוחות: 🛑1 ⚠️3` line to the existing portfolio
   prompt. This touches a shared `telegram_bot.py` prompt line and adds a
   second cheap engine read on every portfolio-menu open; it is **deferred** to
   keep the `telegram_bot.py` change strictly minimal/additive (re-export +
   routing only) per the no-wholesale-rewrite constraint. The feature is fully
   reachable via the menu button and `/tasks`; the badge is a pure
   discoverability nicety, safe to add later as its own small item.
3. **Pagination / "show done" toggle (UX §2 notes, §5).** Implemented the
   core list/detail/lifecycle; pagination (`task_page|n`) and the read-only
   done/skipped view (`task_show_done`) are non-essential view sugar and were
   left as documented follow-ups to keep Wave-2 scoped to the lifecycle-
   critical path. No guardrail interaction.

---

## 6. Rollback note

All changes are additive and reversible.

- **Code:** revert the worktree (new files `open_tasks.py`,
  `telegram_tasks.py`, `tests/test_open_tasks.py`,
  `tests/test_telegram_tasks.py`; additive edits to `telegram_bot.py`,
  `telegram_callbacks.py`, `telegram_menus.py`,
  `migrations/verify_migrations.py`, `docs/teams/OPEN_TASKS_METHODOLOGY_SPEC.md`
  §6). No existing function signature, message, or number changed → reverting
  restores byte-identical prior behaviour.
- **Database:** the migration was **not executed**. If later applied, roll back
  with `migrations/rollback_005.sql` (`DROP INDEX … ; DROP TABLE IF EXISTS
  open_tasks;`) — the table is brand-new with no FKs, so dropping it loses only
  stored done/skip/note lifecycle deltas; every *open* task is re-derived from
  the engine on next render (the table cannot drift the engine).
- **Runtime safety:** the surface is dormant until a user opens the menu/
  `/tasks` (pull-only). If `open_tasks` does not exist yet, lifecycle reads
  fail-soft (`_read_lifecycle` returns `{}` → tasks shown as open) and
  writes fail-soft (logged to stderr, user sees "שמירה נכשלה"); nothing
  crashes, no other service is affected.
