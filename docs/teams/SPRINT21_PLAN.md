# Sprint 21 — COMPREHENSIVE Plan: production data-delivery fix (3 workstreams)

**Date:** 2026-05-16 · **Branch:** `claude/review-system-audit-FBZ2h`
**Trigger:** DEC-20260516-018 (+UPDATE/UPDATE 2). Founder: "תיקון מלא וזהיר — חלוקת משימות ע״פ צוותים וטיפול מקיף".
**Structure:** Wave 1 (parallel, doc-only) → checkpoint → Wave 2 (build, workstream-bounded) → consolidation.

## Established fact (do not relitigate)
`compute_period_analytics` is PROVEN CORRECT on the founder's real data (`tests/test_real_data_april_regression.py`: April→8 closed/+$180.49/WR 37.5%/Exp +1.07R/PF 2.63; weekly→3 ALGO-excluded -$37.23). The production "0" is a **data-delivery gap**, not a logic/display defect. Sprint-21 localizes & fixes it across 3 bounded workstreams.

## WS-A — Live read-only diagnostic probe (LOW)
New strictly read-only, admin-gated module that runs the REAL `report_scheduler._fetch_trades_df` in the live env for the on-demand weekly+monthly windows and reports: rows fetched, `trade_date` min/max, #SELL in-window, #closed campaigns the real pipeline computes, per-campaign classification (campaign_id/setup/initial_stop/`get_campaign_risk_metrics`+valid+reason/`stat_bucket`/countable/net_pnl), #in-window NULL-`campaign_id`, and the effective Supabase auth context (service-role vs anon + row visibility — NO secret values). Reuse the EXISTING dev-menu admin/PIN gate; minimal additive handler + one menu entry; no `telegram_bot.py` wholesale rewrite.

## WS-B — NULL-`campaign_id` honest surfacing + repair runbook (MED)
NULL/blank `campaign_id` trades silently vanish from BOTH realized (`analytics_engine.py:258 .dropna()`) and open-book (`engine_core.py:479 notnull()`). Add an HONEST disclosure (in-window count + Σ`pnl_usd` of unlinked trades) — never silent-zero (#1); NEVER auto-mutate Supabase from a read flow. Deliver a documented manual repair query/runbook for the founder to re-link the 8 rows from 2026-05-11+ (`9476246095`,`9488472266`,`9497196356`,`9498906569`,`9504706921`,`9505181333`,`9506481882`,`9510331382`) via `parent_trade_id`/symbol. Countable realized + open-book values byte-identical (guard).

## WS-C — `initial_stop` vs `initial_risk_price` fallback (HIGH — Mark-GATED, may DEFER)
Manual EP/VCP campaigns with `initial_stop=-1`/above-entry but a real stop in `initial_risk_price` (AEHR 54.85, etc.) → DATA_INCOMPLETE despite a genuine stop. **Campaign-math = CLAUDE.md most-protected.** Mark rules: valid fallback in `get_campaign_risk_metrics`, OR strictly founder data-correction (no code). If code: everything currently countable byte-identical + extensive tests + `test_real_data_april_regression.py` updated only with Mark sign-off. DEFER on any ambiguity.

## Hard constraints (whole sprint)
WS-A strictly read-only (no Supabase write/snap_save/scheduler-state mutation). Admin protection preserved (no secure_runner bypass; no telegram_bot.py wholesale rewrite — minimal additive). #8 ALGO segregation; #1 honesty (never silent-zero / fabricated). NO campaign/R/NAV/Expectancy math change outside an explicit Mark WS-C ruling + byte-identical guards. Preserve 920be95/bcf32f5/Sprint-16/18/19/20 + the real-data regression. No migration/compose/secure_runner change. Baseline 1816.

## Wave 1 — task distribution (parallel, doc-only)
- **🧠 Mark (lead — gates Wave 2):** `MARK_SPRINT21_RULINGS.md` — WS-A: read-only safety contract + exact honest Hebrew output + no-secrets rule + admin-gate reuse. WS-B: exact honest "N עסקאות לא-מקושרות — לא נספרו · $X" wording (realized + open-book), the no-auto-mutate rule, the repair-runbook safety. WS-C: the BINDING ruling — is `initial_risk_price`/`stop_loss` a valid `initial_stop` fallback (precise precedence + LONG/SHORT validity + which currently-countable campaigns must stay byte-identical), or DEFER to founder data-correction. 14-item pass/fail checklist incl. byte-identical guard, read-only proof, #8, #1, no-secret, 920be95/bcf32f5/16/18/19/20 intact.
- **🏗️ Architecture + Engine:** `SPRINT21_DESIGN.md` — WS-A `period_data_probe.py` (reuse `_fetch_trades_df`/`_get_closed_campaigns`/`classify_stat_bucket` read-only) + the minimal admin/PIN dev-menu wiring point (cite exact existing gate). WS-B disclosure seam (additive ctx, same disjoint-namespace pattern as Sprint-20 `_excluded_ctx`) + repair-runbook SQL. WS-C: design BOTH branches behind ⟨MARK⟩ (fallback impl vs no-op) with the byte-identical proof + guard tests; default = no-op until Mark rules. AST/spy read-only proof; Sprint-16..20 + real-data-regression intact. Baseline 1816.
- **🚀 Hyperscaler:** `HYPERSCALER_SPRINT21_ADDENDUM.md` (≤90 words) — read-only over existing per-host data: no schema/migration (verify_migrations stays 005), no user_id, single-user byte-identical, host-agnostic, zero billing; WS-C any campaign-math change is logic-only (no schema); per-user diagnostic = deferred Phase-B.

## Checkpoint
Parent independently verifies: WS-A provably read-only (AST/spy: no write/insert/update/snap_save/scheduler-mutation) + admin-gated via existing gate + no secret in output; WS-B never silent-zero, no auto-mutate, countable byte-identical; WS-C either DEFERRED or Mark-ruled with byte-identical guard + real-data regression green; #8/#1 intact; Sprint-16..20 + 920be95 + bcf32f5 + real-data regression intact; full suite green.

## Carried
🔴 Live accumulated smoke-test (Sprint 11–21) — closes once the probe localizes the production gap and the founder confirms a real report shows the true numbers. Partial-exit double-surface (Mark Q1). Per-user (Phase-B). ALGO Oversight Gate (DEC-20260515-014).
