# Current System State

This file is a concise source of truth for the current repo state.

Update it after meaningful architecture, deployment, or workflow changes.

## Current date context

Last updated: 2026-05-09

## Production wiring

Docker Compose services:

- `sentinel-bot` runs `python3 main.py`
- `telegram-bot` runs `python3 telegram_bot_secure_runner.py`
- `dashboard` runs `streamlit run dashboard.py`
- `risk-monitor` runs `python risk_monitor.py`

## Telegram hardening status

Current status: implemented in code, requires server deployment verification.

Protection layer:

- `telegram_bot_secure_runner.py`

It adds:

- admin-only access through `TELEGRAM_ADMIN_ID`
- rate limiting
- cooldown after bursts
- data-source disclosure note for sensitive reports

Open validation:

- Pull latest `main` on server.
- Rebuild/restart `telegram-bot`.
- Test Telegram commands and rate limiting.

## Documentation status

Agent onboarding docs exist:

- `AGENTS.md`
- `CLAUDE.md`
- `docs/README.md`
- `docs/AI_AGENT_CONTEXT.md`
- `docs/MODULE_MAP.md`
- `docs/DATA_CONTRACTS.md`
- `docs/SAFE_CHANGE_PROTOCOL.md`
- `docs/TESTING_AND_DEPLOYMENT.md`
- `docs/AGENT_TASK_TEMPLATE.md`
- `docs/CHANGE_IMPACT_MATRIX.md`
- `docs/USER_REQUIREMENTS.md`
- `docs/AGENT_TASKS.md`

## Known high-risk areas

1. `telegram_bot.py` is long and should not be rewritten wholesale.
2. NAV/config path consistency must be validated on the server.
3. Campaign/R calculations must be protected with tests.
4. Supabase write flows must remain explicit and traceable.
5. Telegram output must remain Hebrew-friendly and not too verbose.

## Current next steps

1. Deploy latest `main` to server.
2. Verify `telegram-bot` starts with secure runner.
3. Validate NAV/account-size data source.
4. Add more deterministic tests for campaign aggregation and NAV fallback.
5. Begin gradual Telegram refactor only after tests are stronger.

## Do not forget

A successful code change is not complete until:

- tests pass,
- server deploy is clear,
- Telegram smoke test passes,
- and fallback data is not shown as exact truth.
