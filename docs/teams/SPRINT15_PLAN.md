# Sprint 15 — Plan & Team-Leads Meeting (Report R-Integrity)

**Date:** 2026-05-15
**Branch:** `claude/review-system-audit-FBZ2h`
**Trigger:** Founder review of the weekly report across all 3 surfaces (Telegram / dashboard / AI-copy textbox).
**Structure:** Wave 1 (parallel, doc-only) → team-leads checkpoint → Wave 2 (build, decided non-ALGO items only) → consolidation.

## Founder findings (verified)

1. **R-type mixing (correctness defect, headline).** Report prints `RiskBasis: Target` but the OpenR for manual positions is computed off **original campaign risk** (`engine_core.compute_r_true`, :997), not target risk (`compute_r_target`, :1004). Both formulas already exist; the report mislabels + conflates. Live: MRVL 9.22R shown vs ~3.73R Account; PWR 1.34 vs 0.89; WCC 0.26 vs 0.11.
2. **Risk capital basis ambiguous** — $47.53 target risk is from NAV ($7,921), not Base Capital ($7,500 → $45.00). Not declared.
3. **NAV vs DB Net PnL gap** — Broker NAV +$421.08 vs DB Net PnL −$320.23 ≈ $741.31 gap, silent.
4. **ALGO open positions: poor data** — `State unknown`, `InitStop/CurrStop External/Unknown`, `Visibility 40/100`.
5. **Dead-money alert** must be strategy-adaptive / algo-aware (no smart follow-through).
6. **Founder-proposed rule:** ALGO Oversight Gate (5-condition exposure freeze).

## Classification

| Item | Status | DEC |
|---|---|---|
| Dual R: Structure R + Account R | **DECIDED** | DEC-20260515-011 |
| Risk Capital Basis declaration | **DECIDED** | DEC-20260515-012 |
| Broker Reconciliation Status | **DECIDED** | DEC-20260515-013 |
| ALGO Oversight Gate (5-cond) | **PROPOSED** — Mark evaluates Wave 1; founder confirms before build | — |
| ALGO position data quality (#4) | **BLOCKED** — pending founder's ALGO rules | — |
| Strategy-adaptive dead-money (#5) | **BLOCKED** — pending founder's ALGO rules | — |

Hard line: this touches R/NAV/campaign reporting → AGENTS.md/CLAUDE.md red line "no R/NAV/campaign math change without Mark + tests". DEC-011/012/013 are **surfacing + labelling + a derived status indicator using formulas that already exist** — NOT new math. Mark gates exact definitions; Wave 2 is test-gated.

## Wave 1 — task distribution (parallel, doc-only, distinct files)

- **🧠 Mark (lead — gates Wave 2):** `MARK_SPRINT15_RULINGS.md`
  - Exact definitions + label strings for **Structure R** (`compute_r_true`) vs **Account R** (`compute_r_target`); ALGO case (no real stop → Structure R = N/A, Account R only); confirm zero new math.
  - `Risk Capital Basis` exact wording + which basis the engine actually uses today (state it, don't change it).
  - `Broker Reconciliation Status` band thresholds (grounded, no invented numbers) + honest "cause unverified" wording (#1).
  - Methodology **evaluation of the founder-proposed ALGO Oversight Gate** (sound? thresholds? interplay with DEC-20260511-001 observer + #8) — a recommendation for the founder, NOT a build directive.
  - Rule the *framework* (not the ALGO logic) for #4/#5 so it can absorb the founder's forthcoming ALGO rules without rework.
  - 12-item pass/fail checklist + explicit "MUST NOT change any R/NAV/PnL number, only add the second metric + labels + status".
- **🏗️ Architecture + Engine:** `SPRINT15_DESIGN.md` — pinpoint where each of the 3 surfaces (`engine_core` report builder, `telegram_formatters`, `dashboard` incl. the AI-copy textbox) emits OpenR + `RiskBasis`; design the dual-R surfacing reusing `compute_r_true`/`compute_r_target` verbatim (no new math); the Risk-Capital-Basis label; the Broker-Reconciliation computation from existing Broker NAV + DB PnL (read-only, derived). ⟨MARK⟩ slots for all wording/thresholds. Wave-2 test plan incl. the MRVL/PWR/WCC numbers as regression fixtures + a "no existing R number changed" guard.
- **🚀 Hyperscaler:** `HYPERSCALER_SPRINT15_ADDENDUM.md` (short) — confirm no migration / no schema / no user_id; display-and-derive only; Phase-A byte-identical.
- **🛠️ System/Infra:** `REVIEW_SPRINT15_RECON_DATA.md` — verify the founder's hypothesis that the IBKR report pulls **YTD-only** (→ trades missing from DB explains part of the gap); document the data window + where Broker NAV vs DB PnL are sourced; no fix, just the grounded data-source truth Mark needs for DEC-013 bands.
- **📣 Marketing:** `MARKETING_SPRINT15_NOTE.md` (short) — confirm dual-R / recon are internal founder-facing only; reaffirm DEC-004 (no public numbers); note nothing here changes the public posture.

## Checkpoint
Parent verifies Mark kept it surfacing-only (no R/NAV/PnL number changes), the dual-R reuses the two existing functions, ALGO-blocked items stay blocked (no invented ALGO logic), and the ALGO Oversight Gate is presented as a proposal not a built rule.

## Out of scope / carried
ALGO data-quality + strategy-adaptive dead-money (blocked pending founder's ALGO rules). Live Sprint 11–14 founder smoke-test still outstanding. SYS-BL-01 disk hygiene. Hyperscaler PR-A3+.
