# Sprint-28 — Security-Posture Re-Verification on the post-Sprint-27 LIVE state (DOC-ONLY)

**Team:** Security (lead). **Date:** 2026-05-18. **Mode:** verification only —
no code, no additions. Re-ran the Sprint-26 100/100 review against the live
deployed tree after Sprint-27 landed.

**Live state audited:** HEAD `168aaa2` ("feat(sprint-27): execute Sprint-26
findings — dashboard honesty, repo-hygiene, companion voice, housekeeping"),
working tree clean (`git status --porcelain` empty). Sprint-27 W1 (dashboard
NAV honesty), W2 (untrack `sentinel_config.json`), W3 (companion voice +
humanized C1/B3 wording), W4c (`telegram_bot.py:~886` raw read → repository)
are all committed and live in this tree.

> Scope discipline: this is a re-hunt for *regressions* in the existing
> intended protections after Sprint-27, plus an honest re-assessment of the
> single Sprint-26 residual (R-1). Sprint-27 deliberately did NOT add
> dashboard auth (an ADDITION — founder decision, OUT of scope). Adding
> dashboard auth is still NOT proposed here as a code change.

---

## Verdict

**Any Sprint-27 security regression? NO.** Every load-bearing Sprint-25/26
control re-verified intact by source. Sprint-27 changed only honesty/wording
and one read routing — no privilege boundary, no write boundary, no secret
surface moved in the unsafe direction. Two changes are mild **net security
positives** (W2 closes the rollback-overwrites-live-NAV data-loss vector; W1
removes a fallback-as-truth dishonesty on the dashboard).

**R-1 status: STILL OPEN — UNCHANGED.** The dashboard on `0.0.0.0:8501` still
has NO app auth AND still contains the "DB Manager" tab that WRITES real trade
rows (incl. `stop_loss` / `initial_stop`). Sprint-27 W1 touched only the
sidebar *render*; the write tab is byte-identical to Sprint-26. Severity,
exploitability, and the absence of any in-code compensating control are
exactly as Sprint-26 reported. This remains a conscious-acceptance /
founder-gated item, not a Sprint-28 code fix.

| Posture area | Sprint-26 | Post-Sprint-27 (now) | Regression? |
|---|---|---|---|
| C1 dev-PIN fail-CLOSED at every privileged handler | CLOSED | **CLOSED (re-verified, flow byte-identical)** | **NO** |
| C1 `DEV_PIN` unset = fail-CLOSED (S-2) | CLOSED | **CLOSED** | **NO** |
| C1 XML→Supabase/NAV write double-gated (S-3) | CLOSED | **CLOSED** | **NO** |
| B3 add-on write-race refuse (zero-write) | CLOSED | **CLOSED (wording humanized, behavior identical)** | **NO** |
| Secure_runner non-bypassable | OK | **OK (re-verified, monkeypatch before import)** | **NO** |
| Secrets hygiene (`.env`, no hardcoded creds) | OK | **OK (re-verified)** | **NO** |
| W4c repo-routed read (`telegram_bot.py:~886`) | n/a (raw read) | **read-only + admin/C1-gated, byte-identical** | **NO** |
| W1 dashboard NAV (`dashboard_nav.py`) | n/a | **no write, no secret, NAV-state only** | **NO** |
| W2 untrack `sentinel_config.json` | tracked (Ops O1 HIGH) | **untracked + gitignored; example = schema only, NO secret** | **NO (net positive)** |
| **Dashboard 8501 — no app auth + WRITE path** | **R-1 OPEN** | **R-1 STILL OPEN — UNCHANGED** | **NO (not regressed; not closed)** |
| `/health` slash dev-PIN-exempt | R-2 (info, accepted) | **unchanged, still admin-gated** | **NO** |

---

## What was re-verified after Sprint-27 (load-bearing checks)

### C1 — dev-PIN guard still fail-CLOSED everywhere ✅ (W3 wording-only)

`telegram_bot.py:155` `_require_active_dev_session(chat_id)`:

- `if not dev_pin_is_configured()` → DENY (`:183-192`, S-2 fail-CLOSED) —
  unchanged.
- `if not dev_pin_session_active(chat_id)` → set
  `user_state[chat_id]={"action":"awaiting_dev_pin"}`, send message,
  `return False` (`:193-209`, S-1/S-3) — control flow unchanged.
- `return True` only on a valid, non-expired session — unchanged.

Sprint-27 W3 changed **ONLY the Hebrew refusal string** inside the
session-inactive branch (`:204-206`: now "🔐 *צריך PIN פעיל לפעולת מפתח* …
הפגישה שלך פגה (תוקף 30 דק' לאבטחתך) — לא בוצעה שום פעולה. הזן את ה-PIN
ונמשיך מכאן:"). The constant-time PIN compare, the 30-min TTL, the
brute-force rate-limit, the `return False`, and the `awaiting_dev_pin`
routing are all untouched. The new wording is **still 100% honest** — it
explicitly states the session expired AND that **no action ran** (no false
reassurance). All ~10 privileged call sites still call the guard at the top
(`:223, :331, :350, :363, :391, :402, :456, :488, :507, :525` + the
menu-open S-2 branch `:310-322` + the XML write-entry defence-in-depth
`:223`). **No regression.**

### B3 — add-on write-race refuse still zero-write ✅ (W3 wording-only)

`telegram_callbacks.py` `addon_confirm` race branch: Sprint-27 W3 reworded
the refusal to "🛡️ עצרתי את החיזוק … לא כתבתי כלום, כדי להגן על הכסף שלך …"
— the zero-Supabase-write protective behavior (no write, pending cleared,
`return`) is UNCHANGED and the new text is still honest ("nothing was
written"). **No regression.**

### W4c — `telegram_bot.py:~886` raw read → repository (read-only, gated) ✅

Before: `res = supabase.table("trades").select("*").execute();
df = pd.DataFrame(res.data)`. After (`telegram_bot.py:886`):
`df = pd.DataFrame(repo.get_all_trades(supabase))`.
`supabase_repository.get_all_trades` (`supabase_repository.py:22-23`) is
`sb.table("trades").select("*").execute().data or []` — a pure **SELECT**,
NO `.update()/.insert()/.delete()`. It is reached inside
`_handle_addon_command` (`telegram_bot.py:838`, dispatched from the single
admin-wrapped text handler via `/addon`), so it is **admin-gated by
secure_runner** and the surrounding C1/B3 logic is untouched. The only
representational delta (`.data` → `.data or []`) is provably byte-identical
for non-empty/`[]`/`None`. Still **read-only + admin-gated**. **No
regression** (a small architecture-hygiene improvement: one fewer raw
Supabase access point).

### W1 — dashboard NAV honesty: no write, no secret added ✅

`dashboard_nav.py` is a **pure stdlib helper** (only `from typing import
Tuple`) — imports NO streamlit/engine/supabase, performs ZERO math, has NO
write path. It consumes only `account_state.load()` fields, which are
exclusively NAV/financial-state (`nav`, `total_deposited`, `risk_pct_input`,
`nav_source`, `nav_updated_at`, `age_hours`, `freshness`, `freshness_label`,
`is_stale`, `is_critical`, `ok`) — verified in `account_state.py`: **NO
token / key / secret / account-number / credential field exists in that
dict**. The new warning string surfaces only the NAV figure + source +
freshness label (already-internal trading state shown on the same screen,
NOT a credential). `dashboard.py` now reads NAV via the canonical
`acc_state.load()` and renders via the helper; `saved_nav` /
`current_acc_size` / `target_risk_usd` and every downstream KPI are the same
canonical value (broker-fresh byte-identical green box). **No new write, no
secret exposure.** This is an honesty *improvement* (closes the
fallback-as-truth class CLAUDE.md/AGENTS #1 forbids on the dashboard
surface). It does **NOT** add auth and does **NOT** touch the R-1 write tab.

### Secure_runner — still non-bypassable ✅

`telegram_bot_secure_runner.py`: `main()` calls
`install_telegram_hardening()` (line 176) — which monkeypatches
`telebot.TeleBot.message_handler` / `callback_query_handler` at **class
scope (lines 160-161)** — **BEFORE** `import telegram_bot` (line 177). So
every `telegram_bot.py` decorator (text catch-all, `handle_document_upload`,
the callback router) is admin-wrapped. `guard_decision` (`:57-83`) is
**fail-CLOSED**: `if not ADMIN_ID or chat_id != str(ADMIN_ID): return False,
'unauthorized'` (`:60-62`); rate-limit + cooldown intact. Sprint-27 touched
none of this file. `docker-compose.yml` still runs
`telegram_bot_secure_runner.py` (CLAUDE.md production wiring preserved).
**No regression.**

### Secrets / W2 untrack — no secret newly exposed ✅ (net positive)

- `.env` is gitignored and **not tracked** (`git ls-files` empty for `.env`).
  No hardcoded token/key/PIN in production code.
- **W2 (`sentinel_config.json` untrack):** the file is now **untracked**
  (`git ls-files --error-unmatch sentinel_config.json` → not tracked) and
  gitignored (`.gitignore:3`); the host working copy is preserved.
  `sentinel_config.example.json` (tracked) contains **only schema /
  placeholder values** (`nav: 0.0`, `total_deposited: 7500.0`,
  `risk_pct_input: 0.5`, a fixed dummy timestamp) and a comment — these are
  the *public field shapes* already documented in `account_state.py`. It
  contains **NO secret, NO real/live NAV, NO token/key/account number**.
  Untracking does **not** widen any secret/exposure surface; it **removes** a
  data-loss vector (a future `git checkout/reset` can no longer silently
  overwrite the live IBKR NAV). Honest note: a prior, *pre-Sprint-27* commit
  (`HEAD~1`) already contains a historical `nav: 7922.18` value in git
  history — that is a NAV *figure* (not a credential), it pre-dates this
  sprint, and W2 is precisely the fix that stops this from worsening going
  forward. Not introduced by Sprint-27; not a regression.
- W1 companion/disclosure strings (dashboard_nav warning, W3 "מה עכשיו?"
  lines) carry only NAV/verdict/open-book state already on those surfaces —
  **no NAV-internal secret, no credential** leaked into any string.

### R-1 — Dashboard `8501` no app auth + Supabase WRITE tab — STILL OPEN, UNCHANGED

`docker-compose.yml` still publishes `8501:8501`. `dashboard.py:1379` is
still the "🛠️ DB Manager (Data Correction)" tab; `dashboard.py:1401-1406`
still does, with **NO PIN / NO admin / NO audit**:

```python
if st.form_submit_button("💾 Save to DB"):
    supabase.table("trades").update({
        "setup_type": n_setup, "quality": n_qual, "score": n_score,
        "stop_loss": n_sl, "initial_stop": n_init_sl,
        "image_url": n_img if n_img else None,
        "management_notes": ...
    }).eq("trade_id", t_id).execute()
```

This is byte-identical to the Sprint-26 R-1 finding. Sprint-27 W1 modified
only the sidebar render block (`dashboard.py:~106-118`) — it did **not**
touch, gate, or remove this write tab (deliberate: dashboard auth = an
ADDITION, founder-gated, OUT of Sprint-27 scope per `SPRINT27_SCOPE.md`
SKIP). **Honest risk quantification (unchanged from Sprint-26):**

- **Severity:** MEDIUM. Exploitability is bounded by **network reach only**,
  NOT by app logic. There is still **NO in-code compensating control** —
  anyone with TCP reach to `8501` can read the full portfolio/Supabase data
  AND rewrite trade stops/journal (which feed R-multiple, NAV-derived risk,
  and exposure math) with no authentication.
- **Compensating controls — assessed honestly:** the ONLY mitigation is the
  host/network boundary (LAN-only / Tailscale / VPN / host firewall /
  loopback-bind+tunnel). The repo/docs still contain **NO verifiable
  evidence** that this boundary is configured. It exists only if the operator
  set it at the host/network layer — **unverified here; must be confirmed by
  Ops/founder, not assumed.** If `8501` is internet- or untrusted-network
  reachable, this is effectively an open read+write console to the trading
  DB.
- **Governance:** adding dashboard app-auth (or gating/auditing the write
  tab) remains an ADDITION → OUT of "no new development". Conscious-acceptance
  / future founder-gated Phase, not a Sprint-28 code change.

### R-2 / devlog — unchanged, accepted by design

`/health` slash remains dev-PIN-exempt (still admin-gated by secure_runner;
test-pinned by design) and the `devlog|` callback remains admin-only (no
secrets in the 3 log paths). Sprint-27 did not change either. No action.

---

## למנכ״ל — בשפה פשוטה

**האם המערכת עדיין בטוחה משימוש לרעה / מחשיפה? כן — בדיוק כמו אחרי
Sprint-26. השינויים של אתמול לא דלפו שום דבר ולא פתחו שום פרצה חדשה.**

- **האם השינויים של אתמול (Sprint-27) הדליפו משהו או שברו הגנה? לא.**
  בדקנו כל שינוי מול הקוד החי:
  - **הדשבורד (W1):** שינינו רק את ה*תצוגה* של ה-NAV בצד — עכשיו הוא אומר
    את האמת אם הנתון לא חי/ישן/fallback (במקום להציג ירוק "Live" תמיד).
    אין כתיבה חדשה, אין סוד חדש שנחשף — הקובץ העוזר משתמש רק בנתוני NAV
    שכבר מוצגים ממילא במסך. **שיפור יושרה, לא סיכון.**
  - **קובץ ה-NAV (W2):** הוצאנו את `sentinel_config.json` ממעקב git כדי
    שגלגול-לאחור לא ימחק בטעות את ה-NAV החי. הקובץ דוגמה שנכנס מכיל **רק
    מבנה ריק/פלייסהולדר — אין בו סוד, אין NAV אמיתי, אין טוקן/מפתח.**
    זה **שיפור** (סוגר סיכון אובדן-נתונים), לא חשיפה.
  - **טלגרם (W3):** רק ניסוח ההודעות התרכך (PIN שפג / סירוב Add-On) —
    ההתנהגות הביטחונית **זהה בדיוק**: עדיין נחסם, עדיין לא נכתב כלום,
    עדיין כנה ("לא בוצעה שום פעולה" / "לא כתבתי כלום").
  - **קריאת DB אחת (W4c):** הועברה דרך שכבת ה-repository — עדיין **קריאה
    בלבד**, עדיין מאחורי admin + C1, עדיין אותה תוצאה בדיוק.
- **כל ההגנות הקיימות עדיין עומדות:** ה-PIN ננעל אוטומטית אם לא מוגדר,
  כל פעולת מפתח חסומה מאחורי PIN פעיל, שכבת ה-admin החיצונית לא ניתנת
  לעקיפה, אין סודות בקוד, אין הזרקת SQL, B3 סגור.
- **הפער היחיד שנשאר — בדיוק כמו ב-Sprint-26, לא השתנה:** הדשבורד
  (פורט 8501) **עדיין בלי סיסמה**, ו**עדיין יש בו לשונית "DB Manager"
  שמאפשרת גם *לשנות* טריידים אמיתיים** (כולל סטופים). Sprint-27 בכוונה
  לא הוסיף סיסמה לדשבורד (זו תוספת — החלטת מנכ״ל). הסיכון, החומרה, וחוסר
  הבקרה-בקוד — **זהים לחלוטין** לדיווח של Sprint-26. לא הורע, לא נסגר.
- **האם זה קביל להריץ כמו שזה?** **רק אם** מאמתים שפורט 8501 נגיש אך ורק
  דרך גבול רשת מהימן (LAN פרטי / Tailscale / VPN + חומת-אש). **עדיין לא
  מצאנו תיעוד שזה אכן מוגדר.** אם הוא נגיש מהאינטרנט/רשת לא-מהימנה — **לא
  קביל** עד שיוסדר גבול הרשת.

**שורה תחתונה:** אין רגרסיית אבטחה מ-Sprint-27. המערכת בטוחה לשימוש בטלגרם
בדיוק כמו אחרי Sprint-26. R-1 (חשיפת הדשבורד) פתוח ולא השתנה — קביל להריץ
**בתנאי** שמאמתים היום שהפורט מאחורי גבול רשת מהימן; אם לא — צריך לסגור
את גבול הרשת קודם.

## מה צריך לעשות

1. **היום, לא-קוד (Ops/founder):** לאמת שפורט `8501` נגיש **רק** דרך גבול
   מהימן (Tailscale/VPN/LAN + חומת-אש; עדיף bind ל-loopback ותיעול). זו
   הבקרה המפצה האמיתית היחידה — פעולת פריסה, לא שינוי קוד. (פריט פתוח
   מ-Sprint-26, עדיין לא אומת.)
2. **רישום קבלה מודעת (founder):** אם (1) מספק לשימוש מפעיל-יחיד — המנכ״ל
   רושם קבלה מפורשת: "לדשבורד אין הזדהות; מוגן רק ע״י גבול רשת X".
3. **W2 — פעולת מארח (founder, אם עוד לא בוצעה):** לוודא על ההוסט שה-
   pull שהנחית את ה-untrack לא מחק NAV (גיבוי `cp sentinel_config.json
   /tmp/nav.bak` לפני; ולאסור `git reset --hard`/`git checkout .` על
   ההוסט), לפי `DEPLOYMENT_RUNBOOK.md`.
4. **Phase עתידי מנוהל (בכפוף לאישור מנכ״ל):** אפיון הזדהות לדשבורד ו/או
   נעילה+תיעוד (audit) של לשונית ה-DB-Manager הכותבת — תוספת, לא חד-צדדי.
5. **ללא פעולה:** R-2 (`/health` ללא PIN) ו-devlog (admin בלבד) — החלטות
   עיצוב מודעות, מתועדות; ללא שינוי. אין שינוי קוד מ-Sprint-28.

---

## Final report (≤180 words)

**No Sprint-27 security regression — NO.** Re-verified by source on live
`168aaa2`: C1 `_require_active_dev_session` is still fail-CLOSED (unset
`DEV_PIN` DENIES; no session → refuse+route, `return False`) at all ~10
privileged handlers + the XML write-entry; W3 changed *only* the Hebrew
refusal wording — flow, TTL, constant-time compare untouched, still honest.
B3 zero-write refuse unchanged (wording-only). Secure_runner still
non-bypassable (class-scope monkeypatch before `import telegram_bot`,
fail-closed admin gate); production wiring intact. W4c read is pure SELECT,
admin/C1-gated, byte-identical. W1 `dashboard_nav.py` is pure stdlib, no
write, and `account_state.load()` exposes only NAV-state (no
secret/credential field) — an honesty improvement, no new exposure. W2
untrack is a net positive: example config is schema-only (no secret/no live
NAV); closes the rollback-NAV-overwrite vector.

**R-1 status: STILL OPEN — UNCHANGED.** Dashboard `8501` still no app auth +
the byte-identical "DB Manager" Supabase trade-WRITE tab; no in-code
compensating control; the network boundary remains undocumented/unverified.

**Acceptable to run as-is ONLY IF** Ops/founder confirms today that `8501` is
reachable solely over a trusted boundary and records conscious acceptance;
otherwise the network lockdown must be scheduled first. Dashboard auth stays
a future founder-gated ADDITION — not done unilaterally.
