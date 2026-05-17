# Sprint-26 — Data / Supabase 100/100 Data-Integrity & Honesty Review (DOC-ONLY)

**Date:** 2026-05-17 · **Mode:** DOC-ONLY (no code, no schema, no migrations).
**Verdict:** **NOT 100/100.** One **P1** residual data-honesty gap on the
dashboard surface (fallback/stale NAV presented as `🏦 Live IBKR NAV`) +
two carried, still-open Sprint-25 items (F4 stray tag P2, F5 NULL-pnl P2).

**Note on baseline:** task cited HEAD `c761967`; the actual repo HEAD is
`8c5a948`. The three named phases ARE in history and were re-verified from
source: NAV-Unify (`5a0f2cb`), Engine-P2P3 F4/F5 (`b926e6e`), B1 (`9d7a1e3`).
The verdict below is against the real deployed source, not the doc claims.

---

## What was re-verified GREEN (from source, not from the impl docs)

| Area | Source re-verification | Status |
|------|------------------------|--------|
| NAV-Unify canonical core | `account_state._resolve_nav_core` (`account_state.py:48-143`) is the single classifier; `load()` is the shape-A adapter; `engine_core.get_nav_with_freshness` is the shape-B adapter over the SAME core (acyclic: account_state is a stdlib leaf). D1 explicit-0 kept, D2 strict-`<`, D3/D4 not-critical — matches PHASE_NAVUNIFY_IMPL. | ✅ honest, single-sourced |
| B1 Telegram/PDF NAV disclosure (Sprint-25 F1/F2) | `report_renderer._nav_disclosure_lines` (`:148-188`) fires iff NOT broker+fresh; appended in BOTH the 0-closed branch (`:488`) and the normal branch (`:570`); all three callers pass the loaded `account` — scheduler weekly (`report_scheduler.py:369`), monthly (`:477`), on-demand (`report_on_demand.py:232`) — BEFORE the `_DEGRADED_PDF_NOTE` trailer ⇒ degraded path covered. | ✅ F1/F2 CLOSED |
| F4 trade_id dedup (3 sites) | `analytics_engine._aggregate_campaigns:421-422` (per `campaign_id` group, BEFORE side split / `pnl_usd` sum); `adaptive_risk_engine.compute_closed_campaigns:147-148` (after `pd.isna(cid)` skip, before `split_side_first`); `engine_core.get_open_positions_campaign:527-528` (AFTER `sort_values(["trade_date","trade_id"])`, before `split_side_first`). All guarded `if "trade_id" in …columns` ⇒ no-op when absent; `keep="first"` after the deterministic sort in the engine site ⇒ stable. Provable identity on unique-id input (LOCKED April / DEC-019 prod). | ✅ correct |
| Unlinked / NULL-blank campaign_id disclosure | `analytics_engine` `_unlinked_keys` (`:75-93`) disjoint `unlinked_*` namespace, gated `count>0`, never summed into a KPI; surfaced to Telegram via `report_renderer._summary_unlinked_lines` (`:482,540`) + open-book (`:465,560`); independent read-only probe `period_data_probe.py:216-230` discloses `ללא campaign_id בחלון` + `Σ pnl_usd לא-מקושר`. | ✅ honest & complete |
| Live-updated `sentinel_config.json` NAV path | Single canonical reader via `_resolve_nav_core(_paths=_CONFIG_PATHS)`; `_CONFIG_PATHS` host/container both covered (`/app/...` + relative). | ✅ post-NAV-Unify canonical |
| `verify_migrations == 005` | `migrations/verify_migrations.py:32-58` enumerates ALL 5 (001…005); Sprint-25 F3 stale "two migrations" docstring NOW corrected (`:22-24`); runtime check is read-only `select("*").limit(1)` / `select(col).limit(1)`. 001–005 additive `IF NOT EXISTS`, each with a matching `rollback_00X.sql`. | ✅ integrity sound |
| No read-only-flow Supabase mutation | No `.insert/.update/.upsert/.delete` in `period_data_probe.py`, `report_scheduler.py`, `report_on_demand.py`, `report_renderer.py`, `report_open_book.py`, `analytics_engine.py` (the `ctx.update(...)` hits are Python dict updates, not Supabase). Probe is a single `select().execute()`. AGENTS.md #4 / DATA_CONTRACTS §"Supabase write contract" intact. | ✅ no read-side mutation |
| DATA_CONTRACTS vs code | `pnl_usd` net-of-commission (F6), period-boundary any-in-window-SELL (F7), F4 dedup note, F9 days_held floor, F7 cent-rounded 1R, F6 dual-PF — all present in `DATA_CONTRACTS.md` and match the code. | ✅ contract == code |

---

## DATA-INTEGRITY GAPS

### D-F1 (P1) — Dashboard sidebar presents fallback/stale/deposited NAV as `🏦 Live IBKR NAV` (B1 did NOT cover the dashboard surface)

- **Where:** `dashboard.py:105-107`
  ```python
  saved_nav = float(settings.get("nav", settings.get("total_deposited", 7500.0)))
  st.sidebar.success(f"🏦 Live IBKR NAV: **${saved_nav:,.2f}**")
  ```
  `settings` is the raw `sentinel_config.json` (`load_settings:44-50`, which itself
  falls back to `{"total_deposited": 7500.0}` on missing/corrupt). The headline is
  **unconditionally** labelled `🏦 Live IBKR NAV` inside a green `st.sidebar.success`
  box, with **no** freshness / staleness / fallback gate. The dashboard never calls
  `get_nav_with_freshness()` for this sidebar value — it only reads it at
  `dashboard.py:746` for the **AI-export footer** (`_NAV freshness: …`). The
  `_nav_source` broker-vs-deposited distinction IS computed at `dashboard.py:121`
  but is only applied to the `fmt_risk_capital_basis` caption (`:122-123`) — NOT to
  the line-107 headline.
- **Scenario:** `sentinel_config.json` has no `nav` (only `total_deposited`), or a
  stale broker NAV (e.g. 30h old), or is missing/corrupt → the dashboard shows e.g.
  `🏦 Live IBKR NAV: $7,500.00` in a green "success" box. The trader reads a
  fallback/stale figure as a fresh, live broker NAV; every dashboard risk/exposure
  panel scales off `current_acc_size = saved_nav`. This is the **exact CLAUDE.md
  red line** — "Do not silently present fallback data as exact truth" — and
  AGENTS.md prime-directive #1, on a *risk-sensitive* surface. The `fmt_risk_capital_basis`
  caption only discloses `deposited`/`fallback`, NOT a *stale broker* NAV (e.g. a
  30h-old `nav` is still `nav_source=="broker"` → caption stays silent), so even the
  partial disclosure misses the stale-broker case.
- **Contract:** `DATA_CONTRACTS.md` §"NAV / account-size contract" rule 2 ("If IBKR
  NAV is unavailable and the system falls back … the report must say so"); §"Core
  principle"; CLAUDE.md hard constraint; AGENTS.md #1. B1 (Sprint-25 Wave-2C) closed
  ONLY the Telegram/PDF summary path (`report_renderer.build_summary_text`) — its own
  impl record scopes it to that path; the dashboard sidebar was never in B1 scope.
- **Severity:** **P1.** **Value÷risk:** HIGH value ÷ LOW risk.
- **Tag:** **closure-fix (founder decision)** — changes a user-facing dashboard
  string (a Streamlit behavior change), so founder-gated per the fragile-area rules.
- **Recommendation (future governed Phase, NOT this sprint):** a dashboard-side B1
  analog. The honest signal already exists — `ec.get_nav_with_freshness()` returns
  `freshness_label` / `is_stale` / `source`. Minimal additive fix: when
  `nav_source != "broker"` OR the NAV is stale/critical, replace the green
  `st.sidebar.success("🏦 Live IBKR NAV …")` with a warning box reusing the verbatim
  `freshness_label` (e.g. `🟠 Fallback NAV — …` / `🟡 NAV ישן (…)`), mirroring B1's
  `_nav_disclosure_lines` gate exactly. Named proof: broker+fresh ⇒ byte-identical
  sidebar (regression guard); fallback/stale ⇒ token present. ZERO engine/analytics
  math change (presentation-only, like B1).

### D-F2 (P2, carried from Sprint-25 F4) — stray `</content>` tag in migration 005 + rollback_005

- **Where:** `migrations/005_create_open_tasks.sql:59` and
  `migrations/rollback_005.sql:18` both end with a literal `</content>` line —
  trailing non-SQL garbage after the final `--` comment block. Still present
  (Engine-P2P3 explicitly kept `migrations/` 0-diff; never authorized to touch it).
- **Scenario:** `005`/`rollback_005` are marked APPLIED 2026-05-15, so production is
  unaffected, but a fresh-environment / re-run copy-paste of the whole file into the
  Supabase SQL Editor hits a syntax error past the comment region. Low likelihood,
  real correctness defect.
- **Severity:** P2. **Value÷risk:** LOW ÷ LOW.
- **Tag:** **closure-fix (founder decision)** — a migration-file edit; out-of-scope
  for the no-migration-change guardrails. Recommendation: a future governed
  migration-hygiene Phase deletes ONLY the two `</content>` lines; `git diff` shows
  exactly two deleted lines; `verify_migrations` still exits 0.

### D-F3 (P2, carried from Sprint-25 F5) — NULL/blank `pnl_usd` on an in-window SELL silently coerced to $0

- **Where:** `analytics_engine.py:31` `_coerce_numeric(df, (… "pnl_usd"))` →
  `.fillna(0)` (`:356-361`); consumed by `_aggregate_campaigns:434`
  `net_pnl = float(sells["pnl_usd"].sum())`. A SELL row with NULL/blank/garbage
  `pnl_usd` contributes `$0.00` with no flag/counter (contrast: NULL `campaign_id`
  IS disclosed via `unlinked_*`).
- **Scenario:** DEC-019/-020 reconciliation proved the April production set has
  populated `pnl_usd` for all countable campaigns → **latent, not active**. A future
  import gap / manual SELL insert would understate realized PnL / Net R and silently
  reclassify a winner→breakeven with zero disclosure.
- **Severity:** P2 (latent; no production occurrence). **Value÷risk:** MEDIUM ÷ LOW.
- **Tag:** **addition (OUT — flag)** — a new "NULL-pnl SELL" disclosure counter is a
  net-new contract surface (mirrors WS-B). Flag for the data-completion backlog as a
  future governed Phase; named proof must keep the countable KPI subset + LOCKED
  April byte-identical (all `pnl_usd` populated ⇒ additive-only).

---

## Severity summary

| ID | Sev | Title | Tag |
|----|-----|-------|-----|
| **D-F1** | **P1** | Dashboard sidebar shows fallback/stale NAV as `🏦 Live IBKR NAV` (B1 not extended to dashboard) | closure-fix (founder) |
| D-F2 | P2 | Stray `</content>` in `005`/`rollback_005` (carried Sprint-25 F4) | closure-fix (founder, migration-OUT) |
| D-F3 | P2 | NULL `pnl_usd` SELL → silent $0, no counter (carried Sprint-25 F5, latent) | addition (OUT — flag) |

**P0:** none. The Supabase write contract, migration integrity, NAV canonical
single-source, F4 dedup correctness, unlinked disclosure, and the Telegram/PDF
B1 honesty path are all GREEN from source. The single live data-honesty hole is
**D-F1 — the dashboard NAV headline**, the same class of defect B1 closed for
Telegram but never extended to the dashboard surface.

---

## למנכ״ל — בשפה פשוטה

**האם הסוחר יכול לבטוח שמה שהוא רואה זה נתונים אמיתיים וכנים? כמעט — עם הסתייגות אחת חשובה.**

- בדוחות הטלגרם וב-PDF: **כן.** אם ה-NAV ישן / לא חי / ברירת-מחדל ($7,500),
  הדוח אומר את זה במפורש בשורת אזהרה ("NAV לא חי … מוערך, לא נתון מדויק"),
  כולל במצב שה-PDF נכשל. תוקן ונבדק מול הקוד.
- חישובי R / Net-R / Expectancy / Profit Factor / קמפיינים: **כן.** המספרים
  אמיתיים, מקור-NAV יחיד וקנוני, כפילויות שורות (trade_id) מנוטרלות, שורות
  בלי campaign_id לא נבלעות בשקט אלא מדווחות בנפרד. אין כתיבה ל-Supabase
  ממסלולי-קריאה.
- **ההסתייגות (P1):** במסך ה-Dashboard, בצד, הכותרת `🏦 Live IBKR NAV`
  מוצגת בקופסה ירוקה תמיד — **גם כשהמספר הוא ברירת-מחדל או ישן ולא חי.**
  שם, ושם בלבד, נתון fallback/ישן עלול להיראות כמו NAV חי אמיתי. זה בדיוק
  הקו האדום ש-CLAUDE.md אוסר — רק שתיקון ה-honesty (B1) כיסה את הטלגרם/PDF
  ולא הורחב למסך ה-Dashboard.

**שורה תחתונה:** מי שמסתמך על דוחות הטלגרם — הנתונים כנים. מי שמסתכל על
ה-Dashboard בצד — שלא יבטח בשורת ה-NAV הירוקה בלי לאמת שהיא טרייה, עד שיתוקן.

## מה צריך לעשות

1. **D-F1 (P1, החלטת מייסד):** לפתוח Phase עתידי מנוהל שמרחיב את לוגיקת B1
   ל-`dashboard.py:107` — כשה-NAV לא ברוקר-טרי, להחליף את הקופסה הירוקה
   `🏦 Live IBKR NAV` באזהרה שמשתמשת ב-`freshness_label` הקיים מ-
   `get_nav_with_freshness()`. תוספת תצוגה בלבד, אפס שינוי מתמטיקה; הוכחה:
   broker+fresh נשאר byte-identical, fallback/stale מציג אזהרה.
2. **D-F2 (P2, החלטת מייסד, OUT לספרינט זה):** Phase היגיינת-מיגרציות עתידי
   שמוחק רק את שתי שורות `</content>` ב-`005`/`rollback_005`.
3. **D-F3 (P2, OUT — לתעד):** לרשום ב-backlog השלמת-הנתונים מונה-גילוי
   ל-SELL עם `pnl_usd` ריק (מראה ל-`unlinked_*`); כרגע latent בלבד.
4. **לא לגעת השבוע:** הכול מאומת DOC-ONLY; כל תיקון הוא Phase עתידי מנוהל
   עם הוכחה, אחרת LOCKED April / Sprint-22 / byte-locks נשברים.
