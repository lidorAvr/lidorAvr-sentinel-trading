# Sentinel Trading Documentation Index

This folder is designed for fast onboarding of AI coding agents and future developers.

## Read order for AI agents

1. `../AGENTS.md` — global operating rules for all agents.
2. `../CLAUDE.md` — Claude Code specific context and constraints.
3. `SYSTEM_STATE.md` — current truth about production wiring, open validations, and next steps.
4. `USER_REQUIREMENTS.md` — living user requirements and product direction.
5. `AGENT_TASKS.md` — active agent task ledger and progress tracking.
6. `ROADMAP.md` — phased development direction.
7. `AI_AGENT_CONTEXT.md` — product purpose, user goals, and high-level behavior.
8. `MODULE_MAP.md` — what each code file does and what it affects.
9. `DATA_CONTRACTS.md` — trade, campaign, NAV, market-data, and Telegram output contracts.
10. `SAFE_CHANGE_PROTOCOL.md` — how to make changes without breaking other services.
11. `CHANGE_IMPACT_MATRIX.md` — what to check before changing each area.
12. `QUALITY_GATES.md` — minimum checks before code is considered safe.
13. `TESTING_AND_DEPLOYMENT.md` — test, CI, deploy, smoke-test, and rollback flow.
14. `DECISIONS.md` — architecture decision log.
15. `AGENT_TASK_TEMPLATE.md` — template for planning future agent work.
16. `AGENT_PROMPTS.md` — reusable prompts for Claude Code, Codex, and other AI agents.

## Why these docs exist

The repo includes multiple connected services:

- trade/account sync
- portfolio/risk engine
- Telegram bot
- dashboard
- risk monitor
- Docker deployment

A change in one file can affect another service. These docs reduce the chance that an AI agent makes a local improvement that breaks portfolio math, Telegram UX, database writes, or production startup.

## Practical rule

Before changing code, an agent should identify:

- affected files
- affected services
- data contracts touched
- tests needed
- rollback path

If a task touches R, NAV, exposure, Supabase writes, Docker service commands, or Telegram authorization, treat it as high risk.

## Token-saving workflow

For future AI sessions, paste this:

```text
Read AGENTS.md, CLAUDE.md, docs/README.md, docs/SYSTEM_STATE.md, docs/USER_REQUIREMENTS.md, and docs/AGENT_TASKS.md first. Then follow docs/SAFE_CHANGE_PROTOCOL.md and docs/QUALITY_GATES.md. Do not ask me to re-explain the project unless a required detail is missing from the docs.
```
