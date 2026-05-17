# Phase Engine-P2/P3 — FULL — IMPLEMENTATION RECORD

**Status:** EXECUTED (tree left dirty; parent does the governed consolidation/commit
+ the post-commit clean-tree CI-equivalent check — the Sprint-24 lesson).
**Branch:** `claude/review-system-audit-FBZ2h` (clean at `89c4e1a` pre-edit).
**Authority:** founder-approved scope `docs/teams/PHASE_ENGINE_P2P3_SCOPE.md` option
**(a) FULL** + **Decision F5 = (i) relative `>= 0.01`**; Sprint-25 Engine audit
F4/F5/F6/F7/F9; Mark Sprint-25 rulings (CLOSURE-FIX founder-gated).
**Classification:** F4 + F5 = CLOSURE-FIX (founder-decision-required) — a genuinely
latent silent-money-corruption defense + a razor-edge boundary fix; F6/F7/F9 = DOC-ONLY
polish; F8 = OUT (untouched). No new feature/flag/command/metric/schema (Mark Ruling 2).

---

## F4 — exact-`trade_id` dedup (governed; 3 sites)

A re-exported / double-synced SELL row is summed twice. F4 adds a guarded
`.drop_duplicates(subset=["trade_id"], keep="first")` on the per-campaign working
frame BEFORE aggregation, applied ONLY when a `trade_id` column exists (absent ⇒
no-op, never raises). **Provable byte-identical when there are no duplicate
`trade_id`s** (LOCKED April fixture + current prod per DEC-019): drop_duplicates on
an all-unique key returns the same rows in the same order ⇒ identical aggregation.
Behavior changes ONLY on the duplicated-row input.

### Site 1 — `analytics_engine._aggregate_campaigns`
`analytics_engine.py` — inside `for cid, grp in closed.groupby("campaign_id"):`,
immediately AFTER the loop header and BEFORE the A3 comment / `buys`/`sells`/`net_pnl`.

**Before:**
```python
    for cid, grp in closed.groupby("campaign_id"):
        # A3 (DEC-20260516-021 Tier-A, comment-only): `buys` is
```
**After (10 explanatory `#` lines + 2 code lines added; ZERO removed):**
```python
    for cid, grp in closed.groupby("campaign_id"):
        # Phase-Engine-P2/P3 F4 (CLOSURE-FIX, founder-gated): drop an
        # ... (10 comment lines) ...
        if "trade_id" in grp.columns:
            grp = grp.drop_duplicates(subset=["trade_id"], keep="first")
        # A3 (DEC-20260516-021 Tier-A, comment-only): `buys` is
```

### Site 2 — `adaptive_risk_engine.compute_closed_campaigns`
`adaptive_risk_engine.py` — inside the `for cid, group in df.groupby("campaign_id"):`
loop, AFTER the `if pd.isna(cid): continue` and BEFORE the Phase-C2 F1 split
(`ec.split_side_first(group)`). Added the same guarded dedup on `group`. The C2
`split_side_first` classifier, dates, first-BUY basis, ALGO/`stat_bucket` handling
are byte-identical otherwise (NOT baseline-locked; covered by `--cov`).

### Site 3 — `engine_core.get_open_positions_campaign`
`engine_core.py` — inside `for cid, group in valid_df.groupby("campaign_id"):`,
AFTER `group = group.sort_values(["trade_date", "trade_id"])` and BEFORE
`split_side_first(group)`. Added (matching engine_core's dense one-liner style):
```python
            if "trade_id" in group.columns: group = group.drop_duplicates(subset=["trade_id"], keep="first")
```
Every other line of `get_open_positions_campaign` / the rest of `engine_core.py`
is byte-identical (C2 `split_side_first`, `net_qty`, `realized_pnl`, `first_day_buys`,
`base_qty`, `avg_price`, `sl`/`init_sl`, `has_sells`, the output dict — untouched).

### Governed byte-lock ritual #1 — `analytics_engine.py` (Sprint-24 Wave-2b style)
- `tests/test_sprint24_wave2_refactor.py::TestAnalyticsEngineAppendOnly`: added the
  CLOSED-literal `_F4_REMOVED = frozenset()` (F4 is strictly append-only on
  analytics_engine — ZERO removed/modified lines) and `_F4_ADDED` frozenset of the
  EXACT `.strip()`-ed F4 NON-comment added lines, verbatim from the real
  `git diff -- analytics_engine.py`:
  - `if "trade_id" in grp.columns:`
  - `grp = grp.drop_duplicates(subset=["trade_id"], keep="first")`
  (the 10 explanatory `#` lines already pass the UNCHANGED comment branch of
  `test_every_added_line_is_comment_or_authorized_b1b3`).
- Added `- self._F4_REMOVED` to the removed-allowlist `continue`/difference and
  `and a.strip() not in self._F4_ADDED` to the added-allowlist `continue` — **no
  existing Sprint-20/21/22/24 clause modified** (the `_B1B3_*` sets, their `continue`
  clauses, `test_b1_b3_helpers_introduced_and_provable`, the period_data_probe /
  engine_core untouched tests are byte-unchanged; only NEW closed sets + their
  clauses ADDED).
- Added the Sprint-25-F4 self-reference hardening
  `test_f4_dedup_introduced_and_paired_proof_bound` (modeled on the Sprint-24
  `test_b1_b3_helpers_introduced_and_provable` precedent): binds the F4 dedup into
  `_aggregate_campaigns`, asserts `_F4_REMOVED == frozenset()` / the exact
  `_F4_ADDED`, and asserts the NEW paired proof `tests/test_phase_engine_p2p3.py`
  EXISTS + defines `class TestPhaseEngineP2P3` + is `--collect-only` collectible
  (the allowlist can never exist while the proof is deleted/gutted).
- Regenerated `tests/_byte_lock_baselines/analytics_engine.py.baseline` to the new
  authorized content (the Wave-2A SHA lock): `cp analytics_engine.py
  tests/_byte_lock_baselines/analytics_engine.py.baseline`.

  **cmp / SHA evidence:**
  ```
  $ cmp analytics_engine.py tests/_byte_lock_baselines/analytics_engine.py.baseline   # exit 0
  $ sha256sum analytics_engine.py tests/_byte_lock_baselines/analytics_engine.py.baseline
  2da07dea076053247a2db7d88b12add142efba5a4478ff51a89059054c2a8b79  analytics_engine.py
  2da07dea076053247a2db7d88b12add142efba5a4478ff51a89059054c2a8b79  tests/_byte_lock_baselines/analytics_engine.py.baseline
  ```
  Identical SHA256 ⇒ `baseline_line_delta("analytics_engine.py")` is `([], [])` on
  the authorized state (the Sprint-25 redteam
  `test_analytics_engine_delta_only_authorized_or_empty` GREEN); the allowlist sets
  remain the governance record constraining a future unauthorized edit.

### Governed byte-lock ritual #2 — `engine_core.py` (C2 SHA-baseline-regen precedent)
`engine_core.py` is guarded by the hard SHA256 guard
`bl.assert_byte_identical("engine_core.py")` (NOT an allowlist-delta path). Per the
`tests/_byte_lock_baseline.py` ritual + the `PHASE_C2_IMPL.md` §5 precedent, the
legitimate Mark-gated edit lands together with a regenerated baseline that is a
verbatim copy: `cp engine_core.py tests/_byte_lock_baselines/engine_core.py.baseline`.

**cmp / SHA evidence:**
```
$ cmp engine_core.py tests/_byte_lock_baselines/engine_core.py.baseline   # exit 0
$ sha256sum engine_core.py tests/_byte_lock_baselines/engine_core.py.baseline
944347331dc44289754fb4b760a1351566abc4a5775286c07fa5b5a42923f915  engine_core.py
944347331dc44289754fb4b760a1351566abc4a5775286c07fa5b5a42923f915  tests/_byte_lock_baselines/engine_core.py.baseline
```
Identical SHA256 ⇒ `assert_byte_identical("engine_core.py")` GREEN. **No other
baseline regenerated/touched:** `period_data_probe.py.baseline` and
`test_real_data_april_regression.py.baseline` git-diff EMPTY (0-diff, verified).
The redteam RED-on-unauthorized-edit direction is unaffected (it sandboxes a
synthetic pair, independent of the live engine bytes) — GREEN.

---

## F5 — partial-fill boundary (Decision i)

`adaptive_risk_engine.py` — `compute_closed_campaigns`, the residual close-test:

**Before:** `if (buys_qty - sells_qty) / buys_qty > 0.01:`
**After:**  `if (buys_qty - sells_qty) / buys_qty >= 0.01:` (+ an 8-line explanatory
comment naming Decision i).

So an EXACT 1%-residual campaign (e.g. 990/1000 sold, `(1000-990)/1000 == 0.01`) is
correctly NOT treated as closed — one share is still open. Byte-identical for
residual 0 (full close — LOCKED April), residual strictly > 1% (already open), and
residual strictly < 1% (already closed). ONLY the exact-1% boundary changes.
`adaptive_risk_engine.py` is NOT byte-locked.

---

## F6 / F7 / F9 — DOC-ONLY (no code) — `docs/DATA_CONTRACTS.md`

- **F7** — added to the **"Initial risk contract"** section (before "For ALGO
  trades:"): a note that `compute_original_campaign_risk`'s `round(..., 2)` is the
  deliberate, load-bearing 1R denominator — removing it BREAKS the LOCKED April PF
  `2.6262`; do NOT "clean up".
- **F6** — added after the `stat_bucket` paragraph (after the
  `compute_closed_campaigns` stat_bucket sentence): the **two intentional
  Profit-Factor conventions** — `analytics_engine` raw `math.inf` for zero-loss
  countable sets (DEC-021 lists this branch intentional / DO-NOT-TOUCH) vs the
  `99.0` sentinel that lives ONLY in dashboard `_bucket_stats`; do NOT "unify" one
  side (reconciliation trap).
- **F9** — added in the same block: out-of-order rows floor `days_held = max(1, …)`
  to 1, inflating `avg_r_per_day` / dev-score (display/score only — R itself is
  correct; the `max(1,…)` div-0 guard is itself correct); LOCKED fixture is ordered
  so byte-identical. No code change.
- Also added a short **F4** contract note in the same block (the new dedup
  convention) for future-agent honesty.

NO code change for F6/F7/F9.

## F8 — OUT, untouched

`period_data_probe.py` WS-C recoverable-candidate heuristic + the `-1`
`initial_stop` sentinel are **OUT of scope, DEFERRED, untouched** (Sprint-23
byte-locked; `period_data_probe.py` + its baseline git-diff EMPTY). Restated here
only.

---

## Named Ruling-3 paired proof — `tests/test_phase_engine_p2p3.py` (NEW)

`class TestPhaseEngineP2P3` (15 assertions, all GREEN; the file the analytics_engine
F4 allowlist self-reference hardening binds to). No existing test deleted/weakened
(Mark 6.1) — only ADDS:

- **F4 dedup identity (3 sites):** a duplicated-`trade_id` SELL frame →
  `compute_period_analytics` / `compute_closed_campaigns` /
  `get_open_positions_campaign` results equal the single-row no-dup result (the
  +$1000 campaign stays +$1000, NOT a double-counted +$2000 / phantom-open).
- **F4 identity on no-dup input:** LOCKED April **8 / +$180.49 / WR .375 /
  PF 2.6262 / excl 2** byte-identical + locked weekly (0 / excl 3 ALGO /
  −$37.234) byte-identical; April `trade_id`s pinned all-unique (the precondition
  that makes drop_duplicates a no-op); a partial-close control (residual qty 60
  stays open).
- **Sprint-22:** tz-aware == tz-naive full-dict unchanged post-F4.
- **F5 (Decision i):** parametrised residual 0% / 0.5% / **exactly 1.0%** / 1.5% →
  the exact-1% campaign is NOT closed (still open); 0% / <1% close as before; >1%
  open as before — pinned twice (the parametrised set + a tight 991/990/989
  boundary test that proves ONLY the exact-1% point flips). LOCKED April (residual
  0, full closes) byte-identical.

---

## ⟨MARK⟩ gate slots

- ⟨MARK Ruling 1.1 — money-math correct vs contract⟩: F4 removes a latent
  double-count (defensive integrity for a money system); F5 fixes a
  contract-wrong inclusive boundary; LOCKED April + DEC-019 reconciliation
  unchanged (no dup ids / all full closes ⇒ provable no-op). _____
- ⟨MARK Ruling 3.3 — LOCKED April byte-identical⟩: 8/+$180.49/WR.375/PF2.6262/excl2;
  `tests/test_real_data_april_regression.py` + its baseline 0-diff, GREEN. _____
- ⟨MARK Ruling 3.4 — Sprint-19/24 lock + paired proof intact⟩: no existing
  Sprint-20/21/22/24 clause modified; only the NEW closed `_F4_*` sets + clauses
  ADDED; `test_analytics_engine_git_diff_empty` + `TestSprint24B1B3ByteIdentical`
  + the new F4 self-reference hardening GREEN. _____
- ⟨MARK Ruling 3.5 — no R/NAV/exposure/campaign math change without proof⟩: F4 is a
  provable identity on no-dup input, F5 a provable no-op off the exact-1% point;
  named proof `tests/test_phase_engine_p2p3.py`. _____
- ⟨MARK Ruling 5.A — suite ≥ floor, 0 failed, no test weakened⟩: CI-equivalent
  command + CI env → **2008 passed, 0 failed** (≥ 1992 floor; new tests only ADD).
  _____
- ⟨MARK Ruling 5.B — CI-equivalent green⟩: exact CI command + CI env →
  **2008 passed, 0 failed**, coverage **71.92% ≥ 67%**. _____
- ⟨MARK Ruling 5.D.8/9 — no addition; behavior change only by gate⟩: CLOSURE-FIX,
  founder-approved scope (a) FULL + Decision F5 (i); no new feature/flag/metric. _____
- ⟨MARK governed baseline regeneration⟩: ONLY `analytics_engine.py.baseline` (SHA
  `2da07dea…`) + `engine_core.py.baseline` (SHA `944347331…`) regenerated as
  verbatim copies; `period_data_probe.py.baseline` /
  `test_real_data_april_regression.py.baseline` 0-diff. _____

---

## Explicit confirmations

- Modified files (exactly): `analytics_engine.py`, `adaptive_risk_engine.py`,
  `engine_core.py`, `docs/DATA_CONTRACTS.md`, `tests/test_sprint24_wave2_refactor.py`,
  `tests/_byte_lock_baselines/analytics_engine.py.baseline`,
  `tests/_byte_lock_baselines/engine_core.py.baseline`; NEW:
  `tests/test_phase_engine_p2p3.py`, `docs/teams/PHASE_ENGINE_P2P3_IMPL.md`.
- 0-diff (git): `period_data_probe.py`, `docker-compose.yml`, `migrations/`,
  `telegram_bot.py`, `telegram_callbacks.py`, `telegram_bot_secure_runner.py`,
  `account_state.py`, `tests/test_real_data_april_regression.py`,
  `tests/_byte_lock_baselines/period_data_probe.py.baseline`,
  `tests/_byte_lock_baselines/test_real_data_april_regression.py.baseline`.
- LOCKED April **8 / +$180.49 / WR .375 / PF 2.6262 / excl 2** byte-identical
  (no dup `trade_id`s ⇒ F4 dedup is identity; all full closes ⇒ F5 `>=` is a no-op);
  Sprint-22 tz / Sprint-23 probe / C1 dev-PIN / C2 `split_side_first` / B3
  `_coerce_numeric` / Arch-F1 reader / Sprint-24 B1/B3 / Wave-2A mechanism intact.
- Behavior change confined to F4-on-duplicated-`trade_id` input and F5-at-exact-1%
  residual. No new feature/flag/command/metric/schema. WS-C / `-1`-sentinel (F8)
  untouched.
- Only `analytics_engine.py.baseline` + `engine_core.py.baseline` regenerated; no
  existing lock clause weakened; redteam + Sprint-24 paired proof + the new F4
  self-reference hardening + all locks GREEN.
- Full suite under the EXACT CI command + CI env: **2008 passed, 0 failed**,
  cov **71.92% ≥ 67%**. (5 C1 dev-PIN tests fail ONLY in a bare local env without
  the CI `DEV_PIN`/env vars — pre-existing on the clean baseline `89c4e1a`,
  unrelated to F4/F5; GREEN under the binding CI-equivalent command.)
- NOT committed/pushed; tree left dirty for the parent's governed consolidation +
  the post-commit clean-tree CI-equivalent re-verification (the Sprint-24 lesson).
