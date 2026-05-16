# Sprint 20 — Plan: RCA-Gated "0 Realized" + Union-Based Period View

**Date:** 2026-05-16 · **Branch:** `claude/review-system-audit-FBZ2h`
**Trigger:** Founder smoke-test of deployed Sprint-19 (`2075756`) → DEC-20260516-017.
**Discipline:** RCA FIRST (read-only, no campaign-math change) → confirm root cause → THEN gated build. NOT the usual immediate Wave-1/2 build — accuracy over confidence (#1, CLAUDE.md).

## Sprint-19 verified live (do NOT regress)
Period-honest headline (no dominant "ללא עסקאות" with a live book); realized cards truthfully "0 בתקופה" (demoted, byte-identical); vs-average honest baseline-pending; System-Health honest; `_period_label` "3–9 במאי"/"1–30 באפריל". 1793 green.

## Founder objection (sharpened, the real core)
"רוב הנתונים 0 ולא תואם לאמת — גם נפתחו וגם נסגרו פוזיציות במהלך השבוע/החודש." Direction: period basis = **union (OR)** of opened-in-period ∪ closed-in-period ∪ open-spanning; count same-period open→close round-trips.

## Code-level RCA finding (leading hypothesis — must be data-confirmed)
- `analytics_engine._get_closed_campaigns:255-262` ALREADY counts any campaign with an in-window SELL incl. same-period round-trips — **not a round-trip formula bug**.
- `:258` `.dropna()` on `campaign_id` → in-window SELL with **NULL campaign_id silently dropped** (never counted, never `excluded`).
- `engine_core.get_open_positions_campaign:479` `notnull()` → null-campaign trades invisible to the OPEN book too ⇒ a null-`campaign_id` trade vanishes from BOTH views.
- `bot_health.py:146` already tracks null-`campaign_id` ⇒ a **known real condition** (ties to the open broker-recon $190.29 gap).
- `excluded_pnl`/`excluded_count` NOT surfaced in templates ⇒ linked-but-DATA_INCOMPLETE round-trips silently 0 (second #1 gap).

## Sprint 20 — Step 1 ONLY now: RCA (read-only, doc + probe design)

Investigation agent (read-only — code audit + probe design; NO analytics/campaign-math edit, NO Supabase write):
- Deep-audit every path a same-period round-trip / partial-exit / null-`campaign_id` / linked-but-excluded trade can take through `_fetch_trades_df` → `_get_closed_campaigns` → `_aggregate_campaigns` → bucket filter, AND through `get_open_positions_campaign`. Enumerate exactly which conditions make a real trade show as `0`.
- Design a strictly read-only, admin-gated dev-menu probe **"תקינות נתוני תקופה"** that, for the last weekly+monthly windows, prints the decisive counts: total trades in window; BUY/SELL counts; **BUY/SELL with NULL `campaign_id`**; #campaigns with an in-window SELL; #opened-AND-closed-in-window round-trips; Σ`pnl_usd` in window; `excluded_count`/`excluded_pnl`; list any in-window SELL whose `campaign_id` is null/unlinked (symbol+date+pnl, no secrets).
- Deliver `docs/teams/SPRINT20_RCA.md`: the decision tree (null-linkage vs unsynced vs out-of-window vs linked-but-excluded), the exact probe spec (file/function, dev-menu wiring, admin-gate reuse), and the precise diagnostic the founder runs to classify it. Propose Mark-ruling questions for the gated build.

## Sprint 20 — Step 2 (GATED on RCA + founder confirmation, NOT started yet)
Union-based period view (opened ∪ closed ∪ open; same-period round-trips counted; excluded/unlinked realized PnL surfaced honestly), Mark-led, full Wave-1/2 rigor, realized linked-closed countable subset byte-identical (guard).

## Hard constraints
RCA strictly read-only (no Supabase mutation, no snap_save, admin-gated). No campaign/R/NAV/Expectancy math change until root cause confirmed. #8 ALGO segregation + #1 (never present unlinked/incomplete data as exact truth; never fabricate closes not in the data — say so). Preserve 920be95/bcf32f5/Sprint-16/Sprint-18/Sprint-19. No migration/compose/secure_runner change.

## Carried
🔴 Live accumulated smoke-test (Sprint 11–20). Broker-recon $190.29 (now likely the SAME root cause as this — RCA will tell). Per-user (Phase-B). ALGO Oversight Gate (DEC-20260515-014).
