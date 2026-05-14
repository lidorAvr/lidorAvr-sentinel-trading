"""setup_profile.py — Per-setup methodology parameters.

Single source of truth for the thresholds that DIFFER by setup type.
The research department's 2026-05-14 audit identified that every R-
management rule in the engine was setup-agnostic — meaning EP positions
got VCP-tuned thresholds (e.g., dead-money at 21 days, when EP's shelf
life is ~10 days).

This module centralizes the profile so:
  - task_engine.py reads dead_money_days / dead_money_r per setup
  - validate_initial_stop reads max_initial_stop_pct per setup
  - (future) compute_position_state, compute_follow_through, etc. read
    runner_r, profit_protect_r, ft_peak_full_pct per setup

Profiles are deliberately conservative — when in doubt, fall back to
the VCP profile (the existing system's defaults).
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class SetupProfile:
    """Methodology parameters for one setup type. Frozen — must not be
    mutated at runtime."""
    name: str
    label: str
    # Time-based rules
    dead_money_days: int        # Days after which a non-progressing position is dead-money
    dead_money_r: float         # R-multiple floor below which the position is considered non-progressing
    # R-multiple thresholds
    profit_protect_r: float     # R-multiple where break-even / 1R-lock becomes mandatory
    runner_r: float             # R-multiple where the position is classified as a RUNNER
    # Initial-stop quality
    max_initial_stop_pct: float # Maximum acceptable initial-stop distance from entry (in %)
    marginal_stop_pct_extra: float = 2.0  # +2% above max = "marginal"; beyond = out-of-spec
    # Follow-through peak threshold
    ft_peak_full_pct: float = 7.0


# ── Profiles per setup family ────────────────────────────────────────────────
#
# VCP (Minervini): tight stops, patient hold, profit cushion at 2R, runner at 5R.
VCP = SetupProfile(
    name="VCP",
    label="VCP (Minervini)",
    dead_money_days=21,
    dead_money_r=0.3,
    profit_protect_r=2.0,
    runner_r=5.0,
    max_initial_stop_pct=8.0,    # 5–8% per Minervini
    ft_peak_full_pct=7.0,
)

# EP (Episodic Pivot): faster decay, lower R targets, tight stops.
# Mark's playbook: D1 gap → D2/D3 entry → exit by week 2-3 even if not
# stopped. 2-3R typical. Dead-money window MUST be shorter than VCP.
EP = SetupProfile(
    name="EP",
    label="EP (Episodic Pivot)",
    dead_money_days=10,           # Half of VCP — EP fades fast
    dead_money_r=1.5,             # Higher floor: by D10 should be at +1.5R
    profit_protect_r=1.5,         # Move stop to BE earlier (EP "explosion" zone)
    runner_r=3.0,                 # Lower runner threshold (EP rarely sees 5R)
    max_initial_stop_pct=8.0,     # Same tightness, just at D1-bar-low usually
    ft_peak_full_pct=5.0,         # Lower peak threshold — EP gaps are smaller
)

# SWING: longer hold horizon, more patience for the trade to develop.
SWING = SetupProfile(
    name="SWING",
    label="Swing",
    dead_money_days=14,
    dead_money_r=0.5,
    profit_protect_r=2.0,
    runner_r=4.0,
    max_initial_stop_pct=10.0,    # Wider — swing trades wider stops by design
    ft_peak_full_pct=6.0,
)

# ALGO is externally managed — these values mostly don't apply, but we
# keep a profile so callers don't have to special-case None. ALGO
# positions are skipped at the engine level for management tasks.
ALGO = SetupProfile(
    name="ALGO",
    label="ALGO (חיצוני)",
    dead_money_days=999,
    dead_money_r=-99.0,
    profit_protect_r=999.0,
    runner_r=999.0,
    max_initial_stop_pct=100.0,
    ft_peak_full_pct=99.0,
)


_PROFILES = {
    "VCP":         VCP,
    "VCP_MANUAL":  VCP,    # collapse — same methodology family
    "EP":          EP,
    "EP_MANUAL":   EP,
    "SWING":       SWING,
    "ALGO":        ALGO,
}


def get_profile(setup_type: str) -> SetupProfile:
    """Return the SetupProfile for a setup string. Unknown / empty
    setups fall back to VCP (the most conservative discretionary
    profile). Case-insensitive."""
    if not setup_type:
        return VCP
    return _PROFILES.get(str(setup_type).upper().strip(), VCP)


# ── Stop quality validator ────────────────────────────────────────────────────

# Grade values are used in display + audit. Don't rename without
# updating the consumers (task_engine, display formatters).
STOP_GRADE_IN_SPEC     = "in_spec"
STOP_GRADE_MARGINAL    = "marginal"
STOP_GRADE_OUT_OF_SPEC = "out_of_spec"
STOP_GRADE_MISSING     = "missing"

_GRADE_LABEL_HE = {
    STOP_GRADE_IN_SPEC:     "✅ במתודולוגיה",
    STOP_GRADE_MARGINAL:    "⚠️ גבולי",
    STOP_GRADE_OUT_OF_SPEC: "🔴 חורג מהמתודולוגיה",
    STOP_GRADE_MISSING:     "⚪ לא הוגדר",
}


def validate_initial_stop(entry: float, initial_stop: float,
                           setup_type: str) -> dict:
    """Grade the entry-time stop against the setup's max_initial_stop_pct.

    Returns:
        {
            "in_spec":          bool,
            "grade":            "in_spec"|"marginal"|"out_of_spec"|"missing",
            "label_he":         Hebrew label for display,
            "stop_pct":         actual stop distance in %,
            "max_allowed_pct":  the profile's max,
            "profile_name":     the resolved setup name,
        }

    The Mark research audit (2026-05-14, BLOCKER #2): without this check,
    an `initial_stop = entry × 0.70` produces a 1R loss that's 4× a real
    methodology loss. The engine accepts it silently. After this check,
    `task_engine` can surface a "stop too loose" task and
    `classify_stat_bucket` can mark the campaign as loose-stop.
    """
    profile = get_profile(setup_type)
    if entry is None or initial_stop is None or entry <= 0 or initial_stop <= 0:
        return {
            "in_spec":         False,
            "grade":           STOP_GRADE_MISSING,
            "label_he":        _GRADE_LABEL_HE[STOP_GRADE_MISSING],
            "stop_pct":        0.0,
            "max_allowed_pct": profile.max_initial_stop_pct,
            "profile_name":    profile.name,
        }
    if initial_stop >= entry:
        # Stop above entry doesn't make sense for a long position;
        # treat as missing.
        return {
            "in_spec":         False,
            "grade":           STOP_GRADE_MISSING,
            "label_he":        _GRADE_LABEL_HE[STOP_GRADE_MISSING],
            "stop_pct":        0.0,
            "max_allowed_pct": profile.max_initial_stop_pct,
            "profile_name":    profile.name,
        }
    stop_pct = (entry - initial_stop) / entry * 100.0
    max_ok = profile.max_initial_stop_pct
    marginal_ceil = max_ok + profile.marginal_stop_pct_extra
    if stop_pct <= max_ok:
        grade = STOP_GRADE_IN_SPEC
    elif stop_pct <= marginal_ceil:
        grade = STOP_GRADE_MARGINAL
    else:
        grade = STOP_GRADE_OUT_OF_SPEC
    return {
        "in_spec":         grade == STOP_GRADE_IN_SPEC,
        "grade":           grade,
        "label_he":        _GRADE_LABEL_HE[grade],
        "stop_pct":        round(stop_pct, 2),
        "max_allowed_pct": max_ok,
        "profile_name":    profile.name,
    }
