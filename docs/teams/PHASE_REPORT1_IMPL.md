# Phase REPORT-1 — IMPL / יישום (T-R1: monthly Coaching honors the true dev-score; F5 closed)

**Status:** LANDED — parent-verified, full CI-equivalent post-commit on the
CLEAN tree 0-failed, weekly + monthly scorecard + LOCKED April byte-identical,
no byte-locked file touched. Scope: `docs/teams/PHASE_REPORT1_SCOPE.md`
(governs). Code HEAD `bbdca06` on `claude/review-system-audit-FBZ2h` (scope
`b671fa3`, baseline `01f49fb` post-ALGO-3). No live financial values in this
doc.

## What landed (T-R1 — the contradiction fix)
Two non-byte-locked production files only:
- `report_scheduler.py` `_monthly_coaching_insights(a, dev_score=None)` — the
  bogus `dev = a.get("dev_score", 0) or 0` (a key that NEVER exists on
  `analytics`; the real composite lives only in the separate `dev_data` the
  scorecard consumes) is **deleted, not shimmed**. The score-line now reads
  the passed `dev_score`:
  - `score >= 80` ⇒ the existing exact "ציון פיתוח מעולה ({score}/100) …"
  - `score < 50` ⇒ the existing exact "ציון פיתוח נמוך ({score}/100) …"
  - `50 ≤ score < 80` ⇒ no dev line (the existing silent band — the observed
    79 case: the contradiction simply disappears, no new text)
  - `score is None` (insufficient-data) ⇒ no dev line, NEVER a false "0/100".
  The `import math`/PF block and every other line are byte-unchanged.
- Both monthly call sites pass the **same** `dev_data["score"]` the scorecard
  already consumes — `report_scheduler.py:502` and `report_on_demand.py:175`
  → `_monthly_coaching_insights(analytics, dev_data.get("score"))`.

Coaching ↔ scorecard are now consistent **by construction** (single source
`dev_data["score"]`). The weekly path (`_weekly_coaching_insights` + its call
sites) and the scorecard/template render paths are **untouched** ⇒ weekly and
the monthly scorecard are byte-identical.

## F5 — closed (verify + test-pin + document; NO production code change)
F5 ("on-demand April monthly renders 0/$0") is **RESOLVED by correct-by-design
relative-window timing**, not a code bug — exactly the `SPRINT30_SCOPE.md`
triage hypothesis. The on-demand monthly resolves to the **last COMPLETE
calendar month** (`report_on_demand.last_complete_monthly_ref(now)` → `now`;
`report_scheduler._monthly_period(ref)` → the previous calendar month; closes
filtered to the `[start, end]` window). Invoked while *now* was still in April
it correctly resolved to **March** ⇒ April closes filtered out ⇒ 0/$0.
Post-April it resolves to **April** and renders the full month (the freshly
exported April PDF confirms full real data). Pinned by `tests/test_phase_report1.py`
Case 6 (a May reference → the April `[2026-04-01 00:00:00, 2026-04-30
23:59:59]` window; day-stable; a pre-April reference → March — the F5 root).
No production code changed for F5; it is closed, not "fixed".

## Proof obligations — verified (parent, independent)
- Full suite (CI env, parent's own run): **2205 passed / 0 failed**
  (2186 baseline + 19 new ADD-only).
- Exact CI command POST-COMMIT on the **clean tree**: `2205 passed`,
  **coverage 73.04% ≥ 67%**, 0 failed.
- REPORT-1 suite: **19 passed**. byte-lock + April + coaching selection:
  **42 passed / 0 failed**.
- Protected-set git-diff EMPTY: `engine_core.py`, `analytics_engine.py`,
  `period_data_probe.py`, LOCKED `tests/test_real_data_april_regression.py`,
  all `tests/_byte_lock_baselines/*`, `docker-compose.yml`,
  `telegram_bot_secure_runner.py`, migrations, `templates/*` — confirmed.
- `git diff --name-only` ⇒ only `report_scheduler.py` + `report_on_demand.py`
  (+ new `tests/test_phase_report1.py`). No existing test modified: no
  bug-codifying monthly-coaching test existed (none asserted the old false
  "0/100"/"נמוך" output) ⇒ no Mark-6.1 correction was required.
- Named proofs held: silent-band 79 ⇒ no dev line / no "0/100"; ≥80 / <50 ⇒
  the existing exact lines with the REAL score; None ⇒ no line; weekly
  byte-identical (signature + output); F5 window pinned; LOCKED April
  (8 / +$180.49 / WR .375 / PF 2.6262 / excl 2) byte-identical.

## Deploy
Narrative-text correctness only; production wiring unchanged
(`docker-compose.yml` byte-identical). Standard pull-and-recreate-all-services
per `docs/DEPLOYMENT_RUNBOOK.md` (the host tracks the branch; full
`--force-recreate` because `volumes: .:/app` + long-running Python).
