# AGENTS.md

## Project
This repository contains Sentinel Trader, a production trading risk-management and trade-tracking system.

## Mandatory Reading Before Any Task
Before editing code, read:
1. SPECIFICATION.md
2. ARCHITECTURE.md
3. RISK_RULES.md
4. TESTING.md
5. The files directly related to the requested task

## Work Style
- Make small, isolated changes.
- Do not rewrite broad parts of the system.
- Do not edit unrelated modules.
- Prefer tests before logic changes.
- Preserve existing behavior unless explicitly asked to change it.

## Forbidden Actions
- Do not edit secrets, tokens, .env files or production credentials.
- Do not modify production Docker files unless explicitly requested.
- Do not change database schema unless explicitly requested.
- Do not change financial calculations unless explicitly requested.
- Do not mix UI/reporting changes with risk/accounting changes.

## Critical Areas
Changes to these areas require tests:
- R calculations
- PnL calculations
- exposure
- risk governor
- lots engine
- campaign engine
- partial exits
- IBKR sync
- Supabase persistence
- Telegram command execution

## Required Response Before Editing
Before editing files, explain:
1. Which module is affected
2. Which files are likely involved
3. What can break
4. What tests are needed
5. What files should not be touched

## Test Command
Use the available test command if one exists.

If pytest exists, run:
pytest

If there are no tests yet, say that clearly and suggest the first tests to add.
