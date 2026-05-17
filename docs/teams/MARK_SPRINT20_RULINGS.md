# MARK — Sprint-20 Step-2 Rulings: Closed-but-Excluded (no-stop) Realized Leg

**Date:** 2026-05-16 · Branch `claude/review-system-audit-FBZ2h` · Mark, methodology owner & build gate.
**Authority:** DEC-20260516-017 + its UPDATE (RCA gate PASSED, root cause data-confirmed via `🏥 בריאות מערכת`). Founder result: `Campaign IDs כולם מלאים` (null-linkage RULED OUT), `Supabase last trade 2026-05-15` (not a sync gap), `52 רשומות סגורות/ארכיון ללא סטופ (HOOD,HP,JPM,MSGE,PLTR) — אינו נספר`.

**Confirmed defect class:** #1 SILENT-DISCLOSURE defect, NOT a campaign-math bug. Trace: real, linked, in-window closes lack `initial_stop` → `classify_stat_bucket(setup, orig_risk=0)` → `STAT_BUCKET_DATA_INCOMPLETE` (`engine_core.py:1257-1258`) → `is_stat_countable`→False (`engine_core.py:1263`) → not in `countable` → `campaigns_closed=len(countable)=0` (`analytics_engine.py:53,89,129`). They DO populate `excluded_count`/`excluded_pnl` (`analytics_engine.py:55,57-58,84-85,144-145`) — **computed but rendered NOWHERE** (absent from `report_renderer.py` `_base_ctx:427-476` + `build_summary_text:239-355` + both `.j2` — verified). Excluding no-stop campaigns from edge stats is methodologically CORRECT (#8 — no R without a stop; DEC-20260515-014). The defect is the silent omission.

---

## §1 — RULING: Exact honest disclosure (Hebrew, RTL, #1)

When `analytics["excluded_count"] > 0` for the in-period set, the weekly/monthly PDF AND the Telegram summary (`build_summary_text`) MUST render a **DISTINCT disclosure block**, visually and semantically separate from the realized KPI block. Mandatory line (manual-incomplete leg):

> `ℹ️ {n} קמפיינים נסגרו בתקופה אך הוחרגו מסטטיסטיקת ה-edge (חסר stop) — רווח/הפסד ממומש לא-מאומת: ${x:+,.0f}. השלם entry/stop כדי להיכלל.`

Hard rules (gate-blocking):

1. **NEVER summed.** `excluded_pnl` is NEVER added into `realized_pnl`, `total_r_net`, `win_rate`, `expectancy_r`, or `profit_factor`. Those are computed from `countable` ONLY (`analytics_engine.py:87-146`) and MUST stay byte-identical (guard test asserts the `_base_ctx:451-464` realized keys are untouched when `excluded_count>0`).
2. **`לא-מאומת` is mandatory wording** (#1 — never present incomplete data as exact edge truth). The word `לא-מאומת` (or `ממומש לא-מאומת`) MUST appear; `$X` is shown as raw realized PnL of the excluded leg with NO R/WR/PF attached to it (no edge math exists for a no-stop campaign).
3. **Sprint-19 reconciliation — NO contradiction.** The existing `_HEADLINE_REALIZED_PNL_LABEL = "רווח ממומש (0 בתקופה)"` (`report_renderer.py:48`) and `"0 קמפיינים נסגרו"` empty-state stay byte-identical — they correctly mean *countable=0*. The new block sits BELOW/BESIDE them and reads as "countable 0; **בנוסף** N נסגרו והוחרגו (חסר stop)". Both true, no overwrite, no merge. The verdict badge / KPI cards are NOT changed (Sprint-19 / `compute_verdict` 920be95 / `analytics_engine.py:230` untouched).
4. **Block, not a KPI card.** It is an `ℹ️`/disclosure block (PDF: a separate `<div class="disclosure">` after the realized KPI section; Telegram: appended after the realized KPI lines `report_renderer.py:318`, before/independent of the open-book append at `:339`). It is NEVER styled as, adjacent-merged with, or summed into a KPI card.

---

## §2 — RULING: ALGO segregation (#8 / DEC-20260515-014 / DEC-20260511-001)

`excluded` (`analytics_engine.py:55`) mixes TWO buckets: `STAT_BUCKET_DATA_INCOMPLETE` (manual, missing stop — `engine_core.py:1258`) AND `STAT_BUCKET_ALGO` (externally managed — `engine_core.py:1252`). RULING:

1. **`excluded_pnl` MUST be split manual-vs-ALGO — a split IS required for honest disclosure.** A single merged `excluded_pnl` would conflate an actionable data-completion gap with an observation-only external system, violating #8 and DEC-20260511-001 (ALGO never instructed, never an actionable line). Step-2 derives, from the SAME already-computed `excluded` frame (zero new math — partition by `ec.is_algo_position` / `stat_bucket == ec.STAT_BUCKET_ALGO`, the predicate already used at `analytics_engine.py:54`): `excluded_manual_count/_pnl` and `excluded_algo_count/_pnl`. This is a read-only partition of an existing sum, NOT new R/NAV/campaign math (CLAUDE.md fragile-area clearance granted).
2. **SEPARATE lines, never merged.** Manual-incomplete line per §1 (actionable: `השלם entry/stop`). ALGO line is OBSERVATION-ONLY, matching `report_open_book.py:49` tone:

> `🔭 {n} קמפייני ALGO נסגרו בתקופה — מנוהל חיצונית, פיקוח בלבד · לא הוראה. ממומש לא-מאומת: ${x:+,.0f} (לא נספר ב-edge).`

3. **ALGO line carries NO instruction, NO `השלם`, NEVER in headline/verdict/edge.** Maximum status is observational (DEC-20260511-001 — never `Action Required`, never management). If `excluded_algo_count == 0` the ALGO line is omitted entirely (no empty ALGO noise). If `excluded_manual_count == 0` the manual line is omitted. They are independent.

---

## §3 — RULING: Union reconciliation (Sprint-18 ∪ Sprint-19 ∪ Step-2)

The founder's "opened ∪ closed ∪ open" basis is satisfied by THREE strictly separated legs — NEVER added into one number:

| Leg | Nature | Source | Sprint |
|-----|--------|--------|--------|
| Countable closed | realized, edge-eligible | `countable` `analytics_engine.py:87-146` | base |
| **Closed-but-excluded** | **realized, UNVERIFIED (no stop)** | **`excluded_*` `analytics_engine.py:55,144-145`** | **Step-2 (this)** |
| Opened-in-period / open-spanning | UNREALIZED (floating) | `report_open_book.py` (`get_open_positions_campaign`) | S18/S19 |

RULING: the closed-but-excluded leg is **realized-but-unverified** — it belongs to the *closed* leg, NOT the open book. It is rendered in/near the realized section as a disclosure block (§1), kept entirely distinct from `report_open_book.py`'s unrealized block (whose `OPEN_BOOK_UNREALIZED_LABEL="לא ממומש"` must NOT be applied to it — this leg IS realized cash, just edge-unverified). No double-counting guard: a campaign is in EXACTLY ONE of {countable, excluded} (mutually exclusive by `analytics_engine.py:53,55`) and the open book is unrealized-only (`get_open_positions_campaign` net-open filter) — the excluded closed leg and the open book can never reference the same campaign, and neither is ever summed into the other or into countable.

---

## §4 — RULING: Founder-side data note (mirror `bot_health.py:142-149` tone)

When `excluded_manual_count > 0`, append (Telegram summary + PDF disclosure block) the honest, actionable, NON-error founder note:

> `📋 {n} קמפיינים נסגרו ללא initial_stop ולכן לא נכנסו לסטטיסטיקת ה-edge. זו השלמת נתונים — לא תקלת מערכת. השלם entry/stop בכל קמפיין כדי שייספר ב-WR/Expectancy/PF/Net-R.`

This MUST read as a data-completion task (matching the existing honest `אינו נספר` contract at `bot_health.py:147` and `engine_core.py:1248` "excluded from Expectancy"), explicitly NOT a system fault. No instruction is given for the ALGO subset (DEC-20260511-001).

---

## §5 — 12-item PASS/FAIL gate checklist (ALL must PASS to ship)

1. `_base_ctx:451-464` realized KPI keys byte-identical when `excluded_count>0` (guard test asserts dict equality vs no-excluded baseline). ☐
2. `excluded_pnl` NEVER summed into `realized_pnl`/`total_r_net`/`win_rate`/`expectancy_r`/`profit_factor`. ☐
3. `excluded_*` SPLIT into manual vs ALGO via existing `ec.is_algo_position`/`stat_bucket` predicate — zero new R/NAV/campaign math. ☐
4. ALGO excluded rendered on a SEPARATE observation-only line; never merged with manual; never an instruction (DEC-20260511-001 / #8). ☐
5. #1 wording `לא-מאומת` present on the realized-excluded disclosure; no R/WR/PF attached to `$X`. ☐
6. Disclosure is a DISTINCT block, never a KPI card, never adjacent-summed. ☐
7. Manual line omitted iff `excluded_manual_count==0`; ALGO line omitted iff `excluded_algo_count==0`; both independent. ☐
8. Sprint-19 `"0 בתקופה"` / `_HEADLINE_REALIZED_PNL_LABEL` (`report_renderer.py:48`) / verdict badge byte-identical; no contradiction (countable 0, excluded N both true). ☐
9. `compute_verdict` 920be95 (`analytics_engine.py:230`) + bcf32f5 + Sprint-16 graceful + Sprint-18 period-scoping + Sprint-19 headline/comparison/System-Health NOT regressed (existing tests green). ☐
10. Founder-side §4 note present, framed as data-completion not system error, mirrors `bot_health.py:147` tone. ☐
11. No Supabase mutation, no snap_save, no migration, no `docker-compose.yml`/`secure_runner` change; `report_open_book.py` unrealized block untouched & still separate. ☐
12. Tests added: (a) excluded surfaced when `excluded_count>0`; (b) manual/ALGO split correct on a mixed fixture; (c) countable-byte-identical guard; (d) ALGO line carries no instruction; full `pytest -q` green. ☐

---

**GATE:** Step-2 is APPROVED to build under the above rulings. It is presentation/additive only (the numbers already exist at `analytics_engine.py:57-58,144-145`). Any deviation — summing the excluded leg, merging ALGO, mutating realized KPIs, or omitting `לא-מאומת` — is a hard FAIL. Accuracy over confidence (CLAUDE.md). Do NOT git commit/push.
