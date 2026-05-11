import os, shutil, datetime

base_dir = "/home/orangepi/sentinel_trading"
archive_dir = os.path.join(base_dir, "_archive_scripts")
backup_dir = os.path.join(base_dir, "_stable_backups")

os.makedirs(archive_dir, exist_ok=True)
os.makedirs(backup_dir, exist_ok=True)

# אלו 12 הקבצים היחידים שדרושים להפעלת המערכת
essential_files = {
    "telegram_bot.py", "dashboard.py", "main.py", "risk_monitor.py",
    "engine_core.py", "docker-compose.yml", "Dockerfile", "requirements.txt",
    ".env", "sentinel_config.json", "risk_monitor_state.json", "sector_cache.json"
}

essential_dirs = {"__pycache__", "_archive_scripts", "_stable_backups"}

# 1. ניקוי העומס
for item in os.listdir(base_dir):
    if item in essential_files or item in essential_dirs or item == "system_cleanup_and_backup.py":
        continue
    item_path = os.path.join(base_dir, item)
    try:
        shutil.move(item_path, os.path.join(archive_dir, item))
    except Exception as e:
        print(f"Skipped {item}: {e}")

# 2. יצירת סנאפשוט של הגרסה היציבה
timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
snapshot_name = f"STABLE_VERSION_{timestamp}"
snapshot_path = os.path.join(backup_dir, snapshot_name)
os.makedirs(snapshot_path, exist_ok=True)

for f in essential_files:
    src = os.path.join(base_dir, f)
    if os.path.exists(src):
        shutil.copy2(src, os.path.join(snapshot_path, f))

# 3. כתיבת קובץ תיעוד לגיבוי
with open(os.path.join(snapshot_path, "README_STABLE.txt"), "w") as f:
    f.write("Sentinel Trading System - STABLE SNAPSHOT\n")
    f.write("=========================================\n")
    f.write(f"Date Saved: {timestamp}\n\n")
    f.write("Status: PERFECTLY WORKING VERSION\n")
    f.write("- Telegram Bot: Operational (Drill-down, Backlog, Live updates)\n")
    f.write("- IBKR Sync (main.py): Pulls trades in memory, updates Supabase, Auto-updates NAV.\n")
    f.write("- Dashboard: Optimized, reads NAV from JSON, clear alerts.\n")
    f.write("- Core Engine: Risk calculations, Minervini scans.\n")

print("🧹 ניקוי התיקייה הושלם!")
print(f"📦 גיבוי מלא נוצר בהצלחה תחת: _stable_backups/{snapshot_name}")
