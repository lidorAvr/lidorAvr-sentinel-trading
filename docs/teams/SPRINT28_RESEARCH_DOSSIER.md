# Sprint-28 — Research Dossier: AS-BUILT post-Sprint-27 (100/100 re-run)

**Status:** DOC-ONLY (no code, no production behavior changed in Sprint-28).
**Prepared by:** Research team, Sprint-28 all-hands.
**Production ref:** `main` / branch HEAD **`168aaa2`** —
`feat(sprint-27): execute Sprint-26 findings`. Prior verified ref:
`9d0c0cc` (Sprint-26 CEO briefing). **Purpose:** the single AS-BUILT
reference every other lead + Mark's hands-on relies on for the Sprint-28
100/100 re-verification, re-mapped from source *including* the Sprint-27
deltas. Maps what is, not what was intended.

---

## 1. Architecture + data-flow map (refreshed, unchanged topology)

### The 6 Docker services (`docker-compose.yml` — all healthy, wiring UNCHANGED by Sprint-27)

| Service | Command | Role | Liveness |
|---|---|---|---|
| `sentinel-bot` | `python3 main.py` | IBKR Flex sync window 07:00–11:00 Asia/Jerusalem; ≤1/clock-hour, ≤5/day; on success imports new XML→Supabase + Telegram backlog ping | heartbeat `/app/state/sentinel_bot_last_cycle` < 1980s |
| `telegram-bot` | `python3 telegram_bot_secure_runner.py` | Runtime guard: admin-only + rate-limit (8 msg/60s, 90s cooldown) + data-source suffix, THEN imports/polls `telegram_bot.py` | thread heartbeat < 180s |
| `dashboard` | `streamlit run dashboard.py` | Streamlit UI port **8501** (Trader Edge Panel, Command Center, Adaptive Risk sidebar) | HTTP `/_stcore/health` |
| `risk-monitor` | `python risk_monitor.py` | 300s loop; state machine + 3-tier anti-spam alerts; `depends_on telegram-bot` | heartbeat < 720s |
| `reporting-service` | `python report_scheduler.py` | 60s poll; weekly Sat 08:30 / monthly 1st 08:40 Israel TZ; analytics→charts→PDF→Telegram | heartbeat < 150s |
| `autoheal` | willfarrell/autoheal (`:latest`, unpinned — Ops O4) | restarts unhealthy `autoheal=true` containers | — |

All app services mount `.:/app` (running code IS the host's checked-out
repo) + share `sentinel_state`. Deploy = `git pull` +
`docker compose up -d --force-recreate` (long-lived Python does NOT
hot-reload the volume). `telegram_bot_secure_runner.py` wiring **verified
byte-unchanged** by Sprint-27.

### Data flow (unchanged)

```
IBKR Flex ─(main.py/ibkr_sync_runner)→ XML → ibkr_trade_importer
                                              │ insert
                                              ▼
                    Supabase `trades`  ◄── telegram_bot.py (journal/backlog
                          │ campaign rows      /quality/stop/addon writes)
                          ▼
   engine_core.py  ── campaign aggregation, R, state machine, ALGO gate
   analytics_engine.py ── period analytics / Expectancy / PF / WR / Net-R
   adaptive_risk_engine.py ── closed campaigns, RISK_LADDER, drawdown auto-cut
        ┌──────────────┼───────────────┐
        ▼              ▼               ▼
   telegram_bot.py   risk_monitor.py  report_scheduler.py
   telegram_portfolio.py  (3-tier      (weekly/monthly PDF
   telegram_callbacks.py   anti-spam)   + summary text)
        └────────► Telegram (Hebrew, RTL, admin-only) ◄────┘

NAV/account-size config: sentinel_config.json (NOW git-untracked + gitignored)
  • report pipeline + DASHBOARD read via account_state.load() (shape A)   ← W1 NEW: dashboard joined this single source
  • bot + risk-monitor read via engine_core.get_nav_with_freshness() (shape B)
  • BOTH delegate classification to the ONE canonical core
    account_state._resolve_nav_core() (post NAV-Unify, unchanged by Sprint-27).
```

---

## 2. Methodology contract the system implements (unchanged — re-pinned)

A discretionary momentum (EP/VCP, Minervini-acknowledged) playbook + an
observer-only ALGO basket. A "personal trading companion": accuracy beats
confidence; no spam, drama, or unsolicited instructions.

- **Campaign truth over rows.** Campaign = one trade idea. `campaign_id` =
  `{SYMBOL}_{firstBUY tradeID}`. Partial sells are NOT new trades.
- **R-multiple.** R = `net_pnl / original_campaign_risk`; denominator is the
  **cent-rounded** (`round(...,2)`, load-bearing — F7) first-BUY basis.
- **Stat-scope segregation (inviolable, AGENTS #8).** WR / Expectancy /
  Avg-Win-R / Avg-Loss-R / PF count **only** `_MANUAL` buckets;
  `ALGO_OBSERVED` = Net-PnL/Net-R only; `DATA_INCOMPLETE` excluded.
- **Position state machine** (10 states): ALGO_OBSERVED, DATA_INCOMPLETE,
  BROKEN, RUNNER, PROFIT_PROTECTION, WORKING, PROVING, YELLOW_FLAG,
  DEAD_MONEY.
- **ALGO oversight (observe-only).** Per-symbol caps QQQ 10/TSLA 7/JPM
  7/PLTR 6/HOOD 6 %; cluster 30/35 %. Never instructs ALGO.
- **Adaptive risk + drawdown auto-cut.** `RISK_LADDER` (authoritative,
  as-built `adaptive_risk_engine.py:20`) = **`[0.25, 0.40, 0.60, 0.85,
  1.15, 1.50, 2.00]`** (7 steps; the doc-drift to `[0.35…2.50]` was
  **corrected to match code by Sprint-27 W4a** — code byte-unchanged).
  30-day realized ≤ −8 % NAV forces risk-pct to the 0.40 floor.
- **3-tier anti-spam.** Tier-1 immediate; Tier-2 once-per-campaign
  (2R/3R/breakeven/sizing-leak<0.65); Tier-3 one Daily Digest 21–22 UTC
  Mon–Fri. Giveback fires only on zone change; BROKEN gates Giveback.
- **Fallback honesty (CLAUDE.md #1).** Any fallback/stale/cached/estimated
  NAV/price must be disclosed on every risk-sensitive surface. **Post-W1
  this now includes the dashboard sidebar** (was the last uncovered
  risk-sensitive surface).

---

## 3. As-built state — Sprint-27 deltas (verified from source @ `168aaa2`)

### W1 — Dashboard NAV honesty (Mark P1-1 + Data D-F1) — LIVE

- NEW pure helper **`dashboard_nav.py`** (`nav_sidebar_render(acc)`,
  stdlib-only, no streamlit/engine import). Gate is **identical** to B1
  `report_renderer._nav_disclosure_lines`: broker_fresh iff
  `nav_source=="broker" AND freshness=="fresh" AND not is_stale AND ok`.
- `dashboard.py:104-118` now reads NAV via the **canonical
  `account_state.load()`** (drops its own bare-`except` `load_settings`
  for the prominent figure — closes the Data D-F1 divergent reader).
  `broker_fresh` → BYTE-IDENTICAL pre-W1 green `st.sidebar.success("🏦 Live
  IBKR NAV: **$X**")`; anything else → `st.sidebar.warning(...)` reusing
  the verbatim `freshness_label` + source.
- Presentation-only; `saved_nav`/`current_acc_size`/`target_risk_usd` and
  every downstream KPI are the same canonical value (D1 explicit-`0` kept
  — intended, not a regression). +24 named tests.

### W2 — Repo-hygiene: untrack live NAV config (Ops O1) — LIVE

- `sentinel_config.json` **removed from git index** (working copy kept);
  `.gitignore:3` now bites → a rollback `git checkout/reset` can no longer
  overwrite the live IBKR NAV. **Verified:** `git ls-files` no longer lists
  it; tracked **`sentinel_config.example.json`** schema template added
  (nav 0.0 / total_deposited 7500 / risk_pct_input 0.5 / nav_updated_at).
- `DEPLOYMENT_RUNBOOK.md §4b` documents the ONE-TIME host untrack-migration
  (backup → `git rm --cached` local → pull → verify → restore-if-needed)
  and forbids `git reset --hard`/`git checkout .` on the prod host. **The
  host migration step is the founder's** (cannot be parent-executed).

### W3 — Companion voice ("🧭 מה עכשיו?") — LIVE, presentation-only

ONE Hebrew verdict+next-step line PREPENDED on three surfaces, derived
ONLY from already-computed signals (zero new computation / data source):

| Surface | File | Signal source | Empty-state disambiguation |
|---|---|---|---|
| Weekly/monthly summary | `report_renderer.py` `whatnow_line()` + `build_summary_text` | existing `compute_verdict` `verdict_class` + B1 broker-fresh gate; `account_state=None`⇒NAV-silent (legacy byte-clean) | `neutral`/0-closed → "זה לא אומר שהכול תקין/לא תקין" |
| Live חדר-מצב/open-book | `telegram_portfolio.py` `handle_portfolio_room` | symbols whose already-computed engine `status` ∈ `("🚨 קריטי","🔴 Broken","🚨 חריגת סיכון אלגו")` (== `risk_monitor.CRITICAL_STATUSES`); existing `nav_stale_label` | `open_pos.empty` → "📭 אין פוזיציות פתוחות כרגע … בדוק סנכרון נתונים" |
| Daily digest | `risk_monitor.py` `_daily_digest_text` | `urgent` set refactored to a list-comp BEFORE the loop (same `state ∈ (BROKEN,RUNNER,PROFIT_PROTECTION)` predicate, same order) | else-branch: "אין פעולה דחופה" (never "הכול תקין") |

Plus **humanized wording** (security/behavior byte-unchanged):
C1 PIN-expiry (`telegram_bot.py:_require_active_dev_session` — still routes
`awaiting_dev_pin`, returns `False`, no TTL/compare touched) and B3
race-refusal (`telegram_callbacks.py` — still zero Supabase write, pending
cleared, `return`). Body numbers byte-identical; 2 existing tests
STRENGTHENED (Sprint-25 §6.1 precedent), not weakened.

### W4 — Housekeeping — LIVE

- **W4a** `docs/MODULE_MAP.md` RISK_LADDER `[0.35…2.50]` → `[0.25…2.00]`
  to match deployed code (DOC-only; code byte-unchanged — verified).
- **W4b** C1 `TestValidSessionUnchanged` self-contained `DEV_PIN` fixture
  (kills the latent CI-lie; test-only, assertions unchanged).
- **W4c** `telegram_bot.py:872` raw `supabase.table("trades").select("*")`
  → `repo.get_all_trades(supabase)` (Arch S26-R1; read-only,
  byte-identical result — `.data or []` ≡ `.data` for the consumer; C1
  guard/admin gate/B3 untouched). +8 parity tests.

### Byte-identical / untouched (verified by `git diff 9d0c0cc 168aaa2`)

- `analytics_engine.py`, `engine_core.py`, `period_data_probe.py`,
  `tests/test_real_data_april_regression.py`, `tests/_byte_lock_baselines/*`,
  `docker-compose.yml`, `telegram_bot_secure_runner.py` — **diff EMPTY**.
- LOCKED April **8 / +$180.49 / WR .375 / PF 2.6262 / excl 2**;
  Sprint-22/23 numbers; every report number on the broker-fresh path.
- Suite: Sprint-27 reports **2088 passed, 0 failed, cov 72.02 % ≥ 67 %**
  (CI-equivalent). 83 test files on disk.

### Still DEFERRED / OUT (NOT closed by Sprint-27)

- **Dashboard :8501 has no app-auth + a WRITE path** (Security S-12 / R-1).
  Sprint-26 escalated this: `dashboard.py:1367-1396` can WRITE
  setup/quality/score to Supabase with no auth/audit. SKIPPED by Sprint-27
  (founder topology/Tailscale decision; addition).
- Engine **F3** NULL/blank `pnl_usd` SELL → silent $0 (founder-gated,
  byte-locked path).
- Migration stray `</content>` tag (D-F2); code-side RISK_LADDER change;
  `analytics_engine` `math.inf`/`99.0` dual-PF convention (by design).
- Ops O4 unpinned `autoheal:latest`; O5 CI/runtime interpreter parity;
  Arch S26-R2/R3 record-only debts.

---

## 4. Sprint-26 finding → closed by Sprint-27? (explicit table)

| Sprint-26 finding | Sev | Closed by Sprint-27? | Evidence / residual |
|---|---|---|---|
| Mark P1-1 / Data D-F1 — dashboard sidebar shows fallback/stale NAV as green "Live" | P1 | **YES** (W1) | `dashboard_nav.py` B1-identical gate; canonical `account_state.load()`; broker-fresh byte-identical; +24 tests |
| Ops O1 — rollback (`git checkout/reset`) wipes live NAV (tracked config) | HIGH | **YES** (W2) | `git rm --cached` confirmed (`git ls-files` clean); example template; runbook §4b host procedure |
| Ops O2 — `git reset --hard` nowhere forbidden in rollback docs | MED | **YES** (W2) | runbook now explicitly forbids `reset --hard`/`checkout .` on host |
| UX P0-1 — no companion "voice"; lede buried | P0 | **YES** (W3) | "🧭 מה עכשיו?" prepended on summary/חדר-מצב/digest |
| UX P0-2 — silence ≠ all-clear never stated | P0 | **YES** (W3) | empty-state lines on report-neutral, `open_pos.empty`, digest else-branch |
| UX P1-2 — C1 PIN friction not humane | P1 | **PARTIAL** (W3) | wording warmed; gate friction (no PIN→full lockout) unchanged by design |
| UX P1-3 — B3 race-refusal blunt | P1 | **YES** (W3) | reframed as protection; zero-write honesty preserved |
| Arch S26-R1 — residual raw Supabase read bypasses repo | MED | **YES** (W4c) | `telegram_bot.py:872`→`repo.get_all_trades`; +8 parity tests |
| Research — RISK_LADDER doc↔code divergence | — | **YES** (W4a) | MODULE_MAP corrected to deployed `[0.25…2.00]` |
| Testing — C1 `TestValidSessionUnchanged` latent CI-lie | P2 | **YES** (W4b) | self-contained `DEV_PIN` fixture |
| Security S-12/R-1 — dashboard :8501 no auth + WRITE path | P1 | **NO** (SKIP) | founder topology decision; `dashboard.py:1367-1396` write path still unauthenticated — **highest residual** |
| Data D-F2 — stray `</content>` in migration 005 | P2 | **NO** (OUT) | migration-OUT, founder-gated |
| Data D-F3 — NULL `pnl_usd` SELL→$0, no counter (== Engine F3) | P2 | **NO** (OUT) | byte-locked engine path, founder-gated |
| Ops O3–O8 / Arch S26-R2/R3 — record-only debts | LOW | **NO** (record-only) | unchanged; not in Sprint-27 scope |
| Engine — 100/100 headline math | — | **N/A (already 100)** | byte-identical; no change needed |

**Net:** every P0/P1 finding routable to a presentation/repo/doc fix was
closed; the single P1 NOT closed is **dashboard :8501 auth (S-12/R-1)** —
a deliberate founder-gated SKIP, not an oversight.

---

## 5. New unknowns Sprint-28 reviewers / Mark must probe

These focus on **regressions Sprint-27 could have introduced** (Sprint-27
added code; Sprint-26 was DOC-only):

1. **W1 dashboard NAV path — the NEW reader-swap.** `dashboard.py` now
   resolves the prominent NAV via `account_state.load()` (shape A) where it
   previously used its own `load_settings`. The OLD `load_settings` is
   *still defined* (`dashboard.py:46-50`) and used elsewhere on the page —
   probe: does any OTHER dashboard figure (Account Settings inputs,
   `current_acc_size`, `fmt_risk_capital_basis` caption,
   Data-Reconciliation) still read the divergent bare-`except` path, so the
   sidebar now disagrees with another box on the same screen? Confirm
   `float(_acc["nav"])` ≡ the old `settings.get("nav", total_deposited,
   7500)` on a real broker config and that D1 explicit-`0` is the only
   intended delta (NOT a silent NAV shift).
2. **W3 companion-line noise / anti-spam regression.** The "🧭 מה עכשיו?"
   line is prepended unconditionally on every summary/חדר-מצב/digest send.
   Probe: does it (a) increase message length past the Telegram
   1024-caption / split thresholds the UX contract guards; (b) change the
   `risk_monitor` `_daily_digest_text` body the dedup/`last_digest_date`
   keys off (verify the `urgent` list-comp refactor is *provably*
   order-identical to the old in-loop append — same set, same order, on a
   mixed-state fixture, not just the happy path); (c) read as nagging when
   the verdict is `strong`/no-critical (the P0-2/P2-1 "companion does not
   nag" invariant)?
3. **W2 untrack side-effects.** `sentinel_config.json` is now gitignored.
   Probe: do any tests, `account_state.load()`, or the CI env depend on a
   *tracked* config existing (CI now has no `sentinel_config.json` →
   `account_state` must fall back honestly, NOT raise)? Verify a fresh
   clone + `sentinel_config.example.json` yields the documented honest
   fallback and that the runbook §4b host procedure cannot itself lose the
   live NAV on an aborted pull. Confirm no other code path writes/reads the
   tracked path assumption.
4. **W3 verdict_class capture change.** `build_summary_text` changed
   `verdict, _ = compute_verdict(...)` → `verdict, verdict_class`. Confirm
   `compute_verdict` truly returns a 4-class value matching
   `_WHATNOW_BY_CLASS` keys for every analytics shape (incl.
   0-closed/PF-∞/all-loss) — an unmapped class silently falls back to
   `"mixed"` wording, which could mislead on a `defensive` period.
5. **W4c repo-swap result parity on the real call site.** `pd.DataFrame(None)
   .equals(pd.DataFrame([]))` is asserted True, but probe the *column dtype*
   path: does `ec.get_open_positions_campaign(pd.DataFrame([]))` behave
   identically to the old `pd.DataFrame(res.data)` when Supabase returns
   `None` vs `[]` vs rows in PROD (the parity test uses mocks)?
6. **Carried unknowns still live** (un-probed by Sprint-27): NAV dual-shape
   A/B still coexists behind the same risk math; F4 `keep="first"` survivor
   on a real duplicate-`trade_id` export; C2 positive-qty SELL never
   field-observed; `pnl_usd` net-of-commission invariant for future
   exports; byte-lock SHA must be re-verified on the **clean committed
   `168aaa2` tree** (not a dirty tree).
7. **Dashboard :8501 unauthenticated WRITE path (S-12/R-1) — UNCHANGED and
   the single largest residual.** Sprint-27 added MORE to the dashboard
   surface (W1) without touching its auth posture. Mark/Security must
   re-confirm the founder's network-boundary (Tailscale/LAN-only)
   acceptance is still the only thing standing between the open `:8501`
   and a real Supabase stop/quality WRITE.

---

## למנכ״ל — סקירה בשפה פשוטה

**מה המערכת הזאת (תזכורת קצרה):** מערכת אישית ש"יושבת לידך" ומנהלת לך את
תמונת-המסחר האמיתית — מושכת אוטומטית את העסקאות מהברוקר, מחשבת לבד רווח/הפסד
וסיכון, מפרידה את המסחר הידני שלך מהאלגו (הסטטיסטיקה נספרת רק על מה שאתה
ניהלת), שולחת לך הודעות קצרות בעברית רק לך, ויש בה בלם-בטיחות שמוריד סיכון
אוטומטית אם הפסדת יותר מ-8% בחודש. הכי חשוב: כשהיא לא בטוחה במספר — היא
אומרת לך את זה במפורש.

**מה השתנה מאתמול (ספרינט-27, כבר חי בפרודקשן):**

1. **המסך (דאשבורד) עכשיו ישר לגבי ה-NAV.** עד אתמול הוא הציג כל NAV
   בקופסה ירוקה "Live" — גם כשזה היה מספר ישן או מספר-גיבוי. עכשיו, רק NAV
   אמיתי וטרי מהברוקר מקבל ירוק; כל השאר מסומן בכתום עם הסבר. בדיוק היושר
   שכבר היה בטלגרם, עכשיו גם במסך.
2. **קובץ ה-NAV החי כבר לא ב-git.** סכנה שהייתה: גלגול-לאחור היה יכול
   למחוק את ה-NAV האמיתי. תוקן — הקובץ הוצא ממעקב-git ומוגן.
3. **קול של מלווה אישי.** הוספנו שורה אחת בראש כל מסך/דוח/סיכום-יומי:
   **"🧭 מה עכשיו?"** — משפט אחד שאומר לך אם צריך לפעול ומה. בלי שום שינוי
   במספרים. גם הניסוח של "פג ה-PIN" ו"עצרתי את החיזוק" רוכך — חם יותר, אבל
   עדיין 100% כן (אומר במפורש שלא נעשתה שום פעולה).
4. **תחזוקה שקטה:** תיקון אי-התאמה בתיעוד, וקריאת-נתונים פנימית עברה לשכבה
   התקנית. אפס שינוי בהתנהגות.

**מה לא תוקן (במכוון, מחכה להחלטה שלך):** הדאשבורד בפורט 8501 עדיין בלי
סיסמה ויכול גם *לכתוב* נתונים — זה בטוח רק אם הוא נגיש אך ורק דרך הרשת
הפרטית שלך (Tailscale/LAN). זו ההחלטה הפתוחה הכי חשובה. כל המספרים הרגישים
(R, NAV, רווח, חשיפה) byte-identical — לא זזו, ונבדקו אוטומטית.

---

*End of dossier. DOC-ONLY; no code or production behavior changed in
Sprint-28.*
