# Sprint-27 W3 + W4c — Implementation (companion voice + S26-R1 repo swap)

**Branch:** `claude/review-system-audit-FBZ2h` · **Date:** 2026-05-17 · Tree
left DIRTY (parent consolidates + verifies + runs post-commit CI-equivalent).
NOT committed/pushed. Scope: W3 + W4c ONLY from `SPRINT27_SCOPE.md`.

W3 is **presentation-only, ZERO math, numbers byte-identical**. W4c is a
**read-only, byte-identical** repo swap (Arch S26-R1). No byte-locked file
touched (verified git-diff EMPTY: `analytics_engine.py`, `engine_core.py`,
`period_data_probe.py`, LOCKED `tests/test_real_data_april_regression.py`,
`tests/_byte_lock_baseline*`, `tests/_byte_lock_baselines/*`). No new
feature/flag/command.

---

## W4c — `telegram_bot.py:872` raw read → repository (Arch S26-R1)

**Before** (`telegram_bot.py:871-873`, inside `_handle_addon_command`):
```python
# Load open position for symbol
res = supabase.table("trades").select("*").execute()
df  = pd.DataFrame(res.data)
```
**After** (`telegram_bot.py:877-886`):
```python
# Load open position for symbol.
# Sprint-27 W4c (Arch S26-R1): route the lone residual raw … through the
# repository layer (supabase_repository.get_all_trades …). Read-only,
# byte-identical result … C1 guard + admin gate + B3 logic UNCHANGED.
df  = pd.DataFrame(repo.get_all_trades(supabase))
```

- `repo` is the **already-imported** `supabase_repository` (`telegram_bot.py:10`
  `import supabase_repository as repo`); `supabase` is the existing `bot_core`
  client. No new import, ONE-line swap, no wholesale rewrite.
- `supabase_repository.get_all_trades(sb)` (`supabase_repository.py:22-23`)
  issues `sb.table("trades").select("*").execute().data or []` — the
  **byte-identical query** the inline read issued.

**Byte-identical-result proof.** The only representational delta vs the inline
read is `.data` → `.data or []`:
| `.data` | inline `pd.DataFrame(res.data)` | repo `pd.DataFrame(... or [])` |
|---|---|---|
| non-empty list | rows | `data or []` is `data` ⇒ same rows |
| `[]` | `pd.DataFrame([])` → (0,0) empty | `[] or []` is `[]` ⇒ (0,0) empty |
| `None` | `pd.DataFrame(None)` → (0,0) empty | `[]` ⇒ (0,0) empty |

`pd.DataFrame(None).equals(pd.DataFrame([]))` is `True` (proven in the test),
so the DataFrame the call site consumes (`ec.get_open_positions_campaign(df)`)
is byte-identical for every result shape. The C1
`_require_active_dev_session` guard, the admin/secure-runner gate, and the B3
`_planned_cid` persistence are all UNCHANGED (asserted in the parity test).

Pinned by **`tests/test_sprint27_w4c_repo_parity.py`** (8 tests): old raw read
vs new repo call → identical columns/shape/values for non-empty / `[]` / `None`;
same `.table("trades").select("*").execute()` chain; end-to-end identical
`get_open_positions_campaign` result; the residual raw read is gone +
C1/B3 markers still present in `telegram_bot.py`.

---

## W3 — Companion voice ("מה עכשיו?")

ONE concise Hebrew verdict+next-step line **PREPENDED** at the TOP of three
surfaces, composed ONLY from signals already computed there. The new line is
prepended; every existing body line + number stays byte-identical.

### (a) Weekly/monthly Telegram summary — `report_renderer.py`

New constants + `whatnow_line(verdict_class, account_state, period_type)`
helper (`report_renderer.py:~191-258`). **Derivation (no new computation):**
- `verdict_class` ∈ {`strong`/`mixed`/`defensive`/`neutral`} is the value
  **already returned** by the existing `analytics_engine.compute_verdict`
  (capture changed from `verdict, _` → `verdict, verdict_class`; the verdict
  text + class semantics untouched).
- `period_type` is the **existing** `build_summary_text` param (only selects
  the existing period noun "שבוע"/"חודש", like `compute_verdict`'s
  `period_word`).
- broker-fresh signal reuses the **exact same gate** B1's
  `_nav_disclosure_lines` already derives (`_account_state_broker_fresh`,
  single source) — when NAV is not broker-fresh the line leads with
  "המספרים מבוססים על NAV לא-חי … כהערכה, לא כאמת מדויקת" (accuracy >
  confidence). `account_state=None` ⇒ NAV-silent (legacy callers byte-clean).

Class → one-action read: strong "אין פעולה דרושה; שמור על השיטה" · mixed
"אין דרישה דחופה; עבור על הקמפיינים" · defensive "עדיפות לצמצום סיכון" ·
neutral (0-closed) "אין עסקאות שנסגרו בתקופה — **זה לא אומר שהכול תקין/לא
תקין**; עבור על הספר הפתוח" (the empty-state disambiguation).

Wiring: `_whatnow = [whatnow_line(...), ""]` then `head = list(_whatnow) + […]`
(0-closed branch) and `lines = list(_whatnow) + […]` (normal branch). The
pre-W3 body literals below are unchanged.

**Byte-identical-numbers proof.** `test_sprint25_b1_fallback_disclosure.py::
test_frozen_literal_representative_fixture` (updated — "Updated NOT
weakened", same precedent as the Sprint-25 C1 test correction) now pins the
exact output AND asserts `got.split("\n",2)[2] == _pre_w3_body` — the body
below the prepended line + its blank separator is **byte-for-byte** the
pre-W3 frozen literal. `test_sprint27_w3_companion_voice.py::
TestReportBodyByteIdenticalPreW3` pins the closed-week body against a frozen
pre-W3 oracle and proves the broker-fresh==no-account equality (the prepend
is symmetric, so B1's `broker_fresh == pre_b1` equality tests still hold).

### (b) Live חדר-מצב / open-book — `telegram_portfolio.py`

`handle_portfolio_room`: during the **existing** position loop, symbols whose
**already-computed** engine `status` is in `("🚨 קריטי","🔴 Broken","🚨 חריגת
סיכון אלגו")` (the exact string the card prints in "סטטוס שוק", same set as
`risk_monitor.CRITICAL_STATUSES`) are collected into `decision_syms` — NO new
computation. Just before send, the line is **prepended** to `msg`:
`decision_syms` → "{n} פוז' דורשות החלטה: … — ראה כרטיסים למטה"; else "{n}
פוז' במעקב, אין מצב קריטי …"; if `nav_stale_label` (the existing footer flag)
the line leads with "שים לב — NAV לא חי …, קרא R/חשיפה כהערכה". The whole
`msg` body built above is unchanged. **Empty-surface disambiguation:** the
`open_pos.empty` branch's "✅ אין פוזיציות פתוחות במערכת." (a green check that
reads as all-clear) → "📭 *אין פוזיציות פתוחות כרגע.* _זה לא אומר שהכול
תקין/לא תקין … אם פתחת עסקה ולא מופיעה, בדוק סנכרון נתונים._"

### (c) Risk-monitor daily digest — `risk_monitor.py`

`_daily_digest_text`: `urgent` is now derived FIRST via a **provably
byte-identical** refactor (the same `state ∈ (BROKEN,RUNNER,
PROFIT_PROTECTION)` predicate, same order — was appended inside the loop, now
a list-comp before it; the per-row bullets + urgent footer are unchanged).
The companion line is inserted as `lines[1]` (right after the title):
urgent → "{n} פוז' דורשות החלטה: … — ראה פירוט למטה"; else "{n} פוז' תחת
מעקב, אין פעולה דחופה" (honest — never "הכול תקין"). Pinned byte-identical
body by `TestDailyDigestCompanionLine::test_digest_body_bullets_byte_identical`.

### Humanized C1 PIN-expiry — `telegram_bot.py:_require_active_dev_session`

**Before:** `🔐 *פעולת מפתח דורשת PIN פעיל*\nהפגישה אינה פעילה או פגה. הזן
את ה-PIN:`
**After:** `🔐 *צריך PIN פעיל לפעולת מפתח*\nהפגישה שלך פגה (תוקף 30 דק'
לאבטחתך) — לא בוצעה שום פעולה.\nהזן את ה-PIN ונמשיך מכאן:`
Security UNCHANGED: still routes to `awaiting_dev_pin`, still returns `False`,
no TTL/compare touched. Warmer + still 100% honest (states the session
expired AND that **no action ran** — no false reassurance).

### Humanized B3 race-refusal — `telegram_callbacks.py` addon_confirm race

**Before:** `❌ *ביטול: הפוזיציה השתנתה — {sym}*\nהפוזיציה הפתוחה עבור הסמל
השתנתה מאז שתכננת את החיזוק.\nהרץ ‎/addon‎ מחדש.`
**After:** `🛡️ *עצרתי את החיזוק — {sym}*\nהפוזיציה הפתוחה ב-{sym} התחלפה
מאז שתכננת (קמפיין אחר) — לא כתבתי כלום, כדי להגן על הכסף שלך.\nהרץ ‎/addon‎
מחדש על המצב הנוכחי.`
Zero-write protective behavior UNCHANGED (no Supabase write, pending cleared,
`return`). Reframed as protection (not rejection), says WHAT changed, states
plainly **nothing was written** — still 100% honest, no false reassurance.

The humanized messages' new wording AND honesty are pinned by
`test_sprint27_w3_companion_voice.py` (C1: still denies + states expiry + "לא
בוצעה שום פעולה"; B3: "עצרתי"/"התחלפה"/"להגן על הכסף שלך" + "לא כתבתי כלום" +
not the success string + pending cleared). The B3 acceptance assertion in
`tests/test_phase_b3_addon_cid.py::test_divergent_cid_refuses_zero_write_clears_pending`
was updated to the new authorized wording, kept EQUALLY strict (still asserts
position-changed + re-run /addon + zero-write honesty + not success).

---

## Tests / verification

- New: `tests/test_sprint27_w3_companion_voice.py` (17), `tests/
  test_sprint27_w4c_repo_parity.py` (8) — both auto-tag `unit`,
  collection-order-independent (isolated module loading, per-load private
  mocks so no shared module is mutated).
- Updated (NOT weakened): `test_sprint25_b1_fallback_disclosure.py`
  (frozen-literal pin now includes the prepend + asserts the pre-W3 body
  byte-identity), `test_phase_b3_addon_cid.py` (B3 refusal assertion → new
  wording, equally strict). No other existing test changed.
- **Full suite** (`python -m pytest -q -p no:cacheprovider`, CI env):
  **2088 passed, 0 failed** (≥ 2039 baseline + 25 new).
- **CI-equivalent** (`pytest --tb=short -q --cov=engine_core
  --cov=adaptive_risk_engine --cov=analytics_engine --cov=addon_risk_engine
  --cov-report=term --cov-fail-under=67`, CI env): **2088 passed, 0 failed,
  total coverage 72.02% ≥ 67%**.
- LOCKED April regression (8/+$180.49/WR.375/PF2.6262/excl2) byte-identical
  (2 passed, file git-diff EMPTY); Sprint-22 tz (18) + Sprint-23 probe (15) +
  Sprint-24 B1/B3 byte-identical (9) + Sprint-19 lock (32) + B3 (5) +
  secure_runner (3) all GREEN. No byte-locked file touched.

Post-commit clean-tree CI-equivalent verification + consolidation is the
parent's step; tree left DIRTY per instruction.
