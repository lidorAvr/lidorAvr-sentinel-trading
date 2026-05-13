"""
addon_risk_engine.py
Add-On / Pyramid Risk Validation Engine for Sentinel

Philosophy: The trader proposes or the system detects eligibility,
but approval depends on campaign risk after the add-on.

This module is pure calculation — no live API calls, no Supabase writes.
All inputs are plain dicts. All outputs are plain dicts.
"""
from __future__ import annotations
import math

# ── Constants ─────────────────────────────────────────────────────────────────
MIN_OPEN_R_FOR_ADDON  = 1.0    # minimum floating open R to consider add-on
MIN_CUSHION_RATIO     = 0.50   # locked_profit >= 50% of orig risk (preferred)
HARD_FLOOR_RATIO      = -0.25  # campaign result never below -25% of original risk
MAX_SIZE_VS_ORIGINAL  = 1.0    # add-on quantity never exceeds original lot size
MAX_SIZE_VS_CURRENT   = 0.50   # add-on quantity never exceeds 50% of current open qty
DEFAULT_SIZE_RATIO    = 0.40   # default suggested add-on = 40% of original qty
CHASE_EXT_LIMIT       = 0.07   # block chase: price > 7% above MA10

# ── Add-on types ──────────────────────────────────────────────────────────────
ADDON_CAMPAIGN = "campaign_add"   # full campaign stop on all lots
ADDON_TACTICAL = "tactical_add"   # tactical stop on add-on only
ADDON_REBUILD  = "rebuild_add"    # after partial profit-taking, new base

# ── Stop modes ────────────────────────────────────────────────────────────────
STOP_UNIFIED = "UNIFIED_CAMPAIGN_STOP"
STOP_LAYERED = "LAYERED_TACTICAL_STOP"

# ── Decision labels ───────────────────────────────────────────────────────────
APPROVED      = "APPROVED"
WATCH         = "WATCH"
BLOCKED       = "BLOCKED"
MANUAL_REVIEW = "MANUAL_REVIEW_REQUIRED"

ADD_REASONS = {
    "VCP_TIGHT":             "VCP — צמצום לפני יציאה",
    "PULLBACK_TO_MA10":      "פולבק ל-MA10",
    "PULLBACK_TO_MA20":      "פולבק ל-MA20",
    "BREAKOUT_CONTINUATION": "המשך פריצה",
    "HIGH_TIGHT_FLAG":       "High Tight Flag",
    "MANUAL":                "ידני",
}


# ── Campaign lot state computation ────────────────────────────────────────────

def compute_campaign_lot_state(
    base_price: float,
    base_qty: float,
    current_qty: float,
    stop_loss: float,
    initial_stop: float,
    realized_pnl_usd: float,
    current_price: float,
    setup_type: str = "EP",
) -> dict:
    """
    Derive campaign state from existing open position data.

    Inputs (from get_open_positions_campaign row):
      base_price       — weighted avg entry of first-day buys
      base_qty         — quantity on entry day (for original risk calc)
      current_qty      — net open quantity today
      stop_loss        — current (possibly raised) stop
      initial_stop     — stop at entry (for original risk)
      realized_pnl_usd — PnL from partial sells
      current_price    — live or cached price
      setup_type       — "EP", "VCP", "ALGO", etc.

    Returns dict:
      original_risk_usd      — (base_price - initial_stop) * base_qty
      open_pnl_usd           — floating PnL on current open qty
      total_pnl_usd          — open_pnl + realized
      locked_profit_usd      — (stop - base_price) * current_qty if stop > entry
      open_risk_usd          — (base_price - stop) * current_qty if stop < entry
      net_result_if_stop_hit — what campaign earns/loses if current stop is hit
      open_r                 — open_pnl / original_risk (floating)
      total_r                — total_pnl / original_risk (including realized)
      cushion_ratio          — locked_profit / original_risk
      data_complete          — False if original_risk can't be computed
    """
    is_algo = str(setup_type).upper() == "ALGO"

    original_risk_usd = 0.0
    data_complete = True

    if initial_stop > 0 and initial_stop < base_price and base_qty > 0:
        original_risk_usd = (base_price - initial_stop) * base_qty
    else:
        data_complete = False

    open_pnl_usd = (current_price - base_price) * current_qty
    total_pnl_usd = open_pnl_usd + realized_pnl_usd

    # Profit locked in raised stop (stop above entry)
    locked_profit_usd = max(0.0, (stop_loss - base_price) * current_qty) if stop_loss > base_price else 0.0

    # Capital still at risk (stop below entry)
    open_risk_usd = max(0.0, (base_price - stop_loss) * current_qty) if stop_loss < base_price else 0.0

    # If stopped right now, what does the campaign earn?
    net_result_if_stop_hit = realized_pnl_usd + (stop_loss - base_price) * current_qty

    # R multiples
    open_r  = open_pnl_usd / original_risk_usd if original_risk_usd > 0 else None
    total_r = total_pnl_usd / original_risk_usd if original_risk_usd > 0 else None
    cushion_ratio = locked_profit_usd / original_risk_usd if original_risk_usd > 0 else 0.0

    return {
        "original_risk_usd":      round(original_risk_usd, 2),
        "open_pnl_usd":           round(open_pnl_usd, 2),
        "total_pnl_usd":          round(total_pnl_usd, 2),
        "locked_profit_usd":      round(locked_profit_usd, 2),
        "open_risk_usd":          round(open_risk_usd, 2),
        "net_result_if_stop_hit": round(net_result_if_stop_hit, 2),
        "open_r":                 round(open_r, 2) if open_r is not None else None,
        "total_r":                round(total_r, 2) if total_r is not None else None,
        "cushion_ratio":          round(cushion_ratio, 3),
        "base_price":             base_price,
        "base_qty":               base_qty,
        "current_qty":            current_qty,
        "stop_loss":              stop_loss,
        "current_price":          current_price,
        "realized_pnl_usd":       realized_pnl_usd,
        "is_algo":                is_algo,
        "data_complete":          data_complete,
    }


# ── Eligibility gate ──────────────────────────────────────────────────────────

def check_addon_eligibility(
    lot_state: dict,
    add_reason: str = "MANUAL",
    market_features: dict | None = None,
) -> dict:
    """
    Multi-gate eligibility check for add-on approval.

    market_features (optional, from engine_core.evaluate_position_engine features):
      ext10        — % extension above MA10
      ext20        — % extension above MA20
      close_below_ma20 — bool
      regime_ok    — bool (True if market is not Risk-Off)
      rs_spy_ok    — bool (RS vs SPY positive)

    Returns:
      status   — APPROVED / WATCH / BLOCKED / MANUAL_REVIEW_REQUIRED
      reasons  — list of passing reason strings
      blocks   — list of blocking reason strings
      warnings — list of non-blocking caution strings
    """
    reasons, blocks, warnings = [], [], []

    # ── Gate 0: Data completeness ─────────────────────────────────────────────
    if not lot_state.get("data_complete"):
        return {
            "status": MANUAL_REVIEW,
            "reasons": [],
            "blocks": ["סטופ מקורי חסר — לא ניתן לחשב סיכון קמפיין"],
            "warnings": ["נדרש: הוסף initial_stop לפוזיציה"],
        }

    # ── Gate 1: ALGO positions — no manual add-ons ───────────────────────────
    if lot_state.get("is_algo"):
        return {
            "status": BLOCKED,
            "reasons": [],
            "blocks": ["פוזיציית ALGO — Sentinel לא ממליץ על חיזוק ידני"],
            "warnings": [],
        }

    orig_risk = lot_state["original_risk_usd"]
    open_r    = lot_state.get("open_r")
    locked    = lot_state["locked_profit_usd"]
    cushion   = lot_state["cushion_ratio"]
    open_risk = lot_state["open_risk_usd"]

    # ── Gate 2: Position must be profitable ──────────────────────────────────
    profit_ok = False
    if open_r is not None and open_r >= MIN_OPEN_R_FOR_ADDON:
        reasons.append(f"✅ Open R: {open_r:.1f}R — מעל סף מינימלי ({MIN_OPEN_R_FOR_ADDON:.0f}R)")
        profit_ok = True
    elif locked >= orig_risk * MIN_CUSHION_RATIO:
        reasons.append(f"✅ רווח נעול: ${locked:.0f} ({cushion*100:.0f}% מסיכון מקורי)")
        profit_ok = True
    else:
        oor_str = f"{open_r:.1f}R" if open_r is not None else "N/A"
        blocks.append(
            f"❌ אין מספיק כרית: Open R={oor_str} (נדרש ≥{MIN_OPEN_R_FOR_ADDON:.0f}R) "
            f"| רווח נעול=${locked:.0f} (נדרש ≥${orig_risk*MIN_CUSHION_RATIO:.0f})"
        )

    # ── Gate 3: Original risk must be reduced ────────────────────────────────
    if open_risk <= 0:
        reasons.append("✅ הקמפיין ב-Breakeven או רווח — אין סיכון הון פתוח")
    elif open_risk <= orig_risk * 0.5:
        reasons.append(f"✅ סיכון פתוח: ${open_risk:.0f} (≤50% מסיכון מקורי ${orig_risk:.0f})")
    elif open_risk <= orig_risk:
        warnings.append(f"⚠️ סיכון פתוח ${open_risk:.0f} עדיין גבוה (נדרש: ≤50% = ${orig_risk*0.5:.0f})")
    else:
        blocks.append(f"❌ סיכון פתוח (${open_risk:.0f}) גבוה מהסיכון המקורי (${orig_risk:.0f})")

    # ── Gate 4: Technical reason ──────────────────────────────────────────────
    reason_label = ADD_REASONS.get(add_reason, add_reason)
    if add_reason != "MANUAL":
        reasons.append(f"✅ סיבה טכנית: {reason_label}")
    else:
        warnings.append(f"⚠️ אין סיבה טכנית מוגדרת — ודא קיום Setup לפני ביצוע")

    # ── Gate 5: Market features (optional) ───────────────────────────────────
    if market_features:
        ext10 = market_features.get("ext10", 0)
        ext20 = market_features.get("ext20", 0)
        regime_ok = market_features.get("regime_ok", True)
        rs_spy_ok = market_features.get("rs_spy_ok", True)
        close_below_ma20 = market_features.get("close_below_ma20", False)

        if ext10 > CHASE_EXT_LIMIT * 100:
            blocks.append(
                f"❌ מחיר מורחב {ext10:.1f}% מעל MA10 — "
                f"סיכון Chase (מעל {CHASE_EXT_LIMIT*100:.0f}%)"
            )
        elif ext10 > 4.0:
            warnings.append(f"⚠️ מחיר {ext10:.1f}% מעל MA10 — בדוק שלא מתרחק מהבסיס")

        if close_below_ma20:
            blocks.append("❌ סגירה מתחת MA20 — מבנה מוחלש")

        if not regime_ok:
            blocks.append("❌ משטר שוק לא תומך — הפחת חיזוקים בסביבה זו")

        if rs_spy_ok:
            reasons.append("✅ כוח יחסי חיובי מול SPY")
        else:
            warnings.append("⚠️ כוח יחסי שלילי מול SPY")

    # ── Decision ──────────────────────────────────────────────────────────────
    if blocks:
        status = BLOCKED
    elif not profit_ok:
        status = BLOCKED
    elif warnings and add_reason == "MANUAL" and not reasons:
        status = WATCH
    elif warnings:
        status = WATCH
    else:
        status = APPROVED

    return {
        "status":   status,
        "reasons":  reasons,
        "blocks":   blocks,
        "warnings": warnings,
    }


# ── Add-on sizing ─────────────────────────────────────────────────────────────

def compute_addon_sizing(
    lot_state: dict,
    add_entry: float,
    add_stop: float,
    desired_buffer_usd: float = 0.0,
) -> dict:
    """
    Compute maximum and suggested add-on quantity.

    Formula:
      available_addon_risk = locked_profit + realized_pnl - buffer
      max_qty = floor(available / risk_per_share)
    Safety caps:
      <= original_qty (MAX_SIZE_VS_ORIGINAL)
      <= 50% of current_qty (MAX_SIZE_VS_CURRENT)

    Returns:
      risk_per_share   — add_entry - add_stop
      available_risk   — how much locked profit is available for add risk
      max_qty          — maximum shares allowed by risk math
      suggested_qty    — recommended (DEFAULT_SIZE_RATIO of original, capped by max)
      add_on_risk_usd  — suggested_qty * risk_per_share
      result_if_stopped — campaign result if add-on stop hit at suggested_qty
      hard_floor_usd   — minimum allowed result (-25% of original_risk)
    """
    if add_entry <= add_stop:
        return {"error": "add_entry must be above add_stop for a long add-on"}

    risk_per_share = add_entry - add_stop
    locked    = lot_state["locked_profit_usd"]
    realized  = lot_state["realized_pnl_usd"]
    orig_risk = lot_state["original_risk_usd"]
    base_qty  = lot_state["base_qty"]
    curr_qty  = lot_state["current_qty"]

    available_risk = max(0.0, locked + realized - desired_buffer_usd)

    raw_max_qty = math.floor(available_risk / risk_per_share) if risk_per_share > 0 else 0
    # Safety caps
    cap_original = math.floor(base_qty * MAX_SIZE_VS_ORIGINAL)
    cap_current  = math.floor(curr_qty * MAX_SIZE_VS_CURRENT)
    max_qty = max(0, min(raw_max_qty, cap_original, cap_current))

    # Suggested: DEFAULT_SIZE_RATIO of original, capped by max
    suggested_qty = max(0, min(math.floor(base_qty * DEFAULT_SIZE_RATIO), max_qty))

    add_on_risk_usd = suggested_qty * risk_per_share

    # Campaign result if add-on stop is hit
    result_if_stopped = lot_state["net_result_if_stop_hit"] - add_on_risk_usd

    hard_floor_usd = -orig_risk * abs(HARD_FLOOR_RATIO) if orig_risk > 0 else 0.0

    return {
        "risk_per_share":    round(risk_per_share, 2),
        "available_risk":    round(available_risk, 2),
        "raw_max_qty":       raw_max_qty,
        "max_qty":           max_qty,
        "suggested_qty":     suggested_qty,
        "add_on_risk_usd":   round(suggested_qty * risk_per_share, 2),
        "result_if_stopped": round(result_if_stopped, 2),
        "hard_floor_usd":    round(hard_floor_usd, 2),
    }


# ── Stop mode recommendation ──────────────────────────────────────────────────

def recommend_stop_mode(add_type: str, lot_state: dict) -> dict:
    """
    Recommend stop mode based on add-on type and campaign state.

    TACTICAL add or runner with raised stop → LAYERED (close add-on only if tactical stop hit)
    CAMPAIGN add or no locked profit → UNIFIED (close all if campaign stop hit)
    """
    locked = lot_state["locked_profit_usd"]
    orig_risk = lot_state["original_risk_usd"]

    if add_type == ADDON_TACTICAL and locked > 0:
        mode = STOP_LAYERED
        description = (
            "אם הסטופ הטקטי (של ההוספה) נפגע — סגור את ההוספה בלבד. "
            "אם הסטופ הראשי נפגע — סגור הכול."
        )
    elif add_type == ADDON_REBUILD:
        mode = STOP_LAYERED
        description = (
            "לפי מבנה חדש. סגור ההוספה אם הבסיס החדש נשבר. "
            "הסטטיסטיקה של הקמפיין המקורי לא מושפעת."
        )
    else:
        mode = STOP_UNIFIED
        description = (
            "סטופ אחד לכל הפוזיציה. אם הסטופ נפגע — סגור הכול."
        )

    return {"mode": mode, "description": description}


# ── Full add-on plan ──────────────────────────────────────────────────────────

def compute_addon_plan(
    lot_state: dict,
    add_entry: float,
    add_stop: float,
    add_type: str = ADDON_TACTICAL,
    quantity: int | None = None,
    add_reason: str = "MANUAL",
    market_features: dict | None = None,
    desired_buffer_usd: float = 0.0,
) -> dict:
    """
    Full add-on decision: eligibility + sizing + stop mode + final approval.

    quantity: if None, uses suggested_qty from sizing formula.
    Returns complete plan dict ready for Telegram formatting.
    """
    if add_entry <= add_stop:
        return {
            "ok": False,
            "error": "add_entry חייב להיות מעל add_stop (פוזיציה לונג)",
        }

    if not lot_state.get("data_complete"):
        return {
            "ok": False,
            "status": MANUAL_REVIEW,
            "error": "Cannot approve: campaign risk cannot be calculated reliably",
            "message": "סטופ מקורי חסר — לא ניתן לאשר חיזוק. הוסף initial_stop לפוזיציה.",
        }

    eligibility = check_addon_eligibility(lot_state, add_reason, market_features)
    sizing      = compute_addon_sizing(lot_state, add_entry, add_stop, desired_buffer_usd)
    stop_mode   = recommend_stop_mode(add_type, lot_state)

    # Use requested quantity or suggested
    proposed_qty = quantity if quantity is not None else sizing["suggested_qty"]
    proposed_qty = max(0, proposed_qty)

    risk_per_share   = add_entry - add_stop
    addon_risk_usd   = proposed_qty * risk_per_share
    result_if_stopped = lot_state["net_result_if_stop_hit"] - addon_risk_usd
    hard_floor        = sizing["hard_floor_usd"]
    orig_risk         = lot_state["original_risk_usd"]

    # Override decision if proposed qty violates hard floor
    final_decision = eligibility["status"]
    final_blocks   = list(eligibility["blocks"])

    if proposed_qty > sizing["max_qty"] and sizing["max_qty"] >= 0:
        final_blocks.append(
            f"❌ כמות מבוקשת ({proposed_qty}) חורגת מהמקסימום המותר ({sizing['max_qty']})"
        )
        final_decision = BLOCKED

    if result_if_stopped < hard_floor:
        final_blocks.append(
            f"❌ תוצאה אם הסטופ נפגע (${result_if_stopped:.0f}) "
            f"מתחת לרצפה המינימלית (${hard_floor:.0f} = -{abs(HARD_FLOOR_RATIO)*100:.0f}% מסיכון מקורי)"
        )
        final_decision = BLOCKED
    elif result_if_stopped < 0 and final_decision == APPROVED:
        final_decision = WATCH
        eligibility["warnings"].append(
            f"⚠️ תוצאה שלילית אם הסטופ נפגע (${result_if_stopped:.0f}) — "
            f"קמפיין מנצח הופך להפסד קל"
        )

    if final_blocks:
        final_decision = BLOCKED

    # R-multiple of result if stopped
    result_r = result_if_stopped / orig_risk if orig_risk > 0 else None

    return {
        "ok":               True,
        "status":           final_decision,
        "add_type":         add_type,
        "add_reason":       add_reason,
        "add_reason_label": ADD_REASONS.get(add_reason, add_reason),
        # Campaign state snapshot
        "lot_state":        lot_state,
        # Proposed add-on
        "add_entry":        add_entry,
        "add_stop":         add_stop,
        "proposed_qty":     proposed_qty,
        "risk_per_share":   round(risk_per_share, 2),
        "addon_risk_usd":   round(addon_risk_usd, 2),
        # Result scenario
        "result_if_stopped":  round(result_if_stopped, 2),
        "result_r":           round(result_r, 2) if result_r is not None else None,
        "hard_floor_usd":     hard_floor,
        # Sizing
        "max_qty":            sizing["max_qty"],
        "suggested_qty":      sizing["suggested_qty"],
        "available_risk_usd": sizing["available_risk"],
        # Stop mode
        "stop_mode":          stop_mode["mode"],
        "stop_mode_desc":     stop_mode["description"],
        # Decision detail
        "reasons":   eligibility["reasons"],
        "blocks":    final_blocks,
        "warnings":  eligibility["warnings"],
    }
