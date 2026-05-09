# Claude Code Context — Sentinel Trading

Start here before editing any code.

## Mission

You are working on a production-like personal trading intelligence system. The user uses this repo to manage real trading decisions, risk, Telegram reports, and portfolio state.

Your job is to improve the system without breaking existing flows.

## Mandatory reading order

1. `AGENTS.md`
2. `docs/AI_AGENT_CONTEXT.md`
3. `docs/MODULE_MAP.md`
4. `docs/DATA_CONTRACTS.md`
5. `docs/SAFE_CHANGE_PROTOCOL.md`
6. `docs/TESTING_AND_DEPLOYMENT.md`

Do not make non-trivial changes before reading these files.

## Hard constraints

- Do not remove Telegram admin protection.
- Do not bypass `telegram_bot_secure_runner.py` in production.
- Do not silently present fallback data as exact truth.
- Do not change R, NAV, exposure, or campaign math without tests.
- Do not mutate Supabase from read-only flows.
- Do not rewrite `telegram_bot.py` wholesale.
- Do not commit secrets.

## Current production wiring

`docker-compose.yml` should run:

```yaml
telegram-bot:
  command: python3 telegram_bot_secure_runner.py
```

This is intentional. It adds runtime guardrails around the older Telegram bot.

## Safe development approach

For each task:

1. Classify risk: low, medium, or high.
2. Identify affected services.
3. Read the relevant docs.
4. Make a small change.
5. Add/update tests if logic changed.
6. Run `pytest -q`.
7. Document deployment/rollback if production behavior changed.

## Most fragile areas

- `engine_core.py`: math, market data, campaign aggregation.
- `telegram_bot.py`: long file with many workflows and Supabase writes.
- `docker-compose.yml`: production service commands.
- NAV/account config: can distort risk and exposure if stale.

## Preferred refactor direction

Do not make a giant rewrite. Instead split gradually:

- extract Telegram formatting helpers
- extract Supabase repository layer
- extract portfolio report builder
- extract risk/NAV config helper
- add tests for each extraction

## Output style for Telegram

Keep Hebrew messages:

- short
- direct
- RTL-friendly
- actionable
- clear about fallback/cached data

## When uncertain

If you are not sure whether data is live, stale, cached, estimated, or fallback, say so explicitly in the output or code comments.

Accuracy is more important than confidence.
