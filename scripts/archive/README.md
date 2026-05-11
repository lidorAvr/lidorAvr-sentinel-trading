# scripts/archive

One-shot fix and debug scripts from iterative development sessions.
These are no longer needed for normal operation and are kept for historical reference only.

## Contents

| File | Purpose |
|------|---------|
| `final_clean_fix.py` | One-time code cleanup after engine refactor |
| `final_nav_fix.py` | One-time NAV key fix (current_nav → nav) |
| `final_recovery.py` | One-time recovery from broken state |
| `final_touch.py` | One-time cosmetic cleanup |
| `fix_dashboard.py` | One-time dashboard config fix |
| `fix_global_boot.py` | One-time Docker boot fix |
| `fix_nav_path.py` | One-time config path fix |
| `fix_none_type.py` | One-time NoneType bug fix |
| `fix_telegram_keys.py` | One-time Telegram keyboard fix |
| `force_first_run.py` | One-time script to force first IBKR sync |
| `force_nav_update.py` | One-time NAV update injection |
| `force_telegram.py` | One-time Telegram message force-send |
| `master_fix.py` | One-time combined fix script |
| `nuclear_fix.py` | One-time full reset script |
| `emergency_stabilize.py` | One-time emergency stabilization |
| `inject_nav_logic.py` | One-time NAV logic injection |
| `rebuild_sync.py` | One-time sync rebuild |
| `smart_sync_upgrade.py` | One-time sync upgrade |
| `system_cleanup_and_backup.py` | One-time cleanup and backup |
| `upgrade_logs.py` | One-time log format upgrade |
| `protect_xml.py` | One-time XML file protection |
| `clean_main.py` | One-time main.py cleanup |
| `set_cooldown.py` | One-time cooldown state injection |
| `silence_pandas.py` | One-time pandas warning suppressor |
| `test_infra.py` | Broken integration test (requires dotenv + live env) |
| `test_xml_ibkr.py` | Broken IBKR XML test (requires dotenv + live env) |

## Production code at root level (active)

See `docs/MODULE_MAP.md` for the canonical list of active production modules.
