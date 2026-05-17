# Sprint-26 — Architecture 100/100 Structural-Health Review (DOC-ONLY)

**Date:** 2026-05-17 · **Team:** 🏗️ Architecture (lead) · **Mode:** verification only —
NO code, NO commit, NO features, NO rewrites.
**Live state:** branch HEAD = **`8c5a948`** (all phases deployed: Sprint-25 Wave-2 +
C2 + B3 + Arch-F1 + Engine-P2/P3 + NAV-Unify + the turnkey-runbook deploy-gap fix).

> **Scope note (honest):** the brief cited `c761967` and a
> `SPRINT26_RESEARCH_DOSSIER.md`. Neither exists. `git cat-file c761967` →
> not an object; `docs/teams/SPRINT26_RESEARCH_DOSSIER.md` → absent. This
> review is therefore anchored to the **actual** live HEAD `8c5a948` and
> re-verified directly against source (every claim below is a re-read
> `file:line` on the on-disk tree, working tree clean).

---

## Verdict

**NOT 100/100. Score: 96/100.** The as-built structure is **solid and safe to
keep changing** — the governance machinery is sound, the NAV core is genuinely
unified, all Sprint-25 closable findings landed. The 4 missing points are
**one open structural risk (S26-R1)** + three accepted/recorded debts. No new
HIGH risk introduced by any phase.

---

## What was VERIFIED sound (the 96)

### A. Module boundaries — healthy and improving
- The Telegram layer is genuinely decomposed: `telegram_bot.py` is **1021 lines**
  (down from the historic monolith) with workflows split into
  `telegram_callbacks.py` (391), `telegram_formatters.py` (840, pure — no
  telebot/supabase/engine import, contract held), `telegram_portfolio.py` (530),
  `telegram_tasks.py` (1039), `telegram_menus.py`, `bot_helpers.py`,
  `telegram_clean_gate.py`. The CLAUDE.md "extract helpers, don't rewrite"
  direction is being followed faithfully.
- `account_state.py` remains a clean **stdlib-only leaf** (`os/json/datetime/typing`).
  `engine_core → account_state` is the acyclic direction (verified: account_state
  does NOT import engine_core). **No import cycle.**
- Repository layer (`supabase_repository.py`) exists and is used everywhere except
  the one residual call (S26-R1).

### B. Byte-lock governance machinery — SOUND and maintainable long-term
`tests/_byte_lock_baseline.py` (130 lines) is well-designed and the Sprint-25 A1
redesign is correct:
- **Commit-state-agnostic:** compares on-disk bytes vs a committed
  `tests/_byte_lock_baselines/<file>.baseline` snapshot — no `git`, no index, no
  `merge-base`, no network. This *correctly* fixes the prior fatal flaw (the old
  `git diff`-based lock was **vacuously true on every clean CI checkout** — the
  protection was inert exactly where merges gate).
- **Fail-CLOSED:** a missing baseline raises (`baseline_text`), so the lock can
  never silently pass because its artifact vanished.
- **Two enforcement modes:** hard SHA256 (`assert_byte_identical`, engine_core) +
  difflib allowlist-delta (`baseline_line_delta`, analytics_engine) — the
  allowlist semantics are byte-preserved from the old form.
- **Live integrity re-verified NOW:** `sha256sum` of `engine_core.py`,
  `analytics_engine.py`, `period_data_probe.py` each **MATCHES** its committed
  `.baseline` on the live tree. The governed regeneration ritual (cp + cmp + SHA
  in every PHASE_*_IMPL) was honored on all three baseline-touching phases (C2,
  Engine-P2P3, NAV-Unify).
- **Long-term maintainability:** SOUND. The one structural cost is *operational
  discipline* — every authorized engine/analytics edit MUST manually `cp` the
  baseline; there is no helper and a forgotten regen fails CI loudly (correct
  fail direction). This is a deliberate, documented friction, not a defect.

### C. NAV canonical core (post NAV-Unify) — genuinely unified
Re-read `account_state._resolve_nav_core` (`account_state.py:48-143`): it is the
single canonical resolver. `account_state.load()` is a thin shape-A adapter;
`engine_core.get_nav_with_freshness()` (`engine_core.py:1583`) calls
`account_state._resolve_nav_core(_paths=_CONFIG_PATHS)` and only re-shapes to
shape-B. The Sprint-25 **F1 triple-divergent NAV resolution** (the prior latent
money-risk: bot/risk-monitor vs report pipeline on two different fallback
contracts feeding the SAME risk math) is **CLOSED** — there is now exactly one
fallback/freshness contract (D1 explicit-0 kept, D2 strict-`<`, D3/D4
not-critical). This was the single highest pre-existing structural risk and it
is resolved correctly.

### D. Sprint-25 closable findings — all landed (re-verified in source)
- **F5 dead `/help`:** REMOVED (`telegram_bot.py:657` explanatory comment; the
  duplicate block is gone; the `:568` superset handler is the only live one).
- **F6a dead `import json as _json`:** GONE (no match in `telegram_bot.py`).
- **F3 Add-On campaign_id race (B3):** the planned `campaign_id` is now persisted
  and the confirm path refuses on a divergent re-resolve (verified in
  `telegram_callbacks.py` guard + PHASE_B3_IMPL).
- **C2 side-first classifier / Engine-P2P3 F4 dedup + F5 boundary:** all present
  in source at the documented sites; LOCKED-April fixture path byte-identical.
- **Arch-F1 reader de-dup:** `risk_monitor` imports `bot_helpers.get_account_settings`;
  the byte-identical local copy + bare `except:` are gone.

---

## Structural risks (the −4)

### S26-R1 · MEDIUM · Residual raw Supabase read bypasses the repository layer
**The single highest open structural risk.** Re-verified: `telegram_bot.py:872`
`res = supabase.table("trades").select("*").execute()` is the **only** direct
`.table(` in `telegram_bot.py`, inside `_handle_addon_command`'s open-position
load. `supabase_repository.get_all_trades(sb)` (`supabase_repository.py:22`)
issues the byte-identical query. This is Sprint-24 #6 / Sprint-25 F4 — **still
open**, line drifted `:769 → :872` (B3/NAV-Unify shifts), proving it survived
multiple phases untouched.
**Why it matters:** module-boundary inconsistency on the CLAUDE.md "extract
Supabase repository layer" direction. Read-only (no mutation → AGENTS.md #4
intact), so the risk is **maintainability/predictability**, not data safety: this
one query will not pick up a future repo-level filter / RLS / dedup change that
every other read gets. It is the lowest-blast-radius defect *and* the only one
that is purely structural with zero behavior change.
**Severity:** MEDIUM · value/risk: med / med (fragile file but read-only).
**Recommended future fix:** a governed micro-phase — replace the inline read with
`pd.DataFrame(repo.get_all_trades(supabase))`; pin with a mock-Supabase parity
test (identical query, identical DataFrame). One-line, additive, mirrors the
proven prior repo extractions. **This is the single thing to address next.**

### S26-R2 · LOW (record-only) · `analytics_engine.compute_period_analytics` "never raises" contract leak
`analytics_engine.py:24` computes `t_risk = account_state["nav"] *
account_state["risk_pct_input"] / 100` **before** the `try:`. The docstring +
MODULE_MAP promise "never raises." A caller passing a non-`account_state.load()`
shape (no `nav` key) crashes instead of returning the honest error dict. NOT
triggered in prod today (scheduler + on-demand both pass `acc_mod.load()`), and
**NAV-Unify reduced the likelihood** (one canonical shape now). The in-file fix
is **byte-lock-blocked** (Sprint-19 permanent lock) → cannot be fixed ad hoc.
**Recommended:** record-only this sprint. Any fix MUST be a Mark-gated governed
allowlist expansion (exactly like Wave-2b), never an unauthorized edit. Add a
contract-pinning test that documents current behavior so a future governed fix
has an oracle. No action without founder + lock-expansion sign-off.

### S26-R3 · LOW (record-only) · Numeric-coerce 3-way drift + 21 bare `except:`
- `_coerce_numeric` written 3 divergent ways: `analytics_engine.py:356` (guarded,
  5 cols) · `period_data_probe.py:168` (inline) · `engine_core.py:522` (inline,
  **no `if col in` guard** → different failure contract on a math path). Unifying
  is **OUT** (Engine-owned, byte-locked, Tier-C) — flag the **debt only**;
  Architecture does not duplicate Engine's locked-regression analysis.
- 21 bare `except:` clauses remain across `dashboard.py / engine_core.py /
  risk_monitor.py / telegram_bot.py`. Error-handling is **not consistent**
  repo-wide. This is accepted long-standing debt; the one on the money-path
  config reader was already removed (Arch-F1). No mass sweep proposed (touching
  `engine_core` bare-excepts hits the byte-lock; a broad change is exactly the
  kind of rewrite CLAUDE.md forbids).

### S26-R4 · LOW (ops debt, record-only) · `sentinel_config.json` tracked-AND-gitignored
**Confirmed contradiction:** `git ls-files` lists `sentinel_config.json` **and**
it is line 3 of `.gitignore`. The tracked content (`{... "nav": 7922.18}`, last
committed in the legacy `7ddde34`) is **stale vs the live runtime value**; the
`.gitignore` entry only stops *new* changes from being staged, it does NOT
untrack the already-tracked file. A `git pull` on the Pi can therefore **revert
the live NAV config to a stale committed value** — the precise class of fault
the `.gitignore` comment for `risk_monitor_state.json` documents was already hit
once (Sprint-14 RC-2). NAV is a CLAUDE.md "most fragile area."
**Recommended future fix (governed, ops-owned):** `git rm --cached
sentinel_config.json` in a documented deploy-window phase (file already
gitignored, so a clean untrack) + a runbook note that the live config lives only
on the Pi/volume. **Behavior-bearing on a deploy path → founder + ops-gated, not
done here.** Deploy frictions in `deploy.sh` / `deploy_watcher.sh` themselves
were re-read and are **structurally fine** (`--force-recreate` not `down`,
mandatory IPv4 self-check, honest fail — no fabricated success; the runbook
deploy-gap "recreate ALL affected services" fix is correctly applied).

---

## למנכ״ל — בשפה פשוטה

**האם המערכת בנויה חזק ובטוח להמשיך לשנות אותה? כן — בזהירות.** 96/100.

- **הליבה התקנית טובה.** מנגנון "נעילת הקבצים הקריטיים" (byte-lock) תוקן נכון,
  הוא באמת תופס שינוי לא-מורשה (קודם הוא היה ריק לחלוטין בכל בדיקת CI — זה תוקן),
  וכל שלושת הקבצים הנעולים תואמים *כרגע* לבסיס שלהם.
- **חישוב ה-NAV אוחד.** הסיכון הכי גדול שהיה — שתי דרכים שונות לחשב NAV שמזינות
  את אותו חישוב סיכון — **נסגר**. עכשיו יש מקור אמת אחד.
- **הסיכון המבני העיקרי שנשאר:** קריאה אחת ישירה ל-Supabase ב-`telegram_bot.py`
  שעוקפת את שכבת ה-DB המסודרת (שורה 872). זו קריאת-קריאה בלבד (אין סכנת נתונים),
  אבל היא חריגה מהמבנה ועלולה "לפספס" שינוי עתידי בשכבת ה-DB.
- **חוב משני לתיעוד:** קובץ הקונפיג `sentinel_config.json` גם נעקב ב-git וגם
  ב-gitignore — `git pull` בשרת עלול להחזיר NAV ישן. צריך לטפל בזה בחלון פריסה
  מבוקר.

**המסקנה: בטוח להמשיך לעבוד בשיטה הנוכחית (שלבים קטנים + טסטים). אין לעשות
שכתוב גדול.**

## מה צריך לעשות

1. **הבא בתור (היחיד החשוב מבנית):** פאזה מבוקרת זעירה — להחליף את הקריאה הישירה
   ב-`telegram_bot.py:872` ל-`repo.get_all_trades(...)` + טסט-זהות מול Supabase
   מדומה. שורה אחת, אדיטיבי, סיכון אפס להתנהגות.
2. **ops, בחלון פריסה:** `git rm --cached sentinel_config.json` (כבר ב-gitignore)
   + הערת runbook שהקונפיג חי רק על ה-Pi. דורש אישור מייסד (נוגע בנתיב פריסה).
3. **לתיעוד בלבד (לא לעשות עכשיו):** חוזה "never raises" ב-`analytics_engine`
   (נעול — דורש הרחבת allowlist מבוקרת); 3 הווריאנטים של `_coerce_numeric`
   (Engine, נעול); ניקוי `except:` רחב — אסור לגעת ידנית בקבצים הנעולים.

---

## Explicitly OUT-OF-SCOPE (verified, not re-litigated)
Engine-owned coerce/math unification (Tier-C, byte-locked); any
`analytics_engine.py` / `engine_core.py` executable-line edit; the
`account_state` vs shape-B presentation difference (intentional caller-presentation
D5, NOT a divergence — both now share the canonical core); `telegram_bot.py`
wholesale rewrite; admin/dev-PIN gate; secure_runner import-order invariant
(documented fragility, HARD red line — do NOT "fix" by restructuring);
docker-compose service commands.

## Recommendation
Founder default: **S26-R1 only** (the governed one-line repo-layer micro-phase),
then reassess. S26-R4 next, ops-gated, in a deploy window. S26-R2/R3 stay
record-only until a Mark-gated lock expansion is independently justified.
