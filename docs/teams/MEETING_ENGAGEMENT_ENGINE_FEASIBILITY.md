# MEETING_ENGAGEMENT_ENGINE_FEASIBILITY — Engine Wave 4

> ENGINE discipline. 21/05/2026. Read-only.
> Inputs: `MEETING_ENGAGEMENT_UX_SYNTHESIS.md`,
> `MEETING_ENGAGEMENT_MARK_RESEARCH_RULINGS.md`, engine sources,
> `CLAUDE.md`.

## Headline verdict

C5-S1 + C2-S1 ship Phase-1 on **zero new math**. C4-S1 ships on one
log field. C1-S2 needs **one new function** — a categorical matcher
over already-computed features. None of the four touches
R / NAV / exposure / campaign math; `CLAUDE.md` red line preserved.
Only non-trivial novelty is the C1 matcher; rest is logging discipline
+ read-only aggregation.

## C1 Callback matcher (deepest — math is novel here)

No precedent for similarity-matching exists: `engine_core.py` has
stat-bucket equality (`:1284-1304`), regime score-class equality
(`:570-611`), 4-gate pass/fail — no similarity scores. Heat windows
(`adaptive_risk_engine.py:675-683`, base_heat at `:683`) are
per-render, never compared across time. Must be built.

**Ruling: categorical 4-tuple, not vector.** Key =
`(symbol, direction, stat_bucket, s9_quintile)` — all from existing
output (`adaptive_risk_engine.py:716-721` dir; `engine_core.py:1284-1304`
bucket; `:679` s9 quintized on FIXED 0-100 boundary). 1.0 only on 4/4;
no partial credit Phase-1.

**Why categorical.** (a) Vector opens "near miss" sprawl; (b) Mark §X4
demands auditable anchor — a 4-tuple round-trips to one SQL `WHERE`;
(c) `ACTION_CALLBACK_FIRED.similarity_score` becomes reconstructable
without committing the metric to schema. Fixed quintile boundaries are
load-bearing — rolling boundaries drift, a row matched today must
still match in 6 months.

**FP/FN: under-fire.** Callback weight = *recognition*
(`UX_SYNTHESIS.md:68`); over-fire = stalker (`:70 R1`). UX capped
1/fortnight/bucket. Matcher stays **strict 4/4**; let cooldown enforce
scarcity. At n≈120 × 6 buckets × 3 dirs × 5 quintiles, strict 4/4
yields ≤1 hit/render most days — desired floor.

**ALGO oversight — critical.** `is_algo_position`
(`engine_core.py:256-269`) keys on `setup_type=="ALGO"` + symbol
fallback. A journal row authored under `algo_observed` records
adherence on a position the founder was *not fully driving*. Quoting
it back at a present manual setup violates §X6 by importing
external-management decisions into a discretionary moment. **Hard
requirement: matcher MUST filter anchors whose contemporaneous mode
was `algo_observed`** — join with `ACTION_POSITION_STATE_TRANSITION`
(`audit_logger.py:53`, metadata `is_algo`). MRVL `missing_data`
(chat-log 19/05 13:12; `engine_core.py:88` bare-except) similarly
disqualifies — rejected without full information.

## C4 Gate Receipt math

**Determinism.** `build_risk_raise_gate_ctx`
(`adaptive_risk_engine.py:552-596`) is pure at its boundary — no
clock, no random, no I/O. `evaluate_risk_raise_gate:490-549` fully
deterministic. `generated_at` `datetime.now()` at `:792` is recorded
artifact, not math input.

**"Save" definition.** `save = (gate.allow_raise == False) AND
(direction == "up" BEFORE clamp at :743-745)`. Δrisk_pct =
`RISK_LADDER[curr_idx+1] − RISK_LADDER[curr_idx]` (`:20`, `:748-749`)
— materiality **structurally guaranteed** by monotonic non-zero-step
ladder. No soft save.

**Cumulative $ saved (D11) — NAV is the missing anchor.** NAV-at-clamp
is implicit in rec-log (`recommended_risk_usd / (pct/100)`, lossy at
`round(. ,0)` at `:764`). **Recommendation: add `nav_at_eval` to
`_log_recommendation:849-874` as part of Phase-1 `gate_result` field.**
S-complexity, zero math drift. Without it, NAV-at-clamp permanently
lost; D11 inherits a precision tax.

**Anti-double-count.** Chat-log msgs 18837 + 18896 in one session =
two physical rec-log writes (`:868` appends each call). Dedup via
existing 48h settle window (`get_risk_settle_info:87-106`,
`RISK_SETTLE_HOURS=48.0`): collapse consecutive clamp rows in one
window into ONE save — matches founder's experience of one decision.

## C5 Monday R-dist + regime

**Windowed stability.** `_aggregate_campaigns:407-478` →
`net_r = net_pnl/orig_risk` (`:465`) with F7 cent-rounded denominator
via `get_campaign_risk_metrics` (`:448`). Stable for last-N /
week-bucketed — `closed` filtered upstream at
`_get_closed_campaigns:399-403` by SELL date.

**Regime join doesn't exist today.** `compute_market_regime:570-612`
is per-render only; `_aggregate_campaigns` emits no `regime_at_close`.
Back-deriving regime against today's SPY/QQQ for an old close-date
returns *today's* regime — the cached/fallback hazard. **D10 must be
captured at close, not reconstructed.**

**D10 SKIP-AND-NULL propagation.** Formatter contract: two tallies —
`overall_r_stats(all in window)` always; `regime_breakdown(WHERE
regime_at_close IS NOT NULL)` per regime; **`skipped_due_to_null_regime:
K` line ALWAYS emitted, including K==0.** A future "K==0 → suppress"
silently reintroduces fallback-as-truth.

## C2 Sizing pattern

**Ratio location.** `target_risk_usd` = `account_state.py:204-206`
(`nav × pct / 100`); `original_campaign_risk` = `engine_core.py:986`.
Computed in **exactly one location**: `risk_monitor.py:1170`, fired
one-time per campaign at `:1171-1174`. The research-cited
`engine_core.py:966-1066` defines the denominator, not the ratio.

**"Last N entries" aggregator — does it exist? No.** No per-symbol
rolling aggregator, no last-9 function, no rolling-20. C2-S1 copy
*"ב-9 הכניסות האחרונות"* requires a new function. Mark's "voice-only
change" framing is correct that the fire path is byte-identical; the
aggregator producing the number IS new math (read-only).
`compute_per_symbol_sizing_history(closed_campaigns, symbol, n=9)`,
pure, S ~12 lines. Mark's `RULINGS.md:144` (dedup key byte-identical)
preserved — new function does NOT sit on `_sizing_leak_alert`.

## Math invariants preserved

- **C1** consumes `s9_score`/`stat_bucket`/`direction`;
  `log_risk_journal:109-131` untouched. ✅
- **C4** `evaluate_risk_raise_gate` untouched (narrowing-only);
  log extensions **additive fields**. ✅
- **C5** `net_r` formula consumed verbatim; D10 NULL-write is new
  field, not redefinition. ✅
- **C2** ratio inputs consumed; new aggregator read-only. ✅

Four for four. No load-bearing primitive redefined.

## New math functions required (with complexity)

1. `compute_callback_match_key(journal_row, ctx) → tuple|None` (C1).
   S, ~15 lines. Returns None under `algo_observed`.
2. `compute_callback_candidates(journal_rows, ctx, audit_rows,
   min_days=60) → list` (C1). Joins with
   `ACTION_POSITION_STATE_TRANSITION`. M, ~30 lines.
3. `count_gate_saves(rec_log, window_days=90, settle_hours=48) → int`
   (C4). Settle-window dedup. S, ~20 lines.
4. `compute_per_symbol_sizing_history(closed, symbol, n=9) → dict`
   (C2). Pure. S.
5. `compute_regime_at_close_skip_aware(closed_in_window) → dict` (C5)
   → `{overall, by_regime, null_regime_n}`. S; depends on D10.

Logging-only additions: `gate_result` + `nav_at_eval` on
`_log_recommendation` (Mark `RULINGS.md:104`); `ACTION_CALLBACK_FIRED`
constant + payload (Mark Q2).

## Sign-off

Four of five ship Phase-1 on existing engine math; the one new piece
(C1 matcher) is well-bounded. Categorical-not-vector is the **right**
call for audit (§X4) + ALGO segregation (§X6).

Top 3 engine risks:

1. **C1 × ALGO segregation** — without the
   `ACTION_POSITION_STATE_TRANSITION` join, Callback can quote a
   rejection authored while ALGO was driving. §X6 failure in numeric
   clothes. **ALGO filter ships with the matcher, not after.**
2. **C4 NAV-at-clamp not stored** — D11 structurally unrecoverable
   from existing rec-log; back-computing NAV loses precision at
   `round(. ,0)` (`adaptive_risk_engine.py:764`). Add `nav_at_eval`
   Phase-1 or D11 inherits a permanent precision tax.
3. **C5 NULL-regime cohort line MUST emit at K==0** — Mark's
   SKIP-AND-NULL is correct, but a "K==0 → suppress" optimization
   silently reintroduces fallback-as-truth.

— ENGINE discipline, Wave-4, 21/05/2026. Read-only.
