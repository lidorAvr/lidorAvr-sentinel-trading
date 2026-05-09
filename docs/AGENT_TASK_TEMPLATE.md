# Agent Task Template

Use this template for every non-trivial AI-agent task.

## Task

Describe the requested change in one sentence.

```text
...
```

## Risk level

Choose one:

- Low
- Medium
- High

High-risk examples:

- NAV/account size
- R/Risk/PnL math
- Supabase writes
- Telegram command routing
- Docker Compose service commands
- authentication / anti-spam

## Affected files

List files likely to change:

```text
...
```

## Affected services

Choose all that apply:

- `sentinel-bot`
- `telegram-bot`
- `dashboard`
- `risk-monitor`
- CI/tests only
- documentation only

## Data impact

Does this change touch any of the following?

- Supabase rows
- campaign aggregation
- NAV/account settings
- live/cached market data
- R multiple
- exposure percentage
- stop-loss logic
- user-facing Telegram reports

Explain:

```text
...
```

## Truth/fallback behavior

Will any output rely on fallback/cached/default data?

If yes, explain how the user will know:

```text
...
```

## Test plan

Required tests or checks:

```bash
pytest -q
```

Manual checks, if needed:

```text
/portfolio
/next
/trade CAT
```

## Rollback plan

How to undo safely:

```text
...
```

## Completion checklist

- [ ] I read `AGENTS.md`.
- [ ] I read relevant docs under `docs/`.
- [ ] I identified affected services.
- [ ] I avoided unrelated rewrites.
- [ ] I preserved Telegram guardrails.
- [ ] I marked fallback/estimated data clearly.
- [ ] I added or updated tests when logic changed.
- [ ] I documented deployment impact.
