# Mark — Sprint 13 Rulings

Branch `claude/review-system-audit-FBZ2h`. I gate Wave 2. Cited file:line.

## 1. `deploy_watcher.sh` safe-change ruling

Evidence: `deploy_watcher.sh:38` runs `$COMPOSE_CMD up -d --build` with no
`down`. This session that left telegram-bot with `[Errno 101]` (stale bridge
attachment) while host+DNS were fine; `down && up -d` fixed it. This is
distinct from DEC-20260512-005 (DNS) — it is bridge re-attachment, not
resolution.

**RULING — use `docker compose up -d --build --force-recreate`.** It
recreates every container's network endpoint (curing the stale-bridge fault)
WITHOUT a separate `down`. Reject `down && up -d --build`: `down` tears the
whole network and stops risk-monitor + reporting-service + sentinel-bot —
full multi-service outage on every button-deploy, unacceptable for a system
holding live risk. `--force-recreate` re-attaches with near-rolling downtime
and is the conservative minimum that demonstrably addresses the observed
fault. Change is ONLY the command string at `deploy_watcher.sh:38`.

**HARD rules.** MUST NOT edit `docker-compose.yml` — `telegram-bot.command`
stays `python3 telegram_bot_secure_runner.py` (`docker-compose.yml:37`;
CLAUDE.md hard constraint; AGENTS.md:38). MUST NOT touch app code. The DNS
blocks (`docker-compose.yml:43-45`) stay (DEC-20260512-005).

**Mandatory post-deploy self-check.** After the `--force-recreate` block
succeeds (new branch at `deploy_watcher.sh:39`), probe telegram-bot
egress over IPv4: `docker exec telegram-bot python3 -c "import
socket; socket.create_connection(('api.telegram.org',443),10)"`. On
success: `log "connectivity OK"`. On failure: `log` the failure to
`deploy_watcher.log` (`:18,22`) AND retry once with `docker compose up -d
--force-recreate telegram-bot`; if still failing, log `🔴 ALERT` and write
the deploy_trigger-style alert — NEVER silently leave a dead bot
(AGENTS.md #1). No fabricated "deploy OK".

**Rollback (explicit).** (a) `git revert` the one-line `deploy_watcher.sh`
change; (b) manual host step — `sudo systemctl restart deploy-watcher` so
systemd re-reads the script (`deploy-watcher.service:11`; the watcher
cannot hot-swap its own running script — SPRINT13_PLAN.md:31). Until both
done, prior `up -d --build` behavior stands (known, recoverable via manual
`docker compose down && up -d`).

## 2. Missing-stops remediation ruling

55 rows (MSGE, SNEX, TSLA, JPM, HP), NULL/0 stop, detected read-only at
`bot_health.py:72-98`. Net-quantity decides open vs closed
(`supabase_repository.py:151-175`).

**RULING — split by lifecycle; (b)+(c), never fabricate.**

- **Open positions missing a stop = real risk gap (urgent).** Route to the
  EXISTING journal-backlog as an actionable real-stop-completion item. The
  flow already prompts the founder for the *true* initial stop
  (`telegram_backlog.py:86-97`) and only writes what the founder types — no
  default. This is approved path (b). It is NOT a fabricated value and these
  rows stay out of WR/Expectancy/PF until the founder completes them
  (AGENTS.md #8; `open_tasks.py:271-280` `COMPLETE_RISK_DATA`, urgency=None,
  never counted).
- **Genuinely archived rows (>30d, closed campaign) = hygiene only.**
  Legacy-classify via the now-gated `/clean` (path c) —
  `telegram_clean_gate.py`: defaulted-NO, open campaigns excluded
  (`:61-79,201-205`), 30-day window absolute (`:117`), `-1` is the existing
  *sentinel* meaning "no real stop", never presented as a price (AGENTS.md
  #1/#4).
- Pure notice-only (a) is INSUFFICIENT for open positions — an open
  position with no stop is a live risk hole, not cosmetic.

**Absolute rules.** No stop value is ever fabricated, inferred, or
defaulted as truth (AGENTS.md #1, Red Line :68). These rows NEVER enter
WR/Expectancy/PF (AGENTS.md #8). The `bot_health.py:92-98` notice text
stays verbatim (Sprint-12 §4) for closed/legacy hygiene.

**Approved Hebrew — journal-backlog open-position stop-completion item:**

```
‏🛡️ פוזיציה פתוחה ללא סטופ — {SYMBOL}
‏הזן את הסטופ ההתחלתי האמיתי (לדוגמה 150.50).
‏לא יומצא ערך. עד להשלמה — לא נכלל בסטטיסטיקה.
```

## 3. Pass/fail checklist — Sprint 13 consolidation

Any FAIL = item does not ship.

1. `deploy_watcher.sh:38` is the ONLY changed line; new command is
   `up -d --build --force-recreate` — no `down`. (SPRINT13_PLAN.md:10)
2. `docker-compose.yml:37` telegram-bot.command UNCHANGED
   (`telegram_bot_secure_runner.py`). FAIL if touched. (CLAUDE.md;
   AGENTS.md:38)
3. `docker-compose.yml:43-45` DNS blocks untouched. (DEC-20260512-005)
4. No app-code change for the deploy fix. (CLAUDE.md most-fragile)
5. Post-deploy IPv4 connectivity self-check present; failure path
   logs + retries + alerts, never silent. (AGENTS.md #1)
6. Explicit rollback documented incl. manual `systemctl restart
   deploy-watcher`. (AGENTS.md DoD; SPRINT13_PLAN.md:31)
7. Open-position missing-stop surfaces ONLY via existing journal-backlog
   and writes only founder-entered values. (AGENTS.md #1;
   `telegram_backlog.py:86-97`)
8. Zero fabricated/defaulted stop anywhere; `-1` only as existing
   sentinel, never shown as a price. (AGENTS.md #1, Red Line :68)
9. Missing-stop rows excluded from WR/Expectancy/PF; no R/NAV/campaign
   math changed; no tests touched there. (AGENTS.md #2,#8; CLAUDE.md)
10. No new Supabase migration; closed/legacy path stays the gated
    `/clean` (defaulted-NO, open campaigns excluded, 30d absolute).
    (`telegram_clean_gate.py:61-79,117,201-205`; AGENTS.md #4)
