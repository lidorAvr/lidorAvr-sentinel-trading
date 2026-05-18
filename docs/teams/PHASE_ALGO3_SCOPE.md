# Phase ALGO-3 — SCOPE / איפיון (T-B-1: classifier honors `stop_loss` fallback)

**Status:** SCOPE — founder-approved (T-B-1). Governed, Mark-gated, parent-verified, exact-CI post-commit clean tree. Source: `docs/teams/ALGO_INVESTIGATION_4.md` + the live census (7 manual DATA_INCOMPLETE; **exactly 1** — `AXGN_9394908015` — has a valid hidden `stop_loss>0` the classifier ignores; the other 6 have no stop in ANY field = legitimately excluded). Live code baseline HEAD `a5e2bd9` (suite 2175/0 cov 72.98%). No live financial values in any committed doc.

## The defect (confirmed, narrow)
`adaptive_risk_engine.py:~203-208,213` `compute_closed_campaigns` derives `original_campaign_risk` from `first_day.iloc[0].initial_stop` ONLY (`initial_stop > 0 and < base_price` for a long); when that fails ⇒ risk=0 ⇒ `classify_stat_bucket` ⇒ `DATA_INCOMPLETE` ⇒ excluded from S9/M21/L50/WR/Expectancy/Heat/the 4-gate. It **never reads the documented, populated `stop_loss` field** (DATA_CONTRACTS.md:25-26). Real but narrow: today exactly 1 manual campaign (AXGN) is wrongly excluded; going forward any manual trade whose stop is recorded in `stop_loss` (not `initial_stop`) is wrongly dropped.

## T-B-1 — fix (additive, precedence-preserving)
In `adaptive_risk_engine.py` at the risk-basis derivation (~:203): keep `initial_stop` as the FIRST source, **unchanged**. Add `stop_loss` as a **documented FALLBACK used ONLY when `initial_stop` does not yield a valid basis** (absent / ≤0 / ≥ base_price). The fallback MUST apply the SAME validity predicate as `initial_stop` (`stop_loss > 0 and < base_price` for the long basis — mirror the existing guard exactly) so a garbage/invalid `stop_loss` can NEVER fabricate a fake risk basis. `engine_core.py` (`classify_stat_bucket`/`is_stat_countable`) is BYTE-LOCKED — do NOT modify it; the fix is entirely in `adaptive_risk_engine.py` (feed it a correct `original_campaign_risk`; classification logic unchanged). ALGO segregation/observe-only UNCHANGED — ALGO campaigns are excluded by bucket/setup before this; the `-1` ALGO sentinel must NOT be "recovered" (it is not a valid `stop_loss>0 & <base_price`, and ALGO is filtered regardless).

## Byte-identity / proof obligations (named)
- **The 9 currently-countable manual campaigns + the LOCKED April regression fixture: byte-identical** — they pass via `initial_stop` today; precedence (initial_stop first) means the fallback is never reached for them ⇒ identical `original_campaign_risk`, identical stat_bucket, identical WR/Expectancy/PF/R/Heat/4-gate. LOCKED April 8/+$180.49/WR.375/PF2.6262/excl2 unchanged.
- **AXGN-class recovered:** a manual campaign with invalid/absent `initial_stop` but a valid `stop_loss>0 & <base_price` is now stat-countable (sample 9→10 on the live base).
- **No false recovery:** the 6 genuinely-stopless manual campaigns (no valid stop in `initial_stop` OR `stop_loss` OR `initial_risk_price`) STAY DATA_INCOMPLETE. A garbage `stop_loss` (≤0 or ≥ base_price) does NOT create a basis.
- **ALGO untouched:** ALGO_OBSERVED count/segregation unchanged; the `-1` sentinel not recovered.
- Sprint-22/23/24 + C1/C2/B3/Arch-F1/NAV-Unify/W1/W3/ALGO-1/ALGO-2/Sprint-30 invariants intact.

## Separate acceptance tests (`tests/test_phase_algo3.py`)
- initial_stop-valid campaign ⇒ risk basis + bucket byte-identical to pre-fix (the precedence proof).
- initial_stop invalid/absent + valid stop_loss ⇒ now countable (AXGN-class).
- no valid stop anywhere ⇒ still DATA_INCOMPLETE (the 6-class; no false recovery).
- garbage stop_loss (≤0 / ≥ base_price) ⇒ rejected, still DATA_INCOMPLETE.
- LOCKED April byte-identical; an ALGO campaign with initial_stop=-1 + any stop_loss ⇒ still ALGO_OBSERVED/excluded (no recovery).
No existing test deleted/weakened (Mark 6.1).

## Hard constraints (auto-FAIL)
`engine_core.py`/`analytics_engine.py`/`period_data_probe.py`/LOCKED April/`tests/_byte_lock_baselines/*`/`docker-compose.yml`/`telegram_bot_secure_runner.py`/migrations git-diff EMPTY. Report-period KPIs + LOCKED April + the 9 currently-countable byte-identical; ALGO observe-only; protection (cut/down/hold/4-gate) logic unchanged (this only widens a CORRECT risk basis, never weakens a gate); no Supabase mutation; no new message type. Full suite `python -m pytest -q` ≥ 2175, 0 failed (new tests only ADD). Exact CI command (CI env) post-commit on the clean tree → 0 failed, cov ≥67.

## Done = deploy-ready
T-B-1 landed, parent-verified, full CI-equivalent post-commit clean-tree 0-failed, byte-locked + report KPIs + LOCKED April + the 9 byte-identical, `docs/teams/PHASE_ALGO3_IMPL.md` written. Then return to the founder with ONE deploy command + the standing deferred reminder (L-1/tokens, OPS-1/2, F5) + the operational note (6 manual campaigns had NO stop logged — a data-entry lever, not code).
