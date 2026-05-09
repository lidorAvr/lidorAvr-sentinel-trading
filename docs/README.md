# Sentinel Trading Documentation Index

This folder is designed for fast onboarding of AI coding agents and future developers.

## Read order for AI agents

1. `../AGENTS.md` — global operating rules for all agents.
2. `../CLAUDE.md` — Claude Code specific context and constraints.
3. `AI_AGENT_CONTEXT.md` — product purpose, user goals, and high-level behavior.
4. `MODULE_MAP.md` — what each code file does and what it affects.
5. `DATA_CONTRACTS.md` — trade, campaign, NAV, market-data, and Telegram output contracts.
6. `SAFE_CHANGE_PROTOCOL.md` — how to make changes without breaking other services.
7. `CHANGE_IMPACT_MATRIX.md` — what to check before changing each area.
8. `TESTING_AND_DEPLOYMENT.md` — test, CI, deploy, smoke-test, and rollback flow.
9. `AGENT_TASK_TEMPLATE.md` — template for planning future agent work.

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
