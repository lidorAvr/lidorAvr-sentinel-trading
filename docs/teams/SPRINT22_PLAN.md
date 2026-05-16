# Sprint 22 — Plan: production "0" ROOT CAUSE — tz-aware bounds vs tz-naive trade_date

**Date:** 2026-05-16 · **Branch:** `claude/review-system-audit-FBZ2h`
**Trigger:** DEC-20260516-019. Founder: "ספרינט Mark-gated מלא".
**Structure:** Wave 1 (parallel, doc-only) → checkpoint → Wave 2 (build) → consolidation.

## Proven root cause (do not relitigate)
Same `tests/test_real_data_april_regression.py::_april_df()` fixture, REAL `analytics_engine.compute_period_analytics`:
- tz-**naive** bounds (100% of the suite) → **8 campaigns / +$180.49** ✅
- tz-**aware** bounds (what PRODUCTION passes via `datetime.now(ISRAEL_TZ)`) → **0 / $0.00** ❌ (silent all-False)

`report_on_demand.py:96-113` + `report_scheduler.py:251,363` pass tz-aware `period_start/period_end`; `analytics_engine.py:30` makes `trade_date` tz-naive; the comparisons at `_get_closed_campaigns:334` + the Sprint-21 WS-B unlinked block `analytics_engine.py:54-55` silently yield all-False (the probe's own pre-filter RAISED — same defect). This is THE production "0". WS-A "data-delivery" was a wrong hypothesis; null-`initial_stop` is a real but SECONDARY data issue (Sprint-21 WS-B/probe already disclose it). WS-C stays DEFERRED, untouched.

## The fix (Mark-gated; analytics-engine = CLAUDE.md MOST-protected)
Single-point tz-normalization at the comparison boundary INSIDE `compute_period_analytics`: normalize BOTH sides to tz-naive (strip tz from `period_start`/`period_end` if tz-aware; guarantee `trade_date` tz-naive post-`pd.to_datetime`). One site fixes ALL callers (on-demand + scheduled + probe→`_get_closed_campaigns`). Mirror the SAME normalization in `period_data_probe.py`'s own pre-pipeline window filter (it filters BEFORE delegating). **NO R/NAV/campaign/Expectancy math change** — pure boundary normalization.

## Hard constraints (whole sprint)
tz-naive path (entire suite + the LOCKED `test_real_data_april_regression.py`) byte-identical (no-op for naive inputs). NEW regression: tz-aware bounds MUST equal tz-naive numbers (April 8/+$180.49/WR .375/PF 2.626/excl 2; weekly 0/excl 3). #1 honesty (fix must not mask/fabricate; honest data only). #8 ALGO segregation untouched. WS-C DEFERRED (not reopened). Preserve 920be95/bcf32f5/Sprint-16..21 + WS-B `unlinked_*` + admin gate + secure_runner; no migration/compose/telegram_bot.py wholesale change. Baseline full suite **1846**.

## Wave 1 — task distribution (parallel, doc-only)
- **🧠 Mark (lead — gates Wave 2):** `MARK_SPRINT22_RULINGS.md` — the BINDING tz-normalization policy: exact normalization rule (which side, naive-target, where in `compute_period_analytics` relative to line 30 + the WS-B `:54-55` block + `_get_closed_campaigns:334`); the invariant that the tz-naive path is byte-identical (normalization MUST be a provable no-op for naive inputs); the tz-aware-equals-tz-naive regression contract (exact locked numbers); the probe-mirroring requirement; #1 (fix must not silently mask a real empty fetch as "0" — the WS-A honest-empty branch must still trigger on a genuinely empty fetch, distinct from the tz bug); confirmation WS-C stays DEFERRED + #8 untouched. 12-item pass/fail checklist incl. byte-identical guard, tz-aware regression, no math change, probe mirrored, 920be95/bcf32f5/Sprint-16..21 + real-data regression intact.
- **🏗️ Architecture + Engine:** `SPRINT22_DESIGN.md` — exact single-point patch design in `compute_period_analytics` (the normalization helper + its placement; how it covers `_get_closed_campaigns` + the WS-B unlinked block + every caller); the mirrored probe patch (`period_data_probe.py` pre-filter at the `work["trade_date"] >= period_start` site ~159-176); proof the naive path is an algebraic no-op; the new tz-aware regression test design (parametrize the locked fixture over naive+aware bounds, assert equality); enumerate all `compute_period_analytics` callers (on-demand, scheduler:251/363, probe) confirming one site suffices. ⟨MARK⟩ slots verbatim for any threshold/wording. Baseline 1846; explicit "will NOT change" list.
- **🚀 Hyperscaler:** `HYPERSCALER_SPRINT22_ADDENDUM.md` (≤90 words) — pure logic/boundary fix, no schema/migration (verify_migrations stays 005), no user_id, single-user byte-identical, host-agnostic, zero billing; tz-normalization is per-process datetime handling (no per-host data change). 3-point consolidation checklist.

## Checkpoint
Parent independently verifies: tz-aware `_april_df()` → 8/+$180.49 AND tz-naive still 8/+$180.49 (byte-identical); the normalization is a provable no-op for naive inputs (no suite delta); probe no longer raises under tz-aware `now` and mirrors the same rule; `compute_period_analytics` callers all covered by one site; NO R/NAV/campaign-math diff; #1 honest-empty still distinct from the tz-fix; #8 + WS-C untouched; 920be95/bcf32f5/Sprint-16..21 + WS-B `unlinked_*` + real-data regression intact; full suite green (≥1846 + new tz tests).

## Carried
🔴 Live accumulated smoke-test (Sprint 11–22) — closes once the founder runs the real on-demand report in production and sees the true non-zero numbers. WS-C reconsideration (needs ratified `initial_risk_price` data contract). NULL-`campaign_id` founder repair runbook (Sprint-21). Per-user (Phase-B). ALGO Oversight Gate (DEC-20260515-014).
