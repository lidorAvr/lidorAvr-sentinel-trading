"""
System health check for Sentinel Trading.

build_health_report() runs 14 data-integrity checks and returns a
Telegram-formatted Hebrew/RTL string. No bot or Telegram dependency —
the caller is responsible for sending the result.
"""
import os
import json
import glob
from datetime import datetime
import pandas as pd
import engine_core as ec
from bot_core import supabase, RTL
from bot_helpers import get_account_settings


def build_health_report() -> str:
    """Run 13 health checks and return a formatted RTL Hebrew report."""
    checks = []
    SEP = "───────────────"

    def ok(msg):   checks.append(f"✅ {msg}")
    def warn(msg): checks.append(f"⚠️ {msg}")
    def bad(msg):  checks.append(f"🔴 {msg}")

    # 1. IBKR Sync Status
    try:
        ss = json.load(open("/app/ibkr_sync_state.json"))
        sd = ss.get("sync_date", "—")
        today = datetime.now().strftime("%Y-%m-%d")
        ok(f"IBKR Sync — {sd}") if sd == today else warn(f"IBKR Sync — אחרון: {sd}")
    except Exception:
        warn("IBKR Sync — קובץ state לא נמצא (טרם רץ?)")

    # 2. IBKR Reports archive
    reports = sorted(glob.glob("/app/ibkr_reports/ibkr_*.xml"))
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
        cfg = get_account_settings()
        rp = float(cfg.get("risk_pct_input", 0))
        ok(f"Risk Config — {rp:.2f}%") if 0.2 <= rp <= 3.0 else warn(f"Risk Config — {rp:.2f}% (מחוץ לטווח 0.2–3%)")
    except Exception:
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
            if ms.empty:
                ok("Missing Stops — אין")
            else:
                warn(f"Missing Stops — {len(ms)} שורות ({syms})")
                # Sprint-12 / Mark §4 — explicit non-numeric data-hygiene
                # NOTICE (VERBATIM from MARK_SPRINT12_RULINGS.md §4). It is
                # NOT a task, NEVER counted, NO fabricated stop — read-only
                # over the SAME existing check (no new query/math). The
                # count+symbols are a factual hygiene readout Mark explicitly
                # permits (honest, not a fabricated metric).
                checks.append(
                    f"‏⚠️ נתוני סיכון חסרים: {len(ms)} רשומות ({syms})."
                )
                checks.append(
                    "‏השלם entry/stop כדי שייכללו. "
                    "(אינו משימה, אינו נספר בסטטיסטיקה.)"
                )
        else:
            warn("Missing Stops — לא נבדק (אין נתונים)")
    except Exception:
        warn("Missing Stops — לא נבדק")

    # 7. Null campaign_ids
    try:
        res3 = supabase.table("trades").select("trade_id,campaign_id").execute()
        df_c = pd.DataFrame(res3.data if res3.data else [])
        null_camps = df_c[df_c["campaign_id"].isnull()] if not df_c.empty else pd.DataFrame()
        ok("Campaign IDs — כולם מלאים") if null_camps.empty else warn(f"Campaign IDs — {len(null_camps)} שורות ללא campaign_id")
    except Exception:
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
    except Exception:
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
    except Exception:
        warn("Risk Monitor State — קובץ לא נמצא (עדיין לא רץ?)")

    # 13. Adaptive Risk Journal
    try:
        rj = json.load(open("risk_recommendations.json"))
        rec_count = len(rj) if isinstance(rj, list) else 0
        ok(f"Risk Journal — {rec_count} המלצות")
    except Exception:
        warn("Risk Journal — קובץ לא נמצא (טרם נוצר)")

    # 14. audit_log table accessible
    # Sprint 7 #4: audit_logger fails-open, so missing migration 002 is
    # silent. This check surfaces it before compliance needs the trail.
    try:
        supabase.table("audit_log").select("id").limit(1).execute()
        ok("Audit Log — טבלה נגישה")
    except Exception as e:
        msg = str(e)[:50]
        if "does not exist" in msg.lower() or "schema cache" in msg.lower():
            bad("Audit Log — טבלה חסרה (החל migration 002_audit_log.sql)")
        else:
            warn(f"Audit Log — שגיאת גישה: {msg}")

    total  = len(checks)
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
