# SPRINT-26 — MARK FINDINGS · Live-System Stress Test (DOC-ONLY, NO code)

**Owner:** Mark (methodology & gate lead). **Date:** 2026-05-17.
**Target:** production `main` `8c5a948` (clean tree; Sprint-25 + C2/B3/B1/Arch-F1/
Engine-P2P3/NAV-Unify all landed; 5 Docker services wired, secure_runner active).
**Method:** I cannot click a live UI, so each scenario is traced from SOURCE
(exact executed code paths) + the named regression proofs as the executed
behavior. **CI-equivalent re-run on the clean committed tree: 2039 passed,
0 failed, coverage 72.02% ≥ 67%** — the locked-path/headline claims in the
PHASE_*_IMPL docs reproduce.

Research-team substrate: `SPRINT26_RESEARCH_DOSSIER.md` is **absent**; per the
prompt I derived from `MODULE_MAP.md` + `DATA_CONTRACTS.md` + the PHASE_*_IMPL
docs + `MARK_SPRINT25_RULINGS.md` (still binding).

---

## Per-scenario verdict

| # | Scenario | Path traced | Verdict |
|---|----------|-------------|---------|
| 1 | Week with closed campaigns | `analytics_engine.compute_period_analytics` → `_get_closed_campaigns` (ANY in-window SELL) → `_aggregate_campaigns` → countable filter; renderer `build_summary_text` | ✅ Correct. LOCKED April 8/+$180.49/WR.375/PF2.6262/excl2 byte-identical; ALGO/DATA_INCOMPLETE excluded from WR/Exp/PF (#8). Methodology-fit: R-first, honest. |
| 2 | Week with 0 closed but a live open book | `build_summary_text` `campaigns_closed==0` branch → `report_open_book.empty_state_lines` Case A | ✅ Correct + honest. Never says "ללא עסקאות" with a live book; states opened-in-period vs held-over; ALGO segregated; price-fallback symbols surfaced (Sprint-25 B1). Strong methodology fit. |
| 3 | Stale / fallback NAV — **Telegram/report** | `account_state.load` (canonical) → `_nav_disclosure_lines`; bot `get_nav_and_risk` → `stale_label` → `telegram_portfolio:205` | ✅ Correct. Fallback/stale/critical/unknown disclosed verbatim; KPIs flagged "מוערך/לא-עדכני, לא נתון מדויק". |
| 3b | Stale / fallback NAV — **Dashboard sidebar** | `dashboard.py:44-50 load_settings` (bare `except`, silent $7,500) → `dashboard.py:107 st.sidebar.success("🏦 Live IBKR NAV: $X")` | ❌ **NOT 100/100.** See P1-1 below. The dashboard's primary visual surface labels ANY NAV "Live" in a green box — stale, critical, no-timestamp, or the $7,500 fallback — with no freshness banner. The fix shipped for Telegram (B1) was never applied here. |
| 4 | Price-fallback symbol | `get_live_price()→None`; open-book `price_is_fallback`; `telegram_portfolio:148-152` `PRICE_FALLBACK_LABEL`; report `price_fallback_warning_lines` | ✅ Correct. Per-figure binary on the actual `None`, never a guess; symbol listed in both active + passive surfaces. |
| 5 | ALGO-observed position | `is_algo_position` (setup primary, symbol fallback); `evaluate_position_engine` → "מנוהל חיצונית — בקרה בלבד"; open-book `open_book_algo` segregated; risk_monitor generic push gated for `algo_observed` | ✅ Correct. ALGO never in WR/Exp/PF; Structure-R = "—" not 0.00R; observation-only label; never an instruction. Exemplary segregation. |
| 6 | Missing-stop campaign | `get_campaign_risk_metrics` → `valid=False`; analytics → DATA_INCOMPLETE (excluded); risk_monitor:654 explicit "סטופ מקורי חסר" alert; `telegram_portfolio:112` "חסר סטופ התחלתי" | ✅ Correct + honest. Not silent-zeroed into stats; trader is told to fix `initial_stop`. Minor nit P3-1 (display `0.0R`). |
| 7 | Add-On flow incl. B3 race | `_handle_addon_command` persists planned `campaign_id`; `telegram_callbacks` 3-case guard (2a proceed / 2b HARDENED refuse-zero-write / 2c legacy) | ✅ Correct. Divergent-cid race ⇒ explicit Hebrew refusal + ZERO Supabase write; also correctly refuses when the campaign closed (resolved=None ≠ planned). Data-integrity sound. |
| 8 | Dev-PIN gate (C1) | `_require_active_dev_session` fail-CLOSED at every privileged handler incl. the XML→Supabase/NAV write entry; unset `DEV_PIN` DENIES | ✅ Correct. Secure_runner outer admin gate intact; defence-in-depth. |
| 9 | Duplicate trade row (F4) | 3-site guarded `drop_duplicates(subset=["trade_id"], keep="first")` (analytics/adaptive/engine) before side-split & `pnl_usd` sum | ✅ Correct. Re-exported SELL no longer double-counts PnL/R nor phantom-opens; provable identity on unique-id prod data. |
| 10 | 1%-residual partial fill (F5) | `adaptive_risk_engine` residual close-test `>= 0.01` | ✅ Correct. Exactly-1% residual is NOT closed (one share still open) — matches the disciplined "campaign open until flat" mental model. |
| 11 | Positive-qty SELL export (C2) | `engine_core.split_side_first` side-string classifier (qty is magnitude-only) used by adaptive + open-positions | ✅ Correct. A broker positive-qty SELL now closes / nets to 0 instead of silently never-closing or phantom-opening. |

---

## Methodology-fit assessment (R-first, no silent-zero, ALGO segregated, drawdown protection)

- **R-first:** PASS. 1R denominator = first-BUY `(entry−initial_stop)×qty+fees`,
  cent-rounded and load-bearing (F7); add-ons never inflate it
  (`get_campaign_risk_metrics` uses base_price/base_qty). Net-R / Expectancy /
  PF computed only on stat-countable campaigns.
- **No silent-zero:** PASS in the engine + Telegram + reports (honest
  zeros distinguishable from defective zeros — DEC-019 tz class closed;
  missing-stop → explicit alert, DATA_INCOMPLETE, never a fake countable 0).
  **Partial gap on the dashboard sidebar NAV (P1-1):** a fallback $7,500 is
  rendered as a confident green "Live IBKR NAV" — a silent-fallback-as-truth
  on the most-looked-at surface.
- **ALGO segregated:** PASS, consistently and rigorously (engine, adaptive,
  analytics, dashboard ALGO-Drag, open-book, risk_monitor generic-push gate,
  daily digest `[ALGO]` tag). Best-implemented invariant in the system.
- **Drawdown protection:** PASS. Risk-deviation (loss-only), Giveback
  zone-change, Profit-Protection 2R/3R checkpoints, Breakeven protocol,
  Sizing-Leak one-time, Daily Digest — all dedup-flagged, anti-spam
  disciplined, BROKEN gates Giveback. Methodologically faithful to a
  capital-preservation-first trader.

---

## Anything NOT 100/100 (brutally honest)

### P1-1 — Dashboard sidebar presents fallback/stale NAV as exact "Live" truth (methodology + honesty gap)
- **File:line:** `dashboard.py:44-50` (`load_settings`, bare `except: pass`,
  silent `{"total_deposited": 7500.0, ...}` fallback) and
  `dashboard.py:105-107`:
  `saved_nav = float(settings.get("nav", settings.get("total_deposited", 7500.0)))`
  → `st.sidebar.success(f"🏦 Live IBKR NAV: **${saved_nav:,.2f}**")`.
- **What's wrong:** the word **"Live"** + a **green success box** are shown
  unconditionally. If `sentinel_config.json` is missing/corrupt → silent
  $7,500 shown as "Live IBKR NAV". If `nav_updated_at` is 3 days old or
  absent → still green "Live". The dashboard *has* the honest signal
  (`ec.get_nav_with_freshness()`) but uses it only at `:746` for the AI-export
  footer, never for the prominent sidebar figure that drives the trader's
  eyeballed sizing and the on-screen `target_risk_usd` (`:116-117`).
- **Contract violated:** `CLAUDE.md` hard constraint "Do not silently present
  fallback data as exact truth"; `AGENTS.md` #1; `DATA_CONTRACTS.md`
  §"Core principle" + dashboard rule "Must identify fallback/estimated values
  clearly"; the exact class Sprint-25 B1 closed for Telegram — left open on
  the dashboard.
- **Severity:** P1 (a risk-sensitive surface shows fallback/stale as exact;
  not a headline-number corruption — the engine math is correct — but it is
  a real honesty/methodology breach on the trader's main screen).
- **Tag:** CLOSURE-FIX (founder-decision-required) — fixing it changes
  observable dashboard output (a banner appears). Not pure polish; not an
  addition (it reuses the existing `account_state.load()` / freshness fields,
  exactly as the Telegram B1 fix did). RECOMMENDED, not unilateral.
- **Named proof strategy:** mirror `test_report_renderer` B1 disclosure tests
  — a dashboard-sidebar test asserting that for `nav_source!="broker"` OR
  `is_stale` OR `freshness!="fresh"` the sidebar emits the freshness label
  (reuse `account_state.load()`); broker+fresh ⇒ byte-identical (no banner).

### P3-1 — Missing-stop / no-risk-basis Open-R displays as `0.0R` (nit)
- **File:line:** `risk_monitor.py:665` `open_r = (... if original_campaign_risk
  > 0 else 0)`; rendered `:722` `Open R: \`0.0R\``.
- **What's wrong:** the position IS flagged with an explicit "סטופ מקורי חסר"
  alert (honest), but the same card still prints `Open R: 0.0R`, which reads
  like a real flat result rather than "not computable". Low-risk because the
  adjacent explicit missing-stop line disambiguates it.
- **Severity:** P3 nit. **Tag:** CLOSURE-FIX-minor (a token like `Open R: —
  (אין בסיס סיכון)` would be the honest form, consistent with the open-book
  "—" convention) — RECOMMEND only.

### Observations (NOT defects — confirmed correct by design)
- `analytics_engine` `math.inf` PF vs dashboard `99.0` sentinel: two
  intentional conventions (F6) — correctly NOT unified; `pf_str` clamps
  display to "∞" at `>90`. Fine.
- `report_scheduler` weekly/monthly `if/elif`: if the 1st falls on a
  Saturday, weekly fires 08:30 and monthly fires the next minute (08:40)
  once `_already_ran(weekly)` flips the `if` false — both still delivered,
  dedup intact. No defect.
- NAV-Unify D1–D4: the bot/risk-monitor now honor an explicit `nav:0` and the
  strict-`<` 24h/48h boundary (canonical = account_state). Money-positive,
  normal path byte-identical. Good.

---

## למנכ״ל — חוות דעת אישית של מארק (שפה פשוטה)

מנכ״ל, ניסיתי את המערכת כמו סוחר אמיתי, תרחיש אחרי תרחיש.

**האם אני סומך עליה כשותפה למסחר? כן — כמעט לגמרי. עוד לא 100/100.**

המתמטיקה נכונה. R, NAV, Expectancy, Profit Factor, אגרגציית קמפיינים —
כולם תקינים מול החוזה, וההוכחות עוברות (2039 טסטים ירוקים על העץ הנקי).
המערכת **משרתת את המתודולוגיה שלי**: R קודם, אין אפס-שקט שמתחזה לתוצאה,
ALGO מופרד בקפדנות, והגנת הון (Giveback / Profit-Protection / Sizing-Leak /
Daily-Digest) עובדת בלי ספאם. הטלגרם — גם פקודות וגם דוחות אוטומטיים —
**ישר עם המשתמש**: אומר במפורש כשמחיר לא חי, כש-NAV ישן, כשחסר סטופ.
זה בדיוק מה שאני רוצה מבן-לוויה למסחר.

**מה שמפריע לי — נקודה אחת ממשית:** הדשבורד, המסך שאני מסתכל עליו הכי הרבה,
עדיין כותב **"Live IBKR NAV"** בקופסה ירוקה — *גם* כשה-NAV ישן ביומיים,
*גם* כשאין חותמת זמן, ו*גם* כשהמערכת נפלה ל-$7,500 ברירת-מחדל. תיקנתם
בדיוק את הבעיה הזו בטלגרם (B1) — אבל לא בדשבורד. סוחר שמסתכל על מספר ירוק
"Live" ובונה עליו sizing, בזמן שהמספר מיושן או מזויף — זו בדיוק ההפרה
ש-CLAUDE.md אוסר. לא טעות חישוב; טעות **כנות** על המסך הכי חשוב.

זה לא הופך את המערכת ללא-בטוחה — המנוע נכון והטלגרם כן. אבל זה מה שמפריד
בין "מצוין" ל-100/100.

## מה צריך לעשות

1. **לאשר CLOSURE-FIX לדשבורד (P1-1):** להוסיף ל-sidebar באנר עדכניות NAV
   זהה ללוגיקת B1 — לקרוא `account_state.load()` (כבר קיים), ולהציג את
   `freshness_label` כשה-NAV אינו broker+fresh; להחליף את הקופסה הירוקה
   "Live" בצבע/טקסט שמשקף ישן/קריטי/fallback. אפס שינוי במתמטיקה. הוכחה
   נדרשת (טסט sidebar במראה של טסטי B1). זו פעולה ממוקדת, ~יום.
2. **לאשר תיקון-נ​יט (P3-1):** במקום `Open R: 0.0R` כשאין בסיס סיכון —
   להציג טוקן `—` עם "אין בסיס סיכון" (עקבי עם הספר הפתוח).
3. **לא לגעת בשאר:** המנוע, הטלגרם, ה-byte-locks, ALGO, F4/F5/C2/B3/C1,
   NAV-Unify — סגורים ונכונים. אין צורך בשום תוספת. ברירת המחדל של Mark
   נשמרת: Tier-A/CLOSURE-FIX ממוקד בלבד, ללא rewrite.

עם שני אלה (בעיקר #1) — זה 100/100 אמיתי. בלעדיהם זה ~96.
