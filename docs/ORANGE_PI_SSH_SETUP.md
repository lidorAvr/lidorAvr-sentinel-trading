# Orange Pi — First-Time SSH Setup

Run these commands once via SSH to activate remote deployment via the Telegram developer menu.

## Prerequisites

- SSH access to Orange Pi
- Docker + docker compose installed
- Repo already cloned to `~/sentinel_trading`

---

## Step-by-step

```bash
# 1. Pull latest code (includes deploy_watcher.sh and deploy-watcher.service)
cd ~/sentinel_trading && git pull

# 2. Set your actual Orange Pi username (replace 'pi' if different)
sed -i 's/YOUR_USER/pi/g' deploy-watcher.service

# 3. Install systemd service
sudo cp deploy-watcher.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now deploy-watcher

# 4. Verify it's running
sudo systemctl status deploy-watcher

# 5. Initial full deploy
docker compose up -d --build
```

---

## How it works after setup

```
Telegram → תפריט מפתח → 🔄 Git Pull + Deploy
  ↓ git pull inside container
  ↓ writes ~/sentinel_trading/deploy_trigger

deploy_watcher.sh (on host, every 5s)
  ↓ detects deploy_trigger
  ↓ git pull on host
  ↓ docker compose up -d --build
  ↓ all containers restart with new code
```

---

## Useful commands

```bash
# Watch deploy watcher logs live
journalctl -u deploy-watcher -f

# Manual deploy (bypass trigger)
cd ~/sentinel_trading && git pull && docker compose up -d --build

# Check all containers
docker compose ps

# Tail telegram-bot logs
docker logs --tail=50 -f telegram-bot

# Restart single service
docker compose restart telegram-bot
```

---

## Rollback

```bash
# Roll back to previous commit
cd ~/sentinel_trading
git log --oneline -10          # find the commit to roll back to
git checkout <commit-hash>
docker compose up -d --build
```
