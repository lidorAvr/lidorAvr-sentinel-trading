# DEPLOYMENT RUNBOOK — Sprint-25 + Phases C2/B3/Arch-F1/Engine-P2P3/NAV-Unify

**Branch:** `claude/review-system-audit-FBZ2h` → merge to `main`. **Head:** `5a0f2cb`.
**Prepared by parent (governed).** Production wiring: `docker-compose.yml` (`sentinel-bot`=`main.py`, `telegram-bot`=`telegram_bot_secure_runner.py`), `volumes: .:/app` ⇒ the running code IS the host's checked-out repo. Deploy = bring approved code to `main`, `git pull` on the host, recreate containers.

---

## 0. ⚠️ BLOCKING PREREQUISITES (verify BEFORE deploy)

0. **Dashboard :8501 — ACCEPTED network-boundary control (DEC-20260518-001).** The dashboard has no in-app auth + a Supabase WRITE tab; founder consciously accepts this ONLY because :8501 is reachable solely over Tailscale (Orange-Pi tailnet addr `100.87.116.60`) / internal LAN — never the public internet. Before/after any deploy do NOT publish `8501` beyond the host's Tailscale/LAN boundary; if that boundary ever changes, in-app auth must be scheduled first.
1. **`DEV_PIN` MUST be set in the production `.env`.** Phase C1 made the dev-PIN gate **fail-CLOSED**. Without `DEV_PIN`, after deploy the ENTIRE dev menu — incl. **Git Pull+Deploy**, IBKR sync, XML upload, config dump, on-demand reports — is DENIED. (Self-lockout risk if you deploy via the in-bot button without `DEV_PIN`.) → On the host: `grep -q '^DEV_PIN=' .env || echo 'ADD DEV_PIN=<pin> TO .env FIRST'`.
2. **`sentinel_config.json` on the host must hold a real `nav`** (not an explicit `nav: 0`). NAV-Unify D1 (founder-approved canonical) makes an explicit `0` size `acc_size=0`/`target_risk=0` for bot+risk-monitor. → `python3 -c "import json;d=json.load(open('sentinel_config.json'));print('nav=',d.get('nav'))"` — confirm non-zero.
3. CI green on `5a0f2cb` (same `pytest --cov-fail-under=67` command verified locally post-commit on a clean tree for every phase).
4. No dependency change in any phase → no image rebuild strictly required, but a clean `build` is safest.

## 1. Merge to main

```bash
# PR claude/review-system-audit-FBZ2h -> main (review, then):
# (squash or merge per repo convention)
```

## 2. Deploy on the production host (founder action — host shell, NOT the in-bot button for the first deploy)

```bash
cd /path/to/lidorAvr-sentinel-trading
# 0. prerequisites
grep -q '^DEV_PIN=' .env && echo "DEV_PIN ok" || { echo "STOP: set DEV_PIN in .env"; exit 1; }
python3 -c "import json,sys;d=json.load(open('sentinel_config.json'));sys.exit(0 if d.get('nav') else 1)" && echo "nav ok" || echo "WARN: check sentinel_config.json nav"
# 1. snapshot current prod ref for rollback
git rev-parse HEAD > /tmp/sentinel_prev_ref.txt && cat /tmp/sentinel_prev_ref.txt
# 2. bring the code. Production tracks `claude/review-system-audit-FBZ2h`
#    (NOT main) — deploy = fast-forward THAT branch (no branch switch; avoids
#    clobbering the live, runtime-updated sentinel_config.json). One-time:
#    `git config core.fileMode false` (neutralises the deploy_watcher.sh exec-bit
#    friction). If instead deploying via main, merge the PR first.
git config core.fileMode false
git fetch origin && git pull --ff-only origin claude/review-system-audit-FBZ2h
# 3. recreate. CRITICAL: the `.:/app` volume updates the FILES, but a
#    long-running Python process does NOT reload modules — it keeps executing
#    the OLD code until the container is recreated. The changes span
#    reporting-service (B1, report pipeline) + risk-monitor (Arch-F1, C2,
#    NAV-Unify) too — recreate ALL affected services, not just the bots:
docker compose build
docker compose up -d --force-recreate sentinel-bot telegram-bot reporting-service risk-monitor dashboard
# (or simply: docker compose up -d --force-recreate   # whole stack — safest)
# 4. health
docker compose ps
docker compose logs --tail=80 sentinel-bot telegram-bot reporting-service risk-monitor
```

## 3. Post-deploy verification (within ~30–60 min)

- `docker compose ps` → **all** of `sentinel-bot` / `telegram-bot` / `reporting-service` / `risk-monitor` / `dashboard` show a fresh `CREATED` time and become `(healthy)` (sentinel-bot healthcheck: `/app/state/sentinel_bot_last_cycle` fresh < 1980s). Any service still showing the OLD uptime was NOT recreated → its behavior changes are NOT live.
- Run the post-deploy NAV check (proves the new code is the running code): `python3 -c "import account_state as a;c=a._resolve_nav_core();print(c['nav'],c['freshness'],c['ok'])"` — must NOT raise `AttributeError`.
- Dev menu: tapping a dev button **requires an active PIN session** (C1) — confirm it prompts/denies without a session and works WITH one.
- A scheduled/on-demand report renders; the Telegram summary shows a NAV freshness/source line and (if a price was non-live) the `⚠️ מחיר לא חי` disclosure (B1).
- No new error spam in `risk_monitor` logs (Arch-F1/NAV-Unify edges).

## 4. Behavior changes that go LIVE (watch these)

| Change | Live effect |
|---|---|
| **C1** dev-PIN fail-closed | every privileged dev handler requires an active PIN; unset `DEV_PIN` ⇒ all denied |
| **C2** SELL/BUY by `side` string | a broker SELL exported with positive `quantity` now closes the campaign correctly (heat/streak/WR/open-book) |
| **B3** Add-On race | `/addon` confirm refuses (no Supabase write) if the symbol's open campaign changed since planning |
| **B1** fallback honesty | NAV source/freshness + price-fallback disclosure lines appear when data is stale/fallback (broker-fresh path unchanged) |
| **Engine F4** | duplicate `trade_id` rows no longer double-count realized PnL/R |
| **Engine F5** | a campaign with exactly 1% residual stays OPEN (was falsely closed) |
| **NAV-Unify D1–D4** | bot/risk-monitor NAV edges now match the report pipeline (D1 `nav:0`→sized 0; D2 24/48h strict-`<`; D3/D4 `is_critical` True→False) |

**Byte-identical (no change):** the LOCKED April regression (8/+$180.49/WR .375/PF 2.6262/excl 2), Sprint-22 tz numbers, Sprint-23 probe loss-free, every report-pipeline number on the normal broker-fresh path.

## 4b. ONE-TIME host migration — untrack the live NAV config (Sprint-27 W2 / Ops O1) — DO THIS BEFORE the pull that lands the untrack commit

`sentinel_config.json` was git-tracked while holding the LIVE IBKR NAV. Sprint-27 untracks it in the repo (now `.gitignore`d) + adds `sentinel_config.example.json`. On the host, the FIRST pull that includes the untrack commit must NOT delete/clobber the live file. Run on the host, ONCE, before that pull:

```bash
cd ~/sentinel_trading
cp -a sentinel_config.json /tmp/nav_live.bak           # 1. backup the LIVE NAV
python3 -c "import json;print('backup nav=',json.load(open('/tmp/nav_live.bak')).get('nav'))"
git rm --cached sentinel_config.json                   # 2. untrack locally too (keeps the file)
git pull --ff-only origin claude/review-system-audit-FBZ2h   # 3. now the untrack commit applies cleanly; the file is untracked+gitignored → never touched
python3 -c "import json;print('live nav after pull=',json.load(open('sentinel_config.json')).get('nav'))"   # 4. MUST equal the backup; if missing: cp /tmp/nav_live.bak sentinel_config.json
docker compose up -d --force-recreate                  # 5. then the normal recreate-all
```

From here on `sentinel_config.json` is host-managed (like `.env`). **NEVER run `git reset --hard` or `git checkout .` on the prod host** — they ignore `.gitignore` for the working tree only for *tracked* files, but a hard reset to an old ref + a stale tracked copy elsewhere can still surprise; treat the live NAV as sacred and always `cp` it aside before any history operation.

## 4c. F-YTD pre-deploy disclaimer CLI (founder workflow, host-side)

After Sentinel deployment the Supabase `trades` table is YTD-bound:
pre-deploy closed campaigns have no rows. The raw broker-reconciliation
gap is therefore OVERSTATED by the missing pre-deploy realized PnL
(`docs/DATA_CONTRACTS.md` §"Data history scope"). The founder can
manually estimate the missing PnL and set it once via the CLI; the
classifier subtracts it from the raw gap before banding so future
`/portfolio` refreshes show the residual.

**Sign convention (match the disclaimer to the gap's direction):**
- Positive raw gap (NAV > expected, pre-deploy GAIN absent from DB) →
  positive estimate (e.g. `+495.67` zeros a `+$495.67` raw gap; this
  is the 21/05/2026 founder case).
- Negative raw gap (NAV < expected, pre-deploy LOSS absent from DB) →
  negative estimate.
- Same direction. If signs don't match, the breakdown line will show a
  *larger* residual than the raw gap — that's the operator's signal to
  flip the sign.

**Invocation (host shell, NOT in the in-bot dev menu):**

```bash
cd ~/sentinel_trading

# 1. show current value + reference fields
python3 scripts/set_pre_db_pnl_estimate.py --show

# 2. set the estimate to neutralise the current raw gap
python3 scripts/set_pre_db_pnl_estimate.py 495.67       # positive: pre-deploy gain
# OR
python3 scripts/set_pre_db_pnl_estimate.py -- -200.50   # negative: pre-deploy loss
#                                            ^^ note `--` to stop argparse from
#                                               eating the leading minus sign

# 3. clear (returns to default-0; raw gap surfaces unmodified)
python3 scripts/set_pre_db_pnl_estimate.py --clear
```

**If invoked from a different CWD or inside docker exec**, point at
the config explicitly:

```bash
SENTINEL_CONFIG_PATH=/app/sentinel_config.json \
  docker compose exec -T sentinel-bot \
  python3 /app/scripts/set_pre_db_pnl_estimate.py --show
```

**Atomicity.** The CLI writes via a temp file at mode 0o600 in the
same directory as the target, then `os.replace`s it onto the live
config — atomic on POSIX (same filesystem), crash-safe under the
`.:/app` bind mount. The live `sentinel_config.json` is `.gitignore`d
(Sprint-27 W2/O1) so this never collides with `git pull`.

**Effect (live, no service restart needed).** On the next
`/portfolio` refresh, the recon line either:
- shows the *softened* clean variant ("מאוזן ✅ אחרי הצהרת היסטוריה
  לפני-DB ($X.XX: גולמי $Y.YY → מותאם $Z.ZZ)") if the residual fell
  below Critical, or
- keeps Mark §3 verbatim wording for the *residual* + appends the
  disclaimer disclosure if the residual is still Critical.

**Audit.** The CLI prints a before/after diff to stdout; the value
lives only in `sentinel_config.json` (not in Supabase or Git). To
review the operator's last set, run `--show` again.

## 5. Rollback (from docs/SAFE_CHANGE_PROTOCOL.md)

```bash
cp -a sentinel_config.json /tmp/nav_live.bak           # ALWAYS back up the live NAV first
docker compose stop telegram-bot sentinel-bot
git checkout "$(cat /tmp/sentinel_prev_ref.txt)"       # the pre-deploy ref (post-W2 this no longer touches sentinel_config.json — it is untracked)
python3 -c "import json;print(json.load(open('sentinel_config.json')).get('nav'))" || cp /tmp/nav_live.bak sentinel_config.json
docker compose up -d --force-recreate sentinel-bot telegram-bot
docker compose logs --tail=80 telegram-bot
```

⚠️ Do NOT use `git reset --hard`/`git checkout .` on the prod host. Post-W2 `sentinel_config.json` is untracked so a normal `git checkout <ref>` no longer reverts the live NAV — but always keep the `/tmp/nav_live.bak` safety copy. Report numbers are byte-identical pre/post, so rollback never changes report output. The byte-lock baselines + governed allowlists are test-only (no runtime effect).
