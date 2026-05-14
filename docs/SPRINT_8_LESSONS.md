# Sprint 8 — Lessons Learned

**Dates:** 2026-05-14 (single intensive day)
**Score** (Mark's verdict at Meeting 9): **9.0 / 10** — recovery complete
**Test count:** 1248 → **1321** (+73 — biggest single-sprint addition)
**Theme:** "Foundations Hardening" — close every debt item from Sprints 1-7.

> Sprint 8 was deliberately not feature work. Ten items, all "should
> have already been done." If we don't close them now, they compound
> through Sprint 9 and the Morning Briefing / Add-On Phase 2b features
> will inherit a fragile floor.

---

## Priority items planned vs. delivered

| # | Day | Priority | Planned | Delivered | PR |
|---|-----|----------|---------|-----------|-----|
| 1 | 1 | Branch protection: required_status_checks | ✅ | ✅ | UI action mid-sprint |
| 2 | 1 | Merge 8 open PRs in order | ✅ | ✅ | #17-19, #22-31 |
| 3 | 1 | Dead code cleanup (`_MANUAL_TRIGGER_FILE`) | ✅ | ✅ | #25 |
| 4 | 2 | pytest markers on 1248 tests | ✅ | ✅ | #29 |
| 5 | 2 | README badges + project orientation | ✅ | ✅ | #28 |
| 6 | 2 | ATR trail buffer (Meeting 5 spec) | ✅ | ✅ | #26 |
| 7 | 3 | audit_logger 8/8 (4 more actions) | ✅ | ❌ deferred to Sprint 9 | — |
| 8 | 3 | management_notes append (not replace) | ✅ | ✅ | #30 |
| 9 | 4 | drawdown auto-cut | ✅ | ✅ | #31 |
| 10 | 4 | Mobile UX: emoji squares (RTL) | ✅ | ✅ | #27 |

**9/10 delivered.** #7 (audit_logger 8/8) was the only deferral — by design (low-urgency additive work; current 4 actions cover the high-signal events).

## Incidents during this sprint

### Incident: WIP overload mid-sprint

- **Detected:** Meeting 8 dry-run audit (Mark, ~3 hours into the sprint)
- **Cause:** 9 features shipped to PRs in 3 hours; merges took longer. At one point **12 PRs were open simultaneously** (Sprint 6+7+8 carryover combined).
- **Effect:** PRs #18 and #19 (Sprint 6 carryover) had stale `base.sha` and inherited the FT bug fix only after `update_pull_request_branch` was triggered.
- **Fix in flight:** Used `mcp__github__update_pull_request_branch` for #18 and #19 — they picked up the FT fix from main and CI went green.
- **Lesson:** "One PR at a time" (Meeting 7 policy) is the floor, not the goal. The team should *pause development* after 3-4 PRs are open and wait for merges.

### Non-incident: zero CI failures on main

For the entire sprint, `main` stayed green. PR #28 was the first PR after Sprint 7's CI fix; all 9 subsequent PRs passed CI on the first try (except #29 which had a docstring conflict — resolved manually in 5 minutes).

### Process win: branch protection mid-sprint

Eyal/Security caught in Meeting 8 audit that the ruleset created at end of Meeting 7 was missing `required_status_checks`. The user added it via UI mid-sprint. **From that moment forward, no PR can merge with red CI.**

## What worked

- **Foundations theme.** No new features — just closing debt. Mental space stayed clear.
- **ATR trail buffer (#26).** Sarah/Daria's Meeting 5 spec — 3 sprints overdue — shipped with 19 tests covering NVDA, MNST, MARA, and edge cases. The math has a clean public API (`atr_pct` optional, defaults to legacy 2%).
- **management_notes append (#30).** Compliance gap of "every addon overwrites prior note" closed. Each entry now timestamp-prefixed. Defense-in-depth with audit_logger.
- **drawdown auto-cut (#31).** Override logic: heat score can't recommend a position-size increase when 30d P&L ≤ -8%. Hard floor.
- **pytest markers (#29).** Auto-tagging hook in `conftest.py` — 42 test files unchanged, but `pytest -m unit` now returns 909 tests instead of 0.
- **Mobile emoji bars (#27).** 2-line fix for a 6-month-old visual bug. RTL emoji squares 🟢⚪ replace block chars █░.
- **Test count +73 in one sprint.** Coverage stayed above 67% gate at 68.88%.
- **All 9 PRs CI-green on first try** (after the one #29 docstring conflict).

## What didn't work

- **WIP overload before the user could keep up.** 9 features ready, 1 reviewer. The merge train queued for hours.
- **Sprint 6 carryover PRs (#18, #19) needed manual `update-branch`** when main moved. Should be automated — Sprint 9 backlog item.
- **engine_core coverage dropped 1pp** (57% → 56%) because new code (ATR helper, drawdown logic) added uncovered branches before the dedicated coverage sweep. Sprint 9 fix.
- **README links to `docs/COVERAGE_BASELINE.md` (PR #19) and `verify_migrations.py` (PR #23)** were intentionally removed from README to avoid dead links during the sprint. Need to re-add now that both PRs are merged.

## New backlog items surfaced

| # | Item | Priority | Sprint target |
|---|------|----------|----------------|
| 1 | audit_logger 4 more actions (manual_trade, deploy, settings, telegram_alert) | 1 | 9 |
| 2 | drawdown auto-cut → P0 alert routing in risk_monitor.py | 1 | 9 |
| 3 | engine_core coverage 56% → 75% (Mark's Meeting 6 target) | 1 | 9 |
| 4 | Morning Briefing view (Meeting 2 ask, 4 sprints overdue) | 1 | 9 |
| 5 | Heat score multiplicative refactor (Sarah, Meeting 9) | 2 | 9 |
| 6 | BACKING_OFF state in compute_position_state (David) | 2 | 9 |
| 7 | `telegram_router.py` extract from telegram_bot.py (Alex) | 2 | 9 |
| 8 | mypy strict on engine_core (Jordan) | 2 | 9 |
| 9 | yfinance cache market-hours-aware (Alex, Meeting 5 #26) | 3 | 9 or later |
| 10 | docs/SECURITY_POLICIES.md (RLS, secret rotation, audit retention) | 3 | 9 |
| 11 | mock_telegram_bot fixture used more broadly | 3 | 9 |
| 12 | test_e2e_risk_monitor::test_full_main_cycle | 3 | 9 |
| 13 | Staging environment / Supabase sandbox (Rachel Manual QA) | 3 | 10+ |
| 14 | Backtesting engine framework (Daria) | 3 | 10+ |
| 15 | Auto-rebase action for stale PRs | 4 | 10+ |
| 16 | CD pipeline once SSH available (Tomer) | 4 | 10+ |
| 17 | README links restored (COVERAGE_BASELINE, verify_migrations) | 4 | 9 (chore) |

## Test coverage snapshot

| Module | Sprint 7 | Sprint 8 | Trend |
|--------|----------|----------|-------|
| `engine_core.py` | 57% | 56% | ↓ 1pp (new ATR + helper paths uncovered) |
| `adaptive_risk_engine.py` | 87% | **88%** | ↑ 1pp (drawdown helpers tested thoroughly) |
| `analytics_engine.py` | 99% | 99% | = |
| `addon_risk_engine.py` | 86% | 86% | = |
| **Total** | 67.99% | **68.88%** | ↑ 0.89pp (gain from adaptive engine outpaces engine_core drift) |

CI gate held at 67% throughout. Sprint 9 target: engine_core → 75%, total ≥ 72%.

## Process changes adopted

1. **Mandatory "stop and merge" trigger:** when >3 PRs are open AND CI is green on all, the team pauses new development until 2+ merge.
2. **PR rebase automation:** `mcp__github__update_pull_request_branch` for stale Sprint carryover PRs (used for #18, #19 this sprint).
3. **Sprint lessons doc written same-day** as the sprint ends. Sprint 6 lessons were written 1 sprint late; Sprint 7 + 8 are same-day.
4. **CI parity in local environment:** `pytest --cov ... --cov-fail-under=67` is now the standard pre-push command. If it doesn't pass locally, don't push.

## Mark's verdict on the lessons

> *"Sprint 8 was the recovery I needed to see. Nine of ten items shipped, zero incidents, CI green throughout, and we caught the branch-protection gap before it bit us. The drawdown auto-cut alone is worth the whole sprint — that's the bleeding-stop rule from Champion ch.13, finally enforced by code rather than by my willpower.*
>
> *Sprint 9 returns to features. Morning Briefing is the headline ask. engine_core coverage to 75% is the structural ask. audit_logger 8/8 is the closure. Five items in Sprint 9. If we ship five clean, Meeting 10 declares Superperformance-ready and we move from 'building the system' to 'using the system to trade.' That's the prize."*
