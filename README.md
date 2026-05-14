# 🛡️ Sentinel Trading

Personal AI-driven portfolio management system implementing **Mark Minervini's
SEPA methodology** (Specific Entry Point Analysis) — risk-first, R-multiple
based, with adaptive sizing and trader development tracking.

[![Sentinel Tests](https://github.com/lidorAvr/lidorAvr-sentinel-trading/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/lidorAvr/lidorAvr-sentinel-trading/actions/workflows/tests.yml)
![Tests](https://img.shields.io/badge/tests-1321%20passing-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-68.9%25-yellow)
![Python](https://img.shields.io/badge/python-3.11-blue)
![License](https://img.shields.io/badge/license-Private-lightgrey)

---

## What it does

Sentinel watches a personal trading account in real time and:

- **Sizes risk** adaptively from a 7-step ladder driven by recent performance
  (S9 / M21 / L50 weighted heat score, 0-100)
- **Manages campaigns** through a 10-state machine (NEW → PROVING → WORKING →
  RUNNER → BROKEN, plus DEAD_MONEY, PROFIT_PROTECTION, etc.)
- **Suggests trailing stops** that scale with ATR (2-8% buffer depending on
  volatility — tight on NVDA, wide on MNST)
- **Validates add-on entries** against 5 eligibility gates (data, ALGO, cushion,
  open-risk, chase) before the trader commits
- **Reports weekly/monthly** PDF + Telegram summary with heat-score thermometer
  and trader development score
- **Audits every state-changing action** to a Supabase `audit_log` table
- **Self-monitors** via 14 health checks accessible from `/system_health` in
  Telegram

## Architecture (one-line tour)

```
Supabase (truth)  →  engine_core (math)  →  risk_monitor (1-min cycle)
                                          ↘
                                            telegram_bot  →  Trader
                                          ↗
                            adaptive_risk_engine (7-step ladder)
```

5 Docker services on an Orange Pi 5:

| Service | Job | Healthcheck |
|---------|-----|-------------|
| `sentinel-bot` | IBKR sync + heartbeat | mtime of `/app/state/sentinel_bot_last_cycle` |
| `telegram-bot` | User interaction | mtime of `/app/state/telegram_bot_last_cycle` |
| `risk-monitor` | 1-min position cycle | mtime of `/app/state/risk_monitor_last_cycle` |
| `reporting-service` | Weekly + monthly reports | mtime of `/app/state/report_scheduler_last_cycle` |
| `dashboard` | Streamlit (port 8501) | `/healthz` |
| `autoheal` | Restart unhealthy containers | docker.sock |

## Repo orientation

- **Production code:** root-level `.py` files (`engine_core.py`, `risk_monitor.py`, etc.)
- **Telegram surface:** `telegram_bot.py` + `telegram_*.py` extracted modules
- **Tests:** `tests/` (1258 passing)
- **Docs:** `docs/` — start with [`docs/README.md`](docs/README.md) for the AI-agent reading order
- **Infrastructure:** `docker-compose.yml`, `.github/workflows/`, `migrations/`

## Quick start

### Local dev

```bash
pip install -r requirements-dev.txt
pytest --tb=short -q
```

Coverage gate (matches CI):
```bash
pytest --cov=engine_core --cov=adaptive_risk_engine \
       --cov=analytics_engine --cov=addon_risk_engine \
       --cov-fail-under=67
```

### Docker (production)

```bash
cp .env.example .env       # fill in TELEGRAM_BOT_TOKEN, SUPABASE_*, IBKR_*
docker compose up -d --build
```

### Verify Supabase schema after deploy

```bash
SUPABASE_URL=... SUPABASE_KEY=... python3 migrations/verify_migrations.py
```

The script reads `INFORMATION_SCHEMA` and reports any missing tables or
columns. Pair with `/system_health` in Telegram (check #14 verifies
`audit_log` is reachable in production).

## Hard constraints (non-negotiable)

- **No silent failures.** Every fallback path either alerts the user or logs explicitly.
- **No production network calls in tests.** `pytest-socket` enforces this — see [`docs/TESTING_GUIDELINES.md`](docs/TESTING_GUIDELINES.md).
- **Telegram admin gate** in `telegram_bot_secure_runner.py` is the production entrypoint. Never bypassed.
- **All risk math has tests** — R-multiple, NAV, exposure, heat score, trail buffer, etc.
- **No Supabase mutations from read-only flows.**

Full constraints in [`CLAUDE.md`](CLAUDE.md).

## Development workflow

1. Read [`docs/README.md`](docs/README.md) and [`CLAUDE.md`](CLAUDE.md) before touching code.
2. Open a PR — the [PR template](.github/PULL_REQUEST_TEMPLATE.md) checklist guards against the failure modes we've already encountered.
3. CI must be green before merge (branch protection enforced on `main`).
4. End of every sprint: fill in `docs/SPRINT_<N>_LESSONS.md` from the [template](docs/SPRINT_LESSONS_TEMPLATE.md).

## Documentation map

- [`AGENTS.md`](AGENTS.md) — operating rules for AI coding agents
- [`CLAUDE.md`](CLAUDE.md) — Claude Code specific context
- [`docs/README.md`](docs/README.md) — full doc index (start here)
- [`docs/SYSTEM_AUDIT_2026_05.md`](docs/SYSTEM_AUDIT_2026_05.md) — most recent system audit
- [`docs/COVERAGE_BASELINE.md`](docs/COVERAGE_BASELINE.md) — coverage targets through Sprint 9
- [`docs/SPRINT_6_LESSONS.md`](docs/SPRINT_6_LESSONS.md) — incident retrospective
- [`docs/SPRINT_7_LESSONS.md`](docs/SPRINT_7_LESSONS.md) — recovery sprint
- [`docs/SPRINT_8_LESSONS.md`](docs/SPRINT_8_LESSONS.md) — foundations hardening
- [`docs/SPRINT_9_PLAN.md`](docs/SPRINT_9_PLAN.md) — current sprint charter

## Recent sprints

| Sprint | Theme | Tests delta | Score |
|--------|-------|-------------|-------|
| 5 | Add-On schema, Supabase fixes, security | +29 | 8.9 |
| 6 | audit_logger, healthchecks real, P1 features | +18 | 7.8 (incident) |
| 7 | pytest-socket, audit healthcheck, process docs | +3 | 8.6 (recovery) |
| 8 | Foundations Hardening | +73 | **9.0** ⭐ |
| 9 | Morning Briefing + engine_core 75% + features (in progress) | — | — |

---

🤖 Built with assistance from [Claude Code](https://claude.ai/code).
