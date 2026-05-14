# Coverage Baseline — Sprint 6 Priority 1 #4

**Measured:** 2026-05-14, after Sprint 5 stable + Sprint 6 P1 #1+#2 merged (PR #17)
**Suite:** 1230 tests, 0 failures
**Tooling:** `pytest-cov` (already in `requirements-dev.txt` since Sprint 3)

## Per-module coverage

Measured with:
```
pytest --cov=engine_core --cov=adaptive_risk_engine \
       --cov=analytics_engine --cov=addon_risk_engine \
       --cov-report=term -q
```

| Module                    | Stmts | Miss | Cover |
|---------------------------|-------|------|-------|
| `analytics_engine.py`     |   139 |    2 | **99%** ✅ |
| `adaptive_risk_engine.py` |   322 |   42 | **87%** ✅ |
| `addon_risk_engine.py`    |   154 |   22 | **86%** ✅ |
| `engine_core.py`          |  1072 |  464 | **57%** ⚠️ |
| **TOTAL**                 |  1687 |  530 | **68.58%** |

## Gate decision: 67% (with buffer)

Meeting 6 voted for a 75% threshold on the 4 core modules. After
measurement, the team adjusted:

- **3 of 4 modules already exceed 86%** — well above the target.
- **`engine_core.py` at 57%** is the bottleneck. Raising it to ≥75% requires
  branch-coverage work on the 1072-statement file — that's a multi-day refactor
  effort, not a one-shot config change.
- A hard 75% gate today would **block every PR** on `engine_core`-adjacent
  changes until the refactor lands.
- The ratchet approach (gate slightly **below** current baseline) prevents
  regressions while leaving room for incremental improvement.

**Gate set to 67%** in `.github/workflows/tests.yml` — 1.58 percentage-point
buffer below the 68.58% baseline. The buffer prevents unrelated PRs (that add
a few uncovered lines) from breaking the build, while a regression of >1.5
percentage points still fails CI.

## Progression plan

| Sprint | Target | What needs to happen |
|--------|--------|----------------------|
| 6 (now) | **67%** | Gate active. Prevents regression. |
| 7 | **68%** | Tighten gate to baseline once Sprint 7 features add tests. |
| 8 | **75%** | Dedicated `engine_core` test-coverage sweep (Mark's target from Meeting 6). |

## Local commands

Coverage with full term + missing lines (for finding gaps):
```
pytest --cov=engine_core --cov=adaptive_risk_engine \
       --cov=analytics_engine --cov=addon_risk_engine \
       --cov-report=term-missing
```

HTML report (browseable in `htmlcov/index.html`):
```
pytest --cov=engine_core --cov=adaptive_risk_engine \
       --cov=analytics_engine --cov=addon_risk_engine \
       --cov-report=html
```

CI gate (matches `.github/workflows/tests.yml`):
```
pytest --cov=engine_core --cov=adaptive_risk_engine \
       --cov=analytics_engine --cov=addon_risk_engine \
       --cov-fail-under=67
```
