# Sprint-26 — Security-Posture Re-Verification (post-C1 / post-B3, DOC-ONLY)

**Team:** Security (lead). **Date:** 2026-05-17. **Mode:** verification only —
no code, no additions. Re-verified against the working tree (the live system).

**Live state audited:** HEAD `8c5a948` on branch `claude/review-system-audit-FBZ2h`
(working tree clean — `git status` empty). C1 commit `f95998e`
("Wave-2B C1 — enforce dev-PIN at every privileged handler (fail-closed)") and
B3 (Add-On `campaign_id` write-race guard) are both committed and live in this
tree. (Task cited `c761967`; the audited tree’s HEAD is `8c5a948` — the same
C1+B3 content is present and verified by source, not by hash.)

> Scope discipline: this is a re-hunt for *residual* gaps in the *existing
> intended* protections after C1/B3. We do NOT propose new auth features.
> Dashboard auth remains an ADDITION (OUT of "no new development") and is
> reported as an honest exposure + conscious-acceptance recommendation only.

---

## Verdict

**Not a clean 100/100 as a security score — but the in-scope closure work is
done.** All Sprint-25 P0/P1 *code* findings (S-1, S-2, S-3, plus the S-4 anchor)
are **closed and behaviorally test-pinned**. The residual risk is a **single
known infra-boundary exposure** (the dashboard) that is **out of code scope by
governance** and requires a *conscious-acceptance* decision, not a code fix.

| Posture area | Sprint-25 | Post-C1/B3 (now) | Residual |
|---|---|---|---|
| S-1 dev-PIN on every privileged handler | P0 OPEN | **CLOSED** | none |
| S-2 `DEV_PIN` unset = fail-open | P0 OPEN | **CLOSED (fail-CLOSED)** | none |
| S-3 XML→Supabase/NAV write ungated | P0 OPEN | **CLOSED (defence-in-depth)** | none |
| S-4 gate anchor mis-cited | P1 OPEN | **CLOSED (anchor corrected)** | none |
| B3 Add-On write-race | Arch-F3 | **CLOSED (HARDENED refuse)** | none |
| Secure_runner non-bypassable | OK | **OK (re-verified)** | none |
| Secrets hygiene | OK | **OK (re-verified)** | none |
| Supabase read/write boundary (bot) | OK | **OK** | none |
| Injection (SQL/filter) | OK | **OK (PostgREST builder-only)** | none |
| **Dashboard 8501 — no app auth + WRITE path** | P1 (S-12) | **STILL OPEN** | **R-1 (the one residual)** |
| `/health` slash dev-PIN-exempt | n/a | **by-design (test-pinned)** | R-2 (info, accepted) |

---

## What was re-verified CLOSED (the load-bearing checks)

### C1 — dev-PIN now fail-CLOSED at every privileged handler ✅

`telegram_bot.py:155` `_require_active_dev_session(chat_id)` is a shared guard
that (a) **denies** when `DEV_PIN` is unconfigured (S-2 fail-CLOSED,
`:183-192`) and (b) **denies** when no active/non-expired PIN session
(`:193-203`). It is called at the **top of every privileged handler**.
Full coverage cross-check (all 10 developer-menu buttons from
`telegram_menus.get_developer_menu`):

| Dev-menu button | Handler | Gate (`_require_active_dev_session`) |
|---|---|---|
| 📡 IBKR Sync ידני | `:324` | `:325` ✅ |
| 📤 העלה דוח XML | `:343` | `:344` ✅ |
| 📊 תוצאת Sync אחרון | `:356` | `:357` ✅ |
| 📋 לוגים | `:384` | `:385` ✅ |
| 🔄 Git Pull + Deploy (`subprocess`) | `:395` | `:396` ✅ |
| ⚙️ הצג Config | `:449` | `:450` ✅ |
| 🏥 בריאות מערכת (button) | `:481` | `:482` ✅ |
| 🔬 Probe | `:500` | `:501` ✅ |
| 📈/📆 דוח עכשיו | `:518` | `:519` ✅ |
| ⬅️ חזרה לתפריט ראשי | not privileged | n/a |

- **S-3 (XML write) — defence-in-depth confirmed.** Arming `awaiting_ibkr_xml`
  now requires the gated `:343` handler **and** `handle_document_upload`
  (`:207`) independently re-asserts `_require_active_dev_session` at the
  *actual* Supabase-insert + `sentinel_config.json` NAV-overwrite entry
  (`:217-219`) — a stale/expired session cannot complete the real-money write.
- **S-2 fail-CLOSED** also at the menu-open button (`:301-320`): unconfigured
  `DEV_PIN` now DENIES the menu (pre-C1 it fell through and opened with zero
  PIN). `DEV_PIN=4915` is set in prod `.env` (configured path active).
- **S-4 anchor corrected**: in-code comment now cites the real gate region
  (`:241-247` / `_require_active_dev_session`), not the false `147-153`
  (`_send_probe_chunks` chunk loop).
- **Named proof present & green:** `tests/test_sprint25_c1_devpin_enforcement.py`
  — `TestC1NoSessionRefuses` (per-handler side-effect-not-invoked incl.
  subprocess/IBKR-thread/XML/config/log/report/probe/health),
  `TestC1ValidSessionUnchanged` (authorized path byte-identical),
  `TestC1FailClosedWhenUnset` (S-2), `TestC1AdminGateAndSecureRunnerUnaffected`,
  `TestC1NonPrivilegedFlowsByteIdentical`. PIN compare stays constant-time
  (`hmac.compare_digest`); brute-force rate-limit + 30-min expiry intact.

### B3 — Add-On write-race CLOSED ✅

`telegram_bot.py` persists the planned `campaign_id`; `telegram_callbacks.py`
`addon_confirm|YES` re-resolves and on divergence **refuses with zero Supabase
write** (HARDENED) — pinned byte-identical for normal/legacy paths by
`tests/test_phase_b3_addon_cid.py` (oracle equality). No user-invisible
cross-campaign corruption path remains on this flow.

### Secure_runner — non-bypassable (re-verified) ✅

`telegram_bot_secure_runner.py` monkeypatches `TeleBot.message_handler` /
`callback_query_handler` at **class scope at line 159-161, BEFORE
`import telegram_bot` at `:177`** — so *every* decorator (the text catch-all,
`handle_document_upload`, the single callback router) is admin-wrapped.
`guard_decision` (`:57-83`) is **fail-CLOSED**: `if not ADMIN_ID or chat_id !=
ADMIN_ID → reject` (`:60`). Rate-limit + cooldown intact.
`docker-compose.yml:37` runs `telegram_bot_secure_runner.py` (production wiring
per CLAUDE.md preserved). Not bypassable from within `telegram_bot.py`.

### Secrets / injection / Supabase boundary ✅

- `.env` is gitignored (`.gitignore:1`) and **never committed** (empty git
  history for `.env`). No hardcoded token/key/PIN in production code.
  `⚙️ הצג Config` masks token/key/secret/password values (`:466-467`).
- No string SQL anywhere — Supabase via PostgREST `.eq()/.update()/.insert()`
  builders; user-controlled `symbol`/`campaign_id`/notes flow as bound filter
  values only. No SQL/filter-injection path. XSS-in-symbol already test-covered.
- Telegram-bot Supabase writes are admin-gated; privileged write flows now also
  dev-PIN-gated (C1) or ratchet-confirmed (stop/addon, B3).

---

## Residual risks

### R-1 (P1, MEDIUM) — Dashboard `8501` has NO app auth **and a Supabase WRITE path**

`docker-compose.yml:69-70` publishes `8501:8501` (host-exposed). `dashboard.py`
binds the default Streamlit address. **Re-verification correction to
Sprint-25 S-12:** the dashboard is **not read-only**. `dashboard.py:1367-1396`
is a **"DB Manager (Data Correction)" tab** whose `💾 Save to DB` button does:

```python
supabase.table("trades").update({
    "setup_type":..., "quality":..., "score":...,
    "stop_loss": n_sl, "initial_stop": n_init_sl,
    "image_url":..., "management_notes":...
}).eq("trade_id", t_id).execute()
```

i.e. a direct unauthenticated **mutation of real trade rows** — including
`stop_loss` / `initial_stop`, which feed R-multiple, NAV-derived risk, and
exposure math. Anyone with network reach to `8501` can read full
portfolio/Supabase data **and rewrite trade stops/journal** with no PIN, no
admin check, no audit. This is a *larger* surface than S-12 described
(write, not just read) and touches CLAUDE.md hard constraints (Supabase
mutation; stale/incorrect stop distorting risk).

- **Severity:** MEDIUM. Exploitability is bounded by **network reach**, not by
  app logic — there is **no app-layer compensating control in code**.
- **Compensating controls — assessed honestly:** The only real mitigation is
  the network boundary. The audited repo/docs contain **NO evidence** of a
  documented Tailscale/WireGuard/VPN/firewall/reverse-proxy restriction on
  `8501` (searched `SPRINT25_OPS_AUDIT`, `README`, `TESTING_AND_DEPLOYMENT`).
  If the Orange Pi host is on a private LAN / behind NAT with no port-forward,
  real exposure is "anyone on the home/office LAN." If it is reachable from
  the internet or an untrusted network, this is effectively an open
  read+write console to the trading DB. **This control exists only if the
  operator configured it at the host/network layer — it is unverified here
  and must be confirmed by Ops, not assumed.**
- **Governance:** adding dashboard auth = an ADDITION → OUT of "no new
  development". Therefore this is **NOT a Sprint-26 code change**. It is a
  **conscious-acceptance / future-governed-Phase** item.
- **Recommendation:**
  1. **Immediate, non-code (Ops, today):** confirm `8501` is reachable ONLY
     over a trusted boundary (Tailscale/VPN/LAN-only + host firewall;
     ideally bind host-loopback and tunnel). This is the real compensating
     control and it is a deployment action, not a code change.
  2. **Conscious-acceptance record:** if (1) is confirmed adequate for the
     single-operator use case, the founder records explicit acceptance of
     "dashboard has no app auth; protected solely by network boundary X."
  3. **Future governed Phase (founder-gated):** scope dashboard app auth
     and/or making the DB-Manager write tab gated/audited — tracked as an
     ADDITION, not done unilaterally.

### R-2 (P3, INFO — accepted by design) — `/health` slash is dev-PIN-exempt

`telegram_bot.py:607` `if text in ["/health", "🏥 בריאות מערכת"]` is reached
**before** any dev gate, so the `/health` *slash command* runs
`_build_health_report()` (portfolio/NAV/Supabase status, open symbols,
missing-stop symbols — sensitive trading info, **no secrets/credentials**)
**without** a dev-PIN session. The dev-menu *button* path (`:481`) is fully
PIN-gated; only the slash shortcut is exempt. This is **intentional and
test-pinned**: `tests/test_sprint25_c1_devpin_enforcement.py:359`
`test_health_command_path_not_dev_gated` explicitly asserts `/health` stays
non-dev-gated ("no PIN"). It remains **admin-gated** by secure_runner.
**Not a defect** — a conscious design choice; recorded here for completeness
so the asymmetry is documented, not a silent surprise. No action; no code
change.

### Note — devlog callback inherits admin-only (S-11 class, unchanged, acceptable)

`telegram_callbacks.py:28` `devlog|` reads `_DEV_LOG_FILES` (3 app log paths,
no secrets) and is admin-gated by secure_runner but **not** dev-PIN re-checked
(reached via the gated `📋 לוגים` handler that *does* PIN-gate at `:385`,
then taps an inline button). Same posture class as Sprint-25 S-11 (admin-only,
not PIN, for read paths) — acceptable, unchanged, recorded.

---

## למנכ״ל — בשפה פשוטה

**האם המערכת בטוחה משימוש לרעה / מחשיפה? כמעט. הפער היחיד שנשאר הוא הדשבורד.**

- כל מה שתוקן ב-Sprint-25 (C1) **באמת תוקן ועובד**: כל פעולת מפתח רגישה
  בטלגרם (משיכת קוד + פריסה, סנכרון IBKR, העלאת XML שכותב ל-Supabase ומעדכן
  NAV, הצגת Config, לוגים, דוחות) **חסומה עכשיו מאחורי PIN פעיל**. אם ה-PIN
  לא מוגדר — הכול **ננעל אוטומטית** (לא נפתח). יש בדיקות אוטומטיות שמוכיחות
  את זה. שכבת ההגנה החיצונית (admin בלבד) לא ניתנת לעקיפה. אין סודות בקוד.
  אין הזרקת SQL. תיקון B3 (מירוץ כתיבה ב-Add-On) סגור.
- **החשיפה האחת והיחידה שנשארה:** הדשבורד (פורט 8501) **אין לו סיסמה/הזדהות**,
  ו**יש בו לשונית "DB Manager" שמאפשרת לא רק לקרוא אלא גם *לשנות* נתוני
  טריידים אמיתיים** (כולל סטופים, שמשפיעים על חישובי סיכון). כל מי שיש לו
  גישה רשתית לכתובת הזו — יכול לראות את כל התיק **וגם לערוך אותו**, בלי שום
  הזדהות.
- **האם זה קביל כמו שזה?** **רק אם** הדשבורד חשוף אך ורק ברשת מאובטחת
  (LAN פרטי / Tailscale / VPN / חומת-אש בהוסט). **לא מצאנו תיעוד שזה אכן
  מוגדר** — צריך לאמת מול Ops. אם הוא נגיש מהאינטרנט/רשת לא-מהימנה — **זה
  לא קביל** עד שיוסדר גבול רשת. הוספת סיסמה לדשבורד היא *פיתוח חדש* (מחוץ
  למנדט הסבב הזה) ולכן זו החלטה מודעת של המנכ״ל, לא תיקון קוד עכשיו.

**שורה תחתונה:** המערכת בטוחה לשימוש בטלגרם. הסיכון היחיד הוא חשיפת הדשבורד —
קביל להריץ כמו שזה **בתנאי** שמאמתים היום שהפורט סגור מאחורי גבול רשת מהימן;
אם לא — צריך לסגור את גבול הרשת לפני שממשיכים.

## מה צריך לעשות

1. **היום, לא-קוד (Ops):** לאמת שפורט `8501` נגיש **רק** דרך גבול מהימן
   (Tailscale/VPN/LAN + חומת-אש בהוסט; עדיף לאגד ל-loopback ולתעל). זהו
   הבקרה המפצה האמיתית — פעולת פריסה, לא שינוי קוד.
2. **רישום קבלה מודעת:** אם (1) מספק לשימוש של מפעיל יחיד — המנכ״ל רושם
   קבלה מפורשת: "לדשבורד אין הזדהות; מוגן רק ע״י גבול רשת X".
3. **Phase עתידי מנוהל (בכפוף לאישור מנכ״ל):** אפיון הזדהות לדשבורד ו/או
   נעילה+תיעוד (audit) של לשונית ה-DB-Manager הכותבת. תוספת — לא לבצע
   באופן חד-צדדי.
4. **ללא פעולה:** R-2 (`/health` ללא PIN) ו-devlog (admin בלבד) — החלטות
   עיצוב מודעות, מתועדות; אין שינוי.

---

## Final report (≤200 words)

C1 is **fully and correctly enforced**: `_require_active_dev_session`
fail-CLOSED guards **all 10** privileged Telegram dev handlers (git
pull+deploy `subprocess`, IBKR sync, XML→Supabase/NAV write — with
defence-in-depth at the write entry, config dump, logs, probe, on-demand
reports), plus the menu-open. Unset `DEV_PIN` now DENIES (S-2 closed);
`DEV_PIN=4915` set in prod. S-3 closed (double-gated). S-4 anchor corrected.
B3 add-on write-race closed (HARDENED refuse, zero-write). Secure_runner is
non-bypassable (class-scope monkeypatch before import; fail-closed admin
gate); production wiring intact. Secrets clean; no SQL/filter injection;
Supabase write boundary respected. All pinned by behavioral tests.

**Not a literal 100/100:** one residual — **R-1: the dashboard on `8501` has
no app auth AND a Supabase trade-WRITE tab** ("DB Manager", `dashboard.py:1391`
updates stops/journal). This is *larger* than Sprint-25 S-12 (write, not just
read) and has **no in-code compensating control** — only the host/network
boundary, which is **undocumented/unverified** here.

**Acceptable to run as-is ONLY IF** Ops confirms today that `8501` is reachable
solely over a trusted boundary (Tailscale/VPN/LAN + firewall) and the founder
records conscious acceptance. If that boundary is unconfirmed/internet-reachable
→ **must be scheduled** (network lockdown now; dashboard-auth as a future
governed, founder-gated Phase — adding auth is an ADDITION, out of this
sprint's no-new-development scope).
