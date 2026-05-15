#!/usr/bin/env bash
# deploy_watcher.sh — runs on the Orange Pi HOST (not inside Docker).
# Watches for /deploy_trigger file written by the Telegram bot,
# then pulls latest code, recreates containers, and verifies the
# telegram-bot container has working IPv4 egress to Telegram.
#
# Sprint 13 (Mark MARK_SPRINT13_RULINGS.md §1): the deploy command gains
# `--force-recreate` (cures the stale-bridge fault WITHOUT a `down` — a
# `down` would tear the whole network and outage risk-monitor +
# reporting-service + sentinel-bot, rejected by Mark). A mandatory
# post-deploy IPv4 connectivity self-check then proves the telegram-bot
# CONTAINER can reach Telegram; "Deploy complete." is logged ONLY after a
# passing probe — never on a dead bot (AGENTS.md #1).
#
# Setup (one-time, via SSH) — see docs/teams/SPRINT13_WAVE2_IMPL.md §1.3:
#   chmod +x ~/sentinel_trading/deploy_watcher.sh
#   sudo cp ~/sentinel_trading/deploy-watcher.service /etc/systemd/system/
#   sudo systemctl daemon-reload          # only if the UNIT file changed
#   sudo systemctl restart deploy-watcher # re-read the new script
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

# Mark §1: connectivity-probe target is the bot's only hard external
# dependency; per-attempt socket timeout is Mark's literal 10s.
PROBE_HOST="api.telegram.org"
PROBE_TIMEOUT="10"

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

# Post-deploy connectivity self-check (Mark §1 :29-31). No curl in the image
# (python:3.10-slim) — stdlib socket only, IPv4-pinned (AF_INET) because the
# live failure was an IPv4 route loss; mirrors the in-image Python-only
# healthcheck idiom. Proves the telegram-bot CONTAINER (not the host) can
# open a TCP/443 IPv4 route to Telegram. Returns 0 = reachable, non-0 = not.
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

        # Mark §1 RULING (:13-20): change is ONLY adding --force-recreate.
        # `down && up` is explicitly REJECTED (full multi-service outage).
        log "Rebuilding containers (up -d --build --force-recreate)..."
        if ! $COMPOSE_CMD up -d --build --force-recreate >> "$LOG" 2>&1; then
            alert "docker compose deploy failed. Bot state UNKNOWN — INVESTIGATE."
            sleep 5
            continue
        fi
        log "Containers up. Waiting for telegram-bot start_period before probe..."
        sleep 30   # matches docker-compose.yml telegram-bot start_period

        # Mark §1 mandatory post-deploy self-check (:27-35).
        if probe_telegram; then
            log "connectivity OK ($PROBE_HOST reachable via IPv4). Deploy complete."
            rm -f "$ALERT_FILE"
        else
            log "connectivity self-check FAILED — retrying once (Mark §1 :32-33)..."
            # Mark §1 (:32-33): retry ONCE with a single-service force-recreate
            # (NOT `down`, NOT a plain `restart`) — re-attaches only the bot.
            $COMPOSE_CMD up -d --force-recreate telegram-bot >> "$LOG" 2>&1
            sleep 30
            if probe_telegram; then
                log "connectivity OK after retry. Deploy complete (post-retry)."
                rm -f "$ALERT_FILE"
            else
                # Mark §1 (:33-35): log 🔴 ALERT + write the alert sentinel,
                # NEVER a fabricated "deploy OK", never silently leave a dead
                # bot (AGENTS.md #1).
                log "🔴 ALERT: telegram-bot has NO Telegram egress after deploy + retry."
                alert "DEAD BOT — telegram-bot unreachable on $PROBE_HOST:443 (IPv4) after force-recreate + retry. Manual intervention required (docs/teams/SPRINT13_WAVE2_IMPL.md §1.4)."
            fi
        fi
    fi
    sleep 5
done
