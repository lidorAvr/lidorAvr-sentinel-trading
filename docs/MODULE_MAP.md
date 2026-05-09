# Module Map

This file explains the purpose of the main files and how they depend on each other.

## `engine_core.py`

Core analytical engine.

Responsibilities:

- market data retrieval and caching through yfinance / Yahoo fallback
- ATR and moving-average calculations
- sector / relative strength mapping
- distribution and accumulation day detection
- trade-stage classification
- position scoring
- hard-rule risk evaluation
- management action suggestions
- open campaign aggregation
- market regime calculation
- Minervini-style analysis helpers

High-risk areas:

- `get_open_positions_campaign`
- `evaluate_position_engine`
- `calculate_atr_series`
- `safe_return`
- `compute_behavior_features`
- `evaluate_hard_rules`
- `score_position`

Rules:

- Do not change risk math without tests.
- Do not change campaign aggregation without sample trade rows.
- Do not change ALGO caps without documenting the reason.
- Do not remove cache behavior without considering provider rate limits.

## `telegram_bot.py`

Main Telegram interaction layer.

Responsibilities:

- menu handling
- backlog/journal completion
- `/portfolio`
- `/next`
- `/trade SYMBOL` / drill-down flows
- user prompts for setup, quality, stops, images, management notes
- Supabase reads and writes
- formatting Telegram reports

Risks:

- very long file
- many implicit flows
- direct Supabase mutation paths
- user-facing reports can become too long or misleading

Rules:

- Avoid broad rewrites.
- Prefer extracting small helpers into new files.
- Always keep Hebrew output readable.
- Any Supabase update must be intentional and traceable.
- Keep `send_long_message` behavior for long reports.

## `telegram_bot_secure_runner.py`

Runtime safety wrapper for Telegram.

Responsibilities:

- run the existing Telegram bot through a protective layer
- enforce `TELEGRAM_ADMIN_ID`
- rate-limit burst usage
- add cooldown after spam-like behavior
- append a data-source note to user-facing reports

Rules:

- Do not bypass this runner in production unless protections are moved directly into `telegram_bot.py`.
- If Docker Compose changes the Telegram command, verify the runner is still active.
- Keep guard logic simple and deterministic.

## `main.py`

Direct sync / account update layer.

Responsibilities may include:

- syncing trading/account information
- updating local config or NAV-related state
- triggering data writes used by other services

Rules:

- Any NAV/account-size write must be documented.
- Ensure Telegram and dashboard read the same account assumptions.
- Avoid multiple competing config file paths.

## `dashboard.py`

Streamlit dashboard.

Responsibilities:

- visual inspection of trades and portfolio state
- user-friendly monitoring
- charts/tables for analysis

Rules:

- Dashboard can be more verbose than Telegram.
- It must still identify fallback/estimated values clearly.
- Avoid calculations that conflict with `engine_core.py`; reuse engine functions where possible.

## `risk_monitor.py`

Automated risk monitoring service.

Responsibilities:

- periodic monitoring
- risk warnings
- possibly Telegram notifications

Rules:

- Must not spam Telegram.
- Must respect the same truth/fallback rules as other reports.
- Must not auto-mutate trade management state unless explicitly designed and documented.

## `docker-compose.yml`

Production wiring.

Current important command:

```yaml
telegram-bot:
  command: python3 telegram_bot_secure_runner.py
```

Rules:

- Do not change Telegram service back to `telegram_bot.py` without replacing the runner protections.
- Rebuild only affected services when possible.
- Validate logs after deployment.

## `requirements.txt`

Runtime dependencies.

Rules:

- Keep dependency additions minimal.
- Avoid unnecessary heavy packages.
- If changing yfinance/pandas/openai/supabase dependencies, verify compatibility.

## `.github/workflows/tests.yml`

CI workflow.

Responsibilities:

- install dev requirements
- run pytest

Rules:

- Keep CI fast.
- Do not add tests that require secrets or live APIs.
- Prefer deterministic unit tests.

## `tests/`

Test suite.

Current focus:

- math regression tests
- secure runner tests
- Telegram UX contracts

Rules:

- Tests should protect behavior, not implementation details unless needed for safety.
- Add fixtures for trade rows when changing campaign logic.
- Avoid external network calls in tests.
