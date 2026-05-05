import html
import streamlit as st
import dashboard_truth_center as truth
import dashboard_ai_export as ai

st.set_page_config(page_title="מרכז אמת", layout="wide")

st.markdown("""
<style>
html, body, [class*="css"] { direction: rtl; }
.block-container { padding-top: 1.1rem; max-width: 1180px; }
[data-testid="stSidebar"] * { direction: rtl; text-align: right; }
.truth-card {
  border: 1px solid #d8dee7;
  border-radius: 8px;
  background: #fff;
  padding: 13px 15px;
  min-height: 90px;
}
.t-label { color:#667085; font-size:.84rem; }
.t-value { color:#101828; font-size:1.35rem; font-weight:750; margin-top:5px; }
</style>
""", unsafe_allow_html=True)

def esc(v):
    return html.escape(str(v if v not in (None, "") else "לא ידוע"))

@st.cache_data(ttl=120)
def load():
    return ai.get_truth()

def card(label, value):
    st.markdown(f"<div class='truth-card'><div class='t-label'>{esc(label)}</div><div class='t-value'>{esc(value)}</div></div>", unsafe_allow_html=True)

data = load()
counts = data.get("counts") or {}
audit = data.get("latest_audit") or {}
nav = data.get("nav") or {}
recon = data.get("latest_trades_reconciliation") or {}

st.title("מרכז אמת Sentinel")
st.caption("אמת חשבונאית, גבולות מדגם, סטטוס תוכניות והתראות. בלי ארכיון ובלי דוח AI כבד.")

cols = st.columns(4)
with cols[0]: card("שווי תיק IBKR", ai.money(nav.get("current_nav")))
with cols[1]: card("טווח נתונים", "YTD")
with cols[2]: card("ביקורת נתונים", ai.he(audit.get("status")))
with cols[3]: card("כשלים קריטיים", audit.get("critical_breaks", 0))

cols = st.columns(5)
with cols[0]: card("Executions", counts.get("executions", 0))
with cols[1]: card("Lots", counts.get("lots", 0))
with cols[2]: card("Closures", counts.get("closures", 0))
with cols[3]: card("Campaigns", counts.get("campaigns", 0))
with cols[4]: card("Open", counts.get("open_campaigns", 0))

st.subheader("קמפיינים פתוחים")
rows = []
for c in data.get("open_campaigns") or []:
    rows.append({
        "סימול": c.get("symbol"),
        "סטטוס": ai.he(c.get("campaign_status")),
        "Setup": c.get("setup_type"),
        "איכות סיכון": ai.he(c.get("risk_data_quality_status")),
        "כמות": c.get("quantity_remaining"),
        "רווח ממומש": ai.money(c.get("realized_pnl_usd")),
        "Closed Target R": ai.rfmt(c.get("closed_target_r")),
    })
if rows:
    st.dataframe(rows, use_container_width=True, hide_index=True)
else:
    st.info("אין קמפיינים פתוחים.")

st.subheader("תוכניות והתראות")
cols = st.columns(4)
with cols[0]: card("תוכניות", counts.get("campaign_plans", 0))
with cols[1]: card("מאושרות", counts.get("approved_db_plans", 0))
with cols[2]: card("ממתינות", counts.get("pending_intake_tasks", 0))
with cols[3]: card("טריגרים שנשלחו", counts.get("plan_monitor_sent_triggers", 0))

st.subheader("סיווג נתונים")
st.write("סטטוס קמפיינים:", {ai.he(k): v for k, v in (data.get("campaign_status") or {}).items()})
st.write("סטטוס אסטרטגי:", {ai.he(k): v for k, v in (data.get("strategy_status") or {}).items()})
st.write("איכות קמפיינים:", {ai.he(k): v for k, v in (data.get("campaign_quality") or {}).items()})
st.write("איכות סיכון:", {ai.he(k): v for k, v in (data.get("risk_quality") or {}).items()})
st.write("התאמת Trades:", ai.he(recon.get("status")), "|", ai.he(recon.get("data_quality_status")))

if st.sidebar.checkbox("מצב טכני: הצג JSON", value=False):
    st.json(data)
