# Sprint-28 — Ops/Infra Runtime & Deploy-Resilience Re-Review (post-Sprint-27)

**Scope:** DOC-ONLY. NO code, NO new pipelines/features. Verification +
flag-only — a re-run of the Sprint-26 100/100 ops review against the
post-Sprint-27 LIVE state.
**Role:** Ops/Infra team lead.
**LIVE ref:** `168aaa2` (`feat(sprint-27): execute Sprint-26 findings —
dashboard honesty, repo-hygiene, companion voice, housekeeping`).
**Deploy reality:** Sprint-27 deployed via the documented host-safe
procedure; live NAV **$7921.07 preserved** across the W2 untrack; all 6
services recreated healthy (founder-confirmed).

> The Sprint-26 brief-label discrepancy (`c761967`) is now historic; this
> review is anchored to the **verified content** of HEAD `168aaa2`, not a
> label. The local sandbox `sentinel_config.json` is a 20-byte stub — that
> is correct and expected: the file is now host-managed (like `.env`); the
> real live NAV lives only on the production host.

---

## Verdict

**Materially safer than Sprint-26. The single HIGH that blocked
"unconditionally safe to REDEPLOY" is CLOSED.** The system remains **safe
to RUN** and is now **safe to REDEPLOY and to ROLL BACK by the documented
procedure** — the live NAV is no longer git-tracked, so no
`pull`/`checkout`/`revert`/`reset` can overwrite it, and the real deploy
empirically confirmed this ($7921.07 survived the untrack).

Still **NOT 100/100**: O1 is closed but leaves one **MEDIUM residual**
(the untrack is not guarded against future re-tracking), and the
pre-existing MEDIUM/LOW items O3–O8 are **unchanged** (Sprint-27 was not
scoped to them). No code changed this sprint.

---

## O1 closed? **YES — verified from source/config.**

Four-part fix, each independently verified on `168aaa2`:

1. **Untracked.** `git cat-file -t HEAD:sentinel_config.json` →
   `fatal: path exists on disk, but not in 'HEAD'`. `git ls-files` lists
   only `sentinel_config.example.json`, **not** `sentinel_config.json`.
   The Sprint-27 commit stat shows `sentinel_config.json | 1 -` (the
   `git rm --cached`). The `.gitignore:3` entry now actually bites:
   `git check-ignore sentinel_config.json` → **IGNORED** (was NOT-IGNORED
   in Sprint-26 — the exact O1 proof, now inverted).
2. **Example template committed.** `sentinel_config.example.json` is a
   tracked blob at HEAD with a correct schema (`nav`/`total_deposited`/
   `risk_pct_input`/`nav_updated_at`) and an explicit in-file comment
   stating the live file is gitignored and must never be tracked. Fresh
   clones get a shape; `account_state.load()` fallback is test-covered
   (`tests/test_account_state.py`).
3. **Runbook §4b host-safe untrack procedure — correct & complete.**
   `DEPLOYMENT_RUNBOOK.md:73-87`: backup live NAV → print it →
   `git rm --cached` locally → `--ff-only` pull → re-verify NAV equals
   backup → restore-if-missing → recreate-all. Ordering is right
   (backup+local-untrack **before** the pull that lands the untrack
   commit, so the pull never deletes the working file). The real deploy
   exercising exactly this path with NAV preserved is the strongest
   possible confirmation.
4. **`git reset --hard` / `git checkout .` forbidden.** Explicit red-box
   prohibition in both `DEPLOYMENT_RUNBOOK.md:87` and the §5 rollback
   block (`:100`), plus the rollback now uses a ref-scoped
   `git checkout <ref>` that — post-untrack — no longer touches the
   live NAV, with a `cp -a … /tmp/nav_live.bak` belt-and-braces snapshot
   retained anyway. This also closes Sprint-26 **O2**.

**Conclusion: the rollback path can no longer silently corrupt the live
NAV. O1 (HIGH) and O2 (MEDIUM) are CLOSED.**

---

## Residual ops risks (severity-ordered)

### O1-R — MEDIUM · the untrack is durable but **not guarded** against re-tracking

- `git rm --cached` + `.gitignore` is durable for the *normal* path:
  `git pull`/`checkout`/`reset` will not resurrect a gitignored file, and
  `git add -A` / `git add .` **skip gitignored files** — so a routine
  accidental "add everything" will NOT re-track it.
- **But** the protection is one footgun deep: `git add -f sentinel_config.json`
  (force), or an explicit path add of a future un-ignored variant, or
  someone "fixing" `.gitignore`, silently re-tracks the live NAV and
  re-opens O1 in full. **No test guards this.** Sprint-14's
  `risk_monitor_state.json` regression has a guard test
  (`tests/test_sprint14_alert_dedup.py::test_state_file_gitignored`); the
  financially most-sensitive file `sentinel_config.json` has **none**.
- **Why only MEDIUM (not HIGH):** requires a deliberate `-f` / explicit
  act, not a routine command; the runbook red-box + the example file's
  in-file warning are real deterrents; and the rollback is now safe even
  if re-tracking happened, *until* a stale value were committed.
- **Future fix (governed Phase, code/test — flagged only):** add a
  one-line guard test mirroring the Sprint-14 precedent:
  assert `sentinel_config.json NOT in git ls-files` AND
  `git check-ignore` returns it AND `.gitignore` contains the line. This
  makes a future re-track fail CI loudly instead of silently re-opening
  O1.

### O5 — MEDIUM · CI/runtime interpreter parity gap — **STILL OPEN (unchanged)**

- `.github/workflows/tests.yml:23` → **Python 3.11**; `Dockerfile:1` →
  **`python:3.10-slim`**. CI validates an interpreter production never
  runs. Carried from Sprint-25 F3 / Sprint-26 O5; **Sprint-27 was not
  scoped to it**. Unchanged hazard: a 3.11-only construct passes CI and
  breaks the Orange-Pi container on deploy.
- **Future fix:** pin CI `python-version: "3.10"` or matrix `[3.10, 3.11]`.

### O3 — MEDIUM · `deploy_watcher.sh` exec-bit / `core.fileMode` friction — unchanged

- Mode `100644` committed; runbook mitigation `git config core.fileMode
  false` is still a manual one-time host step, not enforced. Sprint-27 did
  not touch it.

### O4 — MEDIUM · `autoheal` image unpinned — unchanged

- `docker-compose.yml:160` `willfarrell/autoheal:latest`. The watchdog for
  all 5 labelled services still floats on `:latest`. Sprint-27 did not
  touch `docker-compose.yml` (verified: only the example file + new
  helper + tests + docs changed).

### O6 — LOW · `risk-monitor`/`reporting-service` `restart: unless-stopped` — unchanged

- `docker-compose.yml:96,129`. Plausibly intentional; flag, do not change.

### O7 — LOW · `secure_runner` host-path `chdir` footgun — unchanged

### O8 — INFO · scheduler `_mark_ran`-before-run — unchanged (behavior change → out of DOC-ONLY)

### O9-NEW — INFO · Sprint-27 introduced **no new ops risk** (verified)

- **`dashboard_nav.py` import safety:** the new helper imports **only**
  `from typing import Tuple` — zero streamlit/engine/network import at
  module load. It **cannot** break the dashboard container's import path
  or add a runtime dependency. `dashboard.py` now also imports
  `account_state` + `dashboard_nav`; `account_state` was already a live
  dependency of every NAV path, so no new failure surface. **Not a risk.**
- **`sentinel_config.example.json`:** a static committed template; no
  service reads it at runtime (services read the host
  `sentinel_config.json`). It cannot shadow or be mistaken for the live
  file by any service. **Not a risk** — it is the O1 fix, working as
  designed.
- W4c is a read-only byte-identical repo swap; W3 is presentation-only.
  Neither changes a service command, NAV/R math, Docker wiring, or the
  secure-runner. Suite 2088/0, coverage 72.02% ≥ 67%, byte-locked
  baselines untouched (per the W1 / W3W4C IMPL docs).

### Known deferred ADDITION (note, do NOT build) — unchanged

- **Dashboard `:8501` 0.0.0.0 binding, no auth** (`docker-compose.yml:70`
  `8501:8501`; `streamlit run dashboard.py`). Sprint-27 explicitly SKIPPED
  this as a **founder network-boundary / topology decision** (Tailscale /
  LAN acceptance / loopback+tunnel). Recorded, **not built**, candidate
  for a future governed Phase. This remains the *deferred-feature*
  boundary, not a regression.

---

## Verified OK (closure-positive — no action)

- Secure runner wiring intact: `telegram-bot.command:
  python3 telegram_bot_secure_runner.py` (`docker-compose.yml:37`) —
  CLAUDE.md hard constraint satisfied.
- Service commands unchanged for all 6 services; no command regressed.
- The §4b host-safe untrack procedure was **executed for real** and the
  live NAV ($7921.07) survived — empirical, not theoretical, proof.
- Secrets clean: `.env` untracked; `sentinel_config.json` now untracked;
  `risk_monitor_state.json` family untracked; no token/key committed.
- Logging/mem/healthcheck/autoheal posture from Sprint-26 unchanged
  (Sprint-27 did not touch `docker-compose.yml`).

---

## למנכ״ל — בשפה פשוטה

**האם בטוח להריץ עכשיו?** כן. ששת השירותים רצים ותקינים, כל מנגנוני
ההגנה (שומר אדמין, הגבלת קצב, גילוי מקור-נתונים, נעילת DEV_PIN) פעילים.

**האם בטוח עכשיו גם לעשות פריסה מחדש / rollback?** **כן — וזה השינוי
הגדול מספרינט-26.** הסכנה החמורה היחידה שחסמה אותנו (O1) **נסגרה**:
קובץ ה-NAV החי `sentinel_config.json` כבר **לא מנוהל ב-git** (אומת מול
המקור: לא קיים ב-HEAD, מסומן `ignored`, נמחק מהמעקב בקומיט הספרינט).
לכן שום `pull` / `checkout` / `revert` / `reset` **לא יכול יותר לדרוס
את ה-NAV החי**. הפריסה האמיתית של ספרינט-27 הוכיחה זאת בשטח —
ה-NAV $7921.07 שרד את כל התהליך. נוסף קובץ דוגמה, ספר הנהלים קיבל נוהל
§4b בטוח, ו-`git reset --hard` נאסר במפורש.

**מה עדיין נשאר (לא חוסם, אבל לתקן):**
1. ההוצאה מ-git **עובדת אבל לא שמורה בבדיקה אוטומטית** — אם מישהו
   בעתיד יריץ `git add -f` או "יתקן" את `.gitignore`, ה-NAV יחזור
   להיות מנוהל ב-git בשקט וה-O1 ייפתח מחדש. אין היום טסט שיתפוס את זה
   (לקובץ פחות-קריטי דווקא יש). **זו הסכנה התפעולית המשמעותית
   ביותר שנותרה.**
2. גרסת Python ב-CI (3.11) עדיין שונה מהייצור (3.10) — באג יכול לעבור
   ב-CI ולשבור את הקופסה רק בפריסה.
3. `autoheal` עדיין על `:latest`, ו-`deploy_watcher.sh` עדיין דורש
   טוגל ידני של `core.fileMode`. כולם פריטים ישנים, לא נגעו בהם
   בספרינט-27.

**שורה תחתונה:** בטוח להריץ; **בטוח גם לפרוס מחדש ולחזור אחורה** בנוהל
המתועד. לא 100/100 — נשאר MEDIUM אחד חדש (חוסר טסט-שמירה על ההוצאה
מ-git) + הפריטים הישנים O3–O8 שלא בתחום הספרינט.

## מה צריך לעשות

1. **(הסיכון הגדול ביותר שנותר) להוסיף טסט-שמירה ל-O1:** טסט בן שורה
   אחת שמוודא ש-`sentinel_config.json` **לא** ב-`git ls-files`, **כן**
   מוחזר מ-`git check-ignore`, ושהשורה קיימת ב-`.gitignore` — בדיוק
   כמו הטסט שכבר קיים ל-`risk_monitor_state.json` (ספרינט-14). כך
   re-track עתידי ייפול ב-CI בקול רם במקום לפתוח מחדש את O1 בשקט.
   (שינוי טסט בלבד → Phase מבוקר; לא נבנה כאן.)
2. **לעולם לא** להריץ `git reset --hard` / `git checkout .` בשרת
   הייצור — וגם עכשיו תמיד `cp -a sentinel_config.json /tmp/nav_live.bak`
   לפני כל פעולת היסטוריה (כתוב נכון ב-§4b/§5 — לאכוף).
3. לקבע גרסת Python ב-CI ל-3.10 (או מטריצה 3.10+3.11) — O5, פתוח.
4. לקבע גרסת `autoheal` (לא `:latest`) — O4.
5. החלטת מנכ"ל נפרדת: גבול הרשת של הדאשבורד ב-`:8501` (loopback+מנהרה /
   Tailscale / auth-proxy). לא נבנה — החלטת טופולוגיה.

---

**Bottom line:** Sprint-27 W2 did exactly what Sprint-26 O1 demanded, and
the real deploy proved it: `sentinel_config.json` is verifiably untracked +
gitignored at `168aaa2`, the §4b host-safe procedure is correct and was
executed with the live NAV ($7921.07) intact, `reset --hard` is forbidden
(O1+O2 CLOSED). Verdict: **safe to run AND safe to redeploy/rollback by the
documented procedure** — but **NOT 100/100**: the single biggest residual
ops hazard is that the untrack has **no regression guard** (a future
`git add -f` / `.gitignore` edit could silently re-track the live NAV and
re-open O1 — add the one-line ls-files/check-ignore guard test, mirroring
the existing Sprint-14 precedent). Pre-existing O3–O8 unchanged (out of
Sprint-27 scope). No code touched this sprint.
