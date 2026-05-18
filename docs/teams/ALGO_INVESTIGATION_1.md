# ALGO Investigation #1 — DOC-ONLY, live HEAD `b433cd4`/main

**Team:** ALGO (acting across the full roster — Lead, Risk & Kill-Switch Officer, Data-Integrity / Reconciliation Analyst, Stats / Trust-Score Quant, Segregation & Reporting Engineer, QA / Methodology Conformance).
**Mandate:** First ALGO mandate (DEC-20260518-001 / `ALGO_TEAM_CHARTER.md` §5). Investigate-first, founder-gated. **NOTHING executed — no code, no tests, no commit.** Every claim reproduced from SOURCE with `file:line` evidence; nothing assumed.

> Accuracy over confidence. ⟨memo⟩ = doctrine inferred from the 2026-05-18 founder/Mark portfolio memo; superseded when the formal ALGO-rules doc arrives.

---

## 0. Method

Traced from source the two reconciliation derivation paths (master/dashboard vs live חדר-מצב), the heat-score risk-raise mechanism, the ALGO segregation buckets across dashboard/reports/engine, the L50/last-N display path, and the ALGO observe-only enforcement. Reproduced each disputed number logically against the actual expressions.

---

## 1. R-ALGO-2 — the two broker-reconciliation numbers — **CONFIRMED (real money-truth bug)**

There genuinely are **two different reconciliation numbers for the same state.** Root cause = a **wrong dict-key** in the חדר-מצב path.

Both paths build the same shape: `gap = NAV − (total_deposited + realized_DB_PnL + open_PnL)`, then classify via the shared, correct `tf.classify_broker_reconciliation` (`telegram_formatters.py:708`). The classifier is **not** the bug — the **realized-DB-PnL input differs**:

| Path | Realized-PnL term | Evidence | Value |
|---|---|---|---|
| **Master / dashboard sidebar "⚖️ Data Reconciliation"** | `total_pnl_net = camp_df['pnl_usd'].sum()` (sum of **every** campaign's `pnl_usd`) | `dashboard.py:424` → `db_equity_expected` `dashboard.py:438` → `reconciliation_gap` `:439` → classifier `:455-461` | Correct realized PnL (full) |
| **Live חדר-מצב "📊 חדר מצב"** | `_db_net_pnl = sum(float(c.get("net_pnl", 0) or 0) for c in are.compute_closed_campaigns(df))` | `telegram_portfolio.py:472-475` → classifier `:476-482` | **always `0.0`** |

**Exact divergence root cause (reproduced):** `adaptive_risk_engine.compute_closed_campaigns()` emits each closed campaign with the realized-PnL key **`total_pnl_usd`** (`adaptive_risk_engine.py:205`) — it **never emits `net_pnl`**. (`net_pnl` is a *different* function's key — `analytics_engine._aggregate_campaigns`, `analytics_engine.py:474` — not this one.) So `c.get("net_pnl", 0)` at `telegram_portfolio.py:473` matches **no key** and falls back to `0` for **every** campaign ⇒ `_db_net_pnl == 0.0` always. The חדר-מצב reconciliation therefore computes expected equity as `deposited + 0 + open_PnL`, **silently omitting ALL realized closed-campaign PnL**, while the dashboard includes it. That fully explains a master-vs-חדר-מצב gap discrepancy of the memo's order ($510.51 vs $190.29): the two numbers differ by ~the realized closed-campaign PnL term that one path drops.

**Which is correct?** The **dashboard/master** side is the methodologically intended one (realized PnL *is* part of expected DB equity). The **חדר-מצב** number is **wrong** (understates/zeroes realized PnL → wrong gap → can render a *false "Balanced/Minor"* band, or a wrong "Critical", on the surface the trader actually reads on the phone). Caveat (honesty): both `pnl_usd`-sum vs `total_pnl_usd`-sum also differ slightly in *which campaigns* count (dashboard sums all rows incl. open-partial via `camp_df`; `compute_closed_campaigns` is closed-only) — the **dominant** error is the `0.0` key bug; a residual closed-vs-all definitional nuance remains and must be stated, not hidden.

- **Verdict:** CONFIRMED. **Severity: HIGH. Money-affecting (truth).** Class: bug-fix (the fix *changes* the חדר-מצב number → it is a behavior change in that surface, in the honest direction).
- **Byte-locked?** NO. `telegram_portfolio.py` + `dashboard.py` are not byte-locked. `analytics_engine.py`/`engine_core.py`/LOCKED April fixture **untouched** by a one-key fix.
- **No test pins the bug:** `tests/test_telegram_portfolio.py:276,365` mocks `compute_closed_campaigns.return_value = []`; `tests/test_sprint15_r_integrity.py:200-270` only tests the pure classifier with hand-passed gaps. The buggy call-site key is **uncovered**.

---

## 2. R-ALGO-3 — "L50" with N<50 — **CONFIRMED (partially: N is disclosed in one sub-line, but the label + score-line lie)**

`l50_stats = _window_stats(disc_camps[:50])` (`adaptive_risk_engine.py:465`). Python `[:50]` of 9 campaigns = **9** — the "L50" score `l50_score` (`:469`) and `all_50_wr` (`:547`) are computed off **9 trades** but branded **"L50"**.

Display paths:
- `telegram_formatters.py:204` — `S9(9)=… | M21(21)=… | L50(50)=…` — the **window sizes are hardcoded literals** `(9)/(21)/(50)`. With 9 real trades this prints **"L50(50)"** — **false confidence**, the 50 is fictional.
- `telegram_formatters.py:213` & `:443` — `L50 ({n50})` *does* show the true count (`n50 = l50_stats["n"]` → `9`), so this one sub-line is honest.
- `telegram_formatters.py:435` (`fmt_heat_thermometer`) — bare `L50 [bar] score`, **no N at all**.

There is **no "L50 unavailable — sample too small" / "Current sample: N/50" disclosure anywhere** in the heat path. An honest helper **already exists but is NOT wired in**: `engine_core.get_sample_size_context()` (`engine_core.py:1205`) returns the exact ⟨memo⟩-aligned Hebrew label *"סטטיסטיקה ראשונית בלבד — אין לאשר הגדלת סיכון אגרסיבית"* for `<30` trades — it is simply not consumed by the L50/heat surface.

- **Verdict:** CONFIRMED (memo's "shows L50 with 9 trades" is real on `:204`/`:435`). **Severity: MEDIUM.** Money-affecting: **no** (presentation), but it materially feeds *false confidence into a money decision* (the risk-raise read-out). Class: **honesty-fix / presentation — CLAUDE.md #1 / B1 honesty class** (the existing Sprint-27 W1 / B1 pattern).
- **Byte-locked?** NO (`telegram_formatters.py`, `adaptive_risk_engine.py` display string only).

---

## 3. ALGO segregation / −$612.16 trust reality — **CONFIRMED segregated for edge-stats; PARTIALLY contaminating one displayed total**

Edge stats are correctly segregated — ALGO **cannot** contaminate Win Rate / Expectancy / PF / streak / heat:
- Dashboard buckets: `countable_df = is_stat_countable` (EP/VCP only), `algo_df` separate (`dashboard.py:409-419`); headline WR/Exp/Adj-RR from `combined_stats=_bucket_stats(countable_df)` (`:415,421-423,1050-1053`).
- Heat / risk-raise excludes ALGO: `_is_disc()` → `ec.is_stat_countable(bucket)` (`adaptive_risk_engine.py:452-458`), ALGO open-R down-weighted 0.25× (`:480-484`).
- Contract enforced: `is_stat_countable` False for `ALGO_OBSERVED`/`DATA_INCOMPLETE` (`engine_core.py:1307`; DATA_CONTRACTS §stat_bucket; AGENTS.md #8).

**BUT** one displayed total is *not* bucket-filtered: `total_pnl_net = camp_df['pnl_usd'].sum()` (`dashboard.py:424`) sums **all** campaigns incl. ALGO. It is shown as **"Total Net PnL (DB)"** (`dashboard.py:767`) and **"DB Net PnL (all)"** in the AI export (`:573`), and it is the realized term of the **reconciliation** (#1). So the ALGO drag (⟨memo⟩ 47 campaigns / −$612.16) **does** flow into the displayed total-PnL line and the recon expected-equity. It is *labelled* "(all)/(DB)" so it is **disclosed, not silently mixed into edge stats** — but it is **not a clean ALGO-segregated cluster line** the way the memo wants (⟨memo⟩ "separate cluster with its own stats"). `algo_stats` exists (`dashboard.py:417`) but the headline-adjacent total isn't split. → supports **R-ALGO-4**.

- **Verdict:** segregation **holds where it must** (edge stats / heat / risk-raise — DEC-20260515-014 / AGENTS.md #8 intact); **partial leak into a disclosed total + the recon input** is the open gap. **Severity: MEDIUM.** Money-affecting: indirectly (via #1 recon). Class: feature/restructure.

---

## 4. As-built risk-raise = Heat-Score-only; ALGO observe-only — **CONFIRMED (both)**

- **Risk-raise is purely Heat-Score-driven.** `direction="up"` (+1 RISK_LADDER step) fires **iff** `heat_score >= 60 and s9_loss_streak < 2` (`adaptive_risk_engine.py:504`); `down_fast` iff `heat<40 or s9_loss_streak>=3` (`:506`). `heat_score = 0.50·S9 + 0.30·M21 + 0.20·L50 + open_R_bonus` (`:471,499`). **No broker-recon gate, no ALGO-cluster gate, no Broken-position gate, no sample-size gate** anywhere in the up-path. RISK_LADDER `[0.25,0.40,0.60,0.85,1.15,1.50,2.00]` (`:20`; MODULE_MAP confirms). The memo's "0.60→0.85 should be rejected while data unclean" is **not enforced** today → this is exactly the gap **R-ALGO-1 / R-ALGO-6** target.
- **ALGO is observe-only — confirmed in code.** `evaluate_position_engine` returns fixed `action="מנוהל חיצונית — בקרה בלבד"`, `suggested_stop: None`, no management logic when `management_mode=="algo_observed"` (`engine_core.py:466-476`); `classify_management_mode` → `algo_observed` for ALGO (`:272-278`). DEC-20260511-001 #8 **holds in code**. No manual ALGO exit path exists. WS-C / `-1`-sentinel remain DEFERRED.

---

## 5. Full R-ALGO-1..8 triage

| ID | Status | Sev | Money? | Class | Byte-locked touched? | Governed-Phase proof strategy |
|---|---|---|---|---|---|---|
| **R-ALGO-1** Recon-gap gate ⇒ block risk-raise | CONFIRMED gap (no gate exists, §4) | HIGH | YES | behavior (new gate) | NO (`adaptive_risk_engine.py` logic; engine_core untouched) | New gate is opt-in branch; **prove byte-identical when gate inactive** (clean data ⇒ identical rec); LOCKED April + `test_adaptive_risk_engine` unchanged; new tests for the blocked path. Founder-gated, HIGH. |
| **R-ALGO-2** Recon $510 vs $190 | **CONFIRMED bug** (§1) | HIGH | YES (truth) | bug-fix (behavior in חדר-מצב) | NO | One-key fix `telegram_portfolio.py:473` `"net_pnl"`→`"total_pnl_usd"`; add a חדר-מצב recon parity test (currently uncovered); LOCKED April byte-identical (not on that path); state residual closed-vs-all nuance honestly. |
| **R-ALGO-3** L50 with N<50 | **CONFIRMED** (§2) | MED | no | honesty-fix (B1) | NO | Wire existing `get_sample_size_context` into `:204/:435`; show real N or "מדגם N/50 — קטן מדי". Pin: N≥50 ⇒ string byte-identical; N<50 ⇒ honest label present. B1/Sprint-27-W1 pattern. |
| **R-ALGO-4** Strict manual/ALGO split (4 tables) | PARTIALLY (edge OK, total leaks, §3) | MED | indirect | feature/restructure | NO | Add segregated ALGO-cluster line; **edge stats byte-identical** (already countable-only); presentation-additive. Founder-gated UX. |
| **R-ALGO-5** Per-engine Trust Score | open (addition) | LOW | no | addition | NO | Pure additive read-only panel; no existing number changes; design-heavy, founder-gated. |
| **R-ALGO-6** 4-gate risk-raise (replace Heat-only) | CONFIRMED as-built Heat-only (§4) | HIGH | YES | behavior change | NO | Supersedes/extends R-ALGO-1; **byte-identical when all 4 gates green** (= today's Heat path); new tests per gate; LOCKED ladder/regression unchanged. HIGH, founder-gated. |
| **R-ALGO-7** Decision-card per position | open (feature) | LOW | no | feature/UX | NO | Additive presentation over existing `compute_position_state`; numbers byte-identical. Founder-gated UX. |
| **R-ALGO-8** Probation/kill-switch state machine + Risk-Breach-Review alert | open; observe-only must hold (§4) | HIGH | YES (gates/alerts) | behavior (observe-only) | NO | Alerts/gates only — **NO manual ALGO exit** (DEC-20260511-001 #8); per-position dedup state (AGENTS.md #7 anti-spam); founder-gated, HIGH. |

---

## 6. Tiered Mark-gated scope menu (same governed model as Sprint-24/25/27)

**Tier-A — pure honesty/doc, LOW risk, byte-identical on the normal path** *(B1 class — recommend first)*
- **R-ALGO-3** L50 sample-honesty: wire the *existing* `get_sample_size_context`; N≥50 byte-identical, N<50 shows honest "N/50 — קטן מדי". No money math.

**Tier-B — founder-gated closure-fixes (bounded, behavior in the honest direction)**
- **R-ALGO-2** the recon-key bug: one-key fix + first-ever חדר-מצב recon parity test + honest note on the residual closed-vs-all nuance. **Truth fix — money-truth, but tiny surface, LOCKED-safe.**
- **R-ALGO-4** add a segregated ALGO-cluster line (edge stats already byte-identical) — presentation-additive.

**Tier-C — money-affecting / HIGH, founder-gated, full governed Phase + named proofs**
- **R-ALGO-1 / R-ALGO-6** the recon/cluster/Broken/sample gates on risk-raise (4-gate model; byte-identical when all-green).
- **R-ALGO-8** probation/kill-switch state machine + Risk-Breach-Review alert (observe-only, anti-spam dedup).
- **R-ALGO-5 / R-ALGO-7** additive Trust-Score & decision-card surfaces (no number change; design-heavy).

**Parent recommendation:** Do **R-ALGO-2 first** (Tier-B) — it is a *live money-truth defect* (a wrong reconciliation number on the surface the trader reads daily), a **single-key, LOCKED-safe, test-coverable** fix; pair it immediately with **R-ALGO-3** (Tier-A, near-zero risk, removes the *false-confidence* the same trader sees). Tier-C (gates/state-machine) only after the founder picks scope — those are HIGH and re-baseline against the forthcoming formal ALGO-rules doc.

---

## למנכ״ל — בשפה פשוטה

- **שני מספרי ההתאמה — באג אמיתי? כן.** המערכת מציגה היום שני מספרי "התאמה לברוקר" שונים לאותו מצב בדיוק. בדשבורד המספר נכון; ב**חדר־מצב בטלגרם** (המסך שאתה קורא בו בנייד) יש **טעות של שם־שדה אחת בקוד** (`telegram_portfolio.py:473`) שגורמת לכל הרווח הממומש מהעסקאות הסגורות **להתאפס לאפס** בחישוב. לכן חדר־מצב יכול להראות "מאוזן/פער קל" כשבאמת יש פער — או להפך. זו טעות אמת בכסף, אבל **התיקון הוא שורה אחת**, בטוח לחלוטין לקבצים הנעולים.
- **ה"L50" מטעה? כן, חלקית.** כשיש רק 9 עסקאות המערכת עדיין כותבת "L50(50)" — כאילו יש 50. באחת השורות כן מוצג המספר האמיתי, אבל הכותרת והמדחום משקרים. אין שום "מדגם קטן מדי". כבר קיים בקוד כלי יושר מוכן (`get_sample_size_context`) — רק לא חיברו אותו.
- **אלגו מופרד נכון? כן — היכן שזה קריטי.** Win Rate / תוחלת / מד החום / המלצת הסיכון **לא** מזוהמים מאלגו (ההפרדה תקינה, DEC-20260511-001 #8 מוחזק בקוד; אלגו נשאר *בקרה בלבד*, אין יציאה ידנית). הפגם היחיד: שורת "סה\"כ רווח" מוצגת כוללת אלגו (מתויג "(all)" — מגולה, לא מוסתר) ונכנסת לחישוב ההתאמה הפגום מעלה.
- **המלצה ראשונה:** לתקן קודם את **R-ALGO-2** (באג ההתאמה — אמת בכסף, שורה אחת, בטוח), ומיד לצידו את **R-ALGO-3** (יושר ה-L50 — סיכון אפסי). השאר (השערים על העלאת הסיכון, מכונת ההשעיה/Kill-Switch) — רק אחרי שתבחר היקף, ולפי מסמך כללי-האלגו הפורמלי כשיגיע.

## מה צריך לעשות

1. **לבחור היקף** — שום קוד לא רץ עד שתאשר. ברירת המחדל המומלצת: Tier-B `R-ALGO-2` + Tier-A `R-ALGO-3` בלבד, כ-Phase ממשל אחד קטן.
2. **R-ALGO-2** — תיקון מפתח אחד (`"net_pnl"`→`"total_pnl_usd"`) + מבחן השוואה ראשון לחדר־מצב (אין כיסוי כיום) + הערת יושר על ההפרש השיורי "סגור מול הכל". הוכחה: LOCKED April זהה בית-לבית.
3. **R-ALGO-3** — לחבר את `get_sample_size_context` הקיים; N≥50 ⇒ מחרוזת זהה בית-לבית, N<50 ⇒ "מדגם N/50 — קטן מדי".
4. **Tier-C** (`R-ALGO-1/6/8/5/7`) — נשאר מושהה, founder-gated, כל אחד Phase ממשל נפרד עם הוכחה נקובה; יתבסס מחדש כשמסמך כללי-האלגו הפורמלי מגיע (תלות מתועדת בצ'רטר §0).
