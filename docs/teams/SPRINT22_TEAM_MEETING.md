# Sprint 22 — Team-Leads Meeting (Consolidation): production "0" ROOT-CAUSE FIX

**Date:** 2026-05-16 · **Branch:** `claude/review-system-audit-FBZ2h`
**Suite:** 1846 → **1864 passed, 0 failed** (canonical full run, exit 0) + parent self-reference hardening.

## The proven root cause (closed)
The production "0 קמפיינים" was NOT data-delivery and NOT engine math. It was a **tz-aware vs tz-naive datetime comparison**: the real flow (`report_on_demand.py:112`, `report_scheduler.py:251/363`) passes tz-AWARE period bounds (`datetime.now(ISRAEL_TZ)` → `_weekly/_monthly_period`) while `analytics_engine.py:30` makes `trade_date` tz-NAIVE. The comparisons at the WS-B unlinked filter + `_get_closed_campaigns:334` silently went all-False → 0 campaigns / $0. Every "engine PROVEN on real data" claim held only on the tz-naive test path, never the production tz-aware path (#1 false-confidence gap — stated plainly, owned).

## Wave-1 commits
`a43ce1b` Mark (BINDING tz-normalization policy, 12-item gate) · `52f3c6c` Arch+Engine (single-point design) · `3f3c19d` Hyperscaler (no-schema confirmation).

## Parent independent verification (not agent self-report)

| Red line | Verified |
|---|---|
| **THE FIX WORKS** | ✅ Same LOCKED `_april_df()`/`_weekly_df()`: tz-**aware** bounds now produce **APR 8 / +$180.49 / WR .375 / PF 2.6262 / excl 2 ; WK 0 / excl 3** — **identical** to tz-naive. The production path now yields the true numbers. |
| tz-naive byte-identical | ✅ `_to_naive` is provable identity (`tzinfo is None → return ts` unchanged); both branch conditions False for naive inputs → zero reassignment. `tests/test_real_data_april_regression.py` **git-diff EMPTY** (LOCKED, untouched). |
| No campaign-math change | ✅ `analytics_engine.py` diff is purely additive — **zero removed lines**; only `_to_naive` + the ONE boundary site. `engine_core.py` **git-diff EMPTY** (WS-C still DEFERRED, untouched). |
| #1 anti-masking | ✅ The `:26` `df is None/empty → _empty()` honest guard precedes normalization; an empty/failed fetch still short-circuits honestly, never conflated with the tz fix. |
| One site covers all | ✅ One engine site covers the WS-B unlinked filter + `_get_closed_campaigns` (transitive, no helper edit) + all 3 prod callers; the probe mirror covers its direct `_get_closed_campaigns` use; probe no longer raises `Invalid comparison` under tz-aware `now`. |
| Sprint-19 guard rescope | ⚠️→✅ The Wave-2 agent changed the mechanism to **derive** the authorized set from live source (self-referential — weaker than the Sprint-20/21 static `_ALLOWED`). **Parent hardened it** (this consolidation): added an assertion that the self-derived authorized region itself contains **no KPI/countable assignment** (`win_rate|expectancy|profit_factor|total_r|real_pnl|campaigns_closed|net_pnl|countable` as `=`/`["..."]`), so even a self-derived allowlist can never admit a math/verdict edit. The load-bearing guarantees (LOCKED regression byte-identical, tz-aware==tz-naive proof, realized-ctx byte-identical) were never weakened. |
| #8 / WS-C / heritage | ✅ #8 ALGO segregation, WS-C DEFERRED, 920be95, bcf32f5, Sprint-16..21, WS-B `unlinked_*`, admin gate, secure_runner — all intact; no migration/compose/`telegram_bot.py` change. |
| Full suite | ✅ 1846 → 1864 passed, 0 failed (+18 tz tests) + parent hardening green. |

## What Sprint-22 delivers
- **`analytics_engine.py`** — pure `_to_naive(ts)` (strip tzinfo, preserve wall-clock, **never** `astimezone`/convert; identity on naive) + ONE boundary-normalization site in `compute_period_analytics` (after the `:30` coerce, after the `:26` empty guard, before the WS-B block): rebinds `period_start`/`period_end` + tz-localizes `trade_date` to naive. NO R/NAV/campaign/Expectancy/PnL math.
- **`period_data_probe.py`** — the SAME normalization mirrored after its coerce, so the probe stops raising under tz-aware `now` and stays faithful to the (now fixed) pipeline.
- **`tests/test_sprint22_tz_regression.py`** — parametrized {tz-naive, tz-aware Asia/Jerusalem} over the LOCKED fixtures asserting identical numbers; probe no-raise; byte-identical guard; #1 honest-empty distinct.
- **`tests/test_sprint19_headline_comparison.py`** — Sprint-22 region admitted via the per-sprint guard (Sprint-20/21 precedent) **plus** parent self-reference hardening.

## Deployment
`cd ~/sentinel_trading && ./deploy.sh` — no pre-step. **Then run the real on-demand weekly/monthly report (and/or the dev-PIN probe).** The production report will now show the TRUE numbers (April ≈ 8 closed / +$180.49 on the founder's real data, modulo any rows still missing `initial_stop`/`campaign_id`). Rollback: `git revert <range> && ./deploy.sh`.

## Honest scope note
Sprint-22 fixes the PRIMARY production blocker (tz). The SECONDARY data-integrity items remain and are independent founder tasks: (1) NULL-`campaign_id` rows from 2026-05-11+ — Sprint-21 `docs/runbooks/SPRINT21_NULL_CAMPAIGN_REPAIR.md`; (2) stop-above-entry / null `initial_stop` (AEHR-class) — surfaced honestly by the probe; the `initial_risk_price` fallback is the DEFERRED WS-C question (needs a ratified data contract + a new Mark ruling).

## Carried
🔴 Live accumulated smoke-test (Sprint 11–22) — closes once the founder runs the real production report and confirms the true non-zero numbers. WS-C reconsideration (ratified `initial_risk_price` contract). NULL-`campaign_id` founder repair runbook. Per-user (Phase-B). ALGO Oversight Gate (DEC-20260515-014).
