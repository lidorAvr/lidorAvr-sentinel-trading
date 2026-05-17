# Sprint 20 (Step-2) — Team-Leads Meeting (Consolidation): Honest Excluded-Closed Disclosure

**Date:** 2026-05-16 · **Branch:** `claude/review-system-audit-FBZ2h`
**Suite:** 1793 → **1816 passed, 0 failed** (canonical full run, exit 0).

## RCA gate (passed) + Wave-1 commits
RCA confirmed via the live `🏥 בריאות מערכת` (founder): null-linkage RULED OUT, sync current, **52 closed records without stop "אינו נספר"** → root cause = closed-but-`DATA_INCOMPLETE` excluded leg computed but rendered NOWHERE (a #1 disclosure defect, NOT campaign-math). `e51dcd7`/`4e29919` (RCA+DEC), `3abcdcc` Mark, `fc18614` Arch+Engine, `d5a9345` Hyperscaler.

## Parent independent verification (not agent self-report)

| Red line | Verified |
|---|---|
| analytics_engine additive-only | ✅ ONLY a comment + read-only partition of the EXISTING `excluded` frame by the EXISTING `stat_bucket` → 4 ADDITIVE keys (`excluded_{count,pnl}_{manual,algo}`). `excluded_count`/`excluded_pnl`/`countable`/edge values UNCHANGED; the one "modified" line is the `excluded_pnl}`→`,`+`}` brace reflow (name+value byte-identical). Exactly Mark's APPROVED ruling #2 |
| compute_verdict / countable / edge | ✅ untouched (no win_rate/expectancy/profit_factor/total_r/real_pnl/campaigns_closed line changed) |
| Sprint-19 guard rescope | ✅ legitimate & STRICTER — replaces the now-obsolete `git diff --exit-code` (Sprint-20 must add the Mark-APPROVED keys) with a structural assert: no non-additive removed/modified line, every added line a comment or confined to the `excluded_*_{manual,algo}` split; would FAIL on any edge/verdict edit. Dedicated countable-byte-identical proof moved to the new test |
| `_base_ctx` realized | ✅ additive-only (no realized line removed/modified); `_excluded_ctx` mirrors the Sprint-19 disjoint-namespace seam |
| excluded never summed | ✅ `excl_*` never merged into realized_pnl/total_r/win_rate/expectancy/profit_factor |
| ALGO #8 | ✅ manual vs ALGO split by canonical `ec.STAT_BUCKET_ALGO`; ALGO on its own observation-only line, never instruction, never headline/edge; invariant `manual+algo==excluded` tested |
| Scope-B / on-demand | ✅ `report_on_demand.py` UNCHANGED by Sprint-20 (invariant preserved by construction; the earlier "❌ mutation" was a false-positive on the invariant docstring) |
| 920be95 / bcf32f5 / Sprint-18 / Sprint-19 | ✅ all intact |
| Forbidden files | ✅ none (no docker-compose / secure_runner / migration; verify_migrations stays 005) |
| Full suite | ✅ 1816/0-fail canonical (+23) |

## What Sprint-20 Step-2 delivers (founder DEC-20260516-017)

When campaigns closed in-period but were excluded for missing `initial_stop` (`excluded_count>0`), the weekly/monthly report + Telegram summary now show a DISTINCT honest disclosure block: "ℹ️ N קמפיינים נסגרו בתקופה אך הוחרגו מסטטיסטיקת ה-edge (חסר stop) — רווח/הפסד ממומש לא-מאומת: $X · השלם entry/stop כדי להיכלל" — manual (actionable) and ALGO (observation-only, `פיקוח בלבד · לא הוראה`) on SEPARATE lines, NEVER summed into Realized/WR/Expectancy/PF/Net-R (which stay byte-identical & #8-clean). This closes the founder's "0 ולא תואם לאמת" — the real closes are now honestly surfaced (realized-but-unverified), reconciled with the Sprint-19 "0 בתקופה" countable framing without contradiction, completing the opened∪closed∪open union view.

## Deferred (documented, none blocking)
Partial-exit double-surface (RCA failure (c) / Mark Q1) — explicitly OUT of scope. 🔴 Live accumulated smoke-test (Sprint 11–20). **Founder data-completion task:** complete entry/stop for the 52 closed records (HOOD/HP/JPM/MSGE/PLTR) so they enter edge stats (the disclosure surfaces them honestly even before; true WR/Expectancy need the stop). Per-user (Phase-B). ALGO Oversight Gate (DEC-20260515-014).

## Deployment
`cd ~/sentinel_trading && ./deploy.sh` — no pre-step. Brings Sprint-20 on top of live Sprint-19. Validate via `🛠️ מפתח → 📈 דוח שבועי/חודשי עכשיו`: when closes-without-stop exist in-window, the disclosure block must appear with the correct N/$X, manual vs ALGO on separate lines, "לא-מאומת" present, and the countable KPI cards UNCHANGED. Rollback: `git revert <range> && ./deploy.sh`.
