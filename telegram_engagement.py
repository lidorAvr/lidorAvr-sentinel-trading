"""
telegram_engagement.py — engagement-phase pull surfaces.

Engagement-meeting Wave-3B (21/05/2026). New shippable surfaces that
build on the Wave-3A foundation (engagement_suppression, audit
constants, gate_result logging, fmt_adaptive_risk_block routing).

Surfaces currently exposed:
  - `/gate_receipt` → C4-S1 Gate Receipt (Mark §C4 binding,
    count-only Phase-1; symmetric framing reserved for Phase-2 D11).

Module discipline (mirrors `telegram_audit_review.py`):
  - SELECT-only: this module never writes to Supabase.
  - Admin-gated via the existing telegram_bot message/callback gate;
    secure_runner untouched.
  - No fabricated numbers (Mark §3 / §X1). When the underlying engine
    function returns ``total_clamps=0`` the formatter returns ""; this
    handler then emits an HONEST empty-state line, never a fake
    "great work" celebration (§C4 R1).
  - Pull-only — no push path here. §X5 silence-as-surface honored.
"""
from bot_core import bot, RTL

import adaptive_risk_engine as are
import telegram_formatters as tf


def handle_gate_receipt(chat_id, n_days: int = 90):
    """`/gate_receipt` — C4-S1 Phase-1 pull surface.

    Reads `risk_recommendations.json` via `compute_gate_clamp_summary`,
    renders via `fmt_gate_receipt`. Honest empty-state when no clamps
    in the window (§C4 R1 — never invent a celebration). Mark §X6 —
    self-data only; no market commentary.
    """
    summary = are.compute_gate_clamp_summary(n_days=n_days)
    body = tf.fmt_gate_receipt(summary)
    if not body:
        # Honest empty-state. NOT a celebration line. The founder may
        # genuinely have zero in-window clamps and that is fine — we
        # surface the fact, no spin.
        text = (
            f"{RTL}🛡️ *קבלה מהשער*\n"
            f"{RTL}אין חסימות סיכון מתועדות ב-`{int(n_days)}` הימים האחרונים."
        )
    else:
        text = body.lstrip("\n")
    bot.send_message(chat_id, text, parse_mode="Markdown")
