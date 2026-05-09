# Data Contracts

This file defines the data assumptions that future agents must preserve.

## Core principle

The system should show the user the truth, or clearly mark uncertainty.

If a value is computed from fallback data, cached data, default config, or incomplete records, the output must say so.

## Trade row contract

Trade rows are stored in Supabase, usually in a `trades` table.

Common fields observed in the system:

- `trade_id`
- `symbol`
- `trade_date`
- `side`
- `quantity`
- `price`
- `pnl_usd`
- `commission`
- `stop_loss`
- `initial_stop`
- `setup_type`
- `quality`
- `score`
- `image_url`
- `management_notes`
- `campaign_id`
- `parent_trade_id`
- `management_state`
- `management_flags`
- `target_risk_usd`

Do not assume every field is always populated. Existing code often handles missing values.

## Side and quantity rules

Current logic assumes:

- buy rows increase campaign quantity
- sell rows reduce campaign quantity
- open campaign exists when net quantity is greater than zero

Be careful: some brokers/export paths may store sell quantity as negative. Before changing quantity logic, inspect real rows.

## Campaign contract

A campaign is one trade idea.

One campaign can include:

- one or more buys
- partial sells
- final sell
- runner state
- management notes

Campaign-level calculations should not treat every row as a separate independent trade.

## Initial risk contract

For discretionary trades such as EP/VCP:

- initial risk should usually be based on first-day buy price/quantity and initial stop
- partial sells should not rewrite the original campaign risk
- R calculations must be based on the correct original risk basis

For ALGO trades:

- ALGO can use different risk interpretation
- symbol exposure caps are more important than discretionary initial-stop sizing

## NAV / account-size contract

NAV/account size can affect:

- risk per trade
- exposure percent
- target risk in dollars
- sizing status
- portfolio-level warnings

Rules:

1. There must be one clear source of truth for NAV/account-size.
2. If IBKR NAV is unavailable and the system falls back to deposited capital/default value, the report must say so.
3. Do not silently mix host paths and container paths.
4. If modifying config paths, update Docker Compose, docs, and tests together.

Known deployment detail:

- Docker services mount the repo into `/app`.
- `docker-compose.yml` currently runs Telegram through `telegram_bot_secure_runner.py`.

## Market data contract

`engine_core.py` retrieves data through yfinance and fallback scraping/cached history.

Rules:

- Live price may be unavailable.
- Cached price may be stale.
- Historical close is not the same as live price.
- Any report using fallback price must identify the uncertainty.

## Telegram report contract

Telegram output should include enough information to act safely, but not overload the user.

Required properties:

- Hebrew-friendly layout
- short sections
- clear action/trigger/status
- no misleading precision
- source/fallback disclosure for risk-sensitive reports
- long reports split below Telegram limits

## Supabase write contract

Supabase writes happen in user workflows, especially backlog/journal completion.

Rules:

- Do not write to Supabase from a read-only report flow unless explicitly required.
- Do not auto-fill missing values unless the rule is deterministic and documented.
- When inheriting values from older campaign rows, keep the logic transparent.
- Any new mutation path should be isolated and testable.

## Status contract

Common position statuses include:

- Power
- Healthy
- Yellow Flag
- Weak
- Broken
- Climactic

Do not change status names lightly because user-facing reports and mental models rely on them.

## Risk language contract

The user expects direct language. Avoid vague output.

Good:

- `לא להוסיף. להחזיק ולעקוב אחרי שבירת MA20.`
- `הנתון משוער כי מחיר חי לא זמין.`

Bad:

- `נראה בסדר כנראה.`
- `המערכת מעריכה מצב חיובי` without evidence.

## Schema change protocol

If adding/removing/changing a field:

1. Document it here.
2. Update all modules that read/write it.
3. Add tests or migration notes.
4. Confirm backward compatibility with existing rows.
