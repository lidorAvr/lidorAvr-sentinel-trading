# Sprint-29 — Review vs the REAL Telegram report: CEO briefing (plain language)

**Date:** 2026-05-18 · 9 teams reviewed the system against the two ACTUAL exported Telegram histories (1,425 real messages) instead of source alone. DOC-ONLY, no code changed, no live financial values in this doc. Exports straddle today's deploy (`tg_report_1` ≈ pre-deploy, `tg_report_2` ≈ post-deploy).

## Why this round mattered
Source-review said "near 100/100". Reviewing the **actual output the trader receives** exposed four serious things source-review could not see — and forced an **honest correction** to a "fixed" claim I made earlier.

## The good (confirmed, protect)
Across all 1,425 real messages the system **never once** presented fallback/stale data as exact truth — the honesty discipline genuinely holds in production. Engine math re-derived clean; LOCKED April byte-identical; ALGO observe-only & segregated exactly as rendered; the on-demand weekly report + חדר-מצב card genuinely delight. These are the model.

## The serious findings (honest, prioritized)

### 1. 🔴🔴 SECURITY — live credentials leak into permanent chat history (URGENT)
The **📋 לוגים** button dumps the raw service-log tail to Telegram with **zero redaction**. On DNS-error windows that tail contains the **live Telegram bot token + the IBKR Flex token**. Admin/PIN-gated to press, but once shown the secret is **permanent** in chat history — and in the two export files you uploaded.
**Your action NOW (not code):** rotate the Telegram bot token + IBKR Flex token; treat the uploaded `*-messages.html` as sensitive; do not press 📋 לוגים until a governed Phase redacts/gates it. (Also L-2: dev-PIN typed as plaintext sits in history; L-3: raw exception text — info only.)

### 2. 🔴 R-ALGO-2 — HONEST CORRECTION: NOT fully closed
I previously reported the recon bug "fixed by deployed ALGO-1". **Correction:** ALGO-1 fixed the *specific* חדר-מצב silently-zero bug (verified in code, test-pinned) — but Research, reading the **post-deploy** export, finds the same command surface STILL shows **two different reconciliation numbers + two different bands** ("פער מהותי" vs "פער נתונים קריטי"), rendered directly above a risk-raise recommendation. A *second* two-surface divergence persists. **So when you run `/portfolio`, the recon may still mismatch — that is this known residual, not a deploy failure.** Needs the next ALGO Phase (R-ALGO-1/4). Engine/Data confirm the math is correct; the divergence is between two presentation surfaces.

### 3. 🔴 The lived stream is a voiceless alert-firehose (UX/Arch P0)
The companion warmth we built (Sprint-27 "🧭 מה עכשיו?") appears **0 times in the 995-message live stream** — only on the on-demand weekly you rarely open mid-burst. Meanwhile the same alert re-fires many times (one campaign 5× in ~65 lines) because the anti-spam de-dups on (symbol+state) and a tiny status flip bypasses the cooldown. The thing built to make it a "personal companion" doesn't reach you when it matters.

### 4. 🟠 Sync reliability (Ops OPS-1/2, pre-existing, HIGH)
The scheduled IBKR sync fails most days (IBKR Flex 1001 + Orange-Pi DNS failures) → you compensate manually → two NAV "truths" on screen (honestly labelled, but unresolved). The same DNS-error log lines are exactly what carry the §1 leaked tokens.

### Smaller / partial
- R-ALGO-3: the honest "מדגם נוכחי: N/50" now reaches the phone (good) — but the misleading hardcoded "L50(50)" literal was left next to it (partial close).
- `✅ ✅ NAV` / `🔴 🟠` doubled glyph: real, new, cosmetic; a test even codifies the bug as correct (must be corrected, not trusted).
- silence ≠ all-clear: still effectively open (0 positive-heartbeat in 1,425).
- Research F5: the on-demand April monthly renders 0/$0 — needs triage (could be data scoping; not yet confirmed a bug).

## מה צריך לעשות (priority order)
1. **🔴 NOW, you (no code):** rotate the Telegram + IBKR tokens; treat the uploaded exports as secret; avoid 📋 לוגים.
2. **Next governed Phase (recommend):** SECURITY L-1 — redact/gate the logs path (highest value÷risk; it's a live exfiltration primitive).
3. **Then, founder-gated Phases (your pick/order):** ALGO Phase-2 = R-ALGO-1/4 (the real two-surface recon + "(all)" leak — closes what Mark originally flagged); the alert-firehose/state-flap de-dup + route the "🧭 מה עכשיו?" voice into the live stream (UX P0); OPS-1/2 sync+DNS reliability; the `✅✅` glyph + its mis-codifying test; finish R-ALGO-3 literal; triage Research F5.

No code was changed this round (review only, as asked). The honesty headline: the system's *soul* (never lie) holds in production; its *reach* (companion voice), *recon consistency*, and *secret hygiene* do not yet — and one of those (tokens in history) needs you today.
