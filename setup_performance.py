"""setup_performance.py — Per-setup performance breakdown.

For the /setup_stats Telegram view. Aggregates closed campaigns by
`setup_type` and computes win rate, payoff, expectancy (R-based), and
total R earned per group.

Pure functions — no Telegram, no Supabase, no I/O. Caller passes the
output of adaptive_risk_engine.compute_closed_campaigns.

Sprint 11 feature. EP-aware (Mark's research note): the breakdown
exposes EP performance separately from VCP, which is essential because
the two setups have very different time signatures and edge profiles.
"""
from __future__ import annotations
from typing import Optional

import engine_core as ec


# Display names per setup_type. Anything not listed renders verbatim.
_SETUP_LABELS = {
    "VCP":         "VCP (Minervini)",
    "VCP_MANUAL":  "VCP (Minervini)",
    "EP":          "EP (Episodic Pivot)",
    "SWING":       "Swing",
    "ALGO":        "ALGO (חיצוני)",
    "":            "ללא setup_type",
}


def _normalize(setup: str) -> str:
    """Collapse VCP_MANUAL into VCP for the display bucket. Keep the
    raw value for tracking but show them as the same setup family."""
    s = (setup or "").upper().strip()
    if s == "VCP_MANUAL":
        return "VCP"
    return s


def compute_setup_breakdown(closed_campaigns: list[dict]) -> dict[str, dict]:
    """Per-setup_type aggregate. Returns:
        {
            "VCP": {
                "n": 8, "wins": 6, "losses": 2,
                "win_rate": 0.75, "total_pnl_usd": 2400.0,
                "avg_pnl_usd": 300.0, "payoff": 4.2,
                "total_r": 12.3, "avg_r": 1.54,
                "stat_countable": True,
            },
            "EP": {...},
            ...
        }

    Excludes campaigns whose stat_bucket is not stat-countable (ALGO_OBSERVED,
    DATA_INCOMPLETE) from the aggregate — they're displayed in a separate
    "ALGO" / "incomplete" bucket if present, but don't pollute the
    discretionary stats.

    R-multiples use `total_pnl_usd / original_campaign_risk`. Campaigns
    with risk == 0 are excluded from the R aggregate (can't compute) but
    still counted in n / wins / losses for completeness.
    """
    by_setup: dict[str, list[dict]] = {}
    for c in closed_campaigns:
        bucket = _normalize(c.get("setup_type", ""))
        by_setup.setdefault(bucket, []).append(c)

    out = {}
    for bucket, camps in by_setup.items():
        n = len(camps)
        wins   = [c for c in camps if c.get("is_win")]
        losses = [c for c in camps if not c.get("is_win")]
        total_pnl = sum(float(c.get("total_pnl_usd", 0)) for c in camps)
        wins_pnl  = sum(float(c.get("total_pnl_usd", 0)) for c in wins)
        losses_pnl = sum(abs(float(c.get("total_pnl_usd", 0))) for c in losses)
        avg_win  = (wins_pnl / len(wins))   if wins else 0.0
        avg_loss = (losses_pnl / len(losses)) if losses else 0.0
        payoff = round(avg_win / avg_loss, 2) if avg_loss > 0 and avg_win > 0 else 0.0

        # R-multiples — only over campaigns where we can compute it.
        r_values = []
        for c in camps:
            risk = float(c.get("original_campaign_risk", 0) or 0)
            pnl  = float(c.get("total_pnl_usd", 0))
            if risk > 0:
                r_values.append(pnl / risk)
        total_r = round(sum(r_values), 2) if r_values else 0.0
        avg_r   = round(sum(r_values) / len(r_values), 2) if r_values else 0.0

        # Mark stat-countable buckets — VCP/EP/SWING with valid risk are.
        sample_bucket = camps[0].get("stat_bucket", "") if camps else ""
        stat_countable = ec.is_stat_countable(sample_bucket)

        out[bucket] = {
            "n":               n,
            "wins":            len(wins),
            "losses":          len(losses),
            "win_rate":        round(len(wins) / n, 3) if n else 0.0,
            "total_pnl_usd":   round(total_pnl, 2),
            "avg_pnl_usd":     round(total_pnl / n, 2) if n else 0.0,
            "payoff":          payoff,
            "total_r":         total_r,
            "avg_r":           avg_r,
            "stat_countable":  stat_countable,
            "label":           _SETUP_LABELS.get(bucket, bucket or "ללא setup"),
        }
    return out


def best_and_worst(breakdown: dict) -> tuple[Optional[str], Optional[str]]:
    """Return (best_bucket, worst_bucket) by expectancy R. Skips buckets
    with no stat-countable data. Returns (None, None) when fewer than 2
    eligible buckets."""
    eligible = [
        (bucket, data) for bucket, data in breakdown.items()
        if data["n"] >= 2 and data["stat_countable"]
    ]
    if len(eligible) < 2:
        return None, None
    eligible.sort(key=lambda kv: kv[1]["avg_r"], reverse=True)
    return eligible[0][0], eligible[-1][0]


def render_breakdown(breakdown: dict) -> str:
    """Render a Telegram-friendly RTL Hebrew block. Splits each setup
    onto its own paragraph with a 3-line summary."""
    RTL = "‏"
    if not breakdown:
        return f"{RTL}📊 *ביצועי Setup*\n{RTL}אין קמפיינים סגורים להצגה."

    # Sort: stat-countable first, by avg_r descending; non-countable last.
    items = list(breakdown.items())
    items.sort(key=lambda kv: (
        not kv[1]["stat_countable"],     # countable first
        -kv[1]["avg_r"],                 # then by avg_r desc
    ))
    lines = [
        f"{RTL}📊 *ביצועי Setup* (כל הקמפיינים הסגורים)",
        f"{RTL}───────────────────",
    ]
    for bucket, d in items:
        if d["n"] == 0:
            continue
        countable_tag = "" if d["stat_countable"] else " _(לא נכלל בסטטיסטיקה)_"
        lines.append("")
        lines.append(f"{RTL}*{d['label']}*{countable_tag}")
        lines.append(
            f"{RTL}  `{d['n']}` קמפיינים | "
            f"win-rate `{d['win_rate']*100:.0f}%` | "
            f"payoff `{d['payoff']:.1f}x`"
        )
        if d["n"] > 0 and d["stat_countable"] and d["total_r"] != 0:
            lines.append(
                f"{RTL}  סה\"כ: `{d['total_r']:+.1f}R` | "
                f"ממוצע לעסקה: `{d['avg_r']:+.2f}R`"
            )
        lines.append(
            f"{RTL}  PnL סה\"כ: `${d['total_pnl_usd']:+,.0f}`"
        )

    best, worst = best_and_worst(breakdown)
    if best and worst and best != worst:
        b_label = breakdown[best]["label"]
        w_label = breakdown[worst]["label"]
        b_r = breakdown[best]["avg_r"]
        w_r = breakdown[worst]["avg_r"]
        lines.append("")
        lines.append(f"{RTL}───────────────────")
        lines.append(
            f"{RTL}💡 *תובנה:* *{b_label}* (`{b_r:+.2f}R`) מנצח את "
            f"*{w_label}* (`{w_r:+.2f}R`) בממוצע — שקול הקצאה גדולה יותר."
        )
    return "\n".join(lines)
