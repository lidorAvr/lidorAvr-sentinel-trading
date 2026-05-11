"""
chart_generator.py — generate static PNG charts for PDF reports.
Uses Plotly + Kaleido. Falls back gracefully when Kaleido is not installed.
All functions return a file path (str) on success, or None on failure.
"""
import os
from typing import Optional

try:
    import plotly.graph_objects as go
    import plotly.io as pio
    _PLOTLY_OK = True
except ImportError:
    _PLOTLY_OK = False

_CHARTS_DIR = "/app/reports/charts"

# Palette (matches report_base.css brand colours)
_BLUE       = "#2563eb"
_DARK_BLUE  = "#1e3a5f"
_GREEN      = "#059669"
_RED        = "#dc2626"
_YELLOW     = "#d97706"
_GREY_BG    = "#f8fafc"
_GRID_COL   = "#e5e7eb"

# Standard export size (matches A4 column width at ~96 dpi → ~520px)
_W, _H = 520, 260


# ── Public API ─────────────────────────────────────────────────────────────────

def campaign_r_bars(analytics: dict, period_label: str, out_dir: Optional[str] = None) -> Optional[str]:
    """
    Horizontal bar chart: Net R per closed campaign, sorted descending.
    Used in weekly report Page 2.
    """
    if not _PLOTLY_OK:
        return None
    campaigns = analytics.get("_campaigns")   # raw list injected by renderer
    if not campaigns:
        return _fallback_bar(analytics, period_label, out_dir, "weekly_campaign_r")
    try:
        labels = [c.get("symbol", "?") for c in campaigns]
        values = [c.get("net_r", 0.0)  for c in campaigns]
        # Sort by value
        pairs  = sorted(zip(values, labels), key=lambda x: x[0])
        values, labels = [p[0] for p in pairs], [p[1] for p in pairs]
        colors = [_GREEN if v >= 0 else _RED for v in values]

        fig = go.Figure(go.Bar(
            x=values, y=labels,
            orientation="h",
            marker_color=colors,
            text=[f"{v:+.2f}R" for v in values],
            textposition="outside",
            textfont=dict(size=9),
        ))
        _style_fig(fig, f"Net R לפי קמפיין — {period_label}", xaxis_title="Net R")
        fig.update_layout(height=max(_H, len(labels) * 22 + 60))
        return _save(fig, "weekly_campaign_r", out_dir)
    except Exception:
        return None


def setup_performance_bars(analytics: dict, period_label: str, out_dir: Optional[str] = None) -> Optional[str]:
    """
    Horizontal bar chart: Net R per setup type.
    Used in weekly (Page 3) and monthly (Page 3) reports.
    """
    if not _PLOTLY_OK:
        return None
    breakdown = analytics.get("setup_breakdown", {})
    if not breakdown:
        return None
    try:
        items  = sorted(breakdown.items(), key=lambda x: x[1]["net_r"])
        setups = [k for k, _ in items]
        net_rs = [v["net_r"] for _, v in items]
        wrs    = [v["win_rate"] * 100 for _, v in items]
        colors = [_GREEN if r >= 0 else _RED for r in net_rs]

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=net_rs, y=setups, orientation="h",
            name="Net R",
            marker_color=colors,
            text=[f"{r:+.2f}R" for r in net_rs],
            textposition="outside",
            textfont=dict(size=9),
        ))
        fig.add_trace(go.Scatter(
            x=wrs, y=setups, mode="markers",
            name="Win%",
            marker=dict(color=_DARK_BLUE, size=8, symbol="diamond"),
            xaxis="x2",
        ))
        fig.update_layout(
            xaxis2=dict(overlaying="x", side="top", title="Win%",
                        showgrid=False, range=[0, 120],
                        tickfont=dict(size=8), title_font=dict(size=9)),
        )
        _style_fig(fig, f"ביצועי Setups — {period_label}", xaxis_title="Net R")
        fig.update_layout(height=max(_H, len(setups) * 28 + 80), legend=dict(
            orientation="h", y=-0.15, font=dict(size=9)))
        return _save(fig, "setup_performance", out_dir)
    except Exception:
        return None


def weekly_equity_curve(weekly_breakdown: list, period_label: str, out_dir: Optional[str] = None) -> Optional[str]:
    """
    Bar chart: Net R per week over a monthly period.
    Used in monthly report Page 2.
    """
    if not _PLOTLY_OK or not weekly_breakdown:
        return None
    try:
        labels   = [w["label"] for w in weekly_breakdown]
        net_rs   = [w["net_r"] for w in weekly_breakdown]
        cum_rs   = []
        running  = 0.0
        for r in net_rs:
            running += r
            cum_rs.append(round(running, 3))
        colors = [_GREEN if r >= 0 else _RED for r in net_rs]

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=labels, y=net_rs,
            name="Net R שבועי",
            marker_color=colors,
            text=[f"{r:+.2f}R" for r in net_rs],
            textposition="outside",
            textfont=dict(size=9),
        ))
        fig.add_trace(go.Scatter(
            x=labels, y=cum_rs, mode="lines+markers",
            name="R מצטבר",
            line=dict(color=_DARK_BLUE, width=2),
            marker=dict(size=6),
        ))
        _style_fig(fig, f"Net R שבועי — {period_label}", yaxis_title="R")
        fig.update_layout(legend=dict(orientation="h", y=-0.2, font=dict(size=9)))
        return _save(fig, "monthly_equity_curve", out_dir)
    except Exception:
        return None


def win_loss_donut(analytics: dict, period_label: str, out_dir: Optional[str] = None) -> Optional[str]:
    """
    Donut chart: Win vs Loss count.
    Used in monthly report Page 2.
    """
    if not _PLOTLY_OK:
        return None
    n       = analytics.get("campaigns_closed", 0)
    wr      = analytics.get("win_rate", 0.0)
    wins    = round(n * wr)
    losses  = n - wins
    if n == 0:
        return None
    try:
        fig = go.Figure(go.Pie(
            labels=["ניצחונות", "הפסדים"],
            values=[wins, losses],
            hole=0.55,
            marker_colors=[_GREEN, _RED],
            textinfo="label+percent",
            textfont=dict(size=10),
            direction="clockwise",
        ))
        fig.update_layout(
            title=dict(text=f"Win/Loss — {period_label}", font=dict(size=11, color=_DARK_BLUE),
                       x=0.5, xanchor="center"),
            paper_bgcolor=_GREY_BG,
            plot_bgcolor=_GREY_BG,
            margin=dict(l=10, r=10, t=40, b=10),
            width=_W // 2, height=_H,
            showlegend=False,
            annotations=[dict(text=f"{wr*100:.0f}%<br>Win", x=0.5, y=0.5,
                              font=dict(size=14, color=_DARK_BLUE), showarrow=False)],
        )
        return _save(fig, "monthly_win_loss_donut", out_dir)
    except Exception:
        return None


# ── Internals ──────────────────────────────────────────────────────────────────

def _fallback_bar(analytics: dict, period_label: str, out_dir, name: str) -> Optional[str]:
    """Generate a simple Net R bar from setup_breakdown when raw campaigns unavailable."""
    return setup_performance_bars(analytics, period_label, out_dir)


def _style_fig(fig: "go.Figure", title: str,
               xaxis_title: str = "", yaxis_title: str = ""):
    fig.update_layout(
        title=dict(text=title, font=dict(size=11, color=_DARK_BLUE),
                   x=0.5, xanchor="center"),
        paper_bgcolor=_GREY_BG,
        plot_bgcolor=_GREY_BG,
        width=_W, height=_H,
        margin=dict(l=10, r=20, t=40, b=40),
        xaxis=dict(
            title=dict(text=xaxis_title, font=dict(size=9)),
            gridcolor=_GRID_COL,
            zerolinecolor=_GRID_COL,
            tickfont=dict(size=8),
        ),
        yaxis=dict(
            title=dict(text=yaxis_title, font=dict(size=9)),
            gridcolor=_GRID_COL,
            tickfont=dict(size=8),
        ),
        font=dict(family="Arial, sans-serif"),
    )


def _save(fig: "go.Figure", name: str, out_dir: Optional[str]) -> Optional[str]:
    """Write PNG to disk. Returns path or None."""
    try:
        directory = out_dir or _CHARTS_DIR
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, f"{name}.png")
        fig.write_image(path, format="png", engine="kaleido")
        return path
    except Exception:
        return None
