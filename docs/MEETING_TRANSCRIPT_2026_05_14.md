# Pi-Integration Team Meeting — 2026-05-14
## Transcript / audit trail

User request: "Team Lead presents a plan, Mark challenges it, leads improve and start working autonomously until everything is implemented end-to-end."

This document captures all three artifacts in order. The team's final action was to push branch `claude/integration-pi-and-main-2026-05-14`.

---

## Phase 1 — Discovery (4 parallel exploration agents)

Spawned in parallel:
1. **Backend / math agent** — engine_core, risk_monitor, adaptive_risk_engine, supabase_repository, analytics_engine, audit_logger
2. **Telegram bot agent** — telegram_bot.py and 9 extracted modules
3. **Test inventory agent** — main vs Pi backup test files
4. **Infra / docs agent** — docker-compose, main.py, migrations, all docs

Initial signal from agents 1, 3, 4: "main has substantial Sprint 6/7/8 additions Pi lacks." From agent 2: "Pi has cleaner refactor structure." Tentative recommendation: take main as base, port 5 Pi features.

Plan v1 was drafted on this premise.

---

## Phase 2 — Plan v1 (Team Lead)

Full text: `/tmp/merge-meeting/01_TEAM_LEAD_PLAN_V1.md` (kept off the integration branch — superseded).

Summary of v1: Take main as base. Cherry-pick 5 Pi commits (`6c3d627` DNS, `ebbd38f` ALGO threshold, `7f4d042` Runner Mode, `ea64e34` IBKR import, `6c8288c` importer fix). Defer Phase 4 to Sprint 10.

---

## Phase 3 — Mark's adversarial review

Full text: `/tmp/merge-meeting/02_MARK_REVIEW.md`. Verdict: **REJECT**.

9 findings, summarised:

| # | Severity | Finding |
|---|---|---|
| 1 | BLOCKER | Main already contains all 5 cherry-pick targets via parallel commits (`76b7251`, `cb1dcc6`, `5a798f3`, `ccfcb4f` + 8 Phase 4 steps). Plan built on inverted facts. |
| 2 | HIGH | Cherry-picks would fabricate fake conflicts (verified by simulation). One produces an empty commit. |
| 3 | MED | Migration 002 timing — fail-open is correct, but compliance gap is silent. Must verify in Supabase. |
| 4 | MED | Test count claim wrong: actual is 1305 (or 1321 collected), not 1248. |
| 5 | BLOCKER | Pi is BEHIND main, not parallel to it. Reframe as deployment, not merge. |
| 6 | HIGH | Production behavior delta unanalyzed: RISK_LADDER, drawdown auto-cut, daily digest, dev_pin removed, autoheal sidecar, alert cooldown, sizing leak, heartbeats. |
| 7 | MED | State-file format gap → first-cycle alert burst. Mitigation: pre-populate timestamps. |
| 8 | MED | Rollback target = same as deploy target. Real rollback SHA: `6c8288c` (Pi backup tip). |
| 9 | HIGH | Phase 4 deferral incoherent — main is already post-Phase-4. |

---

## Phase 4 — Plan v2 (Team Lead, post-Mark)

Full text: `/tmp/merge-meeting/03_TEAM_LEAD_PLAN_V2.md`.

Reframed as **DEPLOY**, not merge. Integration branch = main + 4 docs + 1 helper script. No production code changes.

Mitigations applied:
- Mark #1, #5, #9 → drop cherry-picks, integration branch = main
- Mark #3 → `python3 migrations/verify_migrations.py` step in pre-flight
- Mark #4 → recounted with `pytest --collect-only`: 1321 tests (passed all 1321)
- Mark #6 → full BEHAVIOR_DELTA doc with 16 changes, severity-rated
- Mark #7 → `scripts/prepare_pi_state_for_deploy.py` + 6 self-tests (all pass)
- Mark #8 → explicit rollback SHA `6c8288c` documented in DEPLOY_GUIDE
- Mark #2 → no cherry-picks attempted, no fake conflicts

---

## Phase 5 — Verification

Run on `/tmp/integration-worktree` (worktree on integration branch):

| Check | Result |
|---|---|
| Pip install -r requirements-dev.txt | ok |
| pytest -q -p no:cacheprovider | **1321 passed, 0 failed, 1 cosmetic warning, 76.19s** |
| Helper script self-tests (6 tests) | **6 passed** |
| `comm -13` of file lists (Pi-only files) | **empty** — Pi adds zero files vs main |
| `diff` of `ibkr_trade_importer.py` between branches | **0 bytes** — byte-identical |
| `git rev-parse origin/main:ibkr_trade_importer.py` vs Pi backup | both `d4c7835` |

---

## Phase 6 — Outputs (this branch)

```
docs/WAKE_UP_BRIEF_2026_05_14.md            ← read first
docs/DEPLOY_GUIDE_PI_2026_05_14.md          ← step-by-step deploy
docs/BEHAVIOR_DELTA_PI_2026_05_14.md        ← every user-visible change
docs/MEETING_TRANSCRIPT_2026_05_14.md       ← this file
scripts/prepare_pi_state_for_deploy.py      ← state-file mitigation
scripts/test_prepare_pi_state.py            ← 6 self-tests
```

Branch pushed to `origin/claude/integration-pi-and-main-2026-05-14`.

---

## Open items requiring user decision (NOT auto-resolved)

These are listed in `WAKE_UP_BRIEF_2026_05_14.md`. The team did not override them autonomously:

1. RISK_LADDER tightening — keep new ladder or revert?
2. Drawdown auto-cut — accept or disable?
3. Daily Digest at 21:00 UTC — keep or disable?
4. Merge integration branch into main after deploy succeeds — yes/no?

---

## Lessons captured for next sprint retrospective

1. **Always verify branch state before planning a merge.** Plan v1 spent 30 minutes assuming Pi had unique features. A 30-second check (`comm -13` of file lists) would have shown the truth immediately.
2. **Adversarial review (Mark) caught 7 of 9 risks the synthesis missed.** Worth the round-trip every time.
3. **State-file forward-compatibility is a real risk class.** Adding new keys with default `0` looks safe in code, hits hard at runtime when the cooldown sees `last_alert_ts=0` and fires every position.
4. **"Same TASK ID, different SHA" is the giveaway** for parallel commits across branches. Always compare commit titles + content (not just SHAs).
