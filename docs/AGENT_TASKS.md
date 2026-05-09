# Agent Tasks Ledger

This file tracks tasks that AI agents should perform or are currently performing.

It is a lightweight task ledger for AI-agent work inside the repository.

## Purpose

- Keep agent work visible.
- Avoid losing context between sessions.
- Reduce repeated prompting.
- Prevent agents from starting unrelated work.
- Track what was done, what is blocked, and what remains.

## Task states

Use one of:

- `todo`
- `in_progress`
- `blocked`
- `implemented`
- `validated`
- `cancelled`

## Task template

```markdown
### TASK-YYYYMMDD-001 — Short title

Status: todo / in_progress / blocked / implemented / validated / cancelled
Source requirement: REQ-YYYYMMDD-XXX
Assigned to: agent / user / both
Risk: Low / Medium / High
Affected services: ...

Goal:
- ...

Plan:
1. ...
2. ...
3. ...

Progress log:
- YYYY-MM-DD HH:MM — ...

Validation:
- [ ] tests added or updated
- [ ] CI passed
- [ ] manual smoke test completed
- [ ] deployment completed

Blockers:
- ...

Files touched:
- ...

Rollback:
- ...
```

## Active tasks

### TASK-20260509-001 — Verify secure Telegram deployment on server

Status: todo
Source requirement: REQ-20260509-002
Assigned to: user
Risk: High
Affected services: telegram-bot

Goal:
- Confirm that the production server pulled the latest `main` and that Telegram runs through `telegram_bot_secure_runner.py`.

Plan:
1. Run `git pull` on the Orange Pi server.
2. Rebuild/restart only `telegram-bot`.
3. Inspect logs.
4. Test Telegram commands.

Validation:
- [ ] `docker compose ps` shows telegram-bot running
- [ ] logs show no crash
- [ ] `/portfolio` works
- [ ] `/next` works
- [ ] `/trade CAT` works
- [ ] fast repeated messages trigger rate-limit behavior

Files touched:
- `docker-compose.yml`
- `telegram_bot_secure_runner.py`

Rollback:
- Temporarily revert the Telegram command only if the secure runner fails.

### TASK-20260509-002 — Maintain AI-agent workflow documentation

Status: in_progress
Source requirement: REQ-20260509-003
Assigned to: agent
Risk: Low
Affected services: docs only

Goal:
- Keep repo-level context and workflow docs updated so AI agents can work efficiently.

Progress log:
- Created `AGENTS.md`.
- Created `CLAUDE.md`.
- Created docs under `docs/`.
- Created requirement and task tracking files.

Validation:
- [x] documentation files added
- [ ] user confirmed workflow is useful

### TASK-20260509-003 — Smart IBKR sync timing and report retention

Status: implemented
Source requirement: REQ-20260509-001
Assigned to: agent
Risk: Medium
Affected services: sentinel-bot (main.py only)

Goal:
- Replace naive hourly sync with smart windowed sync.
- Save last 3 IBKR XML reports for debugging.
- Alert via Telegram after 3 failed attempts.

Plan:
1. Define sync window 07:00–11:00 (Asia/Jerusalem, server is already on IDT).
2. Attempt once per hour, not on every 15-min loop tick.
3. Track state in /app/ibkr_sync_state.json (sync_date, fail_count, fail_date, last_attempt_hour, notified_date).
4. Save raw XML to /app/ibkr_reports/ibkr_YYYY-MM-DD_HH-MM.xml, keep last 3 files.
5. Send Telegram alert after MAX_ATTEMPTS_PER_DAY (3) failures.
6. Send success notification when report received.

Progress log:
- 2026-05-09: main.py rewritten (v16.0). Old v15.0 sync replaced.

Validation:
- [ ] Deployed on Orange Pi (git pull + docker compose up -d --build sentinel-bot)
- [ ] /app/ibkr_reports/ directory created on first run
- [ ] /app/ibkr_sync_state.json updated after each loop
- [ ] Report received next morning at 07:xx and saved as XML
- [ ] Success Telegram notification received
- [ ] Failure alert tested by temporarily using wrong token

Rollback:
- git revert HEAD on main.py
- docker compose up -d --build sentinel-bot

Files touched:
- main.py

## Completed / validated tasks

Move validated tasks here when done.
