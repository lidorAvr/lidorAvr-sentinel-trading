# Sprint 14 — Wave-2 Build Impl Record (Alert-Spam Remediation)

**Date:** 2026-05-15
**Branch:** `claude/review-system-audit-FBZ2h`
**Engineer:** Sprint-14 Wave-2 build
**Gating docs (locked):** `SPRINT14_DESIGN.md`, `MARK_SPRINT14_RULINGS.md`,
`SPRINT14_PLAN.md`, `HYPERSCALER_SPRINT14_ADDENDUM.md`, `CLAUDE.md`, `AGENTS.md`.
**Baseline:** 1620 passed (full suite). Must stay green; new tests additive.

This record is written incrementally so an interruption still leaves a usable
trail. Status markers: `[DONE]`, `[IN PROGRESS]`, `[PENDING]`.

---

## 0. Scope (narrow, conservative)

Three workstreams, no math change, no `docker-compose.yml` change, no
`telegram_bot_secure_runner.py` change:

1. **PRIMARY — persistence (RC-2 + RC-3):** relocate `risk_monitor_state.json`
   onto the EXISTING `sentinel_state:/app/state` named volume (already mounted
   on risk-monitor at `docker-compose.yml:108`). No compose edit. Gitignore the
   file. One-time fresh start in the volume is accepted.
2. **RC-6 — ALGO push gate:** gate the generic recurring Live-Alert
   `send_telegram(msg)` (`risk_monitor.py:680`) so `algo_observed` positions
   never traverse it as a recurring management push (Mark §2).
3. **Cadence / healthy-hold hardening:** apply Mark §1 alert-policy table —
   unchanged-key healthy held position must NOT re-push; existing constants
   only, none invented (Mark §1).

Hard invariant carried through all three: every real P0 still fires
(Mark §4) — the `CAT 22:33 🚨 קריטי` critical-exit is the regression anchor.

---

## 1. Grounding verified in code (pre-change)

| Claim | Verified at | Result |
|---|---|---|
| `STATE_FILE` is a bare relative name (resolves to git tree root) | `risk_monitor.py:31` | `STATE_FILE = "risk_monitor_state.json"` — CONFIRMED |
| `bot_helpers` second writer points at same bare name | `bot_helpers.py:13` | `_RM_STATE_FILE = "risk_monitor_state.json"` — CONFIRMED |
| File is git-tracked, NOT gitignored | `git ls-files` / `git check-ignore` | tracked; `NOT_IGNORED` — CONFIRMED (RC-2) |
| `sentinel_state:/app/state` already mounted on risk-monitor | `docker-compose.yml:108` | `- sentinel_state:/app/state` present — CONFIRMED (no compose change needed) |
| Heartbeat dir constant already `/app/state` w/ makedirs | `risk_monitor.py:11,16` | `_HEARTBEAT_DIR="/app/state"`, `os.makedirs(...,exist_ok=True)` — CONFIRMED |
| Read-only consumers of the literal path | `dashboard.py:495`, `bot_health.py:174` | both `open("risk_monitor_state.json")` — CONFIRMED, repointed |
| `save_state` runs BEFORE the heartbeat makedirs in a cycle | `risk_monitor.py:1019` then `:1020` | CONFIRMED → `save_state` must create the dir itself (belt-and-suspenders; the named-volume mountpoint already exists) |
| `atomic_write_json` needs the target dir to exist (mkstemp dir=) | `state_io.py:70-71` | CONFIRMED → makedirs guard added in `save_state` |

---

## 2. Code changes (file:line) [DONE]

All line numbers are post-edit (the file shifted as comments were added).

### 2.1 Persistence — RC-2 + RC-3 (PRIMARY)

| File:line | Change | Notes |
|---|---|---|
| `state_io.py:42-54` | **NEW** shared constants `RM_STATE_DIR = "/app/state"`, `RM_STATE_FILE = os.path.join(RM_STATE_DIR, "risk_monitor_state.json")` | Single source of truth so the two cross-container writers can never drift onto two inodes (would split-brain the `fcntl` lock + dedup memory). Additive; no logic/math. Resolves SPRINT14_DESIGN §2.1 "single-shared-constant" + Mark §3 (location left to Infra). |
| `risk_monitor.py:31` | `STATE_FILE = "risk_monitor_state.json"` → `STATE_FILE = state_io.RM_STATE_FILE` (= `/app/state/risk_monitor_state.json`) | Path now on the EXISTING `sentinel_state` named volume (compose:108) and outside the git tree. `_graceful_shutdown:1071` `if os.path.exists(STATE_FILE)` follows the constant automatically (no extra edit). |
| `risk_monitor.py:save_state` | Added `os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)` guard before the lock/atomic write | `save_state` (`:1037`) runs BEFORE `_touch_heartbeat` (`:1038`) in a cycle, so on a brand-new volume's first post-deploy cycle the dir-create keeps `atomic_write_json`'s `mkstemp(dir=...)` safe. The named-volume mountpoint already exists; this is belt-and-suspenders. No math. |
| `bot_helpers.py:13` | `_RM_STATE_FILE = "risk_monitor_state.json"` → `_RM_STATE_FILE = state_io.RM_STATE_FILE` | The telegram-bot runner-decision RMW now writes the SAME inode on the shared volume → cross-container `fcntl` lock + dedup state stay coordinated. |
| `bot_helpers._write_runner_decision` | Added the same `os.makedirs(...exist_ok=True)` guard before the lock | The bot could be the first writer on a fresh volume. |
| `dashboard.py:13` + `:497` | Added `import state_io`; `open("risk_monitor_state.json")` → `open(state_io.RM_STATE_FILE)` | Read-only consumer repointed; no behavior change beyond the path. |
| `bot_health.py:14` + `:176` | Added `import state_io`; `json.load(open("risk_monitor_state.json"))` → `json.load(open(state_io.RM_STATE_FILE))` | Read-only health probe repointed. |
| `.gitignore` | Added `risk_monitor_state.json` and `state/risk_monitor_state.json` (with rationale comment) | Belt-and-suspenders so a stray copy can never be re-committed and re-reverted (RC-2). `git rm --cached` is deliberately NOT run here — the parent does that at consolidation (Mark §5 item 1). |

### 2.2 RC-6 — ALGO observer-only push gate

| File:line | Change |
|---|---|
| `risk_monitor.py` (live-alert block, ~`:664-688`) | Compute `_mgt_mode = ec.classify_management_mode(setup, sym)` and `_algo_observed = (_mgt_mode == "algo_observed")` BEFORE the generic push; changed `if do_alert:` → `if do_alert and not _algo_observed:` so `send_telegram(msg)` (the generic recurring Live-Alert at the old `:680`) is gated for ALGO observer-only positions. |
| `risk_monitor.py` (old `:737`) | Removed the now-duplicate `_mgt_mode = ec.classify_management_mode(...)` (hoisted above; replaced with a comment). Value is identical → the existing `_mgt_mode != "algo_observed"` guards at `:771/:789/:837/:846` are unchanged. Pure read, no math, classification called exactly once per position (same as before). |

### 2.3 Cadence / healthy-hold hardening (Mark §1 row 1)

| File:line | Change |
|---|---|
| `risk_monitor.py:39` | **NEW** module constant `CRITICAL_STATUSES = ["🚨 קריטי", "🔴 Broken", "🚨 חריגת סיכון אלגו"]` — lifted VERBATIM from the inline list that was in `should_alert`'s critical/broken repeat branch. No status string changed. |
| `risk_monitor.py:should_alert` `prev is None` branch | `if prev is None: return True, now_ts` → return `(current_status in CRITICAL_STATUSES), now_ts`. Mark §1 row 1: "Drop the `:151 prev is None` blanket push for non-P0 status." A genuine non-P0 first sighting (healthy/held) is pull-only; a genuine first sighting that is ALREADY P0/critical still fires immediately (Mark §4.1/4.3/4.5). Caller still records state either way → later escalations fire normally. |
| `risk_monitor.py:should_alert` critical-repeat branch | `if current_status in [".."]` → `if current_status in CRITICAL_STATUSES` (same values, now the shared constant — the two sites can never drift). |

The unchanged-key healthy-hold no-repush is the EXISTING fall-through
`return False, last_alert_ts` when `prev_key == current_key` and not an
escalation/critical (SPRINT14_DESIGN §1.1: it was never the defect — it just
needed `prev` to persist, which §2.1 now guarantees). The non-escalating
key-change path keeps the existing `LIVE_ALERT_REPEAT_COOLDOWN` (45m) — Mark
§1 "Weak (no escalation)" row, existing constant, **no number invented**.

---

## 3. How each Mark ruling / ⟨MARK⟩ slot is honored [DONE]

- **MARK §1 row 1 (Power/Healthy held, key unchanged → pull only, never push,
  drop the `:151 prev is None` blanket push for non-P0):** honored exactly —
  `should_alert` `prev is None` now returns `False` for non-P0 status; the
  unchanged-key fall-through already returns `False`. Test cases 1, 5, 13.
- **MARK §1 "Status escalation → immediate, never throttled":** untouched
  `STATUS_RANK` escalation branch (`:195`). Tests 8, 9, 16.
- **MARK §1 "Weak (no escalation) → 45m only on key change":** existing
  `LIVE_ALERT_REPEAT_COOLDOWN` path unchanged. No new number.
- **MARK §1 "Critical-exit (price<stop) → P0, never suppressed; 6h repeat in
  market hours":** existing `:198-201` branch, now using `CRITICAL_STATUSES`;
  values identical. Tests 8, 10, 16.
- **MARK §1 "Giveback → zone transition only, 6h per class, no within-zone
  repeat":** existing `:516-536` logic unchanged; `GIVEBACK_COOLDOWN_SEC` =
  6h asserted unchanged in test 11. Tests 11, 12, 15.
- **MARK §2 (ALGO observer-only — never push a management action; gate the
  generic Live-Alert at `:680`; existing `:771/:819` guards stay):** honored
  exactly — `_algo_observed` gate added before the generic push; the
  duplicate-removed `_mgt_mode` keeps every downstream ALGO guard identical;
  ALGO's allowed observer-framed paths (deep-loss one-time, loss-streak,
  deviation, 24h portfolio) are NOT the generic msg and keep firing. Tests
  6, 7, 14.
- **MARK §3 (state is runtime not code; `.gitignore` + persistent named
  volume parity with the heartbeat):** `STATE_FILE`/`_RM_STATE_FILE` →
  `/app/state` (the `sentinel_state` volume, parity with the heartbeat);
  `.gitignore` updated; `state_io` atomic+lock semantics unchanged;
  `_graceful_shutdown` still works. NO compose change (the volume is already
  mounted at `docker-compose.yml:108`). `git rm --cached` deferred to the
  parent (Mark §5 item 1). Tests 2, 3, 4.
- **MARK §4 (MUST STILL FIRE set):** all five preserved — see §4 below.
- **⟨MARK⟩ design slots 1–9 (SPRINT14_DESIGN):** all resolved from
  MARK_SPRINT14_RULINGS — slot 1 = reuse existing volume (Mark §3); slot 2 =
  durability-critical persistent volume (Mark §3); slot 3 = single shared
  constant in `state_io` (Mark §3 left location to Infra; design §2.1
  recommended single-constant; chosen `state_io.RM_STATE_FILE`); slot 4 =
  ALGO never on generic path, only dedicated throttled visibility (Mark §2);
  slot 5 = healthy held pull-only, never push (Mark §1 row 1); slot 6 = non-P0
  first sight pull-only, P0 first sight always pushes (Mark §1 row 1 + §4.4);
  slot 7 = cadence numbers are existing constants only, P0 always fires
  (Mark §1/§4); slot 8 = giveback zone-only + 6h (Mark §1 giveback row);
  slot 9 = must-fire set = Mark §4, mapped to tests 8–16. **No cadence /
  policy number / wording invented; every slot filled from the rulings doc.**

---

## 4. Must-still-fire proof (Mark §4) [DONE]

| Mark §4 item | Mechanism preserved | Test |
|---|---|---|
| 1. Price<stop / Critical-exit (`🚨 קריטי`, CAT 22:33) | escalation branch `:195` + critical branch `:198`; first-sight P0 returns True | 8, 16 |
| 2. Status worsening (`STATUS_RANK[cur]>STATUS_RANK[prev]`) | branch `:195` untouched | 9, 16 |
| 3. → Broken entry / deep deviation / `algo_deep_loss` / deviation escalation | state-machine `:855` + ALGO deep-loss `:867` + deviation path — none touched; ALGO gate only blocks the GENERIC msg, not these dedicated paths | 7, 9 |
| 4. First-ever genuine alert | non-P0 first sight is intentionally pull-only per Mark §1 row 1; P0 first sight still pushes (returns True) | 5b, 16 |
| 5. P0 deep-loss / system deviation | ALERT_PRIORITY P0 paths + deep-loss `:867` untouched | 7 |

**CAT 22:33 anchor:** test `test_regression_cat_p0_preserved` asserts the
critical-exit fires (a) as a genuine first sighting, (b) as a Healthy→Critical
escalation with a persisted recent prev, and (c) is in `CRITICAL_STATUSES`.

---

## 5. One-time fresh-start note [DONE]

The stale committed `risk_monitor_state.json` (every `updated_at` frozen at
2026-05-08, today 2026-05-15) is **deliberately NOT migrated**. After deploy,
`/app/state/risk_monitor_state.json` does not yet exist on the named volume,
so the first post-deploy cycle sees `prev is None` for every open position:

- a healthy/held non-P0 position → pull-only (no push) per Mark §1 row 1;
- a position already at P0/critical → one immediate push (correct — Mark §4);

then state is written to the persistent volume and every subsequent cycle has
a real `prev`. From that point dedup memory persists across cycles, container
`--force-recreate`, AND `git pull` (file is gitignored + on the named volume).
A one-time fresh start is correct and acceptable — no migration, no Supabase
change, no financial-truth data involved (anti-spam memory is operational).

---

## 6. Manual post-deploy verification (host-only) [DONE]

1. Deploy via the supported manual path (`deploy.sh`, DEC-20260515-010).
2. `docker exec risk-monitor ls -la /app/state/risk_monitor_state.json` →
   exists on the `sentinel_state` volume; `updated_at` advances every ~5-min
   cycle (no longer frozen at a committed date).
3. `docker compose up -d --build --force-recreate`, re-inspect → state
   **survives** (timestamps continue, not reset). Run a `git pull` → file is
   NOT reverted (gitignored, not in `git ls-files` after the parent's
   `git rm --cached`).
4. Observe founder Telegram ≥3h across ≥1 redeploy: healthy unchanged PWR
   pushes **0×** (pull-only per Mark §1 row 1); HOOD ALGO does NOT live-path
   spam; PWR giveback does not repeat <6h within the same zone.
5. Confirm a deliberately staged or next-genuine **P0 still fires
   immediately** — e.g. a `CAT 22:33`-type `🚨 קריטי | מחיר נוכחי נמוך מסטופ`
   must push with zero added latency. Anti-spam must never suppress a real
   escalation.
6. Rollback: revert the `state_io` constants + `STATE_FILE`/`_RM_STATE_FILE`
   + `.gitignore` + the two read-only consumers + the RC-6 gate + the
   `CRITICAL_STATUSES`/first-sight change (single revert), then
   `docker compose up -d --build --force-recreate`. No data migration to
   undo (state file is operational, not financial truth).

---

## 7. Test delta [DONE]

- **New file:** `tests/test_sprint14_alert_dedup.py` — 18 tests (the 16
  SPRINT14_DESIGN §3 cases + 2 split helper assertions: P0 first-sight, and
  non-ALGO-still-pushes).
- **Baseline:** 1620 → **full suite 1638 passed, 0 failed, 1 warning**
  (pre-existing unrelated `analytics_engine` dateutil warning).
- **Drift test:** `tests/test_open_tasks.py::test_ruleset_matches_methodology_spec`
  → **1 passed** (untouched — no `open_tasks` / `_RULESET` / §6 change).
- Command: `python -m pytest -q -p no:cacheprovider`.

---

## 8. Consolidation checklist (Mark §5, 12 items) [DONE]

1. `risk_monitor_state.json` in `.gitignore` ☑ ; `git rm --cached` →
   **deferred to parent at consolidation** (per task instruction). ◐
2. State volume-persisted, survives `force-recreate` (parity w/ heartbeat) ☑
   (path = `state_io.RM_STATE_FILE` = `/app/state/...`, the existing
   `sentinel_state` volume).
3. `git pull` cannot reset state ☑ (gitignored; parent's `git rm --cached`
   completes "not in `git ls-files`").
4. PWR healthy unchanged-key ≤1 push then pull-only — no 7× ☑ (tests 1, 13:
   **0 pushes**).
5. HOOD ALGO Weak→Broken→Broken — no recurring management push, gated at the
   generic `:680` ☑ (tests 6, 14).
6. Giveback same-zone repeat suppressed; cross-zone still fires; 6h honored
   because state persists ☑ (tests 11, 12, 15).
7. CAT critical-exit (price<stop) still fires immediately ☑ (tests 8, 16).
8. Status escalation path untouched; first-ever true P0 still fires ☑
   (tests 9, 5b, 16).
9. No R/NAV/exposure/campaign/stop math change ☑ (only path constants +
   gate predicates + a status-list constant; engine_core untouched).
10. No `docker-compose.yml` service `command:` change; secure_runner intact
    ☑ (compose NOT edited at all).
11. ALGO never enters Win-Rate/Expectancy; ALGO push stays observer-framed
    ☑ (no stats touched; ALGO only gated OUT of the generic push).
12. Full suite green (baseline 1620); new dedup/persistence unit tests added
    ☑ (**1638 passed**; +18 new).

Items 1 (`git rm --cached`) is intentionally left to the parent's
consolidation per the Wave-2 task instruction (do not `git rm`, leave the
tree dirty). All other 11 are green.
