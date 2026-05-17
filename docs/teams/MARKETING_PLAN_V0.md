# Marketing Team — V0 Plan

> **Document type:** strategic groundwork (NOT copywriting)
> **Status:** V0 / draft for founder review
> **Owner:** Marketing Team (newly formed 2026-05-14)
> **Branch:** `claude/review-system-audit-FBZ2h`
> **Confidence level:** medium — based on repo audit + docs; many assumptions need founder validation (see Phase 6)
> **Working principle (per `CLAUDE.md`):** accuracy over confidence. Where data is missing or estimated, this document says so explicitly.

---

## Executive summary

- **Sentinel is technically marketable, operationally not.** The product has real depth (1321 passing tests, 9 production modules across 5 Docker services, Minervini methodology baked into the math) but zero outward-facing marketing surface: no public site, no demo, no logo, no public track record, no pricing.
- **Hebrew-first is both moat and ceiling.** All Telegram UX is RTL Hebrew. This is a defensible niche in Israel but blocks any English-speaking Minervini follower until i18n exists. Founder must decide: stay Hebrew, or dual-language.
- **Minervini brand association is the strongest asset and the biggest legal risk.** `README.md`, `docs/SPRINT_9_PLAN.md`, and `docs/USER_REQUIREMENTS.md` reference Mark Minervini and his methodology as a system pillar. Marketing leverage is huge — but we do **not** know if his name can be used publicly without permission. This is Question #1 for the founder.
- **The product is one sprint away from a "stop building, start trading" milestone** (Sprint 9 → Meeting 10 "Superperformance-ready" per `docs/SPRINT_9_PLAN.md`). Marketing should align Q1 deliverables to that milestone — landing page goes live when the system goes from internal-only to "could-be-shown."
- **The four-rail readiness gap is product (no signup), trust (no track record), compliance (no disclaimer), and demo (no try-before-buy).** None can be solved by marketing alone. We name the owners we need from product/legal in Phase 4.

---

## Phase 1 — Asset inventory

What the project owns today, where it lives, and how usable it is as marketing material.

| Asset | Location | State | Marketing-readiness |
|---|---|---|---|
| **README.md** (English, polished, badges, architecture diagram) | `/README.md` | Polished | **High** — directly usable as the spine of a landing page. Lines 1-43 are already a product narrative; the Docker services table (lines 44-53) sells operational rigor. |
| **CLAUDE.md / AGENTS.md** (operating philosophy: "no silent failures," "truth in user-facing reports") | `/CLAUDE.md`, `/AGENTS.md` | Polished | **Medium** — these are gold for a "principles" page targeting sophisticated buyers, but in current form they're written for AI agents, not customers. Need rewrite. |
| **Methodology pedigree — Mark Minervini SEPA** | `README.md` line 3, `docs/USER_REQUIREMENTS.md` REQ-20260509-005 / REQ-20260510-004 ("Minervini as system mentor") | Embedded in product | **High potential, blocked on legal.** Cannot use publicly until founder clarifies if Minervini name can be cited (see Phase 6 Q1). |
| **Test count + coverage badges** | `README.md` lines 8-9 ("1321 passing", "68.9% coverage") | Polished | **High** — credibility marker for a technical audience. Caveat: per `docs/SYSTEM_AUDIT_2026_05.md` section 3, pure functions are well-covered but integration/Supabase/yfinance paths have gaps. Don't overstate. |
| **System Audit (Hebrew)** | `docs/SYSTEM_AUDIT_2026_05.md` | Raw | **Medium** — internal-language, contains failure modes ("Silent Failures" section 5.1). Could be reframed as "transparent engineering" content marketing, but only if founder is comfortable with that level of openness. |
| **Sprint lessons** | `docs/SPRINT_6_LESSONS.md`, `SPRINT_7_LESSONS.md`, `SPRINT_8_LESSONS.md` | Raw / internal | **Low–Medium** — great raw material for a "build in public" content series. As-is, too internal. |
| **Telegram UX (Hebrew)** | `telegram_bot.py`, `telegram_formatters.py`, `telegram_portfolio.py` | Polished (Hebrew only) | **High for Israeli market.** RTL formatting, hierarchical menus, Hebrew coaching insights, inline-button decision flows (REQ-20260512-001). |
| **Screenshots / demo media** | NONE in repo | **Missing** | **Critical gap.** No PNG/GIF/MP4 anywhere in repo. Need at minimum: 1 Telegram screenshot, 1 dashboard screenshot, 1 morning briefing mock (when Sprint 9 ships it). |
| **Track record / public metrics** | NONE | **Missing** | **Critical gap.** `risk_journal.json`, `risk_recommendations.json` are local runtime files, NOT committed (per `engine_core.py` audit and `docs/USER_REQUIREMENTS.md` REQ-20260509-006). NAV, R-history, win-rate are private. Without anonymization tooling, no public proof exists. |
| **Logo** | NONE | **Missing** | The shield emoji 🛡️ + "Sentinel Trading" is the de facto wordmark. No SVG/PNG/brand mark exists. |
| **Tagline beyond "Sentinel Trading"** | `README.md` subtitle: *"Personal AI-driven portfolio management system implementing Mark Minervini's SEPA methodology — risk-first, R-multiple based, with adaptive sizing and trader development tracking."* | Raw | Strong substance, but 30 words is not a tagline. Needs compression. (Not doing copywriting in this doc — flagged for Q3.) |
| **Domain / website** | None known | **Missing** | Need to verify with founder if `sentinel-trading.com` or `.co.il` is owned. |
| **Public GitHub presence** | `https://github.com/lidorAvr/lidorAvr-sentinel-trading` | Private (license badge says "Private") | Repo is private per README badge line 11. Cannot drive traffic to source. |
| **PDF report templates** | `templates/weekly_report.html.j2`, `monthly_report.html.j2`, `report_base.css` (per `docs/SYSTEM_STATE.md` session 5) | Polished | **High** — a real PDF report is a great lead magnet ("download a sample weekly trading report"). Currently generated for one user only. |
| **Documentation depth** | `docs/` — 35+ files | Polished (for agents) | **Medium** — `docs/MODULE_MAP.md`, `docs/DATA_CONTRACTS.md`, `docs/SAFE_CHANGE_PROTOCOL.md` signal engineering maturity. Useful for B2B / family-office credibility but not for retail. |
| **CI/CD signals** | `.github/workflows/`, `pytest.ini`, branch protection (per README workflow) | Polished | **Medium** — "tests must be green on main" is buyer trust signal for technical buyers. |

### Inventory verdict

We have a **strong technical asset base** (code quality, methodology, documentation) and a **near-empty marketing surface** (no visuals, no proof, no public face, no brand assets). The product is more ready than the brand by an order of magnitude.

---

## Phase 2 — Audience personas

Five candidate personas evaluated. Format: name, bio, portfolio range, pain, what Sentinel uniquely solves, willingness to pay, reach channel.

### Persona A — "Tomer the Tel Aviv momentum trader" (PRIMARY — best current fit)

- **Bio:** 32-45, Hebrew-native, 2-7 years self-directed trading on IBKR, follows Minervini / Mark Douglas / SMB Capital content, trades US stocks while based in Israel.
- **Portfolio size:** $25k–$250k.
- **Current pain:**
  - Loses discipline late in the day; size up after a winner, panic out on a 3-day pullback.
  - Already pays for IBKR PRO data, TradingView Premium, sometimes TC2000. Spreadsheets are out of date.
  - Reads English Minervini books but wants the daily reminders / coaching in Hebrew.
- **What Sentinel uniquely solves:** Hebrew-native Telegram alerts (`telegram_formatters.py` is RTL-correct), adaptive risk ladder enforces sizing discipline (`adaptive_risk_engine.py` RISK_LADDER), 48h settle period (`RISK_SETTLE_HOURS=48`) prevents revenge re-sizing.
- **Willingness to pay:** **$40–$100/month** (already spends $200+/month on tools).
- **Reach channel:** Israeli Telegram groups (e.g., "סוחרים אקטיביים"), Hebrew finance YouTube, Facebook trading communities, IB-Israel meetups.
- **Why primary:** Bot is already in their language, methodology already matches their books, no localization needed.

### Persona B — "Daniel the English-speaking Minervini follower"

- **Bio:** 35-55, US/UK/Canada, member of Minervini Private Access (paid community), reads SEPA / Trade Like a Stock Market Wizard, posts trades to X / Stocktwits.
- **Portfolio size:** $50k–$1M.
- **Current pain:**
  - Wants automated heat-score / ladder enforcement but TraderSync / Edgewonk don't grade by Minervini Trend Template specifically.
  - Discipline drift between conviction and execution.
- **What Sentinel uniquely solves:** 8-criteria Trend Template per position (REQ-20260509-005), R-multiple bucketed by stat_bucket (EP_MANUAL / VCP_MANUAL / ALGO_OBSERVED), state machine (NEW → PROVING → WORKING → RUNNER) tied to Minervini stages.
- **Willingness to pay:** **$60–$150/month** (already paying for Minervini Access, expects polished US-grade tooling).
- **Reach channel:** Minervini's own ecosystem (if endorsed — see Q1), Stocktwits, X #SEPA / $SPY, podcast guest spots.
- **Blocker:** **Bot is Hebrew-only.** Cannot serve this persona until i18n. Estimated 1–2 sprints of work, mostly in `telegram_formatters.py` + new locale layer.

### Persona C — "Rachel the family-office risk analyst"

- **Bio:** 28-40, works at a $50M–$500M family office, oversees discretionary equity sleeves, reports to a managing principal weekly.
- **Portfolio size:** N/A — she oversees, doesn't trade.
- **Current pain:**
  - Manual Excel reports on exposure, R-history, drawdown. Can't audit principals' compliance with sizing rules.
- **What Sentinel uniquely solves:** `audit_logger` 8/8 action types (Sprint 9 Priority 3), every state-changing action logged to Supabase `audit_log`, PDF weekly/monthly reports, "no silent failures" engineering ethos.
- **Willingness to pay:** **$500–$2,500/month per seat** (institutional pricing).
- **Reach channel:** LinkedIn outreach to family-office ops, niche conferences (FamilyOffice Forum), introductions via founder's network.
- **Verdict:** **NOT a near-term fit.** Requires multi-account architecture (currently single-user/ADMIN_CHAT_ID per `bot_core.py`), RLS, SLA, contracts. 12+ months out. Listed for completeness.

### Persona D — "Yossi the swing-trading educator"

- **Bio:** 40-55, runs a paid Hebrew trading course or YouTube channel, 500–5,000 students.
- **Portfolio size:** N/A — looking to resell.
- **Current pain:**
  - Students don't follow rules. He can teach Minervini but can't enforce his curriculum.
- **What Sentinel uniquely solves:** "Coach in a box" — adaptive sizing + Hebrew coaching insights from `generate_minervini_coaching` enforces what he teaches.
- **Willingness to pay:** **Revenue share / bulk seats** ($15–$30 per student/month wholesale, marks up to $50–$80).
- **Reach channel:** Direct outreach — there are maybe 10–20 Hebrew trading educators in Israel. List is tractable.
- **Verdict:** **High-leverage channel partner candidate.** One signed educator = 100–500 users. Lower CAC than direct retail.

### Persona E — "Avi the disciplined long-term investor"

- **Bio:** 45-65, B&H investor, no day-trading, holds VTI / VOO / individual quality names for years.
- **Portfolio size:** $100k–$5M.
- **Current pain:** Wants to know if any single position is dragging the portfolio.
- **What Sentinel uniquely solves:** Almost nothing relevant.
- **Verdict:** **NOT a fit. Reject.** Sentinel is built for active swing/momentum trading (10-state campaign machine, ATR-based trailing stops, earnings risk on 7-day windows). Long-term holders don't need 60-second risk monitoring or Telegram alerts on 2R checkpoints. Targeting them would force product compromises that hurt Personas A/B/D.

### Persona priority ranking

1. **Persona A (Hebrew momentum trader)** — Q1-Q2 primary acquisition target.
2. **Persona D (Hebrew educator)** — Q2-Q3 channel partner (force multiplier).
3. **Persona B (English Minervini follower)** — Q3+, blocked on i18n + on Q1 Minervini-name decision.
4. **Persona C (family office)** — defer to year 2+.
5. **Persona E (long-term investor)** — explicitly out of ICP.

---

## Phase 3 — Positioning

### Category lane

We considered four lanes:

| Lane | Fit | Why / why not |
|---|---|---|
| AI co-pilot | Medium | True (`generate_minervini_coaching`, adaptive recommendations) but the AI-trading category is crowded with overpromise. We'd be one of many. |
| Trading journal | Low | TraderSync / Edgewonk own this lane. Our journal is a side-effect. |
| Risk monitor | **HIGH** | This is what `risk_monitor.py` actually does — 60-second cycle, 13+ alert types, anti-spam state machine. Closest to product truth. |
| **Discipline enforcer** | **HIGHEST** | Adaptive ladder + settle period + state machine + decision logging = "the bot makes you stick to the plan." This is the actual emotional value prop. |

**Recommended lane:** **Discipline enforcer for the Minervini-method trader.** Risk monitor is the *what*; discipline enforcement is the *why*.

### One-sentence positioning

> *"Sentinel is the Hebrew-native risk-and-discipline bot for momentum traders who follow the Minervini method but break their own rules under pressure."*

(One sentence. Naming the target, the lane, the methodology, and the emotional pain — without the legally-loaded "Minervini" word if needed; "Minervini method" is descriptive use and lower risk than "Mark Minervini endorses.")

### Anti-positioning (we are NOT)

1. **We are not a signal service.** Sentinel never tells you what to buy.
2. **We are not an auto-trader.** Sentinel never places an order. The trader executes.
3. **We are not financial advice.** Every report is risk telemetry, not a recommendation. (See Phase 4 compliance gap.)
4. **We are not for buy-and-hold investors.** If you don't have an entry stop and a campaign, we have nothing to monitor.
5. **We are not a backtester.** Per `docs/SPRINT_9_PLAN.md` out-of-scope, no backtesting engine exists.
6. **We are not a broker.** Sentinel reads from IBKR Flex; it does not execute or hold funds.

### Defensible differentiation vs incumbents

| Competitor | What they do well | What Sentinel does that they don't |
|---|---|---|
| **Trade Ideas** | Real-time scanning, AI signals | No per-position state machine, no adaptive risk ladder tied to YOUR rolling performance, no Hebrew UI |
| **TC2000** | Charting + scanning | No risk monitor loop, no decision audit log, no Telegram-native delivery |
| **TraderSync / Edgewonk** | Post-trade journal + analytics | They are *retrospective*. Sentinel is *prospective* — alerts during the trade, not after. Also no adaptive sizing recommendation. |
| **Tradervue** | Sharing + community journal | No live monitoring, no risk basis classification |
| **Generic Telegram bots** | Price alerts | No methodology, no campaign aggregation, no R-multiple, no ladder, no audit |

**Unique differentiators (concrete, from the codebase):**

1. **Adaptive 7-step heat-score risk ladder** (`adaptive_risk_engine.RISK_LADDER`, S9/M21/L50 windowing 50%/30%/20%) — no incumbent computes sizing recommendations from your *own* recent campaigns this way.
2. **48-hour settle period** (`RISK_SETTLE_HOURS=48`) — prevents revenge re-sizing. Behavioral guardrail no competitor has.
3. **10-state campaign machine** (NEW / PROVING / WORKING / PROFIT_PROTECTION / RUNNER / YELLOW_FLAG / BROKEN / DEAD_MONEY / ALGO_OBSERVED / DATA_INCOMPLETE per `engine_core.py`) — alerts on *transitions*, not levels.
4. **Telegram-native, Hebrew-first.** No competitor speaks Hebrew. Period.
5. **"No silent failures" engineering ethos** — REQ-20260509-001 codified; truth suffix injected by `telegram_bot_secure_runner.py`. We can promise this in writing.
6. **Decision audit trail** — every risk-ladder confirm/reject is logged to `risk_journal.json` with reason text. Differentiator for compliance-conscious buyers (Persona C, eventually).
7. **Hard separation of EP_MANUAL / VCP_MANUAL / ALGO_OBSERVED stat buckets** (REQ-20260511-004) — no contamination of discipline stats by algo P&L. Sophisticated buyers will notice.

---

## Phase 4 — Marketing readiness gaps

Concrete list of what blocks a paid go-to-market. Each item names the team that owns it.

### 4.1 Product gaps (Hyperscaler team / Backend)

| Gap | Severity | Owner |
|---|---|---|
| **No signup / onboarding flow.** Today there is one ADMIN_CHAT_ID per `bot_core.py`. New user = manual env var + container restart. | **Blocker** | Hyperscaler |
| **No multi-tenant data model.** Supabase `trades` table has no user_id partition (per `docs/DATA_CONTRACTS.md` review). | **Blocker for paid** | Hyperscaler / Backend |
| **No billing.** No Stripe, no subscription state machine. | **Blocker for paid** | Hyperscaler |
| **No way to bring your own IBKR account.** Flex query token is in `.env` (one user). | **Blocker** | Backend |
| **Single-Orange-Pi deployment.** All 5 services run on one device. Per `README.md`, the host is the founder's Orange Pi 5. Not scalable. | **Blocker for paid** | Hyperscaler / DevOps |

### 4.2 Trust gaps

| Gap | Severity | Owner |
|---|---|---|
| **No public track record.** `risk_journal.json` and `risk_recommendations.json` are local-only. NAV is private. No anonymized export tool exists. | **Critical** | Backend (export tool) + Founder (decision to share) |
| **No customer testimonials.** N=1 user (the founder). | **Critical** | Grow user base first |
| **No third-party endorsement.** Minervini name is referenced internally but no public endorsement exists or is confirmed. | **High** | Founder (Q1) |
| **Repo is private.** Can't offer "look at the code" credibility to technical buyers. | **Medium** | Founder decision (Q2: open-source partial?) |
| **No SLA, no uptime page.** | **Medium** | Hyperscaler |

### 4.3 Compliance gaps

| Gap | Severity | Owner |
|---|---|---|
| **No disclaimer.** Bot delivers risk telemetry that could be construed as investment advice in some jurisdictions. No "not investment advice" footer is in `telegram_formatters.py`. | **Blocker** | Legal + Marketing |
| **No Terms of Service / Privacy Policy.** Bot reads IBKR portfolio data. No data-handling policy is published. | **Blocker** | Legal |
| **Israel Securities Authority (ISA) status unknown.** Is offering a paid tool that recommends position sizing regulated in Israel? Unknown. | **Critical question** | Legal (Q5) |
| **Mark Minervini name usage rights unknown.** Public marketing using his name may require permission. | **Critical question** | Legal + Founder (Q1) |
| **GDPR for EU users.** If any EU customer ever signs up, we need a data processing agreement. | **High when international** | Legal |
| **Audit log isn't a compliance audit log.** `audit_logger` tracks user actions, not regulatory events. Re-purposing for compliance would need legal review. | **Medium** | Legal |

### 4.4 Internationalization gaps

| Gap | Severity | Owner |
|---|---|---|
| **All Telegram strings are Hebrew.** `telegram_formatters.py`, `bot_health.py`, `telegram_portfolio.py`, `telegram_devops.py` — none are externalized. | **Blocker for Persona B** | Backend (extract to locale files) |
| **No English version of the dashboard.** `dashboard.py` mixes Hebrew labels into Streamlit. | **Blocker** | Backend |
| **Reports are Hebrew.** `templates/weekly_report.html.j2` is RTL Hebrew per `docs/SYSTEM_STATE.md`. | **Blocker** | Backend |
| **README is English (good)** — but the product behind it is Hebrew. Mismatch will confuse English visitors. | **High** | Marketing (clarify on landing page) + Backend (i18n) |

**Strategic decision needed:** Hebrew is a *moat* (no competitor speaks it) and a *ceiling* (90% of the world's momentum traders don't speak it). Founder must choose: Hebrew-only forever, or dual-language by Q3. (Q3 founder question.)

### 4.5 Demo gaps

| Gap | Severity | Owner |
|---|---|---|
| **No way to try before buying.** Bot requires real IBKR Flex token + Supabase + container deploy. | **Critical** | Hyperscaler (sandbox) + Backend (synthetic data mode) |
| **No screenshots, no GIFs, no video.** Repo has zero media assets. | **Critical** | Marketing (this team) |
| **No public dashboard demo URL.** `dashboard.py` runs on port 8501 on the Orange Pi — not internet-exposed. | **High** | DevOps + Backend (read-only demo mode) |
| **No sample PDF report on the web.** Weekly/monthly PDF reports exist but are sent only to founder's Telegram. | **High** — easy win | Marketing + Backend (anonymize one report) |
| **No 60-second "what it does" video.** | **High** | Marketing (Q1 deliverable) |

---

## Phase 5 — 6-month marketing roadmap

Quarter-by-quarter. Marketing-only deliverables (product/infra owned by Hyperscaler and Backend teams). Costs are rough estimates in USD; effort is in person-days assuming 1 marketing FTE + 0.25 designer.

### Q1 (months 1-2 from today, 2026-05-14 → ~2026-07-14) — Foundation

**Theme:** "Tell one person what this is, in one place, with one screenshot." Synchronize with Sprint 9 Meeting 10 "Superperformance-ready" milestone.

| # | Deliverable | Owner | Effort | $ cost |
|---|---|---|---|---|
| Q1.1 | **Landing page V0** (Hebrew, single page, 5 sections: what / who-for / how / proof / signup-waitlist) hosted on Vercel or Netlify free tier | Marketing + freelance designer | 5 days | $500 (domain $20 + designer $480) |
| Q1.2 | **First media kit:** 3 Telegram screenshots (`/portfolio`, regime report, runner alert), 1 dashboard screenshot (anonymized), 1 logo SVG | Marketing + designer | 3 days | $400 |
| Q1.3 | **One anonymized PDF report** (weekly) as downloadable lead magnet | Marketing + Backend (anonymize script) | 2 days | $0 (internal) |
| Q1.4 | **Legal foundation:** ToS draft, Privacy Policy draft, "not investment advice" disclaimer, Minervini-name decision (Q1 founder Q1) | Legal + Marketing | 5 days | $1,500–$3,000 (Israeli lawyer one-time) |
| Q1.5 | **Waitlist setup** (Mailchimp / ConvertKit free tier, max 1000 signups) | Marketing | 1 day | $0 |
| Q1.6 | **Brand bible V0:** one-pager — name origin, tone (Hebrew direct + RTL friendly per CLAUDE.md), do/don't list | Marketing | 1 day | $0 |

**Q1 exit criteria:**
- Landing page is live with a real URL.
- Anyone who lands can: see what Sentinel is in <10 seconds, download a sample PDF, join the waitlist.
- Legal disclaimer is on every page.
- Founder has answered Q1, Q3, Q5 from Phase 6.

**Q1 total cost estimate:** ~$2,400–$3,900.

### Q2 (months 3-4, ~2026-07-14 → ~2026-09-14) — First paid users

**Theme:** "Convert 5 of Tomer's friends to paying users by hand."

| # | Deliverable | Owner | Effort | $ cost |
|---|---|---|---|---|
| Q2.1 | **5 manual onboardings** of Persona A (Hebrew momentum trader). Founder-led white-glove. Document every friction point. | Founder + Marketing notes | 10 days spread over 8 weeks | $0 (concierge) |
| Q2.2 | **Pricing experiment.** Three tiers tested (e.g. $39 / $79 / $149/month) on landing page. Measure waitlist conversion by tier shown. | Marketing | 2 days | $50 (A/B tool) |
| Q2.3 | **First testimonial collection.** 3 short Hebrew quotes + permission to use real name or pseudonym + 1 video testimonial. | Marketing | 3 days | $0 |
| Q2.4 | **Hebrew Telegram presence.** Founder starts posting in 2-3 Israeli trader groups (with group-owner permission — anti-spam ethos). Educational content, not sales. | Founder + Marketing copy support | Ongoing (2 hrs/week) | $0 |
| Q2.5 | **"How the heat score works" deep-dive blog post** (translated from `docs/SYSTEM_AUDIT_2026_05.md` section 2.4 into customer-facing language). | Marketing | 3 days | $0 |
| Q2.6 | **Educator outreach (Persona D).** Identify 10 Hebrew trading educators, send a personal letter to each. Goal: 1 trial integration by end of Q2. | Founder + Marketing | 5 days | $0 |
| Q2.7 | **Demo mode v1** — Backend ships read-only sandbox with synthetic portfolio. Marketing wraps with "try Sentinel" CTA. | Backend (Hyperscaler) + Marketing | 3 days (Marketing only) | $0 |

**Q2 exit criteria:**
- 5 paying users.
- Pricing locked.
- At least 1 educator (Persona D) in pilot.
- Real testimonials on the landing page.

**Q2 total cost estimate:** ~$200 (marketing-only; backend effort is the hidden cost).

### Q3 (months 5-6, ~2026-09-14 → ~2026-11-14) — Scale (Hebrew first, English groundwork)

**Theme:** "From 5 users to 50. Start English groundwork."

| # | Deliverable | Owner | Effort | $ cost |
|---|---|---|---|---|
| Q3.1 | **English landing page** (when Backend ships i18n in Telegram). Soft launch — no paid acquisition yet. | Marketing + designer | 4 days | $400 |
| Q3.2 | **Content engine — Hebrew.** 1 long post/week on heat score, settle period, state machine. SEO targeting Hebrew finance keywords. | Marketing (or contracted writer) | Ongoing | $400/month writer |
| Q3.3 | **Paid acquisition pilot — Israel only.** $500 Meta Ads + $500 Google Ads, target Hebrew finance keywords. Measure CAC per persona. | Marketing | 5 days setup + ongoing | $1,000 ad spend + $0 mgmt |
| Q3.4 | **Affiliate / referral program.** Each existing user gets 1 month free per referral. Educator (Persona D) gets revenue share. | Marketing + Hyperscaler (billing) | 3 days (Marketing) | $0 |
| Q3.5 | **First conference / meetup talk.** Founder presents Sentinel at an Israeli trader meetup. Bring stickers. | Founder + Marketing | 3 days prep | $200 (stickers + travel) |
| Q3.6 | **Reach out to Minervini's team officially** (only if Q1 founder Q1 answer was "yes, eventually"). Goal: explore whether endorsement or affiliate relationship is possible. | Founder + Legal | 1 day | $0 (relationship effort) |
| Q3.7 | **"Build in public" series launch** — once a week, founder publishes one lesson learned (Hebrew, optional English). Source: existing `SPRINT_*_LESSONS.md`. | Founder + Marketing edit | 1 hr/week | $0 |

**Q3 exit criteria:**
- 50 paid users.
- English landing page live.
- CAC measured per channel.
- "Build in public" cadence running for at least 4 weeks.

**Q3 total cost estimate:** ~$2,800 ($1,000 ads + $1,200 writer x 3 months + $400 design + $200 events).

### Roadmap totals

| Quarter | Cash cost (rough) | New paid users target |
|---|---|---|
| Q1 | $2,400 – $3,900 | 0 (waitlist building) |
| Q2 | ~$200 | 5 |
| Q3 | ~$2,800 | 45 (cumulative ~50) |
| **6-month total** | **$5,400 – $6,900** | **50 paid users** |

These numbers assume Hebrew-Israel-only with English groundwork. Going global earlier multiplies all costs roughly 3-5x.

---

## Phase 6 — Open questions for founder (Lidor)

We cannot finalize positioning, pricing, or legal disclaimers without these answers. Ordered by urgency.

### Q1. Will Mark Minervini's name appear publicly in marketing? **[URGENT — blocks Q1]**

- Today, `README.md`, `docs/USER_REQUIREMENTS.md`, and `docs/SPRINT_9_PLAN.md` reference Mark Minervini, his books, and his methodology repeatedly.
- Public marketing using his name (vs. just "SEPA methodology" or "the trend template method") may require permission or risk a cease-and-desist.
- **We need to know:** (a) is there an existing relationship? (b) if no, are you willing to reach out? (c) if neither, can we use "Minervini method" descriptively but not his name/likeness/logo?
- **Why urgent:** Determines whether the landing page hero says *"Trade like Minervini"* or *"Trade momentum with discipline."*

### Q2. Open-source posture? **[Affects trust strategy]**

- Repo is private (`license: Private` per `README.md`). Many technical buyers (Persona B especially) trust open-source signals.
- **Options:** (a) keep fully closed; (b) open-source the `engine_core` math (no Telegram, no Supabase glue) as proof-of-rigor; (c) open-source everything with a non-commercial license.
- **Recommendation we'd push for:** option (b) — protects the moat (the Telegram UX, the deployment, the multi-tenant work) while building trust on the math.

### Q3. Launch geography — Israel only, or global from day one? **[Determines i18n priority]**

- Hebrew-first means Persona A is easy and Persona B is blocked.
- English i18n is 1–2 sprints of Backend work plus translation budget.
- **We need to know:** Is the goal "dominate Israeli market then expand" or "go global, Hebrew is just a starting point"?
- Marketing roadmap above assumes the former.

### Q4. Acceptable price points and free-tier policy? **[Q2 blocker]**

- Persona A research (informal) suggests $40–$100/month tolerance. Persona B tolerates higher.
- **We need to know:** (a) what's the absolute minimum monthly price you'd accept? (b) is a free tier acceptable, and if so, with what limitations (e.g., 1 position, no Telegram alerts)? (c) is annual pricing OK?

### Q5. Israel Securities Authority (ISA) regulatory posture? **[Compliance blocker]**

- Sentinel makes sizing *recommendations* and fires alerts that look like trading nudges.
- Does this count as "investment advice" under Israeli law? In other words: do you need an ISA license to charge for this?
- **We need to know:** Has a lawyer reviewed this? If not, Q1.4 above must include this scope.

### Q6. Single-user vs multi-user — when does Hyperscaler ship multi-tenancy?

- Today: one ADMIN_CHAT_ID, one IBKR Flex token, one NAV in `sentinel_config.json`.
- Marketing Q2 plan assumes manual onboarding of 5 users. That works for 5, not for 50.
- **We need to know:** Hyperscaler's ETA for multi-tenant Supabase + per-user Flex tokens + Stripe billing. This caps how fast marketing can drive traffic in Q3.

### Q7. Are you willing to publish anonymized track record? **[Trust gap]**

- Even one user's anonymized 6-month NAV curve + R-distribution would be the strongest marketing asset we could produce.
- **We need to know:** (a) are you willing to publish your own anonymized stats? (b) if not, what's the lowest-disclosure proof you'd accept (e.g., aggregated win-rate without dollar amounts)?

### Q8. Are you the public face of the product, or do you want to stay anonymous?

- "Build in public" content (Q3.7) only works if there's a person behind it.
- **We need to know:** (a) public LinkedIn / X / Twitter handle? (b) willing to do a podcast? (c) anonymous/pseudonymous OK?

### Q9. Personal brand strategy — Lidor as a Hebrew-trader-thinker?

- Adjacent to Q8 but distinct: would you write essays in Hebrew on momentum trading discipline, separate from Sentinel-the-product? This builds an audience that converts to Sentinel users.
- **We need to know:** willingness to commit 2 hours/week to founder-led content for 12+ months.

### Q10. Do you have a domain or trademark already?

- We assume `sentinel-trading.com` / `.co.il` may or may not be available.
- **We need to know:** (a) any domain reserved? (b) trademark application filed? (c) is "Sentinel Trading" the final name or open to change?

---

## Notes for the next Marketing Team revision

- **This is V0.** Before going to V1, we need answers to at least Q1, Q3, Q5, Q7.
- **Cross-team dependencies are explicit** in Phase 4 (Hyperscaler owns signup, Backend owns i18n, Legal owns disclaimers). Marketing cannot ship Q2 alone.
- **Don't write copy until positioning is locked.** Phase 3 is a hypothesis; once founder answers Q1, the hero line either includes "Minervini" or doesn't, and that changes every other word on the site.
- **Risks not yet addressed:**
  - Competitive risk: if Minervini Private Access or TraderSync ships Hebrew tomorrow, we lose the moat.
  - Product-risk: per `docs/SYSTEM_AUDIT_2026_05.md` section 5, several silent-failure modes still exist. A bad first-week incident with paid users could be fatal.
  - Single-developer-bus-factor risk: founder is the only producer.

End of V0.
