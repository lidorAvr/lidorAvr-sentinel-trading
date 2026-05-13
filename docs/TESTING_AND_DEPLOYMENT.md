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

Current passing test count: **1107 tests**.

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
- stat_bucket classification (`classify_stat_bucket`, `is_stat_countable`)

### Adaptive risk engine

Add tests when changing:

- `compute_closed_campaigns()` — especially stat_bucket assignment per campaign
- `_is_disc()` — must filter by `is_stat_countable(bucket)`, not raw setup_type
- Win rate and expectancy calculations — must exclude DATA_INCOMPLETE and ALGO_OBSERVED
- Direction change or streak detection

Reference: `tests/test_adaptive_risk_engine.py` covers:
- VCP_MANUAL / DATA_INCOMPLETE / ALGO_OBSERVED bucket assignment in `compute_closed_campaigns()`
- Win rate filter for stat_countable campaigns only
- Streak filter for disc-only campaigns
- Legacy dict fallback for old state format

### risk_monitor anti-spam

Add tests when changing:

- `build_position_alert_key()` — must NOT include `trigger`
- `should_alert()` — escalation, cooldown, non-escalating change
- Giveback zone-change detection — fires on zone change only
- BROKEN state gate on Giveback
- `sizing_leak_alerted` one-time flag behavior
- `last_digest_date` one-per-day gate for Daily Digest

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

Typical deploy flow for Telegram changes:

```bash
cd ~/sentinel_trading
git pull
docker compose up -d --build telegram-bot
docker logs -f telegram-bot
```

If risk-monitor or dashboard changed:

```bash
docker compose up -d --build risk-monitor dashboard
docker logs -f risk-monitor
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

## Risk monitor smoke tests

After deploying `risk_monitor.py` changes, verify:

1. **No spam on first run** — only one Live Alert per position unless status truly escalated.
2. **Giveback fires only on zone change** — confirm with two runs where price stays in same zone: no second alert.
3. **Sizing Leak fires once** — confirm `sizing_leak_alerted = true` in state file after first fire.
4. **Daily Digest timing** — set system time or confirm logs show digest fires once in the 21:00–22:00 UTC window on a weekday.
5. **BROKEN gate** — after BROKEN status, confirm no Giveback fires even if price drops further.

State file inspection:

```bash
cat risk_monitor_state.json | python3 -m json.tool | head -100
```

Check that:
- `sizing_leak_alerted` is present for any small-sized position that fired
- `last_digest_date` updates to today after digest fires
- `last_giveback_class` reflects most recent zone (even when no alert fired)

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

reporting-service:
  command: python3 report_scheduler.py
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
docker logs -f reporting-service
```

For recent logs only:

```bash
docker logs --tail=200 telegram-bot
docker logs --tail=200 risk-monitor
```

## Rollback examples

Rollback latest code:

```bash
git log --oneline -5
git revert <commit_sha>
docker compose up -d --build telegram-bot
```

Rollback risk-monitor only:

```bash
docker compose stop risk-monitor
git revert <commit_sha>
docker compose up -d --build risk-monitor
docker logs -f risk-monitor
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
- risk-monitor smoke test (if risk_monitor.py changed)

Rollback:
- ...
```
