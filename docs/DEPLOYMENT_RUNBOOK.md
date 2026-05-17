# DEPLOYMENT RUNBOOK — Sprint-25 + Phases C2/B3/Arch-F1/Engine-P2P3/NAV-Unify

**Branch:** `claude/review-system-audit-FBZ2h` → merge to `main`. **Head:** `5a0f2cb`.
**Prepared by parent (governed).** Production wiring: `docker-compose.yml` (`sentinel-bot`=`main.py`, `telegram-bot`=`telegram_bot_secure_runner.py`), `volumes: .:/app` ⇒ the running code IS the host's checked-out repo. Deploy = bring approved code to `main`, `git pull` on the host, recreate containers.

---

## 0. ⚠️ BLOCKING PREREQUISITES (verify BEFORE deploy)

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

## 5. Rollback (from docs/SAFE_CHANGE_PROTOCOL.md)

```bash
docker compose stop telegram-bot sentinel-bot
git checkout "$(cat /tmp/sentinel_prev_ref.txt)"   # the pre-deploy ref
docker compose up -d --force-recreate sentinel-bot telegram-bot
docker compose logs --tail=80 telegram-bot
```

Report numbers are byte-identical pre/post, so rollback never changes report output. The byte-lock baselines + governed allowlists are test-only (no runtime effect).
