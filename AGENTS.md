# Sentinel Trading — Agent Operating Guide

This repository is a personal trading intelligence and risk-control system. Treat it as a production system that can affect real trading decisions.

## Prime directive

Do not optimize one area by breaking another area. Every change must preserve these invariants:

1. User-facing Telegram messages must not present fallback or stale data as exact truth.
2. NAV, risk, R-multiple, exposure, and PnL math must remain explainable and testable.
3. Telegram must remain admin-only and resistant to spam/burst usage.
4. Supabase trade records must not be mutated unless the user action explicitly requires it.
5. Existing EP, VCP, ALGO, portfolio, dashboard, and risk-monitor flows must continue working.
6. Hebrew RTL readability matters. Keep Telegram output short, structured, and readable.
7. Alert anti-spam rules must be preserved. Never add recurring alerts without per-position state dedup.
8. Win Rate and Expectancy must never include DATA_INCOMPLETE or ALGO_OBSERVED campaigns.

## Read these files first

Before modifying code, read:

1. `docs/AI_AGENT_CONTEXT.md`
2. `docs/MODULE_MAP.md`
3. `docs/DATA_CONTRACTS.md`
4. `docs/SAFE_CHANGE_PROTOCOL.md`
5. `docs/TESTING_AND_DEPLOYMENT.md`

## Production services

The Docker Compose services are:

- `sentinel-bot`: runs `main.py`, responsible for the direct sync layer.
- `telegram-bot`: runs `telegram_bot_secure_runner.py`, which wraps the existing Telegram bot with guardrails.
- `dashboard`: runs `dashboard.py` using Streamlit.
- `risk-monitor`: runs `risk_monitor.py`.
- `reporting-service`: runs `report_scheduler.py`.

Do not bypass `telegram_bot_secure_runner.py` unless you intentionally replace its protections inside `telegram_bot.py`.

## Critical code areas

- `engine_core.py`: technical/risk engine. Highest risk for math regressions.
- `telegram_bot.py`: user-facing Telegram workflows and Supabase write flows. High UX and safety risk.
- `telegram_bot_secure_runner.py`: runtime guard for Telegram access, spam protection, and data-source disclosure.
- `main.py`: sync layer and account/config updates.
- `dashboard.py`: visual inspection layer. Contains Trader Edge Panel and Adaptive Risk sidebar.
- `risk_monitor.py`: monitoring and automated risk alerts. Contains anti-spam state machine.
- `adaptive_risk_engine.py`: stat_bucket classification and adaptive risk recommendation.
- `docker-compose.yml`: production service wiring.

## Required workflow for any change

1. Identify affected module and downstream modules.
2. Add or update tests before changing core math or data contracts.
3. Keep changes small and reversible.
4. Run `pytest -q` locally or through CI.
5. For Telegram changes, manually test `/portfolio`, `/next`, and `/trade SYMBOL` after deployment.
6. For NAV or risk changes, verify values against IBKR/source data before trusting output.
7. For risk_monitor changes, verify no new alert fires more than once without a state flag.

## Red lines

Do not:

- Remove admin protection from Telegram.
- Remove anti-spam behavior.
- Replace campaign/R/risk formulas without tests.
- Silently fallback from live price or NAV to old/default values.
- Change database semantics without updating `docs/DATA_CONTRACTS.md`.
- Add huge AI-generated rewrites to `telegram_bot.py` without splitting modules first.
- Put secrets, tokens, account numbers, or credentials in the repo.
- Mix ALGO campaigns into Win Rate or Expectancy calculations.
- Add a recurring Telegram alert that does not check a per-position dedup flag in state.

## Preferred development style

- Prefer additive wrappers and tests before large rewrites.
- Split long files gradually.
- Keep user-facing text direct, short, and Hebrew-friendly.
- Keep English code identifiers stable.
- Write comments only where they protect future maintainers from mistakes.

## Definition of done

A change is done only when:

- tests pass,
- deployment command is clear,
- user-facing behavior is documented,
- rollback path is clear,
- and no unrelated service is affected.
