# Sprint 24 — Consolidated Findings (parent checkpoint; evidence independently verified)

All cited `file:line` evidence spot-checked against the live tree and CONFIRMED real. Tiered by Mark's value÷risk rubric. Baseline suite **1879**. Wave-2 executes ONLY the founder-chosen tier(s); fragile-area items need explicit founder go-ahead (Mark ruling 2).

## Tier-A — zero-risk, documentation/comments ONLY (no code-path byte changes)
| # | file:line | fix | proof |
|---|---|---|---|
| A1 | `analytics_engine.py:381` | `_get_closed_campaigns` docstring says "campaigns whose **last SELL** falls in…" but the code keys off **ANY** in-window SELL — correct the docstring | no code change; suite 1879 unchanged |
| A2 | `report_scheduler.py:115` | docstring "**4-week** lookback" vs actual `:132 timedelta(weeks=8)` — correct to 8-week (keep the production-validated behavior) | no code change |
| A3 | `analytics_engine.py` `_aggregate_campaigns` / `orig_risk` | comment-only clarity: the BUY sort dependency + the "fallback never reaches a countable campaign" invariant | comments only |

## Tier-B — small behavior-preserving refactors, strong byte-identical proof
| # | file:line | change | risk | proof |
|---|---|---|---|---|
| B1 | `analytics_engine.py:121-123` | compute the `is_stat_countable` mask ONCE (currently applied twice: `:121` and `~…:123`) | med (analytics = fragile) | LOCKED April regression + Sprint-22 tz full-dict equality + full suite — pure no-op |
| B2 | `report_scheduler.py:124,131` | lazy module-singleton Supabase client (stop rebuilding `load_dotenv()`+`create_client()` every `_fetch_trades_df` call) | med | same client/credentials → identical fetch; Sprint-22/23 reconciliation re-run unchanged |
| B3 | `analytics_engine.py:30-33` | extract a shared **pure** `_coerce_numeric` helper (analytics-side ONLY; probe side STAYS Sprint-23 byte-locked → OUT) | med | provable identity vs the inlined loop; locked regression byte-identical |
| B4 | Telegram senders | extract ONE pure `split_for_telegram(text,limit)` string helper; per-caller send loops UNCHANGED (probe stays Sprint-23-locked) | med | pure function + unit tests; existing callers byte-identical |

## Tier-C — fragile-area structural cleanups (explicit founder go-ahead; higher risk)
| # | file:line | change | risk |
|---|---|---|---|
| C1 | `bot_helpers.py:80` / `risk_monitor.py:150` | single-source the byte-duplicated `get_account_settings` | HIGH — NAV/risk config (CLAUDE.md most-fragile) |
| C2 | `telegram_bot.py:769` | route the lone raw `supabase.table("trades").select` through the existing `supabase_repository` (read-only) | HIGH — telegram_bot (most-fragile) |
| C3 | `analytics_engine.py:58-59` | `_series_to_naive` helper for the twice-inlined tz-strip | HIGH — Sprint-22 tz load-bearing path |

## OUT OF SCOPE (all teams + Mark — will NOT do)
ALGO "תקן entry/stop" wording (behavior change to a production-validated string) · WS-C / `-1`-sentinel (DEFERRED) · unifying the 5 Telegram senders (transport/parse_mode/retry divergence is load-bearing) · deleting the test-pinned `algo_dead_money_rule` stub · sender error-handling unification · flat ERROR-print logging rework.

## Parent recommendation
**Tier-A + Tier-B** — delivers the founder's "cleaner + more efficient" with strong byte-identical proofs while avoiding the highest-risk fragile files. Tier-C deferred unless the founder explicitly wants the structural NAV/repo cleanups. (Mark's strict default is Tier-A only then reassess; Tier-B is recommended here because doc-only alone does not meet "יעיל יותר".)
