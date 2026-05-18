# ALGO Investigation #2 — DOC-ONLY, live HEAD `102d0ef`/main

**Team:** ALGO (full roster — Lead, Risk & Kill-Switch Officer, Data-Integrity / Reconciliation Analyst, Stats / Trust-Score Quant, Segregation & Reporting Engineer, QA / Methodology Conformance).
**Mandate:** Founder question on the LIVE rendered report — the heat block shows "מדגם נוכחי: 9/50" / "7/50" and "Win Rate — S9 (9): 56% | L50 (9): 56%" (S9 and L50 the SAME tiny n). Founder is confident he has FAR more than 7-9 MANUAL (non-ALGO) trades. **Investigate-first, founder-gated. NOTHING executed — no code, no tests, no commit.** Every claim reproduced from SOURCE with `file:line`. Structural only — no live NAV/position/P&L copied; counts/relationships only.

> Accuracy over confidence. ⟨memo⟩ = doctrine inferred from the 2026-05-18 founder/Mark portfolio memo; superseded when the formal ALGO-rules doc arrives. Builds on `ALGO_INVESTIGATION_1.md` (R-ALGO-3 confirmed; the "מדגם נוכחי: N/50" honesty line is now wired via `telegram_formatters._l50_sample_honesty_line:113-130` — that fix has shipped; THIS investigation asks the *next* question: is 7-9 itself correct).

---

## 0. Method

Traced the FULL population pipeline that feeds the rendered heat block, from SOURCE: `report_scheduler._fetch_trades_df` → `report_scheduler._compute_risk_rec` → `adaptive_risk_engine.compute_closed_campaigns` → `_is_disc` window split → `disc_camps[:9|21|50]` → `_window_stats`. Cross-checked each shrink against the **live Probe extract** `/tmp/tg_report_2.txt` (the read-only `period_data_probe` surface, same DB/window contract as the report — `report_scheduler.py:120` notes the probe shares the engine path). The Probe prints, per campaign, `bucket=` and `נספר=כן/לא` — a direct, line-level census of the funnel with no live $ needed.

**Key clarification (which pipeline renders the founder's line).** The "מדגם נוכחי" / "Win Rate — S9 | L50" heat block is fed by `adaptive_risk_engine.compute_closed_campaigns` via `report_scheduler._compute_risk_rec` (`report_scheduler.py:256-260`) — **NOT** `analytics_engine._get_closed_campaigns`. The two are parallel closed-campaign extractors; the heat surface uses the ARE one. Both share the same upstream `df` (the 8-week-lookback fetch) and the same `engine_core.classify_stat_bucket` contract, so the funnel logic below is common.

---

## 1. The quantified funnel — where the population shrinks and by how much

Source window of the founder's report = the **monthly** run (the widest the report builds; the weekly heat uses the same fetcher with the same `weeks=8` lookback). Numbers below are the **structural census from the live Probe** (counts/relationships only — no $):

| Stage | Mechanism | `file:line` | Population | Census from Probe |
|---|---|---|---|---|
| **1. Raw manual history (all-time)** | Whatever the founder has ever traded manually (EP/VCP/…) — many tens+ | — (founder's premise) | "FAR more than 7-9" — **plausibly true all-time** | not visible in any window |
| **2. DB fetch — 8-WEEK LOOKBACK** | `lookback = period_start − timedelta(weeks=8)`; query `gte(trade_date, lookback)` … `lte(trade_date, period_end)` | `report_scheduler.py:169-178` | **only trades in ~8 weeks survive** | monthly probe: 107 visible rows, `trade_date` range 2026-02-05…2026-04-30 (`tg:2819-2820`) — i.e. a ~2-month slab, NOT all-time |
| **3. Closed campaigns (ANY in-window SELL, fully exited)** | ARE: group by `campaign_id`, side-split, `buys_qty>0`, residual `< 0.01`, has SELL | `adaptive_risk_engine.py:137-170` | campaigns that *closed* in the slab | monthly probe: **`SELL בחלון: 28 → קמפיינים שנסגרו: 20`** (`tg:2821`); weekly slabs: 3 and 4 |
| **4. NULL-`campaign_id` drop** | `if pd.isna(cid): continue`; `_get_closed_campaigns` `.dropna()` mirror | `adaptive_risk_engine.py:138`; `analytics_engine.py:403` | unlinked SELLs silently excluded | **`ללא campaign_id בחלון: 0` · `Σ pnl_usd לא-מקושר: $+0.00`** (`tg:2822`) — **ZERO loss here, not the cause** |
| **5. F4 trade_id dedup** | drop EXACT-`trade_id`-dup row | `adaptive_risk_engine.py:147-148` | byte-identical when ids unique | no evidence of dups; not the cause |
| **6. C2 side classifier** | side-string SELL/BUY (qty = magnitude only) | `engine_core.split_side_first:482-516` | provable no-op on correct convention | not the cause |
| **7. Manual (non-ALGO) split** | `_is_disc` → `is_stat_countable(stat_bucket)`; ALGO → excluded | `adaptive_risk_engine.py:452-458`; `engine_core.py:1297-1309` | drops every ALGO campaign | monthly probe: of 20 closed, **10 are `bucket=ALGO_OBSERVED · נספר=לא`** (HOOD/JPM/PLTR/QQQ/TSLA), 10 are manual `EP_MANUAL`/`VCP_MANUAL · נספר=כן`. Rendered "🔭 10 קמפייני ALGO נסגרו" (`tg:2544`) confirms 10 ALGO. |
| **8. stat-countable (DATA_INCOMPLETE / missing-stop / `-1`)** | `classify_stat_bucket`: ALGO→`ALGO_OBSERVED`; manual w/ `original_campaign_risk<=0`→`DATA_INCOMPLETE`; ARE risk: `init_sl>0 and init_sl<base_price` else 0 | `engine_core.py:1284-1304`; `adaptive_risk_engine.py:189-199`; `get_campaign_risk_metrics:1006-1017` | manual + valid stop | **EVERY excluded campaign in the probe is an ALGO `initial_stop=-1` row** ("initial_stop invalid (-1.00 vs base …)"). The probe shows **0 manual `DATA_INCOMPLETE`** — every `EP/VCP` line is `risk_valid=✓ · נספר=כן` |
| **9. Window slice → rendered N** | `disc_camps[:9]`, `[:21]`, `[:50]` ; `_window_stats["n"]=len` | `adaptive_risk_engine.py:463-465,290` | `[:50]` of ~7-10 = ~7-10 | rendered **9/50 and 7/50** (`tg:4307,4501`); WR lines S9(9)=L50(9), S9(7)=L50(7) (identical n) |

**Funnel headline (qualitative, structural):** all-time manual (many) → **collapses to ~2 months** at Stage 2 (the dominant collapse — the entire manual history before the lookback is structurally invisible) → ~20 closed in that slab → **~half are ALGO and correctly removed** (Stage 7, by-design segregation, ⟨memo⟩/AGENTS.md #8) → ~10 manual remain → **0 further loss to DATA_INCOMPLETE/`-1`/NULL-cid for manual rows** (Stage 8 — all manual EP/VCP carry valid stops in the probe) → the weekly heat slab (narrower than monthly) lands at the rendered **7-9**. The S9 and L50 counts are identical because `[:9]` and `[:50]` slice the **same 7-9-element list**.

### 1.1 Bug-vs-by-design verdict, per filter

| Filter | Verdict | Basis |
|---|---|---|
| **8-week lookback (Stage 2)** | **BY-DESIGN — and the dominant cause of "7-9".** | `report_scheduler.py:152-155` explicitly documents `weeks=8` as the production-validated DEC-20260516-020 April-reconcile value ("do NOT change"). Working as written. It is *the* reason the manual sample is tiny — the all-time history is **out of window by construction.** |
| **ALGO split (Stage 7)** | **BY-DESIGN — correct.** | ⟨memo⟩ "ALGO must be a separate cluster — never mixed into manual success"; DEC-20260511-001 #8; `is_stat_countable` excludes `ALGO_OBSERVED` (`engine_core.py:1307-1309`). Removing the 10 ALGO is *required* honesty, not a bug. Investigation #1 §3 already confirmed this segregation holds. |
| **`initial_stop=-1` / DATA_INCOMPLETE (Stage 8)** | **BY-DESIGN for the rows it actually hits — and it hits ZERO legitimate manual campaigns here.** | Every `-1`-stop row in the probe is **also ALGO** (HOOD/JPM/PLTR/QQQ/TSLA) — it would be excluded at Stage 7 anyway. The `-1` sentinel exclusion (`get_campaign_risk_metrics:1010-1017`) is the long-DEFERRED WS-C population, ALGO-only, founder-gated (charter §1). No manual EP/VCP row in the probe is `DATA_INCOMPLETE` (all `risk_valid=✓ · נספר=כן`). |
| **NULL-`campaign_id` (Stage 4)** | **NOT triggered.** | Probe: `ללא campaign_id בחלון: 0` (`tg:2822,2804,2402`). Zero contribution. |
| **F4 dedup / C2 side (Stages 5-6)** | **NOT triggered.** | Provable no-ops on the current convention; no dup/positive-qty-SELL evidence in the probe. |

**⇒ There is NO genuine under-count bug.** No legitimate manual closed campaign is silently dropped. Every exclusion that shrinks the founder's manual sample is either (a) the deliberate 8-week horizon or (b) the deliberate ALGO segregation. The `-1`/DATA_INCOMPLETE path — the one that *could* be a money-relevant correctness defect — does **not** hit a single manual campaign in the live window; it only removes ALGO rows that the ALGO filter removes anyway. **Bug-vs-by-design verdict: BY-DESIGN. The "7-9" is correct given the as-built 8-week statistical horizon + correct ALGO segregation.**

---

## 2. Is "L50" (a 50-sample frame) ever reachable given the window? — **NO. Structurally unreachable.**

`l50_stats = _window_stats(disc_camps[:50])` (`adaptive_risk_engine.py:465`). `disc_camps` is the manual-only subset of campaigns that **closed within the 8-week lookback** (Stage 7 of §1). For `[:50]` to yield 50, the founder would need **≥50 manual campaigns to fully close inside any single ~8-week window**.

Live structural reality: the widest window in the report (monthly) yields **20 closed total, ~10 manual** (§1). The weekly heat slabs yield far fewer (7-9 manual rendered). To reach L50=50 the manual closing rate would have to be ~5-7× the observed rate, sustained across every 8-week slab. At the founder's actual cadence this **never happens** — `[:50]` will essentially always collapse to the same 7-15 element list as `[:9]`, which is exactly why the report shows `S9(9)=L50(9)` and `S9(7)=L50(7)` (identical n).

There is also a degenerate fallback that makes L50 *even less* meaningful: if `disc_camps` is empty, `disc_camps = closed_campaigns[:50]` (`adaptive_risk_engine.py:459-460`) — i.e. it would fall back to **ALGO-contaminated** campaigns. Not the cause of "7-9" (here `disc_camps` is non-empty), but it is a latent honesty hazard worth flagging.

**Conclusion:** "L50" is a **methodology / labelling defect** — a 50-window that, under the as-built 8-week horizon, is **permanently unreachable** at the founder's trade cadence. The Investigation-#1 R-ALGO-3 fix (the "מדגם נוכחי: 9/50 — סטטיסטיקה ראשונית בלבד — אין לאשר הגדלת סיכון אגרסיבית" caveat, now live at `tg:4307,4501`) makes this **honest** — the partial-sample / no-aggressive-risk-raise disclaimer is therefore **permanent**, which is **correct conservatism** as long as the statistical base stays the 8-week window. The open question is a **founder/Mark design decision**: should the statistical base for L50 draw from **longer / all-time manual history** instead of the 8-week reporting window? That is money-affecting (it would change the heat score and the risk-raise gate) and is Tier-C.

---

## 3. Genuine under-count bug? — **NONE found.**

No legitimate manual campaign is silently dropped: the probe census shows **every** manual EP/VCP closed campaign in-window is `risk_valid=✓ · bucket=*_MANUAL · נספר=כן` and **every** excluded row is ALGO (`-1` stop). NULL-cid loss = 0. F4/C2 = no-ops. The money-relevant correctness risk the mandate asked us to rule out (a real manual campaign mis-bucketed to DATA_INCOMPLETE/`-1` and thus skewing WR/Expectancy/Heat/the risk-raise gate) is **NOT present in the live window**. The small sample is *honest*, not corrupted. (Latent caveats, not live bugs: the empty-`disc_camps` ALGO fallback `:459-460`; and the score-line literal `L50(50)` at `telegram_formatters.py:204` still prints the fictional `50` even though the new caveat line now contradicts/corrects it on the next line — Investigation #1 §2 / R-ALGO-3 residual.)

---

## 4. Tiered Mark-gated scope menu (same governed model as ALGO-1 / Sprint-24/25/27)

**Tier-A — pure honesty/doc, LOW risk, byte-identical on the normal path** *(recommend first)*
- **T-A1 — Horizon-honesty label on the heat block.** The caveat says "מדגם נוכחי: N/50" but never says *why* N is small (it is the 8-week window, by design — not a data error). Add one clause: state the sample is drawn from the ~8-week reporting window, so a small N is expected and not a defect. Removes the founder's exact confusion ("I have far more trades") without touching any math. Pairs with the existing `_l50_sample_honesty_line`. Byte-identical KPIs.
- **T-A2 — Kill the fictional `L50(50)` literal** (Investigation-#1 R-ALGO-3 residual, `telegram_formatters.py:204`): show real N in the score line too, so it stops contradicting the honest caveat one line below. N≥50 byte-identical.

**Tier-B — founder-gated closure-fix (bounded, honest direction)**
- **T-B1 — Empty-`disc_camps` ALGO-fallback hardening** (`adaptive_risk_engine.py:459-460`): when no manual campaigns exist, the code falls back to ALGO-contaminated `closed_campaigns[:50]` for the heat windows — a latent segregation leak (not the cause of "7-9", but a real ⟨memo⟩/AGENTS.md #8 hazard). Replace the fallback with an explicit "no countable manual sample" state. Provable byte-identical whenever `disc_camps` is non-empty (the live case). LOCKED-safe (`engine_core` untouched).

**Tier-C — money-affecting / HIGH, founder-gated, full governed Phase + named proofs**
- **T-C1 — The statistical-horizon decision (the real founder/Mark call).** Should L50 (and S9/M21) draw from **all-time / longer manual history** instead of the 8-week reporting window? This makes "L50" actually reachable and changes WR/Expectancy/Heat/the risk-raise gate (`adaptive_risk_engine.py:504`) — **money-affecting, HIGH**. Requires a separate fetch horizon for the *stats* base vs the *reporting* window; must NOT perturb the DEC-20260516-020 April-reconcile `weeks=8` reporting fetch. Re-baselines against the forthcoming formal ALGO-rules doc. Founder/Mark design decision — do **not** touch without explicit scope.
- **T-C2 — WS-C `-1`-sentinel manual-recovery** stays **DEFERRED** (charter §1) — irrelevant here anyway since no manual row is `-1` in the live window.

**Parent recommendation:** The founder's premise ("far more than 7-9 manual trades") is **true all-time but irrelevant to the current statistic** — the report intentionally measures only the 8-week window and intentionally removes ALGO. **There is no bug.** Do **T-A1 first** (Tier-A, near-zero risk, byte-identical): it directly answers the founder's confusion by stating *why* N is small (by-design horizon, not a data defect) on the surface he reads. Pair with **T-A2** (kill the residual fictional `L50(50)`). Hold **T-B1** (real but latent segregation-fallback hazard) for the next governed Phase. **T-C1 is the only thing that would actually make L50 "50"** — and it is a HIGH, money-affecting founder/Mark design decision, explicitly out of scope until the formal ALGO-rules doc and an explicit founder pick.

---

## למנכ״ל — בשפה פשוטה

- **ה-7-9 — באג או בכוונה? בכוונה. אין באג.** אתה צודק שיש לך הרבה יותר מ-7-9 עסקאות ידניות *בסך הכל* — אבל הדוח **לא** סופר את כל ההיסטוריה. הוא סופר רק עסקאות שנסגרו ב**חלון של ~8 שבועות** (זו החלטה מכוונה ומאומתת בקוד, `report_scheduler.py:169`). כל ההיסטוריה הישנה פשוט מחוץ לחלון — לכן המדגם קטן.
- **למה דווקא ~חצי נופל?** מתוך ~20 הקמפיינים שנסגרו בחלון, **~10 הם ALGO** — והם מוסרים בכוונה (אסור לערבב ALGO בסטטיסטיקה הידנית — בדיוק לפי הדוקטרינה שלך ושל מארק). נשארים ~10 ידניים, ובחלון השבועי הצר עוד פחות — וזה ה-7-9.
- **בדקנו אם נופל קמפיין ידני לגיטימי בטעות — לא.** בנתונים החיים, **כל** עסקה ידנית (EP/VCP) שנסגרה בחלון נספרת (`נספר=כן`). כל מה שמוחרג זה ALGO עם סטופ -1. אין כסף שמושפע מטעות חישוב, ואין סטטיסטיקה מעוותת.
- **"L50" אף פעם לא יגיע ל-50** בקצב המסחר שלך עם חלון 8 שבועות — לכן ההסתייגות "מדגם חלקי — אין לאשר הגדלת סיכון אגרסיבית" היא **קבועה, וזה נכון ושמרני**. אם תרצה ש-L50 *באמת* יהיה 50 — צריך להחליט (אתה + מארק) שהסטטיסטיקה תימשך מכל ההיסטוריה הידנית, לא מ-8 השבועות. זו החלטה שמשפיעה על כסף (על מד-החום ועל שער העלאת-הסיכון) — לא נוגעים בלי החלטה מפורשת.

## מה צריך לעשות

1. **הבנה ראשית** — אין באג, אין תת-ספירה, אין כסף שנפגע. ה-7-9 נכון בהינתן השיטה הקיימת. הבלבול נובע מכך שהדוח מודד 8 שבועות, לא תמיד.
2. **Tier-A T-A1 (מומלץ ראשון, סיכון אפסי, ללא שינוי מתמטי)** — להוסיף משפט אחד בבלוק החום: לציין *שהמדגם נמשך מחלון ~8 השבועות, ולכן מספר קטן הוא צפוי ולא תקלה*. זה עונה ישירות על השאלה שלך על המסך שאתה קורא.
3. **Tier-A T-A2** — לבטל את הליטרל המטעה `L50(50)` שעדיין מודפס בשורת הציון וסותר את שורת ההסתייגות הכנה שמתחתיו (שארית R-ALGO-3 מחקירה #1).
4. **Tier-B T-B1** — להקשיח את נפילת-החלון ל-ALGO כשאין מדגם ידני (סכנת-הדלפה חבויה, לא הגורם ל-7-9). Phase ממשל נפרד, בטוח לקבצים הנעולים.
5. **Tier-C T-C1** — *רק אם תבחר*: להחליט (אתה + מארק) אם בסיס הסטטיסטיקה יימשך מהיסטוריה ארוכה/מלאה במקום 8 שבועות. זה היחיד שיהפוך את "L50" לאמיתי — וזה HIGH ומשפיע על כסף; founder-gated, יתבסס מחדש כשמסמך כללי-האלגו הפורמלי מגיע.

---

*DOC-ONLY. No code, no tests, no commit. Structural counts/relationships only — no live NAV/position/P&L. Reproduced from SOURCE (`file:line`) + the live read-only Probe census `/tmp/tg_report_2.txt`.*
