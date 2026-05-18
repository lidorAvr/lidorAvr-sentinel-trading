# ALGO Investigation #3 — DOC-ONLY, live HEAD `cb65613`/main

**Team:** ALGO + Engine + Mark-doctrine joint (full ALGO roster — Lead, Risk & Kill-Switch Officer, Data-Integrity / Reconciliation Analyst, Stats / Trust-Score Quant, Segregation & Reporting Engineer, QA / Methodology Conformance — with the Engine team on the heat-math + Mark on the doctrine read).
**Mandate (founder, 2026-05-18):** (a) verify the **statistical horizon** (the 8-week window feeding Trust/Heat/risk-raise) with the dedicated teams; (b) determine what the system relies on when there is **NOT enough data inside that window** (cold-start / tiny-N). Parent pre-analysis flagged two suspected defects (D1, D2) — CONFIRM/refute each from SOURCE with `file:line`, assess the horizon vs Mark's doctrine, and return a tiered Mark-gated scope menu. **Investigate-first, founder-gated. NOTHING executed — no code, no tests, no commit.**

> Accuracy over confidence. ⟨memo⟩ = doctrine inferred from the 2026-05-18 founder/Mark portfolio memo; superseded when the formal ALGO-rules doc arrives (`ALGO_TEAM_CHARTER.md` §0). Builds on Investigation #1 (R-ALGO-3 confirmed/shipped: the "מדגם נוכחי N/50" honesty line) and #2 (the 8-week horizon is BY-DESIGN and the dominant cause of "7-9"; the empty-`disc_camps` ALGO fallback flagged as a latent T-B1 hazard). This investigation rigorously confirms the **mechanism** of that fallback (D1) and the **absent sample-gate on the risk-raise itself** (D2). Structural counts/relationships only — no live NAV/position/P&L.

---

## 0. Method

Traced the full risk-raise mechanism from SOURCE: `report_scheduler._fetch_trades_df` (8-week DB lookback) → `report_scheduler._compute_risk_rec` → `adaptive_risk_engine.compute_closed_campaigns` → `compute_adaptive_risk` (the `_is_disc`/`disc_camps` build + fallback, `_window_stats`, `_window_heat_score`, `base_heat`, the `heat_score ≥ 60 → "up"` RISK_LADDER step). Cross-checked the segregation contract `engine_core.is_stat_countable` / `classify_stat_bucket` / `is_algo_position`, the honesty line `telegram_formatters._l50_sample_honesty_line`, and `drawdown_auto_cut_recommendation`. Each disputed branch reproduced logically against the actual expressions; the smallest-N that mechanically forces `direction="up"` derived by hand from `_window_heat_score`.

---

## 1. The risk-raise mechanism (as-built, from source)

The scheduled-report heat thermometer / risk-raise read-out is produced by:

`_fetch_trades_df` (`report_scheduler.py:169` — `lookback = period_start - timedelta(weeks=8)`, DB query `gte(trade_date, lookback)`) → `_compute_risk_rec` (`report_scheduler.py:256-260`) → `compute_closed_campaigns(df)` → `compute_adaptive_risk(closed, risk_pct, nav)` (`adaptive_risk_engine.py:429`).

Inside `compute_adaptive_risk`:

- **Hard floor:** `if len(closed_campaigns) < 3: return {ok:False, "not_enough_trades"}` (`adaptive_risk_engine.py:445-450`). This is the **only** sample gate — and it counts **ALL** closed campaigns (ALGO + manual + DATA_INCOMPLETE), not disc-only, not a meaningful-N.
- **Disc split:** `_is_disc(c)` → `ec.is_stat_countable(c["stat_bucket"])` (`:452-456`); `disc_camps = [c for c in closed_campaigns if _is_disc(c)]` (`:458`).
- **Cold-start fallback:** `if not disc_camps: disc_camps = closed_campaigns[:50]` (`:459-460`). **No `_is_disc` filter on this branch.**
- **Windows:** `s9=_window_stats(disc_camps[:9])`, `m21=…[:21]`, `l50=…[:50]` (`:463-465`); `_window_heat_score` each (`:467-469`); `base_heat = s9*0.50 + m21*0.30 + l50*0.20` (`:471`); `heat_score = clamp(base_heat + open_r_bonus)` (`:499`).
- **Risk-raise trigger:** `if heat_score >= 60 and s9_loss_streak < 2: direction="up"` (`:504`); `direction=="up"` ⇒ `new_idx = min(curr_idx+1, len-1)` — **+1 RISK_LADDER step** (`:512-513`); `RISK_LADDER = [0.25,0.40,0.60,0.85,1.15,1.50,2.00]` (`:20`).

There is **no broker-recon gate, no ALGO-cluster gate, no Broken-position gate, and no minimum-sample gate** anywhere on the up-path (Investigation #1 §4 confirmed; re-confirmed here at HEAD `cb65613`, `:504-513`).

---

## 2. Evidence table — D1 & D2

| # | Claim | Source `file:line` | Verdict | Trigger / smallest-N | Severity · Money |
|---|---|---|---|---|---|
| **D1** | Cold-start ALGO contamination: when **zero** stat-countable manual campaigns exist in the 8-week window, `disc_camps = closed_campaigns[:50]` is **NOT** `_is_disc`-filtered ⇒ ALGO campaigns enter the disc-only heat / S9·M21·L50 / risk-raise base | `adaptive_risk_engine.py:458` (the `_is_disc` filtered list) → **`:459-460`** (`if not disc_camps: disc_camps = closed_campaigns[:50]` — raw, unfiltered) → flows to `:463-465` windows → `:471` base_heat → `:504` "up" trigger; contract bypassed: `engine_core.is_stat_countable:1307-1309` excludes `ALGO_OBSERVED` | **CONFIRMED** | **Triggers exactly when** `disc_camps == []` — i.e. **zero** closed campaigns in the 8-week window are stat-countable (every in-window close is `ALGO_OBSERVED` or `DATA_INCOMPLETE`) **AND** `len(closed_campaigns) >= 3` (else the `:445` floor returns `not_enough_trades` first). Per Investigation #2's live probe (~10 ALGO closed in a monthly slab), an all-ALGO / zero-manual 8-week window is realistic in a quiet manual stretch. When it triggers, `closed_campaigns[:50]` (newest-first, **ALGO included**) feeds S9/M21/L50 ⇒ ALGO win/loss/PnL drives `heat_score` ⇒ can drive `direction="up"` ⇒ a RISK_LADDER step-up on the founder's **discretionary** risk, computed off **ALGO** performance. | **HIGH.** Money-affecting (drives the risk-% recommendation). Breaches the **inviolable** ALGO-segregation doctrine (⟨memo⟩ "ALGO must be a separate cluster — never mixed into manual success"; DEC-20260511-001 #8; AGENTS.md #8; charter §1 "INVIOLABLE"). |
| **D2** | Risk-raise not sample-gated (false confidence): `_window_heat_score` returns **50.0 on n==0**; tiny-N feeds the same short list into S9/M21/L50 ⇒ `heat_score ≥ 60` from a few wins ⇒ `direction="up"` ⇒ a RISK_LADDER step-up, with **no minimum-sample gate on the mechanism** (only the display caveat warns) | `adaptive_risk_engine.py:327-328` (`if stats["n"] == 0: return 50.0`) → `:329-352` (score from `wr`/`payoff`/`pf`/`streak`, **no N term**) → `:463-471` (same short list sliced 3×) → **`:504`** (`heat_score >= 60 and s9_loss_streak < 2` ⇒ `"up"`); the only sample floor is `:445` (`< 3` **all** campaigns); the honesty line `telegram_formatters._l50_sample_honesty_line:113-130` is a **display string only** — it does **not** read back into `heat_score`/`direction` | **CONFIRMED** | **Exact threshold path:** `heat_score ≥ 60` with `s9_loss_streak < 2`. **Smallest-N that mechanically forces "up": N=3** (the `:445` floor is the only barrier; it counts *all* buckets). With **3 all-win disc campaigns**: each window `wr=1.0`→`base=100`; `loss_pnl` empty ⇒ `avg_loss=0`⇒`payoff=0.0` (no penalty, since the `0<p<0.8` test needs `p>0`); `gross_loss=0, gross_profit>0` ⇒ `pf=math.inf` ⇒ **+12**; `loss_streak=0`. Score `=112 → clamp 100.0` for S9=M21=L50 ⇒ `base_heat=100`, `heat_score≥60`, `s9_loss_streak=0<2` ⇒ **`direction="up"` → +1 ladder step from 3 winning trades.** Even a partial sample tilts up: e.g. **N=4, 3W/1L** with a healthy payoff/PF clears 60 well before any statistically meaningful sample. The `n==0 → 50.0` rule (`:327`) means an *empty* window contributes a **neutral 50** (not a penalty) into `base_heat`, so a strong S9 on a handful of trades is not dragged down by empty M21/L50. **No gate enforces N before the step-up.** | **HIGH.** Money-affecting (the as-built Heat-only risk-raise; ⟨memo⟩ "do NOT raise risk on a tiny/dirty sample" / "clean truth before aggressiveness"). The display caveat (R-ALGO-3, live) **warns the human** but does **not** block the **mechanism** — exactly the **unbuilt enforcement** of the founder/Mark **4-gate** (R-ALGO-1 / R-ALGO-6: recon-gap · negative-ALGO-cluster · Broken-position · **sample-size**). |

**D1 + D2 are independent and compounding.** D2 = "a tiny *manual* sample can raise risk." D1 = "when the manual sample is *empty*, the tiny sample raising risk is **ALGO** data." Together: in an all-ALGO 8-week window with ≥3 closed campaigns, the system can recommend raising the founder's discretionary risk based on a handful of **externally-managed ALGO** outcomes — a direct doctrine breach **and** false confidence on the same path.

### 2.1 Doctrine mapping (Mark / ⟨memo⟩ / DEC-20260511-001 #8)

- **Inviolable segregation (charter §1; AGENTS.md #8; ⟨memo⟩ "separate cluster, never mixed into manual success"):** D1 **breaches** it on the cold-start branch. The contract `is_stat_countable` is correct; the `:459-460` fallback *bypasses* the contract it was built to enforce. ALGO history (⟨memo⟩ 47 campaigns, ≈ −0.27R/trade, low-medium trust) could literally set the founder's manual risk-% in a quiet manual stretch.
- **"Don't raise risk on a tiny/dirty sample" + "clean truth before aggressiveness" (⟨memo⟩):** D2 is the direct violation — the mechanism has **no sample gate**; the only floor (`:445 < 3`) is far below statistical meaning and counts dirty buckets.
- **The founder/Mark 4-gate (R-ALGO-1 / R-ALGO-6):** the memo's "0.60%→0.85% risk-raise rejected while data unclean / tiny" is **not enforced in code** — the up-path is purely Heat-Score-driven. D2 is the *false-confidence* face of the unbuilt sample-gate; D1 is the *contamination* face of the unbuilt cluster-gate. Both are inside the R-ALGO-1/6 scope.

---

## 3. Horizon assessment — is the 8-week window the right statistical base for the **risk-raise** decision per Mark's doctrine?

**The horizon is `period_start − timedelta(weeks=8)`** (`report_scheduler.py:169`), production-validated as the **DEC-20260516-020 April-reconcile** value, documented "**do NOT change the weeks=8 behavior**" (`report_scheduler.py:152-155`). It is *correct as the **reporting** fetch* and must not move.

**The methodology problem (Mark-doctrine framing):** the same 8-week fetch is *reused* as the **statistical base** for the risk-raise. Investigation #2 already established that at the founder's manual cadence the 8-week window yields ~7-10 manual closed campaigns — **L50 is structurally unreachable** and the partial-sample caveat is **permanent**. So the risk-raise decision (a money decision the memo wants gated by *clean, sufficient* evidence) is being made off a window whose manual sample is, by construction, almost always tiny. This is the root that makes D1 (empty manual ⇒ fallback) and D2 (tiny manual ⇒ false "up") *reachable in normal operation*, not edge cases.

**The methodology decision for the founder/Mark (no recommendation forced — tradeoffs only):**

| Option | What it is | Pros | Cons / risk |
|---|---|---|---|
| **(i) Keep + relabel ("honest 8-week window, not L50")** | Leave the fetch + math byte-identical; rename "L50" → an honest "חלון 8-שבועות (לא L50)" label; state *why* N is small (by-design horizon). | Zero math/KPI change; byte-identical; LOCKED-safe; directly answers the founder's recurring confusion; pure honesty (B1 class). | Does **not** make the statistic more powerful; the risk-raise still fires off a tiny sample (D2 untouched); the caveat stays permanent. Honest, but conservative-forever. |
| **(ii) Extend to a rolling last-N *manual* campaigns, all-time** | A **separate** stats fetch (not the reporting fetch) drawing the last-N closed **manual** campaigns regardless of the 8-week reporting window. | Makes S9/M21/L50 statistically meaningful; the risk-raise rests on real edge, not a 7-trade slab; aligns with ⟨memo⟩ "decide on clean, sufficient data." | **Money-affecting / HIGH.** Changes heat_score and the risk-raise gate. Needs a second fetch horizon for *stats* vs *reporting* (must NOT perturb the DEC-20260516-020 `weeks=8` reporting fetch). Re-baselines vs the forthcoming formal ALGO-rules doc. Older trades may be regime-stale (a known tradeoff: power vs recency). |
| **(iii) Hybrid (recency-weighted / floor-N)** | Use the 8-week window but **backfill** to a minimum manual-N from older history (or recency-weight older manual campaigns). | Balances recency against sample power; the risk-raise never fires on <N; degrades gracefully. | Most design-heavy; two parameters to tune (floor-N, decay); HIGH; needs Mark sign-off on the weighting math; full governed Phase + named proofs. |

**Doctrine read:** Mark's doctrine ("clean truth before aggressiveness"; "don't raise risk on a tiny/dirty sample") is **satisfied by the *caveat*** for the *human*, but **not by the *mechanism*** — and option (i) keeps it that way (honest but permanently conservative), while (ii)/(iii) would let the system *earn* an aggressive read on real evidence. This is a **founder/Mark methodology call**, explicitly money-affecting, Tier-C, and re-baselines when the formal ALGO-rules doc lands.

---

## 4. Does `drawdown_auto_cut` have the same tiny-N / empty exposure? — **NO. It fails SAFE (refuted).**

`drawdown_auto_cut_recommendation` (`adaptive_risk_engine.py:243-280`):

- `if not closed_campaigns or nav <= 0: return None` (`:260`) — empty ⇒ **no action** (no cut, no raise).
- `recent = filter_closed_within_days(closed_campaigns, 30)`; `if not recent: return None` (`:262-264`) — no recent data ⇒ **no action**.
- It only ever returns a **protective** result: `force_cut_to_pct = DRAWDOWN_CUT_TO_PCT (0.40)`, and **only** when `drawdown_pct <= DRAWDOWN_TRIGGER_PCT (-8.0)` (`:267`) **and** current risk is above the floor (`:269`). It can **never raise** risk and **never** fabricates a cut on no/low data — on missing data it returns `None` (the heat path then governs, unchanged).

**Two honest caveats (NOT money-mis-fires, logged for completeness):**
1. **It does *not* `_is_disc`-filter** — `pnl_30d = sum(total_pnl_usd for c in recent)` (`:265`) sums **all** buckets incl. ALGO. Direction of effect: ALGO losses make the protective cut **more likely / earlier** (conservative); ALGO gains could **mask** a real manual drawdown and **suppress** a protective cut (a *missed protection*, not a wrong aggressive action). This is the **mirror** of D1 on the protective side and is worth flagging to Mark, but it does **not** "silently mis-fire" toward more risk — its only output is a cut or `None`.
2. It is **not wired into `_compute_risk_rec`** (`report_scheduler.py:256-260` calls only `compute_adaptive_risk`); `drawdown_auto_cut_recommendation` is invoked elsewhere (dashboard / risk-monitor paths) — out of this mandate's scope to fully trace, but confirms the scheduled-report risk-raise path does **not** layer the drawdown protection. Logged, not in scope.

**Verdict:** the protective side does **not** share D1/D2's *raise-risk-on-no-data* hazard — it is **fail-safe** (returns `None` on empty/insufficient data, only ever cuts). The single open nuance is the ALGO-unfiltered 30-day PnL sum (`:265`) which can *under-protect* (mask a manual drawdown) — a Tier-B-adjacent honesty item, **not** a false-aggressive defect.

---

## 5. Tiered Mark-gated scope menu (same governed model as ALGO-1/2, Sprint-24/25/27)

**Tier-A — pure honesty/clarity, LOW risk, byte-identical on the normal path** *(recommend first)*
- **T-A1 (horizon-honesty label).** State on the heat block that the sample is drawn from the ~8-week reporting window (by-design, not a data defect) — extends Investigation #2's T-A1; pairs with the live `_l50_sample_honesty_line`. Zero math/KPI change; byte-identical. *(carry-over, still open)*
- **T-A2 (kill the fictional `L50(50)` literal).** Show real N in the score line so it stops contradicting the honest caveat one line below. N≥50 byte-identical. *(carry-over)*

**Tier-B — founder-gated closure-fixes (bounded, behavior in the honest/safe direction)**
- **T-B1 — D1 fix: `_is_disc`-filter the cold-start fallback** (`adaptive_risk_engine.py:459-460`). Replace `disc_camps = closed_campaigns[:50]` with an **explicit "no countable manual sample"** state (e.g. surface `{ok:False, "no_countable_manual_sample"}` / a neutral non-raising heat) instead of falling back to ALGO-contaminated campaigns. **Provably byte-identical whenever `disc_camps` is non-empty** (the live case — guard test). `engine_core` untouched / LOCKED-safe. Closes the **inviolable**-doctrine breach. **Highest value ÷ risk in the menu.**
- **T-B1b (optional, paired) — `drawdown_auto_cut` ALGO-filter honesty** (`adaptive_risk_engine.py:265`): `_is_disc`-filter the 30-day PnL sum so ALGO gains can't mask a manual drawdown and suppress the protective cut. Conservative direction; byte-identical when no ALGO in the 30-day window.

**Tier-C — money-affecting / HIGH, founder-gated, full governed Phase + named proofs**
- **T-C1 — D2 fix: sample-gate the risk-raise (the 4-gate, R-ALGO-1 / R-ALGO-6).** Add a **minimum stat-countable-manual-N gate** (+ recon-gap / negative-ALGO-cluster / Broken-position gates) so `direction="up"` cannot fire on a tiny/dirty sample. **Byte-identical when all gates green** (= today's Heat path); new tests per gate; LOCKED ladder/regression unchanged. HIGH; supersedes/extends R-ALGO-1.
- **T-C2 — the statistical-horizon decision** (§3 options i/ii/iii). The real founder/Mark methodology call: does the *stats* base stay the 8-week reporting window, or draw from longer/all-time manual history? Money-affecting; separate stats fetch (must NOT touch the DEC-20260516-020 reporting `weeks=8`); re-baselines vs the formal ALGO-rules doc. Do **not** touch without explicit scope.

**Parent recommendation.** Do **T-B1 first** — it is the single highest **value ÷ risk** fix: it closes an **inviolable**-doctrine breach (ALGO mixed into the founder's manual risk-raise base), it is **bounded** (one branch, `:459-460`), **provably byte-identical on the live non-empty path**, and **LOCKED-safe** (`engine_core` untouched). Pair it with the cheap Tier-A honesty carry-overs (T-A1/T-A2). Hold **T-C1 (D2 sample-gate)** and **T-C2 (horizon)** for explicit founder scope + the formal ALGO-rules doc — both are HIGH and money-affecting; D2's *mechanism* fix is the right home for the 4-gate, but the human is already warned (R-ALGO-3 live), so the *contamination* (D1) is the more urgent, lower-risk closure. Nothing executed until the founder picks scope.

---

## למנכ״ל — בשפה פשוטה

- **כשאין מספיק נתונים בחלון — האם המערכת נשארת בטוחה? בחלקה לא.** מצאנו **שני פגמים אמיתיים**, שניהם אושרו מהקוד.
- **פגם 1 (חמור — קו אדום):** כשבחלון ה-8 שבועות **אין אף עסקה ידנית** שנספרת (רק עסקאות ALGO/חסרות-נתונים), הקוד "נופל" ומשתמש בעסקאות **ALGO** כדי לחשב את מד-החום ואת המלצת הסיכון (`adaptive_risk_engine.py:459-460`). זה **מערבב ALGO לתוך החלטת הסיכון הידנית שלך** — בדיוק הדבר שהדוקטרינה שלך ושל מארק אוסרת **באופן מוחלט**. בתקופה שקטה ידנית זה יכול לקרות באמת.
- **פגם 2 (חמור):** המנגנון שמעלה סיכון מסתמך **רק על מד-חום**, ללא שום שער של "מספיק מדגם". מבחינה מתמטית, **3 עסקאות מנצחות בלבד** כבר מספיקות כדי שהמערכת תמליץ **להעלות מדרגת סיכון**. ההסתייגות שכבר הוספנו (R-ALGO-3) **מזהירה אותך על המסך**, אבל היא **לא חוסמת את ההמלצה עצמה** — האכיפה האמיתית (מודל 4-השערים של מארק) **עדיין לא נבנתה**.
- **חלון 8 השבועות:** הוא **נכון כחלון דיווח** ואסור לשנות אותו. הבעיה היא ששאותו חלון משמש גם **כבסיס הסטטיסטי** להעלאת סיכון — ולכן המדגם כמעט תמיד קטן מדי. זו **החלטת מתודולוגיה של המנכ"ל + מארק** (להשאיר ולתייג בכנות / למשוך מהיסטוריה ארוכה / היברידי) — לא נוגעים בלי החלטה מפורשת.
- **הצד המגן (חיתוך-סיכון אוטומטי בדרודאון): בטוח.** הוא **לעולם לא מעלה סיכון** ועל היעדר נתונים פשוט לא עושה כלום — נכשל לכיוון הבטוח. הסתייגות אחת בלבד: הוא לא מסנן ALGO, כך שרווחי ALGO *יכולים להסתיר* דרודאון ידני אמיתי ולמנוע חיתוך מגן (פספוס הגנה — לא פעולה אגרסיבית שגויה).

## מה צריך לעשות

1. **הבנה ראשית:** על מעט/אין נתונים — הצד המגן בטוח, אבל **הצד שמעלה סיכון לא**: יכול להעלות סיכון ממדגם זעיר (פגם 2), ובמצב קר אף לערבב ALGO (פגם 1, קו אדום).
2. **מומלץ ראשון — Tier-B T-B1 (היחס ערך-חלקי-סיכון הגבוה ביותר):** לתקן את פגם 1 — לסנן ALGO גם בנפילת-החלון (`:459-460`), ובמקום זה מצב מפורש "אין מדגם ידני נספר". מוכח **זהה בית-לבית כשיש מדגם ידני** (המצב החי), בטוח לקבצים הנעולים. סוגר הפרת דוקטרינה **מוחלטת**.
3. **לצרף Tier-A** (סיכון אפסי, ללא שינוי מתמטי): T-A1 — לציין שהמדגם מחלון 8 השבועות (לכן קטן זה צפוי); T-A2 — לבטל את הליטרל המטעה `L50(50)`.
4. **Tier-C — רק בבחירת היקף מפורשת (HIGH, משפיע על כסף):** T-C1 — מודל 4-השערים שמונע העלאת-סיכון על מדגם זעיר/מלוכלך (תיקון המנגנון של פגם 2); T-C2 — החלטת המנכ"ל+מארק על בסיס הסטטיסטיקה (8-שבועות מול היסטוריה ארוכה/היברידי). יתבסס מחדש כשמסמך כללי-האלגו הפורמלי מגיע.

---

*DOC-ONLY. No code, no tests, no commit. Structural counts/relationships only — no live NAV/position/P&L. Every claim reproduced from SOURCE (`file:line`) at live HEAD `cb65613`.*
