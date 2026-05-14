# Day 1 — Mid-day Standup

**Date:** 2026-05-14
**Branch:** `claude/review-system-audit-FBZ2h`
**Attendees:** Research, Hyperscaler, Marketing, Adaptive UX, Mark (methodology)
**Format:** Synthesis of 5 V0 deliverables. No production code touched today.

---

## TL;DR for the founder (5 bullets)

1. **The existing audit is partially stale.** Research re-verified all 7 audit claims against current code: 3 are already fixed (PF sentinel, risk_monitor silent failures, state-save timing), 3 are downgraded (still real but less severe), 1 is unchanged (heat score still additive — Sprint 9 P4 not yet shipped).
2. **The audit had one big blind spot.** `analytics_engine._aggregate_campaigns` does NOT filter ALGO/DATA_INCOMPLETE — meaning the weekly + monthly PDF reports today silently violate `AGENTS.md` invariant #8. This blocks any marketing claim about win-rate or expectancy until fixed.
3. **There are zero multi-tenant primitives.** A grep for `user_id|account_id|tenant` across the entire `.py` codebase returns no hits. 40 single-user assumptions inventoried (14 BLOCKER). A 4-phase additive migration is proposed; Phase A is the gating step for Marketing, Adaptive UX, and any future team.
4. **Methodology profiles is the central architectural question.** Hyperscaler wants 4 profiles. Mark says Minervini-strict stays the **only default** and the AGENTS.md Red Lines must remain hard-coded constants in every profile. Adaptive UX agrees and added the "stop discipline is a floor, not a slider" pattern.
5. **One founder decision blocks the landing page.** Marketing's Q1 question — *"can we name-drop Mark Minervini publicly?"* — gates the positioning hero line and several differentiation claims. Everything else can proceed in parallel.

---

## Cross-team conflicts surfaced today

Mark predicted 8 conflicts; the parallel work confirmed 5 of them and surfaced 2 new ones.

| # | Conflict | Teams | Resolution today |
|---|---|---|---|
| 1 | Methodology profiles vs Red Lines | Hyperscaler ↔ Mark | Profiles allowed; `mix_algo_into_wr=false` becomes a HARDCODED constant, never a profile field. `is_stat_countable()` stays parameter-free. |
| 2 | `follow_through_score` per-profile vs hard floor | Research ↔ Mark ↔ UX | FT minimum is methodology, not preference — stays hardcoded. Per-profile only adjusts cosmetic thresholds. |
| 3 | Admin gate single-chat_id vs multi-user | Hyperscaler ↔ Mark | Admin gate kept intact during Phase A. Phase C introduces per-user bot or webhook routing; `telegram_bot_secure_runner.py` stays the chokepoint. |
| 4 | Public metrics for marketing vs founder's private trades | Marketing ↔ Mark | Synthetic backtest data with explicit disclaimer; real metrics only with founder's signed consent. No anonymized real data on landing pages. |
| 5 | Hebrew-only as moat vs ceiling | Marketing ↔ UX | UX has language in Layer 1 of the glove model; Marketing flagged i18n as Q2-3 readiness gap. Founder must pick launch geography. |
| 6 | **NEW: 7-8% stop enforcement** | Mark ↔ UX ↔ Marketing | Mark wants per-trade soft-warning at 8%; UX wants user-tolerance scale; Marketing wants to claim "Minervini discipline enforcer." Resolution: implement soft-warning (informational), label aggressive profile as "outside Minervini doctrine" in UI. |
| 7 | **NEW: Stale audit doc as source of truth** | Research ↔ everyone | The audit was being cited as current state; 3 claims are fixed. Research takes ownership of the audit doc (Sprint 10 directive #4) and rewrites it. |

---

## Per-team summary

### 🔬 Research — `RESEARCH_FINDINGS_DAY1.md` (717 lines)

**Status of the 7 audit claims:**

| Claim | Audit said | Reality today | Severity |
|---|---|---|---|
| A | 3 definitions of `original_campaign_risk` | Now only 2 — `adaptive_risk_engine:159-175` still inlines its own | HIGH |
| B | `follow_through_score` always None | Now computed at `risk_monitor:741`, but `engine_core:2030,2043-2044` still treats `None` as pass during first 5 trading days | MEDIUM |
| C | PF sentinel 2.0 vs 99.0 | **FIXED** — both modules use `math.inf` (`adaptive_risk_engine:281`, `analytics_engine:54`) | NOT-A-BUG |
| D | Silent failures in risk_monitor | **FIXED** — all 3 sites now send alerts (`risk_monitor:594-602, 612-618, 633-640`) | NOT-A-BUG (but throttle the new alerts) |
| E | State file save only at end of loop | **FIXED** — mid-loop checkpoint at line 927 + SIGTERM/SIGINT handler at 1038-1059 | NOT-A-BUG |
| F | WR/Expectancy must exclude ALGO/DATA_INCOMPLETE | **VIOLATED** — `analytics_engine._aggregate_campaigns` does NOT filter. Reports leak. | **HIGH (BLIND SPOT)** |
| G | Heat score additive | Confirmed unchanged. Sprint 9 P4 candidate. | MEDIUM |

**3 new angles:**
- **N1** — `score_position` NaN-handling correct only because of `len(hist) < 60` gate (`engine_core:417`). Booleans like `close < NaN` return False — would silently inflate scores if the gate weakens.
- **N2** — `addon_risk_engine.compute_campaign_lot_state` math correct, but `open_r` vs `total_r` doc drift is dangerous (open_r decreases proportionally after partial sells).
- **N3 (HIGH)** — real race condition on `risk_monitor_state.json`. Non-atomic writes at `risk_monitor:106-107`, non-atomic RMW from another container at `bot_helpers:49-66`, unprotected reads at `dashboard:495` and `bot_health:121`. Lost updates → duplicate alerts / dropped checkpoints.

**Sprint 10 P0 list:** Fix F (analytics filter), N3 (atomic writes + `flock`), D follow-up (throttle the new error alerts to respect anti-spam).

---

### 🚀 Hyperscaler — `HYPERSCALER_DESIGN_V0.md` (561 lines)

**Investigation:** grep for `user_id|account_id|tenant` across all `.py` → zero hits. `audit_log` tracks `chat_id` only. Every Supabase query is unfiltered.

**40 single-user assumptions** inventoried: 14 BLOCKER, 18 HIGH, 6 MEDIUM, 2 LOW. Examples:
- BLOCKER: admin guard, no `user_id` in DB, shared JSON state files, single IBKR Flex token, hardcoded ALGO universe, shared Docker volume.
- HIGH: methodology constants in `engine_core:13-16,1685-1708` + `adaptive_risk_engine:20-33` + `risk_monitor:39-52`, fallback NAV $7,500 baked into 8 files, no dashboard auth.

**Target architecture:** shared Supabase + RLS, mandatory `user_id UUID`, Supabase Auth, Telegram `chat_id` + IBKR token as linked artifacts, 4 methodology profiles, NAV-derived size tiers (small/medium/large), per-user worker queue.

**4-phase migration (preserves Mark's prod):**
- **Phase A** (~10 dev-days) — additive `user_id` columns + `DEFAULT_USER_ID` env var. **Zero behaviour change.** This is the dependency for every other Day 2+ team.
- **Phase B** (~20 dev-days) — JSON state files → DB tables; methodology DI; dashboard auth.
- **Phase C** (~30 dev-days) — real second user; webhook bot; RLS on; per-user IBKR workers; onboarding wizard.
- **Phase D** — billing, BYO-bot, multi-broker.

**12 founder questions** block Phase B kickoff.

---

### 📣 Marketing — `MARKETING_PLAN_V0.md`

**Honest framing:** *"technically marketable, operationally not."*

- 5 personas: HE momentum trader (primary), EN Minervini follower (secondary), family office (year 2+), swing educator (year 2+), long-term investor (rejected).
- **Positioning:** "discipline enforcer for the Minervini-method trader." 6 anti-positioning statements (not AI hype, not buy-and-hold, not social, not advice).
- **7 differentiators** all cited to code (RISK_LADDER, RISK_SETTLE_HOURS=48, 10-state machine, S9/M21/L50 windows, etc.).
- **Readiness gaps** in 5 rails (product, trust, compliance, i18n, demo). Hyperscaler named owner of signup/billing blockers.
- **6-month roadmap:** Q1 foundation (aligned to Meeting 10 "Superperformance-ready"), Q2 first paid, Q3 scale. $5.4–6.9k total to land 50 paid users.
- **10 founder questions** — Q1 (Minervini name usage) blocks the entire landing-page hero.

---

### 🧠 Mark — `MARK_ALIGNMENT_REVIEW.md`

**Methodology codification:** all 9 Minervini pillars traced to code. Surprises:
- Weinstein Stage 1-4 **NOT implemented** in the repo — Trend Template 8/8 is the de-facto Stage-2 proxy.
- 7-8% per-trade stop **NOT enforced** — only the account-level -8% NAV drawdown auto-cut exists.
- Risk ladder in code (`[0.25, 0.40, 0.60, 0.85, 1.15, 1.50, 2.00]`) is tighter than the older 8-step ladder in `SPRINT_9_PLAN.md`. The plan doc is stale.

**Sprint 9 priority callouts:**
- P4 heat-score multiplicative refactor: approved with fix — **clamp floor must be 0.15, not 0.30**.
- P5 BACKING_OFF: proposed priority order is wrong — **PROFIT_PROTECTION must precede RUNNER**, not the other way around.

**Sprint 10 directives (8):** `mix_algo_into_wr=false` as hard constant; single-user smoke test for every Hyperscaler PR; 7-8% stop soft-warning; Research owns the audit doc; consolidate `original_campaign_risk` to one function; marketing copy review gate; drawdown bypasses settle; heat-score clamp floor 0.15.

---

### 🤝 Adaptive UX — `PERSONAL_ADAPTIVE_DESIGN.md` (715 lines)

**Today's adaptive surface:** heat-score → risk-ladder loop in `adaptive_risk_engine`, drawdown auto-cut, 48h settle, NAV/risk_pct config, admin gate.

**Hardcoded-for-one-trader spots:** ALGO universe (`engine_core:13`), cooldowns (`risk_monitor:40-44,48`), risk ladder (`adaptive_risk_engine:20`), report schedule (`report_scheduler:34-40`), distribution windows + trail thresholds, add-on defaults, Hebrew-only output, fixed 5-button menu. **No position-count cap exists anywhere.**

**4-layer model:**
- **L1 — Identity** (explicit, once): language, TZ, capital tier, methodology profile, risk tolerance, experience level.
- **L2 — Trading style** (explicit, narrows): time horizon, universe, sector tilt, position-count target.
- **L3 — Behavioural learning** (silent, observed): check-in patterns, alert-response latency, revenge-trading pattern, message-length preference.
- **L4 — Methodology coaching** (advisory): nudges when behaviour drifts from stated profile.

**Additive shim pattern:** every constant becomes `get_user_constant(user_id, name)` with founder's `small × balanced` profile preserving byte-identical current behaviour.

**10 concrete touchpoints** with file:line + backward-compat shim each. Onboarding capped at 7 questions. Rollout: 12-15 small additive PRs (PR-A data layer → PR-B `user_context` module → one touchpoint per PR).

---

## Sprint 10 candidate priority list (consolidated)

| # | Item | Owner | Sources | Severity |
|---|---|---|---|---|
| P0 | Fix analytics_engine ALGO/DATA_INCOMPLETE filter (Issue F) | Daria + Jordan | Research, Mark | HIGH — methodology + compliance |
| P0 | Atomic writes + `flock` for state files (Issue N3) | Jordan | Research | HIGH — silent data loss |
| P0 | Consolidate `original_campaign_risk` to single function (Issue A) | Sarah | Research, Mark | HIGH — cross-module consistency |
| P0 | Hyperscaler Phase A — additive `user_id` columns + `DEFAULT_USER_ID` env | Hyperscaler lead | Hyperscaler, Mark | HIGH — unblocks every Day 2 team |
| P1 | Heat-score multiplicative refactor with clamp floor 0.15 (Sprint 9 P4 carry-over) | Sarah + Mark | Sprint 9, Mark | MEDIUM |
| P1 | BACKING_OFF state — fix priority order (PROFIT_PROTECTION > RUNNER) | David | Sprint 9, Mark | MEDIUM |
| P1 | Fix `follow_through_score=None` gate during first 5 days (Issue B) | Jordan | Research, Mark | MEDIUM |
| P1 | Soft-warning at 7-8% per-trade stop | David + Mark | Mark | MEDIUM |
| P1 | Throttle new D-alert error notifications (anti-spam compliance) | Jordan | Research | MEDIUM |
| P2 | Research rewrites `SYSTEM_AUDIT_2026_05.md` to reflect fixes | Research lead | Mark directive #4 | MEDIUM |
| P2 | UX `user_context` module skeleton (shim layer only) | Adaptive UX | UX, Hyperscaler | MEDIUM |
| P2 | Marketing waits on founder Q1 (Minervini name) | Marketing | Marketing | BLOCKED on founder |

**Out of Sprint 10 (Sprint 11+):**
- Hyperscaler Phase B (JSON state → DB, methodology DI, dashboard auth)
- Marketing Q1 deliverables (landing, demo URL, analytics)
- UX behavioural learning (Layer 3)

---

## Blocking founder decisions (need answers before Sprint 10 kickoff)

1. **Mark Minervini name usage** — public branding, endorsement, or none? (blocks Marketing hero, Phase 3 positioning, several differentiators)
2. **Methodology breadth** — keep Minervini-strict as the only default, or offer the 4 profiles Hyperscaler proposed?
3. **Launch geography** — Israel-only, global, or both? (drives i18n investment + compliance scope)
4. **Pricing range** — micro retail $19/mo or pro $199/mo? Both? (drives feature gating)
5. **Public track record** — synthetic backtest only, or anonymized real data?

The 17 other founder questions across the team docs can wait until Sprint 11 planning.

---

## Process notes for the afternoon / night shift

- All 5 V0 docs committed and pushed to `claude/review-system-audit-FBZ2h`. No production code changed. CI green on `main`.
- **No team is unblocked enough to ship Sprint 10 code yet** — Mark's directives + the 5 blocking founder decisions must close first.
- Recommended next session: founder reviews the 5 blocking decisions; Research starts the audit-doc rewrite (does not require any decision); Hyperscaler drafts the Phase A migration script as a no-op shim.
- Afternoon work to pull in *without* code changes: V1 of Hyperscaler design with explicit schema for the `user_id` migration; V1 of UX design with the `user_context` interface spec.

---

## Appendix — file index

| Doc | Path | Lines |
|---|---|---|
| Research findings | `docs/teams/RESEARCH_FINDINGS_DAY1.md` | 717 |
| Hyperscaler design | `docs/teams/HYPERSCALER_DESIGN_V0.md` | 561 |
| Marketing plan | `docs/teams/MARKETING_PLAN_V0.md` | 385 |
| Mark alignment | `docs/teams/MARK_ALIGNMENT_REVIEW.md` | 338 |
| Adaptive UX | `docs/teams/PERSONAL_ADAPTIVE_DESIGN.md` | 715 |
| This standup | `docs/teams/DAY1_MIDDAY_STANDUP.md` | (this file) |
