# MARK — Sprint 19 Rulings (gates Wave 2)

DEC-20260516-016 made precise. Code-cited. Doc-only; no code; no commit/push.
Builds on DEC-20260516-015 (Sprint-18 open book) + DEC-20260511-001 (ALGO
observer) + DEC-20260515-011/-012 (dual-R) + DEC-20260515-014 (#8 cohort) +
AGENTS.md #1/#8 + CLAUDE.md (accuracy > confidence; realized math frozen).

**Frozen by construction (provable boundary, all four sections):**
`analytics_engine.compute_period_analytics:14` and `compute_verdict:230`
(920be95 period-aware signature) are BYTE-UNTOUCHED. Every Sprint-19 ruling is
**presentation-layer only**: additive `report_renderer` ctx keys + template
conditionals + `report_scheduler._build_system_health` string mapping +
`_period_label` arithmetic. NO realized R/NAV/campaign/Expectancy/#8 math
change. `_base_ctx:247-296` realized keys are read, never rewritten. The
open-book path is the Sprint-18 SEPARATE `open_book`/`open_marks` dict —
it never feeds `compute_period_analytics`. ALGO (`ec.is_algo_position`,
`STAT_BUCKET_ALGO`) is NEVER in the headline and NEVER merged into any
realized or comparison number (#8). Sprint-18 period-scoping
(`report_open_book._classify_period:110`), 920be95, bcf32f5, Sprint-16
graceful degradation must not regress.

---

## 1. Period-honest headline (presentation only)

**Trigger condition (exact):** `analytics.campaigns_closed == 0` AND
`open_book is not None` AND `open_book["open_book_present"] == True` (the
Sprint-18 wired-caller path; legacy `open_book is None` callers keep the
byte-identical 920be95 verdict — no regression).

`compute_verdict:238-239` still returns `("{period} ללא עסקאות","neutral")` —
**this return value MUST NOT change** (920be95 frozen). The fix is that the
template MUST NOT render that string as the dominant page-1 badge in the
trigger condition. Rulings:

**1a. Verdict badge (`templates/*_report.html.j2:22`/`:20`).** When the
trigger holds, the `verdict-badge` element MUST be SUPPRESSED (not rendered)
and REPLACED by a period-honest headline badge. The replacement badge text
(weekly; "חודש" for monthly), RTL:

> `📌 שבוע ללא סגירות — ספר פתוח פעיל`

with badge class `verdict-neutral` (no green/red verdict semantics — it is
neither strong nor defensive; it is "no realized verdict this period").
The literal substring `ללא עסקאות` MUST NOT appear anywhere on page 1 when a
live book spanned the period. The word "סגירות" (closings) is the honest noun
— zero campaigns *closed*, not zero *trading*.

**1b. Promoted open-book period line (new, directly under the badge, page 1,
BEFORE the KPI grid).** A prominent banner (reuse the `freshness-banner`
visual weight, not the small grey empty-state line) with these lines, RTL,
ALGO segregated:

> `✅ 0 קמפיינים נסגרו בתקופה — אין ביצועים *ממומשים* (זה לא "ללא מסחר").`
> `📌 ספר פתוח (לא ממומש): {n_disc} דיסקרציוני · צף ${floating_disc:+,.0f} · חשיפה {exposure_disc:.1f}%`
> `🆕 {n_opened_total} פוזיציות נפתחו בתקופה זו` *(only when `n_opened_total > 0`; else:)* `↳ כולן מוחזקות מתקופה קודמת (פעילות פתוחה לאורך החלון)`
> `📅 חלון: {period_label} · מקור: {Live/Cached/Sync זמני}`

ALGO, if any, on its OWN segregated line below (NEVER summed into the disc
floating/exposure, NEVER in the headline number — #8 / DEC-20260511-001):

> `🟠 ALGO (פיקוח בלבד · לא הוראה): {n_algo} פוז' · צף ${floating_algo:+,.0f} · חשיפה {exposure_algo:.1f}% — מנוהל חיצונית, ללא הוראת Sentinel`

The mark-to-market Δ line is appended ONLY per §2 (baseline-pending token
until a prior `open_marks` exists). Reuse the Sprint-18 strings in
`report_open_book.empty_state_lines:377` / `EMPTY_STATE_*` — extend them, do
not duplicate; the single source of truth stays `report_open_book.py`.

**1c. Realized KPI cards — BYTE-IDENTICAL values, REFRAMED label only.** The
six KPI cards (`weekly:35-70`) keep their EXACT values from `_base_ctx`
(`realized_pnl`, `win_rate`, `campaigns_closed`, `expectancy_r`,
`profit_factor`, `nav`, `dev_score` — unchanged numbers, $0 / 0% / 0.00
when truly zero — never hidden, never altered: #1 truth). The ONLY change:
under the trigger condition, the cards section gets a preceding sub-heading

> `📉 ביצועים ממומשים (0 קמפיינים נסגרו בתקופה)`

and the "רווח ממומש" card label becomes `רווח ממומש (0 בתקופה)`. The grid is
DEMOTED below the §1b banner — it is no longer the first/dominant visual but
it is still fully present and numerically untouched. The realized cards must
remain a faithful "0 ממומש" statement, never spun as positive.

**1d. Truly empty (0 closed AND 0 open, `open_book_present == False`).**
Badge stays the legacy `compute_verdict` "שבוע/חודש ללא עסקאות"
(`verdict-neutral`) — that wording is CORRECT here (genuinely no activity).
Supplement with the Sprint-18 line `EMPTY_STATE_TRULY_EMPTY`
(`✅ 0 קמפיינים נסגרו · אין פוזיציות פתוחות. שבוע ללא פעילות מסחר.`). No §1a
suppression in this case — there is no live book to misrepresent.

**Boundary (provable):** §1 touches ONLY templates + `_open_book_ctx:299`
additive keys + `report_open_book` strings. `compute_verdict` return value,
`verdict_class`, `_base_ctx` realized keys: all byte-identical. ALGO never in
the headline badge or the disc figures.

---

## 2. Period-over-period + vs-average

**2a. Realized — "מול תקופה קודמת".** Reuse `compute_period_comparison:199`
(exists, unchanged) fed by `report_snapshot_store.load_previous:121`. Metrics
that get the WoW/MoM delta column (the set `compute_period_comparison`
already emits): `win_rate`, `expectancy_r`, `profit_factor`, `total_r_net`,
`realized_pnl`, `missing_stop_rate`, `oversized_rate`, `avg_r_per_day`. No
new metric, no new math. ALGO is structurally absent here (realized cohort
already #8-filtered in `compute_period_analytics`) — nothing to segregate,
but the comparison label MUST read `מול תקופה קודמת (ממומש בלבד)` so it is
never read as including the open book.

**2b. Realized — "מול ממוצע".** New presentation-only helper averages the
SAME metric set across `report_snapshot_store.load_recent(period_type, n=N)`
(read-only; pure mean of stored snapshot KPI floats; `profit_factor` infs
already stored as `None` by `_safe_float` → excluded from its mean). It
introduces NO new trading math — only an arithmetic mean of already-computed,
already-stored realized KPIs. Label: `מול ממוצע {k} {שבועות/חודשים}` where
`k` = the actual count averaged (state the real N used, never a rounded
claim).

**2c. Minimum-history N + baseline-pending (#1 — no fabricated average).**
The "מול ממוצע" block is shown ONLY when **N ≥ 3** prior same-type snapshots
with `campaigns_closed`-bearing data exist (3 = the smallest count where a
mean is not dominated by a single period; matches the
`adaptive_risk_engine` ≥3-closed-campaigns precedent in
`report_scheduler._compute_risk_rec:194`). Until then the block renders
EXACTLY (RTL), and nothing else in its place:

> `📊 מול ממוצע: — · ממתין ל-{N} תקופות בסיס (קיימות {k} מתוך {N})`

(`N`=3, `k`=actual available count). A partial average over 1–2 periods is
NEVER computed or shown — that would present a fabricated/unstable mean as
"the average" (#1 violation). Same rule, same token style, for the open-book
average (§2d).

**2d. Open book — period-over-period + vs-average.** Source = the Sprint-18
`open_marks` history in the snapshot store (written by
`report_snapshot_store.save:67-94`, read via `load_previous`/`load_recent`).
Reuse `report_open_book.compute_mark_delta:419` for period-over-period (it is
already the pure prior-vs-current subtraction with the verbatim
baseline-pending token `DELTA_BASELINE_PENDING` until a prior `open_marks`
exists — DO NOT change it). For "מול ממוצע" of the open book: a parallel
presentation-only mean of `open_marks.floating_pnl_disc` and
`open_marks.open_exposure_pct` across `load_recent`, **ALGO segregated**
(`floating_pnl_algo` averaged on its OWN line, never folded into the disc
mean — #8 / DEC-20260511-001), gated by the SAME N≥3 rule and SAME
baseline-pending token as §2c. Open-book comparison/average is ALWAYS
labelled "(לא ממומש)" and rendered in the open-book section, NEVER in the
realized comparison table — the two are never visually merged.

**2e. ALGO in every comparison.** ALGO is NEVER merged into any realized or
discretionary comparison/average number. Where ALGO history exists, its
delta/average appears only on its own segregated, observation-only line with
the `פיקוח בלבד · לא הוראה` label (DEC-20260511-001). ALGO never enters the
headline (§1) comparison.

**2f. On-demand READ-ONLY (Scope-B invariant).** `report_on_demand.py`
(file:15 invariant) still performs NO `snap_save` and NO scheduler-state
mutation. It MAY now READ existing history and render comparison/average
READ-ONLY (`load_previous`/`load_recent` are pure reads — already used at
`report_on_demand.py:159` for the weekly breakdown). When on-demand finds
< N history it shows the §2c baseline-pending token (honest, identical to
the scheduled path). On-demand MUST NOT write the snapshot it just read.

---

## 3. System-Health honest mapping

**RCA confirmed.** `ibkr_sync_runner.py:16`
`IBKR_ERROR_CLASSES[1001]=("temporary","הדוח לא נוצר כרגע — ניסיון מאוחר יותר")`
is the IBKR **flex-query** status string. `report_scheduler._build_system_health:176`
does `sync_label = f"✅ Sync {status} — {message[:60]}"` — blindly prefixing
`✅` and echoing the raw flex `message`, producing
`✅ Sync temporary — הדוח לא נוצר כרגע …` inside a *delivered* Sentinel
report. Two faults: (a) `✅` on a non-ok state; (b) "הדוח" reads as the
Sentinel report ("the report was not created") — actively false (#1).

**3a. Ruling — map by STATUS, never echo the raw flex message.**
`_build_system_health` MUST switch on the `status` field of
`/app/ibkr_last_sync_result.json` and emit a Sentinel-authored Hebrew label.
The raw IBKR-flex `message` MUST NOT be concatenated into `sync_status`.
Exact mappings (RTL):

| status | sync_status (exact) |
|---|---|
| `ok` / `success` | `✅ סנכרון IBKR תקין` |
| `temporary` / `rate_limit` | `⏳ סנכרון IBKR — עיכוב זמני בצד IBKR (לא משפיע על דוח זה)` |
| `fatal` | `🔴 סנכרון IBKR — תקלה, נדרשת בדיקה (NAV עלול להיות לא עדכני)` |
| file missing / parse-fail / status absent/unrecognised | `⚠️ סנכרון IBKR — מצב לא ידוע` |

No `✅` on `temporary`/`rate_limit`/`fatal`/unknown. The string `הדוח לא נוצר`
(and any verbatim `IBKR_ERROR_CLASSES` message) MUST NEVER appear in
`sync_status` — the `temporary` line explicitly states "in IBKR's side · does
not affect this report" so it can never be read as the Sentinel report
failing. Optional: append the *NAV freshness* (already honest via
`account_state` / `nav_freshness_label`) — but never the flex message.

**3b. `_period_label` off-by-one (`report_renderer.py:422-428`).** Bug
confirmed: `_monthly_period` (`report_scheduler.py:162-167`) returns
`period_end = last_of_prev` = the **inclusive** last instant (April →
`2026-04-30 23:59:59`). `_period_label:426` computes `end.day - 1` → renders
`1–29 באפריל`. The `- 1` is wrong because `period_end` is ALREADY the
inclusive last day, not an exclusive boundary. **Ruling:** the inclusive end
day MUST be `period_end.day` (no `- 1`) for the monthly path, so April reads
`1–30 באפריל`, not `1–29`. Implementation must not break the weekly label:
weekly `_weekly_period` also returns an inclusive `period_end` (Saturday
`23:59:59`), so the SAME fix (drop the `- 1`, use the inclusive end day) is
correct for both branches — verify with a focused test for each (weekly
Sun–Sat span; monthly 1–30/1–31/1–28/29 leap). Provable boundary:
arithmetic-only, no period *definition* change in `_weekly_period`/
`_monthly_period`.

---

## 4. Pass/fail checklist (12)

1. **Realized byte-identical guard:** `compute_period_analytics` +
   `compute_verdict` git-diff EMPTY; `_base_ctx` realized keys
   byte-identical with vs without §1/§2 (regression test, both paths).
2. **#1 honesty — headline:** when `campaigns_closed==0` AND a live book
   spanned the period, the substring `ללא עסקאות` does NOT appear on page 1;
   the §1a honest badge + §1b promoted open-book line ARE present.
3. **Realized cards present & true:** the six KPI cards still render the
   exact $0 / 0% / 0.00 realized values (never hidden/spun), reframed as
   `ממומש (0 בתקופה)` and demoted below the §1b banner.
4. **Truly-empty (§1d):** 0 closed AND 0 open → legacy
   `compute_verdict` wording stays + `EMPTY_STATE_TRULY_EMPTY`; no §1a
   suppression, no fabricated open-book line.
5. **Period-over-period:** realized WoW/MoM via unchanged
   `compute_period_comparison`+`load_previous`, labelled `(ממומש בלבד)`.
6. **vs-average gating (#1):** "מול ממוצע" shown ONLY at N≥3 real
   same-type snapshots; with 0–2 it shows EXACTLY the baseline-pending
   token (`ממתין ל-3 תקופות בסיס (קיימות k מתוך 3)`) — never a partial mean.
7. **Open-book comparison:** uses Sprint-18 `open_marks` +
   unchanged `compute_mark_delta` token until a prior mark; open-book
   average gated by the same N≥3 token; always labelled `(לא ממומש)`,
   never in the realized table.
8. **ALGO segregation (#8/DEC-011):** ALGO never in headline, never in any
   realized/discretionary comparison or average — only on its own
   `פיקוח בלבד · לא הוראה` observation line.
9. **System-Health no `✅` on temporary:** `sync_status` never starts `✅`
   for `temporary`/`rate_limit`/`fatal`/unknown; status-mapped per §3a.
10. **No raw flex string:** `הדוח לא נוצר` (and any verbatim
    `IBKR_ERROR_CLASSES` message) NEVER appears in a delivered report.
11. **`_period_label` inclusive end:** monthly April renders `1–30 באפריל`
    (not `1–29`); weekly span unaffected — focused tests for both;
    `_weekly_period`/`_monthly_period` definitions unchanged.
12. **Invariants intact:** on-demand still NO `snap_save` / no scheduler
    state mutation (comparison/average READ-ONLY); 920be95 + bcf32f5 +
    Sprint-16 graceful + Sprint-18 period-scoping all green; full suite
    (baseline 1761) passes.
