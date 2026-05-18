# Sprint-28 Engine Findings — 100/100 re-verification of the LIVE money-math on the post-Sprint-27 state (DOC-ONLY, NO code)

**Date:** 2026-05-18 · **Verifier:** Engine team lead
**Verified state:** LIVE on `168aaa2` (`feat(sprint-27): execute Sprint-26
findings — dashboard honesty, repo-hygiene, companion voice, housekeeping`),
clean tree. Parent of the verification is `7ef1c0d` (Sprint-27 SCOPE, DOC-only).
**Method:** re-derived from SOURCE + live throwaway probes + the full
CI-equivalent suite; the Sprint-27 commit diff inspected line-by-line; the
pre-Sprint-27 worktree (`7ef1c0d`) used to PROVE the order-sensitive test
collisions are pre-existing and NOT Sprint-27-introduced.

---

## Verdict: **100/100 on the headline money-math — UNCHANGED by Sprint-27.**

No P0/P1. No correctness regression. No NEW correctness gap. The 3 prior
latent gaps (F3 / F4-edge / neg-qty-BUY) are status-unchanged. No code
recommended this sprint (verification-only).

### Sprint-27 introduced ZERO numeric change — proven by FOUR independent facts

1. **Zero-line diff on every byte-locked / production-critical file.**
   `git diff 7ef1c0d 168aaa2 -- analytics_engine.py engine_core.py
   adaptive_risk_engine.py period_data_probe.py
   tests/test_real_data_april_regression.py tests/_byte_lock_baselines/
   docker-compose.yml telegram_bot_secure_runner.py` ⇒ **0 lines**. The
   Sprint-27 commit's changed-file list does not contain a single
   money-math file. `docs/DATA_CONTRACTS.md` ⇒ 0-line diff.
2. **SHA byte-lock integrity (re-verified live).**
   - `sha256 engine_core.py` == baseline = `d9547622…` ✓
   - `sha256 analytics_engine.py` == baseline = `2da07dea…` ✓
   - `sha256 period_data_probe.py` == baseline = `f86f20e1…` ✓
   - `sha256 tests/test_real_data_april_regression.py` == baseline =
     `10de3256…` ✓
   - `adaptive_risk_engine.py` = `d2e09877…` (unchanged; not in the
     Sprint-27 diff).
3. **LOCKED April regression re-run live — byte-identical.**
   `tests/test_real_data_april_regression.py` ⇒ **2 passed**, asserting
   exactly **8 campaigns / +$180.49 realized / WR .375 / PF 2.6262 /
   excl 2** (manual +$69.34, ALGO −$48.905); weekly 03–09/05 ⇒ **3 ALGO
   excluded / −$37.234, 0 countable**. Byte-identical, GREEN.
4. **W3/W4c are provably non-numeric by construction (source-read).**
   - W3 `report_renderer.py`: a NEW pure helper `whatnow_line()` +
     constants; `compute_verdict` capture changed from `verdict, _` →
     `verdict, verdict_class` (captures a previously-discarded EXISTING
     return value — `compute_verdict` lives in byte-locked
     `analytics_engine.py`, SHA unchanged); both body builders changed
     `head=[…]`/`lines=[…]` → `list(_whatnow) + […]`. Pure PREPEND of
     `[whatnow_line(...), ""]`; every existing body literal/number below
     is byte-for-byte unchanged.
   - W3 `risk_monitor._daily_digest_text`: `urgent` moved from an
     in-loop `.append` to a pre-loop list-comp with the **identical**
     `state ∈ (BROKEN,RUNNER,PROFIT_PROTECTION)` predicate iterating the
     same `rows` in the same order ⇒ provably byte-identical set; the
     per-row bullets + urgent footer are unchanged; companion line
     inserted at `lines[1]` only.
   - W3 `telegram_portfolio.handle_portfolio_room`: `decision_syms`
     collected from the ALREADY-computed `status` string in the existing
     loop (no new computation/data source); line PREPENDED via
     `msg = "🧭 …\n\n" + msg`; the empty-state branch is a disambiguation
     string with no positions present.
   - W4c `telegram_bot.py:874`: `pd.DataFrame(res.data)` →
     `pd.DataFrame(repo.get_all_trades(supabase))`;
     `supabase_repository.get_all_trades` (line 22-23) issues
     `sb.table("trades").select("*").execute().data or []` — the
     **byte-identical query**. The only representational delta is
     `.data` vs `.data or []`; for non-empty rows it is the same list,
     and for `[]`/`None` both produce a `(0,0)` DataFrame
     (`pd.DataFrame(None).equals(pd.DataFrame([]))` is `True`), so the
     `ec.get_open_positions_campaign(df)` input is byte-identical for
     every result shape. C1 guard / admin gate / B3 logic untouched.
   - C1 PIN-expiry + B3 race-refusal: wording-only; fail-closed
     behavior (route to `awaiting_dev_pin`, `return False`; zero
     Supabase write, pending cleared, `return`) byte-unchanged — no TTL/
     compare/return touched.

### Full CI-equivalent (the authoritative deployment gate)
`pytest --tb=short -q --cov=engine_core --cov=adaptive_risk_engine
--cov=analytics_engine --cov=addon_risk_engine --cov-fail-under=67`, CI env,
default ordering ⇒ **2088 passed, 0 failed, coverage 72.02% ≥ 67%** —
exactly the SPRINT27_W3W4C_IMPL.md claim (2039 baseline + 49 new) and the
Sprint-26 floor (72.02%).

### Test-ordering collisions seen in manual sub-orderings — PROVEN pre-existing, NOT a Sprint-27 regression
Two alternate (non-CI) manual `-p no:cacheprovider` sub-orderings showed
spurious failures, both of which are the **known pytest module-mock
cross-contamination** Sprint-26 already documented ("NOT a code defect, NOT
engine-math"), proven independent of Sprint-27 against the pre-27 worktree:

- `test_sprint23_probe_split.py` → `test_heat_in_weekly_report.py`:
  11 fail (a `period_data_probe`/`report_renderer` import-mock leak →
  a `Mock` in `lines` → `"\n".join` TypeError at `report_renderer.py:662`).
  Heat file passes 15/15 alone and 33/33 after `test_sprint22_tz`.
  **Reproduced identically on the pre-Sprint-27 worktree `7ef1c0d`**
  (same 11 fail / 19 pass) ⇒ pre-existing.
- `test_phase_b3_addon_cid.py` → `test_sprint25_b1_fallback_disclosure.py`:
  4 fail (B3's `supabase`/`account_state` module-mock leaks → B1's real
  `account_state.load()` returns `ok=False`). B1 file passes 17/17 alone;
  W1→B1 passes 41/41; W3→B1 34/34; W4c→B1 25/25.
  **Reproduced identically on the pre-Sprint-27 worktree `7ef1c0d`**
  (same 4 fail) — both files predate Sprint-27 ⇒ pre-existing. NOTE: the
  failing `test_april_numbers_unchanged_b1_is_analytics_free` runs against
  a **mocked** account_state, NOT the LOCKED
  `test_real_data_april_regression.py` (which passes clean with the real
  8/+$180.49/WR.375/PF2.6262 numbers). SPRINT27_W1_IMPL.md already
  documented this B1 test as order-sensitive in the shared tree,
  independent of W1.

The authoritative CI command (default ordering, the deploy gate) is
**0-failed**. These collisions are a pre-existing test-hygiene debt, not a
money-math defect and not Sprint-27-caused.

---

## Prior latent gaps — status UNCHANGED (none corrupt today's KPIs)

| Gap | Location (re-verified, byte-locked, SHA-MATCH) | Status |
|---|---|---|
| **Gap-1 F3** — NaN-`pnl_usd`→$0 silent coercion | `analytics_engine.py:361` `pd.to_numeric(...).fillna(0)` over `pnl_usd` — UNCHANGED (SHA `2da07dea…`) | **OPEN, latent, deferred** — not observed in prod (DEC-019 clean); LOCKED April has clean pnl ⇒ byte-identical. Founder-gated future fix. |
| **Gap-2 F4-edge** — legitimate shared exec-id 2nd partial silently dropped | `analytics_engine.py:422`, `adaptive_risk_engine.py:148`, `engine_core.py:528` `drop_duplicates(subset=["trade_id"],keep="first")` — UNCHANGED | **OPEN P2, latent** — DOC-only DATA_CONTRACTS §F4 amendment recommended; correctly NOT done in Sprint-27 (out of scope, DATA_CONTRACTS 0-line diff). |
| **Gap-3 neg-qty BUY** — raw-signed `base_qty` in open-book view | `engine_core.py:538-539` raw signed `.sum()` (not `.abs()`) — UNCHANGED (SHA `d9547622…`) | **P3, no documented trigger** — auto-excluded as DATA_INCOMPLETE; no KPI impact; no real-row trigger. |

No NEW correctness gap found. Sprint-27 is the lowest-risk class of change
(presentation prepend + read-only repo swap + wording) and it touched zero
money-math byte.

---

## למנכ״ל — בשפה פשוטה

**האם מספרי הכסף עדיין אמינים, ולא השתנו מהעבודה של אתמול? כן — לשני
החלקים.**

בדקנו מחדש, משורת-הקוד ולא מהמסמכים, את כל חישובי הכסף החיים אחרי
העבודה של אתמול (Sprint-27): רווח/הפסד, R, אחוז הצלחה, תוחלת,
Profit Factor, NAV, סיכון, חיתוך אוטומטי בירידה, והפרדת ALGO. הרגרסיה
הנעולה של אפריל יצאה **בדיוק אותו דבר** — 8 קמפיינים / +180.49$ /
37.5% הצלחה / PF 2.6262. **שום מספר לא זז.**

העבודה של אתמול הייתה תצוגתית בלבד: שורת "מה עכשיו?" קצרה שנוספה
**מעל** הדוחות (לא נוגעת באף מספר קיים), החלפה פנימית של שאילתת נתונים
שמחזירה **בדיוק אותו דבר**, וניסוח חם יותר להודעות אבטחה (ההתנהגות
זהה). הוכחנו זאת בארבע דרכים בלתי-תלויות, כולל שקבצי המנוע הקריטיים
לא נגעו בהם אפילו בתו אחד (אותו SHA, diff באורך אפס).

שלוש ההסתייגויות התיאורטיות הישנות (שורת pnl פגומה → 0$ בשקט; מזהה
מילוי-חלקי כפול לגיטימי; קנייה בכמות שלילית) **נשארו בדיוק כפי שהיו** —
אף אחת לא קורית בנתונים שלך, אף אחת לא משפיעה על מספר בדוח, ואף אחת לא
נגעה בה אתמול. אין פרצה חדשה.

## מה צריך לעשות

1. **כלום דחוף.** המספרים אמינים *וגם* לא השתנו מאתמול; אפשר להמשיך
   לסחור ולסמוך על הדוחות.
2. **בדיקת-הצלבה ידנית אחת (כמו תמיד, לא חדש):** הצלב פעם בשבוע את
   ה-**רווח/הפסד הממומש הכולל** (Realized PnL) של התקופה מול דף ה-IBKR.
   זו עדיין הנקודה התיאורטית היחידה שבה שורה פגומה אחת מהברוקר עלולה
   להיכנס בשקט (Gap-1). כל שאר המספרים מוגנים בבדיקות נעולות.
3. **חוב-תחזוקה (לא דחוף, לא מספרי):** יש התנגשות בין קבצי-בדיקה
   מסוימים בסדר-הרצה ידני (לא בסדר ה-CI הרשמי) — קיימת מלפני
   Sprint-27, לא נובעת ממנה, לא משפיעה על מספר. שווה ניקוי-בדיקות
   מבוקר בעתיד.

---

## Recommendation (conservative — DOC-ONLY sprint)

**P0/P1-live: NONE.** The deployed engine/analytics/adaptive/NAV math is
**100/100 on every headline money number** and byte-identical on the LOCKED
April + weekly pins (re-verified live). **Sprint-27 changed no number** —
proven by the 0-line byte-locked diff, the unchanged SHA baselines, the
byte-identical LOCKED April re-run, and the by-construction
prepend/read-only-swap source analysis. The 3 prior latent gaps (F3 / F4-edge /
neg-qty-BUY) are status-unchanged and founder-gated; they remain DEFERRED,
untouched, with no current trigger or KPI impact. The single highest
value÷risk *future* item remains Gap-1 (F3, additive disclosed-exclusion
counter, byte-identical against LOCKED April), still requiring explicit
founder + Mark go-ahead and the full governed byte-lock ritual. The only
real, separate finding is the pre-existing test-mock-ordering hygiene debt
(not money-math; not Sprint-27-caused) — a candidate for a future
test-only cleanup. WS-C / `-1`-sentinel (F8) stay DEFERRED.

— Engine team, Sprint-28 (DOC-ONLY; no code changed; no commit/push).
