# Mark — Sprint 14 Rulings (Alert-Spam Remediation)

**Date:** 2026-05-15 · **Branch:** `claude/review-system-audit-FBZ2h` · **Severity:** HIGH
**Status:** RULINGS — gates Wave 2. No code here. Cite file:line.

Root cause confirmed (not the gate logic): `risk_monitor.py:31` `STATE_FILE = "risk_monitor_state.json"` resolves under the `.:/app` bind mount (git tree), is **git-tracked** and **not in `.gitignore`**. The persistent named volume `sentinel_state` is mounted only at `/app/state` (heartbeat, `:11`), NOT the alert state. Every `git pull` reverts the file to commit `7ddde34`; recreate can lose it. So `prev` is repeatedly `None` → `should_alert` `:151 if prev is None: return True` fires; the stable key from `build_position_alert_key` (`:130-137`) and the `:169` gate never get a chance. Giveback (`:484-498`) and state-cooldown (`:81-97`) memory die the same way.

## 1. Alert policy table

Cadence numbers are existing constants only — none invented.

| State / signal | Surface | First fire | Re-fire cadence | Exact condition (file:line) |
|---|---|---|---|---|
| Power / Healthy, held, key unchanged | **Pull only** (Open Tasks) | never push | never | key from `:133-137` `{status,action,sizing}` unchanged AND no `STATUS_RANK` `:33` rise — **MUST NOT re-push** (the position working). Drop the `:151 prev is None` blanket push for non-P0 status. |
| Status escalation (any worsening) | Push | immediate | immediate | `STATUS_RANK[cur] > STATUS_RANK[prev]` `:158` — P0/P1, never throttled |
| Weak (`🟠`, no escalation) | Push once | on transition | `LIVE_ALERT_REPEAT_COOLDOWN` 45m `:43` only on key change `:169-171` | P2; de-escalation/oscillation only |
| Dead-money | Push once | on state entry | `STATE_ALERT_COOLDOWN["DEAD_MONEY"]` 12h `:52` | P3, `_should_fire_state_alert` `:81-97`, market-hours gated `:147` |
| Broken | Push | on entry | 6h `:162` AND `is_during_us_market_hours` `:161-164`; state re-entry `STATE_ALERT_COOLDOWN["BROKEN"]` 4h `:51` | P1 |
| Critical-exit (price<stop) | Push | immediate | 6h repeat in market hours `:161-164` | **P0 — never suppressed** |
| Giveback | Push | zone transition only `:487-492` | `GIVEBACK_COOLDOWN_SEC` 6h `:42` per class; **no repeat within same zone** | P2/P3 `:69,78`; requires `peak_open_r>=1.5` & not BROKEN `:481` |
| Deviation | Push | on class escalation `:459` | `DEVIATION_COOLDOWN_SEC` 3h `:41` | P0–P2 by `dev["alert_level"]` |
| Sizing-leak | Push once ever | one-time `:870-876` | never repeat (`sizing_leak_alerted` flag) | P-info; `< SIGN... SIZING_LEAK_THRESHOLD 0.65` `:46` |
| ALGO-observed | see §2 | — | — | gated at `:771`, `:819`, `:828` |
| Runner / checkpoint | Push once | state entry `:777` / `PROFIT_CHECKPOINTS` `:40` cross `:474` | `STATE_ALERT_COOLDOWN["RUNNER"]` 4h `:50`; hold-decision 24h `:780`; checkpoint once per level `:472-477` | P1/P2 |

**Hard rule:** a healthy held position whose alert-key (`status/action/sizing`, `:133-137`) is unchanged and `STATUS_RANK` not risen MUST NOT re-push — it belongs on the pull surface. This is invariant #7 (no recurring alert without per-position dedup) — the dedup must actually persist (§3).

## 2. ALGO push ruling (DEC-20260511-001 / invariant #8)

ALGO is observer-only. ALGO positions **must never push a management action** (no Runner/Broken/Dead-money/checkpoint/breakeven). The existing `_mgt_mode != "algo_observed"` guards at `:771`, `:819` are correct and MUST stay. Ruling:

- Allowed ALGO pushes, heavily throttled, observer-framed only: deep-loss **one-time** `≤ −2R` `:849-851` (P0-equivalent visibility), loss-streak yellow/orange one-shot-with-reset `:837-846`, deviation `:453-465`, portfolio visibility (24h throttle `:892`). All carry "פיקוח / מנוהל חיצונית", no exit/stop instruction (templates `:328-365` already conform).
- ALGO must NOT traverse the generic Live-Alert status push (`:649-680`) as a recurring management alert. Add an `is_algo`/`_mgt_mode=="algo_observed"` gate **before** the `send_telegram(msg)` at `:680` so ALGO yields at most a single throttled P0 visibility note, never a repeated status push (HOOD Weak→Broken→Broken spam is exactly this path firing because `prev` was lost). Gate path to cite for Wave 2: `risk_monitor.py:646-680` + `ec.classify_management_mode` at `:737`/`:700`. No change to ALGO math, R, or stats; DEC-20260515-006 read-out stays pull-only.

## 3. State-persistence ruling

Anti-spam memory (`prev` status, `last_alert_ts`, `last_giveback_class/ts`, `last_deviation_class/ts`, `last_state_alert_type/ts`, `checkpoints_hit`, `algo_*_alerted`, `cluster.last_alert_ts`, `risk_alert`) MUST survive **(a)** monitor cycles and **(b)** deploys (`git pull` + `up -d --build --force-recreate`).

Ruling:
- `risk_monitor_state.json` is **runtime state, not code**. It MUST be added to `.gitignore` and the tracked copy removed from the index (`git rm --cached`, file kept on disk) — consistent with DEC-20260510-006 / DEC-20260509-003 (operational state is gitignored). A `git pull` must NEVER reset it.
- It MUST be volume-persisted on a named volume that survives container recreate — same guarantee the heartbeat already has via `sentinel_state:/app/state` (`docker-compose.yml:106-108`, risk_monitor.py:11). Approved options for Architecture/Infra: move the file under `/app/state/` (point `STATE_FILE` at `state_io` path inside the persistent volume) **or** add a dedicated named-volume mount for it. Adding a `volumes:` entry is explicitly authorised here (SPRINT14_PLAN §36); the `command:` and `secure_runner` stay untouched.
- This changes **zero** risk/NAV/campaign/stop math — it only relocates/ignores a JSON file. `state_io` atomic+lock semantics (`state_io.py:47-81`) are unchanged; `_graceful_shutdown` `:1041-1062` still works.

## 4. MUST STILL FIRE (never delay/suppress)

Any anti-spam change MUST preserve, with zero added latency:
1. **Price < stop / Critical-exit** — `🚨 קריטי`, `CAT 22:33` class. P0 `:161-164`.
2. **Status worsening** — any `STATUS_RANK[cur] > STATUS_RANK[prev]` `:158` (Healthy→Weak→Broken→Critical).
3. **→ Broken state entry** `:804-806`; **deep deviation/`algo_deep_loss`** `:849`; deviation escalation `:459`.
4. **First-ever alert for a campaign** — genuine first observation still pushes (the fix removes the *spurious* `prev is None` caused by lost state, NOT a true first sighting).
5. **P0 deep-loss / system deviation** `ALERT_PRIORITY` P0 `:57-61`.

The remediation reduces noise by **persisting dedup memory**, not by widening cooldowns on escalations.

## 5. Consolidation pass/fail checklist (12)

1. `risk_monitor_state.json` in `.gitignore` AND `git rm --cached` (DEC-20260510-006). ☐
2. State volume-persisted; survives `force-recreate` (parity with `:11`/compose `:106-108`). ☐
3. `git pull` cannot reset state (verified: file not in `git ls-files`). ☐
4. PWR healthy unchanged-key scenario: ≤1 push then pull-only — no 7× repeat (invariant #7). ☐
5. HOOD ALGO Weak→Broken→Broken: no recurring management push; gate at `:680` (DEC-20260511-001, #8). ☐
6. Giveback same-zone repeat suppressed; cross-zone still fires `:487-492` (6h `:42` honoured because state persists). ☐
7. CAT critical-exit (price<stop) still fires immediately — §4.1, `:161-164`. ☐
8. Status escalation path `:158` untouched; first-ever true alert still fires — §4.2/4.4. ☐
9. No change to R/NAV/exposure/campaign/stop math (CLAUDE.md; AGENTS #2). ☐
10. No `docker-compose.yml` service `command:` change; secure_runner intact (DEC-20260515-009, CLAUDE.md). ☐
11. ALGO never enters Win-Rate/Expectancy; ALGO push stays observer-framed (#8, DEC-20260511-001). ☐
12. Full suite green (baseline 1620); new dedup/persistence unit tests added (AGENTS workflow #7). ☐

All 12 ☑ required before Wave 2 merge.
