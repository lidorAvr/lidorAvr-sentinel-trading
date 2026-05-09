# Architecture Decision Log

This file records important architecture and workflow decisions.

Use it when a decision affects future development, deployment, safety, or data correctness.

## Decision template

```markdown
### ADR-YYYYMMDD-001 — Short title

Status: proposed / accepted / replaced / rejected
Date: YYYY-MM-DD
Owner: user / agent / both

Context:
- ...

Decision:
- ...

Why:
- ...

Consequences:
- ...

Related files:
- ...
```

## Accepted decisions

### ADR-20260509-001 — Use a secure Telegram runner before refactoring the Telegram bot

Status: accepted
Date: 2026-05-09
Owner: both

Context:
- `telegram_bot.py` is long and contains many working flows.
- Rewriting it all at once is high risk.
- The system still needs admin-only access, rate limiting, and data-source disclosure.

Decision:
- Keep `telegram_bot.py` intact for now.
- Run Telegram through `telegram_bot_secure_runner.py`.
- Docker Compose should start Telegram using `python3 telegram_bot_secure_runner.py`.

Why:
- This adds guardrails without a risky large rewrite.
- It keeps current Telegram flows working.
- It gives time to add tests and refactor gradually.

Consequences:
- Future agents must not bypass the secure runner.
- A future refactor may move these protections directly into smaller Telegram modules.

Related files:
- `telegram_bot.py`
- `telegram_bot_secure_runner.py`
- `docker-compose.yml`

### ADR-20260509-002 — Track user requirements and agent tasks inside the repo

Status: accepted
Date: 2026-05-09
Owner: both

Context:
- The user wants efficient AI-agent development with minimal repeated explanations.
- Requirements evolve over time.
- Multiple agents may work on the repo.

Decision:
- Use `docs/USER_REQUIREMENTS.md` for user requirements.
- Use `docs/AGENT_TASKS.md` for agent task tracking.
- Use `docs/SYSTEM_STATE.md` for current truth.

Why:
- Reduces token waste.
- Preserves context between sessions.
- Helps agents avoid unrelated changes.

Consequences:
- Agents should update these files when doing meaningful work.
- These docs must remain concise and current.

Related files:
- `docs/USER_REQUIREMENTS.md`
- `docs/AGENT_TASKS.md`
- `docs/SYSTEM_STATE.md`

### ADR-20260509-003 — Treat fallback data as uncertainty, not truth

Status: accepted
Date: 2026-05-09
Owner: both

Context:
- Market data, NAV, and external sources may be unavailable or stale.
- The user makes trading decisions based on system output.

Decision:
- User-facing reports must mark fallback/cached/estimated values clearly.

Why:
- Prevents misleading confidence.
- Keeps the system honest.

Consequences:
- Report builders must include data-source labels when relevant.
- Tests should protect fallback disclosure behavior.

Related files:
- `docs/DATA_CONTRACTS.md`
- `telegram_bot_secure_runner.py`
- `engine_core.py`
