# Sprint-20 Step-2 Wave-2 — IMPL: Honest disclosure of the CLOSED-but-excluded realized leg

**Date:** 2026-05-16 · **Branch:** `claude/review-system-audit-FBZ2h`
**Status:** built, full suite green (1816 passed, baseline 1793 +23). NOT committed (parent consolidates).
**Authority:** `docs/teams/MARK_SPRINT20_RULINGS.md` (gate APPROVED, presentation/additive only) +
`docs/teams/SPRINT20_DESIGN.md` + DEC-20260516-017(+UPDATE)/-016/-015 / DEC-20260511-001 /
DEC-20260515-014 / AGENTS.md #1/#8 / CLAUDE.md (no campaign/R/NAV math; no wholesale rewrite).

This is a pure **#1 silent-disclosure** fix. The numbers already existed (`excluded_count`/
`excluded_pnl` at `analytics_engine.py`) and were rendered NOWHERE. ZERO campaign/R/NAV/
Expectancy math change. Excluding no-stop campaigns from edge stats stays methodologically
correct (#8 — no R without a stop); the defect was the silent omission.

---

## 1. File:line per change

### 1.1 `analytics_engine.py` — ADDITIVE manual/ALGO partition only

| Change | Location | Nature |
|---|---|---|
| Manual/ALGO partition of the SAME `excluded["net_pnl"]` | `analytics_engine.py:60-75` (directly after the existing `excluded_count`/`excluded_pnl` at `:57-58`) | ADDITIVE — `excl_algo = excluded[stat_bucket == ec.STAT_BUCKET_ALGO]`, `excl_manual = excluded[stat_bucket != ec.STAT_BUCKET_ALGO]`; four new ints/floats. NO new R/NAV/campaign/Expectancy math — read-only `len()`/`.sum()` of the already-filtered `excluded` frame, by the already-computed `stat_bucket` series (the predicate already used at `:54-55`). |
| 4 keys in `countable.empty` early return | `analytics_engine.py:103-106` | ADDITIVE — `excluded_count_manual/_pnl_manual/_count_algo/_pnl_algo` appended; the pre-existing `"excluded_pnl": excluded_pnl}` closing brace was reflowed to `,` + a separate `}` (key NAME/VALUE byte-identical). |
| 4 keys in main return | `analytics_engine.py:167-170` | ADDITIVE — appended after `excluded_pnl`. |
| 4 keys in `_empty()` (all 0) | `analytics_engine.py:344-347` | ADDITIVE — `_empty()` already set `excluded_count/_pnl` 0; the four split keys also 0. |

`compute_period_analytics:14` countable path (`:87-146` win/loss/WR/Exp/PF/Net-R/best/worst/
setup_breakdown), `campaigns_closed = len(countable)` (`:89`), and `compute_verdict:230`
(920be95) are byte-identical (no edit). `excluded_count`/`excluded_pnl` existing values
UNCHANGED — only ADD `*_manual`/`*_algo`. `engine_core` `classify_stat_bucket`/
`is_stat_countable`/`STAT_BUCKET_*` (`:1238-1263`) UNTOUCHED.

### 1.2 `report_renderer.py` — additive `_excluded_ctx` seam + summary block

| Change | Location | Nature |
|---|---|---|
| Mark-verbatim wording constants | `report_renderer.py:68-117` | NEW module constants; each cites its Mark §-slot. |
| `_excluded_ctx(analytics) -> dict` helper | `report_renderer.py:750-814` | NEW pure helper; returns ONLY `excl_*` keys; reads ONLY the already-computed `excluded_*` analytics keys. Gated `excluded_count>0`. Same disjoint-namespace discipline as `_headline_ctx:534`/`_comparison_ctx:615`. |
| `_summary_excluded_lines(analytics) -> list` helper | `report_renderer.py:489-518` | NEW pure helper; builds the Telegram lines from `_excluded_ctx`; `[]` when `excluded_count==0`. |
| Wire into `render_weekly` ctx | `report_renderer.py:222-224` (`ctx.update(_excluded_ctx(analytics))` after `_comparison_ctx`) | ADDITIVE; signature UNCHANGED. |
| Wire into `render_monthly` ctx | `report_renderer.py:279-281` | ADDITIVE; signature UNCHANGED. |
| `build_summary_text` normal path | `report_renderer.py:393-400` (after vs-average lines, before the Sprint-18 open-book append) | ADDITIVE `lines.extend(_summary_excluded_lines(analytics))`; realized KPI lines above NOT modified. |
| `build_summary_text` Case-A 0-closed path | `report_renderer.py:346-353` (after ob-cmp lines, before heat thermometer) | ADDITIVE; founder scenario (countable 0, excluded N) surfaces honestly, NOT "ללא עסקאות". |

`_base_ctx:427-476` realized keys, `_open_book_ctx:479`, `_headline_ctx:534`,
`_comparison_ctx:615` NOT touched. `render_weekly`/`render_monthly`/`build_summary_text`
signatures UNCHANGED ⇒ all existing callers (`report_scheduler.py`, `report_on_demand.py`)
byte-identical; the block only appears when `excluded_count>0`.

### 1.3 Templates — new `{% if excl_present %}` section (REALIZED side)

| Template | Location | Placement |
|---|---|---|
| `templates/weekly_report.html.j2:172-209` | after `🏆 עסקאות קיצוניות` (`:164-170`), before the Sprint-18 `{% if open_book_present %}` (`:212`) | REALIZED side, distinct disclosure block. |
| `templates/monthly_report.html.j2:213-250` | after the realized breakdown / weekly-breakdown block (`:211`), before the Sprint-18 open book (`:253`) | REALIZED side, identical markup. |

Both: a `<h3>`/caveat + a 3-row metrics table (manual row iff `excl_count_manual>0`,
ALGO row iff `excl_count_algo>0`, total row), the §1 manual line, the §2 ALGO
observation-only caveat, and the §4 founder note. NOT a KPI card; NEVER summed into the
realized cards / verdict / metrics-table (which are untouched markup).

### 1.4 Tests

| File | Change |
|---|---|
| `tests/test_sprint20_wave2_excluded_disclosure.py` | NEW — 23 tests (split, countable-byte-identical, disclosure presence, #1 wording, ALGO segregation, Sprint-19 reconciliation, on-demand no-snap_save). |
| `tests/test_analytics_engine.py:326-368` | EXTENDED (not duplicated) — `test_excluded_pnl_reported` + `test_all_excluded_returns_empty_with_disclosure` now also assert the manual/ALGO split + invariant on the existing mixed fixtures. |
| `tests/test_sprint19_headline_comparison.py:142-200` | UPDATED `test_analytics_engine_git_diff_empty` — the Sprint-19 git-diff-empty guard was Sprint-19-scoped; rescoped to assert the Sprint-20 diff is purely the Mark-APPROVED additive `excluded_*_manual`/`_algo` split (no removed/modified countable/edge/verdict line; only the early-return brace reflow tolerated, key/value byte-identical). |

---

## 2. ⟨MARK⟩ slots filled (all VERBATIM from MARK_SPRINT20_RULINGS.md — nothing invented)

| Slot | Source | Value (constant @ `report_renderer.py`) |
|---|---|---|
| §1 manual-incomplete line | MARK §1 | `_EXCL_MANUAL_LINE` `:77` — `ℹ️ {n} קמפיינים נסגרו בתקופה אך הוחרגו מסטטיסטיקת ה-edge (חסר stop) — רווח/הפסד ממומש לא-מאומת: ${x:+,.0f}. השלם entry/stop כדי להיכלל.` |
| §2 ALGO observation-only line | MARK §2.2 | `_EXCL_ALGO_LINE` `:83` — `🔭 {n} קמפייני ALGO נסגרו בתקופה — מנוהל חיצונית, פיקוח בלבד · לא הוראה. ממומש לא-מאומת: ${x:+,.0f} (לא נספר ב-edge).` |
| §4 founder data-completion note | MARK §4 | `_EXCL_FOUNDER_NOTE` `:90` — `📋 {n} קמפיינים נסגרו ללא initial_stop ולכן לא נכנסו לסטטיסטיקת ה-edge. זו השלמת נתונים — לא תקלת מערכת. השלם entry/stop בכל קמפיין כדי שייספר ב-WR/Expectancy/PF/Net-R.` |
| Section heading | MARK §1/§2 terms | `_EXCL_HEADING` — `📕 קמפיינים שנסגרו בתקופה אך הוחרגו מסטטיסטיקת ה-edge` |
| Caveat | MARK §1 hard-rule 1/2 + #8 | `_EXCL_CAVEAT` — `רווח/הפסד ממומש לא-מאומת · חסר initial stop · לא נספר ב-WR / Expectancy / PF / Net-R (#8 — אין R ללא stop)` |
| Manual / ALGO / total row labels | MARK §1/§2 | `_EXCL_ROW_MANUAL`=`ידני · חסר stop (DATA_INCOMPLETE)`; `_EXCL_ROW_ALGO`=`🟠 ALGO · פיקוח בלבד · לא הוראה`; `_EXCL_ROW_TOTAL`=`סה"כ מוחרג (לא-מאומת)` |
| ALGO caveat | MARK §2 (reuse Sprint-18 canonical) | `report_open_book.ALGO_EXTERNAL_CAVEAT` = `מנוהל חיצונית — פיקוח, ללא הוראת Sentinel` |
| Split required? | MARK §2.1 | YES — "a split IS required for honest disclosure"; minimal additive partition implemented. |

---

## 3. Proofs

**Countable-byte-identical proof.** `compute_period_analytics` countable path
(`:87-146`) and `compute_verdict` (`:230`) have NO edited line — the only analytics
change is 4 additive `excluded_*_manual`/`_algo` keys derived by `len()`/`.sum()` of the
already-filtered `excluded` frame. Proven by `test_countable_kpis_identical_with_vs_without_excluded`
(pure-manual vs mixed dataset: WR/Exp/PF/Net-R/realized_pnl/best/worst/setup_breakdown/
avg_r_per_day byte-identical) and `test_same_analytics_realized_ctx_byte_identical_vs_no_excluded_seam`
(SAME analytics, with vs without the `_excluded_ctx` seam neutralized: realized +
discipline ctx + verdict byte-identical, seam adds ONLY `excl_*` keys). `_base_ctx`
realized keys never read/written by `_excluded_ctx` (proof by construction;
`test_excluded_ctx_namespace_disjoint`). Note: `missing_stop_rate`/`oversized_rate`
correctly MOVE across *different* datasets (they count MANUAL incl. DATA_INCOMPLETE by
design — `analytics_engine.py:54,60-71`; that is the metric's purpose) but are byte-
identical for the SAME analytics with/without the seam.

**ALGO-#8 proof.** ALGO is partitioned by the canonical `ec.STAT_BUCKET_ALGO`
(`analytics_engine.py:70`, set by `classify_stat_bucket:1251-1252`). ALGO is never in
`countable` (existing `:53` — unchanged), never in WR/Exp/PF/Net-R, never in the
headline (`test_algo_not_in_headline_badge`), rendered ONLY on its own observation-only
row/line carrying NO `השלם` instruction (`test_algo_line_observation_only_no_instruction`).
`test_split_follows_canonical_stat_bucket_not_symbol` confirms the split follows the
existing `stat_bucket` series exactly (an explicit `setup="ALGO"` close → ALGO; a no-stop
unknown-setup close stays DATA_INCOMPLETE/manual — pre-Sprint-20 classification UNCHANGED).

**Never-summed proof.** `realized_pnl` on the mixed fixture == `$200` (the countable win
only), NOT `$200+$900`; `total_r_net == +2.0`; `win_rate == 1.0`; PF == `+inf`
(`test_excluded_never_summed_into_realized`). The disclosure is a separate block/line set
gated `excluded_count>0`, never added into any realized KPI.

**#1 "לא-מאומת" proof.** `test_summary_has_lo_meumat_and_action_hint` asserts `לא-מאומת`
+ `השלם entry/stop` + `הוחרגו מסטטיסטיקת ה-edge` present, with raw `$+300` and NO
R/WR/PF attached; `test_rendered_html_contains_disclosure_and_amounts` asserts the same
tokens in the PDF HTML; `test_no_excluded_no_section` asserts absence when
`excluded_count==0`. Founder note framed as data-completion not a fault
(`test_founder_note_data_completion_not_system_error` asserts
`זו השלמת נתונים — לא תקלת מערכת`, mirroring `bot_health.py:147` honest `אינו נספר` tone).

**On-demand no-snap_save proof.** `test_on_demand_excluded_no_snap_save` runs
`report_on_demand.run_on_demand` on the mixed fixture with `report_snapshot_store.save`,
`sched._mark_ran`, `sched._save_state` patched to raise — `res["ok"] is True`, none
called (Scope-B invariant intact).

**Regression intact.** Full suite `python -m pytest -q -p no:cacheprovider`:
**1816 passed, 0 failed** (baseline 1793 +23 new). Sprint-18 period-scoping, Sprint-19
headline/comparison/System-Health, 920be95, bcf32f5, Sprint-16 graceful WeasyPrint,
`_period_label` inclusive-end all green. No `docker-compose.yml` /
`telegram_bot_secure_runner.py` / migration / Supabase-schema change (verified clean
via `git status`); `report_open_book.py` unrealized block untouched & still separate.

---

## 4. Test delta

+23 new (`tests/test_sprint20_wave2_excluded_disclosure.py`), 2 existing analytics tests
extended in place (`tests/test_analytics_engine.py`), 1 Sprint-19 guard rescoped
(`tests/test_sprint19_headline_comparison.py`). 1793 → 1816 passed, 0 failed.

---

## 5. Deferred (OUT of Sprint-20 Step-2 scope)

- **Partial-exit double-surface** (a campaign with an in-window partial SELL also
  appearing in the open book) = Mark Q1 / RCA failure (c). Explicitly OUT of scope; the
  closed-but-excluded leg and the open book are disjoint by source
  (`_get_closed_campaigns` requires in-window SELL; `get_open_positions_campaign`
  net-open filter), so no double-count within Step-2. Deferred to the gated union build.
