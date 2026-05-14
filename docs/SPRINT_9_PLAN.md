# Sprint 9 — Charter

**Theme:** "Return to features, hold the floor"
**Approved by:** Mark Minervini, Meeting 9
**Starts:** When Meeting 9 retrospective doc (this) is merged
**Score gate:** Sprint 8 closed at 9.0/10. Sprint 9 target: ≥ 9.0/10. **No incidents.**

---

## Mission

Three sprints of process work (6 recovery, 7 hardening structural, 8 closing debt) brought the score from 7.8 to 9.0. The team now has a stable floor. Sprint 9 returns to **feature work** without losing that floor.

If Sprint 9 ships 5/5 priorities clean, Meeting 10 declares the system **Superperformance-ready** — meaning we stop "building the system" and start "using the system to trade."

---

## 5 Priorities (Mark's call, Meeting 9)

### Priority 1 — 🌅 Morning Briefing view

**Owner:** Maya (Telegram UX) + Lior (User Journey)
**Files:** `telegram_portfolio.py` (new `handle_morning_briefing`), `telegram_formatters.py` (new `fmt_morning_briefing`), `telegram_menus.py` (button)
**Estimate:** L (2-3 days)
**Mark's ask from Meeting 2:** *"What I want to see at 9:30 AM, before market opens, in one screen, 30 seconds to read."*

Specification:
- Single screen, 8-12 lines max
- Top: market regime icon + 1-line summary
- Middle: ⚡ urgent positions (BROKEN, RUNNER needing trail, DEAD_MONEY exit), with action button per row
- Bottom: today's adaptive risk recommendation + drawdown status

Acceptance:
- [ ] `pytest` adds 8+ tests, all pass
- [ ] Mark approves the wireframe (handed to Maya from Meeting 2)
- [ ] Sarah verifies on iPhone 14 + Pixel 7 (no RTL bugs, no truncation)
- [ ] Coverage stays ≥ 67%

### Priority 2 — 🧪 Engine_core coverage 56% → 75%

**Owner:** Chris (QA) lead + Jordan (Backend) writing tests
**Files:** `tests/test_engine_core_*.py` (likely multiple new files)
**Estimate:** L (whole-sprint side project — Chris commits 2 hours/day)
**Mark's Meeting 6 target finally achieved.**

Strategy:
1. Run `pytest --cov=engine_core --cov-report=term-missing` — print top 5 uncovered functions
2. Each uncovered function gets 3-5 tests (happy path + 2 edge + 1 invalid)
3. Sprint 9 milestone: 70% by mid-sprint, 75% by end

Acceptance:
- [ ] `--cov-fail-under=72` (raised from 67) passes CI by mid-sprint
- [ ] `--cov-fail-under=75` passes CI by sprint end
- [ ] No new test takes > 5 seconds (slow tier banned for unit additions)

### Priority 3 — 🛡️ audit_logger 8/8 + drawdown P0 alert wiring

**Owner:** Jordan (Backend) + Compliance review
**Files:** `audit_logger.py` (already has constants), 4 new call sites, `risk_monitor.py` (drawdown alert)
**Estimate:** M (1 day)
**This is the Sprint 8 #7 deferral — finally closed.**

Wiring the 4 remaining actions:
- `manual_trade` → `supabase_repository.insert_trades`
- `deploy_trigger` → `telegram_devops` (deploy file write)
- `settings_change` → wherever `sentinel_config.json` is updated outside `update_risk_pct`
- `telegram_alert_send` → sampled (1%) in `send_telegram` wrapper to avoid log volume

Drawdown P0 alert:
- `risk_monitor.py` checks `result.get("override") == "drawdown_auto_cut"`
- When true, fires P0 alert that bypasses normal 24h adaptive cooldown
- Alert format includes drawdown_pct + pnl_30d_usd + recommended ladder

Acceptance:
- [ ] `audit_log` rows for all 8 action types verified in Supabase
- [ ] Drawdown alert fires within 1 cycle of trigger
- [ ] Existing 4 audit call sites untouched
- [ ] +10 tests, all pass

### Priority 4 — 📊 Heat score multiplicative refactor

**Owner:** Sarah (Quantitative) + Mark (final formula approval)
**Files:** `adaptive_risk_engine._window_heat_score`
**Estimate:** M (1-2 days, mostly math design)
**Sarah's Meeting 9 ask — current additive model gives false confidence.**

Current model:
```
score = wr*100 + payoff_bonus + pf_bonus + streak_penalty   (additive)
```
At WR=70%, payoff=0.5, PF=0.8: score ≈ 70 + 0 - 12 = 58 → trader looks "OK"
**But payoff < 1 means average loss > average win — this is a losing system.**

Proposed:
```
wr_factor      = wr             (0-1)
payoff_factor  = clamp(payoff / 2.0, 0.3, 2.0)
pf_factor      = clamp(pf / 1.5, 0.3, 2.0)
streak_factor  = max(0.5, 1 - 0.15 * max(loss_streak - 1, 0))

score = round(100 * wr_factor * payoff_factor * pf_factor * streak_factor)
```
At WR=70%, payoff=0.5, PF=0.8: 0.7 × 0.25 × 0.53 × 1.0 ≈ 9 → "down_fast" correctly fires.

Acceptance:
- [ ] Daria validates on 5+ historical examples from books
- [ ] New score correlates with old score in normal range (r > 0.7)
- [ ] Edge cases (small samples, all wins, all losses) handled
- [ ] +15 tests, all pass

### Priority 5 — 📉 BACKING_OFF state in compute_position_state

**Owner:** David (Risk Management)
**Files:** `engine_core.compute_position_state`, `engine_core.POSITION_STATE_BACKING_OFF` (new const)
**Estimate:** S (0.5 day)
**David's Meeting 9 ask — gap between WORKING and BROKEN.**

State definition:
- `open_r` was ≥ +1.0R within last N days but is now ≤ -0.3R
- Price broke MA10 from above
- NOT yet at stop (stop_loss < current_price)

This is the "trade going wrong but not yet stopped" state — gives the trader a *warning* before BROKEN fires.

Acceptance:
- [ ] Priority order in compute_position_state: BROKEN > BACKING_OFF > RUNNER > WORKING
- [ ] State machine partition holds (no two states active simultaneously)
- [ ] +6 tests covering transitions in and out of BACKING_OFF
- [ ] Alert format added to risk_monitor.py (warning level, not critical)

---

## Stretch items (only if 1-5 ship by mid-sprint)

| # | Item | Owner | Estimate |
|---|------|-------|----------|
| S1 | yfinance cache market-hours-aware (60s during market, 3600s after) | Alex | 30 min |
| S2 | docs/SECURITY_POLICIES.md (RLS, secret rotation, retention) | Eyal | 1 day |
| S3 | telegram_router.py refactor (extract handlers from telegram_bot.py) | Alex | 1 day |
| S4 | mypy strict on engine_core | Jordan | 1 day |
| S5 | mock_telegram_bot used in test_telegram_portfolio | Chris | 0.5 day |

---

## Out of scope (Sprint 10+)

- Backtesting engine framework (Daria)
- Staging environment + Supabase sandbox (Rachel)
- CD pipeline (Tomer — requires SSH to Orange Pi)
- Auto-rebase action for stale PRs (Tomer)
- 48h Settle Period empirical validation (needs 60+ days of production data first)

---

## Process rules (carried from Sprint 7-8)

1. **One PR at a time** — close one before opening the next. When >3 open, pause development.
2. **CI green on main** before merge (enforced by `required_status_checks`).
3. **PR template** checklist auto-populated (see `.github/PULL_REQUEST_TEMPLATE.md`).
4. **Manual smoke** after every merge to main (when the bot is deployable).
5. **Sprint lessons doc** written same-day as sprint end.

---

## Success criteria

Sprint 9 is **success** if and only if:
- ✅ 5/5 priorities delivered (or 4/5 with explicit Mark approval for the deferral)
- ✅ Test count ≥ 1380 (current 1321 + ~60 from new features)
- ✅ Coverage gate raised to **75%** by end-of-sprint
- ✅ Zero incidents (no CI red on main; no compliance silent gaps)
- ✅ Mark scores Meeting 10 at ≥ 9.0/10

If success → Meeting 10 declares **Superperformance-ready** and the team's focus shifts from "building" to "trading with."

---

## Mark's framing for Sprint 9

> *"Three sprints recovering from process gaps. Now we finish. Morning Briefing is what I asked for in Meeting 2 — overdue. engine_core coverage to 75% is what I asked for in Meeting 6 — overdue. audit_logger 8/8 is what Compliance has asked for since Meeting 7 — overdue.*
>
> *Sprint 9 is the closing chapter of 'building the system.' Sprint 10 opens 'trading with the system.' If the team holds Sprint 9 clean, the prize money offer from Meeting 6 stays on the table — and I'm one Sprint away from writing the check."*
