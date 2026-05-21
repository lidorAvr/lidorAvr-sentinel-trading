# MEETING_ENGAGEMENT_OPS_FEASIBILITY — OPS Discipline (Wave 4)

> OPS artifact. 21/05/2026. Read-only. Inputs: `UX_SYNTHESIS.md`,
> `MARK_RESEARCH_RULINGS.md`, `report_scheduler.py`, `risk_monitor.py`,
> `docker-compose.yml`, `MEETING_UX_OPS_FINDINGS.md §F2`.

## Headline verdict

**Phase-1 is feasible as ONE coordinated full-stack deploy — not five
incremental ships.** The scheduler today has ZERO weekday clock-time
triggers — only Sat 08:30 + 1st-of-month 08:40
(`report_scheduler.py:54-60`). C5-S1 + C4-S1 + C1-S1 ALL fire Mon 16:08 IL,
forcing a new weekday-cron seat. Push budget (8/60s,
`telegram_bot_secure_runner.py:49-51`) has slack on normal days but
concentrates around the Monday open — same window as `risk_monitor`'s burst
capacity. §X5 demands a new fail-safe helper EVERY emitter consults first.

## Scheduler changes per concept

- **C1-S1 backfill** — daily check, NOT behavior-triggered. UX: "Backfill
  cron in `risk_monitor`-companion (NOT inside the 300s loop)"
  (`UX_SYNTHESIS.md:77`). Recommend daily 16:05 IL in
  `report_scheduler.py`, idempotent on `risk_journal_id`, max 1/week
  (`UX_SYNTHESIS.md:57`). Per-decision eval would tangle
  `risk_monitor.py:1384` and burn budget 99% of days.
- **C4-S1 Gate Receipt** — PUSH, Mon 16:08 IL (`UX_SYNTHESIS.md:190`). NOT
  on-demand (re-fires every `/portfolio` = AGENTS §3 violation), NOT
  per-clamp (accumulation IS the point). New `_WEEKLY_MON_HOUR=16,
  _MINUTE=8` alongside `_WEEKLY_WEEKDAY=5` (`report_scheduler.py:54-60`).
- **C5-S1 Monday opener** — Mon 16:08 IL = 13:08 UTC
  (`UX_SYNTHESIS.md:232`). **Bundle with C4+C1**: ONE Mon-16:08 hook
  emits C5 always → C4 (clamp≥3) → C1 (14d-match). One cron, three state
  keys.
- **C2-S1 sizing** — Mark: "voice-only change on existing path
  (`risk_monitor.py:497-540, 1168-1174`)" + dedup byte-identical
  (`RULINGS.md:131-144`). **No new schedule.** Test asserts the
  campaign-id cooldown at `:1168-1174` is unchanged.

## Push-rate budget + cooldown

Ceiling 8/60s → 90s cooldown (`telegram_bot_secure_runner.py:49-51`). The
21/05 msg-18799 trip was interactive burst, not push — but budget is
shared. Worst-case:

| Window | Existing | Phase-1 new | Risk |
|---|---|---|---|
| Mon 16:08 (cron alone) | 0 | 3 | safe |
| Mon 16:08 + `/portfolio` render (4 msgs) | 4 | +3 | 7/60 — close |
| `risk_monitor` burst (3-5) coincident w/ cron | 3-5 | +3 | 6-8/60 — collision class |

**New cooldown rule.** Monday-cron emitter sleeps 5s between messages
(spreads burst). §X5 suppression is the primary defense — silence-as-beat
doubles as rate-limit defense.

## §X5 Silence-As-Beat ops implementation

Per Mark: "absence IS the surface" (`RULINGS.md:184-197`). Three inputs:
(1) **missed-day ≥48h** — `audit_log` last INTERACTIVE event (NOT
`_last_cycle` heartbeats — those are Sentinel-side); (2) **-2R day** —
`audit_log` closes today, sum realized R; (3) **settle-period** —
`get_risk_settle_info()` (`adaptive_risk_engine.py:87-106`)
`hours_remaining > 0`.

**Decision lives** in new `engagement_suppression.py`:
`should_suppress_for_silence_or_2r_or_settle(state, now_ts) ->
tuple[bool, str]` (Mark named at `RULINGS.md:195`). Called FIRST by EVERY
emitter. NOT in `report_scheduler.py` (too coupled), NOT in
`risk_monitor.py` (300s loop overloaded).

**Fail-safe direction.** Per CLAUDE.md accuracy>confidence + §X5: any
exception MUST return `(True, "suppression_check_failed")`. A silent day
is on-brand; "we noticed" is the §X5 violation. Pin at
`RULINGS.md:191-193`.

## Deployment story (incremental vs coordinated)

**Coordinated — full-stack recreate.** Chain at `RULINGS.md:223-235` spans
three services: U1 (`risk-monitor`), U4 (`telegram-bot`), `gate_result` +
`ACTION_CALLBACK_FIRED` + `engagement_suppression.py` (ALL — shared
modules), C5/C4/C1 cron (`reporting-service`), C2 voice (`risk-monitor`).
Per `DEPLOYMENT_RUNBOOK.md:42-45` ("recreate ALL affected services") use
`docker compose up -d --force-recreate` whole-stack. **NO schema migration
Phase-1** (D10 = Phase-2); rollback stays code-only per
`SAFE_CHANGE_PROTOCOL`. Incremental ship would leave
`ACTION_CALLBACK_FIRED` on one service and missing on another → audit-row
crash class.

## Risks from existing OPS findings

- **F2 reconnect-storm** (`MEETING_UX_OPS_FINDINGS.md:19-25`). 11
  reconnects 18-21/05; `main.py:32` `LOOP_INTERVAL_SEC=900` vs
  `docker-compose.yml:27` stale=1980s = 2.2× margin. 13:12 MRVL
  `evaluate_position_engine` → 13:13 reconnect is precedent. Engagement
  multiplies push surfaces ~3× — each emitter is a new exception site.
  **Mitigation:** every emitter `try/except Exception: log+continue` (NOT
  re-raise) — one push fail must never stall the loop.
- **MRVL `missing_data`** — bare `except:` at `engine_core.py:88, 107,
  121, 134, 156, 430` + returns at `:426, :618, :787`. C2-S1 (MRVL) and
  Callback C1-S2 (bucket-match) depend on per-position reads. **Engagement
  raises this MEDIUM → HIGH**: founder sees "missing surface", not "errored
  compute". Mitigation: emitters check `ok=False` explicitly + emit new
  `ACTION_ENGAGEMENT_SUPPRESSED_DATA_GAP` audit row.
- **Secure-runner + admin gate.** Phase-1 surfaces are default-channel
  PUSHES to `TELEGRAM_CHAT_ID`. Admin gate
  (`telegram_bot_secure_runner.py:60-62`) gates INCOMING — compatible, no
  new protection needed. `truth_suffix` marker-list (`:92-101`) does NOT
  match engagement surfaces — correct per §X1 (engagement carries
  freshness INLINE).

## Sign-off

**APPROVE_WITH_CONDITIONS.** Binding: (1) new Mon-16:08-IL cron seat in
`report_scheduler.py` emits C5 → C4 → C1 sequentially, §X5-gated FIRST +
5s inter-message sleep; (2) `engagement_suppression.py` fail-safe to
`(True, …)` on exception, pinned; (3) every emitter
`try/except: log+continue` so one failure cannot trigger F2; (4) Phase-1
ships as ONE coordinated whole-stack recreate per
`DEPLOYMENT_RUNBOOK.md:42-45`; (5) test asserts `_sizing_leak_alert`
dedup key at `risk_monitor.py:1168-1174` is byte-identical after C2-S1
voice refactor (Mark binding).

**Top 3 risks:** (1) F2 reconnect-storm amplification — new emitters = new
heartbeat-stall sites (HIGH); (2) §X5 helper bug → passive-aggressive
message (HIGH); (3) MRVL-class `missing_data` × engagement → silently-
missing pushes without audit trail (MEDIUM-HIGH).

— OPS, Wave-4 engagement-phase feasibility, 21/05/2026. Read-only.
