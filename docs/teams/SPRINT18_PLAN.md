# Sprint 18 — Plan & Team-Leads Meeting: Open-Book in Weekly/Monthly Report

**Date:** 2026-05-16 · **Branch:** `claude/review-system-audit-FBZ2h`
**Trigger:** Founder smoke-test (Sprint-17 on-demand button) → DEC-20260516-015.
**Founder choice:** "מלא + snapshot קדימה" (full open-book section + honest empty-state + begin snapshotting marks so the true weekly delta appears next week).
**Structure:** Wave 1 (parallel, doc-only) → checkpoint → Wave 2 (build) → consolidation.

## The problem (precise)

`compute_period_analytics` is realized-only ("campaigns that closed within the period"). With a live 6-position book (HOOD/MRVL/PLTR/PWR/TSLA/WCC, +$230 floating, 31.3% exposure) and 0 *closed* campaigns in the on-demand window, the report said "🔴 שבוע ללא עסקאות" — misleading (#1) + the open book's state/performance is entirely absent.

## What Sprint 18 delivers (DEC-20260516-015)

1. **Open-book section** in weekly+monthly: per open position — entry / current / floating PnL / Open-R / exposure — reusing the EXISTING live source `ec.get_open_positions_campaign` (engine_core.py:473; identical to the command room). **Realized vs unrealized strictly separated**; the open book NEVER enters realized WR/Expectancy/PF/Net-R. **ALGO segregated** (#8 / DEC-20260515-014), observation-only (DEC-20260511-001).
2. **Honest empty-state**: when 0 closed but a live book exists → "0 קמפיינים נסגרו בתקופה" + open-book summary, not "ללא עסקאות". #1-honest about window + data source (Live/Cached/Sync-temporary).
3. **Begin snapshotting open-position marks** per scheduled run (additive `report_snapshot_store` field) → true weekly mark-to-market delta from NEXT week. Honest "—" until a baseline exists (no retroactive open-mark; accuracy over confidence).

## Hard constraints (carry the whole sprint)

- **No realized R/NAV/campaign/Expectancy math change** (CLAUDE.md fragile area). Realized KPIs byte-identical with vs without the new open-book code path (guard test).
- **Strict realized/unrealized separation + ALGO #8** provable by construction + test: the open book never contaminates realized stats; ALGO open positions never in headline; ALGO advisory/observation only.
- **#1 honesty**: never present an empty realized set as "no activity"; never present a snapshot-less delta as a number — show "—" + reason.
- **Reuse `get_open_positions_campaign`** (battle-tested in the command room) — invent NO new position/PnL/R math. No wholesale renderer rewrite.
- New snapshot field additive — Hyperscaler: no migration, per-host derived state, single-user byte-identical.
- Sprint-17 #8 AST guard (`analytics_engine` imports no `algo_metrics`) stays green; Sprint-16 graceful PDF path intact; the just-shipped weekly-PDF/`%`-format fix (920be95) preserved.

## Wave 1 — task distribution (parallel, doc-only, distinct files)

- **🧠 Mark (lead — gates Wave 2):** `MARK_SPRINT18_RULINGS.md`
  - Rule the EXACT realized-vs-unrealized boundary: which fields the open-book section shows, the precise wording that 0-closed-but-live-book must render (Hebrew, RTL, #1-honest), and that the open book is provably excluded from every realized KPI.
  - ALGO open positions: segregation rule (#8 / DEC-014), observation-only labels (DEC-20260511-001), backtest-caveat applicability (these are LIVE open positions, not the backtest — be precise: the ALGO *rules* are backtest-derived, the open position's floating PnL is live; word it correctly, no false caveat, no missing caveat).
  - Snapshot-delta rule: the new field's exact contents, how "—/baseline pending" is shown until a prior open-mark exists, and that an on-demand run still must NOT snap_save (DEC Scope-B / report_on_demand invariant).
  - 12-item pass/fail checklist incl. the "realized KPIs byte-identical with vs without open-book path" guard.
- **🏗️ Architecture + Engine:** `SPRINT18_DESIGN.md`
  - Where the open-book section slots into `report_renderer` (weekly+monthly templates) + `build_summary_text`, fed by `ec.get_open_positions_campaign` read-only; the realized/unrealized seam (separate ctx keys, never merged into the realized KPI block).
  - The empty-state branch change in `compute_verdict`/`build_summary_text`/templates so a live book is surfaced honestly (build on the just-shipped period-aware verdict; do not regress 920be95).
  - The additive `report_snapshot_store` open-marks field + `_run_weekly`/`_run_monthly` write path; the next-run delta read; on-demand stays no-snap_save.
  - ⟨MARK⟩ slots for every threshold/label/wording. Test plan: realized-KPI byte-identical guard; open-book + ALGO-segregation fixtures from the founder's command-room data; #1 wording assertions; on-demand no-snap_save still asserted; Sprint-16 graceful + 920be95 regression intact. Baseline 1716.
- **🚀 Hyperscaler:** `HYPERSCALER_SPRINT18_ADDENDUM.md` (≤90 words) — confirm the open-marks snapshot field is additive per-host derived state: no DB schema/migration (verify_migrations stays 005), no user_id, single-user byte-identical; per-user open-book = deferred Phase-B touchpoint only.

(No Marketing — internal report; DEC-20260515-004 forbids public ALGO numbers.)

## Checkpoint
Parent independently verifies: realized KPIs byte-identical (guard); open book never in realized stats + ALGO never in headline (by construction + test); #1 wording (no "no activity" when a book exists; "—" not a fake delta); on-demand still no snap_save; no realized-math/migration/compose/secure_runner change; 920be95 + Sprint-16 graceful intact; full suite green.

### Founder clarification 2026-05-16 14:00 (binding — verify at consolidation)
Founder smoke-tested the deployed 920be95/bcf32f5 (weekly pdf=True ✅, monthly "חודש" ✅) and sharpened the core requirement: **"the report still does not recognize trades OPENED during the week/month — says 0, which is plainly wrong."**
Consolidation MUST verify the open-book/empty-state reflects **period-scoped activity**, not only a current snapshot:
- Positions whose entry (`trade_date`/buy) falls within `[period_start, period_end]` are explicitly attributed as **"נפתחה בתקופה"** in the open-book section.
- Positions **open/held during** the period (entry ≤ period_end and still open) are surfaced even if opened before the window.
- The empty-state, when 0 campaigns closed but a book was open/held in the window, must state plainly that N positions were **open/held (and which opened) during the period** — it must NEVER render "ללא עסקאות"/"0 פעילות" when there was opening or holding activity in the window.
- Still: realized vs unrealized strictly separated; ALGO #8-segregated & observation-only; #1-honest about window + Live/Cached source.
If Wave-2 output does not fully satisfy this, the parent applies a focused refinement BEFORE the Sprint-18 deploy (do not ship a report that still says "0/no trades" while a live book spanned the period).

## Out of scope / carried
The 2 just-shipped fixes (920be95) deploy independently NOW (weekly-PDF crash is urgent — Saturday). Live accumulated smoke-test (Sprint 11–18). Broker-recon material gap ($190.29) is correctly surfaced as "requires manual verification" (#1 working — informational, not a Sprint-18 task).
