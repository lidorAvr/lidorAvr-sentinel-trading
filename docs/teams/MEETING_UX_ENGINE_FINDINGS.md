# Meeting UX — ENGINE Findings (review of 3ac93e8 / fdd4e84 / e9872f8)

**Date:** 2026-05-21 · **Branch:** `claude/review-system-audit-FBZ2h` · **Discipline:** ENGINE.
**Scope:** F-YTD recon-classifier disclaimer + adaptive-block compact path + CLI helper.
**Posture:** READ-ONLY. No code changed.

## Headline

Three commits are presentation-layer cleanups with ONE money-affecting seam: the disclaimer
re-enters the engine via `build_risk_raise_gate_ctx` ⇒ G1 (Clean Data) gate. The defensive
`min(|raw|,|adjusted|)` guard is sound for the BAND but the GATE consumes only the band string,
so an over-disclaimer that softens `Critical Data Gap` → anything else does unlock a risk-raise.
This is the design choice — the test suite pins it — but the dependency chain needs a finding.
Otherwise the math invariants (R, NAV, exposure, PnL) are preserved; the disclaimer is band-only.

## Findings

### F1 — Disclaimer reaches a money-affecting gate via band classification (P1)
`adaptive_risk_engine.py:519` — G1 Clean Data fails only on `Critical Data Gap`. `:585-591`
`build_risk_raise_gate_ctx` now feeds `pre_db_realized_pnl_estimate` into
`classify_broker_reconciliation`, which is the SAME band string G1 reads. The classifier's
`min(|raw|,|adjusted|)` defensive guard at `telegram_formatters.py:1005` prevents UPWARD
escalation, but a founder-supplied estimate that exceeds the residual flips
`Critical` → `Balanced`/`Minor`/`Material` and G1 transitions from fail → pass. CLAUDE.md hard
constraint (R/NAV/exposure math without tests) is not violated — math is untouched — but the
INPUT to the G1 decision is now founder-tunable. The classifier-level tests pin softening
behavior; no test pins the full `build_risk_raise_gate_ctx → evaluate_risk_raise_gate` end-to-end
behavior when the disclaimer is configured. **Fix direction:** add an integration test asserting
that an over-disclaim that softens the band does enable risk-raise, AND that the surfaced
disclaimer (line 1099-1102) appears wherever the raise actually fires. Optionally: G1 could
read `adjusted_gap` numerically rather than the band string, so a softened-by-disclaimer
Critical-residual still blocks (defense-in-depth).

### F2 — Compact-path branch is symmetrically safe for drawdown / down_fast (P3, OK)
`telegram_formatters.py:400-405` — `gate_clamped_hold` requires `direction == 'hold'` AND
`gate_info.evaluated is True` AND `allow_raise is False`. Verified against the drawdown
override path at `adaptive_risk_engine.py:824-843`: when drawdown fires, `direction` becomes
`"down_fast"`, so the compact branch correctly does NOT swallow the drawdown verbose block.
Also verified the ladder-bug-fix at `adaptive_risk_engine.py:759-761`: when gate allows the
raise but `new_idx == curr_idx`, direction reverts to hold while `allow_raise=True`, so the
compact branch does not fire (verbose path correctly explains the natural hold). No bug — but
this safety property is not pinned by a unit test. **Fix direction:** add an explicit fixture
test "gate-evaluated + allow_raise=True + ladder-clamped → verbose path".

### F3 — heat_factors filter assumes ⛔ is unique to gate reasons (P2)
`telegram_formatters.py:414-417` — compact path iterates `heat_factors` and keeps lines containing
`"⛔"`. At `adaptive_risk_engine.py:820-822` the gate reason is PREPENDED with `⛔ `, and at
`:839` the drawdown auto-cut override REPLACES `heat_factors` with `[f"⛔ {dd['reason']}"]`. The
compact branch never fires in the drawdown path (direction=down_fast), so no current collision —
but any future addition of a ⛔-prefixed factor to the normal-hold flow would leak into the
compact line. **Fix direction:** filter by structural key (`risk_raise_gate.reason` directly)
not by the emoji prefix in `heat_factors`. The emoji-as-filter is fragile.

### F4 — Recon "band_softened" branch depends on band string equality (P3)
`telegram_formatters.py:1079-1080` — `band_softened = (adjustment_applied and band != "Critical Data Gap")`.
The English band literal is hard-coded; if the classifier were ever to localize the English
band into Hebrew on the `band` (not `band_he`) field, the branch would silently invert. Today
this is correct — classifier at `:1018-1025` always sets `band` to the English string. **Fix
direction:** key the softened branch on `not is_critical_band(band)` helper, or use the existing
`band_he`/`band` pair consistently.

### F5 — MRVL `evaluate_position_engine` `missing_data` (P2)
`engine_core.py:425-426` — `get_cached_history` returns empty DataFrame on ANY yfinance exception
(`engine_core.py:88-90` bare `except: pass`). `evaluate_position_engine` then short-circuits with
`missing_data` when `len(hist) < 60`. This is a one-cycle SKIP — the next minute's poll re-tries
the same `yf.Ticker(...).history(...)` call (TTL 300s on cache MISS does NOT cache the empty
DataFrame: line 85-87 caches only when `hist is not None and not hist.empty`). MRVL recovery is
the next successful yfinance call. NOT a deeper engine fragility — but the bare `except:` at
`:88` silently swallows every error class (network, rate-limit, parse). **Fix direction:** log
the exception type/symbol at WARN level so a sustained yfinance outage is visible in ops, not
masked as routine "missing_data" per-position; consider negative-result caching with short TTL
to avoid hammering on persistent failures.

### F6 — Win-Rate 56% → 67% jump is structurally explainable but knife-edge (P2)
`adaptive_risk_engine.py:316-319` — `_window_stats` derives WR off `is_win`/`stat_bucket`. Chat
log shows L50 sample 11 → 10 (`stat_base="report_window"`, so `disc_camps` = filtered
campaigns). A single trade re-bucketed by `_is_disc` (line 640-644: `is_stat_countable(bucket)`
OR `setup_type != ALGO`) shifts both numerator and denominator. With small N, |ΔWR| ≈
|win_delta·11 − wins·1| / (10·11) — a 1-trade swing on N=11 moves WR by 5-9 points; observed
+11 implies ONE LOSS re-bucketed out AND ONE WIN added in (6/11 → 7/10), which is consistent
with a backlog completion sweep that both re-classified and back-filled. Stable IF the
re-bucketing was deterministic; fragile because Prime Directive #8 (DATA_INCOMPLETE/ALGO excluded
from WR) is one stat_bucket flip away from a 10-point swing. **Fix direction:** when a campaign's
`stat_bucket` changes after first publication, log the (campaign_id, old_bucket, new_bucket, ts)
to an audit trail so the founder can reconcile the WR jump to a specific event.

### F7 — Profit Factor 3.5x → 5.6x jump verified plausible (P2)
`adaptive_risk_engine.py:325-332` — PF = gross_profit / gross_loss. A loss re-bucketed OUT
removes that PnL from `gross_loss`, AND a win added IN adds to `gross_profit`. Math: if the
removed loss was ≈ avg_loss and the added win is ≈ avg_win, then PF jumps by
`(gp + avg_win)/(gl − avg_loss) ≈ 5.6` vs `gp/gl = 3.5` — consistent. **CONCERN**: `math.inf`
sentinel at `:330` is the same divergence Sprint-25 F6 flagged (analytics_engine uses inf;
dashboard `_bucket_stats` uses 99.0). NOT regressed by these commits but the new compact path
in `fmt_adaptive_risk_block` does not render PF, so the inf-vs-99 divergence remains gated to
the verbose path. **Fix direction:** same as Sprint-25 F6 — document the convention; do not
"clean up" `math.inf` (LOCKED-April PF 2.6262 depends on this branch).

### F8 — JPM ALGO 15-min + 25-min downtrend anti-spam intact (P3, OK)
`risk_monitor.py:1111-1129` — `algo_loss_streak` counter increments per run (~5 min). Yellow
fires at `streak >= 3 AND not _alerted_yellow` (≈15 min), Orange at `streak >= 5 AND not _alerted_orange`
(≈25 min). Per-position dedup flags (`algo_streak_alerted_yellow` / `algo_streak_alerted_orange`)
prevent re-fire until `_new_streak == 0` (line 1127-1129). The chat log evidence (msg 18844
yellow + 18845 orange, identical Open R −0.02R) is consistent with the streak crossing both
thresholds in the same poll-cycle window — TWO distinct level transitions, not duplicates.
AGENTS.md #7 (per-position dedup flag) preserved. **No action required.**

### F9 — Sizing Leak alert fired correctly on MRVL (P3, OK)
`risk_monitor.py:1147-1159` — MRVL at 0.41x target risk vs threshold `SIZING_LEAK_THRESHOLD =
0.65` at `:70`. `sizing_leak_alerted` flag at `:1159` ensures one-time fire. The 48h
post-raise settle suppression at `:1151-1154` is correctly skipped (not in settle). **No action.**

## Cross-cut convergence

- F1 + F-YTD design: the disclaimer is correctly defended at the CLASSIFIER (min-guard) and at
  the SURFACE (line 1099-1102 always shows raw + adjusted), but the GATE consumes the band
  string — a layer of indirection that is doctrinally clean but lets founder-tunable input
  reach a money-affecting decision.
- F5 + F6 + F7 converge on a single fragility: small N. Per-position yfinance flake produces
  a 1-cycle missing_data; per-trade re-bucketing produces a multi-point KPI swing. Both are
  recoverable; both deserve audit-trail logging for forensic clarity.
- F2 + F3: the compact-path filter is correct today but uses two implicit invariants (direction
  semantics, ⛔ uniqueness in heat_factors) that are not pinned by tests.

## Math invariants preserved

- R, NAV, exposure, PnL — all UNCHANGED by these commits. `engine_core`/`analytics_engine`
  untouched; `adaptive_risk_engine` gained ONE additive kwarg with default 0 ⇒ byte-identical
  for any deployment that doesn't set the config field. LOCKED-April fixture unaffected
  (analytics path doesn't consume the classifier).
- Mark §3 honesty contract preserved on the verbose path (Critical residual still gets the full
  "cause unverified / manual verification required" preamble).
- AGENTS.md #8 (ALGO/DATA_INCOMPLETE excluded from WR/Expectancy) preserved — `_is_disc` filter
  at `adaptive_risk_engine.py:640-644` is unchanged.
- AGENTS.md #7 (anti-spam per-position dedup) preserved — Phase-4 ALGO Oversight at
  `risk_monitor.py:1111-1129` still gates by `algo_streak_alerted_*` flags.

## Out-of-scope but flagged

- Sprint-25 F1/F2 SELL/BUY side-vs-quantity-sign divergence — NOT touched, still latent.
- `get_cached_history` bare `except:` swallowing all exceptions — pre-existing, the MRVL
  missing_data is downstream of this. Worth a separate Wave-3 ops finding.
- `pre_db_realized_pnl_estimate` is a single scalar; it does not distinguish per-symbol or
  per-period. If the founder ever needs partial pre-DB backfill (e.g., one symbol), the
  current model can't represent it — the design doc itself flags per-trade backfill as the
  long-term path.

## Sign-off

- Three commits land cleanly with 2564/0 CI and additive contracts. No P0.
- One P1 (F1): disclaimer reaches G1 via band string; not blocking, but needs an
  end-to-end test pinning the gate-raise interaction.
- Three P2 (F3, F5, F6/F7): fragility around emoji-as-filter, bare yfinance except, and
  small-N KPI swings. Recoverable; deserves logging not code rewrite.
- Remaining items P3 / OK.

— ENGINE team (read-only review; no code/tests changed; no commit/push).
