# Sprint-20 Step-2 — DESIGN: Honest disclosure of the CLOSED-but-excluded realized leg

**Date:** 2026-05-16 · **Branch:** `claude/review-system-audit-FBZ2h`
**Team:** Architecture + Engine · **Status:** design only — NO production code, NO commit/push.
**Gates:** DEC-20260516-017 (+UPDATE), DEC-20260516-016, DEC-20260516-015,
DEC-20260515-014, DEC-20260511-001 · AGENTS.md #1/#8 · CLAUDE.md (no
campaign/R/NAV math; no wholesale rewrite; accuracy > confidence).
**Mark Sprint-20 rulings:** `docs/teams/MARK_SPRINT20_RULINGS.md` is **ABSENT**
this session. Every label / threshold / wording below is a verbatim
`⟨MARK:…⟩` placeholder — **invent none**; Wave-2 build is BLOCKED on Mark
filling each `⟨MARK⟩` slot. Where a Sprint-18/19 precedent string already
exists and is reused unchanged, it is cited as such and still `⟨MARK⟩`-confirmed.

---

## 0. Confirmed root cause (RCA gate PASSED — recap, code-cited)

Period closes are real, campaign-linked, in-data, but lack `initial_stop`:

- `analytics_engine._get_closed_campaigns:255-262` picks them up (campaign_id
  present, in-window SELL).
- `_aggregate_campaigns:265-304` → `ec.get_campaign_risk_metrics` →
  `true_orig_risk = 0.0` (:285) → `stat_bucket =
  ec.classify_stat_bucket(setup, 0.0)` (:292) → `STAT_BUCKET_DATA_INCOMPLETE`
  (`engine_core.py:1257-1258`).
- `is_stat_countable` False (`engine_core.py:1263`) → row NOT in `countable`
  (`analytics_engine.py:53`) → `campaigns_closed = len(countable) = 0`
  (`analytics_engine.py:89` weekly, `:129` return).
- They DO populate `excluded = campaigns[~bucket.apply(ec.is_stat_countable)]`
  (`:55`), `excluded_count` (`:57`), `excluded_pnl = excluded["net_pnl"].sum()`
  (`:58`), surfaced in BOTH return dicts (`:84-85`, `:144-145`) and the
  early-empty path (`_empty():318` sets them 0).
- **`excluded_count`/`excluded_pnl` are rendered NOWHERE**: confirmed absent
  from `report_renderer.py` (`_base_ctx:427-476` has no `excluded_*` key;
  `build_summary_text:239-355` never reads them) and from BOTH
  `templates/weekly_report.html.j2` / `monthly_report.html.j2` (grep clean).

⇒ Pure **#1 disclosure/honesty defect**, NOT a campaign-math bug. Excluding
no-stop campaigns from edge stats (WR/Exp/PF/Net-R) is methodologically
CORRECT (#8 — no R without a stop). The fix is to stop being SILENT.

**Risk classification: LOW–MEDIUM.** Presentation-layer only; additive ctx +
template + one summary line; ZERO change to the analytics number path. Medium
only because it touches the report seam the founder smoke-tests and because
the manual/ALGO split (§2) adds a derived analytics key (additive, partition
of an already-aggregated total — no new R/NAV/campaign/Expectancy math).
Affected services: `reporting-service` (`report_scheduler.py`),
on-demand path (`report_on_demand.py`) — read-only, no `snap_save` impact.

---

## 1. Disclosure block — additive `excluded_*` ctx → new weekly+monthly section + summary line

### 1.1 Data already exists — zero analytics-number change

`compute_period_analytics` already returns `excluded_count` (int) and
`excluded_pnl` (float) in **all three** return shapes
(`analytics_engine.py:84-85`, `:144-145`, `_empty():318`). Step-2 reads these
existing keys; it does **not** alter `_get_closed_campaigns`,
`_aggregate_campaigns`, the `bucket`/`countable`/`manual`/`excluded` split
(`:52-58`), `campaigns_closed`, or any KPI. **`compute_period_analytics:14`
and `compute_verdict:230` git-diff EMPTY** (guard, §4).

### 1.2 Additive renderer ctx (new `_excluded_ctx` seam — mirrors Sprint-19 `_headline_ctx`/`_comparison_ctx`)

New pure helper `report_renderer._excluded_ctx(analytics: dict) -> dict`,
called additively in `render_weekly` (after `_comparison_ctx`, ~line 179) and
`render_monthly` (~line 233). It returns ONLY `excl_*`-namespaced keys; it
NEVER reads or writes a `_base_ctx` realized key (proof by construction —
identical seam discipline as `_headline_ctx:534`/`_comparison_ctx:615`).

Gate: the whole block is shown **iff** `excluded_count > 0`.

```
def _excluded_ctx(analytics: dict) -> dict:
    n   = int(analytics.get("excluded_count", 0) or 0)
    pnl = float(analytics.get("excluded_pnl", 0.0) or 0.0)
    # §2 additive split (Mark-gated) — partition of the SAME excluded_pnl:
    n_manual   = int(analytics.get("excluded_count_manual", 0) or 0)
    pnl_manual = float(analytics.get("excluded_pnl_manual", 0.0) or 0.0)
    n_algo     = int(analytics.get("excluded_count_algo", 0) or 0)
    pnl_algo   = float(analytics.get("excluded_pnl_algo", 0.0) or 0.0)
    return {
        "excl_present":      n > 0,
        "excl_count":        n,
        "excl_pnl":          pnl,
        "excl_count_manual": n_manual,
        "excl_pnl_manual":   pnl_manual,
        "excl_count_algo":   n_algo,
        "excl_pnl_algo":     pnl_algo,
        "excl_heading":      ⟨MARK: section heading he/RTL —
                              e.g. "📕 קמפיינים שנסגרו אך הוחרגו מסטטיסטיקת edge"⟩,
        "excl_caveat":       ⟨MARK: one-line caveat —
                              e.g. "רווח/הפסד ממומש לא-מאומת · חסר initial stop ·
                              לא נספר ב-WR/Expectancy/PF/Net-R"⟩,
        "excl_action_hint":  ⟨MARK: founder data-completion hint —
                              e.g. "השלם entry/stop כדי להיכלל בסטטיסטיקה"⟩,
    }
```

`render_weekly`/`render_monthly` signatures are **UNCHANGED** (the helper
reads the existing `analytics` arg) ⇒ all existing callers
(`report_scheduler.py:287/394`, `report_on_demand.py:149/184`) are
byte-identical with NO call-site edit; the new section only appears when
`excluded_count > 0`, which is already true exactly in the founder's scenario.

### 1.3 New template section — REALIZED-but-unverified, DISTINCT from Sprint-18/19

A new `{% if excl_present %}` section in BOTH `weekly_report.html.j2` and
`monthly_report.html.j2`, placed **on the realized side** — directly AFTER the
"🏆 עסקאות קיצוניות" block and BEFORE the Sprint-18 `{% if open_book_present %}`
open-book section (weekly `:170-176`, monthly `:215-216`). Placement rationale
(reconciliation §3): it is a CLOSED/REALIZED leg, so it sits with realized
content, visually separated from the Sprint-18 UNREALISED open book (which
keeps its own heading) and never inside the Sprint-19 §1 headline banner.

```
{# Sprint-20 Step-2 — CLOSED but excluded from edge stats (DATA_INCOMPLETE /
   ALGO). Realized but UNVERIFIED (no initial stop). NEVER in WR/Exp/PF/Net-R
   (#8 correct). DISTINCT from the Sprint-18 unrealized open book and the
   Sprint-19 headline. Shown iff excluded_count > 0. #}
{% if excl_present %}
<h3>{{ excl_heading }}</h3>
<p style="font-size:9pt; color:#374151;">{{ excl_caveat }}</p>
<table class="metrics-table no-break">
  <tr><th>שכבה</th><th>קמפיינים</th><th>רווח/הפסד ממומש (לא-מאומת)</th></tr>
  {% if excl_count_manual > 0 %}
  <tr>
    <td>{{ ⟨MARK: manual-row label — e.g. "ידני · חסר stop (DATA_INCOMPLETE)"⟩ }}</td>
    <td class="num">{{ excl_count_manual }}</td>
    <td class="num {{ 'good' if excl_pnl_manual >= 0 else 'bad' }}">
      <span class="ltr">{{ "{:+,.0f}".format(excl_pnl_manual) }}$</span></td>
  </tr>
  {% endif %}
  {% if excl_count_algo > 0 %}
  <tr>
    <td>{{ ⟨MARK: ALGO-row label — e.g. "🟠 ALGO · פיקוח בלבד · לא הוראה"⟩ }}</td>
    <td class="num">{{ excl_count_algo }}</td>
    <td class="num {{ 'good' if excl_pnl_algo >= 0 else 'bad' }}">
      <span class="ltr">{{ "{:+,.0f}".format(excl_pnl_algo) }}$</span></td>
  </tr>
  {% endif %}
  <tr>
    <td><strong>{{ ⟨MARK: total-row label — e.g. "סה\"כ מוחרג"⟩ }}</strong></td>
    <td class="num"><strong>{{ excl_count }}</strong></td>
    <td class="num {{ 'good' if excl_pnl >= 0 else 'bad' }}">
      <strong><span class="ltr">{{ "{:+,.0f}".format(excl_pnl) }}$</span></strong></td>
  </tr>
</table>
<p style="font-size:8.5pt; color:#9ca3af;">{{ excl_action_hint }}</p>
{% if excl_count_algo > 0 %}
<p class="caveat" style="font-size:8.5pt; color:#9ca3af;">
  {{ ⟨MARK: ALGO observation-only caveat — reuse
     report_open_book.ALGO_EXTERNAL_CAVEAT "מנוהל חיצונית — פיקוח, ללא הוראת
     Sentinel"⟩ }}</p>
{% endif %}
{% endif %}
```

The realized KPI cards / metrics-table / `best_trade`/`worst_trade` /
`compute_verdict` badge are **untouched** — the new section is purely
appended; the existing realized values render byte-identical (§4 guard).

### 1.4 New `build_summary_text` line (Telegram pre-PDF)

Add ONE additive block to `build_summary_text` (`report_renderer.py:239-355`),
gated `analytics.get("excluded_count", 0) > 0`, mirroring the Sprint-18
open-book append (`:339-350`) and the `bot_health.py:142-149` honest tone:

- In the **Case-A 0-closed-with-book** path (`:283-302`): append AFTER
  `rob.empty_state_lines` and the ob-cmp lines, BEFORE the heat thermometer.
- In the **normal** path (`:304-355`): append AFTER the realized KPI block
  and the §2a/§2b vs-average lines, BEFORE the Sprint-18 open-book append —
  so realized · excluded · unrealized read in that order.

Lines (RTL, `⟨MARK⟩`-verbatim):

```
⟨MARK: line 1 — e.g. "📕 {n} קמפיינים נסגרו בתקופה אך הוחרגו מ-edge (חסר stop)"⟩
⟨MARK: line 2 — e.g. "↳ רווח/הפסד ממומש *לא-מאומת*: ${pnl:+,.0f} — לא ב-WR/Exp/PF"⟩
⟨MARK: line 3 manual — only if excl_count_manual>0 — e.g.
       "· ידני (חסר stop): {n_manual} · ${pnl_manual:+,.0f}"⟩
⟨MARK: line 4 ALGO — only if excl_count_algo>0 — e.g.
       "🟠 ALGO (פיקוח בלבד · לא הוראה): {n_algo} · ${pnl_algo:+,.0f}"⟩
⟨MARK: line 5 — e.g. "השלם entry/stop כדי להיכלל" (founder data-completion)⟩
```

The string `⟨MARK⟩` MUST contain a "לא-מאומת" token (DEC-20260516-017 UPDATE
§1: *labeled "לא-מאומת / חסר stop", never as exact edge truth*). It MUST NOT
say "ללא עסקאות". `build_summary_text` signature unchanged (reads existing
`analytics`); legacy callers byte-identical (block only fires when
`excluded_count > 0`).

### 1.5 Additive-only proof (realized byte-identical by construction)

- `_excluded_ctx` returns only `excl_*` keys; `ctx.update(_excluded_ctx(...))`
  cannot overwrite a `_base_ctx`/`_headline_ctx`/`_comparison_ctx`/
  `_open_book_ctx` key (disjoint namespace — guard test asserts key-set
  disjointness AND `_base_ctx` dict identical with/without the call).
- Template section is additive markup under a NEW `{% if excl_present %}`
  block; no existing element edited (no realized card / verdict / metrics-row
  touched).
- `build_summary_text` block is appended; existing lines are not modified
  (same discipline as Sprint-18 `:339`).

---

## 2. Manual vs ALGO split (Mark-gated) — minimal additive partition of the SAME `excluded_pnl`

`excluded_pnl` currently SUMS DATA_INCOMPLETE + ALGO
(`analytics_engine.py:58`, `excluded = campaigns[~bucket.apply(
ec.is_stat_countable)]` → both `STAT_BUCKET_DATA_INCOMPLETE` and
`STAT_BUCKET_ALGO`, since `is_stat_countable:1263` is False for both).
DEC-20260516-017 UPDATE §2 + DEC-20260511-001 require ALGO disclosed on its
OWN observation-only line, never merged. `⟨MARK⟩` rules whether the split is
required; if yes, the MINIMAL additive computation:

The `bucket` series already exists at `analytics_engine.py:52`
(`bucket = campaigns["stat_bucket"]`) and `excluded` at `:55`. Add — **only
inside the existing `excluded`-already-computed region (:55-58) and the two
return dicts** — a pure partition of the already-aggregated `net_pnl`:

```
# directly after analytics_engine.py:58, ADDITIVE — no countable/manual/
# excluded semantics changed; no R/NAV/campaign/Expectancy math; pure
# partition of the SAME excluded["net_pnl"] already summed above.
excl_algo   = excluded[excluded["stat_bucket"] == ec.STAT_BUCKET_ALGO]
excl_manual = excluded[excluded["stat_bucket"] != ec.STAT_BUCKET_ALGO]
excluded_count_algo   = int(len(excl_algo))
excluded_pnl_algo     = float(excl_algo["net_pnl"].sum())   if not excl_algo.empty   else 0.0
excluded_count_manual = int(len(excl_manual))
excluded_pnl_manual   = float(excl_manual["net_pnl"].sum()) if not excl_manual.empty else 0.0
# invariant (guard, §4): manual + algo == existing excluded_count / excluded_pnl
```

These four ADDITIVE keys are added to **all three** return shapes (the
`countable.empty` early return `:81-85`, the main return `:144-145`, and
`_empty()` `:318` → all four = 0). HARD: `excluded_count`/`excluded_pnl`
existing keys/semantics are UNCHANGED; `countable`/`manual`/`win_rate`/
`expectancy`/`profit_factor`/`total_r`/`real_pnl` UNCHANGED;
`is_stat_countable`/`classify_stat_bucket`/`STAT_BUCKET_*` engine_core
UNTOUCHED. ALGO partition uses the canonical `ec.STAT_BUCKET_ALGO` constant
(set by `classify_stat_bucket:1251-1252` via `is_algo_position`), so a
symbol-fallback ALGO is correctly segregated and NEVER counted as manual (#8).

ALGO appears ONLY on its own observation-only line/row (§1.3 ALGO row + §1.4
line 4 + the ALGO caveat) — never folded into the manual figure, never in the
headline, never in WR/Exp/PF (DEC-20260511-001 / #8).

`⟨MARK⟩` decisions required: (a) split required or single-line acceptable?
(b) exact manual-row / ALGO-row / total-row labels; (c) the "לא-מאומת"
phrasing; (d) ALGO caveat string (reuse `report_open_book.ALGO_EXTERNAL_CAVEAT`?).

---

## 3. Reconciliation — three legs coexist, NO double-count

| Leg | Source | Realized? | Section | #8 |
|---|---|---|---|---|
| **Countable closed** (linked + has stop) | `analytics_engine` `countable` (`:53`) | realized, verified | existing KPI cards + metrics table + verdict | in WR/Exp/PF/Net-R |
| **Closed-but-excluded** (Sprint-20 — DATA_INCOMPLETE / ALGO) | `excluded_count`/`excluded_pnl` (`:57-58`) split §2 | realized, **UNVERIFIED** | NEW §1.3 section (realized side, before open book) | NEVER in WR/Exp/PF/Net-R |
| **Open book** (Sprint-18) | `report_open_book.build_open_book` (`engine_core.get_open_positions_campaign`) | UNREALISED | `{% if open_book_present %}` (own heading) | ALGO segregated, observation-only |
| **Opened-in-period / headline** (Sprint-18/19) | `_classify_period` + `_headline_ctx` | unrealised framing | Sprint-19 §1 banner | ALGO own line |

**No double-count, by construction:**

- Countable vs excluded is a **partition of the SAME `campaigns` frame** by
  `is_stat_countable` (`analytics_engine.py:53` vs `:55`) — `countable ∩
  excluded = ∅`. A closed campaign is in exactly one. The Sprint-20 section
  reports ONLY the `excluded` side; the existing KPI cards report ONLY
  `countable`. Disjoint.
- Realized (closed: countable + excluded) vs Open book (unrealised) are
  disjoint data **sources**: `analytics_engine._get_closed_campaigns`
  requires an in-window SELL; `get_open_positions_campaign` keeps only
  `net_qty > 0` (engine_core.py:483) → a campaign cannot be both a closed
  realized row and an open-book row at the same instant. (A genuine
  partial-exit double-surface is RCA failure (c) — explicitly OUT of
  Sprint-20 Step-2 scope; deferred to the gated union build / Mark Q1.)
- ALGO is reported on its OWN row in the excluded section (§2) AND its OWN
  line in the open book (Sprint-18) — different legs (realized-excluded vs
  unrealised), never summed together, never in any headline/edge figure.
- Founder's union framing satisfied: closed-but-excluded (realized leg now
  visible) + Sprint-18 open book (unrealised) + Sprint-19 opened-in-period
  all surface honestly, each in its own clearly-labelled section.

`⟨MARK⟩` wording slots: section heading; "לא-מאומת" caveat; row labels;
action hint; ALGO caveat; summary lines 1-5 (all §1.3/§1.4).

---

## 4. Test plan (additions; baseline **1793** must stay green + new tests)

**A. Realized byte-identical guard (the load-bearing test).**
1. `git diff` of `analytics_engine.compute_period_analytics:14` and
   `compute_verdict:230` is EMPTY (the §2 split is the ONLY analytics edit and
   it is purely additive new keys — assert the countable dict subset
   {`campaigns_closed`,`win_rate`,`expectancy_r`,`profit_factor`,`avg_win_r`,
   `avg_loss_r`,`total_r_net`,`realized_pnl`,`best_trade`,`worst_trade`,
   `setup_breakdown`,`missing_stop_rate`,`oversized_rate`,`avg_r_per_day`,
   `excluded_count`,`excluded_pnl`} is **byte-identical** before/after the
   §2 patch on a fixture with mixed countable + DATA_INCOMPLETE + ALGO).
2. `_base_ctx` realized keys identical with vs without `_excluded_ctx`
   (assert `_excluded_ctx` returns only `excl_*` keys; key-set disjoint from
   `_base_ctx`/`_headline_ctx`/`_comparison_ctx`/`_open_book_ctx`).
3. `compute_verdict` / `verdict_class` unchanged in every scenario.

**B. Disclosure appears iff `excluded_count > 0`, correct $.**
- `excluded_count == 0` ⇒ `excl_present` False, no section, summary line
  absent, render byte-identical to pre-Sprint-20.
- `excluded_count > 0` (the founder fixture: closed no-stop campaigns,
  `campaigns_closed == 0`) ⇒ section present; rendered `excl_pnl` equals
  `analytics["excluded_pnl"]` to the cent; summary line present.

**C. Manual-vs-ALGO split correctness + ALGO-never-in-countable (#8).**
- Fixture: 1 countable manual win + 1 DATA_INCOMPLETE close ($X) + 1 ALGO
  close ($Y). Assert `excluded_count == 2`, `excluded_pnl == X+Y` (existing
  semantics unchanged — reuses existing
  `test_excluded_pnl_reported`/`test_all_excluded_returns_empty_with_disclosure`
  fixtures, tests/test_analytics_engine.py:326-355), AND new
  `excluded_count_manual == 1`, `excluded_pnl_manual == X`,
  `excluded_count_algo == 1`, `excluded_pnl_algo == Y`, AND invariant
  `manual + algo == excluded` total. Assert `win_rate == 1.0`,
  `campaigns_closed == 1` (ALGO + DATA_INCOMPLETE NEVER in countable — #8).
- ALGO partition via `ec.STAT_BUCKET_ALGO` symbol-fallback case (unknown
  setup, ALGO symbol) lands in `excluded_*_algo`, not `_manual`.

**D. #1 wording.** Rendered HTML + summary text contain the `⟨MARK⟩`
"לא-מאומת" token and the action hint; do NOT contain "ללא עסקאות"; ALGO row
carries the observation-only caveat.

**E. On-demand no `snap_save`.** `report_on_demand` path renders the section
read-only; assert no `report_snapshot_store.save` call (Scope-B invariant,
DEC-20260516-016 §2f / MARK_SPRINT19 §2f).

**F. No-regression (full suite, baseline 1793 + new ~8-12 tests):**
Sprint-18 period-scoping (`_classify_period`); Sprint-19 §1 headline / §2
comparison & vs-average / §3 System-Health; `compute_verdict` 920be95
period-aware signature; bcf32f5; Sprint-16 graceful WeasyPrint degradation;
`_period_label` inclusive-end. All green.

### Risk classification & explicit "will NOT change"

**Risk: LOW–MEDIUM** (presentation + one additive analytics partition; no
number recomputed). **Will NOT change:** campaign / R / NAV / Expectancy /
Win-Rate / Profit-Factor / Net-R math; `compute_verdict` (920be95 frozen);
`analytics_engine` #8 seam (`countable`/`manual`/`is_stat_countable`),
`excluded_count` / `excluded_pnl` existing semantics (only ADDITIVE
`excluded_*_manual`/`excluded_*_algo` keys); `classify_stat_bucket` /
`STAT_BUCKET_*` (`engine_core.py:1238-1263`); `get_open_positions_campaign`;
`render_weekly`/`render_monthly`/`build_summary_text` signatures;
`telegram_bot_secure_runner.py`; `docker-compose.yml`; Supabase schema (NO
migration — `excluded_*` are runtime-derived, never stored). Realized KPIs
byte-identical (guard A) — proof by construction (disjoint namespace +
additive markup) AND test.

**Rollback:** revert the additive `_excluded_ctx` + the two `{% if
excl_present %}` template blocks + the `build_summary_text` block + the four
additive `analytics_engine` keys. No data/migration/state to undo (read-only,
no `snap_save`).

---

**Build BLOCKED until Mark fills every `⟨MARK⟩` slot** (heading, "לא-מאומת"
caveat, manual/ALGO/total row labels, action hint, ALGO caveat, summary
lines 1-5, and the §2 split-required ruling). No code, no commit/push this
session.
