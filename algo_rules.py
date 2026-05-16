"""
algo_rules.py — static per-symbol ALGO §1 known stop/exit data + pure lookup.

NEW pure leaf (Sprint-17 Wave-2, #4). NO imports of bot / supabase / engine
state / network — static data + pure functions only, so it is trivially safe
to import anywhere and cannot mutate anything.

Source of truth: docs/teams/ALGO_REFERENCE_2026_05_16.md §1 (founder real data),
display wording transcribed VERBATIM from docs/teams/MARK_SPRINT17_RULINGS.md §3
(the #4 display contract). Nothing here is invented.

Observation-only (DEC-20260511-001): every string describes the ALGO's OWN rule
that Sentinel *observes*. It is NEVER an instruction to the ALGO, NEVER a
Sentinel-set or Sentinel-guaranteed stop, NEVER a Task, and is NEVER counted in
any statistic (AGENTS.md #8). The honesty mandate (AGENTS.md #1): "no hard stop
→ time-exit controlled" is stated as a *fact about the ALGO's design*, not a
Sentinel defect; an unknown symbol returns None (we never fabricate a rule).
"""

# Backtest caveat (MARK_SPRINT17_RULINGS.md §5 — verbatim, non-suppressible).
# Re-exported here so every ALGO-stat / ALGO-rule surface can attach it without
# importing the metrics module.
ALGO_BACKTEST_CAVEAT_HE = (
    "‏נתוני ALGO = בק-טסט (ללא עמלות/החלקה/הון אמיתי) — לא טראק-רקורד חי."
)
ALGO_BACKTEST_CAVEAT_EN = (
    "ALGO stats = backtest (no fees/slippage/real capital) — "
    "not a live track record."
)

# ── Per-symbol known rules (ALGO_REFERENCE §1; display = MARK §3 verbatim) ────
#
# Keys are factual, observation-only descriptors. `display` is the exact Hebrew
# line MARK ruled must replace the bare "Unknown" (MARK §3 table). `time_exits`
# (when present) is also the #5 strategy-adaptive dead-money signal source.
ALGO_KNOWN_RULES = {
    "QQQ": {
        "hard_stop_pct": None,           # §1: "none (hard)" — no hard stop
        "emergency_cushion_pct": None,
        "time_exits": "3c<−2% · 33c<0% · 46c<1.7% · 90c<11%",   # §1 QQQ
        "tp_pct": 11.0,                  # §1 "+11%"
        "tech_exit": "SMA16 ↓ SMA51",    # §1
        # MARK §3 verbatim:
        "display": ("ALGO ללא סטופ קשיח — נשלט ביציאות-זמן "
                    "(3c<−2% · 33c<0% · 46c<1.7% · 90c<11%)"),
    },
    "HOOD": {
        "hard_stop_pct": None,           # §1: "none (hard)"
        "emergency_cushion_pct": None,
        "time_exits": "10c<4% · 65c<25% · 85c<40%",             # §1 HOOD
        "tp_pct": 80.0,                  # §1 "+80%"
        "tech_exit": "EMA21 ↑ EMA9",     # §1
        "display": ("ALGO ללא סטופ קשיח — נשלט ביציאות-זמן "
                    "(10c<4% · 65c<25% · 85c<40%)"),
    },
    "TSLA": {
        "hard_stop_pct": -4.3,           # §1 "−4.3%"
        "emergency_cushion_pct": None,
        "time_exits": None,              # §1: "—" (MA-cross / TP / hard-stop)
        "tp_pct": 25.0,                  # §1 "+25%"
        "tech_exit": "SMA5 ↓ SMA34",     # §1
        "display": "סטופ ALGO ידוע: −4.3%",                     # MARK §3
    },
    "JPM": {
        "hard_stop_pct": -3.3,           # §1 "−3.3%"
        "emergency_cushion_pct": None,
        "time_exits": None,              # §1: "—"
        "tp_pct": 18.0,                  # §1 "+18%"
        "tech_exit": "SMA6 ↓ SMA40",     # §1
        "display": "סטופ ALGO ידוע: −3.3%",                     # MARK §3
    },
    "PLTR": {
        "hard_stop_pct": None,           # no management stop
        "emergency_cushion_pct": -25.0,  # §1 "−25% (emergency cushion)"
        "time_exits": "230c if loss>14.8% · 295c if loss>12%",  # §1 PLTR
        "tp_pct": 16.0,                  # §1 "+16% (after candle close)"
        "tech_exit": None,               # §1: "—"
        "display": ("אין סטופ ניהולי — כרית חירום בלבד −25% "
                    "(יציאות-זמן: 230c אם הפסד>14.8% · 295c אם >12%)"),
    },
}


def get_algo_known_rule(symbol):
    """Return the static §1 known-rule dict for `symbol`, or None.

    Exact uppercase match only. An unknown symbol → None (we never fabricate a
    rule — honesty mandate, AGENTS.md #1). Pure: no I/O, no mutation.
    """
    if symbol is None:
        return None
    rule = ALGO_KNOWN_RULES.get(str(symbol).upper())
    # Return a shallow copy so callers cannot mutate the module-level table.
    return dict(rule) if rule is not None else None


def describe_algo_risk_control(symbol):
    """One honest Hebrew line describing the ALGO's OWN risk control for
    `symbol` (observed, NOT enforced by Sentinel). Unknown symbol → None, so
    the caller keeps the existing "Unknown" (never a fabricated rule).

    Pure & descriptive — contains no imperative verb; it states what the ALGO's
    design *is* (MARK §3 honesty mandate), never "do X".
    """
    rule = get_algo_known_rule(symbol)
    if rule is None:
        return None
    return rule["display"]


def algo_time_exit_signal(symbol):
    """#5 source: the ALGO's OWN §1 time-exit descriptor for `symbol`, or None.

    QQQ/HOOD/PLTR have §1 time-exits (their non-working signal). TSLA/JPM have
    NO ALGO time-exit (§1: MA-cross / TP / hard-stop controlled) → returns None,
    so the caller emits NO ALGO dead-money signal for them (MARK §4 — honest;
    the generic 0.75R is NOT applied to ALGO). Pure, no I/O.
    """
    rule = get_algo_known_rule(symbol)
    if rule is None:
        return None
    return rule.get("time_exits")
