"""algo_divergence.py — Phase ALGO-2A (W-2A1 pure divergence helper).

Read-only, deterministic, observe-only **edge-shape** divergence between the
live ALGO cohort (already isolated by `algo_metrics.build_algo_cohort` /
`engine_core.is_algo_position` → `STAT_BUCKET_ALGO`) and the externally
managed bot's TrendSpider **backtest** stats (already computed by
`algo_backtest_store.compute_algo_backtest_stats`), joined **by SYMBOL only**.

OBSERVE-ONLY DOCTRINE (INVIOLABLE — AGENTS.md #8 / DEC-20260511-001 /
PHASE_ALGO2A_SCOPE §4): ZERO directive, ZERO push, ZERO Supabase write,
ZERO state mutation, ZERO new message TYPE. The divergence is display /
disclosure only — NEVER a recommendation, NEVER fed into
WR / Expectancy / PF / Net-R / edge / headline. Neutral `🔭` only — no
🔴/🟢 verdict colour, no imperative verb; max wording is "דרוש עיון",
NEVER "דרושה פעולה".

PURITY / IMPORT DISCIPLINE (SCOPE §2): this module imports **none** of
`engine_core` / `analytics_engine` / `period_data_probe` / Supabase /
network. It only re-uses the verbatim Hebrew label constants from the
pure leaves `algo_backtest_store` (no engine/network coupling — csv/math/
os/statistics only) and `algo_rules` (pure static data, no imports). The
live ALGO cohort aggregates are passed IN by the caller (obtained via the
existing `algo_metrics` helpers on the caller's side) — this helper never
reaches for live state itself.

HONESTY (SCOPE §3): a hard min-live-sample gate mirrors the
`algo_metrics.ALGO_COHORT_WINDOW = 30` discipline. Below the floor we emit
an explicit Hebrew "not enough live sample" marker and NEVER a delta and
NEVER a silent zero (zero-as-truth is forbidden — a missing/empty side is
an honest empty marker, never 0). Every surfaced figure carries the
existing `BACKTEST_LABEL` + `OBSERVE_ONLY_LABEL` + the 6 honesty
disclaimers + the founder-asserted (NOT system-verified) join banner.

ANTI-DRIFT (SCOPE §5): `format_symbol_divergence` is the **single source
of truth** for the displayed text. BOTH surfaces (the Telegram ALGO panel
and the dashboard ALGO-backtest panel) call THIS one formatter — neither
formats independently, so the two surfaces are byte-identical by
construction.

Never raises (boundary-input discipline): any missing / malformed / empty
input degrades to an honest marker, never a crash and never a fabricated
number.
"""
import math
from typing import Any, Dict, Optional

# Re-use the EXISTING verbatim Hebrew label constants — do NOT duplicate the
# strings (SCOPE §3). Both leaves are pure (no engine/Supabase/network).
from algo_backtest_store import BACKTEST_LABEL, OBSERVE_ONLY_LABEL
from algo_rules import ALGO_BACKTEST_CAVEAT_HE

# ── Hard min-live-sample gate (SCOPE §3 #1) ─────────────────────────────────
# Mirror the algo_metrics.ALGO_COHORT_WINDOW = 30 discipline WITHOUT importing
# algo_metrics (it transitively imports engine_core). The value is duplicated
# here as a deliberate, documented purity boundary; the cross-suite test pins
# it equal to algo_metrics.ALGO_COHORT_WINDOW so the two can never silently
# drift.
MIN_LIVE_SAMPLE = 30

# ── Honesty disclaimers (SCOPE §3) — Hebrew, RTL-friendly, observe-only ─────
# #1 hard min-sample gate text (NEVER a delta, NEVER a silent zero):
INSUFFICIENT_LIVE_SAMPLE_HE = (
    "אין מספיק מדגם חי — לא מוצג הפרש (לא חוסר, לא איתות)"
)
# #2 date-window / regime mismatch:
WINDOW_REGIME_MISMATCH_HE = "חלון בקטסט שונה ממסחר חי — אינדיקטיבי בלבד"
# #3 survivorship / look-ahead:
SURVIVORSHIP_HE = "בקטסט עלול לכלול הטיית-היסטוריה"
# #4 Volume=1 / cost=0 / no-slippage → reuse the EXISTING BACKTEST_LABEL
#    verbatim (do NOT duplicate the string).
NO_COST_HE = BACKTEST_LABEL
# #5 long-only-vs-live:
LONG_ONLY_HE = "אסטרטגיות לונג-בלבד — לא חופף למסחר החי"
# #6 multiple-comparisons (5 strategies):
MULTIPLE_COMPARISONS_HE = "5 השוואות — חריגה בודדת אינה הוכחה"
# Mandatory join banner — founder-asserted, NOT system-verified (SCOPE §3):
JOIN_BANNER_HE = (
    "הצמדה לפי-סימול · אותה-אסטרטגיה לפי אישור המנהל · לא מאומת אוטומטית"
)
# Mandatory non-suppressible backtest caveat (re-used verbatim from
# algo_rules — same constant the existing handle_algo_panel already appends).
BACKTEST_CAVEAT_HE = ALGO_BACKTEST_CAVEAT_HE

# Neutral observe-only marker — NO 🔴/🟢 verdict colour (SCOPE §4).
MARKER = "🔭"

# The full ordered disclaimer bundle (always shown with any divergence text).
ALL_DISCLAIMERS_HE = (
    WINDOW_REGIME_MISMATCH_HE,
    SURVIVORSHIP_HE,
    NO_COST_HE,
    LONG_ONLY_HE,
    MULTIPLE_COMPARISONS_HE,
)


# ── small pure helpers ──────────────────────────────────────────────────────

def _finite_float(v: Any) -> Optional[float]:
    """Best-effort finite-float read. Returns None (never raises, never a
    fabricated 0.0) when the value is missing / non-numeric / non-finite."""
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return f


def _finite_int(v: Any) -> Optional[int]:
    """Best-effort non-negative int read (sample sizes / streaks). None on
    any non-numeric / negative / non-finite input (never a fabricated 0)."""
    f = _finite_float(v)
    if f is None or f < 0:
        return None
    return int(f)


def _fmt_pct(v: Optional[float]) -> str:
    """Signed-% display, or the honest empty marker '—' (never '0.00%' as a
    stand-in for missing — zero-as-truth is forbidden, SCOPE §3)."""
    return f"{v:+.2f}%" if v is not None else "—"


def _fmt_num(v: Optional[float]) -> str:
    return f"{v:.2f}" if v is not None else "—"


def _fmt_pf(v: Optional[float]) -> str:
    """Profit-factor display: '∞' for an honest no-loss infinite, '—' for a
    missing side, else 2dp."""
    if v is None:
        return "—"
    if math.isinf(v):
        return "∞"
    return f"{v:.2f}"


def _delta(live: Optional[float], bt: Optional[float]) -> Optional[float]:
    """live − backtest, ONLY when BOTH sides are honest finite numbers;
    otherwise None (honest empty — never a zero-as-truth delta)."""
    if live is None or bt is None:
        return None
    return live - bt


def _pf_delta(live: Optional[float], bt: Optional[float]) -> Optional[float]:
    """PF delta is only meaningful when BOTH PFs are finite; an ∞ on either
    side ⇒ None (no fabricated finite delta from an infinity)."""
    if live is None or bt is None:
        return None
    if math.isinf(live) or math.isinf(bt):
        return None
    return live - bt


# ── live-aggregate extraction (per symbol; caller passes algo_metrics output)─

def _live_symbol_aggregates(
    symbol: str, live_aggregates: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Pull the per-symbol live ALGO edge-shape aggregates out of the dict
    the CALLER built from the existing `algo_metrics` helpers.

    Accepted shapes (read-only, never mutated; missing ⇒ honest None, never
    a fabricated 0):
      * ``{"<SYMBOL>": {"n":, "win_rate_pct":, "median_return_pct" |
        "avg_return_pct":, "profit_factor":, "loss_streak":}, ...}``
      * a flat single-symbol dict with the same inner keys.

    Returns a normalised dict with ``n`` / ``win_rate_pct`` /
    ``return_pct`` / ``return_basis`` / ``profit_factor`` / ``loss_streak``,
    each value either an honest number or None.
    """
    sym = (symbol or "").strip().upper()
    src: Dict[str, Any] = {}
    if isinstance(live_aggregates, dict):
        by_sym = live_aggregates.get(sym)
        if isinstance(by_sym, dict):
            src = by_sym
        elif not any(isinstance(v, dict) for v in live_aggregates.values()):
            # flat single-symbol aggregate dict
            src = live_aggregates

    # SCOPE §1 — "median (or avg, match what algo_metrics exposes)". The
    # live cohort path (`algo_metrics`) exposes the MEAN per-trade return
    # (`_expectancy`), so AVG is the canonical comparable basis; median is a
    # graceful fallback only if avg is absent. Basis is surfaced honestly so
    # the displayed line never claims a basis it did not use.
    avg = _finite_float(src.get("avg_return_pct"))
    med = _finite_float(src.get("median_return_pct"))
    if avg is not None:
        ret, basis = avg, "ממוצע"
    elif med is not None:
        ret, basis = med, "חציון"
    else:
        ret, basis = None, "—"

    return {
        "n": _finite_int(src.get("n")),
        "win_rate_pct": _finite_float(src.get("win_rate_pct")),
        "return_pct": ret,
        "return_basis": basis,
        "profit_factor": _finite_float(src.get("profit_factor")),
        "loss_streak": _finite_int(src.get("loss_streak")),
    }


def _backtest_symbol_aggregates(
    symbol: str, backtest_stats: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Pull the per-symbol backtest edge-shape aggregates out of the
    `algo_backtest_store.compute_algo_backtest_stats` output (joined by
    SYMBOL only — exactly one backtest strategy per symbol, SCOPE §1).

    Returns the same normalised shape as ``_live_symbol_aggregates`` with an
    extra ``present`` flag; a missing symbol ⇒ all-None, ``present=False``
    (honest empty, never a fabricated 0).
    """
    sym = (symbol or "").strip().upper()
    out = {
        "present": False,
        "n": None,
        "win_rate_pct": None,
        "return_pct": None,
        "return_basis": "—",
        "profit_factor": None,
        "loss_streak": None,
    }
    if not isinstance(backtest_stats, dict):
        return out
    strategies = backtest_stats.get("strategies")
    if not isinstance(strategies, dict):
        return out
    # Join by SYMBOL only (one strategy per symbol).
    match = None
    for s in strategies.values():
        if isinstance(s, dict) and \
                str(s.get("symbol", "")).strip().upper() == sym:
            match = s
            break
    if match is None:
        return out

    # Same canonical basis as the live side (AVG first, median fallback) so
    # the join compares like-for-like; basis surfaced honestly.
    avg = _finite_float(match.get("avg_return_pct"))
    med = _finite_float(match.get("median_return_pct"))
    if avg is not None:
        ret, basis = avg, "ממוצע"
    elif med is not None:
        ret, basis = med, "חציון"
    else:
        ret, basis = None, "—"
    # profit_factor may be math.inf (honest no-loss) — keep it, do NOT coerce.
    pf_raw = match.get("profit_factor")
    pf: Optional[float]
    if isinstance(pf_raw, (int, float)) and not isinstance(pf_raw, bool):
        pf = float(pf_raw) if math.isinf(float(pf_raw)) \
            else _finite_float(pf_raw)
    else:
        pf = None

    out.update({
        "present": True,
        "n": _finite_int(match.get("n")),
        "win_rate_pct": _finite_float(match.get("win_rate_pct")),
        "return_pct": ret,
        "return_basis": basis,
        "profit_factor": pf,
        "loss_streak": _finite_int(match.get("longest_loss_streak")),
    })
    return out


# ── W-2A1 — pure per-symbol divergence (read-only, never raises) ────────────

def compute_symbol_divergence(
    symbol: str,
    live_aggregates: Optional[Dict[str, Any]],
    backtest_stats: Optional[Dict[str, Any]],
    min_live_sample: int = MIN_LIVE_SAMPLE,
) -> Dict[str, Any]:
    """Pure, deterministic, read-only per-symbol edge-shape delta joined by
    SYMBOL only. NEVER raises; NEVER mutates input; NEVER fabricates a zero
    for a missing side; NEVER feeds WR/Expectancy/PF/Net-R/edge/headline.

    Returns a self-contained dict (observe-only — no directive, no state):

      symbol            uppercased symbol
      enough_sample     bool — live n >= min_live_sample (hard gate)
      live_n            live ALGO cohort N for this symbol (or None)
      backtest_present  whether a backtest strategy exists for this symbol
      win_rate_delta / return_delta / profit_factor_delta / loss_streak_delta
                        live − backtest, ONLY when BOTH sides are honest
                        finite numbers; otherwise None (honest empty)
      live / backtest   the normalised per-side aggregates (for display)
      disclaimers       the ordered Hebrew honesty disclaimer bundle
      join_banner / backtest_label / observe_only_label / backtest_caveat
                        the mandatory non-suppressible labels

    Below the hard min-live-sample gate ⇒ ``enough_sample=False`` and ALL
    delta fields are None (the formatter then emits the explicit
    "אין מספיק מדגם חי" marker — never a delta, never a silent zero).
    """
    sym = (symbol or "").strip().upper()
    try:
        floor = int(min_live_sample)
    except (TypeError, ValueError):
        floor = MIN_LIVE_SAMPLE
    if floor < 0:
        floor = MIN_LIVE_SAMPLE

    live = _live_symbol_aggregates(sym, live_aggregates)
    bt = _backtest_symbol_aggregates(sym, backtest_stats)

    live_n = live["n"]
    enough = live_n is not None and live_n >= floor

    result: Dict[str, Any] = {
        "symbol": sym,
        "enough_sample": enough,
        "min_live_sample": floor,
        "live_n": live_n,
        "backtest_present": bool(bt["present"]),
        "win_rate_delta": None,
        "return_delta": None,
        "return_basis": None,
        "profit_factor_delta": None,
        "loss_streak_delta": None,
        "live": live,
        "backtest": bt,
        "disclaimers": list(ALL_DISCLAIMERS_HE),
        "join_banner": JOIN_BANNER_HE,
        "backtest_label": BACKTEST_LABEL,
        "observe_only_label": OBSERVE_ONLY_LABEL,
        "backtest_caveat": BACKTEST_CAVEAT_HE,
        "insufficient_sample_text": INSUFFICIENT_LIVE_SAMPLE_HE,
    }

    # Hard min-sample gate: below the live-N floor ⇒ NEVER a delta, NEVER a
    # zero-as-truth. The structured deltas stay None and the formatter shows
    # the explicit "not enough live sample" marker.
    if not enough:
        return result

    # Deltas are computed ONLY when BOTH sides are honest finite numbers.
    result["win_rate_delta"] = _delta(
        live["win_rate_pct"], bt["win_rate_pct"])
    result["return_delta"] = _delta(live["return_pct"], bt["return_pct"])
    result["return_basis"] = (
        live["return_basis"] if result["return_delta"] is not None else None
    )
    result["profit_factor_delta"] = _pf_delta(
        live["profit_factor"], bt["profit_factor"])
    result["loss_streak_delta"] = _delta(
        (None if live["loss_streak"] is None
         else float(live["loss_streak"])),
        (None if bt["loss_streak"] is None
         else float(bt["loss_streak"])),
    )
    return result


# ── W-2A1 — THE single pure formatter (SINGLE SOURCE OF TRUTH) ──────────────

def format_symbol_divergence(
    symbol: str,
    live_aggregates: Optional[Dict[str, Any]],
    backtest_stats: Optional[Dict[str, Any]],
    min_live_sample: int = MIN_LIVE_SAMPLE,
) -> str:
    """THE single source of truth for the displayed per-symbol divergence
    text (SCOPE §5 anti-drift). BOTH surfaces — the Telegram ALGO panel and
    the dashboard ALGO-backtest panel — call THIS one formatter so the two
    are byte-identical by construction.

    Pure: no I/O, no side effect, no state, never raises. Observe-only:
    neutral `🔭` only (no 🔴/🟢, no imperative verb); max wording
    "דרוש עיון", never "דרושה פעולה". Below the hard min-live-sample gate
    ⇒ the explicit "אין מספיק מדגם חי" marker, NEVER a delta / zero.

    Output is a single multi-line block (Hebrew, RTL-friendly). It is
    deterministic for a given input — calling twice yields an identical
    string.
    """
    d = compute_symbol_divergence(
        symbol, live_aggregates, backtest_stats, min_live_sample)
    sym = d["symbol"]

    # Mandatory non-suppressible labels + the founder-asserted join banner +
    # the full disclaimer bundle, always present with ANY divergence text.
    tail = (
        f"{MARKER} {sym}: {d['join_banner']}\n"
        f"{MARKER} {OBSERVE_ONLY_LABEL} · {BACKTEST_LABEL}\n"
        f"{MARKER} {' · '.join(d['disclaimers'])}\n"
        f"{MARKER} {BACKTEST_CAVEAT_HE}"
    )

    # Hard min-sample gate (SCOPE §3 #1): explicit honest marker — NEVER a
    # delta, NEVER a silent zero. "דרוש עיון" wording only, no imperative.
    if not d["enough_sample"]:
        return (
            f"{MARKER} {sym}: הפרש חי↔בקטסט — {INSUFFICIENT_LIVE_SAMPLE_HE} "
            f"(דרוש עיון, לא פעולה)\n"
            f"{tail}"
        )

    if not d["backtest_present"]:
        return (
            f"{MARKER} {sym}: הפרש חי↔בקטסט — אין אסטרטגיית בקטסט תואמת "
            f"לסימול (לא מוצג הפרש; דרוש עיון, לא פעולה)\n"
            f"{tail}"
        )

    basis = d["return_basis"] or "—"
    # Edge-shape deltas only; each missing side ⇒ honest '—', never a zero.
    head = (
        f"{MARKER} {sym}: הפרש edge חי↔בקטסט (תצפית בלבד, לא איתות; "
        f"דרוש עיון, לא פעולה)\n"
        f"{MARKER}  N-חי={d['live_n']} · "
        f"ΔWR={_fmt_pct(d['win_rate_delta'])} · "
        f"Δתשואה({basis})={_fmt_pct(d['return_delta'])} · "
        f"ΔPF={_fmt_num(d['profit_factor_delta'])} · "
        f"Δרצף-L={_fmt_num(d['loss_streak_delta'])}\n"
        f"{MARKER}  חי: WR={_fmt_pct(d['live']['win_rate_pct'])} · "
        f"תשואה={_fmt_pct(d['live']['return_pct'])} · "
        f"PF={_fmt_pf(d['live']['profit_factor'])}  |  "
        f"בקטסט: WR={_fmt_pct(d['backtest']['win_rate_pct'])} · "
        f"תשואה={_fmt_pct(d['backtest']['return_pct'])} · "
        f"PF={_fmt_pf(d['backtest']['profit_factor'])}"
    )
    return f"{head}\n{tail}"
