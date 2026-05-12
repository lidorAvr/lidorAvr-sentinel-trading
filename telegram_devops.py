"""
Developer-menu IBKR sync infrastructure for Sentinel Trading.

Extracted from telegram_bot.py:
- Rate limiting:        _dev_sync_check, _dev_sync_record
- Manual sync runner:   _run_manual_sync_thread (background thread)
- XML upload processor: _process_uploaded_ibkr_xml (manual Flex Query upload)
- NAV reader:           get_ibkr_nav (parse last on-disk XML)

These functions read/write paths on the host filesystem and depend on the
shared bot/supabase singletons from bot_core. They are exercised from the
developer menu in telegram_bot.handle_all_messages.
"""
import os
import json
import glob as _glob
import xml.etree.ElementTree as ET
from datetime import datetime

from bot_core import bot, RTL
from bot_helpers import _bot_log
from telegram_menus import get_developer_menu
from ibkr_sync_runner import (run_ibkr_sync, MANUAL_RESULT_FILE,
                               _REPORTS_DIR, _REPORTS_TO_KEEP, _CONFIG_PATH)

# ── Developer-menu constants ─────────────────────────────────────────────────
_DEV_STATE_FILE      = "/app/ibkr_dev_state.json"
_MANUAL_TRIGGER_FILE = "/app/ibkr_manual_trigger"  # unused — see TODO below
_DEPLOY_TRIGGER_FILE = "/app/deploy_trigger"       # unused — placeholder

_DEV_SYNC_MAX_PER_DAY    = 2
_DEV_SYNC_COOLDOWN_HOURS = 3

# NOTE: _MANUAL_TRIGGER_FILE is defined in main.py as the channel that
# main.py watches to know when the developer menu triggered a sync.
# However, _run_manual_sync_thread below calls run_ibkr_sync directly
# instead of writing the trigger file — so the file is never created and
# main.py's _handle_manual_trigger code path is dead. Resolution deferred.


def _dev_sync_check() -> tuple:
    """Returns (allowed: bool, reason: str, state_dict: dict)."""
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        state = json.load(open(_DEV_STATE_FILE)) if os.path.exists(_DEV_STATE_FILE) else {}
    except Exception:
        state = {}
    count_today = state.get("count_today", 0) if state.get("date") == today else 0
    if count_today >= _DEV_SYNC_MAX_PER_DAY:
        return False, f"הגעת למגבלה היומית ({_DEV_SYNC_MAX_PER_DAY} סנכרונים ביום). נסה מחר.", state
    last_ts_str = state.get("last_ts")
    if last_ts_str:
        try:
            hours_since = (datetime.now() - datetime.fromisoformat(last_ts_str)).total_seconds() / 3600
            if hours_since < _DEV_SYNC_COOLDOWN_HOURS:
                remaining = _DEV_SYNC_COOLDOWN_HOURS - hours_since
                return False, f"Cooldown פעיל — המתן עוד `{remaining:.1f}h` (cooldown: {_DEV_SYNC_COOLDOWN_HOURS}h).", state
        except Exception:
            pass
    return True, "", state


def _dev_sync_record(state: dict):
    today = datetime.now().strftime("%Y-%m-%d")
    count_today = state.get("count_today", 0) if state.get("date") == today else 0
    state.update({"date": today, "count_today": count_today + 1,
                  "last_ts": datetime.now().isoformat()})
    try:
        with open(_DEV_STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception:
        pass


def _run_manual_sync_thread(chat_id: int):
    """Background thread: runs IBKR sync and reports back to Telegram."""
    _bot_log(f"Manual IBKR sync started by chat_id={chat_id}")
    try:
        result = run_ibkr_sync(log_fn=_bot_log)
        status  = result["status"]
        message = result["message"]
        nav     = result.get("nav")
        try:
            result["triggered_at"] = datetime.now().isoformat()
            with open(MANUAL_RESULT_FILE, "w") as f:
                json.dump(result, f)
        except Exception:
            pass
        emoji = "✅" if status == "success" else ("🚨" if status == "fatal" else "⚠️")
        status_heb = {"success": "הצליח", "fatal": "שגיאה חמורה",
                      "rate_limit": "Rate Limit", "temporary": "זמני"}.get(status, status)
        nav_line = f"\n{RTL}NAV מעודכן: `${nav:,.0f}`" if nav else ""
        bot.send_message(
            chat_id,
            f"{RTL}{emoji} *IBKR Manual Sync — {status_heb}*\n{RTL}{message}{nav_line}",
            reply_markup=get_developer_menu(), parse_mode="Markdown",
        )
        _bot_log(f"Manual IBKR sync result: {status} — {message}")
    except Exception as e:
        bot.send_message(chat_id, f"❌ שגיאה בסנכרון ידני: {e}",
                         reply_markup=get_developer_menu(), parse_mode="Markdown")
        _bot_log(f"Manual IBKR sync error: {e}")


def _process_uploaded_ibkr_xml(chat_id: int, message):
    """Download and process a manually-uploaded IBKR Flex XML report."""
    try:
        doc = message.document
        if not (doc.file_name or "").lower().endswith(".xml"):
            bot.send_message(chat_id, f"{RTL}❌ יש לשלוח קובץ XML בלבד.",
                             reply_markup=get_developer_menu())
            return

        bot.send_message(chat_id, f"{RTL}⏳ מעבד דוח...", reply_markup=get_developer_menu())
        file_info = bot.get_file(doc.file_id)
        xml_text = bot.download_file(file_info.file_path).decode("utf-8")

        report_root = ET.fromstring(xml_text)

        nav_updated = None
        nav_node = report_root.find(".//ChangeInNAV")
        if nav_node is not None:
            v = nav_node.get("endingValue")
            if v:
                nav_updated = float(v)

        trades = report_root.findall(".//Trade")

        if nav_updated is None and not trades:
            bot.send_message(
                chat_id,
                f"{RTL}⚠️ הקובץ לא נראה כדוח IBKR תקין.\n"
                f"{RTL}לא נמצא ChangeInNAV ולא נמצאו עסקאות.",
                reply_markup=get_developer_menu(),
            )
            return

        os.makedirs(_REPORTS_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
        report_path = os.path.join(_REPORTS_DIR, f"ibkr_{ts}.xml")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(xml_text)
        all_reports = sorted(_glob.glob(os.path.join(_REPORTS_DIR, "ibkr_*.xml")))
        while len(all_reports) > _REPORTS_TO_KEEP:
            os.remove(all_reports.pop(0))

        if nav_updated is not None:
            try:
                cfg = {"total_deposited": 7500.0, "risk_pct_input": 0.5}
                if os.path.exists(_CONFIG_PATH):
                    with open(_CONFIG_PATH) as f:
                        cfg = json.load(f)
                cfg["nav"] = nav_updated
                cfg["nav_updated_at"] = datetime.now().isoformat()
                with open(_CONFIG_PATH, "w") as f:
                    json.dump(cfg, f)
            except Exception as e:
                _bot_log(f"NAV update error in manual upload: {e}")

        try:
            result = {
                "status": "success", "code": None,
                "message": f"{len(trades)} עסקאות נטענו מקובץ ידני",
                "nav": nav_updated,
                "triggered_at": datetime.now().isoformat(),
                "source": "manual_upload",
            }
            with open(MANUAL_RESULT_FILE, "w") as f:
                json.dump(result, f)
        except Exception:
            pass

        nav_str = f"\n{RTL}NAV מעודכן: `${nav_updated:,.2f}`" if nav_updated else ""
        _bot_log(f"Manual XML upload OK: {len(trades)} trades, NAV={nav_updated}")
        bot.send_message(
            chat_id,
            f"{RTL}✅ *דוח IBKR נטען בהצלחה*\n"
            f"{RTL}עסקאות: `{len(trades)}`{nav_str}\n"
            f"{RTL}קובץ: `{os.path.basename(report_path)}`",
            reply_markup=get_developer_menu(), parse_mode="Markdown",
        )

    except ET.ParseError as e:
        bot.send_message(chat_id, f"{RTL}❌ XML לא תקין: {e}",
                         reply_markup=get_developer_menu())
    except Exception as e:
        _bot_log(f"Manual XML upload error: {e}")
        bot.send_message(chat_id, f"{RTL}❌ שגיאה בעיבוד: {e}",
                         reply_markup=get_developer_menu())


def get_ibkr_nav():
    """Parse the last on-disk IBKR raw report and return NAV (or None)."""
    try:
        report_path = "ibkr_raw_report.xml"
        if not os.path.exists(report_path):
            return None
        tree = ET.parse(report_path)
        root = tree.getroot()
        for elem in root.iter():
            if elem.tag.lower().endswith("changeinnav"):
                ending_val = elem.attrib.get('endingValue')
                if ending_val:
                    return float(ending_val)
        return None
    except Exception:
        return None
