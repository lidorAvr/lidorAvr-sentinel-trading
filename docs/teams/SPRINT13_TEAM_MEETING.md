# Sprint 13 — Team-Leads Meeting (Consolidation)

**Date:** 2026-05-15
**Branch:** `claude/review-system-audit-FBZ2h`
**Theme:** Operational hardening + data hygiene (from live-deploy findings).
**Structure:** Wave 1 (4 parallel teams) → team-leads checkpoint → Wave 2 (1 build) → this consolidation.
**Suite:** 1609 → **1620 passed, 0 failed** (+11; 1 pre-existing unrelated analytics warning). Drift test green (open_tasks.py/§6 not modified → drift-safe by construction). `bash -n deploy_watcher.sh` clean.

## Wave 1 commits
`081a322` Mark rulings · `03931c9` Arch+Infra design · `4a1c85c` Hyperscaler addendum · `11a60c6` Marketing week-3.

## Checkpoint (parent independent verification, pre-build)
- `deploy_watcher.sh:38` confirmed `up -d --build` with NO `down` (the recurring [Errno 101] cause). ✅
- `docker-compose.yml:37` `command: python3 telegram_bot_secure_runner.py` + `:43-45` DNS present (must stay). ✅
- `open_tasks.py:271-281` `COMPLETE_RISK_DATA` (urgency=None, info_only, never counted) + `telegram_backlog.py:86-97` writes only founder input / `-1` skip sentinel. ✅

## Wave 2 — parent independent verification (this consolidation)

| Item | Verified |
|---|---|
| Protected files untouched | ✅ empty git diff for `docker-compose.yml`, `deploy-watcher.service`, `telegram_bot_secure_runner.py` (CLAUDE.md hard constraint) |
| deploy_watcher single-purpose | ✅ only `:96` deploy cmd → `up -d --build --force-recreate`; NO `down` in any executable line (only comments). `down && up` rejected per Mark §1 (multi-service outage) |
| IPv4 self-check | ✅ `probe_telegram` uses `docker compose exec -T telegram-bot python3 -c` stdlib `socket`, `AF_INET` forced (the live failure was IPv4 route loss), 10s timeout, probes the CONTAINER not the host, no curl (slim image) |
| Never false-success | ✅ "Deploy complete." logged ONLY inside a passing probe; fail → retry once `up -d --force-recreate telegram-bot` → re-probe → `🔴 ALERT` + `deploy_last_alert` sentinel; git-pull/up failures alert + leave bot honestly UNCHANGED/UNKNOWN (AGENTS.md #1). No Telegram push added (#7) |
| Drift-safe | ✅ `open_tasks.py` + `§6` NOT modified → no new ruleset key; drift test green; no migration; no new table |
| No fabricated stop | ✅ `telegram_backlog.py` diff is additive wording only (Mark's verbatim `MISSING_STOP_BACKLOG_HE`); write path unchanged (founder-typed price or `-1` skip). `classify_missing_stops` is pure/read-only — docstring & code emit no stop/price/$/R; missing-stop rows never enter WR/Expectancy/PF (#8) |
| Missing-stops split | ✅ open-position-missing-stop = real risk gap → existing journal-backlog (actionable, real input); closed/legacy → existing gated `/clean`; `/health` notice (Sprint-12) unchanged + read-only split label appended |

## Integration ("הטמעה") — manual one-time host step (required)

`deploy_watcher.sh` is run by the host `deploy-watcher` systemd service; the running watcher cannot hot-swap its own script mid-deploy. Full procedure in `SPRINT13_WAVE2_IMPL.md §1.3/§1.4`. Summary:

```bash
ssh <pi> && cd ~/sentinel_trading
git pull origin claude/review-system-audit-FBZ2h     # brings the new deploy_watcher.sh
chmod +x deploy_watcher.sh
sudo systemctl restart deploy-watcher                # re-read the new script
#   NO `daemon-reload` — deploy-watcher.service is UNCHANGED
sudo systemctl status deploy-watcher                 # active (running)
```
The very next `🔄 Git Pull + Deploy` (or `touch deploy_trigger`) then uses `--force-recreate` and the post-deploy IPv4 self-check.

**Rollback:** `git revert <this commit>` (or restore the prior `deploy_watcher.sh`) + `sudo systemctl restart deploy-watcher`. No DB/compose/unit change to undo.

**Verification after install:** `SPRINT13_WAVE2_IMPL.md` V1–V8 (manual — host bash is not unit-testable). Key: trigger a deploy, then `grep -E 'connectivity OK|DEPLOY-ALERT' ~/sentinel_trading/deploy_watcher.log` — expect `connectivity OK ... Deploy complete.` and **no** DEPLOY-ALERT.

## Carried / out of scope
Sprint 11/12 live founder-UI smoke-test still outstanding (deployed + suite-green; recommend after this Sprint-13 host install). Hyperscaler PR-A3+ (only when moving past single-user). Broad data backfill beyond the flagged rows.

## Process note
Worktree isolation again did not take effect (build agent wrote to the shared tree); mitigated identically — parent independently verified every red-line item, ran the full suite, committed by explicit filenames. `.claude/` gitignored.
