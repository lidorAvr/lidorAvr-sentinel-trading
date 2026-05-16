"""
analytics_engine.py — pure-function KPI computation for weekly/monthly reports.
Takes a trades DataFrame (from Supabase) + period bounds + account state.
No network calls, no Supabase — fully testable.
"""
import math
import pandas as pd
from datetime import datetime
from typing import Optional
import engine_core as ec

# ── Public API ─────────────────────────────────────────────────────────────────

def compute_period_analytics(
    df_trades: pd.DataFrame,
    period_start: datetime,
    period_end: datetime,
    account_state: dict,
) -> dict:
    """
    Compute all KPIs for campaigns that closed within [period_start, period_end).
    Returns a flat metrics dict. Never raises — returns error dict on failure.
    """
    t_risk = account_state["nav"] * account_state["risk_pct_input"] / 100
    try:
        if df_trades is None or df_trades.empty:
            return {**_empty(), "target_risk_usd": t_risk}

        df = df_trades.copy()
        df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
        for col in ("price", "quantity", "stop_loss", "initial_stop", "pnl_usd"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        closed_trades = _get_closed_campaigns(df, period_start, period_end)
        if closed_trades.empty:
            return {**_empty(), "target_risk_usd": t_risk}

        campaigns = _aggregate_campaigns(closed_trades, t_risk)
        if campaigns.empty:
            return {**_empty(), "target_risk_usd": t_risk}

        # Two distinct filters (AGENTS.md invariant #8):
        #   • Edge stats (WR / Expectancy / PF / R / best-worst / breakdown)
        #     count ONLY stat-countable campaigns — never ALGO_OBSERVED or
        #     DATA_INCOMPLETE. Mirrors adaptive_risk_engine._is_disc and
        #     dashboard.py so the report matches the bot and dashboard.
        #   • Process-discipline stats (missing_stop_rate / oversized_rate)
        #     count MANUAL campaigns including DATA_INCOMPLETE — a missing
        #     stop is precisely what that metric exists to surface. Only
        #     ALGO (externally managed, no manual stop) is excluded there.
        bucket    = campaigns["stat_bucket"]
        countable = campaigns[bucket.apply(ec.is_stat_countable)]
        manual    = campaigns[bucket != ec.STAT_BUCKET_ALGO]
        excluded  = campaigns[~bucket.apply(ec.is_stat_countable)]

        excluded_count = int(len(excluded))
        excluded_pnl   = float(excluded["net_pnl"].sum()) if not excluded.empty else 0.0

        # ── Sprint-20 Step-2 (Mark §2 / DEC-20260516-017 UPDATE §2 /
        # DEC-20260511-001 / #8) — ADDITIVE manual-vs-ALGO partition of the
        # SAME already-aggregated `excluded["net_pnl"]`. NO new R / NAV /
        # campaign / Expectancy math: a pure read-only split of the existing
        # `excluded` frame by the existing `stat_bucket` series (the predicate
        # already at :54-55), so the silent excluded leg can be disclosed with
        # the actionable manual leg kept distinct from the observation-only
        # externally-managed ALGO leg. `excluded_count`/`excluded_pnl` and the
        # `countable`/`manual`/edge semantics are UNCHANGED — these four keys
        # are strictly additive. invariant: manual + algo == excluded.
        excl_algo   = excluded[excluded["stat_bucket"] == ec.STAT_BUCKET_ALGO]
        excl_manual = excluded[excluded["stat_bucket"] != ec.STAT_BUCKET_ALGO]
        excluded_count_algo   = int(len(excl_algo))
        excluded_pnl_algo     = float(excl_algo["net_pnl"].sum())   if not excl_algo.empty   else 0.0
        excluded_count_manual = int(len(excl_manual))
        excluded_pnl_manual   = float(excl_manual["net_pnl"].sum()) if not excl_manual.empty else 0.0

        # Execution quality — over MANUAL campaigns (DATA_INCOMPLETE kept).
        buy_in_period = df[
            df["side"].str.upper().eq("BUY") &
            df["campaign_id"].isin(manual["campaign_id"])
        ].copy()
        n_buys = len(buy_in_period)

        missing_stop_rate = 0.0
        oversized_rate    = 0.0
        if n_buys > 0:
            no_stop = (buy_in_period["initial_stop"] <= 0).sum()
            missing_stop_rate = no_stop / n_buys
            has_stop = buy_in_period[buy_in_period["initial_stop"] > 0].copy()
            if not has_stop.empty:
                has_stop["actual_risk"] = (
                    (has_stop["price"] - has_stop["initial_stop"]) * has_stop["quantity"]
                )
                over = (has_stop["actual_risk"] > t_risk * 1.25).sum()
                oversized_rate = over / len(has_stop)

        if countable.empty:
            return {**_empty(), "target_risk_usd": t_risk,
                    "missing_stop_rate": float(missing_stop_rate),
                    "oversized_rate":    float(oversized_rate),
                    "excluded_count":    excluded_count,
                    "excluded_pnl":      excluded_pnl,
                    "excluded_count_manual": excluded_count_manual,
                    "excluded_pnl_manual":   excluded_pnl_manual,
                    "excluded_count_algo":   excluded_count_algo,
                    "excluded_pnl_algo":     excluded_pnl_algo}

        wins   = countable[countable["net_pnl"] > 0]
        losses = countable[countable["net_pnl"] <= 0]
        n      = len(countable)

        win_rate    = len(wins) / n if n else 0
        avg_win_r   = float(wins["net_r"].mean())   if not wins.empty   else 0.0
        avg_loss_r  = float(losses["net_r"].mean()) if not losses.empty else 0.0
        expectancy  = win_rate * avg_win_r + (1 - win_rate) * avg_loss_r

        gross_profit = wins["net_pnl"].sum()   if not wins.empty   else 0.0
        gross_loss   = abs(losses["net_pnl"].sum()) if not losses.empty else 0.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (math.inf if gross_profit > 0 else 0.0)

        total_r   = float(countable["net_r"].sum())
        real_pnl  = float(countable["net_pnl"].sum())

        best  = countable.loc[countable["net_pnl"].idxmax()]
        worst = countable.loc[countable["net_pnl"].idxmin()]

        # R / day (clip days to ≥1 to avoid div/0)
        countable = countable.copy()
        countable["days_held"] = countable["days_held"].clip(lower=1)
        avg_r_per_day = float((countable["net_r"] / countable["days_held"]).mean())

        # Setup breakdown
        setup_breakdown = {}
        for setup, grp in countable.groupby("setup_type"):
            g_wins   = grp[grp["net_pnl"] > 0]
            g_losses = grp[grp["net_pnl"] <= 0]
            gw_pnl   = g_wins["net_pnl"].sum()   if not g_wins.empty   else 0
            gl_pnl   = abs(g_losses["net_pnl"].sum()) if not g_losses.empty else 0
            setup_breakdown[str(setup)] = {
                "count":         len(grp),
                "net_r":         float(grp["net_r"].sum()),
                "win_rate":      len(g_wins) / len(grp) if grp.shape[0] else 0,
                "avg_r":         float(grp["net_r"].mean()),
                "profit_factor": gw_pnl / gl_pnl if gl_pnl > 0 else (math.inf if gw_pnl > 0 else 0.0),
            }

        return {
            "ok":                True,
            "error":             None,
            "campaigns_closed":  n,
            "win_rate":          win_rate,
            "expectancy_r":      float(expectancy),
            "profit_factor":     profit_factor,
            "avg_win_r":         avg_win_r,
            "avg_loss_r":        avg_loss_r,
            "total_r_net":       total_r,
            "realized_pnl":      real_pnl,
            "best_trade":        {"symbol": best["symbol"], "net_r": float(best["net_r"]), "net_pnl": float(best["net_pnl"])},
            "worst_trade":       {"symbol": worst["symbol"], "net_r": float(worst["net_r"]), "net_pnl": float(worst["net_pnl"])},
            "setup_breakdown":   setup_breakdown,
            "missing_stop_rate": float(missing_stop_rate),
            "oversized_rate":    float(oversized_rate),
            "avg_r_per_day":     avg_r_per_day,
            "target_risk_usd":   t_risk,
            "excluded_count":    excluded_count,
            "excluded_pnl":      excluded_pnl,
            "excluded_count_manual": excluded_count_manual,
            "excluded_pnl_manual":   excluded_pnl_manual,
            "excluded_count_algo":   excluded_count_algo,
            "excluded_pnl_algo":     excluded_pnl_algo,
        }

    except Exception as e:
        return {**_empty(), "ok": False, "error": str(e), "target_risk_usd": t_risk}


def compute_trader_development_score(analytics: dict) -> dict:
    """
    Score 0–100 measuring process quality, not just PnL.
    35 pts: process discipline  |  35 pts: edge quality
    20 pts: risk behavior       |  10 pts: execution efficiency
    """
    if not analytics.get("ok") or analytics.get("campaigns_closed", 0) == 0:
        return {"score": None, "breakdown": {}, "label": "אין מספיק נתונים"}

    def clamp(v, lo=0.0, hi=1.0):
        return max(lo, min(hi, v))

    # Process discipline (35): missing stops, oversized, conceptually add-on
    miss   = clamp(1 - analytics["missing_stop_rate"])
    over   = clamp(1 - analytics["oversized_rate"])
    process = (miss * 0.5 + over * 0.5) * 35

    # Edge quality (35): expectancy, profit_factor, payoff ratio
    exp_norm = clamp((analytics["expectancy_r"] + 1) / 3)     # −1R..+2R → 0..1
    pf_norm  = clamp((analytics["profit_factor"] - 0.5) / 3)  # 0.5..3.5 → 0..1
    payoff   = abs(analytics["avg_win_r"] / analytics["avg_loss_r"]) if analytics["avg_loss_r"] != 0 else 1.0
    pay_norm = clamp((payoff - 0.5) / 2.5)
    edge     = (exp_norm * 0.45 + pf_norm * 0.35 + pay_norm * 0.20) * 35

    # Risk behavior (20): adherence (supplied externally, default 0.7)
    adh       = clamp(analytics.get("risk_adherence_rate", 0.7))
    risk_part = adh * 20

    # Execution efficiency (10): R/day
    r_day_norm = clamp(analytics["avg_r_per_day"] * 10)  # 0.1R/day → full score
    exec_part  = r_day_norm * 10

    score = int(round(process + edge + risk_part + exec_part))
    label = "מצוין 🟢" if score >= 75 else ("טוב 🟡" if score >= 50 else "דורש שיפור 🔴")

    return {
        "score":     score,
        "label":     label,
        "breakdown": {
            "process":   round(process, 1),
            "edge":      round(edge, 1),
            "risk":      round(risk_part, 1),
            "execution": round(exec_part, 1),
        },
    }


def compute_period_comparison(current: dict, previous: dict) -> dict:
    """
    Compute delta metrics between current and previous period analytics.
    Returns dict of {metric: {current, previous, delta, direction}}.
    """
    if not previous:
        return {}

    metrics = ["win_rate", "expectancy_r", "profit_factor", "total_r_net",
               "realized_pnl", "missing_stop_rate", "oversized_rate", "avg_r_per_day"]

    result = {}
    for m in metrics:
        c = current.get(m)
        p = previous.get(m)
        if c is None or p is None:
            continue
        delta = c - p
        # For rates where lower is better, flip the direction label
        lower_is_better = m in ("missing_stop_rate", "oversized_rate")
        improving = delta < 0 if lower_is_better else delta > 0
        result[m] = {
            "current":   round(c, 4),
            "previous":  round(p, 4),
            "delta":     round(delta, 4),
            "direction": "up" if delta > 0 else ("down" if delta < 0 else "flat"),
            "improving": improving,
        }
    return result


def compute_verdict(analytics: dict, period_word: str = "שבוע") -> tuple:
    """
    Returns (verdict_he: str, verdict_class: str).
    verdict_class: "strong" | "mixed" | "defensive"
    period_word: the Hebrew period noun ("שבוע" weekly / "חודש" monthly) —
    display only; does NOT affect any stat or the #8 partition. Default keeps
    weekly callers byte-identical.
    """
    if not analytics.get("ok") or analytics.get("campaigns_closed", 0) == 0:
        return f"{period_word} ללא עסקאות", "neutral"
    tr   = analytics["total_r_net"]
    wr   = analytics["win_rate"]
    miss = analytics["missing_stop_rate"]
    over = analytics["oversized_rate"]
    process_ok = miss < 0.15 and over < 0.20
    if tr >= 1.0 and wr >= 0.55 and process_ok:
        return f"{period_word} חזק 💪", "strong"
    elif tr <= -0.5 or wr < 0.35:
        return f"{period_word} הגנתי 🛡️", "defensive"
    else:
        return f"{period_word} מעורב ➡️", "mixed"


# ── Internals ──────────────────────────────────────────────────────────────────

def _get_closed_campaigns(df: pd.DataFrame, start: datetime, end: datetime) -> pd.DataFrame:
    """Return all trades belonging to campaigns whose last SELL falls in [start, end)."""
    sells = df[df["side"].str.upper().eq("SELL")]
    in_period = sells[(sells["trade_date"] >= start) & (sells["trade_date"] < end)]
    if in_period.empty:
        return pd.DataFrame()
    closed_ids = in_period["campaign_id"].dropna().unique()
    return df[df["campaign_id"].isin(closed_ids)]


def _aggregate_campaigns(closed: pd.DataFrame, target_risk_usd: float) -> pd.DataFrame:
    """Aggregate per-campaign metrics: net_pnl, net_r, days_held, setup_type, symbol."""
    records = []
    for cid, grp in closed.groupby("campaign_id"):
        buys  = grp[grp["side"].str.upper().eq("BUY")].sort_values("trade_date")
        sells = grp[grp["side"].str.upper().eq("SELL")]
        if buys.empty:
            continue

        net_pnl = float(sells["pnl_usd"].sum())
        fb      = buys.iloc[0]
        entry   = float(fb["price"])
        init_sl = float(fb["initial_stop"])
        qty     = float(fb["quantity"])
        setup   = str(fb.get("setup_type", "Unknown"))
        sym     = str(fb.get("symbol", "?"))

        _risk_row = {"price": entry, "quantity": qty, "initial_stop": init_sl,
                     "side": str(fb.get("side", "BUY"))}
        _metrics  = ec.get_campaign_risk_metrics(_risk_row)
        true_orig_risk = _metrics["original_risk"] if _metrics["valid"] else 0.0
        # net_r keeps the target_risk fallback so the displayed R stays usable,
        # but stat_bucket is classified from the TRUE risk — otherwise the
        # fallback would mask a missing stop and misclassify a DATA_INCOMPLETE
        # campaign as countable.
        orig_risk = true_orig_risk if true_orig_risk > 0 else target_risk_usd
        net_r     = net_pnl / orig_risk if orig_risk > 0 else 0.0
        stat_bucket = ec.classify_stat_bucket(setup, true_orig_risk)

        entry_date     = buys["trade_date"].iloc[0]
        last_sell_date = sells["trade_date"].max() if not sells.empty else entry_date
        days_held      = max(1, (pd.Timestamp(last_sell_date) - pd.Timestamp(entry_date)).days)

        records.append({
            "campaign_id": cid, "symbol": sym, "setup_type": setup,
            "net_pnl": net_pnl, "net_r": net_r,
            "orig_risk": orig_risk, "days_held": days_held,
            "stat_bucket": stat_bucket,
        })
    return pd.DataFrame(records) if records else pd.DataFrame()


def _empty() -> dict:
    return {
        "ok": True, "error": None,
        "campaigns_closed": 0,
        "win_rate": 0.0, "expectancy_r": 0.0, "profit_factor": 0.0,
        "avg_win_r": 0.0, "avg_loss_r": 0.0,
        "total_r_net": 0.0, "realized_pnl": 0.0,
        "best_trade": None, "worst_trade": None,
        "setup_breakdown": {},
        "missing_stop_rate": 0.0, "oversized_rate": 0.0,
        "avg_r_per_day": 0.0, "target_risk_usd": 0.0,
        "excluded_count": 0, "excluded_pnl": 0.0,
        # Sprint-20 Step-2 — additive manual/ALGO partition of excluded (0 on
        # the empty path; existing excluded_count/excluded_pnl untouched).
        "excluded_count_manual": 0, "excluded_pnl_manual": 0.0,
        "excluded_count_algo": 0, "excluded_pnl_algo": 0.0,
    }
