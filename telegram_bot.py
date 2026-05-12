import os, telebot, json, traceback, threading, subprocess, glob as _glob
import pandas as pd
from telebot import types
from supabase import create_client
from dotenv import load_dotenv
from datetime import datetime
import xml.etree.ElementTree as ET
import engine_core as ec
import telegram_formatters as tf
import adaptive_risk_engine as are
from ibkr_sync_runner import (run_ibkr_sync, MANUAL_RESULT_FILE,
                               _REPORTS_DIR, _REPORTS_TO_KEEP, _CONFIG_PATH)

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = os.getenv("TELEGRAM_ADMIN_ID")
bot = telebot.TeleBot(TOKEN)
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

user_state = {}
RTL = "\u200F"

# \u2500\u2500 Developer-menu constants \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
_DEV_STATE_FILE      = "/app/ibkr_dev_state.json"
_MANUAL_TRIGGER_FILE = "/app/ibkr_manual_trigger"
_DEPLOY_TRIGGER_FILE = "/app/deploy_trigger"
_BOT_LOG_FILE        = "/app/logs/sentinel_bot.log"
_BOT_LOG_MAX_LINES   = 2000

_DEV_LOG_FILES = {
    "sentinel-main":    "/app/logs/sentinel_main.log",
    "sentinel-bot":     "/app/logs/sentinel_bot.log",
    "risk-monitor":     "/app/logs/sentinel_risk.log",
}

_DEV_SYNC_MAX_PER_DAY     = 2
_DEV_SYNC_COOLDOWN_HOURS  = 3


def _bot_log(msg: str):
    """Append a line to the bot log file (developer menu log viewer reads this)."""
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {msg}\n"
        os.makedirs(os.path.dirname(_BOT_LOG_FILE), exist_ok=True)
        with open(_BOT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
        import random
        if random.random() < 0.05:
            lines = open(_BOT_LOG_FILE, encoding="utf-8").readlines()
            if len(lines) > _BOT_LOG_MAX_LINES:
                with open(_BOT_LOG_FILE, "w", encoding="utf-8") as f:
                    f.writelines(lines[-_BOT_LOG_MAX_LINES:])
    except Exception:
        pass


def _dev_sync_check() -> tuple:
    """Returns (allowed: bool, reason: str, state_dict: dict)."""
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        state = json.load(open(_DEV_STATE_FILE)) if os.path.exists(_DEV_STATE_FILE) else {}
    except Exception:
        state = {}
    count_today = state.get("count_today", 0) if state.get("date") == today else 0
    if count_today >= _DEV_SYNC_MAX_PER_DAY:
        return False, f"\u05D4\u05D2\u05E2\u05EA \u05DC\u05DE\u05D2\u05D1\u05DC\u05D4 \u05D4\u05D9\u05D5\u05DE\u05D9\u05EA ({_DEV_SYNC_MAX_PER_DAY} \u05E1\u05E0\u05DB\u05E8\u05D5\u05E0\u05D9\u05DD \u05D1\u05D9\u05D5\u05DD). \u05E0\u05E1\u05D4 \u05DE\u05D7\u05E8.", state
    last_ts_str = state.get("last_ts")
    if last_ts_str:
        try:
            hours_since = (datetime.now() - datetime.fromisoformat(last_ts_str)).total_seconds() / 3600
            if hours_since < _DEV_SYNC_COOLDOWN_HOURS:
                remaining = _DEV_SYNC_COOLDOWN_HOURS - hours_since
                return False, f"Cooldown \u05E4\u05E2\u05D9\u05DC \u2014 \u05D4\u05DE\u05EA\u05DF \u05E2\u05D5\u05D3 `{remaining:.1f}h` (cooldown: {_DEV_SYNC_COOLDOWN_HOURS}h).", state
        except Exception:
            pass
    return True, "", state


def _dev_sync_record(state: dict):
    today = datetime.now().strftime("%Y-%m-%d")
    count_today = state.get("count_today", 0) if state.get("date") == today else 0
    state.update({"date": today, "count_today": count_today + 1, "last_ts": datetime.now().isoformat()})
    try:
        with open(_DEV_STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception:
        pass


_RM_STATE_FILE = "risk_monitor_state.json"

def _write_runner_decision(campaign_id: str, decision: str) -> None:
    """Write runner_decision + runner_decision_ts into risk_monitor_state.json for the given campaign."""
    try:
        try:
            with open(_RM_STATE_FILE, "r", encoding="utf-8") as f:
                rm_state = json.load(f)
        except Exception:
            rm_state = {"positions": {}, "cluster": {}}
        pos_entry = rm_state.setdefault("positions", {}).get(campaign_id)
        if pos_entry is None:
            rm_state["positions"][campaign_id] = {}
            pos_entry = rm_state["positions"][campaign_id]
        pos_entry["runner_decision"] = decision
        pos_entry["runner_decision_ts"] = datetime.now().timestamp()
        with open(_RM_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(rm_state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _read_last_log_lines(path: str, n: int = 50) -> str:
    try:
        if not os.path.exists(path):
            return f"_(\u05E7\u05D5\u05D1\u05E5 \u05DC\u05D0 \u05E7\u05D9\u05D9\u05DD: {path})_"
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
        tail = "".join(lines[-n:]) if lines else "(\u05E8\u05D9\u05E7)"
        return tail.strip()
    except Exception as e:
        return f"_(\u05E9\u05D2\u05D9\u05D0\u05D4 \u05D1\u05E7\u05E8\u05D9\u05D0\u05EA \u05DC\u05D5\u05D2: {e})_"


def _run_manual_sync_thread(chat_id: int):
    """Background thread: runs IBKR sync and reports back to Telegram."""
    _bot_log(f"Manual IBKR sync started by chat_id={chat_id}")
    try:
        result = run_ibkr_sync(log_fn=_bot_log)
        status  = result["status"]
        message = result["message"]
        nav     = result.get("nav")
        # Persist last result for \uD83D\uDCCA \u05EA\u05D5\u05E6\u05D0\u05D4 button
        try:
            result["triggered_at"] = datetime.now().isoformat()
            with open(MANUAL_RESULT_FILE, "w") as f:
                json.dump(result, f)
        except Exception:
            pass
        emoji = "\u2705" if status == "success" else ("\uD83D\uDEA8" if status == "fatal" else "\u26A0\uFE0F")
        status_heb = {"success": "\u05D4\u05E6\u05DC\u05D9\u05D7", "fatal": "\u05E9\u05D2\u05D9\u05D0\u05D4 \u05D7\u05DE\u05D5\u05E8\u05D4",
                      "rate_limit": "Rate Limit", "temporary": "\u05D6\u05DE\u05E0\u05D9"}.get(status, status)
        nav_line = f"\n{RTL}NAV \u05DE\u05E2\u05D5\u05D3\u05DB\u05DF: `${nav:,.0f}`" if nav else ""
        bot.send_message(
            chat_id,
            f"{RTL}{emoji} *IBKR Manual Sync \u2014 {status_heb}*\n{RTL}{message}{nav_line}",
            reply_markup=get_developer_menu(), parse_mode="Markdown",
        )
        _bot_log(f"Manual IBKR sync result: {status} \u2014 {message}")
    except Exception as e:
        bot.send_message(chat_id, f"\u274C \u05E9\u05D2\u05D9\u05D0\u05D4 \u05D1\u05E1\u05E0\u05DB\u05E8\u05D5\u05DF \u05D9\u05D3\u05E0\u05D9: {e}",
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

        # Save to reports directory (same cleanup as auto-sync)
        os.makedirs(_REPORTS_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
        report_path = os.path.join(_REPORTS_DIR, f"ibkr_{ts}.xml")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(xml_text)
        all_reports = sorted(_glob.glob(os.path.join(_REPORTS_DIR, "ibkr_*.xml")))
        while len(all_reports) > _REPORTS_TO_KEEP:
            os.remove(all_reports.pop(0))

        # Update sentinel_config.json NAV
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

        # Persist result so "📊 תוצאת Sync אחרון" picks it up
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
    try:
        report_path = "ibkr_raw_report.xml"
        if not os.path.exists(report_path): return None
        tree = ET.parse(report_path)
        root = tree.getroot()
        for elem in root.iter():
            if elem.tag.lower().endswith("changeinnav"):
                ending_val = elem.attrib.get('endingValue')
                if ending_val: return float(ending_val)
        return None
    except: return None

def get_account_settings():
    try:
        with open("sentinel_config.json", "r") as f: return json.load(f)
    except: return {"total_deposited": 7500.0, "risk_pct_input": 0.5}


def get_nav_and_risk(account_settings=None):
    """
    Single source of truth for NAV + target risk.
    Returns (acc_size, target_risk_usd, nav_freshness_label).
    Uses get_nav_with_freshness() so staleness is always surfaced.
    """
    if account_settings is None:
        account_settings = get_account_settings()
    nav_info = ec.get_nav_with_freshness()
    acc_size = nav_info["nav"] if nav_info["ok"] else float(account_settings.get("total_deposited", 7500.0))
    risk_pct = float(account_settings.get("risk_pct_input", 0.5))
    target_risk_usd = acc_size * (risk_pct / 100)
    stale_label = nav_info["freshness_label"] if nav_info["is_stale"] else None
    return acc_size, target_risk_usd, stale_label


def _build_health_report():
    """
    Run 13 data integrity checks and return a formatted Telegram health report.
    Designed to be fast — reads local files + one lightweight Supabase query.
    """
    import glob as _glob
    checks = []
    SEP = "───────────────"

    def ok(msg):  checks.append(f"✅ {msg}")
    def warn(msg): checks.append(f"⚠️ {msg}")
    def bad(msg):  checks.append(f"🔴 {msg}")

    # 1. IBKR Sync Status
    try:
        ss = json.load(open("/app/ibkr_sync_state.json"))
        sd = ss.get("sync_date", "—")
        today = datetime.now().strftime("%Y-%m-%d")
        ok(f"IBKR Sync — {sd}") if sd == today else warn(f"IBKR Sync — אחרון: {sd}")
    except:
        warn("IBKR Sync — קובץ state לא נמצא (טרם רץ?)")

    # 2. IBKR Reports archive
    reports = sorted(_glob.glob("/app/ibkr_reports/ibkr_*.xml"))
    if reports:
        ok(f"IBKR Reports — {len(reports)} קבצים, אחרון: {os.path.basename(reports[-1])[:20]}")
    else:
        warn("IBKR Reports — אין קבצים ב-/app/ibkr_reports/")

    # 3. NAV Config + freshness
    nav_info = ec.get_nav_with_freshness()
    if not nav_info["ok"]:
        bad("NAV Config — sentinel_config.json לא נמצא")
    elif nav_info["is_critical"]:
        bad(nav_info["freshness_label"])
    elif nav_info["is_stale"]:
        warn(nav_info["freshness_label"])
    else:
        ok(nav_info["freshness_label"])

    # 4. Risk Config range
    try:
        cfg = cfg if 'cfg' in dir() else get_account_settings()
        rp = float(cfg.get("risk_pct_input", 0))
        ok(f"Risk Config — {rp:.2f}%") if 0.2 <= rp <= 3.0 else warn(f"Risk Config — {rp:.2f}% (מחוץ לטווח 0.2–3%)")
    except:
        warn("Risk Config — לא נבדק")

    # 5. Supabase connection + data freshness
    try:
        res = supabase.table("trades").select("trade_date").order("trade_date", desc=True).limit(1).execute()
        if res.data:
            ok(f"Supabase — טרייד אחרון: {str(res.data[0]['trade_date'])[:10]}")
        else:
            warn("Supabase — מחובר אך אין נתוני טריידים")
    except Exception as e:
        bad(f"Supabase — שגיאת חיבור: {str(e)[:40]}")

    # 6. Missing stops (open buy rows)
    try:
        res2 = supabase.table("trades").select("symbol,stop_loss,quantity,side").execute()
        df_h = pd.DataFrame(res2.data if res2.data else [])
        if not df_h.empty:
            buys = df_h[df_h["side"].str.upper() == "BUY"].copy()
            buys["stop_loss"] = pd.to_numeric(buys["stop_loss"], errors="coerce").fillna(0)
            buys["quantity"] = pd.to_numeric(buys["quantity"], errors="coerce").fillna(0)
            ms = buys[(buys["quantity"] > 0) & (buys["stop_loss"] <= 0)]
            syms = ", ".join(ms["symbol"].unique()[:5])
            ok("Missing Stops — אין") if ms.empty else warn(f"Missing Stops — {len(ms)} שורות ({syms})")
        else:
            warn("Missing Stops — לא נבדק (אין נתונים)")
    except:
        warn("Missing Stops — לא נבדק")

    # 7. Null campaign_ids
    try:
        res3 = supabase.table("trades").select("trade_id,campaign_id").execute()
        df_c = pd.DataFrame(res3.data if res3.data else [])
        null_camps = df_c[df_c["campaign_id"].isnull()] if not df_c.empty else pd.DataFrame()
        ok("Campaign IDs — כולם מלאים") if null_camps.empty else warn(f"Campaign IDs — {len(null_camps)} שורות ללא campaign_id")
    except:
        warn("Campaign IDs — לא נבדק")

    # 8. ALGO positions (info only)
    try:
        df_all = pd.DataFrame(supabase.table("trades").select("symbol,setup_type,quantity,side").execute().data or [])
        if not df_all.empty:
            algo_rows = df_all[df_all["setup_type"].str.upper() == "ALGO"]
            algo_syms = algo_rows["symbol"].unique()
            if len(algo_syms):
                ok(f"ALGO Positions — {len(algo_syms)} סמלים: {', '.join(algo_syms[:6])}")
            else:
                ok("ALGO Positions — אין פוזיציות ALGO")
    except:
        warn("ALGO Positions — לא נבדק")

    # 9. Telegram Admin ID
    ok("Telegram Admin — מוגדר") if os.getenv("TELEGRAM_ADMIN_ID") else bad("Telegram Admin — חסר TELEGRAM_ADMIN_ID!")

    # 10. IBKR Token
    ok("IBKR Token — מוגדר") if os.getenv("IBKR_TOKEN") else bad("IBKR Token — חסר IBKR_TOKEN!")

    # 11. IBKR Query ID
    ok(f"IBKR Query ID — {os.getenv('IBKR_QUERY_ID', 'default')}") if os.getenv("IBKR_QUERY_ID") else warn("IBKR Query ID — משתמש ב-default")

    # 12. Risk Monitor State
    try:
        rm = json.load(open("risk_monitor_state.json"))
        pos_count = len(rm.get("positions", {}))
        ok(f"Risk Monitor State — {pos_count} פוזיציות במעקב")
    except:
        warn("Risk Monitor State — קובץ לא נמצא (עדיין לא רץ?)")

    # 13. Adaptive Risk Journal
    try:
        rj = json.load(open("risk_recommendations.json"))
        rec_count = len(rj) if isinstance(rj, list) else 0
        ok(f"Risk Journal — {rec_count} המלצות")
    except:
        warn("Risk Journal — קובץ לא נמצא (טרם נוצר)")

    total = len(checks)
    n_ok   = sum(1 for c in checks if c.startswith("✅"))
    n_warn = sum(1 for c in checks if c.startswith("⚠️"))
    n_bad  = sum(1 for c in checks if c.startswith("🔴"))
    status_icon = "✅" if n_bad == 0 and n_warn == 0 else ("⚠️" if n_bad == 0 else "🔴")

    lines = [
        f"{RTL}🏥 Sentinel System Health {status_icon}",
        f"{RTL}{SEP}",
        f"{RTL}✅ {n_ok} תקין | ⚠️ {n_warn} אזהרה | 🔴 {n_bad} שגיאה ({total} בדיקות)",
        f"{RTL}{SEP}",
    ]
    lines += [f"{RTL}{c}" for c in checks]
    return "\n".join(lines)


def get_main_menu():
    """תפריט ראשי — 5 קטגוריות."""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("📊 מצב תיק"), types.KeyboardButton("🔬 ניתוח"))
    markup.add(types.KeyboardButton("📚 יומן"), types.KeyboardButton("❓ עזרה"))
    markup.add(types.KeyboardButton("🛠️ מפתח"))
    return markup


def get_developer_menu():
    """תפריט מפתח — כלי פיתוח ודיבאג."""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("📡 IBKR Sync ידני"), types.KeyboardButton("📤 העלה דוח XML"))
    markup.add(types.KeyboardButton("🔄 Git Pull + Deploy"), types.KeyboardButton("⚙️ הצג Config"))
    markup.add(types.KeyboardButton("📊 תוצאת Sync אחרון"), types.KeyboardButton("🏥 בריאות מערכת"))
    markup.add(types.KeyboardButton("📋 לוגים"), types.KeyboardButton("⬅️ חזרה לתפריט ראשי"))
    return markup

def get_portfolio_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(types.KeyboardButton("📊 חדר מצב (פוזיציות)"))
    markup.add(types.KeyboardButton("🌡️ משטר שוק וסיכונים"))
    markup.add(types.KeyboardButton("⬅️ חזרה לתפריט ראשי"))
    return markup

def get_analysis_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(types.KeyboardButton("🔬 סקירת מניה"))
    markup.add(types.KeyboardButton("🧠 ניתוח מינרביני מלא"))
    markup.add(types.KeyboardButton("⬅️ חזרה לתפריט ראשי"))
    return markup

def get_journal_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(types.KeyboardButton("🔍 סריקת יומן (Backlog)"))
    markup.add(types.KeyboardButton("🧹 ארכיון עסקאות (Legacy)"))
    markup.add(types.KeyboardButton("⬅️ חזרה לתפריט ראשי"))
    return markup

def get_rating_keyboard(t_id, field):
    keyboard = types.InlineKeyboardMarkup(row_width=5)
    btns = [types.InlineKeyboardButton(text=str(i), callback_data=f"v|{t_id}|{field}|{i}") for i in range(1, 11)]
    keyboard.add(*btns)
    keyboard.add(types.InlineKeyboardButton(text="⏭️ דילוג", callback_data=f"v|{t_id}|{field}|-1"))
    return keyboard

def get_setup_keyboard(t_id):
    setups = ["VCP", "ALGO", "SWING", "EP"]
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    for s in setups: keyboard.add(types.InlineKeyboardButton(text=s, callback_data=f"v|{t_id}|setup_type|{s}"))
    keyboard.add(types.InlineKeyboardButton(text="⏭️ דילוג", callback_data=f"v|{t_id}|setup_type|Skipped"))
    return keyboard

def send_long_message(chat_id, text, reply_markup=None):
    max_len = 3900
    if len(text) <= max_len:
        bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode="Markdown")
        return
    parts = []
    while len(text) > 0:
        if len(text) <= max_len:
            parts.append(text)
            break
        split_idx = text.rfind('〰️〰️〰️〰️〰️〰️〰️〰️〰️\n', 0, max_len)
        if split_idx == -1:
            split_idx = text.rfind('\n', 0, max_len)
            if split_idx == -1: split_idx = max_len
        else: split_idx += len('〰️〰️〰️〰️〰️〰️〰️〰️〰️\n')
        parts.append(text[:split_idx])
        text = text[split_idx:]
    for i, part in enumerate(parts):
        try:
            if i == len(parts) - 1: bot.send_message(chat_id, part, reply_markup=reply_markup, parse_mode="Markdown")
            else: bot.send_message(chat_id, part, parse_mode="Markdown")
        except Exception as e: print(f"Error sending part {i}: {e}")

def get_next_missing(chat_id):
    try:
        query_or = "setup_type.is.null,quality.is.null,and(side.eq.BUY,initial_stop.is.null),and(side.eq.BUY,initial_stop.eq.0),and(side.eq.SELL,score.is.null),and(side.eq.SELL,image_url.is.null),and(side.eq.SELL,management_notes.is.null)"
        res = supabase.table("trades").select("*").or_(query_or).order("trade_date", desc=False).order("trade_id", desc=False).limit(100).execute()
        t = None
        for row in res.data:
            if str(row.get('setup_type')) == 'Legacy': continue
            if row.get('side', '').upper() == 'BUY':
                cid = row.get('campaign_id')
                if cid:
                    older_buys = supabase.table("trades").select("*").eq("campaign_id", cid).eq("side", "BUY").lt("trade_date", row["trade_date"]).execute()
                    if older_buys.data:
                        first_b = older_buys.data[0]
                        upd = {"setup_type": first_b.get("setup_type"), "quality": first_b.get("quality"), "initial_stop": first_b.get("initial_stop"), "stop_loss": first_b.get("stop_loss")}
                        supabase.table("trades").update(upd).eq("trade_id", row["trade_id"]).execute()
                        continue
                if str(row.get('setup_type')).upper() == 'ALGO':
                    init_sl = row.get('initial_stop')
                    if init_sl is None or init_sl == 0:
                        supabase.table("trades").update({"initial_stop": -1, "stop_loss": -1}).eq("trade_id", row["trade_id"]).execute()
                        continue 
            t = row
            break
        if not t:
            bot.send_message(chat_id, "✅ *היומן מעודכן לחלוטין!*\nאין חוסרים במערכת.", reply_markup=get_main_menu(), parse_mode="Markdown")
            return
        t_id, symbol, side, t_date = t['trade_id'], t['symbol'], t['side'], t['trade_date']
        total_steps = 3 if side.upper() == 'BUY' else 5
        curr_step = 1
        if t.get('setup_type') is not None: curr_step += 1
        if t.get('quality') is not None: curr_step += 1
        if side.upper() == 'BUY':
            if t.get('initial_stop') not in [None, 0]: curr_step += 1
        elif side.upper() == 'SELL':
            if t.get('score') is not None: curr_step += 1
            if t.get('image_url') is not None and str(t.get('image_url')) not in ["None", "Skipped"]: curr_step += 1
        card = f"🏷️ *נכס:* {symbol} | {side}\n📅 *תאריך:* {t_date}\n🆔 *מזהה:* `{t_id}`\n⏳ *השלמת יומן - שלב {curr_step}/{total_steps}*\n〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️"
        if t.get('setup_type') is None:
            bot.send_message(chat_id, f"{card}\n🎯 *אנא סווג את האסטרטגיה (Setup):*", reply_markup=get_setup_keyboard(t_id), parse_mode="Markdown")
            return
        if t.get('quality') is None:
            if str(t.get('setup_type')).upper() == 'VCP':
                bot.send_message(chat_id, f"⏳ מנתח Trend Template עבור {symbol}...", parse_mode="Markdown")
                report_res = ec.get_minervini_analysis(symbol)
                report = report_res["data"][0] if report_res["ok"] else str(report_res.get("error", "Error")).replace("_", " ")
                bot.send_message(chat_id, f"{card}\n{report}\n\n💎 *מה הציון הסופי שלך? (1-10):*", reply_markup=get_rating_keyboard(t_id, 'quality'), parse_mode="Markdown")
            else:
                bot.send_message(chat_id, f"{card}\n💎 *מהי איכות הסטאפ בטרייד זה? (1-10):*", reply_markup=get_rating_keyboard(t_id, 'quality'), parse_mode="Markdown")
            return
        if side.upper() == "BUY":
            init_sl = t.get('initial_stop')
            if init_sl is None or init_sl == 0:
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton(text="⏭️ דילוג / ללא סטופ", callback_data=f"v|{t_id}|initial_stop|-1"))
                bot.send_message(chat_id, f"{card}\n🎯 *מהו הסטופ ההתחלתי? (Initial Stop)*\nיש להקליד כעת את מחיר הסטופ המקורי (למשל 150.50).", reply_markup=markup, parse_mode="Markdown")
                user_state[chat_id] = {'action': 'initial_stop', 't_id': t_id}
                return
        if side.upper() == "SELL":
            if t.get('score') is None:
                bot.send_message(chat_id, f"{card}\n🏆 *כיצד היית מדרג את סגירת העסקה שלך? (1-10):*", reply_markup=get_rating_keyboard(t_id, 'score'), parse_mode="Markdown")
                return
            if t.get('image_url') is None or t.get('image_url') == "None":
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton(text="⏭️ דילוג על תמונה", callback_data=f"v|{t_id}|image_url|Skipped"))
                bot.send_message(chat_id, f"{card}\n🔗 *קישור לתמונה נדרש:*\nאנא הדבק קישור מ-TradingView.", reply_markup=markup, parse_mode="Markdown")
                user_state[chat_id] = {'action': 'image', 't_id': t_id}
                return
            if t.get('management_notes') is None:
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton(text="⏭️ ללא הערה (דילוג)", callback_data=f"v|{t_id}|management_notes|Skipped"))
                bot.send_message(chat_id, f"{card}\n📝 *תובנות ניהול פוזיציה (אופציונלי):*\nהקלד כעת בהודעה את תובנות הניהול, תחושות או טעויות שביצעת (יישמר בעמודה ייעודית).", reply_markup=markup, parse_mode="Markdown")
                user_state[chat_id] = {'action': 'management_notes', 't_id': t_id}
                return
    except Exception as e: bot.send_message(chat_id, f"❌ *שגיאת מערכת:* {str(e)}", parse_mode="Markdown")

def handle_drilldown(chat_id, symbol):
    msg_id = bot.send_message(chat_id, f"⏳ שואב נתוני רנטגן (Drill-down) עבור {symbol}...", parse_mode="Markdown").message_id
    try:
        res = supabase.table("trades").select("*").eq("symbol", symbol).execute()
        df = pd.DataFrame(res.data)
        pos_res = ec.get_open_positions_campaign(df)
        if not pos_res["ok"] or pos_res["data"].empty:
            bot.edit_message_text(f"❌ לא נמצאו פוזיציות פתוחות או קמפיינים פעילים עבור {symbol}.", chat_id, msg_id)
            return
        open_pos = pos_res["data"].iloc[0]
        entry, qty, sl = float(open_pos['price']), float(open_pos['quantity']), float(open_pos['stop_loss'])
        init_sl = float(open_pos['initial_stop'])
        setup, mgt_state, entry_date = open_pos['setup_type'], open_pos.get('management_state', 'full_position'), open_pos['entry_date']
        curr = ec.get_live_price(symbol)
        if curr is None: curr = entry
        
        account_settings = get_account_settings()
        acc_size, target_risk_usd, nav_stale_label = get_nav_and_risk(account_settings)
        weight_pct = ((curr * qty) / acc_size) * 100 if acc_size > 0 else 0
        spy_hist = ec.get_cached_history("SPY", "1y", "1d")
        
        base_price = open_pos.get('base_price', entry)
        base_qty = open_pos.get('base_qty', qty)
        
        init_sl_clean = init_sl if (init_sl > 0 and init_sl < base_price) else 0
        original_campaign_risk = (base_price - init_sl_clean) * base_qty if init_sl_clean > 0 else 0
        
        engine_res = ec.evaluate_position_engine(
            symbol=symbol, entry_price=entry, entry_date_str=entry_date, current_stop=sl, 
            setup_type=setup, mgt_state=mgt_state, weight_pct=weight_pct, total_r=0, 
            target_risk_usd=target_risk_usd, actual_risk_usd=original_campaign_risk, spy_hist=spy_hist
        )
        if not engine_res["ok"]:
            bot.edit_message_text(f"❌ שגיאת מנוע בחישוב {symbol}: {engine_res['error']}", chat_id, msg_id)
            return
        data = engine_res["data"]
        feats = data.get("features", {})
        
        sizing_str = f"ניהול: `{mgt_state}` | חשיפה: `{weight_pct:.1f}%`"
        if str(setup).upper() != "ALGO":
            if original_campaign_risk > 0 and data.get("sizing_status") != "✅ תקין":
                clean_sizing = data.get("sizing_status").replace('⚠️ ', '').replace('📉 ', '')
                sizing_str += f"\n⚖️ סטטוס סיכון: {clean_sizing}"
            elif original_campaign_risk == 0:
                sizing_str += f"\n⚠️ חסר סטופ התחלתי לחישוב בקרת סיכון."
            
        rep = f"{RTL}🔬 *דו\"ח מודיעין עומק (Drill-down) - {symbol}*\n\n"
        rep += f"*{symbol}* | 🏷️ {setup} | סטטוס: {data['status']}\n{sizing_str}\n〰️〰️〰️〰️〰️〰️〰️〰️〰️\n\n"
        rep += f"{RTL}📊 *פרופיל טכני:*\n"
        if feats.get('dist_12d') is not None: rep += f"• ימי פיזור (12 ימים): `{feats['dist_12d']}`\n"
        if feats.get('accum_10d') is not None: rep += f"• ימי איסוף (10 ימים): `{feats['accum_10d']}`\n"
        if feats.get('good_closes_10') is not None: rep += f"• סגירות חזקות מול חלשות: `{feats['good_closes_10']}` מול `{feats['bad_closes_10']}`\n"
        rep += f"\n{RTL}📈 *מטריצת כוח יחסי (Relative Strength):*\n"
        if feats.get('rs20_market') is not None:
            val = feats['rs20_market'] * 100
            rep += f"• מול השוק (SPY): {'🟢 מובילה' if val > 0 else '🔴 מפגרת'} ({val:+.1f}%)\n"
        sec_bundle = ec.get_sector_bundle(symbol)
        sec_etf = sec_bundle.get('sector_etf')
        if feats.get('rs20_stock_sector') is not None and sec_etf:
            val = feats['rs20_stock_sector'] * 100
            rep += f"• מול הסקטור ({sec_etf}): {'🟢 מובילה' if val > 0 else '🔴 מפגרת'} ({val:+.1f}%)\n"
        rep += f"\n{RTL}🌪️ *משטר תנודתיות (Volatility Regime):*\n"
        if feats.get('atr_regime') is not None:
            reg_val = feats['atr_regime']
            reg_text = "מתרחבת 📈" if reg_val > 1.2 else "מתכווצת 📉" if reg_val < 0.85 else "נורמלית ➖"
            rep += f"• יחס תנודתיות: `{reg_val:.2f}x` ({reg_text})\n"
        if feats.get('stretch_ma20_atr') is not None: rep += f"• מתיחות (ממרחק MA20): `{feats['stretch_ma20_atr']:.1f}` יחידות ATR\n"
        if data['issues']: rep += f"\n{RTL}⚠️ *אזהרות:* {', '.join(data['issues'])}\n"
        bot.edit_message_text(rep, chat_id, msg_id, parse_mode="Markdown")
    except Exception as e: bot.edit_message_text(f"❌ שגיאה בשליפת נתוני עומק: {e}", chat_id, msg_id)

@bot.callback_query_handler(func=lambda call: True)
def handle_queries(call):
    chat_id = call.message.chat.id
    data = call.data
    if data.startswith("devlog|"):
        bot.answer_callback_query(call.id)
        service_name = data.split("|", 1)[1]
        log_path = _DEV_LOG_FILES.get(service_name, "")
        lines = _read_last_log_lines(log_path, 50)
        # Telegram message limit: split if needed
        header = f"{RTL}📋 *לוגים — {service_name} (50 שורות אחרונות):*\n"
        body   = f"```\n{lines[-3600:]}\n```"
        try:
            bot.send_message(chat_id, header + body,
                             reply_markup=get_developer_menu(), parse_mode="Markdown")
        except Exception:
            bot.send_message(chat_id, header + lines[-3000:],
                             reply_markup=get_developer_menu())
        return
    if data.startswith("drill|"):
        symbol = data.split("|")[1]
        bot.answer_callback_query(call.id)
        handle_drilldown(chat_id, symbol)
        return
    if data == "start_trail_flow":
        if chat_id in user_state and 'temp_positions' in user_state[chat_id]:
            count = len(user_state[chat_id]['temp_positions'])
            bot.send_message(chat_id, f"🎯 *קידום סטופ:*\nהקלד את מספר הטרייד מהרשימה (1-{count}):\n(או שלח 'ביטול')", parse_mode="Markdown")
            user_state[chat_id]['action'] = 'select_trade_index'
        else: bot.send_message(chat_id, "⚠️ המידע פג תוקף. לחץ שוב על 'חדר מצב'.")
        bot.answer_callback_query(call.id)
    elif data == "cancel_action":
        bot.send_message(chat_id, "❌ הפעולה בוטלה.", reply_markup=get_main_menu())
        if chat_id in user_state: del user_state[chat_id]
        bot.answer_callback_query(call.id)
    elif data.startswith("risk_confirm|"):
        bot.answer_callback_query(call.id)
        parts = data.split("|")
        action = parts[1]
        rec_pct = float(parts[2])
        curr_pct = float(parts[3])
        account_settings = get_account_settings()
        nav, _, _ = get_nav_and_risk(account_settings)

        if action == "YES":
            success = are.update_risk_pct(rec_pct)
            are.mark_adherence(recommended_pct=rec_pct, actual_pct=rec_pct, followed=True)
            are.log_risk_journal({
                "direction": "up" if rec_pct > curr_pct else "down_fast",
                "current_risk_pct": curr_pct,
                "recommended_risk_pct": rec_pct,
                "action": "confirmed",
                "actual_pct_set": rec_pct,
                "nav": nav,
            })
            status = "✅" if success else "⚠️ שגיאת שמירה"
            try:
                bot.edit_message_text(
                    f"{RTL}{status} *סיכון עודכן ל-{rec_pct:.2f}%*\n"
                    f"{RTL}(${round(nav * rec_pct / 100):,.0f} לעסקה) — נשמר ביומן הסיכון.",
                    chat_id, call.message.message_id, parse_mode="Markdown"
                )
            except Exception:
                bot.send_message(chat_id, f"{status} סיכון עודכן ל-{rec_pct:.2f}%", parse_mode="Markdown")

        elif action == "NO":
            user_state[chat_id] = {
                "action": "risk_reject_reason",
                "rec_pct": rec_pct,
                "curr_pct": curr_pct,
                "original_msg_id": call.message.message_id,
            }
            try:
                bot.edit_message_text(
                    f"{RTL}❌ *דוחה שינוי סיכון*\n{RTL}המלצה: `{rec_pct:.2f}%` ← נדחתה\n\n{RTL}📝 חובה: הסבר את הסיבה (יירשם ביומן):",
                    chat_id, call.message.message_id, parse_mode="Markdown"
                )
            except Exception:
                bot.send_message(chat_id, f"{RTL}📝 *הסבר מדוע דחית:*", parse_mode="Markdown")

    elif data.startswith("runner_decision|"):
        bot.answer_callback_query(call.id)
        parts = data.split("|")
        action   = parts[1] if len(parts) > 1 else ""
        sym      = parts[2] if len(parts) > 2 else ""
        cid      = parts[3] if len(parts) > 3 else ""
        try: bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)
        except Exception: pass

        if action == "hold":
            _write_runner_decision(cid, "hold")
            if cid:
                try:
                    ts_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                    supabase.table("trades").update({"management_notes": f"Runner: להחזיק ({ts_str})"}).eq("campaign_id", cid).eq("side", "BUY").execute()
                except Exception: pass
            bot.send_message(chat_id, f"{RTL}✅ *{sym} — להחזיק*\nההחלטה נרשמה. Sentinel לא ישלח התראות Runner ל-24 שעות.", parse_mode="Markdown")

        elif action == "tighten":
            user_state[chat_id] = {"action": "tighten_stop", "sym": sym, "campaign_id": cid}
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("❌ ביטול", callback_data="cancel_action"))
            bot.send_message(chat_id, f"{RTL}🔒 *{sym} — הדקת סטופ*\nהזן את מחיר הסטופ החדש:", reply_markup=markup, parse_mode="Markdown")

        elif action == "partial":
            if cid:
                try:
                    ts_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                    supabase.table("trades").update({"management_notes": f"Runner: כוונת מימוש חלקי ({ts_str})"}).eq("campaign_id", cid).eq("side", "BUY").execute()
                except Exception: pass
            bot.send_message(chat_id, f"{RTL}📊 *{sym} — מימוש חלקי*\nהכוונה נרשמה. בצע את הפקודה ב-IBKR ועדכן במערכת לאחר ביצוע.", parse_mode="Markdown")

    elif data.startswith("v|"):
        bot.answer_callback_query(call.id)
        parts = data.split('|')
        try:
            t_id, field, val = parts[1], parts[2], parts[3]
            if field in ['quality', 'score']:
                supabase.table("trades").update({field: int(val)}).eq("trade_id", t_id).execute()
            elif field == 'initial_stop':
                supabase.table("trades").update({"initial_stop": float(val), "stop_loss": float(val)}).eq("trade_id", t_id).execute()
            elif field == 'stop_loss':
                supabase.table("trades").update({field: float(val)}).eq("trade_id", t_id).execute()
            else:
                save_val = "Skipped" if val == 'Skipped' else val
                supabase.table("trades").update({field: save_val}).eq("trade_id", t_id).execute()

            bot.delete_message(chat_id, call.message.message_id)
            get_next_missing(chat_id)
        except Exception as e: bot.send_message(chat_id, f"❌ *תקלה בעדכון:* {str(e)}", parse_mode="Markdown")

@bot.message_handler(content_types=['document'])
def handle_document_upload(message):
    chat_id = message.chat.id
    if user_state.get(chat_id, {}).get('action') != 'awaiting_ibkr_xml':
        return
    del user_state[chat_id]
    _process_uploaded_ibkr_xml(chat_id, message)


@bot.message_handler(func=lambda m: True, content_types=['text', 'photo'])
def handle_all_messages(message):
    chat_id = message.chat.id
    text = message.text if message.text else ""

    if text in ["ביטול", "cancel", "/cancel", "❌ ביטול"]:
        if chat_id in user_state: del user_state[chat_id]
        bot.send_message(chat_id, "❌ הפעולה בוטלה. חוזרים לתפריט הראשי.", reply_markup=get_main_menu())
        return

    # ── טיפול ב-state פעיל ─────────────────────────────────────────────
    active_state = user_state.get(chat_id, {})
    if active_state.get("action") == "risk_reject_reason":
        reason = text.strip()
        rec_pct = active_state["rec_pct"]
        curr_pct = active_state["curr_pct"]
        account_settings = get_account_settings()
        nav, _, _ = get_nav_and_risk(account_settings)
        are.mark_adherence(recommended_pct=rec_pct, actual_pct=curr_pct, followed=False, reason=reason)
        are.log_risk_journal({
            "direction": "up" if rec_pct > curr_pct else "down_fast",
            "current_risk_pct": curr_pct,
            "recommended_risk_pct": rec_pct,
            "action": "rejected",
            "reason": reason,
            "actual_pct_set": curr_pct,
            "nav": nav,
        })
        del user_state[chat_id]
        bot.send_message(
            chat_id,
            f"{RTL}📝 *הדחייה נרשמה ביומן הסיכון*\n{RTL}המלצה `{rec_pct:.2f}%` נדחתה.\n{RTL}סיבה: _{reason}_",
            reply_markup=get_main_menu(), parse_mode="Markdown"
        )
        return

    # ── תפריטים היררכיים ──────────────────────────────────────────────
    if text == "⬅️ חזרה לתפריט ראשי":
        if chat_id in user_state: del user_state[chat_id]
        bot.send_message(chat_id, f"{RTL}🏠 *תפריט ראשי*", reply_markup=get_main_menu(), parse_mode="Markdown")
        return

    if text == "📊 מצב תיק":
        bot.send_message(chat_id, f"{RTL}📊 *מצב תיק — בחר פעולה:*", reply_markup=get_portfolio_menu(), parse_mode="Markdown")
        return

    if text == "🔬 ניתוח":
        bot.send_message(chat_id, f"{RTL}🔬 *ניתוח — בחר פעולה:*", reply_markup=get_analysis_menu(), parse_mode="Markdown")
        return

    if text == "📚 יומן":
        bot.send_message(chat_id, f"{RTL}📚 *יומן — בחר פעולה:*", reply_markup=get_journal_menu(), parse_mode="Markdown")
        return

    if text == "🛠️ מפתח":
        bot.send_message(chat_id, f"{RTL}🛠️ *תפריט מפתח — כלי פיתוח ודיבאג*", reply_markup=get_developer_menu(), parse_mode="Markdown")
        return

    # ── Developer menu handlers ────────────────────────────────────────────────

    if text == "📡 IBKR Sync ידני":
        allowed, reason, state_dict = _dev_sync_check()
        if not allowed:
            bot.send_message(chat_id, f"{RTL}⛔ *Sync נחסם:*\n{RTL}{reason}",
                             reply_markup=get_developer_menu(), parse_mode="Markdown")
            return
        _dev_sync_record(state_dict)
        bot.send_message(
            chat_id,
            f"{RTL}📡 *IBKR Manual Sync — מתחיל...*\n"
            f"{RTL}תקבל עדכון ב-Telegram כשהסנכרון יסתיים (עד ~3 דקות).",
            reply_markup=get_developer_menu(), parse_mode="Markdown",
        )
        _bot_log(f"Manual IBKR sync triggered by {chat_id}")
        threading.Thread(target=_run_manual_sync_thread, args=(chat_id,), daemon=True).start()
        return

    if text == "📤 העלה דוח XML":
        user_state[chat_id] = {'action': 'awaiting_ibkr_xml'}
        bot.send_message(
            chat_id,
            f"{RTL}📤 *העלה דוח IBKR XML*\n"
            f"{RTL}שלח את קובץ ה-XML שהורדת מ-IBKR (Flex Query → Activity Flex Query → XML).\n\n"
            f"{RTL}לביטול שלח *ביטול*",
            reply_markup=types.ReplyKeyboardRemove(), parse_mode="Markdown",
        )
        return

    if text == "📊 תוצאת Sync אחרון":
        try:
            if not os.path.exists(MANUAL_RESULT_FILE):
                bot.send_message(chat_id, f"{RTL}⚪ אין תוצאת סנכרון ידני שמורה.",
                                 reply_markup=get_developer_menu(), parse_mode="Markdown")
                return
            r = json.load(open(MANUAL_RESULT_FILE))
            status   = r.get("status", "?")
            message  = r.get("message", "—")
            nav      = r.get("nav")
            ts       = r.get("triggered_at", "—")[:19]
            emoji    = "✅" if status == "success" else ("🚨" if status == "fatal" else "⚠️")
            nav_line = f"\n{RTL}NAV: `${nav:,.0f}`" if nav else ""
            bot.send_message(
                chat_id,
                f"{RTL}{emoji} *תוצאת Sync אחרון*\n"
                f"{RTL}סטטוס: `{status}`\n"
                f"{RTL}הודעה: {message}{nav_line}\n"
                f"{RTL}בוצע: `{ts}`",
                reply_markup=get_developer_menu(), parse_mode="Markdown",
            )
        except Exception as e:
            bot.send_message(chat_id, f"❌ שגיאה בקריאת תוצאה: {e}",
                             reply_markup=get_developer_menu(), parse_mode="Markdown")
        return

    if text == "📋 לוגים":
        # Inline keyboard to choose service
        kb = types.InlineKeyboardMarkup(row_width=1)
        for name in _DEV_LOG_FILES:
            kb.add(types.InlineKeyboardButton(f"📋 {name}", callback_data=f"devlog|{name}"))
        bot.send_message(chat_id, f"{RTL}📋 *לוגים — בחר שירות:*",
                         reply_markup=kb, parse_mode="Markdown")
        return

    if text == "🔄 Git Pull + Deploy":
        bot.send_message(chat_id, f"{RTL}🔄 *Git Pull — מריץ...*",
                         reply_markup=get_developer_menu(), parse_mode="Markdown")
        _bot_log(f"Git pull triggered by {chat_id}")
        try:
            result = subprocess.run(
                ["git", "-C", "/app", "pull"],
                capture_output=True, text=True, timeout=60,
            )
            stdout = result.stdout.strip()[-800:] or "(ריק)"
            stderr = result.stderr.strip()[-400:] or ""
            rc     = result.returncode
            status_icon = "✅" if rc == 0 else "❌"
            msg = (
                f"{RTL}{status_icon} *Git Pull — {'הצליח' if rc == 0 else 'נכשל'} (rc={rc})*\n"
                f"{RTL}```\n{stdout}\n```"
            )
            if stderr:
                msg += f"\n{RTL}⚠️ stderr:\n```\n{stderr}\n```"
            msg += (
                f"\n\n{RTL}🔄 *להפעיל מחדש את הקונטיינרים* הרץ על השרת:\n"
                f"`docker compose up -d --build`"
            )
            _bot_log(f"Git pull rc={rc}: {stdout[:200]}")
        except FileNotFoundError:
            msg = (
                f"{RTL}⚠️ *git לא מותקן בקונטיינר זה.*\n"
                f"{RTL}כדי לפרוס עדכון, הרץ על Orange Pi:\n"
                f"`cd ~/sentinel && git pull && docker compose up -d --build`"
            )
        except subprocess.TimeoutExpired:
            msg = f"{RTL}⏳ *Git pull פג timeout (60s).*"
        except Exception as e:
            msg = f"❌ שגיאה: {e}"
        bot.send_message(chat_id, msg, reply_markup=get_developer_menu(), parse_mode="Markdown")
        return

    if text == "⚙️ הצג Config":
        try:
            cfg_paths = ["/app/sentinel_config.json", "sentinel_config.json"]
            cfg = None
            for p in cfg_paths:
                if os.path.exists(p):
                    cfg = json.load(open(p))
                    break
            if cfg is None:
                bot.send_message(chat_id, f"{RTL}⚠️ sentinel_config.json לא נמצא.",
                                 reply_markup=get_developer_menu(), parse_mode="Markdown")
                return
            # Mask any token-like values for safety
            safe_cfg = {}
            for k, v in cfg.items():
                if any(s in k.lower() for s in ("token", "key", "secret", "password")):
                    safe_cfg[k] = "***"
                else:
                    safe_cfg[k] = v
            cfg_text = json.dumps(safe_cfg, indent=2, ensure_ascii=False)
            bot.send_message(
                chat_id,
                f"{RTL}⚙️ *sentinel_config.json:*\n```\n{cfg_text[:3000]}\n```",
                reply_markup=get_developer_menu(), parse_mode="Markdown",
            )
        except Exception as e:
            bot.send_message(chat_id, f"❌ שגיאה: {e}",
                             reply_markup=get_developer_menu(), parse_mode="Markdown")
        return

    if text == "🏥 בריאות מערכת":
        return bot.send_message(chat_id, _build_health_report(),
                                reply_markup=get_developer_menu())

    if text in ["❓ עזרה", "❓ פקודות מערכת", "/help"]:
        help_txt = (
            f"{RTL}🛡️ *Sentinel — מדריך פקודות*\n"
            f"{RTL}───────────────\n"
            f"{RTL}📊 *מצב תיק* — פוזיציות ומשטר שוק\n"
            f"{RTL}🔬 *ניתוח* — סקירת מניה ו-Trend Template\n"
            f"{RTL}📚 *יומן* — מילוי יומן וארכיון\n"
            f"{RTL}───────────────\n"
            f"{RTL}/portfolio — חדר מצב\n"
            f"{RTL}/trade SYMBOL — ניתוח עומק לפוזיציה\n"
            f"{RTL}/mentor SYMBOL — Trend Template מלא\n"
            f"{RTL}/analyze SYMBOL — ניתוח VCP מינרביני\n"
            f"{RTL}/next — יומן (הבא)\n"
            f"{RTL}/stats — סטטיסטיקת ציות להמלצות סיכון\n"
        )
        return bot.send_message(chat_id, help_txt, reply_markup=get_main_menu(), parse_mode="Markdown")

    if text in ["/stats", "📊 סטטיסטיקת ציות"]:
        stats = are.compute_adherence_stats()
        if not stats.get("ok"):
            bot.send_message(chat_id, f"⚪ {stats.get('message', 'שגיאה')}", parse_mode="Markdown")
            return
        last_str = " ".join(stats.get("last_actions", []))
        msg = (
            f"{RTL}📊 *סטטיסטיקת ציות — המלצות סיכון*\n"
            f"{RTL}───────────────\n"
            f"{RTL}סה\"כ המלצות: `{stats['total_recommendations']}`\n"
            f"{RTL}הוערכו: `{stats['evaluated']}`\n"
            f"{RTL}אושרו ✅: `{stats['followed']}`\n"
            f"{RTL}נדחו ❌: `{stats['not_followed']}`\n"
        )
        if stats["adherence_pct"] is not None:
            msg += f"{RTL}ציות כללי: `{stats['adherence_pct']:.0f}%`\n"
        if last_str:
            msg += f"{RTL}10 האחרונות: {last_str}"
        return bot.send_message(chat_id, msg, parse_mode="Markdown")

    if text in ["/health", "🏥 בריאות מערכת"]:
        return bot.send_message(chat_id, _build_health_report())

    if text == "🧠 ניתוח מינרביני מלא":
        bot.send_message(chat_id, f"{RTL}🧠 *ניתוח Trend Template מלא (8 קריטריונים):*\nהקלד סימול מניה (לדוגמה: AAPL):", parse_mode="Markdown")
        user_state[chat_id] = {'action': 'mentor_symbol'}
        return

    if text.startswith("/mentor ") or text.startswith("/mentor\n"):
        sym_raw = text.split(" ", 1)[-1].strip().upper()
        if sym_raw:
            _loading = bot.send_message(chat_id, f"⏳ מנתח Trend Template עבור {sym_raw}...", parse_mode="Markdown")
            tt_res = ec.compute_trend_template_full(sym_raw)
            report = tf.fmt_minervini_trend_template(sym_raw, tt_res)
            try: bot.delete_message(chat_id, _loading.message_id)
            except: pass
            bot.send_message(chat_id, report, reply_markup=get_analysis_menu(), parse_mode="Markdown")
        return

    if text.startswith("/analyze "):
        symbol = text.split(" ")[1].upper()
        bot.send_message(chat_id, f"⏳ מנתח נתונים עבור {symbol}...", parse_mode="Markdown")
        report_res = ec.get_minervini_analysis(symbol)
        report = report_res["data"][0] if report_res["ok"] else str(report_res.get("error", "Error")).replace("_", " ")
        bot.send_message(chat_id, report, parse_mode="Markdown")
        return

    if text == "🔬 סקירת מניה":
        bot.send_message(chat_id, "📈 *מנתח Trend Template:*\nאנא הקלד את סימול המניה לסריקה (לדוגמה: AAPL):", parse_mode="Markdown")
        user_state[chat_id] = {'action': 'analyze_symbol'}
        return

    if text in ["🔍 סריקת יומן (Backlog)", "/next", "📚 ניהול יומן (Backlog)"]: return get_next_missing(chat_id)

    if text in ["🧹 ארכיון עסקאות (Legacy)", "/clean"]:
        bot.send_message(chat_id, "🧹 *מבצע ניקוי היסטוריה (עסקאות מעל 30 יום בלבד)...*", parse_mode="Markdown")
        try:
            thirty_days_ago = (datetime.now() - pd.Timedelta(days=30)).strftime('%Y-%m-%d')
            res = supabase.table("trades").select("*").lt("trade_date", thirty_days_ago).execute()
            count = 0
            for t in res.data:
                needs_update = False
                upd = {}
                if t.get('setup_type') is None: upd['setup_type'] = "Legacy"; needs_update = True
                if t.get('quality') is None: upd['quality'] = -1; needs_update = True
                if t.get('side', '').upper() == 'BUY':
                    if t.get('initial_stop') in [None, 0]: upd['initial_stop'] = -1; upd['stop_loss'] = -1; needs_update = True
                if t.get('side', '').upper() == 'SELL':
                    if t.get('score') is None: upd['score'] = -1; needs_update = True
                    if t.get('image_url') is None: upd['image_url'] = "Skipped"; needs_update = True
                    if t.get('management_notes') is None: upd['management_notes'] = "Skipped"; needs_update = True
                if needs_update:
                    supabase.table("trades").update(upd).eq("trade_id", t['trade_id']).execute()
                    count += 1
            bot.send_message(chat_id, f"✅ ארכיון נקי! {count} עסקאות ישנות טופלו בהצלחה.", parse_mode="Markdown")
        except Exception as e:
            bot.send_message(chat_id, f"❌ שגיאה בניקוי הארכיון: {e}")
        return get_next_missing(chat_id)

    if text in ["❓ פקודות מערכת", "/help"]:
        return bot.send_message(chat_id, "🛡️ *מערכת הפיקוד (Sentinel Command)*\n\n/trade SYMBOL - צלילת עומק לפוזיציה\n/next - סריקת יומן\n/portfolio - חדר מצב\n/clean - מטאטא ארכיון (מוגן 30 יום)", parse_mode="Markdown")

    if text == "🌡️ משטר שוק וסיכונים":
        msg_id = bot.send_message(chat_id, "⏳ בודק דופק שוק...", parse_mode="Markdown").message_id
        try:
            spy_hist = ec.get_cached_history("SPY", "1y", "1d")
            qqq_hist = ec.get_cached_history("QQQ", "1y", "1d")
            regime = ec.compute_market_regime(spy_hist, qqq_hist)
            res = supabase.table("trades").select("*").execute()
            df = pd.DataFrame(res.data)
            pos_res = ec.get_open_positions_campaign(df)
            open_pos = pos_res["data"] if pos_res["ok"] else pd.DataFrame()
            account_settings = get_account_settings()
            acc_size, target_risk_usd_regime, nav_stale_label = get_nav_and_risk(account_settings)
            exp = {"ALGO": 0, "VCP": 0, "EP": 0, "OTHER": 0}
            if not open_pos.empty:
                for _, row in open_pos.iterrows():
                    sym, setup = row["symbol"], str(row["setup_type"]).upper()
                    curr = ec.get_live_price(sym) or float(row["price"])
                    val = curr * float(row["quantity"])
                    if setup in exp: exp[setup] += val
                    else: exp["OTHER"] += val
            total_exp = sum(exp.values())
            total_pct = (total_exp / acc_size) * 100 if acc_size > 0 else 0
            rep = tf.fmt_regime_report(regime, total_pct, exp["ALGO"], exp["VCP"], exp["EP"], acc_size)
            if nav_stale_label:
                rep += f"\n\n⚠️ _{nav_stale_label}_"
            # --- Adaptive Risk Block ---
            try:
                current_risk_pct = float(account_settings.get("risk_pct_input", 0.5))
                nav_for_risk = acc_size
                closed_camps = are.compute_closed_campaigns(df)
                risk_rec = are.compute_adaptive_risk(closed_camps, current_risk_pct, nav_for_risk)
                rep += tf.fmt_adaptive_risk_block(risk_rec)
            except Exception:
                pass
            bot.edit_message_text(rep, chat_id, msg_id, parse_mode="Markdown")
        except Exception as e: bot.edit_message_text(f"❌ תקלה בחישוב משטר שוק: {e}", chat_id, msg_id)
        return

    if text in ["📊 חדר מצב (פוזיציות)", "/portfolio"]:
        loading_msg = bot.send_message(chat_id, "⏳ *שואב נתונים ומרכיב דו\"ח...*", parse_mode="Markdown")
        try:
            res = supabase.table("trades").select("*").execute()
            df = pd.DataFrame(res.data)
            pos_res = ec.get_open_positions_campaign(df)
            if not pos_res["ok"]:
                try: bot.delete_message(chat_id, loading_msg.message_id)
                except: pass
                return bot.send_message(chat_id, f"❌ שגיאת תשתית במשיכת פוזיציות:\n`{pos_res['error']}`")
            open_pos = pos_res["data"]
            if open_pos.empty: 
                try: bot.delete_message(chat_id, loading_msg.message_id)
                except: pass
                return bot.send_message(chat_id, "✅ אין פוזיציות פתוחות במערכת.")

            account_settings = get_account_settings()
            acc_size, target_risk_usd, nav_stale_label = get_nav_and_risk(account_settings)
            spy_hist = ec.get_cached_history("SPY", "1y", "1d")
            
            user_state[chat_id] = {'temp_positions': open_pos.to_dict('records')}
            total_open_pnl = total_disc_pnl = total_algo_pnl = total_risk = total_realized_camp = 0
            total_exposure = total_disc_exposure = total_algo_exposure = 0
            total_locked_profit = total_giveback_risk = 0
            
            algo_count = 0
            active_symbols = []
            
            msg = f"{RTL}🔭 *חדר מצב - דו\"ח ריכוז פוזיציות:*\n\n"
            
            for i, row in enumerate(user_state[chat_id]['temp_positions'], 1):
                sym = row['symbol']
                active_symbols.append(sym)
                entry, sl, init_sl = row['price'], row['stop_loss'], row['initial_stop']
                setup, qty, init_qty = row['setup_type'], row['quantity'], row.get('initial_qty', row['quantity']) 
                realized_pnl, entry_date, mgt_state = row.get('realized_pnl', 0), row['entry_date'], row.get('management_state', 'full_position')
                
                add_on_count = row.get('add_on_count', 0)
                base_price = row.get('base_price', entry)
                base_qty = row.get('base_qty', init_qty)
                
                curr = ec.get_live_price(sym)
                if curr is None: curr = entry
                
                open_pnl_usd = (curr - entry) * qty
                pos_value = curr * qty
                total_pos_profit = open_pnl_usd + realized_pnl
                weight_pct = (pos_value / acc_size) * 100 if acc_size > 0 else 0
                
                init_sl_clean = init_sl if (init_sl > 0 and init_sl < base_price) else 0
                original_campaign_risk = (base_price - init_sl_clean) * base_qty if init_sl_clean > 0 else 0
                
                if sl > base_price: 
                    current_open_loss_risk = 0
                    locked_profit_usd = (sl - base_price) * qty
                    giveback_risk_usd = (curr - sl) * qty if curr > sl else 0
                else:
                    current_open_loss_risk = (base_price - sl) * qty if sl > 0 else 0
                    locked_profit_usd = 0
                    giveback_risk_usd = 0
                
                total_campaign_r = (total_pos_profit / target_risk_usd) if str(setup).upper() == 'ALGO' and target_risk_usd > 0 else ((total_pos_profit / original_campaign_risk) if original_campaign_risk > 0 else 0)
                open_r_val = (open_pnl_usd / target_risk_usd) if str(setup).upper() == 'ALGO' and target_risk_usd > 0 else ((open_pnl_usd / original_campaign_risk) if original_campaign_risk > 0 else 0)

                engine_res = ec.evaluate_position_engine(symbol=sym, entry_price=entry, entry_date_str=entry_date, current_stop=sl, setup_type=setup, mgt_state=mgt_state, weight_pct=weight_pct, total_r=total_campaign_r, target_risk_usd=target_risk_usd, actual_risk_usd=original_campaign_risk, spy_hist=spy_hist)
                if not engine_res["ok"]: status, action_short, trigger, issues_str, sizing_str, score, stage, suggested_stop, feats = ("❌ שגיאה", "שגיאה", engine_res["error"], "", "✅ תקין", None, "", sl, {})
                else:
                    e_data = engine_res["data"]
                    status, action_short, trigger = e_data['status'], e_data['action'], e_data['trigger']
                    sizing_str = e_data.get('sizing_status', "✅ תקין")
                    issues_str = f": {' | '.join(e_data['issues'])}" if e_data['issues'] else ""
                    score, stage, suggested_stop, feats = e_data['score'], e_data['stage'], e_data['suggested_stop'], e_data.get('features', {})
                
                total_open_pnl += open_pnl_usd
                total_realized_camp += realized_pnl
                total_exposure += pos_value
                total_locked_profit += locked_profit_usd
                total_giveback_risk += giveback_risk_usd
                
                try: days_held = (datetime.now() - pd.to_datetime(entry_date)).days if entry_date else 0
                except: days_held = 0
                pnl_icon = '🟢' if open_pnl_usd >= 0 else '🔴'
                
                qty_text = f"`{qty}`" + (f" (+חיזוק)" if add_on_count > 0 else "")
                entry_text = f"${entry:.2f}" + (f" (בסיס: ${base_price:.2f})" if add_on_count > 0 else "")

                if str(setup).upper() == 'ALGO':
                    algo_count += 1
                    total_algo_pnl += open_pnl_usd
                    total_algo_exposure += pos_value
                    open_r_str = f"`{open_r_val:.1f}R` *(Target Risk Base)*"
                    e_data = engine_res.get("data") or {}
                    risk_basis = e_data.get("risk_basis", "Target")
                    risk_vis = e_data.get("risk_visibility_score", 40)

                    msg += f"{RTL}*{i}. {sym}* | 🏷️ ALGO | 🟠 מנוהל חיצונית\n"
                    msg += f"{RTL}   ▸ ותק: `{days_held}` ימים | כמות: {qty_text}\n"
                    msg += f"{RTL}   ▸ כניסה: {entry_text} | נוכחי: `${curr:.2f}`\n"
                    msg += f"{RTL}   ▸ סטופ: מנוהל חיצונית | בסיס R: `{risk_basis}` | שקיפות סיכון: `{risk_vis}/100`\n"
                    msg += f"{RTL}   ▸ רווח צף: {pnl_icon} `${open_pnl_usd:.2f}` | כולל: `${total_pos_profit:.2f}`\n"
                    msg += f"{RTL}   ▸ חשיפה: `{weight_pct:.1f}%` מקרן הבסיס\n"
                    msg += f"{RTL}   ▸ Open R (צף): {open_r_str}\n"
                    msg += f"{RTL}   ▸ סטטוס שוק: {status}\n"
                    msg += f"{RTL}   ▸ פיקוח: `מידע בלבד — Sentinel אינה מנהלת יציאות אלגו`\n"
                else:
                    total_disc_pnl += open_pnl_usd
                    total_disc_exposure += pos_value
                    total_risk += current_open_loss_risk

                    msg += tf.fmt_position_card(
                        i=i, sym=sym, setup=setup, days_held=days_held,
                        curr=curr, entry=entry, open_pnl=open_pnl_usd,
                        pos_value=pos_value, weight_pct=weight_pct,
                        total_pos_profit=total_pos_profit,
                        total_campaign_r=total_campaign_r,
                        open_r_val=open_r_val, status=status,
                        action_short=action_short,
                        add_on_count=add_on_count, base_price=base_price,
                        locked_profit=locked_profit_usd,
                        giveback_risk=giveback_risk_usd,
                        capital_risk=current_open_loss_risk,
                    ) + "\n"
                    if original_campaign_risk > 0 and sizing_str != "✅ תקין":
                        clean_sizing = sizing_str.replace('⚠️ ', '').replace('📉 ', '')
                        msg += f"{RTL}   ▸ ⚖️ בקרת קמפיין: {clean_sizing}\n"
                    if total_campaign_r <= -1.25 and original_campaign_risk > 0:
                        msg += f"{RTL}   ▸ 🚨 בקרת ביצוע: חריגה מהסטופ! ({total_campaign_r:.1f}R)\n"
                    if trigger:
                        msg += f"{RTL}   ▸ טריגר ניהולי: `{trigger}`\n"

                rs_str = ""
                if feats and feats.get("rs20_market") is not None:
                    rm = feats["rs20_market"] * 100
                    rss = feats.get("rs20_stock_sector")
                    if rss is not None:
                        rs_str = f"{RTL}   ▸ כוח יחסי (RS): שוק {rm:+.1f}% | סקטור {rss * 100:+.1f}%\n"
                    else:
                        rs_str = f"{RTL}   ▸ כוח יחסי (RS): שוק {rm:+.1f}%\n"
                msg += rs_str + f"{RTL}〰️〰️〰️〰️〰️〰️〰️〰️〰️\n"

            total_weight = (total_exposure / acc_size) * 100 if acc_size > 0 else 0
            algo_cluster_pct = (total_algo_exposure / acc_size) * 100 if acc_size > 0 else 0
            total_pnl_icon = '🟢' if total_open_pnl >= 0 else '🔴'
            
            total_secured = total_realized_camp + total_locked_profit

            msg += f"{RTL}📊 *סיכום תיק הפיקוד:*\n"
            msg += f"{RTL}▸ סה\"כ רווח צף: {total_pnl_icon} `${total_open_pnl:,.2f}` (דיסק': `${total_disc_pnl:,.2f}`)\n"
            msg += f"{RTL}▸ סה\"כ סיכון הפסד הון (דיסק'): `${total_risk:,.2f}`\n"
            msg += f"{RTL}▸ רווח שמומש בעסקאות פתוחות: `${total_realized_camp:,.2f}`\n"
            msg += f"{RTL}▸ רווח נעול (Locked) בסטופים: `${total_locked_profit:,.2f}`\n"
            msg += f"{RTL}▸ סך הכל רווח מוגן (Secured): `${total_secured:,.2f}`\n"
            msg += f"{RTL}▸ סיכון ויתור רווח צף (Giveback): `${total_giveback_risk:,.2f}`\n"
            msg += f"{RTL}▸ חשיפה כללית: `{total_weight:.1f}%` מקרן הבסיס\n"
            if algo_count > 0:
                msg += f"\n{RTL}🤖 *בקרת אשכול אלגו:*\n{RTL}▸ חשיפה אלגו: `{algo_cluster_pct:.1f}%` מהקרן\n"

            # שורת coaching מינרביני
            spy_hist_caching = ec.get_cached_history("SPY", "1y", "1d")
            regime_for_coaching = ec.compute_market_regime(spy_hist_caching)
            regime_status_str = regime_for_coaching.get('data', {}).get('status', '') if regime_for_coaching.get('ok') else ''
            try:
                all_res = supabase.table("trades").select("campaign_id,pnl_usd,trade_date").execute()
                camp_all = pd.DataFrame(all_res.data)
                if not camp_all.empty and 'campaign_id' in camp_all.columns:
                    closed_cids = camp_all.groupby('campaign_id')['pnl_usd'].sum()
                    wins_c = (closed_cids > 0).sum()
                    wr_c = wins_c / len(closed_cids) if len(closed_cids) > 0 else 0
                else:
                    wr_c = 0
            except: wr_c = 0
            coaching_insights = ec.generate_minervini_coaching(
                win_rate=wr_c, expectancy_r=0, adj_rr=0,
                oversized_count=0, market_regime_status=regime_status_str,
                streak_losses=0, total_r_net=0
            )
            if coaching_insights:
                msg += f"\n{RTL}🎓 *מינרביני אומר:*\n"
                for ins in coaching_insights[:2]:  # מקסימום 2 insights בטלגרם
                    clean_ins = ins.replace('<b>', '*').replace('</b>', '*')
                    msg += f"{RTL}▸ {clean_ins}\n"

            # --- Adaptive Risk Recommendation ---
            try:
                current_risk_pct = float(account_settings.get("risk_pct_input", 0.5))
                closed_camps = are.compute_closed_campaigns(df)
                risk_rec = are.compute_adaptive_risk(closed_camps, current_risk_pct, acc_size)
                msg += tf.fmt_adaptive_risk_block(risk_rec)
            except Exception:
                pass

            if nav_stale_label:
                msg += f"\n\n{RTL}⚠️ _{nav_stale_label}_"

            try: bot.delete_message(chat_id, loading_msg.message_id)
            except: pass
            
            markup = types.InlineKeyboardMarkup(row_width=3)
            drill_btns = [types.InlineKeyboardButton(text=f"🔍 {s}", callback_data=f"drill|{s}") for s in active_symbols]
            markup.add(*drill_btns)
            markup.add(types.InlineKeyboardButton("🎯 הזן קידום סטופ", callback_data="start_trail_flow"))
            
            send_long_message(chat_id, msg, reply_markup=markup)
            
        except Exception as e:
            err_details = traceback.format_exc()
            b_ticks = "`" * 3
            try: bot.delete_message(chat_id, loading_msg.message_id)
            except: pass
            bot.send_message(chat_id, f"❌ תקלת מערכת בחדר המצב:\n`{e}`\n\n{b_ticks}\n{err_details[-500:]}\n{b_ticks}", parse_mode="Markdown")
            return

    if chat_id in user_state:
        state = user_state[chat_id]
        action = state.get('action')

        if action == 'analyze_symbol':
            symbol = text.strip().upper()
            bot.send_message(chat_id, f"⏳ מושך נתונים טכניים ומנתח את {symbol}...", parse_mode="Markdown")
            report_res = ec.get_minervini_analysis(symbol)
            report = report_res["data"][0] if report_res["ok"] else str(report_res.get("error", "Error")).replace("_", " ")
            bot.send_message(chat_id, report, reply_markup=get_analysis_menu(), parse_mode="Markdown")
            del user_state[chat_id]
            return

        if action == 'mentor_symbol':
            symbol = text.strip().upper()
            _loading = bot.send_message(chat_id, f"⏳ מנתח Trend Template מלא עבור {symbol}...", parse_mode="Markdown")
            tt_res = ec.compute_trend_template_full(symbol)
            report = tf.fmt_minervini_trend_template(symbol, tt_res)
            try: bot.delete_message(chat_id, _loading.message_id)
            except: pass
            bot.send_message(chat_id, report, reply_markup=get_analysis_menu(), parse_mode="Markdown")
            del user_state[chat_id]
            return

        if action == 'select_trade_index':
            try:
                idx = int(text) - 1
                positions = state['temp_positions']
                if 0 <= idx < len(positions):
                    selected = positions[idx]
                    state['selected_trade'] = selected
                    state['action'] = 'input_new_sl'
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("❌ ביטול", callback_data="cancel_action"))
                    bot.send_message(chat_id, f"✅ בחרת ב-*{selected['symbol']}*.\nמחיר כניסה: `${selected['price']:.2f}`\nסטופ נוכחי: `${selected['stop_loss']:.2f}`\n\n*הקלד את מחיר הסטופ החדש:*", reply_markup=markup, parse_mode="Markdown")
                else: bot.send_message(chat_id, f"❌ מספר לא תקין. בחר בין 1 ל-{len(positions)}.")
            except: bot.send_message(chat_id, "❌ נא להזין מספר בלבד.")
            return

        elif action == 'tighten_stop':
            try:
                new_sl = float(text)
                sym_ts  = state.get('sym', '')
                cid_ts  = state.get('campaign_id', '')
                if cid_ts:
                    supabase.table("trades").update({"stop_loss": new_sl}).eq("campaign_id", cid_ts).eq("side", "BUY").execute()
                    bot.send_message(chat_id, f"{RTL}🔒 *סטופ עודכן — {sym_ts}*\nסטופ חדש: `${new_sl:.2f}`", reply_markup=get_main_menu(), parse_mode="Markdown")
                else:
                    bot.send_message(chat_id, "❌ תקלת מערכת: לא נמצא campaign_id.")
                del user_state[chat_id]
            except: bot.send_message(chat_id, "❌ מחיר לא תקין. נא להזין מספר (למשל 150.50).")
            return

        elif action == 'initial_stop':
            try:
                new_sl = float(text)
                trade_id = state.get('t_id')
                if trade_id:
                    supabase.table("trades").update({"initial_stop": new_sl, "stop_loss": new_sl}).eq("trade_id", trade_id).execute()
                    bot.send_message(chat_id, f"🚀 *הסטופ ההתחלתי נשמר במערכת: ${new_sl:.2f}*", parse_mode="Markdown")
                del user_state[chat_id]
                get_next_missing(chat_id)
            except: bot.send_message(chat_id, "❌ מחיר לא תקין. נא להזין מספר בלבד (למשל 150.50).")
            return

        elif action == 'input_new_sl':
            try:
                new_sl = float(text)
                trade = state['selected_trade']
                cid = trade.get('campaign_id')
                if cid:
                    supabase.table("trades").update({"stop_loss": new_sl}).eq("campaign_id", cid).eq("side", "BUY").execute()
                    bot.send_message(chat_id, f"🚀 *הסטופ עודכן בהצלחה!*\nנכס: `{trade['symbol']}`\nסטופ מעודכן ל: `${new_sl:.2f}`\nפקודות הקנייה בקמפיין עודכנו.", reply_markup=get_main_menu(), parse_mode="Markdown")
                else: bot.send_message(chat_id, "❌ תקלת מערכת: לא נמצא מזהה קמפיין לעסקה זו.")
                del user_state[chat_id]
            except: bot.send_message(chat_id, "❌ מחיר לא תקין. נא להזין מספר.")
            return

        t_id = state.get('t_id')
        if action == 'image' and t_id:
            if message.content_type == 'photo':
                bot.send_message(chat_id, "🚨 *שגיאה:* יש לשלוח לינק מ-TradingView, לא העלאת תמונה.", parse_mode="Markdown")
                return
            supabase.table("trades").update({"image_url": text.strip()}).eq("trade_id", t_id).execute()
            bot.send_message(chat_id, "✅ תמונה נשמרה.", parse_mode="Markdown")
            del user_state[chat_id]
            get_next_missing(chat_id)
            return

        if action == 'management_notes' and t_id:
            if message.content_type != 'text':
                bot.send_message(chat_id, "🚨 שגיאה: יש לשלוח הערת טקסט בלבד.", parse_mode="Markdown")
                return
            supabase.table("trades").update({"management_notes": text.strip()}).eq("trade_id", t_id).execute()
            bot.send_message(chat_id, "✅ תובנות הניהול נשמרו ביומן המערכת.", parse_mode="Markdown")
            del user_state[chat_id]
            get_next_missing(chat_id)
            return

    bot.send_message(chat_id, "🎯 *Sentinel Standby*\nמערכת מוכנה לפעולה. בחר מהתפריט למטה:", reply_markup=get_main_menu(), parse_mode="Markdown")

if __name__ == "__main__":
    _bot_log("Sentinel Telegram Bot — started")
    if ADMIN_ID:
        try:
            bot.send_message(
                ADMIN_ID,
                "🛡️ *Sentinel Monitoring: ONLINE*\n"
                "v3.7 — תפריט מפתח פעיל (🛠️ מפתח).",
                reply_markup=get_main_menu(), parse_mode="Markdown",
            )
        except:
            pass
    bot.infinity_polling()
