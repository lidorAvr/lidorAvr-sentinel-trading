#!/usr/bin/env bash
# deploy.sh — MANUAL, operator-run deployment for Sentinel Trading.
#
# Why this exists (DEC-20260515-010): the host `deploy-watcher` systemd
# service is NOT installed on this Pi, so the Telegram "🔄 Git Pull + Deploy"
# button is a no-op and the real deploy path is a manual SSH command. A raw
# `docker compose up -d --build` left telegram-bot with no IPv4 egress
# ([Errno 101]) — see SPRINT13_TEAM_MEETING.md. This script applies the EXACT
# Sprint-13 resilience Mark ruled for deploy_watcher.sh
# (MARK_SPRINT13_RULINGS.md §1), but operator-run and operator-controlled —
# no auto-deploy, no watcher.
#
# Usage (one-time):  chmod +x deploy.sh
# Usage (each deploy, from ~/sentinel_trading on the Pi):  ./deploy.sh
#
# Does NOT modify docker-compose.yml service commands, secure_runner, the
# unit file, or any app/risk/NAV/campaign math. New standalone file only.

set -o pipefail

SENTINEL_DIR="${SENTINEL_DIR:-$HOME/sentinel_trading}"
COMPOSE_CMD="docker compose"
PROBE_HOST="api.telegram.org"      # the bot's only hard external dependency
PROBE_TIMEOUT="10"                 # Mark §1 literal per-attempt socket timeout
START_PERIOD="30"                  # matches docker-compose telegram-bot start_period

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# Post-deploy connectivity self-check — proves the telegram-bot CONTAINER
# (not the host) can open a TCP/443 IPv4 route to Telegram. stdlib socket
# only (no curl in python:3.10-slim); AF_INET forced because the live
# failure was an IPv4 route loss and an IPv6 fallback could mask it.
# Returns 0 = reachable, non-0 = not.
probe_telegram() {
    $COMPOSE_CMD exec -T telegram-bot python3 -c "
import socket, sys
host, port, t = '$PROBE_HOST', 443, float('$PROBE_TIMEOUT')
try:
    infos = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(t)
    s.connect(infos[0][4])
    s.close()
    sys.exit(0)
except Exception as e:
    print('PROBE_FAIL:', type(e).__name__, e, file=sys.stderr)
    sys.exit(1)
"
}

cd "$SENTINEL_DIR" || { log "ERROR: cannot cd to $SENTINEL_DIR"; exit 1; }

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
log "Branch: $BRANCH"

log "git pull origin $BRANCH ..."
if ! git pull origin "$BRANCH"; then
    log "ERROR: git pull failed — NOT deploying. Working tree unchanged."
    exit 1
fi

# Mark §1: --force-recreate cures the stale-bridge fault WITHOUT a `down`
# (a `down` would outage risk-monitor/reporting/sentinel-bot too).
log "docker compose up -d --build --force-recreate ..."
if ! $COMPOSE_CMD up -d --build --force-recreate; then
    log "ERROR: docker compose up failed. Bot state UNKNOWN — investigate:"
    log "  $COMPOSE_CMD ps ; $COMPOSE_CMD logs --tail=50 telegram-bot"
    exit 1
fi

log "Containers up. Waiting ${START_PERIOD}s for telegram-bot start_period..."
sleep "$START_PERIOD"

if probe_telegram; then
    log "✅ connectivity OK ($PROBE_HOST reachable via IPv4). Deploy complete."
    exit 0
fi

log "connectivity self-check FAILED — retrying once (single-service recreate)..."
$COMPOSE_CMD up -d --force-recreate telegram-bot
sleep "$START_PERIOD"
if probe_telegram; then
    log "✅ connectivity OK after retry. Deploy complete (post-retry)."
    exit 0
fi

# Never report a fabricated success on a dead bot (AGENTS.md #1). The
# operator is present and in control (DEC-20260515-010) — surface the exact
# recovery command and exit non-zero rather than silently `down` the whole
# stack.
log "🔴 ALERT: telegram-bot has NO Telegram egress after deploy + retry."
log "   The stale-bridge fault did not clear with --force-recreate."
log "   RUN THIS to recover (full network recreate; ~30s multi-service downtime):"
log "     $COMPOSE_CMD down && $COMPOSE_CMD up -d"
log "   Then re-run ./deploy.sh to re-verify."
exit 1
