# Sprint 10 — Team Meeting (Consolidation)

**Date:** 2026-05-15
**Branch:** `claude/review-system-audit-FBZ2h`
**Feature:** Open Tasks (Action-Items) engine — the founder's real "open tasks" intent (per-position Minervini-driven action items with done/skip/notes), NOT the journal walker.
**Structure:** Wave 1 = 5 parallel design/research teams → checkpoint → Wave 2 = 1 coherent build → consolidation.
**Suite:** 1466 → **1523 passed, 0 failed** (+57; the 1 warning is the pre-existing unrelated analytics dateutil warning).

---

## What shipped

| Wave | Commit | Deliverable |
|---|---|---|
| 1 | `8c5834f` | Hyperscaler Sprint-10 addendum (open_tasks table Phase-A contract) |
| 1 | `4b14d47` | Mark methodology spec — **zero new numeric thresholds** |
| 1 | `d132467` | Marketing Sprint-10 week-1 closed-beta execution |
| 1 | `573152b` | Architecture engine design + migration 005 DRAFT |
| 1 | `9829e87` | UX Telegram design |
| 2 | `56293c7` | **Open Tasks engine + Telegram UX implemented** (+57 tests) |

---

## Checkpoint result (between waves) — PASS with one adjustment

- ✅ Methodology grounded: Mark rejected the founder's example thresholds ("1R→breakeven", "3R→lock avg") and mapped every task onto the *existing* engine state machine (`compute_position_state()` engine_core.py:1963, 10 states) → **zero new numeric thresholds shipped**. The engine is a pure read-only surface.
- ✅ Migration 005 matches Hyperscaler's contract (exact sentinel literal, additive new-table, reversible, `UNIQUE(user_id,campaign_id,task_type)`).
- ⚠️ **Adjustment applied in Wave 2:** the Wave-1 design's `load_ruleset()` *parsing Mark's `.md` at runtime* was rejected as fragile. Wave 2 implemented `_RULESET` as a **typed Python constant** (transcribed verbatim from Mark's spec §6, one `# spec:` cite each); `OPEN_TASKS_METHODOLOGY_SPEC.md §6` is the **audit source**, the constant is the **runtime source**, and a **drift test** (`test_ruleset_matches_methodology_spec`) fails CI if they diverge — so Mark stays the methodology owner and production is robust.

## Mark's 9 guardrails — parent-verified (independent code review, not just agent self-report)

| # | Guardrail | Verified |
|---|---|---|
| G1 | Read-only over engine math (no new R/NAV/campaign) | ✅ `derive_tasks` consumes caller `state_result`; imports `engine_core` for `POSITION_STATE_*` constants only; calls **no** engine function; snapshot is a copy |
| G2 | ALGO → info-only, never an action | ✅ `ALGO_OBSERVE_ONLY` info_only=True, no stop/exit text |
| G3 | DATA_INCOMPLETE → no numeric task, never counted | ✅ urgency=None, info_only=True (invariant #8) |
| G4 | No task instructs a stop loosen | ✅ RUNNER embeds engine's own `compute_suggested_trail_stop` verbatim; never computes a stop; text "אל תרופף"; honest fallback (no fabricated number) |
| G5 | No new push / no double-notify | ✅ pull-only; every `send_message` is user-action-triggered; invariant #7 untouched |
| G6 | Writes isolated to `open_tasks` | ✅ never touches `trades`/`management_state`/`risk_monitor_state.json`; fail-open audit |
| G7 | Reuse existing P0–P3 tiers | ✅ display mapping only |
| G8 | P0 BROKEN skip never silent | ✅ typed-reason mandatory in UX; `skip_task` audits `skipped_critical_exit` |
| G9 | Admin-only entry | ✅ unchanged — enforced by `telegram_bot_secure_runner.py` (untouched) |

Import discipline (leaf) verified: `open_tasks.py` imports only stdlib + `engine_core` + `user_context` + `audit_logger`; no `telegram_*`/`bot_core`/`risk_monitor`. Wiring is additive only — no `telegram_bot.py` wholesale rewrite.

---

## ⚠️ Deployment step required (founder action)

The feature is **dormant until the `open_tasks` table exists**. `migrations/005_create_open_tasks.sql` is a DRAFT — **not executed** (no DB access from this session).

- **Task derivation/list works without the table** (engine-derived; read-only).
- **done / skip / notes persistence requires the table.** Until migration 005 is run, those lifecycle writes fail *open* (no crash, no data corruption) — the list still renders, but a "done"/"skip"/note will not persist.
- **To activate:** run `migrations/005_create_open_tasks.sql` in Supabase → SQL Editor (it is `CREATE TABLE IF NOT EXISTS`, additive, reversible via `rollback_005.sql`). Then redeploy the telegram-bot service.

No `docker-compose.yml` change. No secure-runner change. Rollback: `git revert 56293c7` + `rollback_005.sql` (safe — table not yet in prod).

---

## Deferred (documented, none guardrail-blocked)
- **T7 drawdown-ack task** — portfolio-level, outside the per-position `derive_tasks` contract; needs its own design (Sprint 11).
- **UX live count badge** on the `📊 מצב תיק` prompt — would touch a shared `telegram_bot.py` prompt string; kept the change minimal.
- **Pagination / "show done" view** — list sugar; current list paginates >8 rows.

## Recommended next (Sprint 11 candidates)
1. Founder runs migration 005 + redeploy → smoke-test the lifecycle end-to-end on the Pi.
2. T7 drawdown-acknowledgement task design.
3. Pre-existing items still open from Day 3: `/clean` confirmation gate; price-fallback labelling.
4. Hyperscaler PR-A3+ (thread `user_id` through writes) — only when moving past single-user.

## Process note
As on Day 3, worktree isolation for the Wave-2 build agent did not take effect (it wrote to the shared main tree). Mitigated identically: parent independently verified the work, ran the full suite, and committed by explicit file names (never `git add -A`); `.claude/` stays gitignored. No partial/foreign work captured.
