# Sprint 19 — Plan & Team-Leads Meeting: Period-Honest Headline + Period-over-Period Context + System-Health #1 Fix

**Date:** 2026-05-16 · **Branch:** `claude/review-system-audit-FBZ2h`
**Trigger:** Founder smoke-test of deployed Sprint-18 (`f43a94c`) → DEC-20260516-016.
**Structure:** Wave 1 (parallel, doc-only) → checkpoint → Wave 2 (build) → consolidation.

## What Sprint-18 already delivered (verified live, do NOT regress)

Open book renders in weekly/monthly; period-scoped (opened-in-period / held-from-before / opened-after-window EXCLUDED); ALGO-segregated & observation-only; honest empty-state LINE; `analytics_engine.py` untouched; 920be95/bcf32f5/Sprint-16 intact; 1761 green.

## The 3 remaining issues (DEC-20260516-016)

1. **Headline still reads "0 / ללא עסקאות".** The big `verdict-badge` + all-zero KPI cards dominate while a live book (+$72 wk / +$224 mo, 33–34% exposure, 4 opened-in-period) spanned the period. The Sprint-18 honest-line is buried under the misleading badge.
2. **No period-over-period / vs-average.** "vs previous" omitted on-demand & only scheduled-with-prior-snapshot; no "vs average" anywhere; open book has no cross-period view.
3. **System-Health #1 bug (RCA complete).** `ibkr_sync_runner.py:16` `IBKR_ERROR_CLASSES[1001]=("temporary","הדוח לא נוצר כרגע — ניסיון מאוחר יותר")` (IBKR flex-query status) is rendered by `report_scheduler._build_system_health:170-184` as `✅ Sync temporary — הדוח לא נוצר כרגע …` inside a delivered Sentinel report → reads as "the [Sentinel] report wasn't created" + `✅` on a non-ok state. Sibling: monthly PDF header "1–29 באפריל" (April=30) — suspected `report_renderer._period_label:422` off-by-one.

## What Sprint 19 delivers

1. **Period-honest headline** (presentation only): when 0 closed + active book spanned the period, the dominant message reflects the OPEN-BOOK period performance (floating PnL / exposure / # opened-in-period / mark-to-market Δ once baseline) clearly separated from realized; realized cards stay byte-identical, reframed as "0 ממומש", NOT the headline verdict. NO `compute_verdict`/realized-math/#8/920be95 change.
2. **Period-over-period + vs-average** for realized (existing `load_recent` snapshot history) AND the open book (Sprint-18 `open_marks` history). Honest baseline-pending until ≥N priors (#1 — never a fabricated average). On-demand READ-ONLY (no snap_save).
3. **System-Health #1 fix**: `_build_system_health` maps sync status honestly — no `✅` on `temporary`; never surface the IBKR-flex "הדוח לא נוצר" string where it reads as the Sentinel report. Fix `_period_label` "1–29" off-by-one.

## Hard constraints (carry the whole sprint)

- `analytics_engine.py` realized path byte-identical (guard); `compute_verdict` 920be95 signature, bcf32f5, Sprint-16 graceful, Sprint-18 period-scoping ALL preserved (regression-tested).
- Realized vs unrealized strictly separated; ALGO #8-segregated & observation-only (DEC-20260511-001) in EVERY new comparison/average too — never in headline/realized.
- #1: explicit baseline-pending until enough history; never present sync-temporary as `✅`/"report not created"; never a fabricated average.
- On-demand NO snap_save; comparison/average READ-ONLY from existing per-host snapshot history (Hyperscaler: no migration, single-user byte-identical).
- No wholesale renderer rewrite; presentation-layer + additive ctx; reuse `compute_period_comparison` + `load_recent` + Sprint-18 `open_marks` + `report_open_book`.

## Wave 1 — task distribution (parallel, doc-only, distinct files)

- **🧠 Mark (lead — gates Wave 2):** `MARK_SPRINT19_RULINGS.md`
  - Rule the EXACT period-honest headline: what the verdict badge + page-1 must say when 0 closed + live book (Hebrew, RTL, #1) so it never visually reads "no trading"; the precise boundary that realized KPI cards remain byte-identical but are demoted from the headline; open-book period performance promoted — without contaminating realized or violating #8 (ALGO never in headline).
  - Rule the comparison/average semantics: which metrics get "מול תקופה קודמת" / "מול ממוצע" (realized AND open-book), the minimum-history N before an average is shown, the exact baseline-pending Hebrew until then (#1 — no fabricated average), and that ALGO stays segregated in every comparison.
  - Rule the System-Health honest mapping: exact Hebrew for ok / temporary / unknown sync states (no `✅` on temporary; never the IBKR-flex "הדוח לא נוצר" verbatim); rule the `_period_label` correct inclusive end ("1–30 באפריל").
  - 12-item pass/fail checklist incl. realized-byte-identical guard + "no `ללא עסקאות`/`✅ temporary`/fabricated-average" honesty asserts.
- **🏗️ Architecture + Engine:** `SPRINT19_DESIGN.md`
  - Presentation-layer headline switch in `report_renderer` (ctx/templates) keyed off the Sprint-18 `open_book_present` + `campaigns_closed==0` — verdict badge + page-1 reframed; `compute_verdict` realized logic, 920be95 signature, `_base_ctx` realized keys NOT touched (additive ctx only; realized-byte-identical proof).
  - Period-over-period + vs-average: reuse `analytics_engine.compute_period_comparison` + `report_snapshot_store.load_recent` for realized; a parallel pure helper over the Sprint-18 `open_marks` history for the open book; baseline-pending wiring; on-demand reads existing history READ-ONLY (assert no snap_save).
  - `_build_system_health` honest sync-state mapping (status→label, no `✅` on temporary, strip/replace the flex "הדוח לא נוצר" semantics); `_period_label` inclusive-end fix with a focused test.
  - ⟨MARK⟩ slots for every label/threshold/N. Test plan: realized-byte-identical guard; headline-switch wording asserts (no "ללא עסקאות" dominant when book present); comparison/average + baseline-pending; System-Health no-`✅`-on-temporary + no-flex-string; `_period_label` 1–30; on-demand no snap_save; Sprint-18 period-scoping + 920be95 + bcf32f5 + Sprint-16 regression intact. Baseline 1761.
- **🚀 Hyperscaler:** `HYPERSCALER_SPRINT19_ADDENDUM.md` (≤90 words) — confirm period-over-period/average reads existing per-host snapshot history only (no DB/migration, verify_migrations stays 005, no user_id, single-user byte-identical, back-compat when history < N → baseline-pending); per-user comparison = deferred Phase-B touchpoint.

(No Marketing — internal report; DEC-20260515-004 forbids public ALGO numbers.)

## Checkpoint
Parent independently verifies: realized KPIs byte-identical (`analytics_engine.py` git-diff empty / additive-only guard); headline no longer dominantly "ללא עסקאות" when a live book spanned the period (but realized cards still truthfully "0 ממומש"); comparison/average honest baseline-pending until ≥N (no fabricated average); System-Health never `✅ temporary` and never the IBKR-flex "הדוח לא נוצר" string; `_period_label` shows inclusive end (1–30); ALGO #8-segregated in every new view; on-demand no snap_save; 920be95 + bcf32f5 + Sprint-16 + Sprint-18 period-scoping intact; full suite green.

## Out of scope / carried
🔴 Live accumulated smoke-test (Sprint 11–19) — closes once the founder confirms the period-honest report + comparison read correctly. Broker-recon $190.29 gap (#1 working — informational). Per-user comparison (Phase-B). ALGO Oversight Gate thresholds (DEC-20260515-014, separate sprint).
