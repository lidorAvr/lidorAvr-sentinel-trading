# Phase ALGO-2 — IMPL (T-B1 + T-C1 + T-C2), ONE coordinated pass

**Status:** BUILT, parent-verify pending. Live HEAD `53c0f73`. Tree LEFT DIRTY
(no commit/push — parent independently verifies + runs the post-commit
CI-equivalent on the clean tree). Source of truth: `PHASE_ALGO2_SCOPE.md`
(governs) + `ALGO_INVESTIGATION_3.md` (D1/D2 confirmed) + `ALGO_TEAM_CHARTER.md`
⟨memo⟩. No live financial values in this doc.

## Files touched (additive / opt-in only — every byte-locked path 0-diff)

| File | Change | Risk |
|---|---|---|
| `adaptive_risk_engine.py` | T-B1 safe fallback + INSUFFICIENT state; T-C1 4-gate + `_window_heat_score` opt-in insufficient signal; opt-in `stat_base_campaigns` (T-C2) | money-affecting, risk-NARROWING only |
| `report_scheduler.py` | NEW `_fetch_stat_base_df` (read-only longer rolling); `_compute_risk_rec` wires T-C2 base + T-C1 recon gate. `_fetch_trades_df` body 0-diff | medium (fail-safe) |
| `supabase_repository.py` | NEW `get_trades_since` — pure SELECT (no mutation) | low (read-only) |
| `telegram_formatters.py` | `_l50_sample_honesty_line` opt-in `stat_base` clause (T-A1 folded in) | low (presentation; byte-identical default) |
| `tests/test_phase_algo2.py` | NEW 30-test acceptance suite (ADD-only) | — |

Byte-locked git-diff EMPTY (verified): `analytics_engine.py`, `engine_core.py`,
`period_data_probe.py`, LOCKED April test, `tests/_byte_lock_baselines/*`,
`docker-compose.yml`, `telegram_bot_secure_runner.py`, migrations.

## T-B1 — D1 fix (the cold-start ALGO contamination)

`adaptive_risk_engine.py:459-460` `if not disc_camps: disc_camps =
closed_campaigns[:50]` was NOT `_is_disc`-filtered ⇒ in an all-ALGO / zero
stat-countable-manual window it fed ALGO performance into the founder's
discretionary S9/M21/L50 + risk-raise (inviolable-doctrine breach). The
unfiltered fallback is **removed**. `disc_camps` is now ALWAYS the
`_is_disc`-filtered set; when it is empty the engine sets
`insufficient_manual_sample = True` — the windows are all `n==0`, heat reads a
neutral non-raising score, `direction` is never "up", and the explicit flag is
consumed by the T-C1 Gate-2.

**Non-empty byte-identical proof:** the new code reaches the
insufficient/empty branch ONLY when the filtered disc set is empty (exactly the
cold-start path the old code unsafely back-filled). On every path where
`disc_camps` is non-empty (the live normal path) the disc set, windows, heat,
direction, ladder and drawdown math are unchanged. `tests/test_phase_algo2.py`
pins this against a **frozen copy of the pre-Phase engine**
(`_frozen_baseline_compute`, which deliberately keeps the OLD unsafe fallback):
`test_non_empty_disc_is_byte_identical_to_baseline` + the (8,2)/(5,5)/(1,9)/
(9,1) matrix assert every pre-existing result key/value is identical (only the
additive Phase keys differ). `test_all_algo_window_yields_insufficient_state`
pins the empty path: 10 ALGO winners ⇒ `insufficient_manual_sample`, all
windows `n==0`, `direction != "up"`.

## T-C1 — D2 fix (the founder/Mark 4-gate, risk-RAISE path ONLY)

`evaluate_risk_raise_gate(...)` enforces ALL FOUR before a step-up:
1. **G1 clean data** — reuse the EXISTING `classify_broker_reconciliation`
   band; `"Critical Data Gap"` / `"פער נתונים קריטי"` ⇒ no raise.
2. **G2 sufficient sample** — stat-countable MANUAL `len(disc_camps)` ≥
   `RISK_RAISE_MIN_MANUAL_SAMPLE = 20` (⟨memo⟩ "≥20, not 9"); the T-B1
   INSUFFICIENT state ⇒ fail outright.
3. **G3 positive expectancy** — `_window_expectancy_r(disc[:50])` ≥
   `RISK_RAISE_MIN_EXPECTANCY_R = 0.30` (⟨memo⟩); `None` (no clean per-R) ⇒
   fail ("clean truth before aggressiveness").
4. **G4 drawdown in control** — no active drawdown-cut AND `s9_loss_streak < 2`.

Any fail ⇒ `direction` clamps `"up"` → `"hold"` + an honest Hebrew reason
("שער X נכשל …"), surfaced via the EXISTING `heat_factors` renderer (no new
message TYPE). `_window_heat_score`'s `n==0 → 50.0` pretend-neutral is replaced
by an explicit `HEAT_INSUFFICIENT_DATA` sentinel **only when opt-in**
(`insufficient_signal=True`) — default 50.0 stays byte-identical.

**Strictly risk-NARROWING:** the gate is OPT-IN (`risk_raise_gate=None`
default), only ever clamps a `"up"` → `"hold"`, and NEVER touches
`drawdown_auto_cut`, `"down_fast"`, `"hold"`, the `RISK_LADDER` values, or
`update_risk_pct`. Pins: `test_smallest_n_all_win_now_blocked` (the N=3-all-win
that mechanically forced "up" is now `"hold"` on G2); `test_each_gate_fail_
blocks_up` (parametrised G1/G4); `test_gate2/3_*` (the ≥20 / ≥0.30R floors);
`test_all_pass_plus_heat_ge_60_still_raises` (all-green ⇒ "up" preserved);
`TestTC1ProtectionNeverWeakened` (down_fast / drawdown-auto-cut / hold / ladder
constants byte-identical with gate ON vs OFF).

## T-C2 — separate statistical base (report numbers byte-identical)

`report_scheduler._fetch_stat_base_df()` is a NEW, DISTINCT, READ-ONLY function
(it does NOT call `_fetch_trades_df` and does NOT touch the DEC-20260516-020
`weeks=8` report-period fetch). It pulls a longer rolling window via the new
read-only `supabase_repository.get_trades_since` (pure SELECT — no
insert/update/delete/upsert). `_compute_risk_rec` builds the longer
stat-countable MANUAL base from it and passes it as `stat_base_campaigns`;
`compute_adaptive_risk` computes S9/M21/L50 + the 4-gate off THAT base when it
has a non-empty disc set, else falls back to the report-window base
(byte-identical). The displayed per-period report KPIs + LOCKED April are
produced by `analytics_engine.compute_period_analytics` off the UNCHANGED `df`
and are not touched. The sample-honesty line now states the true base + N
(T-A1 clarity folded in), silent on the legacy path (byte-identical).

**Report-numbers byte-identical proof:** `_fetch_trades_df` body git-diff
EMPTY; `analytics_engine.py`/`engine_core.py`/LOCKED April test git-diff EMPTY;
`test_locked_april_regression_still_passes_untouched` re-asserts the founder
ground truth (8 / +$180.49 / WR .375 / PF 2.6262 / excl 2) through the LOCKED
fixture's own df; `test_byte_locked_files_unmodified` asserts the SHA baselines;
`test_report_period_fetch_untouched_weeks8` asserts the `weeks=8` lookback
literal is verbatim and the stat-base read is a distinct function;
`test_stat_base_repo_read_is_select_only` proves no mutation verb is issued.
T-C2 was feasible READ-ONLY without touching a byte-locked path ⇒ **NOT
re-scoped; shipped together with T-B1+T-C1.**

## Verification (this build, dirty tree — parent re-verifies on clean tree)

- New suite: `tests/test_phase_algo2.py` — 30 passed.
- Full suite `python -m pytest -q -p no:cacheprovider`: **2175 passed, 0
  failed** (2145 baseline + 30 new; no existing test weakened — Mark 6.1).
- Exact CI command (CI env) `--cov-fail-under=67`: **2175 passed, 0 failed,
  total coverage 72.98% ≥ 67%**.
- Byte-locked + report-period + LOCKED April git-diff EMPTY; ALGO observe-only
  (no entries/exits added — gating/disclosure only); no Supabase mutation
  (read-only `get_trades_since`); no new alert/message TYPE; non-empty-disc
  live path byte-identical (frozen-oracle proof).
