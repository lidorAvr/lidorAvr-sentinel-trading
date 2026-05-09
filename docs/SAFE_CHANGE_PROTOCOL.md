# Safe Change Protocol

This protocol is mandatory for humans and AI agents working on this repo.

## Goal

Improve the system without breaking unrelated parts.

The system has multiple coupled areas:

- broker/account sync
- Supabase trade records
- Telegram workflows
- risk engine
- dashboard
- risk monitor
- Docker deployment

A change in one area can break another area. Always reason about downstream impact.

## Change categories

### Low-risk changes

Examples:

- documentation updates
- wording improvements that do not affect commands or parsing
- adding tests
- adding non-used helper functions

Process:

1. Make the change.
2. Run tests.
3. Verify no production command changed unexpectedly.

### Medium-risk changes

Examples:

- Telegram message formatting
- dashboard layout
- adding a new read-only report
- adding a new non-mutating metric

Process:

1. Identify user-facing behavior.
2. Keep the old path working.
3. Add a fallback if data is missing.
4. Add tests where possible.
5. Manually test Telegram/dashboard behavior.

### High-risk changes

Examples:

- R-multiple math
- NAV/account size handling
- open campaign aggregation
- Supabase writes
- Docker Compose commands
- Telegram authorization / anti-spam
- any auto-management or auto-update behavior

Process:

1. Stop and document the intended behavior.
2. Add or update tests first.
3. Use sample rows and edge cases.
4. Make a small change.
5. Run tests.
6. Verify Docker command if service behavior changed.
7. Document rollback.

## Mandatory impact checklist

Before changing code, answer these questions in the PR/commit notes or working notes:

1. Which service is affected?
2. Does it read or write Supabase?
3. Does it affect NAV, R, exposure, PnL, or stop logic?
4. Does it affect Telegram output?
5. Does it affect Docker deployment?
6. Does it introduce live API dependency?
7. What is the rollback path?

## Rules for `engine_core.py`

`engine_core.py` is the math engine. Treat it like a library.

Do:

- add deterministic unit tests
- use small pure helper functions
- document new risk formulas
- keep old behavior unless intentionally changed

Do not:

- change formulas silently
- add network calls to functions that should be pure
- mix user-facing Hebrew strings deeply into core formulas unless already existing
- make campaign logic depend on UI assumptions

## Rules for `telegram_bot.py`

`telegram_bot.py` is long and high-risk.

Do:

- keep changes narrow
- extract helpers to new modules
- preserve existing commands
- keep `send_long_message` for long reports
- keep Hebrew output readable

Do not:

- rewrite the whole file in one pass
- remove existing callback formats without migration
- add new Supabase writes without documenting them
- bypass `telegram_bot_secure_runner.py`

## Rules for `telegram_bot_secure_runner.py`

This file protects the bot until the Telegram layer is refactored.

Do:

- keep access control and rate limit active
- keep behavior deterministic
- keep messages short

Do not:

- remove admin checks
- remove cooldown behavior
- call Supabase from this wrapper
- add complex business logic here

## Rules for Supabase writes

Every write must be intentional.

Safe examples:

- user explicitly submitted a quality score
- user explicitly entered an initial stop
- deterministic backlog inheritance from same campaign

Unsafe examples:

- auto-changing stops from analysis output without user confirmation
- overwriting setup type from weak inference
- filling unknown values with defaults that look real

## Rules for fallback data

Fallbacks are allowed only if marked.

Examples of fallback:

- live price unavailable, using last close
- IBKR NAV unavailable, using deposited capital
- sector unavailable, using cached hardcoded sector map

User-facing reports must mark this as estimated/cached/fallback.

## Rollback protocol

If production breaks after a change:

1. Stop only the affected service if possible.
2. Check logs.
3. Revert the last commit or restore previous command.
4. Rebuild only the affected container.
5. Verify Telegram and dashboard manually.

Common rollback for Telegram runner:

```bash
docker compose stop telegram-bot
# temporarily revert command to python3 telegram_bot.py only if secure runner itself is the problem
docker compose up -d --build telegram-bot
```

Use direct `telegram_bot.py` only as an emergency rollback, because it bypasses the runner protections.

## Refactor protocol

When splitting long files:

1. Extract one concern at a time.
2. Keep public function behavior identical.
3. Add tests around extracted behavior.
4. Do not mix refactor with feature changes.
5. Commit refactor separately from behavior changes.

Recommended future splits:

- `telegram_handlers.py`
- `telegram_formatters.py`
- `telegram_backlog.py`
- `portfolio_reports.py`
- `supabase_repository.py`
- `risk_formatters.py`
- `config.py`
