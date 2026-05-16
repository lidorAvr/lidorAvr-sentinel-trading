# Sprint 19 — Architecture + Engine Design

**Period-honest headline · Period-over-period + vs-average · System-Health #1 fix + `_period_label` off-by-one**

Branch `claude/review-system-audit-FBZ2h` · doc-only (Wave 1) · DEC-20260516-016.
Mark's `MARK_SPRINT19_RULINGS.md` is **ABSENT** at write time → every label / threshold / N / wording is a verbatim `⟨MARK:…⟩` slot. **Nothing invented.** Wave 2 is gated on Mark filling these.

Citations are `file:line` against the tree at `2c8745d`.

---

## 0. Invariants this design preserves (proof-by-construction summary)

- `analytics_engine.py` **0-diff** — no edit to `compute_period_analytics:14`, `compute_verdict:230` (920be95 signature `period_word=` arg), `compute_period_comparison:199`, `_get_closed_campaigns:255`, `_aggregate_campaigns:265`, the #8 seam `:43-58`. Realized R / NAV / campaign / Expectancy / PF math untouched.
- `report_renderer._base_ctx:247` realized KPI keys (`win_rate`, `expectancy_r`, `profit_factor`, `total_r_net`, `realized_pnl`, `campaigns_closed`, `verdict`, `verdict_class`, …) **byte-identical** — all new ctx is **additive, namespaced** (`headline_*`, `cmp_*`, `obcmp_*`) emitted from a NEW seam helper, never mutating `_base_ctx`'s returned dict.
- `report_open_book.build_open_book:135` / `compute_mark_delta:419` / `open_marks` snapshot field / Sprint-18 §5 period-scoping: **not regressed** (read-only reuse only).
- On-demand: **NO** `report_snapshot_store.save`; comparison/average read existing per-host history **READ-ONLY**.
- ALGO #8-segregated and observation-only (DEC-20260511-001) in every new comparison/average; **ALGO never in the headline**.
- `telegram_bot_secure_runner.py`, `docker-compose.yml`, Supabase schema / `verify_migrations`: **untouched** (no migration — Hyperscaler addendum).

---

## 1. Period-honest headline (presentation-layer switch)

### 1.1 Problem (cited)

When `analytics.campaigns_closed == 0`, `compute_verdict:238-239` returns `("{period_word} ללא עסקאות", "neutral")`. Templates render this as the dominant `verdict-badge` (`weekly_report.html.j2:22`, `monthly_report.html.j2:20`) plus all-zero KPI cards (`weekly:35-70` / `monthly:30-65`). Sprint-18's honest banner (`ob_show_empty_state`, `weekly:28-32` / `monthly:24-28`) is a *subordinate* `freshness-banner` **below** the badge — visually buried while a live book (+$72 wk / +$224 mo, 33–34% exposure, 4 opened-in-period) spanned the period.

### 1.2 Design — additive ctx + template reframe, zero realized-byte change

Keying signal (already available, no new compute):
`headline_open_book_mode = (analytics.get("campaigns_closed",0) == 0) and bool(open_book and open_book.get("open_book_present"))`
— exactly Sprint-18's `open_book_present` (`report_open_book.py:313`) AND `campaigns_closed==0`. Truly-empty (`open_book_present == False`) ⇒ mode off ⇒ legacy badge path preserved.

New helper `report_renderer._headline_ctx(analytics, open_book, mark_delta, period_label)` returning **only** `headline_*` keys, called from `render_weekly:65` / `render_monthly:108` right after `_open_book_ctx` (same additive seam pattern Sprint-18 used at `report_renderer.py:299-351`). It **reads** `analytics`/`open_book` but **never** writes a `_base_ctx` key:

| ctx key | value | source |
|---|---|---|
| `headline_open_book_mode` | bool above | derived |
| `headline_badge_text` | `⟨MARK: dominant badge wording when 0 closed + live book — must NOT read "ללא עסקאות"/"no trading/zero"; reflects OPEN-BOOK period performance; ALGO excluded (#8)⟩` | Mark |
| `headline_badge_class` | `⟨MARK: verdict-badge CSS class for the open-book headline (e.g. a neutral/info class — must NOT be "defensive"/"strong"/"mixed" since those are realized verdicts; reuse an existing class in report_base.css)⟩` | Mark |
| `headline_sub_lines` | reuse `rob.empty_state_lines(open_book, period_label)` Case-A (`report_open_book.py:377-416`) — already founder-approved Sprint-18 wording; ALGO segregated in totals | reuse |
| `headline_realized_frame` | `⟨MARK: the short label that demotes the realized KPI block, e.g. "0 ממומש — ראה ספר פתוח"; realized cards stay byte-identical, only gain this caption⟩` | Mark |

`compute_verdict` is **still called unchanged** (`render_weekly:52`, `render_monthly:93`); its `verdict`/`verdict_class` stay in ctx **byte-identical** (legacy path / 920be95 / Sprint-16 graceful / non-zero-campaign callers unaffected). The template *chooses which to show*; the verdict value itself never changes.

### 1.3 Template change (presentation only)

`weekly_report.html.j2:22` and `monthly_report.html.j2:20`, the dominant badge line:

```jinja
{% if headline_open_book_mode %}
<div class="verdict-badge {{ headline_badge_class }}">{{ headline_badge_text }}</div>
<div class="freshness-banner freshness-unknown">
  {% for line in headline_sub_lines %}<div><span class="ltr">{{ line }}</span></div>{% endfor %}
</div>
{% else %}
<div class="verdict-badge verdict-{{ verdict_class }}">{{ verdict }}</div>
{% endif %}
```

KPI cards (`weekly:35-70` / `monthly:30-65`): **unchanged markup/values**; add ONLY a caption row above the grid, rendered solely when `headline_open_book_mode`:
```jinja
{% if headline_open_book_mode %}<div class="kpi-frame-note"><span class="ltr">{{ headline_realized_frame }}</span></div>{% endif %}
```
The numbers in every `kpi-value` stay the exact same Jinja expressions on the exact same `_base_ctx` keys ⇒ realized cards byte-identical; only a sibling caption is added in the new mode. The Sprint-18 `ob_show_empty_state` block (`weekly:28-32`) becomes redundant under the new headline and is **folded into** `headline_sub_lines` (same `rob.empty_state_lines` source — no wording change, no regression); it remains for `open_book is not None and campaigns_closed==0` only when `headline_open_book_mode` is false (defensive — identical output).

`build_summary_text` (`report_renderer.py:115`): Sprint-18 already switches the Telegram text to the honest open-book lines at `:157-169` (Case A/B). **No change needed** for the headline issue in text — it is the *PDF/template* badge that is the #1 visual defect. (Comparison lines added in §2.)

### 1.4 Realized-byte-identical proof

`_headline_ctx` returns a dict whose keys are all `headline_*` (disjoint from `_base_ctx` keys). `ctx.update(_headline_ctx(...))` cannot collide. With Mark slots empty the helper is not wired ⇒ literally zero behaviour change. Guard test §4.1 asserts the realized ctx subset is identical with/without the new code path and `git diff analytics_engine.py` is empty.

---

## 2. Period-over-period + vs-average

### 2.1 Realized — reuse `compute_period_comparison` + `load_recent`

`compute_period_comparison:199` already exists (used at `report_scheduler.py:229,325`) and yields `{metric:{current,previous,delta,direction,improving}}`. It is **reused unchanged**.

**vs previous (realized).** Already wired for scheduled runs (`_run_weekly:229`, `_run_monthly:325`) via `load_previous`. Gap: on-demand passes `comparison=None` by design (`report_on_demand.py:126`). Sprint-19 change: on-demand may compute it **READ-ONLY** from existing history:
```python
# report_on_demand.py — replace the hard None with a read-only read:
from report_snapshot_store import load_previous
prev_snap  = load_previous(period_type, period_start)   # READ-ONLY
comparison = compute_period_comparison(analytics, prev_snap) if prev_snap else None
```
`load_previous:121` only reads files (`load_recent:99` → `os.listdir`/`json.load`). **No `report_snapshot_store.save`, no `_mark_ran`/`_save_state`.** The Scope-B no-mutation invariant (`report_on_demand.py:14-23`) is preserved and re-asserted by test §4.5.

**vs average (realized) — NEW pure helper, no new financial math.** Add `analytics_engine.compute_period_average(snapshots: list, n: int) -> dict` — a pure arithmetic mean over the **already-stored** snapshot KPI floats (`report_snapshot_store.save:48-58` writes `win_rate`/`expectancy_r`/`profit_factor`/`total_r_net`/`realized_pnl`/`missing_stop_rate`/`oversized_rate`/`avg_r_per_day`). It computes **no R/NAV/campaign math** — only `mean()` of values the realized engine already produced and persisted. Same metric list as `compute_period_comparison:207-208`. Signature:

```python
def compute_period_average(snapshots, n):
    """Mean of stored KPI floats over the most-recent n snapshots.
    Returns {} when len(snapshots) < n  (baseline-pending — #1, never a
    fabricated average). profit_factor None (inf-guarded by _safe_float on
    save) is skipped per-metric so the mean is honest."""
```
- `N` priors required = `⟨MARK: N — minimum prior snapshots before an average is shown⟩`.
- Baseline-pending wording when `< N`: `⟨MARK: exact Hebrew baseline-pending string for "vs average" — analogous to report_open_book.DELTA_BASELINE_PENDING; never a number⟩`.

Wiring: in `_run_weekly`/`_run_monthly` after `load_previous`, add `recent = load_recent(period_type, n=⟨MARK:N⟩+1)`; drop the current period if present; `avg = compute_period_average(recent, ⟨MARK:N⟩)`; pass new `period_average=avg` kwarg into `render_weekly`/`render_monthly` and `build_summary_text`. On-demand passes the same READ-ONLY `load_recent` result (it already does a read-only `load_recent("weekly")` at `report_on_demand.py:160` — precedent that read-only history reads are in-scope and non-mutating).

`render_*` gains additive `period_average: Optional[dict] = None` (default None ⇒ byte-identical for existing callers/tests, exactly the Sprint-18 additive-kwarg pattern at `report_renderer.py:39-40`). `_headline_ctx`/a `_comparison_ctx` emits namespaced `cmp_*` keys (`cmp_vs_prev`, `cmp_vs_avg`, `cmp_baseline_pending`, `cmp_avg_n_have`, `cmp_avg_n_need`).

### 2.2 Open book — NEW pure helper over `open_marks` history

Sprint-18 already persists `open_marks` per scheduled run (`report_snapshot_store.save:67-94`: `floating_pnl_disc`, `floating_pnl_algo`, `open_exposure_pct`, `n_disc`, `n_algo`, `per_symbol`, all `_safe_float`-guarded). Add `report_open_book.compute_open_book_history(open_book, snapshots, n) -> dict` — a pure helper that **reuses the stored floats only** (no `get_live_price`, no new PnL/R math; mirrors `compute_mark_delta:419` which is "PURE subtraction of two stored floats"):

- vs previous: current `open_book_totals.floating_pnl_disc/algo` − previous snapshot's `open_marks` (this is essentially `compute_mark_delta:454-459`, reused, not duplicated — `compute_open_book_history` calls `compute_mark_delta` for the prev leg).
- vs average: mean of `open_marks.floating_pnl_disc` / `floating_pnl_algo` / `open_exposure_pct` over the most-recent `⟨MARK:N⟩` snapshots **that contain `open_marks`** (old snapshots without it are skipped — `report_snapshot_store.py` comment `:31-33`).
- **ALGO segregated**: disc and ALGO deltas/averages reported separately, ALGO line carries `ALGO_OBSERVATION_LABEL` (`report_open_book.py:49`) and is never merged into the disc figure — exactly the `compute_mark_delta:463-466` precedent.
- Baseline-pending when fewer than `⟨MARK:N⟩` `open_marks`-bearing snapshots: returns `available=False` + `⟨MARK: open-book vs-average baseline-pending Hebrew (reuse the §4 DELTA_BASELINE_PENDING style)⟩`. Never a fabricated average (#1).

### 2.3 Template + summary surfacing

Metrics tables already have comparison columns: weekly `weekly_report.html.j2:83-128` (`{% if comparison %}` "שינוי מהשבוע הקודם"), monthly `monthly_report.html.j2:90-125` ("חודש קודם" / "שינוי MoM"). Add **one additive column** `⟨MARK: header for the vs-average column, e.g. "מול ממוצע"⟩` rendered only `{% if cmp_vs_avg %}`, populated from `cmp_vs_avg[key]`; when `< N`, the cell shows `cmp_baseline_pending` (text, never a number). Open-book section (`weekly:143-203` / `monthly:175-235`) gains, after the existing `open_book_mark_delta_text` line (`weekly:200-202`), an additive `obcmp_*` line block (disc / ALGO-segregated vs-prev + vs-avg, or the baseline-pending token). `build_summary_text`: append a compact `⟨MARK⟩`-worded comparison line after the realized KPI block (`report_renderer.py:185`) and after the open-book summary (`:193`) — additive, never modifying the realized KPI lines `:171-185`.

---

## 3. System-Health honest mapping + `_period_label` fix

### 3.1 `_build_system_health` bug (cited RCA)

`report_scheduler._build_system_health:170-184` reads `/app/ibkr_last_sync_result.json` (the dict `run_ibkr_sync` writes — keys `status` ∈ {`success`,`temporary`,`fatal`,`rate_limit`} from `ibkr_sync_runner.py:123,136,155,197,204`; `message` is the IBKR-flex Hebrew, e.g. `IBKR_ERROR_CLASSES[1001]` = `"הדוח לא נוצר כרגע — ניסיון מאוחר יותר"` at `ibkr_sync_runner.py:16`) and does:

```python
sync_label = f"✅ Sync {last.get('status','?')} — {last.get('message','')[:60]}"
```

Two faults: (a) hard-coded `✅` regardless of `status` → `✅` shown on `temporary`/`fatal`; (b) echoes the raw flex `message` ("הדוח לא נוצר…") into a delivered Sentinel report where "הדוח" reads as *the Sentinel report*.

### 3.2 Fix — class-driven honest mapping (no `✅` on non-ok; never echo raw flex string)

Map `status` to a label by IBKR class semantics (the `IBKR_ERROR_CLASSES` *class* taxonomy at `ibkr_sync_runner.py:15-33`): `success`→ok; `temporary`/`rate_limit`→temporary; `fatal`→fatal; anything else / file-missing / parse-fail → unknown. Replace `:173-178` with:

```python
status = (last.get("status") or "").lower()
if status == "success":
    sync_label = ⟨MARK: exact Hebrew OK sync line — MAY use ✅; conveys IBKR sync succeeded (Sentinel report itself is fine)⟩
elif status in ("temporary", "rate_limit"):
    sync_label = ⟨MARK: exact Hebrew TEMPORARY line — NO ✅ (use ⚠️ or neutral); states the IBKR *flex sync* is temporarily delayed; MUST NOT contain "הדוח לא נוצר" / imply the Sentinel report failed⟩
elif status == "fatal":
    sync_label = ⟨MARK: exact Hebrew FATAL line — NO ✅ (🔴); IBKR sync auth/config failure; still must not read as the Sentinel report⟩
else:
    sync_label = ⟨MARK: exact Hebrew UNKNOWN line — NO ✅; "מצב סנכרון לא ידוע"-style⟩
```

- The raw flex `message` is **never interpolated verbatim**. If Mark wants a code surfaced, it is `last.get("code")` (an int, unambiguous), not the Hebrew flex sentence.
- File-missing branch (`:177-178`, currently `"⚠️ Sync — אין מידע זמין"`) → `⟨MARK: keep or reword; must remain ✅-free⟩`.
- `risk_monitor_status`/`report_service_status` (`:182-183`) and the `_base_ctx` defaults (`report_renderer.py:291-293`) are **unchanged** — out of scope.

### 3.3 `_period_label` off-by-one — root cause + minimal fix

`_period_label` (`report_renderer.py:422-428`) does `end.day - 1` in both branches. This assumes an **exclusive** `period_end` (half-open `[start, end)`), which matches `_weekly_period` (`report_scheduler.py:157`: end = Saturday 23:59:59 — and analytics uses `< end`, `analytics_engine.py:258`). **But `_monthly_period` produces an INCLUSIVE end**: `report_scheduler.py:165-166` → `last_of_prev = first_of_this - timedelta(seconds=1)` ⇒ April end = `2026-04-30 23:59:59`. `_period_label` then renders `end.day - 1 = 30 - 1 = 29` → **"1–29 באפריל"** (April has 30 days). Root cause: **two callers disagree on the end-bound convention; `_period_label` hard-codes the exclusive `- 1` for both.**

Minimal, lowest-risk fix (presentation-only, no period-math touched): make `_period_label`'s end honest to the inclusive value it is given by detecting the end-of-day inclusive sentinel — the monthly end is the last second of the day (`23:59:59`), the weekly end is also `23:59:59` (`report_scheduler.py:157`). Both are inclusive last-instant-of-day timestamps. So the `- 1` is wrong for **both** when end is a `23:59:59` inclusive bound — weekly currently renders e.g. a Saturday week as `…–{Fri}` (off by one too, masked because nobody reported it). The correct, convention-free fix: **render the end's own calendar day, do not subtract** when `end` is an inclusive timestamp:

```python
def _period_label(start, end):
    _HE_MONTHS = [...]
    # period_end from _weekly_period/_monthly_period is the INCLUSIVE last
    # instant of the final day (23:59:59). Render its own day — the historic
    # `end.day - 1` assumed an exclusive end and produced "1–29 באפריל"
    # (April=30) for the monthly inclusive end (report_scheduler.py:165-166).
    end_day = end.day
    if start.month == end.month and start.year == end.year:
        return f"{start.day}–{end_day} ב{_HE_MONTHS[start.month-1]} {start.year}"
    return (f"{start.day} ב{_HE_MONTHS[start.month-1]} – "
            f"{end_day} ב{_HE_MONTHS[end.month-1]} {end.year}")
```

⟨MARK: confirm the inclusive-end ruling — monthly must read "1–30 באפריל"; confirm the weekly label's intended end day (the historic `-1` also under-counted weekly by one)⟩. **Existing tests** `test_ux_formatting_comprehensive.py:40-75` assert only month-name presence / non-emptiness / year presence — they do **not** pin the day number, so the fix does not break them; the new fixture §4.4 pins "1–30 באפריל". (If Mark rules weekly intentionally wants `end-1`, the fix is gated on the `23:59:59` inclusive sentinel only for the monthly caller — flagged as the fallback.)

---

## 4. Test plan (additive; baseline **1761** green; collected count confirmed `1761 tests`)

New file `tests/test_sprint19_headline_comparison.py` (+ targeted adds to `test_report_scheduler.py`, `test_ux_formatting_comprehensive.py`, `test_open_book.py`, `test_report_open_book_snapshot.py`). All Mark-worded asserts carry a `⟨MARK⟩` placeholder until rulings land.

1. **Realized-byte-identical guard.** (a) `subprocess`/`git diff --exit-code analytics_engine.py` == empty. (b) Build ctx via `render_weekly`/`render_monthly` (mock WeasyPrint→HTML path) WITH and WITHOUT open_book/period_average; assert every `_base_ctx:254-296` key (esp. `win_rate`,`expectancy_r`,`profit_factor`,`total_r_net`,`realized_pnl`,`campaigns_closed`,`verdict`,`verdict_class`) is equal across both; assert `compute_period_analytics` output dict equality with/without the new paths.
2. **Headline-switch wording.** Fixture: `campaigns_closed==0` + `open_book_present==True` (4 opened-in-period, +$72). Assert rendered HTML badge == `headline_badge_text` (⟨MARK⟩) and contains **no** "ללא עסקאות"; realized cards still truthfully show `0`/`$0`/`0.0%` and a `headline_realized_frame` ("0 ממומש"-style ⟨MARK⟩) caption; ALGO symbols absent from the badge/sub-lines (#8). Truly-empty fixture (`open_book_present==False`): legacy `verdict`/`verdict_class` badge path byte-identical (no `headline_open_book_mode`).
3. **Comparison + average + baseline-pending.** (a) `compute_period_average` over `< N` snapshots → `{}`; over `≥ N` → exact arithmetic mean of stored floats (hand-computed fixture); `profit_factor None` skipped. (b) `compute_open_book_history`: prev leg == `compute_mark_delta` value; ALGO line segregated, carries `ALGO_OBSERVATION_LABEL`; `< N` `open_marks` → baseline-pending token, never a number. (c) on-demand with a real prior snapshot in `tmp_path` → comparison populated; **assert no file written** (snapshot dir mtime unchanged) and `report_snapshot_store.save` not called (monkeypatch raises if invoked).
4. **`_period_label` 1–30 fixture.** `_period_label(*sched._monthly_period(datetime(2026,5,1)))` → contains `"1–30 באפריל"`; weekly fixture per ⟨MARK⟩ end-day ruling; assert existing `TestPeriodLabels` (`test_ux_formatting_comprehensive.py:40-75`) still green.
5. **System-Health honesty.** `_build_system_health` with `ibkr_last_sync_result.json` `status="temporary"`/`message="הדוח לא נוצר כרגע — ניסיון מאוחר יותר"` → `sync_status` contains **no** `✅` and **not** the substring `"הדוח לא נוצר"`; `status="success"`→ ⟨MARK⟩ ok line; `status="fatal"`→ no `✅`; missing file → no `✅`. (Extends `test_report_scheduler.py`.)
6. **On-demand no snap_save still asserted.** Re-run the existing Scope-B no-mutation assertion after the §2.1 change (monkeypatch `report_snapshot_store.save` / `report_scheduler._mark_ran` / `_save_state` to fail; `run_on_demand` succeeds).
7. **Regression intact.** Full `pytest -q` == **1761** + new tests, all green. Explicit re-run of Sprint-18 period-scoping (`test_open_book.py`, `test_report_open_book_snapshot.py`), 920be95 (`compute_verdict` `period_word` signature — `test_analytics_engine.py`), bcf32f5 (scheduled comparison KeyError — `test_report_scheduler.py`), Sprint-16 graceful degrade (`test_report_renderer_degraded.py`).

---

## 5. Risk classification & explicit "will NOT change"

| Item | Risk | Note |
|---|---|---|
| §1 headline ctx + template switch | **MEDIUM** | presentation only; additive `headline_*` ctx; realized cards byte-identical by construction + guard |
| §2.1 realized vs-prev on-demand | **LOW** | read-only `load_previous`; reuses existing `compute_period_comparison` |
| §2.1 `compute_period_average` | **LOW** | pure mean of already-stored floats; no R/NAV/campaign math; baseline-pending |
| §2.2 `compute_open_book_history` | **LOW** | reuses stored `open_marks` floats + `compute_mark_delta`; ALGO segregated |
| §2.3 template additive column | **LOW** | one `{% if cmp_vs_avg %}` column; existing columns untouched |
| §3.1 `_build_system_health` mapping | **LOW–MED** | string mapping by existing class taxonomy; no behaviour outside the label |
| §3.3 `_period_label` fix | **LOW** | drop `-1`; presentation only; existing tests don't pin the day |

**Will NOT change:** realized R / NAV / campaign / Expectancy / PF math; `analytics_engine.compute_period_analytics` / `compute_verdict` (920be95 `period_word` signature) / `compute_period_comparison` / #8 seam `:43-58`; `_base_ctx` realized keys; `engine_core` R/NAV functions; `report_open_book.build_open_book`/`compute_mark_delta` Sprint-18 logic; `report_snapshot_store.save` schema / `open_marks` shape; `telegram_bot_secure_runner.py`; `docker-compose.yml`; Supabase schema / migrations (`verify_migrations` stays — no DB, single-user byte-identical, back-compat when history < N → baseline-pending).

**Wave-2 gate:** every `⟨MARK:…⟩` slot above must be filled from `MARK_SPRINT19_RULINGS.md` before any code is written. Engineering invents no label, threshold, N, or Hebrew string.
