# Sprint 13 — Architecture + Infra Design

**Team:** 🏗️ Architecture + 🛠️ Infra (combined)
**Date:** 2026-05-15
**Branch:** `claude/review-system-audit-FBZ2h`
**Status:** Wave-1 design — **doc-only, no code/script/compose change applied.**
**Gates:** Wave-2 build is blocked until Mark's `MARK_SPRINT13_RULINGS.md` lands
and the parent checkpoint releases it. Mark's file was **absent** when this was
authored (parallel team) — every methodology/sequence decision below is a
**verbatim `⟨MARK: …⟩` slot**. Engineering invents none of them.

## Scope inputs (read)

- `docs/teams/SPRINT13_PLAN.md` — Wave-1 task split, integration note (`:30-31`).
- `docs/DECISIONS.md` — **DEC-20260512-005** (explicit per-service
  `dns: [8.8.8.8, 1.1.1.1]`; the prior network decision — still in force,
  `docker-compose.yml:12-14,43-45,73-75,103-105,136-138`).
- `CLAUDE.md` — `docker-compose.yml` service `command:` = most-fragile
  production wiring; `telegram_bot_secure_runner.py` intentional; no app/risk/
  NAV/campaign math change.
- `AGENTS.md` — #1 (no fallback/stale-as-truth), #8 (no DATA_INCOMPLETE/ALGO in
  stats), Red Lines `:65-73`.
- `docs/teams/MARK_SPRINT12_RULINGS.md` §4 (`:277-305`) — the **prior**
  missing-stops ruling (notice-only). Sprint 13 explicitly re-opens this
  (`SPRINT13_PLAN.md:11,18`); recorded here as the **methodology-safe default**
  pending Mark's Sprint-13 re-ruling.
- Infra: `deploy_watcher.sh` (full, `:1-49`), `deploy-watcher.service`
  (`:1-19`), `docker-compose.yml` (full).
- Surfaces: `bot_health.py:72-102` (Sprint-12 missing-stops notice),
  `telegram_backlog.py` (journal completion), `open_tasks.py`
  (`DATA_INCOMPLETE`/`COMPLETE_RISK_DATA` shape, `:271-281`),
  `supabase_repository.py:11-19,30-40` (`_INCOMPLETE_TRADES_QUERY`).

---

## 0. ⟨MARK⟩ slot register (fill from `MARK_SPRINT13_RULINGS.md`; do not invent)

| Slot | Decision Mark must rule | Engineering default if Mark unavailable |
|---|---|---|
| `⟨MARK:DEPLOY_SEQ⟩` | The exact compose deploy sequence: `down && up -d --build` **vs** `up -d --build --force-recreate` **vs** `up -d --build` + targeted `docker network` recreate. | **Block Wave-2** — no infra change ships without this. |
| `⟨MARK:DOWN_TIMEOUT⟩` | `down` stop-grace (`-t` seconds) acceptable for a single-admin bot. | Block. |
| `⟨MARK:PROBE_HOST⟩` | Connectivity-probe target host. | `api.telegram.org` (the bot's only hard external dependency; recorded, not authoritative). |
| `⟨MARK:PROBE_TIMEOUT⟩` | Probe socket timeout (s) + total probe budget. | Block. |
| `⟨MARK:RETRY_POLICY⟩` | On probe fail: retry-once form (`down && up -d` network-recreate vs `restart telegram-bot`) and whether a 2nd failure escalates. | Block. |
| `⟨MARK:SURFACE_RULING⟩` | Missing-stops: **notice-only** (re-affirm S12 §4) **vs** **actionable surface** into journal-backlog/Open Tasks **vs** **legacy-classify**. | **Notice-only** (verbatim S12 `MARK_SPRINT12_RULINGS.md` §4 `:283-305`). |
| `⟨MARK:ROUTING_SPLIT⟩` | *If* actionable: the open-position-missing-stop (urgent) vs old-closed-legacy (hygiene) split rule + which existing surface each routes to. | N/A unless `⟨MARK:SURFACE_RULING⟩` = actionable. |
| `⟨MARK:VERIFY_GATE⟩` | The pass/fail bar for the manual host verification checklist. | Block host install until ruled. |

---

## 1. `deploy_watcher.sh` change design

### 1.1 Problem (live finding #1, `SPRINT13_PLAN.md:10`)

`deploy_watcher.sh:36-45` runs `git pull` then `docker compose up -d --build`
with **no `down`**. A live `--build` deploy left the `telegram-bot` container
with no egress (`[Errno 101] Network is unreachable`) while host + DNS were
healthy; `docker compose down && up -d` (Docker network recreate) fixed it.
Because the watcher never `down`s, every future button-deploy can recur this,
and the script does **not notice** — it logs "Deploy complete." on a dead bot.

Two defects: (a) no network recreate; (b) **no post-deploy proof the bot can
reach Telegram** — a silent-dead-bot blind spot (violates AGENTS.md #1 spirit:
do not present a broken deploy as success).

### 1.2 Design constraints (hard)

- **MUST NOT** modify `docker-compose.yml` — service `command:` for
  `telegram-bot` stays `python3 telegram_bot_secure_runner.py`
  (`docker-compose.yml:37`; CLAUDE.md hard constraint; AGENTS.md #3). The probe
  uses `docker compose exec`, never edits the compose file or the entrypoint.
- **No `curl`/`wget` in the image** (python:3.10-slim, see
  `DEC-20260510-001`). The probe is `docker compose exec -T telegram-bot
  python3 -c …` (stdlib `socket`, IPv4-pinned), matching the existing in-image
  Python-only healthcheck idiom (`docker-compose.yml:58`).
- Conservative: the new sequence is **exactly `⟨MARK:DEPLOY_SEQ⟩`** — not an
  engineering choice. Diff rationale below is written against the two candidate
  forms Mark is choosing between; the doc ships the chosen one verbatim.
- Self-hot-swap is unsafe: a running watcher cannot replace the very script
  executing the deploy mid-loop. Install is a **manual one-time host step**
  (`SPRINT13_PLAN.md:30-31`; §1.5).
- Probe failure **never** silently leaves a dead bot: log to `$LOG`, retry once
  per `⟨MARK:RETRY_POLICY⟩`, and **surface** (a durable, greppable
  `DEPLOY-ALERT` line in `$LOG` + a sentinel file the existing
  `bot_health.py`/operator can see — no new Telegram push path added by the
  host script; AGENTS.md #7).

### 1.3 Proposed full new `deploy_watcher.sh` (NOT applied — doc artifact)

`⟨MARK:DEPLOY_SEQ⟩` and `⟨MARK:DOWN_TIMEOUT⟩`/`⟨MARK:PROBE_*⟩`/
`⟨MARK:RETRY_POLICY⟩` placeholders are **literal** until Mark rules. Wave-2
substitutes Mark's verbatim values, changes nothing else.

```bash
#!/usr/bin/env bash
# deploy_watcher.sh — runs on the Orange Pi HOST (not inside Docker).
# Watches for /deploy_trigger file written by the Telegram bot,
# then pulls latest code, recreates containers, and verifies the
# telegram-bot container has working IPv4 egress to Telegram.
#
# Setup (one-time, via SSH) — see SPRINT13_DESIGN.md §1.5:
#   chmod +x ~/sentinel_trading/deploy_watcher.sh
#   sudo cp ~/sentinel_trading/deploy-watcher.service /etc/systemd/system/
#   sudo systemctl daemon-reload
#   sudo systemctl restart deploy-watcher   # re-read the new script
#
# Check status:
#   sudo systemctl status deploy-watcher
#   journalctl -u deploy-watcher -f
#   grep DEPLOY-ALERT ~/sentinel_trading/deploy_watcher.log

set -o pipefail

SENTINEL_DIR="${SENTINEL_DIR:-$HOME/sentinel_trading}"
TRIGGER="$SENTINEL_DIR/deploy_trigger"
LOG="$SENTINEL_DIR/deploy_watcher.log"
ALERT_FILE="$SENTINEL_DIR/deploy_last_alert"   # surfaced; greppable; not a push
COMPOSE_CMD="docker compose"

# ⟨MARK:DOWN_TIMEOUT⟩  — compose stop-grace seconds (single-admin bot).
DOWN_TIMEOUT="⟨MARK:DOWN_TIMEOUT⟩"
# ⟨MARK:PROBE_HOST⟩    — connectivity-probe target (default api.telegram.org).
PROBE_HOST="⟨MARK:PROBE_HOST⟩"
# ⟨MARK:PROBE_TIMEOUT⟩ — per-attempt socket timeout seconds.
PROBE_TIMEOUT="⟨MARK:PROBE_TIMEOUT⟩"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"
}

# Durable, greppable surface for a failed/at-risk deploy. NOT a Telegram push
# (AGENTS.md #7 — the host script adds no push path). The existing
# bot_health.py / operator reads this; the line is unmistakable in $LOG.
alert() {
    log "DEPLOY-ALERT: $*"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" > "$ALERT_FILE"
}

# Post-deploy connectivity self-check. No curl in the image (python:3.10-slim)
# — stdlib socket only, IPv4-pinned (AF_INET), matching the in-image
# Python-only healthcheck idiom (docker-compose.yml:58). Proves the
# telegram-bot CONTAINER (not the host) can open a TCP/443 IPv4 route to
# Telegram. Returns 0 = reachable, non-0 = unreachable.
probe_telegram() {
    $COMPOSE_CMD exec -T telegram-bot python3 -c "
import socket, sys
host, port, t = '$PROBE_HOST', 443, float('$PROBE_TIMEOUT')
try:
    # AF_INET = force IPv4 (the live failure was an IPv4 route loss; an
    # IPv6 fallback could mask it). getaddrinfo+connect, no payload.
    infos = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(t)
    s.connect(infos[0][4])
    s.close()
    sys.exit(0)
except Exception as e:
    print('PROBE_FAIL:', type(e).__name__, e, file=sys.stderr)
    sys.exit(1)
" >> "$LOG" 2>&1
}

log "deploy_watcher started. Watching: $TRIGGER"

while true; do
    if [ -f "$TRIGGER" ]; then
        WRITTEN=$(cat "$TRIGGER" 2>/dev/null || echo "?")
        rm -f "$TRIGGER"
        log "Trigger detected (ts=$WRITTEN). Starting deploy..."

        cd "$SENTINEL_DIR" || { log "ERROR: cannot cd to $SENTINEL_DIR"; sleep 10; continue; }

        log "Running: git pull"
        if ! git pull >> "$LOG" 2>&1; then
            alert "git pull failed — skipping docker compose. Bot UNCHANGED."
            sleep 5
            continue
        fi
        log "git pull OK."

        # ⟨MARK:DEPLOY_SEQ⟩ — the EXACT new sequence. One of:
        #   (A) $COMPOSE_CMD down -t "$DOWN_TIMEOUT" && \
        #       $COMPOSE_CMD up -d --build
        #   (B) $COMPOSE_CMD up -d --build --force-recreate
        # Substitute Mark's chosen form VERBATIM here (changes nothing else).
        log "Rebuilding containers (⟨MARK:DEPLOY_SEQ⟩)..."
        if ! ⟨MARK:DEPLOY_SEQ⟩ >> "$LOG" 2>&1; then
            alert "docker compose deploy failed. Bot state UNKNOWN — INVESTIGATE."
            sleep 5
            continue
        fi
        log "Containers up. Waiting for telegram-bot start_period before probe..."
        sleep 30   # matches docker-compose.yml:62 start_period

        if probe_telegram; then
            log "Connectivity self-check OK ($PROBE_HOST reachable via IPv4). Deploy complete."
            rm -f "$ALERT_FILE"
        else
            log "Connectivity self-check FAILED. Applying retry (⟨MARK:RETRY_POLICY⟩)..."
            # ⟨MARK:RETRY_POLICY⟩ — retry-once form. One of:
            #   (A) $COMPOSE_CMD down -t "$DOWN_TIMEOUT" && $COMPOSE_CMD up -d
            #       (full Docker-network recreate — matches the live fix)
            #   (B) $COMPOSE_CMD restart telegram-bot
            ⟨MARK:RETRY_POLICY⟩ >> "$LOG" 2>&1
            sleep 30
            if probe_telegram; then
                log "Connectivity recovered after retry. Deploy complete (post-retry)."
                rm -f "$ALERT_FILE"
            else
                alert "telegram-bot has NO Telegram egress after deploy + retry. \
DEAD BOT — manual intervention required (see SPRINT13_DESIGN.md §1.6)."
            fi
        fi
    fi
    sleep 5
done
```

### 1.4 Line-by-line diff rationale (vs current `deploy_watcher.sh:1-49`)

| Change | Old | New | Why |
|---|---|---|---|
| `set -o pipefail` | absent | added | `git pull \| tee` / `compose \| tee` must fail the step if the left side fails — current code's `if git pull >> "$LOG"` is fine but the probe pipeline relies on it. Conservative; no behavior change to the happy path. |
| `ALERT_FILE` + `alert()` | none | added | Surface a failed/at-risk deploy durably & greppably. **No Telegram push** from the host script (AGENTS.md #7 — push stays `risk_monitor.py`). `bot_health.py`/operator reads `$LOG`/file. |
| `git pull` failure | `log "ERROR…"` then loop | `alert(…)`; explicit "Bot UNCHANGED" | Old wording buried a real failure as a normal log line; new `DEPLOY-ALERT` is unmistakable and states the bot is safe (unchanged). |
| deploy step | `up -d --build` only | `⟨MARK:DEPLOY_SEQ⟩` (down+up **or** force-recreate) | Root-cause fix for finding #1 (stale Docker network). **Mark-ruled**, not engineering-chosen. |
| post-deploy verify | none | `sleep 30` (start_period) + `probe_telegram` | Closes the silent-dead-bot blind spot — proves the *container* has IPv4 egress, not just that compose returned 0. |
| probe mechanism | n/a | `compose exec -T … python3 -c "socket…"` | No curl in slim image; IPv4-pinned (`AF_INET`) because the live failure was an IPv4 route loss; mirrors the in-image Python-only healthcheck idiom. **Does not touch the entrypoint/`command:`.** |
| failure action | `log "ERROR"`, continue | retry once (`⟨MARK:RETRY_POLICY⟩`), re-probe, else `DEPLOY-ALERT` "DEAD BOT" | Never silently leave a dead bot. Retry form is Mark-ruled (full network recreate vs container restart). |
| "Deploy complete." | unconditional after `up` | only after a **passing probe** | Old code lied — logged success on a dead bot. Now success ⇒ verified egress. |
| service-command edits | — | **none** | Hard constraint: `docker-compose.yml:37` `command: python3 telegram_bot_secure_runner.py` untouched; probe is exec-only. |

### 1.5 Manual one-time host install procedure

The watcher cannot hot-swap the script it is mid-deploy in
(`SPRINT13_PLAN.md:30-31`). One-time, via SSH on the Orange Pi:

1. Confirm the updated `deploy_watcher.sh` is on disk (post-`git pull`):
   `sha256sum ~/sentinel_trading/deploy_watcher.sh` — compare to the value
   recorded by Wave-2 / the PR.
2. **Ensure no deploy is in flight:** `tail -n 5
   ~/sentinel_trading/deploy_watcher.log` shows the last line is a terminal
   state (`Deploy complete.` / `DEPLOY-ALERT` / idle), not "Starting deploy".
3. `chmod +x ~/sentinel_trading/deploy_watcher.sh`
4. `sudo systemctl restart deploy-watcher` (NOT `daemon-reload` alone —
   `Type=simple`/`ExecStart` re-execs the file; `deploy-watcher.service` is
   **unchanged**, so no `daemon-reload` is needed unless the unit file itself
   changed — it does not in Sprint 13).
5. Verify it re-read the new file:
   `journalctl -u deploy-watcher -n 10 --no-pager` → expect the new
   `deploy_watcher started.` banner.

#### Rollback (host)

1. `git -C ~/sentinel_trading checkout -- deploy_watcher.sh` (or
   `git checkout <prev_sha> -- deploy_watcher.sh`) to restore the
   `:1-49` version.
2. `chmod +x` then `sudo systemctl restart deploy-watcher`.
3. Confirm via `journalctl -u deploy-watcher -n 5`.
4. Rollback is **safe at any time** — the old script is purely a `git
   pull && up -d --build` loop with no new state; the only artifact the new
   script creates is `deploy_last_alert`, which the old script ignores (delete
   it manually if desired: `rm -f ~/sentinel_trading/deploy_last_alert`).

### 1.6 Manual verification checklist (bash on host — NOT unit-testable)

This is host bash invoked by systemd; there is no Python import seam, so it is
**manual-only**. The bar is `⟨MARK:VERIFY_GATE⟩`. Human steps, run on the Pi
after install, in a low-risk window:

- [ ] **V1 — happy path.** `touch ~/sentinel_trading/deploy_trigger`; watch
  `journalctl -u deploy-watcher -f`. Expect: `Trigger detected` →
  `git pull OK` → `Rebuilding…` → `Containers up` → `sleep 30` →
  `Connectivity self-check OK` → `Deploy complete.` No `DEPLOY-ALERT`.
- [ ] **V2 — bot actually reachable.** Within ~1 min of V2, send `/portfolio`
  in Telegram; the bot replies (proves egress is real, not just a TCP handshake
  artifact).
- [ ] **V3 — probe true-negative (simulated outage).** Temporarily block the
  container's egress (e.g. detach its network or a host firewall rule for the
  test), trigger a deploy. Expect: `Connectivity self-check FAILED` →
  retry (`⟨MARK:RETRY_POLICY⟩`) → on still-fail, a single
  `DEPLOY-ALERT: … DEAD BOT …` line in `$LOG` and a populated
  `deploy_last_alert`. Restore egress; trigger again; expect clean success and
  `deploy_last_alert` removed.
- [ ] **V4 — `git pull` failure path.** Create a local uncommitted conflict so
  `git pull` fails; trigger. Expect `DEPLOY-ALERT: git pull failed — … Bot
  UNCHANGED.` and the bot **still answering** `/portfolio` (proves a failed
  pull does not touch a healthy bot).
- [ ] **V5 — service-command untouched.** `docker inspect telegram-bot
  --format '{{.Config.Cmd}}'` shows `telegram_bot_secure_runner.py`
  (CLAUDE.md hard constraint held; secure_runner not bypassed).
- [ ] **V6 — DEC-20260512-005 intact.** `docker inspect telegram-bot
  --format '{{.HostConfig.Dns}}'` still lists `8.8.8.8 1.1.1.1` after the new
  sequence (the per-service `dns:` survives `down`/`force-recreate`).
- [ ] **V7 — no self-hot-swap.** Confirm the install was done while idle (§1.5
  step 2) and the running PID corresponds to the new file
  (`sudo systemctl show -p MainPID deploy-watcher`; `ls -l /proc/<pid>/exe`
  is bash; the script path is the unit's `ExecStart`).
- [ ] **V8 — rollback rehearsed.** Perform §1.5 Rollback once on a non-deploy
  window; confirm the old banner returns and a `touch` trigger still deploys
  (old behavior). Re-apply the new script.

---

## 2. Missing-stops surface design (per Mark)

### 2.1 The data (live finding #2, `SPRINT13_PLAN.md:11`)

`bot_health.py:72-102` already detects **55 rows** (MSGE, SNEX, TSLA, JPM, HP)
where `side==BUY`, `quantity>0`, `stop_loss<=0`. Sprint 12 added a
**non-numeric notice only** there (`bot_health.py:86-98`), per Mark S12 §4
(`MARK_SPRINT12_RULINGS.md:283-305`).

### 2.2 Decision point — `⟨MARK:SURFACE_RULING⟩`

Sprint 13 explicitly re-opens this (`SPRINT13_PLAN.md:11,18`). **Engineering
proposes nothing new** — it implements exactly one of Mark's three options:

#### Option A — notice-only (S12 §4 re-affirmed; engineering default)

No change beyond what already ships. `bot_health.py:86-98` stays the single
honest, non-numeric, never-counted, no-fabricated-stop readout (the exact
`DATA_INCOMPLETE` shape, `open_tasks.py:271-281`). **If Mark rules notice-only,
this section ends here — nothing else is built (`SPRINT13_PLAN.md` "If Mark
rules notice-only, document that and stop").**

#### Option B — actionable surface (only if `⟨MARK:SURFACE_RULING⟩` = actionable)

Route the 55 rows into the **existing** journal-backlog / Open Tasks contracts
— **no migration, no new table, no fabricated stop, never a stat**. The split
is Mark-ruled via `⟨MARK:ROUTING_SPLIT⟩`. The engineering-feasible mapping
(presented for Mark to ratify, not as a decision):

- **Open-position-missing-stop = urgent real risk.** A row whose `campaign_id`
  is a *currently-open* campaign (`engine_core.get_open_positions_campaign`,
  `engine_core.py:473-514`: `campaign_id NOT NULL` and `net_qty > 0.001`) and
  whose BUY leg has `stop_loss<=0`. This is precisely the engine's existing
  `POSITION_STATE_DATA_INCOMPLETE` → `COMPLETE_RISK_DATA` task
  (`open_tasks.py:273-280`): `urgency=None`, `info_only=True`, **never counted**
  (AGENTS.md #8), Hebrew is the verbatim ruleset string "‏⚠️ נתוני סיכון חסרים
  — השלם entry/stop כדי שהפוזיציה תיכלל." **No new task type, no new ruleset
  key** (would break the `test_ruleset_matches_methodology_spec` drift test —
  `open_tasks.py:194-205`). It surfaces only because the engine already
  classifies that open position as `DATA_INCOMPLETE`; this design **adds no
  derivation** — it confirms the existing path already covers open positions
  and requires **zero code** beyond ensuring the open-position pipeline feeds
  `derive_tasks` (it already does).

- **Old-closed-legacy = hygiene.** A row whose campaign is *closed*
  (`net_qty <= 0.001`) or `setup_type=='Legacy'` — `telegram_backlog.py:19-20`
  already **skips `Legacy`**, and a closed campaign is not an open position so
  it never reaches Open Tasks. These stay in the **`bot_health.py` notice**
  exactly as today (count + symbols, non-numeric, never counted). They are
  **not** promoted to an action item — completing the stop on a long-closed
  trade changes no live risk; it is pure data hygiene and Mark S12 §4 already
  ruled that surface notice-only.

  *Net effect of Option B:* the **urgent subset** is already an Open Task via
  the engine's existing `DATA_INCOMPLETE` classification (no new code, no
  migration, reuses `open_tasks.py` contract verbatim); the **legacy subset**
  stays the `bot_health.py` notice. The only Wave-2 work is a **read-only
  reconciliation** that the Health notice's 55-count is split-labelled into
  "X open (already in Open Tasks) / Y legacy (hygiene only)" so the operator
  understands the urgent vs hygiene breakdown — still non-numeric re risk, no
  $/R, no fabricated stop, no stat.

#### Option C — legacy-classify (only if `⟨MARK:SURFACE_RULING⟩` = legacy-classify)

Mark may instead rule that the closed/archived subset be marked
`setup_type='Legacy'` so it drops out of `get_incomplete_trades`
(`supabase_repository.py:11-19` already excludes nothing by `Legacy`, but
`telegram_backlog.py:19-20` skips it) — a **gated, audited, UPDATE-only**
data-hygiene pass reusing the **existing `/clean`-style** confirm+dry-run+audit
pattern (`MARK_SPRINT12_RULINGS.md` §2). This is **out of Sprint-13 automated
scope unless Mark explicitly rules it in** (`SPRINT13_PLAN.md:34` carries broad
backfill out of scope). Engineering does **not** select this.

### 2.3 Invariants honored in every option

- **No fabricated stop, ever** (AGENTS.md #1 / Red Line `:68`;
  `MARK_SPRINT12_RULINGS.md:300-302`). Sentinel never invents/defaults a stop.
- **Never enters WR/Expectancy/PF** (AGENTS.md #8;
  `open_tasks.py:271-281` `urgency=None`/`info_only=True`).
- **No migration, no new table, no new ruleset key** (`SPRINT13_PLAN.md:21,28`;
  Hyperscaler addendum). Reuses `open_tasks` lifecycle + the existing
  `_INCOMPLETE_TRADES_QUERY` / `get_open_positions_campaign` contracts verbatim.
- **No Supabase trade mutation from a read-only flow** (AGENTS.md #4) — Options
  A and B are SELECT-only; Option C (if Mark rules it) is the gated audited
  `/clean`-pattern UPDATE only, never a delete.

---

## 3. Risk classification + "will NOT change" + Wave-2 verification plan

### 3.1 Risk classification (per CLAUDE.md)

| Item | Risk | Affected services | Why |
|---|---|---|---|
| `deploy_watcher.sh` rewrite | **HIGH** | host systemd; transitively every container on each deploy | CLAUDE.md most-fragile (production wiring); a bad sequence can take the bot down. Mitigated: Mark-ruled sequence, conservative diff, post-deploy probe, manual install + rehearsed rollback, V1–V8 verification. |
| Post-deploy connectivity probe | **MEDIUM** | `telegram-bot` (exec only) | `exec -T … python3 -c` is read-only, no payload, no entrypoint change; worst case = a false-negative `DEPLOY-ALERT` (safe — surfaces, never auto-destroys). |
| Missing-stops Option A (notice-only) | **LOW** | none | Zero code change. |
| Missing-stops Option B (actionable) | **LOW–MEDIUM** | `telegram-bot` (Open Tasks render) | Reuses the engine's *existing* `DATA_INCOMPLETE` path + `open_tasks` contract; the only new code is a read-only split-label on the Health notice. No new ruleset key (drift-test-safe by construction). |
| Missing-stops Option C (legacy-classify) | **HIGH** | Supabase `trades` | Trade mutation — only if Mark explicitly rules it in; gated/audited `/clean` pattern, UPDATE-only. Default: **not in scope.** |

### 3.2 Will **NOT** change (explicit)

- `docker-compose.yml` **service `command:`** for any service — `telegram-bot`
  stays `python3 telegram_bot_secure_runner.py` (`:37`). CLAUDE.md hard
  constraint; AGENTS.md #3.
- `telegram_bot_secure_runner.py` — not bypassed, not edited, not removed
  (admin protection + rate-limit, DEC-20260515-009).
- `deploy-watcher.service` — unit file unchanged (no `daemon-reload` needed;
  only the script body changes).
- DEC-20260512-005 per-service `dns: [8.8.8.8,1.1.1.1]` — preserved (V6).
- App / risk / NAV / R-multiple / exposure / campaign / drawdown math — **zero**
  changes (CLAUDE.md; AGENTS.md #2). The probe is `socket`-only; the
  missing-stops work is read-only over existing engine output.
- No new Supabase migration, no new table, no new `open_tasks` ruleset key, no
  threading of `user_id` beyond the existing sentinel (Hyperscaler addendum;
  `SPRINT13_PLAN.md:21,28`).
- No fabricated stop value, no DATA_INCOMPLETE/ALGO row into any stat.

### 3.3 Wave-2 verification plan — testable vs manual-only

**Test-suite-testable (Python; must keep baseline `1609` green,
`SPRINT12_WAVE2_IMPL.md:5,165`):**

- *Only if `⟨MARK:SURFACE_RULING⟩` = Option B:* a unit test for the read-only
  Health-notice **split-label helper** (a pure Python function: given the 55
  detected rows + the open-campaign set, returns
  `(open_count, legacy_count, symbols)` — asserts it never emits a stop number,
  never a $/R, total == 55, and is referentially transparent). Mirrors the
  existing `open_tasks` pure-function test discipline.
- Re-affirm `test_ruleset_matches_methodology_spec` stays green (Option B adds
  **no** `_RULESET` key by construction — `open_tasks.py:194-205`).
- No test is added for Option A (no code) or Option C (out of scope).

**Manual-only (NOT unit-testable — host bash under systemd):**

- The entire `deploy_watcher.sh` change. There is no import seam; it is a
  systemd-run loop with `git`/`docker compose`/`socket` side effects. Verified
  exclusively by the **§1.6 V1–V8** human checklist on the Orange Pi, plus the
  §1.5 install and rehearsed rollback. The bar is `⟨MARK:VERIFY_GATE⟩`.
- The connectivity probe's true-negative behavior (V3) requires deliberately
  breaking container egress on the host — cannot be exercised in CI.

### 3.4 Wave-2 gating

Wave-2 must NOT start until: (a) `MARK_SPRINT13_RULINGS.md` fills every
§0 `⟨MARK⟩` slot; (b) the parent checkpoint verifies the design does not touch
`docker-compose.yml` service commands / secure_runner and that missing-stops
never fabricates (`SPRINT13_PLAN.md:24-25`). The `deploy_watcher.sh` change
takes effect on the Pi **only** after the manual §1.5 host install — Wave-2
delivers the file + this procedure; the host step is operator-run.
