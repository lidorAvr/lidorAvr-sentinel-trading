#!/usr/bin/env bash
# deploy_watcher.sh — runs on the Orange Pi HOST (not inside Docker).
# Watches for /deploy_trigger file written by the Telegram bot,
# then pulls latest code and rebuilds containers.
#
# Setup (one-time, via SSH):
#   chmod +x ~/sentinel_trading/deploy_watcher.sh
#   sudo cp ~/sentinel_trading/deploy-watcher.service /etc/systemd/system/
#   sudo systemctl daemon-reload
#   sudo systemctl enable --now deploy-watcher
#
# Check status:
#   sudo systemctl status deploy-watcher
#   journalctl -u deploy-watcher -f

SENTINEL_DIR="${SENTINEL_DIR:-$HOME/sentinel_trading}"
TRIGGER="$SENTINEL_DIR/deploy_trigger"
LOG="$SENTINEL_DIR/deploy_watcher.log"
COMPOSE_CMD="docker compose"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"
}

log "deploy_watcher started. Watching: $TRIGGER"

while true; do
    if [ -f "$TRIGGER" ]; then
        WRITTEN=$(cat "$TRIGGER" 2>/dev/null || echo "?")
        rm -f "$TRIGGER"
        log "Trigger detected (ts=$WRITTEN). Starting deploy..."

        cd "$SENTINEL_DIR" || { log "ERROR: cannot cd to $SENTINEL_DIR"; sleep 10; continue; }

        log "Running: git pull"
        if git pull >> "$LOG" 2>&1; then
            log "git pull OK. Rebuilding containers..."
            if $COMPOSE_CMD up -d --build >> "$LOG" 2>&1; then
                log "Deploy complete."
            else
                log "ERROR: docker compose up failed."
            fi
        else
            log "ERROR: git pull failed — skipping docker compose."
        fi
    fi
    sleep 5
done
