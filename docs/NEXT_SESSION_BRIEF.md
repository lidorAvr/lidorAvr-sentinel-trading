# 🚀 Next Session Brief — Sentinel Trading
**Updated: 2026-05-14 end-of-session | Read me FIRST**

This document tells the next AI agent everything needed to resume work in <2 minutes.

---

## ⚡ One-paragraph summary

Sentinel is a personal trading intelligence system enforcing Mark Minervini's
SEPA methodology with adaptive risk sizing, task-driven position management,
and EP/VCP setup differentiation. **Production-deployed on Orange Pi 3 LTS**,
6 Docker services, 1,622 tests passing (71.4% coverage on core modules),
0 regressions across 15 unmerged commits on `claude/integration-pi-and-main-2026-05-14`.
Sprint 11 closed 12 of 17 findings from the methodology research audit.

---

## 📍 Where to start

| Want to... | Read this |
|---|---|
| Understand the architecture | `docs/MODULE_MAP.md` |
| Understand the methodology | `docs/SPRINT_11_RESEARCH_AUDIT_2026_05_14.md` |
| Understand the data model | `docs/DATA_CONTRACTS.md` |
| Understand operational constraints | `CLAUDE.md` + `AGENTS.md` |
| Deploy or rollback | `docs/DEPLOY_GUIDE_PI_2026_05_14.md` |
| Read sprint history | `docs/SPRINT_10_11_LESSONS.md` |
| See what's pending | This doc — section "Open work items" below |

---

## 🌳 Current branch state

**Branch**: `claude/integration-pi-and-main-2026-05-14`
**15 commits ahead of `main`** (see `git log origin/main..HEAD`):

| # | SHA | Sprint | Description |
|---|---|---|---|
| 1 | `8bab814` | — | Pi integration docs + state mitigation script |
| 2 | `73af2da` | — | IBKR 1001 fixes (cooldown + trigger handoff + period log) |
| 3 | `aff1118` | — | Cleanup orphan scripts + risk-monitor log tee (#33) |
| 4 | `ed4d568` | — | IBKR config visibility (bot_health #11,#15 + reference doc) |
| 5 | `ab7d676` | — | Display/UX batch: 6 fixes from 2026-05-14 feedback |
| 6 | `e61f8f5` | — | B1: campaign target locked at entry (migration 003) |
| 7 | `76f7932` | — | B3: closed-campaigns ladder gate |
| 8 | `717105f` | — | C1: slash shortcuts + flat main menu |
| 9 | `67d0507` | Sprint 10 | **Task Review feature** (📋 משימות — 5 task types) |
| 10 | `2fcbf6d` | Sprint 11 P1 | Morning Briefing + Setup Performance + Research Audit |
| 11 | `695abc8` | Sprint 11 P2 | SetupProfile + 2 BLOCKERs + CI default-arg fix |
| 12 | `dea7adf` | Sprint 11 P3 | 5 HIGH items + 2 MEDIUM from audit (regime, FTD, per-bucket, age-gate, trail reconcile, dead-money reconcile, 25d distribution) |
| 13 | `72f920c` | Sprint 11 P4 | Trend Template 5→8 criteria migration |

The branch is **pushed and CI-green** as of P2 commit. Migrations 001/002/003
all applied to user's Supabase.

---

## 🏗️ System map (high-level)

### Production modules (root level)
**Core math**:
- `engine_core.py` — R-multiples, heat, regime, Trend Template (8 criteria), FTD, MAs, distribution-day cluster
- `adaptive_risk_engine.py` — RISK_LADDER + 4 gates (closed-campaigns, Cold-regime, per-bucket heat, drawdown auto-cut)
- `analytics_engine.py` — period analytics, win rate, expectancy, profit factor
- `addon_risk_engine.py` — 5-gate add-on validator

**Sprint 10/11 modules (new)**:
- `task_engine.py` — task computation (5 stops-only rules: BE@profit_protect_r, trail@trigger, dead-money setup-aware, stop-breach, loose-stop)
- `task_state.py` — task ack/snooze persistence (JSON, atomic writes)
- `telegram_tasks.py` — UI handlers for the 5-screen task flow
- `setup_profile.py` — per-setup methodology parameters (VCP / EP / SWING / ALGO)
- `setup_performance.py` — per-setup-type closed-campaign breakdown

**Phase 4 Telegram split**:
- `telegram_bot.py` (458 lines, was 2000+) — top-level routing
- `telegram_bot_secure_runner.py` — admin gate + rate limit
- `telegram_callbacks.py` — inline button dispatch
- `telegram_menus.py` — keyboard builders
- `telegram_portfolio.py` — portfolio room + market regime
- `telegram_backlog.py` — journal completion flow
- `telegram_devops.py` — developer menu, IBKR manual sync trigger
- `telegram_formatters.py` — pure formatters (8-criterion Trend Template etc.)
- `bot_core.py`, `bot_helpers.py`, `bot_health.py` — shared singletons + utilities

**Pipeline**:
- `main.py` — IBKR auto-sync window 07:00–11:00 IL + manual-trigger handler
- `ibkr_sync_runner.py` — Flex Query SendRequest/GetStatement + cooldown
- `ibkr_trade_importer.py` — XML → Supabase with snapshot fields
- `supabase_repository.py` — DI'd DB access layer
- `audit_logger.py` — append-only audit trail (fail-open)

**Services**:
- `risk_monitor.py` — 300s loop, anti-spam, Morning Briefing + Daily Digest, state machine
- `report_scheduler.py` — weekly/monthly PDF
- `dashboard.py` — Streamlit

### Docker services
```
sentinel-bot      → python3 main.py
telegram-bot      → python3 telegram_bot_secure_runner.py
dashboard         → streamlit run dashboard.py
risk-monitor      → python risk_monitor.py
reporting-service → python report_scheduler.py
autoheal          → restart unhealthy containers
```

---

## 🧪 Test discipline

| Metric | Value |
|---|---|
| Total tests | 1,622 |
| Passing | 100% |
| Coverage (core modules) | 71.4% (gate: 67%) |
| Test time | ~84 sec |
| Regressions across 15 commits | 0 |

**Critical conventions**:
- `pytest-socket` blocks network in tests — no flaky CI
- Auto-marker tagging via `tests/conftest.py` (unit / integration / slow)
- Mock telebot/supabase/dotenv at `sys.modules` level — DO NOT stub `telegram_formatters`/`engine_core`/`adaptive_risk_engine` (real modules; stubbing leaks via global `sys.modules`)
- State files atomic-written (tmp + os.replace)

---

## 🔬 Methodology coverage (audit-grade)

| Principle | Status | Where |
|---|---|---|
| Trend Template (8 criteria) | ✅ enforced | `engine_core.compute_trend_template_full` |
| Trend Template in Telegram | ✅ migrated | `tf.fmt_minervini_trend_template` |
| RISK_LADDER (0.25–2.00%) | ✅ | `adaptive_risk_engine:20` |
| Closed-campaigns ladder gate | ✅ | requires ≥5 closed since last change |
| Market regime gate | ✅ | Cold → force hold |
| Per-bucket heat gate | ✅ | weakest of {EP, VCP} < 60 → blocks UP |
| Drawdown auto-cut | ✅ | -8% NAV → 0.40% override |
| EP profile (10d/1.5R dead-money, 1.5R BE, 3R runner) | ✅ | `setup_profile.EP` |
| VCP profile (21d/0.3R dead-money, 2.0R BE, 5R runner) | ✅ | `setup_profile.VCP` |
| Initial-stop 5–8% validator | ✅ | `setup_profile.validate_initial_stop` + `task_engine._task_loose_stop` |
| Power/Weak age gate | ✅ | days_held < 10 → no Power; < 15 → no Weak |
| Dead-money setup-aware | ✅ | `task_engine._task_dead_money` + `map_time_efficiency` |
| BE@2R → trail@3R | ✅ | task_engine (intermediate R band) |
| MA21/MA50 trail in RUNNER zone | ✅ | `engine_core.compute_suggested_trail_stop` (R≥5) |
| Distribution 25-day cluster | ✅ | `dist_25d` + `distribution_cluster` in features |
| Follow-Through Day (market) | ✅ | `engine_core.compute_market_ftd` |
| Audit log (every confirm) | ✅ | `audit_logger.log_action` |
| Mgmt-notes APPEND not REPLACE | ✅ | `supabase_repository.update_management_notes` |
| Heat-bar emoji squares | ✅ | RTL-safe iOS Telegram |
| ATR-based trail buffer | ✅ | `engine_core.compute_suggested_trail_stop` |
| Sizing Leak alert | ✅ | `risk_monitor._sizing_leak_alert` |

---

## 🛣️ Open work items (Sprint 12 candidates)

Ranked by research audit severity:

### 🟠 HIGH (still pending)
1. **VCP entry detector** — programmatic pivot / contraction quality / breakout volume at entry time. Audit ref: HIGH 4.
2. **EP catalyst metadata** — add `catalyst_date`, `catalyst_type`, `gap_pct` columns + importer support. Required for EP entry-quality grading.
3. **SetupProfile fully threaded through engine_core** — `evaluate_position_engine` and `compute_position_state` still use fixed `_R_RUNNER=5.0` / `_R_PROFIT_PROTECT=2.0`. Audit ref: BLOCKER #1.
4. **FTD → Morning Briefing** — wire `compute_market_ftd` output into the daily briefing.
5. **Watchlist scanner** — daily scan for VCP breakouts on user-defined list.

### 🟡 MEDIUM (still pending)
6. Distribution 25-day cluster used by `evaluate_hard_rules` (currently only surfaced, not gating)
7. Structured intent enum instead of `management_state` text matching
8. ALGO add-on gating by Power-state requirement (currently no state check in `addon_risk_engine`)
9. Mistake-classification structured codes (currently regex/substring on management_notes)

### 🟢 LOW
10. Document magic numbers in `engine_core` (RUNNER_FOLLOW_THROUGH_MIN, etc.)
11. Disambiguate Hebrew labels that share emoji (e.g., two yellow 🟡 labels)

### User-side action (no code)
12. **Periodic check on `/bot_health`** in Telegram — verifies Query ID + Flex Period stay correct

---

## 🚨 Hard constraints (DO NOT VIOLATE)

From `CLAUDE.md` + `AGENTS.md`:
1. ❌ Do NOT remove Telegram admin protection (`TELEGRAM_ADMIN_ID` check)
2. ❌ Do NOT bypass `telegram_bot_secure_runner.py` in production
3. ❌ Do NOT silently present fallback data as exact truth
4. ❌ Do NOT change R / NAV / exposure / campaign math without tests
5. ❌ Do NOT mutate Supabase from read-only flows
6. ❌ Do NOT rewrite `telegram_bot.py` wholesale (already extracted to 9 modules)
7. ❌ Do NOT mix ALGO campaigns into Win Rate or Expectancy
8. ❌ Do NOT add recurring Telegram alerts without per-position dedup flag
9. ❌ Do NOT commit secrets
10. ❌ Do NOT stub `telegram_formatters` / `engine_core` / `adaptive_risk_engine` in `sys.modules` — leaks globally

---

## 🔧 Operational commands

### Run tests locally
```bash
pip install -r requirements-dev.txt
pytest -q                                # 1622 tests
pytest --cov=engine_core --cov=adaptive_risk_engine \
       --cov=analytics_engine --cov=addon_risk_engine \
       --cov-fail-under=67               # CI replica (71.4%)
```

### Deploy to Pi
```bash
ssh orangepi@orangepi3-lts
cd ~/sentinel_trading
git fetch origin
git pull origin claude/integration-pi-and-main-2026-05-14
docker compose down && docker compose up -d --build
```

### Verify production
```bash
docker ps                                                # all healthy
docker exec sentinel-bot python3 /app/migrations/verify_migrations.py
# In Telegram: /p, /t, /s, 🏥 בריאות מערכת
```

### Rollback
```bash
git checkout 6c8288c                                     # Pi-backup tip
docker compose up -d --build
```

---

## 📂 Documentation map (post-update)

**Mandatory reading order (unchanged)**:
1. `AGENTS.md` — operating rules
2. `docs/AI_AGENT_CONTEXT.md` — context for AI agents
3. `docs/MODULE_MAP.md` — module purposes
4. `docs/DATA_CONTRACTS.md` — schema (now includes migration 003)
5. `docs/SAFE_CHANGE_PROTOCOL.md` — change protocol
6. `docs/TESTING_AND_DEPLOYMENT.md` — test count + deploy steps

**Sprint history**:
- `docs/SPRINT_6_LESSONS.md` — incident retrospective
- `docs/SPRINT_7_LESSONS.md` — recovery
- `docs/SPRINT_8_LESSONS.md` — foundations hardening
- `docs/SPRINT_9_PLAN.md` — was planned, partially superseded by 10/11
- `docs/SPRINT_10_11_LESSONS.md` — Task Review + methodology gap closure (NEW)

**Recent investigations**:
- `docs/IBKR_1001_INVESTIGATION_2026_05_14.md` — broker integration deep-dive
- `docs/IBKR_CONFIG_REFERENCE.md` — broker config spec
- `docs/SPRINT_11_RESEARCH_AUDIT_2026_05_14.md` — methodology gap analysis (3 BLOCKERs, 6 HIGH, 8 MEDIUM, 3 LOW)
- `docs/DEPLOY_GUIDE_PI_2026_05_14.md` — operator deploy spec
- `docs/BEHAVIOR_DELTA_PI_2026_05_14.md` — 16 user-visible changes
- `docs/MEETING_TRANSCRIPT_2026_05_14.md` — team meeting record

---

## 💬 Last thing — for the new agent

If you're picking this up cold:
1. Run `pytest -q` first to confirm 1,622 passing
2. Read `docs/SPRINT_11_RESEARCH_AUDIT_2026_05_14.md` (2200 words) — this gives you the methodology context
3. Pick ONE item from "Open work items" above — don't try to do many at once
4. Each item is sized to a single focused commit. Add tests. Run pytest. Commit with detailed message. Push.
5. If the user asks for "team meeting" / "Mark adversarial review" — those are productized patterns. Use Agent + `general-purpose` subagent_type with the relevant prompt.

The team is: **Senior (lead) + Mark (methodology) + Sarah Chen & Daria (research/quant) + IBKR Implementer + UX Designer + implicit QA discipline**. All personae have appeared in this session's transcripts.

— Last session signed off at 2026-05-14 ~17:00 IL, after Sprint 11 P4.
