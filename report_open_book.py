"""
report_open_book.py — Sprint-18 pure leaf: build the OPEN-BOOK (unrealized)
view for the weekly/monthly report.

Mark-gated (docs/teams/MARK_SPRINT18_RULINGS.md). HARD invariants enforced
*by construction* in this module:

  • Realized vs unrealized are STRICTLY separated. This module reads ONLY
    `engine_core.get_open_positions_campaign` (engine_core.py:473) — the EXACT
    live source the command room uses (telegram_portfolio.handle_portfolio_room)
    — and returns a NEW dict under `open_book_*` keys. It NEVER mutates, reads,
    or feeds `analytics_engine.compute_period_analytics`. The realized KPI dict
    is byte-identical with vs without this path (guard test).

  • No new position / PnL / R math is invented. Floating PnL, Structure R and
    Account R are produced by the EXISTING engine functions with the SAME
    inputs the command room uses (engine_core.compute_r_true:997 /
    compute_r_target:1004 / get_campaign_risk_metrics:943). This module only
    *reuses* and *labels* them.

  • ALGO positions are SEGREGATED (AGENTS.md #8 / DEC-20260515-014 /
    DEC-20260511-001) into a distinct `open_book_algo` list — NEVER in the
    discretionary list, NEVER counted in any realized figure, observation-only
    ("פיקוח בלבד · לא הוראה"). Their floating PnL/price IS live (no backtest
    caveat on the number); exactly ONE caveat — Mark §3 — applies, about the
    external-management nature, not a fabricated backtest disclaimer.

  • Honest data source (#1): a per-figure binary on `get_live_price` returning
    `None` — never a guessed price; the symbol is recorded for the fallback
    label. ALGO Structure R = the "no real stop" token (never `0.00R`).
"""
from typing import Optional

import pandas as pd

import engine_core as ec


# ── Mark §1 / §2 / §3 / §4 verbatim wording (filled from
#    docs/teams/MARK_SPRINT18_RULINGS.md — nothing invented) ───────────────────

# §1 — floating PnL / Open-R explicitly labelled unrealized.
OPEN_BOOK_UNREALIZED_LABEL = "לא ממומש"

# §1 — section heading (he, RTL).
OPEN_BOOK_HEADING = "📌 ספר פתוח (לא ממומש)"

# §3 — ALGO sub-group: observation-only, never an instruction (DEC-20260511-001).
ALGO_OBSERVATION_LABEL = "פיקוח בלבד · לא הוראה"
# §3 — the EXACTLY-ONE caveat for the ALGO sub-block. The floating PnL/price is
# LIVE (no backtest caveat attaches to it); the only honest caveat is the
# external-management nature.
ALGO_EXTERNAL_CAVEAT = "מנוהל חיצונית — פיקוח, ללא הוראת Sentinel"

# §1 — data-source disclosure tokens. "Live" when every shown price came from a
# live quote; "Cached" when at least one symbol fell back to its entry price
# (get_live_price returned None — a per-figure binary, never a guess);
# "Sync זמני" reserved for the transient post-sync window (surfaced verbatim
# when the caller passes it; this module never fabricates it).
DATA_SOURCE_LIVE = "Live"
DATA_SOURCE_CACHED = "Cached"
DATA_SOURCE_SYNC_TEMP = "Sync זמני"

# §2 — honest empty-state, RTL, #1 (presentation switch in report_renderer; the
# strings live here so there is a single source of truth).
#   Case A: 0 closed campaigns but a LIVE book exists.
EMPTY_STATE_ZERO_CLOSED_WITH_BOOK_L1 = (
    "✅ 0 קמפיינים נסגרו בתקופה — אין נתוני ביצועים ממומשים."
)
EMPTY_STATE_ZERO_CLOSED_WITH_BOOK_L2 = (
    "📌 ספר פתוח (לא ממומש): {n} פוזיציות · חשיפה {exposure:.1f}% · "
    "צף ${floating:+,.0f}"
)
EMPTY_STATE_ZERO_CLOSED_WITH_BOOK_L3 = (
    "📅 חלון: {label} · מקור: {source}"
)
#   Case B: truly empty — 0 closed AND 0 open.
EMPTY_STATE_TRULY_EMPTY = (
    "✅ 0 קמפיינים נסגרו · אין פוזיציות פתוחות. שבוע ללא פעילות מסחר."
)

# §4 — snapshot-delta baseline-pending token (no retroactive open-mark exists;
# accuracy over confidence, #1) — surfaced verbatim until a prior open-mark.
DELTA_BASELINE_PENDING = "Δ שבועי (mark-to-market): — · ממתין לבסיס שבוע קודם"

# §5 — PERIOD-SCOPED activity attribution (founder binding criterion
# 2026-05-16, SPRINT18_PLAN.md). A position is attributed by its entry_date
# (engine_core.get_open_positions_campaign already computes it = first buy
# trade_date — no new data/math). Positions whose entry is AFTER period_end
# never existed during the period and are EXCLUDED (e.g. a position opened
# 14/05 must not appear in a 03–09/05 weekly report). entry_date
# missing/unparseable ⇒ kept (never drop real data, #1) with no label.
OPENED_IN_PERIOD_LABEL  = "נפתחה בתקופה"
HELD_FROM_BEFORE_LABEL  = "מוחזקת מתקופה קודמת"


def _is_algo_row(row: dict) -> bool:
    """Mirror the command room's ALGO predicate exactly.

    `telegram_portfolio.handle_portfolio_room` branches on
    `str(setup).upper() == 'ALGO'`; `engine_core.is_algo_position`
    (engine_core.py:247) is the canonical predicate (setup_type primary,
    ALGO_SYMBOLS fallback only when setup is unknown). Use the canonical one so
    a symbol-fallback ALGO (e.g. HOOD/PLTR/TSLA with unknown setup) is still
    segregated — never leaking into the discretionary list.
    """
    return ec.is_algo_position(row.get("setup_type"), row.get("symbol"))


def _classify_period(entry_date, period_start, period_end):
    """(keep: bool, status: str, label: str) for one position vs the period.

    keep=False ⇒ entry strictly AFTER period_end (never open during the
    period → excluded). Unknown/unparseable entry or missing period bounds
    ⇒ keep with no label (never drop real data; never fabricate, #1).
    """
    if period_start is None or period_end is None or entry_date is None:
        return True, "", ""
    try:
        import pandas as pd
        ed = pd.to_datetime(entry_date, errors="coerce")
        if ed is None or pd.isna(ed):
            return True, "", ""
        ed = ed.date()
        ps, pe = period_start.date(), period_end.date()
    except Exception:
        return True, "", ""
    if ed > pe:
        return False, "after_period", ""
    if ed < ps:
        return True, "held_from_before", HELD_FROM_BEFORE_LABEL
    return True, "opened_in_period", OPENED_IN_PERIOD_LABEL


def build_open_book(
    df_trades: pd.DataFrame,
    account_state: dict,
    *,
    period_start=None,
    period_end=None,
    data_source_override: Optional[str] = None,
) -> dict:
    """Build the open-book (unrealized) view, read-only, reuse-only.

    Returns a NEW dict namespaced `open_book_*`. Returns
    ``{"open_book_present": False, ...}`` (never raises) on any infra error so
    the realized report is never blocked by an open-book failure.

    `account_state` is the same dict `account_state.load()` returns; NAV +
    target risk are derived exactly as the command room does
    (telegram_portfolio.py:248 via bot_helpers.get_nav_and_risk equivalent:
    acc_size = NAV, target_risk_usd = NAV * risk_pct/100).

    `data_source_override`: when the caller knows the run is inside the
    transient post-sync window it may pass DATA_SOURCE_SYNC_TEMP; this module
    never fabricates that state (#1).
    """
    empty = {
        "open_book_present": False,
        "open_book_disc": [],
        "open_book_algo": [],
        "open_book_totals": {
            "floating_pnl_disc": 0.0,
            "floating_pnl_algo": 0.0,
            "exposure_pct_total": 0.0,
            "exposure_pct_disc": 0.0,
            "exposure_pct_algo": 0.0,
            "n_disc": 0,
            "n_algo": 0,
            "n_opened_disc": 0,
            "n_opened_algo": 0,
            "n_opened_total": 0,
        },
        "open_book_data_source": data_source_override or DATA_SOURCE_LIVE,
        "open_book_price_fallback_syms": [],
        "open_book_error": None,
    }

    try:
        if df_trades is None or (hasattr(df_trades, "empty") and df_trades.empty):
            return empty

        pos_res = ec.get_open_positions_campaign(df_trades)
        if not pos_res.get("ok"):
            return {**empty, "open_book_error": pos_res.get("error")}

        open_pos = pos_res["data"]
        if open_pos is None or open_pos.empty:
            return empty

        # NAV + frozen target risk — derived exactly as the command room
        # (telegram_portfolio.py:248): acc_size = NAV, target = NAV*risk/100.
        # No new NAV math; pure read of account_state.
        acc_size = float(
            account_state.get("nav")
            or account_state.get("total_deposited")
            or 0.0
        )
        risk_pct = float(account_state.get("risk_pct_input", 0.5))
        target_risk_usd = acc_size * (risk_pct / 100.0) if acc_size > 0 else 0.0

        disc, algo = [], []
        floating_disc = floating_algo = 0.0
        exposure_disc = exposure_algo = 0.0
        price_fallback_syms = []

        for row in open_pos.to_dict("records"):
            sym = row["symbol"]
            entry = float(row["price"])
            base_price = float(row.get("base_price", entry))
            qty = float(row["quantity"])
            setup = row.get("setup_type", "Unknown")
            realized_pnl = float(row.get("realized_pnl", 0) or 0)

            # §5 — period-scoped activity (founder binding criterion). A
            # position opened AFTER period_end never existed during the
            # period → exclude it from THIS period's book.
            keep, period_status, period_label_he = _classify_period(
                row.get("entry_date"), period_start, period_end)
            if not keep:
                continue

            # Honest price (#1 / Mark §1): per-figure binary on the ACTUAL
            # None — never a guess. Mirrors telegram_portfolio.py:279-283.
            curr = ec.get_live_price(sym)
            price_is_fallback = curr is None
            if price_is_fallback:
                curr = entry
                price_fallback_syms.append(sym)
            curr = float(curr)

            # Reuse-only: SAME open-PnL expression the command room uses
            # (telegram_portfolio.py:285). No new PnL math.
            open_pnl_usd = (curr - entry) * qty
            pos_value = curr * qty
            exposure_pct = (
                (pos_value / acc_size) * 100.0 if acc_size > 0 else 0.0
            )

            is_algo = _is_algo_row(row)

            # Original campaign risk — the SINGLE source of truth
            # (engine_core.get_campaign_risk_metrics:943). The command room
            # uses an inline expression with identical inputs; the engine
            # helper returns the same value (base_price/base_qty/init_stop).
            risk_metrics = ec.get_campaign_risk_metrics(row)
            original_campaign_risk = (
                risk_metrics["original_risk"] if risk_metrics["valid"] else 0.0
            )

            # Dual R via the EXISTING engine functions, SAME inputs as
            # telegram_portfolio.py:312-313 — never one conflated number
            # (DEC-20260515-011). No new R math.
            structure_r = ec.compute_r_true(
                open_pnl_usd, original_campaign_risk
            )
            account_r = ec.compute_r_target(open_pnl_usd, target_risk_usd)

            # ALGO ⇒ Structure R has no real stop → the "—" token, never
            # 0.00R (Mark §3 / DEC-20260515-011); Account R only.
            structure_valid = (not is_algo) and original_campaign_risk > 0
            account_valid = target_risk_usd > 0

            rec = {
                "symbol": sym,
                "entry": entry,                 # avg entry (row["price"])
                "base_price": base_price,       # campaign-open price
                "current": curr,
                "qty": qty,
                "floating_pnl": open_pnl_usd,   # unrealized — never realized
                "realized_pnl": realized_pnl,   # separate; never summed in
                "structure_r": structure_r,
                "account_r": account_r,
                "structure_valid": bool(structure_valid),
                "account_valid": bool(account_valid),
                "exposure_pct": exposure_pct,
                "price_is_fallback": price_is_fallback,
                "is_algo": is_algo,
                # §5 period attribution — display only; never affects PnL/R/#8.
                "period_status": period_status,
                "period_label_he": period_label_he,
                "unrealized_label": OPEN_BOOK_UNREALIZED_LABEL,
                # Risk Capital Basis declaration (DEC-20260515-012) — NAV-derived
                # target; declaration only, no number change.
                "risk_capital_basis": account_state.get("nav_source", "—"),
            }

            if is_algo:
                # Mark §3: observation-only, exactly ONE external caveat; the
                # floating PnL/price is LIVE so NO backtest caveat attaches.
                rec["observation_label"] = ALGO_OBSERVATION_LABEL
                rec["external_caveat"] = ALGO_EXTERNAL_CAVEAT
                rec["structure_r_token"] = "—"  # never 0.00R
                algo.append(rec)
                floating_algo += open_pnl_usd
                exposure_algo += exposure_pct
            else:
                disc.append(rec)
                floating_disc += open_pnl_usd
                exposure_disc += exposure_pct

        # Data source honesty (#1): any price fallback ⇒ "Cached", else
        # "Live"; the caller may force "Sync זמני" for the transient window
        # (never fabricated here).
        if data_source_override:
            data_source = data_source_override
        elif price_fallback_syms:
            data_source = DATA_SOURCE_CACHED
        else:
            data_source = DATA_SOURCE_LIVE

        return {
            "open_book_present": bool(disc or algo),
            "open_book_disc": disc,
            "open_book_algo": algo,
            "open_book_totals": {
                "floating_pnl_disc": floating_disc,
                "floating_pnl_algo": floating_algo,
                "exposure_pct_total": exposure_disc + exposure_algo,
                "exposure_pct_disc": exposure_disc,
                "exposure_pct_algo": exposure_algo,
                "n_disc": len(disc),
                "n_algo": len(algo),
                "n_opened_disc": sum(
                    1 for r in disc
                    if r.get("period_status") == "opened_in_period"),
                "n_opened_algo": sum(
                    1 for r in algo
                    if r.get("period_status") == "opened_in_period"),
                "n_opened_total": sum(
                    1 for r in (disc + algo)
                    if r.get("period_status") == "opened_in_period"),
            },
            "open_book_data_source": data_source,
            "open_book_price_fallback_syms": price_fallback_syms,
            "open_book_error": None,
        }
    except Exception as e:  # never block the realized report
        return {**empty, "open_book_error": str(e)}


def open_book_summary_lines(open_book: dict) -> list:
    """Compact RTL summary lines for the Telegram pre-PDF message (§1.4).

    Pure presentation; appended AFTER the realized KPI block by
    report_renderer.build_summary_text. Discretionary first, ALGO segregated
    and observation-only. Returns [] when there is no book.
    """
    if not open_book or not open_book.get("open_book_present"):
        return []
    t = open_book["open_book_totals"]
    src = open_book.get("open_book_data_source", DATA_SOURCE_LIVE)
    lines = [
        f"📌 *ספר פתוח (לא ממומש)* · מקור: `{src}`",
        f"▸ דיסקרציוני: `{t['n_disc']}` פוז' · "
        f"צף `${t['floating_pnl_disc']:+,.0f}` · "
        f"חשיפה `{t['exposure_pct_disc']:.1f}%`",
    ]
    if t["n_algo"] > 0:
        lines.append(
            f"▸ ALGO ({ALGO_OBSERVATION_LABEL}): `{t['n_algo']}` פוז' · "
            f"צף `${t['floating_pnl_algo']:+,.0f}` · "
            f"חשיפה `{t['exposure_pct_algo']:.1f}%`"
        )
    if t.get("n_opened_total", 0) > 0:
        lines.append(
            f"🆕 מתוכן `{t['n_opened_total']}` נפתחו בתקופה זו"
        )
    fb = open_book.get("open_book_price_fallback_syms") or []
    if fb:
        lines.append(
            f"⚠️ מחיר לא חי (לפי כניסה): `{', '.join(fb)}`"
        )
    return lines


def empty_state_lines(open_book: dict, period_label: str) -> list:
    """Honest empty-state lines (Mark §2) for the 0-closed-campaigns case.

    Presentation switch consumed by report_renderer.build_summary_text when
    `analytics.campaigns_closed == 0`. Never the word "ללא עסקאות" while a
    live book exists.
      • book present  → Case A (0 closed + live book), 3 lines.
      • book absent    → Case B (truly empty), 1 line.
    """
    if open_book and open_book.get("open_book_present"):
        t = open_book["open_book_totals"]
        src = open_book.get("open_book_data_source", DATA_SOURCE_LIVE)
        n_total = t["n_disc"] + t["n_algo"]
        floating_total = t["floating_pnl_disc"] + t["floating_pnl_algo"]
        n_opened = t.get("n_opened_total", 0)
        lines = [
            EMPTY_STATE_ZERO_CLOSED_WITH_BOOK_L1,
            EMPTY_STATE_ZERO_CLOSED_WITH_BOOK_L2.format(
                n=n_total,
                exposure=t["exposure_pct_total"],
                floating=floating_total,
            ),
        ]
        # Founder binding criterion: never imply "no trades" — state plainly
        # whether positions were OPENED in this window vs only held over.
        if n_opened > 0:
            lines.append(
                f"🆕 {n_opened} מתוכן נפתחו בתקופה זו — פעילות מסחר בחלון."
            )
        else:
            lines.append(
                "↳ כולן נפתחו לפני התקופה ומוחזקות לאורכה (פעילות פתוחה)."
            )
        lines.append(
            EMPTY_STATE_ZERO_CLOSED_WITH_BOOK_L3.format(
                label=period_label, source=src
            )
        )
        return lines
    return [EMPTY_STATE_TRULY_EMPTY]


def compute_mark_delta(open_book: dict, prev_snapshot: Optional[dict]) -> dict:
    """Weekly mark-to-market delta — PURE subtraction of two stored floats.

    No new math (Mark §4). When there is no prior open-mark (old snapshot, or
    `prev_snapshot` is None / lacks `open_marks`) the delta is surfaced as the
    verbatim baseline-pending token — NEVER a fabricated number (#1, accuracy
    over confidence).

    Returns:
      {"available": bool,
       "text": str,                       # always set (token or formatted)
       "delta_floating_disc": float|None,
       "delta_floating_algo": float|None}
    """
    prev_marks = (prev_snapshot or {}).get("open_marks") if prev_snapshot else None
    if not prev_marks:
        return {
            "available": False,
            "text": DELTA_BASELINE_PENDING,
            "delta_floating_disc": None,
            "delta_floating_algo": None,
        }
    if not open_book or not open_book.get("open_book_present"):
        # A prior baseline exists but there is no current book — still honest:
        # nothing to mark against now.
        return {
            "available": False,
            "text": DELTA_BASELINE_PENDING,
            "delta_floating_disc": None,
            "delta_floating_algo": None,
        }

    cur = open_book["open_book_totals"]
    # Pure subtraction of two previously-stored floats — reuses the floating
    # PnL get_open_positions_campaign already produced; invents no math.
    d_disc = float(cur["floating_pnl_disc"]) - float(
        prev_marks.get("floating_pnl_disc", 0.0) or 0.0
    )
    d_algo = float(cur["floating_pnl_algo"]) - float(
        prev_marks.get("floating_pnl_algo", 0.0) or 0.0
    )
    return {
        "available": True,
        # ALGO segregated, observation-only, never merged into the disc delta.
        "text": (
            f"Δ שבועי (mark-to-market): דיסקרציוני `${d_disc:+,.0f}` · "
            f"ALGO ({ALGO_OBSERVATION_LABEL}) `${d_algo:+,.0f}`"
        ),
        "delta_floating_disc": d_disc,
        "delta_floating_algo": d_algo,
    }
