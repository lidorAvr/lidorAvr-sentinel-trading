import html
import streamlit as st

import dashboard_truth_center as truth
import dashboard_ai_export as ai

st.set_page_config(page_title="חדר פיקוד Sentinel", layout="wide")

st.markdown("""
<style>
html, body, [class*="css"] { direction: rtl; }
.block-container { padding-top: 1.1rem; max-width: 1180px; }
[data-testid="stSidebar"] * { direction: rtl; text-align: right; }
h1, h2, h3 { letter-spacing: 0 !important; }
.s-card {
  border: 1px solid #d8dee7;
  border-radius: 8px;
  background: #ffffff;
  padding: 13px 15px;
  min-height: 94px;
}
.s-label { color: #667085; font-size: .86rem; margin-bottom: 6px; }
.s-value { color: #101828; font-size: 1.45rem; font-weight: 750; line-height: 1.25; }
.s-hint { color: #667085; font-size: .82rem; margin-top: 5px; }
.s-good { border-right: 5px solid #0f766e; }
.s-warn { border-right: 5px solid #b45309; }
.s-bad { border-right: 5px solid #dc2626; }
.pos-card {
  border: 1px solid #d8dee7;
  border-radius: 8px;
  background: #fff;
  padding: 14px 16px;
  margin: 8px 0 12px 0;
}
.pos-head { display:flex; justify-content:space-between; align-items:center; gap:10px; }
.symbol { font-size: 1.35rem; font-weight: 800; color:#101828; }
.pill {
  display:inline-block; padding: 3px 9px; border-radius: 999px;
  background:#eef6f4; color:#0f766e; font-size:.8rem; font-weight:700;
}
.gridline { color:#344054; font-size:.92rem; line-height:1.75; }
.note-box {
  border: 1px solid #f1c27d; background: #fff8ed; color:#53380a;
  border-radius: 8px; padding: 12px 14px; margin: 8px 0;
}
.small-muted { color:#667085; font-size:.9rem; }
</style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=120)
def cached_truth():
    return ai.get_truth()

@st.cache_data(ttl=180)
def cached_recent(limit):
    return ai.recent_campaigns(limit)

@st.cache_data(ttl=180)
def cached_report():
    return ai.build_master_context_report()

def esc(v):
    return html.escape(str(v if v not in (None, "") else "לא ידוע"))

def card(label, value, hint="", tone=""):
    cls = "s-card"
    if tone:
        cls += f" s-{tone}"
    return f"""
    <div class="{cls}">
      <div class="s-label">{esc(label)}</div>
      <div class="s-value">{esc(value)}</div>
      <div class="s-hint">{esc(hint)}</div>
    </div>
    """

def metric_cards(items, per_row=5):
    for i in range(0, len(items), per_row):
        cols = st.columns(len(items[i:i+per_row]))
        for col, item in zip(cols, items[i:i+per_row]):
            with col:
                st.markdown(card(*item), unsafe_allow_html=True)

def open_campaign_card(c):
    st.markdown(f"""
    <div class="pos-card">
      <div class="pos-head">
        <div class="symbol">{esc(c.get('symbol'))}</div>
        <div class="pill">{esc(ai.he(c.get('campaign_status')))}</div>
      </div>
      <div class="gridline">
        Setup: {esc(c.get('setup_type'))} · סטטוס אסטרטגי: {esc(ai.he(c.get('strategy_status')))} · איכות סיכון: {esc(ai.he(c.get('risk_data_quality_status')))}<br>
        כמות פתוחה: {esc(c.get('quantity_remaining'))} · רווח ממומש: {esc(ai.money(c.get('realized_pnl_usd')))} · Closed Target R: {esc(ai.rfmt(c.get('closed_target_r')))}<br>
        רווח נעול: {esc(ai.money(c.get('locked_profit_usd')))} · ויתור אפשרי עד סטופ: {esc(ai.money(c.get('giveback_to_stop_usd')))}
      </div>
    </div>
    """, unsafe_allow_html=True)

def render_command(data):
    counts = data.get("counts") or {}
    nav = data.get("nav") or {}
    audit = data.get("latest_audit") or {}
    recon = data.get("latest_trades_reconciliation") or {}

    st.title("חדר פיקוד Sentinel")
    st.caption("מסך יומי מהיר: מצב תיק, קמפיינים פתוחים, יומן מסחר ו־AI Export בלי טעינה כבדה מראש.")

    metric_cards([
        ("שווי תיק IBKR", ai.money(nav.get("current_nav")), ai.he(nav.get("status")), "good"),
        ("טווח נתונים", "YTD", "לא מסיקים All-Time מנתוני YTD בלבד", "warn"),
        ("ביקורת נתונים", ai.he(audit.get("status")), f"איכות: {ai.he(audit.get('data_quality_status'))}", "good" if audit.get("critical_breaks", 0) == 0 else "bad"),
        ("קמפיינים פתוחים", counts.get("open_campaigns", 0), "ניהול חי בלבד עד סגירה", "good"),
        ("משימות Intake", counts.get("pending_intake_tasks", 0), "תוכניות שממתינות לאישור", "warn" if counts.get("pending_intake_tasks", 0) else "good"),
    ])

    st.subheader("מה דורש תשומת לב")
    items = []
    if counts.get("pending_intake_tasks", 0):
        items.append(f"יש {counts.get('pending_intake_tasks')} תוכניות ניהול שממתינות לאישור.")
    if counts.get("open_campaigns", 0):
        items.append("יש קמפיינים פתוחים. לאמת סטופ, רווח נעול, ויתור אפשרי וטריגרים שנשלחו.")
    if audit.get("warning_breaks", 0):
        items.append(f"יש {audit.get('warning_breaks')} אזהרות נתונים, ללא כשלים קריטיים.")
    if recon.get("status"):
        items.append(f"התאמת Trades מול בסיס הנתונים: {ai.he(recon.get('status'))}.")
    if not items:
        items.append("אין כרגע פעולה דחופה מתוך מרכז האמת.")
    st.markdown("<div class='note-box'>" + "<br>".join("• " + esc(x) for x in items) + "</div>", unsafe_allow_html=True)

    st.subheader("קמפיינים פתוחים")
    open_campaigns = data.get("open_campaigns") or []
    if not open_campaigns:
        st.info("אין כרגע קמפיינים פתוחים.")
    for c in open_campaigns:
        open_campaign_card(c)

def render_journal():
    st.title("יומן מסחר")
    st.caption("טעינה מהירה של קמפיינים אחרונים. הארכיון המלא והכבד עדיין קיים בעמוד הייעודי, אבל כאן עובדים מהר.")
    limit = st.slider("כמה קמפיינים להציג", 5, 60, 25, step=5)
    rows = cached_recent(limit)

    if not rows:
        st.info("לא נמצאו קמפיינים להצגה.")
        return

    for item in rows:
        c = item["campaign"]
        ex = item["executions"]
        pnl = c.get("realized_pnl_usd") or c.get("net_pnl") or c.get("pnl")
        r = c.get("closed_actual_r") or c.get("closed_target_r") or c.get("total_campaign_r")
        title = f"{c.get('symbol', '?')} | {ai.he(c.get('campaign_status') or c.get('status'))} | {ai.money(pnl)} | {ai.rfmt(r)}"
        with st.expander(title):
            st.write(f"קמפיין: {c.get('campaign_id', 'לא ידוע')}")
            st.write(f"Setup: {c.get('setup_type') or c.get('strategy') or 'לא ידוע'}")
            st.write(f"איכות נתונים: {ai.he(c.get('data_quality_status'))} | סטטוס אסטרטגי: {ai.he(c.get('strategy_status'))}")
            notes = c.get("management_notes") or c.get("notes") or c.get("review_notes") or c.get("post_trade_notes")
            if notes:
                st.markdown("**תובנות ניהול**")
                st.write(notes)
            if ex:
                st.markdown("**פעולות**")
                for e in ex:
                    st.write(f"{ai.short_date(e.get('executed_at') or e.get('trade_date') or e.get('created_at'))} · {e.get('side') or e.get('action') or ''} · כמות {e.get('quantity') or e.get('qty') or '?'} · מחיר {e.get('price') or e.get('execution_price') or '?'}")
            else:
                st.caption("אין פעולות מקושרות להצגה.")

def render_ai_export():
    st.title("ייצוא הקשר מלא ל־AI")
    st.caption("הדוח הכבד נוצר רק בלחיצה, כדי שהדאשבורד יישאר מהיר ביום־יום.")
    st.markdown("<div class='note-box'>הדוח כולל תמונת תיק, קמפיינים פתוחים, תוכניות ניהול, יומן קמפיינים אחרונים ונספח נתונים מלא למודל.</div>", unsafe_allow_html=True)

    if st.button("יצירת דוח מלא להעתקה", type="primary"):
        st.session_state["ai_report"] = cached_report()

    report = st.session_state.get("ai_report")
    if report:
        st.text_area("דוח מלא להעתקה", report, height=560)
        st.download_button("הורדת קובץ TXT", report, file_name="sentinel_ai_master_context.txt", mime="text/plain")
    else:
        st.info("לחיצה על הכפתור תיצור את הדוח. עד אז הוא לא נטען ולא מאט את הדאשבורד.")

def render_health(data):
    st.title("בריאות נתונים")
    counts = data.get("counts") or {}
    audit = data.get("latest_audit") or {}

    metric_cards([
        ("Executions", counts.get("executions", 0), "פעולות מקור", "good"),
        ("Lots", counts.get("lots", 0), "שכבות FIFO", "good"),
        ("Closures", counts.get("closures", 0), "סגירות חלקיות/מלאות", "good"),
        ("Campaigns", counts.get("campaigns", 0), "רעיונות מסחר", "good"),
        ("Warnings", audit.get("warning_breaks", 0), "אזהרות לא קריטיות", "warn"),
    ])

    st.subheader("סיווגים")
    st.write("סטטוס קמפיינים:", {ai.he(k): v for k, v in (data.get("campaign_status") or {}).items()})
    st.write("סטטוס אסטרטגי:", {ai.he(k): v for k, v in (data.get("strategy_status") or {}).items()})
    st.write("איכות קמפיינים:", {ai.he(k): v for k, v in (data.get("campaign_quality") or {}).items()})
    st.write("איכות סיכון:", {ai.he(k): v for k, v in (data.get("risk_quality") or {}).items()})

    if st.sidebar.checkbox("מצב טכני: הצג JSON", value=False):
        st.json(data)

data = cached_truth()

section = st.sidebar.radio(
    "ניווט",
    ["חדר מצב", "יומן מסחר", "AI Export", "בריאות נתונים"],
    label_visibility="visible",
)

if section == "חדר מצב":
    render_command(data)
elif section == "יומן מסחר":
    render_journal()
elif section == "AI Export":
    render_ai_export()
else:
    render_health(data)
