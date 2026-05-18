# Sprint-28 — Data / Supabase 100/100 Data-Integrity & Honesty Re-Review (DOC-ONLY)

**Date:** 2026-05-18 · **Mode:** DOC-ONLY (no code, no schema, no migrations).
**LIVE state re-verified from source:** HEAD `168aaa2`
("feat(sprint-27): execute Sprint-26 findings"). Working tree CLEAN.
**Verdict:** **D-F1 CLOSED.** Dashboard NAV is now honest end-to-end on a
single canonical source; no Sprint-27 data regression found. **NOT yet
100/100** only because the two carried Sprint-25/26 P2s (D-F2 stray
`</content>`, D-F3 NULL-`pnl_usd` SELL) are still open and were explicitly
ruled OUT of Sprint-27 scope — both remain latent / non-production.

> **"D-F1 closed? — YES.**" Re-verified from source, not from the impl docs.

---

## D-F1 — re-verified CLOSED from source (the Sprint-26 P1 headline)

| Check | Source evidence | Status |
|-------|-----------------|--------|
| Dashboard NAV reads the **canonical single source** | `dashboard.py:111-112` now `_acc = acc_state.load(); saved_nav = float(_acc["nav"])`. The old bare-`except` divergent reader (`load_settings`, `dashboard.py:46-52`) is **no longer the source of the prominent figure** — `load_settings()` is still imported for `total_deposited`/`risk_pct_input` UI inputs only, NOT for the green NAV box. | ✅ canonical |
| No bare-except divergence for the headline | `account_state.load()` is the shape-A adapter over the shared `_resolve_nav_core` (`account_state.py:48-201`); D1 explicit-0 kept, D2 strict-`<`, D3/D4 honest fallback. `dashboard.py` no longer has an independent NAV classifier. | ✅ single-sourced |
| Fallback/stale NEVER shown as `🏦 Live IBKR NAV` | `dashboard_nav.nav_sidebar_render(acc)` GATE is **byte-identical to B1** `_nav_disclosure_lines`: `nav_source=="broker" AND freshness=="fresh" AND not is_stale AND ok`. broker+fresh ⇒ `("success", "🏦 Live IBKR NAV: **$X**")` (byte-identical pre-W1 green box); ANY other state (deposited / fallback / stale / critical / unknown / `ok=False` / non-dict) ⇒ `st.sidebar.warning(...)` reusing the verbatim `freshness_label` + source + "ערך מוערך/לא-עדכני — לא נתון מדויק". Closes the stale-broker gap the old `fmt_risk_capital_basis` caption missed. | ✅ honest |
| Downstream math byte-identical | `saved_nav` = `account_state.load()["nav"]` = the SAME canonical value the old `settings.get("nav", settings.get("total_deposited", 7500.0))` produced on a normal broker config; `current_acc_size`/`target_risk_usd`/all KPI panels unchanged. Presentation-only delta (box style + honest string), exactly mirroring B1. | ✅ zero math change |
| Gate matches B1 exactly (no divergence) | `dashboard_nav.nav_sidebar_render`, `report_renderer._nav_disclosure_lines`, and `report_renderer._account_state_broker_fresh` (W3) all use the **identical** broker-fresh predicate over the **same** `account_state.load()` shape. One honest signal, three surfaces, no desync. | ✅ unified honesty |

`dashboard.py:132` still computes the Sprint-15 `fmt_risk_capital_basis`
caption from the **legacy** `_nav_source = "broker" if "nav" in settings`
(reads `settings`, the old `load_settings()` dict). This is the
**pre-existing** Sprint-15 caption, explicitly OUT of W1's tight scope,
unchanged, and **no longer the prominent honesty surface** — the green
"Live" box (the D-F1 root) is now honest. Noting it as a residual
consistency wrinkle, NOT a reopened D-F1 (the caption already discloses
`deposited`/`fallback`; the headline box now covers the stale-broker case
the caption missed). **Tag: residual (watch), not a regression.**

## Sprint-27 regression sweep — NONE found

| Sprint-27 item | Re-verification | Verdict |
|----------------|-----------------|---------|
| **W4c** `telegram_bot.py:886` raw read → `repo.get_all_trades` | `supabase_repository.get_all_trades(sb)` = `sb.table("trades").select("*").execute().data or []` — the byte-identical query the inline `supabase.table("trades").select("*").execute()` issued. Only delta `.data` → `.data or []` (`None`/`[]` ⇒ `pd.DataFrame` (0,0), same as before; non-empty ⇒ same rows, same columns, no null/shape drift). C1 `_require_active_dev_session` guard + admin gate + B3 logic untouched. The lone residual raw read is gone (no other `supabase.table("trades").select("*")` in `telegram_bot.py`). | ✅ byte-identical, no drift |
| **W3** companion "🧭 *מה עכשיו?*" line — never asserts exactness over fallback/stale, never contradicts body | (a) `report_renderer.whatnow_line`: when NAV not broker-fresh it **prepends** "המספרים מבוססים על NAV לא-חי (ראה הבהרת NAV למטה) — קרא אותם כהערכה, לא כאמת מדויקת" then the verdict read; the B1 `_nav_disclosure_lines` body still appears below (line 573 / normal branch) — the line points DOWN to it, consistent. (b) `telegram_portfolio.py:540-552`: when `nav_stale_label` set, leads "שים לב — NAV לא חי (ראה הערה למטה), קרא R/חשיפה כהערכה"; existing footer note preserved. (c) `risk_monitor._daily_digest_text`: digest rows are live per-position state/Open-R (NOT NAV-scaled realized KPIs), so absence of a NAV caveat is correct and matches pre-W3 (no regression). `neutral`/`אין פעולה דחופה`/empty-state strings explicitly say "זה לא אומר שהכול תקין/לא תקין" — honest, never false reassurance. | ✅ honest, no contradiction |
| W3 did not change realized math | `compute_verdict` signature is `(analytics, period_word) -> tuple` (`analytics_engine.py:331`) — unchanged; W3 only **captures** the already-returned `verdict_class` instead of discarding it. `verdict` text/class semantics untouched. | ✅ zero KPI change |
| No read-only-flow Supabase mutation introduced | No `.insert/.update/.upsert/.delete` added in `report_renderer.py`, `dashboard_nav.py`, `risk_monitor._daily_digest_text`, or the W4c read path. The only `.delete` near the W4c site is `bot.delete_message` (Telegram), not Supabase. W4c is a single read-only `.select("*")` through the repo. AGENTS #4 / DATA_CONTRACTS §"Supabase write contract" intact. | ✅ no read-side mutation |
| Migrations still 005 | `migrations/` = 001–005 + rollbacks + `verify_migrations.py` (enumerates 001…005). No new migration, no schema change in Sprint-27. | ✅ unchanged |
| Byte-locked engine/analytics untouched | Sprint-27 commit `168aaa2` git-stat: `analytics_engine.py`, `engine_core.py`, `period_data_probe.py`, all `_byte_lock_baseline*`, LOCKED April regression, `migrations/` are NOT in the changed-file list. | ✅ locks intact |
| Untracked `sentinel_config.json` (W2) doesn't change data-contract conformance | `sentinel_config.json` is gitignored (`.gitignore:3`) and removed from the index in `168aaa2` (live content NOT committed); only `sentinel_config.example.json` is tracked. `account_state._CONFIG_PATHS` = `["/app/sentinel_config.json", "sentinel_config.json"]` is **unchanged** — the canonical reader still finds the live host/container file at runtime; untracking the file changes only VCS hygiene, not the data-contract NAV-source resolution. | ✅ no contract impact |

## Carried residuals (still open — OUT of Sprint-27 scope, unchanged)

| ID | Sev | Status now | Note |
|----|-----|------------|------|
| **D-F1** | — | **CLOSED** | Re-verified from source above. |
| **D-F2** | P2 | **Still open** | Stray `</content>` in `migrations/005_create_open_tasks.sql` + `rollback_005.sql`. Sprint-27 explicitly did NOT touch `migrations/` (git-stat confirms). Production unaffected (005 APPLIED); fresh-env copy-paste hazard only. Future governed migration-hygiene Phase. |
| **D-F3** | P2 | **Still open (latent)** | NULL/blank `pnl_usd` on in-window SELL → silent `$0` via `analytics_engine` `.fillna(0)`, no counter (contrast: NULL `campaign_id` IS disclosed). Engine byte-locked / untouched in Sprint-27. DEC-019/-020 proved April prod fully populated ⇒ latent, not active. Backlog flag. |

**P0/P1:** none. The single Sprint-26 P1 (D-F1) is now closed. The only
open items are the two pre-existing, OUT-of-scope, non-production P2s.

---

## למנכ״ל — בשפה פשוטה

**האם הסוחר יכול עכשיו לבטוח שמה שהוא רואה — כולל ה-Dashboard — זה אמיתי
וכן? כן.** וכן — מה שתוקן אתמול (ספרינט-27) סגר בדיוק את החור.

- **ה-Dashboard (החור הגדול של ספרינט-26): תוקן ואומת מול הקוד.** הכותרת
  הירוקה `🏦 Live IBKR NAV` מופיעה עכשיו **אך ורק** כש-ה-NAV באמת חי
  מהברוקר וטרי. אם הוא ברירת-מחדל ($7,500) / ישן / לא-חי — מופיעה במקום
  זה **אזהרה** (לא ירוק) שאומרת במפורש "ערך מוערך/לא-עדכני — לא נתון
  מדויק", עם המקור. אותה לוגיקה בדיוק כמו בטלגרם (B1) — מקור אחד, קנוני,
  בלי קורא-כפול נסתר.
- **טלגרם / PDF / חישובי R / Net-R / Expectancy / PF / קמפיינים: כן,
  כמו קודם.** המספרים אמיתיים, מקור-NAV יחיד, כפילויות שורות מנוטרלות,
  שורות בלי campaign_id מדווחות בנפרד. אין כתיבה ל-Supabase ממסלולי-קריאה.
- **השורה החדשה "🧭 מה עכשיו?"** (ספרינט-27): כשה-NAV לא חי היא **מקדימה
  ואומרת** "המספרים מבוססים על NAV לא-חי — קרא כהערכה, לא כאמת מדויקת",
  ומפנה להבהרה למטה. היא אף פעם לא מתיימרת לדיוק על נתון ישן ולא סותרת
  את הגוף. ב-0 עסקאות / אין-פוזיציות היא אומרת מפורשות "זה לא אומר שהכול
  תקין/לא תקין". כנה.
- **לא נמצאה אף נסיגה (regression) של ספרינט-27.** ההחלפה ב-W4c מחזירה
  נתונים זהים בייט-לבייט; מנוע/אנליטיקה/מיגרציות לא נגעו בהם.

**שורה תחתונה:** כן — אחרי ספרינט-27 הסוחר יכול לבטוח גם ב-Dashboard וגם
בטלגרם. נשארו רק שני פגמים קטנים (P2) שלא נוגעים לפרודקשן ולא היו בהיקף
אתמול: גרבג `</content>` בקובץ מיגרציה 005, וחוסר מונה ל-SELL עם
`pnl_usd` ריק (latent בלבד — בפרודקשן הכל מאוכלס).

## מה צריך לעשות

1. **D-F1: סגור — אין מה לעשות.** רק לשמור: כל עריכה עתידית ל-
   `account_state.load()` או לגייט broker-fresh חייבת הוכחה
   (broker+fresh נשאר byte-identical, fallback/stale מציג אזהרה) —
   זה הגייט המשותף ל-3 משטחים (Dashboard / B1 טלגרם / W3).
2. **לאחד את caption ה-Sprint-15** (`dashboard.py:132`,
   `fmt_risk_capital_basis`) על אותו `account_state.load()` כמו הקופסה
   הירוקה — כרגע הוא עוד קורא את ה-`settings` הישן. לא נסיגה (הקופסה
   הראשית כבר כנה), אבל wrinkle עקביות; Phase תצוגה-בלבד עתידי.
3. **D-F2 (P2, OUT):** Phase היגיינת-מיגרציות עתידי שמוחק רק את שתי
   שורות `</content>` ב-`005`/`rollback_005`.
4. **D-F3 (P2, OUT — לתעד):** backlog — מונה-גילוי ל-SELL עם `pnl_usd`
   ריק (מראה ל-`unlinked_*`); latent בלבד עד שתהיה שורה כזו בפרודקשן.
5. **לא לגעת השבוע:** הכול אומת DOC-ONLY מול המקור; כל תיקון = Phase
   עתידי מנוהל עם הוכחה, אחרת LOCKED April / byte-locks נשברים.
