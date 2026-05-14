# Sprint 7 — Lessons Learned

**Dates:** 2026-05-14 (single-day sprint, recovery from Sprint 6 incident)
**Score** (Mark's verdict at Meeting 8): **8.6 / 10** — up from 7.8 post-Meeting 7
**Test count:** 1248 → 1251 (+3 socket meta-tests in PR #22)

> Sprint 7 was a "process recovery" sprint, not feature work. Goal:
> close the Sprint 6 incident class permanently and codify the
> processes that should have prevented it.

---

## Priority items planned vs. delivered

| # | Priority | Planned | Delivered | PR |
|---|----------|---------|-----------|-----|
| 1 | Merge PR #15 / fix CI / merge to main | ✅ | ✅ | #21 |
| 2 | Branch protection rules on main | ✅ | 🟡 (rule created Meeting 8) | UI action |
| 3 | pytest-socket default disable | ✅ | ✅ | #22 |
| 4 | `audit_log` healthcheck + verify_migrations.py | ✅ | ✅ | #23 |
| 5 | PR template + testing guidelines + lessons template | ✅ | ✅ | #24 |

**5/5 delivered** (P2 completed late in Meeting 8 via Repository Rulesets UI).

## Incidents during this sprint

### Incident: PR #15 mergeable_state = "dirty"

- **Detected:** Meeting 7 audit
- **Cause:** PR #15 had been open 5 meetings (from Sprint 2 through Sprint 6) and main had drifted significantly.
- **Fix:** Sprint 7 P1 rebased + merged in 1 commit (`acb1da6`).
- **Prevention:** "One PR at a time" rule (David PO, Meeting 7) + branch protection that requires up-to-date branches.

### Non-incident: CI green on main first time

After PR #21 merged, CI ran green on `main` for the first time in the project's history. Previously CI ran only on PRs, so main could silently drift.

## What worked

- **Five priorities, five PRs, all in one day.** Tight scope, no scope creep.
- **The structural fix (pytest-socket) is bigger than the incident.** PR #21 fixed the FT test; PR #22 prevents the class. Defense in depth.
- **`bot_health` check #14 with migration filename hint.** When the operator sees red, they see the *exact* migration to apply — not a vague "fix audit".
- **PR template captured the failure modes we'd just lived through.** No more "I forgot the migration."
- **Sprint 6 retrospective was actually written** before Sprint 7 started. Mark's gate (lessons doc before next sprint) worked.

## What didn't work

- **Branch protection was completed in two halves.** The rule was created at the end of Meeting 7 but lacked `required_status_checks`. That gap stayed open across Sprint 8 Day 1 until Meeting 8 audit caught it. Lesson: branch protection should be a one-shot config with a verification step.
- **PRs #18 and #19 stayed open through all of Sprint 7.** They were base'd on old main (`c61c73c`) — they didn't have the FT fix. Tomer/DevOps had to manually trigger `update_pull_request_branch` later. Lesson: stale PRs that pre-date a fix on main need explicit rebase.
- **audit_logger merged without migration 002 applied.** PR #20 (Sprint 6) merged the code; the migration was committed but not applied in production. This silent compliance gap was only caught in Meeting 7 retro. Sprint 7 PR #23 added the healthcheck — but the gap shipped for days.

## New backlog items surfaced

| # | Item | Priority | Sprint | PR |
|---|------|----------|--------|-----|
| 1 | pytest-socket meta-tests | 1 | 7 | #22 |
| 2 | `audit_log` healthcheck #14 | 1 | 7 | #23 |
| 3 | `verify_migrations.py` operator script | 1 | 7 | #23 |
| 4 | PR template with migration checklist | 2 | 7 | #24 |
| 5 | `docs/TESTING_GUIDELINES.md` | 2 | 7 | #24 |
| 6 | `SPRINT_LESSONS_TEMPLATE.md` | 2 | 7 | #24 |
| 7 | Branch protection: `required_status_checks` | 1 | 8 | UI action |
| 8 | Coverage gate ≥67% in CI | 1 | 8 | #19 (Sprint 6 reopened) |
| 9 | audit_logger 8/8 (4 more actions) | 2 | 9 | upcoming |

## Test coverage snapshot

| Module | Sprint 6 | Sprint 7 | Trend |
|--------|----------|----------|-------|
| `engine_core.py` | 57% | 56-57% | ≈ (FT semantic fix added one helper) |
| `adaptive_risk_engine.py` | 87% | 87% | = |
| `analytics_engine.py` | 99% | 99% | = |
| `addon_risk_engine.py` | 86% | 86% | = |
| **Total** | 68.58% | 67.99% | ↓ 0.59pp (one new uncovered path) |

CI gate remained at 67% — Sprint 7 stayed within the ratchet.

## Process changes adopted

1. **One PR at a time policy** — David PO. WIP > 2 open PRs needs justification.
2. **CI must be green on main before next sprint kickoff** — Mark gate.
3. **Branch protection with `required_status_checks: tests, strict: true`** — Eyal.
4. **PR template auto-populates** on every new PR. Six checklist sections (Summary, Test Plan, Hard constraints, Network/external deps, Migrations/human action, Risk classification).
5. **`docs/TESTING_GUIDELINES.md`** is now the source of truth for what makes a "good" test (no network, deterministic, hermetic, no silent failures).
6. **`docs/SPRINT_LESSONS_<N>.md`** filled in at end of every sprint. Sprint 6 lessons doc was the first example; this is the second.

## Mark's verdict on the lessons

> *"Sprint 7 took one day. One day to fix everything we'd been doing wrong for six weeks. The lesson isn't 'we're fast' — the lesson is 'incidents reveal scope that was hiding under feature work.' Sprint 6 surfaced 5 problems; Sprint 7 solved all 5. That's the right ratio. Now Sprint 8 has to demonstrate we don't regress — and Sprint 9 has to demonstrate we can ship features again without losing the new floor."*
