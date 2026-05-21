# Meeting (UX) — OPS Findings

**Scope:** Three just-landed commits `3ac93e8` (meeting-fytd), `fdd4e84` (CLI helper), `e9872f8` (meeting-ux cleanup) on branch `claude/review-system-audit-FBZ2h` (HEAD `e9872f8`). **DOC-ONLY. NO code, NO new pipelines/features. Flag-only.** Cross-checked against the Sprint-25 OPS precedent (`docs/teams/SPRINT25_OPS_AUDIT.md`).

## Headline

The three commits are **operationally low-risk and additive** — secure-runner wrap, admin guard, anti-spam, PIN brute-force protection, heartbeat/healthcheck wiring, audit logging — all preserved and untouched. **But the CLI helper landed without runbook documentation** (F1) and the chat-log evidence reveals **a real `sentinel-bot` restart-loop pattern** (F2) that has been hidden by `autoheal` masking a tight `LOOP_INTERVAL_SEC` vs healthcheck-staleness ratio. Two MEDIUMs, three LOWs, no P0/P1. Coverage scope **regressed in posture** (F6): the new CLI script is tested but **not** in the `--cov=` allowlist, so it joins the unmeasured majority.

---

## F1 (MEDIUM) — `scripts/set_pre_db_pnl_estimate.py` has no runbook entry; `SENTINEL_CONFIG_PATH` is undocumented outside the script docstring

`scripts/set_pre_db_pnl_estimate.py:42` documents the env var. `docs/DEPLOYMENT_RUNBOOK.md` has **zero** matches for `set_pre_db`, `pre_db_realized`, or `SENTINEL_CONFIG_PATH` (verified by grep on `docs/*.md`). The commit `fdd4e84` describes the docker-exec invocation only in the commit body — invisible the moment the founder is at the Orange Pi prompt without `git log` in front of them.

- **Why it matters:** the script exists *because* the founder asked for a safe way to set `pre_db_realized_pnl_estimate` on the Orange Pi (commit body cites the 21/05 ~03:00 founder request). If the operator has to `git log | grep` for the invocation, the "safe alternative to hand-editing JSON" promise is half-delivered.
- **Production invocation reality:** the file lives at `/app/sentinel_config.json` inside the `telegram-bot` container (or any of the four services — all bind-mount `.:/app`). Canonical invocation: `docker exec -e SENTINEL_CONFIG_PATH=/app/sentinel_config.json telegram-bot python3 /app/scripts/set_pre_db_pnl_estimate.py --show`. **Not** in the runbook. Without it, the default `./sentinel_config.json` resolves against the container's `WORKDIR=/app` (Dockerfile:2) — so the env var is actually **redundant in-container** but **load-bearing on the host** (where CWD may be `~/sentinel_trading` or elsewhere). This is exactly the kind of footgun the runbook exists to eliminate.
- **Fix direction:** add a "F-YTD calibration" subsection to `docs/DEPLOYMENT_RUNBOOK.md` with the three canonical invocations (`--show`, `<value>`, `--clear`), both host and `docker exec` forms, and an explicit "leave `SENTINEL_CONFIG_PATH` unset inside the container" note. Optionally cross-link from `docs/DATA_CONTRACTS.md:508` (where the field is contractually defined).

## F2 (MEDIUM) — `sentinel-bot` restart-loop pattern masked by autoheal; LOOP_INTERVAL vs healthcheck staleness ratio is too tight

`main.py:32` `LOOP_INTERVAL_SEC = 900` (15 min); `docker-compose.yml:27` healthcheck stale-window is **1980s (33 min)** — only ~2.2× the loop interval. The "Sentinel Bot מחובר" startup banner is sent ONCE at `main.py:165`, **outside** the `while True:` loop — therefore every chat-log occurrence is a **real process restart**, not a scheduled reconnect.

- **Evidence pattern:** 11 reconnects across 18–21/05. Clusters: 03:31 / 03:36 / 03:31 / 03:37 / 03:52 (daily 03:30-ish band), and 08:58 / 09:01 / 10:03 / 11:06 / 12:06 / 13:13 (all inside or adjacent to the IBKR sync window 07:00–11:00, `main.py:29-30`). The 13:12 MRVL `evaluate_position_engine` error followed by 13:13 reconnect is the smoking gun: an exception inside the loop stalled the heartbeat past 1980s, autoheal (`willfarrell/autoheal`, compose:159) tripped, and `restart: always` brought it back — sending the banner again.
- **Why this is OPS-relevant now:** the three commits don't touch `main.py` or compose, but the UX cleanup landings expose a pattern of operator confusion (each "מחובר" reads as a healthy ping; in fact it's a self-healed crash). This is a **silent-fallback class** issue under AGENTS.md #1: the user-facing message presents a recovery as if it were a scheduled event.
- **Fix direction:** (a) widen `sentinel_bot_last_cycle` staleness to ~3-4× loop interval (e.g. 3600s) OR shorten the loop and bound external calls with timeouts; (b) tag the startup banner with a short "(restart)" suffix if `state/sentinel_bot_last_cycle` exists at boot — distinguishes first-start from autoheal-restart; (c) emit a single Telegram message per *day* aggregating restart count rather than one per restart. None are in scope for this meeting; flag only.

## F3 (LOW) — Atomic temp+rename across the docker bind-mount: works, but matches the host filesystem, not a Docker volume

`scripts/set_pre_db_pnl_estimate.py:88-106` uses `tempfile.mkstemp(dir=path.parent.resolve())` + `os.replace()`. The bind-mount `.:/app` (compose:16) means the temp file is created on the **host filesystem** (the Orange Pi's `~/sentinel_trading/`), and `os.replace` is atomic on POSIX *same-filesystem* renames. Since both source and destination resolve to the same host directory, atomicity holds — verified by `test_temp_files_cleaned_up` (`tests/test_scripts_set_pre_db_pnl_estimate.py:146`).

- **Caveat:** if `SENTINEL_CONFIG_PATH` is ever set to a path inside the named volume `sentinel_state:/app/state` (compose:17 / volumes:171), the temp file lands in the volume too — still same-fs, still atomic. But the script test does not exercise that path. If someone moves the config under `/app/state`, the assumption still holds; flag only.
- **Fix direction:** none required; add a note in the runbook (F1) clarifying that `sentinel_config.json` MUST stay in the bind-mounted repo root (host-managed per Sprint-27 untrack precedent), not inside the volume.

## F4 (LOW) — Rate-limit threshold (8 msgs / 60s) is appropriate; the 09:11 trip is expected behaviour, not a misconfiguration

`telegram_bot_secure_runner.py:49-51`: `MAX_MESSAGES=8`, `WINDOW_SECONDS=60`, `COOLDOWN_SECONDS=90`. The chat-log evidence (msg 18799 at 2026-05-19 09:11 firing "⏳ קצב הודעות גבוה מדי") during a journal-completion follow-up is the rate-limiter doing its job — 8 messages in a 60s burst is a legitimate trip threshold for an interactive flow that emits 3-5 cards per action.

- **Fix direction:** none required. The 90s cooldown is short enough to be a UX hiccup, not an outage. If the founder reports this as friction more than once a week, consider raising `TELEGRAM_MAX_MESSAGES_PER_WINDOW` to 12 — but **not** without re-verifying anti-spam intent under AGENTS.md #3. Flag only.

## F5 (LOW) — PIN brute-force protection intact; the "1945" → "4915" sequence (msg 18914) is benign operator typo

`telegram_devops.py:31-36`: `_PIN_RATE_LIMIT_COUNT=3` failed attempts within `_PIN_RATE_LIMIT_WINDOW=300s` (5 min). Persistent across container restart (`_PIN_FAILED_FILE = "/app/state/dev_pin_failed.json"`, `:34`); `hmac.compare_digest` constant-time compare (`:110`); every failure audit-logged (`:127-141`).

- The two-PIN-value pattern in chat (wrong "1945" → correct "4915" — looks like a digit-reorder typo, common when two PINs cohabit operator memory) consumed 1 of 3 attempts and was within the 5-min window. No rate-limit reached, no audit anomaly. **Anti-bruteforce intact.**
- **Fix direction:** none. Optional UX nicety (out of scope): after a failed attempt, show remaining attempts ("נשארו 2 ניסיונות") so the operator knows the threshold. Flag only.

## F6 (LOW) — New CLI script `scripts/set_pre_db_pnl_estimate.py` is NOT in the CI coverage allowlist

`.github/workflows/tests.yml:40-43` measures `--cov=engine_core,adaptive_risk_engine,analytics_engine,addon_risk_engine` only. The new helper has 14 tests (good) but lives **outside** the measured set — so `--cov-fail-under=67` (`:45`) gives it no floor. This is the same pre-existing class flagged in SPRINT25_OPS_AUDIT F6 (telegram bot, secure runner, scheduler, risk_monitor, dashboard also unmeasured); the script joins that bucket rather than worsening it.

- **Fix direction:** add `--cov=scripts.set_pre_db_pnl_estimate` (or `--cov=scripts/`) when the COVERAGE_BASELINE.md Sprint-8 broadening lands. Out of scope this sprint; flag only.

## Cross-cut convergence

- **F1 + F3 + F6** converge on the same gap: the CLI helper is a clean, well-tested utility but is **operationally orphaned** — no runbook entry, no coverage floor, no in-container env-var clarity. The code is fine; the surrounding scaffolding is not. Fix-direction is a single small doc addition to `DEPLOYMENT_RUNBOOK.md`.
- **F2 + F4** converge on operator perception: every "מחובר" banner and every rate-limit message currently looks identical regardless of cause. Better signal-to-noise on these two surfaces would resolve a category of false-alarm tickets.

## Ops invariants preserved (closure-positive)

- `docker-compose.yml:37` `telegram-bot.command: python3 telegram_bot_secure_runner.py` — secure runner wiring **untouched** (CLAUDE.md hard constraint).
- Admin guard (`:60`), rate limit (`:76-81`), data-source disclosure (`truth_suffix`, `:92-101`), audit-log (`telegram_devops.py:97-103,134-141`): all preserved by the three commits (none of them touch these files).
- Heartbeat path parity preserved (`telegram_bot_last_cycle` `/app/state`, `:27-35`). Healthchecks read same paths.
- No secrets/PII committed; `sentinel_config.json` remains gitignored per Sprint-27 untrack (verified `git check-ignore`).
- F-YTD config path is read-only at runtime by the four bot/dashboard/risk-monitor/scheduler callers; only the new CLI mutates it (atomic). No race condition possible — the CLI is operator-triggered, the readers re-read per-call.

## Out-of-scope but flagged

- **`telegram_bot_secure_runner.py:48` `WORKDIR='/home/orangepi/sentinel_trading'`** — still a host-path default inside the container (SPRINT25_OPS_AUDIT F8). Unchanged by these three commits; carry-forward.
- **CI Python 3.11 vs Docker 3.10-slim** (SPRINT25_OPS_AUDIT F3) — unchanged; the new CLI's `tempfile.mkstemp` + `os.fdopen` is stdlib-stable across 3.10/3.11 so no new exposure introduced.
- **`report_scheduler.py` `_mark_ran` before `_run_weekly/_run_monthly`** (SPRINT25_OPS_AUDIT F10) — unchanged.

## Sign-off

```
$ python3 -m pytest --collect-only -q | tail -3
tests/test_ux_formatting_comprehensive.py::TestSchedulerMonthLabels::test_monthly_period_label_uses_hebrew_months
tests/test_ux_formatting_comprehensive.py::TestSchedulerMonthLabels::test_weekly_period_label_format

2565 tests collected in 2.73s
```

**Findings:** 0 P0/P1, **2 MEDIUM** (F1, F2), **4 LOW** (F3, F4, F5, F6). Branch `claude/review-system-audit-FBZ2h` @ HEAD `e9872f8`. Three commits **safe to merge from an OPS standpoint**; recommend the single F1 runbook addition land before the next deploy so the operator has the CLI invocation in front of them on the Orange Pi.
