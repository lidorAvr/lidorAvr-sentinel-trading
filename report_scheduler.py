"""
report_scheduler.py — standalone reporting service.
Weekly: every Saturday at 08:30 Israel time.
Monthly: 1st of each month at 08:40 Israel time.
Runs as a separate Docker service; never touches telegram_bot.py or main.py.
"""
import os
import json
import time
import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional

ISRAEL_TZ   = ZoneInfo("Asia/Jerusalem")
LOG_FILE    = "/app/logs/sentinel_report.log"
LOG_MAX_LINES = 2000

STATE_FILE       = "/app/report_state/scheduler_state.json"
LOOP_SEC         = 60
_HEARTBEAT_DIR   = "/app/state"


def _touch_heartbeat(name: str) -> None:
    """Write current timestamp to /app/state/{name}_last_cycle so healthchecks can verify liveness."""
    try:
        os.makedirs(_HEARTBEAT_DIR, exist_ok=True)
        path = os.path.join(_HEARTBEAT_DIR, f"{name}_last_cycle")
        with open(path, "w") as fh:
            fh.write(str(time.time()))
    except Exception:
        pass

# Schedule: (weekday, hour, minute) — weekday 5 = Saturday (Python: Mon=0, Sun=6)
_WEEKLY_WEEKDAY = 5
_WEEKLY_HOUR    = 8
_WEEKLY_MINUTE  = 30
_MONTHLY_DAY    = 1
_MONTHLY_HOUR   = 8
_MONTHLY_MINUTE = 40


# ── Logging ────────────────────────────────────────────────────────────────────

def log(msg: str):
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] report_scheduler: {msg}"
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        if random.random() < 0.05:
            lines = open(LOG_FILE, encoding="utf-8").readlines()
            if len(lines) > LOG_MAX_LINES:
                with open(LOG_FILE, "w", encoding="utf-8") as f:
                    f.writelines(lines[-LOG_MAX_LINES:])
    except Exception:
        pass


# ── Scheduler state ────────────────────────────────────────────────────────────

def _load_state() -> dict:
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_state(state: dict):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"ERROR saving state: {e}")


def _already_ran(state: dict, key: str, today_str: str) -> bool:
    """Return True if we already ran report type `key` for `today_str`."""
    return state.get(key) == today_str


def _mark_ran(state: dict, key: str, today_str: str):
    state[key] = today_str
    _save_state(state)


# ── Supabase data pull ─────────────────────────────────────────────────────────

def _fetch_trades_df(period_start: datetime, period_end: datetime):
    """
    Pull trades from Supabase for the given period (with a 4-week lookback for
    open positions that closed within the period).
    Returns a pandas DataFrame or None on failure.
    """
    try:
        import pandas as pd
        from dotenv import load_dotenv
        from supabase import create_client

        load_dotenv()
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_KEY", "")
        if not url or not key:
            log("ERROR: SUPABASE_URL or SUPABASE_KEY not set")
            return None

        sb = create_client(url, key)
        lookback = period_start - timedelta(weeks=8)
        lookback_str = lookback.strftime("%Y-%m-%d")
        period_end_str = period_end.strftime("%Y-%m-%d")

        resp = (sb.table("trades")
                .select("*")
                .gte("trade_date", lookback_str)
                .lte("trade_date", period_end_str)
                .order("trade_date", desc=False)
                .execute())

        if not resp.data:
            return pd.DataFrame()
        return pd.DataFrame(resp.data)
    except Exception as e:
        log(f"ERROR fetching trades: {e}")
        return None


# ── Period helpers ─────────────────────────────────────────────────────────────

def _weekly_period(ref: datetime):
    """Return (period_start, period_end) for the week ending Saturday `ref`.
    period_start = previous Sunday 00:00, period_end = Saturday 23:59:59."""
    # ref.weekday() == 5 (Saturday)
    period_end   = ref.replace(hour=23, minute=59, second=59, microsecond=0)
    period_start = (ref - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
    return period_start, period_end


def _monthly_period(ref: datetime):
    """Return (period_start, period_end) for the previous calendar month."""
    first_of_this = ref.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_of_prev  = first_of_this - timedelta(seconds=1)
    first_of_prev = last_of_prev.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return first_of_prev, last_of_prev


def _build_system_health() -> dict:
    """Quick best-effort health snapshot for report context."""
    sync_ok = os.path.exists("/app/ibkr_last_sync_result.json")
    try:
        with open("/app/ibkr_last_sync_result.json") as f:
            last = json.load(f)
        sync_label = f"✅ Sync {last.get('status','?')} — {last.get('message','')[:60]}"
    except Exception:
        sync_label = "⚠️ Sync — אין מידע זמין"

    return {
        "sync_status": sync_label,
        "risk_monitor_status": "✅ Risk Monitor פעיל",
        "report_service_status": "✅ Report Service פעיל",
    }


def _compute_risk_rec(df, account: dict) -> dict:
    """
    Best-effort adaptive-risk computation for the scheduled summary heat
    thermometer. Returns the same dict shape as
    adaptive_risk_engine.compute_adaptive_risk; on any failure (import error,
    empty df, <3 closed campaigns) returns {ok: False, ...} which the
    formatter renders as "אין מספיק נתונים".
    """
    try:
        from adaptive_risk_engine import compute_closed_campaigns, compute_adaptive_risk
        closed = compute_closed_campaigns(df) if df is not None and not df.empty else []
        risk_pct = float(account.get("risk_pct_input", 0.5))
        nav      = float(account.get("nav", 0))
        return compute_adaptive_risk(closed, risk_pct, nav)
    except Exception as e:
        return {"ok": False, "error": "compute_failed", "message": str(e)}


# ── Report runners ─────────────────────────────────────────────────────────────

def _run_weekly(now: datetime):
    log("Starting weekly report generation")
    try:
        import account_state as acc_mod
        from analytics_engine import (compute_period_analytics,
                                       compute_trader_development_score,
                                       compute_period_comparison,
                                       compute_verdict)
        from report_snapshot_store import save as snap_save, load_previous
        from report_renderer import render_weekly, build_summary_text
        from report_delivery import deliver_report

        period_start, period_end = _weekly_period(now)
        log(f"Weekly period: {period_start.date()} → {period_end.date()}")

        account = acc_mod.load()
        df = _fetch_trades_df(period_start, period_end)

        analytics   = compute_period_analytics(df, period_start, period_end, account)
        dev_data    = compute_trader_development_score(analytics)
        prev_snap   = load_previous("weekly", period_start)
        comparison  = compute_period_comparison(analytics, prev_snap["analytics"]) if prev_snap else None
        health      = _build_system_health()

        coaching = _weekly_coaching_insights(analytics)

        pdf_path = render_weekly(
            analytics=analytics,
            account_state=account,
            period_start=period_start,
            period_end=period_end,
            comparison=comparison,
            dev_score_data=dev_data,
            system_health=health,
            coaching_insights=coaching,
            risk_adherence_rate=analytics.get("risk_adherence_rate"),
        )

        snap_save("weekly", period_start, period_end, analytics, account, pdf_path)

        period_label = f"{period_start.strftime('%d/%m')}–{period_end.strftime('%d/%m/%Y')}"
        risk_rec     = _compute_risk_rec(df, account)
        summary_text = build_summary_text(analytics, period_label, "weekly", risk_rec=risk_rec)
        caption      = f"📊 Sentinel Weekly Report | {period_label}"

        token   = os.environ.get("TELEGRAM_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            log("ERROR: TELEGRAM_TOKEN or TELEGRAM_CHAT_ID not configured — skipping delivery")
            return

        result = deliver_report(pdf_path, summary_text, caption, chat_id, token)
        log(f"Weekly delivery: summary={result['summary_ok']}, pdf={result['pdf_ok']}")

    except Exception as e:
        import traceback
        log(f"ERROR in weekly report: {e}\n{traceback.format_exc()}")
        _notify_error("שגיאה בדוח שבועי", str(e))


def _run_monthly(now: datetime):
    log("Starting monthly report generation")
    try:
        import account_state as acc_mod
        from analytics_engine import (compute_period_analytics,
                                       compute_trader_development_score,
                                       compute_period_comparison)
        from report_snapshot_store import save as snap_save, load_previous, load_recent
        from report_renderer import render_monthly, build_summary_text
        from report_delivery import deliver_report

        period_start, period_end = _monthly_period(now)
        log(f"Monthly period: {period_start.date()} → {period_end.date()}")

        account = acc_mod.load()
        df = _fetch_trades_df(period_start, period_end)

        analytics   = compute_period_analytics(df, period_start, period_end, account)
        dev_data    = compute_trader_development_score(analytics)
        prev_snap   = load_previous("monthly", period_start)
        comparison  = compute_period_comparison(analytics, prev_snap["analytics"]) if prev_snap else None
        health      = _build_system_health()
        coaching    = _monthly_coaching_insights(analytics)
        weekly_snaps = load_recent("weekly", n=5)
        weekly_breakdown = _build_weekly_breakdown(weekly_snaps, period_start, period_end)

        pdf_path = render_monthly(
            analytics=analytics,
            account_state=account,
            period_start=period_start,
            period_end=period_end,
            comparison=comparison,
            dev_score_data=dev_data,
            system_health=health,
            coaching_insights=coaching,
            risk_adherence_rate=analytics.get("risk_adherence_rate"),
            weekly_breakdown=weekly_breakdown,
        )

        snap_save("monthly", period_start, period_end, analytics, account, pdf_path)

        month_names = ["ינואר","פברואר","מרץ","אפריל","מאי","יוני",
                       "יולי","אוגוסט","ספטמבר","אוקטובר","נובמבר","דצמבר"]
        period_label = f"{month_names[period_start.month - 1]} {period_start.year}"
        risk_rec     = _compute_risk_rec(df, account)
        summary_text = build_summary_text(analytics, period_label, "monthly", risk_rec=risk_rec)
        caption      = f"📊 Sentinel Monthly Report | {period_label}"

        token   = os.environ.get("TELEGRAM_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            log("ERROR: TELEGRAM_TOKEN or TELEGRAM_CHAT_ID not configured — skipping delivery")
            return

        result = deliver_report(pdf_path, summary_text, caption, chat_id, token)
        log(f"Monthly delivery: summary={result['summary_ok']}, pdf={result['pdf_ok']}")

    except Exception as e:
        import traceback
        log(f"ERROR in monthly report: {e}\n{traceback.format_exc()}")
        _notify_error("שגיאה בדוח חודשי", str(e))


# ── Coaching helpers ───────────────────────────────────────────────────────────

def _weekly_coaching_insights(a: dict) -> list:
    insights = []
    if a.get("win_rate", 0) >= 0.6 and a.get("expectancy_r", 0) >= 0.5:
        insights.append("שבוע מצוין! ה-Win Rate וה-Expectancy שניהם מעל הסף. שמור על הסלקטיביות.")
    elif a.get("expectancy_r", 0) < 0:
        insights.append(
            f"Expectancy שלילי ({a['expectancy_r']:+.2f}R) — בדוק אם ה-setups שאתה לוקח "
            "עומדים בקריטריוני Minervini. איכות על כמות."
        )
    if a.get("missing_stop_rate", 0) > 0.15:
        insights.append(
            f"{a['missing_stop_rate']*100:.0f}% מהעסקאות חסרות Initial Stop — "
            "זוהי הפרה של ה-risk protocol. אין כניסה בלי סטופ."
        )
    if a.get("oversized_rate", 0) > 0.20:
        insights.append(
            f"{a['oversized_rate']*100:.0f}% מהפוזיציות Oversized (>125% Target Risk). "
            "תחשב מחדש sizing לפני כניסה."
        )
    if not insights:
        insights.append("התהליך השבועי תקין — המשך לפעול לפי הפרוטוקול.")
    return insights


def _monthly_coaching_insights(a: dict) -> list:
    insights = []
    dev = a.get("dev_score", 0) or 0
    if dev >= 80:
        insights.append(f"ציון פיתוח מעולה ({dev}/100) — אתה פועל בעקביות ברמה גבוהה.")
    elif dev < 50:
        insights.append(
            f"ציון פיתוח נמוך ({dev}/100) — יש לשפר משמעת תהליך ואיכות ה-edge. "
            "קרא שוב את כללי ה-Minervini ויישם."
        )

    import math as _math
    pf = a.get("profit_factor") or 0  # None (no losses, loaded from snapshot) → 0
    pf_display = "∞" if isinstance(pf, float) and _math.isinf(pf) else f"{pf:.2f}"
    if pf >= 2.0:  # True for math.inf; False for 0 or None-coerced-to-0
        insights.append(f"Profit Factor של {pf_display} — המערכת עובדת. אל תשנה setups שעובדים.")
    elif pf < 1.0 and a.get("campaigns_closed", 0) > 5:
        insights.append(
            f"Profit Factor מתחת ל-1 ({pf_display}) — ה-system במצב הפסד. "
            "שקול הפחתת גודל עד שה-edge יתאושש."
        )

    if not insights:
        insights.append("חודש סביר — תמשיך לעקוב אחרי הפרמטרים ולשפר בהדרגה.")
    return insights


def _build_weekly_breakdown(weekly_snaps: list, period_start: datetime, period_end: datetime) -> list:
    """Filter weekly snapshots that fall within the monthly period."""
    result = []
    for snap in weekly_snaps:
        try:
            ps = datetime.fromisoformat(snap["period_start"])
            pe = datetime.fromisoformat(snap["period_end"])
            if ps >= period_start and pe <= period_end:
                a = snap.get("analytics", {})
                result.append({
                    "label":     f"{ps.strftime('%d/%m')}–{pe.strftime('%d/%m')}",
                    "campaigns": a.get("campaigns_closed", 0),
                    "net_r":     a.get("total_r_net", 0),
                    "win_rate":  a.get("win_rate", 0),
                })
        except Exception:
            continue
    return result


# ── Error notification ─────────────────────────────────────────────────────────

def _notify_error(subject: str, detail: str):
    try:
        import requests as req
        token   = os.environ.get("TELEGRAM_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if token and chat_id:
            text = f"🔴 *{subject}*\n`{detail[:300]}`"
            req.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=10,
            )
    except Exception:
        pass


# ── Main loop ──────────────────────────────────────────────────────────────────

def main():
    log("Report scheduler started")
    state = _load_state()

    while True:
        try:
            now   = datetime.now(ISRAEL_TZ)
            today = now.strftime("%Y-%m-%d")

            # Weekly: Saturday at 08:30
            if (now.weekday() == _WEEKLY_WEEKDAY
                    and now.hour == _WEEKLY_HOUR
                    and now.minute >= _WEEKLY_MINUTE
                    and not _already_ran(state, "weekly", today)):
                _mark_ran(state, "weekly", today)
                _run_weekly(now)

            # Monthly: 1st of month at 08:40
            elif (now.day == _MONTHLY_DAY
                    and now.hour == _MONTHLY_HOUR
                    and now.minute >= _MONTHLY_MINUTE
                    and not _already_ran(state, "monthly", today)):
                _mark_ran(state, "monthly", today)
                _run_monthly(now)

        except Exception as e:
            log(f"ERROR in main loop: {e}")

        _touch_heartbeat("report_scheduler")
        time.sleep(LOOP_SEC)


if __name__ == "__main__":
    main()
