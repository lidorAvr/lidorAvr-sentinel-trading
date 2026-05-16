"""
report_on_demand.py — Scope item B: on-demand weekly/monthly report generation
for the LAST COMPLETE period, for developer-menu testing (esp. validating the
Sprint-16 graceful-degradation path without waiting for Sat 08:30 IL).

HARD constraints (SPRINT17_PLAN.md Scope item B; verified by test):
  • Reuses the EXACT same period logic the scheduler uses
    (`report_scheduler._weekly_period` / `_monthly_period`) — no new period
    definition is invented here.
  • Reuses the EXACT same render+delivery path
    (`render_weekly`/`render_monthly` → `build_summary_text` →
    `report_delivery.deliver_report`) including the Sprint-16 graceful PDF
    degradation (text + ⚠️ trailer on PDF failure). ZERO report
    content/number change.
  • **MUST NOT mutate the scheduled report's state.** This module NEVER calls
    `report_snapshot_store.save` (no snap_save into the real snapshot store)
    and NEVER touches the scheduler period-dedup
    (`report_scheduler._mark_ran` / `_save_state` / `STATE_FILE`). The real
    Saturday/monthly run + its "vs previous" comparison stay byte-identical in
    behaviour. Sprint-19 §2f: "vs previous" + "vs average" are now rendered
    READ-ONLY from existing history (`load_previous`/`load_recent` are pure
    file reads — report_snapshot_store.py:99-128); on-demand still NEVER
    writes the snapshot it just read, and < N history honestly shows the §2c
    baseline-pending token (identical to the scheduled path). See
    SPRINT17_WAVE2_IMPL.md §3 + SPRINT19_WAVE2_IMPL.md §4 for the
    no-mutation proof.

This module has NO ALGO-governance overlap (Workstream A); it lives in its own
file and is wired only from the developer menu (admin-gated via the existing
dev-menu/PIN path).
"""
from datetime import datetime, timedelta

import report_scheduler as sched


def last_complete_weekly_ref(now: datetime) -> datetime:
    """The reference Saturday for the LAST COMPLETE week, given `now`.

    The scheduler runs weekly on Saturday for the week *ending that Saturday*
    (`_weekly_period`: prev-Sunday 00:00 → Saturday 23:59:59). For an
    on-demand run on an arbitrary day we want the most recent Saturday whose
    full week has already elapsed (i.e. that Saturday is strictly in the
    past — not today). Python weekday(): Mon=0 … Sat=5, Sun=6.
    """
    # Days since the most recent Saturday (0 if today is Saturday).
    days_since_sat = (now.weekday() - 5) % 7
    last_sat = now - timedelta(days=days_since_sat)
    # If that Saturday is "today", its week is not yet complete → go back one.
    if last_sat.date() == now.date():
        last_sat = last_sat - timedelta(days=7)
    return last_sat.replace(hour=12, minute=0, second=0, microsecond=0)


def last_complete_monthly_ref(now: datetime) -> datetime:
    """A reference datetime whose `_monthly_period` is the LAST COMPLETE month.

    `_monthly_period(ref)` returns the *previous* calendar month relative to
    `ref`'s month-start. Passing `now` itself yields the last complete month
    (whatever day of the current month we are on), matching the scheduler's
    1st-of-month run for the just-ended month.
    """
    return now


def run_on_demand(period_type: str, now: datetime = None,
                  token: str = None, chat_id: str = None) -> dict:
    """Generate + deliver the LAST COMPLETE `period_type` report on demand.

    period_type: "weekly" | "monthly".

    token/chat_id: delivery credentials. The dev button runs INSIDE the
    telegram-bot process, which uses TELEGRAM_BOT_TOKEN / TELEGRAM_ADMIN_ID
    (`bot_core`), NOT the scheduler's TELEGRAM_TOKEN / TELEGRAM_CHAT_ID
    convention (`report_scheduler` runs in the separate reporting-service
    container). The caller passes its own working bot creds; we fall back
    to the scheduler env convention only when not supplied.

    Returns a dict: {ok, period_label, summary_ok, pdf_ok, pdf_degraded,
    error}. NEVER calls snap_save and NEVER touches the scheduler dedup state
    (proof: this function imports neither `report_snapshot_store.save` nor any
    `report_scheduler` state mutator; it only borrows the pure period/fetch/
    risk-rec helpers + the render/deliver path).
    """
    import os

    import account_state as acc_mod
    from analytics_engine import (compute_period_analytics,
                                  compute_trader_development_score,
                                  compute_period_comparison)
    from report_renderer import (render_weekly, render_monthly,
                                  build_summary_text, compute_period_average)
    from report_delivery import deliver_report
    import report_open_book as rob

    if now is None:
        now = datetime.now(sched.ISRAEL_TZ)

    try:
        if period_type == "weekly":
            ref = last_complete_weekly_ref(now)
            period_start, period_end = sched._weekly_period(ref)
        elif period_type == "monthly":
            ref = last_complete_monthly_ref(now)
            period_start, period_end = sched._monthly_period(ref)
        else:
            return {"ok": False, "error": f"bad period_type: {period_type!r}"}

        account = acc_mod.load()
        df = sched._fetch_trades_df(period_start, period_end)

        analytics = compute_period_analytics(df, period_start, period_end,
                                             account)
        dev_data = compute_trader_development_score(analytics)
        health = sched._build_system_health()

        # Sprint-18: build the open-book for RENDERING ONLY (read-only — same
        # df, command-room source). On-demand is read-only w.r.t. the snapshot
        # store (Scope-B invariant): NO snap_save.
        open_book = rob.build_open_book(
            df, account, period_start=period_start, period_end=period_end)

        # Sprint-19 §2f — on-demand MAY now READ existing per-host snapshot
        # history and render comparison/average READ-ONLY. load_previous /
        # load_recent are PURE file reads (report_snapshot_store.py:99-128 →
        # os.listdir/json.load); they NEVER write. The Scope-B invariant
        # (this file:15-23) is preserved by construction: NO
        # report_snapshot_store.save, NO report_scheduler._mark_ran/_save_state
        # is ever called here. When < N history exists the §2c
        # baseline-pending token is shown — honest, identical to the scheduled
        # path (#1: never a fabricated mean; on-demand never writes what it
        # read). mark_delta + period-over-period reuse the unchanged
        # compute_mark_delta / compute_period_comparison.
        from report_snapshot_store import load_previous, load_recent
        prev_snap = load_previous(period_type, period_start)   # READ-ONLY
        comparison = (compute_period_comparison(analytics, prev_snap)
                      if prev_snap else None)
        mark_delta = rob.compute_mark_delta(open_book, prev_snap)
        recent_snaps = load_recent(period_type,
                                   n=rob.OPEN_BOOK_HISTORY_MIN_N + 2)  # RO
        period_avg = compute_period_average(recent_snaps)
        ob_history = rob.compute_open_book_history(
            open_book, recent_snaps, prev_snap)

        if period_type == "weekly":
            coaching = sched._weekly_coaching_insights(analytics)
            pdf_degraded = False
            try:
                pdf_path = render_weekly(
                    analytics=analytics,
                    account_state=account,
                    period_start=period_start,
                    period_end=period_end,
                    comparison=comparison,
                    dev_score_data=dev_data,
                    system_health=health,
                    coaching_insights=coaching,
                    risk_adherence_rate=analytics.get("risk_adherence_rate"),
                    open_book=open_book,
                    mark_delta=mark_delta,
                    period_average=period_avg,
                    open_book_history=ob_history,
                )
                if not sched._is_pdf_path(pdf_path):
                    pdf_degraded = True
            except Exception:
                pdf_degraded = True
                pdf_path = ""
            if pdf_degraded:
                pdf_path = ""
            period_label = (f"{period_start.strftime('%d/%m')}–"
                            f"{period_end.strftime('%d/%m/%Y')}")
            caption = f"📊 Sentinel Weekly Report (On-Demand) | {period_label}"
        else:
            coaching = sched._monthly_coaching_insights(analytics)
            # Reuse the scheduler's monthly weekly-breakdown helper exactly;
            # it is a pure read (load_recent reads, does NOT write).
            from report_snapshot_store import load_recent
            weekly_snaps = load_recent("weekly", n=5)
            weekly_breakdown = sched._build_weekly_breakdown(
                weekly_snaps, period_start, period_end)
            pdf_degraded = False
            try:
                pdf_path = render_monthly(
                    analytics=analytics,
                    account_state=account,
                    period_start=period_start,
                    period_end=period_end,
                    comparison=comparison,
                    dev_score_data=dev_data,
                    system_health=health,
                    coaching_insights=coaching,
                    risk_adherence_rate=analytics.get("risk_adherence_rate"),
                    weekly_breakdown=weekly_breakdown,
                    open_book=open_book,
                    mark_delta=mark_delta,
                    period_average=period_avg,
                    open_book_history=ob_history,
                )
                if not sched._is_pdf_path(pdf_path):
                    pdf_degraded = True
            except Exception:
                pdf_degraded = True
                pdf_path = ""
            if pdf_degraded:
                pdf_path = ""
            month_names = ["ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני",
                           "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר",
                           "דצמבר"]
            period_label = (f"{month_names[period_start.month - 1]} "
                            f"{period_start.year}")
            caption = f"📊 Sentinel Monthly Report (On-Demand) | {period_label}"

        # ── NO snap_save here. This is the deliberate divergence from
        #    _run_weekly/_run_monthly (report_scheduler.py:265 / :345) — the
        #    on-demand path is read-only w.r.t. the snapshot store and the
        #    scheduler period-dedup. The real scheduled run is byte-identical.

        risk_rec = sched._compute_risk_rec(df, account)
        summary_text = build_summary_text(analytics, period_label,
                                          period_type, risk_rec=risk_rec,
                                          open_book=open_book,
                                          mark_delta=mark_delta,
                                          period_average=period_avg,
                                          open_book_history=ob_history)
        if pdf_degraded:
            summary_text = f"{summary_text}\n\n{sched._DEGRADED_PDF_NOTE}"

        token = token or os.environ.get("TELEGRAM_TOKEN", "")
        chat_id = (str(chat_id) if chat_id
                   else os.environ.get("TELEGRAM_CHAT_ID", ""))
        if not token or not chat_id:
            return {"ok": False, "error": "telegram_not_configured",
                    "period_label": period_label,
                    "pdf_degraded": pdf_degraded}

        result = deliver_report(pdf_path, summary_text, caption,
                                chat_id, token)
        return {
            "ok": True,
            "period_label": period_label,
            "summary_ok": result["summary_ok"],
            "pdf_ok": result["pdf_ok"],
            "pdf_degraded": pdf_degraded,
            "error": None,
        }
    except Exception as e:
        import traceback
        return {"ok": False, "error": f"{e}",
                "traceback": traceback.format_exc()}
