"""
period_data_probe.py — Sprint-21 WS-A: live, PURE READ-ONLY data-delivery probe.

WHY (DEC-20260516-018 UPDATE; MARK_SPRINT21_RULINGS.md §WS-A): the engine is
PROVEN correct on the founder's real rows (tests/test_real_data_april_
regression.py). Production "0 קמפיינים" is a DATA-DELIVERY gap, not a logic
defect. This probe localizes that gap by re-running the EXACT live read path
(`report_scheduler._fetch_trades_df`) for BOTH on-demand windows and reporting,
honestly, what the real pipeline yields — distinguishing "fetch failed / empty
input" from "fetched N rows, 0 closed in window" (#1). It NEVER substitutes
cached/fallback rows and NEVER presents an empty fetch as "0 closes".

READ-ONLY SAFETY CONTRACT (BINDING — MARK_SPRINT21_RULINGS.md §A1,
AST-provable by tests/test_sprint21_wave2.py):
  • Reads ONLY via the EXACT existing path
    `report_scheduler._fetch_trades_df` (report_scheduler.py:113-148 — the
    single Supabase `select(...).execute()` lives there, not here) and the
    pure helpers `report_on_demand.last_complete_weekly_ref` /
    `last_complete_monthly_ref` + `report_scheduler._weekly_period` /
    `_monthly_period` + `analytics_engine._get_closed_campaigns` /
    `_aggregate_campaigns` + `engine_core.get_campaign_risk_metrics` /
    `classify_stat_bucket` / `is_stat_countable`.
  • Computes ZERO new R/NAV/campaign/Expectancy math — only counts, already-
    stored `pnl_usd` sums, and the existing `get_campaign_risk_metrics`
    result, recomputed read-only on a local copy.
  • NO `.save`/`.insert`/`.update`/`.upsert`/`.delete`, NO non-`select`
    `.execute()`, NO `report_snapshot_store.save`/`snap_save`, NO
    `report_scheduler._save_state`/`_mark_ran`, NO `os.environ[...] =`, NO
    file write, NO `account_state` write, NO `run_on_demand`/deliver/render
    path. It fetches + classifies + formats a Telegram string ONLY; delivery
    is the caller's job (the probe NEVER sends/persists).

NO-SECRETS RULE (BINDING — MARK_SPRINT21_RULINGS.md §A3, AGENTS.md red line,
#1): the probe NEVER prints `SUPABASE_KEY`/`SUPABASE_URL`/
`TELEGRAM_BOT_TOKEN` (or any substring), JWTs, account numbers, broker IDs.
The ONLY auth disclosure is the literal JWT *role* word
(`service_role` | `anon`) parsed locally with the key value discarded; on any
doubt → `הרשאה: לא ודאית`.

Admin-gated by construction: reachable ONLY behind the EXISTING dev-menu PIN
gate (telegram_bot.py:147-153) — see telegram_bot.py / telegram_menus.py
(one additive button + one additive handler `if`). No new auth path, no
secure_runner bypass, no wholesale telegram_bot.py rewrite.
"""
from datetime import datetime

import report_scheduler as sched
import report_on_demand as rod

# RTL marker — identical to bot_core.RTL ('‏') so the message renders
# RTL exactly like every other Telegram message.
_RTL = "‏"


def _supabase_auth_role() -> str:
    """Return the JWT *role* claim word ONLY ('service_role'|'anon') or a safe
    'unknown' marker — the key value is NEVER returned, logged, or kept.

    MARK_SPRINT21_RULINGS.md §A3: base64-decode the middle JWT segment, read
    `payload["role"]`, emit the literal word; discard everything else. On ANY
    failure return "" → caller renders the honest "לא ודאית" token (never a
    guess, never the key).
    """
    import os
    import base64
    import json

    try:
        key = os.environ.get("SUPABASE_KEY", "") or ""
        if not key or key.count(".") != 2:
            return ""
        mid = key.split(".")[1]
        # base64url pad
        pad = "=" * (-len(mid) % 4)
        raw = base64.urlsafe_b64decode(mid + pad)
        payload = json.loads(raw.decode("utf-8", "replace"))
        role = str(payload.get("role", "")).strip().lower()
        # value (key) intentionally discarded here — only the role word lives on
        if role in ("service_role", "anon"):
            return role
        return ""
    except Exception:
        return ""


def _is_blank_cid(series):
    """Vectorised NULL/blank campaign_id mask (mirrors the SPRINT21_DESIGN
    §A.1/§B.2.a predicate exactly): NaN OR str ∈ {'', 'nan', 'None'}."""
    return series.isna() | series.astype(str).str.strip().isin(
        ("", "nan", "None", "NaT"))


def _window_block(period_type: str, now: datetime) -> str:
    """Build ONE honest per-window block (MARK_SPRINT21_RULINGS.md §A2).

    Read-only: resolves the EXACT live window via the pure helpers, calls the
    REAL `_fetch_trades_df`, and recomputes the pipeline classification
    read-only on a local copy. Never fabricates a number; on empty/None fetch
    emits the mandatory honest "input ריק/כשל" line and STOPS that window.
    """
    import pandas as pd
    import analytics_engine as ae
    import engine_core as ec

    label = "שבועי" if period_type == "weekly" else "חודשי"

    if period_type == "weekly":
        ref = rod.last_complete_weekly_ref(now)
        period_start, period_end = sched._weekly_period(ref)
    else:
        ref = rod.last_complete_monthly_ref(now)
        period_start, period_end = sched._monthly_period(ref)

    win_lo = period_start.strftime("%Y-%m-%d")
    win_hi = period_end.strftime("%Y-%m-%d")

    # The live read under test — the EXACT scheduler path. The only Supabase
    # .execute() in WS-A lives inside this reused function (a `select` chain).
    df = sched._fetch_trades_df(period_start, period_end)

    # Auth context — role word ONLY, never the key/URL/token (§A3).
    role = _supabase_auth_role()
    auth_he = role if role in ("service_role", "anon") else "לא ודאית"

    header = (
        f"🔬 בדיקת אספקת נתונים (קריאה בלבד) — {label}\n"
        f"חלון: {win_lo} ← {win_hi}"
    )

    # ── Mandatory honest empty/fail branch (§A1/§A2/#1) ──────────────────────
    # Distinguish "fetch failed / empty input" from "0 closes". NEVER a
    # fabricated breakdown, NEVER cached/fallback substitution.
    if df is None or (hasattr(df, "empty") and df.empty):
        return (
            f"{header}\n"
            f"מקור: Supabase · הרשאה: {auth_he} · רשומות גלויות: 0\n"
            f'⚠️ לא נמשכו שורות (input ריק/כשל) — זהו פער האספקה. '
            f'לא מוצג כ-"0 סגירות".'
        )

    n_rows = int(len(df))

    # Local copy + the SAME numeric coerce as analytics_engine.py:30-33 — pure,
    # read-only, no mutation of the source df.
    work = df.copy()
    work["trade_date"] = pd.to_datetime(work["trade_date"], errors="coerce")
    for col in ("price", "quantity", "stop_loss", "initial_stop", "pnl_usd"):
        if col in work.columns:
            work[col] = pd.to_numeric(work[col], errors="coerce").fillna(0)

    td = work["trade_date"]
    td_min = td.min()
    td_max = td.max()
    td_min_s = td_min.strftime("%Y-%m-%d") if pd.notna(td_min) else "—"
    td_max_s = td_max.strftime("%Y-%m-%d") if pd.notna(td_max) else "—"

    # #SELL in-window (same window predicate the pipeline uses: [start, end)).
    sells = work[work["side"].astype(str).str.upper().eq("SELL")]
    sells_in = sells[(sells["trade_date"] >= period_start) &
                     (sells["trade_date"] < period_end)]
    n_sell = int(len(sells_in))

    # #closed campaigns the REAL pipeline yields — NOT a re-derivation:
    # exactly `_get_closed_campaigns` + `_aggregate_campaigns` (read-only).
    closed = ae._get_closed_campaigns(work, period_start, period_end)
    if closed.empty:
        campaigns = pd.DataFrame()
    else:
        # target_risk only feeds net_r display fallback inside the existing
        # helper; classification uses TRUE risk. We pass 0.0 → no new math.
        campaigns = ae._aggregate_campaigns(closed, 0.0)
    n_closed = int(len(campaigns))

    # #in-window NULL/blank campaign_id (SELL & BUY both — the silent drop).
    in_win = work[(work["trade_date"] >= period_start) &
                  (work["trade_date"] < period_end)]
    null_in = in_win[_is_blank_cid(in_win["campaign_id"])]
    n_null = int(len(null_in))
    null_sells = null_in[null_in["side"].astype(str).str.upper().eq("SELL")]
    pnl_null = float(pd.to_numeric(
        null_sells.get("pnl_usd", pd.Series(dtype=float)),
        errors="coerce").fillna(0).sum())

    lines = [
        header,
        f"מקור: Supabase · הרשאה: {auth_he} · רשומות גלויות: {n_rows}",
        f"שורות שנמשכו: {n_rows}  ·  טווח trade_date: {td_min_s}…{td_max_s}",
        f"SELL בחלון: {n_sell}  ·  קמפיינים שנסגרו "
        f"(לפי הצינור האמיתי): {n_closed}",
        f"ללא campaign_id בחלון: {n_null}  ·  "
        f"Σ pnl_usd לא-מקושר: ${pnl_null:+,.2f}",
        "— פירוט קמפיין —",
    ]

    if campaigns.empty:
        lines.append("(אין קמפיינים שנסגרו בחלון לפי הצינור האמיתי)")
        return "\n".join(lines)

    # Per-campaign classification line. risk_valid / reason are taken VERBATIM
    # from get_campaign_risk_metrics (engine_core.py:943-977) — the SAME
    # _risk_row construction as _aggregate_campaigns:307-308. #8: ALGO appears
    # flagged observation-only, never merged into the countable count.
    for _, crow in campaigns.iterrows():
        cid = crow["campaign_id"]
        grp = closed[closed["campaign_id"] == cid]
        buys = grp[grp["side"].astype(str).str.upper().eq("BUY")].sort_values(
            "trade_date")
        if buys.empty:
            continue
        fb = buys.iloc[0]
        entry = float(fb["price"])
        istop = float(fb["initial_stop"])
        qty = float(fb["quantity"])
        setup = str(fb.get("setup_type", "Unknown"))
        sym = str(fb.get("symbol", "?"))
        _risk_row = {"price": entry, "quantity": qty,
                     "initial_stop": istop,
                     "side": str(fb.get("side", "BUY"))}
        m = ec.get_campaign_risk_metrics(_risk_row)
        valid = bool(m["valid"])
        reason = str(m.get("reason", "") or "")
        bucket = str(crow["stat_bucket"])
        countable = ec.is_stat_countable(bucket)
        net = float(crow["net_pnl"])
        rv = "✓" if valid else f"✗ {reason}"
        cnt = "כן" if countable else "לא"
        lines.append(
            f"{cid} · {sym} · {setup} · initial_stop={istop:g} · "
            f"risk_valid={rv} · bucket={bucket} · נספר={cnt} · "
            f"net=${net:+,.2f}"
        )
        # WS-C presentation-only honest founder guidance (MARK_SPRINT21
        # §WS-C, verbatim) — surfaced ONLY where a campaign is excluded for
        # an invalid stop. NO campaign-math change (DEFERRED, binding).
        if (not valid) and ("initial_stop invalid" in reason):
            lines.append(
                f"⚠️ stop לא תקין (initial_stop {istop:g} מול כניסה "
                f"{entry:g}) — תקן entry/stop כדי להיכלל בסטטיסטיקה"
            )

    return "\n".join(lines)


def build_probe_report(period_type: str = None,
                        now: datetime = None) -> str:
    """Return a Telegram-ready, RTL-prefixed, #1-honest probe string.

    When `period_type` is None, BOTH on-demand windows (weekly + monthly) are
    probed and concatenated (the dev-menu handler uses this). Delivery is the
    caller's responsibility — this function NEVER sends, writes, or persists.
    """
    if now is None:
        now = datetime.now(sched.ISRAEL_TZ)

    if period_type in ("weekly", "monthly"):
        return _RTL + _window_block(period_type, now)

    weekly = _window_block("weekly", now)
    monthly = _window_block("monthly", now)
    return _RTL + weekly + "\n\n" + _RTL + monthly
