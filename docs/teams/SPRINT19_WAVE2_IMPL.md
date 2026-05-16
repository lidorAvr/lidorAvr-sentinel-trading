# Sprint 19 — Wave 2 Implementation (build engineer)

Branch `claude/review-system-audit-FBZ2h` · HEAD at start `2ad6c66` · baseline **1761 passed**.
Gated by `MARK_SPRINT19_RULINGS.md` (authoritative) + `SPRINT19_DESIGN.md`. Written incrementally
as code lands. **No git commit/push** — worktree left dirty for parent consolidation.

ONE workstream: (1) period-honest headline, (2) period-over-period + vs-average context,
(3) System-Health #1 fix + `_period_label` off-by-one.

---

## 0. ⟨MARK⟩ slot table (every value taken verbatim from `MARK_SPRINT19_RULINGS.md` — nothing invented)

| Design slot | Filled value | Ruling cite |
|---|---|---|
| headline badge text (0-closed + live book) | `📌 שבוע ללא סגירות — ספר פתוח פעיל` / monthly `📌 חודש ללא סגירות — ספר פתוח פעיל` | §1a:41 |
| headline badge class | `verdict-neutral` (existing class; not strong/defensive/mixed) | §1a:43-44 |
| §1b promoted banner L1 | `✅ 0 קמפיינים נסגרו בתקופה — אין ביצועים *ממומשים* (זה לא "ללא מסחר").` | §1b:54 |
| §1b promoted banner L2 (disc) | `📌 ספר פתוח (לא ממומש): {n_disc} דיסקרציוני · צף ${floating_disc:+,.0f} · חשיפה {exposure_disc:.1f}%` | §1b:55 |
| §1b promoted banner L3 (opened) | `🆕 {n_opened_total} פוזיציות נפתחו בתקופה זו` else `↳ כולן מוחזקות מתקופה קודמת (פעילות פתוחה לאורך החלון)` | §1b:56 |
| §1b promoted banner L4 (window) | `📅 חלון: {period_label} · מקור: {source}` | §1b:57 |
| §1b ALGO segregated line | `🟠 ALGO (פיקוח בלבד · לא הוראה): {n_algo} פוז' · צף ${floating_algo:+,.0f} · חשיפה {exposure_algo:.1f}% — מנוהל חיצונית, ללא הוראת Sentinel` | §1b:62 |
| §1c realized sub-heading | `📉 ביצועים ממומשים (0 קמפיינים נסגרו בתקופה)` | §1c:76 |
| §1c realized PnL card label | `רווח ממומש (0 בתקופה)` | §1c:78 |
| §1d truly-empty | legacy `compute_verdict` badge + `EMPTY_STATE_TRULY_EMPTY` (Sprint-18, unchanged) | §1d:84-88 |
| §2a realized vs-prev label | `מול תקופה קודמת (ממומש בלבד)` | §2a:107 |
| §2b realized vs-avg label | `מול ממוצע {k} {שבועות/חודשים}` (k = real count) | §2b:114 |
| §2c minimum-priors N | **N = 3** | §2c:119 |
| §2c baseline-pending token | `📊 מול ממוצע: — · ממתין ל-3 תקופות בסיס (קיימות {k} מתוך 3)` | §2c:126 |
| §2d open-book vs-avg label | `(לא ממומש)` open-book section only; same N≥3 + same token style | §2d:144-146 |
| §3a sync `ok`/`success` | `✅ סנכרון IBKR תקין` | §3a:183 |
| §3a sync `temporary`/`rate_limit` | `⏳ סנכרון IBKR — עיכוב זמני בצד IBKR (לא משפיע על דוח זה)` | §3a:184 |
| §3a sync `fatal` | `🔴 סנכרון IBKR — תקלה, נדרשת בדיקה (NAV עלול להיות לא עדכני)` | §3a:185 |
| §3a sync missing/parse/unknown | `⚠️ סנכרון IBKR — מצב לא ידוע` | §3a:186 |
| §3b `_period_label` | drop `- 1` in BOTH branches (inclusive end day) | §3b:200-206 |

Per `analytics_engine.py` hard constraint (git-diff EMPTY target), the new pure helpers
`compute_period_average` / `compute_open_book_history` are placed in the **presentation layer**
(`report_renderer.py` / `report_open_book.py`), NOT in `analytics_engine.py`. They reuse the
same metric list `compute_period_comparison:207-208` already emits — no realized math is added.

---

## 1. Period-honest headline — file:line (presentation-only, additive ctx)

- `report_renderer.py` — new constants `_HEADLINE_*` (verbatim §1a/§1b/§1c
  wording) + new additive seam `_headline_ctx(analytics, open_book,
  mark_delta, period_label, period_word)`. Trigger = `campaigns_closed==0`
  AND `open_book is not None` AND `open_book["open_book_present"]` (Sprint-18
  wired path; legacy `open_book is None` ⇒ mode False ⇒ byte-identical 920be95
  badge). Returns ONLY `headline_*` keys; reads, never writes a `_base_ctx`
  realized key. ALGO totals are read for the SEGREGATED line only; the disc
  banner line carries `floating_pnl_disc`/`exposure_pct_disc` only — never the
  disc+algo sum, never in the badge (#8).
- Wired in `render_weekly` (`ctx.update(_headline_ctx(... "שבוע"))`) and
  `render_monthly` (`... "חודש"`), right after `_open_book_ctx` — same
  additive-seam pattern Sprint-18 used. `compute_verdict` still called
  unchanged; `verdict`/`verdict_class` stay byte-identical.
- `templates/weekly_report.html.j2` / `monthly_report.html.j2` page 1:
  `{% if headline_open_book_mode %}` SUPPRESSES the dominant
  `verdict-badge verdict-{{verdict_class}}` and renders
  `verdict-{{headline_badge_class}}` (= `verdict-neutral`, an EXISTING class —
  `report_base.css:117`) + the promoted `freshness-banner` banner; the
  `{% else %}` branch keeps the byte-identical legacy badge + the Sprint-18
  `ob_show_empty_state` block (now reachable only for truly-empty §1d —
  defensive, identical output). Realized KPI grid gets a preceding
  `kpi-frame-note` sub-heading (`headline_realized_subheading`) and the
  realized-PnL card LABEL becomes `headline_realized_pnl_label` — the
  `kpi-value` expressions are byte-identical Jinja on the same `_base_ctx`
  keys.
- `templates/report_base.css` — added `.kpi-frame-note` (caption only; no
  change to any existing rule).

## 2. Period-over-period + vs-average — file:line (reuse + pure helpers)

- `report_renderer.compute_period_average(snapshots, n=3)` — NEW pure helper
  (placed here, NOT in `analytics_engine.py`, to keep that file git-diff
  EMPTY). Arithmetic mean of the SAME stored KPI floats
  (`report_snapshot_store.save:48-58`) the unchanged
  `compute_period_comparison:207-208` already uses. NO R/NAV/campaign/PF math.
  `profit_factor None` (inf-guarded by `_safe_float` on save) skipped
  per-metric. `< N` ⇒ `{"available": False, baseline_pending_text}` — never a
  partial mean (#1).
- `report_open_book.compute_open_book_history(open_book, snapshots,
  prev_snapshot, n=3)` — NEW pure helper. Prev leg = REUSE
  `compute_mark_delta` verbatim (its own `DELTA_BASELINE_PENDING` token). Mean
  of stored `open_marks` floats only (no `get_live_price`, no new PnL/R math).
  ALGO (`floating_pnl_algo`) averaged on its OWN line
  (`avg_algo_text`, carries `ALGO_OBSERVATION_LABEL` + `ALGO_EXTERNAL_CAVEAT`)
  — never folded into the disc mean (#8 / DEC-20260511-001). `< N`
  open_marks-bearing snapshots ⇒ baseline-pending token, never a number (#1).
  New constants `OPEN_BOOK_HISTORY_MIN_N=3`, `OPEN_BOOK_AVG_BASELINE_PENDING`.
- `report_renderer._comparison_ctx(comparison, period_average,
  open_book_history, period_type)` — additive seam emitting `cmp_*`/`obcmp_*`
  only; never mutates the unchanged `comparison` dict. §2a label
  `cmp_vs_prev_label = "מול תקופה קודמת (ממומש בלבד)"`.
- `render_weekly`/`render_monthly`/`build_summary_text` gain additive
  `period_average`/`open_book_history` kwargs (default None ⇒ byte-identical).
  `build_summary_text` appends the realized vs-average line AFTER the realized
  KPI block (never modifying lines `:171-185`) and the open-book cross-period
  lines via `_summary_open_book_cmp_lines` (ALGO segregated). `isinstance`
  guards keep a mock/None input from corrupting the realized text.
- Templates: ONE additive `{% if cmp_vs_avg_available %}` "מול ממוצע" column
  (weekly metrics table + monthly `rows` loop); the existing "vs previous"
  column header relabelled `{{ cmp_vs_prev_label }}` (text only — values
  unchanged); `< N` ⇒ §2c baseline-pending token shown ABOVE the table (text,
  never a number). Open-book section gains an `obcmp_*` block after the
  existing `open_book_mark_delta_text` line (disc + ALGO-segregated; always
  "(לא ממומש)" via the source strings; never in the realized table).
- `report_scheduler._run_weekly`/`_run_monthly` — `load_recent` is now
  imported in weekly too; `period_avg = compute_period_average(recent)`,
  `ob_history = rob.compute_open_book_history(open_book, recent, prev_snap)`,
  passed into `render_*` + `build_summary_text`. `load_recent` is called
  BEFORE `snap_save` ⇒ every snapshot is a true PRIOR (current period not yet
  written).
- `report_on_demand.py` §2f — replaced the hard `comparison = None` /
  `mark_delta = None` with READ-ONLY `load_previous`/`load_recent` (pure file
  reads — `report_snapshot_store.py:99-128`) feeding
  `compute_period_comparison`/`compute_mark_delta`/`compute_period_average`/
  `compute_open_book_history`. NO `report_snapshot_store.save`, NO
  `_mark_ran`/`_save_state` — the Scope-B invariant is preserved by
  construction (no `save` import/attr; asserted by `test_sprint17_wave2.py`
  AST check + `test_report_open_book_snapshot.py` spy).

## 3. System-Health #1 + `_period_label` — file:line

- `report_scheduler._build_system_health` — rewrote the sync line to switch on
  `last.get("status")`: `ok`/`success`→`✅ סנכרון IBKR תקין`;
  `temporary`/`rate_limit`→`⏳ סנכרון IBKR — עיכוב זמני בצד IBKR (לא משפיע על
  דוח זה)`; `fatal`→`🔴 סנכרון IBKR — תקלה, נדרשת בדיקה (NAV עלול להיות לא
  עדכני)`; missing/parse/unknown→`⚠️ סנכרון IBKR — מצב לא ידוע`. NEVER `✅` on
  non-success; the raw IBKR-flex `message` is NEVER interpolated (the
  `הדוח לא נוצר` string can no longer reach a delivered report).
- `report_renderer._period_label` — dropped `- 1` in BOTH branches
  (same-month AND cross-month). `period_end` from `_weekly_period`
  (Sat 23:59:59) and `_monthly_period` (`last_of_prev` 23:59:59) is the
  INCLUSIVE last instant ⇒ `.day` is already correct. Monthly April now reads
  `1–30 באפריל`; weekly Sun–Sat reads `3–9 במאי`.
  `_weekly_period`/`_monthly_period` definitions unchanged (arithmetic-only).

## 4. Proofs

- **Realized byte-identical:** `git diff --exit-code analytics_engine.py` ⇒
  EMPTY (test `TestRealizedByteIdentical::test_analytics_engine_git_diff_empty`).
  `_base_ctx` realized keys (`verdict`, `verdict_class`, `campaigns_closed`,
  `win_rate`, `expectancy_r`, `profit_factor`, `avg_win_r`, `avg_loss_r`,
  `total_r_net`, `realized_pnl`, `best_trade`, `worst_trade`,
  `setup_breakdown`, `missing_stop_rate`, `oversized_rate`, `avg_r_per_day`)
  asserted equal WITH vs WITHOUT every new path; new ctx keys are disjoint and
  all `headline_`/`cmp_`/`obcmp_`-namespaced. `compute_verdict` return value
  unchanged (920be95) — asserted.
- **#8 ALGO segregation in every new view:** headline badge/disc banner carry
  NO ALGO (`test_algo_not_in_headline_badge_or_disc_figures`: disc line `$+150`
  not `$+300`; ALGO only on its own `פיקוח בלבד · לא הוראה` line);
  `compute_open_book_history` ALGO mean on `avg_algo_text` only, never in
  `avg_text`; realized comparison cohort is already #8-filtered upstream
  (analytics untouched).
- **Headline honesty:** rendered page-1 HTML has NO `ללא עסקאות` when a live
  book spanned the period; the §1a badge + §1b banner present; realized cards
  still truthfully `0`/`$0`/`0.0%` reframed `(0 בתקופה)` + demoted.
- **Baseline-pending (#1):** `compute_period_average`/
  `compute_open_book_history` return baseline-pending tokens (verbatim §2c
  strings) for k∈{0,1,2}; exact arithmetic mean only at N≥3; no fabricated
  partial mean.
- **System-Health honesty:** `sync_status` never starts/contains `✅` for
  `temporary`/`rate_limit`/`fatal`/unknown/missing; `הדוח לא נוצר` never
  present; `success`→ exact OK line.
- **`_period_label`:** monthly `1–30 באפריל` (not `1–29`), `1–31 במרץ`,
  `1–28/1–29 בפברואר` (non-leap/leap); weekly `3–9 במאי`; legacy
  `TestPeriodLabels`/`test_security` invariants still green.
- **On-demand no snap_save:** `report_snapshot_store.save` spy
  `assert_not_called()`; AST proof no `save` import / no
  `report_snapshot_store.save` attribute; `_mark_ran`/`_save_state` raise if
  called — `run_on_demand` still ok.
- **Sprint-18 / 920be95 / bcf32f5 / Sprint-16 intact:** full prior suite green
  (period-scoping, prev_snap-no-`["analytics"]`, graceful PDF degrade,
  `compute_verdict` period_word signature) — 1761 baseline preserved.

## 5. Test delta / deferred

- New file `tests/test_sprint19_headline_comparison.py` — **+32 tests**
  (realized-byte-identical guard, headline switch + no-`ללא עסקאות`,
  truly-empty/legacy-caller, `compute_period_average`,
  `compute_open_book_history` + ALGO segregation, on-demand
  read-only/no-snap_save, System-Health honesty, `_period_label` inclusive
  end, comparison template wiring).
- Updated in place (evolved to the §2f-correct behavior — the no-snap_save
  invariant assertions are KEPT and strengthened):
  `tests/test_report_open_book_snapshot.py::TestOnDemandNoSnapSave`
  (`mark_delta` is now the honest baseline-pending dict, not None; still
  `snap_save.assert_not_called()`),
  `tests/test_sprint17_wave2.py::test_on_demand_module_does_not_call_snapshot_save`
  (AST: `save` still excluded; `load_recent`/`load_previous` now permitted
  pure reads).
- Full suite: baseline **1761 → 1793 passed, 0 failed** (1761 + 32 new; the
  evolved tests stay within the file counts). 1 pre-existing pandas
  UserWarning (unchanged `analytics_engine.py:30`), not introduced here.
  `test_button_in_developer_menu_only` is a pre-existing cross-file
  MagicMock-`telebot` ordering interaction (passes in isolation AND in the
  canonical full-suite order; unrelated to these changes).
- **Deferred (out of scope, carried):** per-user comparison (Phase-B);
  live accumulated Sprint 11–19 smoke-test; broker-recon $190.29 gap; ALGO
  Oversight Gate numeric thresholds (DEC-20260515-014, separate sprint).
