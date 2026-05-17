# Sprint-26 Engine Findings — 100/100 re-verification of the LIVE money-math (DOC-ONLY, NO code)

**Date:** 2026-05-17 · **Verifier:** Engine team lead
**Verified state:** local HEAD `8c5a948` (clean tree) — contains every deployed
phase the brief names: C2 side-first classifier (`5e7634b`), Engine-P2/P3
F4/F5 + F6/F7/F9 docs (`b926e6e`), NAV-Unify canonical core (`5a0f2cb`),
Arch-F1 reader de-dup (`9017cab`), B3 add-on race guard (`67fca7a`).
The brief's prod tag `c761967` is the parent's *future* governed
consolidation commit and is not in this clone; source verified against the
phase commits it will consolidate (engine bytes are SHA-pinned, see below).
**Method:** re-derived from SOURCE + live throwaway probes against the real
functions (NOT trusting prior phase docs), plus the full CI-equivalent suite.

---

## Verdict: **100/100 on the headline money-math** — with ONE documentation
caveat (no live money error) and TWO latent open-book-only edges (not
KPI-affecting). No P0/P1. No correctness regression. No code recommended
this sprint (verification-only); the caveat below is a future *governed*
DOC-ONLY Phase candidate.

### Byte-lock / pin integrity (re-verified live)
- `sha256 engine_core.py` == `engine_core.py.baseline` = `d9547622…` ✓
  (matches the NAV-Unify record exactly).
- `sha256 analytics_engine.py` == `analytics_engine.py.baseline` = `2da07dea…` ✓
  (matches the Engine-P2/P3 record).
- LOCKED April regression re-run live: **8 / +$180.49 / WR .375 /
  PF 2.6262 / excl 2 (1 manual +$69.34, 1 ALGO −$48.905)** — byte-identical,
  GREEN. Weekly: **0 countable / 3 ALGO / −$37.234** — byte-identical, GREEN.
- Full CI-equivalent (`--cov … --cov-fail-under=67`, CI env):
  **2039 passed, 0 failed**, coverage **72.02% ≥ 67%** — equals the deployed
  NAV-Unify floor exactly. (A run that mixes Telegram suites shows 2 spurious
  `telebot.types` ImportErrors — pure pytest module-mock cross-contamination;
  `test_phase_b3_addon_cid.py` is **GREEN in isolation and in the full run**;
  NOT a code defect, NOT engine-math.)

### Closure-fixes re-verified CORRECT from source (live probes)
| Item | Probe result | Verdict |
|---|---|---|
| C2 F1/F2 (positive-qty SELL) | fully-closed pos-qty SELL → adaptive **1** closed (was 0), open-book **0** phantom (was 200) | ✓ closed |
| C2 partial control | pos-qty partial SELL → net_qty **60** open, realized_pnl **80** (side-string sum, correct) | ✓ |
| F4 dedup | exact-dup `trade_id` SELL → pnl **100** not 200 (all 3 sites) | ✓ closed |
| F5 boundary | exact 1%-residual (990/1000) → **NOT** closed (still open) | ✓ closed |
| F6/F7/F9 | `math.inf`-vs-`99.0`, cent-rounded 1R, `days_held` floor — all DOC'd in DATA_CONTRACTS §F6/F7/F9 | ✓ documented |
| NAV-Unify | account_state canonical; D1 explicit-0 / D2 strict-`<` / D3·D4 not-critical | ✓ single-sourced |
| R / stat_bucket / is_stat_countable / ALGO segregation / Expectancy / PF / WR | re-derived from source; AGENTS #8 invariant holds (`DATA_INCOMPLETE`+`ALGO_OBSERVED` excluded from WR/Exp/PF) | ✓ |
| drawdown auto-cut | now fed by the C2-correct closed set (F1 root cause that could hide a real losing run is closed) | ✓ |

The Sprint-25 P1 trio (F1/F2/F3) status: **F1+F2 CLOSED** by C2 (re-proven
live). **F3** (NaN-`pnl_usd` silently coerced to $0 via `_coerce_numeric`
→ a real win counted as a $0 loss) was explicitly **flag-only / DEFERRED**
in Sprint-25 and remains **untouched** — see Gap-1 below.

---

## Remaining gaps (latent; none corrupt today's headline KPIs)

### Gap-1 — F3 NaN-`pnl_usd` masking — still OPEN (P1, latent, was deferred)
`analytics_engine._coerce_numeric` does `pd.to_numeric(...).fillna(0)` over
`pnl_usd`; a SELL row with missing/garbage `pnl_usd` becomes **$0**, so a
real winning campaign silently enters WR/PF/Expectancy as a $0 loss with
**zero disclosure** — a CLAUDE.md hard-constraint ("do not silently present
fallback data as exact truth") concern. **Severity:** P1 *if* a corrupt
`pnl_usd` ever reaches the engine; **not observed in current prod** (DEC-019
reconciliation: all rows have clean `pnl_usd`; the LOCKED April fixture has
clean pnl → byte-identical). It is latent, not live. **Recommended (future,
governed) fix:** a `pnl_usd`-NaN → excluded + disclosed path with a NEW
honest counter (mirroring the Sprint-21 WS-B `unlinked_*` additive pattern),
proven byte-identical on the LOCKED April set; touches the Wave-2b-locked
`_coerce_numeric` so it needs the full Mark byte-lock ritual + founder gate.

### Gap-2 — F4 can silently drop a LEGITIMATE second partial fill (P2, latent)
F4's `drop_duplicates(subset=["trade_id"], keep="first")` assumes a repeated
`trade_id` is always a re-export/double-sync. If a broker reuses one exec-id
across two *genuinely distinct* partial fills (some IBKR exec-id reuse on
split fills), the **second real SELL is silently dropped** → realized
PnL/closure understated, and a fully-closed campaign can wrongly stay
"open". Live-probed: same-`trade_id` 5+5 distinct SELLs → 0 closed (true =
150 / fully closed). The DATA_CONTRACTS §F4 note says "behavior changes ONLY
on the duplicated-row input" but does **not warn** that *legitimate* shared
exec-ids are indistinguishable from dupes. **Severity:** P2 (depends on a
broker exec-id-reuse pattern not seen in DEC-019 prod; the LOCKED fixture has
all-unique ids → byte-identical). **Recommended (future, governed):** a
DOC-ONLY DATA_CONTRACTS §F4 amendment stating the dedup key assumes
exec-id-unique fills, plus a future raw-row audit before any move to a
composite key (`trade_id`+`trade_date`+`side`+`quantity`). No code now.

### Gap-3 — negative-qty BUY mis-signs open-book base_qty (P3, undocumented input)
`get_open_positions_campaign` line 538 `base_qty = first_day_buys["quantity"]
.sum()` and line 544 `avg_price` use the **raw signed** quantity (NOT
`.abs()`, unlike C2's `split_side_first`). A broker BUY exported with
*negative* quantity (mirror of the SELL ambiguity, but the SELL-only case is
the one DATA_CONTRACTS:59 documents) yields `base_qty = −100`. **Severity:
P3.** It does NOT reach headline money-math: live-probed, such a closed
campaign hits `get_campaign_risk_metrics` `base_qty <= 0` → INVALID →
`original_risk = 0` → **DATA_INCOMPLETE → correctly EXCLUDED** from
WR/Exp/PF/Net-R, and `net_qty` itself is C2 `.abs()`-correct. Impact is
confined to a wrong-sign `base_qty`/`base_price` in the open-book exposure
*view* for an **undocumented, not-currently-occurring** input. **Recommended
(future, governed):** if a negative-qty BUY is ever observed in a real raw
row, route `base_qty`/`avg_price` through the C2 `.abs()` magnitude (the
classifier already returns the correct subsets) — DEC-019 raw-row sign audit
first; no code now (no documented trigger, no KPI impact).

---

## למנכ״ל — בשפה פשוטה

**האם מספרי הכסף אמינים? כן — המספרים שאתה רואה בדוחות אמינים.**

בדקנו מחדש, משורת-הקוד ולא מהמסמכים, את כל חישובי הכסף החיים: רווח/הפסד,
R, אחוז הצלחה, תוחלת, Profit Factor, ה-NAV, חישוב הסיכון, חיתוך אוטומטי
בירידה, והפרדת עסקאות ALGO. הרגרסיה הנעולה של אפריל יצאה **בדיוק אותו דבר**
(8 קמפיינים / +180.49$ / 37.5% הצלחה / PF 2.6262) — שום מספר לא זז.
שלושת התיקונים הגדולים שנפרסו (C2, F4, F5) עובדים בפועל כפי שתוכננו.

**הסתייגות אחת חשובה (לא טעות חיה, אלא הגנה שעדיין חסרה):** אם אי-פעם תגיע
שורת מכירה עם שדה רווח/הפסד **ריק או פגום** מהברוקר — המערכת כיום הופכת
אותו בשקט ל-0$, כלומר רווח אמיתי יכול להיחשב כהפסד אפס בלי שום אזהרה. **זה
לא קורה היום** (כל הנתונים שלך נקיים, אומת מול הברוקר), אבל זו פרצה
תיאורטית שכדאי לסגור בעתיד בצורה מבוקרת. אין צורך בפעולה דחופה.

## מה צריך לעשות

1. **כלום דחוף.** המספרים אמינים; אפשר להמשיך לסחור ולסמוך על הדוחות.
2. **המספר היחיד לבדיקה ידנית מדי פעם:** ה-**רווח/הפסד הממומש הכולל**
   (Realized PnL) של תקופה — הצלב אותו פעם בשבוע מול דף ה-IBKR. זו הנקודה
   היחידה שבה שורה פגומה אחת מהברוקר עלולה (תיאורטית) להיכנס בשקט. כל שאר
   המספרים מוגנים בבדיקות נעולות.
3. **לעתיד (Phase מבוקר, לא דחוף):** לסגור את Gap-1 (גילוי שורת pnl
   פגומה במקום הפיכה שקטה ל-0) ולהוסיף הערת-תיעוד ל-Gap-2 (F4 עלול
   להפיל מילוי-חלקי לגיטימי עם מזהה כפול). שניהם דורשים אישור מייסד +
   טקס ה-byte-lock המלא — לא לגעת בלי תהליך.

---

## Recommendation (conservative — DOC-ONLY sprint)

**P0/P1-live: NONE.** The deployed engine/analytics/adaptive/NAV math is
**100/100 on every headline money number** and byte-identical on the LOCKED
April + Sprint-22 pins (re-verified live, not from docs). The deployed
C2/F4/F5/NAV-Unify closure-fixes are genuinely correct.

The single highest value÷risk *future* item is **Gap-1 (F3)** — the only
remaining finding that is *latently money-affecting on a possible bad input*
with zero disclosure (a CLAUDE.md honesty constraint), explicitly deferred
in Sprint-25, fixable as an additive disclosed-exclusion counter provably
byte-identical against the LOCKED April set. **Gap-2** is a DOC-ONLY
DATA_CONTRACTS §F4 amendment. **Gap-3** has no documented trigger and no KPI
impact (auto-excluded as DATA_INCOMPLETE). All three are fragile-area — no
edit without explicit founder + Mark go-ahead and the full governed
byte-lock ritual. WS-C / `-1`-sentinel (F8) stay DEFERRED, untouched.

— Engine team, Sprint-26 (DOC-ONLY; no code changed; no commit/push).
