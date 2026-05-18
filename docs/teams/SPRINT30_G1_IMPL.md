# Sprint-30 G1 — IMPL: R-ALGO-2 finish (two-surface recon band divergence)

**Status:** BUILT, parent-pending. Tree left DIRTY (no commit/push per scope).
Spec: `docs/teams/SPRINT30_SCOPE.md` (G1). Evidence:
`docs/teams/ALGO_INVESTIGATION_1.md` (§1), `SPRINT29_RESEARCH_REPORTMAP.md`
(F1), `SPRINT29_ENGINE_REPORT_REVIEW.md` / `SPRINT29_DATA_REPORT_REVIEW.md`,
`PHASE_ALGO1_IMPL.md`, post-deploy export `/tmp/tg_report_2.txt`.
Live HEAD at build: `2db811c`. Baseline suite 2101/0 cov 72.02%.

> **DATA-SENSITIVITY:** structural only. No live NAV / P&L / position value is
> reproduced here. The two anchor magnitudes ($190.29 / $510.52) are named
> exactly as already public in `ALGO_INVESTIGATION_1.md` / the Sprint-29
> review docs; no new live figure introduced.

---

## 1. Investigate-first: the EXACT divergence root

### What the post-deploy export shows (`/tmp/tg_report_2.txt`)

The "📊 סיכום תיק הפיקוד" footer (חדר-מצב surface, `telegram_portfolio.py
handle_portfolio_room`) renders, for a byte-identical body state (same
floating profit, same NAV, same target risk, same exposure):

- L1239/1415/1770/2743/3120/3226/3840/4091 (**pre-deploy**, old buggy
  `net_pnl`→0.0 path): `מצב התאמה מול ברוקר: פער מהותי. פער $190.29`
- L4300 (**post-deploy**, W-A2 `total_pnl_usd` fix live — confirmed by the
  adjacent W-A3 honesty line L4307): `פער נתונים קריטי. פער $510.52`

The deploy boundary is dateable in the export: W3 companion first at L4005,
W-A3 L50 honesty first at L4307. So the **magnitude** difference
($510.52 − $190.29 = $320.23) is the pre/post-W-A2-deploy temporal artifact
(W-A2 correctly stopped silently zeroing realized closed-campaign PnL).

### The STILL-LIVE structural divergence (the real remaining closure)

Both the dashboard/master oracle and the חדר-מצב surface call the SAME
classifier `tf.classify_broker_reconciliation` (`telegram_formatters.py:765`).
That classifier's Critical-Data-Gap branch (`telegram_formatters.py:799-800`):

```python
is_critical = (agap > 5*unit) or (bool(max_open_campaign_risk)
                                    and agap > max_open_campaign_risk)
```

| Surface | `max_open_campaign_risk` arg | Effect |
|---|---|---|
| **Dashboard oracle** (`dashboard.py:452,460`) | **PASSES** `live_df["OriginalRisk"].max()` | second Critical condition LIVE |
| **חדר-מצב** (`telegram_portfolio.py:484-489`, pre-G1) | **OMITTED** ⇒ defaults `0.0` | `bool(0.0)` False ⇒ second Critical branch **DEAD** |

**Root cause (`file:line`):** `telegram_portfolio.py` (pre-G1, the
`classify_broker_reconciliation` call ~:484-489) **omitted the
`max_open_campaign_risk=` argument** that the dashboard recon oracle
(`dashboard.py:460`, fed from `dashboard.py:452`) passes. With the argument
defaulted to `0.0`, the classifier's open-risk Critical branch is dead on the
phone surface. A reconciliation gap that sits **inside** the 5R anchor
(`agap ≤ 5*unit`) but **exceeds** the biggest single open-campaign original
risk is therefore banded the softer **"פער מהותי" (Material Gap)** on the
phone, while the dashboard oracle — the documented correctness reference
(ALGO-1 §1: "the dashboard/master side is the methodologically intended
one") — bands the SAME state **"פער נתונים קריטי" (Critical Data Gap)**.
Numerically reproduced: NAV $7,921, risk 0.60% ⇒ unit $47.53, 5×unit
$237.63; a gap such as $190.29 is < 5×unit (not 5R-critical) but > the
~$48 max open-campaign risk ⇒ oracle=Critical, phone(no arg)=Material — the
exact "פער מהותי" vs "פער נתונים קריטי" split the founder saw directly above
a risk-raise recommendation.

> The realized-PnL **key** divergence (ALGO-1 R-ALGO-2 / W-A2) was already
> closed (`total_pnl_usd`, `telegram_portfolio.py` recon path). On
> inspection the ALGO-1 §1 "closed-vs-all" residual is NOT a magnitude
> defect: both the dashboard's `camp_df` (`dashboard.py:300-367`) and
> `adaptive_risk_engine.compute_closed_campaigns` (`:120-213`) are
> **closed-only** lists with the same `sells['pnl_usd'].sum()` realized
> term. The remaining, still-live, user-visible divergence is the
> **classifier-argument (band) omission** documented above.

## 2. The fix (telegram_portfolio.py ONLY — authorized G1 file)

Three additive hunks inside `handle_portfolio_room`, zero deletions, zero
math change, recon broker numbers byte-identical **except** the authorized
band correction:

1. Init `_max_open_campaign_risk = 0.0` alongside the existing loop totals.
2. In the existing per-open-position loop, right after the existing
   `original_campaign_risk` computation, track its running max — the EXACT
   same per-position quantity the dashboard feeds `live_df["OriginalRisk"]`
   (`dashboard.py:230`). Read-only, no new data source, no new math.
3. Pass `max_open_campaign_risk=_max_open_campaign_risk` into the existing
   `tf.classify_broker_reconciliation(...)` call — mirroring
   `dashboard.py:460` exactly.

## 3. Resolution chosen — EQUAL (not labelled-distinct), and WHY

The two surfaces measure the **same thing**: one broker reconciliation for
one state. The dashboard oracle is the documented correctness reference. The
honest resolution is therefore an **equality** fix: feed the חדר-מצב
classifier the SAME `max_open_campaign_risk` the oracle feeds it, so both
surfaces emit the SAME band for the SAME state. This is NOT a forced wrong
equality — the classifier is **unchanged**; equality holds only because both
call-sites now feed it identical honest inputs. The classifier still
legitimately bands a gap that is genuinely sub-5R AND below the max
open-campaign risk as the softer "Material Gap" (pinned). A
labelled-distinct outcome would be dishonest here: there is no second,
legitimately-different reconciliation being measured — only one call-site was
under-informing the shared classifier.

## 4. Proof (pinned)

`tests/test_sprint30_g1_recon.py` (new, ADD-only — Mark 6.1):

- `TestDivergenceRootIsTheOmittedArgument` — proves the bug: same shared
  classifier, same state, two DIFFERENT bands ("פער מהותי" vs
  "פער נתונים קריטי") solely because one call-site omitted the argument;
  isolates it to the `max_open_campaign_risk` branch (gap inside 5R anchor).
- `TestPostFixSurfaceParity::test_postfix_phone_band_equals_dashboard_oracle_band`
  — the money-truth parity pin: phone == oracle band + Hebrew label + gap +
  full structural identity for the same state.
- `test_classifier_itself_is_unchanged_no_forced_equality` — proves no wrong
  equality forced (a genuinely sub-5R/under-open-risk gap is still Material;
  a >5R gap is still Critical regardless of arg).
- `TestPhoneCallSitePassesTheArgument` — AST static guard: the recon call now
  passes `max_open_campaign_risk=` + the accumulator exists (regression lock).
- `TestLockedAprilByteIdentical` — re-runs the LOCKED April regression
  in-process: 2 passed, byte-identical (8 / +$180.49 / WR .375 / PF 2.6262
  / excl 2).

## 5. Confirmations

- **No byte-locked file modified.** `git diff --stat` EMPTY for
  `engine_core.py` / `analytics_engine.py` / `period_data_probe.py` /
  `adaptive_risk_engine.py` / LOCKED `tests/test_real_data_april_regression.py`
  / `tests/_byte_lock_baselines/*` / `docker-compose.yml` /
  `telegram_bot_secure_runner.py` / migrations.
- **LOCKED April byte-identical** — `test_real_data_april_regression.py`
  2 passed; file diff empty.
- **No cross-workstream file touched.** My only edits: `telegram_portfolio.py`
  (the 31-line G1 recon hunk) + new `tests/test_sprint30_g1_recon.py`. NOT
  touched by G1: `telegram_formatters.py` (G5 — verified its change is the
  L50 sample helper, NOT the recon classifier my fix depends on),
  `risk_monitor.py` (G2/3/6), `bot_health.py` (G4), `tests/test_bot_health.py`
  (G4). Those carry parallel-workstream changes I did not author or modify.
- **Sprint-22/23/24 + C1/C2/B3/Arch-F1/NAV-Unify/W1/W3/ALGO-1 intact;**
  ALGO observe-only & segregation unchanged (recon is a read-only display
  classification; no exit-management, no Supabase write). No new message type.
- **Full suite** `python -m pytest -q -p no:cacheprovider`:
  **2145 passed, 0 failed** (2101 baseline + 9 new G1 ADD + parallel
  workstreams' ADD tests; none weakened).
- **Exact CI command** (`--tb=short -q --cov=engine_core
  --cov=adaptive_risk_engine --cov=analytics_engine --cov=addon_risk_engine
  --cov-report=term --cov-fail-under=67`, CI env): **2145 passed, 0 failed,
  coverage 72.02%** (≥67).
