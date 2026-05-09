# User Requirements Registry

This file is the living source of user requirements, preferences, and requested product direction.

It exists to reduce repeated explanations and keep AI agents aligned with the user's actual goals.

## How to use this file

When the user asks for a new capability, change, rule, preference, or product direction, add it here before or during implementation.

Every requirement should be tracked from request to delivery.

## Requirement states

Use one of these states:

- `proposed` — user mentioned it, but scope is not fully defined
- `approved` — user explicitly approved the direction
- `in_progress` — agent is actively implementing it
- `implemented` — code/docs changed
- `validated` — tested in CI or manually on server
- `blocked` — cannot continue without missing access/data/decision
- `rejected` — intentionally not doing it

## Requirement template

```markdown
### REQ-YYYYMMDD-001 — Short title

Status: proposed / approved / in_progress / implemented / validated / blocked / rejected
Owner: user / agent / both
Area: Telegram / risk engine / dashboard / sync / database / deployment / docs
Priority: High / Medium / Low

User request:
- ...

Acceptance criteria:
- ...
- ...

Implementation notes:
- ...

Validation:
- [ ] tests added or updated
- [ ] CI passed
- [ ] manual server test completed
- [ ] user confirmed

Related files:
- ...
```

## Active requirements

### REQ-20260509-001 — Preserve truth in user-facing trading reports

Status: approved
Owner: both
Area: Telegram / risk engine / sync
Priority: High

User request:
- The system must show the user truth only.
- If live data is unavailable and fallback/cached/default values are used, reports must clearly say so.

Acceptance criteria:
- Telegram reports identify data source or uncertainty when relevant.
- NAV/account-size assumptions are not silently mixed.
- Risk and exposure numbers are not presented as exact if based on fallback data.

Related files:
- `telegram_bot_secure_runner.py`
- `telegram_bot.py`
- `engine_core.py`
- `docs/DATA_CONTRACTS.md`

### REQ-20260509-002 — Keep Telegram safe, clear, short, and Hebrew-friendly

Status: approved
Owner: both
Area: Telegram
Priority: High

User request:
- Telegram messages must be clear, accurate, not overloaded, and suitable for Hebrew RTL readers.
- The bot must include smart anti-spam behavior.

Acceptance criteria:
- Telegram service runs through `telegram_bot_secure_runner.py`.
- Admin-only access remains active.
- Rate limit and cooldown remain active.
- Long reports are split safely.
- Reports remain readable in Hebrew.

Related files:
- `telegram_bot_secure_runner.py`
- `telegram_bot.py`
- `docker-compose.yml`

### REQ-20260509-003 — Support efficient AI-agent development

Status: approved
Owner: both
Area: docs / workflow
Priority: High

User request:
- The repo should contain context files so Claude Code, Codex, and other AI agents can understand the project quickly and work cheaply with fewer tokens.
- Agents should not break unrelated parts while improving one part.

Acceptance criteria:
- Agent operating guide exists.
- Claude-specific context exists.
- Data contracts exist.
- Safe change protocol exists.
- Agent task and user requirement tracking exist.

Related files:
- `AGENTS.md`
- `CLAUDE.md`
- `docs/README.md`
- `docs/AI_AGENT_CONTEXT.md`
- `docs/SAFE_CHANGE_PROTOCOL.md`
- `docs/AGENT_TASKS.md`
- `docs/USER_REQUIREMENTS.md`

## Completed / validated requirements

Move requirements here only after validation.
