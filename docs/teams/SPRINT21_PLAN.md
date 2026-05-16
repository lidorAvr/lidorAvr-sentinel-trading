# Sprint 21 — Plan: Full-DB Read-Only Diagnostic ("where are my closes")

**Date:** 2026-05-16 · **Branch:** `claude/review-system-audit-FBZ2h`
**Trigger:** Founder smoke-test of deployed Sprint-20 (`8e6834b`) → DEC-20260516-018.
**Structure:** Wave 1 (parallel, doc-only) → checkpoint → Wave 2 (build) → consolidation.

## The honest finding (why this is NOT another report-logic sprint)
Sprint-20 live: NO excluded-disclosure block for the 03–09/05 weekly or April monthly windows ⇒ `excluded_count==0` AND `campaigns_closed==0` there. The report is now correct/honest across all three legs. The 52 missing-stop CLOSED records from `🏥 בריאות מערכת` are GLOBAL/all-time (unwindowed check) — NOT dated in the tested windows. So the question is now **data-location/visibility**: where in time are the founder's closes? Founder direction: **show the FULL database**.

## What Sprint 21 delivers
A strictly read-only, admin-gated dev-menu diagnostic (`📊 תקינות נתוני תקופה` / full-history) that prints:
- Total trades; `trade_date` min/max; recent-N-month breakdown: #BUY, #SELL, #closed campaigns (countable vs excluded-no-stop vs ALGO), Σ realized `pnl_usd`, #round-trips (opened&closed same month).
- The missing-stop CLOSED records listed WITH actual close date + symbol + pnl (the 52 → which months).
- Windowed null/blank `campaign_id` reconfirm.
- #1-honest labels; #8 ALGO segregated; no secrets.

## Hard constraints (carry whole sprint)
- Strictly read-only: no Supabase write / `snap_save` / scheduler-state mutation; reuse existing read path; NO campaign/R/NAV/Expectancy math (counts + already-stored `pnl_usd` sums only).
- Admin protection preserved: wire ONLY via the EXISTING dev-menu admin/PIN gate; do NOT remove admin protection / bypass `telegram_bot_secure_runner.py` / rewrite `telegram_bot.py` wholesale — minimal additive handler + one menu entry.
- No secrets in output. Preserve 920be95/bcf32f5/Sprint-16/Sprint-18/Sprint-19/Sprint-20. No migration/compose/secure_runner change.

## Wave 1 — task distribution (parallel, doc-only)
- **🧠 Mark (lead — gates Wave 2):** `MARK_SPRINT21_RULINGS.md` — rule: the exact read-only safety contract (what guarantees "no write"); the EXACT honest Hebrew/RTL output (per-month breakdown labels; "אין סגירות בחלון" vs "סגירות קיימות בחודש X — לא-מאומת/חסר stop"); #8 ALGO segregation in the breakdown (observation-only, never merged into edge counts); no-secrets rule (what fields may/!may appear); the admin-gate reuse requirement; 10-item pass/fail checklist incl. "no Supabase write / no snap_save / admin-gated / no secret / #8 / no campaign-math".
- **🏗️ Architecture + Engine:** `SPRINT21_DESIGN.md` — new pure read-only module (`period_data_probe.py`), reusing the existing read (`report_scheduler._fetch_trades_df` or an equivalent read-only select), the per-month aggregation (counts + `pnl_usd` sums only — reuse `_get_closed_campaigns`/`classify_stat_bucket` read-only, invent no math); the MINIMAL additive wiring point into the existing admin/PIN dev-menu (cite the exact existing gate: telegram_bot.py PIN session + telegram_menus.py entry the RCA flagged); ⟨MARK⟩ slots; test plan (read-only proof via AST/spy: no `.save`/insert/update/snap_save; admin-gate enforced; #8 split; honest-wording asserts; Sprint-16..20 regression intact). Baseline 1816.
- **🚀 Hyperscaler:** `HYPERSCALER_SPRINT21_ADDENDUM.md` (≤90 words) — confirm read-only over existing per-host data: no schema/migration (verify_migrations stays 005), no user_id, single-user byte-identical, host-agnostic, zero billing; per-user diagnostic = deferred Phase-B.

## Checkpoint
Parent independently verifies: probe is provably read-only (no Supabase write/insert/update, no snap_save, no scheduler-state mutation — AST/spy); admin-gated via the EXISTING gate (admin protection NOT weakened, secure_runner NOT bypassed, telegram_bot.py NOT wholesale-rewritten); no secrets in output; #8 ALGO segregated; NO campaign/R/NAV/Expectancy math; Sprint-16..20 + 920be95 + bcf32f5 intact; full suite green.

## Carried
🔴 Live accumulated smoke-test (Sprint 11–21) — closes once the founder uses the probe to locate their closes and we confirm the report reflects truth. Founder data task: complete entry/stop for the 52 no-stop closed records. Partial-exit double-surface (Mark Q1). Per-user (Phase-B). ALGO Oversight Gate (DEC-20260515-014).

---

## Ground-truth findings (founder dumped full `trades` table, 2026-05-16)

Manual analysis vs code (must be confirmed by the probe — no more eyeballing):

1. **Closes DO exist in the 03–09/05 weekly window** — 3 round-trips, ALL `setup_type=ALGO`: `JPM_9412172555` (open 04-30 → close 05-04, pnl -9.18), `JPM_9443250181` (05-06→05-07, -9.84), `HOOD_9449697599` (05-06→05-07, -18.22). `campaigns_closed=0` is #8-correct (ALGO never in edge). But Sprint-20 should have surfaced the **ALGO-excluded disclosure line** (excluded_count≈3, excluded_pnl_algo≈-37.2). The founder's post-Sprint-20 report showed NO disclosure block → **investigate**: (a) Sprint-20 gating bug when the excluded set is ALL-ALGO (manual=0), or (b) the report run predated the 8e6834b deploy.
2. **April has many real closes** — RVMD (+88.5, +111.2), AEHR (+35.6, +33.7), MTZ (+67.2), NEE (-11.6), DAR (+24.6), INTC (-33.6), AXGN (-12.8) — several EP/VCP with a **valid `initial_stop`** (e.g. RVMD_9307924911 entry 130.9 / initial_stop 127.8 → valid LONG stop). These SHOULD be `*_MANUAL` countable. The April report showed `0 קמפיינים` → **suspected real classification/linkage bug** (not only a disclosure gap). Must be reproduced per-campaign.
3. **Active NULL-`campaign_id` data bug (RCA path a, live now):** trades from 2026-05-11+ (`9476246095` onward — incl. CAT SELL 05-15 +13.71, JPM/HOOD round-trips 05-12..05-14) have `campaign_id=null` → silently dropped from BOTH realized and open-book views (`analytics_engine.py:258` `.dropna()`, `engine_core.py:479` `notnull()`). `bot_health` reported "כולם מלאים" because it ran before these rows' `created_at`.

## Probe scope SHARPENED (definitive instrument)

The Sprint-21 read-only probe MUST, for a given window, output **per closed campaign**: campaign_id, symbol, first-buy setup_type, first-buy initial_stop, computed `original_risk`+valid+reason (via the EXISTING `get_campaign_risk_metrics`, read-only), `stat_bucket`, countable? / which excluded bucket, net_pnl; PLUS counts of in-window SELLs with NULL campaign_id (silent-drop) and a per-month closed/opened summary. This converts every "0" into an explained list — turning hypotheses (1)/(2)/(3) into deterministic fact before ANY campaign-math change is even considered.
