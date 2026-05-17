# Sprint-26 — Ops/Infra Runtime & Deploy Resilience Findings

**Scope:** DOC-ONLY. NO code, NO new pipelines/features. Verification + flag-only.
**Role:** Ops/Infra team lead.
**Branch (host-tracked):** `claude/review-system-audit-FBZ2h` — production tracks the
branch, **not `main`**. **Actual HEAD:** `8c5a948`
(`docs(runbook): fix deploy gap — recreate ALL affected services`).
**Live stack:** 6 services (sentinel-bot, telegram-bot, reporting-service,
risk-monitor, dashboard, autoheal) recreated and healthy.

> **Coordination discrepancy (flag, not a runtime risk):** the Sprint-26
> brief states live HEAD `c761967`. That object does **not exist** in this
> repo (`git cat-file -t c761967` → not found); actual HEAD is `8c5a948`.
> Whoever deploys must reconcile the intended ref before pulling — deploying
> against an unverified ref label is itself an operational hazard. Treat the
> *content* of HEAD (verified below), not the label, as canonical.

`docs/teams/SPRINT26_RESEARCH_DOSSIER.md` is **absent** (optional per brief);
this review proceeds on the live tree + Sprint-25 OPS audit as the baseline.

---

## Verdict

**NOT 100/100.** The system is **safe to RUN as-is** (running containers are
healthy, guardrails active). It is **NOT unconditionally safe to REDEPLOY**:
the documented rollback path destroys live financial state. One **HIGH**
operational hazard, plus medium/low items below. All are pre-existing,
governed-Phase candidates — **no code changed this sprint.**

---

## Operational risks (severity-ordered)

### O1 — HIGH · Rollback (`git checkout`/`reset --hard`) silently reverts the live runtime NAV

- **Proof:** `git ls-files` lists `sentinel_config.json`; `git check-ignore
  sentinel_config.json` → **NOT-IGNORED** (tracked despite `.gitignore:3`).
  Committed content: `{"total_deposited": 7500.0, "risk_pct_input": 0.5,
  "nav": 7922.18}`. The file is **runtime-updated on the host** by the IBKR
  sync (CLAUDE.md "most fragile area": NAV/account config).
- **Hazard:** `docs/DEPLOYMENT_RUNBOOK.md:77` rollback is
  `git checkout "$(cat /tmp/sentinel_prev_ref.txt)"`. On a live host where the
  synced `nav` has drifted from the committed `7922.18`, that checkout (and
  any `git reset --hard`, and even a routine `git pull` if the committed value
  is ever bumped) **overwrites the live NAV with a stale committed number**.
  Because the `.:/app` mount makes the running code read this exact file,
  every downstream R-multiple / exposure / target-risk / risk-monitor
  computation is then silently wrong until the next IBKR sync — and
  NAV-Unify D1 makes an explicit `nav: 0` size `acc_size=0`/`target_risk=0`,
  so a bad revert can also zero out sizing. This is the **same incident class**
  as the documented Sprint-14 `risk_monitor_state.json` git-revert spam
  incident (`.gitignore:6-12`), still unresolved for the financially most
  sensitive file.
- **Why HIGH not just medium:** it is on the **rollback** path. Rollback runs
  precisely when production is already broken and the operator is under
  pressure — the worst moment to silently corrupt NAV. Recovery is not
  obvious (numbers look plausible, just wrong).
- **Recommended future fix (governed Phase, code change — flagged only):**
  `git rm --cached sentinel_config.json` (keep the working copy), so the
  `.gitignore` entry finally takes effect and no pull/checkout/reset can
  revert the host NAV; ship a minimal committed `sentinel_config.example.json`
  for first-boot; confirm `account_state.load()` fallback is exercised
  (`tests/test_account_state.py` exists). Until done, the runbook rollback
  step **must** be amended to a path-scoped checkout that **excludes**
  `sentinel_config.json` (e.g. snapshot the live file before any
  `git checkout`/`reset` and restore it after).

### O2 — MEDIUM · `git reset --hard` is nowhere forbidden in the rollback docs

- `docs/SAFE_CHANGE_PROTOCOL.md` "Rollback protocol" and
  `docs/DEPLOYMENT_RUNBOOK.md:75-80` describe `git checkout <ref>` /
  `git revert` but never explicitly **prohibit `git reset --hard`**. An
  operator improvising a "clean" rollback under pressure will reach for
  `reset --hard`, which (per O1) wipes the live NAV **and** any other
  runtime-tracked state. The hazard is real because the safe alternative is
  not written down.
- **Future fix:** add an explicit "**NEVER `git reset --hard` /
  `git checkout .` on the production host — it destroys runtime-updated
  `sentinel_config.json` (live NAV)**" red box to both rollback sections, and
  document the snapshot-restore-config wrapper.

### O3 — MEDIUM · `deploy_watcher.sh` exec-bit / `core.fileMode` friction

- **Proof:** `git ls-files -s deploy_watcher.sh` → mode **`100644`** (no
  committed exec bit); `git config core.fileMode` → **`true`**. With
  `core.fileMode=true`, the host `chmod +x` (one-time setup per the script
  header `:16`) shows the file as **modified** to git, and a `git pull`
  carrying a clean-tree expectation can hit "local changes would be
  overwritten" friction or silently reset the exec bit, breaking the
  systemd-driven in-bot deploy path.
- **Mitigation already in runbook:** `git config core.fileMode false`
  (`DEPLOYMENT_RUNBOOK.md:36`) — correct, but it is a **manual one-time host
  step**, not enforced, and absent from `SAFE_CHANGE_PROTOCOL.md`.
- **Future fix:** commit the script with mode `100755`
  (`git update-index --chmod=+x deploy_watcher.sh`) **and** add a tracked
  `.gitattributes`/repo-level note so the exec bit no longer depends on a
  per-host manual `core.fileMode` toggle.

### O4 — MEDIUM · `autoheal` image is unpinned (`willfarrell/autoheal:latest`)

- `docker-compose.yml:160`. The healing sidecar (the last line of defense
  for the 5 labelled services) floats on `:latest`. Any rebuild/repull can
  swap the watchdog implementation under production with no review — an
  upstream regression could stop healing silently, or change socket
  behaviour. Low likelihood, but the blast radius is "auto-recovery is gone
  and nobody is told."
- **Future fix:** pin to a digest or explicit tag
  (`willfarrell/autoheal:1.x.x` / `@sha256:…`); add to the deploy verification
  that the autoheal container is the pinned version.

### O5 — MEDIUM · CI/runtime interpreter parity gap (carried from Sprint-25 F3)

- `.github/workflows/tests.yml:23` runs **Python 3.11**; `Dockerfile:1` is
  **`python:3.10-slim`**. CI validates an interpreter production never runs.
  A 3.11-only construct passes CI and breaks the Orange-Pi container on
  deploy — invisible until it is live. This was flagged P1 in Sprint-25
  (F3) and is **still open** on the head being deployed.
- **Future fix:** pin CI `python-version: "3.10"` (or matrix `[3.10, 3.11]`)
  and re-run the full suite on 3.10.

### O6 — LOW · `risk-monitor` / `reporting-service` use `restart: unless-stopped`

- `docker-compose.yml:96,129`. `unless-stopped` (vs the bots' `always`) means
  if these are ever manually `docker stop`-ed and the Docker daemon later
  restarts, they stay **down** until a manual `up`. Real but low: the
  per-service healthcheck + `autoheal` recover a *crashed* (not
  operator-stopped) container, and the asymmetry is plausibly intentional
  for maintenance windows. Flag, don't change.
- **Future fix (optional):** document the asymmetry explicitly in the runbook
  so an operator knows these two will not self-resurrect after a deliberate
  stop + daemon bounce.

### O7 — LOW · `secure_runner` host-path `chdir` footgun (carried from Sprint-25 F8)

- `telegram_bot_secure_runner.py:48,173` default
  `SENTINEL_WORKDIR=/home/orangepi/sentinel_trading` (a **host** path; absent
  in-container, so `chdir` is skipped — correct *by accident*). If
  `SENTINEL_WORKDIR` is ever set in `.env`, the bot chdir's away from `/app`
  and every relative state/config read resolves wrong. Latent.
- **Future fix:** default `SENTINEL_WORKDIR` to `/app` or drop the chdir
  (Dockerfile already sets `WORKDIR /app`).

### O8 — INFO · scheduler `_mark_ran`-before-run (Sprint-25 F10) — unchanged

- A hard crash/OOM between `_mark_ran` and `_run_weekly/_monthly` consumes
  the day → that week's report silently skipped. Rare; fixing it is a
  behavior change (mark-after-success) → out of DOC-ONLY scope. Noted only.

### Known deferred ADDITION (note, do NOT build)

- **Dashboard on `:8501` has no auth** (`docker-compose.yml:69` publishes
  `8501:8501`; `streamlit run dashboard.py`, no reverse-proxy/basic-auth).
  Anyone with host network reach sees portfolio/NAV. This is a **deferred
  feature addition**, not a regression — recorded here, **not built** this
  sprint, candidate for a future governed Phase (auth proxy or bind to
  loopback + tunnel).

---

## Verified OK (closure-positive — no action)

- Secure runner correctly wired: `telegram-bot.command:
  python3 telegram_bot_secure_runner.py` (`docker-compose.yml:37`) — CLAUDE.md
  hard constraint satisfied; admin guard + rate limit + data-source
  disclosure active and observable (`_log`, code-verified, never logs
  token/admin id).
- **C1 DEV_PIN fail-closed verified live:** unset/empty `DEV_PIN` **DENIES**
  the entire dev menu incl. in-bot Git Pull+Deploy (`telegram_bot.py:174,188,
  304-311`; `telegram_devops.py:108-115` `not _DEV_PIN` → deny;
  `hmac.compare_digest`). **Operational consequence:** deploying without
  `DEV_PIN` in the host `.env` = **self-lockout** from the in-bot deploy
  button. The runbook's BLOCKING PREREQUISITE #1 (`grep -q '^DEV_PIN=' .env`)
  is correct and **mandatory** — keep it.
- Secrets: `.env` **not tracked** (`git ls-files` clean; host has no `.env` in
  the repo tree — correctly external); `risk_monitor_state.json` /
  `risk_recommendations.json` / `risk_journal.json` not tracked; CI `env:`
  uses placeholder values only. No token/key committed.
- Logging bounded on all 5 app services: `json-file`, `max-size:10m`,
  `max-file:5` → ≤50 MB/service, no disk-fill risk.
- `mem_limit: 1200m` on all 5 app services — bounded, OOM-kill + `restart` /
  `autoheal` recover.
- Healthchecks: every app service reads its own
  `/app/state/<name>_last_cycle` heartbeat with sane staleness windows
  (telegram 180s, sentinel 1980s, risk 720s, report 150s, dashboard HTTP
  `/_stcore/health`). Heartbeat writers/readers path-match
  (`secure_runner._touch_heartbeat`). `autoheal` sidecar with
  `autoheal=true` labels + 30s interval.
- Restart-ordering / mixed-restart gotcha is **correctly documented**:
  `DEPLOYMENT_RUNBOOK.md:38-49` explicitly states the `.:/app` mount updates
  files but long-running Python keeps OLD code until `--force-recreate`, and
  HEAD `8c5a948` fixed the gap to **recreate ALL affected services**.
  `deploy_watcher.sh:96` uses `up -d --build --force-recreate` (whole stack,
  no `down` — correct: avoids the network teardown outage). This is the
  single best-handled lesson from the real deploy.
- `restart: always` on the two bots + sentinel; `depends_on: telegram-bot`
  for risk-monitor & reporting-service — sane ordering.

---

## למנכ״ל — בשפה פשוטה

**האם בטוח להריץ עכשיו?** כן. ששת השירותים רצים ותקינים, כל מנגנוני
ההגנה (שומר אדמין, הגבלת קצב, גילוי מקור-נתונים, ננעל ב-DEV_PIN) פעילים
ומאומתים. אין סיכון פתוח שמחייב עצירה.

**האם בטוח לעשות פריסה מחדש / לחזור אחורה (rollback)?** לא באופן עיוור.
יש סכנה אחת חמורה אחת: קובץ `sentinel_config.json` מכיל את ה-NAV האמיתי
(כ-7,922$) ומתעדכן בזמן ריצה מול IBKR — אבל הוא **עדיין מנוהל ב-git**.
פקודת ה-rollback בספר הנהלים (`git checkout <ref>` / `git reset --hard`)
**תדרוס את ה-NAV החי בערך ישן שנשמר ב-git**, וכל חישובי הסיכון, החשיפה
וה-R יהיו שגויים בשקט — בדיוק ברגע הכי גרוע, כשכבר מנסים להציל מצב.

**הסכנה התפעולית המרכזית:** rollback / `git reset --hard` מוחק את ה-NAV
החי. סכנה משנית: פריסה בלי `DEV_PIN` ב-`.env` נועלת אותך מחוץ לכפתור
הפריסה בבוט (self-lockout). שתיהן ניתנות למניעה לחלוטין בנהלים.

## מה צריך לעשות

1. **(קריטי) להוציא את `sentinel_config.json` מ-git:**
   `git rm --cached sentinel_config.json` (להשאיר את הקובץ עצמו), כך
   ש-`.gitignore` סוף-סוף יתפוס אותו ושום `pull`/`checkout`/`reset` לא
   ידרוס את ה-NAV החי. עד שזה נעשה — **אסור** `git reset --hard` /
   `git checkout .` על שרת הייצור; ב-rollback קודם לגבות את הקובץ ואז
   לשחזר אותו.
2. **תמיד לעשות `--force-recreate` לכל השירותים** בפריסה (לא רק לבוטים).
   קוד פייתון ארוך-חיים ממשיך להריץ קוד ישן עד יצירה-מחדש של הקונטיינר.
   זה כבר כתוב נכון בספר הנהלים — לאכוף אותו.
3. **לפני כל פריסה לוודא `DEV_PIN` ב-`.env`** (`grep -q '^DEV_PIN=' .env`)
   — אחרת נעילה עצמית מכפתור הפריסה.
4. להוסיף לספר הנהלים אזהרה אדומה מפורשת נגד `git reset --hard` /
   `git checkout .` בשרת הייצור.
5. לקבע גרסת `autoheal` (לא `:latest`) ולהשוות את גרסת פייתון ב-CI
   (3.11) לזו של הייצור (3.10).

---

**Bottom line:** Safe to run, conditionally safe to redeploy. Verdict
**NOT 100/100** — one HIGH (rollback wipes live NAV; fix = untrack
`sentinel_config.json` + forbid `reset --hard` in the runbook) plus
medium/low pre-existing items, all routed to a future governed Phase. No
code touched this sprint.
