# Testing

## Goal
Every change to financial truth must be protected by tests.

Critical calculations that require tests:
- R calculation
- open R
- closed R
- campaign R
- partial exits
- runner logic
- current risk
- original risk
- exposure
- ALGO caps
- data scope labels

## Initial Test Command
If pytest is available:

pytest

If no tests exist yet, the first development milestone is to create minimal pytest tests for accounting and risk logic.
