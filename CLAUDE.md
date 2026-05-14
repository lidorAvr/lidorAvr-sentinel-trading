# Claude Code Context — Sentinel Trading

Start here before editing any code.

## Mission

You are working on a production-like personal trading intelligence system. The user uses this repo to manage real trading decisions, risk, Telegram reports, and portfolio state.

Your job is to improve the system without breaking existing flows.

## Mandatory reading order

**Fast-track (single doc, recommended for first read after Sprint 11):**

1. `docs/NEXT_SESSION_BRIEF.md` — current state, open work items, hard constraints

**Full reading (after fast-track or when going deep into core changes):**

1. `AGENTS.md`
2. `docs/AI_AGENT_CONTEXT.md`
3. `docs/MODULE_MAP.md`
4. `docs/DATA_CONTRACTS.md`
5. `docs/SAFE_CHANGE_PROTOCOL.md`
6. `docs/TESTING_AND_DEPLOYMENT.md`
7. `docs/SPRINT_11_RESEARCH_AUDIT_2026_05_14.md` — methodology gap analysis

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

- `engine_core.py`: math, market data, campaign aggregation, FTD, Trend Template
- `adaptive_risk_engine.py`: 4 ladder gates (closed-campaigns / cold-regime / per-bucket / drawdown)
- `risk_monitor.py`: anti-spam state machine + Morning Briefing + Daily Digest
- `task_engine.py`: 5 setup-aware management rules (BE/trail/dead-money/breach/loose-stop)
- `telegram_bot.py`: top-level router (already extracted to 9 sub-modules)
- `docker-compose.yml`: production service commands
- NAV/account config: can distort risk and exposure if stale

## Preferred refactor direction

The Phase 4 refactor (Sprint 9-era) split `telegram_bot.py` from 2000+ to 458
lines across 9 modules. The Sprint 10/11 work continued that pattern:

- `task_engine.py` / `task_state.py` / `telegram_tasks.py` — Task Review
- `setup_profile.py` / `setup_performance.py` — per-setup methodology

When adding new features, follow this pattern:
- pure-logic module (engine-like) at root
- UI module (`telegram_<feature>.py`) under root
- state persistence (`<feature>_state.py`) if applicable
- dedicated test file per module

DO NOT bundle UI + logic + state in one file.

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
