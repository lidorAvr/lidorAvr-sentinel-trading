# Quality Gates

This file defines the minimum checks before code is considered safe.

## Gate 1 — Documentation and scope

Required for every non-trivial task:

- Requirement added or updated in `docs/USER_REQUIREMENTS.md`.
- Task added or updated in `docs/AGENT_TASKS.md`.
- Affected services identified.
- Risk level identified.

## Gate 2 — Data correctness

Required if touching:

- NAV
- account size
- R multiple
- exposure
- PnL
- campaign aggregation
- stop-loss logic
- market data source

Checks:

- Formula is documented.
- Test data exists.
- Fallback/cached data is clearly marked.
- Output does not imply false precision.

## Gate 3 — Telegram safety and UX

Required if touching Telegram:

- Telegram still runs through `telegram_bot_secure_runner.py` or equivalent protections exist.
- Admin-only behavior remains active.
- Rate-limit/cooldown behavior remains active.
- Hebrew output remains readable.
- Long reports are split safely.
- Sensitive reports disclose data source or uncertainty.

## Gate 4 — Supabase writes

Required if touching database updates:

- Write path is explicit.
- User action or deterministic rule is documented.
- No read-only report accidentally mutates data.
- Existing records remain backward compatible.

## Gate 5 — Deployment safety

Required if touching Docker or service startup:

- `docker-compose.yml` remains valid.
- Only affected service is rebuilt when possible.
- Rollback command is documented.
- Logs are checked after deployment.

## Gate 6 — Tests

Required for logic changes:

```bash
pytest -q
```

Tests must be deterministic and must not require secrets.

## Gate 7 — Manual smoke test

Required for Telegram changes after deployment:

```text
/portfolio
/next
/trade CAT
```

Also send several messages quickly to verify rate limiting.

## Definition of ready to merge/deploy

A change is ready only when:

- scope is clear,
- tests pass,
- data contracts are respected,
- deployment path is clear,
- rollback path is clear,
- and no unrelated service is affected.
