# Testing and Deployment

## Local test command

Run:

```bash
pytest -q
```

If dependencies are missing:

```bash
pip install -r requirements-dev.txt
pytest -q
```

## CI

GitHub Actions workflow:

```text
.github/workflows/tests.yml
```

The workflow installs `requirements-dev.txt` and runs `pytest -q`.

Tests should not require:

- Telegram token
- Supabase credentials
- OpenAI key
- live IBKR data
- live Yahoo requests

## Tests that should exist for high-risk changes

### Engine math

Add tests when changing:

- ATR
- R-multiple
- trade stage
- time efficiency
- position score
- open campaign aggregation
- ALGO exposure caps
- market regime

### Telegram

Add tests or manual checklist when changing:

- command handlers
- callback formats
- report formatting
- long-message splitting
- RTL behavior
- secure runner behavior
- rate limit behavior

### Supabase writes

Add tests or fixtures when changing:

- backlog auto-fill
- initial stop updates
- setup/quality scoring
- management notes
- campaign inheritance

## Manual deployment on Orange Pi

Typical deploy flow:

```bash
cd ~/sentinel_trading
git pull
docker compose up -d --build telegram-bot
docker logs -f telegram-bot
```

If multiple services changed:

```bash
docker compose up -d --build
```

Prefer rebuilding only the affected service.

## Required Telegram smoke tests

After deploying Telegram changes, test:

```text
/portfolio
/next
/trade CAT
/help
```

Also test fast repeated messages to verify rate limiting.

Expected behavior:

- bot responds only to the admin user
- bot does not crash on repeated messages
- portfolio report is readable
- long reports are split correctly
- reports include data-source/fallback disclosure when relevant

## NAV validation checklist

After changes touching NAV/account settings:

1. Run or wait for IBKR sync.
2. Inspect the config/source file used by the service.
3. Verify Telegram output uses the same NAV/account-size assumption.
4. Verify dashboard uses the same assumption.
5. Compare against IBKR/account source.
6. If fallback is used, verify output clearly says so.

## Docker service commands

Current expected commands:

```yaml
sentinel-bot:
  command: python3 main.py

telegram-bot:
  command: python3 telegram_bot_secure_runner.py

dashboard:
  command: streamlit run dashboard.py

risk-monitor:
  command: python risk_monitor.py
```

If the Telegram command is changed back to `telegram_bot.py`, admin/rate-limit protections may be bypassed.

## Log inspection

Useful commands:

```bash
docker ps
docker logs -f telegram-bot
docker logs -f sentinel-bot
docker logs -f risk-monitor
docker logs -f dashboard
```

For recent logs only:

```bash
docker logs --tail=200 telegram-bot
```

## Rollback examples

Rollback latest code:

```bash
git log --oneline -5
git revert <commit_sha>
docker compose up -d --build telegram-bot
```

Emergency Telegram rollback only if secure runner itself fails:

1. Change Telegram command temporarily to `python3 telegram_bot.py`.
2. Rebuild `telegram-bot`.
3. Fix secure runner.
4. Restore `python3 telegram_bot_secure_runner.py`.

## Release notes template

For every meaningful change, include:

```text
Changed:
- ...

Risk:
- low / medium / high

Affected service:
- ...

Tests:
- pytest -q
- manual Telegram smoke test

Rollback:
- ...
```
