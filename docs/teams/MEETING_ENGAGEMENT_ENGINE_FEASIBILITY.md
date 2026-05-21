# MEETING_ENGAGEMENT_ENGINE_FEASIBILITY — Engine Wave 4

> ENGINE discipline, engagement-phase feasibility. 21/05/2026. Read-only.
> Inputs: `MEETING_ENGAGEMENT_UX_SYNTHESIS.md` (C1/C4/C5/C2 approved),
> `MEETING_ENGAGEMENT_MARK_RESEARCH_RULINGS.md` (rulings + Q2 +
> Q3 SKIP-AND-NULL), `engine_core.py`, `adaptive_risk_engine.py`,
> `analytics_engine.py`, `CLAUDE.md`.

## Headline verdict

C5-S1 and C2-S1 ship Phase-1 on **zero new math**. C4-S1 ships on a
one-field log change. C1-S2 (the Callback) needs **one genuinely new
function** — a per-render similarity matcher over already-computed
features. None of the four touches R / NAV / exposure / campaign math;
the `CLAUDE.md` red line is preserved. The only non-trivial engine
novelty is the C1 matcher; the rest is logging discipline and
read-only aggregation.

## C1 Callback matcher (deepest analysis — math is novel here)

There is **no precedent for vector similarity** in this codebase.
`engine_core.py` has stat-bucket equality (`:1284-1304`), regime
score-class equality (`:570-611`), and 4-gate pass/fail — no
similarity scores. Heat-window scores (`adaptive_risk_engine.py:675-683`,
weighted base_heat at `:683`) are per-render aggregates, never
compared across time. The matcher must be **built**.

**Ruling: categorical 4-tuple, not real-valued vector.** Match key:
`(symbol, direction, stat_bucket, s9_quintile)` — all derivable from
existing engine output (`adaptive_risk_engine.py:716-721` for
direction; `engine_core.py:1284-1304` for bucket; `:679` for s9_score
quintized on a fixed 0-100 boundary). `similarity_score = 1.0` when
4/4 match; partial credit disallowed Phase-1.

**Why categorical.** (a) Vector distance opens "near miss" sprawl at
every quintile boundary; (b) Mark §X4 demands an auditable anchor —
a 4-tuple round-trips into one SQL `WHERE`, a distance metric doesn't;
(c) `ACTION_CALLBACK_FIRED.similarity_score` becomes
reconstructable without committing the metric to schema. Fixed
quintile boundaries (not rolling mean-σ) are load-bearing — a row
matched today must still match under the same key in 6 months;
rolling boundaries drift.

**False-positive vs false-negative ruling.** Under-fire. The Callback's
weight is *recognition* (`UX_SYNTHESIS.md:68` "איך לא השתמשתי בזה");
over-fire produces the stalker risk (`:70 R1`). UX already capped
1/fortnight/reason-bucket. Engine ruling: matcher stays **strict 4/4**;
let the cooldown enforce scarcity. At typical n≈120 journal rows ×
~6 buckets × ~3 directions × 5 quintiles, strict 4/4 yields ≤1
hit/render most days — the desired floor.

**ALGO oversight effect — critical.** `is_algo_position`
(`engine_core.py:256-269`) keys on `setup_type=="ALGO"` plus a symbol
fallback. A risk-journal row authored during an `algo_observed`
management window records adherence on a position the founder was
*not fully driving*. Quoting it back at a present manual setup
violates §X6 Process-Mirror by importing external-management decisions
into a discretionary moment. **Engine requirement: the matcher MUST
filter anchor candidates whose contemporaneous management mode was
`algo_observed`** — join `risk_journal.json` row with the matching
`ACTION_POSITION_STATE_TRANSITION` row (`audit_logger.py:53`,
metadata `is_algo`). MRVL `missing_data` (chat-log 19/05 13:12) is a
separate defect (`engine_core.py:88` bare-except) and similarly
disqualifies — the founder rejected without full information.

## C4 Gate Receipt math

**Determinism at `build_risk_raise_gate_ctx`
(`adaptive_risk_engine.py:552-596`).** Pure at its boundary — no
clock, no random, no I/O it owns. `evaluate_risk_raise_gate:490-549`
is fully deterministic. `compute_adaptive_risk` uses
`datetime.now().isoformat()` for `generated_at` (`:792`) — a recorded
artifact, not a math input. Verdict: deterministic.

**"Save" semantic — math definition.** Per-event:
`save = (gate_result.allow_raise == False) AND (heat_direction == "up"
BEFORE the clamp at :743-745)`. The would-have-been Δrisk_pct is
`RISK_LADDER[curr_idx+1] − RISK_LADDER[curr_idx]` (`:20`, `:748-749`)
— materiality is **structurally guaranteed** by the monotonic
non-zero-step ladder. No "soft" save to disambiguate.

**Cumulative dollar saved (Phase-2, D11) — NAV is the missing
anchor.** NAV at clamp time is currently only implicit in the rec-log
(`recommended_risk_usd / (pct/100)` — lossy at the `round(. ,0)` step
in `:764`). **Recommendation: add `nav_at_eval` to
`_log_recommendation:849-874`** as part of the Phase-1 `gate_result`
field. S-complexity, zero math drift, makes D11 feasible without
per-clamp price modeling. Without it, NAV-at-clamp is permanently lost.

**Anti-double-count.** Per chat-log, gate refused at msg 18837 + 18896
in one session = **two physical rec-log writes** (every
`compute_adaptive_risk` appends, `:868`). Semantic "saved you N times"
needs dedup. The natural unit is the existing `T1.12` 48h settle
window (`get_risk_settle_info:87-106`, `RISK_SETTLE_HOURS=48.0`):
collapse consecutive clamp rows within one settle window into ONE
save event. This matches the founder's experience of the clamp as one
decision, not N re-evaluations.

## C5 Monday R-dist + regime

**Windowed stability.** `analytics_engine._aggregate_campaigns:407-478`
→ `net_r = net_pnl / orig_risk` (`:465`) with `orig_risk` from
`ec.get_campaign_risk_metrics` (`:448`, F7 cent-rounded denominator).
The chain is **stable** for last-N or week-bucketed subsets — the
`closed` frame is filtered upstream at `_get_closed_campaigns:399-403`
by SELL date, `_window_stats:311-342` works on any subset.

**Win-rate by regime — the join doesn't exist today.**
`compute_market_regime:570-612` is per-render only; `_aggregate_campaigns`
emits no `regime_at_close` column. Back-deriving regime against
today's SPY/QQQ bars for an old close-date returns *today's* regime —
the cached/fallback hazard `CLAUDE.md` warns against. **D10 must be
captured at close, not reconstructed.**

**D10 SKIP-AND-NULL propagation.** Mark's Q3 ruling is load-bearing
for the math chain. Formatter contract: two tallies, both honest —
`overall_r_stats(all in window)` always shown;
`regime_breakdown(closed where regime_at_close IS NOT NULL)` shown
per regime; **`skipped_due_to_null_regime: K` line ALWAYS emitted,
including K==0**. A future "K==0 → suppress" optimization silently
reintroduces fallback-as-truth.

## C2 Sizing pattern

**Where the ratio lives.** `target_risk_usd` at
`account_state.py:204-206` (`nav × pct / 100`).
`original_campaign_risk` at `engine_core.py:986`. The ratio itself is
computed in **exactly one location**: `risk_monitor.py:1170`
(`_sizing_ratio = original_campaign_risk / target_risk_usd`), fired
one-time per campaign at `:1171-1174`. The research-cited
`engine_core.py:966-1066` defines the denominator, not the ratio.

**"His sizing pattern over last N trades" — does it exist?** **No.**
No per-symbol rolling aggregator, no last-9-entries function, no
rolling-20 mean exists. The C2-S1 copy *"ב-9 הכניסות האחרונות עליו
היית ב-0.41x"* therefore requires a new function. Mark's
"voice-only change" framing is correct that the *fire path* is
byte-identical; the aggregator producing the number IS new math
(read-only, no R/NAV change). Engine recommendation:
`compute_per_symbol_sizing_history(closed_campaigns, symbol, n=9) →
{mean_ratio, n_used, last_n_ratios}`. Pure read-only over
already-aggregated campaigns. S-complexity (~12 lines, one groupby).
Mark's binding at `RULINGS.md:144` (dedup key byte-identical) is
preserved — the new function does NOT sit on `_sizing_leak_alert`.

## Math invariants preserved

- **C1** matcher consumes `s9_score` / `stat_bucket` / `direction`;
  `log_risk_journal:109-131` untouched. ✅
- **C4** `evaluate_risk_raise_gate:490-549` untouched (still
  narrowing-only); `_log_recommendation` extensions are **additive
  fields**. ✅
- **C5** `net_r = net_pnl / orig_risk` (`analytics_engine.py:465`)
  consumed verbatim; D10 NULL-write is a new field, not a redefinition. ✅
- **C2** `target_risk_usd` (`account_state.py:206`) and
  `original_campaign_risk` (`engine_core.py:986`) consumed; new
  aggregator is read-only. ✅

Four for four. No concept redefines a load-bearing math primitive.

## New math functions required (with complexity)

1. `compute_callback_match_key(journal_row, current_ctx) →
   tuple[str,str,str,int]` (C1). S, ~15 lines. Returns `None` when
   anchor was authored under `algo_observed`.
2. `compute_callback_candidates(journal_rows, current_ctx,
   audit_log_rows, min_days=60) → list[row]` (C1). Joins journal with
   `ACTION_POSITION_STATE_TRANSITION` audit for ALGO filter. M, ~30 lines.
3. `count_gate_saves(rec_log_rows, window_days=90, settle_hours=48)
   → int` (C4). Settle-window dedup. S, ~20 lines.
4. `compute_per_symbol_sizing_history(closed_campaigns, symbol, n=9)
   → dict` (C2). Pure. S.
5. `compute_regime_at_close_skip_aware(closed_in_window) → dict` (C5)
   returning `{overall, by_regime, null_regime_n}`. S; depends on D10.

Logging-not-math (field additions only): `gate_result` + `nav_at_eval`
on `_log_recommendation` (B-tier, Mark `RULINGS.md:104`);
`ACTION_CALLBACK_FIRED` constant + payload in `audit_logger.py`
(Mark Q2 ratified).

## Sign-off

Four of five concepts ship Phase-1 on existing engine math; the one
genuinely new piece (C1 categorical similarity matcher) is
well-bounded. Categorical-not-vector is the **right** choice for both
audit (§X4) and ALGO segregation (§X6).

Top 3 engine risks:

1. **C1 matcher × ALGO segregation** — without the
   `ACTION_POSITION_STATE_TRANSITION` join, the Callback can quote a
   rejection authored while ALGO was driving. That is §X6 Process-Mirror
   failure in numeric clothes. **Hard requirement: ALGO filter ships
   with the matcher, not after.**
2. **C4 NAV-at-clamp not stored today** — D11 (Phase-2) is
   structurally unrecoverable from existing rec-log rows; back-computing
   NAV from `recommended_risk_usd / pct` loses precision at
   `round(. ,0)` (`adaptive_risk_engine.py:764`). Add `nav_at_eval`
   in Phase-1 logging change or D11 inherits a permanent precision tax.
3. **C5 NULL-regime cohort line** — Mark's SKIP-AND-NULL is correct,
   but the formatter MUST always emit the skipped-count line, even at
   K==0. A future optimization that suppresses on K==0 silently
   reintroduces fallback-as-truth.

— ENGINE discipline, Wave-4 engagement-phase feasibility,
21/05/2026. Read-only.
