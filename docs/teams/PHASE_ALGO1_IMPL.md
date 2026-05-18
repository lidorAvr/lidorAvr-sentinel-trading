# Phase ALGO-1 — IMPL (W-A2 + W-A3)

**Status:** BUILT, parent-pending. Tree left DIRTY (no commit/push per scope).
Spec: `docs/teams/PHASE_ALGO1_SCOPE.md`. Evidence: `docs/teams/ALGO_INVESTIGATION_1.md`.
Live HEAD at build: `bddad08`. Baseline suite 2088/0 cov 72.02%.

---

## W-A2 — R-ALGO-2 recon-key bug (CLOSURE-FIX)

### Producer key — VERIFIED from source

`adaptive_risk_engine.compute_closed_campaigns()` emits each closed campaign's
realized PnL under the key **`total_pnl_usd`** —
`adaptive_risk_engine.py:205`:

```python
"total_pnl_usd": round(float(total_pnl), 2),
```

where `total_pnl = sells["pnl_usd"].sum()` (`adaptive_risk_engine.py:172`). It
**never** emits `net_pnl` (that is a different function's key —
`analytics_engine._aggregate_campaigns`, `analytics_engine.py:474`).

**Semantics == the dashboard's realized quantity:** the dashboard oracle is
`camp_df['pnl_usd'].sum()` (`dashboard.py:424`). Over a fully-closed campaign
the producer's `round(sells['pnl_usd'].sum(), 2)` is the same realized
quantity summed per closed campaign. Confirmed equal on the fixture
(both `+150.00`). Key/semantics matched the dashboard's realized quantity —
no STOP/guess condition triggered.

### Change — `telegram_portfolio.py:473` (one site only)

Before:
```python
_db_net_pnl = sum(float(c.get("net_pnl", 0) or 0) for c in _closed_for_rec)
```
After (+ a provenance comment block at :473):
```python
_db_net_pnl = sum(float(c.get("total_pnl_usd", 0) or 0) for c in _closed_for_rec)
```

`c.get("net_pnl", 0)` matched **no** producer key ⇒ `_db_net_pnl` was silently
**always `0.0`**, dropping ALL realized closed-campaign PnL and diverging from
the dashboard. The one-key fix makes חדר-מצב's recon realized term equal the
dashboard oracle. No surrounding flow refactored. Authorized behavior change
only: the חדר-מצב recon number now matches the dashboard.

### Parity proof (pinned)

`tests/test_phase_algo1_recon_and_sample.py::TestWA2ReconKeyParity`:
- `test_producer_emits_total_pnl_usd_not_net_pnl` — producer key contract.
- `test_prefix_net_pnl_read_was_always_zero` — pre-fix sum == `0.0`.
- `test_postfix_recon_matches_dashboard_realized_oracle` — post-fix
  `_db_net_pnl` (`+150.00`) **==** dashboard oracle
  `df[closed_ids]['pnl_usd'].sum()` (`+150.00`); strictly `!= 0.0`.
- `test_recon_classifier_band_now_reflects_truth` — same unchanged
  classifier (`tf.classify_broker_reconciliation`): pre-fix gap `$150`
  (mis-band), post-fix gap `$0.00` ⇒ truthful `Balanced`.

---

## W-A3 — R-ALGO-3 L50 honesty (HONESTY-FIX, presentation-only)

### Helper reused VERBATIM (CALLED, never modified)

`engine_core.get_sample_size_context(countable_trades) -> dict` with
`label` (Hebrew), `warning`, `usable`, `significant`
(`engine_core.py:1205`). For `<30` it returns
`"סטטיסטיקה ראשונית בלבד — אין לאשר הגדלת סיכון אגרסיבית"`. `engine_core.py`
git-diff is EMPTY (lazy `import engine_core` inside the helper; called only).

### Change — `telegram_formatters.py`

New private helpers `_l50_true_sample(risk_rec)` (reads the same true L50
sample the existing Win-Rate sub-lines use: `l50_stats['n']` →
`n_used_50`/`n_trades`) and `_l50_sample_honesty_line(n)` (returns `None`
when `n >= 50` ⇒ existing literal stays byte-identical; else an honest
disclosure line `"⚠️ L50 מבוסס מדגם חלקי — מדגם נוכחי: N/50 — {helper label}"`
reusing the helper's own wording).

Wired at the two confirmed lying sites — additive only:
- `fmt_adaptive_risk_block` after the `S9(9)…L50(50)` score line
  (`telegram_formatters.py` ~:204 origin) — appends the disclosure only
  when true sample `< 50`.
- `fmt_heat_thermometer` after the bare `L50 [bar] score` block
  (~:435 origin) — appends the disclosure only when true sample `< 50`.

ZERO math/KPI change; no new UX invented (helper wording reused).

### Honesty proof (pinned)

`tests/test_phase_algo1_recon_and_sample.py::TestWA3L50SampleHonesty`:
- `test_sample_ge_50_byte_identical_adaptive_block` /
  `…_heat_thermometer` — true sample `>=50` ⇒ the L50 line is
  **byte-identical** to the reconstructed pre-fix literal; no disclosure.
- `test_sample_lt_50_honest_disclosure_adaptive_block` /
  `…_heat_thermometer` — true sample `9` ⇒ `"מדגם נוכחי: 9/50"` + the
  helper's verbatim `label` present; never a bare misleading L50.
- `test_helper_called_not_modified_contract` — pins the helper's `<30`
  contract wording (called verbatim, unmodified).

---

## ⟨MARK⟩ / charter conformance

- ALGO observe-only **unchanged** — only a DISPLAY/recon read + a label
  touched; no exit-management (DEC-20260511-001 #8). Pinned by
  `TestAlgoSegregationObserveOnlyUnaffected`.
- ALGO segregation intact — ALGO stays not-stat-countable
  (`is_stat_countable(STAT_BUCKET_ALGO) is False`); ALGO realized PnL
  flows only through the disclosed `(all)` recon total exactly as the
  dashboard does (investigation §3 disclosed-not-mixed).
- Honesty (CLAUDE.md #1) — fallback/partial sample now disclosed, not
  presented as exact truth.

## Confirmations

- NO byte-locked file modified — `git diff --stat` empty for
  `engine_core.py` / `analytics_engine.py` / `period_data_probe.py` /
  LOCKED `tests/test_real_data_april_regression.py` /
  `tests/_byte_lock_baselines/*` / `docker-compose.yml` /
  `telegram_bot_secure_runner.py` / migrations. `engine_core.py` 0-diff
  (helper CALLED only).
- Only `telegram_formatters.py` + `telegram_portfolio.py` modified
  (the two authorized edits) + new additive
  `tests/test_phase_algo1_recon_and_sample.py`.
- LOCKED April byte-identical: `test_real_data_april_regression.py`
  2 passed (8 / +$180.49 / WR .375 / PF 2.6262 / excl 2). Sprint-22/23/24
  + C1/C2/B3/Arch-F1/NAV-Unify/Sprint-27 W1/W3 invariants intact (full
  suite green).
- No addition / schema / migration. Only the two authorized behavior
  changes; everything else (incl. broker-fresh report numbers,
  `>=50` L50 label) byte-identical.
- Full suite `python -m pytest -q -p no:cacheprovider`: **2101 passed,
  0 failed** (2088 baseline + 13 new ADD; none weakened — Mark 6.1).
- Exact CI command (`--tb=short -q --cov=engine_core
  --cov=adaptive_risk_engine --cov=analytics_engine --cov=addon_risk_engine
  --cov-report=term --cov-fail-under=67`, CI env): **2101 passed, 0
  failed, cov 72.02%** (≥67).

> Note: running the ad-hoc 3-file subset
> `test_real_data_april_regression.py test_telegram_portfolio.py
> test_sprint15_r_integrity.py` shows pre-existing mock-pollution
> failures that **reproduce identically with these changes stashed**
> (clean tree). Unrelated to W-A2/W-A3; the authoritative full-suite
> and exact-CI runs are 0-failed.
