# SPRINT-28 — MARK FINDINGS · Re-run of the Sprint-26 hands-on stress-test on the post-Sprint-27 LIVE system (DOC-ONLY, NO code)

**Owner:** Mark (methodology & gate lead). **Date:** 2026-05-18.
**Target:** production LIVE on HEAD `168aaa2` (clean tree; Sprint-27 W1/W2/W3/W4
landed; 6 Docker services healthy, secure_runner active).
**Method:** I cannot click a live UI. Each scenario is traced from the CURRENT
SOURCE (exact executed code paths at `168aaa2`) + the named regression/proof
tests **executed by me as the executed behavior**.

**CI-equivalent re-run on the clean committed tree (exact CI command + CI env):
`pytest --tb=short -q --cov=engine_core --cov=adaptive_risk_engine
--cov=analytics_engine --cov=addon_risk_engine --cov-report=term
--cov-fail-under=67` ⇒ 2088 passed, 0 failed, coverage 72.02% ≥ 67%.**
The SPRINT27_W3W4C_IMPL headline (2088/0/72.02%) reproduces byte-for-byte.
LOCKED April regression in isolation: 2/2. B1 disclosure in isolation: 17/17.
(A 6-failure cluster appears ONLY in an ad-hoc cross-file run order — each
file is GREEN alone and under the authoritative default CI ordering; this is
the SAME pre-existing collection-order state-bleed the W1/W3 impl docs already
documented, NOT a Sprint-27 regression. The authoritative CI command is
0-failed.)

Research substrate: `SPRINT28_RESEARCH_DOSSIER.md` is **absent**; per the
prompt I derived from `SPRINT26_RESEARCH_DOSSIER.md` + `MODULE_MAP.md` +
`DATA_CONTRACTS.md` + the `SPRINT27_*_IMPL` docs + all binding `MARK_*`
rulings (Sprint-25 still binding; Sprint-26 P1-1/P3-1 carried).

---

## Per-scenario verdict (re-simulated from current source, incl. the Sprint-27 surfaces)

| # | Scenario | Path traced @ `168aaa2` | Verdict |
|---|----------|-------------------------|---------|
| 1 | Week with closed campaigns | `analytics_engine.compute_period_analytics`→`compute_verdict`→`report_renderer.build_summary_text` normal branch (`:582 lines = list(_whatnow)+[…]`) | ✅ Correct. LOCKED April 8/+$180.49/WR.375/PF2.6262/excl2 byte-identical (2/2 isolated; the frozen-literal pin now asserts `body == _pre_w3_body` so every KPI line below the prepend is byte-for-byte pre-W3). ALGO/DATA_INCOMPLETE excluded from WR/Exp/PF. The W3 line is **prepended only** — zero math touched. |
| 2 | 0 closed + live open book | `build_summary_text` `campaigns_closed==0 and open_book is not None`→`report_open_book.empty_state_lines` Case A; W3 `head=list(_whatnow)+[…]` | ✅ Correct + honest. Never "ללא עסקאות" with a live book; price-fallback per-symbol surfaced; the W3 `neutral` line explicitly says "אין עסקאות שנסגרו… **זה לא אומר שהכול תקין/לא תקין**" — the exact silence≠all-clear disambiguation a disciplined trader needs. Strong methodology fit. |
| 3 | Stale/fallback NAV — **Telegram/report** | `account_state.load` (canonical, NAV-Unify intact) → `_nav_disclosure_lines`; W3 `_account_state_broker_fresh` reuses the SAME B1 gate; `_WHATNOW_NAV_NOT_FRESH` leads "המספרים מבוססים על NAV לא-חי… כהערכה, לא כאמת מדויקת" | ✅ Correct + improved. The companion line now itself caveats an estimated NAV before giving the verdict — accuracy>confidence, exactly my doctrine. |
| 3b | Stale/fallback NAV — **Dashboard sidebar** (the Sprint-26 P1-1 gap) | `dashboard.py:111 acc_state.load()` (canonical single source) → `:112 saved_nav=float(_acc["nav"])` → `:114 nav_sidebar_render(_acc)` → `:115-118` `success` ONLY iff broker+fresh else `st.sidebar.warning` | ✅ **NOW CORRECT — P1-1 CLOSED.** See the dedicated section below. The unconditional green "Live IBKR NAV" box is gone; the bare-`except` divergent reader no longer drives the prominent figure. |
| 4 | Price-fallback symbol | `ec.get_live_price()→None`; `telegram_portfolio.py:296 price_is_fallback=curr is None`; `:522 PRICE_FALLBACK_LABEL`; report `price_fallback_warning_lines` | ✅ Correct. Per-figure binary on the actual `None`, never a guess; surfaced in active + passive surfaces. Unchanged by Sprint-27. |
| 5 | ALGO-observed position | `is_algo_position`; `evaluate_position_engine`→observation-only; W3 digest `[ALGO]` tag preserved; ALGO never in WR/Exp/PF | ✅ Correct. Best-implemented invariant; W3 did not perturb it (digest bullet body byte-identical, pinned). |
| 6 | Missing-stop campaign | `get_campaign_risk_metrics`→`valid=False`; analytics→DATA_INCOMPLETE (excluded); `risk_monitor:654` explicit "סטופ מקורי חסר" alert | ✅ Correct + honest. NOT silent-zeroed into stats. Residual P3-1 nit unchanged (see below) — RECOMMEND-only, disambiguated by the adjacent explicit alert. |
| 7 | Add-On + B3 race (humanized wording) | `telegram_callbacks.py:317 planned_cid` / `:318 resolved_cid` / `:320 resolved!=planned` ⇒ clear pending + humanized refuse + **`return` BEFORE any Supabase write** | ✅ Correct — still 100% honest, ZERO write. New wording (`🛡️ עצרתי את החיזוק… התחלפה… לא כתבתי כלום, כדי להגן על הכסף שלך… הרץ /addon מחדש`) states WHAT changed and **explicitly that nothing was written** — protection framing, no false reassurance. Refusal pinned EQUALLY strict in `test_phase_b3_addon_cid.py` (updated NOT weakened). |
| 8 | Dev-PIN gate C1 (humanized expiry) | `telegram_bot.py:155 _require_active_dev_session`: `:183` unconfigured `DEV_PIN`⇒DENY (S-2), `:193` no/expired session⇒route to `awaiting_dev_pin`+`return False` (S-1/S-3) | ✅ Correct — still fail-CLOSED. New wording (`🔐 צריך PIN פעיל… הפגישה שלך פגה (תוקף 30 דק' לאבטחתך) — לא בוצעה שום פעולה… הזן את ה-PIN ונמשיך מכאן`) is warmer yet still states plainly the session expired AND **no action ran** — zero TTL/compare touched. Secure_runner outer admin gate intact. |
| 9 | Duplicate trade row (F4) | 3-site `drop_duplicates(subset=["trade_id"],keep="first")` | ✅ Correct. Untouched by Sprint-27 (no byte-locked file changed). |
| 10 | 1%-residual partial fill (F5) | `adaptive_risk_engine` residual `>= 0.01` | ✅ Correct. Untouched. |
| 11 | Positive-qty SELL export (C2) | `engine_core.split_side_first` side-string classifier | ✅ Correct. Untouched. |
| 12 *(NEW Sprint-27 surface)* | "🧭 מה עכשיו?" on weekly/monthly + חדר-מצב + daily digest | `report_renderer.whatnow_line` (`:241`, prepended `:506`); `telegram_portfolio.py:540-552` (`decision_syms` from already-computed engine `status`, prepended `:552`); `risk_monitor.py:446-458` (`urgent` lifted before the loop, byte-identical predicate, inserted `lines[1]`) | ✅ Correct, additive, never wrong/contradictory, **genuinely helpful** — see the dedicated assessment below. |
| 13 *(NEW Sprint-27 surface)* | Empty open-book / 0-rows surfaces | `telegram_portfolio.py:242 open_pos.empty`⇒"📭 אין פוזיציות פתוחות כרגע… זה לא אומר שהכול תקין/לא תקין… בדוק סנכרון נתונים"; W3 `neutral` report line; digest "{n} פוז' תחת מעקב, אין פעולה דחופה" (never "הכול תקין") | ✅ Correct + honest. The old green-✅ "all-clear" read on an empty surface (a real methodology trap — silence misread as confirmation) is closed. |

---

## Is the Sprint-26 P1-1 dashboard gap now CLOSED? — **YES, cleanly.**

**P1-1 (Sprint-26):** `dashboard.py` rendered `🏦 Live IBKR NAV` in a green
`st.sidebar.success` box **unconditionally** — even for a stale / no-timestamp
/ silent $7,500 fallback NAV, fed by its own bare-`except` `load_settings()`
(`dashboard.py:46-52`) divergent from the canonical resolver.

**Verified closed at `168aaa2` by tracing the executed path:**

1. **Canonical single source.** `dashboard.py:111 _acc = acc_state.load()` —
   the prominent NAV figure (`:112 saved_nav = float(_acc["nav"])`, then
   `current_acc_size`, `target_risk_usd`, every downstream KPI) now reads the
   **same canonical `account_state.load()`** the Telegram B1 path uses. The
   bare-`except` `load_settings()` no longer drives the prominent figure (it
   survives only for the two `number_input` widget defaults + the secondary
   Sprint-15 caption — see NEW-1 below; not the headline NAV).
2. **Honest render.** `dashboard.py:114 nav_sidebar_render(_acc)` →
   `dashboard_nav.py:51` gate `broker_fresh = nav_source=="broker" and
   freshness=="fresh" and not is_stale and ok` — **byte-identically the same
   gate** as `report_renderer._nav_disclosure_lines` (B1). broker+fresh ⇒
   `("success", "🏦 Live IBKR NAV: **$X**")` → green box, BYTE-IDENTICAL to
   pre-W1. ANY other state (deposited / fallback / stale / critical / no
   timestamp / `ok=False` / non-dict) ⇒ `("warning", …)` → a NON-green
   `st.sidebar.warning` reusing the **verbatim** already-honest
   `freshness_label` + the NAV source + "ערך מוערך/לא-עדכני — לא נתון מדויק".
3. **Zero math / KPI change.** `nav_sidebar_render` is a pure stdlib helper:
   no R/NAV/Expectancy/sizing computation, invents no field. The byte-locked
   files are git-diff-EMPTY; the LOCKED April regression is byte-identical
   (2/2 isolated). This is a presentation-only honesty closure — exactly the
   Sprint-25 B1 pattern I asked for, applied to the dashboard, **not a
   rewrite, not an addition.**
4. **Proven as executed behavior.** `tests/test_sprint27_w1_dashboard_nav
   _honesty.py` (24 tests, GREEN in the 2088): broker+fresh ⇒ text
   byte-identical to the literal pre-W1 f-string, NO disclosure; REAL config
   files (missing / corrupt / no-timestamp / stale / fresh-broker) driven
   through the REAL `account_state.load()` then the helper ⇒ honest warning,
   never a green "Live" box; a wiring test pins that `dashboard.py` imports
   the helper + `acc_state.load()` and the old bare-except success box is gone.

**Verdict: P1-1 is genuinely CLOSED.** The exact "fallback-as-truth on the
trader's main screen" honesty breach that cost the 4 points in Sprint-26 is
fixed at the root, with the canonical single source, byte-identical happy
path, and a named proof — clean, no regression, no scope creep.

---

## The "🧭 מה עכשיו?" companion line — is it correct, additive, never wrong, and does it actually help?

I held this to my hardest bar: a companion line is **worse than nothing** if
it can ever be wrong, contradict the body, or train the trader to read a
reassurance that isn't earned. Traced on all three surfaces:

- **Weekly/monthly report (`report_renderer.whatnow_line`):** derived ONLY
  from `verdict_class` (the value `analytics_engine.compute_verdict` ALREADY
  returns — `strong`/`mixed`/`defensive`/`neutral`, capture changed
  `verdict,_ → verdict,verdict_class`; verdict text + semantics untouched) +
  the SAME broker-fresh signal B1 already derives. `_WHATNOW_BY_CLASS` covers
  all four classes with a `mixed` fallback for any unknown ⇒ **cannot crash,
  cannot contradict the verdict** (it IS the verdict's class). `neutral`
  (0-closed) explicitly says "זה לא אומר שהכול תקין/לא תקין" — the honest
  empty-state read. NAV-not-fresh prepends the estimate caveat FIRST. Pinned
  byte-identical body (`got.split("\n",2)[2] == _pre_w3_body`).
- **חדר-מצב (`telegram_portfolio.py`):** `decision_syms` collected from the
  **already-computed engine `status`** during the existing loop (the EXACT
  `_WHATNOW_CRITICAL` set = `risk_monitor.CRITICAL_STATUSES`) — no new
  computation, no new data read. "{n} פוז' דורשות החלטה: … — ראה כרטיסים
  למטה" else "{n} פוז' במעקב, אין מצב קריטי — … אין פעולה דחופה". If
  `nav_stale_label` it leads with "שים לב — NAV לא חי … קרא R/חשיפה כהערכה".
  The whole `msg` body is unchanged; the line is the LAST thing prepended
  (`:552`), so it reflects the final computed state.
- **Daily digest (`risk_monitor._daily_digest_text`):** `urgent` lifted to a
  list-comp BEFORE the loop with the **identical predicate/order** the footer
  already used (provably byte-identical body, pinned). "{n} פוז' דורשות
  החלטה…" else "{n} פוז' תחת מעקב, אין פעולה דחופה" — **never "הכול תקין"**
  (no false all-clear).

**Assessment:** It is **correct, strictly additive, and never wrong or
contradictory** — every variant is a faithful summary of a signal the surface
already computed and already displays below. It is **not noise**: it converts
three surfaces that previously front-loaded layout/raw-data (forcing the human
to reconstruct "am I OK, what do I do?") into surfaces that lead with the one
disciplined-trader question. Critically it is **honest under uncertainty** —
it caveats a non-fresh NAV before the verdict, and it refuses to say
"everything is fine" on empty/zero surfaces. This is methodology-positive: it
nudges toward the verdict→action loop without inventing certainty. I would
keep it.

---

## Anything NOT 100/100 / any Sprint-27-introduced regression (brutally honest)

### Sprint-26 P1-1 — **CLOSED** (was the ONE gap; now fixed cleanly, see above).

### Sprint-26 P3-1 — Open-R `0.0R` when no risk basis — **STILL OPEN (unchanged), P3 RECOMMEND-only**
`risk_monitor.py:679` still `open_r = (… if original_campaign_risk > 0 else
0)`; rendered `:736` `Open R: \`0.0R\``. Sprint-27 correctly did NOT touch
this (out of W1–W4 scope; it is a P3 nit, RECOMMEND-only, and the adjacent
explicit "סטופ מקורי חסר" alert disambiguates it on the same card). **Not a
regression; consistent with my Sprint-26 ruling and the Sprint-27 scope.** It
remains the only stylistic honesty nit — it does not block 100/100 (a P3
RECOMMEND was never a gate item; P1-1 was the gate).

### NEW-1 — Dashboard secondary risk-capital-basis caption still reads the OLD `settings` (LOW observation, NOT a regression, NOT a P1)
`dashboard.py:132 _nav_source = "broker" if "nav" in settings else
"deposited"` feeds the Sprint-15 `fmt_risk_capital_basis` **caption** —
`settings` is still the old bare-`except` `load_settings()` dict, NOT the
canonical `_acc`. **Why this is not the P1-1 class and not a regression:**
(a) it pre-dates Sprint-27 (Sprint-15 code); W1's tight scope explicitly left
the Sprint-15 caption untouched (documented in `SPRINT27_W1_IMPL.md`); (b) it
is a *basis-label* caption ("risking X% of NAV/deposited"), it **never claims
"Live"** and never presents a fallback NAV figure as exact — the prominent NAV
box and `current_acc_size`/`target_risk_usd` are all canonical; (c) the only
realistic divergence is the `nav_source` *word* in a secondary caption when
`sentinel_config.json` shape differs between the two readers — cosmetic, not a
fallback-as-truth money breach. **Severity: P3/LOW, CLOSURE-FIX-minor,
RECOMMEND-only** — for a future tidy-up, point `:132` at `_acc["nav_source"]`
(one line, reuses canonical, zero math). It does **not** reopen P1-1 and does
**not** block 100/100.

### Observations (NOT defects — confirmed correct by design)
- W2 (config untrack) verified: `git ls-files` shows `sentinel_config.json`
  is **no longer tracked** (only `sentinel_config.example.json` is);
  `.gitignore:3` now bites; the live working copy is preserved on disk. The
  data-loss-on-rollback risk (Ops O1) is closed at the repo layer; the
  host-safe step remains the founder's runbook item as scoped.
- W4c verified: `telegram_bot.py` routes the lone residual raw read through
  `repo.get_all_trades`; the C1 guard / admin gate / B3 `_planned_cid` are
  untouched; parity pinned (8 tests GREEN). Read-only, byte-identical.
- W3 prepend is symmetric on every surface ⇒ B1's `broker_fresh == pre_b1`
  equalities still hold; the frozen-literal pin was **updated NOT weakened**
  (same precedent as the Sprint-25 C1 test correction). No existing test
  relaxed.
- The cross-file 6-failure cluster is the SAME pre-existing collection-order
  state-bleed documented in the W1/W3 impl docs (each file GREEN alone +
  under the authoritative default CI ordering = 2088/0). NOT a Sprint-27
  regression; the authoritative CI command is the gate and it is 0-failed.

---

## למנכ״ל — חוות דעת אישית של מארק (שפה פשוטה)

מנכ״ל, חזרתי על אותו מבחן שעשיתי בספרינט-26 — תרחיש אחרי תרחיש — הפעם על
המערכת החיה אחרי ספרינט-27.

**האם אני סומך עליה עכשיו במלואה כשותפה למסחר שלי? כן. עכשיו זה 100/100.**

בספרינט-26 הייתה נקודה אחת ויחידה שמנעה את ה-100: הדשבורד, המסך שאני מסתכל
עליו הכי הרבה, כתב **"Live IBKR NAV"** בקופסה ירוקה — *גם* כש-NAV ישן, *גם*
כשאין חותמת זמן, *גם* כשהמערכת נפלה ל-$7,500 ברירת-מחדל. זו הייתה הפרת כנות
על המסך הכי חשוב, ובדיוק מה ש-CLAUDE.md אוסר.

**עכשיו זה סגור — נקי.** עקבתי אחרי הקוד החי: הדשבורד קורא היום בדיוק את אותו
מקור קנוני שהטלגרם קורא (`account_state.load()`), והקופסה הירוקה "Live"
מופיעה **רק** כשה-NAV באמת חי ומהברוקר. בכל מצב אחר — ישן, קריטי, בלי חותמת,
ברירת-מחדל — מופיעה הודעה כתומה כנה שאומרת במפורש "ערך מוערך/לא-עדכני — לא
נתון מדויק". זה בדיוק התיקון שביקשתי, באותה תבנית של B1, בלי שום שינוי
במתמטיקה, עם הוכחה אוטומטית. הרצתי בעצמי את כל מערך הטסטים על העץ הנקי:
**2088 עברו, 0 נכשלו, כיסוי 72%** — כולל ה-LOCKED של אפריל byte-identical.

ומעבר לתיקון — ספרינט-27 הוסיף את שורת **"🧭 מה עכשיו?"** בראש הדוח השבועי/
חודשי, חדר-המצב, והסיכום היומי. בדקתי אותה קשה: היא **תמיד נכונה, אף פעם לא
סותרת את הגוף, ולא רעש** — היא רק מרימה למעלה את השאלה שסוחר ממושמע שואל
ראשונה ("מה מצבי ומה לעשות?"). וכשה-NAV לא חי, היא אומרת את זה *לפני* המסקנה.
זה משרת את השיטה שלי, לא מסכן אותה.

**מה שנשאר — שתי נקודות קטנטנות בלבד, לא חוסמות:** (1) הנ​יט מספרינט-26 של
`Open R: 0.0R` כשאין בסיס סיכון — עדיין שם, RECOMMEND בלבד, ויש לידו התראת
"סטופ מקורי חסר" מפורשת שמבהירה אותו. (2) כיתוב-משנה אחד בדשבורד (basis,
מספרינט-15) עדיין קורא את הקובץ הישן — אבל הוא לא טוען "Live" אף פעם ולא מציג
NAV מזויף כאמת; קוסמטי. אף אחת מהשתיים אינה הפרת כנות ואף אחת לא הייתה אי-פעם
תנאי-שער. ה-P1 — הנקודה היחידה שמנעה 100 — סגור.

**זה 100/100 אמיתי בשבילי.** המנוע נכון, הטלגרם ישר, הדשבורד עכשיו ישר, וה-
"מה עכשיו?" הופך את המערכת לבן-לוויה אמיתי, לא רק לוח-מחוונים.

## מה צריך לעשות

1. **לפרוס/לאשר את ספרינט-27 כפי שהוא — אין חסם.** P1-1 סגור נקי, byte-locks
   שלמים, 2088/0, אין רגרסיה. זה ה-100/100.
2. **לא לגעת בשום דבר נוסף עכשיו.** המנוע, הטלגרם, B3/C1/F4/F5/C2/Arch-F1/
   NAV-Unify — סגורים ונכונים. ברירת-המחדל של Mark נשמרת: ללא rewrite, ללא
   תוספות.
3. **שתי משימות תחזוקה ל-backlog (לא דחוף, RECOMMEND בלבד, לא חוסם 100):**
   (a) P3-1 — להחליף `Open R: 0.0R` ב-`Open R: — (אין בסיס סיכון)` כשאין בסיס
   סיכון, עקבי עם הספר הפתוח; (b) NEW-1 — להפנות את `dashboard.py:132`
   `_nav_source` ל-`_acc["nav_source"]` (שורה אחת, מקור קנוני, אפס מתמטיקה)
   כדי שגם כיתוב-המשנה יקרא מהמקור הקנוני. שתיהן P3, נחמדות-שיהיו, לא תנאי.
4. **לזכור: הצעד הבטוח של W2 בהוסט הוא עדיין באחריותך** (גיבוי
   `sentinel_config.json` לפני ה-pull שמנתק את ה-tracking, ואיסור
   `git reset --hard`/`git checkout .` על הוסט הפרודקשן) — כפי שתועד ב-runbook.
