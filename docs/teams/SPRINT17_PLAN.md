# Sprint 17 — Plan & Team-Leads Meeting (ALGO Governance: fine-tune + unblock)

**Date:** 2026-05-16
**Branch:** `claude/review-system-audit-FBZ2h`
**Trigger:** Founder supplied the full real ALGO data review → `docs/teams/ALGO_REFERENCE_2026_05_16.md` (authoritative source of truth).
**Structure:** Wave 1 (parallel, doc-only) → team-leads checkpoint → Wave 2 (build) → consolidation.

## What the ALGO data unlocks (3 things)

1. **Fine-tunes DEC-20260515-014** (ALGO Oversight Gate): the founder's §6 Risk Governor is the concrete threshold set (decay / open-profit / cluster controls). Mark calibrates DEC-014's locked structure to these real numbers.
2. **Unblocks #4 (ALGO data quality):** §1 gives the real per-symbol stop/exit logic — "InitStop/CurrStop/State Unknown" must be replaced with each ALGO's known rules (QQQ/HOOD = no hard stop, time-exits are the control; TSLA −4.3%; JPM −3.3%; PLTR −25% emergency).
3. **Unblocks #5 (strategy-adaptive dead-money):** each ALGO's §1 time-exits ARE its "not working" signal — dead-money for an ALGO must be its own time-exit rule, not the generic discretionary DEAD_MONEY.

## Hard constraints (carry into the whole sprint)

- **AGENTS.md #8 — mandatory:** the ALGO cohort (PF/expectancy/win-rate, loss-streak, decay) is **isolated** and NEVER contaminates headline manual Win-Rate/Expectancy. The founder explicitly: "separating manual vs ALGO stats is mandatory".
- **DEC-20260511-001 — observer:** the Governor is **advisory** (withholds the *founder's* discretionary size-up/new-asset/exposure) — it NEVER instructs an ALGO, never alters an ALGO trade, emits at most `Review Required`, never `Action Required`.
- **No new R/NAV/campaign math** without Mark + tests. Reuse existing engine signals where the Governor overlaps them (Giveback alert, RUNNER state, profit checkpoints, loss-streak, the Day-3..16 work) — invent no new math; the backtest caveat (no fees/slippage/real capital) must be honored, never present backtest % as live truth (#1).
- The genuinely-new parts (ALGO-segregated rolling PF/expectancy cohort; Cluster Risk) need careful methodology + #8 isolation + tests.

## Wave 1 — task distribution (parallel, doc-only, distinct files)

- **🧠 Mark (lead — gates Wave 2):** `MARK_SPRINT17_RULINGS.md`
  - **Fine-tune DEC-014** against `ALGO_REFERENCE_2026_05_16.md §6`: lock the exact decay/open-profit/cluster thresholds, each anchored to a real datum or an existing engine constant (no invented numbers); reconcile with the already-shipped Day-3..16 signals (Giveback, RUNNER, profit checkpoints, loss-streak) so the Governor *reuses* them, not duplicates.
  - **#4 ruling:** the per-ALGO known-stop/exit data contract (from §1) — what the engine should display instead of "Unknown" per symbol; honest about "no hard stop → time-exit-controlled".
  - **#5 ruling:** strategy-adaptive ALGO dead-money = the ALGO's own §1 time-exit logic; define how it surfaces (Open Tasks / alert) without managing the ALGO and without #8 contamination.
  - The ALGO-segregated cohort definition (which trades, the window 20–30, PF/expectancy formula) with #8 isolation proof; backtest-caveat disclosure wording (#1).
  - 12-item pass/fail checklist + the explicit "ALGO cohort never enters headline stats" guard list.
- **🏗️ Architecture + Engine:** `SPRINT17_DESIGN.md`
  - Where ALGO stop/state is currently emitted as "Unknown" (`evaluate_position_engine` :446-467, the ALGO_OBSERVED path) and how to surface the §1 per-symbol known rules read-only.
  - Design the ALGO-segregated metrics module (rolling PF/expectancy/loss-streak over ALGO-only trades) **physically separate** from the headline analytics (prove #8 by construction — separate function, separate cohort, never merged); reuse `is_stat_countable`/the existing exclusion path.
  - The Governor as an advisory surface (Review Required) reusing existing Giveback/RUNNER/checkpoint/cluster signals; the Cluster-Risk computation from existing exposure data read-only.
  - ⟨MARK⟩ slots for every threshold/label. Wave-2 test plan incl. a #8-isolation guard (headline WR/Expectancy byte-identical with/without ALGO trades present) + the founder's real numbers as fixtures. Baseline 1676, drift green.
- **🚀 Hyperscaler:** `HYPERSCALER_SPRINT17_ADDENDUM.md` (≤90 words) — confirm no schema/migration/user_id; ALGO metrics are derived read-only; single-user byte-identical; per-user ALGO cohort = deferred Phase-B touchpoint only.
- **🛠️ System/Infra:** fold a short note into the Arch doc — no infra/deploy change expected; if any ALGO metric is persisted it reuses existing stores (no new volume/migration).

(No Marketing floor — internal risk-discipline control; DEC-004 already forbids any public ALGO numbers.)

## Checkpoint
Parent verifies: #8 isolation proven by construction (ALGO cohort physically separate; headline stats byte-identical); Governor is advisory/`Review Required` only (no ALGO instruction); thresholds trace to `ALGO_REFERENCE §6` / existing constants (none invented); backtest caveat surfaced honestly (#1); no new R/NAV/campaign math; reuses existing Day-3..16 signals not duplicates.

## Out of scope / carried
Live Sprint 11–16 founder smoke-test (still outstanding). Deploy Sprint 15/16. SYS-BL-01 disk hygiene. Hyperscaler PR-A3+. The exposure %s in §5 are the founder's allocation guidance — informational; the Governor gates *increase decisions*, it does not auto-allocate.
