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
import state_io
import telegram_formatters as tf
from bot_core import supabase, RTL
from bot_helpers import get_account_settings


# Sprint-30 G4 — doubled status-glyph fix (R10/F7, presentation-only).
# `engine_core.get_nav_with_freshness()` returns a `freshness_label` that
# ALREADY begins with its OWN status emoji (`✅`/`🟡`/🟠`/`🔴`/`⚠️` —
# engine_core.py:1600,1613-1634; engine_core is BYTE-LOCKED, consumed only).
# `ok()/warn()/bad()` then PREPEND a second emoji ⇒ `✅ ✅ NAV …`,
# `🔴 🟠 NAV …`, `⚠️ 🟠 NAV …` — a doubled glyph whose two halves can even
# DISAGREE (wrapper severity from is_stale/is_critical routing vs the label's
# own leading glyph). Fix is in bot_health.py ONLY: strip a leading status
# glyph from any msg before the wrapper prefixes the ONE authoritative glyph,
# so every freshness state (fresh/stale/critical/unknown/manual/fallback)
# renders exactly one correct, non-disagreeing status glyph. Zero semantic
# change — the freshness ROUTING (bad/warn/ok) is unchanged and remains the
# single source of the displayed severity.
_STATUS_GLYPHS = ("✅", "⚠️", "🔴", "🟠", "🟡", "🚨")


def _strip_leading_status_glyph(msg: str) -> str:
    """Remove a single leading status emoji (+ its following space) from a
    check message so the ok()/warn()/bad() wrapper supplies exactly ONE
    authoritative glyph. Idempotent and safe for messages with no leading
    glyph (the common case — returned unchanged)."""
    s = str(msg)
    for g in _STATUS_GLYPHS:
        if s.startswith(g):
            return s[len(g):].lstrip(" ")
    return s


def build_health_report() -> str:
    """Run 13 health checks and return a formatted RTL Hebrew report."""
    checks = []
    SEP = "───────────────"

    # G4: strip any glyph the message already carries (e.g. the NAV
    # freshness_label) BEFORE prefixing — never double-prefix; the wrapper's
    # single glyph (driven by the freshness routing below) is authoritative.
    def ok(msg):   checks.append(f"✅ {_strip_leading_status_glyph(msg)}")
    def warn(msg): checks.append(f"⚠️ {_strip_leading_status_glyph(msg)}")
    def bad(msg):  checks.append(f"🔴 {_strip_leading_status_glyph(msg)}")

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
        res2 = supabase.table("trades").select(
            "symbol,stop_loss,quantity,side,campaign_id"
        ).execute()
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
                # permits (honest, not a fabricated metric). Mark §2 :71-72
                # requires THIS verbatim text stays for the closed/legacy
                # subset — kept unchanged below.
                checks.append(
                    f"‏⚠️ נתוני סיכון חסרים: {len(ms)} רשומות ({syms})."
                )
                checks.append(
                    "‏השלם entry/stop כדי שייכללו. "
                    "(אינו משימה, אינו נספר בסטטיסטיקה.)"
                )
                # Sprint-13 / Mark §2 — READ-ONLY split-label. Derive the
                # OPEN-campaign set with the engine's EXISTING net-qty>0.001
                # rule (no new math: signed-quantity sum per campaign, the
                # same rule engine_core.get_open_positions_campaign:473-514
                # already uses). Then label open (→ existing journal-backlog,
                # founder-typed real stop only, never fabricated) vs closed/
                # archived (→ already-gated /clean hygiene). No stat, no $/R,
                # no fabricated stop; no new ruleset key (drift test green).
                try:
                    qty_all = pd.to_numeric(
                        df_h.get("quantity"), errors="coerce"
                    ).fillna(0)
                    cid_all = df_h.get("campaign_id")
                    net_by_cid: dict = {}
                    for cid, q in zip(cid_all, qty_all):
                        if cid is None or (isinstance(cid, float) and pd.isna(cid)):
                            continue
                        net_by_cid[cid] = net_by_cid.get(cid, 0.0) + float(q)
                    open_cids = {
                        c for c, n in net_by_cid.items() if n > 0.001
                    }
                    split = tf.classify_missing_stops(
                        ms.to_dict("records"), open_cids
                    )
                    label = tf.fmt_missing_stops_split_label(split)
                    if label:
                        for ln in label.split("\n"):
                            checks.append(ln)
                except Exception:
                    # Split-label is best-effort; the verbatim S12 notice
                    # above is the guaranteed honest surface.
                    pass
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
        # Sprint 14: state file relocated to the /app/state named volume
        # (state_io.RM_STATE_FILE) — read-only health probe follows the
        # single shared constant.
        rm = json.load(open(state_io.RM_STATE_FILE))
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
