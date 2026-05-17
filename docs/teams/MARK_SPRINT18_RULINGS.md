# MARK — Sprint 18 Rulings (gates Wave 2)

DEC-20260516-015 made precise. Code-cited. No code; no commit/push.

## 1. Realized/unrealized boundary (crux)
Open-book reads ONLY `ec.get_open_positions_campaign` (`engine_core.py:473`) — the
command-room source. Invent no position/PnL/R math. Per position SHOW: symbol,
entry (`base_price`), current price, floating PnL, **Structure R** (`compute_r_true`
:997, vs `get_campaign_risk_metrics` :943 `original_risk`) **and Account R**
(`compute_r_target` :1004, vs frozen target) — both labelled, never one conflated
(DEC-20260515-011); Risk Capital Basis (DEC-20260515-012); exposure %; ALGO-or-not;
market status (Live/Cached/Sync-temporary). Floating PnL/R explicitly labelled
"לא ממומש" (unrealized).
**Exclusion guard:** open-book consumes a SEPARATE ctx key (`open_book`); it never
enters `compute_period_analytics` (`analytics_engine.py:14`) — that function takes
only the closed-trades df and is byte-untouched. Realized KPIs (WR/Expectancy/PF/
Net-R/missing-stop/oversized) MUST be byte-identical with vs without the open-book
path. Guard test asserts identical `compute_period_analytics` output for both.

## 2. Honest empty-state (Hebrew, RTL, #1)
0 closed + live book — REPLACE "שבוע/חודש ללא עסקאות" (`compute_verdict` :239) at the
render layer (do NOT regress 920be95 period-aware verdict / weekly:116):
`✅ 0 קמפיינים נסגרו בתקופה — אין נתוני ביצועים ממומשים.`
`📌 ספר פתוח (לא ממומש): {N} פוזיציות · חשיפה {X}% · צף {±$Y}`
`📅 חלון: {label} · מקור: {Live/Cached/Sync זמני}`
Truly empty (0 closed AND 0 open):
`✅ 0 קמפיינים נסגרו · אין פוזיציות פתוחות. שבוע ללא פעילות מסחר.`
Never the word "ללא עסקאות" while a book exists.

## 3. ALGO open positions
ALGO segregated into an own block (#8 / DEC-20260515-014 / `is_algo_position`,
`STAT_BUCKET_ALGO` :1232) — NEVER in headline, never in any KPI/cohort. Labels:
"פיקוח בלבד · לא הוראה" (DEC-20260511-001). Caveat ruling: floating PnL/price IS
live and real-time — attach NO backtest caveat to it. The backtest caveat applies
ONLY to ALGO *rules/stats*; since the open-book shows none, NO backtest caveat
appears here. Exactly one caveat: "מנוהל חיצונית — פיקוח, ללא הוראת Sentinel".

## 4. Snapshot-delta rule
New additive `report_snapshot_store.save` (:20) field `open_marks`: list of
`{symbol, qty, price, floating_pnl, structure_r, account_r, is_algo}` +
`open_exposure_pct`, `open_total_floating`, `marks_source`. Weekly delta shown
ONLY when `load_previous` (:77) yields a prior `open_marks`; until then exactly:
`Δ שבועי (mark-to-market): — · ממתין לבסיס שבוע קודם` (no retroactive fabrication,
#1). `report_on_demand.py` performs NO `snap_save` (Scope-B invariant, file:15) —
the scheduled `_run_weekly`:265 / `_run_monthly`:345 own the only write.

## 5. Pass/fail checklist
1. Realized KPIs byte-identical with vs without open-book path (guard test). 2.
`compute_period_analytics` untouched. 3. Open book never in WR/Exp/PF/Net-R/
missing-stop/oversized. 4. ALGO never in headline/cohort (#8). 5. ALGO labelled
observation-only (DEC-011). 6. No false/missing backtest caveat (§3). 7. Empty-state
never says "ללא עסקאות" with a live book. 8. Window + source honest (#1). 9.
`open_marks` additive; no migration. 10. Delta "—/baseline pending" until prior
mark. 11. on-demand still NO snap_save. 12. 920be95 + Sprint-16 graceful + no
R/NAV/campaign math change — not regressed.
