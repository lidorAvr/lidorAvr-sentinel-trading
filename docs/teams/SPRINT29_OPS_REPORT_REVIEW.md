# Sprint-29 — Ops/Infra Review from the ACTUAL Telegram History (DOC-ONLY)

**Scope:** DOC-ONLY. NO code, NO new pipelines. Infer runtime/operational
health purely from the real Telegram exports the trader actually saw.
**Role:** Ops/Infra team lead.
**LIVE ref:** HEAD `09dbec7` (`fix(phase-algo1): R-ALGO-2 recon money-truth
fix + R-ALGO-3 L50 sample honesty`).
**Sources:** `/tmp/tg_report_1.txt` (11469 lines) + `/tmp/tg_report_2.txt`
(4515 lines) — bot menus, live alerts, daily digest, system-health card,
and pasted `sentinel-main` log tails with sync/NAV lines.
**Data-sensitivity:** STRUCTURAL only. NAV/position/P&L figures are NOT
copied in; NAV drift/consistency is described qualitatively.
**Time span observed:** roughly 2026-05-11 → 2026-05-18 — the exports
PREDATE / straddle today's deploy, so each finding is classified
fixed-by-deployed / still-open / new.

---

## Verdict (honest)

**The system is running, but not running *reliably* as the trader
experiences it.** Across the week the operator is doing the work the
automation is supposed to do: the scheduled 07:00–11:00 IBKR window fails
on most days (IBKR Flex error 1001 + host DNS-resolution outages), and the
trader keeps **manually** hitting "IBKR Sync ידני" / "Manual XML upload"
to get fresh trades and NAV in. That manual loop *works* — but it means
the headline NAV the risk/portfolio panels show is frequently a
**manually-set, timestamp-less number** that drifts and disagrees with the
broker-synced NAV shown on the health card and in sync logs. That NAV
freshness/consistency gap — visible to the trader as two different NAVs —
is the single biggest operational signal in the real history.

No crash/Traceback/OOM text reached Telegram. Restarts happened (several
"עולה מחדש"/`v18.0 Active` in one evening) but the bot always came back
and the secure-runner + admin protections were never seen bypassed.

---

## Operational findings — symptom → suspected cause → severity → status

### OPS-1 — HIGH · NAV freshness/consistency the trader actually sees (the headline)

- **Symptom (history):** the portfolio / adaptive-risk panels repeatedly
  render NAV with the literal flag **"אין timestamp (הוגדר ידנית)"** and a
  🟠/🔴 marker — i.e. a manually-set NAV with no age. In the SAME export
  window the system-health card and the `Sync OK` / `NAV updated` log
  lines show a *different*, broker-synced NAV that itself moves between
  consecutive sync events (a real-trade XML upload, then a Flex sync,
  then a later Flex sync each report a materially different NAV; one
  intra-day pair swings by ~$100 then partially reverts on the next
  day's sync). The health card simultaneously shows the broker NAV as
  "עודכן לפני N ש׳" with N seen as large as ~22–23h (stale).
- **Suspected cause:** the 07:00–11:00 scheduled sync mostly fails (see
  OPS-2), so live NAV is not refreshed automatically; the trader sets NAV
  manually / via XML upload, producing a `nav` with no
  `nav_updated_at`. The risk panels source that manual stub while the
  health card sources the last broker file → **two NAV truths surfaced to
  the same trader within minutes.** Inter-sync NAV jumps are real account
  movement *plus* the manual/XML vs Flex source switching, not a math bug
  — but it is indistinguishable from a bug at the trader's eye level.
- **Severity:** HIGH — every R/exposure/sizing line the trader acts on is
  scaled by NAV; a stale/ambiguous NAV silently distorts risk. Touches
  AGENTS.md invariant #1 (no stale-as-truth) and #2 (NAV explainable).
- **Status: STILL-OPEN.** The disclosure is *honest* (it explicitly says
  "הוגדר ידנית" / "עודכן לפני Nש׳" / the Live/Cached footer is present —
  the B1 honesty work is visibly doing its job, GOOD), but the underlying
  reliability gap (no fresh automatic NAV most days) is not closed by the
  HEAD deploy, which is ALGO-recon scoped. Predates today's deploy.

### OPS-2 — HIGH · scheduled IBKR sync window is unreliable; operator carries it manually

- **Symptom:** `Attempting IBKR sync (attempt 1/5)…` → `SendRequest
  error: 1001 (temporary)` or `Failed to resolve
  'www.interactivebrokers.com'/'api.telegram.org' ([Errno -3] Temporary
  failure in name resolution)`, then `Already attempted sync at hour N.
  Waiting for next hour.` — repeated on 05-12, 05-14, 05-15, 05-17,
  05-18. The window often exhausts attempts without a success; the trader
  then runs Manual Sync / Manual XML upload to recover (many "Manual IBKR
  sync result: temporary" + eventual "Manual XML upload OK: N trades").
- **Suspected cause:** two independent transient faults: (a) IBKR Flex
  server-side `ErrorCode 1001` ("Statement could not be generated… try
  again shortly") — external, not ours; (b) **host DNS resolution
  failures on the Orange-Pi** (Errno -3) hitting *both* IBKR and
  `api.telegram.org` — a host networking/DNS problem (the compose
  `dns: 8.8.8.8/1.1.1.1` is set but resolution still intermittently
  fails). The "1/5 then wait an hour" cadence means a transient blip can
  burn the whole 4-hour window.
- **Severity:** HIGH for trust/operability (the automation's core promise
  — fresh trades+NAV each morning — is not kept on most observed days),
  though self-healing via the manual path keeps data eventually correct.
- **Status: STILL-OPEN / NEW-confirmed.** Not addressed by HEAD. The
  retry/Telegram-send code path is fragile under host DNS loss
  (Telegram-send errors mean the trader sometimes does not even get the
  failure notice in real time).

### OPS-3 — MEDIUM · raw internal errors surfaced to Telegram

- **Symptom:** `❌ דוח שבועי (On-Demand) נכשל — שגיאה:
  telegram_not_configured` and `❌ דוח חודשי (On-Demand) נכשל — שגיאה:
  telegram_not_configured`; also `🚨 Sentinel — שגיאה בהערכת פוזיציה …
  evaluate_position_engine נכשל: missing_data` (HOOD, TSLA).
- **Suspected cause:** the `telegram_not_configured` failures coincide
  with the OPS-2 DNS-outage window (the report pipeline could not reach
  the Telegram API and reported it as a config error — a misleading
  message; it was a network outage, not a misconfiguration). The
  `missing_data` engine error is a *contained* per-position skip
  ("הפוזיציה דולגה בסבב זה") — it degrades gracefully and does not crash
  the cycle (GOOD), but the raw function name leaks to the trader.
- **Severity:** MEDIUM — no wrong data, but the messages are alarming and
  the `telegram_not_configured` label actively misdiagnoses a transient
  network fault as a permanent config fault.
- **Status: STILL-OPEN** (message-clarity / error-classification), NOT a
  HEAD-deploy concern.

### OPS-4 — MEDIUM→LOW · PDF weekly-report degradation — FIXED (closure-positive)

- **Symptom (history):** weekly On-Demand returns `✅ דוח שבועי
  (On-Demand) נשלח (PDF דרדור — טקסט מלא נשלח)` — the PDF degrades but
  the **full text report is still delivered**.
- **Cross-ref:** `docs/teams/INCIDENT_20260516_weekly_report.md`
  (WeasyPrint `libgobject-2.0-0` missing → whole weekly run aborted).
- **Assessment:** the export proves the **graceful-degradation fix
  shipped and works** — the report no longer fails entirely when the PDF
  engine is unavailable; the trader still gets the numbers + an honest
  "PDF degraded" note.
- **Status: FIXED-BY-DEPLOYED** (relative to the INCIDENT). The one
  `telegram_not_configured` weekly/monthly failure is a *different*
  cause (OPS-2 network), not the WeasyPrint regression.

### OPS-5 — LOW/INFO · service restarts; no crash text — acceptable

- **Symptom:** on 2026-05-11 several `🔄 מערכת Sentinel עולה מחדש…` /
  `Sentinel v18.0 Active` / `Startup notification sent.` at 16:09, 19:45,
  19:59; bot recovers each time. `Already synced today … Sleeping until
  next cycle` shows the main loop healthy between windows.
- **Suspected cause:** deploy/recreate activity + the OPS-2 DNS-outage
  evening (a restart-triggering network blip), plus `Git pull triggered`
  events the trader ran. `autoheal` (compose `:latest`) plausibly
  recycled an unhealthy container.
- **Severity:** LOW — restarts are visible, bounded, and self-recover; no
  Traceback/OOM/SIGKILL reached Telegram.
- **Status:** EXPECTED behaviour, not a regression. (Restart noise to the
  trader is the only UX cost.)

### OPS-6 — LOW · repeat/identical alert pressure — anti-spam mostly holding

- **Symptom:** many `🚨 Sentinel Live Alert` for the same
  symbol/campaign appear in clusters; `📉 Giveback Alert — להדק — ויתור
  מעל 35%` for TSLA fires twice close together as the metric drifts
  within the same band.
- **Assessment:** the bursts are overwhelmingly **on-demand**
  (interleaved with the trader's menu/`/portfolio` taps) — NOT autonomous
  spam. The autonomous path shows a working state machine: ALGO
  Oversight **escalates with state** (15min/3-runs → 25min/5-runs, never
  flat-repeat) and `✅ MRVL — להחזיק … לא ישלח התראות Runner ל-24 שעות`
  confirms per-position dedup/snooze is live. The only weakness: a
  Giveback band can re-fire as the % keeps drifting inside the same band
  (dedup is per-band-cross, not per-band-occupancy).
- **Severity:** LOW — anti-spam invariant (AGENTS.md #7/#15) is
  substantively preserved.
- **Status: STILL-OPEN (minor)** — band-occupancy dedup granularity is a
  nice-to-have, not a regression.

### OPS-7 — INFO · "silence ≠ all-clear" (SPRINT28 P1) — partially MITIGATED in the digest

- **Symptom/observation:** the daily `📋 Sentinel — סיכום יומי` digest
  fires (e.g. 13/05, 15/05) and **ends with an explicit honesty footer**:
  `(ללא פעולה נוספת? הדאשבורד עדכני)` — it actively tells the trader to
  verify on the dashboard rather than implying "no message = all fine".
- **Assessment:** within the *daily digest* path the SPRINT28 P1 concern
  is addressed — there IS a positive heartbeat with a don't-assume-silence
  cue. **But** the gap is not fully closed: on the failed-sync mornings
  the trader's only signal is the `⚠️ ניסיון סנכרון 1/5 נכשל` notice
  (and on DNS-outage days even *that* Telegram send can fail, OPS-2/3) —
  so a silent morning can still mean "monitor could not run / could not
  reach Telegram", which is exactly the P1 risk.
- **Severity:** INFO/LOW — the digest mitigation is real and working;
  the residual is the OPS-2 send-path fragility, tracked there.
- **Status:** P1 PARTIALLY-MITIGATED (digest), residual folded into
  OPS-2.

---

## Verified OK from the history (closure-positive — no action)

- Data-source honesty footer present on portfolio/health output
  ("ℹ️ מקור נתונים: Live/Cached…", explicit "הוגדר ידנית" / "עודכן לפני
  Nש׳" NAV markers) — B1 honesty work visibly functioning.
- Admin/secure-runner: no bypass, no unauthorized-access symptom seen;
  dev menu reachable only via the dev path; CLAUDE.md hard constraint
  intact in `docker-compose.yml` (`telegram_bot_secure_runner.py`).
- Eventual data correctness: every failed scheduled sync is followed by a
  successful manual Sync / XML upload with a sane trade count + NAV; no
  evidence of corrupted or double-counted trades in the surfaced lines.
- Engine errors degrade gracefully ("הפוזיציה דולגה בסבב זה"), cycle
  continues.
- Weekly report PDF-degradation handled gracefully (OPS-4, FIXED).

## Fixed / Open / New summary

| ID | Symptom | Sev | Status |
|----|---------|-----|--------|
| OPS-1 | Manual/stale NAV vs broker NAV — two NAV truths to the trader | HIGH | STILL-OPEN |
| OPS-2 | Scheduled IBKR window unreliable (Flex 1001 + host DNS) | HIGH | STILL-OPEN |
| OPS-3 | Raw `telegram_not_configured`/`evaluate_position_engine` to TG | MED | STILL-OPEN |
| OPS-4 | Weekly PDF degradation | LOW | FIXED-BY-DEPLOYED |
| OPS-5 | Service restarts, no crash text | LOW | EXPECTED |
| OPS-6 | Repeat-alert / band-occupancy dedup | LOW | STILL-OPEN (minor) |
| OPS-7 | Silence≠all-clear (SPRINT28 P1) | INFO | PARTIALLY-MITIGATED |

> None of OPS-1/2/3 is in scope of HEAD `09dbec7` (ALGO recon). They are
> pre-existing operational realities the export makes concrete, not
> regressions introduced by the deploy.

---

## למנכ״ל — בשפה פשוטה

**האם המערכת רצה אמין, כפי שרואים בהיסטוריית ההודעות? לא לגמרי.**
המערכת *באוויר* וכל ההגנות (שומר אדמין, secure-runner) פעילות, אבל לאורך
השבוע **הסנכרון האוטומטי של הבוקר מול IBKR נכשל ברוב הימים** — גם בגלל
תקלה זמנית בצד IBKR וגם בגלל **תקלות רשת/DNS בשרת עצמו** (השרת לפעמים לא
מצליח לפתור כתובות אינטרנט, גם של IBKR וגם של טלגרם). התוצאה: אתה
בעצמך נאלץ ללחוץ ידנית "סנכרון" / להעלות XML כדי להכניס עסקאות ו-NAV
מעודכנים.

**הסיכון התפעולי המרכזי:** בגלל זה, ה-NAV שמופיע במסכי הסיכון/התיק הוא
פעמים רבות **מספר שהוגדר ידנית, בלי חותמת זמן**, והוא לא תמיד מסכים עם
ה-NAV שמגיע מהברוקר (שמוצג במקום אחר עם "עודכן לפני N שעות", לפעמים יותר
מ-22 שעות). כלומר אתה רואה לפעמים *שני NAV שונים* — וכל חישוב סיכון נשען
על המספר הזה. המערכת **כן אומרת לך בכנות** שזה ידני/לא טרי (זה טוב), אבל
חוסר הטריות עצמו לא נפתר.

חדשות טובות: שום קריסה אמיתית לא הגיעה לטלגרם, הבוט תמיד חזר לעצמו,
הדוח השבועי כבר *לא נופל לגמרי* כשאין PDF (הוא שולח טקסט מלא — תוקן),
והסיכום היומי כולל שורה שמזכירה לך לבדוק בדאשבורד ולא להניח ש"שקט = הכל
טוב".

## מה צריך לעשות

1. **(הסיכון הגדול ביותר) לסגור את פער טריות ה-NAV (OPS-1):** לוודא
   שמסכי הסיכון/התיק וה-health card מציגים *אותו* מקור NAV, ושכשה-NAV
   ידני/ישן זה בולט וחוסם החלטות-סיכון שגויות (Phase מבוקר עם טסטים —
   לא נבנה כאן, שינוי מתמטיקת NAV דורש טסטים לפי CLAUDE.md).
2. **לטפל בשורש תקלות הרשת/DNS בשרת (OPS-2):** לבדוק את הגדרת ה-DNS של
   ה-Orange-Pi (resolver/יציבות), ולשפר את לוגיקת ה-retry כך שבליפ זמני
   לא ישרוף את כל חלון 07:00–11:00 (למשל retry צפוף יותר בתוך החלון
   במקום "פעם בשעה").
3. **לתקן את הודעות השגיאה (OPS-3):** למפות כשל-רשת ל"בעיית רשת זמנית"
   במקום `telegram_not_configured` מטעה, ולא לחשוף שמות פונקציה
   (`evaluate_position_engine`) למשתמש.
4. **לקבע גרסת `autoheal` (לא `:latest`)** ולהמשיך לנטר את restart-storm
   כשיש deploy — פריט ישן, עדיין פתוח.
5. **שיפור קל (OPS-6):** dedup לפי *שהייה* בתוך band ולא רק חציית band,
   להפחית כפילות Giveback.

---

**Bottom line:** the real Telegram history says the system *runs and
self-recovers*, but the morning IBKR sync is unreliable (IBKR-1001 +
host DNS failures), so the trader manually keeps NAV fresh — and the
biggest operational signal is the resulting **NAV freshness/consistency
gap**: risk panels often show a manually-set, timestamp-less NAV while
the health card shows a different, sometimes ~22h-stale broker NAV. It is
honestly disclosed (B1 working) but unresolved. Weekly-report PDF
degradation is FIXED; the SPRINT28 P1 silence-gap is partially mitigated
in the daily digest. OPS-1/2/3 are pre-existing and out of HEAD
`09dbec7`'s ALGO scope — STILL-OPEN, not new regressions. No code touched
this sprint (DOC-ONLY).
