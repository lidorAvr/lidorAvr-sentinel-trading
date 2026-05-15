# Sprint 14 — Team-Leads Meeting (Consolidation): Alert-Spam Fix

**Date:** 2026-05-15
**Branch:** `claude/review-system-audit-FBZ2h`
**Severity:** HIGH (alert fatigue burying real P0).
**Suite:** 1620 → **1638 passed, 0 failed** (+18; 1 pre-existing unrelated warning). Drift test green (open_tasks.py/§6 untouched).

## Wave 1 commits
`93d511e` Mark · `dea607b` Arch+Infra · `6761d84` Hyperscaler · `ebd2d0a` Marketing.
Mark + Arch independently converged on the root cause and the reuse-existing-volume approach.

## Root cause (verified at checkpoint, not assumed)
`risk_monitor_state.json` is git-tracked & NOT gitignored; its `STATE_FILE` (risk_monitor.py:31) is a relative path on the `.:/app` bind mount, NOT the persistent `sentinel_state` volume. **Smoking gun:** the committed file's `updated_at` is frozen at **2026-05-08** while today is 2026-05-15 — every `git pull` deploy reverts runtime mutations → `prev=None` → `should_alert:151` re-pushes every position. The gate logic was sound; the failure was lost persistence. Plus RC-6: no `algo_observed` gate before the generic push (~:680) → HOOD ALGO spam.

## Wave 2 — parent independent verification (this consolidation)

| Item | Verified |
|---|---|
| Protected files untouched | ✅ empty diff: `docker-compose.yml`, `telegram_bot_secure_runner.py`, `deploy_watcher.sh`, `deploy.sh` |
| No math change | ✅ `risk_monitor.py` diff = STATE_FILE constant + `CRITICAL_STATUSES` (lifted verbatim) + makedirs guard + should_alert + ALGO gate; zero risk/NAV/campaign/stop math |
| Persistence fix, no compose change | ✅ `state_io.RM_STATE_FILE="/app/state/risk_monitor_state.json"` — the **existing** `sentinel_state` volume already mounted on risk-monitor (docker-compose.yml:108). `risk_monitor.py`, `bot_helpers.py`, `dashboard.py`, `bot_health.py` all repointed via the shared constant |
| `should_alert` prev-None → P0-only | ✅ `:176-188` — genuine first sighting pushes ONLY if `current_status in CRITICAL_STATUSES`; healthy/held → pull-only. Escalation (`STATUS_RANK` :195) + critical-repeat (:198) preserved |
| **CAT 22:33 P0 must-fire** | ✅ `test_p0_critical_exit_always_fires_with_persisted_same_key` asserts 🚨 קריטי fires even with a persisted same-key prev; `test_prev_none_p0_first_sight_still_fires` asserts first-ever P0 fires; `test_algo_p0_deep_loss_still_fires` preserves the ALGO P0 path |
| ALGO gate | ✅ `do_alert and not _algo_observed` before the generic `:680` push; ALGO P0 dedicated paths untouched (Mark §2) |
| Drift / migration | ✅ no `_RULESET`/§6/migration/table change; drift test green |
| State untracked | ✅ `.gitignore` adds `risk_monitor_state.json` + `state/risk_monitor_state.json`; parent ran `git rm --cached risk_monitor_state.json` at consolidation so `git pull` can never revert it again |

## Behaviour after deploy (founder expectation — refined)
Not a full burst. On the first post-deploy cycle the state volume is empty → `prev=None` → only positions that are **already P0/critical at that moment** push (e.g. a real price<stop). Healthy/unchanged positions (PWR Power) are silent immediately. From cycle 2 on, anti-spam persists across `git pull` AND container recreate (volume) — the 7×/2.5h spam cannot recur. Real P0 escalations always fire (CAT anchor).

## Integration ("הטמעה") — human steps (deploy-ready)
1. `cd ~/sentinel_trading && ./deploy.sh` (Sprint-13 safe path; no new mechanism).
2. Optional hygiene: `rm -f ~/sentinel_trading/risk_monitor_state.json` (stray untracked root copy; harmless — code reads `/app/state/`).
3. Verify ≤1h: healthy PWR-type does NOT re-push; HOOD ALGO quiet; a real price<stop P0 STILL fires; `docker compose exec -T risk-monitor ls -la /app/state/risk_monitor_state.json` mtime advances each cycle.
4. Rollback: `git revert <consolidation commit> && ./deploy.sh` (volume file harmless to leave).

## Carried / out of scope
Sprint 11/12/13 live founder-UI smoke-test still outstanding. Hyperscaler PR-A3+. Per-user state split = deferred Phase-B touchpoint (PR-A5).

## Process note
Worktree isolation again did not take effect; mitigated identically — parent independently verified every red-line item, ran the full suite, committed by explicit filenames + the deferred `git rm --cached`. `.claude/` gitignored.
