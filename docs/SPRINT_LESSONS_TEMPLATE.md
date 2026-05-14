# Sprint <N> — Lessons Learned

**Dates:** YYYY-MM-DD → YYYY-MM-DD
**Score** (Mark Minervini's verdict): X.X / 10
**Test count:** before → after

> Copy this template to `docs/SPRINT_<N>_LESSONS.md` at the end of each sprint.
> Mark approves the next sprint's kickoff only when this document is filled in.

---

## Priority items planned vs. delivered

| # | Priority | Planned | Delivered | Notes |
|---|----------|---------|-----------|-------|
| 1 | ... | ✅/❌ | ✅/❌ | |
| 2 | ... | | | |
| 3 | ... | | | |
| 4 | ... | | | |
| 5 | ... | | | |

## Incidents during this sprint

For each unplanned issue surfaced — CI failure, production silence, user-visible bug:

### Incident: <name>

- **Detected:** YYYY-MM-DD HH:MM
- **Introduced:** YYYY-MM-DD HH:MM (commit SHA if known)
- **Time-to-detect (TTD):** N days/weeks
- **Time-to-fix (TTF):** N hours/days
- **Root cause:** what specifically broke, in one sentence
- **Fix:** PR # and what changed
- **Prevention added:** PR # for the structural guardrail, if any

> Example (Sprint 6): `test_returns_none_when_history_empty` non-deterministic.
> Detected post-PR-#20 merge when coverage gate forced CI green. Introduced in
> Sprint 2. TTD = 6 weeks. TTF = 5 minutes after seeing the log. Fix: PR #21.
> Prevention: PR #22 (pytest-socket disable by default).

## What worked

Bullet list — keep doing these:
- ...

## What didn't work

Bullet list — change before next sprint:
- ...

## New backlog items surfaced

| # | Item | Priority | Owner | Sprint target |
|---|------|----------|-------|---------------|
| | | | | |

## Test coverage snapshot

| Module | Cover | Trend |
|--------|-------|-------|
| `engine_core.py` | XX% | ↑/↓/= |
| `adaptive_risk_engine.py` | XX% | |
| `analytics_engine.py` | XX% | |
| `addon_risk_engine.py` | XX% | |
| **Total** | XX% | |

## Process changes for next sprint

Any new rules, templates, or workflows introduced — and how the team will hold itself accountable.

- ...

## Mark's verdict on the lessons

A 1-2 sentence quote from Mark assessing whether the team genuinely learned from this sprint, or just documented motions.

> "..."
