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

## Completed / validated tasks

Move validated tasks here when done.
