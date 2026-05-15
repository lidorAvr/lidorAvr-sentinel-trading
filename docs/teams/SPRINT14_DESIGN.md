# Sprint 14 — Architecture + Infra Design (Alert-Spam Remediation)

**Date:** 2026-05-15
**Branch:** `claude/review-system-audit-FBZ2h`
**Team:** Architecture + Infra (combined)
**Status:** Wave-1 design — doc only, NO production code changes, NOT committed.
**Gating:** Mark's `MARK_SPRINT14_RULINGS.md` is **absent at time of writing**. Every
policy number / cadence / decision is left as a verbatim `⟨MARK:…⟩` slot. Nothing
invented. Wave-2 build is blocked until Mark fills these.
**Baseline:** 1620 tests collected (`pytest -q --co`), full suite must stay green.

---

## 1. Root-Cause Confirmation (evidence first)

### 1.1 The paradox to explain

`build_position_alert_key` (`risk_monitor.py:130-137`) returns
`{status, action, sizing}` and **excludes** `trigger`/price. For a healthy held
PWR (`🔥 Power / החזקה (מובילה) / sizing stable`) the key is **byte-stable across
cycles**. `should_alert` (`risk_monitor.py:149-173`) would, given a persisted
`prev`, take the path: not an escalation (`STATUS_RANK` equal), not
critical/broken, `prev_key == current_key` → **returns `(False, last_alert_ts)`**.
So a stable healthy position should fire **once, ever** — not 7× in 2.5h.

The gate logic is therefore **not** the primary defect. The defect is that
`prev` is **not the prior cycle's state** when `should_alert` runs.

### 1.2 Confirmed root causes (with file:line + infra evidence)

**RC-1 — `if prev is None: return True` fires whenever per-campaign state is
absent. `risk_monitor.py:151`.**
`prev = state["positions"].get(campaign_id)` (`risk_monitor.py:647`). If the
`positions` map is empty/reset at cycle start, `prev is None` → unconditional
re-push of every open position, healthy or not. This is the *mechanism*; RC-2/RC-3
are *why `prev` keeps being None / stale*.

**RC-2 — The state file is git-tracked and is reverted by every `git pull`
deploy. CONFIRMED, primary root cause.**
- `git ls-files | grep risk_monitor_state.json` → **tracked** (committed in
  `7cb067b`/`7ddde34`).
- `git check-ignore risk_monitor_state.json` → **NOT ignored**. `.gitignore`
  (read in full) lists `sentinel_config.json`, `risk_recommendations.json`,
  `risk_journal.json` — but **not** `risk_monitor_state.json`. It is the only
  runtime-mutated state file that is committed.
- **Smoking gun:** the committed/working `risk_monitor_state.json` has every
  `positions.*.updated_at` frozen at **`2026-05-08T10:17–10:18`** and
  `cluster.updated_at` at `2026-05-08`, with `manual`/`market` blocks at
  `2026-04-21`. Today is **2026-05-15**. A monitor that ran every 5 min would
  have rewritten `updated_at` on every cycle. The file is frozen at a
  week-old committed snapshot → runtime writes are being **discarded on each
  deploy**: the operator deploy path (`git pull` / `git checkout` /
  `git stash` during `deploy.sh` — DEC-20260515-010) overwrites or stashes the
  runtime-mutated tracked file, restoring the stale committed copy. This
  session ran many `docker compose up -d --build --force-recreate` + `git pull`
  cycles → anti-spam memory reset on **every** deploy.
- Corroborating: committed `PWR_9415330854` is `⚠️ Climactic`, but the live
  founder evidence shows PWR pushing as `🔥 Power / החזקה (מובילה)` — i.e. the
  live engine output no longer matches the reverted committed snapshot, so the
  reverted `prev` either mismatches the live key (RC-4) or is wiped, and the
  next cycle re-pushes.

**RC-3 — The state file is NOT on the persistent named volume; it is on the
bind mount and ephemeral semantics apply across `--force-recreate`.
`docker-compose.yml:106-108`.**
The `risk-monitor` service mounts:
```
volumes:
  - .:/app                 # repo bind mount — risk_monitor_state.json lives HERE (repo root)
  - sentinel_state:/app/state   # named volume — ONLY /app/state/*_last_cycle heartbeats
```
`STATE_FILE = "risk_monitor_state.json"` (`risk_monitor.py:31`) is a **relative
path**, written via `state_io.atomic_write_json` → resolves to **`/app/risk_monitor_state.json`**,
i.e. the **repo bind mount**, NOT the `sentinel_state` named volume. The named
volume only holds `/app/state/risk_monitor_last_cycle` (heartbeat). So the
anti-spam state's durability is entirely tied to the host repo working tree —
which RC-2 shows is reverted by `git`. (Container `--force-recreate` alone would
*preserve* it because the bind mount is the host repo; the killer is the `git`
revert of that tracked file, RC-2.)

**RC-4 — Cooperating factor: campaign-id-keyed `prev` + reverted stale state →
key mismatch path.** Even on a cycle where a stale (week-old) `prev` survives,
`prev.get("alert_key")` is the *old committed* key. If the live engine key
differs (`⚠️ Climactic` committed vs `🔥 Power` live), `should_alert` line 169
`prev_key != current_key` is **True**; with `last_alert_ts` also stale
(2026-05-08 → far older than `LIVE_ALERT_REPEAT_COOLDOWN = 45min`,
`risk_monitor.py:43`) the cooldown is already elapsed → **re-push**. After the
push, `new_alert_ts` is written to state — but RC-2 reverts it next deploy, so
the cooldown never accumulates. This explains the ~7 pushes clustering around
deploy/restart events rather than a clean single push.

**RC-5 — Giveback 6h cooldown ineffective — same persistence root cause.**
`GIVEBACK_COOLDOWN_SEC = 6h` (`risk_monitor.py:42`); giveback dedup state lives
in `last_giveback_class` / `last_giveback_ts` carried via the same
`state["positions"][campaign_id]` dict (`risk_monitor.py:496-498`, carry-over
list `:688-697`). When RC-2/RC-3 wipe/revert that dict, the giveback memory
resets too → PWR giveback 19:36 and 19:42 (6 min apart) despite the 6h cooldown.
Not a giveback-logic bug; same root cause as RC-2.

**RC-6 — ALGO observer-only positions still traverse the live-alert push path.**
The main live-alert block (`risk_monitor.py:651-680`) has **no
`management_mode == "algo_observed"` gate before `send_telegram(msg)`**. The
`_mgt_mode` ALGO gate (`risk_monitor.py:737, 771, 819, 828`) is applied only to
the *state-machine / breakeven / streak* sub-alerts, **after** the unconditional
live-alert push already fired. So HOOD (ALGO, DEC-20260511-001 observer-only)
push-spams Weak/Broken (21:08/21:20/21:45) through the un-gated live path. This
is a real **logic gap**, independent of persistence — it must be fixed even
once persistence is solved.

**RC-7 — Loop interval.** `risk_monitor.py:1073` `time.sleep(300)` → **5 min**
cycle (not 15–30 min). With persistence broken, that is a re-push opportunity
every 5 min; in practice pushes cluster at deploy/restart boundaries (RC-2)
because that is when state is reset, which matches the founder's observed
timestamps (bursts, not perfectly even 5-min spacing).

### 1.3 Root-cause summary

| ID | Root cause | Evidence |
|----|------------|----------|
| RC-2 | State file git-tracked → reverted by every `git pull`/`stash` deploy (PRIMARY) | `git ls-files`/`git check-ignore`; `updated_at` frozen 2026-05-08 vs today 2026-05-15 |
| RC-3 | State file on repo bind mount, NOT on `sentinel_state` named volume | `docker-compose.yml:106-108`, `risk_monitor.py:31` relative path |
| RC-1 | `if prev is None: return True` re-pushes everything when state absent | `risk_monitor.py:151` |
| RC-4 | Stale reverted `prev` → key/ts mismatch → cooldown never accumulates | `risk_monitor.py:169-171`, committed-state diff |
| RC-5 | Giveback cooldown ineffective — same persistence loss | `risk_monitor.py:496-498`, `:42` |
| RC-6 | No ALGO observer gate before the live-alert `send_telegram` | `risk_monitor.py:651-680` (gate absent) vs `:737/771/819` |
| RC-7 | 5-min loop amplifies every reset into a burst | `risk_monitor.py:1073` |

**Primary fix target: RC-2 + RC-3 (persist state across deploys).** RC-6 is an
independent must-fix logic gap. RC-1/RC-4/RC-5 are healed by fixing persistence;
RC-1 may also be hardened per Mark's ruling.

---

## 2. Fix Design (Mark-gated via ⟨MARK⟩ slots)

Two independent workstreams. **Zero risk/NAV/campaign/stop-math change. No
`docker-compose.yml` `command:` change. `telegram_bot_secure_runner.py`
untouched. No new migration.**

### 2.1 Persistence fix (RC-2 + RC-3) — primary

**Goal:** anti-spam memory survives (a) monitor cycles, (b) container
`--force-recreate`, and (c) `git pull` deploys.

**Design:** move the state file off the git-tracked repo root and onto the
existing `sentinel_state` **named volume** at `/app/state/`, and gitignore the
old name.

Concretely (exact change set, Wave-2):

| File | Change | Why |
|------|--------|-----|
| `risk_monitor.py:31` | `STATE_FILE = "risk_monitor_state.json"` → `STATE_FILE = os.path.join(_HEARTBEAT_DIR, "risk_monitor_state.json")` (i.e. `/app/state/risk_monitor_state.json`; `_HEARTBEAT_DIR` already `= "/app/state"` and `os.makedirs(..., exist_ok=True)` already called by `_touch_heartbeat`) | Path now lands on the `sentinel_state` named volume (RC-3) and outside the git tree (RC-2). No math touched. |
| `risk_monitor.py:1055` | `_graceful_shutdown` `if os.path.exists(STATE_FILE)` — automatically correct once `STATE_FILE` is the new path (no code edit beyond the constant) | Shutdown checkpoint follows the constant. |
| `bot_helpers.py:13` | `_RM_STATE_FILE = "risk_monitor_state.json"` → same `/app/state/risk_monitor_state.json` (single shared constant — see below) | The telegram-bot RMW (`bot_helpers._write_runner_decision`, `:51-66`) must point at the **same** file or the lock/state split-brains. Both services already mount `sentinel_state:/app/state`, so the cross-container `fcntl` lock in `state_io.file_lock` still coordinates (same inode on the shared named volume). |
| read-only consumers | `dashboard.py:495`, `bot_health.py:174` open the literal `"risk_monitor_state.json"` | Must be repointed to the new path (read-only; no behavior change other than the path). |
| `.gitignore` | add `risk_monitor_state.json` (and `state/risk_monitor_state.json`) | Belt-and-suspenders so a stray root copy is never re-committed and re-reverted (RC-2). Mirrors DEC-20260510-006 precedent (runtime JSON must be gitignored). |
| repo cleanup | `git rm --cached risk_monitor_state.json` (untrack the committed stale copy) — **Wave-2, operator-run, NOT in this doc-only pass** | Stops the week-old snapshot from ever reverting live state again. |

**Single-constant refactor (recommended, Mark to confirm):** introduce one
shared constant (e.g. in `state_io.py` or a tiny shared module) consumed by
`risk_monitor.py` and `bot_helpers.py` so the path can never drift between the
two writers. Additive, no logic change. ⟨MARK: approve single-shared-constant
location, or keep two literals?⟩

**`docker-compose.yml` `volumes:` — already sufficient, NO change needed (state
the finding explicitly):** `risk-monitor`, `telegram-bot`, `sentinel-bot`,
`reporting-service` **already** mount `sentinel_state:/app/state` and the named
volume `sentinel_state` already exists (`docker-compose.yml:170-172`). Moving
`STATE_FILE` into `/app/state/` reuses the existing persistent volume — **no new
`volumes:` entry, no `command:` change, secure_runner untouched.** This satisfies
the plan's constraint without needing a Mark `volumes:` ruling at all.
⟨MARK: confirm "reuse existing `sentinel_state:/app/state` volume, add no new
`volumes:` entry" is the approved persistence mechanism; OR if Mark instead
mandates a brand-new dedicated `volumes:` mount, that add is permitted ONLY by
Mark's explicit ruling and must not alter any `command:`.⟩

Note vs DEC-20260509-003 / DEC-20260510-006: those decided *operational*
JSON (IBKR sync, risk recommendations) may be lost on ephemeral volumes
("acceptable"). Anti-spam state is **NOT** in that class — losing it directly
violates AGENTS.md invariant #7 / #15 and Red Line "no recurring alert without a
per-position dedup flag." Hence it must be on the **persistent named volume**,
not merely gitignored. ⟨MARK: confirm anti-spam state is durability-critical
(persistent volume required), not best-effort like sync state.⟩

### 2.2 Logic hardening (Mark-gated)

**H-1 — ALGO observer-only push policy (RC-6).** Add a `management_mode ==
"algo_observed"` check **before** the live-alert `send_telegram(msg)` at
`risk_monitor.py:651-680`. Per DEC-20260511-001 ALGO is observer-only;
`_mgt_mode = ec.classify_management_mode(setup, sym)` is already computed at
`:737` — move/duplicate that classification above the live-alert block (pure
read, no math) and gate the push.
⟨MARK: ALGO live-alert policy — should an observer-only ALGO position push
on the generic Live-Alert path at all? Options: (a) never (ALGO uses only its
dedicated oversight alerts `:828-861`); (b) P0-only (only `🚨 חריגת סיכון אלגו` /
deep-loss escalations). Specify the exact allowed ALGO push set.⟩

**H-2 — Healthy held position should not push (PWR core scenario).**
⟨MARK: rule whether `🔥 Power` + `החזקה (מובילה)` + structure-intact +
unchanged key should EVER push, or be pull-only (Open Tasks / digest surface).
If pull-only: specify the suppression predicate (e.g. status in
{`🔥 Power`,`🟢 Healthy`} AND action == hold-class AND no sizing issue AND key
unchanged → no push, route to digest). Engineering will encode exactly Mark's
predicate; no math.⟩

**H-3 — `should_alert` first-sight behavior (RC-1).**
⟨MARK: when `prev is None` (genuinely new campaign vs state-loss), should the
first emission be push or pull-only-until-escalation? P0 (price<stop / →Broken /
critical-exit / algo risk breach) MUST still push on first sight regardless —
confirm. Specify whether non-P0 first-sight is push-once or digest-only.⟩

**H-4 — Re-alert cadence per priority tier.** `ALERT_PRIORITY`
(`risk_monitor.py:55-79`) and the cooldown constants
(`LIVE_ALERT_REPEAT_COOLDOWN=45m`, `DEVIATION_COOLDOWN_SEC=3h`,
`GIVEBACK_COOLDOWN_SEC=6h`, `STATE_ALERT_COOLDOWN` RUNNER/BROKEN=4h,
DEAD_MONEY=12h) are present. ⟨MARK: confirm or override each P0/P1/P2/P3
re-alert cadence number. P0 = always fire, never suppressed (confirm verbatim).⟩

**H-5 — Giveback re-alert policy (RC-5).** Logic already fires only on zone
transition (`risk_monitor.py:487-498`); the 6-min repeat was the persistence
loss (RC-5), not the zone logic. ⟨MARK: confirm "giveback fires on zone
transition only, 6h cooldown within zone, persistence-backed" is the policy;
confirm `GIVEBACK_COOLDOWN_SEC = 6h` stands.⟩

**Hard invariant carried into every option above:** real P0 escalations
(`🚨 קריטי`, `🔴 Broken` first entry, `🚨 חריגת סיכון אלגו`, price<stop,
status-worsened via `STATUS_RANK`) **always fire, never suppressed** by any
anti-spam change. The `CAT 22:33` critical-exit MUST still fire. This is encoded
today at `risk_monitor.py:158` (escalation) and `:161-164` (critical/broken) and
MUST be preserved verbatim. ⟨MARK: confirm the exact "must STILL fire" set.⟩

---

## 3. Wave-2 Test Plan

The dedup / persistence / `should_alert` / ALGO-gate logic **is unit-testable**
without Telegram/Supabase (same module-stub pattern as
`tests/test_e2e_risk_monitor.py` and `tests/test_phase3_state_alerts.py`).
New file: `tests/test_sprint14_alert_dedup.py`. Baseline 1620 → must stay green;
new tests additive.

**Persistence / reload (RC-2/RC-3/RC-4):**
1. `test_stable_key_no_repush_across_cycles` — same `prev` (healthy PWR key)
   passed to `should_alert` over N simulated cycles → push **exactly once**,
   subsequent calls return `(False, last_alert_ts)`.
2. `test_prev_persists_across_simulated_reload` — write state via
   `state_io.atomic_write_json` to a tmp path, `load_state()` it back, assert
   `prev` for the campaign is non-None and `alert_key`/`last_alert_ts`
   round-trip intact → no re-push after a simulated reload.
3. `test_state_path_is_under_app_state` — assert `risk_monitor.STATE_FILE` and
   `bot_helpers._RM_STATE_FILE` resolve to the same `/app/state/...` path
   (regression guard against the two literals drifting / landing in repo root).
4. `test_state_file_gitignored` — assert `risk_monitor_state.json` is matched by
   `.gitignore` (guards RC-2 from regressing).

**`should_alert` / ALGO gate (RC-1/RC-6):**
5. `test_prev_none_first_sight` — encode Mark's H-3 ruling
   (⟨MARK: push-once vs digest-only for non-P0 first sight⟩).
6. `test_algo_observer_not_pushed_on_live_path` — ALGO `management_mode ==
   algo_observed` position with a non-P0 status does **not** call
   `send_telegram` on the live-alert path (per H-1 ⟨MARK: exact allowed set⟩).
7. `test_algo_p0_still_fires` — ALGO at `🚨 חריגת סיכון אלגו` / open_r ≤ −2R
   **still** pushes (deep-loss path `:849`).

**P0 must-fire regression (hard invariant):**
8. `test_p0_critical_exit_always_fires` — `🚨 קריטי` / price<stop fires even
   when `prev` is a persisted same-key state and cooldown not elapsed.
9. `test_escalation_always_fires` — `STATUS_RANK` worsened (Healthy→Broken)
   fires immediately regardless of cooldown (`risk_monitor.py:158`).
10. `test_broken_repeat_market_hours_gate` — `🔴 Broken` repeat honors the 6h +
    US-market-hours gate (`:161-164`), per H-4 ⟨MARK cadence⟩.

**Giveback (RC-5):**
11. `test_giveback_6h_cooldown_honored_with_persistence` — two giveback checks
    6 min apart with persisted `last_giveback_ts` → second is suppressed
    (zone unchanged); proves the 19:36/19:42 spam cannot recur once state
    persists. ⟨MARK: confirm 6h.⟩
12. `test_giveback_fires_on_zone_transition` — natural→watch→tighten transitions
    still fire (no over-suppression).

**Founder live-incident regression suite (exact observed scenarios):**
13. `test_regression_pwr_healthy_no_respam` — replay PWR `🔥 Power /
    החזקה (מובילה) / structure-intact`, unchanged, Open R 1.3R, across the 7
    observed cycle/deploy events with **persistence intact** → **exactly one**
    push (or zero if Mark H-2 = pull-only).
14. `test_regression_hood_algo_no_respam` — HOOD ALGO Weak/Broken/Broken
    (21:08/21:20/21:45) → gated per H-1, no live-path spam.
15. `test_regression_pwr_giveback_dedup` — PWR giveback 19:36 then 19:42 →
    second suppressed (RC-5 fixed).
16. `test_regression_cat_p0_preserved` — `CAT 22:33` critical-exit (price<stop)
    **still fires** even amid all the above suppression — the anti-regression
    anchor.

Mark's 12-item consolidation checklist (`MARK_SPRINT14_RULINGS.md`) maps 1:1
onto cases 5–16; ⟨MARK: provide the checklist so each test asserts the exact
ruled number/cadence⟩.

---

## 4. Risk Classification & "Will NOT Change"

### 4.1 Risk classification (per CLAUDE.md)

**Overall: MEDIUM-HIGH.** `risk_monitor.py` is a CLAUDE.md *most-fragile* area
and houses the anti-spam state machine (AGENTS.md invariant #7, Red Line
"no recurring alert without per-position dedup"). However:

- The **persistence fix (2.1)** is **LOW-MEDIUM**: a path constant change +
  `.gitignore` + reuse of an **already-existing** named volume. No algorithm,
  no math, no `command:`, no schema. Risk is mainly the two-writer path
  alignment (`risk_monitor.py` ↔ `bot_helpers.py`) — mitigated by test #3 and
  the single-shared-constant refactor.
- The **logic hardening (2.2)** is **MEDIUM-HIGH** and Mark-gated: it changes
  *which* alerts push. Must not over-suppress P0. Fully covered by test cases
  5–16; build blocked until Mark fills every ⟨MARK⟩ slot.

Affected services: `risk-monitor` (primary), `telegram-bot` (shared state
writer via `bot_helpers`), `dashboard` + `bot_health` (read-only consumers of
the path). `sentinel-bot`, `reporting-service`, `autoheal` unaffected.

### 4.2 Will NOT change (explicit)

- ❌ Risk / NAV / R-multiple / exposure / campaign / stop / giveback **math**
  (engine_core untouched; `compute_*` not modified).
- ❌ `docker-compose.yml` **service `command:`** lines (all five services keep
  exact current commands; `risk-monitor` stays `python risk_monitor.py`).
- ❌ `telegram_bot_secure_runner.py` (CLAUDE.md hard constraint; secure_runner
  guardrails + 8 msg/60s rate-limit per DEC-20260515-009 untouched).
- ❌ Telegram admin-only protection.
- ❌ Real P0 firing — `risk_monitor.py:158` escalation + `:161-164`
  critical/broken paths preserved verbatim; `CAT 22:33` critical-exit MUST
  still fire (regression test #16).
- ❌ No new Supabase migration / no `user_id` threading (single-user, Phase-A
  byte-identical — see Hyperscaler addendum).
- ❌ No wholesale `risk_monitor.py` / `telegram_bot.py` rewrite — additive,
  minimal, Mark-gated.
- ❌ DECISIONS.md DEC IDs unchanged (this design is consistent with
  DEC-20260511-001 ALGO observer, DEC-20260510-002/-007 cooldowns,
  DEC-20260515-010 manual deploy).

### 4.3 Manual verification (post-deploy, host-only — not unit-testable)

1. Deploy via the supported manual path (`deploy.sh`, DEC-20260515-010); confirm
   `git pull` no longer reverts state (file now gitignored + on named volume).
2. `docker exec risk-monitor ls -la /app/state/risk_monitor_state.json` →
   exists on the `sentinel_state` volume; `updated_at` advances each ~5-min
   cycle (no longer frozen at a committed date).
3. `docker compose up -d --build --force-recreate` then re-inspect → state
   **survives** the recreate (timestamps continue, not reset).
4. Observe live founder Telegram for ≥3h across at least one redeploy: a
   healthy unchanged PWR pushes **0–1×** (per Mark H-2), HOOD ALGO does not
   live-path spam, PWR giveback does not repeat <6h apart.
5. Confirm a deliberately staged P0 (or the next genuine one) **still fires
   immediately** — anti-spam must never have suppressed a real escalation.
6. Rollback path: revert the `STATE_FILE` constant + `.gitignore` + the
   `bot_helpers` constant (single commit), `docker compose up -d --build
   --force-recreate`. No data migration to undo (state file is operational, not
   financial truth).

---

## Open ⟨MARK⟩ slots (consolidated — Wave-2 blockers)

1. ⟨MARK: persistence mechanism — confirm "reuse existing
   `sentinel_state:/app/state` named volume, no new `volumes:` entry"; or
   mandate a dedicated `volumes:` add (permitted only by Mark, no `command:`
   change).⟩
2. ⟨MARK: anti-spam state is durability-critical (persistent volume required),
   not best-effort like DEC-20260509-003/-006 sync state.⟩
3. ⟨MARK: single-shared-state-path-constant location, or keep two literals.⟩
4. ⟨MARK H-1: exact ALGO live-path push policy — never / P0-only / specify set.⟩
5. ⟨MARK H-2: healthy held PWR — push-never (pull-only) or push-once; exact
   suppression predicate.⟩
6. ⟨MARK H-3: `prev is None` non-P0 first-sight — push-once or digest-only;
   confirm P0 first-sight always pushes.⟩
7. ⟨MARK H-4: confirm/override every P0/P1/P2/P3 re-alert cadence number;
   confirm P0 = always fire, never suppressed.⟩
8. ⟨MARK H-5: confirm giveback zone-transition-only + `GIVEBACK_COOLDOWN_SEC`
   = 6h.⟩
9. ⟨MARK: the exact "must STILL fire" P0 set for the regression suite + the
   12-item consolidation checklist mapped to test cases 5–16.⟩
