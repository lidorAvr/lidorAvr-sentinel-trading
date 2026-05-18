# Phase REPORT-1 — SCOPE / איפיון (T-R1: monthly Coaching honors the true dev-score; F5 closure)

**Status:** SCOPE — founder-approved ("Phase ממושטר לסתירה + סגירת F5"). Governed, Mark-gated, parent-verified, exact-CI post-commit on the clean tree. Source: live exported April-2026 monthly PDF self-contradiction + the read-only investigation. Live baseline HEAD `01f49fb` (post-ALGO-3, parent-verified, suite **2186/0 cov 73.04%**). No live financial values in any committed doc.

## The defect (confirmed, narrow)
In the **monthly** report the headline + scorecard show the real composite "ציון תהליך **79/100 — מצוין**" (`compute_trader_development_score` → the separate `dev_data` dict, consumed correctly by the scorecard at `report_scheduler.py:517` / `report_on_demand.py:190`). But the "🎓 Coaching — סיכום חודשי" block prints "ציון פיתוח **נמוך (0/100)**" — the SAME report contradicts itself. Root: `report_scheduler.py:600-609` `_monthly_coaching_insights(a)` does `dev = a.get("dev_score", 0) or 0`, reading a key that **never exists on `analytics`** (the score lives only in `dev_data`, never merged in) ⇒ always `0` ⇒ the `dev < 50` branch ⇒ the false "נמוך (0/100)" line. `report_on_demand.py:175` passes only `analytics` to the same helper ⇒ identical contradiction on the on-demand path. The WEEKLY path is structurally immune: `_weekly_coaching_insights` (`report_scheduler.py:576-597`) never references a dev score.

## T-R1 — fix (source-correctness, byte-identity-preserving)
`report_scheduler.py` `_monthly_coaching_insights`: add an optional `dev_score=None` parameter; replace the bogus `a.get("dev_score", 0) or 0` with the **true score passed in from the same `dev_data["score"]` the scorecard already consumes**. Behavior of the score-line:
- real score ≥ 80 ⇒ the EXISTING "ציון פיתוח מעולה ({score}/100) …" line, byte-identical text/format.
- real score < 50 ⇒ the EXISTING "ציון פיתוח נמוך ({score}/100) …" line, byte-identical text/format (a genuinely-low real score is still honestly flagged).
- 50 ≤ score < 80 ⇒ **no dev-score line** (the existing silent band — this is the observed 79 case: the contradiction simply disappears, no new text introduced).
- `score is None` (insufficient-data, `compute_trader_development_score` returns `{"score": None,…}`) ⇒ **no dev-score line at all** — NEVER the false "נמוך (0/100)".

The PF block and every other line of `_monthly_coaching_insights` are **unchanged**. Update the two monthly call sites to pass the real score: `report_scheduler.py:502` → `_monthly_coaching_insights(analytics, dev_data.get("score"))`; `report_on_demand.py:175` → `sched._monthly_coaching_insights(analytics, dev_data.get("score"))`. The bogus `a.get("dev_score")` read is **deleted**, not shimmed (it was always the bug; no back-compat fallback). Scorecard/template render path UNCHANGED. `_weekly_coaching_insights` and its call sites (`report_scheduler.py:~361`, `report_on_demand.py:146`) **UNCHANGED** ⇒ weekly byte-identical. Coaching ↔ scorecard now consistent **by construction** (single source `dev_data["score"]`). If any existing test asserts the OLD false "0/100 נמוך" monthly output, it CODIFIES the bug and MUST be corrected to the true-source expectation (Mark 6.1 — corrected, never weakened), not left.

## F5 — closure (verify + test-pin + document; NO production code change)
Deferred F5 ("on-demand April monthly renders 0/$0") is **RESOLVED by correct-by-design relative-window timing**, not a code bug — exactly the `SPRINT30_SCOPE.md` triage hypothesis. The on-demand monthly resolves to the **last COMPLETE calendar month** (`report_on_demand.py:~63` ref=`now` → `_monthly_period(now)` → previous calendar month; closes filtered to `[start,end)` in `analytics_engine.py:~400`; the 8-week lookback only widens the *fetch*, never the close-window). Invoked while *now* was still in April it resolved to **March** ⇒ April closes filtered out ⇒ 0/$0. Post-April it resolves to **April** and renders the full month (the freshly-exported April PDF confirms: 10 campaigns, real KPIs). Closure = a test pinning that the on-demand monthly window resolves to the last *complete* calendar month (so a future silent window-shift regression is caught) + an explicit IMPL note. No production code is changed for F5.

## Byte-identity / proof obligations (named)
- **Weekly report byte-identical** — `_weekly_coaching_insights` + weekly wiring untouched.
- **Monthly scorecard / KPIs byte-identical** — render path + `compute_*` untouched; only the monthly *coaching narrative* score-line changes (false→true/silent).
- **LOCKED April byte-identical** — 8 / +$180.49 / WR .375 / PF 2.6262 / excl 2 unchanged (coaching is narrative text, not a KPI/R/NAV/PF/count; the locked regression + all `_byte_lock_*` stay green).
- **Contradiction gone** — for a real score in the silent band (e.g. 79) the monthly coaching emits NO dev line (no "0/100"); for ≥80 / <50 the existing exact lines with the REAL score; for None, no line.
- **F5 pinned** — on-demand monthly window = last complete calendar month (regression-locked).
- ALGO observe-only / segregation unchanged; no new message TYPE; Sprint-22/23/24 + C1/C2/B3/Arch-F1/NAV-Unify/W1/W3/ALGO-1/2/3/Sprint-30 invariants intact.

## Separate acceptance tests (`tests/test_phase_report1.py`)
- `_monthly_coaching_insights` + true score 79 ⇒ NO "ציון פיתוח" line, NO "0/100"; PF/other lines unchanged.
- score 85 ⇒ exact "ציון פיתוח מעולה (85/100) …"; score 40 ⇒ exact "ציון פיתוח נמוך (40/100) …".
- score None ⇒ NO dev-score line (never the false low line).
- Bug-regression: monthly wiring (analytics WITHOUT `dev_score`, dev_data score=79) ⇒ no false low line; the pre-fix path provably produced "נמוך (0/100)".
- Weekly coaching byte-identical for representative analytics (no dev line ever).
- F5: the on-demand monthly ref/`_monthly_period` for a May reference date resolves to the April `[start,end)` window (last complete month).
- LOCKED April KPIs byte-identical post-fix.
No existing test deleted/weakened (Mark 6.1); a bug-codifying monthly-coaching test, if present, is CORRECTED.

## Hard constraints (auto-FAIL)
`engine_core.py`/`analytics_engine.py`/`period_data_probe.py`/LOCKED April/`tests/_byte_lock_baselines/*`/`docker-compose.yml`/`telegram_bot_secure_runner.py`/migrations git-diff EMPTY. Weekly report + monthly scorecard/KPIs + LOCKED April byte-identical; ALGO observe-only; no new message TYPE; no Supabase mutation. Only the two non-locked files change: `report_scheduler.py` + `report_on_demand.py` (small) and the new `tests/test_phase_report1.py`. Full suite `python -m pytest -q` ≥ **2186**, 0 failed (new tests only ADD). Exact CI command (CI env) post-commit on the clean tree → 0 failed, cov ≥67.

## Done = deploy-ready
T-R1 landed + F5 test-pinned/closed, parent-verified, full CI-equivalent post-commit clean-tree 0-failed, weekly+scorecard+LOCKED April byte-identical, no byte-locked file touched, `docs/teams/PHASE_REPORT1_IMPL.md` written. Then return to the founder with ONE deploy command + the standing deferred reminder (L-1/token rotation, OPS-1/2) + the explicit F5-closed note + the prior operational note (6 manual campaigns had NO stop logged — a data-entry lever, not code).
