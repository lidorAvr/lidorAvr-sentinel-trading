# Testing Guidelines — Sentinel Trading

**Sprint 7 #5** — codified from Meeting 7 retrospective on the Sprint 6 CI incident.

## The hard rules

### 1. No production network calls in tests

`pytest-socket` blocks all socket calls by default (`tests/conftest.py`). Any test that touches `yfinance`, `Supabase`, the Telegram API, or any other DNS-resolved host raises `SocketBlockedError` immediately.

**Why:** the Sprint 6 incident — `test_returns_none_when_history_empty` passed an empty `hist_df` and expected `None`. The production code fell through to a real `yf.Ticker.history(...)` fetch. Local sandbox = no internet = empty fetch = test passed. CI = internet = real AAPL data = test failed with `assert 13.0 is None`. The test lived 6 weeks before surfacing.

**If you genuinely need a local socket** (e.g. an in-process HTTP server), use:

```python
@pytest.mark.enable_socket
def test_my_local_server(...):
    ...
```

No test should ever reach a public host. Code review enforces.

### 2. Tests must be deterministic

A test that passes in one environment and fails in another is broken — even if both environments are "correct." Examples of non-determinism to avoid:

- Falling back to a network fetch on missing input
- Reading the current wall-clock time (use a fixed `freeze_time` or pass `now` as a parameter)
- Iterating over `dict.keys()` and asserting order (Python 3.7+ is insertion-ordered but tests that depend on this are fragile)
- Filesystem state that leaks between tests

### 3. Tests must be hermetic

A test that depends on `risk_recommendations.json` existing on disk, or on `/app/state/` being writable, is hermetic only on the developer's machine. Use:

- `tmp_path` fixture for any filesystem write
- `monkeypatch.setattr` for module-level constants like file paths
- The shared fixtures in `tests/conftest.py` (`mock_supabase`, `mock_yfinance`, `mock_telegram_bot`)

### 4. No silent failures (in code OR in tests)

If production code has `except Exception: pass`, a reviewer rejects it. The same rule applies in test fixtures: a fixture that swallows a setup error and returns a half-baked mock will produce confusing failures elsewhere.

If you can't recover from an exception, **raise it** and let the test framework report a clear failure. If recovery is intentional, log it explicitly (`audit_logger.log_action` style — stderr is acceptable for non-business events).

## Markers — pytest.ini

The suite uses three markers:

```ini
markers =
    unit:        pure math, no I/O
    integration: cross-module, uses mocks
    slow:        requires network or heavy computation
```

Apply them with care:

- `@pytest.mark.unit` — almost everything. Default if no other marker fits.
- `@pytest.mark.integration` — exercises a real cross-module flow (e.g. `test_e2e_risk_monitor`). Still no real network — uses fixtures.
- `@pytest.mark.slow` — anything > 5 seconds. Excluded from PR CI via `pytest -m "not slow"`.

## Coverage targets

| Module | Today | Sprint 7 | Sprint 8 |
|--------|-------|----------|----------|
| `analytics_engine.py` | 99% | 99% | 99% |
| `adaptive_risk_engine.py` | 87% | 87% | 90% |
| `addon_risk_engine.py` | 86% | 86% | 90% |
| `engine_core.py` | 57% | 60% | **≥75%** |
| **CI gate** | 67% | 68% | 75% |

`engine_core.py` is the bottleneck — 1072 statements, 464 uncovered (mostly fallback paths). Sprint 8 dedicates a coverage sweep. Until then, the CI gate sits at 67% as a ratchet — prevents regression without blocking unrelated work.

Run locally:

```bash
pytest --cov=engine_core --cov=adaptive_risk_engine \
       --cov=analytics_engine --cov=addon_risk_engine \
       --cov-report=term-missing
```

`term-missing` shows the exact uncovered line numbers — that's where new tests should target.

## When you find a bug

1. Write a test that reproduces it. This test should **fail** on `main` and **pass** on your fix branch.
2. If the bug was a non-deterministic test (Sprint 6 incident class), the fix is **two PRs**:
   - One PR fixes the specific code (e.g. PR #21)
   - One PR adds a structural guardrail to prevent the class (e.g. PR #22 pytest-socket)

## When you write a new feature

1. Plan the test cases **before** writing the feature. If you can't think of failure modes, the feature isn't designed.
2. Tests come in the same PR as the code. No "tests in a follow-up" — that's how Sprint 2's `compute_follow_through` got a bad test that lived 6 weeks.
3. Run `pytest --tb=short -q --cov-fail-under=67` locally. If it fails on your machine, it'll fail in CI.

## Open questions tracked in `docs/SPRINT_LESSONS_*.md`

Anything we don't know how to test yet — Telegram inline button flows, weasyprint output, multi-cycle race conditions — gets a row in the current sprint's lessons doc with a TODO.
