# Sprint 21 — Team-Leads Meeting (Consolidation): Production Data-Delivery Fix (3 workstreams)

**Date:** 2026-05-16 · **Branch:** `claude/review-system-audit-FBZ2h`
**Suite:** 1818 → **1843 passed, 0 failed** (canonical full run, exit 0). +25 tests.

## Premise (proven, locked)
`compute_period_analytics` is PROVEN CORRECT on the founder's real data (`tests/test_real_data_april_regression.py`: April→8 closed/+$180.49/WR 37.5%/Exp +1.07R/PF 2.63; weekly→3 ALGO-excluded -$37.23). Production "0" = a **data-delivery gap**, not logic. Sprint-21 = WS-A diagnostic + WS-B honest disclosure + WS-C deferred.

## Wave-1 commits
`9289011` Mark (WS-A/B APPROVED, WS-C DEFERRED) · `23e990d` Arch+Engine · `c7a9ecd` Hyperscaler.

## Parent independent verification (not agent self-report)

| Red line | Verified |
|---|---|
| WS-C no-op | ✅ `engine_core.py` **git-diff EMPTY**; `test_real_data_april_regression.py` byte-identical (Mark DEFERRED `initial_risk_price` fallback — would risk fabricating R without a ratified data contract) |
| WS-B additive-only | ✅ `analytics_engine.py` adds ONLY the disjoint `unlinked_*` keys (count + stored-`pnl_usd` sum — no R/NAV/campaign/Expectancy math); `excluded_pnl_algo` & all countable/excluded values byte-identical (only the Sprint-20-style authorized brace-reflow); dedicated `TestWSBByteIdentical` proves countable + open-book byte-identical on the real-data fixture |
| WS-A read-only | ✅ `period_data_probe.py` has no write/`.save`/`snap_save`/`_mark_ran`/`_save_state`/`.execute()`/`.insert/update/delete`/env-write in code (only docstring describes the contract); the sole Supabase `.execute()` is the reused `_fetch_trades_df` `select` chain |
| WS-A admin gate | ✅ `telegram_bot.py`+`telegram_menus.py` = 25 insertions only (1 menu button + 1 handler `if` after `🏥 בריאות מערכת`); the `dev_pin` gate + `secure_runner` lines untouched; no telegram_bot.py wholesale rewrite |
| Sprint-19 guard rescope | ✅ legitimate — `_TOL_REFLOW` allowlist is 2 EXACT strings (the Sprint-20 + Sprint-21-WS-B authorized brace reflows); still fails on ANY countable/edge/verdict edit; dedicated byte-identical proof delegated to `test_sprint21_wave2.py` |
| #8 / #1 | ✅ ALGO segregation intact; `unlinked_*` never silent-zero (count==0 ⇒ no line, WS-A honest-empty governs the empty-fetch case); never auto-mutates Supabase |
| Regression | ✅ 920be95 / bcf32f5 / Sprint-16 / 18 / 19 / 20 + real-data regression all green; no migration/compose/secure_runner change |
| Full suite | ✅ 1843/0-fail canonical (+25) |

## What Sprint-21 delivers

- **WS-A — live read-only diagnostic** (`period_data_probe.py`, dev-menu button behind the existing `dev_pin` gate): runs the REAL `_fetch_trades_df` for the on-demand weekly+monthly windows and reports rows fetched, `trade_date` min/max, #SELL in-window, #closed campaigns the real pipeline yields, per-campaign classification (campaign_id/setup/initial_stop/`get_campaign_risk_metrics`+valid+reason/bucket/countable/net_pnl), #in-window NULL-`campaign_id`, and the Supabase auth role word (`service_role|anon|unknown` — NEVER key/token/account values). Mandatory honest "input ריק/כשל — NOT shown as 0 closes" branch. **This localizes WHY production input is empty (RLS/key vs runtime-failure vs data) when run live with the service's own credentials.**
- **WS-B — NULL-`campaign_id` honest surfacing**: the rows `analytics_engine.py:286 .dropna()` (realized) and `engine_core.py:479 .notnull()` (open-book) silently discard are now disclosed verbatim (`⚠️ {N} עסקאות לא-מקושרות (חסר campaign_id) — לא נכללו · ${X} · דורש קישור`) in weekly/monthly + Telegram summary + open-book — never silent-zero (#1), never auto-mutating Supabase. Disjoint additive `unlinked_*`; countable/excluded/open-book byte-identical. Reversible founder-run repair runbook (`docs/runbooks/SPRINT21_NULL_CAMPAIGN_REPAIR.md`) for the 8 named 2026-05-11+ rows.
- **WS-C — DEFERRED (Mark, binding)**: no `get_campaign_risk_metrics`/R/NAV/campaign-math change; only the verbatim honest founder-guidance string ("⚠️ stop לא תקין … תקן entry/stop") surfaced presentationally. Re-opening needs a new Mark ruling + ratified `initial_risk_price` data contract + founder confirmation.

## Deployment
`cd ~/sentinel_trading && ./deploy.sh` — no pre-step. **Then run, behind the developer PIN, the new diagnostic button** and send its output: it will show, with the live service credentials, exactly how many rows `_fetch_trades_df` returns for the April/weekly windows and the per-campaign classification — the definitive localization of the production "0". Rollback: `git revert <range> && ./deploy.sh`.

## Founder data tasks (independent, recommended now)
1. Re-link the 8 NULL-`campaign_id` rows from 2026-05-11+ (incl. CAT SELL 05-15 +$13.71) via `docs/runbooks/SPRINT21_NULL_CAMPAIGN_REPAIR.md`.
2. Correct the stop-above-entry data-entry errors (AEHR-class: `initial_stop` set above entry while the real stop sits in `initial_risk_price`).

## Carried
🔴 Live accumulated smoke-test (Sprint 11–21) — closes once the WS-A probe localizes the production gap and a real report shows the true numbers. Partial-exit double-surface (Mark Q1). Per-user (Phase-B). ALGO Oversight Gate (DEC-20260515-014). WS-C reconsideration (needs ratified data contract).
