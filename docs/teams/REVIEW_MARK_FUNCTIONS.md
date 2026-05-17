# Review — Every Function the System Now Does (Mark)

**Author:** Mark (methodology owner & team lead) · **Branch:** `claude/review-system-audit-FBZ2h` · **Date:** 2026-05-15

Founder-readable, function-by-function, verified against code (file:line). The
system is a single-user Minervini long-momentum Telegram bot on an Orange Pi.
Every user surface is admin-only behind `telegram_bot_secure_runner.py`
(8 msgs/60s, unchanged — DEC-20260515-009).

---

## 1. Open Tasks engine — `📋 משימות פתוחות` / `/tasks`

The "what do I do now" list. It is a **read-only view + lifecycle over the
engine's existing 10-state machine** — it invents zero new R/NAV/campaign math
(`open_tasks.py:417` is a pure projection; `engine_core.compute_position_state`
:1963 is the only authority).

**The 10 states** (`engine_core.py:1660-1669`, classified in priority order at
`:2007-2074`): ALGO_OBSERVED → DATA_INCOMPLETE → BROKEN (`_price_through_stop`
or `violation_score≥6`) → RUNNER (`open_r≥5R` or realized≥risk) →
PROFIT_PROTECTION (`≥2R`) → WORKING → YELLOW_FLAG (`violation≥2`) → DEAD_MONEY
(stale 8d+, no new high) → PROVING → NEW.

**Task ruleset T1–T8** (`open_tasks._RULESET:206-281`, transcribed verbatim
from the methodology spec §6; a CI drift test keeps the two in lockstep so I
stay the owner): BROKEN→**EXECUTE_EXIT P0** (T1 price-through-stop / T2
violation, collapsed — engine `reason` carries the "why"); RUNNER→
**PROTECT_RUNNER_PROFIT P1**; PROFIT_PROTECTION→**TIGHTEN_STOP_PROFIT P2**;
YELLOW_FLAG→**REVIEW_YELLOW_FLAG P2**; DEAD_MONEY→**TRIM_OR_EXIT P3**;
ALGO_OBSERVED→**ALGO_OBSERVE_ONLY P3 info-only**; DATA_INCOMPLETE→
**COMPLETE_RISK_DATA, urgency=null, never counted**. NEW/PROVING/WORKING
deliberately map to no task. Urgency tiers **P0–P3 reuse the existing
`ALERT_PRIORITY`** (`risk_monitor.py:72-95`) — no second severity scale; the
display bands (`telegram_tasks.py:47`) are colour only.

**RUNNER no-op suppression (ε):** T3 is *not* emitted when the current stop is
already at/above the engine's own suggested trail stop within ε, where
`ε = _TRAIL_MA_BUFFER_PCT × suggested_stop` and `_TRAIL_MA_BUFFER_PCT` is read
**live** from `engine_core.py:1887` (0.02), never hard-copied
(`open_tasks._runner_task_suppressed:371-414`). This kills the MRVL-type $0.41
(0.26%) noise tighten. A *material* tighten still surfaces; absent/invalid
engine output → not suppressed (never hide on missing data).

**Lifecycle (`open_tasks.py:835-944`):** done/skip/note write **only** the
`open_tasks` table (never `trades`); each writes a fail-open audit row.
**P0-skip is mandatory-reason**: skipping a BROKEN exit forces a typed reason
(`telegram_tasks.handle_task_skip:874-891`), is audited as
`skipped_critical_exit`, and the task is **never** silently dropped — a BROKEN
price-bounce makes it `stale`/visible, not auto-closed (spec §3/K5).

**Consolidated ALGO panel** (`telegram_tasks.handle_algo_panel:747`): one
non-tappable read-out (not per-row). It shows only what the engine already
*observes* — state label, `risk_basis`, an external stop **only if ALGO
exposes one** (else "לא ידוע", never $0.00, never a Sentinel-computed stop).
Mandatory first-line disclaimer "בקרה בלבד… לא הוראת פעולה". It is an
**observation, not a recommendation** because `evaluate_position_engine`
(`engine_core.py:457-462`) deliberately refuses to compute a discretionary
action for ALGO — that refusal *is* DEC-20260511-001 in code. **T7**
portfolio drawdown-ack is a separate `__PORTFOLIO__`-keyed ack-only task
(`open_tasks.derive_portfolio_tasks:529`), pull-only, never counted.

## 2. Stop promotion — `🎯 קידום סטופ`

Tap-only batch: one button per discretionary position
(`telegram_stop_promote.py:89`), ALGO excluded entirely. Write path is
byte-identical to the legacy flow. **Ratchet-up guard** (`guard_stop_write:342`):
a long's stop may only rise; a *loosen* (`new < current`) is intercepted with a
**defaulted-NO** confirm and, only on explicit YES, a `stop_loosen_override`
audit row written **first**, then the write (`finalize_pending_loosen:387`).
First-time/unknown stops and all tightens proceed with zero friction.

## 3. Alert engine — `risk_monitor.py`

**Pushes:** status escalation (`STATUS_RANK` rise, `:195` — never throttled),
→BROKEN entry, **critical-exit price<stop (P0, never suppressed)**, ALGO
deep-loss/streak/deviation (observer-framed only), giveback cross-zone,
checkpoints. **Pull-only now (post-Sprint-14):** a healthy/held position whose
alert-key is unchanged — it belongs in Open Tasks, not a push
(`should_alert:176-188`). **Must-fire P0:** price<stop, status worsening,
→BROKEN, ALGO deep-loss, system deviation (Mark S14 §4). **ALGO push gate:**
`do_alert and not _algo_observed` before the generic push
(`risk_monitor.py:700`) — ALGO never pushes a management action (#8 /
DEC-20260511-001). **Persistence fix:** the spam (HOOD Weak→Broken×N, PWR 7×)
was *not* bad gate logic — `risk_monitor_state.json` was git-tracked on the
bind mount, so every `git pull` reverted it → `prev=None` → re-push. Fixed by
moving `STATE_FILE` to the persistent `sentinel_state` volume
(`state_io.RM_STATE_FILE=/app/state/...`) **and** gitignoring + `git rm
--cached` the file (verified: not in `git ls-files`). It now survives
`git pull` *and* `--force-recreate`, so the spam structurally cannot recur.

## 4. Other surfaces

- **`/clean` (`🧹 ארכיון עסקאות`)** — `telegram_clean_gate.py`: read-only
  dry-run preview → defaulted-NO confirm → audit row → byte-identical
  UPDATE-only sweep. 30-day window absolute; **open campaigns excluded**
  (re-derived independently at write time); never deletes, never fabricates.
- **Price-fallback labelling** — when `get_live_price()` returns `None` and
  entry-price is substituted, the surface shows the honest
  "מחיר לא חי" label (`telegram_stop_promote.py:73,119`,
  `telegram_tasks.py:223`); no label on the live path; never a fabricated
  number.
- **`🧾 הפעולות שלי` audit review** — `telegram_audit_review.py`: SELECT-only
  over `audit_log`, most-recent-first, friendly Hebrew. Surfaces only the
  user's own decisions (risk-%, add-on, manual trade, stop-loosen override,
  task done/skip incl. `skipped_critical_exit`); omits dev-pin / deploy /
  alert-send. **No performance numbers** computed — actions only.
- **`/health`** — `bot_health.py`: 14 checks incl. the **missing-stops
  notice** (count + symbols, non-numeric, "אינו משימה, אינו נספר", split into
  open→journal-backlog vs closed→`/clean`).
- **Journal backlog** — `telegram_backlog.py:94-103`: an open position with no
  stop prompts the founder for the *real* initial stop; only the typed value
  (or `-1` skip sentinel) is written — never fabricated; excluded from stats
  until completed.

## 5. Methodology red lines (non-negotiable — what the system refuses)

AGENTS.md invariants #1–#8 + DEC rulings are hard, not profile fields
(DEC-20260515-002). The system will refuse to: present fallback/stale/cached
data as exact truth; change R/NAV/exposure/campaign math without tests; loosen
a long's stop without explicit defaulted-NO confirm + audit; mix ALGO or
DATA_INCOMPLETE into Win Rate / Expectancy / PF; add a recurring alert without
persisted per-position dedup; mutate Supabase from a read-only flow; bypass
the admin/secure-runner boundary.

## 6. What the system deliberately does NOT do

- Never instructs or computes an ALGO stop/exit/trim — observation only.
- Never fabricates, infers, or defaults a stop to "fix" missing data.
- Never counts ALGO / DATA_INCOMPLETE / `__PORTFOLIO__` in any statistic.
- Never auto-loosens a stop; never silently auto-closes or silently skips a
  P0 exit.
- Never reports a fabricated deploy success — `deploy.sh` self-checks
  Telegram egress over IPv4, retries once, then prints the manual recovery
  and exits non-zero (it never silently leaves a dead bot, never auto-`down`s
  the stack; `deploy-watcher` is intentionally not installed —
  DEC-20260515-010).
- Open Tasks never opens a second push channel — it is pull-only.

## 7. Honest status caveat

All Sprint 11–14 work is **deployed and full-suite-green (1638 passed)** but
the **live founder-UI smoke-test for Sprints 11/12/13 is still outstanding**
(carried in each team meeting). Sprint-14's alert-spam fix needs ≥3h of
founder Telegram observation across one redeploy to confirm in production.
Treat these surfaces as correct-by-test, not yet founder-confirmed.

— Mark
