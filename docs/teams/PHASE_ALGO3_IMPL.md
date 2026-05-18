# Phase ALGO-3 — IMPL / יישום (T-B-1: classifier honors `stop_loss` fallback)

**Status:** LANDED — parent-verified, full CI-equivalent post-commit on the
CLEAN tree 0-failed, byte-locked + LOCKED April + the 9 currently-countable
byte-identical. Scope: `docs/teams/PHASE_ALGO3_SCOPE.md` (governs). Code HEAD
`2d5f404` on `claude/review-system-audit-FBZ2h` (scope `77c940a`, baseline
`a5e2bd9` ALGO-2). No live financial values in this doc.

## What landed (the single production change)
`adaptive_risk_engine.py` `compute_closed_campaigns` — the risk-basis
derivation. `initial_stop` remains the **FIRST, byte-unchanged** source
(`init_sl > 0 and init_sl < base_price` ⇒ `round((base_price-init_sl)*base_qty,2)`).
ONLY the fall-through `else: original_campaign_risk = 0.0` was replaced with a
documented `stop_loss` **FALLBACK** applying the **IDENTICAL** validity guard
(`sl > 0 and sl < base_price`); on guard-fail it still resolves to `0.0`. Net
`+15 / −1`. `engine_core.py` (`classify_stat_bucket`/`is_stat_countable`)
called only — **byte-locked, untouched**.

## Why it is safe (precedence ⇒ byte-identity)
Because `initial_stop` is evaluated first and is completely unchanged, the new
fallback branch is **never reached** for any campaign that already had a valid
`initial_stop`. Therefore the 9 currently-countable manual campaigns and the
LOCKED April fixture produce an **identical** `original_campaign_risk`,
identical `stat_bucket`, identical WR/Expectancy/PF/R/Heat/4-gate. The change
can ONLY widen a CORRECT risk basis (recover a campaign that was wrongly 0),
never weaken a gate or alter a protection (cut/down/hold) path.

## Behavior delta (authorized, narrow)
- **Recovered:** a manual campaign with absent/invalid `initial_stop` but a
  valid `stop_loss>0 & <base_price` is now stat-countable (the live
  `AXGN_9394908015` class; manual sample 9 → 10 on the live base).
- **No false recovery:** the 6 genuinely-stopless manual campaigns (no valid
  stop in `initial_stop` OR `stop_loss`) stay `DATA_INCOMPLETE`. A garbage
  `stop_loss` (≤0 or ≥ base_price) does NOT fabricate a basis.
- **ALGO untouched:** the `-1` sentinel fails the `>0` guard and ALGO is
  bucket/setup-filtered before risk is consulted ⇒ ALGO observe-only /
  segregation unchanged; not recovered.

## Proof obligations — verified (parent, independent)
- Full suite (CI env, parent's own run): **2186 passed / 0 failed**
  (2175 baseline + 11 new ADD-only).
- Exact CI command POST-COMMIT on the **clean tree**:
  `2186 passed`, **coverage 73.04% ≥ 67%**, 0 failed.
- byte-lock + LOCKED April selection: **26 passed / 0 failed**.
- Protected-set git-diff EMPTY: `engine_core.py`, `analytics_engine.py`,
  `period_data_probe.py`, LOCKED `tests/test_real_data_april_regression.py`,
  all `tests/_byte_lock_baselines/*`, `docker-compose.yml`,
  `telegram_bot_secure_runner.py`, migrations — confirmed.
- `git diff --name-only` ⇒ only `adaptive_risk_engine.py` (+ new
  `tests/test_phase_algo3.py`).
- New `tests/test_phase_algo3.py` (11) pins all 5 scope cases: precedence
  byte-identity, AXGN-class recovery, no-false-recovery (6-class), garbage
  `stop_loss` rejected, ALGO `-1` not recovered. No existing test
  deleted/weakened (Mark 6.1).

## Operational note (NOT code — a data-entry lever for the founder)
6 manual closed campaigns had **NO stop logged in any field**
(`initial_stop`/`stop_loss`/`initial_risk_price`). They remain — correctly —
`DATA_INCOMPLETE` and excluded from the statistics. This is a data-entry
discipline lever (record a stop on every manual entry), not a code defect.

## Deploy
Behavior-narrowing risk-basis widening; production wiring unchanged
(`docker-compose.yml` byte-identical). Standard pull-and-recreate-all-services
per `docs/DEPLOYMENT_RUNBOOK.md` (the deployed host tracks the branch).
