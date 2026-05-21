# Meeting UX — ENGINE Findings (review of 3ac93e8 / fdd4e84 / e9872f8)

**Date:** 2026-05-21 · **Branch:** `claude/review-system-audit-FBZ2h` · **Discipline:** ENGINE.
**Scope:** F-YTD recon-classifier disclaimer + adaptive-block compact path + CLI helper.
**Posture:** READ-ONLY. No code changed.

## Headline

Three commits are presentation-layer cleanups with ONE money-affecting seam: the disclaimer
re-enters the engine via `build_risk_raise_gate_ctx` ⇒ G1 (Clean Data) gate. The defensive
`min(|raw|,|adjusted|)` guard is sound for the BAND but G1 consumes only the band string, so
an over-disclaimer that softens `Critical Data Gap` unlocks a risk-raise. Band-softening is
pinned; band→G1→raise is not pinned end-to-end. Math invariants (R, NAV, exposure, PnL)
preserved; Mark §3 verbose contract holds on Critical residual.

## Findings

### F1 — Disclaimer reaches a money-affecting gate via band classification (P1)
`adaptive_risk_engine.py:519` — G1 Clean Data fails only on `Critical Data Gap`. `:585-591`
`build_risk_raise_gate_ctx` now feeds `pre_db_realized_pnl_estimate` into
`classify_broker_reconciliation`. The classifier's `min(|raw|,|adjusted|)` guard at
`telegram_formatters.py:1005` prevents UPWARD escalation, but a founder-supplied estimate that
softens `Critical` → other band flips G1 from fail→pass. CLAUDE.md hard constraint not
violated (math untouched) but the INPUT to a money-affecting gate is founder-tunable; the
`build_ctx → evaluate_gate` chain is not pinned end-to-end. **Fix direction:** integration
test pinning over-disclaim → band soften → risk-raise enabled AND disclaimer disclosure on
the raise surface. Optional defense-in-depth: G1 reads `adjusted_gap` numerically.

### F2 — Compact-path branch symmetrically safe for drawdown / down_fast (P3, OK)
`telegram_formatters.py:400-405` — compact requires `direction == 'hold'` AND
`evaluated is True` AND `allow_raise is False`. Verified against drawdown override at
`adaptive_risk_engine.py:824-843` (sets `direction="down_fast"` → falls through to verbose) and
the ladder-bug-fix at `:759-761` (gate allows raise but new_idx==curr_idx → hold + allow_raise=True
→ falls through to verbose). No bug; not pinned. **Fix direction:** add explicit
"gate-evaluated + allow_raise=True + ladder-clamped → verbose" fixture test.

### F3 — heat_factors filter assumes ⛔ is unique to gate reasons (P2)
`telegram_formatters.py:414-417` — compact path keeps `heat_factors` lines containing `"⛔"`.
The gate reason is prepended with `⛔ ` at `adaptive_risk_engine.py:820-822`; the drawdown
override REPLACES `heat_factors` with a `⛔`-prefixed entry at `:839`. No current collision
(drawdown path never reaches compact), but emoji-as-filter is fragile against future additions.
**Fix direction:** filter by structural key (`risk_raise_gate.reason` directly), not by emoji
prefix in `heat_factors`.

### F4 — Recon "band_softened" branch depends on English band string equality (P3)
`telegram_formatters.py:1079-1080` — `band_softened = (adjustment_applied and band != "Critical
Data Gap")`. Today `:1018-1025` always sets `band` to the English literal, so safe. **Fix
direction:** key the softened branch on `not is_critical_band(band)` helper.

### F5 — MRVL `evaluate_position_engine` `missing_data` (P2)
`engine_core.py:425-426` — `get_cached_history` returns empty DataFrame on ANY yfinance
exception (`:88-90` bare `except: pass`); `evaluate_position_engine` short-circuits when
`len(hist) < 60`. Empty DataFrames are NOT cached (`:85-87` requires non-empty), so the next
minute re-fetches. This is a one-cycle SKIP, NOT deeper fragility — but the bare `except:`
masks network/rate-limit/parse errors as routine "missing_data". **Fix direction:** log
exception type/symbol at WARN; consider short-TTL negative caching to avoid hammering.

### F6 — Win-Rate 56% → 67% jump structurally explainable but knife-edge (P2)
`adaptive_risk_engine.py:316-319` — `_window_stats` derives WR off `is_win`/`stat_bucket`. L50
sample 11→10 via `_is_disc` at `:640-644`. WR 6/11 → 7/10 implies ONE LOSS re-bucketed out
AND ONE WIN backfilled in — consistent with a backlog sweep. Fragile: AGENTS.md #8 is one
`stat_bucket` flip away from a 10-point KPI swing. **Fix direction:** log
`(campaign_id, old_bucket, new_bucket, ts)` on every bucket change after first publication.

### F7 — Profit Factor 3.5x → 5.6x jump verified plausible (P2)
`adaptive_risk_engine.py:325-332` — PF = gross_profit / gross_loss. A loss re-bucketed OUT
removes from `gross_loss`; a win added IN adds to `gross_profit`. If removed loss ≈ avg_loss
and added win ≈ avg_win then `(gp+avg_win)/(gl−avg_loss) ≈ 5.6` vs `3.5` — consistent.
**Concern:** the `math.inf` sentinel at `:330` remains the same divergence Sprint-25 F6
flagged (analytics inf vs dashboard 99.0). NOT regressed; the new compact path doesn't render
PF so the divergence remains gated to verbose. **Fix direction:** same as Sprint-25 F6 —
document the convention; do not "clean up" `math.inf`.

### F8 — JPM ALGO 15-min + 25-min downtrend anti-spam intact (P3, OK)
`risk_monitor.py:1111-1129` — `algo_loss_streak` increments per ~5-min run. Yellow at
`streak>=3 AND not _alerted_yellow` (≈15 min), Orange at `streak>=5 AND not _alerted_orange`
(≈25 min). Per-position dedup flags prevent re-fire until `_new_streak == 0` (`:1127-1129`).
Msg 18844 yellow + 18845 orange at identical Open R −0.02R is TWO distinct level transitions,
not duplicates. AGENTS.md #7 preserved. **No action.**

### F9 — Sizing Leak alert fired correctly on MRVL (P3, OK)
`risk_monitor.py:1147-1159` — MRVL 0.41x < `SIZING_LEAK_THRESHOLD = 0.65` (`:70`); one-time
flag `sizing_leak_alerted` at `:1159`; 48h post-raise settle suppression at `:1151-1154`
correctly skipped. **No action.**

## Cross-cut convergence

- F1 + F-YTD design: defended at the classifier (min-guard) and the surface (line 1099-1102
  always shows raw+adjusted), but the GATE consumes the band string — founder-tunable input
  reaches a money-affecting decision via one layer of indirection.
- F5 + F6 + F7: all converge on small-N fragility. Per-position yfinance flake → 1-cycle
  missing_data; per-trade re-bucketing → multi-point KPI swing. Both recoverable; both deserve
  audit-trail logging for forensic clarity.
- F2 + F3: compact-path filter is correct today but uses two implicit invariants (direction
  semantics, ⛔ uniqueness in heat_factors) not pinned by tests.

## Math invariants preserved

- R, NAV, exposure, PnL — UNCHANGED. `engine_core`/`analytics_engine` untouched;
  `adaptive_risk_engine` gained ONE additive kwarg default 0 ⇒ byte-identical when unset.
  LOCKED-April fixture unaffected (analytics doesn't consume the classifier).
- Mark §3 honesty preserved on verbose path (Critical residual keeps the full preamble).
- AGENTS.md #8 (ALGO/DATA_INCOMPLETE excluded from WR/Expectancy) preserved at
  `adaptive_risk_engine.py:640-644`.
- AGENTS.md #7 (per-position anti-spam dedup) preserved at `risk_monitor.py:1111-1129`.

## Out-of-scope but flagged

- Sprint-25 F1/F2 SELL/BUY side-vs-quantity-sign divergence — not touched, still latent.
- `get_cached_history` bare `except:` — pre-existing; downstream of F5. Worth Wave-3 ops.
- `pre_db_realized_pnl_estimate` is a single scalar — no per-symbol/per-period granularity.

## Sign-off

Three commits land cleanly (2564/0 CI), additive contracts. No P0. One P1 (F1: disclaimer →
G1 chain not pinned end-to-end). Three P2 (F3, F5, F6/F7: emoji-as-filter, bare yfinance
except, small-N KPI swings). Remaining items P3 / OK.

— ENGINE team (read-only review; no code/tests changed; no commit/push).
