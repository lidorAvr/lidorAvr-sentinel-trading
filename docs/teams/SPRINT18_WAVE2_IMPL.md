# Sprint 18 — Wave 2 Implementation (build)

**Date:** 2026-05-16 · **Branch:** `claude/review-system-audit-FBZ2h` · **Status:** build, tree dirty (parent consolidates).
**Gated by:** `MARK_SPRINT18_RULINGS.md` (authoritative methodology), `SPRINT18_DESIGN.md` (architecture).
**Baseline:** 1718 passed (verified pre-change with `python -m pytest -q -p no:cacheprovider`).

This doc is written incrementally. Every `⟨MARK:…⟩` slot is filled verbatim from
`MARK_SPRINT18_RULINGS.md` — nothing invented.

---

## 0. ⟨MARK⟩ slots — filled verbatim (single source of truth)

All wording lives in `report_open_book.py` module constants so there is exactly
one source. Filled from `MARK_SPRINT18_RULINGS.md`:

| Slot | Mark § | Verbatim value | `report_open_book.py` constant |
|---|---|---|---|
| Open-book section heading | §2 | `📌 ספר פתוח (לא ממומש)` | `OPEN_BOOK_HEADING` |
| Floating PnL/R unrealized label | §1 | `לא ממומש` | `OPEN_BOOK_UNREALIZED_LABEL` |
| ALGO observation-only label | §3 / DEC-20260511-001 | `פיקוח בלבד · לא הוראה` | `ALGO_OBSERVATION_LABEL` |
| ALGO single caveat (no false backtest caveat) | §3 | `מנוהל חיצונית — פיקוח, ללא הוראת Sentinel` | `ALGO_EXTERNAL_CAVEAT` |
| ALGO Structure-R no-stop token | §3 / DEC-011 | `—` (never `0.00R`) | `rec["structure_r_token"]` |
| Data-source tokens | §1 | `Live` / `Cached` / `Sync זמני` | `DATA_SOURCE_*` |
| Empty-state Case A line 1 | §2 | `✅ 0 קמפיינים נסגרו בתקופה — אין נתוני ביצועים ממומשים.` | `EMPTY_STATE_ZERO_CLOSED_WITH_BOOK_L1` |
| Empty-state Case A line 2 | §2 | `📌 ספר פתוח (לא ממומש): {N} פוזיציות · חשיפה {X}% · צף {±$Y}` | `EMPTY_STATE_ZERO_CLOSED_WITH_BOOK_L2` |
| Empty-state Case A line 3 | §2 | `📅 חלון: {label} · מקור: {Live/Cached/Sync זמני}` | `EMPTY_STATE_ZERO_CLOSED_WITH_BOOK_L3` |
| Empty-state Case B (truly empty) | §2 | `✅ 0 קמפיינים נסגרו · אין פוזיציות פתוחות. שבוע ללא פעילות מסחר.` | `EMPTY_STATE_TRULY_EMPTY` |
| Snapshot-delta baseline-pending | §4 | `Δ שבועי (mark-to-market): — · ממתין לבסיס שבוע קודם` | `DELTA_BASELINE_PENDING` |

§2 forbids the word "ללא עסקאות" while a live book exists — Case A uses
"0 קמפיינים נסגרו" wording instead; Case B (no book) keeps the legacy
"ללא עסקאות"-free honest sentence above.

---

## 1. New pure leaf — `report_open_book.py`

New file (no existing file rewritten). API:

- `build_open_book(df_trades, account_state, *, data_source_override=None) -> dict`
  — reads ONLY `ec.get_open_positions_campaign` (engine_core.py:473), returns a
  NEW `open_book_*`-namespaced dict; never raises (infra error ⇒
  `open_book_present=False`, realized report unaffected).
- `open_book_summary_lines(open_book)` — §1.4 Telegram lines.
- `empty_state_lines(open_book, period_label)` — §2 presentation switch.
- `compute_mark_delta(open_book, prev_snapshot)` — §4 pure subtraction / baseline-pending.

### Realized-byte-identical proof (by construction)

`report_open_book.build_open_book` imports `engine_core` only. It calls
`ec.get_open_positions_campaign(df)` (read-only — that function `df.copy()`s
internally, line 477), `ec.get_live_price`, `ec.get_campaign_risk_metrics`,
`ec.compute_r_true`, `ec.compute_r_target`, `ec.is_algo_position`. It NEVER
imports `analytics_engine`, never touches `compute_period_analytics`, returns a
fresh dict with `id()` distinct from the analytics dict. Therefore the realized
KPI dict is unchanged key-for-key with vs without this path — asserted by the
guard test (§5.1).

### Reuse-only proof (no invented math)

| Open-book field | Source (verbatim reuse) | Command-room parity |
|---|---|---|
| `floating_pnl` | `(curr - entry) * qty` | `telegram_portfolio.py:285` identical expression |
| `structure_r` | `ec.compute_r_true(open_pnl_usd, original_campaign_risk)` | `telegram_portfolio.py:312` |
| `account_r` | `ec.compute_r_target(open_pnl_usd, target_risk_usd)` | `telegram_portfolio.py:313` |
| `original_campaign_risk` | `ec.get_campaign_risk_metrics(row)` (single source of truth, engine_core.py:943) | command room inlines identical base_price/base_qty/init_stop inputs |
| `current` price honesty | `ec.get_live_price`, binary on actual `None` | `telegram_portfolio.py:279-283` |
| ALGO segregation | `ec.is_algo_position(setup, symbol)` (engine_core.py:247) | command room branches `setup=='ALGO'`; canonical predicate also catches symbol-fallback ALGO |

### ALGO #8 / observation-only proof

ALGO rows go to a DISTINCT `open_book_algo` list, NEVER `open_book_disc`,
NEVER summed into any realized figure (this module produces no realized
figure). `structure_r_token = "—"` (never `0.00R`, Mark §3 / DEC-011).
Exactly ONE caveat — `ALGO_EXTERNAL_CAVEAT` — and NO backtest caveat on the
live floating PnL/price (Mark §3: the number is live; only ALGO *rules* are
backtest-derived and none are shown here). `observation_label =
"פיקוח בלבד · לא הוראה"` (DEC-20260511-001).

---

## 2. Renderer wiring — `report_renderer.py`

| Change | file:line | Note |
|---|---|---|
| `render_weekly` additive `open_book`/`mark_delta` params + `ctx.update(_open_book_ctx(...))` | `report_renderer.py:29` | `_base_ctx` call unchanged; open-book keys merged AFTER realized ctx |
| `render_monthly` same additive params + ctx merge | `report_renderer.py:72` | same seam |
| `build_summary_text` additive `open_book`/`mark_delta` + §2 presentation switch | `report_renderer.py:115` | realized KPI lines unmodified; switch fires only when `campaigns_closed==0 AND open_book is not None` |
| NEW `_open_book_ctx` helper | `report_renderer.py:299` | returns ONLY `open_book_*`/`ob_*` keys; `_base_ctx` (`:247`) body byte-untouched (`git diff` proves) |

### Realized-byte-identical proof (renderer)

`_base_ctx` (`report_renderer.py:247`) is unchanged (diff: docstring/comment
references only, no logic line). `_open_book_ctx` reads `analytics` ONLY for
`analytics.get("campaigns_closed", 0)` (a read, never a write) and returns a
dict whose keys are all `open_book_*`/`ob_*` — none of the realized KPI keys
(`win_rate`, `expectancy_r`, `realized_pnl`, `total_r_net`, `setup_breakdown`,
`verdict`, `verdict_class`, …). Test
`TestRendererWiring::test_open_book_ctx_only_adds_namespaced_keys` asserts no
realized key leaks; the byte-identical guard test asserts the analytics dict is
`==` with vs without the open-book path.

### 920be95 + Sprint-16 + bcf32f5 preserved

- `compute_verdict` signature and realized logic NOT touched (the §2 honest
  empty-state is a presentation switch in `build_summary_text` /
  `_open_book_ctx`, keyed on `open_book is not None`).
- LEGACY callers that do NOT pass `open_book` (pre-Sprint-18 path, e.g.
  `test_report_renderer_degraded.TestPeriodAwareVerdict`) keep the BYTE-
  IDENTICAL 920be95 `"{period_word} ללא עסקאות"` verdict path — proven green
  (`test_report_renderer_degraded.py` all pass; new
  `test_zero_closed_legacy_caller_no_open_book_byte_identical`).
- `weekly_report.html.j2:116` `{:+,.0f}` realized-PnL format unchanged; the
  open-book section uses the SAME `{:+,.0f}` style for its own signed money.
- Sprint-16 graceful HTML-only degradation path unchanged (real-Jinja2 render
  of weekly+monthly WITH and WITHOUT open-book verified → produces `.pdf`/
  `.html`, no `ValueError`).
- `report_scheduler` `prev_snap` passed directly post-bcf32f5 (no
  `["analytics"]`); `compute_mark_delta` reads `prev_snap["open_marks"]`
  directly — test `TestBcf32f5Preserved` asserts no `["analytics"]` KeyError on
  a flat prev_snap.

### Templates (additive sections only)

`templates/weekly_report.html.j2` + `templates/monthly_report.html.j2`:
- `{% if ob_show_empty_state %}` honest banner directly below the verdict-badge
  (supplement, never replaces the badge — verdict_class unchanged).
- `{% if open_book_present %}` self-contained OPEN-BOOK section (disc table +
  ALGO sub-table with `structure_r_token`="—" + single
  `open_book_algo_external_caveat`, NO backtest caveat on live PnL) + data-
  source/price-fallback disclosure + mark-delta line. Every existing realized
  row/KPI/verdict element untouched (verified by rendering WITHOUT open_book →
  no `ספר פתוח` string present).

---

## 3. Snapshot — `report_snapshot_store.py`

| Change | file:line |
|---|---|
| `save` additive optional `open_book` kwarg | `report_snapshot_store.py:20` |
| Additive `open_marks` block, `_safe_float`-guarded, ALGO-segregated `per_symbol` | `report_snapshot_store.py:81` |

### Back-compat / additive proof

When `open_book` is None (or `open_book_present=False`) NO `open_marks` key is
written → snapshot is byte-identical to pre-Sprint-18; `load_recent` /
`load_previous` unchanged → old snapshots simply have
`snap.get("open_marks") is None`. NO migration, NO schema change
(`verify_migrations` unaffected — no DB touched). `_safe_float` reused for
inf/nan (test `test_safe_float_guards_inf_nan` → null, never a non-finite JSON
token). Single-user byte-identical (Hyperscaler addendum).

### Mark-to-market delta — baseline-pending (#1)

`report_open_book.compute_mark_delta`: prev snapshot `None` OR lacking
`open_marks` ⇒ verbatim `Δ שבועי (mark-to-market): — · ממתין לבסיס שבוע קודם`
(never a fabricated number). With a prior `open_marks` ⇒ delta = PURE
subtraction of two stored floats (`floating_pnl_disc` − prev, ALGO segregated
separately). No new math (reuses the floating PnL
`get_open_positions_campaign` already produced).

---

## 4. Scheduler + on-demand wiring

| Change | file:line |
|---|---|
| `_run_weekly`: build open_book + mark_delta from same df + prev_snap | `report_scheduler.py:237-238` |
| `_run_weekly`: pass into `render_weekly`, `snap_save(..., open_book=)`, `build_summary_text` | `report_scheduler.py:276` |
| `_run_monthly`: same seam | `report_scheduler.py:329-330`, `:367` |
| `report_on_demand.run_on_demand`: build + render open_book, `mark_delta=None`, **NO snap_save** | `report_on_demand.py:118-122` |

### On-demand NO-snap_save proof (Scope-B invariant)

`report_on_demand` builds the open-book for RENDERING ONLY and sets
`mark_delta=None` (an isolated test run must NOT read the real scheduled
snapshot history). It NEVER imports `report_snapshot_store.save`. Test
`TestOnDemandNoSnapSave::test_run_on_demand_never_calls_snap_save` spies
`report_snapshot_store.save` → `assert_not_called()`, while asserting the
open-book WAS built and passed into `render_weekly` (`open_book_present=True`,
`mark_delta is None`). The scheduled `_run_weekly`/`_run_monthly` own the only
`open_marks` write.

---

## 5. Test delta

- NEW `tests/test_open_book.py` (24 tests): realized-byte-identical guard +
  AST no-analytics-import proof; founder command-room HOOD/MRVL/PLTR/PWR/TSLA/
  WCC fixtures — ALGO segregation, dual-R/floating parity vs command room,
  ALGO `—` token, observation-only + single caveat + no false backtest caveat;
  data-source honesty (Live/Cached/Sync, price-fallback records symbol);
  empty-state matrix (Case A / Case B, never "ללא עסקאות" with a book);
  mark-delta baseline-pending + pure subtraction.
- NEW `tests/test_report_open_book_snapshot.py` (16 tests): snapshot additive/
  back-compat/`_safe_float`/round-trip; renderer-ctx namespacing + empty-state
  switch; `build_summary_text` Case-A/Case-B + legacy byte-identical + >0-closed
  realized prefix; on-demand no-snap_save; bcf32f5 flat-prev_snap.
- **Full suite: 1718 → 1756 passed, 0 failed** (`python -m pytest -q
  -p no:cacheprovider`). Drift/#8 AST guard (`test_sprint17_wave2.py`) green
  (`analytics_engine` imports no `algo_metrics` — open-book is a separate leaf).

> Note: a flaky FAILURE appears only in certain *partial* multi-file orderings
> (pre-existing cross-module `telebot` MagicMock leakage in
> `test_sprint17_wave2.py::test_button_in_developer_menu_only`); it PASSES in
> isolation, with its own file (35/35), and in the FULL suite (1756/1756 —
> the authoritative gate). Not introduced by Sprint-18.

---

## 6. Confirmations

- Realized KPIs byte-identical with vs without the open-book path; `analytics_
  engine.py` diff = 0 lines; `_base_ctx` body byte-untouched.
- Open book NEVER in realized WR/Expectancy/PF/Net-R/missing-stop/oversized
  (separate leaf, separate ctx keys, by construction + guard test).
- ALGO segregated into `open_book_algo`, observation-only
  ("פיקוח בלבד · לא הוראה"), Structure-R `—` (never 0.00R), exactly ONE caveat
  ("מנוהל חיצונית — פיקוח, ללא הוראת Sentinel"), NO false backtest caveat on
  live PnL (#8 / DEC-20260511-001 / Mark §3).
- #1 wording present: Case A / Case B verbatim, never "ללא עסקאות" with a live
  book, data-source + price-fallback honest.
- Snapshot additive + back-compat; delta baseline-pending until prior mark; on-
  demand NO snap_save.
- 920be95 + Sprint-16 graceful + bcf32f5 regressions intact.
- NO migration / docker-compose / secure_runner / realized-math change; no
  wholesale renderer rewrite; `get_open_positions_campaign` + existing R fns
  reused (no invented position math).

## 7. Deferred / out of scope

- Pre-existing note (NOT Sprint-18): `_run_weekly` reads `prev_snap` as a flat
  dict post-bcf32f5 — confirmed compatible; the older `["analytics"]`
  observation in DESIGN §3.1 is already resolved by bcf32f5 (not re-touched).
- Per-user open-book = Phase-B (Hyperscaler addendum) — not in scope.
- ALGO Oversight Gate numeric thresholds (DEC-20260515-014) — separate sprint,
  not built here.
