# Change Impact Matrix

Use this file before changing code. Its purpose is to prevent a local improvement from damaging another service.

## Engine changes

Files usually involved:

- `engine_core.py`
- tests under `tests/`

Possible impact:

- R calculations
- position status
- exposure calculations
- portfolio reports
- dashboard and monitoring output

Required checks:

- run `pytest -q`
- add deterministic test data for changed formulas
- verify one open campaign manually

## Telegram changes

Files usually involved:

- `telegram_bot.py`
- `telegram_bot_secure_runner.py`

Possible impact:

- user commands
- callback buttons
- journal completion
- Supabase updates
- Hebrew message layout

Required checks:

- test `/portfolio`
- test `/next`
- test `/trade CAT`
- verify long messages still split correctly
- verify user-facing data source notes still appear where needed

## Sync and NAV changes

Files usually involved:

- `main.py`
- config files
- Docker environment

Possible impact:

- account size
- target risk
- exposure percentage
- sizing status

Required checks:

- compare NAV/account value to the broker/source
- verify Telegram and dashboard use the same assumption
- clearly mark fallback values

## Dashboard changes

Files usually involved:

- `dashboard.py`
- `engine_core.py`

Possible impact:

- visual interpretation
- manual trade decisions
- mismatch with Telegram reports

Required checks:

- reuse engine functions where possible
- avoid separate conflicting formulas
- mark cached or estimated values

## Monitor changes

Files usually involved:

- `risk_monitor.py`
- Telegram/report helpers

Possible impact:

- alert frequency
- noise level
- risk messaging

Required checks:

- keep alerts bounded
- avoid duplicate reports
- verify messages are short and actionable

## Docker changes

Files usually involved:

- `docker-compose.yml`
- `Dockerfile`
- environment files

Possible impact:

- service startup
- mounted paths
- production command routing

Required checks:

- run `docker compose config`
- rebuild only affected services when possible
- inspect logs after deployment
- keep Telegram routed through `telegram_bot_secure_runner.py` unless equivalent protections exist elsewhere

## Documentation changes

Files usually involved:

- `AGENTS.md`
- `CLAUDE.md`
- `docs/`

Possible impact:

- future agent behavior
- development consistency

Required checks:

- keep commands aligned with actual code
- update related docs together
- avoid outdated assumptions
