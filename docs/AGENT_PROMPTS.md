# Agent Prompt Library

Use these prompts to start future AI-agent sessions with minimal token waste.

## Universal repo onboarding prompt

```text
You are working on my Sentinel Trading repository.
Before editing code, read AGENTS.md, CLAUDE.md, docs/README.md, docs/SYSTEM_STATE.md, docs/USER_REQUIREMENTS.md, and docs/AGENT_TASKS.md.
Follow docs/SAFE_CHANGE_PROTOCOL.md.
Do not rewrite large files.
Do not change R, NAV, exposure, Supabase writes, Docker commands, or Telegram authorization without explaining impact and adding tests.
Start by summarizing what files you need to touch and why.
```

## Small bug fix prompt

```text
Fix this bug with the smallest safe change.
Read AGENTS.md and docs/CHANGE_IMPACT_MATRIX.md first.
Identify affected files and services.
Add or update tests if behavior changes.
Do not refactor unrelated code.
After the fix, update docs/AGENT_TASKS.md with what was done and what remains.
```

## Feature development prompt

```text
Implement the requested feature using the safe change protocol.
First add the requirement to docs/USER_REQUIREMENTS.md.
Then add a task to docs/AGENT_TASKS.md.
Classify the risk level.
Explain affected services and data contracts.
Implement in small commits.
Add tests where logic changes.
Do not bypass telegram_bot_secure_runner.py.
```

## Telegram change prompt

```text
I need a Telegram behavior change.
Read docs/MODULE_MAP.md, docs/DATA_CONTRACTS.md, and docs/SAFE_CHANGE_PROTOCOL.md.
Keep Hebrew output short, clear, and RTL-friendly.
Do not remove admin-only behavior or rate limiting.
Do not add Supabase writes unless explicitly required.
Manually test /portfolio, /next, and /trade CAT after deployment.
```

## Risk math change prompt

```text
I need a risk/math change.
Read docs/DATA_CONTRACTS.md and docs/CHANGE_IMPACT_MATRIX.md.
Do not change R, NAV, exposure, campaign aggregation, or stop logic without deterministic tests.
Create sample trade rows if needed.
Explain old formula, new formula, and migration impact.
```

## Refactor prompt

```text
Refactor only one concern.
Do not change behavior unless explicitly requested.
Add tests around existing behavior first.
Do not mix refactor with new features.
Prefer extracting helpers from telegram_bot.py instead of rewriting it.
Update docs/MODULE_MAP.md if module responsibilities change.
```

## Deployment prompt

```text
Prepare a deployment-safe change.
Check docker-compose.yml and docs/TESTING_AND_DEPLOYMENT.md.
Identify affected service.
Provide exact commands to deploy only the affected service.
Provide rollback command.
Do not change production command routing without explaining impact.
```

## Code review prompt

```text
Review this change as a production-risk reviewer.
Check if it can break Telegram, NAV, risk math, campaign aggregation, Supabase writes, Docker startup, or Hebrew UX.
List required tests and manual checks.
Reject broad rewrites or hidden fallback behavior.
```

## Token-saving context prompt

```text
Do not ask me to re-explain the project.
Use AGENTS.md, CLAUDE.md, docs/SYSTEM_STATE.md, docs/USER_REQUIREMENTS.md, docs/AGENT_TASKS.md, and docs/ROADMAP.md as your context.
Only ask clarifying questions if the docs do not contain the answer and guessing would be risky.
```
